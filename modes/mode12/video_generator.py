"""
Mode 12 Video Generator — таймлапс уборки и реставрации комнаты (keyframe-цепочка).

Спека: 16:9, статика 24–35 мм, уровень глаз ~1,5 м; фото 8K (или макс.); видео 4K, 8 с на переход;
бригада в белых СИЗ на этапах 1–4; финал без рабочих в комбинезонах.

Stills run sequentially (each references the previous frame for layout lock). Keyframe clips use the
same pattern as mode8/mode9: asyncio.create_task per clip + asyncio.gather (each clip → own FastGen
browser in a thread). After all stage stills: generate showcase END still (closer frame), then one parallel wave like mode8/mode9:
all transition keyframe videos + showcase video each in its own browser (asyncio.gather + create_task).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from loguru import logger

from agents.content_generator.fastgen_scraper import (
    generate_images_with_references_fastgen,
    generate_single_video_fastgen,
    generate_video_from_keyframes,
)
from config import settings
from modes.mode12.scenario_writer import STAGE_ORDER

ROOM_TYPE_VISUALS = {
    "studio": {
        "visual": "studio apartment layout with sleeping zone and small kitchenette, one large window",
        "features": "compact living, open plan, urban interior",
    },
    "bedroom": {
        "visual": "bedroom with bed, wardrobe, side tables, window with curtains",
        "features": "private rest space, soft furnishings",
    },
    "living": {
        "visual": "living room with sofa, coffee table, shelves or TV wall",
        "features": "main lounge area, decor layers",
    },
    "kitchen": {
        "visual": "kitchen with cabinets, counter, stove area, small dining nook",
        "features": "functional cooking space",
    },
    "kids": {
        "visual": "children's room with bed, desk, toy corners, cheerful accents",
        "features": "playful colorful interior",
    },
    "loft": {
        "visual": "loft interior with brick or concrete wall, tall ceiling, industrial hints",
        "features": "open loft aesthetic",
    },
}

ROOM_LIGHTING_VISUALS = {
    "morning_soft": {
        "visual": "soft morning sun through window, long shadows across floor",
        "features": "gentle low-angle daylight, calm palette",
    },
    "daylight_neutral": {
        "visual": "even neutral daylight from window, natural soft shadows",
        "features": "balanced interior exposure",
    },
    "golden_hour": {
        "visual": "warm golden sunlight, long dramatic shadows, cozy tone",
        "features": "magic-hour mood indoors",
    },
    "warm_lamps": {
        "visual": "evening scene lit by floor lamp and table lamp, warm pools of light",
        "features": "hygge interior lighting",
    },
    "overcast_soft": {
        "visual": "soft diffused daylight from cloudy sky, even illumination",
        "features": "no harsh highlights, muted exterior",
    },
}


def _is_cozy_final(scene: dict[str, Any]) -> bool:
    return scene.get("stage_key") == "full_restoration_cozy"


def _validate_scenario_scenes(scenes: list[dict[str, Any]]) -> None:
    if len(scenes) != len(STAGE_ORDER):
        raise ValueError(
            f"[Mode12] Expected {len(STAGE_ORDER)} scenes, got {len(scenes)} — cannot keep gradual renovation order."
        )
    for i, expected_key in enumerate(STAGE_ORDER):
        got = scenes[i].get("stage_key")
        if got != expected_key:
            raise ValueError(
                f"[Mode12] Scene index {i} must be stage_key {expected_key!r}, got {got!r}."
            )


def _quality_still_block() -> str:
    return """━━━ QUALITY (STILLS) ━━━
- Magazine-grade interior photography: natural color, accurate white balance, sharp focus, fine texture (plaster, wood grain, fabric).
- Photoreal only; NO cartoon, NO illustration, NO CGI plastic look, NO waxy AI faces, NO warped architecture.
- Clean exposure; avoid blown highlights on the window unless physically plausible.
- Use ONE consistent “camera + grade” recipe for the whole 5-image set — do not switch to a different photographic look between stills."""


def _single_shot_composition_still_block() -> str:
    return """━━━ SINGLE SHOT — NO SPLIT / COLLAGE ━━━
- Exactly ONE uninterrupted photograph — one moment, one static frame, one continuous field of view (like a DSLR interior shot). No “video-style” composite of two shots.
- FORBIDDEN: split-screen, diptych/triptych, before-and-after panels, stacked images, collage, montage, picture-in-picture, storyboard/contact-sheet grid, side-by-side comparison, thin white/gray seam or bar splitting top/bottom or left/right, or any layout that merges two different photographs into one output.
- FORBIDDEN: duplicated scene strips, mirrored halves, multiple timestamps, or “two phases of work visible as separate panels” in a single image."""


def _mode12_anonymity_no_public_figures_block(*, for_video: bool) -> str:
    """Steers away from provider blocks labeled like «images of famous people» / real-person likeness."""
    base = """━━━ ANONYMITY — NO IDENTIFIABLE REAL PEOPLE / CELEBRITY LIKENESS ━━━
