"""
Mode 12 — таймлапс уборки и реставрации комнаты (ровно 5 стадий).

Сценарий → ключевые кадры FastGen → сборка (общий ассемблер как у mode 10).
"""

from __future__ import annotations

import functools
import time
from pathlib import Path
from typing import Any

from loguru import logger

from config import settings
from modes.mode10.video_assembler import assemble_mode10_video
from modes.mode12.publishing_metadata import generate_publishing_metadata
from modes.mode12.scenario_writer import run_mode12_scenario_writer
from modes.mode12.video_generator import generate_room_restoration_videos


def _video_duration_seconds(path: Path) -> float:
    from moviepy import VideoFileClip

    vc = VideoFileClip(str(path))
    try:
        return float(vc.duration or 0.0)
    finally:
        vc.close()


async def run_mode12_pipeline(
    session_id: str | None = None,
    local_only: bool = True,
    room_type: str | None = None,
    room_lighting: str | None = None,
    control: dict | None = None,
) -> dict[str, Any]:
    import asyncio
    from pipeline_control import checkpoint

    session_id = session_id or str(int(time.time() * 1000))
    videos_dir = settings.videos_dir
    clips_dir = videos_dir / session_id / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        f"=== Mode 12 | Уборка и реставрация комнаты | session={session_id} | "
        f"room={room_type or 'random'} | light={room_lighting or 'random'} | стадий=5 (фикс.) ==="
    )

    await checkpoint(control)
    logger.info("Step 1/4 — сценарий (5 стадий)...")
    scenario = await run_mode12_scenario_writer(
        room_type=room_type,
        room_lighting=room_lighting,
        control=control,
    )

    title = scenario.get("title_en") or scenario.get("title", "Room cleanup timelapse")
    rname = scenario.get("room_type_name", "")
    lname = scenario.get("room_lighting_name", "")
    room_type_key = scenario.get("room_type", "studio")
    room_lighting_key = scenario.get("room_lighting", "morning_soft")
    stages = scenario.get("scenes", [])
    logger.success(f"[Mode12] Сценарий: {title} | {rname} | {lname} | {len(stages)} стадий")

    await checkpoint(control)
    logger.info("Step 2/4 — FastGen: кадры + keyframe...")
    video_paths, enriched_scenario = await generate_room_restoration_videos(
        scenario=scenario,
        output_dir=clips_dir,
        session_id=session_id,
    )

    valid_paths = [p for p in video_paths if p and Path(p).exists()]
    if not valid_paths:
        raise RuntimeError("[Mode12] Не сгенерировано ни одного клипа")

    await checkpoint(control)
    logger.info("Step 3/4 — сборка видео...")
    output_path = videos_dir / f"video_{session_id}.mp4"
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        functools.partial(
            assemble_mode10_video,
            valid_paths,
            output_path,
            title=title,
            speed_multiplier=1.1,
            music_dir_only=True,
            background_music_volume=0.6,
        ),
    )

    video_path = str(output_path.resolve())
    video_duration = await loop.run_in_executor(
        None,
        functools.partial(_video_duration_seconds, output_path),
    )
    logger.success(f"[Mode12] Длительность финала: {video_duration:.2f}s")

    logger.info("Step 4/4 — clickbait title + publishing metadata (EN only)...")
    from modes.mode8.clickbait_titles import generate_clickbait_title

    clickbait_title = generate_clickbait_title(
        content_type="room",
        style_or_type=room_type_key,
        location=room_lighting_key,
        duration_seconds=video_duration,
        language="en",
    )
    logger.success(f"[Mode12] Clickbait: {clickbait_title}")

    duration_hint = int(round(video_duration)) or 30
    publishing_en = await generate_publishing_metadata(
        room_type_key=room_type_key,
        room_lighting_key=room_lighting_key,
        stages=stages,
        title=title,
        force_title=clickbait_title,
        duration_hint_seconds=duration_hint,
    )
    publishing = {"en": publishing_en}

    from agents.topics_history import mark_topic_used

    mark_topic_used(
        topic=f"[Room] {title}",
        session_id=session_id,
        video_path=str(output_path),
        video_angle=(
            f"room={rname},light={lname},stages=5,type={room_type_key},"
            f"light_key={room_lighting_key},duration={video_duration:.2f}s"
        ),
        publishing=publishing,
    )

    logger.success(f"=== Mode 12 DONE | {video_path} ===")

    return {
        "session_id": session_id,
        "video_path": video_path,
        "topic": title,
        "scenario": enriched_scenario,
        "trend": None,
        "report": None,
        "publishing": publishing,
    }
