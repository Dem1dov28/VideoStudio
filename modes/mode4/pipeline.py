"""
Mode 4 Pipeline — Цитата известной личности + фото → 1 или 2 видеофрагмента.

Язык: RU | EN | RU+EN (bilingual)
Озвучка: только FastGen (без TTS). Субтитры — по желанию.
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
from modes.mode4.video_assembler import assemble_mode4_video
from modes.mode4.video_generator import generate_quote_videos


async def run_mode4_pipeline(
    quote: str,
    person_name: str,
    photo_path: str | Path,
    session_id: str | None = None,
    language: str = "ru",
    show_subtitles: bool = True,
    control: dict | None = None,
) -> dict[str, Any]:
    """
    Запуск пайплайна «Цитата + фото личности» → видеофрагмент(ы).

    Args:
        quote: цитата на русском
        photo_path: путь к фото личности
        session_id: уникальный ID
        language: "ru" | "en" | "both"
        show_subtitles: показывать субтитры
        control: для pause/cancel

    Returns:
        dict с video_path, session_id
    """
    from pipeline_control import checkpoint

    session_id = session_id or str(int(time.time() * 1000))
    output_dir = settings.videos_dir / session_id / "clips"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"=== Mode 4 Pipeline | quote ({len(quote)} chars) | session={session_id} | lang={language} ===")

    await checkpoint(control)

    # Step 1: Prompt agent
    logger.info("Step 1/3 - Mode4 Prompt Agent")
    auto_detect = (language or "").lower() == "auto"
    bilingual = not auto_detect and language.lower() == "both"
    lang = "en" if language.lower() == "en" else "ru"
    prompt_data = await run_quote_prompt_agent(
        Path(photo_path), quote,
        person_name=person_name,
        bilingual=bilingual,
        subtitle_lang=lang,
        auto_detect_lang=auto_detect,
    )
    if auto_detect:
        lang = prompt_data.get("detected_lang") or lang

    if bilingual:
        video_prompts = [
            prompt_data.get("video_prompt_ru") or prompt_data.get("video_prompt", ""),
            prompt_data.get("video_prompt_en") or prompt_data.get("video_prompt", ""),
        ]
        scripts = [prompt_data.get("script_ru") or quote, prompt_data.get("script_en") or quote]
        subtitle_texts = scripts if show_subtitles else ["", ""]
    else:
        video_prompts = [prompt_data.get("video_prompt", "")]
        scripts = [prompt_data.get("script_ru") if lang == "ru" else prompt_data.get("script_en") or quote]
        if not scripts[0]:
            scripts[0] = quote
        subtitle_texts = scripts if show_subtitles else [""]

    voice_desc = prompt_data.get("voice_description") or ""

    await checkpoint(control)

    # Step 2: Video generator
    logger.info(f"Step 2/3 - Mode4 Video Generator")
    video_paths = await generate_quote_videos(
        video_prompts, output_dir, Path(photo_path),
        voice_description=voice_desc,
        scripts=scripts,
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
    fnames = ["video_ru.mp4", "video_en.mp4"] if bilingual else ["video_ru.mp4" if lang == "ru" else "video_en.mp4"]
    loop = asyncio.get_event_loop()
    for i, (clip_path, sub) in enumerate(zip(valid_paths, subs)):
        out_name = fnames[i] if i < len(fnames) else f"video_{i}.mp4"
        out_path = session_dir / out_name
        await loop.run_in_executor(
            None,
            functools.partial(
                assemble_mode4_video,
                [clip_path],
                [sub],
                out_path,
            ),
        )
        output_paths.append(out_path)

    video_path = str(output_paths[0].resolve())
    video_paths = [str(p.resolve()) for p in output_paths]
    from agents.topics_history import mark_topic_used
    mark_topic_used(topic=f"Цитата: {quote[:50]}...", session_id=session_id, video_path=video_path)

    logger.success(f"=== Mode 4 Pipeline DONE | {len(output_paths)} file(s) → {[p.name for p in output_paths]} ===")
    return {
        "session_id": session_id,
        "video_path": video_path,
        "video_paths": video_paths,
        "topic": quote[:80],
        "trend": None,
        "report": None,
    }