- Must read as generic fictional renovation extras only — NOT modeled on any real individual; MUST NOT resemble or evoke any celebrity, politician, influencer, athlete, performer, or other public figure (living or historical).
- FORBIDDEN: recognizable face of a known person, intentional lookalike, caricature of someone famous, “in the style of [person]”, meme faces, paparazzi likeness, or any depiction plausibly read as a specific real identity.
- Stills: keep PPE masks/respirators on crew; faces small, turned away, shadowed, or partly hidden; no sharp eye-contact portraits; stage-5 casual figures must stay equally generic — no celebrity glam or distinctive signature look."""
    video_extra = """

- Video: same — documentary wide shots; backs/sides of heads; masks on workers; NEVER punch in to a facial close-up; faces stay small and indistinct in frame; blur/shallow focus on people OK if interiors stay sharp."""
    return base + (video_extra if for_video else "")


def _room_camera_style_lock_block(is_first_still: bool) -> str:
    establish = (
        "- THIS IS STILL 1/5: establish the CANONICAL room shell + camera framing. Every following still MUST copy this geometry and viewpoint exactly (reference chain enforces it)."
        if is_first_still
        else "- STILLS 2–5: you MUST NOT invent a new room or angle — replicate the prior reference’s architecture and camera verbatim."
    )
    return f"""━━━ ROOM + CAMERA + STYLE LOCK (ABSOLUTE — ALL 5 STILLS) ━━━
{establish}
- The PHYSICAL ROOM never changes dimensions: same floor footprint, ceiling height, wall spans, corner layout — FORBIDDEN to widen/narrow/lengthen the space, add/remove walls, move the window or door, or change ceiling shape.
- WINDOW is ONE fixed opening: same position in the image frame, same width/height, same sill and head height, same frame, mullions, and grille pattern (if any). Only cleanliness, dressings, and light through it may evolve per story.
- VIEW OUTSIDE the window stays ONE consistent exterior slice (same buildings/trees/sky geometry, same horizon line, same season read) — only brightness/color of daylight may shift per LIGHT CONTINUITY rules; NO swapping city, landscape, or weather system between stills.
- Door (if visible): same location, size, swing — never relocate or resize.
- CAMERA is frozen ONE setup for the whole series: same tripod point, same distance into the room, same height (~1.5 m eye level), same horizontal 16:9 framing, same focal length character (24–35 mm FF equiv). NO new angle, NO crop, NO vertical frame, NO drone, NO “different lens” feel.
- VISUAL STYLE must stay UNIFORM: same photoreal DSLR/interior-photo rendering, same sharpness and micro-contrast, same grain level, same lens distortion — NOT one frame illustrated and another photoreal; NOT HDR/sharpness reboot mid-series.
- ALLOWED to change ONLY: surface finishes (paint, plaster mess, floor material state), clutter vs tidy, staged objects and furniture, workers per rules, lamp/light fixture state, and subtle exposure shift that follows the same lens — NEVER the room shell, NEVER the camera, NEVER the imaging style/medium."""


def _topic_progression_block(stage_index: int, stage_key: str) -> str:
    step = stage_index + 1
    hints = {
        "dilapidated_room": "Heavy dirt, junk, old furniture, cobwebs — 2–3 people in white PPE begin dismantling and clearance.",
        "clearance_prep": "Stripped / empty / construction-prep — workers allowed; not yet finished plaster or decor.",
        "rough_finish": "Fresh plaster, screed, rough electrical — gray, unfinished; no final paint or move-in furniture.",
        "finish_furniture": "New finishes and main furniture only — still minimal accessories (no full styled decor yet).",
        "full_restoration_cozy": "Rugs, curtains, decor, plants, lamps — NO PPE crew; vacant preferred or optional 1–2 casual stylist/homeowner figures.",
    }
    hint = hints.get(stage_key, "Match this step exactly.")
    return f"""━━━ TOPIC & STAGE LOCK (step {step}/5) ━━━
- Single real INDOOR residential room renovation — same four walls and layout for all five steps.
- This image MUST reflect ONLY renovation stage {step}/5 ({hint})
- FORBIDDEN: outdoor or street views, other buildings, different room layout, exterior demolition, unrelated objects, watermarks, readable text or logos.
- Forward narrative only: do not jump to a later “after” look when this step is still earlier."""


def _clip_prompt_text(s: str, max_len: int = 90) -> str:
    """One line for video prompts; keeps FastGen prompts short."""
    t = (s or "").strip().replace("\n", " ")
    if len(t) <= max_len:
        return t
    cut = t[: max_len - 1]
    return cut.rsplit(" ", 1)[0] + "..."


def _compact_video_rules_block() -> str:
    """Morph + realism + human agency in one block (avoid repetition + token limit)."""
    return """CORE
