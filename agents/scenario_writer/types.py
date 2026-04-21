"""Scenario Writer types — shared across single-LLM and multi-agent."""

from __future__ import annotations

from typing import TypedDict


class ScenarioScene(TypedDict):
    index: int
    narration_text: str
    subtitle_text: str
    image_prompt: str
    video_prompt: str


class Scenario(TypedDict):
    title: str
    hook: str
    scenes: list[ScenarioScene]
    outro: str
