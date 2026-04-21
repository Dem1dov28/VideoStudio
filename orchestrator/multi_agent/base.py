"""Base utilities for multi-agent workflows."""

from __future__ import annotations

from typing import Any


async def checkpoint_if_control(control: dict | None) -> None:
    """Call pipeline checkpoint if control dict is provided (for pause/cancel)."""
    if control:
        from pipeline_control import checkpoint
        await checkpoint(control)
