"""
Mode 5 Pipeline — Длинные видео (~1 час).

Шаги:
  1. Long-form Scenario Writer — тема → длинный сценарий с сегментами и точками смены картинки
  2. Image Generator — генерирует изображения только для сегментов с image_prompt
  3. TTS — озвучка каждого сегмента (RU или EN)
  4. Video Assembler — склейка: изображение + аудио по сегментам, без субтитров
"""

from __future__ import annotations

import asyncio
import functools
import time
from pathlib import Path
from typing import Any

from loguru import logger

from agents.content_generator.fastgen_scraper import generate_images_fastgen
from agents.video_editor.tts import synthesize_all
from config import settings
from modes.mode5.scenario_writer import run_long_form_scenario_writer
from modes.mode5.video_assembler import assemble_mode5_video


async def run_mode5_pipeline(
    topic: str,
    session_id: str | None = None,
    local_only: bool = True,
    language: str = "ru",
    control: dict | None = None,
) -> dict[str, Any]:
    """
    Запуск пайплайна «Длинные видео».

    Args:
        topic: тема видео
        session_id: уникальный ID
        language: "ru" | "en"
        control: для pause/cancel

    Returns:
        dict с video_path, session_id
    """
    from pipeline_control import checkpoint, fastgen_cancel_event

    session_id = session_id or str(int(time.time() * 1000))
    output_dir = settings.output_dir / session_id
    images_dir = output_dir / "images"
    audio_dir = settings.audio_dir / session_id
    videos_dir = settings.videos_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"=== Mode 5 Pipeline | Long-form | topic={topic!r} | session={session_id} ===")

    await checkpoint(control)

    # Step 1: Long-form scenario (multi-agent: Structure → Content per subchapter → Coherence)
    logger.info("Step 1/4 - Mode5 Scenario Writer (multi-agent: structure + content + coherence)")
    scenario = await run_long_form_scenario_writer(topic, language=language, control=control)
    segments = scenario["segments"]
    title = scenario.get("title") or topic

    await checkpoint(control)

    # Step 2: Generate images only for segments with image_prompt
    prompts_with_idx: list[tuple[int, str]] = [
        (i, s["image_prompt"])
        for i, s in enumerate(segments)
        if s.get("image_prompt")
    ]
    if not prompts_with_idx:
        raise RuntimeError("[Mode5] No image prompts in scenario")

    logger.info(f"Step 2/4 - Image Generator ({len(prompts_with_idx)} images)")
    image_prompts = [p for _, p in prompts_with_idx]
    image_paths = await generate_images_fastgen(
        image_prompts, images_dir, parallel=False, cancel_event=fastgen_cancel_event(control)
    )
    if len(image_paths) < len(prompts_with_idx):
        raise RuntimeError(f"[Mode5] Expected {len(prompts_with_idx)} images, got {len(image_paths)}")

    # Map segment index -> image path (reuse previous when no new image)
    idx_to_img: dict[int, Path] = {}
    for k, (seg_idx, _) in enumerate(prompts_with_idx):
        if k < len(image_paths) and image_paths[k]:
            idx_to_img[seg_idx] = Path(image_paths[k])
    current_img: Path | None = None
    for i in range(len(segments)):
        if i in idx_to_img:
            current_img = idx_to_img[i]
        if current_img is None:
            raise RuntimeError(f"[Mode5] Segment {i} has no image (first segment must have image_prompt)")
        idx_to_img[i] = current_img

    await checkpoint(control)

    # Step 3: TTS for each segment (slow rate for sleep story)
    logger.info(f"Step 3/4 - TTS ({len(segments)} segments, slow sleep-story voice)")
    narration_texts = [s["narration_text"] for s in segments]
    tts_rate = getattr(settings, "mode5_tts_rate", "-35%")
    audio_paths, _, _ = await synthesize_all(
        narration_texts, audio_dir, language=language, rate=tts_rate
    )

    await checkpoint(control)

    # Step 4: Assemble
    logger.info("Step 4/4 - Mode5 Video Assembler")
    segment_data: list[tuple[Path, Path]] = []
    for i, s in enumerate(segments):
        img_path = idx_to_img.get(i)
        audio_path = audio_paths[i] if i < len(audio_paths) else None
        if img_path and audio_path and Path(audio_path).exists():
            segment_data.append((img_path, Path(audio_path)))

    if not segment_data:
        raise RuntimeError("[Mode5] No valid segment data for assembly")

    session_dir = videos_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    output_path = session_dir / "video.mp4"

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        functools.partial(assemble_mode5_video, segment_data, output_path),
    )

    video_path = str(output_path.resolve())
    from agents.topics_history import mark_topic_used
    mark_topic_used(topic=title[:50], session_id=session_id, video_path=video_path)

    logger.success(f"=== Mode 5 Pipeline DONE | video={output_path} ===")
    return {
        "session_id": session_id,
        "video_path": video_path,
        "topic": title,
        "trend": None,
        "report": None,
    }
