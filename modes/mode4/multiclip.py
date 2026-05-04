"""
Несколько клипов на одну цитату: фрагменты → FastGen → склейка + субтитры.
Только один язык вывода (ru или en), не «оба сразу».
"""

from __future__ import annotations

import asyncio
import functools
import json
import re
import shutil
import time
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger
from moviepy import VideoFileClip

from config import settings
from modes.mode4.multiclip_fastgen import generate_parable_clips, regenerate_parable_clip
from modes.mode4.segment_split import (
    split_parable_into_balanced_segments,
    unlink_false_sentence_breaks,
)
from modes.mode4.prompt_agent import run_quote_prompt_agent
from modes.mode4.publishing_metadata import (
    build_fallback_publishing_pair,
    generate_mode4_publishing_pair,
)
from modes.mode4.quote_format import (
    format_quote_caption,
    strip_outer_quote_marks,
    unlink_split_quotes_across_segments,
)
from modes.mode4.video_assembler import assemble_mode4_video
from modes.mode4.video_generator import build_quote_fragment_prompt
from utils.llm import make_llm
from utils.llm_content_filter import is_provider_content_filter_error

QUOTE_MULTICLIP_PLAN = "quote_multiclip_plan.json"


def _session_dir(session_id: str) -> Path:
    return settings.videos_dir / session_id


def load_quote_multiclip_plan(session_id: str) -> dict[str, Any]:
    p = _session_dir(session_id) / QUOTE_MULTICLIP_PLAN
    if not p.is_file():
        raise FileNotFoundError(f"{QUOTE_MULTICLIP_PLAN} not found for this session")
    return json.loads(p.read_text(encoding="utf-8"))


def _save_quote_multiclip_plan(session_id: str, plan: dict[str, Any]) -> None:
    p = _session_dir(session_id) / QUOTE_MULTICLIP_PLAN
    p.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_clip_duration_sec(path: Path) -> float:
    vc = VideoFileClip(str(path))
    try:
        return float(vc.duration or 0.0)
    finally:
        vc.close()


def _normalize_clip_ranges_for_assemble(
    plan: dict[str, Any],
    paths: list[Path],
) -> list[tuple[float, float] | None]:
    trims_raw = plan.get("clip_trims")
    by_index: dict[int, tuple[float, float]] = {}
    if isinstance(trims_raw, list):
        for row in trims_raw:
            if not isinstance(row, dict):
                continue
            try:
                idx = int(row.get("index"))
                a = float(row.get("start_sec"))
                b = float(row.get("end_sec"))
            except Exception:
                continue
            if idx < 0:
                continue
            if b - a < 0.12:
                continue
            by_index[idx] = (a, b)
    out: list[tuple[float, float] | None] = []
    for i, p in enumerate(paths):
        rr = by_index.get(i)
        if rr is None:
            out.append(None)
            continue
        dur = _load_clip_duration_sec(p)
        if dur <= 0.2:
            out.append(None)
            continue
        s = max(0.0, min(float(rr[0]), dur - 0.12))
        e = max(s + 0.12, min(float(rr[1]), dur))
        out.append((s, e))
    return out


def _refs_from_plan(plan: dict[str, Any], session_id: str) -> list[Path]:
    out: list[Path] = []
    for x in plan.get("reference_paths") or []:
        pp = Path(str(x))
        if pp.is_file():
            out.append(pp.resolve())
    if out:
        return out
    root = _session_dir(session_id)
    for name in (
        "mode4_reference_face.jpg",
        "mode4_reference_face.jpeg",
        "mode4_reference_face.png",
        "mode4_reference_face.webp",
    ):
        p = root / name
        if p.is_file():
            return [p.resolve()]
    for p in sorted(root.glob("mode4_reference_face.*")):
        if p.is_file():
            return [p.resolve()]
    return []