- 8s: smooth START->END keyframe morph; locked wide tripod 16:9 photoreal; no camera move; timelapse - steady craft, no long freezes.
- Same geometry: outer room shell (corners, ceiling height, door position) fixed; wall/floor SURFACES may change per stage. Mid-clip ~ plausible halfway.
- FIXED MAJOR OBJECTS (anti-drift): WINDOW frame, mullions/grille, sill height/width in frame MUST stay identical within this clip unless the arc is EXPLICIT glazed replacement (old unit clearly removed then new one installed in separate beats) — NO silent resize, NO new window layout, NO crossfade to a different opening.
- BED / WARDROBE / LARGE CABINET: same piece, same footprint, same silhouette until END shows intentional removal or a VISIBLE swap (haul-out then new placement). NO morphing mattress, NO cabinet that reshapes mid-clip.
- Every visible delta must be earned: tools change surfaces (strip/paint/floor/fixtures), bags haul junk — no pop-in/out, no mime on unchanged zones that should be worked.
- WALL + CEILING WORK VISIBLE: whenever stage implies demo/plaster/paint, crew must physically engage VERTICALS — hands/tools touching walls (scrape, pry, sand, roll, trowel) and ceiling/st overhead (ladder, pole, overhead strip); FORBIDDEN “workers only shuffling floor trash” while walls/ceiling look untouched in a demolition/rough stage.
- While PPE crew on screen, START->END differences need contact + haul. Stage-1 still already has workers. Final cozy clip: PPE crew exit; END has no coveralls (optional casual figures or vacant per still).
- Crew poses natural; faces generic; no text/logos/watermarks."""


# Start stage_key → end stage_key: short stage-specific cues (details live in CORE).
_TRANSITION_REALISM: dict[tuple[str, str], str] = {
    ("dilapidated_room", "clearance_prep"): """HINT - Clear-out: START already has 2-3 PPE workers in the junk; intensity ramps toward 3-4 as space clears; constant wall/ceiling stripping, ladder work, heavy bags; END stripped walls, gutted floor, swept - NOT empty room until crew arrives.""",
    ("clearance_prep", "rough_finish"): """HINT - Rough: trowel/plaster/leveling visibly pressed onto WALL PLANES and ceiling; floor screed passes; where END shows new glazing, show beats: prep opening → unit swap — old window geometry must not morph into new one in one ghost crossfade.""",
    ("rough_finish", "finish_furniture"): """HINT - Finish: paint/wallpaper/brush on walls/ceilings; floor laid; mounts screwed — overhead arm moves; furniture placed without swapping unrelated objects; window frame stays until masked/painted only.""",
    ("finish_furniture", "full_restoration_cozy"): """HINT - Cozy: textiles/art/lighting — hands hang, align, tuck; beds/wardrobes only STYLED not replaced unless END clearly shows new piece carried in earlier; then crew exits; END vacant.""",
}


def _transition_realism_block(scene: dict[str, Any], next_scene: dict[str, Any]) -> str:
    fk = str(scene.get("stage_key", ""))
    tk = str(next_scene.get("stage_key", ""))
    return _TRANSITION_REALISM.get(
        (fk, tk),
        "HINT — Match honest material change from START to END with readable mid-clip states.",
    )


def _camera_still_block() -> str:
    return """━━━ CAMERA (IDENTICAL FOR ALL STILLS) ━━━
- ONE locked-off tripod: absolutely NO camera move, pan, tilt, zoom, or shake.
- Lens: wide-angle full-frame equivalent 24–35mm.
- Height: eye level ~1.5m above floor.
- Aspect ratio: 16:9 horizontal (NOT vertical).
- Target still resolution: 8K or the highest quality the model allows.
- Photorealistic fine detail: wood grain, fabric weave, plaster, dirt, dust."""


def _light_window_block() -> str:
    return """━━━ LIGHT CONTINUITY (WINDOW FIXED, MOOD MAY BUILD) ━━━
- Natural light ALWAYS enters from the SAME single window and opening you locked above — same sun direction family and time-of-day feel (prefer morning/day) across the sequence.
- The EXTERIOR GEOMETRY visible through the glass does not change — only exposure, glare level, and warmth may shift with renovation stage and fixtures.
- Artificial light evolves: scene 1 dim warm bulb; scenes 2–3 temporary work lamps; scene 4 permanent ceiling fixtures + maybe floor lamp; scene 5 layered warm light (sconces, floor lamp, LED accents).
- Color/exposure may progress: stage 1 dull yellowish → stage 3 neutral white → stage 5 warm rich — but still ONE consistent photographic style (see STYLE LOCK); no “different film stock” per frame."""


def _animal_still_block(scene: dict[str, Any], stage_index: int) -> str:
    sk = str(scene.get("stage_key", ""))
    if stage_index == 0 or sk == "dilapidated_room":
        return """━━━ ANIMALS (RARE, SAFE USE ONLY) ━━━
- DEFAULT: no animals.
- OPTIONAL only if composition stays stable: one cat OR one small dog may briefly pass near the doorway or extreme edge of frame.
- Keep the animal secondary, floor-grounded, side-profile or partial silhouette only.
- FORBIDDEN: animal close-up, direct eye contact to camera, jumping, being carried, interacting with tools, blocking workers, or becoming the subject."""

    return """━━━ ANIMALS (OPTIONAL PASS-BY) ━━━
