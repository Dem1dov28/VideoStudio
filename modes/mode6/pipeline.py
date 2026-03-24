"""
Mode 6 Pipeline — Viral Cartoon Drama Generator.

Generates short absurd cartoon stories with vegetable characters
for TikTok/Reels/Shorts format.

Flow:
  1. Scenario Writer — Generate absurd drama scenario
  2. Video Generator — Create video clips via FastGen with character references
  3. Video Assembler — Combine into final video with music
"""

from __future__ import annotations

import functools
import time
from pathlib import Path
from typing import Any

from loguru import logger

from config import settings
from modes.mode6.scenario_writer import run_mode6_scenario_writer
from modes.mode6.video_generator import generate_cartoon_videos
from modes.mode6.video_assembler import assemble_mode6_video


async def run_mode6_pipeline(
    session_id: str | None = None,
    local_only: bool = True,
    num_scenes: int = 6,
    num_characters: int = 3,
    language: str = "ru",
    control: dict | None = None,
) -> dict[str, Any]:
    """
    Run the viral cartoon drama pipeline.
    
    Args:
        session_id: Unique run identifier.
        local_only: If True, skip publishing.
        num_scenes: Number of scenes (4-8).
        num_characters: Number of characters (2-4).
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
        f"=== Mode 6 Pipeline | Cartoon Drama | "
        f"session={session_id} | scenes={num_scenes} | characters={num_characters} ==="
    )
    
    # Step 1: Generate scenario
    await checkpoint(control)
    logger.info("Step 1/3 - Cartoon Scenario Writer")
    
    scenario = await run_mode6_scenario_writer(
        num_scenes=num_scenes,
        num_characters=num_characters,
        language=language,
        control=control,
    )
    
    title = scenario.get("title", "Овощная драма")
    logger.success(f"[Mode6] Scenario: {title} | {len(scenario.get('scenes', []))} scenes")
    
    # Step 2: Generate video clips via FastGen
    await checkpoint(control)
    logger.info("Step 2/3 - Cartoon Video Generator (FastGen)")
    
    video_paths, enriched_scenario = await generate_cartoon_videos(
        scenario=scenario,
        output_dir=clips_dir,
        session_id=session_id,
        language=language,
    )
    
    valid_paths = [p for p in video_paths if p and Path(p).exists()]
    if not valid_paths:
        raise RuntimeError("[Mode6] No video clips generated")
    
    logger.success(f"[Mode6] Generated {len(valid_paths)} video clips")
    
    # Step 3: Assemble final video
    await checkpoint(control)
    logger.info("Step 3/3 - Video Assembly")
    
    output_path = videos_dir / f"video_{session_id}.mp4"
    
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        functools.partial(
            assemble_mode6_video,
            valid_paths,
            output_path,
            title=title,
        ),
    )
    
    # Record in history
    from agents.topics_history import mark_topic_used
    mark_topic_used(
        topic=f"[Cartoon] {title}",
        session_id=session_id,
        video_path=str(output_path),
        video_angle=f"characters={','.join(scenario.get('characters', []))}",
    )
    
    video_path = str(output_path.resolve())
    
    logger.success(f"=== Mode 6 Pipeline DONE | video={video_path} ===")
    
    return {
        "session_id": session_id,
        "video_path": video_path,
        "topic": title,
        "scenario": enriched_scenario,
        "characters": scenario.get("characters", []),
        "total_absurdity": scenario.get("total_absurdity", 0),
        "trend": None,
        "report": None,
    }
