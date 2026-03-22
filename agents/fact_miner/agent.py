"""
Fact Miner Agent.

Goal: build evidence (key factual points + sources) for each planned scene,
so ScenarioWriter can generate narration that is grounded in verifiable claims.
This reduces "strange" fact corrections later by FactChecker.
"""

from __future__ import annotations

import asyncio
import json
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from utils.llm import make_llm
from agents.trends_analyzer.sources import ddg_instant_answer, search_wikipedia


class SceneFactEvidence(TypedDict):
    scene_index: int
    claim: str
    key_points: list[str]     # short statements grounded in evidence
    sources_used: list[str]   # for debugging/traceability


class FactContext(TypedDict):
    topic: str
    scenes: list[SceneFactEvidence]


class _ClaimCandidate(TypedDict):
    scene_index: int
    claim: str
    search_query: str
    # How strongly this claim is expected to be "important + interesting".
    # Used only for ranking candidates before narration generation.
    priority_score: float


_MINER_SYSTEM = """Ты — Fact Miner для научно-популярного формата.

Твоя задача: придумать кандидаты утверждений (claim) и дать поисковый запрос,
по которому можно найти подтверждения (Wikipedia/интернет).

Кандидаты ОБЯЗАТЕЛЬНО должны быть РАНЖИРОВАНЫ:
сначала САМЫЕ ИНТЕРЕСНЫЕ и ВАЖНЫЕ (по масштабу, последствиям, необычному эффекту),
потом менее.

Ограничения:
- claim должен быть одной мыслью (1 предложение).
- claim должен начинаться с существительного/объекта (кто/что) и
  содержать научную связь/свойство (как/почему/в каком размере).
- avoid: художественные метафоры, откровенно фантастические утверждения.
- claim length: до 18 слов.
- priority_score: число 0-100, где 100 = самый важный и интересный.

Верни ТОЛЬКО валидный JSON array без markdown:
[
  {"scene_index": 1, "claim": "...", "search_query": "...", "priority_score": 0-100},
  ...
]"""


_EXTRACT_SYSTEM = """Ты — научный редактор.

Дано:
- claim (верифицируемое утверждение)
- evidence текст из источников (Wikipedia + web snippets)

Твоя задача:
1) На основе evidence выдели 2-3 КОРОТКИХ фактических пункта (key_points),
   которые прямо поддерживают claim по смыслу.
2) Не добавляй новых фактов, отсутствующих в evidence.
3) Если evidence слабое/не подходит — верни пустой список key_points.

Верни ТОЛЬКО JSON:
{"key_points": ["...", "..."]}"""


def _safe_json_loads(raw: str):
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract first JSON array/object
        if raw.startswith("{"):
            s, e = raw.find("{"), raw.rfind("}") + 1
        else:
            s, e = raw.find("["), raw.rfind("]") + 1
        if s == -1 or e <= s:
            raise
        return json.loads(raw[s:e])


def _build_claim_prompt(
    topic: str,
    num_candidates: int,
    trend_context: dict | None,
) -> str:
    angle = (trend_context or {}).get("video_angle") or ""
    why = (trend_context or {}).get("why_trending") or ""
    category = (trend_context or {}).get("category") or ""

    return (
        f"Topic: {topic}\n"
        f"Category: {category}\n"
        f"Suggested angle: {angle}\n"
        f"Why trending: {why}\n\n"
        f"Number of candidate claims: {num_candidates}\n\n"
        "Generate verifiable fact claims in Russian, ranked by importance+interest."
    )


