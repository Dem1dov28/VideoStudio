"""
Mode 9 Video Generator — Vehicle Assembly Timelapse.

KEYFRAME APPROACH for smooth transitions:
1. Generate ALL images SEQUENTIALLY with reference chaining:
   - Stage 0: generate with NO reference
   - Stage 1: generate with stage 0 image as reference
   - Continue chaining for all stages

2. Generate KEYFRAME videos (transitions between stages):
   - Video 0: transition from stage_0 to stage_1
   - Video 1: transition from stage_1 to stage_2
   - ...
   - Video N-1: transition from stage_(N-1) to stage_N

STYLE: Photorealistic timelapse with mechanics and machinery.
"""

from __future__ import annotations

import asyncio
import random
from pathlib import Path
from typing import Any

from loguru import logger

from agents.content_generator.fastgen_scraper import (
    generate_single_video_multi_ref,
    generate_video_from_keyframes,
)
from config import settings


# ═══════════════════════════════════════════════════════════════════════════
# VEHICLE TYPE VISUALS
# ═══════════════════════════════════════════════════════════════════════════

VEHICLE_TYPE_VISUALS = {
    # ✈️ АВИАЦИЯ
    "airplane_passenger": {
        "visual": "passenger airplane, metallic fuselage, wings with flaps, tail section, jet engines under wings",
        "features": "aluminum body, jet engines, swept wings, modern aviation design",
    },
    "airplane_private": {
        "visual": "luxury private jet, streamlined fuselage, small wings, spoilers",
        "features": "composite materials, aluminum, leather interior, sleek design",
    },
    "airplane_fighter": {
        "visual": "fighter jet, triangular wings, jet engine, camouflage paint",
        "features": "titanium, aluminum, composites, military aviation",
    },
    "airplane_cargo": {
        "visual": "large cargo airplane, wide fuselage, cargo door, powerful engines",
        "features": "steel, aluminum, composites, freight transport",
    },
    "helicopter": {
        "visual": "helicopter with large main rotor, tail rotor, pilot cabin, landing skids",
        "features": "aluminum, composites, steel, glass, aviation",
    },
    "drone": {
        "visual": "large industrial quadcopter, industrial propellers, camera, sensors",
        "features": "carbon fiber, plastic, aluminum, drone technology",
    },
    "seaplane": {
        "visual": "seaplane with floats instead of wheels, water-landing hull",
        "features": "aluminum, composites, stainless steel, marine aviation",
    },
    # 🚗 АВТОМОБИЛИ
    "car_modern": {
        "visual": "modern sedan, streamlined body, LED headlights, alloy wheels",
        "features": "steel, aluminum, plastic, glass, modern automotive design",
    },
    "car_sport": {
        "visual": "low sports car, aggressive design, large wheels, spoiler",
        "features": "carbon fiber, aluminum, leather, performance design",
    },
    "car_suv": {
        "visual": "large SUV, high ground clearance, massive wheels, roof rails",
        "features": "steel, aluminum, plastic, off-road capability",
    },
    "car_electric": {
        "visual": "futuristic electric vehicle, smooth body, hidden grille",
        "features": "aluminum, composites, lithium batteries, EV technology",
    },
    "truck_cargo": {
        "visual": "large cargo truck, cabin, cargo compartment, many wheels",
        "features": "steel, aluminum, rubber, commercial vehicle",
    },
    "truck_pickup": {
        "visual": "pickup truck with open bed, powerful wheels, strong frame",
        "features": "steel, aluminum, plastic, utility vehicle",
    },
    "bus_city": {
        "visual": "long city bus, many windows, passenger doors",
        "features": "steel, aluminum, glass, public transport",
    },
    # 🚜 СПЕЦТЕХНИКА
    "tractor": {
        "visual": "powerful agricultural tractor, large wheels with rough tread, driver cab, hitch",
        "features": "steel, cast iron, rubber, glass, agricultural machinery",
    },
    "excavator": {
        "visual": "construction excavator, long boom, bucket, tracks or wheels",
        "features": "steel, hydraulics, rubber, heavy machinery",
    },
    "bulldozer": {
        "visual": "powerful bulldozer, large front blade, tracks",
        "features": "steel, hydraulics, cast iron, earthmoving equipment",
    },
    "crane_construction": {
        "visual": "tall construction crane, long boom, counterweight, operator cabin",
        "features": "steel, hydraulics, electronics, lifting equipment",
    },
    "concrete_mixer": {
        "visual": "truck with rotating drum, chassis, discharge chute",
        "features": "steel, hydraulics, rubber, concrete equipment",
    },
    "road_roller": {
        "visual": "road roller, large metal cylinder, operator cabin",
        "features": "steel, hydraulics, rubber, road construction equipment",
    },
    "loader": {
        "visual": "front loader, bucket in front, articulated frame",
        "features": "steel, hydraulics, rubber, loading equipment",
    },
    # 🚢 ТРАНСПОРТ
    "ship_cargo": {
        "visual": "large cargo ship, containers on deck, bridge",
        "features": "steel, aluminum, composites, maritime transport",
    },
    "yacht": {
        "visual": "luxury yacht, smooth hull, masts, deck",
        "features": "fiberglass, aluminum, teak, luxury marine",
    },
    "fishing_boat": {
        "visual": "fishing vessel, nets, winches, fish hold",
        "features": "steel, aluminum, nylon, fishing equipment",
    },
    "submarine": {
        "visual": "submarine, cylindrical hull, conning tower, propellers",
        "features": "special steel, titanium, composites, underwater vessel",
    },
    "ferry": {
        "visual": "passenger ferry, multiple decks, gangways, windows",
        "features": "steel, aluminum, glass, passenger transport",
    },
    # 💨 ИНДУСТРИЯ
    "wind_turbine": {
        "visual": "tall wind turbine, three large blades, generator",
        "features": "steel, composites, copper, renewable energy",
    },
    "industrial_crane": {
        "visual": "massive industrial crane, beams, winches, cabin",
        "features": "steel, hydraulics, electronics, heavy industry",
    },
    "industrial_robot": {
        "visual": "robotic arm manipulator, joints, gripper, control panel",
        "features": "aluminum, servomotors, electronics, automation",
    },
    "oil_rig": {
        "visual": "oil rig, drilling column, pumps, platforms",
        "features": "steel, special alloys, offshore structure",
    },
    "solar_farm": {
        "visual": "solar panels on metal supports, inverters, cables",
        "features": "silicon, aluminum, glass, copper, solar power",
    },
}