def _persist_mode4_reference_image(session_path: Path, photo_src: Path) -> Path:
    """Копия лица в папку сессии — иначе путь из временной загрузки исчезает до перегенерации клипа."""
    src = photo_src.resolve()
    if not src.is_file():
        raise FileNotFoundError(f"Reference image not found: {photo_src}")
    suf = src.suffix.lower()
    if suf not in (".jpg", ".jpeg", ".png", ".webp"):
        suf = ".jpg"
    dest = session_path / f"mode4_reference_face{suf}"
    try:
        shutil.copy2(src, dest)
    except OSError as e:
        logger.warning(f"[Mode4 MC] could not copy reference into session ({e}); using original path")
        return src
    return dest.resolve()


def _multiclip_prompts_from_plan(plan: dict[str, Any]) -> list[str]:
    """Промпты из плана или пересборка из segments (старые планы / сбой записи)."""
    segments = [str(s).strip() for s in (plan.get("segments") or []) if str(s).strip()]
    if len(segments) < 2:
        return []
    raw = plan.get("prompts")
    if (
        isinstance(raw, list)
        and len(raw) == len(segments)
        and all(isinstance(x, str) and str(x).strip() for x in raw)
    ):
        return [str(x) for x in raw]
    master_en = str(plan.get("master_scene_en") or "").strip()
    voice_desc = str(plan.get("voice_description") or "").strip()
    speech_lang = (plan.get("speech_lang") or "ru").strip().lower()
    if speech_lang not in ("ru", "en"):
        speech_lang = "ru"
    n = len(segments)
    return [
        build_quote_fragment_prompt(master_en, seg, voice_desc, i, n, speech_lang)
        for i, seg in enumerate(segments)
    ]


def _resolve_segments(
    script_main: str,
    manual_segments: list[str] | None,
) -> list[str]:
    manual = [s.strip() for s in (manual_segments or []) if str(s).strip()]
    if len(manual) >= 2:
        return unlink_false_sentence_breaks(unlink_split_quotes_across_segments(manual))
    t = " ".join((script_main or "").split())
    if len(t) < 40:
        raise ValueError(
            "Текст слишком короткий для авторазбиения (≥40 символов) или укажите минимум 2 блока вручную"
        )
    raw = split_parable_into_balanced_segments(t, min_n=2, target_chars=96)
    return unlink_false_sentence_breaks(unlink_split_quotes_across_segments(raw))


def _text_is_mostly_cyrillic(s: str) -> bool:
    t = (s or "").strip()
    if not t:
        return False
    cyr = sum(1 for c in t if "\u0400" <= c <= "\u04ff")
    lat = sum(1 for c in t.lower() if "a" <= c <= "z")
    return cyr >= 8 and cyr >= lat


def _scene_bible_from_video_prompt(video_prompt: str) -> str:
    """
    Для multiclip нужен только master scene, без полной реплики из исходного video_prompt.
    Иначе FastGen получает конфликтующие инструкции и может проговорить всю цитату целиком.
    """
    text = " ".join((video_prompt or "").split())
    if not text:
        return ""
    cleaned = text
    cleaned = re.sub(
        r"(?is)\b5\.\s*(?:speech|речь)\s*:.*?(?=\b6\.\s|\Z)",
        " ",
        cleaned,
    )
    cleaned = re.sub(
        r'(?is)\bHe/She begins speaking\b.*?(?=(?:\b6\.\s|period-accurate\b|photorealistic\b|8K\b|vertical 9:16\b|$))',
        " ",
        cleaned,
    )
    cleaned = re.sub(r'(?is)\bsaying:\s*"[^"]+"', " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,;")
    return cleaned or text


async def _translate_ru_to_en(text_ru: str) -> str:
    llm = make_llm(temperature=0.2)
    sys = SystemMessage(
        content=(
            "Translate Russian narration into natural spoken English. "
            "Output only translated text, no notes. "
            "If the source fragment has no sentence-ending punctuation, do not add one."
        )
    )
    human = HumanMessage(content=f"Translate:\n\n{text_ru.strip()}")
    try:
        resp = await asyncio.wait_for(llm.ainvoke([sys, human]), timeout=90.0)
    except Exception as e:
        if not is_provider_content_filter_error(e):
            raise
        logger.warning("[Mode4 MC] EN translate: content filter fallback")
        resp = await asyncio.wait_for(
            llm.ainvoke(
                [
                    SystemMessage(
                        content="Translate Russian text into English for documentary voiceover. Output only translation."
                    ),
                    HumanMessage(content=text_ru.strip()),
                ]
            ),
            timeout=90.0,
        )
    out = (getattr(resp, "content", "") or "").strip()
    return out or text_ru


