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
    num_floors = scenario.get("num_floors", 2)  # NEW: Get floors from scenario
    floor_word = "floors" if num_floors > 1 else "floor"
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

━━━ CRITICAL: STATIC CAMERA - NO MOVEMENT! ━━━
⚠️ THIS IS A STATIC IMAGE — CAMERA IS COMPLETELY LOCKED!
- Camera is completely motionless — tripod-mounted, locked-off position
- Camera angle CANNOT change — think: camera is bolted to concrete
- If camera moves even 1 degree, the entire timelapse will be ruined
- This is THE MOST IMPORTANT rule for construction timelapse
- Absolutely static camera, like the attached reference photo in FastGen
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ CRITICAL: BACKGROUND STAYS THE SAME! ━━━
The BACKGROUND (sky, trees, neighboring houses, street, landscape) MUST REMAIN EXACTLY THE SAME across all stages!
- Same sky, same clouds position
- Same trees, same grass, same ground
- Same neighboring buildings, same street
- ONLY THE HOUSE CHANGES — background is FROZEN!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ CAMERA CALIBRATION DATA (ABSOLUTE PRECISION REQUIRED) ━━━
CAMERA PARAMETERS - MUST BE IDENTICAL FOR EVERY SINGLE IMAGE:
- Position: X=0.0m (center), Y=8.0m (height - elevated for full house view)
- Angle: Horizontal=0°, Vertical=-10° (slight downward angle from height)
- Focal Length: 35mm full-frame equivalent (wide enough for entire house)
- Horizon Line: 60% from bottom edge (elevated viewpoint)
- Cloud Motion: ALWAYS moving RIGHT (never static, never left)
- These parameters are LOCKED - ZERO tolerance for variation
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

**HOUSE SPECIFICATIONS:**
• Number of floors: {num_floors} {floor_word}
• House design: MUST remain consistent across all stages

━━━ SCENE SPECIFICATIONS ━━━
{visual_prompt}

COMPOSITION:
- ⚠️ CRITICAL: Use EXACT camera calibration parameters from above - NO variations allowed
- Wide shot showing the ENTIRE house and building site (house occupies 40-50% of frame)
- Vertical 9:16 aspect ratio (TikTok/Reels/Shorts format)
- ⚠️ Camera angle is LOCKED - same perspective for ALL stages (see calibration data)
- Natural daylight, sun position consistent (sun at ~45° elevation from horizon)
- Realistic shadows and lighting (shadows must match across all stages)
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

━━━ CRITICAL: STATIC CAMERA - NO MOVEMENT! ━━━
⚠️ THIS IS A STATIC IMAGE — CAMERA IS COMPLETELY LOCKED!
- Camera is completely motionless — tripod-mounted, locked-off position
- Camera angle CANNOT change — think: camera is bolted to concrete
- If camera moves even 1 degree, the entire timelapse will be ruined
- This is THE MOST IMPORTANT rule for construction timelapse
- Absolutely static camera, like the attached reference photo in FastGen
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ CRITICAL: BACKGROUND STAYS THE SAME! ━━━
The BACKGROUND (sky, trees, neighboring houses, street, landscape) MUST REMAIN EXACTLY THE SAME across all stages!
- Same sky, same clouds position
- Same trees, same grass, same ground
- Same neighboring buildings, same street
- ONLY THE HOUSE CHANGES — background is FROZEN!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ CAMERA CALIBRATION DATA (ABSOLUTE PRECISION REQUIRED) ━━━
CAMERA PARAMETERS - MUST BE IDENTICAL FOR EVERY SINGLE IMAGE:
- Position: X=0.0m (center), Y=8.0m (height - elevated for full house view)
- Angle: Horizontal=0°, Vertical=-10° (slight downward angle from height)
- Focal Length: 35mm full-frame equivalent (wide enough for entire house)
- Horizon Line: 60% from bottom edge (elevated viewpoint)
- Cloud Motion: ALWAYS moving RIGHT (never static, never left)
- These parameters are LOCKED - ZERO tolerance for variation
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

**HOUSE SPECIFICATIONS:**
• Number of floors: {num_floors} {floor_word}
• House design: MUST remain consistent across all stages

