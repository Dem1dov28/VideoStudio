"""
Mode 11 Contextual Prompt Generator — LLM-based monument pipeline.

Pipeline:
1) Analyze scenario and continuity constraints
2) Generate image prompts per stage (complete -> empty)
3) Generate reconstruction video prompts (empty -> complete)
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from utils.json_parse import parse_json_safe
from utils.llm import make_llm
from modes.mode11.scenario_writer import (
    build_transition_profiles,
    linear_monument_remaining_pct,
    monument_remaining_pct_rubric,
)

# Per-clip video LLM sees two image-prompt excerpts; cap each to limit tokens while keeping quotas + stage detail.
_MODE11_KEYFRAME_IMG_PROMPT_MAX_CHARS = 3600


async def _llm_text(system_text: str, human_text: str, timeout_s: float = 30.0, temperature: float = 0.5) -> str:
    llm = make_llm(temperature=temperature)
    resp = await asyncio.wait_for(
        llm.ainvoke(
            [
                SystemMessage(content=system_text),
                HumanMessage(content=human_text),
            ]
        ),
        timeout=timeout_s,
    )
    return (resp.content.strip() if hasattr(resp, "content") else str(resp).strip()) or ""


def _brief_scene(scene: dict[str, Any], num_scenes: int = 0) -> str:
    note = scene.get("photo_director_note_en") or ""
    extra = f" | director={note}" if note else ""
    pct = scene.get("monument_remaining_pct")
    pct_note = ""
    if pct is not None and num_scenes > 1:
        pct_note = f" | ~{pct}%_of_iconic_mass_remains"
    return (
        f"- idx={scene.get('index')} key={scene.get('stage_key')} "
        f"name={scene.get('name_en', scene.get('name'))} "
        f"action={scene.get('action_en', scene.get('action'))}{pct_note}{extra}"
    )


def _format_plan_lines(title: str, lines: list[str] | None) -> str:
    items = [str(x).strip() for x in (lines or []) if str(x).strip()]
    if not items:
        return ""
    return f"{title}:\n" + "\n".join(f"- {x}" for x in items)


def _fallback_context_payload(structure: str, location: str, camera_position: str) -> dict[str, Any]:
    return {
        "camera_rules": [
            f"Use one fixed camera position: {camera_position}",
            "Keep exact framing and lens characteristics between all stages and transitions",
            "Keep camera altitude above the monument highest point with a high-angle overview",
            "Keep full monument body fully visible in frame at all times without cropping",
            "Never pan, rotate, reframe, mirror, or tilt the frame",
        ],
        "background_invariants": [
            f"Keep location identity stable: {location}",
            "Preserve skyline, horizon level, and weather baseline",
            "No new landmarks, no scene relocation, no style switching",
        ],
        "physics_rules": [
            "Changes must follow realistic material behavior and structural dependencies",
            "No magical morphing, teleportation, or instant geometry replacement",
            "Intermediate states should remain physically plausible",
            "Reference frames are ordered complete→cleared site: each stage must show strictly MORE damage than the complete anchor — never repair, restore, or rebuild toward completeness",
            "Linear timelapse pacing: each stage removes about the same share of visible mass vs the iconic complete state (no one huge jump early then microscopic edits late); reconstruction clips must advance through their percentage band steadily over time",
        ],
        "identity_anchors": [
            f"Preserve core identity features of {structure}",
            "Maintain monument silhouette logic for each stage",
            "Use stage-specific damage and remains consistent with timeline direction",
        ],
        "orientation_rules": [
            "Frame must stay upright and vertical for 9:16 composition",
            "No upside-down frames and no mirrored flips",
            "Horizon must remain horizontal and stable",
        ],
    }


def _context_payload_to_text(context_payload: dict[str, Any]) -> str:
    sections = [
        ("Camera Rules", context_payload.get("camera_rules", [])),
        ("Background Invariants", context_payload.get("background_invariants", [])),
        ("Physics Rules", context_payload.get("physics_rules", [])),
        ("Identity Anchors", context_payload.get("identity_anchors", [])),
        ("Orientation Rules", context_payload.get("orientation_rules", [])),
    ]
    chunks: list[str] = []
    for title, lines in sections:
        items = [str(x).strip() for x in (lines or []) if str(x).strip()]
        if not items:
            continue
        chunks.append(f"{title}:")
        chunks.extend([f"- {x}" for x in items])
    return "\n".join(chunks).strip()


def _normalize_whitespace(text: str) -> str:
    cleaned = re.sub(r"[ \t]+", " ", (text or "")).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def _ensure_required_constraints(text: str, is_video: bool = False) -> str:
    out = _normalize_whitespace(text)
    low = out.lower()
    required_chunks = [
        "vertical 9:16",
        "fixed camera",
        "same location",
        "high-angle",
        "camera above",
        "fully visible",
        "upright",
        "horizon level",
        "no logos",
        "no text",
        "photorealistic",
    ]
    if is_video:
        required_chunks.extend(
            [
                "physical reconstruction",
                "no magical morphing",
            ]
        )
    missing = [chunk for chunk in required_chunks if chunk not in low]
    if missing:
        out = (
            f"{out}\n\n"
            "Constraints: vertical 9:16, photorealistic, fixed camera, same location, high-angle view, "
            "camera above monument top line, full monument fully visible in frame, upright frame, "
            "horizon level, no logos, no text."
        )
        if is_video:
            out += " Use physical reconstruction only and no magical morphing."
    return out.strip()


def _enforce_video_word_count(text: str, min_words: int = 120, max_words: int = 180) -> str:
    out = _normalize_whitespace(text)
    words = out.split()
    if len(words) > max_words:
        return " ".join(words[:max_words]).strip()
    if len(words) >= min_words:
        return out
    filler = (
        " Keep motion physically consistent between keyframes, maintain stable perspective and background landmarks, "
        "and ensure every added structural element appears in a believable construction order with realistic material interaction."
    )
    while len(out.split()) < min_words:
        out = f"{out}{filler}"
    return " ".join(out.split()[:max_words]).strip()


# Mode 11 video prompts must carry landmark labor + pacing; 180 words often drops steel/equipment specifics.
_MODE11_VIDEO_PROMPT_MAX_WORDS = 260


def _sanitize_prompt_text(
    text: str,
    is_video: bool = False,
    *,
    max_video_words: int | None = None,
) -> str:
    out = _ensure_required_constraints(text, is_video=is_video)
    if is_video:
        cap = max_video_words if max_video_words is not None else 180
        out = _enforce_video_word_count(out, min_words=120, max_words=cap)
    return out


async def _analyze_context(scenario: dict[str, Any]) -> dict[str, Any]:
    structure = scenario.get("structure_name_en", "Monument")
    location = scenario.get("location_name", "Historic location")
    camera_position = scenario.get("camera_position_en", "Fixed three-quarter view, level horizon, upright subject.")
    scenes = scenario.get("scenes", [])
    nsc = len(scenes)
    scene_list = "\n".join(_brief_scene(s, num_scenes=nsc) for s in scenes)

    narrative_en = (scenario.get("narrative_arc_en") or "").strip()
    profile_note = (scenario.get("stage_count_profile_en") or "").strip()
    photo_plan_block = _format_plan_lines("Photo stills plan (deconstruction chain)", scenario.get("photo_generation_plan_en"))
    video_plan_block = _format_plan_lines("Reconstruction video plan", scenario.get("video_generation_plan_en"))
    creative_block = "\n\n".join(
        x
        for x in (
            f"Landmark narrative (tone + story):\n{narrative_en}" if narrative_en else "",
            f"Stage-density guidance:\n{profile_note}" if profile_note else "",
            photo_plan_block,
            video_plan_block,
        )
        if x
    )

    fallback_payload = _fallback_context_payload(structure, location, camera_position)
    prompt = f"""Create continuity rules for a monument timelapse.
