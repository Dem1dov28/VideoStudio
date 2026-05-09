from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from config import settings
from utils.llm import make_llm
from utils.publishing_metadata import finalize_metadata, hashtags_from_text

_HASHTAGS_RU = ["#сон", "#релакс", "#медитация", "#успокаивающе", "#sleepvideo"]
_HASHTAGS_EN = ["#sleep", "#relax", "#meditation", "#calm", "#sleepvideo"]
_TAGS_RU = [
    "факты перед сном",
    "успокаивающий рассказ",
    "длинное видео для сна",
    "расслабляющий фон",
    "медленный образовательный контент",
    "sleep facts",
    "calm documentary",
    "ночной релакс",
    "атмосферное видео для сна",
    "background for sleep",
]
_TAGS_EN = [
    "sleep facts",
    "calm documentary",
    "long form sleep video",
    "relaxing narration",
    "ambient educational content",
    "bedtime facts",
    "soft spoken style",
    "night background video",
    "slow paced storytelling",
    "sleep meditation video",
]

_PUBLISHING_PROMPT = """Create YouTube metadata for a long-form sleep-oriented video.

VIDEO CONTEXT:
- Topic/title: {topic}
- Sub-mode: {sub_mode}
- Approx duration (minutes): {duration_min}
- Script excerpt: {script_excerpt}

TARGET QUALITY:
- Non-template writing. Sound human, modern, and channel-ready for 2026 YouTube.
- Audience intent: watch before sleep (calm, slow, trustworthy, no hype spam).
- Title: 45-70 chars, no hashtags, clear and searchable, calm curiosity hook.
- Description: 2 short paragraphs, first line instantly explains viewer value.
- Hashtags: 3-5.
- Tags: 10-15 practical YouTube Studio tags, intent-focused, no duplicates.
- first_comment: one engaging, calm CTA question.

Return strict JSON only:
{{
  "title": "...",
  "description": "...",
  "hashtags": ["#sleep", "..."],
  "tags": ["...", "..."],
  "first_comment": "..."
}}

Language: {language}
"""

_THUMBNAIL_PROMPT = """Design one high-quality YouTube thumbnail concept for a sleep-oriented long-form video.

VIDEO CONTEXT:
- Topic/title: {topic}
- Sub-mode: {sub_mode}
- Script excerpt: {script_excerpt}

OUTPUT REQUIREMENTS:
- Return only JSON with key "prompt".
- The prompt must be for generating one cinematic 16:9 thumbnail image.
- Visual style baseline (must be close to this): high-quality whimsical soft-cartoon look, Ghibli-inspired atmosphere, magical but clean.
- Composition baseline (must be close to this): one iconic scene tied to topic + large clean negative space (left half preferred) for title text.
- Typography baseline: large bold rounded bubble-like title text integrated in-scene, white fill with soft dark outline, readable at mobile size.
- Text structure baseline: main hook line + second small sleep line in banner (e.g. "FOR SLEEP"), with tiny sleep icons/stars around text.
- Must be trend-aware for YouTube in 2026: strong focal hierarchy, premium cinematic lighting, zero clutter.
- Calm sleep mood is mandatory (no chaos, no aggressive action, no horror, no bright red alarm palette).
- Keep topic relevance literal and sub-mode aware; avoid generic unrelated scenes.
- One scene only, one frame only, no watermark/logo/UI.

Return strict JSON only:
{{"prompt":"..."}}
"""


def _fallback_publish(topic: str, language: str) -> dict[str, Any]:
    t = re.sub(r"\s+", " ", str(topic or "").strip()) or ("Успокаивающие факты для сна" if language == "ru" else "Calming Facts for Sleep")
    if language == "ru":
        return {
            "title": f"{t[:62]}",
            "description": (
                f"{t}. Спокойный формат для вечернего просмотра и мягкого погружения в сон.\n\n"
                "Медленный темп, атмосферная подача и расслабляющий визуальный фон без перегрузки."
            ),
            "hashtags": _HASHTAGS_RU,
            "tags": _TAGS_RU,
            "first_comment": "Какую тему в спокойном формате для сна сделать следующей?",
        }
    return {
        "title": f"{t[:62]}",
        "description": (
            f"{t}. A calm long-form format designed for nighttime viewing and easy wind-down.\n\n"
            "Slow pacing, atmospheric visuals, and sleep-friendly narration with no overload."
        ),
        "hashtags": _HASHTAGS_EN,
        "tags": _TAGS_EN,
        "first_comment": "Which sleep-friendly topic should be the next long-form episode?",
    }


