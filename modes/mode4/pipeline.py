"""
Mode 4 Pipeline — Цитата + фото → RU и/или EN (по only_lang: None = оба, "ru"/"en" = один файл).

Ввод: цитата и имя автора только на русском; агент переводит для английской версии.
Озвучка: только FastGen. Субтитры — по желанию.
"""

from __future__ import annotations

import asyncio
import functools
import time
from pathlib import Path
from typing import Any

from loguru import logger

from config import settings
from modes.mode4.prompt_agent import run_quote_prompt_agent
from modes.mode4.quote_format import format_quote_caption
from modes.mode4.video_assembler import assemble_mode4_video
from modes.mode4.video_generator import generate_quote_videos


async def run_mode4_pipeline(
    quote: str,
    person_name: str,
    photo_path: str | Path,
    session_id: str | None = None,
    language: str = "both",
    show_subtitles: bool = True,
    control: dict | None = None,
    only_lang: str | None = None,
) -> dict[str, Any]:
    """
    Запуск пайплайна «Цитата + фото личности» → video_ru.mp4 и/или video_en.mp4.

    Args:
        quote: цитата на русском
        person_name: имя автора на русском
        language: служебный параметр API
        only_lang: None = оба ролика; "ru" | "en" — один ролик (форма или библиотека)
    """
    from pipeline_control import checkpoint, fastgen_cancel_event

    session_id = session_id or str(int(time.time() * 1000))
    output_dir = settings.videos_dir / session_id / "clips"
    output_dir.mkdir(parents=True, exist_ok=True)

    quote_caption_ru = format_quote_caption(quote, person_name)
    ol = (only_lang or "").strip().lower()
    if ol == "en":
        logger.info(f"=== Mode 4 Pipeline | quote RU ({len(quote)} chars) | session={session_id} | EN only ===")
    elif ol == "ru":
        logger.info(f"=== Mode 4 Pipeline | quote RU ({len(quote)} chars) | session={session_id} | RU only ===")
    else:
        logger.info(f"=== Mode 4 Pipeline | quote RU ({len(quote)} chars) | session={session_id} | RU+EN ===")

    await checkpoint(control)

    # Step 1: Prompt agent (русский ввод → перевод для EN-ролика)
    logger.info("Step 1/3 - Mode4 Prompt Agent")
    prompt_data = await run_quote_prompt_agent(
        Path(photo_path), quote,
        person_name=person_name,
        bilingual=True,
        subtitle_lang="ru",
        auto_detect_lang=False,
        source_russian_only=True,
    )
    script_ru = (prompt_data.get("script_ru") or quote).strip()
    script_en = (prompt_data.get("script_en") or quote).strip()
    person_name_en = (prompt_data.get("person_name_en") or person_name).strip()
    quote_caption_en = format_quote_caption(script_en, person_name_en)

    vp_ru = prompt_data.get("video_prompt_ru") or prompt_data.get("video_prompt", "")
    vp_en = prompt_data.get("video_prompt_en") or prompt_data.get("video_prompt", "")
    if ol == "en":
        video_prompts = [vp_en]
        scripts = [script_en]
        subtitle_texts = [quote_caption_en] if show_subtitles else [""]
        spoken_for_subs = [script_en]
        authors_for_subs = [person_name_en]
        whisper_langs = ["en"]
        out_names = ["video_en.mp4"]
    elif ol == "ru":
        video_prompts = [vp_ru]
        scripts = [script_ru]
        subtitle_texts = [quote_caption_ru] if show_subtitles else [""]
        spoken_for_subs = [script_ru]
        authors_for_subs = [person_name]
        whisper_langs = ["ru"]
        out_names = ["video_ru.mp4"]
    else:
        video_prompts = [vp_ru, vp_en]
        scripts = [script_ru, script_en]
        subtitle_texts = (
            [quote_caption_ru, quote_caption_en] if show_subtitles else ["", ""]
        )
        spoken_for_subs = [script_ru, script_en]
        authors_for_subs = [person_name, person_name_en]
        whisper_langs = ["ru", "en"]
        out_names = ["video_ru.mp4", "video_en.mp4"]

    voice_desc = prompt_data.get("voice_description") or ""

    await checkpoint(control)

    # Step 2: Video generator
    logger.info(f"Step 2/3 - Mode4 Video Generator")
    video_paths = await generate_quote_videos(
        video_prompts, output_dir, Path(photo_path),
        voice_description=voice_desc,
        scripts=scripts,
        cancel_event=fastgen_cancel_event(control),
    )
    valid_paths = [Path(p) for p in video_paths if p and Path(p).exists()]
    if not valid_paths:
        raise RuntimeError("[Mode4] No videos generated")

    await checkpoint(control)

    # Step 3: Assembler — видео FastGen (озвучка от FastGen) + субтитры
    logger.info("Step 3/3 - Mode4 Video Assembler")
    subs = subtitle_texts[: len(valid_paths)]
    if len(subs) < len(valid_paths):
        subs.extend([""] * (len(valid_paths) - len(subs)))
    session_dir = settings.videos_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    output_paths: list[Path] = []
    loop = asyncio.get_event_loop()
    for i, (clip_path, sub) in enumerate(zip(valid_paths, subs)):
        out_name = out_names[i] if i < len(out_names) else f"video_{i}.mp4"
        out_path = session_dir / out_name
        # Субтитры: караоке по Whisper + золотое слово; полная подпись «"…" – Автор» при фолбэке
        use_static_caption = not bool(show_subtitles and sub and str(sub).strip())
        await loop.run_in_executor(
            None,
            functools.partial(
                assemble_mode4_video,
                [clip_path],
                [sub],
                out_path,
                use_static_caption,
                # Один клип в вызове → в assembler индекс всегда 0; передаём только строку этого ролика (RU/EN).
                spoken_scripts=(
                    [spoken_for_subs[i]]
                    if show_subtitles and i < len(spoken_for_subs)
                    else None
                ),
                authors=(
                    [authors_for_subs[i]]
                    if show_subtitles and i < len(authors_for_subs)
                    else None
                ),
                whisper_languages=[whisper_langs[i]] if show_subtitles else None,
            ),
        )
        output_paths.append(out_path)

    video_path = str(output_paths[0].resolve())
    video_paths = [str(p.resolve()) for p in output_paths]
    from agents.topics_history import mark_topic_used
    mark_topic_used(
        topic=quote_caption_ru,
        session_id=session_id,
        video_path=video_path,
        quote_caption_en=quote_caption_en,
    )

    logger.success(f"=== Mode 4 Pipeline DONE | {len(output_paths)} file(s) → {[p.name for p in output_paths]} ===")
    return {
        "session_id": session_id,
        "video_path": video_path,
        "video_paths": video_paths,
        "topic": quote_caption_ru,
        "quote_caption": quote_caption_ru,
        "quote_caption_ru": quote_caption_ru,
        "quote_caption_en": quote_caption_en,
        "trend": None,
        "report": None,
    }
