"""
Mode 9 Publishing Metadata Generator.

YouTube Shorts metadata for vehicle and machinery assembly timelapse videos.
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

_HASHTAGS_RU = ["#Shorts", "#timelapse", "#сборка", "#beforeafter", "#машины"]
_HASHTAGS_EN = ["#Shorts", "#timelapse", "#assembly", "#beforeafter", "#machinebuild"]
_TAGS_RU = [
    "сборка транспорта",
    "таймлапс сборки",
    "сборка машины",
    "как собирают",
    "автомобиль сборка",
    "производство техники",
    "заводской процесс",
    "машина до после",
    "vehicle assembly",
    "assembly timelapse",
]
_TAGS_EN = [
    "vehicle assembly",
    "vehicle assembly timelapse",
    "machine build",
    "how its made vehicle",
    "factory assembly",
    "manufacturing process",
    "parts to vehicle",
    "before after assembly",
    "engineering timelapse",
    "assembly satisfying",
]

PUBLISHING_PROMPT = """Create YouTube Shorts metadata for a vehicle or machinery assembly timelapse.

VIDEO CONTEXT:
- Vehicle type: {vehicle_type}
- Location: {location}
- Assembly stages: {stages_description}
- Working title: {title}

BEST PRACTICE TARGET:
- Title: 40-58 chars, no hashtags, no spam, clear build/transformation hook.
- Put the core searchable phrase early (vehicle assembly / machine build / timelapse).
- Description: 2 short paragraphs, first 120-160 chars should clearly describe the video.
- Hashtags: 3-5 only.
- Tags: 8-12 focused Studio tags with search intent, no duplicates.
- Tone: precision, engineering, satisfying transformation.

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


def _fallback_payload(vehicle_type: str, location: str, title: str, language: str) -> dict[str, Any]:
    vehicle_name = vehicle_type.replace("_", " ").title() if vehicle_type else ("транспорт" if language == "ru" else "vehicle")
    loc_name = location.replace("_", " ").title() if location else ("цех" if language == "ru" else "factory")
    if language == "ru":
        return {
            "title": f"Сборка машины: от деталей к финалу",
            "description": (
                f"Из деталей в готовый {vehicle_name.lower()} — весь процесс в коротком assembly timelapse.\n\n"
                f"Рама, узлы, двигатель и финальная сборка в {loc_name}: чистая инженерная трансформация без лишнего текста."
            ),
            "hashtags": _HASHTAGS_RU,
            "tags": _TAGS_RU,
            "first_comment": "Какой этап выглядит мощнее всего: рама, двигатель или момент финальной сборки?",
        }
    return {
        "title": "Vehicle Assembly: From Parts to Final",
        "description": (
            f"From loose parts to a finished {vehicle_name.lower()} — the full assembly in a short timelapse.\n\n"
            f"Frame, core components, and final build in {loc_name}: a clean engineering transformation with satisfying progression."
        ),
        "hashtags": _HASHTAGS_EN,
        "tags": _TAGS_EN,
        "first_comment": "Which stage do you enjoy most in assembly videos: frame-up, engine install, or the final completed machine?",
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
    vehicle_type: str,
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
        stages_desc = " -> ".join(stage_names[:6]) or "frame -> components -> engine -> body -> final machine"
        prompt = PUBLISHING_PROMPT.format(
            vehicle_type=vehicle_type.replace("_", " ").title() if vehicle_type else "Vehicle",
            location=location.replace("_", " ").title() if location else "Factory",
            stages_description=stages_desc,
            title=title or "Vehicle Assembly",
            language=language,
        )
        fallback = _fallback_payload(vehicle_type, location, title, language)
        try:
            llm = make_llm(temperature=0.55)
            response = await asyncio.wait_for(
                llm.ainvoke(
                    [
                        SystemMessage(
                            content="You are a YouTube Shorts metadata strategist. Write concise hooks, natural descriptions, and focused tags. Use 3-5 hashtags max."
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
                    logger.success(f"[Mode9 Publishing] Generated metadata: {result.get('title', 'N/A')}")
                    return result
        except Exception as e:
            logger.warning(f"[Mode9 Publishing] LLM failed, using fallback: {e}")
        return _finalize({}, fallback=fallback, force_title=force_title)
    except Exception as e:
        logger.error(f"[Mode9 Publishing] All methods failed: {e}")
        return _finalize({}, fallback=_fallback_payload(vehicle_type, location, title, language), force_title=force_title)
