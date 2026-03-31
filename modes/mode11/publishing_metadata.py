"""
Mode 11 Publishing Metadata Generator.

Generates YouTube Shorts publishing metadata for monument reverse-timelapse videos.
No house-specific fallbacks.
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


PUBLISHING_PROMPT = """Generate final YouTube Shorts publishing content for a monument timelapse video.

VIDEO CONTEXT:
- Monument: {monument}
- Location: {location}
- Stages: {stages_description}
- Title: {title}

OUTPUT STRUCTURE:

1. TITLE (for Shorts)
- Short and attention-grabbing
- First 2 words must be strong monument/timelapse keywords (e.g. "Monument Timelapse", "Ancient Wonder", "Reverse Build")
- Clearly reflect transformation (empty/ruins -> complete monument)
- Max 1 emoji at the end (relevant to construction)
- Always end with exactly 2 hashtags: #timelapse #beforeafter

2. DESCRIPTION
- First line: 1 short sentence describing monument reconstruction/reveal
- Then naturally include 4-5 keywords:
  (monument timelapse, reverse transformation, historical architecture, restoration vibe, before after)
- Text must read naturally, not like keyword spam
- At the end of description, always add exactly these 5 hashtags:
  - For Russian: #monument #история #architecture #timelapse #beforeafter
  - For English: #monument #history #architecture #timelapse #beforeafter

CONTENT RULES:
- Focus on visual transformation and iconic monument identity
- Keep style suitable for Shorts feed
- No misleading clickbait claims
- No spam keyword stuffing

OUTPUT FORMAT (JSON):

{{
  "title": "...",
  "description": "...",
  "tags": ["tag1", "tag2", ...]
}}

Language: {language}. Return JSON only.
"""


# Fallback templates if LLM fails
FALLBACK_TEMPLATES = {
    "ru": {
        "titles": [
            "Монумент Timelapse: {monument} от пустоты к легенде 🏛️ #timelapse #beforeafter",
            "{monument} за секунды: обратная трансформация #timelapse #beforeafter",
            "Как появляется {monument} в {location} #timelapse #beforeafter",
            "Историческая архитектура: {monument} в timelapse #timelapse #beforeafter",
        ],
        "descriptions": [
            "Смотрите, как пустое пространство превращается в культовый монумент в формате timelapse. #monument #история #architecture #timelapse #beforeafter",
            "Визуальная реконструкция знаменитого сооружения: этапы от руин к целостному виду. #monument #история #architecture #timelapse #beforeafter",
        ],
        "tags": ["монумент", "история", "архитектура", "таймлапс", "before after", "reconstruction", "ancient wonder", "restoration vibe"],
    },
    "en": {
        "titles": [
            "Monument Timelapse: {monument} From Empty to Icon 🏛️ #timelapse #beforeafter",
            "{monument} Reverse Transformation in Seconds #timelapse #beforeafter",
            "From Ruins to Wonder: {monument} Timelapse #timelapse #beforeafter",
            "Historical Architecture Reveal: {monument} in {location} #timelapse #beforeafter",
        ],
        "descriptions": [
            "Watch empty space transform into an iconic monument in a satisfying timelapse sequence. #monument #history #architecture #timelapse #beforeafter",
            "A reverse-to-complete monument transformation with cinematic historical architecture vibes. #monument #history #architecture #timelapse #beforeafter",
        ],
        "tags": ["monument timelapse", "history", "architecture", "before after", "reverse transformation", "reconstruction", "ancient wonder", "cinematic timelapse"],
    },
}


def _generate_fallback_metadata(
    monument: str,
    location: str,
    stages: list[dict],
    title: str,
    language: str = "en",
) -> dict[str, Any]:
    """Generate fallback metadata using templates."""
    templates = FALLBACK_TEMPLATES.get(language, FALLBACK_TEMPLATES["en"])
    
    monument_name = monument.replace("_", " ").title() if monument else "Monument"
    loc_name = location.replace("_", " ").title() if location else "Suburbs"
    
    # Pick random template
    title_template = random.choice(templates["titles"])
    generated_title = title_template.format(monument=monument_name, location=loc_name)
    
    description = random.choice(templates["descriptions"])
    tags = templates["tags"]
    
    return {
        "title": generated_title,
        "description": description,
        "tags": tags,
    }


async def generate_publishing_metadata(
    structure_type: str,
    location: str,
    stages: list[dict],
    title: str,
    language: str = "en",
    force_title: str | None = None,  # NEW: Override generated title
) -> dict[str, Any]:
    """
    Generate publishing metadata for YouTube Shorts.
    
    Args:
        structure_type: Monument key (e.g. colosseum, eiffel_tower)
        location: Monument location name
        stages: List of scenario stages
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
            stages_desc = " → ".join(stage_names[:8])
        
        prompt = PUBLISHING_PROMPT.format(
            monument=structure_type.replace("_", " ").title() if structure_type else "Monument",
            location=location.replace("_", " ").title() if location else "Suburbs",
            stages_description=stages_desc or "Construction stages",
            title=title or "Monument Timelapse",
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
                logger.warning(f"[Mode11 Publishing] Metadata generation timeout (30s), using fallback")
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
                    result.setdefault("tags", FALLBACK_TEMPLATES.get(language, FALLBACK_TEMPLATES["en"])["tags"])
                    # Force override title if provided
                    if force_title:
                        result["title"] = force_title
                    logger.success(f"[Mode11 Publishing] Generated metadata: {result.get('title', 'N/A')}")
                    return result
        except Exception as e:
            logger.warning(f"[Mode11 Publishing] LLM failed, using fallback: {e}")
        
        # Fallback
        fallback_result = _generate_fallback_metadata(structure_type, location, stages, title, language)
        # Force override title if provided
        if force_title:
            fallback_result["title"] = force_title
        return fallback_result
    except Exception as e:
        # Ultimate fallback if anything fails
        logger.error(f"[Mode11 Publishing] All methods failed: {e}")
        lang_hashtags = "#monument #история #architecture #timelapse #beforeafter" if language == "ru" else "#monument #history #architecture #timelapse #beforeafter"
        return {
            "title": force_title or f"Monument Reverse Timelapse {structure_type or ''} {location or ''} #timelapse #beforeafter".strip(),
            "description": f"Watch workers build and restore this world landmark in a satisfying construction timelapse. {lang_hashtags}",
            "tags": FALLBACK_TEMPLATES.get(language, FALLBACK_TEMPLATES["en"])["tags"],
        }