Structure: {structure}
Location: {location}
Camera baseline: {camera_position}
Scenes (reverse timeline complete->empty):
{scene_list}

{creative_block if creative_block else "(No extra creative brief supplied.)"}

Return strict JSON only with this schema:
{{
  "camera_rules": ["..."],
  "background_invariants": ["..."],
  "physics_rules": ["..."],
  "identity_anchors": ["..."],
  "orientation_rules": ["..."]
}}
Each list must have 3-6 concise bullets in English.
"""
    try:
        text = await _llm_text(
            system_text="You are a senior prompt director for photoreal timelapse generation.",
            human_text=prompt,
            timeout_s=35.0,
            temperature=0.4,
        )
        payload = parse_json_safe(text)
        for key in fallback_payload.keys():
            if not isinstance(payload.get(key), list) or not payload.get(key):
                payload[key] = fallback_payload[key]
        analysis_text = _context_payload_to_text(payload)
        return {
            "analysis": analysis_text,
            "structured": payload,
        }
    except Exception as e:
        logger.warning(f"[Mode11 Context] Context analysis fallback: {e}")
        return {
            "analysis": _context_payload_to_text(fallback_payload),
            "structured": fallback_payload,
        }


async def _generate_image_prompts(scenario: dict[str, Any], analysis_text: str) -> list[dict[str, Any]]:
    scenes = scenario.get("scenes", [])
    structure = scenario.get("structure_name_en", "Monument")
    camera_position = scenario.get("camera_position_en", "Fixed three-quarter view, level horizon, upright subject.")
    narrative_en = (scenario.get("narrative_arc_en") or "").strip()
    profile_note = (scenario.get("stage_count_profile_en") or "").strip()
    photo_plan_block = _format_plan_lines("Checklist from creative director (photo)", scenario.get("photo_generation_plan_en"))
    prompts: list[dict[str, Any]] = []
    prev_text = ""

    n_still = len(scenes)
    for i, scene in enumerate(scenes):
        base_visual = scene.get("visual_prompt", "")
        stage_name = scene.get("name_en", scene.get("name", f"stage_{i+1}"))
        director_note = (scene.get("photo_director_note_en") or "").strip()
        director_block = f"Stage-specific director note:\n{director_note}\n" if director_note else ""
        narrative_block = f"Landmark narrative:\n{narrative_en}\n" if narrative_en else ""
        profile_block = f"Density profile:\n{profile_note}\n" if profile_note else ""
        quota_pct = scene.get("monument_remaining_pct")
        if quota_pct is None and n_still > 1:
            quota_pct = linear_monument_remaining_pct(i, n_still)
        pacing_line = ""
        if quota_pct is not None and n_still > 1:
            step = max(1, round(100 / (n_still - 1)))
            prev_q = linear_monument_remaining_pct(i - 1, n_still) if i > 0 else None
            next_q = linear_monument_remaining_pct(i + 1, n_still) if i < n_still - 1 else None
            ladder = (
                f"0–100 ladder: prev ~{prev_q}% → THIS ~{quota_pct}% → next ~{next_q}% (~{step} points per step). "
                if prev_q is not None and next_q is not None
                else ""
            )
            rubric = monument_remaining_pct_rubric(quota_pct)
            cliff = ""
            if i == n_still - 2:
                cliff = (
                    "PENULTIMATE FRAME MUST BE TRACE-LEVEL RUINS, NOT ‘almost complete’ — next frame is bare ground. "
                )
            if i == n_still - 1:
                cliff = "FINAL FRAME: only remove last ~{step}% rubble from near-vanish state. ".format(step=step)
            pacing_line = (
                f"LINEAR PHOTO TARGET: ~{quota_pct}% iconic mass remains (~{step} points between neighbors).\n"
                f"{ladder}{cliff}\n"
                f"Rubric: {rubric}\n"
            )
        prompt = f"""Generate an English photorealistic IMAGE prompt for stage {i+1}/{len(scenes)}.
