"""Social Media Publisher Agent."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from agents.content_generator.agent import EnrichedScene
from agents.publisher.postiz_client import publish_to_all_platforms
from utils.llm import make_llm


_CAPTION_SYSTEM = """You are a social media copywriter optimized for 2025-2026 algorithm changes.

Given a video topic and scene subtitles, write:
  1. A compelling caption (2-3 sentences, engaging, emoji allowed).
     - Instagram: keyword-rich for SEO (not just hashtags)
     - TikTok: caption text helps algorithm categorize content
     - YouTube: include #Shorts in caption
  2. 3-5 highly relevant hashtags (without #, as JSON array of strings).
     - Mix: 1-2 niche-specific + 1-2 category + 0-1 broad/trending
     - Quality over quantity — excessive hashtags reduce reach

PLATFORM-SPECIFIC NOTES:
- Instagram (Dec 2025): Keywords in caption matter MORE than hashtags
- TikTok: 3-5 hashtags optimal, trending sounds boost FYP placement
- YouTube Shorts: 55-second content gets 3x views vs 15-second

Return ONLY valid JSON: {"caption": "...", "hashtags": ["tag1", "tag2", ...]}"""


def _generate_caption(topic: str, subtitles: list[str]) -> tuple[str, list[str]]:
    llm = make_llm(temperature=0.8)
    messages = [
        SystemMessage(content=_CAPTION_SYSTEM),
        HumanMessage(content=f"Topic: {topic}\nSubtitles:\n" + "\n".join(f"- {s}" for s in subtitles)),
    ]
    response = llm.invoke(messages)
    raw = response.content.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}") + 1
        data = json.loads(raw[start:end])
    return data["caption"], data.get("hashtags", [])


async def run_publisher_agent(
    video_path: str,
    scenes: list[EnrichedScene],
    topic: str,
    schedule_at: datetime | None = None,
) -> dict[str, Any]:
    subtitles = [s["subtitle_text"] for s in scenes]
    logger.info("[PublisherAgent] Generating caption via OpenRouter ...")
    caption, hashtags = _generate_caption(topic, subtitles)
    logger.info(f"[PublisherAgent] Caption: {caption[:80]}...")

    results = await publish_to_all_platforms(
        video_path=Path(video_path),
        caption=caption,
        hashtags=hashtags,
        schedule_at=schedule_at,
    )

    report = {
        "topic": topic,
        "video_path": video_path,
        "caption": caption,
        "hashtags": hashtags,
        "platforms": results,
    }
    logger.success("[PublisherAgent] Done")
    return report