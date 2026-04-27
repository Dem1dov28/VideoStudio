from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from loguru import logger

_LOW_VALUE_PHRASES = (
    "в этом видео",
    "подписывайтесь",
    "ставьте лайк",
    "like and subscribe",
    "in this video",
)


@dataclass
class Mode5QualityResult:
    score: float
    repetition_ratio: float
    low_value_ratio: float
    transition_issues: int
    flagged_indices: list[int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 3),
            "repetition_ratio": round(self.repetition_ratio, 3),
            "low_value_ratio": round(self.low_value_ratio, 3),
            "transition_issues": int(self.transition_issues),
            "flagged_indices": list(self.flagged_indices),
        }


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Zа-яА-Я0-9]+", (text or "").lower())


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def assess_mode5_narration_quality(narrations: list[str], *, language: str) -> Mode5QualityResult:
    tokens_per_block = [set(_tokenize(item)) for item in narrations]
    neighbors = 0
    high_overlap = 0
    transition_issues = 0
    flagged: list[int] = []
    low_value_hits = 0
    words_total = 0
    repeated_words = 0
    seen_counts: dict[str, int] = {}

    for idx, text in enumerate(narrations):
        lowered = (text or "").lower()
        words = _tokenize(text)
        words_total += len(words)
        for w in words:
            seen_counts[w] = seen_counts.get(w, 0) + 1
            if seen_counts[w] > 8:
                repeated_words += 1
        if any(p in lowered for p in _LOW_VALUE_PHRASES):
            low_value_hits += 1
            flagged.append(idx)
        if idx > 0:
            neighbors += 1
            overlap = _jaccard(tokens_per_block[idx - 1], tokens_per_block[idx])
            if overlap > 0.62:
                high_overlap += 1
                flagged.append(idx)
            if len(words) < 80:
                transition_issues += 1
                flagged.append(idx)

    repetition_ratio = (repeated_words / words_total) if words_total else 0.0
    low_value_ratio = (low_value_hits / max(1, len(narrations)))
    overlap_ratio = (high_overlap / max(1, neighbors))
    transition_ratio = transition_issues / max(1, len(narrations))
    score = max(0.0, 1.0 - (0.45 * repetition_ratio + 0.25 * low_value_ratio + 0.2 * overlap_ratio + 0.1 * transition_ratio))
    return Mode5QualityResult(
        score=score,
        repetition_ratio=repetition_ratio,
        low_value_ratio=low_value_ratio,
        transition_issues=transition_issues,
        flagged_indices=sorted(set(flagged)),
    )


def remediate_mode5_narrations(
    narrations: list[str],
    *,
    language: str,
    max_items: int = 3,
) -> tuple[list[str], dict[str, Any]]:
    quality = assess_mode5_narration_quality(narrations, language=language)
    if quality.score >= 0.78 or not quality.flagged_indices:
        return list(narrations), {"applied": False, "quality_before": quality.to_dict(), "quality_after": quality.to_dict()}

    repaired = list(narrations)
    appendix = (
        " Переход к следующей части звучит плавно и без повторов."
        if language == "ru"
        else " The transition to the next part stays smooth and avoids repetition."
    )
    for idx in quality.flagged_indices[: max(1, int(max_items))]:
        base = re.sub(r"\s+", " ", str(repaired[idx] or "").strip())
        if not base:
            continue
        repaired[idx] = f"{base}{appendix}"

    after = assess_mode5_narration_quality(repaired, language=language)
    logger.info(
        "[Mode5 quality] remediation applied={}, score {:.3f} -> {:.3f}, flagged={}",
        True,
        quality.score,
        after.score,
        quality.flagged_indices[:max_items],
    )
    return repaired, {
        "applied": True,
        "quality_before": quality.to_dict(),
        "quality_after": after.to_dict(),
    }
