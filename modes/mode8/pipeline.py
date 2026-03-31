"""
Mode 8 Pipeline — House Building Timelapse Video Generator.

Generates satisfying timelapse videos showing house construction progress.
Uses KEYFRAME approach for smooth transitions between stages.

Flow:
  1. Scenario Writer — Generate building stages (empty land -> finished house)
  2. Video Generator — Sequential images + KEYFRAME videos (transitions between stages)
  3. Video Assembler — Combine into final timelapse with construction sounds
"""

from __future__ import annotations

import functools
import time
from pathlib import Path
from typing import Any

from loguru import logger

from config import settings
from modes.mode8.scenario_writer import run_mode8_scenario_writer
from modes.mode8.video_generator import generate_house_videos
from modes.mode8.video_assembler import assemble_mode8_video
from modes.mode8.publishing_metadata import generate_publishing_metadata


async def _run_mode8_user_keyframes_pipeline(
    session_id: str,
    local_only: bool,
    start_frame_path: str,
    end_frame_path: str,
    language: str,
    control: dict | None,
) -> dict[str, Any]:
    """Один ролик FastGen по двум загруженным кадрам (как в UI «Свои keyframes»)."""
    import asyncio

    from modes.mode8.clickbait_titles import generate_clickbait_title
    from modes.mode8.video_generator import _build_keyframe_video_prompt, _generate_keyframe_video
    from pipeline_control import checkpoint

    videos_dir = settings.videos_dir
    clips_dir = videos_dir / session_id / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    start_p = Path(start_frame_path).resolve()
    end_p = Path(end_frame_path).resolve()
    if not start_p.is_file() or not end_p.is_file():
        raise FileNotFoundError("Mode 8 keyframes: файлы не найдены")

    await checkpoint(control)
    logger.info("[Mode8] Режим пользовательских keyframes: один переход start→end")

    minimal_scenario: dict[str, Any] = {
        "title": "Custom keyframe transition",
        "house_style": "modern",
        "location": "suburbs",
        "num_floors": 2,
        "house_style_name": "custom",
        "location_name": "keyframes",
        "scenes": [],
    }
    minimal_scene: dict[str, Any] = {
        "name_en": "Construction transition",
        "start_state_en": "initial frame composition",
        "end_state_en": "final frame composition",
        "action_en": "smooth timelapse transition strictly matching both keyframes",
        "workers_en": "construction crew active on site",
        "machinery_en": "generic construction equipment",
    }

    video_prompt = _build_keyframe_video_prompt(minimal_scene, minimal_scenario, language)
    clip_path = await _generate_keyframe_video(
        index=0,
        prompt=video_prompt,
        start_frame=start_p,
        end_frame=end_p,
        output_dir=clips_dir,
    )
    if not clip_path or not Path(clip_path).exists():
        raise RuntimeError("[Mode8] Не удалось сгенерировать видео по двум кадрам")

    await checkpoint(control)
    output_path = videos_dir / f"video_{session_id}.mp4"
    loop = asyncio.get_event_loop()
    assembled_path, video_duration = await loop.run_in_executor(
        None,
        functools.partial(
            assemble_mode8_video,
            [clip_path],
            output_path,
            title="Custom keyframes",
            preview_image_path=None,
            preview_duration=0.3,
        ),
    )

    video_path = str(assembled_path.resolve())
    logger.success(f"[Mode8] Custom keyframes | duration={video_duration:.2f}s")

    house_style_name = "custom"
    location_name = "keyframes"
    title = "House timelapse (custom keyframes)"
    stages: list[Any] = []

    logger.info("Step 4/4 - Publishing metadata (custom keyframes)...")
    clickbait_title_ru = generate_clickbait_title(
        content_type="house",
        style_or_type=house_style_name,
        location=location_name,
        duration_seconds=video_duration,
        language="ru",
    )
    clickbait_title_en = generate_clickbait_title(
        content_type="house",
        style_or_type=house_style_name,
        location=location_name,
        duration_seconds=video_duration,
        language="en",
    )
    publishing_ru_raw = await generate_publishing_metadata(
        house_style=house_style_name,
        location=location_name,
        stages=stages,
        title=title,
        language="ru",
        force_title=clickbait_title_ru,
    )
    publishing_en_raw = await generate_publishing_metadata(
        house_style=house_style_name,
        location=location_name,
        stages=stages,
        title=title,
        language="en",
        force_title=clickbait_title_en,
    )
    publishing = {"ru": publishing_ru_raw, "en": publishing_en_raw}

    enriched_scenario = {
        **minimal_scenario,
        "custom_keyframes": True,
        "start_frame": str(start_p),
        "end_frame": str(end_p),
    }

    from agents.topics_history import mark_topic_used

    mark_topic_used(
        topic=f"[Timelapse] {title}",
        session_id=session_id,
        video_path=str(assembled_path),
        video_angle="mode=custom_keyframes",
        publishing=publishing,
    )

    _ = local_only
    logger.success(f"=== Mode 8 CUSTOM KEYFRAMES DONE | video={video_path} ===")

    return {
        "session_id": session_id,
        "video_path": video_path,
        "topic": title,
        "scenario": enriched_scenario,
        "house_style": house_style_name,
        "location": location_name,
        "stages": 0,
        "trend": None,
        "report": None,
        "publishing": publishing,
    }


