"""
Mode 10 Video Generator — Beach cleanup timelapse (keyframe-цепочка как mode8).

Те же шаги: последовательные still с ref-цепочкой → keyframe-видео между стадиями.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from loguru import logger

from agents.content_generator.fastgen_scraper import (
    generate_single_video_multi_ref,
    generate_video_from_keyframes,
)
from config import settings


# ═══════════════════════════════════════════════════════════════════════════
# BEACH TYPE + COAST (согласованы с modes/mode10/scenario_writer.py)
# ═══════════════════════════════════════════════════════════════════════════

BEACH_TYPE_VISUALS = {
    "tropical": {
        "visual": "white coral sand, palm trees at edge, turquoise water",
        "features": "tropical beach, bright sand, palm silhouettes, clear sea",
    },
    "urban": {
        "visual": "city beach near waterfront promenade, distant skyline, pier or breakwater",
        "features": "urban coastal, buildings in background, structured shore",
    },
    "rocky_cove": {
        "visual": "sand and pebbles, large rocks at sides, some seaweed at tideline",
        "features": "rocky cove, natural stones, intimate bay",
    },
    "resort": {
        "visual": "groomed sand, distant umbrellas and boardwalk, lounge chairs",
        "features": "resort beach, maintained shore, vacation atmosphere",
    },
    "wild": {
        "visual": "natural undeveloped shore, dunes with grass, no buildings",
        "features": "wild beach, dunes, untouched coastline",
    },
}

COAST_SETTING_VISUALS = {
    "morning_calm": {
        "visual": "soft morning light, calm sea, long gentle shadows on sand",
        "features": "calm morning, pale sky, peaceful horizon",
    },
    "midday_bright": {
        "visual": "bright overhead sun, short shadows, vivid blue sky",
        "features": "midday sun, sparkling water, high contrast",
    },
    "golden_hour": {
        "visual": "warm golden sunlight, long shadows on sand, sunset tones on water",
        "features": "golden hour, cinematic warm light",
    },
    "overcast_soft": {
        "visual": "soft diffused light, even tones, no harsh shadows",
        "features": "overcast, muted sky, calm mood",
    },
    "breezy": {
        "visual": "lively waves, foam line, grass on dunes moving in wind",
        "features": "breezy day, whitecaps, dynamic sky",
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# PROMPT BUILDERS
# ═══════════════════════════════════════════════════════════════════════════

def _build_image_prompt(
    scene: dict[str, Any],
    index: int,
    scenario: dict[str, Any],
    language: str = "ru",
) -> str:
    """Still для таймлапса уборки пляжа — фотореализм, смартфон."""
    beach_type = scenario.get("beach_type", "tropical")
    location = scenario.get("location", "morning_calm")

    style_visual = BEACH_TYPE_VISUALS.get(beach_type, BEACH_TYPE_VISUALS["tropical"])
    loc_visual = COAST_SETTING_VISUALS.get(location, COAST_SETTING_VISUALS["morning_calm"])

    stage_name = scene.get("name", "этап уборки")
    stage_name_en = scene.get("name_en", "cleanup stage")
    visual_prompt = scene.get("visual_prompt", "")

    if language == "en":
        title_line = f"STAGE: {stage_name_en.upper()} — beach cleanup stage {index + 1}"
    else:
        title_line = f"STAGE: {stage_name.upper()} — стадия уборки пляжа {index + 1}"

    prompt = f"""Create a photorealistic still image for a BEACH CLEANUP timelapse video.

━━━ CRITICAL: BACKGROUND STAYS THE SAME! ━━━
The BACKGROUND (horizon, sea, sky, distant land/pier, dune line, fixed landmarks) MUST REMAIN EXACTLY THE SAME across all stages!
- Same sky, same cloud positions, same wave pattern feel
- Same shoreline geometry, same camera position
- ONLY THE AMOUNT OF TRASH / CLEANLINESS / ACTIVITY ON SAND CHANGES — background is FROZEN!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ CONTENT SAFETY (MANDATORY) ━━━
Generic content only. NO brands, logos, readable text. Generic tools, generic vehicles, no identifiable people.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STYLE: Photorealistic smartphone photo, natural light. NOT CGI, NOT cartoon.

{title_line}

BEACH TYPE: {style_visual['visual']}
Features: {style_visual['features']}

