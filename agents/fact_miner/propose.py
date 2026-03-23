"""Propose claims — Fact Miner step 1."""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage
from utils.llm import make_llm

from agents.fact_miner.types import ClaimCandidate
from agents.fact_miner.prompts import MINER_SYSTEM


def _safe_json_loads(raw: str):
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        if raw.startswith("{"):
            s, e = raw.find("{"), raw.rfind("}") + 1
        else:
            s, e = raw.find("["), raw.rfind("]") + 1
        if s == -1 or e <= s:
            raise
        return json.loads(raw[s:e])


def _build_claim_prompt(topic: str, num_candidates: int, trend_context: dict | None) -> str:
    angle = (trend_context or {}).get("video_angle") or ""
    why = (trend_context or {}).get("why_trending") or ""
    category = (trend_context or {}).get("category") or ""
    return (
        f"Topic: {topic}\nCategory: {category}\n"
        f"Suggested angle: {angle}\nWhy trending: {why}\n\n"
        f"Number of candidate claims: {num_candidates}\n\n"
        "Generate verifiable fact claims in Russian, ranked by importance+interest."
    )


async def propose_claims(
    topic: str,
    num_candidates: int,
    trend_context: dict | None,
) -> list[ClaimCandidate]:
    """Generate candidate claims with search queries (LLM)."""
    llm = make_llm(temperature=0.45)
    messages = [
        SystemMessage(content=MINER_SYSTEM),
        HumanMessage(content=_build_claim_prompt(topic, num_candidates, trend_context)),
    ]
    resp = await llm.ainvoke(messages)
    raw = resp.content.strip()
    data = _safe_json_loads(raw)
    claims: list[ClaimCandidate] = []
    for item in data:
        claims.append({
            "scene_index": int(item.get("scene_index", len(claims) + 1)),
            "claim": str(item.get("claim", "")),
            "search_query": str(item.get("search_query", item.get("claim", ""))),
            "priority_score": float(item.get("priority_score", 50)),
        })
    claims.sort(key=lambda x: x["scene_index"])
    return claims[:num_candidates]
