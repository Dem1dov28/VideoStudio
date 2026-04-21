"""Fact Miner types."""

from __future__ import annotations

from typing import TypedDict


class SceneFactEvidence(TypedDict):
    scene_index: int
    claim: str
    key_points: list[str]
    sources_used: list[str]


class FactContext(TypedDict):
    topic: str
    scenes: list[SceneFactEvidence]


class ClaimCandidate(TypedDict):
    scene_index: int
    claim: str
    search_query: str
    priority_score: float
