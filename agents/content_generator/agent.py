"""Image Generator Agent."""

from __future__ import annotations

import asyncio
import base64
import time
from pathlib import Path

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings
from agents.content_generator.prompt_builder import Scene, build_scenes
from agents.content_generator.types import EnrichedScene


# ── fast-gen.ai ────────────────────────────────────────────────────────────────

async def _generate_images_fastgen(prompts: list[str], output_dir: Path) -> list[Path]:
    from agents.content_generator.fastgen_scraper import generate_images_fastgen
    return await generate_images_fastgen(prompts, output_dir)


# ── HuggingFace FLUX.1-schnell ────────────────────────────────────────────────

_HF_URL = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell/v1/text-to-image"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=5, max=30))
async def _generate_hf(prompt: str, dest: Path) -> Path:
    if not settings.hf_token:
        raise ValueError(
            "HF_TOKEN is empty. Get a free token at https://huggingface.co/settings/tokens"
        )
    headers = {"Authorization": f"Bearer {settings.hf_token}", "Content-Type": "application/json"}
    payload = {"inputs": prompt, "parameters": {"width": 832, "height": 1216}}
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(_HF_URL, headers=headers, json=payload)
        if r.status_code == 503:
            wait = int(r.headers.get("X-WaitFor", "20"))
            await asyncio.sleep(wait)
            raise RuntimeError("Model loading, retrying")
        r.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return dest


async def _generate_images_hf(prompts: list[str], output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, prompt in enumerate(prompts):
        dest = output_dir / f"frame_{int(time.time())}_{i}.jpg"
        paths.append(await _generate_hf(prompt, dest))
        await asyncio.sleep(1)
    return paths


# ── DALL-E 3 ──────────────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
async def _generate_dalle(prompt: str, dest: Path) -> Path:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is empty. Set it in .env for DALL-E.")
    import openai
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    size = "1024x1792" if settings.video_format == "vertical" else "1792x1024"
    response = await client.images.generate(
        model="dall-e-3", prompt=prompt, size=size,
        quality="standard", n=1, response_format="b64_json",
    )
    image_data = response.data[0].b64_json
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(base64.b64decode(image_data))
    return dest


async def _generate_images_dalle(prompts: list[str], output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    tasks = [
        _generate_dalle(prompt, output_dir / f"frame_{int(time.time())}_{i}.png")
        for i, prompt in enumerate(prompts)
    ]
    return list(await asyncio.gather(*tasks))


# ── Public API ─────────────────────────────────────────────────────────────────

async def run_image_generator_agent(
    topic: str,
    num_scenes: int = 5,
    session_id: str | None = None,
    scenario: "list | None" = None,
) -> list[EnrichedScene]:
    """
    Generate images for each scene.

    Args:
        topic:      Video topic (used to build scenes if no scenario provided).
        num_scenes: Number of scenes to generate.
        session_id: Unique run identifier.
        scenario:   Optional pre-built list of ScenarioScene dicts from ScenarioWriterAgent.
                    If provided, uses their image_prompts, narration_text, and subtitle_text.
    """
    session_id = session_id or str(int(time.time()))
    output_dir = settings.images_dir / session_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build scene list — prefer pre-written scenario, fall back to prompt_builder
    if scenario:
        logger.info(f"[ImageAgent] Using pre-written scenario ({len(scenario)} scenes)")
        prompts = [s["image_prompt"] for s in scenario]
    else:
        logger.info(f"[ImageAgent] Building scenes for: {topic!r}")
        scenes_raw: list[Scene] = build_scenes(topic, num_scenes)
        prompts = [s["image_prompt"] for s in scenes_raw]
        # Convert to scenario-like format for uniform downstream handling
        scenario = [
            {
                "index": s["index"],
                "narration_text": s["subtitle_text"],
                "subtitle_text": s["subtitle_text"],
                "image_prompt": s["image_prompt"],
            }
            for s in scenes_raw
        ]

    strategy = settings.image_gen_strategy.lower()
    image_paths: list[Path] = []

    # Each strategy is isolated — no silent fallthrough
    if strategy == "fastgen":
        logger.info("[ImageAgent] Using fast-gen.ai (Playwright) ...")
        image_paths = await _generate_images_fastgen(prompts, output_dir)

    elif strategy == "hf":
        logger.info("[ImageAgent] Using HuggingFace FLUX.1-schnell ...")
        image_paths = await _generate_images_hf(prompts, output_dir)

    elif strategy == "dalle":
        logger.info("[ImageAgent] Using DALL-E 3 ...")
        image_paths = await _generate_images_dalle(prompts, output_dir)

    elif strategy == "both":
        logger.info("[ImageAgent] Trying fast-gen.ai first ...")
        try:
            image_paths = await _generate_images_fastgen(prompts, output_dir)
            logger.success(f"[ImageAgent] fast-gen.ai: {len(image_paths)} images")
        except Exception as exc:
            logger.warning(f"[ImageAgent] fast-gen.ai failed: {exc}")
            logger.info("[ImageAgent] Falling back to DALL-E 3 ...")
            image_paths = await _generate_images_dalle(prompts, output_dir)

    else:
        raise ValueError(
            f"Unknown IMAGE_GEN_STRATEGY: '{strategy}'. "
            "Use: fastgen | hf | dalle | both"
        )

    if not image_paths:
        raise RuntimeError(
            f"[ImageAgent] No images were generated with strategy '{strategy}'"
        )

    enriched: list[EnrichedScene] = []
    for scene, img_path in zip(scenario, image_paths):
        enriched.append(EnrichedScene(
            index=scene["index"],
            image_prompt=scene["image_prompt"],
            subtitle_text=scene.get("subtitle_text", ""),
            narration_text=scene.get("narration_text", scene.get("subtitle_text", "")),
            image_path=str(img_path.resolve()),
            outro_bg_image_path=None,
        ))

    logger.success(f"[ImageAgent] Done - {len(enriched)} scenes ready")

    # ── Outro background generation (likes + subscribe) ──────────────────
    # Structured using Image Generation Expert formula: Subject + Style + Lighting + Composition + Quality + Format
    outro_prompt = (
        "Large glowing 3D thumbs-up icon and notification bell floating in space, "
        "modern UI/UX design style with glassmorphism effects, "
        "dramatic violet neon rim lighting with soft bokeh background lights, "
        "centered composition with shallow depth of field, "
        "ultra detailed 8K UHD, cinematic color grading, hyper-detailed textures, "
        "vertical 9:16 portrait format, subject centered, no text, no letters, no watermark"
    )

    outro_bg_path: Path | None = None
    try:
        if strategy == "fastgen":
            p = await _generate_images_fastgen([outro_prompt], output_dir)
            outro_bg_path = p[0] if p else None
        elif strategy == "hf":
            p = await _generate_images_hf([outro_prompt], output_dir)
            outro_bg_path = p[0] if p else None
        elif strategy == "dalle":
            p = await _generate_images_dalle([outro_prompt], output_dir)
            outro_bg_path = p[0] if p else None
        elif strategy == "both":
            try:
                p = await _generate_images_fastgen([outro_prompt], output_dir)
                outro_bg_path = p[0] if p else None
            except Exception:
                p = await _generate_images_dalle([outro_prompt], output_dir)
                outro_bg_path = p[0] if p else None
    except Exception as exc:
        logger.warning(f"[ImageAgent] Outro background generation failed: {exc}")

    if enriched and outro_bg_path is not None:
        enriched[0]["outro_bg_image_path"] = str(outro_bg_path.resolve())

    return enriched