LOCATION_VISUALS = {
    # 🏗️ ИНДУСТРИАЛЬНЫЕ
    "construction_site": {
        "visual": "construction site, cranes, building materials, machinery",
        "features": "heavy equipment, building materials, outdoor setting",
    },
    "factory": {
        "visual": "modern assembly plant, conveyor line, industrial robots, bright lighting",
        "features": "robotic arms, conveyor belt, parts on shelves, automotive setting",
    },
    "shipyard": {
        "visual": "shipbuilding yard, dry docks, slipways, lifting cranes",
        "features": "ships at various stages, sea water, maritime setting",
    },
    "hangar": {
        "visual": "large industrial hangar, high ceiling, metal trusses, industrial lighting",
        "features": "tools on walls, overhead cranes, equipment, aviation setting",
    },
    "industrial_zone": {
        "visual": "industrial zone, factories, pipes, warehouses",
        "features": "smoking pipes, trucks, cranes, heavy industry",
    },
    # 🌿 ПРИРОДА
    "empty_field": {
        "visual": "open field, green grass, clear sky",
        "features": "trees on horizon, hills, natural landscape",
    },
    "forest_clearing": {
        "visual": "forest clearing, trees surrounding, natural lighting",
        "features": "tall trees, bushes, woodland setting",
    },
    "desert": {
        "visual": "sandy desert, dunes, bright sun",
        "features": "sand dunes, cacti, arid climate",
    },
    "mountain_valley": {
        "visual": "valley between mountains, rocky peaks, river",
        "features": "mountain peaks, clouds, alpine setting",
    },
    "snowy_plain": {
        "visual": "snowy plain, white snow, cold sky",
        "features": "snowdrifts, ice formations, winter landscape",
    },
    # 🌆 УРБАН
    "city_outskirts": {
        "visual": "city outskirts, buildings on horizon, roads",
        "features": "city skyline, highway, urban edge",
    },
    "parking_lot": {
        "visual": "paved parking lot, markings, fences",
        "features": "nearby buildings, lamp posts, asphalt area",
    },
    "abandoned_industrial": {
        "visual": "old abandoned factory, rusty structures, broken windows",
        "features": "destroyed buildings, old metal, decay",
    },
    "building_roof": {
        "visual": "flat building roof, parapet, city view",
        "features": "cityscape, sky, elevated position",
    },
    # 🌊 УНИКАЛЬНЫЕ
    "ocean_coast": {
        "visual": "ocean coast, waves, beach, rocks",
        "features": "ocean horizon, seagulls, coastal setting",
    },
    "floating_platform": {
        "visual": "large floating platform, pontoons, moorings",
        "features": "water, shoreline, marine structure",
    },
    "island": {
        "visual": "island in middle of water, beach, vegetation",
        "features": "ocean, other islands, tropical paradise",
    },
    "quarry": {
        "visual": "open quarry, rock formations, machinery",
        "features": "rock walls, gravel, mining site",
    },
    "port": {
        "visual": "seaport, docks, containers, cranes",
        "features": "cargo ships, port facilities, maritime industry",
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
    """
    Build a prompt for generating a reference image (first frame).

    CRITICAL: Photorealistic style, like a real smartphone photo.
    """
    vehicle_type = scenario.get("vehicle_type", "car_modern")
    location = scenario.get("location", "factory")
    stage_key = scene.get("stage_key", "empty_space")

    style_visual = VEHICLE_TYPE_VISUALS.get(vehicle_type, VEHICLE_TYPE_VISUALS["car_modern"])
    loc_visual = LOCATION_VISUALS.get(location, LOCATION_VISUALS["factory"])

    stage_name_en = scene.get("name_en", "construction stage")
    visual_prompt = scene.get("visual_prompt", "")

    title_line = f"STAGE: {stage_name_en.upper()} — construction stage {index + 1}"

    prompt = f"""Create a photorealistic still image for a house construction timelapse video.

{title_line}

━━━ CRITICAL: BACKGROUND STAYS THE SAME! ━━━
The BACKGROUND (sky, trees, neighboring houses, street, landscape) MUST REMAIN EXACTLY THE SAME across all stages!
- Same sky, same clouds position
- Same trees, same grass, same ground
- Same neighboring buildings, same street
- ONLY THE HOUSE CHANGES — background is FROZEN!
- This is essential for smooth timelapse video.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ CONTENT SAFETY (MANDATORY) ━━━
Generate ONLY original, generic content.
- NO brand names, company names, logos
- NO copyrighted characters
- NO famous buildings or real-world designs
- NO "in the style of" known brands
- All vehicles and tools must be GENERIC (e.g., "excavator", not branded)
- NO visible text or logos in the scene
- Use only neutral descriptions (materials, shapes, function)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STYLE: Photorealistic, shot on smartphone camera, natural lighting, authentic construction site look. NOT 3D render, NOT CGI, NOT animated, NOT cartoon. Must look like REAL smartphone footage.

{title_line}

HOUSE STYLE: {style_visual['visual']}
Features: {style_visual['features']}

LOCATION: {loc_visual['visual']}
Background: {loc_visual['features']}

SCENE DESCRIPTION:
{visual_prompt}

COMPOSITION:
- Wide shot showing the entire building site
- Vertical 9:16 aspect ratio (TikTok/Reels/Shorts format)
- Camera positioned at consistent angle (same perspective as other stages)
- Natural daylight, sun at ~45 degrees
- Realistic shadows and lighting
- Construction materials visible: concrete, bricks, wood, tools, equipment
- Real textures: rough concrete, brick patterns, dirt, grass
- WORKERS visible if appropriate for this stage
- CONSTRUCTION EQUIPMENT visible if appropriate (cranes, trucks, excavators)

CRITICAL REQUIREMENTS:
- This MUST look like a REAL PHOTO from a construction site
- Imperfect lighting, realistic proportions
- Authentic construction site details
- No artificial or rendered look
- Natural colors, not oversaturated
- If previous stage image is provided as reference, match the EXACT camera angle and perspective
- BACKGROUND = FROZEN (only house evolves)"""

    return prompt


def _build_video_prompt(
    scene: dict[str, Any],
    index: int,
    total_stages: int,
    scenario: dict[str, Any],
    language: str = "ru",
) -> str:
    """
    Build a FastGen video prompt for construction timelapse.

    CRITICAL: Show REAL CONSTRUCTION PROCESS with workers and machinery.
    NOT magical transformation - actual building actions.
    """
    vehicle_type = scenario.get("vehicle_type", "car_modern")
    location = scenario.get("location", "factory")

    style_visual = VEHICLE_TYPE_VISUALS.get(vehicle_type, VEHICLE_TYPE_VISUALS["car_modern"])
    loc_visual = LOCATION_VISUALS.get(location, LOCATION_VISUALS["factory"])

    start_state = scene.get("start_state_en", "previous stage")
    end_state = scene.get("end_state_en", "next stage")
    action = scene.get("action_en", "construction work")
    stage_name_en = scene.get("name_en", "construction stage")

    # Stage-specific workers and machinery (always English)
    workers = scene.get("workers_en")
    machinery = scene.get("machinery_en")
    micro_actions = scene.get("micro_actions_en")
    
    # NEW: Intensity, temporal, peak moment
    build_intensity = scene.get("build_intensity", "medium")
    time_of_day = scene.get("time_of_day", "midday")
    is_peak_moment = scene.get("is_peak_moment", False)

    transformation_title = f"CONSTRUCTION STAGE: {stage_name_en.upper()}"

    # ===== BUILD INTENSITY SECTION =====
    intensity_section = {
        "low": """
ACTIVITY LEVEL: LOW
- Fewer workers visible, slower pace
- Minimal simultaneous activities
- Calm, early-stage atmosphere""",
        "medium": """
ACTIVITY LEVEL: MEDIUM
- Several workers actively working
- Multiple simultaneous activities
- Steady construction pace""",
        "high": """
ACTIVITY LEVEL: HIGH (PEAK ACTIVITY)
- MANY workers moving simultaneously
- Intense, fast-paced construction activity
- Multiple machines and workers in sync
- Visually dynamic and impressive scene""",
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
━━━ ⭐ PEAK VISUAL MOMENT ⭐ ━━━
This stage contains the MOST DRAMATIC construction moment!
- Maximum visual impact
- Dramatic crane operations or structural changes
- This is the "WOW" moment of the entire timelapse
- Make it visually STUNNING and memorable
━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

    # Build workers section
    workers_section = ""
    if workers:
        workers_section = f"""
WORKERS ACTIVELY WORKING:
{workers}
- Each worker performs realistic tasks: digging, assembling, lifting, installing
- Motion-blurred movement (timelapse style)
- Workers interact naturally with materials and equipment"""
    else:
        workers_section = """
WORKERS ACTIVELY WORKING:
- Workers moving, walking, carrying materials
- Using tools: hammers, drills, saws, trowels
- Lifting, placing, assembling parts
- Motion-blurred movement (timelapse style)"""

    # Build machinery section
    machinery_section = ""
    if machinery:
        machinery_section = f"""
MACHINERY IN MOTION (ACTIVELY USED):
{machinery}
- All machinery is MOVING and ACTIVELY WORKING
- Equipment operates naturally, NOT standing still"""
    else:
        machinery_section = """
MACHINERY IN MOTION (ACTIVELY USED):
- Trucks arriving and delivering materials
- Cranes operating and lifting loads
- Equipment driving in and out of frame"""

    # Build micro-actions section
    micro_actions_section = ""
    if micro_actions and len(micro_actions) > 0:
        actions_text = "\n".join([f"- {a}" for a in micro_actions[:5]])  # Max 5 actions
        micro_actions_section = f"""
SPECIFIC MICRO-ACTIONS VISIBLE:
{actions_text}
- These actions happen in sequence, showing real work being done"""

    prompt = f"""A highly satisfying construction timelapse showing WORK IN PROGRESS between two stages.

{transformation_title}

HOUSE STYLE: {style_visual['visual']}
LOCATION: {loc_visual['visual']}
{peak_section}
━━━ CRITICAL: SHOW THE WORK, NOT JUST THE RESULT ━━━
{workers_section}
{machinery_section}
{intensity_section}

THE BUILDING EVOLVES THROUGH REAL CONSTRUCTION ACTIONS:
- Materials assemble step by step
- Structure grows piece by piece
- NOT instant transformation, NOT magical appearance
- Logical and physically believable progress
{micro_actions_section}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TRANSITION:
FROM: {start_state}
TO: {end_state}

MAIN ACTIVITY: {action}

━━━ CAMERA RULES (MANDATORY) ━━━
- FIXED CAMERA position (tripod-mounted look)
- SAME LOCATION throughout the video
- SAME PERSPECTIVE, same angle
- Only the construction progresses
- SUBTLE natural micro-motion: tiny, almost imperceptible camera vibration
- This micro-motion makes footage feel REAL, not CGI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ MOTION RULES (MANDATORY) ━━━
- FORWARD MOTION ONLY, no reversing
- Continuous progress, no sudden jumps
- Smooth timelapse speed (1 day = 6 seconds)
- Clean satisfying motion
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ CHAOS & IMPERFECTIONS (REALISM) ━━━
- Scattered materials on ground: piles of bricks, lumber, tools
- Uneven surfaces, dirt patches, construction mess
- Workers' footprints in dirt
- Temporary structures, tarps, protective coverings
- Real construction site feels lived-in and working
- NOT a perfect clean CGI scene
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ SMALL DETAILS (SECRET TO REALISM) ━━━
- Dust rising from activity
- Shadows shifting as time passes
- Machinery operating in background
- Workers' shadows moving
- Small debris and movement
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{lighting_section}

FRAMING: Vertical 9:16. Wide shot of construction site.

AUDIO: Construction site ambience — machinery sounds, tools, footsteps, activity. NO MUSIC. NO VOICE.

STYLE: Photorealistic, cinematic, ultra detailed, smooth motion.

━━━ KEYFRAME RULES ━━━
The transition must strictly follow the change from the start frame to the end frame.
No sudden jumps or unrelated changes.
━━━━━━━━━━━━━━━━━━━━

━━━ CONTENT SAFETY ━━━
NO dangerous situations
NO accidents or injuries
Safe, satisfying construction progress only
━━━━━━━━━━━━"""

    return prompt


def _build_keyframe_video_prompt(
    scene: dict[str, Any],
    scenario: dict[str, Any],
    language: str = "ru",
) -> str:
    """
    Build a SHORT video prompt for FastGen keyframe video generation.
    Based on video skills best practices for image-to-video generation.
    
    VIDEO PROMPT FORMULA:
    [Shot Type] + [Subject Action] + [Camera Motion] + [Environment] + [Temporal] + [Technical]
    
    For construction timelapse:
    - Shot: wide_shot (full construction site visible)
    - Camera: static/locked-off (CRITICAL for timelapse consistency)
    - Temporal: time_lapse (compressed time)
    - Environment: outdoor construction site
    """
    vehicle_type = scenario.get("vehicle_type", "car_modern")
    location = scenario.get("location", "factory")

    style_visual = VEHICLE_TYPE_VISUALS.get(vehicle_type, VEHICLE_TYPE_VISUALS["car_modern"])
    loc_visual = LOCATION_VISUALS.get(location, LOCATION_VISUALS["factory"])

    start_state = scene.get("start_state_en", "previous stage")
    end_state = scene.get("end_state_en", "next stage")
    action = scene.get("action_en", "construction work")
    stage_name_en = scene.get("name_en", "construction stage")

    # Stage-specific workers and machinery (always English)
    workers = scene.get("workers_en")
    machinery = scene.get("machinery_en")
    
    # Truncate long workers/machinery text
    workers_short = (workers[:80] + "...") if workers and len(workers) > 80 else (workers or "workers active")
    machinery_short = (machinery[:80] + "...") if machinery and len(machinery) > 80 else (machinery or "equipment operating")
    
    # PROFESSIONAL VIDEO PROMPT (based on video skills)
    # Formula: Shot + Action + Camera + Temporal + Technical
    # Optimized for FastGen (~700 chars)
    prompt = f"""Wide shot (WS), construction timelapse: {stage_name_en}.
{style_visual['visual']}, {loc_visual['visual']}.

SUBJECT: {action}. Workers: {workers_short}. Equipment: {machinery_short}.

CAMERA: Locked-off tripod, static frame. CRITICAL: camera must not move.
TEMPORAL: Time-lapse, forward motion ONLY, step-by-step progress.

TRANSITION: "{start_state}" → "{end_state}".
MUST strictly follow start frame to end frame. No sudden jumps.

BACKGROUND: Sky, trees, street stay SAME. Only house evolves.

SAFETY: Generic content ONLY. NO brands, logos, copyrighted material. Generic equipment.

TECHNICAL: Vertical 9:16, 1080x1920, cinematic, photorealistic."""

    return prompt


def _build_final_drone_video_prompt(
    scenario: dict[str, Any],
    language: str = "ru",
) -> str:
    """
    Build a video prompt for the FINAL SHOWCASE shot.
    
    PURPOSE: Emotional payoff, show full result clearly, increase retention.
    
    KEY PRINCIPLE: NO MORE BUILDING — ONLY PRESENTATION
    
    DRONE SHOT STYLE (randomly selected):
    - Slow pull-back (отдаление)
    - Orbit (облет вокруг транспорта)
    - Rise-up (подъём вверх)
    - Diagonal fly-by (плавный пролёт сбоку)
    """
    vehicle_type = scenario.get("vehicle_type", "car_modern")
    location = scenario.get("location", "factory")

    style_visual = VEHICLE_TYPE_VISUALS.get(vehicle_type, VEHICLE_TYPE_VISUALS["car_modern"])
    loc_visual = LOCATION_VISUALS.get(location, LOCATION_VISUALS["factory"])

    # Random movement selection for variety
    movements = [
        "slow pull-back: camera starts close to vehicle, gently moves backward and upward, revealing the full vehicle",
        "smooth orbit: camera circles around the vehicle at medium height, showing all angles",
        "rise-up reveal: camera starts low near ground, slowly rises upward while pulling back",
        "diagonal fly-by: camera passes alongside the vehicle diagonally, showing front and side views",
    ]
    selected_movement = random.choice(movements)
    
    # Time of day for cinematic lighting
    times_of_day = [
        "golden hour sunset, warm orange glow, long dramatic shadows, beautiful reflections on paint",
        "golden hour sunrise, soft pink-orange light, peaceful morning atmosphere",
        "soft overcast daylight, even illumination, professional automotive photography look",
    ]
    selected_time = random.choice(times_of_day)

    # FINAL SHOWCASE PROMPT - premium cinematic presentation
    prompt = f"""A cinematic drone showcase of the COMPLETED vehicle. This is the FINAL RESULT — NO assembly, NO workers, NO machinery.

SUBJECT: {style_visual['visual']}
LOCATION: {loc_visual['visual']}

━━━ CRITICAL: THIS IS A SHOWCASE, NOT ASSEMBLY ━━━
The vehicle is FULLY BUILT and must remain UNCHANGED throughout.
NO assembly activities.
NO workers.
NO machinery.
NO transformation.
ONLY the finished, beautiful result.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CAMERA MOVEMENT: {selected_movement}
- Smooth, continuous drone motion
- No sudden movements, no cuts
- Natural camera drift
- Subtle parallax effect between foreground and background

FRAMING:
- Vehicle is always the main focus
- Environment fully visible (surroundings, floor, background)
- Cinematic wide shot composition
- Rule of thirds for premium look

LIGHTING: {selected_time}
- Realistic shadows consistent with scene
- Beautiful reflections on vehicle surface
- Professional automotive photography quality

ENVIRONMENT MOTION:
- Slight ambient movement
- Natural environmental life
- Professional showcase atmosphere

STYLE:
- Ultra realistic
- Cinematic
- Calm and satisfying
- Premium automotive showcase quality
- Emotional payoff for viewer

TECHNICAL: Vertical 9:16, 1080x1920, cinematic drone footage, smooth motion.

SAFETY: Generic content ONLY. NO brands, logos, copyrighted material.

GOAL: Showcase the final result in a premium, beautiful, cinematic way as if filmed by a professional drone operator."""

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
        logger.error(f"[Mode9] Image generation failed for stage {index}: {e}")
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
    clip_retries = 2
    for retry in range(clip_retries + 1):
        try:
            result = await generate_single_video_multi_ref(
                index=index,
                prompt=prompt,
                output_dir=output_dir,
                reference_image_paths=reference_image_paths,
            )

            if result and Path(result).exists():
                logger.success(f"[Mode9] Stage {index + 1} video saved: {Path(result).name}")
                return result
            else:
                if retry < clip_retries:
                    logger.warning(f"[Mode9] Stage {index + 1} video generation failed, retry {retry + 2}/{clip_retries + 1} ...")

        except Exception as e:
            logger.error(f"[Mode9] Stage {index + 1} video generation failed on attempt {retry + 1}: {e}")
            if retry < clip_retries:
                logger.warning(f"[Mode9] Retrying video {index + 1} ...")

    logger.error(f"[Mode9] Stage {index + 1} video generation failed after all attempts.")
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
    clip_retries = 2
    for retry in range(clip_retries + 1):
        try:
            result = await generate_video_from_keyframes(
                prompt=prompt,
                output_dir=output_dir,
                start_frame_path=start_frame,
                end_frame_path=end_frame,
                index=index,
            )

            if result and Path(result).exists():
                logger.success(f"[Mode9] Keyframe video {index + 1} saved: {Path(result).name}")
                return result
            else:
                if retry < clip_retries:
                    logger.warning(f"[Mode9] Keyframe video {index + 1} failed, retry {retry + 2}/{clip_retries + 1} ...")

        except Exception as e:
            logger.error(f"[Mode9] Keyframe video {index + 1} generation failed on attempt {retry + 1}: {e}")
            if retry < clip_retries:
                logger.warning(f"[Mode9] Retrying video {index + 1} ...")

    logger.error(f"[Mode9] Keyframe video {index + 1} generation failed after all attempts.")
    return None


# ═══════════════════════════════════════════════════════════════════════════
# MAIN GENERATION FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

async def generate_vehicle_videos(
    scenario: dict[str, Any],
    output_dir: Path,
    session_id: str,
    language: str = "ru",
) -> tuple[list[Path | None], dict[str, Any]]:
    """
    Generate vehicle assembly timelapse video clips via FastGen.

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
        raise ValueError("[Mode9] No scenes to generate")

    fastgen_key = getattr(settings, "fastgen_api_key", "") or ""
    if not fastgen_key:
        raise RuntimeError("FASTGEN_API_KEY not set — required for Mode 9")

    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "reference_images"
    images_dir.mkdir(parents=True, exist_ok=True)

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 1: SEQUENTIAL image generation with reference chaining
    # ═══════════════════════════════════════════════════════════════════════

    logger.info(f"[Mode9] STEP 1: Generating {len(scenes)} reference images SEQUENTIALLY (chaining)...")

    ref_image_paths: list[Path | None] = []
    previous_image: Path | None = None
    image_retries = 2  # Same as Mode 4

    for i, scene in enumerate(scenes):
        # Build image prompt
        image_prompt = _build_image_prompt(scene, i, scenario, language)

        # Reference = previous image (for continuity)
        refs = [previous_image] if previous_image else []

        # Generate ONE image (sequential, not parallel) WITH RETRY
        logger.info(
            f"[Mode9] Generating image {i + 1}/{len(scenes)}: {scene.get('stage_key', 'stage')} "
            f"(with {len(refs)} reference(s))"
        )

        image_path = None
        for retry in range(image_retries + 1):
            image_path = await _generate_single_image_with_ref(
                prompt=image_prompt,
                output_dir=images_dir,
                index=i,
                reference_image_paths=refs,
            )
            if image_path and Path(image_path).exists():
                break
            if retry < image_retries:
                logger.warning(f"[Mode9] Image {i + 1} failed, retry {retry + 2}/{image_retries + 1} ...")

        if image_path:
            ref_image_paths.append(image_path)
            previous_image = image_path  # Chain to next stage
            logger.success(f"[Mode9] Stage {i + 1} reference image: {image_path.name}")
        else:
            ref_image_paths.append(None)
            logger.error(f"[Mode9] Stage {i + 1}: Failed to generate reference image after {image_retries + 1} attempts")
            # Don't break — continue with None, but warn
            if i < len(scenes) - 1:
                logger.warning(f"[Mode9] Stage {i + 2} will have no reference image!")

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 2: KEYFRAME video generation (transition between stages)
    # ═══════════════════════════════════════════════════════════════════════
    
    # CORRECTED: Generate ALL N-1 keyframe videos (all assembly stages)
    # PLUS 1 bonus drone shot at the end
    num_keyframe_videos = len(scenes) - 1  # ALL transitions (N-1)
    num_total_videos = len(scenes)  # N-1 keyframe + 1 bonus drone
        
    if num_keyframe_videos < 1:
        raise ValueError("[Mode9] Need at least 2 stages for video generation")
        
    logger.info(f"[Mode9] STEP 2: Generating {num_keyframe_videos} KEYFRAME videos + 1 BONUS DRONE SHOT...")
    
    video_tasks = []
        
    # 2a: Generate ALL keyframe videos (ALL transitions between stages)
    for i in range(num_keyframe_videos):
        # Get start and end frames for this transition
        start_frame = ref_image_paths[i] if i < len(ref_image_paths) else None
        end_frame = ref_image_paths[i + 1] if i + 1 < len(ref_image_paths) else None
    
        # Both frames must exist for keyframe generation
        if not start_frame or not end_frame:
            logger.warning(f"[Mode9] Skipping video {i}: missing frames")
            video_tasks.append(asyncio.create_task(asyncio.sleep(0)))  # Placeholder
            continue
            
        if not Path(start_frame).exists() or not Path(end_frame).exists():
            logger.warning(f"[Mode9] Skipping video {i}: frame files not found")
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
    
    # 2b: Generate BONUS DRONE SHOT video (uses only last frame as reference)
    # This is ADDITIONAL final showcase, NOT a replacement for assembly video
    final_frame_index = len(scenes) - 1
    final_frame = ref_image_paths[final_frame_index] if final_frame_index < len(ref_image_paths) else None
    
    if final_frame and Path(final_frame).exists():
        logger.info(f"[Mode9] Generating BONUS DRONE SHOT video (index {num_keyframe_videos})...")
        
        drone_prompt = _build_final_drone_video_prompt(scenario, language)
        
        # Use single reference image (final frame) for drone shot
        drone_task = _generate_single_video(
            index=num_keyframe_videos,
            prompt=drone_prompt,
            reference_image_paths=[Path(final_frame)],
            output_dir=output_dir,
        )
        video_tasks.append(drone_task)
    else:
        logger.warning(f"[Mode9] Skipping BONUS DRONE SHOT: final frame not available")
        video_tasks.append(asyncio.create_task(asyncio.sleep(0)))  # Placeholder

    # Generate ALL videos in parallel
    video_paths = await asyncio.gather(*video_tasks, return_exceptions=True)

    # Handle results
    valid_paths: list[Path | None] = []
    for i, result in enumerate(video_paths):
        if isinstance(result, Exception):
            logger.error(f"[Mode9] Keyframe video {i + 1} failed: {result}")
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
        f"[Mode9] Generated {ref_count}/{len(scenes)} reference images "
        f"and {valid_count}/{num_videos} keyframe videos"
    )

    return valid_paths, enriched_scenario