COAST LIGHTING / MOOD: {loc_visual['visual']}
Atmosphere: {loc_visual['features']}

SCENE DESCRIPTION:
{visual_prompt}

COMPOSITION:
- Wide shot of the beach cleanup area, vertical 9:16
- Same tripod angle as other stages
- Sand, debris, bags, rakes, volunteers, optional small loader — as appropriate
- Real wet sand, foam line, natural imperfections

CRITICAL:
- REAL photo look; if reference image provided, match EXACT camera angle
- BACKGROUND FROZEN — only cleanup state evolves"""

    return prompt


def _build_video_prompt(
    scene: dict[str, Any],
    index: int,
    total_stages: int,
    scenario: dict[str, Any],
    language: str = "ru",
) -> str:
    """Видео-промпт: реальная уборка пляжа, таймлапс, не магия."""
    beach_type = scenario.get("beach_type", "tropical")
    location = scenario.get("location", "morning_calm")

    style_visual = BEACH_TYPE_VISUALS.get(beach_type, BEACH_TYPE_VISUALS["tropical"])
    loc_visual = COAST_SETTING_VISUALS.get(location, COAST_SETTING_VISUALS["morning_calm"])

    start_state = scene.get("start_state", "previous stage")
    end_state = scene.get("end_state", "next stage")
    action = scene.get("action", "construction work")
    stage_name = scene.get("name", "этап уборки")
    stage_name_en = scene.get("name_en", "cleanup stage")

    # Stage-specific workers and machinery
    workers = scene.get("workers") if language == "ru" else scene.get("workers_en")
    machinery = scene.get("machinery") if language == "ru" else scene.get("machinery_en")
    micro_actions = scene.get("micro_actions") if language == "ru" else scene.get("micro_actions_en")
    
    # NEW: Intensity, temporal, peak moment
    build_intensity = scene.get("build_intensity", "medium")
    time_of_day = scene.get("time_of_day", "midday")
    is_peak_moment = scene.get("is_peak_moment", False)

    if language == "en":
        transformation_title = f"BEACH CLEANUP STAGE: {stage_name_en.upper()}"
    else:
        transformation_title = f"ЭТАП УБОРКИ ПЛЯЖА: {stage_name.upper()}"

    # ===== BUILD INTENSITY SECTION =====
    intensity_section = {
        "low": """
ACTIVITY LEVEL: LOW
- Fewer people, slower cleanup pace
- Calm early stage""",
        "medium": """
ACTIVITY LEVEL: MEDIUM
- Several volunteers actively picking, raking, bagging
- Steady cleanup pace""",
        "high": """
ACTIVITY LEVEL: HIGH
- Many people and/or machinery moving
- Visually busy satisfying cleanup""",
    }.get(build_intensity, "ACTIVITY LEVEL: MEDIUM")

    # ===== TIME OF DAY / LIGHTING SECTION =====
    lighting_section = {
        "morning": """
LIGHTING: Early morning light
- Soft, warm sunlight from low angle
- Long shadows stretching across site
- Fresh, clean atmosphere, dew on ground""",
        "midday": """
LIGHTING: Midday sun
- Bright, direct sunlight overhead
- Short, crisp shadows
- Hot, active work environment""",
        "afternoon": """
LIGHTING: Afternoon golden light
- Warm sunlight from the side
- Medium shadows, rich contrast
- Active but comfortable atmosphere""",
        "golden_hour": """
LIGHTING: Golden hour (MAGIC HOUR)
- Beautiful warm, golden sunlight
- Long, dramatic shadows
- Cinematic, photogenic atmosphere
- Perfect for final reveal shots""",
    }.get(time_of_day, "LIGHTING: Natural daylight")

    # ===== PEAK MOMENT EMPHASIS =====
    peak_section = ""
    if is_peak_moment:
        peak_section = """
