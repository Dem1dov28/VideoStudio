"""
Mode 11 Video Generator — Landmark construction / restoration timelapse (keyframe build-up).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import asyncio
from loguru import logger
from langchain_core.messages import HumanMessage, SystemMessage

from agents.content_generator.fastgen_scraper import (
    generate_video_from_keyframes,
    generate_images_with_references_fastgen,
    generate_single_video_multi_ref,
)
from config import settings
from utils.llm import make_llm
from modes.clickbait_preview import generate_clickbait_preview
from modes.mode11.contextual_prompt_generator import generate_contextual_prompts
from modes.mode11.scenario_writer import build_transition_profiles


def _probe_video_duration(path: Path) -> float | None:
    if not path or not path.exists():
        return None
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout or "{}")
        duration_str = (data.get("format") or {}).get("duration")
        return float(duration_str) if duration_str else None
    except Exception:
        return None


def _probe_video_info(path: Path) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout or "{}")
    except Exception:
        return {}


def _has_video_stream(probe_data: dict[str, Any]) -> bool:
    for stream in probe_data.get("streams", []) or []:
        if (stream or {}).get("codec_type") == "video":
            return True
    return False


def _can_decode_first_frame(path: Path) -> bool:
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(path),
        "-frames:v",
        "1",
        "-f",
        "null",
        "-",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return result.returncode == 0
    except Exception:
        return False


def _is_video_valid(path: Path, min_duration: float = 2.0, min_size_bytes: int = 120_000) -> bool:
    if not path or not path.exists():
        return False
    if path.stat().st_size < min_size_bytes:
        logger.warning(f"[Mode11] Video {path.name} is too small: {path.stat().st_size} bytes")
        return False
    probe_data = _probe_video_info(path)
    duration = _probe_video_duration(path)
    if duration is None and not probe_data:
        return True
    if not _has_video_stream(probe_data):
        logger.warning(f"[Mode11] Video {path.name} has no video stream")
        return False
    if duration is not None and duration < min_duration:
        logger.warning(f"[Mode11] Video {path.name} too short: {duration:.2f}s")
        return False
    if not _can_decode_first_frame(path):
        logger.warning(f"[Mode11] Video {path.name} failed decode check")
        return False
    return True


async def _normalize_video(path: Path, output_dir: Path) -> Path | None:
    normalized = output_dir / f"{path.stem}_norm.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(path),
        "-r",
        "30",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "19",
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(normalized),
    ]
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and normalized.exists():
            return normalized
        logger.warning(f"[Mode11] ffmpeg normalize failed for {path.name}: {result.stderr[-200:] if result.stderr else 'unknown'}")
        return None
    except Exception as e:
        logger.warning(f"[Mode11] normalize error for {path.name}: {e}")
        return None


def _build_image_prompt(scene: dict[str, Any], index: int, total: int, scenario: dict[str, Any] | None = None) -> str:
    camera_position = scene.get("camera_position_en", "Fixed three-quarter view, level horizon, upright subject.")
    site_activity = ""
    if scene.get("stage_key") and scene.get("stage_key") != "final_complete":
        site_activity = (
            "\nSITE ACTIVITY (deconstruction only): dust plumes, falling debris, rubble piles, collapse dust — "
            "no repair crews, no restorers, no scaffolding that adds new mass.\n"
        )
    director = (scene.get("photo_director_note_en") or "").strip()
    director_block = f"\nDIRECTOR NOTE (this stage): {director}\n" if director else ""
    creative_extra = ""
    if scenario:
        nar = (scenario.get("narrative_arc_en") or "").strip()
        prof = (scenario.get("stage_count_profile_en") or "").strip()
        if nar:
            creative_extra += f"\nLANDMARK NARRATIVE: {nar}\n"
        if prof:
            creative_extra += f"DENSITY PROFILE: {prof}\n"
    return f"""Create a photorealistic still image for a landmark deconstruction reference sequence (complete → cleared site).

