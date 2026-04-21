"""Extract key points from evidence — Fact Miner step 3."""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage
from utils.llm import make_llm

from agents.fact_miner.prompts import EXTRACT_SYSTEM


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


async def extract_key_points(claim: str, evidence_text: str) -> list[str]:
    """Extract 2-3 key_points from evidence that support the claim."""
    llm = make_llm(temperature=0.2)
    user_msg = (
        f"Claim:\n{claim}\n\n"
        f"Evidence:\n{evidence_text[:2500] if evidence_text else ''}\n\n"
        "If evidence is empty/irrelevant, return empty key_points."
    )
    messages = [SystemMessage(content=EXTRACT_SYSTEM), HumanMessage(content=user_msg)]
    resp = await llm.ainvoke(messages)
    raw = resp.content.strip()
    try:
        data = _safe_json_loads(raw)
        return [str(x).strip() for x in data.get("key_points", []) if str(x).strip()]
    except Exception:
        return []
