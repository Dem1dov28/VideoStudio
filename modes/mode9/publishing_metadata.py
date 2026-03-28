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
- Max 2-3 hashtags at the end (no spam)

2. DESCRIPTION
- First line: 1 short sentence describing the transformation (e.g. from chassis to powerful machine)
- Then naturally include 4-5 keywords:
  (vehicle assembly, timelapse build, factory process, machine transformation, how it's made)
- Text must read naturally, not like keyword spam

3. HASHTAGS (separate block)
- Add 4-5 relevant hashtags only
- Focus on niche:
  #assembly #timelapse #mechanic #factory #satisfying

4. TAGS (for YouTube Studio)
- 10-15 tags
- Mix of:
  - specific (vehicle assembly timelapse)
  - general (manufacturing, assembly)
  - viral (satisfying, engineering)
  - include channel name

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
  "hashtags": ["#tag1", "#tag2", ...],
  "tags": ["tag1", "tag2", ...]
}}

Language: {language}
"""


# Fallback templates if LLM fails
FALLBACK_TEMPLATES = {
    "ru": {
        "titles": [
            "Сборка транспорта: от деталей до готовой машины 🚗 #сборка #таймлапс",
            "{style} за 60 секунд: полная сборка #timelapse #assembly",
            "От рамы до машины: {style} в {location} 🔧 #сборка",
            "Таймлапс сборки: как собрали {style} #assembly #satisfying",
        ],
        "descriptions": [
            "Смотрите как из отдельных деталей рождается готовый транспорт. Полный процесс сборки в таймлапсе!",
            "От шасси до двигателя — весь процесс сборки машины за минуту. Удовольствие для глаз!",
        ],
        "hashtags": ["#сборка", "#таймлапс", "#транспорт", "#машина", "#satisfying"],
        "tags": ["сборка транспорта", "таймлапс", "сборка", "машина", "автомобиль", "satisfying", "timelapse", "assembly", "vehicle", "factory"],
    },
    "en": {
        "titles": [
            "Vehicle Build: From Parts to {style} 🚗 #assembly #timelapse",
            "{style} Assembly Timelapse: Complete Build #satisfying",
            "From Frame to {style}: Full Assembly Process 🔧 #assembly",
            "Vehicle Assembly Timelapse: {style} in {location} #factory",
        ],
        "descriptions": [
            "Watch a complete vehicle come together from individual parts. Full assembly process in timelapse!",
            "From chassis to engine - the entire vehicle assembly process in one minute. Satisfying to watch!",
        ],
        "hashtags": ["#assembly", "#timelapse", "#vehiclebuild", "#beforeafter", "#satisfying"],
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
    hashtags = templates["hashtags"]
    tags = templates["tags"]
    
    return {
        "title": generated_title,
        "description": description,
        "hashtags": hashtags,
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
        dict with title, description, hashtags, tags
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
        return {
            "title": f"Vehicle Assembly Timelapse {vehicle_type or ''} {location or ''}".strip(),
            "description": "Watch the complete vehicle assembly process in this satisfying timelapse.",
            "hashtags": ["#assembly", "#timelapse", "#vehiclebuild", "#satisfying"],
            "tags": ["vehicle assembly", "timelapse", "manufacturing", "satisfying"],
        }
