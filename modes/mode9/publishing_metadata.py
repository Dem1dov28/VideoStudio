"""
Mode 9 Publishing Metadata Generator.

Generates Title, Description, Hashtags, Tags for YouTube Shorts
based on the vehicle assembly timelapse video content.
"""

from __future__ import annotations

import json
import random
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger
from utils.llm import make_llm


PUBLISHING_PROMPT = """Generate final YouTube Shorts publishing content for a video about vehicle assembly (building cars, airplanes, tractors, machinery).

VIDEO CONTEXT:
- Vehicle Type: {vehicle_type}
- Location: {location}
- Stages: {stages_description}
- Title: {title}

OUTPUT STRUCTURE:

1. TITLE
- Short, attention-grabbing
- First 2 words must be strong keywords related to assembly (e.g. "Vehicle Build", "Assembly Timelapse", "Machine Build")
- Clearly reflect transformation (parts → finished vehicle)
- Max 1 emoji at the end (relevant to vehicles or tools)
- Always end with exactly 2 hashtags: #timelapse #beforeafter

2. DESCRIPTION
- First line: 1 short sentence describing the transformation (e.g. from chassis to powerful machine)
- Then naturally include 4-5 keywords:
  (vehicle assembly, timelapse build, factory process, machine transformation, how it's made)
- Text must read naturally, not like keyword spam
- At the end of description, always add exactly these 5 hashtags:
  - For Russian: #assembly #сборка #vehiclebuild #timelapse #beforeafter
  - For English: #assembly #vehiclebuild #machinery #timelapse #beforeafter

CONTENT RULES:

- Focus on process, not just result
- Emphasize transformation and engineering precision
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
            "Сборка транспорта: от деталей до готовой машины 🚗 #timelapse #beforeafter",
            "{style} за 60 секунд: полная сборка #timelapse #beforeafter",
            "От рамы до машины: {style} в {location} 🔧 #timelapse #beforeafter",
            "Таймлапс сборки: как собрали {style} #timelapse #beforeafter",
        ],
        "descriptions": [
            "Смотрите как из отдельных деталей рождается готовый транспорт. Полный процесс сборки в таймлапсе! #assembly #сборка #vehiclebuild #timelapse #beforeafter",
            "От шасси до двигателя — весь процесс сборки машины за минуту. Удовольствие для глаз! #assembly #сборка #vehiclebuild #timelapse #beforeafter",
        ],
        "tags": ["сборка транспорта", "таймлапс", "сборка", "машина", "автомобиль", "satisfying", "timelapse", "assembly", "vehicle", "factory"],
    },
    "en": {
        "titles": [
            "Vehicle Build: From Parts to {style} 🚗 #timelapse #beforeafter",
            "{style} Assembly Timelapse: Complete Build #timelapse #beforeafter",
            "From Frame to {style}: Full Assembly Process 🔧 #timelapse #beforeafter",
            "Vehicle Assembly Timelapse: {style} in {location} #timelapse #beforeafter",
        ],
        "descriptions": [
            "Watch a complete vehicle come together from individual parts. Full assembly process in timelapse! #assembly #vehiclebuild #machinery #timelapse #beforeafter",
            "From chassis to engine - the entire vehicle assembly process in one minute. Satisfying to watch! #assembly #vehiclebuild #machinery #timelapse #beforeafter",
        ],
        "tags": ["vehicle assembly timelapse", "assembly process", "manufacturing", "vehicle build", "before after", "satisfying", "transformation", "timelapse", "factory", "production"],
    },
}


def _generate_fallback_metadata(
    vehicle_type: str,
    location: str,
    stages: list[dict],
    title: str,
    language: str = "en",
) -> dict[str, Any]:
    """Generate fallback metadata using templates."""
    templates = FALLBACK_TEMPLATES.get(language, FALLBACK_TEMPLATES["en"])
    
    style_name = vehicle_type.replace("_", " ").title() if vehicle_type else "Vehicle"
    loc_name = location.replace("_", " ").title() if location else "Factory"
    
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
    vehicle_type: str,
    location: str,
    stages: list[dict],
    title: str,
    language: str = "en",
) -> dict[str, Any]:
    """
    Generate publishing metadata for YouTube Shorts.
    
    Args:
        vehicle_type: Vehicle type (car, airplane, tractor, etc.)
        location: Location (factory, hangar, workshop, etc.)
        stages: List of assembly stages
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
            vehicle_type=vehicle_type.replace("_", " ").title() if vehicle_type else "Vehicle",
            location=location.replace("_", " ").title() if location else "Factory",
            stages_description=stages_desc or "Assembly stages",
            title=title or "Vehicle Assembly",
            language=language,
        )
        
        try:
            llm = make_llm(temperature=0.8)
            messages = [
                SystemMessage(content="You are a YouTube Shorts SEO expert. Generate viral, clickable metadata optimized for the algorithm."),
                HumanMessage(content=prompt),
            ]
            response = await llm.ainvoke(messages)
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
                    logger.success(f"[Mode9 Publishing] Generated metadata: {result.get('title', 'N/A')}")
                    return result
        except Exception as e:
            logger.warning(f"[Mode9 Publishing] LLM failed, using fallback: {e}")
        
        # Fallback
        return _generate_fallback_metadata(vehicle_type, location, stages, title, language)
    except Exception as e:
        # Ultimate fallback if anything fails
        logger.error(f"[Mode9 Publishing] All methods failed: {e}")
        lang_hashtags = "#assembly #сборка #vehiclebuild #timelapse #beforeafter" if language == "ru" else "#assembly #vehiclebuild #machinery #timelapse #beforeafter"
        return {
            "title": f"Vehicle Assembly Timelapse {vehicle_type or ''} {location or ''} #timelapse #beforeafter".strip(),
            "description": f"Watch the complete vehicle assembly process in this satisfying timelapse. {lang_hashtags}",
            "tags": ["vehicle assembly", "timelapse", "manufacturing", "satisfying"],
        }
