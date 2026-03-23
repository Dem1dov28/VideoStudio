"""
Mode 3 Video Generator — 5 видео для минимизации дрейфа.

Clip 0: intro (ruined exterior → interior)
Clip 1: exterior prep + roof (ref = before)
Clip 2: exterior windows + finish → скриншот для clip 4
Clip 3: interior (ref = intro last frame)
Clip 4: showcase (ref = скриншот clip 2)
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from agents.content_generator.fastgen_scraper import generate_single_video_fastgen
from config import settings
from modes.mode3.constants import NUM_RESTORATION_CLIPS

# Для вступительного и первых клипов
_FIRST_CLIP_PREFIX = (
    "CRITICAL: Reference = your STARTING FRAME. First second = reference EXACTLY. "
    "Same building in reference = same building in your video. Do NOT redesign. "
)

# Для фрагментов 2+ — последний кадр предыдущего
_REFERENCE_PREFIX = (
    "CRITICAL: Reference = last frame of previous clip. FIRST FRAME = reference EXACTLY. "
    "This is a CONTINUATION — same house, same camera angle. Building MUST be identical to reference. "
    "Do NOT create a different house. Preserve roof, windows, door from reference. "
)

# Для финального showcase (clip 4)
_LAST_CLIP_SUFFIX = (
    " CRITICAL: This is the FINAL clip — showcase of the completed restoration. "
    "No workers, no construction. Show EVERY detail: exterior (roof, walls, windows, door, yard) then interior (ceiling, walls, floor, furniture, trim). "
    "Photorealistic, sharp focus, magazine-cover quality. "
)

# Экстерьер
_STYLE_SUFFIX = (
    ", first frame = reference EXACTLY — same building, same proportions, "
    "FROZEN: roof form, window positions, door — NEVER change. Same house in every frame. "
    "EVEN PACE, workers active, cinematic 4K photorealistic, vertical 9:16 portrait"
)

# Интерьер — рабочие и таймлапс как снаружи
_INTERIOR_STYLE = (
    ", first frame = reference EXACTLY — same room layout, same window/door positions. "
    "WORKERS INSIDE: people doing restoration work — same as exterior. Carrying materials, painting, fixing. "
    "TIME-LAPSE: fast pace, work progresses quickly, materials appear, tools in use. Same feel as exterior restoration. "
    "FROZEN: ONE room, studio — no layout change. EVEN PACE, workers active, cinematic 4K photorealistic, vertical 9:16 portrait"
)

# Интро — может быть панорама
_INTRO_STYLE = (
    ", first frame = reference exactly, "
    "cinematic 4K photorealistic, vertical 9:16 portrait, smooth camera movement"
)

# Финальный showcase — ref = скриншот clip 2, тот же дом
_SHOWCASE_STYLE = (
    ", first frame = reference EXACTLY — this IS the house from clip 3, do NOT change it. "
    "Exterior first (reference), then pan inside — interior is INSIDE this same house. "
    "Same roof, windows, door. ONE room inside. Sharp focus, photorealistic, cinematic 4K, vertical 9:16 portrait"
)


def _extract_last_frame(video_path: Path, output_dir: Path, index: int) -> Path | None:
    """Извлечь последний кадр видео как JPEG для следующего reference."""
    try:
        from moviepy import VideoFileClip

        vc = VideoFileClip(str(video_path))
        frame = vc.get_frame(max(0.0, vc.duration - 0.1))
        vc.close()

        from PIL import Image

        img = Image.fromarray(frame)
        out_path = output_dir / f"ref_{index:03d}.jpg"
        img.save(str(out_path), "JPEG", quality=92)
        logger.info(f"[Mode3] Extracted last frame → {out_path.name}")
        return out_path
    except Exception as e:
        logger.error(f"[Mode3] Failed to extract frame from {video_path}: {e}")
        return None


async def generate_restoration_videos(
    video_prompts: list[str],
    output_dir: Path,
    reference_image_path: str | Path,
    *,
    ref_overrides: dict[int, Path] | None = None,
) -> list[Path | None]:
    """
    Генерирует 5 видео. Ref chain:
    - Clip 0: intro. После → скриншот = ref для clip 3.
    - Clips 1–2: exterior. После clip 2 → скриншот = ref для clip 4.
    - Clip 3: interior, ref = intro last frame.
    - Clip 4: showcase, ref = скриншот clip 2.
    """
    if len(video_prompts) != NUM_RESTORATION_CLIPS:
        raise ValueError(f"Expected {NUM_RESTORATION_CLIPS} prompts, got {len(video_prompts)}")

    fastgen_key = getattr(settings, "fastgen_api_key", "") or ""
    if not fastgen_key:
        raise RuntimeError("FASTGEN_API_KEY not set — required for Mode 3")

    ref_dir = output_dir / "refs"
    ref_dir.mkdir(parents=True, exist_ok=True)
    overrides = ref_overrides or {}

    current_ref = Path(reference_image_path)
    if not current_ref.exists():
        raise FileNotFoundError(f"Reference image not found: {reference_image_path}")

    paths: list[Path | None] = []
    built_prompts: list[str] = []
    for i, p in enumerate(video_prompts):
        if i == 0:
            base = p.rstrip(" .,") + _INTRO_STYLE
        elif i == 4:
            base = p.rstrip(" .,") + _SHOWCASE_STYLE
        elif i == 3:
            base = p.rstrip(" .,") + _INTERIOR_STYLE
        else:
            base = p.rstrip(" .,") + _STYLE_SUFFIX
        base = (_FIRST_CLIP_PREFIX if i in (0, 1, 4) else _REFERENCE_PREFIX) + base
        if i == NUM_RESTORATION_CLIPS - 1:
            base = base + _LAST_CLIP_SUFFIX
        built_prompts.append(base)

    logger.info(f"[Mode3 Video] Generating {NUM_RESTORATION_CLIPS} clips")

    clip_retries = 2
    ref_from_intro: Path | None = None
    ref_from_clip_2: Path | None = None

    for i in range(NUM_RESTORATION_CLIPS):
        if i in overrides:
            current_ref = overrides[i]
        elif i == 3 and ref_from_intro is not None:
            current_ref = ref_from_intro
        elif i == 4:
            if ref_from_clip_2 is not None:
                current_ref = ref_from_clip_2
                logger.info(f"[Mode3 Video] Clip 4 ref = screenshot from clip 2 ({current_ref.name})")
            elif 4 in overrides:
                current_ref = overrides[4]
        if not current_ref.exists():
            raise FileNotFoundError(f"[Mode3 Video] Ref for clip {i} not found: {current_ref}")

        logger.info(f"[Mode3 Video] Generating clip {i + 1}/{NUM_RESTORATION_CLIPS} (ref: {current_ref.name}) ...")
        path = None
        for retry in range(clip_retries + 1):
            path = await generate_single_video_fastgen(
                built_prompts[i], output_dir, i, current_ref
            )
            if path and Path(path).exists():
                break
            if retry < clip_retries:
                logger.warning(f"[Mode3 Video] Clip {i} failed, retry {retry + 2}/{clip_retries + 1} ...")
        paths.append(path)
        if not path or not Path(path).exists():
            logger.warning(f"[Mode3 Video] Clip {i} failed after {clip_retries + 1} attempts, stopping chain")
            break

        next_ref = _extract_last_frame(Path(path), ref_dir, i)
        if not next_ref:
            logger.warning(f"[Mode3 Video] Could not extract frame from clip {i}, stopping chain")
            break
        if i == 0:
            ref_from_intro = next_ref
        elif i == 2:
            ref_from_clip_2 = next_ref
            logger.info(f"[Mode3 Video] Saved screenshot from clip 2 → {next_ref.name} (ref for showcase)")
        current_ref = next_ref

    return paths