async def _translate_segments_ru_to_en(segments_ru: list[str]) -> list[str]:
    if not segments_ru:
        return []
    sem = asyncio.Semaphore(4)

    async def _one(seg: str) -> str:
        async with sem:
            return await _translate_ru_to_en(seg)

    return list(await asyncio.gather(*[_one(s) for s in segments_ru]))


async def run_mode4_multiclip_pipeline(
    quote: str,
    person_name: str,
    photo_path: str | Path,
    session_id: str,
    *,
    show_subtitles: bool = True,
    control: dict | None = None,
    only_lang: str = "ru",
    show_author_on_video: bool = True,
    video_header_title: str | None = None,
    manual_segments: list[str] | None = None,
    skip_final_assembly: bool = True,
    subtitle_style: str = "karaoke",
    location_steering_hint: str | None = None,
) -> dict[str, Any]:
    from pipeline_control import checkpoint, fastgen_cancel_event

    output_dir = settings.videos_dir / session_id / "clips"
    output_dir.mkdir(parents=True, exist_ok=True)
    session_path = _session_dir(session_id)
    session_path.mkdir(parents=True, exist_ok=True)

    pn_ru = (person_name or "").strip()
    header_stripped = (video_header_title or "").strip() or None
    speech_lang = (only_lang or "ru").strip().lower()
    if speech_lang not in ("ru", "en"):
        speech_lang = "ru"

    logger.info(f"=== Mode 4 Multiclip | session={session_id} | lang={speech_lang} ===")
    await checkpoint(control)

    logger.info("Step 1/3 - Mode4 Prompt Agent (полная цитата)")
    prompt_data = await run_quote_prompt_agent(
        Path(photo_path),
        quote,
        person_name=pn_ru,
        bilingual=True,
        subtitle_lang="ru",
        auto_detect_lang=False,
        source_russian_only=True,
        location_steering_hint=location_steering_hint,
    )
    script_ru = (prompt_data.get("script_ru") or quote).strip()
    script_en = (prompt_data.get("script_en") or quote).strip()
    person_name_en = (prompt_data.get("person_name_en") or pn_ru).strip()
    quote_caption_ru = format_quote_caption(quote, pn_ru)
    quote_caption_en = format_quote_caption(script_en, person_name_en)

    script_main = script_ru if speech_lang == "ru" else script_en
    author_main = pn_ru if speech_lang == "ru" else person_name_en

    segments = _resolve_segments(script_main, manual_segments)
    if speech_lang == "en" and segments and all(_text_is_mostly_cyrillic(s) for s in segments):
        logger.info("[Mode4 MC] Manual/auto segments are Russian, translating to English for EN speech")
        segments = await _translate_segments_ru_to_en(segments)
    n = len(segments)
    if n < 2:
        raise RuntimeError("[Mode4 Multiclip] Нужно минимум 2 фрагмента")

    master_en = _scene_bible_from_video_prompt(
        (prompt_data.get("video_prompt_en") or prompt_data.get("video_prompt") or "").strip()
    )
    voice_desc = (prompt_data.get("voice_description") or "").strip()
    prompts = [
        build_quote_fragment_prompt(master_en, seg, voice_desc, i, n, speech_lang)
        for i, seg in enumerate(segments)
    ]

    photo = _persist_mode4_reference_image(session_path, Path(photo_path))

    style = (subtitle_style or "karaoke").strip().lower()
    style = "plain_whisper" if style in ("plain_whisper", "plain") else "karaoke"
    plan_dict: dict[str, Any] = {
        "segments": segments,
        "prompts": prompts,
        "speech_lang": speech_lang,
        "master_scene_en": master_en,
        "voice_description": voice_desc,
        "reference_paths": [str(photo)],
        "show_subtitles": bool(show_subtitles),
        "show_author_on_video": bool(show_author_on_video),
        "header_title": header_stripped,
        "quote_caption_ru": quote_caption_ru,
        "quote_caption_en": quote_caption_en,
        "script_ru": script_ru,
        "script_en": script_en,
        "person_name_ru": pn_ru,
        "person_name_en": person_name_en,
        "segmentation_manual": len([s for s in (manual_segments or []) if str(s).strip()]) >= 2,
        "skip_final_assembly": bool(skip_final_assembly),
        "assembled": False,
        "subtitle_style": style,
        "clip_trims": [],
    }
    try:
        _save_quote_multiclip_plan(session_id, plan_dict)
    except Exception as e:
        logger.debug(f"[Mode4 MC] plan save: {e}")

    publishing_task = asyncio.create_task(
        generate_mode4_publishing_pair(
            quote_ru=script_ru,
            person_name_ru=pn_ru,
            quote_en=script_en,
            person_name_en=person_name_en,
        )
    )

    await checkpoint(control)
    logger.info(f"Step 2/3 - Mode4 Multiclip FastGen ({n} clips)")
    video_paths = await generate_parable_clips(
        prompts,
        output_dir,
        [photo],
        cancel_event=fastgen_cancel_event(control),
    )
    valid = [Path(p) for p in video_paths if p and Path(p).exists()]
    if len(valid) < n:
        publishing_task.cancel()
        try:
            await publishing_task
        except asyncio.CancelledError:
            pass
        raise RuntimeError(f"[Mode4 Multiclip] Сгенерировано только {len(valid)}/{n} клипов")

    await checkpoint(control)

    try:
        publishing = await publishing_task
    except asyncio.CancelledError:
        publishing = build_fallback_publishing_pair(script_ru, pn_ru, script_en, person_name_en)
    except Exception as e:
        logger.warning(f"[Mode4 MC] Publishing failed: {e}")
        publishing = build_fallback_publishing_pair(script_ru, pn_ru, script_en, person_name_en)

    try:
        (session_path / "publishing.json").write_text(
            json.dumps(publishing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.debug(f"[Mode4 MC] publishing.json: {e}")

    lang_tag = "EN" if speech_lang == "en" else "RU"
    topic_preview = f"Цитата ({lang_tag}, {n} ч.): {quote[:90]}"

    if skip_final_assembly:
        logger.success(f"=== Mode 4 Multiclip CLIPS READY | {n} files ===")
        return {
            "session_id": session_id,
            "video_path": None,
            "video_paths": [],
            "mode4_multiclip_ready": True,
            "mode4_clip_filenames": [f"clip_{i:03d}.mp4" for i in range(len(valid))],
            "mode4_segments": segments,
            "mode4_clip_trims": list(plan_dict.get("clip_trims") or []),
            "mode4_show_subtitles": bool(show_subtitles),
            "topic": topic_preview,
            "quote_caption": quote_caption_ru,
            "quote_caption_ru": quote_caption_ru,
            "quote_caption_en": quote_caption_en,
            "trend": None,
            "report": None,
            "publishing": publishing,
        }

    logger.info("Step 3/3 - Mode4 Multiclip Assembler (сразу)")
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        functools.partial(
            assemble_mode4_multiclip_final_sync,
            session_id,
            show_subtitles,
        ),
    )
    result["publishing"] = publishing
    result["quote_caption_ru"] = quote_caption_ru
    result["quote_caption_en"] = quote_caption_en
    return result


def assemble_mode4_multiclip_final_sync(
    session_id: str,
    show_subtitles: bool | None = None,
) -> dict[str, Any]:
    plan = load_quote_multiclip_plan(session_id)
    session_path = _session_dir(session_id)
    output_dir = session_path / "clips"
    segments: list[str] = list(plan.get("segments") or [])
    n = len(segments)
    if n < 1:
        raise ValueError("В плане нет фрагментов")

    paths: list[Path] = []
    for i in range(n):
        p = output_dir / f"clip_{i:03d}.mp4"
        if not p.is_file():
            raise FileNotFoundError(f"Нет файла {p.name} — сгенерируйте все фрагменты")
        paths.append(p)
    clip_ranges = _normalize_clip_ranges_for_assemble(plan, paths)

    speech_lang = (plan.get("speech_lang") or "ru").strip().lower()
    if speech_lang not in ("ru", "en"):
        speech_lang = "ru"

    subs_on = plan.get("show_subtitles", True) if show_subtitles is None else bool(show_subtitles)
    header_title = plan.get("header_title")

    whisper_lang = "en" if speech_lang == "en" else "ru"
    whisper_langs = [whisper_lang] * n

    out_path = session_path / ("video_en.mp4" if speech_lang == "en" else "video_ru.mp4")
    style = str(plan.get("subtitle_style") or "karaoke").strip().lower()
    plain_whisper = style in ("plain_whisper", "plain")
    show_auth = bool(plan.get("show_author_on_video", True))
    pn_key = "person_name_en" if speech_lang == "en" else "person_name_ru"
    pn = str(plan.get(pn_key) or "").strip()

    def _spoken_seg(seg: str) -> str:
        t = (seg or "").strip()
        if not show_auth:
            return strip_outer_quote_marks(t)
        return t

    def _sub_line(seg: str) -> str:
        return format_quote_caption(seg, pn, include_quotes=show_auth)

    if subs_on and not plain_whisper:
        subs_list = [_sub_line(str(segments[i])) for i in range(n)]
        spoken_scripts = [_spoken_seg(str(segments[i])) for i in range(n)]
        authors = [pn if show_auth and pn else None for _ in range(n)]
    elif subs_on:
        subs_list = [str(segments[i]).strip() for i in range(n)]
        spoken_scripts = None
        authors = None
    else:
        subs_list = [""] * n
        spoken_scripts = None
        authors = None

    assemble_mode4_video(
        paths,
        subs_list,
        out_path,
        not bool(subs_on and any(str(s).strip() for s in subs_list)),
        spoken_scripts=spoken_scripts,
        authors=authors,
        whisper_languages=whisper_langs if subs_on else None,
        trim_clips_to_whisper_speech=False,
        whisper_vad_filter=not plain_whisper,
        header_title=(str(header_title).strip() if header_title else None) or None,
        plain_timed_subtitles=plain_whisper,
        clip_ranges=clip_ranges,
    )

    video_path = str(out_path.resolve())
    lang_tag = "EN" if speech_lang == "en" else "RU"
    src = (plan.get("script_ru") or "")[:200]
    topic = f"Цитата ({lang_tag}, {n} ч.): {(src or '')[:100] or '…'}"

    from agents.topics_history import mark_topic_used

    pub: dict[str, Any] | None = None
    try:
        pub_path = session_path / "publishing.json"
        if pub_path.is_file():
            pub = json.loads(pub_path.read_text(encoding="utf-8"))
    except Exception:
        pass

    if not plan.get("assembled"):
        mark_topic_used(
            topic=plan.get("quote_caption_ru") or topic,
            session_id=session_id,
            video_path=video_path,
            quote_caption_en=plan.get("quote_caption_en"),
            publishing=pub,
        )
    plan["assembled"] = True
    plan["final_video"] = out_path.name
    plan["show_subtitles"] = subs_on
    try:
        _save_quote_multiclip_plan(session_id, plan)
    except Exception as e:
        logger.debug(f"[Mode4 MC] plan update: {e}")

    logger.success(f"=== Mode4 Multiclip ASSEMBLED | {out_path.name} ===")
    return {
        "session_id": session_id,
        "video_path": video_path,
        "video_paths": [video_path],
        "topic": plan.get("quote_caption_ru") or topic,
        "quote_caption": plan.get("quote_caption_ru") or topic,
        "quote_caption_ru": plan.get("quote_caption_ru"),
        "quote_caption_en": plan.get("quote_caption_en"),
        "mode4_multiclip_ready": False,
        "trend": None,
        "report": None,
        "publishing": None,
    }


async def regenerate_mode4_multiclip_clip(session_id: str, clip_index: int) -> dict[str, Any]:
    plan = load_quote_multiclip_plan(session_id)
    prompts = _multiclip_prompts_from_plan(plan)
    if clip_index < 0 or clip_index >= len(prompts):
        raise ValueError("Некорректный индекс клипа")
    prev_prompts = plan.get("prompts")
    if not isinstance(prev_prompts, list) or len(prev_prompts) != len(prompts):
        plan["prompts"] = prompts
        try:
            _save_quote_multiclip_plan(session_id, plan)
        except Exception as e:
            logger.debug(f"[Mode4 MC] plan save prompts: {e}")
    refs = _refs_from_plan(plan, session_id)
    if not refs:
        raise FileNotFoundError(
            "Референсное фото из плана недоступно на диске. "
            "Если это старая сессия, запустите режим цитаты заново — фото должно сохраняться в папке сессии."
        )
    output_dir = _session_dir(session_id) / "clips"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = await regenerate_parable_clip(
        str(prompts[clip_index]),
        output_dir,
        clip_index,
        refs,
        cancel_event=None,
    )
    if not path:
        raise RuntimeError(f"FastGen не вернул клип {clip_index}")
    return {"ok": True, "index": clip_index, "filename": Path(path).name}


def set_mode4_multiclip_clip_trim(
    session_id: str,
    clip_index: int,
    *,
    start_sec: float,
    end_sec: float,
) -> dict[str, Any]:
    plan = load_quote_multiclip_plan(session_id)
    segments = list(plan.get("segments") or [])
    if clip_index < 0 or clip_index >= len(segments):
        raise ValueError("Некорректный индекс клипа")
    clip_path = _session_dir(session_id) / "clips" / f"clip_{clip_index:03d}.mp4"
    if not clip_path.is_file():
        raise FileNotFoundError(f"Нет файла {clip_path.name}")
    dur = _load_clip_duration_sec(clip_path)
    if dur <= 0.2:
        raise ValueError("Некорректная длительность клипа")
    s = max(0.0, min(float(start_sec), dur - 0.12))
    e = max(s + 0.12, min(float(end_sec), dur))
    trims = list(plan.get("clip_trims") or [])
    out: list[dict[str, Any]] = []
    replaced = False
    for row in trims:
        if not isinstance(row, dict):
            continue
        try:
            idx = int(row.get("index"))
        except Exception:
            continue
        if idx == clip_index:
            out.append({"index": clip_index, "start_sec": round(s, 3), "end_sec": round(e, 3)})
            replaced = True
        else:
            out.append(row)
    if not replaced:
        out.append({"index": clip_index, "start_sec": round(s, 3), "end_sec": round(e, 3)})
    plan["clip_trims"] = sorted(out, key=lambda x: int(x.get("index", 0)))
    _save_quote_multiclip_plan(session_id, plan)
    return {
        "ok": True,
        "index": clip_index,
        "start_sec": round(s, 3),
        "end_sec": round(e, 3),
        "duration_sec": round(dur, 3),
        "clip_trims": list(plan.get("clip_trims") or []),
    }


def clear_mode4_multiclip_clip_trim(session_id: str, clip_index: int) -> dict[str, Any]:
    """Убрать сохранённую обрезку для клипа — в финале снова используется весь файл."""
    plan = load_quote_multiclip_plan(session_id)
    segments = list(plan.get("segments") or [])
    if clip_index < 0 or clip_index >= len(segments):
        raise ValueError("Некорректный индекс клипа")
    trims_in = list(plan.get("clip_trims") or [])
    trims_out: list[dict[str, Any]] = []
    for row in trims_in:
        if not isinstance(row, dict):
            continue
        try:
            idx = int(row.get("index"))
        except Exception:
            continue
        if idx != clip_index:
            trims_out.append(row)
    plan["clip_trims"] = trims_out
    _save_quote_multiclip_plan(session_id, plan)
    return {
        "ok": True,
        "index": clip_index,
        "clip_trims": list(plan.get("clip_trims") or []),
    }