{scene.get('visual_prompt', '')}
{site_activity}{director_block}{creative_extra}
Frame index: {index + 1}/{total}
Vertical 9:16, realistic texture detail.
Keep camera and background frozen across all frames.
Camera position (must be exact and unchanged): {camera_position}
Camera viewpoint is high-angle and above the monument highest point.
Keep the entire monument fully visible in frame (no cropping of top/base/sides).
Keep image orientation upright: do not rotate, flip, or tilt.
Keep horizon perfectly level.
Only monument condition changes according to stage — always toward MORE damage, NEVER toward repair or restoration.
"""


async def _llm_enrich_image_prompt(base_prompt: str, structure_name: str) -> str:
    try:
        llm = make_llm(temperature=0.25)
        msg = [
            SystemMessage(content="You are an expert photorealistic prompt engineer."),
            HumanMessage(
                content=(
                    f"Improve this image generation prompt for a landmark deconstruction still-frame sequence of {structure_name} "
                    "(stages go from iconic complete toward cleared site; each frame must be more damaged than the anchor, never repaired). "
                    "Keep camera-lock rules and realism constraints. Return plain prompt text only.\n\n"
                    f"{base_prompt}"
                )
            ),
        ]
        resp = await asyncio.wait_for(llm.ainvoke(msg), timeout=20.0)
        text = resp.content.strip() if hasattr(resp, "content") else str(resp).strip()
        return text or base_prompt
    except Exception:
        return base_prompt


def _build_keyframe_prompt(
    start_scene: dict[str, Any],
    end_scene: dict[str, Any],
    scenario: dict[str, Any],
    transition_profile: dict[str, Any] | None = None,
    reconstruction_mode: bool = False,
) -> str:
    camera_position = (start_scene.get("camera_position_en") or scenario.get("camera_position_en") or "Fixed three-quarter view, level horizon, upright subject.")
    structure_en = scenario.get("structure_name_en", "monument")
    location = scenario.get("location_name", "historic location")

    workers = (transition_profile or {}).get("workers_en") or "Workers in period-appropriate clothing moving on scaffolding and ground."
    machinery = (transition_profile or {}).get("machinery_en") or "Scaffolding, ropes, hand winches, barrows — generic unbranded equipment."
    main_action = (transition_profile or {}).get("action_en") or end_scene.get("action_en", "progressive construction work")
    micro = (transition_profile or {}).get("micro_actions_en") or []
    micro_lines = "\n".join(f"- {m}" for m in (micro[:6] if isinstance(micro, list) else []))

    transition_directive = (
        "CONSTRUCTION / RESTORATION TIMELAPSE: the monument physically gains mass, detail, and coherence from START frame to END frame. "
        "Show real labor — carrying, lifting, riveting, mortaring, planting, cabling — not magic morphs."
        if reconstruction_mode
        else "State transition with physical plausibility."
    )

    nar = (scenario.get("narrative_arc_en") or "").strip()
    prof = (scenario.get("stage_count_profile_en") or "").strip()
    vplan = scenario.get("video_generation_plan_en") or []
    vplan_txt = ""
    if isinstance(vplan, list) and vplan:
        vplan_txt = "\n".join(f"- {str(x).strip()}" for x in vplan[:8] if str(x).strip())
    creative_block = ""
    if nar or prof or vplan_txt:
        creative_block = "\n━━━ CREATIVE BRIEF (follow for this landmark) ━━━\n"
        if nar:
            creative_block += f"Narrative: {nar}\n"
        if prof:
            creative_block += f"Stage density: {prof}\n"
        if vplan_txt:
            creative_block += f"Video plan:\n{vplan_txt}\n"

    return f"""⚠️ MONUMENT TIMELAPSE — SAME IDEA AS HOUSE CONSTRUCTION (MODE 8)
Highly satisfying construction timelapse: START frame → END frame with visible WORK IN PROGRESS.

STRUCTURE: {structure_en} — {location}
{transition_directive}
{creative_block}

START STATE (less complete): {start_scene.get('name_en', start_scene.get('name', 'stage'))}
END STATE (more complete): {end_scene.get('name_en', end_scene.get('name', 'stage'))}

PRIMARY BUILD ACTION (this clip):
{main_action}

WORKERS (must be active, motion-blurred timelapse):
{workers}

EQUIPMENT & SCAFFOLDING (moving / in use):
{machinery}

SPECIFIC MICRO-ACTIONS:
{micro_lines if micro_lines else "- teams passing materials\n- dust and chips\n- shadows shifting"}

━━━ CAMERA (LOCKED — LIKE MODE 8) ━━━
- Tripod-locked: same position, lens, and framing for entire clip
- {camera_position}
- High-angle overview; entire monument body stays fully visible (no cropping top/base/sides)
- Horizon level; frame upright; no dutch angle; no orbital drift
- Background sky/landmarks frozen — only site activity and structure change

━━━ PHYSICS ━━━
- Forward-only narrative: continuous build toward END frame
- No instant pop-in; changes read as assembly, repair, and staged installation
- No logos, no readable text, no brand names on equipment

