"""
Mode 8 Video Generator — House Building Timelapse.

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

STYLE: Photorealistic timelapse with workers and machinery.
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
from modes.clickbait_preview import generate_clickbait_preview
from modes.mode8.contextual_prompt_generator import (
    generate_contextual_prompts,
    GeneratedPrompt,
)


# ═══════════════════════════════════════════════════════════════════════════
# HOUSE STYLE VISUALS
# ═══════════════════════════════════════════════════════════════════════════

HOUSE_STYLE_VISUALS = {
    # 🏙️ СОВРЕМЕННЫЕ
    "modern": {
        "visual": "modern minimalist house, flat roof, large windows, geometric shapes, concrete and glass",
        "features": "clean lines, large glass panels, flat roof, minimalist design",
    },
    "contemporary": {
        "visual": "ultra-modern contemporary house, panoramic windows, mixed materials, asymmetrical shape",
        "features": "steel, glass, concrete, composites, cutting-edge design",
    },
    "minimalist": {
        "visual": "minimalist house, clean lines, monochromatic palette, hidden elements",
        "features": "concrete, glass, aluminum, simplicity",
    },
    "scandinavian": {
        "visual": "scandinavian house, light facades, wooden accents, large windows",
        "features": "wood, stone, glass, nordic design",
    },
    # 🏡 ТРАДИЦИОННЫЕ
    "cottage": {
        "visual": "cozy cottage with pitched roof, stone facade, wooden elements",
        "features": "pitched roof, stone walls, wooden accents, cozy atmosphere",
    },
    "villa": {
        "visual": "luxurious villa, multiple floors, terraces, pool, elegant architecture",
        "features": "multiple floors, elegant columns, large terraces, luxurious finish",
    },
    "farmhouse": {
        "visual": "classic farmhouse, wide porch, white fence, barn nearby",
        "features": "wide front porch, white siding, barn, rural setting",
    },
    "colonial": {
        "visual": "colonial house, symmetrical facade, columns, central door",
        "features": "brick, wood, shingles, traditional colonial style",
    },
    "victorian": {
        "visual": "victorian house, towers, bay windows, decorative elements, vibrant colors",
        "features": "wood, brick, slate, ornate details",
    },
    "mediterranean": {
        "visual": "mediterranean villa, red tile roof, arched windows, stucco",
        "features": "stucco, tile roof, stone, mediterranean style",
    },
    # 🌲 НАТУРАЛЬНЫЕ
    "cabin": {
        "visual": "wooden log cabin in forest, log walls, cozy porch, chimney",
        "features": "log construction, wooden walls, stone chimney, forest setting",
    },
    "log_house": {
        "visual": "large log house, massive logs, traditional architecture",
        "features": "logs, stone, metal, traditional craftsmanship",
    },
    "chalet": {
        "visual": "alpine chalet, sloping roof, wooden balconies, stone foundation",
        "features": "wood, stone, tiles, alpine architecture",
    },
    "adobe": {
        "visual": "adobe house, rounded forms, earth tones, traditional style",
        "features": "adobe, clay, straw, southwestern style",
    },
    # 🏛️ ЭЛИТНЫЕ
    "mansion": {
        "visual": "huge mansion, columns, fountains, landscape design",
        "features": "marble, granite, bronze, glass, luxury estate",
    },
    "estate": {
        "visual": "family estate, multiple buildings, park, pond",
        "features": "brick, stone, metal, heritage property",
    },
}

LOCATION_VISUALS = {
    # 🏙️ ПРИГОРОДНЫЕ
    "suburbs": {
        "visual": "quiet suburban neighborhood, other houses visible, paved street, trees",
        "features": "suburban setting, neighbors, street, manicured lawns",
    },
    "urban_edge": {
        "visual": "city outskirts, modern buildings in distance, highway, infrastructure",
        "features": "city skyline, roads, street lights",
    },
    "planned_community": {
        "visual": "new residential area, similar houses, manicured lawns, playgrounds",
        "features": "similar homes, sidewalks, street lamps",
    },
    # 🌲 ПРИРОДНЫЕ
    "forest": {
        "visual": "dense forest, pine and spruce trees, clearing for house, natural landscape",
        "features": "forest setting, tall trees, natural clearing, wilderness",
    },
    "wooded_area": {
        "visual": "mixed forest, deciduous and coniferous trees, undergrowth",
        "features": "diverse trees, bushes, woodland",
    },
    "seaside": {
        "visual": "coastal area, sandy beach nearby, palm trees, ocean breeze",
        "features": "ocean view, beach nearby, palm trees, coastal atmosphere",
    },
    "lakefront": {
        "visual": "lake shore, calm water, dock, boat",
        "features": "lake, opposite shore, waterfront",
    },
    "riverside": {
        "visual": "river bank, flowing water, reeds, trees along river",
        "features": "river, riverside vegetation, water flow",
    },
    "countryside": {
        "visual": "open field, hills on horizon, pasture, tractor in distance",
        "features": "rural farmland, rolling hills, open fields, peaceful countryside",
    },
    "farmland": {
        "visual": "cultivated fields, crop rows, agricultural machinery",
        "features": "fields, farm buildings, crops",
    },
    "vineyard": {
        "visual": "rows of grapevines, hills, mediterranean climate",
        "features": "vineyards, rural setting, wine country",
    },
    "mountains": {
        "visual": "mountain slope, coniferous forest, snow-capped peaks on horizon, rocks",
        "features": "mountain setting, elevation, scenic views, alpine atmosphere",
    },
    "hillside": {
        "visual": "hill slope, terraced lot, panoramic view",
        "features": "hills, valleys below, elevated position",
    },
    "valley": {
        "visual": "green valley, river flowing, trees, meadows",
        "features": "valley surrounded by mountains, lush greenery",
    },
    # 🏜️ ЭКЗОТИЧЕСКИЕ
    "desert": {
        "visual": "sandy desert, dunes, cacti, bright sun",
        "features": "sand dunes, sparse vegetation, arid climate",
    },
    "oasis": {
        "visual": "desert oasis, palm trees, water source, greenery",
        "features": "desert with green zone, water, palms",
    },
    "tropical": {
        "visual": "tropical forest, exotic plants, humid climate",
        "features": "jungle, palm trees, tropical vegetation",
    },
    "island": {
        "visual": "small island, beach all around, coconut palms",
        "features": "ocean, other islands, island paradise",
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
    
    NOW WITH VARIATIONS: Uses rich visual prompts from scenario that include
    unique architectural details generated by LLM.

    CRITICAL: Photorealistic style, like a real smartphone photo.
    """
    house_style = scenario.get("house_style", "modern")
    location = scenario.get("location", "suburbs")
    stage_key = scene.get("stage_key", "empty_land")

    style_visual = HOUSE_STYLE_VISUALS.get(house_style, HOUSE_STYLE_VISUALS["modern"])
    loc_visual = LOCATION_VISUALS.get(location, LOCATION_VISUALS["suburbs"])

    stage_name_en = scene.get("name_en", "construction stage")
    
    # Use the enriched visual prompt from scenario (now with variation details)
    visual_prompt = scene.get("visual_prompt", "")
    
    # Check if this is a varied prompt (contains architectural details sections)
    has_variation_details = "━━━ ARCHITECTURAL CHARACTER ━━━" in visual_prompt

    title_line = f"STAGE: {stage_name_en.upper()} — construction stage {index + 1}"

    # If we have rich variation details, use a simplified prompt that leverages them
    if has_variation_details:
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
- All vehicles and tools must be GENERIC
- NO visible text or logos in the scene
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STYLE: Photorealistic, shot on smartphone camera, natural lighting, authentic construction site look. NOT 3D render, NOT CGI, NOT animated, NOT cartoon. Must look like REAL smartphone footage.

