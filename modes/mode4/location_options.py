from __future__ import annotations

import asyncio
import json
import random
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from utils.llm import make_llm
from utils.json_parse import parse_json_safe

_FALLBACK_LOCATIONS: tuple[str, ...] = (
    "кабинет с книжными полками и мягким теплым светом",
    "историческая библиотека с высокими окнами",
    "каменная набережная с ветром и водой на фоне",
    "внутренний двор старого университета",
    "мастерская с инструментами и фактурными стенами",
    "зал с колоннами и приглушенным светом",
    "садовая аллея у старинного особняка",
    "монастырский клуатр с аркадами",
    "тихая терраса с видом на город",
    "узкая улочка старого города на закате",
)


def _fallback(limit: int) -> list[str]:
    n = max(3, min(12, int(limit or 7)))
    pool = list(_FALLBACK_LOCATIONS)
    random.shuffle(pool)
    return pool[:n]


def _normalize_options(data: Any, limit: int) -> list[str]:
    raw = data.get("locations") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    max_n = max(3, min(12, int(limit or 7)))
    for item in raw:
        text = " ".join(str(item or "").split()).strip(" -")
        if len(text) < 8:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= max_n:
            break
    return out


async def suggest_mode4_locations(
    *,
    person_name: str,
    quote: str = "",
    limit: int = 7,
) -> list[str]:
    name = " ".join((person_name or "").split()).strip()
    if len(name) < 2:
        return _fallback(limit)
    q = " ".join((quote or "").split()).strip()
    llm = make_llm(temperature=0.45, max_tokens=1200)
    sys = SystemMessage(
        content=(
            "You suggest historically and emotionally fitting cinematic locations for quote videos.\n"
            "Return JSON only: {\"locations\": [\"...\", ...]}.\n"
            "Rules:\n"
            "- 6-10 diverse options.\n"
            "- Concrete, visually rich, and plausible for the character's era/status.\n"
            "- No modern anachronisms unless the person is modern.\n"
            "- Keep each option short (5-14 words), in Russian.\n"
            "- Avoid duplicates and generic repeats.\n"
        )
    )
    human = HumanMessage(
        content=(
            f"Персонаж: {name}\n"
            f"Цитата (контекст, может быть пусто): {q or '—'}\n"
            f"Сколько вариантов: {max(3, min(12, int(limit or 7)))}"
        )
    )
    try:
        resp = await asyncio.wait_for(llm.ainvoke([sys, human]), timeout=35.0)
        text = (getattr(resp, "content", "") or "").strip()
        try:
            data = parse_json_safe(text)
        except Exception:
            # Fallback: some providers wrap JSON into fenced blocks.
            cleaned = text.strip()
            if cleaned.startswith("```"):
                first_nl = cleaned.find("\n")
                if first_nl != -1:
                    cleaned = cleaned[first_nl + 1 :]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
            data = json.loads(cleaned.strip())
        options = _normalize_options(data, limit)
        return options or _fallback(limit)
    except Exception:
        return _fallback(limit)
