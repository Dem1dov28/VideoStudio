"""
Mode 4 Video Generator — 1 или 2 видеофрагмента с reference image (фото личности).
Несколько фрагментов одной цитаты — параллельная генерация как в режиме 12 (generate_parable_clips).
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from agents.content_generator.fastgen_scraper import (
    generate_single_video_fastgen,
    generate_videos_fastgen,
)
from config import settings

from modes.mode4.quote_format import dashes_to_commas_for_voice, strip_quotes_for_voice

_STYLE_SUFFIX = (
    ", 9:16 portrait, photorealistic, no AI artifacts, "
    "absolutely no on-screen text, no subtitles, no captions, no titles, no lower-thirds, "
    "no burned-in words, no letters, no typography, no logos, no watermark"
)

_QUOTE_FRAGMENT_STYLE = (
    ", 9:16 portrait, photorealistic, no AI artifacts, ~8 second take, "
    "cinematic feature-film quality: richly detailed multi-layer background, "
    "same locked historical scene and wardrobe across all parts of this quotation; "
    "preserve the same 3-5 anchor details of the environment in every clip; "
    "speech begins within the first fraction of a second; no long silence before or after; "
    "steady or very slow camera; the first second must feel visually arresting with an immediate cinematic read of the setting; "
    "absolutely no on-screen text, no subtitles, no captions, "
    "no title cards, no lower-thirds, no burned-in words, no letters, no logos, no watermark"
)

_TEXT_ONLY_SCENE_LOCK = (
    "Honor the master scene's single location in every frame — one coherent place, "
    "no random backdrop swaps; identical era, costume, and environment as in the scene bible. "
)


def build_quote_fragment_prompt(
    master_scene_en: str,
    segment_text: str,
    voice_description: str,
    fragment_index: int,
    num_fragments: int,
    speech_lang: str = "ru",
) -> str:
    """Один клип из серии: та же сцена, что в master_scene_en; озвучка — только segment_text."""
    seg_voice = strip_quotes_for_voice((segment_text or "").strip())
    voice = (voice_description or "").strip()
    base = (master_scene_en or "").strip().rstrip(".,; ")
    lang = (speech_lang or "ru").lower()
    tail = (seg_voice or "").rstrip()
    has_terminal = bool(tail) and tail[-1] in ".!?…"
    flow_hint = (
        " The line may be a mid-sentence clause: speak it without inserting "
        "an oral full stop or long pause at the end; flow naturally into the idea continuing in other clips."
        if not has_terminal
        else " End with natural closure only if the line ends with sentence-final punctuation."
    )
    if lang.startswith("en"):
        dialogue_priority = (
            "PRIMARY SPOKEN LINE (English) — The speaker in reference image 1 must say ONLY this, "
            "word-for-word, in clear speech: "
            f"{seg_voice} "
            "Rules: no paraphrase, no extra sentences, no translation; lip-sync must match this exact text. "
        )
        delivery_mid = (
            f"Segment {fragment_index + 1} of {num_fragments} of one continuous quotation — same scene and breath. "
            f"Speak clearly in English; start quickly; no long silence before or after.{flow_hint} "
        )
        dialogue_repeat = f" FINAL AUDIO CHECK — spoken words must be exactly: {seg_voice}"
    else:
        dialogue_priority = (
            "PRIMARY SPOKEN LINE (Russian) — The speaker in reference image 1 must say ONLY this, "
            "word-for-word, in clear Russian: "
            f"{seg_voice} "
            "Rules: no paraphrase, no extra sentences, do not switch to English; lip-sync must match. "
        )
        delivery_mid = (
            f"Segment {fragment_index + 1} of {num_fragments} of one continuous quotation — same scene and breath. "
            f"Speak clearly in Russian; start quickly; no long silence before or after.{flow_hint} "
        )
        dialogue_repeat = f" FINAL AUDIO CHECK — spoken words must be exactly: {seg_voice}"

    block = (
        f"{dialogue_priority}"
        f"{base}. "
        f"{_TEXT_ONLY_SCENE_LOCK}"
        f"IDENTICAL wardrobe, face, hair, and the same richly detailed environment as in all other parts. "
        "Keep the same visual hook, same dominant background structure, same light direction, and same anchor props. "
        f"Do not change clothing or era. "
        f"{delivery_mid}"
        "Subtle natural gestures only; soft natural sound. Make the image feel premium and scroll-stopping through depth, silhouette, texture, and light rather than gimmicks. "
        "VISUAL CLEAN FRAME RULE: absolutely no text rendered inside the video image - "
        "no subtitles, no captions, no quote text on screen, no title overlays, no lower-thirds, "
        "no letters on walls, no signs, no poster text, no watermark, no logo. "
    )
    if voice and len(voice) > 10:
        block += f" Voice and delivery: {voice}"
    return dashes_to_commas_for_voice(block + dialogue_repeat + _QUOTE_FRAGMENT_STYLE)


def _enrich_prompt(prompt: str, voice_description: str, script: str) -> str:
    """Добавляет голос и цитату только если их ещё нет в промпте (без дублирования)."""
    base = prompt.rstrip(" .,")
    base_lower = base.lower()
    script_clean = (script or "").strip()
    voice_clean = (voice_description or "").strip()

    # Цитата уже в промпте — не дублируем
    if script_clean and len(script_clean) > 10:
        # Проверяем по первым словам (цитата может быть в кавычках)
        snippet = script_clean[:40].replace('"', "").replace("«", "").replace("»", "")
        if snippet.lower() not in base_lower:
            base = base + f'. He speaks these words: "{script_clean}"'

    # Голос уже описан — не дублируем
    if voice_clean and len(voice_clean) > 15:
        words = voice_clean.lower().split()[:5]
        if not any(w in base_lower for w in words if len(w) > 3):
            base = base + f". Voice: {voice_clean}"

    # Озвучка FastGen плохо читает тире — в промпт уходят запятые; субтитры без изменений
    base = (
        base
        + ". VISUAL CLEAN FRAME RULE: absolutely no text rendered inside the video image - "
        + "no subtitles, no captions, no quote text on screen, no title overlays, no lower-thirds, "
        + "no letters, no readable signage, no logos, no watermark"
    )
    return dashes_to_commas_for_voice(base + _STYLE_SUFFIX)


async def generate_quote_videos(
    video_prompts: list[str],
    output_dir: Path,
    reference_image_path: str | Path,
    voice_description: str = "",
    scripts: list[str] | None = None,
    cancel_event=None,
) -> list[Path | None]:
    """
    Генерирует 1 или 2 видео с использованием фото личности как reference.

    При двух промптах (RU+EN) запускаются два окна FastGen параллельно (ThreadPoolExecutor).

    Args:
        video_prompts: список промптов (1 = один фрагмент; 2 = RU и EN параллельно)
        output_dir: папка для clip_000.mp4, clip_001.mp4
        reference_image_path: фото личности для image-to-video
        voice_description: описание голоса (добавляется в промпт для FastGen)
        scripts: точный текст цитаты для каждого фрагмента (добавляется в промпт)
    """
    ref_path = Path(reference_image_path).resolve()
    if not ref_path.exists():
        raise FileNotFoundError(f"Reference image not found: {reference_image_path}")

    scripts = scripts or []
    enriched: list[str] = []
    for i, prompt in enumerate(video_prompts):
        script = scripts[i] if i < len(scripts) else ""
        enriched.append(_enrich_prompt(prompt, voice_description, script))

    # Два языка (RU+EN) — два окна FastGen параллельно (как _run_fastgen_video_sync)
    if len(enriched) == 2:
        logger.info(
            f"[Mode4 Video] Generating RU + EN in parallel; same reference for both: {ref_path}"
        )
        paths = await generate_videos_fastgen(
            enriched,
            output_dir,
            str(ref_path),
            mode4_veo_flow_flower=settings.mode4_veo_enable_flower_fallback,
            flow_max_attempts=settings.fastgen_veo_flow_max_attempts,
        )
        if any(p is None or not Path(p).exists() for p in paths):
            failed = [i for i, p in enumerate(paths) if p is None or not Path(p).exists()]
            logger.warning(f"[Mode4 Video] Parallel run had failures at indices {failed}, retrying those sequentially ...")
            clip_retries = 2
            out: list[Path | None] = list(paths)
            for i in failed:
                for retry in range(clip_retries + 1):
                    logger.info(f"[Mode4 Video] Retry clip {i} with reference: {ref_path}")
                    path = await generate_single_video_fastgen(
                        enriched[i],
                        output_dir,
                        i,
                        ref_path,
                        cancel_event=cancel_event,
                        mode4_veo_flow_flower=settings.mode4_veo_enable_flower_fallback,
                        flow_max_attempts=settings.fastgen_veo_flow_max_attempts,
                    )
                    if path and Path(path).exists():
                        out[i] = path
                        break
                    if retry < clip_retries:
                        logger.warning(
                            f"[Mode4 Video] Fragment {i} retry {retry + 2}/{clip_retries + 1} ..."
                        )
            return out
        return paths

    paths: list[Path | None] = []
    clip_retries = 2
    for i, full_prompt in enumerate(enriched):
        logger.info(f"[Mode4 Video] Generating fragment {i + 1}/{len(enriched)} ...")
        path = None
        for retry in range(clip_retries + 1):
            logger.info(f"[Mode4 Video] Clip {i}: reference image {ref_path}")
            path = await generate_single_video_fastgen(
                full_prompt,
                output_dir,
                i,
                ref_path,
                cancel_event=cancel_event,
                mode4_veo_flow_flower=settings.mode4_veo_enable_flower_fallback,
                flow_max_attempts=settings.fastgen_veo_flow_max_attempts,
            )
            if path and Path(path).exists():
                break
            if retry < clip_retries:
                logger.warning(f"[Mode4 Video] Fragment {i} failed, retry {retry + 2}/{clip_retries + 1} ...")
        paths.append(path)
        if not path or not Path(path).exists():
            logger.warning(f"[Mode4 Video] Fragment {i} failed after {clip_retries + 1} attempts")
            break

    return paths
