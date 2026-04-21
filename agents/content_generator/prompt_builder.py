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


_SYSTEM_PROMPT = """You are an expert creative director and prompt engineer for AI image generation in short vertical social-media videos (TikTok/Reels/Shorts).

═══ IMAGE PROMPT ENGINEERING RULES ═══
Structure every image_prompt using this formula:
[Subject] + [Style] + [Lighting] + [Composition] + [Quality Modifiers] + [Vertical Format]

**Subject**: Be specific and vivid. "A majestic golden retriever" not "a dog"
**Style**: Choose ONE per scene for consistency:
  - photorealistic, cinematic, 3D render
  - digital art, concept art, hyper-realistic
  - documentary style, editorial photography
**Lighting**: Use specific lighting for mood:
  - dramatic lighting, soft natural light, golden hour
  - studio lighting, rim lighting, volumetric lighting
**Composition**: Direct the framing:
  - close-up portrait, wide angle, Dutch angle
  - rule of thirds, centered subject, shallow depth of field
**Quality Modifiers**: Always include quality boosters:
  - ultra detailed, 8K UHD, sharp focus, hyper-detailed textures
  - professional photography, award-winning, cinematic color grading
**Vertical Format** (REQUIRED): End EVERY prompt with:
  "vertical 9:16 portrait format, subject centered, no text, no watermark"

═══ SCROLL-STOPPING TECHNIQUES ═══
- Use unexpected angles or perspectives
- Include motion implications (frozen action, dynamic pose)
- Add emotional impact through lighting and color
- Create visual curiosity gaps that demand attention

═══ NEGATIVE PROMPT ELEMENTS (Avoid) ═══
- No text, no letters, no words, no watermark
- No blurry, no low quality, no distorted
- No duplicate elements, no cluttered composition

═══ OUTPUT FORMAT ═══
Each scene has:
  - "index": integer (1, 2, 3 ...)
  - "image_prompt": Complete English image description following the formula above
  - "subtitle_text": Short Russian sentence (<=10 words) for subtitle/TTS

Return ONLY valid JSON array, no markdown, no extra text.
Example:
[
  {"index":1,"image_prompt":"A dramatic close-up of an astronaut helmet reflecting nebula colors, photorealistic style, cinematic rim lighting, shallow depth of field, ultra detailed 8K UHD, sharp focus, hyper-detailed metallic textures, vertical 9:16 portrait format, subject centered, no text, no watermark","subtitle_text":"..."},
  {"index":2,"image_prompt":"Ancient temple ruins overgrown with bioluminescent plants, digital art style, volumetric god rays filtering through mist, wide angle composition, award-winning concept art, cinematic color grading, ultra detailed, vertical 9:16 portrait format, subject centered, no text, no watermark","subtitle_text":"..."}
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