- OPTIONAL and sparse: at most ONE animal total — either one cat OR one small-to-medium dog.
- Placement: near doorway, along far wall, or at extreme frame edge; keep paws on floor and body mostly side-on.
- Behavior: calm walk-through only; a brief pass-by, not a pose.
- FORBIDDEN: centered hero pet, multiple animals, running toward camera, jumping on furniture, interacting with workers/tools, or changing the room composition."""


def _animal_video_block(scene: dict[str, Any], next_scene: dict[str, Any]) -> str:
    starts_abandoned = str(scene.get("stage_key", "")) == "dilapidated_room"
    ends_cozy = _is_cozy_final(next_scene)
    if starts_abandoned:
        return (
            "ANIMALS: usually none. Optional only if naturally plausible: one cat OR one small dog briefly crosses near the doorway or extreme frame edge, floor-level and secondary; no close-up, no interaction with crew or tools."
        )
    if ends_cozy:
        return (
            "ANIMALS: optional calm pass-through of one cat OR one small-to-medium dog near the wall, doorway, or frame edge; keep it brief and peripheral, then let the finished room remain the hero."
        )
    return (
        "ANIMALS: optional and sparse — at most one cat OR one small-to-medium dog may briefly walk through along the far wall or doorway, always secondary, floor-grounded, and never interacting with workers, tools, or furniture."
    )


_WORKER_POSE_HINTS: dict[str, str] = {
    "dilapidated_room": "early dismantling: 2–3 workers bending, lifting bags, pulling loose wallpaper, prying base trim, first ladder touches at ceiling corners, dragging old furniture scraps — busy amid hoarded junk.",
    "clearance_prep": "demolition / haul-out: crowbar at wall-ceiling junction, peeling paper overhead, scraping high corners, stepladder for ceiling strips, shoulder against wall panels, dragging debris but ALSO repeated tool-to-wall/ceiling contact.",
    "rough_finish": "rough trade: trowel/hawk smoothing vertical wall planes and ceiling soffits, sander on upper walls, measuring along plastered surfaces, buckets lifted toward walls — bodies leaning into wall work, not only floor pacing.",
    "finish_furniture": "install / fit-out: brush/roller on walls and ceiling edges, hanging wall cabinets with drill, aligning headboard to wall, overhead lighting mounts, kneeling for floor BUT visible wall touch every beat.",
}


def _people_still_block(scene: dict[str, Any], stage_index: int) -> str:
    sk = str(scene.get("stage_key", ""))
    if stage_index == 0 or sk == "dilapidated_room":
        return """━━━ PEOPLE (STILL 1 — CREW STARTS) ━━━
- Exactly 2–3 adults in WHITE full-body PPE (coveralls, masks/respirators, gloves), generic non-identifiable faces — actively dismantling amid trash (see TRASH block).
- No children or unrelated bystanders.
- NO text, logos, watermarks."""

    if stage_index == 4 or _is_cozy_final(scene):
        return """━━━ PEOPLE (STILL 5 — FINISHED; NO PPE CREW) ━━━
- NO workers in white coveralls or construction gear.
- DEFAULT: vacant showcase — zero humans.
- ALLOWED optionally: at most 1–2 adults in casual clothes (homeowner/stylist), generic faces, softly placed — OR keep fully empty.
- NO text, logos, watermarks."""

    pose_line = _WORKER_POSE_HINTS.get(
        str(scene.get("stage_key", "")),
        "varied active work stances: different heights and facing, no copy-paste poses.",
    )
    return f"""━━━ PEOPLE (WORK STAGES — STILL {stage_index + 1}/5) ━━━
- ALL crew: white protective coveralls, respirators/masks, gloves, shoe covers — same uniform where workers appear.
- POSES (CRITICAL): Each still must show workers in FRESH, DISTINCT body poses vs. any previous still — change stance, arm angles, spine bend, which way they face, and where they stand in the room. NO frozen identical silhouettes across stages; NO “copy” of the reference image’s body positions.
- Stage-appropriate motion cues: favor {pose_line}
- Faces stay generic / non-identifiable; bodies must read as genuinely busy, not repeated stock poses.
- NO children, NO random human passers-by.
- NO text, logos, watermarks."""


def _first_still_extreme_trash_block() -> str:
    return """━━━ STILL 1 — TRASH + OLD FURNITURE + ACTIVE CREW ━━━
