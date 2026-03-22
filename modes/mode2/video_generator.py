"""
Mode 2 Video Generator — generate via fast-gen.ai or fetch from Pexels API.

If FASTGEN_API_KEY is set, uses fast-gen.ai (same as Mode 1 images).
Otherwise falls back to Pexels stock videos.
"""

from __future__ import annotations

from pathlib import Path

import httpx
from loguru import logger

from agents.content_generator.fastgen_scraper import generate_videos_fastgen
from config import settings


PEXELS_VIDEO_SEARCH = "https://api.pexels.com/videos/search"


async def search_and_download_video(
    query: str,
    output_path: Path,
    orientation: str = "portrait",
) -> Path | None:
    """
    Search Pexels for a video by query and download the first result.

    Args:
        query: English search phrase (e.g. "dog wagging tail").
        output_path: Destination file path (.mp4).
        orientation: "portrait" | "landscape" | "square".

    Returns:
        Path to downloaded video, or None if no results / error.
    """
    api_key = getattr(settings, "pexels_api_key", "") or ""
    if not api_key:
        logger.warning("[Mode2 Video] PEXELS_API_KEY not set — skipping Pexels download")
        return None

    output_path.parent.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.get(
                PEXELS_VIDEO_SEARCH,
                params={
                    "query": query,
                    "orientation": orientation,
                    "per_page": 5,
                },
                headers={"Authorization": api_key},
            )
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"[Mode2 Video] Pexels API error: {e.response.status_code} — {e.response.text[:200]}")
            return None
        except Exception as e:
            logger.error(f"[Mode2 Video] Pexels request failed: {e}")
            return None

    videos = data.get("videos") or []
    if not videos:
        logger.warning(f"[Mode2 Video] No Pexels results for: {query!r}")
        return None

    video = videos[0]
    video_files = video.get("video_files") or []

    # Prefer portrait/sd for vertical format
    def _score_file(f: dict) -> tuple:
        qual = f.get("quality", "").lower()
        h = f.get("height") or 0
        w = f.get("width") or 0
        link = f.get("link") or ""
        if not link or f.get("file_type") != "video/mp4":
            return (999, 0)
        # Prefer sd for faster download; prefer portrait for vertical output
        q_order = {"sd": 0, "hd": 1}
        q_rank = q_order.get(qual, 2)
        is_portrait = 1 if h > w else 0
        return (q_rank, -is_portrait, -h)

    sorted_files = sorted(video_files, key=_score_file)
    best = sorted_files[0] if sorted_files else None
    if not best or not best.get("link"):
        logger.warning(f"[Mode2 Video] No suitable video file for: {query!r}")
        return None

    download_url = best["link"]
    logger.info(f"[Mode2 Video] Downloading: {query!r} → {output_path.name}")

    try:
        async with httpx.AsyncClient(timeout=120) as dl_client:
            dl = await dl_client.get(download_url)
            dl.raise_for_status()
            output_path.write_bytes(dl.content)
        logger.success(f"[Mode2 Video] Downloaded → {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"[Mode2 Video] Download failed: {e}")
        return None


def _topic_to_intro_prompt(topic: str, first_scene: dict | None) -> str:
    """Build thematic intro video prompt from topic."""
    base = (
        (first_scene.get("video_search_query") or first_scene.get("subtitle_text", ""))
        if first_scene
        else topic
    )
    if not (base or "").strip():
        base = topic or "cinematic atmospheric"
    return f"{base.strip()}, vertical 9:16 portrait format, centered subject, cinematic lighting, high quality"


async def generate_intro_video_for_topic(
    topic: str,
    scenes: list[dict],
    output_dir: Path,
    reference_image_path: str | None = None,
) -> Path | None:
    """
    Generate a thematic intro video from the video topic (FastGen only).
    Returns path to intro clip, or None.
    """
    fastgen_key = getattr(settings, "fastgen_api_key", "") or ""
    if not fastgen_key:
        return None
    prompt = _topic_to_intro_prompt(topic, scenes[0] if scenes else None)
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"[Mode2 Video] Generating thematic intro from topic: {prompt[:60]}...")
    ref_path = reference_image_path if reference_image_path and Path(reference_image_path).exists() else None
    paths = await generate_videos_fastgen([prompt], output_dir, reference_image_path=ref_path)
    if paths and paths[0] and paths[0].exists():
        logger.success(f"[Mode2 Video] Intro video saved: {paths[0].name}")
        return paths[0]
    return None


async def download_videos_for_scenes(
    scenes: list[dict],
    output_dir: Path,
    reference_image_path: str | None = None,
    title: str | None = None,
) -> list[dict]:
    """
    For each scene with video_search_query:
    - If FASTGEN_API_KEY set → generate via fast-gen.ai (same service as Mode 1 images)
    - Else → fetch from Pexels

    If title is provided, prepends an intro video (fragment 1) that speaks the topic.
    Returns 6 items: [intro, scene0, scene1, scene2, scene3, scene4].
    """
    first_query = (scenes[0].get("video_search_query") if scenes else None) or title or ""
    intro_scene: dict = {
        "narration_text": title or "",
        "subtitle_text": title or "",
        "video_search_query": first_query,
        "video_path": None,
        "index": 0,
    }
    scenes_to_fetch = [intro_scene] + list(scenes)

    fastgen_key = getattr(settings, "fastgen_api_key", "") or ""
    if fastgen_key:
        logger.info("[Mode2 Video] Using fast-gen.ai for video generation (vertical 9:16)")
        _CHANNEL_STYLE_SUFFIX = (
            ", vibrant saturated rich colors, cinematic documentary style, "
            "shallow depth of field, 4K photorealistic, vertical 9:16 portrait, "
            "centered subject, attention-grabbing composition"
        )
        intro_prompt = _topic_to_intro_prompt(title or "cinematic", scenes[0] if scenes else None)
        scene_prompts = [
            (s.get("video_search_query") or s.get("subtitle_text", "nature")).strip()
            for s in scenes
        ]
        prompts = [intro_prompt] + [p.rstrip(" .,") + _CHANNEL_STYLE_SUFFIX for p in scene_prompts]
        ref_path = None
        if reference_image_path and Path(reference_image_path).exists():
            ref_path = reference_image_path
        paths = await generate_videos_fastgen(
            prompts, output_dir, reference_image_path=ref_path
        )
        result: list[dict] = []
        for i, scene in enumerate(scenes_to_fetch):
            scene_copy = dict(scene)
            path = paths[i] if i < len(paths) else None
            scene_copy["video_path"] = str(path.resolve()) if path else None
            result.append(scene_copy)
        return result

    logger.info("[Mode2 Video] Using Pexels (fast-gen not configured)")
    result = []
    for i, scene in enumerate(scenes_to_fetch):
        scene_copy = dict(scene)
        query = scene.get("video_search_query") or scene.get("subtitle_text") or title or "nature"
        out_path = output_dir / f"clip_{i:03d}.mp4"
        path = await search_and_download_video(
            query, out_path, orientation="portrait"
        )
        scene_copy["video_path"] = str(path.resolve()) if path else None
        result.append(scene_copy)
    return result
