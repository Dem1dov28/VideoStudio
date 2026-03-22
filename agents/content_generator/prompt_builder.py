"""
Asks the LLM to decompose a topic into a list of scene descriptions
(image prompts + subtitle text) for the video.
"""

from __future__ import annotations

import json
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from utils.llm import make_llm


class Scene(TypedDict):
    index: int
    image_prompt: str
    subtitle_text: str


_SYSTEM_PROMPT = """You are a creative director for short vertical social-media videos (TikTok/Reels/Shorts).
Given a topic, produce a JSON array of scenes. Each scene has:
  - "index": integer (1, 2, 3 ...)
  - "image_prompt": vivid English image description for AI image generation.
    ALWAYS include: "vertical portrait orientation, 9:16 aspect ratio, subject centered,
    photorealistic, cinematic lighting, 4K". Keep the main subject centered vertically.
  - "subtitle_text": short Russian sentence (<=10 words) shown as subtitle and read as TTS voiceover.
    Keep it short so it fits on one line.

Return ONLY valid JSON array, no markdown, no extra text.
Example:
[
  {"index":1,"image_prompt":"...vertical portrait orientation, 9:16 aspect ratio...","subtitle_text":"..."},
  {"index":2,"image_prompt":"...vertical portrait orientation, 9:16 aspect ratio...","subtitle_text":"..."}
]"""


def build_scenes(topic: str, num_scenes: int = 5) -> list[Scene]:
    """Use the LLM via OpenRouter to generate a list of scenes from a topic."""
    llm = make_llm(temperature=0.7)
    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Topic: {topic}\n"
                f"Number of scenes: {num_scenes}\n"
                "Language for subtitle_text: Russian"
            )
        ),
    ]
    response = llm.invoke(messages)
    raw = response.content.strip()
    logger.debug(f"LLM scenes response: {raw[:300]}")

    try:
        scenes: list[Scene] = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start != -1 and end > start:
            scenes = json.loads(raw[start:end])
        else:
            raise ValueError(f"Could not parse scenes JSON: {raw}")

    logger.info(f"Generated {len(scenes)} scenes for topic: {topic!r}")
    return scenes