- HEAVY neglect: torn bags, spills, bottles, cardboard, fabric, collapsed shelves — floor largely covered; KEEP derelict OLD furniture (worn sofa/bed/wardrobe per room type) as props workers interact with.
- Cobwebs, dull wallpaper stains, ceiling corner grime; window geometry LOCKED — only dirt.
- Crew 2–3 in white PPE must look mid-task in the mess, not posed after cleanup.
- If it reads empty or “light mess” — WRONG."""


def _build_image_prompt(
    scene: dict[str, Any],
    index: int,
    scenario: dict[str, Any],
) -> str:
    room_type = scenario.get("room_type", "studio")
    room_lighting = scenario.get("room_lighting", "morning_soft")

    rv = ROOM_TYPE_VISUALS.get(room_type, ROOM_TYPE_VISUALS["studio"])
    lv = ROOM_LIGHTING_VISUALS.get(room_lighting, ROOM_LIGHTING_VISUALS["morning_soft"])

    stage_name_en = scene.get("name_en", "stage")
    stage_key = str(scene.get("stage_key", ""))
    visual_prompt = scene.get("visual_prompt", "")

    title_line = f"STILL {index + 1}/5 — {stage_name_en.upper()} — room restoration"

    if index == 0:
        ref_people = (
            "PEOPLE: 2–3 workers in white PPE actively clearing — generic faces. "
            "This still defines locked room shell + camera; junk + old furniture volume high."
        )
    elif index == 4:
        ref_people = (
            "PEOPLE: no PPE crew; prefer EMPTY finished room OR optional 1–2 casual figures max. "
            "Match reference shell, camera, style; only decor as scripted."
        )
    else:
        ref_people = (
            "PEOPLE: fully re-pose crew vs. the reference. "
            "GEOMETRY + STYLE: walls, window, door, camera, and imaging look are COPY-PASTE identical to the reference — change ONLY renovation state, objects, and people."
        )

    trash_block = _first_still_extreme_trash_block() if index == 0 else ""

    return f"""Create ONE photorealistic still for a ROOM RESTORATION series (strict order 1→5).
{title_line}

{_quality_still_block()}

{_single_shot_composition_still_block()}

{_mode12_anonymity_no_public_figures_block(for_video=False)}

{_topic_progression_block(index, stage_key)}

{_room_camera_style_lock_block(index == 0)}

{_camera_still_block()}

{_light_window_block()}

{_people_still_block(scene, index)}
{_animal_still_block(scene, index)}
{trash_block}
━━━ ROOM TYPE (keep furniture consistent on late stages) ━━━
{rv['visual']}
{rv['features']}

━━━ USER WINDOW MOOD HINT (blend subtly; must not break single-window continuity above) ━━━
{lv['visual']} | {lv['features']}

━━━ SCENE CONTENT ━━━
{visual_prompt}

REFERENCE CHAIN: If a reference image is provided, treat it as a geometric + stylistic master: same wall corners, ceiling line, window size/position, door (if any), floor perspective, and identical camera vantage. Pixel-align edges where possible. Evolve ONLY surface condition, staged contents, lighting, and people per rules — NEVER a new room or art style. {ref_people}"""


def _build_keyframe_video_prompt(
    scene: dict[str, Any],
    next_scene: dict[str, Any],
    scenario: dict[str, Any],
) -> str:
    """scene → next_scene; 8 s, 16:9, static wide shot. All prompt text in English."""
    room_type = scenario.get("room_type", "studio")
    room_lighting = scenario.get("room_lighting", "morning_soft")

    rv = ROOM_TYPE_VISUALS.get(room_type, ROOM_TYPE_VISUALS["studio"])
    lv = ROOM_LIGHTING_VISUALS.get(room_lighting, ROOM_LIGHTING_VISUALS["morning_soft"])

    from_outcome = scene.get("end_state_en") or scene.get("end_state", "")
    to_outcome = next_scene.get("end_state_en") or next_scene.get("end_state", "")
    action_s = scene.get("action_en") or scene.get("action", "")
    action_e = next_scene.get("action_en") or next_scene.get("action", "")
    stage_name_en = scene.get("name_en", "stage")
    next_name_en = next_scene.get("name_en", "next")

    tool_parts = []
    for t in (scene.get("machinery_en"), next_scene.get("machinery_en")):
        if t:
            tool_parts.append(str(t))
    tools_merged = "; ".join(tool_parts)
    tools_short = (tools_merged[:180] + "...") if len(tools_merged) > 180 else tools_merged

    ends_cozy = _is_cozy_final(next_scene)
    starts_abandoned = str(scene.get("stage_key")) == "dilapidated_room"

    if ends_cozy:
        motion_people = (
            "PEOPLE: PPE crew installs decor (hang art, shelves, lamps, textiles) with real wall contact; then all coveralls exit; END finished room — vacant preferred or optional casual figures only. Preserve bed/wardrobe/window identity per CORE."
        )
    elif starts_abandoned:
        motion_people = (
            "PEOPLE: 2-3 PPE workers already in frame on START; grow busy work to match END (3-4): ladder ceiling strips, wall pry, continuous bag haul - faceless; no children or unrelated bystanders."
        )
    else:
        motion_people = (
            "PEOPLE: white PPE — continuous tool-to-wall and tool-to-ceiling work (trowel, sand, roll, mount); bodies visibly working vertical planes, not only pacing the floor; faceless; no extra people or children."
        )

    arc_a = _clip_prompt_text(from_outcome, 85)
    arc_b = _clip_prompt_text(to_outcome, 85)
    work_from = _clip_prompt_text(action_s, 75)
    work_to = _clip_prompt_text(action_e, 75)

    return f"""Keyframe video: "{stage_name_en}" -> "{next_name_en}". 8s, locked wide tripod 16:9, photoreal ~4K, accelerated timelapse, no camera move, 24-35mm ~1.5m eye height.

