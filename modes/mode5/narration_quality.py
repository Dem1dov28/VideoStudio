from __future__ import annotations

import re


def narration_ngram_overlap(a: str, b: str, *, n: int = 4) -> float:
    """Small lexical overlap signal for adjacent long-form narration blocks."""
    wa = re.findall(r"[a-zа-яё0-9]+", (a or "").lower(), flags=re.IGNORECASE)
    wb = re.findall(r"[a-zа-яё0-9]+", (b or "").lower(), flags=re.IGNORECASE)
    if len(wa) < n or len(wb) < n:
        return 0.0
    ga = {" ".join(wa[i : i + n]) for i in range(len(wa) - n + 1)}
    gb = {" ".join(wb[i : i + n]) for i in range(len(wb) - n + 1)}
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / float(min(len(ga), len(gb)))


def adjacent_repetition_pairs(items: list[str], *, threshold: float = 0.08) -> list[tuple[int, float]]:
    """Return indices of blocks that repeat the immediately previous block too much."""
    out: list[tuple[int, float]] = []
    for idx in range(1, len(items)):
        score = narration_ngram_overlap(items[idx - 1], items[idx])
        if score >= threshold:
            out.append((idx, score))
    return out
