"""
Mode 8 Publishing Metadata Generator.

YouTube Shorts metadata for private house construction timelapse videos.
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

_HASHTAGS_RU = ["#Shorts", "#timelapse", "#строительстводома", "#beforeafter", "#стройка"]
_HASHTAGS_EN = ["#Shorts", "#timelapse", "#housebuild", "#beforeafter", "#construction"]
_TAGS_RU = [
    "строительство дома",
    "таймлапс стройки",
    "частный дом",
    "дом до после",
    "процесс строительства",
    "загородный дом",
    "строительство коттеджа",
    "стройка satisfying",
    "house build",
    "before after house",
]
_TAGS_EN = [
    "house build",
    "house construction timelapse",
    "single family home",
    "before after house",
    "building process",
    "residential construction",
    "home build timelapse",
    "construction satisfying",
    "plot to house",
    "private house build",
]

PUBLISHING_PROMPT = """Create YouTube Shorts metadata for a private house construction timelapse.

VIDEO CONTEXT:
- House style: {house_style}
- Location: {location}
- Build stages: {stages_description}
- Working title: {title}

BEST PRACTICE TARGET:
- Title: 40-58 chars, no hashtags, no keyword stuffing, clear transformation hook.
- Front-load the core keyword in the title (house build / construction / timelapse).
- Description: 2 short paragraphs, informative first 120-160 chars, natural keywords, no spam.
- Hashtags: 3-5 only, for description block only.
- Tags: 8-12 focused YouTube Studio tags, no filler, no duplicates.
- Tone: satisfying transformation, progress, craftsmanship, realism.

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


def _fallback_payload(
    house_style: str,
    location: str,
    title: str,
    language: str,
) -> dict[str, Any]:
    style_name = house_style.replace("_", " ").title() if house_style else ("дом" if language == "ru" else "house")
    loc_name = location.replace("_", " ").title() if location else ("пригород" if language == "ru" else "suburbs")
    if language == "ru":
        return {
            "title": f"Таймлапс стройки: {style_name} с нуля",
            "description": (
                f"Из пустого участка в готовый {style_name.lower()} — весь путь в коротком timelapse.\n\n"
                f"Фундамент, стены, крыша и финальный вид дома в {loc_name}: чистая визуальная трансформация без воды."
            ),
            "hashtags": _HASHTAGS_RU,
            "tags": _TAGS_RU,
            "first_comment": (
                "На каком этапе стройка выглядит для вас самым satisfying моментом: фундамент, коробка или финальная отделка?"
            ),
        }
    return {
        "title": f"House Build Timelapse: From Plot to Home",
        "description": (
            f"From an empty plot to a finished {style_name.lower()} — the full build in a short timelapse.\n\n"
            f"Foundation, walls, roof, and final reveal in {loc_name}: a clean before-after construction transformation."
        ),
        "hashtags": _HASHTAGS_EN,
        "tags": _TAGS_EN,
        "first_comment": (
            "Which stage is the most satisfying to watch for you: foundation, framing, or the final reveal?"
        ),
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
    house_style: str,
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
        stages_desc = " -> ".join(stage_names[:6]) or "foundation -> walls -> roof -> finished home"
        prompt = PUBLISHING_PROMPT.format(
            house_style=house_style.replace("_", " ").title() if house_style else "House",
            location=location.replace("_", " ").title() if location else "Suburbs",
            stages_description=stages_desc,
            title=title or "House Building",
            language=language,
        )
        fallback = _fallback_payload(house_style, location, title, language)
        try:
            llm = make_llm(temperature=0.55)
            response = await asyncio.wait_for(
                llm.ainvoke(
                    [
                        SystemMessage(
                            content="You are a YouTube Shorts metadata strategist. Favor clear hooks, concise titles, natural SEO, and 3-5 hashtags max."
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
                    logger.success(f"[Mode8 Publishing] Generated metadata: {result.get('title', 'N/A')}")
                    return result
        except Exception as e:
            logger.warning(f"[Mode8 Publishing] LLM failed, using fallback: {e}")
        return _finalize({}, fallback=fallback, force_title=force_title)
    except Exception as e:
        logger.error(f"[Mode8 Publishing] All methods failed: {e}")
        return _finalize({}, fallback=_fallback_payload(house_style, location, title, language), force_title=force_title)