async def run_mode8_pipeline(
    session_id: str | None = None,
    local_only: bool = True,
    house_style: str | None = None,
    location: str | None = None,
    num_stages: int = 5,
    num_floors: int = 2,  # NEW: Number of floors
    language: str = "ru",
    control: dict | None = None,
    *,
    use_keyframes: bool = False,
    start_frame_path: str | None = None,
    end_frame_path: str | None = None,
) -> dict[str, Any]:
    """
    Run the House Building Timelapse video pipeline.

    Args:
        session_id: Unique run identifier.
        local_only: If True, skip publishing.
        house_style: House style preference (modern, cottage, villa, cabin, farmhouse, random).
        location: Location preference (suburbs, forest, seaside, countryside, mountains, random).
        num_stages: Number of building stages (5-8).
        num_floors: Number of floors in the house (1-3).
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

    sf = (start_frame_path or "").strip()
    ef = (end_frame_path or "").strip()
    if use_keyframes and sf and ef:
        logger.info(f"=== Mode 8 Pipeline | CUSTOM KEYFRAMES | session={session_id} ===")
        return await _run_mode8_user_keyframes_pipeline(
            session_id=session_id,
            local_only=local_only,
            start_frame_path=sf,
            end_frame_path=ef,
            language=language,
            control=control,
        )

    logger.info(
        f"=== Mode 8 Pipeline | House Building Timelapse | "
        f"session={session_id} | style={house_style or 'random'} | "
        f"location={location or 'random'} | stages={num_stages} | floors={num_floors} ==="
    )

    # Step 1: Generate scenario (building stages)
    await checkpoint(control)
    logger.info("Step 1/4 - Generating Building Scenario...")

    scenario = await run_mode8_scenario_writer(
        house_style=house_style,
        location=location,
        num_stages=num_stages,
        num_floors=num_floors,  # NEW: pass floors
        language=language,
        control=control,
    )

    title = scenario.get("title", "House Building Timelapse")
    house_style_name = scenario.get("house_style_name", "house")
    location_name = scenario.get("location_name", "location")
    stages = scenario.get("scenes", [])
    logger.success(
        f"[Mode8] Scenario: {title} | {house_style_name} | {location_name} | "
        f"{len(stages)} stages"
    )

    # Step 2: Generate video clips via FastGen (sequential images + KEYFRAME videos)
    await checkpoint(control)
    logger.info("Step 2/4 - House Video Generator (Sequential Images + Keyframe Videos)")

    video_paths, enriched_scenario = await generate_house_videos(
        scenario=scenario,
        output_dir=clips_dir,
        session_id=session_id,
        language=language,
        use_contextual=True,  # Enable new contextual prompt generation
        generate_preview=True,  # Enable clickbait preview generation
    )

    valid_paths = [p for p in video_paths if p and Path(p).exists()]
    if not valid_paths:
        raise RuntimeError("[Mode8] No video clips generated")

    # N+1 images produce N videos: N-1 keyframe transitions (between construction stages) + 1 bonus drone shot (construction → aerial showcase)
    expected_videos = len(stages)  # N-1 keyframe + 1 drone
    logger.success(f"[Mode8] Generated {len(valid_paths)}/{expected_videos} videos (includes final drone showcase)")

    # Step 3: Assemble final video
    await checkpoint(control)
    logger.info("Step 3/4 - Video Assembly")

    output_path = videos_dir / f"video_{session_id}.mp4"

    # Get preview path from enriched scenario if available
    preview_path = enriched_scenario.get("preview_path")
    
    # Log preview path for debugging
    if preview_path:
        logger.success(f"[Mode8] Preview path found: {preview_path}")
        preview_path_obj = Path(preview_path)
        if preview_path_obj.exists():
            logger.info(f"[Mode8] Preview file exists: {preview_path}")
            logger.info(f"[Mode8] Preview will be appended to final video (0.3s)")
        else:
            logger.error(f"[Mode8] Preview file does NOT exist: {preview_path}")
            preview_path = None  # Reset to None so assembler won't try to add it
    else:
        logger.warning("[Mode8] No preview path in enriched scenario - preview will NOT be added to final video")
    
    loop = asyncio.get_event_loop()
    assembled_path, video_duration = await loop.run_in_executor(
        None,
        functools.partial(
            assemble_mode8_video,
            valid_paths,
            output_path,
            title=title,
            preview_image_path=preview_path,  # Pass preview to assembler
            preview_duration=0.3,  # Show preview for 0.3 seconds at end
        ),
    )

    video_path = str(assembled_path.resolve())
    logger.success(f"[Mode8] Final video duration: {video_duration:.2f}s")

    # Step 4: Generate clickbait title with real duration + publishing metadata
    logger.info("Step 4/4 - Generating Clickbait Title + Publishing Metadata (RU & EN)...")
    
    from modes.mode8.clickbait_titles import generate_clickbait_title
    
    # Generate clickbait title using real video duration (RU version)
    clickbait_title_ru = generate_clickbait_title(
        content_type="house",
        style_or_type=house_style_name,
        location=location_name,
        duration_seconds=video_duration,
        language="ru",  # Russian for RU publishing
    )
    logger.success(f"[Mode8] Clickbait title (RU): {clickbait_title_ru}")
    
    # Generate English clickbait title
    clickbait_title_en = generate_clickbait_title(
        content_type="house",
        style_or_type=house_style_name,
        location=location_name,
        duration_seconds=video_duration,
        language="en",  # English for EN publishing
    )
    logger.success(f"[Mode8] Clickbait title (EN): {clickbait_title_en}")
    
    # Generate full publishing metadata with forced clickbait title
    publishing_ru_raw = await generate_publishing_metadata(
        house_style=house_style_name,
        location=location_name,
        stages=stages,
        title=title,  # Pass original title to LLM for context
        language="ru",
        force_title=clickbait_title_ru,  # Force Russian clickbait title
    )
    publishing_en_raw = await generate_publishing_metadata(
        house_style=house_style_name,
        location=location_name,
        stages=stages,
        title=title,  # Pass original title to LLM for context
        language="en",
        force_title=clickbait_title_en,  # Force English clickbait title
    )
    
    # Create final publishing (titles already forced in generate_publishing_metadata)
    publishing = {
        "ru": publishing_ru_raw,
        "en": publishing_en_raw,
    }

    # Record in history
    from agents.topics_history import mark_topic_used
    mark_topic_used(
        topic=f"[Timelapse] {title}",  # Keep original topic format
        session_id=session_id,
        video_path=str(assembled_path),
        video_angle=f"style={house_style_name},location={location_name},stages={len(stages)},duration={video_duration:.2f}s",
        publishing=publishing,
    )

    logger.success(f"=== Mode 8 Pipeline DONE | video={video_path} ===")

    return {
        "session_id": session_id,
        "video_path": video_path,
        "topic": title,
        "scenario": enriched_scenario,
        "house_style": house_style_name,
        "location": location_name,
        "stages": len(stages),
        "trend": None,
        "report": None,
        "publishing": publishing,
    }