def _finalize(raw: dict[str, Any], *, fallback: dict[str, Any]) -> dict[str, Any]:
    title = raw.get("title") or fallback["title"]
    description = raw.get("description") or fallback["description"]
    hashtags = raw.get("hashtags") or hashtags_from_text(description) or fallback["hashtags"]
    tags = raw.get("tags") or fallback["tags"]
    return finalize_metadata(
        title=title,
        description=description,
        tags=tags,
        hashtags=hashtags,
        fallback_title=fallback["title"],
        fallback_description=fallback["description"],
        fallback_tags=fallback["tags"],
        fallback_hashtags=fallback["hashtags"],
        first_comment=raw.get("first_comment") or fallback.get("first_comment"),
        title_max_chars=72,
        min_description_chars=180,
        max_description_chars=900,
        min_tags=10,
        max_tags=15,
        min_hashtags=3,
        max_hashtags=5,
    )


def _extract_json_dict(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines and lines[-1].startswith("```") else lines[1:])
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        obj = json.loads(m.group())
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


async def generate_mode5_publishing_metadata(
    *,
    topic: str,
    sub_mode: str,
    script_excerpt: str,
    duration_min: int,
    language: str = "ru",
) -> dict[str, Any]:
    lang = "ru" if str(language).lower() == "ru" else "en"
    fallback = _fallback_publish(topic, lang)
    prompt = _PUBLISHING_PROMPT.format(
        topic=re.sub(r"\s+", " ", str(topic or "").strip())[:220],
        sub_mode=re.sub(r"\s+", " ", str(sub_mode or "").strip())[:80] or "manual",
        duration_min=max(1, int(duration_min or 1)),
        script_excerpt=re.sub(r"\s+", " ", str(script_excerpt or "").strip())[:2000],
        language=lang,
    )
    try:
        model = getattr(settings, "openrouter_model", None)
        llm = make_llm(temperature=0.62, model=model, max_tokens=900)
        response = await asyncio.wait_for(
            llm.ainvoke(
                [
                    SystemMessage(
                        content="You are a senior YouTube metadata strategist for sleep-focused long-form channels. Write natural, modern, non-template metadata."
                    ),
                    HumanMessage(content=prompt),
                ]
            ),
            timeout=40.0,
        )
        data = _extract_json_dict(response.content if hasattr(response, "content") else str(response))
        if isinstance(data, dict):
            return _finalize(data, fallback=fallback)
    except Exception as e:
        logger.warning(f"[Mode5 Publishing] LLM metadata fallback: {e}")
    return _finalize({}, fallback=fallback)


async def generate_mode5_thumbnail_prompt(
    *,
    topic: str,
    sub_mode: str,
    script_excerpt: str,
) -> str:
    base_topic = re.sub(r"\s+", " ", str(topic or "").strip())[:220] or "Sleep facts video"
    sub_mode_clean = re.sub(r"\s+", " ", str(sub_mode or "").strip())[:80] or "manual"
    if re.search(r"\bfacts?\b", base_topic, flags=re.IGNORECASE):
        title_overlay_hint = base_topic.upper()
    else:
        title_overlay_hint = f"{base_topic.upper()}".strip()
    fallback = (
        "A high-quality whimsical YouTube thumbnail in a soft cartoon style inspired by Studio Ghibli. "
        f"Topic: {base_topic}. Sub-mode: {sub_mode_clean}. "
        "Create one iconic topic-related scene with calm magical night mood, cinematic lighting, and deep but clean composition. "
        "Keep a large clean left-side negative space for text. "
        f"Add big rounded title typography: \"{title_overlay_hint}\" and a smaller banner line: \"FOR SLEEP\". "
        "White text with soft dark-blue outline, mobile-readable, zero clutter. 16:9, no watermark/logo/UI."
    )
    prompt = _THUMBNAIL_PROMPT.format(
        topic=base_topic,
        sub_mode=sub_mode_clean,
        script_excerpt=re.sub(r"\s+", " ", str(script_excerpt or "").strip())[:1800],
    )
    try:
        model = getattr(settings, "openrouter_model", None)
        llm = make_llm(temperature=0.68, model=model, max_tokens=700)
        response = await asyncio.wait_for(
            llm.ainvoke(
                [
                    SystemMessage(
                        content="You are an elite YouTube thumbnail creative director. Return strict JSON only."
                    ),
                    HumanMessage(content=prompt),
                ]
            ),
            timeout=35.0,
        )
        data = _extract_json_dict(response.content if hasattr(response, "content") else str(response))
        p = re.sub(r"\s+", " ", str((data or {}).get("prompt") or "").strip())
        if p:
            return p
    except Exception as e:
        logger.warning(f"[Mode5 Thumbnail] LLM prompt fallback: {e}")
    return fallback
