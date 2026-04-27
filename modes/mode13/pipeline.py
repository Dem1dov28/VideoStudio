"""
Mode 13: загрузка аудио → смена тембра → чанки 5 мин → Whisper по чанку → окна 30 с →
картинки в едином стиле → превью MP4 на чанк → ручная проверка → финальная склейка.
"""

from __future__ import annotations

import asyncio
import functools
import json
from concurrent.futures import ThreadPoolExecutor
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from agents.content_generator.agent import (
    _generate_images_dalle,
    _generate_images_fastgen,
    _generate_images_hf,
)
from agents.video_editor.moviepy_editor import SceneData, assemble_video
from agents.video_editor.whisper_timestamps import get_word_timestamps_from_audio_path
from config import settings
from modes.mode13.voice_transform import transform_voice_to_wav
from utils.ffmpeg_resolve import require_ffmpeg_or_raise
from utils.llm import make_llm
from utils.wav_pcm import slice_wav_time_range, split_wav_to_chunks

MODE13_PLAN = "mode13_plan.json"
CHUNK_SEC_DEFAULT = 300
SEG_SEC_DEFAULT = 30

# Mode 5 outline / book_night: не тянуть премодерн по умолчанию — эпоха из смысла, как у facts50.
VISUAL_POLICY_LONGFORM_FLEX = "longform_flex"

_FALLBACK_STYLE = (
    "Unified cinematic digital illustration, cool teal and warm amber palette, soft diffused light, "
    "vertical portrait composition, painterly detail, editorial clarity."
)
_FALLBACK_STYLE_FASTGEN = (
    "Unified cinematic digital illustration, cool teal and warm amber palette, soft diffused light, "
    "horizontal widescreen landscape composition, painterly detail, editorial clarity."
)

_NEUTRAL_SAFE_VISUAL_FALLBACK = (
    "Calm contemporary public space at golden hour: anonymous adults in everyday clothing on a bench and path, "
    "soft natural light, peaceful mood, no recognizable individuals, no text or signage in focus."
)

# Эпоха из смысла: современные темы → современный визуал; явная древность/средневековье → период без современной техники.
# Раньше отдельный блок «только премодерн» вставлялся в default scene-brief и давал смещение в сторону истории.
_FACTS50_ERA_FLEX_RULES = (
    "Infer the IMPLIED ERA from the scene concept: for present-day geography, travel, cities, science, technology, nature, "
    "food, sports, or general modern culture, depict contemporary photorealistic environments (accurate modern architecture, "
    "current clothing, realistic daylight or golden hour, editorial travel or documentary photography). "
    "For clearly ancient/medieval/early-modern historical subjects, use period-accurate settings without visible modern tech. "
    "Do not default to castles, knights, or generic medieval fantasy when the topic is a broad modern country or mixed facts. "
    "Avoid anachronisms: no medieval villages for obviously modern topics."
)

_UNSAFE_PHRASES_EN = (
    "sexual intercourse",
    "had sex",
    "having sex",
    "have sex",
    "anal sex",
    "oral sex",
    "pornographic",
    "masturbat",
    "blow job",
    "blowjob",
    "hand job",
    "molest",
    "pedoph",
    "child porn",
    "cum on",
    "cum inside",
    "dick in",
    "cock in",
    "boob job",
    " ejacul",
    "clitoris",
    "scrotum",
)

_UNSAFE_BOUNDARY_RE = re.compile(
    r"\b("
    r"sexual|intercourse|nudes?|naked|nude|erotic|porn|nsfw|orgasm|penis|vagina|"
    r"incest|rape|raped|fuck|fucking|masturbat|"
    r"xxx|pussy|tits|whore|slut|bitch|shit|cocksucker|dickhead"
    r")\b",
    re.IGNORECASE,
)

_UNSAFE_PHRASES_RU = (
    "секс",
    "сексуал",
    "порно",
    "эрот",
    "голый",
    "голая",
    "голые",
    "интим",
    "изнасил",
    "половой акт",
    "генитал",
    "мастурб",
    "минет",
    "оральный секс",
)

def _segment_text_flagged_unsafe(text: str) -> bool:
    """Whisper can garble sacred audio into taboo wording; never pass that verbatim to image APIs."""
    if not (text or "").strip():
        return False
    low = text.lower()
    if any(p in low for p in _UNSAFE_PHRASES_EN):
        return True
    if any(p in low for p in _UNSAFE_PHRASES_RU):
        return True
    if _UNSAFE_BOUNDARY_RE.search(text):
        return True
    return False


async def _llm_safe_visual_subject(raw: str) -> str:
    try:
        llm = make_llm(temperature=0.2)
        sys = SystemMessage(
            content=(
                "You turn a short speech-to-text excerpt into ONE safe English phrase (max 40 words) "
                "for an artist's illustration brief. The transcript may contain errors or distorted taboo wording. "
                "Never repeat sexual, violent, or graphic wording. Describe only what can appear in a reverent "
                "PG-rated illustration: setting, clothing era, gestures, lighting, symbolic objects. "
                "Do not make books, scrolls, manuscripts, or pages of text the focus — show people, places, and mood instead. "
                f"{_FACTS50_ERA_FLEX_RULES} "
                "Never use proper names of real historical or religious figures — only generic roles (e.g. a traveler, a mother). "
                "If the source is biblical or sacred, preserve wholesome intent. Output only the phrase, no quotes."
            )
        )
        hum = HumanMessage(content=f"Transcript excerpt:\n\n{raw[:1200]}")
        resp = await asyncio.wait_for(llm.ainvoke([sys, hum]), timeout=45.0)
        out = (getattr(resp, "content", None) or "").strip().strip('"').strip("'")
        if len(out) < 12:
            return _NEUTRAL_SAFE_VISUAL_FALLBACK
        return out[:500]
    except Exception as e:
        logger.warning(f"[Mode13] LLM visual sanitize failed: {e}")
        return _NEUTRAL_SAFE_VISUAL_FALLBACK


