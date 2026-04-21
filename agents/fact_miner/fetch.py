"""Fetch evidence — Fact Miner step 2 (Wikipedia, DuckDuckGo)."""

from __future__ import annotations

from agents.trends_analyzer.sources import ddg_instant_answer, search_wikipedia


async def gather_evidence(search_query: str) -> tuple[str, list[str]]:
    """Fetch evidence from Wikipedia RU/EN and DuckDuckGo."""
    sources_used: list[str] = []
    evidence_parts: list[str] = []

    try:
        wiki_ru = await search_wikipedia(search_query, lang="ru", limit=2)
        for w in wiki_ru:
            if w.get("extract"):
                evidence_parts.append(f"[Wikipedia RU — {w['title']}]\n{w['extract']}")
                sources_used.append(f"Wikipedia RU: {w['title']}")
    except Exception:
        pass

    try:
        wiki_en = await search_wikipedia(search_query, lang="en", limit=1)
        for w in wiki_en:
            if w.get("extract"):
                evidence_parts.append(f"[Wikipedia EN — {w['title']}]\n{w['extract']}")
                sources_used.append(f"Wikipedia EN: {w['title']}")
    except Exception:
        pass

    try:
        ddg = await ddg_instant_answer(search_query)
        if ddg:
            evidence_parts.append(f"[DuckDuckGo]\n{ddg}")
            sources_used.append("DuckDuckGo")
    except Exception:
        pass

    evidence_text = "\n\n".join(evidence_parts).strip()
    return evidence_text or "", sources_used
