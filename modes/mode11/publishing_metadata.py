"""
Mode 11 Publishing Metadata Generator.

YouTube Shorts metadata for monument reconstruction / reverse timelapse videos.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from utils.llm import make_llm
from utils.publishing_metadata import finalize_metadata, hashtags_from_text

_HASHTAGS_RU = ["#Shorts", "#timelapse", "#история", "#архитектура", "#beforeafter"]
_HASHTAGS_EN = ["#Shorts", "#timelapse", "#history", "#architecture", "#beforeafter"]
_TAGS_RU = [
    "монумент timelapse",
    "историческая архитектура",
    "реконструкция монумента",
    "до после архитектура",
    "визуальная история",
    "архитектура shorts",
    "знаменитые сооружения",
    "таймлапс история",
    "ancient wonder",
    "monument reconstruction",
]
_TAGS_EN = [
    "monument timelapse",
    "historical architecture",
    "monument reconstruction",
    "before after monument",
    "ancient wonder",
    "history shorts",
    "architectural transformation",
    "reverse timelapse",
    "iconic landmark",
    "cinematic monument",
]

PUBLISHING_PROMPT = """Create YouTube Shorts metadata for a monument reconstruction or reverse timelapse video.

VIDEO CONTEXT:
- Monument: {monument}
- Location: {location}
- Stages: {stages_description}
- Working title: {title}

BEST PRACTICE TARGET:
- Title: 40-58 chars, no hashtags, clear landmark + transformation hook.
- Front-load the searchable phrase (monument / history / architecture / reconstruction).
- Description: 2 short paragraphs, informative opening, natural keywords, no spam.
- Hashtags: 3-5 only.
- Tags: 8-12 focused Studio tags, no filler or duplicates.
- Tone: iconic, historical, visually satisfying, honest.

Return JSON only:
{{
  "title": "...",
  "description": "...",
  "hashtags": ["#Shorts", "#timelapse", "..."],
  "tags": ["...", "..."],
  "first_comment": "..."
}}

Language: {language}
"""


def _fallback_payload(structure_type: str, location: str, title: str, language: str) -> dict[str, Any]:
    monument_name = structure_type.replace("_", " ").title() if structure_type else ("монумент" if language == "ru" else "monument")
    loc_name = location.replace("_", " ").title() if location else ("историческая локация" if language == "ru" else "historic site")
    if language == "ru":
        return {
            "title": f"{monument_name}: визуальная реконструкция",
            "description": (
                f"Знаковый {monument_name.lower()} проходит путь от пустоты или руин к цельному образу в коротком timelapse.\n\n"
                f"Историческая архитектура, поэтапная сборка и финальный reveal в {loc_name} без лишнего кликбейта."
            ),
            "hashtags": _HASHTAGS_RU,
            "tags": _TAGS_RU,
            "first_comment": "Какой монумент или историческое сооружение вы бы хотели увидеть в такой же реконструкции следующим?",
        }
    return {
        "title": f"{monument_name}: Reconstruction Timelapse",
        "description": (
            f"An iconic {monument_name.lower()} moves from emptiness or ruins to a full visual reveal in a short timelapse.\n\n"
            f"Historical architecture, staged reconstruction, and a clean final payoff in {loc_name} without fake hype."
        ),
        "hashtags": _HASHTAGS_EN,
        "tags": _TAGS_EN,
        "first_comment": "Which landmark or ancient structure would you want to see reconstructed next in this format?",
    }


def _finalize(raw: dict[str, Any], *, fallback: dict[str, Any], force_title: str | None = None) -> dict[str, Any]:
    title = force_title or raw.get("title") or fallback["title"]
    description = raw.get("description") or fallback["description"]
    hashtags = raw.get("hashtags") or hashtags_from_text(description) or fallback["hashtags"]
    tags = raw.get("tags") or fallback["tags"]
    return finalize_metadata(
        title=title,
        description=description,
        tags=tags,
        hashtags=hashtags,
        fallback_title=force_title or fallback["title"],
        fallback_description=fallback["description"],
        fallback_tags=fallback["tags"],
        fallback_hashtags=fallback["hashtags"],
        first_comment=raw.get("first_comment") or fallback.get("first_comment"),
    )


async def generate_publishing_metadata(
    structure_type: str,
    location: str,
    stages: list[dict],
    title: str,
    language: str = "en",
    force_title: str | None = None,
) -> dict[str, Any]:
    language = "ru" if language == "ru" else "en"
    try:
        stage_names = [
            s.get("name_en" if language == "en" else "name", f"Stage {i + 1}")
            for i, s in enumerate(stages or [])
        ]
        stages_desc = " -> ".join(stage_names[:8]) or "ruins -> reconstruction -> completed monument"
        prompt = PUBLISHING_PROMPT.format(
            monument=structure_type.replace("_", " ").title() if structure_type else "Monument",
            location=location.replace("_", " ").title() if location else "Historic Site",
            stages_description=stages_desc,
            title=title or "Monument Timelapse",
            language=language,
        )
        fallback = _fallback_payload(structure_type, location, title, language)
        try:
            llm = make_llm(temperature=0.55)
            response = await asyncio.wait_for(
                llm.ainvoke(
                    [
                        SystemMessage(
                            content="You are a YouTube Shorts metadata strategist. Write specific, non-spammy monument/history metadata with 3-5 hashtags max."
                        ),
                        HumanMessage(content=prompt),
                    ]
                ),
                timeout=30.0,
            )
            raw = response.content.strip() if hasattr(response, "content") else str(response)
            if raw.startswith("```"):
                lines = raw.splitlines()
                raw = "\n".join(lines[1:-1] if lines and lines[-1].startswith("```") else lines[1:])
            match = re.search(r"\{[\s\S]*\}", raw)
            if match:
                data = json.loads(match.group())
                if isinstance(data, dict):
                    result = _finalize(data, fallback=fallback, force_title=force_title)
                    logger.success(f"[Mode11 Publishing] Generated metadata: {result.get('title', 'N/A')}")
                    return result
        except Exception as e:
            logger.warning(f"[Mode11 Publishing] LLM failed, using fallback: {e}")
        return _finalize({}, fallback=fallback, force_title=force_title)
    except Exception as e:
        logger.error(f"[Mode11 Publishing] All methods failed: {e}")
        return _finalize({}, fallback=_fallback_payload(structure_type, location, title, language), force_title=force_title)
