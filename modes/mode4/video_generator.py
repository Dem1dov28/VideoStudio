"""
Mode 4 Video Generator — 1 или 2 видеофрагмента с reference image (фото личности).
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from agents.content_generator.fastgen_scraper import generate_single_video_fastgen
from config import settings

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

    return base + _STYLE_SUFFIX


async def generate_quote_videos(
    video_prompts: list[str],
    output_dir: Path,
    reference_image_path: str | Path,
    voice_description: str = "",
    scripts: list[str] | None = None,
) -> list[Path | None]:
    """
    Генерирует 1 или 2 видео с использованием фото личности как reference.

    Args:
        video_prompts: список промптов (1 = один язык, 2 = русский + английский)
        output_dir: папка для clip_000.mp4, clip_001.mp4
        reference_image_path: фото личности для image-to-video
        voice_description: описание голоса (добавляется в промпт для FastGen)
        scripts: точный текст цитаты для каждого фрагмента (добавляется в промпт)
    """
    ref_path = Path(reference_image_path)
    if not ref_path.exists():
        raise FileNotFoundError(f"Reference image not found: {reference_image_path}")

    scripts = scripts or []
    paths: list[Path | None] = []
    clip_retries = 2  # повторить при ошибке FastGen
    for i, prompt in enumerate(video_prompts):
        script = scripts[i] if i < len(scripts) else ""
        full_prompt = _enrich_prompt(prompt, voice_description, script)
        logger.info(f"[Mode4 Video] Generating fragment {i + 1}/{len(video_prompts)} ...")
        path = None
        for retry in range(clip_retries + 1):
            path = await generate_single_video_fastgen(
                full_prompt, output_dir, i, ref_path
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