Structure: {structure}
Stage: {stage_name}
Still-image order is ONLY: iconic complete → progressive damage → cleared site. Do NOT describe construction, repair, or restoration in these image prompts.

{pacing_line}{narrative_block}{profile_block}{photo_plan_block}

{director_block}
Continuity rules:
{analysis_text}

Camera position (must stay unchanged):
{camera_position}

Current stage source details:
{base_visual}

Previous generated prompts summary:
{prev_text[-1200:] if prev_text else "none"}

Requirements:
- Vertical 9:16 realistic camera look
- Same fixed camera and unchanged location
- Camera is above monument top line (high-angle overview)
- Full monument body fully visible in frame (no cropped top/base/sides)
- Keep frame upright: no rotation, no upside-down image, no mirrored flip
- Horizon must be horizontal and stable
- Only monument condition changes for THIS stage
- Monotonic deconstruction: later stages must NEVER look repaired, restored, or more intact than earlier stages; forbid construction crews, repair, rebuilding, or adding mass
- Match the linear pacing target and rubric: never output penultimate-almost-complete + last-empty; late frames must be mostly gone before the final clear
- CONTENT PRESERVATION (critical): Your final prompt MUST retain every substantive fact from "Current stage source details" — PHOTO QUOTA percentages, neighbor ladder, 5-/7-scene UNIQUE STAGE DETAIL (heights, tiers, materials, what is removed). You may tighten wording but must NOT drop numbers, structural stages, or anti-cliff rules; do not replace with generic "ruins" language
- Avoid repeating exact wording from previous prompts
- No brands/logos/text in frame
Return only the final prompt text."""
        try:
            out = await _llm_text(
                system_text=(
                    "You write precise image prompts for photoreal generation. "
                    "When the user supplies a long 'Current stage source details' block, your output must embed those "
                    "requirements (quotas, exact ruin states, dimensions) so the image model cannot miss them."
                ),
                human_text=prompt,
                timeout_s=30.0,
                temperature=0.55,
            )
        except Exception:
            out = f"{base_visual}\nFixed camera, same background, photorealistic 9:16."
        out = _sanitize_prompt_text(out, is_video=False)
        prompts.append(
            {
                "stage_index": i,
                "stage_key": scene.get("stage_key", f"stage_{i}"),
                "prompt_text": out,
                "prompt_type": "image",
                "language": "en",
            }
        )
        prev_text += f"\n[{i}] {out}"
    return prompts


async def _generate_reconstruction_video_prompts(
    scenario: dict[str, Any],
    analysis_text: str,
    image_prompts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    scenes = scenario.get("scenes", [])
    structure = scenario.get("structure_name_en", "Monument")
    camera_position = scenario.get("camera_position_en", "Fixed three-quarter view, level horizon, upright subject.")
    transition_profiles: list[dict[str, Any]] = list(scenario.get("transition_profiles") or [])
    narrative_en = (scenario.get("narrative_arc_en") or "").strip()
    profile_note = (scenario.get("stage_count_profile_en") or "").strip()
    video_plan_block = _format_plan_lines("Checklist from creative director (video)", scenario.get("video_generation_plan_en"))
    prompts: list[dict[str, Any]] = []

    # Playback order for videos: empty->complete
    for out_idx, start_idx in enumerate(range(len(scenes) - 1, 0, -1)):
        from_scene = scenes[start_idx]
        to_scene = scenes[start_idx - 1]
        from_img = image_prompts[start_idx]["prompt_text"] if start_idx < len(image_prompts) else ""
        to_img = image_prompts[start_idx - 1]["prompt_text"] if start_idx - 1 < len(image_prompts) else ""
        prof = transition_profiles[out_idx] if out_idx < len(transition_profiles) else {}
        labor_block = ""
        if prof:
            micro = prof.get("micro_actions_en") or []
            micro_txt = "\n".join(f"  - {m}" for m in micro[:8]) if isinstance(micro, list) else ""
            labor_block = f"""