{title_line}

━━━ SCENE SPECIFICATIONS ━━━
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
- CONSTRUCTION EQUIPMENT visible if appropriate

CRITICAL REQUIREMENTS:
- This MUST look like a REAL PHOTO from a construction site
- Imperfect lighting, realistic proportions
- Authentic construction site details
- No artificial or rendered look
- Natural colors, not oversaturated
- If previous stage image is provided as reference, match the EXACT camera angle and perspective
- BACKGROUND = FROZEN (only house evolves)"""
    else:
        # Fallback to original template-based prompt
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
    house_style = scenario.get("house_style", "modern")
    location = scenario.get("location", "suburbs")

    style_visual = HOUSE_STYLE_VISUALS.get(house_style, HOUSE_STYLE_VISUALS["modern"])
    loc_visual = LOCATION_VISUALS.get(location, LOCATION_VISUALS["suburbs"])

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
    house_style = scenario.get("house_style", "modern")
    location = scenario.get("location", "suburbs")

    style_visual = HOUSE_STYLE_VISUALS.get(house_style, HOUSE_STYLE_VISUALS["modern"])
    loc_visual = LOCATION_VISUALS.get(location, LOCATION_VISUALS["suburbs"])

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


def _build_drone_showcase_image_prompt(
    scenario: dict[str, Any],
    language: str = "ru",
) -> str:
    """
    Build a prompt for generating DRONE SHOWCASE IMAGE (end frame for drone video).
    
    PURPOSE: Create a beautiful aerial view showing house + full property context.
    
    KEY REQUIREMENTS:
    - SAME house (identical design, materials, colors)
    - DIFFERENT camera angle (higher elevation, wider view)
    - Show FULL property: garden, driveway, landscaping, surroundings
    - Cinematic real estate photography quality
    """
    house_style = scenario.get("house_style", "modern")
    location = scenario.get("location", "suburbs")

    style_visual = HOUSE_STYLE_VISUALS.get(house_style, HOUSE_STYLE_VISUALS["modern"])
    loc_visual = LOCATION_VISUALS.get(location, LOCATION_VISUALS["suburbs"])

    # Drone showcase image prompt - aerial view with full property context
    prompt = f"""━━━ ★★★ DRONE SHOWCASE IMAGE ★★★ ━━━