{_mode12_anonymity_no_public_figures_block(for_video=True)}
{_compact_video_rules_block()}
{_transition_realism_block(scene, next_scene)}

ARC: {arc_a!r} -> {arc_b!r}. WORK: {work_from!r} -> {work_to!r}. {motion_people}
{_animal_video_block(scene, next_scene)}

ROOM (fixed): {rv['visual']}. LIGHT: one window line; user mood ~ {lv['features']} - keep exterior slice consistent with both keys, adjust only brightness/warmth with stage.
PROPS: {tools_short or "none"}.

Audio: NO music, NO soundtrack, NO melodic background or beats — ONLY realistic diegetic construction/renovation sounds (drills, hammering, sander, scrapes, debris bags, ladder clunks, distant tool impacts). If audio must be minimal, prefer near-silent over any music. No on-screen text/logos. Photoreal; no worker face detail; mid-clip must look halfway between START and END."""


def _build_showcase_zoom_end_still_prompt(scenario: dict[str, Any]) -> str:
    """
    Second image for showcase: same finished room as reference, camera noticeably closer (tighter 16:9).
    """
    room_type = scenario.get("room_type", "studio")
    room_lighting = scenario.get("room_lighting", "morning_soft")
    rv = ROOM_TYPE_VISUALS.get(room_type, ROOM_TYPE_VISUALS["studio"])
    lv = ROOM_LIGHTING_VISUALS.get(room_lighting, ROOM_LIGHTING_VISUALS["morning_soft"])

    return f"""Create ONE photorealistic 16:9 horizontal still — ZOOMED-IN continuation of the attached reference (finished cozy room).

{_single_shot_composition_still_block()}

{_mode12_anonymity_no_public_figures_block(for_video=False)}

REFERENCE: treat as locked 3D scene. You are the SAME room, SAME furniture pieces, SAME decor, SAME window (same frame, mullions, sill — only appears larger in frame because camera moved forward), SAME walls/floor/rugs/plants — ZERO new objects, ZERO removals, ZERO restyle, ZERO different furniture models.

CAMERA ONLY CHANGE: move forward / longer focal length so the field of view is CLEARLY TIGHTER (~20–40% closer than reference): hero zone (sofa or bed or main seating) fills more of frame; edges crop naturally. Eye height ~1.45–1.55m; still interior, not drone.

LIGHT: same mood and direction as reference — {lv["features"]}; no new light fixtures, no time-of-day jump.

Quality: sharp detail on textiles and materials (this frame will be the END key for video — detail must hold).

Room type anchor: {rv["visual"]}. No people or at most same vague figures as reference. No text/logos."""


def _build_room_showcase_keyframe_video_prompt(scenario: dict[str, Any]) -> str:
    """Keyframe video: wide cozy START → closer END still; morph simulates slow dolly-in."""
    room_type = scenario.get("room_type", "studio")
    room_lighting = scenario.get("room_lighting", "morning_soft")
    rv = ROOM_TYPE_VISUALS.get(room_type, ROOM_TYPE_VISUALS["studio"])
    lv = ROOM_LIGHTING_VISUALS.get(room_lighting, ROOM_LIGHTING_VISUALS["morning_soft"])

    return f"""Showcase ZOOM-IN keyframe video. 8s, 16:9 photoreal ~4K, locked tripod at each key, smooth accelerated morph START→END.

{_mode12_anonymity_no_public_figures_block(for_video=True)}
START key: wide establishing finished room. END key: closer framing of THE SAME space — same furniture instances, same window geometry (reads larger in frame), same decor identity. Transition = slow cinematic dolly-in / zoom only.

FORBIDDEN mid-morph: swapping sofa/bed/wardrobe, new art, window replacement, repainting walls a different color, adding/removing major props, lighting style change.

ALLOWED: parallax consistent with forward camera move; subtle exposure shift if physically consistent.

ROOM: {rv["visual"]}. LIGHT line: {lv["features"]}.

Audio: NO music or score — only subtle real interior room tone (quiet ambience) or silent; never background music.

No on-screen text/logos. Photoreal. Mid-clip ~ optical halfway between wide and tight framing."""


def _build_room_showcase_single_ref_fallback_prompt(scenario: dict[str, Any]) -> str:
    """If end still fails — same as before: one ref, prompt-only zoom (worse detail retention)."""
    room_type = scenario.get("room_type", "studio")
    room_lighting = scenario.get("room_lighting", "morning_soft")
    rv = ROOM_TYPE_VISUALS.get(room_type, ROOM_TYPE_VISUALS["studio"])
    lv = ROOM_LIGHTING_VISUALS.get(room_lighting, ROOM_LIGHTING_VISUALS["morning_soft"])

    return f"""Interior RESULT showcase. 8 seconds, 16:9 photoreal ~4K. Single reference = opening frame only.

{_mode12_anonymity_no_public_figures_block(for_video=True)}
LOCK CONTENTS: keep same finished room — same furniture, decor, window. FORBIDDEN restyle or object swaps. CAMERA: slow ZOOM-IN toward main seating/sleep zone; ~1.45m eye height.

