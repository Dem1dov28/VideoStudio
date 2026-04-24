"""Encyclopedia / search snippets for mode5 longform grounding (book_night, unwritten_chapter)."""

from __future__ import annotations

from loguru import logger

_MAX_EVIDENCE_OUTLINE_CHARS = 9000


def clip_evidence(text: str, max_chars: int) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[:max_chars].rstrip() + "\n[…truncated]"


async def gather_mode5_grounding_snippets(query: str) -> tuple[str, list[str]]:
    """Short third-party snippets — reduces invented specifics when LLM plans outline/narration."""
    from agents.fact_miner.fetch import gather_evidence

    try:
        evidence, sources = await gather_evidence(query)
    except Exception as e:
        logger.warning(f"[Mode5 grounding] gather_evidence failed: {e}")
        return "", []
    if not (evidence or "").strip():
        return "", sources
    return clip_evidence(evidence, _MAX_EVIDENCE_OUTLINE_CHARS), sources


def sources_block_book_night(evidence: str) -> str:
    if (evidence or "").strip():
        return (
            "\n\n---\nEXTERNAL_SOURCES (encyclopedia / search snippets only; "
            "not the full book, often incomplete). Use for themes, author, scope; "
            "do not contradict; do not treat as verbatim book text:\n"
            f"{evidence.strip()}"
        )
    return (
        "\n\n---\nEXTERNAL_SOURCES: none retrieved. "
        "Stay at the level of widely known, uncontroversial themes and real TOC structure for this title. "
        "Do NOT invent statistics, named studies, dates, dialogue, anecdotes, or long quotes "
        'in "coverage" or anywhere else.'
    )


def sources_block_unwritten(evidence: str) -> str:
    if (evidence or "").strip():
        return (
            "\n\n---\nEXTERNAL_SOURCES (encyclopedia / search snippets only; incomplete). "
            "Use for broad context, dates, and named entities when they appear here; "
            "do not contradict a clear statement in these snippets. "
            "Do not treat snippets as a full archive or primary documents.\n"
            f"{evidence.strip()}"
        )
    return (
        "\n\n---\nEXTERNAL_SOURCES: none retrieved. "
        "Stay conservative: widely known framing only; do NOT invent declassified memo numbers, "
        "exact witness quotes, precise statistics, or document references not grounded in common knowledge."
    )
