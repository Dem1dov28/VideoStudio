"""
Mode 8 Publishing Metadata Generator.

Generates Title, Description, Hashtags, Tags for YouTube Shorts
based on the house building timelapse video content.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger
from utils.llm import make_llm


PUBLISHING_PROMPT = """Generate final YouTube Shorts publishing content for a timelapse of a PRIVATE HOUSE / SINGLE-FAMILY HOME being built on a plot (empty land → finished home). Not office towers, not apartment blocks, not monuments — only residential house construction.

VIDEO CONTEXT:
- House Style: {house_style}
- Location: {location}
- Stages: {stages_description}
- Title: {title}

OUTPUT STRUCTURE:

1. TITLE
- Short, attention-grabbing
- First 2 words must be strong keywords related to construction (e.g. "House Build", "Build Timelapse", "From Nothing")
- Clearly reflect transformation (before → after)
- Max 1 emoji at the end (relevant to construction)
- Always end with exactly 2 hashtags: #timelapse #beforeafter

2. DESCRIPTION
- First line: 1 short sentence describing the transformation (e.g. from empty land to house)
- Then naturally include 4-5 keywords:
  (construction timelapse, building process, house build, before after, transformation)
- Text must read naturally, not like keyword spam
- At the end of description, always add exactly these 5 hashtags:
  - For Russian: #housebuilding #дома #buildingprocess #timelapse #beforeafter
  - For English: #housebuilding #home #buildingprocess #timelapse #beforeafter

CONTENT RULES:

- Focus on process, not just result
- Emphasize transformation and progression
- Avoid generic or vague titles
- Avoid spammy keywords
- Keep everything clean, readable, and optimized for Shorts feed

OUTPUT FORMAT (JSON):

{{
  "title": "...",
  "description": "...",
  "tags": ["tag1", "tag2", ...]
}}

