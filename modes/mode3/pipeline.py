"""
Mode 3 Pipeline — Восстановление старых домов.

Два режима:
  A) Загрузка изображений — start + end картинки
  B) Текст (topic) — генерация «дом ДО» и «дом ПОСЛЕ» через FastGen

Шаги:
  1. Prompt Agent — (A) vision | (B) text agent → промпты
  2. [B only] Image Gen — фото разваленного дома (before)
  3. Video Generator — цепочка: video₁ (ref=before) → frame₁ → video₂ (ref=frame₁) → video₃
  4. Assembler — склейка + музыка
"""

from __future__ import annotations

import asyncio
import functools
import time
from pathlib import Path
from typing import Any

from loguru import logger

from config import settings
from modes.mode3.prompt_agent import run_image_prompt_agent, run_prompt_agent
from modes.mode3.video_assembler import assemble_mode3_video
from modes.mode3.video_generator import generate_restoration_videos


async def _generate_mode3_images_chain(
    image_prompt_before: str,
    image_prompt_before_interior: str,
    image_prompt_after: str,
    image_prompt_mid_exterior: str,
    image_prompt_mid_interior: str,
    image_prompt_after_interior: str,
    output_dir: Path,
) -> tuple[Path, Path, Path, Path, Path, Path]:
    """
    Цепочка 6 изображений: text2img ruined → img2img mid → img2img final (экстерьер + интерьер).
    Returns: (ext_ruined, ext_mid, ext_final, int_ruined, int_mid, int_final)
    """
    from agents.content_generator.fastgen_scraper import generate_images_chain_fastgen

    steps = [
        (image_prompt_before, None),              # 0: ruined exterior (text2img)
        (image_prompt_mid_exterior, 0),            # 1: mid exterior (img2img)
        (image_prompt_after, 1),                   # 2: final exterior (img2img)
        (image_prompt_before_interior, None),      # 3: ruined interior (text2img)
        (image_prompt_mid_interior, 3),            # 4: mid interior (img2img)
        (image_prompt_after_interior, 4),           # 5: final interior (img2img)
    ]
    paths = await generate_images_chain_fastgen(steps, output_dir)
    if len(paths) < 6:
        raise RuntimeError(f"[Mode3] Expected 6 images, got {len(paths)}")
    return tuple(Path(p) for p in paths)


async def run_mode3_pipeline_from_topic(
    topic: str,
    session_id: str | None = None,
    local_only: bool = True,
    control: dict | None = None,
) -> dict[str, Any]:
    """
    Запуск пайплайна «Восстановление старого дома» по текстовому описанию.

    Генерирует «дом ДО» и «дом ПОСЛЕ» через FastGen, затем собирает 3 видео.
    """
    session_id = session_id or str(int(time.time() * 1000))
    videos_dir = settings.videos_dir / session_id
    clips_dir = videos_dir / "clips"
    images_dir = videos_dir / "generated_images"
    clips_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    from pipeline_control import checkpoint

    logger.info(f"=== Mode 3 Pipeline (from topic) | session={session_id} ===")

    await checkpoint(control)
    # ── Step 1: Image prompt agent ───────────────────────────────────────────
    logger.info("Step 1/4 - Image prompt agent (topic → before/before_interior/after)")
    prompt_data = await run_image_prompt_agent(topic)
    image_prompt_before = prompt_data["image_prompt_before"]
    image_prompt_before_interior = prompt_data["image_prompt_before_interior"]
    image_prompt_after = prompt_data["image_prompt_after"]
    video_prompts = prompt_data["video_prompts"]

    await checkpoint(control)
    # ── Step 2: Generate 6 images via chain ───────────────────────────────────────
    logger.info("Step 2/4 - FastGen chain: ruined→mid→final (exterior + interior)")
    ext_ruined, ext_mid, ext_final, int_ruined, int_mid, int_final = await _generate_mode3_images_chain(
        image_prompt_before,
        image_prompt_before_interior,
        image_prompt_after,
        prompt_data.get("image_prompt_mid_exterior", ""),
        prompt_data.get("image_prompt_mid_interior", ""),
        prompt_data.get("image_prompt_after_interior", ""),
        images_dir,
    )
    logger.success(
        f"[Mode3] Generated 6 images: ext {ext_ruined.name}→{ext_mid.name}→{ext_final.name} | "
        f"int {int_ruined.name}→{int_mid.name}→{int_final.name}"
    )

    await checkpoint(control)
    # ── Step 3: Video Generator — 5 clips with 6 ref images ──────────────────────
    logger.info("Step 3/4 - Mode3 Video Generator (intro + exterior×2 + interior + showcase)")
    video_paths = await generate_restoration_videos(
        video_prompts,
        clips_dir,
        reference_image_path=ext_ruined,
        ref_overrides={
            0: ext_ruined,
            1: ext_ruined,
            2: ext_mid,
            3: int_ruined,
            4: ext_final,
        },
    )
    valid_paths = [p for p in video_paths if p and Path(p).exists()]
    if len(valid_paths) < 5:
        logger.warning(f"[Mode3] Only {len(valid_paths)}/5 videos generated")

    await checkpoint(control)
    # ── Step 4: Assembler ───────────────────────────────────────────────────
    logger.info("Step 4/4 - Mode3 Video Assembler (music only)")
    output_path = settings.videos_dir / f"video_{session_id}.mp4"
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        functools.partial(assemble_mode3_video, valid_paths, output_path),
    )

    logger.success(f"=== Mode 3 Pipeline (topic) DONE | video={output_path} ===")
    video_path = str(output_path.resolve())
    from agents.topics_history import mark_topic_used
    mark_topic_used(topic=topic or "Реставрация дома", session_id=session_id, video_path=video_path)
    return {
        "session_id": session_id,
        "video_path": video_path,
        "topic": topic,
        "trend": None,
        "report": None,
    }