━━━ PEAK MOMENT ━━━
Most dramatic cleanup moment — loader, big bag haul, or major visible change.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

    # Build workers section
    workers_section = ""
    if workers:
        workers_section = f"""
VOLUNTEERS / PEOPLE:
{workers}
- Realistic bending, bagging, raking, carrying
- Motion blur (timelapse)"""
    else:
        workers_section = """
VOLUNTEERS / PEOPLE:
- Picking trash, filling bags, raking sand
- Timelapse motion blur"""

    # Build machinery section
    machinery_section = ""
    if machinery:
        machinery_section = f"""
EQUIPMENT IN MOTION:
{machinery}
- Loader or truck actively moving bags off the beach"""
    else:
        machinery_section = """
EQUIPMENT (if any):
- Small loader or utility vehicle helping haul bags"""

    # Build micro-actions section
    micro_actions_section = ""
    if micro_actions and len(micro_actions) > 0:
        actions_text = "\n".join([f"- {a}" for a in micro_actions[:5]])  # Max 5 actions
        micro_actions_section = f"""
SPECIFIC MICRO-ACTIONS VISIBLE:
{actions_text}
- These actions happen in sequence, showing real work being done"""

    prompt = f"""A satisfying BEACH CLEANUP timelapse — real work between two stages.

{transformation_title}

BEACH: {style_visual['visual']}
COAST MOOD: {loc_visual['visual']}
{peak_section}
━━━ SHOW REAL CLEANUP WORK ━━━
{workers_section}
{machinery_section}
{intensity_section}

THE BEACH GETS CLEANER THROUGH BELIEVABLE ACTIONS:
- Trash removed step by step, bags fill, sand gets cleaner
- NOT magic wipe — physical picking, raking, hauling
{micro_actions_section}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TRANSITION:
FROM: {start_state}
TO: {end_state}

MAIN ACTIVITY: {action}

━━━ CAMERA ━━━
Fixed tripod, same angle; only cleanup state changes. Subtle micro-shake OK.

━━━ MOTION ━━━
Forward-only timelapse, smooth, no time-reverse tricks.

━━━ REALISM ━━━
Wet sand, foam, scattered debris, footprints, imperfect piles — lived-in beach.
{lighting_section}

FRAMING: Vertical 9:16, wide beach shot.

AUDIO: Waves, wind, distant voices, bags rustling — NO music, NO voiceover in prompt.

STYLE: Photorealistic, smooth motion.

━━━ KEYFRAME ━━━
Strictly interpolate start frame → end frame. Horizon and sea line stay consistent.

━━━ SAFETY ━━━
No injuries, no dangerous stunts. Positive environmental cleanup only.
"""

    return prompt


def _build_keyframe_video_prompt(
    scene: dict[str, Any],
    scenario: dict[str, Any],
    language: str = "ru",
) -> str:
    """Короткий keyframe-промпт для FastGen."""
    beach_type = scenario.get("beach_type", "tropical")
    location = scenario.get("location", "morning_calm")

    style_visual = BEACH_TYPE_VISUALS.get(beach_type, BEACH_TYPE_VISUALS["tropical"])
    loc_visual = COAST_SETTING_VISUALS.get(location, COAST_SETTING_VISUALS["morning_calm"])

    start_state = scene.get("start_state", "previous stage")
    end_state = scene.get("end_state", "next stage")
    action = scene.get("action", "beach cleanup")
    stage_name_en = scene.get("name_en", "cleanup stage")

    workers = scene.get("workers") if language == "ru" else scene.get("workers_en")
    machinery = scene.get("machinery") if language == "ru" else scene.get("machinery_en")

    workers_short = (workers[:80] + "...") if workers and len(workers) > 80 else (workers or "volunteers active")
    machinery_short = (machinery[:80] + "...") if machinery and len(machinery) > 80 else (machinery or "equipment if any")

    prompt = f"""Wide shot (WS), beach cleanup timelapse: {stage_name_en}.
{style_visual['visual']}, {loc_visual['visual']}.

SUBJECT: {action}. People: {workers_short}. Equipment: {machinery_short}.

CAMERA: Locked tripod, static. TEMPORAL: time-lapse, forward only.

TRANSITION: "{start_state}" → "{end_state}". Match start/end frames.

BACKGROUND: Horizon, sea, sky FROZEN. Only trash/clean sand/activity changes.

SAFETY: Generic, no brands. TECH: vertical 9:16, photorealistic."""

    return prompt
# ═══════════════════════════════════════════════════════════════════════════