LIGHT: {lv["features"]}. Room: {rv["visual"]}. Audio: NO music — quiet interior ambience or silent. No logos/text."""


async def _generate_single_ref_showcase_video(
    index: int,
    prompt: str,
    reference_still: Path,
    output_dir: Path,
    *,
    max_attempts: int = 4,
) -> Path | None:
    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = await generate_single_video_fastgen(
                prompt=prompt,
                output_dir=output_dir,
                index=index,
                reference_image_path=reference_still,
            )
            if result and Path(result).exists():
                logger.success(f"[Mode12] Showcase fallback (single-ref) clip saved: {Path(result).name}")
                return result
            logger.warning(
                f"[Mode12] Showcase fallback: no result (attempt {attempt}/{max_attempts})"
            )
        except Exception as e:
            last_err = e
            logger.warning(
                f"[Mode12] Showcase fallback attempt {attempt}/{max_attempts} failed: {e}"
            )
    if last_err:
        logger.error(f"[Mode12] Showcase fallback failed after {max_attempts} attempts: {last_err}")
    return None


async def _generate_single_image_with_ref(
    prompt: str,
    output_dir: Path,
    index: int,
    reference_image_paths: list[Path],
    *,
    max_attempts: int = 4,
    output_filename: str | None = None,
    log_label: str | None = None,
) -> Path | None:
    last_err: Exception | None = None
    label = log_label or f"Still {index + 1}"
    for attempt in range(1, max_attempts + 1):
        try:
            prompts_with_refs = [(prompt, reference_image_paths)]
            image_paths = await generate_images_with_references_fastgen(
                prompts_with_refs,
                output_dir,
                parallel=False,
            )
            if image_paths and len(image_paths) > 0:
                img_path = image_paths[0]
                if img_path and Path(img_path).exists():
                    name = output_filename or f"stage_{index:03d}_ref.png"
                    new_path = output_dir / name
                    Path(img_path).rename(new_path)
                    return new_path
            logger.warning(f"[Mode12] {label}: empty result (attempt {attempt}/{max_attempts})")
        except Exception as e:
            last_err = e
            logger.warning(
                f"[Mode12] {label} image attempt {attempt}/{max_attempts} failed: {e}"
            )
    if last_err:
        logger.error(f"[Mode12] {label} image failed after {max_attempts} attempts: {last_err}")
    return None


async def _generate_keyframe_video(
    index: int,
    prompt: str,
    start_frame: Path,
    end_frame: Path,
    output_dir: Path,
    *,
    max_attempts: int = 4,
    log_label: str | None = None,
) -> Path | None:
    last_err: Exception | None = None
    label = log_label or f"Keyframe clip {index + 1}"
    for attempt in range(1, max_attempts + 1):
        try:
            result = await generate_video_from_keyframes(
                prompt=prompt,
                output_dir=output_dir,
                start_frame_path=start_frame,
                end_frame_path=end_frame,
                index=index,
            )
            if result and Path(result).exists():
                logger.success(f"[Mode12] {label} saved: {Path(result).name}")
                return result
            logger.warning(f"[Mode12] {label}: no result (attempt {attempt}/{max_attempts})")
        except Exception as e:
            last_err = e
            logger.warning(f"[Mode12] {label} attempt {attempt}/{max_attempts} failed: {e}")
    if last_err:
        logger.error(f"[Mode12] {label} failed after {max_attempts} attempts: {last_err}")
    return None


async def generate_room_restoration_videos(
    scenario: dict[str, Any],
    output_dir: Path,
    session_id: str,
) -> tuple[list[Path | None], dict[str, Any]]:
    scenes = scenario.get("scenes", [])
    if not scenes:
        raise ValueError("[Mode12] No scenes to generate")
    _validate_scenario_scenes(scenes)

    fastgen_key = getattr(settings, "fastgen_api_key", "") or ""
    if not fastgen_key:
        raise RuntimeError("FASTGEN_API_KEY not set — required for Mode 12")

    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "reference_images"
    images_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"[Mode12] {len(scenes)} stills (16:9 chain, ~8s clips between stages)...")
    ref_image_paths: list[Path | None] = []
    previous_image: Path | None = None

    for i, scene in enumerate(scenes):
        image_prompt = _build_image_prompt(scene, i, scenario)
        refs = [previous_image] if previous_image else []
        logger.info(f"[Mode12] Still {i + 1}/{len(scenes)} ({scene.get('stage_key', '')})")
        image_path = await _generate_single_image_with_ref(
            prompt=image_prompt,
            output_dir=images_dir,
            index=i,
            reference_image_paths=refs,
        )
        if image_path:
            ref_image_paths.append(image_path)
            previous_image = image_path
            logger.success(f"[Mode12] Stage {i + 1} ref: {image_path.name}")
        else:
            ref_image_paths.append(None)
            logger.error(f"[Mode12] Stage {i + 1}: image failed")

    failed_stills = [i for i, p in enumerate(ref_image_paths) if p is None]
    if failed_stills:
        raise RuntimeError(
            f"[Mode12] Reference still generation failed for stage index(es) {failed_stills} — "
            "cannot build a consistent gradual sequence."
        )

    num_videos = len(scenes) - 1
    if num_videos < 1:
        raise ValueError("[Mode12] Need at least 2 stages")

    last_still = Path(ref_image_paths[-1])
    showcase_index = 50

    # Like mode8 drone showcase image: extra still BEFORE parallel video wave (end frame for showcase).
    showcase_end_prompt = _build_showcase_zoom_end_still_prompt(scenario)
    logger.info(
        f"[Mode12] STEP 1b: showcase END still (closer framing, ref={last_still.name}) "
        "— before parallel videos..."
    )
    showcase_end_still: Path | None = await _generate_single_image_with_ref(
        prompt=showcase_end_prompt,
        output_dir=images_dir,
        index=5,
        reference_image_paths=[last_still],
        output_filename="showcase_zoom_end_ref.png",
        log_label="Showcase zoom END still",
    )

    # Same pattern as mode8/mode9: N asyncio tasks → one gather (each → own FastGen browser via to_thread).
    n_parallel = num_videos + 1
    logger.info(
        f"[Mode12] STEP 2: parallel video generation — {num_videos} stage transitions + 1 showcase "
        f"= {n_parallel} tasks (separate browser per task, like mode8/mode9)..."
    )
    video_tasks: list[asyncio.Task] = []
    for i in range(num_videos):
        start_frame = ref_image_paths[i]
        end_frame = ref_image_paths[i + 1]
        scene_a = scenes[i]
        scene_b = scenes[i + 1]
        video_prompt = _build_keyframe_video_prompt(scene_a, scene_b, scenario)
        video_tasks.append(
            asyncio.create_task(
                _generate_keyframe_video(
                    index=i,
                    prompt=video_prompt,
                    start_frame=Path(start_frame),
                    end_frame=Path(end_frame),
                    output_dir=output_dir,
                )
            )
        )

    if showcase_end_still and Path(showcase_end_still).exists():
        kf_prompt = _build_room_showcase_keyframe_video_prompt(scenario)
        video_tasks.append(
            asyncio.create_task(
                _generate_keyframe_video(
                    index=showcase_index,
                    prompt=kf_prompt,
                    start_frame=last_still,
                    end_frame=Path(showcase_end_still),
                    output_dir=output_dir,
                    log_label="Showcase zoom keyframe video",
                )
            )
        )
    else:
        logger.warning(
            f"[Mode12] Showcase end still missing — parallel slot {n_parallel} uses single-ref fallback"
        )
        fb_prompt = _build_room_showcase_single_ref_fallback_prompt(scenario)
        video_tasks.append(
            asyncio.create_task(
                _generate_single_ref_showcase_video(
                    index=showcase_index,
                    prompt=fb_prompt,
                    reference_still=last_still,
                    output_dir=output_dir,
                )
            )
        )

    raw_results = await asyncio.gather(*video_tasks, return_exceptions=True)

    transition_results = raw_results[:num_videos]
    showcase_result = raw_results[num_videos]

    valid_paths: list[Path | None] = []
    for i, result in enumerate(transition_results):
        if isinstance(result, Exception):
            logger.error(f"[Mode12] Transition clip {i + 1}: {result}")
            valid_paths.append(None)
        else:
            valid_paths.append(result)

    failed_clips = [
        i for i, p in enumerate(valid_paths) if p is None or not Path(p).exists()
    ]
    if failed_clips:
        raise RuntimeError(
            f"[Mode12] Keyframe video failed for transition index(es) {failed_clips} — "
            "partial timeline is not accepted."
        )

    showcase_path: Path | None = None
    if isinstance(showcase_result, Exception):
        logger.error(f"[Mode12] Showcase clip: {showcase_result}")
    elif showcase_result and Path(showcase_result).exists():
        showcase_path = Path(showcase_result)

    if not showcase_path or not Path(showcase_path).exists():
        raise RuntimeError(
            "[Mode12] Showcase overview clip failed (parallel batch returned no valid file)."
        )
    valid_paths.append(showcase_path)

    enriched_scenes = []
    for i, scene in enumerate(scenes):
        es = dict(scene)
        if i < len(ref_image_paths) and ref_image_paths[i]:
            es["reference_image_path"] = str(ref_image_paths[i])
        if i > 0 and i - 1 < len(valid_paths) and valid_paths[i - 1]:
            es["video_path"] = str(valid_paths[i - 1])
        enriched_scenes.append(es)

    enriched = dict(scenario)
    enriched["scenes"] = enriched_scenes
    enriched["clip_duration_seconds"] = 8
    enriched["aspect_ratio"] = "16:9"
    enriched["showcase_video_path"] = str(showcase_path)
    if showcase_end_still and Path(showcase_end_still).exists():
        enriched["showcase_end_reference_path"] = str(showcase_end_still.resolve())
    else:
        enriched["showcase_end_reference_path"] = None
    ok = sum(1 for p in valid_paths if p and Path(p).exists())
    logger.success(
        f"[Mode12] Done: {ok}/{num_videos + 1} clips "
        f"({num_videos} stage transitions + 1 zoom showcase)"
    )
    return valid_paths, enriched