STYLE: Photorealistic, cinematic, vertical 9:16, natural daylight, busy authentic worksite.
AUDIO (if implied): construction ambience only — no music, no voice.
"""


async def _llm_enrich_video_prompt(base_prompt: str, structure_name: str) -> str:
    try:
        llm = make_llm(temperature=0.3)
        msg = [
            SystemMessage(content="You create concise, physically-consistent keyframe video prompts."),
            HumanMessage(
                content=(
                    f"Enhance this keyframe transition prompt for {structure_name}. "
                    "Keep fixed camera and realistic construction/reassembly physics (workers, staging, materials). "
                    "Return only final prompt text.\n\n"
                    f"{base_prompt}"
                )
            ),
        ]
        resp = await asyncio.wait_for(llm.ainvoke(msg), timeout=20.0)
        text = resp.content.strip() if hasattr(resp, "content") else str(resp).strip()
        return text or base_prompt
    except Exception:
        return base_prompt


def _anchor_reference_suffix(index: int) -> str:
    """FastGen uses stage_000 as img2img anchor; without strict wording the model often 'heals' ruins."""
    if index <= 0:
        return ""
    return """

ANCHOR REFERENCE (mandatory when a reference image is attached):
- The reference is ONLY the fully complete monument (first frame, stage_000) for camera, lens, framing, lighting, scale, and background.
- Your output MUST show STRICTLY MORE destruction/decay/collapse than that reference — never equal or “cleaner”.
- FORBIDDEN: repair, restoration, reconstruction, rebuilding, new masonry, repointing, cleaning weathering away,
  construction crews, cranes adding structure, or scaffolding that restores form.