async def _generate_single_image_with_ref(
    prompt: str,
    output_dir: Path,
    index: int,
    reference_image_paths: list[Path],
) -> Path | None:
    """
    Generate a single reference image using FastGen.
    Uses the previous image as reference for continuity.
    """
    try:
        from agents.content_generator.fastgen_scraper import (
            generate_images_with_references_fastgen,
        )

        # Call with single item list (we generate one at a time)
        prompts_with_refs = [(prompt, reference_image_paths)]

        image_paths = await generate_images_with_references_fastgen(
            prompts_with_refs,
            output_dir,
            parallel=False,  # Sequential generation
        )

        if image_paths and len(image_paths) > 0:
            img_path = image_paths[0]
            if img_path and Path(img_path).exists():
                # Rename to scene index
                new_path = output_dir / f"stage_{index:03d}_ref.png"
                Path(img_path).rename(new_path)
                return new_path

        return None

    except Exception as e:
        logger.error(f"[Mode10] Image generation failed for stage {index}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# VIDEO GENERATION
# ═══════════════════════════════════════════════════════════════════════════

async def _generate_single_video(
    index: int,
    prompt: str,
    reference_image_paths: list[Path],
    output_dir: Path,
) -> Path | None:
    """Generate a single timelapse video with reference image."""
    try:
        result = await generate_single_video_multi_ref(
            index=index,
            prompt=prompt,
            output_dir=output_dir,
            reference_image_paths=reference_image_paths,
        )

        if result and Path(result).exists():
            logger.success(f"[Mode10] Stage {index + 1} video saved: {Path(result).name}")
            return result
        else:
            logger.error(f"[Mode10] Stage {index + 1}: Video generation returned no result")
            return None

    except Exception as e:
        logger.error(f"[Mode10] Stage {index + 1} video generation failed: {e}")
        return None


async def _generate_keyframe_video(
    index: int,
    prompt: str,
    start_frame: Path,
    end_frame: Path,
    output_dir: Path,
) -> Path | None:
    """
    Generate a video transitioning from start_frame to end_frame using keyframes.
    This is the PREFERRED method for smooth transitions between construction stages.
    """
    try:
        result = await generate_video_from_keyframes(
            prompt=prompt,
            output_dir=output_dir,
            start_frame_path=start_frame,
            end_frame_path=end_frame,
            index=index,
        )

        if result and Path(result).exists():
            logger.success(f"[Mode10] Keyframe video {index + 1} saved: {Path(result).name}")
            return result
        else:
            logger.error(f"[Mode10] Keyframe video {index + 1}: Generation returned no result")
            return None

    except Exception as e:
        logger.error(f"[Mode10] Keyframe video {index + 1} generation failed: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# MAIN GENERATION FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

async def generate_beach_cleanup_videos(
    scenario: dict[str, Any],
    output_dir: Path,
    session_id: str,
    language: str = "ru",
) -> tuple[list[Path | None], dict[str, Any]]:
    """
    Generate beach cleanup timelapse clips via FastGen.

    WORKFLOW (KEYFRAME APPROACH):
    1. SEQUENTIAL image generation with reference chaining:
       - Stage 0: generate with NO reference
       - Stage 1: generate with stage 0 image as reference
       - Stage 2: generate with stage 1 image as reference
       - ... and so on

    2. KEYFRAME video generation (transition between stages):
       - Video 0: transition from stage_0 to stage_1
       - Video 1: transition from stage_1 to stage_2
       - ...
       - Video N-1: transition from stage_(N-1) to stage_N

    Returns:
        Tuple of (list of video paths, enriched scenario)
    """
    scenes = scenario.get("scenes", [])

    if not scenes:
        raise ValueError("[Mode10] No scenes to generate")

    fastgen_key = getattr(settings, "fastgen_api_key", "") or ""
    if not fastgen_key:
        raise RuntimeError("FASTGEN_API_KEY not set — required for Mode 10")

    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "reference_images"
    images_dir.mkdir(parents=True, exist_ok=True)

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 1: SEQUENTIAL image generation with reference chaining
    # ═══════════════════════════════════════════════════════════════════════

    logger.info(f"[Mode10] STEP 1: Generating {len(scenes)} reference images SEQUENTIALLY (chaining)...")

    ref_image_paths: list[Path | None] = []
    previous_image: Path | None = None

    for i, scene in enumerate(scenes):
        # Build image prompt
        image_prompt = _build_image_prompt(scene, i, scenario, language)

        # Reference = previous image (for continuity)
        refs = [previous_image] if previous_image else []

        # Generate ONE image (sequential, not parallel)
        logger.info(
            f"[Mode10] Generating image {i + 1}/{len(scenes)}: {scene.get('stage_key', 'stage')} "
            f"(with {len(refs)} reference(s))"
        )

        image_path = await _generate_single_image_with_ref(
            prompt=image_prompt,
            output_dir=images_dir,
            index=i,
            reference_image_paths=refs,
        )

        if image_path:
            ref_image_paths.append(image_path)
            previous_image = image_path  # Chain to next stage
            logger.success(f"[Mode10] Stage {i + 1} reference image: {image_path.name}")
        else:
            ref_image_paths.append(None)
            logger.error(f"[Mode10] Stage {i + 1}: Failed to generate reference image")
            # Don't break — continue with None, but warn
            if i < len(scenes) - 1:
                logger.warning(f"[Mode10] Stage {i + 2} will have no reference image!")

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 2: KEYFRAME video generation (transition between stages)
    # ═══════════════════════════════════════════════════════════════════════

    # Number of videos = number of transitions = N-1 (if we have N stages)
    # But we can also generate N videos where each shows progress to that stage
    num_videos = len(scenes) - 1  # Transitions between stages
    
    if num_videos < 1:
        raise ValueError("[Mode10] Need at least 2 stages for keyframe video generation")
    
    logger.info(f"[Mode10] STEP 2: Generating {num_videos} KEYFRAME videos (transitions between stages)...")

    video_tasks = []
    for i in range(num_videos):
        # Get start and end frames for this transition
        start_frame = ref_image_paths[i] if i < len(ref_image_paths) else None
        end_frame = ref_image_paths[i + 1] if i + 1 < len(ref_image_paths) else None

        # Both frames must exist for keyframe generation
        if not start_frame or not end_frame:
            logger.warning(f"[Mode10] Skipping video {i}: missing frames")
            video_tasks.append(asyncio.create_task(asyncio.sleep(0)))  # Placeholder
            continue
        
        if not Path(start_frame).exists() or not Path(end_frame).exists():
            logger.warning(f"[Mode10] Skipping video {i}: frame files not found")
            video_tasks.append(asyncio.create_task(asyncio.sleep(0)))  # Placeholder
            continue

        # Build SHORT video prompt for FastGen (limited input capacity)
        scene = scenes[i]  # Current stage
        
        video_prompt = _build_keyframe_video_prompt(
            scene,
            scenario,
            language,
        )

        task = _generate_keyframe_video(
            index=i,
            prompt=video_prompt,
            start_frame=Path(start_frame),
            end_frame=Path(end_frame),
            output_dir=output_dir,
        )
        video_tasks.append(task)

    # Generate ALL videos in parallel
    video_paths = await asyncio.gather(*video_tasks, return_exceptions=True)

    # Handle results
    valid_paths: list[Path | None] = []
    for i, result in enumerate(video_paths):
        if isinstance(result, Exception):
            logger.error(f"[Mode10] Keyframe video {i + 1} failed: {result}")
            valid_paths.append(None)
        elif result is None:
            # Placeholder task (skipped)
            valid_paths.append(None)
        else:
            valid_paths.append(result)

    # Enrich scenario with video paths and reference image paths
    enriched_scenes = []
    for i, scene in enumerate(scenes):
        enriched_scene = dict(scene)
        if i < len(ref_image_paths) and ref_image_paths[i]:
            enriched_scene["reference_image_path"] = str(ref_image_paths[i])
        # Video for stage i shows transition to this stage
        if i > 0 and i - 1 < len(valid_paths) and valid_paths[i - 1]:
            enriched_scene["video_path"] = str(valid_paths[i - 1])
        enriched_scenes.append(enriched_scene)

    enriched_scenario = dict(scenario)
    enriched_scenario["scenes"] = enriched_scenes

    valid_count = sum(1 for p in valid_paths if p and Path(p).exists())
    ref_count = sum(1 for p in ref_image_paths if p and Path(p).exists())
    logger.success(
        f"[Mode10] Generated {ref_count}/{len(scenes)} reference images "
        f"and {valid_count}/{num_videos} keyframe videos"
    )

    return valid_paths, enriched_scenario