HOUSE STYLE: {style_visual['visual']}
Features: {style_visual['features']}

LOCATION: {loc_visual['visual']}
Background: {loc_visual['features']}

SCENE DESCRIPTION:
{visual_prompt}

COMPOSITION:
- ⚠️ CRITICAL: Use EXACT camera calibration parameters from above - NO variations allowed
- Wide shot showing the ENTIRE house and building site (house occupies 40-50% of frame)
- Vertical 9:16 aspect ratio (TikTok/Reels/Shorts format)
- ⚠️ Camera angle is LOCKED - same perspective for ALL stages (see calibration data)
- Natural daylight, sun position consistent (sun at ~45° elevation from horizon)
- Realistic shadows and lighting (shadows must match across all stages)
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
    num_floors = scenario.get("num_floors", 2)  # NEW: Get floors from scenario
    floor_word = "floors" if num_floors > 1 else "floor"

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

    prompt = f"""⚠️ CRITICAL: HOUSE STRUCTURE MUST REMAIN COMPLETELY UNCHANGED THROUGHOUT THIS VIDEO!
⚠️ The house itself does NOT grow, change, or add new fragments during this video.
⚠️ ONLY workers and machinery move around the FIXED house structure.
⚠️ Think: house is a STATIC PHOTO - workers are DYNAMIC overlay.

A highly satisfying construction timelapse showing WORK IN PROGRESS between two stages.

{transformation_title}

HOUSE STYLE: {style_visual['visual']}
LOCATION: {loc_visual['visual']}
NUM FLOORS: {num_floors} {floor_word} house under construction

**BUILDING STABILITY RULE (MOST IMPORTANT):**
• House structure: 100% IDENTICAL from start to end of video
• No new walls, roofs, or fragments appear - house is already built
• ONLY workers/machinery moving AROUND the fixed house
• Camera captures workers working, NOT house changing
{peak_section}

━━━ CONSTRUCTION PROGRESS CONTEXT ━━━
This video shows the transition from "{start_state}" to "{end_state}".
MAIN ACTIVITY: {action}

WORK ALREADY COMPLETED (visible in START frame):
- Foundation: {'DONE - visible at ground level' if scene.get('has_foundation') else 'NOT YET BUILT'}
- Walls: {'DONE - walls erected' if scene.get('has_walls') else 'NOT YET BUILT'}
- Roof: {'DONE - roof installed' if scene.get('has_roof') else 'NOT YET BUILT'}
- Windows/Doors: {'DONE - installed' if scene.get('has_windows') else 'NOT YET INSTALLED'}
- Facade Finish: {'DONE - completed' if scene.get('has_facade') else 'NOT YET FINISHED'}

WORK TO BE DONE IN THIS VIDEO (will appear in END frame):
- Focus on completing: {action}
- This stage adds: {stage_name_en} progress
- After this video: structure moves closer to completion
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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

FRAMING: Vertical 9:16. ⚠️ Wide shot composition is FIXED - same framing for ALL stages.

━━━ CAMERA CALIBRATION (LOCKED) ━━━
⚠️ CRITICAL: Camera parameters MUST match image calibration exactly:
- Position: X=0.0m, Y=1.5m, Z=5.0m
- Angle: 0° horizontal, 0° vertical
- Focal Length: 50mm full-frame
- Horizon Line: 40% from bottom
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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
    
    CRITICAL: ALL keyframe videos use STATIC CAMERA - NO movement except final drone showcase.
    """
    house_style = scenario.get("house_style", "modern")
    location = scenario.get("location", "suburbs")
    num_floors = scenario.get("num_floors", 2)  # NEW: Get floors from scenario
    floor_word = "floors" if num_floors > 1 else "floor"

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
    # CRITICAL: House stays IDENTICAL - only workers move
    # Formula: Shot + Action + Camera + Temporal + Technical
    # Optimized for FastGen (~700 chars)
    prompt = f"""⚠️ CRITICAL: HOUSE STRUCTURE MUST REMAIN COMPLETELY UNCHANGED!
⚠️ The house does NOT grow/change/add fragments - it's already complete.
⚠️ ONLY workers/machinery move around the FIXED structure.

⚠️ FIXED CAMERA: Wide shot composition is LOCKED - same framing for ALL stages.
Construction timelapse: {stage_name_en}.
{style_visual['visual']}, {loc_visual['visual']}.
NUM FLOORS: {num_floors} {floor_word} house under construction

**BUILDING STABILITY RULE:**
• House: 100% IDENTICAL start to end
• No construction on house - already built
• ONLY workers moving AROUND fixed house

SUBJECT: {action}. Workers: {workers_short}. Equipment: {machinery_short}.

━━━ CAMERA CALIBRATION (LOCKED PARAMETERS) ━━━
- Position: X=0.0m, Y=8.0m (height - elevated), Z=25.0m (distance - far) — NEVER changes
- Angle: 0° horizontal, -10° vertical (slight downward angle) — ALWAYS identical
- Focal Length: 35mm full-frame — NO zooming allowed
- Horizon Line: 60% from bottom — MUST stay fixed
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CAMERA: Locked-off tripod, static frame. CRITICAL: camera must not move - SAME position across ALL stages.
CLOUDS: ALWAYS moving RIGHT — never static, never left, always visible motion
TEMPORAL: Time-lapse, forward motion ONLY, step-by-step progress.

TRANSITION: "{start_state}" → "{end_state}".
MUST strictly follow start frame to end frame. No sudden jumps.

BACKGROUND: Sky, trees, street stay SAME. Only house evolves.

SAFETY: Generic content ONLY. NO brands, logos, copyrighted material. Generic equipment.

TECHNICAL: Vertical 9:16, 1080x1920, cinematic, photorealistic.

STYLE: Photorealistic, shot on smartphone camera, natural lighting. NOT 3D render, NOT CGI."""

    return prompt