LANDMARK-SPECIFIC LABOR (must follow — this is not generic CGI):
Workers: {prof.get('workers_en', '')}
Equipment: {prof.get('machinery_en', '')}
Main action for this clip: {prof.get('action_en', '')}
Micro-actions:
{micro_txt}
"""
        cs = prof.get("completeness_start_pct")
        ce = prof.get("completeness_end_pct")
        pacing_video = ""
        if cs is not None and ce is not None:
            pacing_video = (
                f"\nEVEN CLIP PACING: Structural completeness must advance steadily from ~{cs}% to ~{ce}% "
                "of the iconic monument (100% = fully built). Spread work across the entire clip evenly — "
                "not a burst at the start nor a nearly static tail.\n"
            )

        narrative_block = f"Landmark narrative (reverse in stills, forward labor here):\n{narrative_en}\n\n" if narrative_en else ""
        profile_block = f"Density profile:\n{profile_note}\n\n" if profile_note else ""
        prompt = f"""Generate an English KEYFRAME VIDEO prompt for a CONSTRUCTION / RESTORATION timelapse (like a house build in mode 8).
Structure: {structure}
Transition playback direction: from LESS complete (from stage) to MORE complete (to stage) — workers ADD mass, detail, and coherence.
From stage: {from_scene.get('name_en', from_scene.get('name'))}
To stage: {to_scene.get('name_en', to_scene.get('name'))}
{labor_block}{pacing_video}
{narrative_block}{profile_block}{video_plan_block}

