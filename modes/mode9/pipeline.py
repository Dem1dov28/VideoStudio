"""
Mode 9 Pipeline — Vehicle Assembly Timelapse Video Generator.

Generates satisfying timelapse videos showing vehicle assembly progress.
Uses KEYFRAME approach for smooth transitions between stages.

Flow:
  1. Scenario Writer — Generate assembly stages (empty space -> finished vehicle)
  2. Video Generator — Sequential images + KEYFRAME videos (transitions between stages)
  3. Video Assembler — Combine into final timelapse with workshop sounds
  4. Publishing Metadata — Generate title, description, hashtags, tags
"""

from __future__ import annotations

import functools
import time
from pathlib import Path
from typing import Any

from loguru import logger

from config import settings
from modes.mode9.scenario_writer import run_mode9_scenario_writer
from modes.mode9.video_generator import generate_vehicle_videos
from modes.mode9.video_assembler import assemble_mode9_video
from modes.mode9.publishing_metadata import generate_publishing_metadata


async def run_mode9_pipeline(
    session_id: str | None = None,
    local_only: bool = True,
    vehicle_type: str | None = None,
    location: str | None = None,
    num_stages: int = 5,
    language: str = "ru",
    control: dict | None = None,
) -> dict[str, Any]:
    """
    Run the Vehicle Assembly Timelapse video pipeline.

    Args:
        session_id: Unique run identifier.
        local_only: If True, skip publishing.
        vehicle_type: Vehicle type preference (airplane, car, tractor, random).
        location: Location preference (hangar, factory, workshop, outdoor, random).
        num_stages: Number of assembly stages (5-7).
        language: Output language ("ru" or "en").
        control: Pause/cancel control dict.

    Returns:
        dict with video_path, session_id, scenario, publishing metadata, etc.
    """
    import asyncio
    from pipeline_control import checkpoint

    session_id = session_id or str(int(time.time() * 1000))
    videos_dir = settings.videos_dir
    clips_dir = videos_dir / session_id / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        f"=== Mode 9 Pipeline | Vehicle Assembly Timelapse | "
        f"session={session_id} | vehicle={vehicle_type or 'random'} | "
        f"location={location or 'random'} | stages={num_stages} ==="
    )

    # Step 1: Generate scenario (assembly stages)
    await checkpoint(control)
    logger.info("Step 1/4 - Generating Assembly Scenario...")

    scenario = await run_mode9_scenario_writer(
        vehicle_type=vehicle_type,
        location=location,
        num_stages=num_stages,
        language=language,
        control=control,
    )

    title = scenario.get("title", "Vehicle Assembly Timelapse")
    vehicle_type_name = scenario.get("vehicle_type_name", "vehicle")
    location_name = scenario.get("location_name", "location")
    stages = scenario.get("scenes", [])
    logger.success(
        f"[Mode9] Scenario: {title} | {vehicle_type_name} | {location_name} | "
        f"{len(stages)} stages"
    )

    # Step 2: Generate video clips via FastGen (sequential images + KEYFRAME videos)
    await checkpoint(control)
    logger.info("Step 2/4 - Vehicle Video Generator (Sequential Images + Keyframe Videos)")

    video_paths, enriched_scenario = await generate_vehicle_videos(
        scenario=scenario,
        output_dir=clips_dir,
        session_id=session_id,
        language=language,
    )

    valid_paths = [p for p in video_paths if p and Path(p).exists()]
    if not valid_paths:
        raise RuntimeError("[Mode9] No keyframe video clips generated")

    expected_videos = len(stages) - 1 if len(stages) > 1 else 1
    logger.success(f"[Mode9] Generated {len(valid_paths)}/{expected_videos} keyframe video clips")

    # Step 3: Assemble final video
    await checkpoint(control)
    logger.info("Step 3/4 - Video Assembly")

    output_path = videos_dir / f"video_{session_id}.mp4"

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        functools.partial(
            assemble_mode9_video,
            valid_paths,
            output_path,
            title=title,
        ),
    )

    video_path = str(output_path.resolve())

    # Step 4: Generate publishing metadata
    logger.info("Step 4/4 - Generating Publishing Metadata...")
    publishing = await generate_publishing_metadata(
        vehicle_type=vehicle_type_name,
        location=location_name,
        stages=stages,
        title=title,
        language=language,
    )

    # Record in history
    from agents.topics_history import mark_topic_used
    mark_topic_used(
        topic=f"[Assembly] {title}",
        session_id=session_id,
        video_path=str(output_path),
        video_angle=f"vehicle={vehicle_type_name},location={location_name},stages={len(stages)}",
        publishing=publishing,
    )

    logger.success(f"=== Mode 9 Pipeline DONE | video={video_path} ===")

    return {
        "session_id": session_id,
        "video_path": video_path,
        "topic": title,
        "scenario": enriched_scenario,
        "vehicle_type": vehicle_type_name,
        "location": location_name,
        "stages": len(stages),
        "trend": None,
        "report": None,
        "publishing": publishing,
    }
