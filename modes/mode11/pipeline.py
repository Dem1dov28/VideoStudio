"""Mode 11 Pipeline — Landmark construction / restoration timelapse."""

from __future__ import annotations

import functools
import time
from pathlib import Path
from typing import Any

from loguru import logger

from config import settings
from modes.mode11.clickbait_titles import generate_clickbait_title
from modes.mode11.publishing_metadata import generate_publishing_metadata
from modes.mode11.scenario_writer import DEFAULT_NUM_STAGES, run_mode11_scenario_writer
from modes.mode11.video_assembler import assemble_mode11_video
from modes.mode11.video_generator import generate_monument_videos


async def run_mode11_pipeline(
    session_id: str | None = None,
    local_only: bool = True,
    structure_type: str | None = None,
    language: str = "ru",
    num_stages: int = DEFAULT_NUM_STAGES,
    control: dict | None = None,
) -> dict[str, Any]:
    import asyncio
    from pipeline_control import checkpoint

    session_id = session_id or str(int(time.time() * 1000))
    videos_dir = settings.videos_dir
    clips_dir = videos_dir / session_id / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        f"=== Mode 11 Pipeline | Landmark construction timelapse | "
        f"session={session_id} | structure={structure_type or 'random'} | stages={num_stages} ==="
    )

    await checkpoint(control)
    logger.info("Step 1/3 - Generating Monument Scenario...")

    scenario = await run_mode11_scenario_writer(
        structure_type=structure_type,
        language=language,
        num_stages=num_stages,
        control=control,
    )

    title = scenario.get("title", "Landmark construction timelapse")
    structure_name = scenario.get("structure_name", "monument")
    stages = scenario.get("scenes", [])
    logger.success(
        f"[Mode11] Scenario: {title} | {structure_name} | {len(stages)} stages"
    )

    await checkpoint(control)
    logger.info("Step 2/4 - Monument Video Generator (Sequential Images + Keyframe Videos)")

    video_paths, enriched_scenario = await generate_monument_videos(
        scenario=scenario,
        output_dir=clips_dir,
        session_id=session_id,
        language=language,
        use_contextual=True,
        generate_preview=True,
    )

    valid_paths = [p for p in video_paths if p and Path(p).exists()]
    if not valid_paths:
        raise RuntimeError("[Mode11] No video clips generated")

    expected_videos = max(1, len(stages) - 1)
    logger.success(f"[Mode11] Generated {len(valid_paths)}/{expected_videos} videos")

    await checkpoint(control)
    logger.info("Step 3/4 - Video Assembly")

    output_path = videos_dir / f"video_{session_id}.mp4"
    preview_path = enriched_scenario.get("preview_path")
    has_preview = bool(preview_path and Path(preview_path).exists())
    loop = asyncio.get_event_loop()
    assembled_path, video_duration = await loop.run_in_executor(
        None,
        functools.partial(
            assemble_mode11_video,
            valid_paths,
            output_path,
            title=title,
            preview_image_path=preview_path if has_preview else None,
            preview_duration=0.3,
            # Keep end timing strict: no extra freeze, preview tail is exactly 0.3s when present.
            final_hold_duration=0.0,
        ),
    )

    video_path = str(assembled_path.resolve())

    logger.info("Step 4/4 - Publishing Metadata + Clickbait Titles")
    structure_key = scenario.get("structure_type", "colosseum")
    structure_name = scenario.get("structure_name_en", "monument")
    location_name = scenario.get("location_name", "historic location")

    clickbait_title_ru = generate_clickbait_title(
        content_type="monument",
        style_or_type=structure_key,
        location=location_name,
        duration_seconds=video_duration,
        language="ru",
    )
    clickbait_title_en = generate_clickbait_title(
        content_type="monument",
        style_or_type=structure_key,
        location=location_name,
        duration_seconds=video_duration,
        language="en",
    )

    publishing_ru_raw = await generate_publishing_metadata(
        structure_type=structure_key,
        location=location_name,
        stages=stages,
        title=title,
        language="ru",
        force_title=clickbait_title_ru,
    )
    publishing_en_raw = await generate_publishing_metadata(
        structure_type=structure_key,
        location=location_name,
        stages=stages,
        title=title,
        language="en",
        force_title=clickbait_title_en,
    )
    publishing = {"ru": publishing_ru_raw, "en": publishing_en_raw}

    from agents.topics_history import mark_topic_used
    mark_topic_used(
        topic=f"[Monument] {title}",
        session_id=session_id,
        video_path=str(assembled_path),
        video_angle=f"structure={structure_name},location={location_name},stages={len(stages)},duration={video_duration:.2f}s",
        publishing=publishing,
    )

    logger.success(f"=== Mode 11 Pipeline DONE | video={video_path} ===")

    return {
        "session_id": session_id,
        "video_path": video_path,
        "topic": title,
        "scenario": enriched_scenario,
        "structure": structure_name,
        "stages": len(stages),
        "trend": None,
        "report": None,
        "publishing": publishing,
    }
