"""
LLM factory - returns a ChatOpenAI client pointed at OpenRouter.

OpenRouter is OpenAI-API compatible: just set base_url and api_key.
All models from https://openrouter.ai/models are supported.

Usage:
    from utils.llm import make_llm
    llm = make_llm(temperature=0.7)
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from config import settings


def make_llm(temperature: float = 0.2, model: str | None = None, **kwargs) -> ChatOpenAI:
    """
    Create a ChatOpenAI client configured for OpenRouter.

    Args:
        temperature: sampling temperature (0.0 = deterministic, 1.0 = creative)
        model: override model (if None, uses settings.openrouter_model)
        **kwargs: any extra ChatOpenAI parameters

    Returns:
        ChatOpenAI instance pointing to OpenRouter API
    """
    effective_model = model or settings.openrouter_model
    return ChatOpenAI(
        model=effective_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=temperature,
        default_headers={
            # OpenRouter recommends sending these for better routing/analytics
            "HTTP-Referer": "https://github.com/VideoEditor",
            "X-Title": "AI Content Factory",
        },
        **kwargs,
    )