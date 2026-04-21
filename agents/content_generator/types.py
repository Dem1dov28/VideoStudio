"""Content Generator types."""

from __future__ import annotations

from typing import TypedDict


class EnrichedScene(TypedDict):
    index: int
    image_prompt: str
    subtitle_text: str
    narration_text: str
    image_path: str
    outro_bg_image_path: str | None
