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
from modes.mode3.constants import NUM_RESTORATION_CLIPS, mode3_blueprint_lock

# Референсные картинки — целевые кадры. Видео должно стремиться к ним.
_FIRST_CLIP_PREFIX = (
    "CRITICAL: Reference = EXACT target frame. First second = reference PIXEL-PERFECT. "
    "FROZEN: roof shape, window count and positions, door, building footprint — NEVER change. "
    "Same house in ALL clips. Do NOT redesign. Copy reference structure. "
)

# Для фрагментов 2+ — референс задаёт целевое состояние того же дома
_REFERENCE_PREFIX = (
    "CRITICAL: Reference = previous clip's last frame. FIRST FRAME = reference EXACTLY — seamless continuity. "
    "THIS IS THE SAME HOUSE. Preserve: roof form, window positions, door, layout. "
    "Change ONLY: restoration progress. Do NOT create a different building. "
)

# Для финального showcase (clip 4)
_LAST_CLIP_SUFFIX = (
    " CRITICAL: FINAL showcase — match BOTH uploaded references. "
    "No workers, no construction. Exterior shots = ref 1 exactly; interior shots = ref 2 exactly (same room as renovation clips). "
    "Photorealistic, sharp focus, magazine-cover quality. "
)

# Экстерьер
_STYLE_SUFFIX = (
    ", first frame = reference PIXEL-PERFECT — identical building. "
    "FROZEN: roof, windows, door — ZERO structural change. Only restoration details evolve. "
    "EVEN PACE, workers active, cinematic 4K photorealistic, vertical 9:16 portrait"
)

# Интерьер — рабочие и таймлапс как снаружи
_INTERIOR_STYLE = (
    ", first frame = reference EXACTLY — same room, same window/door positions. "
    "WORKERS INSIDE: restoration work — carrying materials, painting, fixing. "
    "FROZEN: ONE room, studio — layout NEVER changes. TIME-LAPSE: fast pace. "
    "EVEN PACE, cinematic 4K photorealistic, vertical 9:16 portrait"
)

# Интро — может быть панорама
_INTRO_STYLE = (
    ", first frame = reference exactly, "
    "cinematic 4K photorealistic, vertical 9:16 portrait, smooth camera movement"
)

# Финальный showcase — два «идеальных» still (снаружи + внутри), не обязательно последний кадр видео
_SHOWCASE_STYLE = (
    ", TWO REFERENCE IMAGES = master shots of FINISHED house: (1) ideal EXTERIOR still — match all outside shots. "
    "(2) ideal INTERIOR still — match inside exactly (same room, walls, furniture). "
    "Same building. No workers. Sharp focus, photorealistic, cinematic 4K, vertical 9:16 portrait"
)

# Второй референс = целевой «готовый» кадр из цепочки изображений (ext_final / int_final)
_DUAL_REF_EXTERIOR = (
    " TWO REFERENCES: (1) start frame = continuity from previous clip. "
    "(2) TARGET = fully finished exterior — final seconds must match ref 2: complete paint, all windows glazed, door finished, yard clean, NO scaffolding, NO workers, renovation DONE. "
)

_DUAL_REF_INTERIOR = (
    " TWO REFERENCES: (1) start frame = continuity. "
    "(2) TARGET = fully finished interior — final seconds must match ref 2: painted walls, finished floor, furniture, lighting, NO workers, room COMPLETE magazine-ready. "
)

