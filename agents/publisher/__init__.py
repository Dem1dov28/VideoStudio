"""Publisher package with lazy imports for optional AI dependencies."""

from __future__ import annotations

from typing import Any

__all__ = ["run_publisher_agent"]


async def run_publisher_agent(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from agents.publisher.agent import run_publisher_agent as _run_publisher_agent

    return await _run_publisher_agent(*args, **kwargs)