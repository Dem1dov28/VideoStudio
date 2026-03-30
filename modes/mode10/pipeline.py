"""
Mode 10 Pipeline — Beach cleanup timelapse (логика как mode8: сценарий → кадры → keyframe → сборка).
"""

from __future__ import annotations

import functools
import time
from pathlib import Path
from typing import Any

from loguru import logger

from config import settings
from modes.mode10.scenario_writer import run_mode10_scenario_writer
from modes.mode10.video_assembler import assemble_mode10_video
from modes.mode10.video_generator import generate_beach_cleanup_videos


async def run_mode10_pipeline(
    session_id: str | None = None,
    local_only: bool = True,
    beach_type: str | None = None,
    coast_setting: str | None = None,
    num_stages: int = 5,
    language: str = "ru",
    control: dict | None = None,
) -> dict[str, Any]:
    import asyncio
    from pipeline_control import checkpoint

    session_id = session_id or str(int(time.time() * 1000))
    videos_dir = settings.videos_dir
    clips_dir = videos_dir / session_id / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        f"=== Mode 10 Pipeline | Beach cleanup timelapse | session={session_id} | "
        f"beach={beach_type or 'random'} | coast={coast_setting or 'random'} | stages={num_stages} ==="
    )

    await checkpoint(control)
    logger.info("Step 1/3 — сценарий уборки пляжа...")
    scenario = await run_mode10_scenario_writer(
        beach_type=beach_type,
        coast_setting=coast_setting,
        num_stages=num_stages,
        language=language,
        control=control,
    )

    title = scenario.get("title", "Beach cleanup")
    beach_name = scenario.get("beach_type_name", "пляж")
    coast_name = scenario.get("location_name", "берег")
    stages = scenario.get("scenes", [])
    logger.success(
        f"[Mode10] Сценарий: {title} | {beach_name} | {coast_name} | {len(stages)} стадий"
    )

    await checkpoint(control)
    logger.info("Step 2/3 — FastGen: кадры + keyframe-видео...")
    video_paths, enriched_scenario = await generate_beach_cleanup_videos(
        scenario=scenario,
        output_dir=clips_dir,
        session_id=session_id,
        language=language,
    )

    valid_paths = [p for p in video_paths if p and Path(p).exists()]
    if not valid_paths:
        raise RuntimeError("[Mode10] Не сгенерировано ни одного клипа")

    expected_videos = len(stages) - 1 if len(stages) > 1 else 1
    logger.success(f"[Mode10] Клипов: {len(valid_paths)}/{expected_videos}")

    await checkpoint(control)
    logger.info("Step 3/3 — сборка финального видео...")
    output_path = videos_dir / f"video_{session_id}.mp4"
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        functools.partial(
            assemble_mode10_video,
            valid_paths,
            output_path,
            title=title,
        ),
    )

    from agents.topics_history import mark_topic_used

    mark_topic_used(
        topic=f"[Пляж] {title}",
        session_id=session_id,
        video_path=str(output_path),
        video_angle=f"beach={beach_name},coast={coast_name},stages={len(stages)}",
    )

    video_path = str(output_path.resolve())
    logger.success(f"=== Mode 10 Pipeline DONE | {video_path} ===")

    return {
        "session_id": session_id,
        "video_path": video_path,
        "topic": title,
        "scenario": enriched_scenario,
        "trend": None,
        "report": None,
    }
