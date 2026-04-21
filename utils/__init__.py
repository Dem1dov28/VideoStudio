"""Utility package with lazy imports for optional heavy dependencies."""

from __future__ import annotations

from typing import Any

__all__ = ["make_llm"]


def make_llm(*args: Any, **kwargs: Any):
    from utils.llm import make_llm as _make_llm

    return _make_llm(*args, **kwargs)