# Три референса: скриншот разрушенного интерьера из клипа 1 → полу-готовый → готовый (img2img от скрина)
_TRIPLE_REF_INTERIOR = (
    " THREE REFERENCES in upload order: "
    "(1) RUINED interior = first frame EXACTLY — same room as end of clip 1. "
    "(2) TARGET semi-restored — timelapse progresses toward ref 2, same layout. "
    "(3) TARGET fully finished — final seconds match ref 3: complete paint, floor, furniture, lighting, NO workers. "
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
    completion_targets: dict[int, Path] | None = None,
    interior_from_intro_prompts: tuple[str, str] | None = None,
    house_blueprint: str = "",
    cancel_event=None,
) -> list[Path | None]:
    """
    Генерирует 5 видео. Ref chain:
    - Clip 0: intro. Последний кадр → скрин разрушенного интерьера; от него img2img: полу- и полностью готовый интерьер для клипа 4.
    - Clips 1–2: exterior; clip 2 может иметь 2 рефа: последний кадр clip 1 + ext_final.
    - Clip 3: интерьер — 3 рефа (скрин + mid + final из img2img) или 2 рефа (цепочка + int_final still).
    - Clip 4: два скриншота — экстерьер + интерьер (последние кадры или still).
    completion_targets: {2: ext_final, 3: int_final} из stills (режим topic).
    interior_from_intro_prompts: (mid_prompt, final_prompt) для img2img после клипа 1.
    house_blueprint: повтор STRUCTURE_ID в начале каждого видеопромпта.
    """
    if len(video_prompts) != NUM_RESTORATION_CLIPS:
        raise ValueError(f"Expected {NUM_RESTORATION_CLIPS} prompts, got {len(video_prompts)}")

    fastgen_key = getattr(settings, "fastgen_api_key", "") or ""
    if not fastgen_key:
        raise RuntimeError("FASTGEN_API_KEY not set — required for Mode 3")

    ref_dir = output_dir / "refs"
    ref_dir.mkdir(parents=True, exist_ok=True)
    overrides = ref_overrides or {}
    targets = completion_targets or {}

    current_ref = Path(reference_image_path)
    if not current_ref.exists():
        raise FileNotFoundError(f"Reference image not found: {reference_image_path}")

    paths: list[Path | None] = []
    built_prompts: list[str] = []
    bp_video = mode3_blueprint_lock(house_blueprint) if (house_blueprint or "").strip() else ""
    for i, p in enumerate(video_prompts):
        stem = bp_video + p.rstrip(" .,")
        if i == 0:
            base = stem + _INTRO_STYLE
        elif i == 4:
            base = stem + _SHOWCASE_STYLE
        elif i == 3:
            base = stem + _INTERIOR_STYLE
        else:
            base = stem + _STYLE_SUFFIX
        base = (_FIRST_CLIP_PREFIX if i in (0, 1, 4) else _REFERENCE_PREFIX) + base
        if i == NUM_RESTORATION_CLIPS - 1:
            base = base + _LAST_CLIP_SUFFIX
        built_prompts.append(base)

    logger.info(f"[Mode3 Video] Generating {NUM_RESTORATION_CLIPS} clips")

    clip_retries = 2
    ref_from_intro: Path | None = None
    ref_from_clip_2: Path | None = None
    ref_from_clip_3: Path | None = None
    int_mid_from_intro: Path | None = None
    int_final_from_intro: Path | None = None

    for i in range(NUM_RESTORATION_CLIPS):
        # Clip 5: приоритет последнему кадру clip 2 (не ext_final из overrides — иначе рвётся связь с видео)
        if i == 4 and ref_from_clip_2 is not None:
            current_ref = ref_from_clip_2
            logger.info(f"[Mode3 Video] Clip 5 primary ref = last frame clip 2 ({current_ref.name})")
        elif i == 4 and 2 in targets and Path(targets[2]).exists():
            current_ref = Path(targets[2])
            logger.warning("[Mode3 Video] Clip 5: no clip-2 last frame, fallback ext_final still")
        elif i == 4 and 4 in overrides:
            current_ref = overrides[4]
        elif (
            i == 3
            and int_mid_from_intro is not None
            and int_final_from_intro is not None
            and Path(int_mid_from_intro).exists()
            and Path(int_final_from_intro).exists()
            and ref_from_intro is not None
            and Path(ref_from_intro).exists()
        ):
            current_ref = ref_from_intro
            logger.info("[Mode3 Video] Clip 4: primary ref = intro last frame + img2img mid/final")
        elif i in overrides:
            current_ref = overrides[i]
        elif i == 3 and ref_from_intro is not None:
            current_ref = ref_from_intro
        if not current_ref.exists():
            raise FileNotFoundError(f"[Mode3 Video] Ref for clip {i} not found: {current_ref}")

        use_intro_interior_chain = (
            i == 3
            and ref_from_intro is not None
            and int_mid_from_intro is not None
            and int_final_from_intro is not None
            and Path(ref_from_intro).exists()
            and Path(int_mid_from_intro).exists()
            and Path(int_final_from_intro).exists()
        )

        # Промпт: усиление для двух/трёх референсов
        clip_prompt = built_prompts[i]
        if i == 2 and i in targets and Path(targets[i]).exists():
            clip_prompt = clip_prompt + _DUAL_REF_EXTERIOR
        if use_intro_interior_chain:
            clip_prompt = clip_prompt + _TRIPLE_REF_INTERIOR
        elif i == 3 and i in targets and Path(targets[i]).exists():
            clip_prompt = clip_prompt + _DUAL_REF_INTERIOR

        ref_paths_multi: list[Path] | None = None
        if i == 2 and i in targets and Path(targets[i]).exists():
            ref_paths_multi = [current_ref, Path(targets[i])]
            logger.info(f"[Mode3 Video] Clip 3: dual ref — chain + ext_final ({targets[i].name})")
        elif use_intro_interior_chain:
            ref_paths_multi = [
                Path(ref_from_intro),
                Path(int_mid_from_intro),
                Path(int_final_from_intro),
            ]
            logger.info(
                "[Mode3 Video] Clip 4: triple ref — intro screenshot + img2img mid + img2img final"
            )
        elif i == 3 and i in targets and Path(targets[i]).exists():
            ref_paths_multi = [current_ref, Path(targets[i])]
            logger.info(f"[Mode3 Video] Clip 4: dual ref — chain + int_final ({targets[i].name})")
        elif i == 4:
            # Приоритет: готовый экстерьер still + готовый интерьер still (как просили: идеал снаружи и внутри)
            ext_ideal = Path(targets[2]) if 2 in targets and Path(targets[2]).exists() else None
            int_ideal = None
            if int_final_from_intro and int_final_from_intro.exists():
                int_ideal = int_final_from_intro
            elif 3 in targets and Path(targets[3]).exists():
                int_ideal = Path(targets[3])
            if ext_ideal and int_ideal:
                ref_paths_multi = [ext_ideal, int_ideal]
                logger.info(
                    f"[Mode3 Video] Clip 5: ideal stills — ext {ext_ideal.name}, int {int_ideal.name}"
                )
            else:
                pair: list[Path] = []
                if ref_from_clip_2 and ref_from_clip_2.exists():
                    pair.append(ref_from_clip_2)
                if ref_from_clip_3 and ref_from_clip_3.exists():
                    pair.append(ref_from_clip_3)
                elif int_final_from_intro and int_final_from_intro.exists():
                    pair.append(int_final_from_intro)
                elif 3 in targets and Path(targets[3]).exists():
                    pair.append(Path(targets[3]))
                if len(pair) >= 2:
                    ref_paths_multi = pair
                    logger.info(
                        f"[Mode3 Video] Clip 5: fallback video last frames — {pair[0].name}, {pair[1].name}"
                    )
                elif len(pair) == 1 and int_ideal:
                    ref_paths_multi = [pair[0], int_ideal]
                    logger.info("[Mode3 Video] Clip 5: one video frame + int ideal still")
                elif len(pair) == 1 and ext_ideal:
                    ref_paths_multi = [ext_ideal, pair[0]]
                    logger.info("[Mode3 Video] Clip 5: ext ideal still + one video frame")
                elif len(pair) == 1 and 3 in targets and Path(targets[3]).exists():
                    ref_paths_multi = [pair[0], Path(targets[3])]
                    logger.info("[Mode3 Video] Clip 5: fallback int = int_final still")

        log_ref = ref_paths_multi[0].name if ref_paths_multi else current_ref.name
        logger.info(f"[Mode3 Video] Generating clip {i + 1}/{NUM_RESTORATION_CLIPS} (ref: {log_ref}{'…' if ref_paths_multi and len(ref_paths_multi) > 1 else ''}) ...")
        path = None
        for retry in range(clip_retries + 1):
            if ref_paths_multi:
                path = await generate_single_video_fastgen(
                    clip_prompt, output_dir, i,
                    reference_image_path=None,
                    reference_image_paths=ref_paths_multi,
                    cancel_event=cancel_event,
                )
            else:
                path = await generate_single_video_fastgen(
                    clip_prompt, output_dir, i, current_ref, cancel_event=cancel_event
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
            if (
                ref_from_intro
                and interior_from_intro_prompts
                and Path(ref_from_intro).exists()
            ):
                mid_p, fin_p = interior_from_intro_prompts
                intro_img_dir = ref_dir / "intro_interior_img2img"
                intro_img_dir.mkdir(parents=True, exist_ok=True)
                try:
                    from agents.content_generator.fastgen_scraper import (
                        generate_images_chain_from_seed_fastgen,
                    )

                    gen = await generate_images_chain_from_seed_fastgen(
                        ref_from_intro,
                        [(mid_p, 0), (fin_p, 1)],
                        intro_img_dir,
                        cancel_event=cancel_event,
                    )
                    if len(gen) >= 2:
                        int_mid_from_intro = Path(gen[0])
                        int_final_from_intro = Path(gen[1])
                        logger.success(
                            f"[Mode3 Video] Intro interior img2img: {int_mid_from_intro.name} → {int_final_from_intro.name}"
                        )
                except Exception as e:
                    logger.warning(
                        f"[Mode3 Video] Intro interior img2img chain failed (fallback to stills): {e}"
                    )
        elif i == 2:
            ref_from_clip_2 = next_ref
            logger.info(f"[Mode3 Video] Saved last frame clip 2 → {next_ref.name} (showcase ext)")
        elif i == 3:
            ref_from_clip_3 = next_ref
            logger.info(f"[Mode3 Video] Saved last frame clip 3 → {next_ref.name} (showcase int)")
        current_ref = next_ref

    return paths