async def _propose_claims(
    topic: str,
    num_candidates: int,
    trend_context: dict | None,
) -> list[_ClaimCandidate]:
    llm = make_llm(temperature=0.45)
    messages = [
        SystemMessage(content=_MINER_SYSTEM),
        HumanMessage(content=_build_claim_prompt(topic, num_candidates, trend_context)),
    ]
    resp = llm.invoke(messages)
    raw = resp.content.strip()
    data = _safe_json_loads(raw)
    claims: list[_ClaimCandidate] = []
    for item in data:
        claims.append(
            {
                "scene_index": int(item.get("scene_index", len(claims) + 1)),
                "claim": str(item.get("claim", "")),
                "search_query": str(item.get("search_query", item.get("claim", ""))),
                "priority_score": float(item.get("priority_score", 50)),
            }
        )
    claims.sort(key=lambda x: x["scene_index"])
    return claims[:num_candidates]


async def _gather_evidence(
    search_query: str,
) -> tuple[str, list[str]]:
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
    if not evidence_text:
        evidence_text = ""
    return evidence_text, sources_used


async def _extract_key_points(
    claim: str,
    evidence_text: str,
) -> list[str]:
    llm = make_llm(temperature=0.2)
    user_msg = (
        f"Claim:\n{claim}\n\n"
        f"Evidence:\n{evidence_text[:2500] if evidence_text else ''}\n\n"
        f"If evidence is empty/irrelevant, return empty key_points."
    )
    messages = [SystemMessage(content=_EXTRACT_SYSTEM), HumanMessage(content=user_msg)]
    resp = llm.invoke(messages)
    raw = resp.content.strip()
    try:
        data = _safe_json_loads(raw)
        return [str(x).strip() for x in data.get("key_points", []) if str(x).strip()]
    except Exception:
        return []


async def _build_scene_evidence(
    scene_index: int,
    claim: str,
    search_query: str,
) -> SceneFactEvidence:
    evidence_text, sources_used = await _gather_evidence(search_query)
    key_points = await _extract_key_points(claim=claim, evidence_text=evidence_text)
    return SceneFactEvidence(
        scene_index=scene_index,
        claim=claim,
        key_points=key_points,
        sources_used=sources_used,
    )


async def run_fact_miner_agent(
    topic: str,
    num_scenes: int = 5,
    trend_context: dict | None = None,
    concurrency: int = 2,
) -> FactContext:
    """Return evidence per scene that ScenarioWriter can use."""
    logger.info(f"[FactMiner] Building evidence for {num_scenes} scenes: {topic!r}")

    # Generate more candidates, then rank after evidence extraction.
    num_candidates = max(6, num_scenes * 2)
    claims = await _propose_claims(topic, num_candidates, trend_context)

    sem = asyncio.Semaphore(concurrency)

    async def bounded(i: int, c: _ClaimCandidate):
        async with sem:
            return await _build_scene_evidence(
                scene_index=i,
                claim=c["claim"],
                search_query=c["search_query"],
            )

    tasks = [
        bounded(c["scene_index"], c)  # scene_index passed through to _build_scene_evidence
        for c in claims
    ]
    scene_facts = list(await asyncio.gather(*tasks))

    # Rank by: LLM priority + evidence support quality.
    priority_by_id = {c["scene_index"]: c.get("priority_score", 50.0) for c in claims}

    def _score(sf) -> float:
        pr = float(priority_by_id.get(sf["scene_index"], 50.0))
        kp = len(sf.get("key_points") or [])
        src = len(sf.get("sources_used") or [])
        # Tuned to prefer claims that are both "important/interesting" and well-supported.
        return pr * 2.0 + kp * 18.0 + src * 3.0

    scene_facts.sort(key=lambda x: x["scene_index"])
    best = sorted(scene_facts, key=_score, reverse=True)[:num_scenes]

    # Re-index scenes to 1..num_scenes in the final ranked order.
    for new_idx, sf in enumerate(best, start=1):
        sf["scene_index"] = new_idx

    best_sorted = sorted(best, key=lambda x: x["scene_index"])
    logger.info(
        "[FactMiner] Done evidence. "
        f"Top scenes with key_points: {sum(1 for s in best_sorted if s['key_points'])}/{len(best_sorted)}"
    )
    return FactContext(topic=topic, scenes=best_sorted)