Continuity rules:
{analysis_text}

Camera position (must stay unchanged):
{camera_position}

From image prompt reference:
{from_img[:_MODE11_KEYFRAME_IMG_PROMPT_MAX_CHARS]}

To image prompt reference:
{to_img[:_MODE11_KEYFRAME_IMG_PROMPT_MAX_CHARS]}

Requirements:
- Fixed camera and identical background (tripod-locked); same high-angle overview; full monument in frame
- Upright frame, level horizon, no orbital camera moves
- Show ACTIVE workers and equipment: walking, lifting, riveting, mortaring, planting, rigging — timelapse motion blur
- The monument STRUCTURE must evolve from start keyframe toward end keyframe through believable staged work (no magical morph)
- Obey EVEN CLIP PACING if provided — uniform progress through the percentage band for the whole duration
- Physical reconstruction only; materials behave by weight and order for THIS landmark
- 120-180 words, concise and actionable
- No logos/text
Return only the final prompt text."""
        try:
            out = await _llm_text(
                system_text="You write keyframe video transition prompts for realistic timelapses.",
                human_text=prompt,
                timeout_s=30.0,
                temperature=0.6,
            )
        except Exception:
            out = (
                f"Reconstruction transition from {from_scene.get('name_en')} to {to_scene.get('name_en')}. "
                "Fixed camera and same location. Realistic progressive build-up only."
            )
        out = _sanitize_prompt_text(out, is_video=True, max_video_words=_MODE11_VIDEO_PROMPT_MAX_WORDS)
        prompts.append(
            {
                "transition_index": out_idx,
                "from_scene_index": start_idx,
                "to_scene_index": start_idx - 1,
                "prompt_text": out,
                "prompt_type": "video",
                "language": "en",
            }
        )
    return prompts


async def generate_contextual_prompts(
    scenario: dict[str, Any],
    language: str = "en",
) -> dict[str, Any]:
    del language  # FastGen prompts stay English
    logger.info("[Mode11 Contextual] Starting monument contextual prompt pipeline...")

    scenario_work = dict(scenario)
    st_key = scenario_work.get("structure_type")
    tprof = list(scenario_work.get("transition_profiles") or [])
    stage_sequence = [s.get("stage_key") for s in scenario_work.get("scenes", []) if s.get("stage_key")]
    if not tprof and st_key:
        scenario_work["transition_profiles"] = build_transition_profiles(
            str(st_key),
            stage_sequence=stage_sequence or None,
        )
    elif (
        tprof
        and st_key
        and any((p or {}).get("completeness_start_pct") is None for p in tprof)
    ):
        scenario_work["transition_profiles"] = build_transition_profiles(
            str(st_key),
            stage_sequence=stage_sequence or None,
        )

    context = await _analyze_context(scenario_work)
    image_prompts = await _generate_image_prompts(scenario_work, context.get("analysis", ""))
    video_prompts = await _generate_reconstruction_video_prompts(
        scenario_work, context.get("analysis", ""), image_prompts
    )

    logger.success(
        f"[Mode11 Contextual] Complete: {len(image_prompts)} image prompts, {len(video_prompts)} video prompts"
    )
    return {
        "context": context,
        "image_prompts": image_prompts,
        "video_prompts": video_prompts,
        "scenario": scenario_work,
    }
