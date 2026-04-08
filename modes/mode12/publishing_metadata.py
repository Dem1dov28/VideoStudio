"""
Mode 12 — метаданные для публикации (YouTube Shorts): заголовок, описание, теги, хештеги.

Только английский (без кириллицы). Комната: запущенное состояние → уборка / реставрация → уютный финал.
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

# Любая кириллица — выкидываем из пользовательских полей (на случай «полезного» LLM).
_CYRILLIC = re.compile(r"[\u0400-\u04FF]")

# Топ-5 хештегов для Shorts (room restoration): в заголовке каждый раз — случайные 2 из 5.
TITLE_HASHTAG_POOL: tuple[str, ...] = (
    "timelapse",
    "beforeafter",
    "roommakeover",
    "satisfying",
    "cleaning",
)


def _has_cyrillic(text: str | None) -> bool:
    return bool(text and _CYRILLIC.search(text))


def _strip_cyrillic(text: str) -> str:
    return _CYRILLIC.sub(" ", text or "").strip()


def sample_title_hashtag_pair() -> tuple[str, str]:
    return tuple(random.sample(list(TITLE_HASHTAG_POOL), 2))


def _strip_trailing_pool_hashtags(title: str) -> str:
    """Убирает с конца строки хештеги из TITLE_HASHTAG_POOL (чтобы не дублировать при пересборке)."""
    t = (title or "").replace("\n", " ").strip()
    pool_lower = {h.lower() for h in TITLE_HASHTAG_POOL}
    while True:
        m = re.search(r"\s+#(\w+)\s*$", t, re.IGNORECASE)
        if not m or m.group(1).lower() not in pool_lower:
            break
        t = t[: m.start()].rstrip()
    return t


def _ensure_title_shorts_hashtags(title: str, pair: tuple[str, str]) -> str:
    """Два хештега в конце заголовка — из заранее выбранной пары (меняются от ролика к ролику)."""
    base = _strip_trailing_pool_hashtags(title)
    h1 = pair[0].lstrip("#").lower()
    h2 = pair[1].lstrip("#").lower()
    extra = f" #{h1} #{h2}"
    return (base + extra)[:100]


def _merge_hashtags_title_pair(pair: tuple[str, str], base: list[str]) -> list[str]:
    """Пара из заголовка — в начале списка для описания / API, без дублей."""
    seen: set[str] = set()
    out: list[str] = []
    for h in list(pair) + base:
        x = str(h).strip().lstrip("#").lower()
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


PUBLISHING_PROMPT = """You write English-only YouTube Shorts metadata for ONE interior ROOM restoration / deep-clean timelapse (not building a house on empty land). Five stages: wreck → crew clears → rough finish → design → cozy reveal.

CONTEXT:
- Room type: {room_type}
- Lighting / mood: {room_lighting}
- Stage flow: {stages_description}
- Working title (hint): {title}

STRICT RULES:
- Use ONLY English (Latin letters, digits, punctuation). NO Cyrillic, NO Russian words.
- Title: catchy, transformation angle (mess → clean / before → after). Max ONE emoji (optional, near the start or before hashtags). End with EXACTLY two hashtags (lowercase), chosen ONLY from this set: #timelapse #beforeafter #roommakeover #satisfying #cleaning — pick any two different tags from these five.
- Title length: aim under 90 characters total (hard cap 100).
- Description: 2–4 short sentences. First sentence = clear hook. Naturally mention: satisfying timelapse, room makeover or restoration, cleaning, before and after. Do NOT use # hashtags in the description body (they are added separately).
- tags: 10–14 search tags for YouTube. English only, lowercase, no # character, each tag under 30 characters. Strategy:
  (1) 2–3 broad: e.g. "room makeover", "cleaning timelapse", "satisfying"
  (2) 2–3 niche tied to room type: e.g. "bedroom makeover", "kitchen deep clean", "living room transformation"
  (3) rest: "before and after", "home renovation", "interior design", "restoration", "deep clean", "home refresh", "asmr cleaning" — pick what fits the scenario, no duplicates, no near-duplicates.

