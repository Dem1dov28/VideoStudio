"""
Mode 4 Video Generator — 1 или 2 видеофрагмента с reference image (фото личности).
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from agents.content_generator.fastgen_scraper import (
    generate_single_video_fastgen,
    generate_videos_fastgen,
)
from config import settings

from modes.mode4.quote_format import dashes_to_commas_for_voice

_STYLE_SUFFIX = ", 9:16 portrait, photorealistic, no AI artifacts"


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
            enriched, output_dir, str(ref_path)
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
                        enriched[i], output_dir, i, ref_path, cancel_event=cancel_event
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
                full_prompt, output_dir, i, ref_path, cancel_event=cancel_event
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