async def run_mode3_pipeline(
    start_image_path: str | Path,
    end_image_path: str | Path,
    session_id: str | None = None,
    local_only: bool = True,
    control: dict | None = None,
) -> dict[str, Any]:
    """
    Запуск пайплайна «Восстановление старого дома».

    Args:
        start_image_path: картинка дома ДО (запущенный)
        end_image_path: картинка дома ПОСЛЕ (восстановленный)
        session_id: уникальный ID запуска
        local_only: не публиковать

    Returns:
        dict с video_path, session_id
    """
    session_id = session_id or str(int(time.time() * 1000))
    videos_dir = settings.videos_dir / session_id
    clips_dir = videos_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    from pipeline_control import checkpoint

    logger.info(f"=== Mode 3 Pipeline | House Restoration | session={session_id} ===")

    await checkpoint(control)
    # ── Step 1: Prompt Agent ─────────────────────────────────────────────────
    logger.info("Step 1/4 - Mode3 Prompt Agent (analyze images, generate prompts)")
    prompt_data = await run_prompt_agent(start_image_path, end_image_path)
    video_prompts = prompt_data["video_prompts"]
    image_prompt_before_interior = prompt_data.get("image_prompt_before_interior")

    await checkpoint(control)
    # ── Step 1b: Generate interior ref (для clip 3) ───────────────────────────
    start_interior_path: Path | None = None
    if image_prompt_before_interior:
        images_dir = videos_dir / "generated_images"
        images_dir.mkdir(parents=True, exist_ok=True)
        suf = ", vertical 9:16 portrait, shot on Canon EOS R5, 8K photograph, no AI artifacts, hyperrealistic"
        prompt = (image_prompt_before_interior or "").rstrip(" .,") + suf
        try:
            from agents.content_generator.fastgen_scraper import generate_images_fastgen
            paths = await generate_images_fastgen([prompt], images_dir)
            if paths:
                start_interior_path = Path(paths[0])
                logger.info(f"[Mode3] Generated interior ref → {start_interior_path.name}")
        except Exception as e:
            logger.warning(f"[Mode3] Could not generate interior image: {e}")

    await checkpoint(control)
    # ── Step 2: Video Generator — 5 clips: intro, exterior×2, interior, showcase ─
    logger.info("Step 2/4 - Mode3 Video Generator (intro + exterior×2 + interior + showcase)")
    overrides: dict[int, Path] = {1: Path(start_image_path), 4: Path(end_image_path)}
    if start_interior_path and start_interior_path.exists():
        overrides[3] = start_interior_path
    video_paths = await generate_restoration_videos(
        video_prompts,
        clips_dir,
        reference_image_path=start_image_path,
        ref_overrides=overrides,
    )
    valid_paths = [p for p in video_paths if p and Path(p).exists()]
    if len(valid_paths) < 5:
        logger.warning(f"[Mode3] Only {len(valid_paths)}/5 videos generated")

    await checkpoint(control)
    # ── Step 3: Assembler ───────────────────────────────────────────────────
    logger.info("Step 3/4 - Mode3 Video Assembler (music only)")
    output_path = settings.videos_dir / f"video_{session_id}.mp4"
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        functools.partial(assemble_mode3_video, valid_paths, output_path),
    )

    logger.success(f"=== Mode 3 Pipeline DONE | video={output_path} ===")
    video_path = str(output_path.resolve())
    from agents.topics_history import mark_topic_used
    mark_topic_used(topic="Реставрация дома", session_id=session_id, video_path=video_path)
    return {
        "session_id": session_id,
        "video_path": video_path,
        "topic": "House Restoration",
        "trend": None,
        "report": None,
    }