def _build_drone_showcase_image_prompt(
    scenario: dict[str, Any],
    language: str = "ru",
) -> str:
    """
    Build a prompt for generating DRONE SHOWCASE IMAGE (end frame for drone video).
    
    PURPOSE: Create a smooth aerial pullback showing the house from a slightly elevated angle.
    
    KEY REQUIREMENTS:
    - SAME house (identical design, materials, colors) — EXACT COPY from reference
    - FARTHER AWAY — drone shows the house from a bit more distance (but still close)
    - MODERATE elevation — just enough to see the house better, not bird's eye
    - House fills most of the frame — NOT a tiny building in vast landscape
    """
    house_style = scenario.get("house_style", "modern")
    location = scenario.get("location", "suburbs")
    num_floors = scenario.get("num_floors", 2)  # NEW: Get floors from scenario
    floor_word = "floors" if num_floors > 1 else "floor"

    style_visual = HOUSE_STYLE_VISUALS.get(house_style, HOUSE_STYLE_VISUALS["modern"])
    loc_visual = LOCATION_VISUALS.get(location, LOCATION_VISUALS["suburbs"])

    # Drone showcase image prompt — FARTHER AWAY aerial view with signs of life
    prompt = f"""━━━ ★★★ DRONE SHOWCASE IMAGE — LIVED-IN HOUSE FROM FARTHER AWAY ★★★ ━━━
PURPOSE: Create the FINAL FRAME for a smooth drone pullback video showing a house that people ALREADY LIVE IN, viewed from SLIGHTLY FARTHER AWAY than construction shots.
This image will be the END POINT of a gentle camera movement from ground-level construction view to a slightly elevated and MORE DISTANT perspective with visible signs of habitation.

━━━ CRITICAL: HOUSE MUST BE IDENTICAL TO REFERENCE + SIGNS OF LIFE ━━━
The house must be EXACTLY the same as in the reference image:
- SAME design, architecture, materials, colors — NO CHANGES ALLOWED
- SAME roof shape, window placement, proportions — EXACT COPY
- SAME exterior finish, textures, facade details
- SAME surrounding landscape, trees, driveway — EVERYTHING IDENTICAL
- THE HOUSE ITSELF DOES NOT CHANGE — ONLY THE CAMERA POSITION IS FARTHER AWAY

BUT NOW ADD SIGNS THAT PEOPLE ARE LIVING HERE (MINIMAL - ONLY 2 ELEMENTS):
- Parked car/vehicle in driveway (modern family car, generic brand) — ONLY 1 element
- Warm interior lights ON in windows (visible glow from inside rooms) — ONLY 2nd element
- DO NOT add: furniture, plants, decorations, mailbox, welcome mat, string lights

DO NOT change ANYTHING about the house structure itself — ONLY move camera farther away and add car + lights.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**HOUSE SPECIFICATIONS:**
• Number of floors: {num_floors} floor{'s' if num_floors > 1 else ''}
• House design: MUST remain consistent with construction stages

SUBJECT: {style_visual['visual']} — now fully lived-in and decorated, viewed from FARTHER AWAY
LOCATION CONTEXT: {loc_visual['visual']}

━━━ CAMERA ANGLE: FARTHER ELEVATED DRONE VIEW ━━━
- MODERATE ELEVATION: 10-20 meters above ground (slightly higher than construction shots)
- FARTHER DISTANCE: 25-40 meters from the house (drone moves BACK to show more context)
- HOUSE STILL DOMINATES: House fills 50-65% of the image (still the hero, but with more surroundings)
- SLIGHT DOWNWARD ANGLE: Camera tilted down ~20-30 degrees
- MORE CONTEXT VISIBLE: Show driveway, front yard, nearby trees, immediate neighborhood hints
- DO NOT show: distant landscape, full property boundaries, far-away elements
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ WHAT TO SHOW (HOUSE AS THE HERO WITH LIFE) ━━━
PRIMARY FOCUS: The completed house — LARGE and DETAILED in frame, FULLY LIVED-IN

VISIBLE SIGNS OF HABITATION (ONLY 2 ELEMENTS - CRITICAL FOR CONSISTENCY):
1. VEHICLE: One modern family car parked in driveway (generic sedan or SUV, neutral color)
   - Positioned naturally, not staged
   - Adds realism and scale

2. INTERIOR LIGHTS: Warm yellow/orange glow visible through windows
   - Shows people are inside living their lives
   - Creates cozy, welcoming atmosphere
   - Multiple windows lit (living room, kitchen, bedrooms)

DO NOT ADD (CRITICAL):
- NO outdoor furniture (chairs, tables, cushions)
- NO potted plants or flower pots
- NO solar pathway lights
- NO welcome mat
- NO mailbox
- NO string lights or lanterns
- NO garden decorations
- NO decorative items of any kind

Adding extra elements BREAKS house identity and causes generation failures.

House should be the CLEAR MAIN SUBJECT, occupying majority of the image, but with MORE SURROUNDINGS visible than construction shots.
Show roof details, facade texture, windows clearly, plus additional context like full driveway, front yard landscaping.
Include more surroundings: complete driveway, front yard edges, several trees, street hints.
Background should show MORE context than construction shots — viewer feels "pulled back to see the full property".
The viewer sees the house from FARTHER AWAY while it remains the HERO — large, detailed, impressive, and FULLY LIVED-IN.

ABSOLUTELY AVOID:
- Wide shots where house is small in the center (house must still dominate!)
- Bird's eye view from high altitude
- Showing entire neighborhood or vast landscape
- Any camera position that makes the house look distant or tiny
- Construction equipment, workers, tools (this is AFTER construction)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

LIGHTING: Golden hour (sunset or sunrise) for cinematic quality
- Warm, soft light with gentle shadows
- Interior lights create warm glow in windows (contrast with exterior light)
- Beautiful lighting that reveals house details and depth
- Professional real estate photography aesthetic

STYLE: Ultra photorealistic, cinematic aerial photography
- Shot on professional drone (DJI Mavic 3 or similar)
- High resolution, sharp architectural details
- Rich colors, excellent dynamic range
- Premium quality with intimate, close perspective
- Emotional, aspirational "dream home" atmosphere

TECHNICAL: Vertical 9:16, 1080x1920, ultra detailed, photorealistic.

SAFETY: Generic content ONLY. NO brands, logos, copyrighted material.
- Car must be GENERIC (no visible emblems or brand identifiers)

GOAL: Create an intimate aerial showcase where the house remains the HERO — large, detailed, impressive, and CLEARLY LIVED-IN with ONLY 2 elements: 1) car in driveway, 2) warm interior lights. House must be PIXEL-PERFECT MATCH to reference — same design, same materials, same everything except camera distance."""

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
    num_floors = scenario.get("num_floors", 2)  # NEW: Get floors from scenario
    floor_word = "floors" if num_floors > 1 else "floor"

    style_visual = HOUSE_STYLE_VISUALS.get(house_style, HOUSE_STYLE_VISUALS["modern"])
    loc_visual = LOCATION_VISUALS.get(location, LOCATION_VISUALS["suburbs"])

    # Random movement selection for variety - ALL STATIC SHOTS, NO CAMERA MOTION
    movements = [
        "static elevated aerial shot from 8-15 meters height — camera is COMPLETELY LOCKED-OFF on tripod, NO movement, NO pull-back, NO rising — single fixed frame showcasing the lived-in house",
        "static moderate aerial view from 10-12 meters — camera is FULLY STATIC, zero motion, fixed position — one beautiful photograph of the occupied home",
        "static high-angle shot from 8-15 meters elevation — camera is TRIPOD-MOUNTED and locked, ABSOLUTELY NO movement — single still showcase image",
        "static diagonal aerial perspective from 12-15 meters — camera is COMPLETELY STILL, NO flying, NO motion — one fixed cinematic frame",
    ]
    selected_movement = random.choice(movements)

    # Time of day for cinematic lighting
    times_of_day = [
        "golden hour sunset, warm orange glow, long dramatic shadows",
        "golden hour sunrise, soft pink-orange light, peaceful morning atmosphere",
        "soft overcast daylight, even illumination, professional real estate look",
    ]
    selected_time = random.choice(times_of_day)

    # TWO-FRAME TRANSITION PROMPT — ACTUALLY A SINGLE STATIC SHOT
    # CRITICAL: This is NOT a transformation video — it's ONE STATIC AERIAL PHOTO
    prompt = f"""━━━ ★★★ SINGLE STATIC AERIAL SHOT: LIVED-IN HOUSE SHOWCASE ★★★ ━━━
THIS IS NOT A VIDEO WITH CAMERA MOVEMENT.
This is ONE BEAUTIFUL STATIC PHOTOGRAPH from elevated drone perspective.

━━━ CRITICAL: STATIC CAMERA (MOST IMPORTANT) ━━━
- Camera is COMPLETELY LOCKED-OFF on tripod at 8-15 meters height
- ZERO camera movement — NO pull-back, NO rising, NO orbiting, NO flying
- This is a SINGLE STILL FRAME, not a motion video
- Think: "beautiful drone photograph", not "drone video"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

A cinematic DRONE PHOTOGRAPH of the COMPLETED, LIVED-IN house. This is the FINAL RESULT — NO construction, NO workers, NO machinery.

SUBJECT: {style_visual['visual']} — now fully lived-in with visible signs of habitation
LOCATION: {loc_visual['visual']}

━━━ CRITICAL: THIS IS A SHOWCASE, NOT CONSTRUCTION ━━━
The house is FULLY BUILT and OCCUPIED. Must show signs that people live here:

VISIBLE SIGNS OF HABITATION (ONLY 2 ELEMENTS - CRITICAL FOR CONSISTENCY):
1. VEHICLE: One modern family car parked in driveway (generic sedan/SUV, neutral color)
2. INTERIOR LIGHTS: Warm yellow/orange glow visible through 3-5 windows

**HOUSE SPECIFICATIONS:**
• Number of floors: {num_floors} floor{'s' if num_floors > 1 else ''}
• House design: MUST remain consistent with construction stages — PIXEL-PERFECT MATCH

DO NOT ADD (CRITICAL):
- NO outdoor furniture (chairs, tables, cushions)
- NO potted plants or flower pots
- NO solar pathway lights
- NO welcome mat
- NO mailbox
- NO string lights or lanterns
- NO garden decorations
- NO decorative items of any kind

Adding extra elements BREAKS house identity and causes generation failures.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ STATIC CAMERA SPECIFICATIONS ━━━
{selected_movement}

PIXEL-PERFECT REQUIREMENTS:
- House position in frame: EXACT SAME as reference image (last construction stage)
- House size: IDENTICAL proportions, NO scaling
- Perspective: MATCHING vanishing points from reference
- This is THE SAME house from slightly elevated viewpoint — NOT a different photo
- House fills 70-80% of frame (dominates composition)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FRAMING (FIXED, NO EVOLUTION):
- Single elevated view from 8-15 meters height
- House is CLEAR HERO — large, detailed, impressive
- Immediate context only: driveway edge, closest trees, front yard
- Background minimal: sky and subtle hints of surroundings
- Viewer feels "close to the house", NOT looking from far away

LIGHTING: {selected_time}
- Realistic shadows consistent with scene
- Warm cinematic glow
- Interior lights create warm yellow/orange glow in windows (visible throughout — this is a static shot)
- Professional real estate photography quality
- Lighting emphasizes the "lived-in" cozy atmosphere

ENVIRONMENT (STATIC, NO MOTION):
- Still air or very slight breeze in trees (subtle, almost frozen)
- Minimal grass movement — this is essentially a photograph
- Calm, peaceful atmosphere
- Soft glow from interior lights (steady, not pulsing)

STYLE:
- Ultra realistic
- Cinematic
- Calm and satisfying
- Premium real estate showcase quality
- Emotional payoff for viewer — sense of "home sweet home"
- Aspirational family living atmosphere

TECHNICAL: Vertical 9:16, 1080x1920, cinematic drone PHOTOGRAPH, sharp details.

SAFETY: Generic content ONLY. NO brands, logos, copyrighted material.
- Car must be GENERIC (no visible emblems or brand identifiers)

GOAL: Create ONE stunning, intimate aerial photograph where the house remains the HERO — large, detailed, impressive, and CLEARLY LIVED-IN with ONLY 2 elements: 1) car in driveway, 2) warm interior lights. House must be PIXEL-PERFECT MATCH to last construction frame — same design, same materials, same everything except camera distance."""

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
    
    # Get house info for video prompts
    num_floors = scenario.get("num_floors", 2)  # Default 2 floors

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
    
    # ═══════════════════════════════════════════════════════════════════════
    # SEPARATE PREVIEW RESULT FROM VIDEO RESULTS
    # ═══════════════════════════════════════════════════════════════════════
    preview_path = None
    
    # Check if preview task was added and extract its result
    if generate_preview and len(video_tasks) > 0:
        # Preview task is always the LAST one added (after drone shot)
        # We need to check if the last task actually produced a preview
        preview_result = video_paths[-1] if len(video_paths) > 0 else None
        
        if isinstance(preview_result, Path):
            # Successfully generated preview - remove it from video_paths
            preview_path = preview_result
            video_paths = video_paths[:-1]  # Remove last item (preview)
            logger.success(f"[Mode8] Clickbait preview generated: {preview_path.name}")
            logger.info(f"[Mode8] Preview full path: {preview_path.absolute()}")
            # Verify file exists
            if not preview_path.exists():
                logger.error(f"[Mode8] Preview file does not exist: {preview_path}")
                preview_path = None
        elif isinstance(preview_result, Exception):
            # Preview generation failed - log error but continue
            logger.error(f"[Mode8] Preview generation failed: {preview_result}")
            video_paths = video_paths[:-1] if len(video_paths) > 0 else video_paths
        else:
            # No preview was generated (task returned None or not added)
            logger.debug("[Mode8] No preview result from last task")
            # Still remove last item if it was a preview task that returned None
            video_paths = video_paths[:-1] if len(video_paths) > 0 else video_paths

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
            # Explicitly skip preview paths - they should not be in video_paths anymore
            result_path = Path(result) if not isinstance(result, Path) else result
            if 'preview' in str(result_path).lower():
                logger.warning(f"[Mode8] Skipping preview path in video results: {result_path}")
                continue
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