Language: {language}
"""


# Fallback templates if LLM fails
FALLBACK_TEMPLATES = {
    "ru": {
        "titles": [
            "Строительство дома: от пустого участка до готового {style} 🏠 #timelapse #beforeafter",
            "{style} за 60 секунд: полная стройка #timelapse #beforeafter",
            "От земли до дома: {style} в {location} 🔨 #timelapse #beforeafter",
            "Таймлапс стройки: как построили {style} #timelapse #beforeafter",
        ],
        "descriptions": [
            "Смотрите как из пустого участка рождается красивый дом. Полный процесс строительства в таймлапсе! #housebuilding #дома #buildingprocess #timelapse #beforeafter",
            "От котлована до крыши — весь процесс постройки дома за минуту. Удовольствие для глаз! #housebuilding #дома #buildingprocess #timelapse #beforeafter",
        ],
        "tags": ["строительство дома", "таймлапс", "частный дом", "дом", "стройка", "satisfying", "timelapse", "загородный дом", "home build", "timelapse дома"],
    },
    "en": {
        "titles": [
            "House Build: From Empty Land to {style} 🏠 #timelapse #beforeafter",
            "{style} Build Timelapse: Complete Construction #timelapse #beforeafter",
            "From Nothing to {style}: Full Build Process 🔨 #timelapse #beforeafter",
            "House Construction Timelapse: {style} in {location} #timelapse #beforeafter",
        ],
        "descriptions": [
            "Watch a beautiful house rise from an empty plot. Full construction process in timelapse! #housebuilding #home #buildingprocess #timelapse #beforeafter",
            "From foundation to roof - the entire house building process in one minute. Satisfying to watch! #housebuilding #home #buildingprocess #timelapse #beforeafter",
        ],
        "tags": ["house construction timelapse", "home build", "single family home", "house build", "before after", "satisfying", "transformation", "timelapse", "residential build", "private house"],
    },
}


def _generate_fallback_metadata(
    house_style: str,
    location: str,
    stages: list[dict],
    title: str,
    language: str = "en",
) -> dict[str, Any]:
    """Generate fallback metadata using templates."""
    templates = FALLBACK_TEMPLATES.get(language, FALLBACK_TEMPLATES["en"])
    
    style_name = house_style.replace("_", " ").title() if house_style else "House"
    loc_name = location.replace("_", " ").title() if location else "Suburbs"
    
    # Pick random template
    title_template = random.choice(templates["titles"])
    generated_title = title_template.format(style=style_name, location=loc_name)
    
    description = random.choice(templates["descriptions"])
    tags = templates["tags"]
    
    return {
        "title": generated_title,
        "description": description,
        "tags": tags,
    }


async def generate_publishing_metadata(
    house_style: str,
    location: str,
    stages: list[dict],
    title: str,
    language: str = "en",
    force_title: str | None = None,  # NEW: Override generated title
) -> dict[str, Any]:
    """
    Generate publishing metadata for YouTube Shorts.
    
    Args:
        house_style: House style (modern, cottage, villa, etc.)
        location: Location (suburbs, forest, seaside, etc.)
        stages: List of building stages
        title: Video title from scenario
        language: Output language ("ru" or "en")

    Returns:
        dict with title, description, tags
    """
    # Ensure we always return valid metadata - wrap everything in try-except
    try:
        # Build stages description
        stages_desc = ""
        if stages:
            stage_names = [s.get("name_en" if language == "en" else "name", f"Stage {i+1}") for i, s in enumerate(stages)]
            stages_desc = " → ".join(stage_names[:6])  # First 6 stages
        
        prompt = PUBLISHING_PROMPT.format(
            house_style=house_style.replace("_", " ").title() if house_style else "House",
            location=location.replace("_", " ").title() if location else "Suburbs",
            stages_description=stages_desc or "Construction stages",
            title=title or "House Building",
            language=language,
        )
        
        try:
            llm = make_llm(temperature=0.8)
            messages = [
                SystemMessage(content="You are a YouTube Shorts SEO expert. Generate viral, clickable metadata optimized for the algorithm."),
                HumanMessage(content=prompt),
            ]
            try:
                response = await asyncio.wait_for(llm.ainvoke(messages), timeout=30.0)
            except asyncio.TimeoutError:
                logger.warning(f"[Mode8 Publishing] Metadata generation timeout (30s), using fallback")
                raise Exception("Timeout")
            raw = response.content.strip() if hasattr(response, 'content') else str(response)
            
            # Strip markdown code fences if present
            if raw.startswith("```"):
                lines = raw.splitlines()
                raw = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
            
            # Try to extract JSON
            json_match = re.search(r"\{[\s\S]*\}", raw)
            if json_match:
                result = json.loads(json_match.group())
                if result:
                    # Force override title if provided
                    if force_title:
                        result["title"] = force_title
                    logger.success(f"[Mode8 Publishing] Generated metadata: {result.get('title', 'N/A')}")
                    return result
        except Exception as e:
            logger.warning(f"[Mode8 Publishing] LLM failed, using fallback: {e}")
        
        # Fallback
        fallback_result = _generate_fallback_metadata(house_style, location, stages, title, language)
        # Force override title if provided
        if force_title:
            fallback_result["title"] = force_title
        return fallback_result
    except Exception as e:
        # Ultimate fallback if anything fails
        logger.error(f"[Mode8 Publishing] All methods failed: {e}")
        lang_hashtags = "#housebuilding #дома #buildingprocess #timelapse #beforeafter" if language == "ru" else "#housebuilding #home #buildingprocess #timelapse #beforeafter"
        return {
            "title": force_title or f"House Building Timelapse {house_style or ''} {location or ''} #timelapse #beforeafter".strip(),
            "description": f"Watch the complete house building process in this satisfying timelapse. {lang_hashtags}",
            "tags": ["house construction", "timelapse", "building", "satisfying"],
        }
