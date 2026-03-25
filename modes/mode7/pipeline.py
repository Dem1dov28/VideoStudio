"""
Mode 7 Pipeline — Viral Animal Keyboard Video Generator.

Generates short satisfying videos featuring animals interacting
with unusual surfaces (honey, slime, ice, chocolate, etc.)
for TikTok/Reels/Shorts format.

Flow:
  1. Scenario Writer — Generate scenario with animal + surface
  2. Video Generator — Create video clips via FastGen
  3. Video Assembler — Combine into final video with music
"""

from __future__ import annotations

import functools
import time
from pathlib import Path
from typing import Any

from loguru import logger

from config import settings
from modes.mode7.scenario_writer import run_mode7_scenario_writer
from modes.mode7.video_generator import generate_animal_videos
from modes.mode7.video_assembler import assemble_mode7_video


async def run_mode7_pipeline(
    session_id: str | None = None,
    local_only: bool = True,
    keyboards: list[str] | None = None,
    animal_type: str | None = None,
    language: str = "ru",
    control: dict | None = None,
) -> dict[str, Any]:
    """
    Run the ASMR animal keyboard video pipeline.
    
    Args:
        session_id: Unique run identifier.
        local_only: If True, skip publishing.
        keyboards: List of keyboard types to include (3-4 keyboards).
        animal_type: Animal preference ("cat", "dog", "kitten", "puppy", "random", or None).
        language: Output language ("ru" or "en").
        control: Pause/cancel control dict.
    
    Returns:
        dict with video_path, session_id, scenario, etc.
    """
    import asyncio
    from pipeline_control import checkpoint
    
    session_id = session_id or str(int(time.time() * 1000))
    videos_dir = settings.videos_dir
    clips_dir = videos_dir / session_id / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(
        f"=== Mode 7 Pipeline | ASMR Keyboard | "
        f"session={session_id} | keyboards={keyboards} | animal={animal_type or 'random'} ==="
    )
    
    # Step 1: Generate scenario
    await checkpoint(control)
    logger.info("Step 1/3 - ASMR Scenario Writer")
    
    scenario = await run_mode7_scenario_writer(
        keyboards=keyboards,
        animal_type=animal_type,
        language=language,
        control=control,
    )
    
    title = scenario.get("title", "ASMR Keyboard")
    animal = scenario.get("animal", "cat")
    keyboards_list = scenario.get("keyboards", [])
    logger.success(f"[Mode7] Scenario: {title} | {animal} | keyboards={keyboards_list}")
    
    # Step 2: Generate video clips via FastGen
    await checkpoint(control)
    logger.info("Step 2/3 - Animal Video Generator (FastGen)")
    
    video_paths, enriched_scenario = await generate_animal_videos(
        scenario=scenario,
        output_dir=clips_dir,
        session_id=session_id,
        language=language,
    )
    
    valid_paths = [p for p in video_paths if p and Path(p).exists()]
    if not valid_paths:
        raise RuntimeError("[Mode7] No video clips generated")
    
    logger.success(f"[Mode7] Generated {len(valid_paths)} video clips")
    
    # Step 3: Assemble final video
    await checkpoint(control)
    logger.info("Step 3/3 - Video Assembly")
    
    output_path = videos_dir / f"video_{session_id}.mp4"
    
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        functools.partial(
            assemble_mode7_video,
            valid_paths,
            output_path,
            title=title,
        ),
    )
    
    # Record in history
    from agents.topics_history import mark_topic_used
    mark_topic_used(
        topic=f"[ASMR] {title}",
        session_id=session_id,
        video_path=str(output_path),
        video_angle=f"animal={animal},keyboards={','.join(keyboards_list)}",
    )
    
    video_path = str(output_path.resolve())
    
    logger.success(f"=== Mode 7 Pipeline DONE | video={video_path} ===")
    
    return {
        "session_id": session_id,
        "video_path": video_path,
        "topic": title,
        "scenario": enriched_scenario,
        "animal": animal,
        "keyboards": keyboards_list,
        "trend": None,
        "report": None,
    }