- If in doubt, increase rubble, loss of mass, and structural damage — never improve condition.
"""


async def _generate_single_reference_image(
    scene: dict[str, Any],
    index: int,
    total: int,
    output_dir: Path,
    reference_images: list[str] | None = None,
    prompt_override: str | None = None,
    scenario: dict[str, Any] | None = None,
) -> str:
    prompt = prompt_override or _build_image_prompt(scene, index, total, scenario=scenario)
    structure_name = scene.get("structure_name_en") or scene.get("structure_name") or "monument"
    if not prompt_override:
        prompt = await _llm_enrich_image_prompt(prompt, structure_name)
    if reference_images and index > 0:
        prompt = f"{prompt}{_anchor_reference_suffix(index)}"
    retries = 2
    for attempt in range(retries + 1):
        try:
            refs = [Path(p) for p in (reference_images or []) if p]
            prompts_with_refs = [(prompt, refs)]
            image_paths = await generate_images_with_references_fastgen(
                prompts_with_refs=prompts_with_refs,
                output_dir=output_dir,
                parallel=False,
            )
            if image_paths and image_paths[0] and Path(image_paths[0]).exists():
                src = Path(image_paths[0])
                dst = output_dir / f"stage_{index:03d}_ref.png"
                if src != dst:
                    src.rename(dst)
                return str(dst)
        except Exception as e:
            logger.warning(f"[Mode11] Image {index + 1} generation attempt {attempt + 1} failed: {e}")
        if attempt < retries:
            await asyncio.sleep(2**attempt)
    return ""


async def _generate_keyframe_video(
    index: int,
    start_img: str,
    end_img: str,
    start_scene: dict[str, Any],
    end_scene: dict[str, Any],
    output_dir: Path,
    scenario: dict[str, Any],
    reconstruction_mode: bool = False,
    prompt_override: str | None = None,
    transition_profile: dict[str, Any] | None = None,
) -> str | None:
    structure_name = start_scene.get("structure_name_en") or start_scene.get("structure_name") or "monument"
    prompt = prompt_override or _build_keyframe_prompt(
        start_scene,
        end_scene,
        scenario,
        transition_profile=transition_profile,
        reconstruction_mode=reconstruction_mode,
    )
    if not prompt_override:
        prompt = await _llm_enrich_video_prompt(prompt, structure_name)
    retries = 2
    for attempt in range(retries + 1):
        try:
            result = await generate_video_from_keyframes(
                prompt=prompt,
                output_dir=output_dir,
                start_frame_path=Path(start_img),
                end_frame_path=Path(end_img),
                index=index,
            )
            if result and Path(result).exists():
                return str(Path(result).resolve())
        except Exception as e:
            logger.warning(f"[Mode11] Keyframe {index + 1} attempt {attempt + 1} failed: {e}")
        if attempt < retries:
            await asyncio.sleep(2**attempt)

    # Fallback for unstable keyframe mode
    try:
        fallback = await generate_single_video_multi_ref(
            index=index,
            prompt=prompt,
            output_dir=output_dir,
            reference_image_paths=[Path(start_img), Path(end_img)],
        )
        if fallback and Path(fallback).exists():
            return str(Path(fallback).resolve())
    except Exception as e:
        logger.error(f"[Mode11] Fallback failed for keyframe {index + 1}: {e}")
    return None


async def generate_monument_videos(
    scenario: dict[str, Any],
    output_dir: Path,
    session_id: str,
    language: str = "ru",
    use_contextual: bool = True,
    generate_preview: bool = True,
) -> tuple[list[str], dict[str, Any]]:
    scenes = scenario.get("scenes", [])
    if len(scenes) < 2:
        raise ValueError("[Mode11] Scenario must contain at least 2 scenes")
    fastgen_key = getattr(settings, "fastgen_api_key", "") or ""
    if not fastgen_key:
        raise RuntimeError("FASTGEN_API_KEY not set — required for Mode 11")

    output_dir.mkdir(parents=True, exist_ok=True)
    refs_dir = output_dir / "reference_images"
    refs_dir.mkdir(parents=True, exist_ok=True)

    image_paths: list[str] = []
    anchor_ref: str | None = None
    contextual_data: dict[str, Any] | None = None
    if use_contextual:
        try:
            contextual_data = await generate_contextual_prompts(scenario=scenario, language="en")
        except Exception as e:
            logger.warning(f"[Mode11] Contextual prompts failed, fallback to local LLM enrich: {e}")
            contextual_data = None

    for i, scene in enumerate(scenes):
        scene["structure_name"] = scenario.get("structure_name")
        scene["structure_name_en"] = scenario.get("structure_name_en")
        scene["camera_position_en"] = scenario.get("camera_position_en")
        logger.info(f"[Mode11] Generating reference image {i + 1}/{len(scenes)}...")
        prompt_override = None
        if contextual_data and i < len(contextual_data.get("image_prompts", [])):
            prompt_override = contextual_data["image_prompts"][i].get("prompt_text")
        # Chain previous frame as img2img ref: models often "beautify" ruins back toward intact.
        # Use only stage_000 (complete) as anchor for stages 1..N so each edit degrades from the same baseline.
        ref_list = [anchor_ref] if (i > 0 and anchor_ref) else None
        img = await _generate_single_reference_image(
            scene=scene,
            index=i,
            total=len(scenes),
            output_dir=refs_dir,
            reference_images=ref_list,
            prompt_override=prompt_override,
            scenario=scenario,
        )
        image_paths.append(img)
        if i == 0 and img:
            anchor_ref = img

    # Images are generated in reverse timeline (complete -> empty),
    # but videos must play forward (empty -> complete).
    transition_profiles: list[dict[str, Any]] = list(scenario.get("transition_profiles") or [])
    if not transition_profiles and scenario.get("structure_type"):
        stage_sequence = [s.get("stage_key") for s in scenes if s.get("stage_key")]
        transition_profiles = build_transition_profiles(
            str(scenario["structure_type"]),
            stage_sequence=stage_sequence or None,
        )

    transition_map: list[tuple[int, int]] = []
    video_specs: list[
        tuple[int, str, str, dict[str, Any], dict[str, Any], str | None, dict[str, Any] | None]
    ] = []
    transition_count = len(image_paths) - 1
    for out_idx, start_idx in enumerate(range(len(image_paths) - 1, 0, -1)):
        if not image_paths[start_idx] or not image_paths[start_idx - 1]:
            logger.warning(f"[Mode11] Skipping transition {out_idx + 1}: missing reference image path")
            continue
        if not Path(image_paths[start_idx]).exists() or not Path(image_paths[start_idx - 1]).exists():
            logger.warning(f"[Mode11] Skipping transition {out_idx + 1}: reference image file not found")
            continue
        video_prompt_override = None
        if contextual_data and out_idx < len(contextual_data.get("video_prompts", [])):
            video_prompt_override = contextual_data["video_prompts"][out_idx].get("prompt_text")
        prof = transition_profiles[out_idx] if out_idx < len(transition_profiles) else None
        transition_map.append((out_idx, start_idx))
        video_specs.append(
            (
                out_idx,
                image_paths[start_idx],
                image_paths[start_idx - 1],
                scenes[start_idx],
                scenes[start_idx - 1],
                video_prompt_override,
                prof,
            )
        )

    max_fg = max(1, int(getattr(settings, "fastgen_video_parallel_workers", 10)))
    parallel_workers = min(len(video_specs), max_fg) if video_specs else 1
    logger.info(
        f"[Mode11] Keyframe clips: {len(video_specs)}/{transition_count} scheduled "
        f"(up to {parallel_workers} parallel FastGen browser workers)"
    )
    semaphore = asyncio.Semaphore(parallel_workers)

    async def _run_spec(
        spec: tuple[int, str, str, dict[str, Any], dict[str, Any], str | None, dict[str, Any] | None],
    ) -> str | None:
        out_idx, start_img, end_img, start_scene, end_scene, prompt_override, tprof = spec
        async with semaphore:
            return await _generate_keyframe_video(
                index=out_idx,
                start_img=start_img,
                end_img=end_img,
                start_scene=start_scene,
                end_scene=end_scene,
                output_dir=output_dir,
                scenario=scenario,
                reconstruction_mode=True,
                prompt_override=prompt_override,
                transition_profile=tprof,
            )

    results = await asyncio.gather(*[_run_spec(spec) for spec in video_specs], return_exceptions=True) if video_specs else []
    videos: list[str] = []
    transition_results: dict[int, str | None] = {}
    for i, result in enumerate(results):
        out_idx = video_specs[i][0] if i < len(video_specs) else i
        if isinstance(result, Exception):
            logger.error(f"[Mode11] Keyframe video {out_idx + 1} failed: {result}")
            transition_results[out_idx] = None
            continue
        if result:
            videos.append(result)
            transition_results[out_idx] = result
        else:
            transition_results[out_idx] = None

    # Validate and regenerate problematic clips
    bad_indices = []
    for out_idx, path in transition_results.items():
        if not path or not _is_video_valid(Path(path), min_duration=2.0):
            bad_indices.append(out_idx)

    if bad_indices:
        logger.warning(f"[Mode11] Found {len(bad_indices)} problematic clip(s), trying regen (parallel)...")

        async def _regen_one(out_idx: int) -> None:
            mapping = [m for m in transition_map if m[0] == out_idx]
            if not mapping:
                return
            start_idx = mapping[0][1]
            start_img = image_paths[start_idx]
            end_img = image_paths[start_idx - 1]
            if not start_img or not end_img:
                return
            if not Path(start_img).exists() or not Path(end_img).exists():
                return

            video_prompt_override = None
            if contextual_data and out_idx < len(contextual_data.get("video_prompts", [])):
                video_prompt_override = contextual_data["video_prompts"][out_idx].get("prompt_text")

            tprof = transition_profiles[out_idx] if out_idx < len(transition_profiles) else None

            async with semaphore:
                try:
                    regen = await _generate_keyframe_video(
                        index=out_idx,
                        start_img=start_img,
                        end_img=end_img,
                        start_scene=scenes[start_idx],
                        end_scene=scenes[start_idx - 1],
                        output_dir=output_dir,
                        scenario=scenario,
                        reconstruction_mode=True,
                        prompt_override=video_prompt_override,
                        transition_profile=tprof,
                    )
                    if regen and _is_video_valid(Path(regen), min_duration=2.0):
                        transition_results[out_idx] = regen
                        logger.success(f"[Mode11] Regen successful for clip {out_idx + 1}")
                    else:
                        logger.error(f"[Mode11] Regen failed for clip {out_idx + 1}")
                except Exception as e:
                    logger.error(f"[Mode11] Regen error for clip {out_idx + 1}: {e}")

        await asyncio.gather(*[_regen_one(oid) for oid in bad_indices], return_exceptions=True)

    # Rebuild ordered video list by transition index
    videos = []
    for out_idx in sorted(transition_results.keys()):
        p = transition_results[out_idx]
        if p and Path(p).exists():
            videos.append(p)

    # Normalize clips for stable downstream stitching/playback
    normalized_videos: list[str] = []
    for p in videos:
        norm = await _normalize_video(Path(p), output_dir)
        normalized_videos.append(str(norm if norm else Path(p)))

    enriched = dict(scenario)
    enriched["reference_images"] = image_paths
    if generate_preview and image_paths:
        preview_dir = output_dir / "previews"
        preview_path = await generate_clickbait_preview(
            final_frame_path=Path(image_paths[0]),
            scenario={
                "house_style_name": scenario.get("structure_name_en", "monument"),
                "location_name": scenario.get("location_name", "historic location"),
            },
            output_dir=preview_dir,
            mode="house",
            style_key="dramatic_reveal",
            language="en" if language == "en" else "ru",
        )
        if preview_path:
            enriched["preview_path"] = str(preview_path)
    return normalized_videos, enriched
