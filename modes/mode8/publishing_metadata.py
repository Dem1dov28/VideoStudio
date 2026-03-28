"""
Mode 8 Publishing Metadata Generator.

Generates Title, Description, Hashtags, Tags for YouTube Shorts
based on the house building timelapse video content.
"""

from __future__ import annotations

import json
import random
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger
from utils.llm import make_llm


PUBLISHING_PROMPT = """Generate final YouTube Shorts publishing content for a video about construction and transformation (building houses, objects, restoration).

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
- Max 2-3 hashtags at the end (no spam)

2. DESCRIPTION
- First line: 1 short sentence describing the transformation (e.g. from empty land to house)
- Then naturally include 4-5 keywords:
  (construction timelapse, building process, house build, before after, transformation)
- Text must read naturally, not like keyword spam

3. HASHTAGS (separate block)
- Add 4-5 relevant hashtags only
- Focus on niche:
  #construction #timelapse #beforeafter #building #satisfying

4. TAGS (for YouTube Studio)
- 10-15 tags
- Mix of:
  - specific (house construction timelapse)
  - general (construction, building)
  - viral (satisfying, transformation)
  - include channel name

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
  "hashtags": ["#tag1", "#tag2", ...],
  "tags": ["tag1", "tag2", ...]
}}

Language: {language}
"""


# Fallback templates if LLM fails
FALLBACK_TEMPLATES = {
    "ru": {
        "titles": [
            "Строительство дома: от пустого участка до готового {style} 🏠 #строительство #таймлапс",
            "{style} за 60 секунд: полная стройка #timelapse #construction",
            "От земли до дома: {style} в {location} 🔨 #строительство",
            "Таймлапс стройки: как построили {style} #building #satisfying",
        ],
        "descriptions": [
            "Смотрите как из пустого участка рождается красивый дом. Полный процесс строительства в таймлапсе!",
            "От котлована до крыши — весь процесс постройки дома за минуту. Удовольствие для глаз!",
        ],
        "hashtags": ["#строительство", "#таймлапс", "#дом", "#стройка", "#satisfying"],
        "tags": ["строительство дома", "таймлапс", "строительство", "дом", "стройка", "satisfying", "timelapse", "постройка", "renovation", "building"],
    },
    "en": {
        "titles": [
            "House Build: From Empty Land to {style} 🏠 #construction #timelapse",
            "{style} Build Timelapse: Complete Construction #satisfying",
            "From Nothing to {style}: Full Build Process 🔨 #construction",
            "House Construction Timelapse: {style} in {location} #building",
        ],
        "descriptions": [
            "Watch a beautiful house rise from an empty plot. Full construction process in timelapse!",
            "From foundation to roof - the entire house building process in one minute. Satisfying to watch!",
        ],
        "hashtags": ["#construction", "#timelapse", "#housebuild", "#beforeafter", "#satisfying"],
        "tags": ["house construction timelapse", "building process", "construction", "house build", "before after", "satisfying", "transformation", "timelapse", "home building", "construction site"],
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
    hashtags = templates["hashtags"]
    tags = templates["tags"]
    
    return {
        "title": generated_title,
        "description": description,
        "hashtags": hashtags,
        "tags": tags,
    }


async def generate_publishing_metadata(
    house_style: str,
    location: str,
    stages: list[dict],
    title: str,
    language: str = "en",
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
                    logger.success(f"[Mode8 Publishing] Generated metadata: {result.get('title', 'N/A')}")
                    return result
        except Exception as e:
            logger.warning(f"[Mode8 Publishing] LLM failed, using fallback: {e}")
        
        # Fallback
        return _generate_fallback_metadata(house_style, location, stages, title, language)
    except Exception as e:
        # Ultimate fallback if anything fails
        logger.error(f"[Mode8 Publishing] All methods failed: {e}")
        return {
            "title": f"House Building Timelapse {house_style or ''} {location or ''}".strip(),
            "description": "Watch the complete house building process in this satisfying timelapse.",
            "hashtags": ["#construction", "#timelapse", "#housebuild", "#satisfying"],
            "tags": ["house construction", "timelapse", "building", "satisfying"],
        }