PURPOSE: Create the FINAL FRAME for a cinematic drone showcase video.
This image will be the END POINT of a smooth camera movement from construction view to aerial showcase.

━━━ CRITICAL: HOUSE MUST REMAIN IDENTICAL ━━━
The house must be EXACTLY the same as in the reference image:
- SAME design, architecture, materials, colors
- SAME roof shape, window placement, proportions
- SAME exterior finish and textures
- DO NOT change the house itself — ONLY change the camera viewpoint
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SUBJECT: {style_visual['visual']}
LOCATION CONTEXT: {loc_visual['visual']}

━━━ CAMERA ANGLE: ELEVATED DRONE VIEW ━━━
- HIGH ELEVATION: 30-50 meters above ground (bird's eye perspective)
- WIDE FIELD OF VIEW: Show entire property + surroundings
- ANGLED DOWNWARD: Camera tilted down ~30-45 degrees
- CINEMATIC COMPOSITION: Rule of thirds, balanced framing
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ WHAT TO SHOW (HOUSE + ENVIRONMENT) ━━━
PRIMARY FOCUS: The completed house (same as reference)
ENVIRONMENT TO INCLUDE:
- Full property boundaries and lot shape
- Driveway and walkways leading to house
- Garden, lawn, landscaping around house
- Trees, shrubs, vegetation on the property
- Street or road access
- Neighboring properties in background (if suburbs)
- Natural landscape context (fields, hills, water if applicable)

The goal is to show the house IN ITS FULL CONTEXT, not isolated.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

LIGHTING: Golden hour (sunset or sunrise) for cinematic quality
- Warm, soft light with long shadows
- Beautiful side-lighting that reveals depth and dimension
- Professional real estate photography aesthetic

STYLE: Ultra photorealistic, cinematic aerial photography
- Shot on professional drone (DJI Mavic 3 or similar)
- High resolution, sharp details
- Rich colors, excellent dynamic range
- Premium real estate marketing quality
- Emotional, aspirational atmosphere

TECHNICAL: Vertical 9:16, 1080x1920, ultra detailed, photorealistic.

SAFETY: Generic content ONLY. NO brands, logos, copyrighted material.

GOAL: Create a stunning aerial showcase image that reveals the full beauty of the property and its surroundings."""

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
    - Orbit (облет вокруг дома)
    - Rise-up (подъём вверх)
    - Diagonal fly-by (плавный пролёт сбоку)
    
    TWO-FRAME TRANSITION:
    - START FRAME: Last construction stage image (ground-level view)
    - END FRAME: Drone showcase image (elevated aerial view)
    - VIDEO: Smooth camera movement from start to end frame
    """
    house_style = scenario.get("house_style", "modern")
    location = scenario.get("location", "suburbs")

    style_visual = HOUSE_STYLE_VISUALS.get(house_style, HOUSE_STYLE_VISUALS["modern"])
    loc_visual = LOCATION_VISUALS.get(location, LOCATION_VISUALS["suburbs"])

    # Random movement selection for variety
    movements = [
        "slow pull-back and upward: camera starts at ground-level construction view, gently moves backward and rises to elevated aerial position, revealing the full property",
        "smooth orbit with elevation gain: camera circles around the house while ascending from ground level to bird's eye view, showing all angles",
        "rise-up reveal: camera starts low near ground at construction viewpoint, slowly rises upward to high aerial position while pulling back",
        "diagonal fly-back: camera passes alongside the house diagonally while moving backward and upward from construction view to aerial overview",
    ]
    selected_movement = random.choice(movements)

    # Time of day for cinematic lighting
    times_of_day = [
        "golden hour sunset, warm orange glow, long dramatic shadows",
        "golden hour sunrise, soft pink-orange light, peaceful morning atmosphere",
        "soft overcast daylight, even illumination, professional real estate look",
    ]
    selected_time = random.choice(times_of_day)

    # TWO-FRAME TRANSITION PROMPT
    # CRITICAL: This video transitions FROM construction view TO aerial showcase
    prompt = f"""━━━ ★★★ TRANSITION: CONSTRUCTION → AERIAL SHOWCASE ★★★ ━━━
THIS VIDEO SHOWS A SMOOTH CAMERA MOVEMENT BETWEEN TWO FRAMES:
- START FRAME: Construction site view (ground-level, human perspective)
- END FRAME: Beautiful aerial showcase view (elevated drone perspective)

The video MUST smoothly transition from the start frame to the end frame.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

A cinematic drone showcase of the COMPLETED house. This is the FINAL RESULT — NO construction, NO workers, NO machinery.

SUBJECT: {style_visual['visual']}
LOCATION: {loc_visual['visual']}

━━━ CRITICAL: THIS IS A SHOWCASE, NOT CONSTRUCTION ━━━
The house is FULLY BUILT and must remain UNCHANGED throughout.
NO building activities.
NO workers.
NO machinery.
NO transformation.
ONLY the finished, beautiful result.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ CAMERA MOVEMENT: SMOOTH TRANSITION ━━━
{selected_movement}

KEY REQUIREMENTS:
- Video STARTS from the construction viewpoint (start frame)
- Video ENDS at the aerial showcase viewpoint (end frame)
- Movement must be SMOOTH, GRADUAL, and CINEMATIC
- No sudden jumps or cuts
- Natural, flowing camera motion
- The house remains IDENTICAL throughout — only camera position changes
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FRAMING EVOLUTION:
- START: Ground-level view focused on house
- MIDDLE: Gradual ascent revealing more surroundings
- END: High aerial overview showing full property + context

LIGHTING: {selected_time}
- Realistic shadows consistent with scene
- Warm cinematic glow
- Professional real estate photography quality

ENVIRONMENT MOTION:
- Slight breeze in trees
- Gentle grass movement
- Natural environmental life

STYLE:
- Ultra realistic
- Cinematic
- Calm and satisfying
- Premium real estate showcase quality
- Emotional payoff for viewer

TECHNICAL: Vertical 9:16, 1080x1920, cinematic drone footage, smooth motion.

SAFETY: Generic content ONLY. NO brands, logos, copyrighted material.

GOAL: Create a stunning, smooth transition that reveals the full beauty of the completed property from an aerial perspective."""

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
        logger.error(f"[Mode8] Image generation failed for stage {index}: {e}")
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
                logger.success(f"[Mode8] Stage {index + 1} video saved: {Path(result).name}")
                return result
            else:
                if retry < clip_retries:
                    logger.warning(f"[Mode8] Stage {index + 1} video generation failed, retry {retry + 2}/{clip_retries + 1} ...")

        except Exception as e:
            logger.error(f"[Mode8] Stage {index + 1} video generation failed on attempt {retry + 1}: {e}")
            if retry < clip_retries:
                logger.warning(f"[Mode8] Retrying video {index + 1} ...")

    logger.error(f"[Mode8] Stage {index + 1} video generation failed after all attempts.")
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
                logger.success(f"[Mode8] Keyframe video {index + 1} saved: {Path(result).name}")
                return result
            else:
                if retry < clip_retries:
                    logger.warning(f"[Mode8] Keyframe video {index + 1} failed, retry {retry + 2}/{clip_retries + 1} ...")

        except Exception as e:
            logger.error(f"[Mode8] Keyframe video {index + 1} generation failed on attempt {retry + 1}: {e}")
            if retry < clip_retries:
                logger.warning(f"[Mode8] Retrying video {index + 1} ...")

    logger.error(f"[Mode8] Keyframe video {index + 1} generation failed after all attempts.")
    return None


# ═══════════════════════════════════════════════════════════════════════════
# MAIN GENERATION FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

async def generate_house_videos(
    scenario: dict[str, Any],
    output_dir: Path,
    session_id: str,
    language: str = "ru",
    use_contextual: bool = True,  # NEW: Enable contextual prompt generation
    generate_preview: bool = True,  # NEW: Generate clickbait social media preview
) -> tuple[list[Path | None], dict[str, Any]]:
    """
    Generate house building timelapse video clips via FastGen.

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

    3. BONUS: Clickbait preview generation for social media (optional):
       - Uses last frame as reference
       - Generates eye-catching thumbnail for maximum CTR

    Returns:
        Tuple of (list of video paths, enriched scenario)
    """
    scenes = scenario.get("scenes", [])

    if not scenes:
        raise ValueError("[Mode8] No scenes to generate")

    fastgen_key = getattr(settings, "fastgen_api_key", "") or ""
    if not fastgen_key:
        raise RuntimeError("FASTGEN_API_KEY not set — required for Mode 8")

    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "reference_images"
    images_dir.mkdir(parents=True, exist_ok=True)

    # ═══════════════════════════════════════════════════════════════════════
    # CONTEXTUAL PROMPT GENERATION (NEW: LLM-powered with history awareness)
    # ═══════════════════════════════════════════════════════════════════════

    contextual_data = None
    if use_contextual:
        logger.info("[Mode8] Generating contextual prompts with LLM analysis...")
        try:
            contextual_data = await generate_contextual_prompts(
                scenario=scenario,
                language="en",  # Always English for FastGen
            )
            logger.success(f"[Mode8] Generated {len(contextual_data['image_prompts'])} image prompts and {len(contextual_data['video_prompts'])} video prompts")
        except Exception as e:
            logger.error(f"[Mode8] Contextual prompt generation failed: {e}, falling back to standard prompts")
            contextual_data = None

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 1: SEQUENTIAL image generation with reference chaining
    # ═══════════════════════════════════════════════════════════════════════

    logger.info(f"[Mode8] STEP 1: Generating {len(scenes)} reference images SEQUENTIALLY (chaining)...")

    ref_image_paths: list[Path | None] = []
    previous_image: Path | None = None
    image_retries = 2  # Same as Mode 4

    for i, scene in enumerate(scenes):
        # Use contextual prompt if available, otherwise build from template
        if contextual_data and i < len(contextual_data["image_prompts"]):
            image_prompt = contextual_data["image_prompts"][i]["prompt_text"]
            logger.debug(f"[Mode8] Using contextual prompt for image {i+1}")
        else:
            image_prompt = _build_image_prompt(scene, i, scenario, language)

        # Reference = previous image (for continuity)
        refs = [previous_image] if previous_image else []

        # Generate ONE image (sequential, not parallel) WITH RETRY
        logger.info(
            f"[Mode8] Generating image {i + 1}/{len(scenes)}: {scene.get('stage_key', 'stage')} "
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
                logger.warning(f"[Mode8] Image {i + 1} failed, retry {retry + 2}/{image_retries + 1} ...")

        if image_path:
            ref_image_paths.append(image_path)
            previous_image = image_path  # Chain to next stage
            logger.success(f"[Mode8] Stage {i + 1} reference image: {image_path.name}")
        else:
            ref_image_paths.append(None)
            logger.error(f"[Mode8] Stage {i + 1}: Failed to generate reference image after {image_retries + 1} attempts")
            # Don't break — continue with None, but warn
            if i < len(scenes) - 1:
                logger.warning(f"[Mode8] Stage {i + 2} will have no reference image!")

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 1c: Generate DRONE SHOWCASE IMAGE (end frame for drone video)
    # ═══════════════════════════════════════════════════════════════════════

    drone_showcase_image: Path | None = None
    final_frame = ref_image_paths[-1] if ref_image_paths else None
    
    if final_frame and Path(final_frame).exists():
        logger.info("[Mode8] Generating DRONE SHOWCASE IMAGE (aerial view for drone video end frame)...")
        
        drone_image_prompt = _build_drone_showcase_image_prompt(scenario, language)
        
        # Generate with reference (to preserve house design)
        drone_showcase_image = await _generate_single_image_with_ref(
            prompt=drone_image_prompt,
            output_dir=images_dir,
            index=len(scenes),  # Index after all stages
            reference_image_paths=[Path(final_frame)],  # Use last frame as reference
        )
        
        if drone_showcase_image and Path(drone_showcase_image).exists():
            logger.success(f"[Mode8] Drone showcase image: {drone_showcase_image.name}")
        else:
            logger.warning("[Mode8] Failed to generate drone showcase image, will use fallback")
            drone_showcase_image = None
    else:
        logger.warning("[Mode8] Skipping drone showcase image: final construction frame not available")

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 2: KEYFRAME video generation (transition between stages)
    # ═══════════════════════════════════════════════════════════════════════
    
    # CORRECTED: Generate ALL N-1 keyframe videos (all construction stages)
    # PLUS 1 bonus drone shot at the end
    num_keyframe_videos = len(scenes) - 1  # ALL transitions (N-1)
    num_total_videos = len(scenes)  # N-1 keyframe + 1 bonus drone
        
    if num_keyframe_videos < 1:
        raise ValueError("[Mode8] Need at least 2 stages for video generation")
        
    logger.info(f"[Mode8] STEP 2: Generating {num_keyframe_videos} KEYFRAME videos + 1 BONUS DRONE SHOT...")
    
    video_tasks = []
        
    # 2a: Generate ALL keyframe videos (ALL transitions between stages)
    for i in range(num_keyframe_videos):
        # Get start and end frames for this transition
        start_frame = ref_image_paths[i] if i < len(ref_image_paths) else None
        end_frame = ref_image_paths[i + 1] if i + 1 < len(ref_image_paths) else None
    
        # Both frames must exist for keyframe generation
        if not start_frame or not end_frame:
            logger.warning(f"[Mode8] Skipping video {i}: missing frames")
            video_tasks.append(asyncio.create_task(asyncio.sleep(0)))  # Placeholder
            continue
            
        if not Path(start_frame).exists() or not Path(end_frame).exists():
            logger.warning(f"[Mode8] Skipping video {i}: frame files not found")
            video_tasks.append(asyncio.create_task(asyncio.sleep(0)))  # Placeholder
            continue
    
        # Build SHORT video prompt for FastGen (limited input capacity)
        scene = scenes[i]  # Current stage
        
        # Use contextual video prompt if available
        if contextual_data and i < len(contextual_data["video_prompts"]):
            video_prompt = contextual_data["video_prompts"][i]["prompt_text"]
            logger.debug(f"[Mode8] Using contextual video prompt for transition {i+1}")
        else:
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
    
    # 2b: Generate BONUS DRONE SHOT video (transition from construction view to aerial showcase)
    # This is ADDITIONAL final showcase, NOT a replacement for construction video
    final_frame_index = len(scenes) - 1
    final_frame = ref_image_paths[final_frame_index] if final_frame_index < len(ref_image_paths) else None
    
    if final_frame and Path(final_frame).exists():
        logger.info(f"[Mode8] Generating BONUS DRONE SHOT video (index {num_keyframe_videos})...")
        
        drone_prompt = _build_final_drone_video_prompt(scenario, language)
        
        # Use TWO frames for better quality: construction view → aerial showcase
        if drone_showcase_image and Path(drone_showcase_image).exists():
            # NEW APPROACH: Keyframe video with start + end frames
            drone_task = _generate_keyframe_video(
                index=num_keyframe_videos,
                prompt=drone_prompt,
                start_frame=Path(final_frame),           # Last construction stage
                end_frame=Path(drone_showcase_image),   # Aerial showcase view
                output_dir=output_dir,
            )
            logger.debug(f"[Mode8] Drone video using two-frame transition: {final_frame.name} → {drone_showcase_image.name}")
        else:
            # FALLBACK: Single reference image (old approach, lower quality)
            logger.warning("[Mode8] Drone showcase image not available, using single-frame fallback")
            drone_task = _generate_single_video(
                index=num_keyframe_videos,
                prompt=drone_prompt,
                reference_image_paths=[Path(final_frame)],
                output_dir=output_dir,
            )
        
        video_tasks.append(drone_task)
        
        # [NEW] Generate CLICKBAIT PREVIEW in PARALLEL with drone shot
        # Preview uses the same final frame but doesn't block video generation
        if generate_preview:
            from modes.clickbait_preview import generate_clickbait_preview as gen_preview
            preview_output_dir = output_dir / "previews"
            preview_output_dir.mkdir(parents=True, exist_ok=True)
            
            # Start preview generation in background (non-blocking)
            preview_task = gen_preview(
                final_frame_path=Path(final_frame),
                scenario=scenario,  # Use original scenario, not enriched
                output_dir=preview_output_dir,
                mode="house",
                style_key="dramatic_reveal",
                language="en",
            )
            # Add to tasks list but track separately
            video_tasks.append(preview_task)  # Will be gathered with videos
    else:
        logger.warning(f"[Mode8] Skipping BONUS DRONE SHOT: final frame not available")
        video_tasks.append(asyncio.create_task(asyncio.sleep(0)))  # Placeholder

    # Generate ALL videos in parallel
    video_paths = await asyncio.gather(*video_tasks, return_exceptions=True)
    
    # Separate video results from preview result (last task might be preview)
    preview_path = None
    if generate_preview and len(video_paths) > num_total_videos:
        # Last item is preview result
        preview_result = video_paths.pop()  # Remove and get preview
        if isinstance(preview_result, Path):
            preview_path = preview_result
            logger.success(f"[Mode8] Clickbait preview generated: {preview_path.name}")
        elif isinstance(preview_result, Exception):
            logger.error(f"[Mode8] Preview generation failed: {preview_result}")
        else:
            logger.warning("[Mode8] Preview generation returned None")

    # Handle results
    valid_paths: list[Path | None] = []
    for i, result in enumerate(video_paths):
        if isinstance(result, Exception):
            logger.error(f"[Mode8] Keyframe video {i + 1} failed: {result}")
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
        f"[Mode8] Generated {ref_count}/{len(scenes)} reference images "
        f"and {valid_count}/{num_total_videos} videos ({num_keyframe_videos} keyframe + 1 drone)"
    )
    
    # Add preview path to enriched scenario if generated
    if preview_path:
        enriched_scenario["preview_path"] = str(preview_path)
    
    return valid_paths, enriched_scenario