OUTPUT: a single JSON object, no markdown fences:
{{
  "title": "...",
  "description": "...",
  "tags": ["tag1", "tag2"]
}}
"""

FALLBACK_TEMPLATES = {
    "titles": [
        "Room Makeover: {room} From Mess to Cozy 🛋️",
        "{room} Cleaning Timelapse — Watch Till the End ✨",
        "{room} Transformation in {duration_hint}s 🔧",
    ],
    "descriptions": [
        "Watch a neglected room turn clean and cozy — full satisfying restoration timelapse, deep clean, and before-and-after reveal.",
        "Crew clears the mess, finishes surfaces, then styles the space — pure room makeover energy in one short.",
    ],
    "hashtags": ["roommakeover", "cleaning", "satisfying", "timelapse", "beforeafter", "shorts"],
    "tags": [
        "room makeover",
        "cleaning timelapse",
        "before and after",
        "satisfying",
        "restoration",
        "interior makeover",
        "deep clean",
        "home renovation",
        "room transformation",
        "home refresh",
        "asmr cleaning",
        "shorts",
    ],
}


def _generate_fallback_metadata(
    room_type_en: str,
    room_lighting_en: str,
    stages: list[dict],
    title: str,
    duration_rounded: int = 30,
    *,
    title_hashtag_pair: tuple[str, str],
) -> dict[str, Any]:
    _ = room_lighting_en
    room_label = (room_type_en or "room").strip()
    if not room_label:
        room_label = "Room"
    title_tpl = random.choice(FALLBACK_TEMPLATES["titles"])
    generated_title = title_tpl.format(room=room_label, duration_hint=str(duration_rounded))
    generated_title = _ensure_title_shorts_hashtags(generated_title, title_hashtag_pair)
    description = random.choice(FALLBACK_TEMPLATES["descriptions"])
    tags = list(FALLBACK_TEMPLATES["tags"])
    # Короткий контекстный тег из типа комнаты (латиница)
    slug = re.sub(r"[^a-z0-9]+", " ", room_label.lower()).strip()
    if slug and slug not in {"room"}:
        tags.insert(0, f"{slug} makeover")
    if title and not _has_cyrillic(title):
        tags = [title[:30].lower()] + tags
    hashtags = _merge_hashtags_title_pair(
        title_hashtag_pair, list(FALLBACK_TEMPLATES["hashtags"])
    )
    return {
        "title": generated_title,
        "description": description,
        "hashtags": hashtags,
        "tags": tags[:14],
    }


def _sanitize_llm_result(
    result: dict[str, Any],
    *,
    force_title: str | None,
    fallback: dict[str, Any],
    title_hashtag_pair: tuple[str, str],
) -> dict[str, Any]:
    out = dict(result)
    desc = (out.get("description") or "").strip()
    if _has_cyrillic(desc):
        desc = _strip_cyrillic(desc)
    if not desc or len(desc) < 20:
        desc = fallback["description"]
    out["description"] = desc

    tags_raw = out.get("tags")
    if not isinstance(tags_raw, list):
        tags_raw = []
    tags: list[str] = []
    for t in tags_raw:
        s = re.sub(r"[\s,;]+", " ", str(t).strip()).strip().lower()
        if not s or s.startswith("#"):
            continue
        s = s[:30]
        if _has_cyrillic(s):
            continue
        if s not in tags:
            tags.append(s)
    if len(tags) < 6:
        tags = list(dict.fromkeys(tags + fallback["tags"]))[:14]
    out["tags"] = tags[:14]

    out["hashtags"] = _merge_hashtags_title_pair(
        title_hashtag_pair, list(FALLBACK_TEMPLATES["hashtags"])
    )

    base_title = (force_title or out.get("title") or fallback["title"] or "").replace("\n", " ").strip()
    if _has_cyrillic(base_title):
        base_title = (fallback.get("title") or "Room makeover timelapse").replace("\n", " ").strip()
    base_title = _strip_trailing_pool_hashtags(base_title)
    out["title"] = _ensure_title_shorts_hashtags(base_title, title_hashtag_pair)
    return out


async def generate_publishing_metadata(
    room_type_key: str,
    room_lighting_key: str,
    stages: list[dict],
    title: str,
    force_title: str | None = None,
    duration_hint_seconds: int = 30,
) -> dict[str, Any]:
    """
    Shorts: title, description, tags, hashtags — English only.
    """
    title_hashtag_pair = sample_title_hashtag_pair()
    try:
        from modes.mode12.scenario_writer import ROOM_LIGHTING, ROOM_TYPES

        rt = ROOM_TYPES.get(room_type_key, {})
        lg = ROOM_LIGHTING.get(room_lighting_key, {})
        room_disp = rt.get("name_en", room_type_key.replace("_", " "))
        light_disp = lg.get("name_en", room_lighting_key.replace("_", " "))

        stages_desc = ""
        if stages:
            stage_names = [s.get("name_en", f"Stage {i + 1}") for i, s in enumerate(stages)]
            stages_desc = " → ".join(stage_names[:6])

        title_hint = title or "Room restoration timelapse"
        if _has_cyrillic(title_hint):
            title_hint = _strip_cyrillic(title_hint) or "Room restoration timelapse"

        prompt = PUBLISHING_PROMPT.format(
            room_type=room_disp,
            room_lighting=light_disp,
            stages_description=stages_desc or "Five restoration stages",
            title=title_hint,
        )

        fb = _generate_fallback_metadata(
            room_disp,
            light_disp,
            stages,
            title_hint,
            duration_rounded=duration_hint_seconds,
            title_hashtag_pair=title_hashtag_pair,
        )

        try:
            llm = make_llm(temperature=0.75)
            messages = [
                SystemMessage(
                    content=(
                        "You are a YouTube Shorts SEO specialist. "
                        "Output valid JSON only. English only — zero Cyrillic."
                    )
                ),
                HumanMessage(content=prompt),
            ]
            try:
                response = await asyncio.wait_for(llm.ainvoke(messages), timeout=30.0)
            except asyncio.TimeoutError:
                logger.warning("[Mode12 Publishing] Metadata timeout (30s), using fallback")
                raise TimeoutError()
            raw = response.content.strip() if hasattr(response, "content") else str(response)

            if raw.startswith("```"):
                lines = raw.splitlines()
                raw = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

            json_match = re.search(r"\{[\s\S]*\}", raw)
            if json_match:
                result = json.loads(json_match.group())
                if result:
                    cleaned = _sanitize_llm_result(
                        result,
                        force_title=force_title,
                        fallback=fb,
                        title_hashtag_pair=title_hashtag_pair,
                    )
                    logger.success(f"[Mode12 Publishing] Generated: {cleaned.get('title', 'N/A')}")
                    return cleaned
        except Exception as e:
            logger.warning(f"[Mode12 Publishing] LLM failed, fallback: {e}")

        if force_title:
            fb["title"] = _ensure_title_shorts_hashtags(force_title, title_hashtag_pair)
        else:
            fb["title"] = _ensure_title_shorts_hashtags(fb["title"], title_hashtag_pair)
        fb["hashtags"] = _merge_hashtags_title_pair(
            title_hashtag_pair, list(FALLBACK_TEMPLATES["hashtags"])
        )
        return fb
    except Exception as e:
        logger.error(f"[Mode12 Publishing] All methods failed: {e}")
        fb_title = _ensure_title_shorts_hashtags(
            force_title or f"Room makeover {room_type_key or ''} {room_lighting_key or ''}".strip(),
            title_hashtag_pair,
        )
        return {
            "title": fb_title,
            "description": (
                "Satisfying room restoration and cleaning timelapse — before and after in one short."
            ),
            "hashtags": _merge_hashtags_title_pair(
                title_hashtag_pair, list(FALLBACK_TEMPLATES["hashtags"])
            ),
            "tags": FALLBACK_TEMPLATES["tags"][:14],
        }
