"""
Несколько клипов FastGen с одним набором референсов (цитата / multiclip).
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from loguru import logger

from agents.content_generator.fastgen_scraper import generate_single_video_fastgen
from config import settings
from modes.mode4.quote_format import strip_quotes_for_voice

_STYLE_SUFFIX = (
    ", 9:16 portrait, photorealistic, no AI artifacts, ~8 second take, "
    "cinematic feature-film quality: richly detailed multi-layer background (foreground, midground, distant depth), "
    "readable environment tied to the parable, volumetric light and atmospheric haze, textured stone and earth, "
    "not a flat or empty backdrop; the opening moment must have an immediate visual hook through silhouette, foreground shape, weather, light shaft, or architectural depth; "
    "living world - subtle ambient motion in the environment that matches the story "
    "(wind in leaves or fabric, drifting dust or incense in light beams, soft water shimmer, "
    "distant tiny figures or birds, slow cloud drift, light flicker on stone); "
    "no static matte-painting look, no empty void; camera steady or imperceptibly slow; "
    "continuous storytelling - no long silence at the very start or end of the clip, "
    "speech begins almost immediately and stays present; quiet natural ambience only"
)

_LIVING_BACKGROUND_BLOCK = (
    "The setting must feel alive and story-driven, not a frozen postcard: "
    "keep the same locked location and the same memorable anchor details, but show gentle natural motion in midground and background "
    "appropriate to this parable (breeze, smoke, water, distant life, particles in light). "
    "Do not add a new location or crowd close to camera; no chaotic background cuts. "
)

_LOCATION_REF_BLOCK = (
    "Reference images: image 1 = this speaker's exact face, hair, beard, and clothing (match precisely). "
    "Image 2 = the LOCKED location plate - keep the SAME stones, paths, soil, plants, walls or architecture, "
    "horizon line, sky, and light direction as in that plate; composite this person only into that exact world. "
    "Do not swap to a different road, hillside, gate, or shoreline between clips - visual continuity is anchored to image 2. Preserve the same dominant composition, horizon, and anchor props. "
)

_TEXT_ONLY_LOCATION_HINT = (
    "Honor the master scene's single parable location in every frame - one coherent place, no random backdrop swaps. "
)

_JESUS_CHRIST_RE = re.compile(
    r"\bJesus\s+Christ\b|\bJesus\b|\bChrist\b",
    flags=re.IGNORECASE,
)
_RU_JESUS = re.compile(
    r"\bИисус(?:а|у|ом|е)?\s+Христос(?:а|у|ом|е)?\b|\bИисус(?:а|у|ом|е)?\b|\bХристос(?:а|у|ом|е)?\b",
    flags=re.IGNORECASE,
)


def _sanitize_fastgen_no_proper_name(text: str) -> str:
    """Заменить религиозные имена на нейтральные формулировки."""
    if not text:
        return text
    t = _JESUS_CHRIST_RE.sub("the central speaker", text)
    t = _RU_JESUS.sub("центральный говорящий", t)
    return t


def build_fragment_prompt(
    master_scene_en: str,
    segment_text: str,
    voice_description: str,
    fragment_index: int,
    num_fragments: int,
    speech_lang: str = "ru",
    *,
    has_location_reference: bool = False,
) -> str:
    seg_voice = strip_quotes_for_voice((segment_text or "").strip())
    voice = _sanitize_fastgen_no_proper_name((voice_description or "").strip())
    base = _sanitize_fastgen_no_proper_name((master_scene_en or "").strip().rstrip(".,; "))
    lang = (speech_lang or "ru").lower()
    tail = (seg_voice or "").rstrip()
    has_terminal = bool(tail) and tail[-1] in ".!?…"
    flow_hint = (
        " The line may be a mid-sentence clause (not ending with . ? ! ...): speak it without inserting "
        "an oral full stop or long end-of-sentence pause; flow naturally into the idea continuing in other clips."
        if not has_terminal
        else " End with natural closure only if the line ends with sentence-final punctuation."
    )
    if lang.startswith("en"):
        dialogue_priority = (
            "PRIMARY SPOKEN LINE (English) - The speaker shown in reference image 1 must say ONLY this, "
            "word-for-word, in clear speech: "
            f"{seg_voice} "
            "Rules: no paraphrase, no synonym swap, no summary, no extra spoken sentences, no skipping words, "
            "no translation to another language; lip-sync and audio must match this exact text. "
        )
        delivery_mid = (
            f"Segment {fragment_index + 1} of {num_fragments} of one continuous parable - same story breath, not a new episode. "
            f"Speak slowly and clearly in English; start this line within the first fraction of a second; "
            f"no long silence before or after.{flow_hint} "
        )
    else:
        dialogue_priority = (
            "PRIMARY SPOKEN LINE (Russian) - The speaker shown in reference image 1 must say ONLY this, "
            "word-for-word, in clear Russian speech: "
            f"{seg_voice} "
            "Rules: no paraphrase, no synonym swap, no summary, no extra spoken sentences, no skipping words, "
            "do not switch to English; lip-sync and audio must match this exact text. "
        )
        delivery_mid = (
            f"Segment {fragment_index + 1} of {num_fragments} of one continuous parable - same story breath, not a new episode. "
            f"Speak slowly and clearly in Russian; start this line within the first fraction of a second; "
            f"no long silence before or after.{flow_hint} "
        )
    dialogue_repeat = f" FINAL AUDIO CHECK - spoken words must be exactly: {seg_voice}"

    loc_lock = _LOCATION_REF_BLOCK if has_location_reference else _TEXT_ONLY_LOCATION_HINT
    block = (
        f"{dialogue_priority}"
        f"{base}. "
        f"{loc_lock}"
        "IDENTICAL wardrobe, face, hair, and the SAME richly detailed story-specific environment as in all other parts - "
        "same era, same parable setting: keep foreground props, midground architecture or nature, and distant skyline "
        "fully rendered and cinematic (depth, texture, motivated light); preserve the same visual hook and the same anchor details from clip to clip; never replace with a plain, flat, or studio void. "
        "Do not change clothing. "
        f"{_LIVING_BACKGROUND_BLOCK}"
        f"{delivery_mid}"
        "Subtle natural gestures only; steady or very slow cinematic camera; soft natural sound; the frame should feel premium, dramatic, and instantly readable in the first second; "
        "no on-screen text, no captions."
    )
    if voice and len(voice) > 10:
        block += f" Voice and delivery: {voice}"
    return block + dialogue_repeat + _STYLE_SUFFIX


async def generate_parable_clips(
    prompts: list[str],
    output_dir: Path,
    reference_paths: list[Path],
    cancel_event=None,
) -> list[Path | None]:
    """Параллельная генерация клипов, каждый в своем браузере FastGen."""
    refs = [p.resolve() for p in reference_paths if p and Path(p).exists()]
    if not refs:
        raise FileNotFoundError("Multiclip: need at least one reference image")
    n = len(prompts)
    if n == 0:
        return []
    workers = min(n, max(1, int(getattr(settings, "fastgen_video_parallel_workers", 10))))
    clip_retries = 2
    logger.info(f"[Multiclip FG] {n} clips parallel (≤{workers} at once), refs={len(refs)}")

    sem = asyncio.Semaphore(workers)

    async def gen_one(i: int, full_prompt: str) -> Path | None:
        async with sem:
            path = None
            for retry in range(clip_retries + 1):
                path = await generate_single_video_fastgen(
                    full_prompt,
                    output_dir,
                    i,
                    reference_image_path=None,
                    reference_image_paths=refs,
                    cancel_event=cancel_event,
                    mode4_veo_flow_flower=True,
                )
                if path and Path(path).exists():
                    logger.info(f"[Multiclip FG] Clip {i + 1}/{n} done")
                    break
                if retry < clip_retries:
                    logger.warning(f"[Multiclip FG] Clip {i} retry {retry + 2}/{clip_retries + 1}")
            if not path or not Path(path).exists():
                logger.error(f"[Multiclip FG] Clip {i} failed")
            return path

    return list(await asyncio.gather(*[gen_one(i, p) for i, p in enumerate(prompts)]))


async def regenerate_parable_clip(
    full_prompt: str,
    output_dir: Path,
    index: int,
    reference_paths: list[Path],
    cancel_event=None,
) -> Path | None:
    """Один клип по готовому промпту."""
    refs = [p.resolve() for p in reference_paths if p and Path(p).exists()]
    if not refs:
        raise FileNotFoundError("Multiclip: need at least one reference image")
    clip_retries = 2
    path = None
    for retry in range(clip_retries + 1):
        path = await generate_single_video_fastgen(
            full_prompt,
            output_dir,
            index,
            reference_image_path=None,
            reference_image_paths=refs,
            cancel_event=cancel_event,
            mode4_veo_flow_flower=True,
        )
        if path and Path(path).exists():
            break
        if retry < clip_retries:
            logger.warning(f"[Multiclip FG] Regenerate clip {index} retry {retry + 2}/{clip_retries + 1}")
    return path if path and Path(path).exists() else None
