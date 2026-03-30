"""
Mode 2 Pipeline — «Почему X?» video generation.

Runs: scenario_writer → video_generator → TTS → video_assembler
"""

from __future__ import annotations

import asyncio
import functools
import time
from pathlib import Path
from typing import Any

from loguru import logger

from config import settings
from agents.video_editor.tts import synthesize_all
from modes.mode2.scenario_writer import write_mode2_scenario
from modes.mode2.video_assembler import Mode2SceneData, assemble_mode2_video
from modes.mode2.video_generator import download_videos_for_scenes


async def run_mode2_pipeline(
    topic: str,
    num_scenes: int = 5,
    session_id: str | None = None,
    local_only: bool = True,
    show_subtitles: bool = True,
    prebuilt_scenario: dict | None = None,
    language: str = "ru",
    custom_title_bg_path: str | None = None,
    custom_outro_bg_path: str | None = None,
    reference_image_path: str | None = None,
    control: dict | None = None,
) -> dict[str, Any]:
    """
    Run the «Почему X?» video pipeline.

    Steps:
      1. scenario_writer — generate 5 "Почему X?" questions with narration, subtitle, video_search_query
      2. video_generator — Pexels API search + download for each scene
      3. TTS — synthesize narration_text for each scene (+ hook/outro)
      4. video_assembler — trim clips to audio duration, add subtitles, crossfades, export

    Args:
        topic: Video theme (e.g. "животные", "военная история").
        num_scenes: Number of Q&A scenes (default 5).
        session_id: Unique run ID.
        local_only: Unused (kept for API compatibility).
        show_subtitles: Whether to render subtitles on video.

    Returns:
        dict with video_path, topic, session_id.
    """
    session_id = session_id or str(int(time.time() * 1000))
    audio_dir = settings.audio_dir / session_id
    videos_dir = settings.videos_dir / session_id
    clips_dir = videos_dir / "clips"

    audio_dir.mkdir(parents=True, exist_ok=True)
    videos_dir.mkdir(parents=True, exist_ok=True)
    clips_dir.mkdir(parents=True, exist_ok=True)

    from pipeline_control import checkpoint, fastgen_cancel_event

    logger.info(f"=== Mode 2 Pipeline | topic={topic!r} | session={session_id} ===")

    await checkpoint(control)
    # ── Step 1: Scenario (prebuilt or generate) ──────────────────────────────
    if prebuilt_scenario:
        scenario = prebuilt_scenario
        scenes = scenario.get("scenes", [])
        logger.success(f"Using pre-built mode2 scenario: {len(scenes)} scenes")
    else:
        logger.info("Step 1/4 - Mode2 Scenario Writer")
        scenario = await write_mode2_scenario(topic, num_scenes=num_scenes, language=language)
        scenes = scenario["scenes"]

    title = scenario.get("title") or topic
    hook = scenario.get("hook", "")

    await checkpoint(control)
    # ── Step 2: Video Generator (fast-gen.ai or Pexels) ───────────────────────
    logger.info("Step 2/4 - Mode2 Video Generator")
    scenes_with_video = await download_videos_for_scenes(
        scenes, clips_dir,
        reference_image_path=reference_image_path,
        title=title,
        cancel_event=fastgen_cancel_event(control),
    )

    # ── Step 3: TTS ──────────────────────────────────────────────────────────
    logger.info("Step 3/4 - TTS Synthesis")
    narration_texts = [
        s.get("narration_text") or s.get("subtitle_text", "")
        for s in scenes_with_video
    ]

    tts_texts: list[str] = []
    scene_audio_start = 0
    tts_texts.extend(narration_texts)

    # Outro slide removed — no TTS for outro

    audio_paths, word_timestamps_list, tts_words_list = await synthesize_all(
        tts_texts, audio_dir, language=language, with_word_timestamps=True
    )

    await checkpoint(control)
    # ── Step 4: Video Assembler ──────────────────────────────────────────────
    logger.info("Step 4/4 - Mode2 Video Assembler")
    scene_data = [
        Mode2SceneData(
            video_path=s.get("video_path"),
            audio_path=str(audio_paths[scene_audio_start + i]) if scene_audio_start + i < len(audio_paths) else "",
            subtitle_text=(s.get("narration_text") or s.get("subtitle_text", "")) if show_subtitles else "",
            word_timestamps=(
                word_timestamps_list[scene_audio_start + i]
                if scene_audio_start + i < len(word_timestamps_list)
                else None
            ),
            tts_words=(
                tts_words_list[scene_audio_start + i]
                if scene_audio_start + i < len(tts_words_list)
                else None
            ),
        )
        for i, s in enumerate(scenes_with_video)
    ]

    output_path = settings.videos_dir / f"video_{session_id}.mp4"
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        functools.partial(
            assemble_mode2_video,
            scene_data,
            output_path,
        ),
    )

    logger.success(f"=== Mode 2 Pipeline DONE | video={output_path} ===")
    return {
        "session_id": session_id,
        "video_path": str(output_path.resolve()),
        "topic": title,
        "trend": None,
        "report": None,
    }