def _mode13_image_strategy() -> str:
    return (settings.image_gen_strategy or "hf").lower()


def _mode13_uses_fastgen() -> bool:
    return _mode13_image_strategy() in ("fastgen", "both")


def _normalize_output_format(output_format: str | None, *, default: str = "vertical") -> str:
    fmt = (output_format or default or "vertical").strip().lower()
    return "horizontal" if fmt == "horizontal" else "vertical"


def _image_aspect_ratio_for_format(output_format: str | None) -> str:
    return "16:9" if _normalize_output_format(output_format) == "horizontal" else "9:16"


def _write_mode13_placeholder_image(path: Path, *, aspect_ratio: str) -> None:
    ff = require_ffmpeg_or_raise()  # raises if missing
    size = "1280x720" if str(aspect_ratio).strip() == "16:9" else "720x1280"
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ff,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=#242833:s={size}",
        "-frames:v",
        "1",
        str(path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _mode13_hard_rules_suffix(*, output_format: str | None = None) -> str:
    """Единый блок жёстких ограничений — один раз в конце финального image prompt (без дублирования в intro/style tail)."""
    fmt = _normalize_output_format(output_format, default=settings.mode13_video_format)
    geo = (
        "Horizontal widescreen landscape format (not portrait)."
        if fmt == "horizontal"
        else "Vertical portrait format for short-form video."
    )
    return (
        f"Hard rules (every frame): {geo} "
        "All-ages only. No readable text/UI/logos/watermarks. "
        "No celebrity or politician likeness. "
        "No text-bearing focal props (book pages, scrolls, signs, screens). "
        "One dominant scene only: single uninterrupted frame, no tiled or segmented layout. "
        "Treat any technical wording as metadata only, never as in-image typography. "
        "Avoid table-with-book as hero composition; prioritize lived environments, people, and actions."
    )


def _compose_image_prompt(
    concept_line: str,
    style_suffix: str,
    *,
    output_format: str | None = None,
    visual_policy: str = "default",
    visual_bible: dict[str, Any] | None = None,
) -> str:
    fmt = _normalize_output_format(output_format, default=settings.mode13_video_format)
    era_rules = f"{_FACTS50_ERA_FLEX_RULES} "
    if fmt == "horizontal":
        intro = (
            "Single horizontal widescreen illustration — one concrete filmable scene from this spoken slice; "
            "not a poster, diagram, or infographic, and not a surface meant mainly to display words. "
        )
    else:
        intro = "Single full-frame illustration for a vertical video slide. "
    scene_rules = (
        "Show one concrete scene from the spoken episode. "
        "Prioritize the most filmable location, action, characters, and mood from this exact moment. "
    )
    core = (
        f"{intro}"
        f"{scene_rules}"
        f"{era_rules}"
        "Scene requirements: one primary subject, one visible action, one concrete environment, clear time-of-day or lighting cue. "
        f"Scene to illustrate: {concept_line}. "
        f"Art direction: {style_suffix}"
    ).strip()
    rules = _mode13_hard_rules_suffix(output_format=output_format)
    return f"{core}\n\n{rules}"


_SCENE_BRIEF_FALLBACK = (
    "Calm believable scene matching the spoken mood: everyday figures in a real-world setting, "
    "warm natural light, environment and gesture in focus rather than documents or screens."
)


def _fast_scene_concept_from_raw(raw: str) -> str:
    """Без LLM: короткая вставка для промпта (быстрее, слабее контроль «книга с текстом»)."""
    snippet = " ".join((raw or "").split())[:240]
    return f"Thematic illustrated scene for this spoken passage: {snippet}"


_ABSTRACT_CONCEPT_WORDS = (
    "symbolic",
    "metaphor",
    "metaphorical",
    "conceptual",
    "abstract",
    "mysterious atmosphere",
    "dramatic scene",
    "moody visual",
    "generic",
)

_ACTION_HINT_WORDS = (
    "standing",
    "walking",
    "looking",
    "holding",
    "examining",
    "speaking",
    "sitting",
    "crossing",
    "opening",
    "placing",
    "pointing",
    "reading",
    "writing",
    "watching",
    "gathering",
    "searching",
    "working",
    "разглядывает",
    "идет",
    "стоит",
    "сидит",
    "держит",
)

_LOCATION_HINT_WORDS = (
    "room",
    "street",
    "office",
    "home",
    "archive",
    "desk",
    "table",
    "map",
    "lab",
    "city",
    "field",
    "forest",
    "shore",
    "workshop",
    "station",
    "interior",
    "courtyard",
    "landscape",
)


def _visual_concept_quality_issues(concept: str, *, visual_policy: str) -> list[str]:
    low = (concept or "").lower()
    issues: list[str] = []
    if len(low.strip()) < 32:
        issues.append("too short")
    if any(w in low for w in _ABSTRACT_CONCEPT_WORDS):
        issues.append("too abstract")
    if not any(w in low for w in _ACTION_HINT_WORDS):
        issues.append("no clear action")
    if not any(w in low for w in _LOCATION_HINT_WORDS):
        issues.append("no concrete location")
    if visual_policy == "book_night" and any(
        w in low for w in ("book cover", "open book", "page spread", "library shelf", "reading table")
    ):
        issues.append("book object is hero")
    return issues


def _strip_abstract_visual_words(concept: str) -> str:
    out = concept or ""
    for word in _ABSTRACT_CONCEPT_WORDS:
        out = re.sub(rf"\b{re.escape(word)}\b", "concrete", out, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", out).strip(" ,.;:-")


async def _repair_visual_concept_if_needed(
    concept: str,
    *,
    segment_text: str,
    visual_policy: str,
    series_scene_cue: str | None,
) -> str:
    pol = (visual_policy or "").strip().lower()
    cleaned = _strip_abstract_visual_words(concept)
    issues = _visual_concept_quality_issues(cleaned, visual_policy=pol)
    if not issues:
        return cleaned
    try:
        cue = (series_scene_cue or "").strip()
        policy_rules = ""
        if pol == "book_night":
            policy_rules = (
                "For book_night, choose a lived human scene from the idea, not books/pages/libraries as the subject. "
            )
        elif pol == "unwritten_chapter":
            policy_rules = (
                "For The Unwritten Chapter, choose an evidence-first archival-investigation scene. "
            )
        sys = SystemMessage(
            content=(
                "Rewrite a weak image concept into ONE concrete English scene phrase, max 42 words. "
                "Keep the future final prompt's series style untouched; only improve subject/action/location/time. "
                "Must include: one primary subject, one visible action, one concrete environment, and lighting/time-of-day. "
                "Prefer literal filmable scene from the excerpt over symbolism. "
                f"{policy_rules}"
                "No readable text, no logos, no celebrity likeness, no markdown."
            )
        )
        hum = HumanMessage(
            content=(
                f"Visual policy: {pol or 'default'}\n"
                f"Director cue: {cue or '(none)'}\n"
                f"Weak concept issues: {', '.join(issues)}\n"
                f"Weak concept:\n{cleaned}\n\n"
                f"Narration excerpt:\n{(segment_text or '')[:900]}\n\n"
                "Return only the improved concept phrase."
            )
        )
        llm = make_llm(temperature=0.22, max_tokens=220)
        resp = await asyncio.wait_for(llm.ainvoke([sys, hum]), timeout=45.0)
        fixed = (getattr(resp, "content", None) or "").strip().strip('"').strip("'")
        fixed = _strip_abstract_visual_words(fixed)
        if len(fixed) >= 24 and not _visual_concept_quality_issues(fixed, visual_policy=pol):
            return fixed[:520]
        logger.warning(f"[Mode13] visual concept fixer kept original; issues={issues}, fixed={fixed[:120]}")
    except Exception as e:
        logger.warning(f"[Mode13] visual concept fixer skipped: {e}")
    if "no clear action" in issues:
        cleaned = f"{cleaned}, a generic figure quietly examining the scene"
    if "no concrete location" in issues:
        cleaned = f"{cleaned}, inside a believable real-world environment"
    return cleaned[:520]


def _parse_numbered_scene_phrases(text: str, n: int) -> list[str] | None:
    if n <= 0:
        return []
    found: dict[int, str] = {}
    for ln in (text or "").strip().splitlines():
        ln = ln.strip()
        if not ln:
            continue
        m = re.match(r"^(\d+)[.)]\s*(.+)$", ln)
        if not m:
            continue
        i = int(m.group(1))
        if 1 <= i <= n:
            found[i] = m.group(2).strip().strip('"').strip("'")
    if len(found) != n:
        return None
    return [found[i] for i in range(1, n + 1)]


async def _narration_to_visual_scene_brief_facts50(
    raw: str,
    *,
    series_scene_cue: str | None = None,
    visual_policy: str = "facts50",
) -> str:
    """Бриф кадра: эпоха/сеттинг из смысла (современный нон-фикш, офис, наука — без замка по умолчанию)."""
    try:
        llm = make_llm(temperature=0.32)
        pol = (visual_policy or "").strip().lower()
        mode_rules = ""
        if pol == "book_night":
            mode_rules = (
                "This excerpt belongs to a calm long-form book-night summary. Prefer intimate contemporary "
                "human scenes (habit in action, reflection moment, workplace/home routine, quiet conversation) "
                "over broad generic stock visuals. "
                "No book covers, open pages, library shelf hero shots, or reading-table compositions as subject. "
            )
        elif pol == "unwritten_chapter":
            mode_rules = (
                "This excerpt belongs to an archival investigation documentary. Prefer evidence-first scenes "
                "(archive room, declassified folders, map table, witness environment, period-accurate location trace), "
                "restrained documentary realism, and grounded investigative mood over abstract symbolism. "
            )
        sys = SystemMessage(
            content=(
                "You write ONE English phrase (max 40 words) for a single photorealistic illustration frame in an educational "
                "\"facts\" video. Input may be Russian or English speech-to-text (noisy). "
                "Priority order: (1) exact event/claim in THIS excerpt, (2) concrete place+action+objects, "
                "(3) era and style constraints. Do not reverse this order. "
                "Infer TIME PERIOD from the excerpt: if it is clearly about ancient/medieval/early-modern history, describe a "
                "period-accurate place and people. If it is about modern countries, cities, science, nature, food, travel, or "
                "everyday life without a historical era, show a CONTEMPORARY real-world scene (today's streets, modern buildings, "
                "labs, landscapes as they look now, current fashion as generic figures). "
                "For self-help, leadership, habits, psychology, or business books, prefer contemporary believable settings "
                "(quiet office, home desk at golden hour, park walk, coaching conversation without readable slides, calm symbolic objects) "
                "— never default to medieval markets or castles unless the words clearly demand that era. "
                "Do NOT default to castles, knights, or medieval Europe when the fact is broadly modern. "
                "Describe place, time of day, weather if outdoors, lighting, and key concrete objects; generic people as roles, not celebrity names. "
                "Prefer literal filmable scenes over symbolism; avoid generic stock-like shots unrelated to this exact line. "
                f"{mode_rules}"
                "No books, scrolls, newspapers, screens with readable text as the main subject. "
                "Output only the phrase, no quotes."
            )
        )
        cue = (series_scene_cue or "").strip()
        cue_block = f"\n\nSERIES_SCENE_CUE (from director — obey):\n{cue}\n" if cue else ""
        hum = HumanMessage(content=f"Fact / narration excerpt:\n\n{raw[:1200]}{cue_block}")
        resp = await asyncio.wait_for(llm.ainvoke([sys, hum]), timeout=45.0)
        out = (getattr(resp, "content", None) or "").strip().strip('"').strip("'")
        if len(out) < 10:
            return _SCENE_BRIEF_FALLBACK
        return out[:500]
    except Exception as e:
        logger.warning(f"[Mode13] facts50 narration→visual brief failed: {e}")
        return _SCENE_BRIEF_FALLBACK


async def _narration_to_visual_scene_brief(raw: str) -> str:
    """Turn ASR text into a short English scene description — avoids dumping raw transcript into T2I (book-with-text trope)."""
    try:
        llm = make_llm(temperature=0.3)
        sys = SystemMessage(
            content=(
                "You write ONE English phrase (max 40 words) for a single illustration frame. "
                "Input may be Russian or English speech-to-text (noisy). "
                "Priority order: (1) exact sentence-level meaning of THIS excerpt moment, "
                "(2) concrete place/action/objects, (3) style constraints. "
                "Describe only the most visually specific scene from this exact episode moment: place, time of day, weather if outdoors, "
                "generic people (roles, not names), gestures, lighting, and key concrete objects. "
                "Prefer literal events over abstract symbolism. "
                f"{_FACTS50_ERA_FLEX_RULES} "
                "Do NOT suggest books, open scriptures, scrolls, letters, newspapers, screens with text, subtitles, or any "
                "image where writing is the subject. Illustrate the story as lived environment and figures, not as text on a page. "
                "Do not output broad thematic visuals if they do not match the current sentence-level meaning. "
                "No proper names of real famous or religious figures — generic roles only. Output only the phrase, no quotes."
            )
        )
        hum = HumanMessage(content=f"Narration excerpt:\n\n{raw[:1200]}")
        resp = await asyncio.wait_for(llm.ainvoke([sys, hum]), timeout=45.0)
        out = (getattr(resp, "content", None) or "").strip().strip('"').strip("'")
        if len(out) < 10:
            return _SCENE_BRIEF_FALLBACK
        return out[:500]
    except Exception as e:
        logger.warning(f"[Mode13] narration→visual brief failed: {e}")
        return _SCENE_BRIEF_FALLBACK


async def _narration_to_visual_scene_brief_batch(texts: list[str]) -> list[str]:
    """Один LLM-запрос на несколько сегментов — сильно быстрее полного пайплайна при длинном аудио."""
    n = len(texts)
    if n == 0:
        return []
    if n == 1:
        return [await _narration_to_visual_scene_brief(texts[0])]
    try:
        llm = make_llm(temperature=0.28, max_tokens=min(4096, 32 + 72 * n))
        sys = SystemMessage(
            content=(
                "For each numbered narration excerpt, output ONE English phrase (max 40 words) for an illustration frame. "
                "Excerpts may be Russian or English speech-to-text (noisy). "
                "Each line: the most visually specific scene from that exact excerpt only — place, time, weather if outdoors, "
                "generic people (roles not names), gestures, lighting, objects. Prefer literal episode action over abstract symbolism. "
                f"{_FACTS50_ERA_FLEX_RULES} "
                "Never books, scriptures, scrolls, letters, newspapers, screens with text, or writing as the subject. "
                "No proper names of famous or religious figures. "
                f"Reply with exactly {n} lines, format: 1. phrase  then 2. phrase  etc. No other text."
            )
        )
        blocks = "\n\n".join(f"{i + 1}. {t[:650]}" for i, t in enumerate(texts))
        hum = HumanMessage(
            content=f"Narration excerpts:\n\n{blocks}\n\nOutput {n} numbered lines as specified."
        )
        timeout_s = min(180.0, 35.0 + 12.0 * n)
        resp = await asyncio.wait_for(llm.ainvoke([sys, hum]), timeout=timeout_s)
        body = (getattr(resp, "content", None) or "").strip()
        parsed = _parse_numbered_scene_phrases(body, n)
        if parsed is None:
            logger.warning(f"[Mode13] batch scene brief parse failed ({n} items), falling back to per-segment calls")
            return await asyncio.gather(*[_narration_to_visual_scene_brief(t) for t in texts])
        out: list[str] = []
        for p in parsed:
            out.append(p if len(p) >= 8 else _SCENE_BRIEF_FALLBACK)
        return out
    except Exception as e:
        logger.warning(f"[Mode13] batch scene brief failed ({n} items): {e}")
        return await asyncio.gather(*[_narration_to_visual_scene_brief(t) for t in texts])


async def _segment_text_to_concept(segment_text: str) -> str:
    raw = (segment_text or "").strip()[:900]
    if not raw:
        return "Abstract atmospheric mood matching the spoken word section."
    if _segment_text_flagged_unsafe(raw):
        logger.warning("[Mode13] Transcript flagged for image prompt; using sanitized visual brief")
        return await _llm_safe_visual_subject(raw)
    if bool(getattr(settings, "mode13_scene_brief_skip_llm", False)):
        return _fast_scene_concept_from_raw(raw)
    return await _narration_to_visual_scene_brief(raw)


async def _segment_text_to_concept_facts50(
    segment_text: str,
    *,
    series_scene_cue: str | None = None,
    visual_policy: str = "facts50",
) -> str:
    raw = (segment_text or "").strip()[:900]
    if not raw:
        return "Calm contemporary documentary scene matching the fact theme."
    if _segment_text_flagged_unsafe(raw):
        return await _llm_safe_visual_subject(raw)
    if bool(getattr(settings, "mode13_scene_brief_skip_llm", False)):
        return _fast_scene_concept_from_raw(raw)
    return await _narration_to_visual_scene_brief_facts50(
        raw,
        series_scene_cue=series_scene_cue,
        visual_policy=visual_policy,
    )


async def _resolve_concepts_for_seg_work(
    seg_work: list[tuple[dict[str, Any], dict[str, Any]]],
) -> list[str]:
    """Брифы сцен для всех сегментов: небезопасные — по одному; остальные — пакетами."""
    n = len(seg_work)
    concepts: list[str | None] = [None] * n
    unsafe_jobs: list[tuple[int, str]] = []
    safe_jobs: list[tuple[int, str]] = []

    for idx, (_, seg) in enumerate(seg_work):
        raw = (seg.get("text") or "").strip()[:900]
        if not raw:
            concepts[idx] = "Abstract atmospheric mood matching the spoken word section."
        elif _segment_text_flagged_unsafe(raw):
            unsafe_jobs.append((idx, raw))
        elif bool(getattr(settings, "mode13_scene_brief_skip_llm", False)):
            concepts[idx] = _fast_scene_concept_from_raw(raw)
        else:
            safe_jobs.append((idx, raw))

    llm_n = max(1, min(24, int(getattr(settings, "mode13_prompt_llm_concurrency", 6) or 6)))
    batch_size = max(1, min(24, int(getattr(settings, "mode13_scene_brief_batch_size", 12) or 12)))

    sem = asyncio.Semaphore(llm_n)

    async def _unsafe_one(idx: int, raw: str) -> None:
        async with sem:
            concepts[idx] = await _llm_safe_visual_subject(raw)

    if unsafe_jobs:
        await asyncio.gather(*(_unsafe_one(i, r) for i, r in unsafe_jobs))

    if safe_jobs:
        if batch_size <= 1:

            async def _safe_one(idx: int, raw: str) -> None:
                async with sem:
                    concepts[idx] = await _narration_to_visual_scene_brief(raw)

            await asyncio.gather(*(_safe_one(i, r) for i, r in safe_jobs))
        else:
            batches: list[list[tuple[int, str]]] = [
                safe_jobs[i : i + batch_size] for i in range(0, len(safe_jobs), batch_size)
            ]

            async def _safe_batch(batch: list[tuple[int, str]]) -> None:
                async with sem:
                    texts = [r for _, r in batch]
                    outs = await _narration_to_visual_scene_brief_batch(texts)
                for (idx, _), phrase in zip(batch, outs):
                    concepts[idx] = phrase

            await asyncio.gather(*(_safe_batch(b) for b in batches))

    return [c if c is not None else _SCENE_BRIEF_FALLBACK for c in concepts]


async def _build_image_prompt_async(
    segment_text: str,
    style_suffix: str,
    *,
    extra_suffix: str = "",
    variation_hint: str = "",
    output_format: str | None = None,
    visual_policy: str = "default",
    visual_bible: dict[str, Any] | None = None,
) -> str:
    concept = await _segment_text_to_concept(segment_text)
    concept = await _repair_visual_concept_if_needed(
        concept,
        segment_text=segment_text,
        visual_policy="default",
        series_scene_cue=None,
    )
    body = _compose_image_prompt(
        concept,
        style_suffix,
        output_format=output_format,
        visual_policy="default",
        visual_bible=None,
    )
    parts = [body]
    vh = (variation_hint or "").strip()
    if vh:
        parts.append(vh)
    suf = (extra_suffix or "").strip()
    if suf:
        parts.append(suf)
    return " ".join(parts).strip()


def _session_dir(session_id: str) -> Path:
    return settings.videos_dir / session_id


def _mode13_dir(session_id: str) -> Path:
    d = _session_dir(session_id) / "clips" / "mode13"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _rel_session(session_root: Path, path: Path) -> str:
    return path.resolve().relative_to(session_root.resolve()).as_posix()


def load_mode13_plan(session_id: str) -> dict[str, Any]:
    p = _session_dir(session_id) / MODE13_PLAN
    if not p.is_file():
        raise FileNotFoundError(f"{MODE13_PLAN} not found for session {session_id}")
    return json.loads(p.read_text(encoding="utf-8"))


def _save_mode13_plan(session_id: str, plan: dict[str, Any]) -> None:
    p = _session_dir(session_id) / MODE13_PLAN
    p.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")


def _text_for_window(
    wts: list[tuple[float, float]],
    words: list[str],
    t0: float,
    t1: float,
) -> str:
    parts: list[str] = []
    for (a, b), w in zip(wts, words):
        if b <= t0 or a >= t1:
            continue
        ww = (w or "").strip()
        if ww:
            parts.append(ww)
    return " ".join(parts).strip()


def _windows_for_duration(duration_sec: float, seg_sec: float) -> list[tuple[float, float]]:
    if duration_sec <= 0:
        return []
    out: list[tuple[float, float]] = []
    t = 0.0
    while t < duration_sec - 0.05:
        t1 = min(t + seg_sec, duration_sec)
        out.append((t, t1))
        t = t1
    return out


async def _derive_style_suffix(
    transcript_sample: str,
    *,
    output_format: str | None = None,
    visual_policy: str = "default",
) -> str:
    sample = (transcript_sample or "").strip()[:2000]
    fmt = _normalize_output_format(output_format, default=settings.mode13_video_format)
    if len(sample) < 80:
        return _FALLBACK_STYLE_FASTGEN if fmt == "horizontal" else _FALLBACK_STYLE
    era_hint = _FACTS50_ERA_FLEX_RULES
    try:
        llm = make_llm(temperature=0.35)
        framing = (
            "Frames are horizontal widescreen landscape (not portrait)."
            if fmt == "horizontal"
            else "Frames are vertical portrait for short-form video."
        )
        sys = SystemMessage(
            content=(
                "You define ONE fixed visual art direction for a series of illustrations. "
                f"{framing} "
                "Output 3–6 short English sentences: palette, lighting, brush/texture style, camera mood. "
                "Prefer illustrating events and places as lived scenes rather than documents or pages. "
                "Same style for all slides. "
                f"{era_hint} "
                "No proper names of real famous or historical people — describe era and look only. "
                "No bullet list labels, just prose. "
                "(Final render also receives global hard rules for no text/logos; do not repeat long negative lists here.)"
            )
        )
        pol = (visual_policy or "default").strip()
        hum = HumanMessage(
            content=(
                f"Pipeline visual_policy hint: {pol}.\n\n"
                f"Narration sample (may be Russian or English):\n\n{sample}\n\n"
                "Describe the unified illustration style."
            )
        )
        resp = await asyncio.wait_for(llm.ainvoke([sys, hum]), timeout=120.0)
        text = (getattr(resp, "content", "") or "").strip()
        if len(text) < 40:
            return _FALLBACK_STYLE_FASTGEN if fmt == "horizontal" else _FALLBACK_STYLE
        return text
    except Exception as e:
        logger.warning(f"[Mode13] style LLM failed: {e}")
        return _FALLBACK_STYLE_FASTGEN if fmt == "horizontal" else _FALLBACK_STYLE


async def _generate_one_image(
    prompt: str,
    dest: Path,
    *,
    aspect_ratio: str | None = None,
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    strategy = (settings.image_gen_strategy or "hf").lower()
    out_dir = dest.parent
    stem = dest.stem

    if strategy == "fastgen":
        paths = await _generate_images_fastgen([prompt], out_dir)
        p = paths[0]
    elif strategy == "hf":
        paths = await _generate_images_hf([prompt], out_dir, aspect_ratio=aspect_ratio)
        p = paths[0]
    elif strategy == "dalle":
        paths = await _generate_images_dalle([prompt], out_dir, aspect_ratio=aspect_ratio)
        p = paths[0]
    elif strategy == "both":
        try:
            paths = await _generate_images_fastgen([prompt], out_dir)
            p = paths[0]
        except Exception:
            paths = await _generate_images_dalle([prompt], out_dir, aspect_ratio=aspect_ratio)
            p = paths[0]
    else:
        raise ValueError(f"Unknown IMAGE_GEN_STRATEGY: {strategy}")

    p_path = Path(p)
    if not p_path.is_file():
        raise RuntimeError(
            f"[Mode13] FastGen не сохранил файл изображения (ожидали {p_path}). "
            "Повторите сегмент или уменьшите MODE13_IMAGE_GEN_CONCURRENCY."
        )
    if p_path.resolve() != dest.resolve():
        shutil.move(str(p_path), str(dest))
    return dest


def _slice_audio_segment(chunk_wav: Path, t0: float, t1: float, out_wav: Path) -> None:
    """Без pydub/ffprobe — только PCM через wave."""
    slice_wav_time_range(chunk_wav, t0, t1, out_wav)


def _build_chunk_preview_sync(
    session_id: str,
    chunk_index: int,
    plan: dict[str, Any],
) -> Path:
    session_root = _session_dir(session_id)
    ch = plan["chunks"][chunk_index]
    show_sub = bool(plan.get("show_subtitles", True))
    header_raw = plan.get("header_title")
    header_title = (str(header_raw).strip() if header_raw else "") or None
    scenes: list[SceneData] = []
    for seg in ch["segments"]:
        img = session_root / seg["image"]
        aud = session_root / seg["audio"]
        sub = seg.get("text", "") if show_sub else ""
        if not img.is_file():
            raise FileNotFoundError(f"Missing image: {img}")
        if not aud.is_file():
            raise FileNotFoundError(f"Missing audio segment: {aud}")
        scenes.append(
            SceneData(
                image_path=str(img.resolve()),
                subtitle_text=sub,
                audio_path=str(aud.resolve()),
            )
        )
    out_mp4 = session_root / ch["preview_relpath"]
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    assemble_video(
        scenes,
        out_mp4,
        title=None,
        hook=None,
        outro=None,
        topic=None,
        skip_background_music=True,
        skip_sound_effects=True,
        show_fact_label=False,
        header_title=header_title,
        output_resolution=settings.mode13_video_resolution,
        subtitle_karaoke=False,
        subtitle_static_font_divisor=18,
        ken_burns_per_scene=True,
        ken_burns_intensity=1.75,
    )
    return out_mp4


def _build_all_chunk_previews_parallel(session_id: str, plan: dict[str, Any]) -> None:
    chunks = plan.get("chunks") or []
    if not chunks:
        return
    n = max(1, min(16, int(getattr(settings, "mode13_preview_mp4_workers", 4) or 4)))
    with ThreadPoolExecutor(max_workers=n) as executor:
        futs = [
            executor.submit(_build_chunk_preview_sync, session_id, ci, plan)
            for ci in range(len(chunks))
        ]
        for fut in futs:
            fut.result()


def _ffmpeg_concat(paths: list[Path], output: Path) -> None:
    from utils.ffmpeg_resolve import resolve_ffmpeg_executable

    ff = resolve_ffmpeg_executable()
    if not ff:
        raise RuntimeError(
            "ffmpeg не найден (WinError 2 / «не удается найти указанный файл»). "
            "Установите ffmpeg, добавьте каталог с ffmpeg.exe в PATH системы "
            "или задайте в .env полный путь: FFMPEG_PATH=C:\\\\ffmpeg\\\\bin\\\\ffmpeg.exe"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    lst = output.parent / "_mode13_concat_list.txt"
    lines = []
    for p in paths:
        s = str(p.resolve()).replace("'", "'\\''")
        lines.append(f"file '{s}'")
    lst.write_text("\n".join(lines), encoding="utf-8")
    cmd = [
        ff,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(lst),
        "-c",
        "copy",
        str(output),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=7200)
    finally:
        lst.unlink(missing_ok=True)


async def run_mode13_pipeline(
    session_id: str,
    audio_path: str | Path,
    *,
    voice_preset: str = "studio",
    voice_gain_db: float = 0.0,
    voice_tempo_scale: float = 1.0,
    voice_pitch_semitones: float = 0.0,
    voice_ai_cleanup: float | None = None,
    voice_noise_suppression: float | None = None,
    voice_level_normalize: float | None = None,
    voice_highpass_hz: int | None = None,
    voice_deesser: float | None = None,
    voice_clarity: float | None = None,
    voice_mud_cut: float | None = None,
    voice_compression: float | None = None,
    language: str | None = None,
    show_subtitles: bool = True,
    skip_final_assembly: bool = True,
    chunk_seconds: int = CHUNK_SEC_DEFAULT,
    segment_seconds: int = SEG_SEC_DEFAULT,
    video_header_title: str | None = None,
    control: dict | None = None,
) -> dict[str, Any]:
    from pipeline_control import checkpoint

    require_ffmpeg_or_raise()

    await checkpoint(control)

    header_stripped = (video_header_title or "").strip() or None

    src = Path(audio_path)
    if not src.is_file():
        raise FileNotFoundError(f"Audio not found: {src}")

    session_root = _session_dir(session_id)
    session_root.mkdir(parents=True, exist_ok=True)
    m13 = _mode13_dir(session_id)

    upload_copy = m13 / f"upload{src.suffix.lower()}"
    shutil.copy2(src, upload_copy)
    await checkpoint(control)

    processed_wav = m13 / "processed_voice.wav"
    await asyncio.to_thread(
        transform_voice_to_wav,
        upload_copy,
        processed_wav,
        preset=voice_preset,
        gain_db=float(voice_gain_db),
        tempo_scale=float(voice_tempo_scale),
        pitch_semitones=float(voice_pitch_semitones),
        ai_cleanup=voice_ai_cleanup,
        noise_suppression=voice_noise_suppression,
        level_normalize=voice_level_normalize,
        highpass_hz=voice_highpass_hz,
        deesser=voice_deesser,
        clarity=voice_clarity,
        mud_cut=voice_mud_cut,
        compression=voice_compression,
    )
    await checkpoint(control)

    chunk_sec = max(60, min(600, int(chunk_seconds)))
    seg_sec = max(10, min(120, int(segment_seconds)))

    chunk_infos = split_wav_to_chunks(processed_wav, float(chunk_sec), m13, "chunk")
    total_dur = sum(d for _, d in chunk_infos)

    logger.info(f"[Mode13] {len(chunk_infos)} chunk(s), total {total_dur:.1f}s")

    # Transcribe each chunk + build segment metadata (text only first)
    chunks_plan: list[dict[str, Any]] = []
    transcript_parts: list[str] = []

    for ci, (chunk_wav, dur_sec) in enumerate(chunk_infos):
        await checkpoint(control)
        wts, words = await asyncio.to_thread(
            get_word_timestamps_from_audio_path,
            chunk_wav,
            language=language,
            vad_filter=False,
        )
        if not wts or not words:
            raise RuntimeError(
                f"[Mode13] Whisper returned no words for chunk {ci}. "
                "Check faster-whisper install and audio clarity."
            )
        windows = _windows_for_duration(dur_sec, seg_sec)
        segs: list[dict[str, Any]] = []
        for si, (t0, t1) in enumerate(windows):
            txt = _text_for_window(wts, words, t0, t1)
            segs.append(
                {
                    "s": si,
                    "t0": t0,
                    "t1": t1,
                    "text": txt,
                }
            )
        transcript_parts.append(" ".join(s["text"] for s in segs))
        # В корне сессии: один сегмент URL для GET /api/video/{sid}/{filename}
        preview_path = session_root / f"mode13_preview_{ci:03d}.mp4"
        preview_relpath = _rel_session(session_root, preview_path)
        chunks_plan.append(
            {
                "index": ci,
                "chunk_audio": _rel_session(session_root, chunk_wav),
                "duration_sec": dur_sec,
                "preview_relpath": preview_relpath,
                "segments": segs,
            }
        )

    output_format = settings.mode13_video_format
    image_aspect_ratio = _image_aspect_ratio_for_format(output_format)
    style_suffix = await _derive_style_suffix("\n".join(transcript_parts), output_format=output_format)
    await checkpoint(control)

    seg_work: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for ch in chunks_plan:
        for seg in ch["segments"]:
            seg_work.append((ch, seg))

    concepts = await _resolve_concepts_for_seg_work(seg_work)
    prompt_list = [
        _compose_image_prompt(c, style_suffix, output_format=output_format)
        for c in concepts
    ]

    img_n = max(1, min(16, int(getattr(settings, "mode13_image_gen_concurrency", 3) or 3)))
    sem = asyncio.Semaphore(img_n)

    async def _gen_seg_image(prompt: str, dest: Path) -> None:
        async with sem:
            try:
                await _generate_one_image(prompt, dest, aspect_ratio=image_aspect_ratio)
            except Exception as e:
                logger.warning(f"[Mode13] Image generation failed, using placeholder: {e}")
                _write_mode13_placeholder_image(dest, aspect_ratio=image_aspect_ratio)

    tasks = []
    for (ch, seg), prompt in zip(seg_work, prompt_list):
        ci = ch["index"]
        si = seg["s"]
        seg["image_prompt"] = prompt
        img_path = m13 / f"img_c{ci}_s{si}.jpg"
        seg["image"] = _rel_session(session_root, img_path)
        awav = m13 / f"seg_c{ci}_s{si}.wav"
        seg["audio"] = _rel_session(session_root, awav)
        tasks.append(_gen_seg_image(prompt, img_path))

    await asyncio.gather(*tasks)
    await checkpoint(control)

    # Export segment WAVs + build preview MP4 per chunk
    for ch in chunks_plan:
        chunk_disk = session_root / ch["chunk_audio"]
        for seg in ch["segments"]:
            _slice_audio_segment(chunk_disk, seg["t0"], seg["t1"], session_root / seg["audio"])

    snap = plan_snapshot_prebuild(chunks_plan, style_suffix, show_subtitles, header_stripped)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        functools.partial(_build_all_chunk_previews_parallel, session_id, snap),
    )

    plan: dict[str, Any] = {
        "version": 1,
        "session_id": session_id,
        "voice_preset": voice_preset,
        "language": language,
        "style_suffix": style_suffix,
        "show_subtitles": bool(show_subtitles),
        "header_title": header_stripped,
        "chunk_seconds": chunk_sec,
        "segment_seconds": seg_sec,
        "source_upload": _rel_session(session_root, upload_copy),
        "processed_wav": _rel_session(session_root, processed_wav),
        "chunks": chunks_plan,
    }
    _save_mode13_plan(session_id, plan)

    preview_filenames = [ch["preview_relpath"] for ch in chunks_plan]
    topic_preview = f"Аудио → слайды ({len(chunks_plan)}×~{chunk_sec // 60} мин, по {seg_sec} с)"

    if skip_final_assembly:
        return {
            "session_id": session_id,
            "video_path": None,
            "video_paths": [],
            "topic": topic_preview,
            "quote_caption": topic_preview,
            "quote_caption_ru": topic_preview[:220],
            "quote_caption_en": None,
            "trend": None,
            "report": None,
            "publishing": None,
            "mode13_review_ready": True,
            "mode13_clip_filenames": preview_filenames,
            "mode13_show_subtitles": bool(show_subtitles),
            "mode13_chunks_meta": [
                {"index": ch["index"], "duration_sec": ch["duration_sec"], "num_segments": len(ch["segments"])}
                for ch in chunks_plan
            ],
        }

    final_path = session_root / "video_mode13.mp4"
    prev_paths = [session_root / p for p in preview_filenames]
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: _ffmpeg_concat(prev_paths, final_path))

    rel_final = _rel_session(session_root, final_path)
    return {
        "session_id": session_id,
        "video_path": rel_final,
        "video_paths": [rel_final],
        "topic": topic_preview,
        "quote_caption": topic_preview,
        "quote_caption_ru": topic_preview[:220],
        "quote_caption_en": None,
        "trend": None,
        "report": None,
        "publishing": None,
        "mode13_review_ready": False,
        "mode13_clip_filenames": [],
        "mode13_show_subtitles": bool(show_subtitles),
        "mode13_chunks_meta": [],
    }


def plan_snapshot_prebuild(
    chunks_plan: list[dict[str, Any]],
    style_suffix: str,
    show_subtitles: bool,
    header_title: str | None = None,
) -> dict[str, Any]:
    """Temporary plan for executor lambda (only fields needed by _build_chunk_preview_sync)."""
    return {
        "chunks": chunks_plan,
        "style_suffix": style_suffix,
        "show_subtitles": show_subtitles,
        "header_title": header_title,
    }


async def regenerate_mode13_segment(
    session_id: str,
    chunk_index: int,
    segment_index: int,
) -> dict[str, Any]:
    plan = load_mode13_plan(session_id)
    if chunk_index < 0 or chunk_index >= len(plan["chunks"]):
        raise ValueError("Invalid chunk_index")
    ch = plan["chunks"][chunk_index]
    segs = ch["segments"]
    if segment_index < 0 or segment_index >= len(segs):
        raise ValueError("Invalid segment_index")

    seg = segs[segment_index]
    style = plan.get("style_suffix") or _FALLBACK_STYLE
    prompt = await _build_image_prompt_async(
        seg.get("text", ""),
        style,
        extra_suffix="Fresh alternative composition, same art direction.",
        output_format=settings.mode13_video_format,
    )
    session_root = _session_dir(session_id)
    img_path = session_root / seg["image"]
    await _generate_one_image(
        prompt,
        img_path,
        aspect_ratio=_image_aspect_ratio_for_format(settings.mode13_video_format),
    )
    seg["image_prompt"] = prompt

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: _build_chunk_preview_sync(session_id, chunk_index, plan))
    _save_mode13_plan(session_id, plan)

    return {
        "ok": True,
        "chunk_index": chunk_index,
        "segment_index": segment_index,
        "preview_relpath": ch["preview_relpath"],
    }


def assemble_mode13_final_sync(session_id: str, show_subtitles: bool | None = None) -> dict[str, Any]:
    plan = load_mode13_plan(session_id)
    if show_subtitles is not None:
        new_subs = bool(show_subtitles)
        old_subs = bool(plan.get("show_subtitles", True))
        plan["show_subtitles"] = new_subs
        _save_mode13_plan(session_id, plan)
        # Субтитры уже «вшиты» в превью — при смене флага пересобираем все части.
        if new_subs != old_subs:
            _build_all_chunk_previews_parallel(session_id, plan)

    session_root = _session_dir(session_id)
    previews = [session_root / ch["preview_relpath"] for ch in plan["chunks"]]
    for p in previews:
        if not p.is_file():
            raise FileNotFoundError(f"Missing preview: {p}")

    final_path = session_root / "video_mode13.mp4"
    _ffmpeg_concat(previews, final_path)
    rel = _rel_session(session_root, final_path)
    topic_preview = f"Аудио → слайды (финал, {len(previews)} частей)"

    return {
        "session_id": session_id,
        "video_path": rel,
        "video_paths": [rel],
        "topic": topic_preview,
        "quote_caption": topic_preview,
        "quote_caption_ru": topic_preview[:220],
        "quote_caption_en": None,
        "trend": None,
        "report": None,
        "publishing": None,
        "mode13_review_ready": False,
        "mode13_clip_filenames": [],
        "mode13_show_subtitles": plan.get("show_subtitles", True),
        "mode13_chunks_meta": [],
    }
