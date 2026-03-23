"""
Fact Miner Agent — Propose → Fetch → Extract per scene.

Pipeline: propose claims → gather evidence (parallel) → extract key_points.
"""

from __future__ import annotations

import asyncio

from loguru import logger

from agents.fact_miner.extract import extract_key_points
from agents.fact_miner.fetch import gather_evidence
from agents.fact_miner.propose import propose_claims
from agents.fact_miner.types import ClaimCandidate, FactContext, SceneFactEvidence


async def _build_scene_evidence(
    scene_index: int,
    claim: str,
    search_query: str,
) -> SceneFactEvidence:
    """Fetch evidence and extract key points for one claim."""
    evidence_text, sources_used = await gather_evidence(search_query)
    key_points = await extract_key_points(claim=claim, evidence_text=evidence_text)
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

    num_candidates = max(6, num_scenes * 2)
    claims = await propose_claims(topic, num_candidates, trend_context)

    sem = asyncio.Semaphore(concurrency)

    async def bounded(c: ClaimCandidate):
        async with sem:
            return await _build_scene_evidence(
                scene_index=c["scene_index"],
                claim=c["claim"],
                search_query=c["search_query"],
            )

    tasks = [bounded(c) for c in claims]
    scene_facts = list(await asyncio.gather(*tasks))

    priority_by_id = {c["scene_index"]: c.get("priority_score", 50.0) for c in claims}

    def _score(sf) -> float:
        pr = float(priority_by_id.get(sf["scene_index"], 50.0))
        kp = len(sf.get("key_points") or [])
        src = len(sf.get("sources_used") or [])
        return pr * 2.0 + kp * 18.0 + src * 3.0

    scene_facts.sort(key=lambda x: x["scene_index"])
    best = sorted(scene_facts, key=_score, reverse=True)[:num_scenes]

    for new_idx, sf in enumerate(best, start=1):
        sf["scene_index"] = new_idx

    best_sorted = sorted(best, key=lambda x: x["scene_index"])
    logger.info(
        f"[FactMiner] Done. Top scenes with key_points: "
        f"{sum(1 for s in best_sorted if s['key_points'])}/{len(best_sorted)}"
    )
    return FactContext(topic=topic, scenes=best_sorted)
