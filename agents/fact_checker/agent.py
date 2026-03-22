"""
Fact Checker Agent.

Verifies the scientific accuracy of each scene in a video scenario.

Pipeline per scene:
  1. Extract the key factual claim from narration_text
  2. Search Wikipedia (RU + EN) for the subject
  3. Optionally query DuckDuckGo Instant Answer for additional context
  4. LLM compares the claim against the collected evidence
  5. Returns a structured verdict: verified | mostly_true | uncertain | false
  6. For false/uncertain claims: suggest a corrected, accurate version

The final "checked scenario" carries corrected scenes so the pipeline
can use verified content and never publish misinformation.
"""

from __future__ import annotations

import asyncio
import json
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from utils.llm import make_llm
from agents.trends_analyzer.sources import search_wikipedia, ddg_instant_answer
from agents.video_editor.tts import sanitize_voiceover_text


# ─────────────────────────────────────────────────────────────────────────────
# Typed output
# ─────────────────────────────────────────────────────────────────────────────

class FactCheckResult(TypedDict):
    scene_index: int
    narration_text: str
    verdict: str          # "verified" | "mostly_true" | "uncertain" | "false"
    confidence: int       # 1-10
    issues: list[str]     # specific problems found (empty if verified)
    correction: str       # corrected narration (empty if no issues)
    sources_used: list[str]  # Wikipedia article titles used


class CheckReport(TypedDict):
    all_clear: bool           # True if no "false" verdicts
    verified_count: int
    mostly_true_count: int
    uncertain_count: int
    false_count: int
    avg_confidence: float
    results: list[FactCheckResult]
    corrected_scenes: list[dict]   # Scenario scenes with corrections applied


# ─────────────────────────────────────────────────────────────────────────────
# LLM verifier
# ─────────────────────────────────────────────────────────────────────────────

_VERIFY_SYSTEM = """Ты — научный редактор научно-популярного видео.

Твоя задача: проверить ФАКТИЧЕСКУЮ точность текста озвучки одной сцены видео.

Тебе предоставлены:
- Текст озвучки (то, что скажет диктор)
- Фрагменты Википедии по теме (авторитетный источник)
- Данные DuckDuckGo (если есть)

Критерии оценки:

"verified" (10/10 точность):
  → Факт полностью соответствует научному консенсусу и источникам
  → Допустимы незначительные упрощения для популярного формата

"mostly_true" (7-9/10):
  → Суть верна, но есть неточные цифры / упрощения, меняющие смысл
  → Небольшие поправки нужны, но содержание не вводит в заблуждение

"uncertain" (4-6/10):
  → Заявление сложно проверить по доступным источникам
  → Или тема спорная в науке
  → Или данные устарели

"false" (1-3/10):
  → Факт противоречит Википедии / научному консенсусу
  → Цифры неверны (ошибка > 50%)
  → Широко известный миф или заблуждение

ВАЖНО:
- Для канала о НАУКЕ стандарт высокий — не пропускай явные ошибки
- НЕ придирайся к художественным приёмам (метафоры, гиперболы для эффекта — OK)
- Если Википедия не подтверждает и не опровергает — это "uncertain", не "false"
- Для "mostly_true" и "false" ОБЯЗАТЕЛЬНО предложи corrected_narration

Верни ТОЛЬКО валидный JSON (без markdown):
{
  "verdict": "verified | mostly_true | uncertain | false",
  "confidence": 8,
  "issues": ["описание конкретной проблемы если есть"],
  "corrected_narration": "исправленный текст (пусто если verified)",
  "explanation": "краткое объяснение вердикта (1-2 предложения)"
}"""


def _make_search_query(narration_text: str, topic: str) -> str:
    """
    Build a clean Wikipedia/DDG search query from scene narration.
    Strips punctuation-heavy video titles and uses key terms from the narration.
    """
    import re
    # Remove emoji, ?, !, ... from topic — keep the first meaningful words
    clean_topic = re.sub(r"[?!…]+", "", topic).split("—")[0].split(":")[0].strip()
    # Take the first sentence/phrase as additional context. In our scenario
    # writer narration is max 2 short sentences, so the key claim is usually
    # in the first one. This reduces mismatch vs. taking only first 6 words.
    import re
    first_sentence = re.split(r"[.!?]", narration_text, maxsplit=1)[0].strip()
    narration_words = first_sentence.split()[:14]
    narration_snippet = " ".join(narration_words)
    # Combine: topic keywords + narration keywords, deduplicated
    query = f"{clean_topic} {narration_snippet}"
    # Remove repeated words (keep order)
    seen, unique = set(), []
    for w in query.split():
        lw = w.lower()
        if lw not in seen:
            seen.add(lw)
            unique.append(w)
    return " ".join(unique[:12])


async def _verify_one_scene(
    scene_index: int,
    narration_text: str,
    topic: str,
    llm,
) -> FactCheckResult:
    """Verify a single scene's narration against Wikipedia + DDG."""
    sources_used: list[str] = []
    search_query = _make_search_query(narration_text, topic)

    # ── Gather evidence ───────────────────────────────────────────────────────
    evidence_parts: list[str] = []

    # Wikipedia RU
    try:
        wiki_ru = await search_wikipedia(search_query, lang="ru", limit=2)
        for w in wiki_ru:
            if w.get("extract"):
                evidence_parts.append(
                    f"[Wikipedia RU — {w['title']}]\n{w['extract']}"
                )
                sources_used.append(f"Wikipedia RU: {w['title']}")
    except Exception:
        pass

    # Wikipedia EN (for extra coverage)
    try:
        wiki_en = await search_wikipedia(search_query, lang="en", limit=1)
        for w in wiki_en:
            if w.get("extract"):
                evidence_parts.append(
                    f"[Wikipedia EN — {w['title']}]\n{w['extract']}"
                )
                sources_used.append(f"Wikipedia EN: {w['title']}")
    except Exception:
        pass

    # DuckDuckGo Instant Answer
    try:
        ddg = await ddg_instant_answer(search_query)
        if ddg:
            evidence_parts.append(f"[DuckDuckGo]\n{ddg}")
    except Exception:
        pass

    evidence = "\n\n".join(evidence_parts) if evidence_parts else "Источники не найдены."

    # ── LLM verification ──────────────────────────────────────────────────────
    user_msg = (
        f"Тема видео: {topic}\n\n"
        f"Текст озвучки сцены {scene_index}:\n«{narration_text}»\n\n"
        f"Доступные источники:\n{evidence[:2000]}"
    )

    messages = [
        SystemMessage(content=_VERIFY_SYSTEM),
        HumanMessage(content=user_msg),
    ]

    try:
        response = llm.invoke(messages)
        raw = response.content.strip()
        # Parse JSON
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            s, e = raw.find("{"), raw.rfind("}") + 1
            data = json.loads(raw[s:e]) if s != -1 and e > s else {}

        verdict    = data.get("verdict", "uncertain")
        confidence = int(data.get("confidence", 5))
        issues     = data.get("issues", [])
        correction = data.get("corrected_narration", "")
        explanation = data.get("explanation", "")

        if explanation:
            logger.debug(f"[FactChecker] Scene {scene_index}: {verdict} ({confidence}/10) — {explanation}")

    except Exception as exc:
        logger.warning(f"[FactChecker] LLM verification failed for scene {scene_index}: {exc}")
        verdict, confidence, issues, correction = "uncertain", 5, [], ""

    return FactCheckResult(
        scene_index=scene_index,
        narration_text=narration_text,
        verdict=verdict,
        confidence=confidence,
        issues=issues if isinstance(issues, list) else [str(issues)],
        correction=correction,
        sources_used=sources_used,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Batch verification
# ─────────────────────────────────────────────────────────────────────────────

async def _verify_all_scenes(
    scenes: list[dict],
    topic: str,
    llm,
    concurrency: int = 3,
) -> list[FactCheckResult]:
    """Verify all scenes with bounded concurrency to avoid rate limits."""
    sem = asyncio.Semaphore(concurrency)

    async def bounded(i: int, scene: dict) -> FactCheckResult:
        async with sem:
            narration = scene.get("narration_text") or scene.get("subtitle_text", "")
            return await _verify_one_scene(i + 1, narration, topic, llm)

    tasks = [bounded(i, s) for i, s in enumerate(scenes)]
    return list(await asyncio.gather(*tasks))


# ─────────────────────────────────────────────────────────────────────────────
# Apply corrections to scenario scenes
# ─────────────────────────────────────────────────────────────────────────────

def _apply_corrections(
    scenes: list[dict],
    results: list[FactCheckResult],
) -> list[dict]:
    """
    Return a new scene list with narration_text replaced by
    fact-checker corrections where verdict is 'false' or 'mostly_true'.
    """
    corrected = []
    for scene, result in zip(scenes, results):
        s = dict(scene)
        if result["verdict"] in ("false", "mostly_true") and result["correction"]:
            logger.info(
                f"[FactChecker] Scene {result['scene_index']} corrected "
                f"({result['verdict']}): {result['correction'][:80]}…"
            )
            s["narration_text"] = sanitize_voiceover_text(result["correction"])
        corrected.append(s)
    return corrected


# ─────────────────────────────────────────────────────────────────────────────
# Summary report builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_report(
    results: list[FactCheckResult],
    corrected_scenes: list[dict],
) -> CheckReport:
    verdict_counts = {"verified": 0, "mostly_true": 0, "uncertain": 0, "false": 0}
    for r in results:
        verdict_counts[r["verdict"]] = verdict_counts.get(r["verdict"], 0) + 1

    avg_conf = sum(r["confidence"] for r in results) / len(results) if results else 0.0
    all_clear = verdict_counts.get("false", 0) == 0

    return CheckReport(
        all_clear=all_clear,
        verified_count=verdict_counts.get("verified", 0),
        mostly_true_count=verdict_counts.get("mostly_true", 0),
        uncertain_count=verdict_counts.get("uncertain", 0),
        false_count=verdict_counts.get("false", 0),
        avg_confidence=round(avg_conf, 1),
        results=results,
        corrected_scenes=corrected_scenes,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

async def run_fact_checker_agent(
    scenario: dict,
    strict: bool = False,
) -> CheckReport:
    """
    Verify every scene in a video scenario for scientific accuracy.

    Args:
        scenario:  Full Scenario dict from ScenarioWriterAgent
                   (must have "scenes", "title" keys).
        strict:    If True, raise RuntimeError if any scene is "false".
                   If False (default), just log warnings and apply corrections.

    Returns:
        CheckReport with per-scene verdicts and corrected scene list.
    """
    scenes: list[dict] = scenario.get("scenes", [])
    topic: str = scenario.get("title") or scenario.get("topic", "Unknown topic")

    if not scenes:
        logger.warning("[FactChecker] No scenes to check")
        return _build_report([], [])

    logger.info(
        f"[FactChecker] Checking {len(scenes)} scenes for: {topic!r}"
    )

    llm = make_llm(temperature=0.1)   # low temperature for factual verification

    results = await _verify_all_scenes(scenes, topic, llm, concurrency=2)

    # Log summary
    counts = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    logger.info(
        f"[FactChecker] Results: "
        + " | ".join(f"{v}={c}" for v, c in counts.items())
        + f" | avg confidence={sum(r['confidence'] for r in results)/len(results):.1f}/10"
    )

    false_scenes = [r for r in results if r["verdict"] == "false"]
    if false_scenes:
        for r in false_scenes:
            logger.warning(
                f"[FactChecker] ⚠ FALSE scene {r['scene_index']}: "
                f"{r['narration_text'][:80]} | issues: {r['issues']}"
            )
        if strict:
            raise RuntimeError(
                f"[FactChecker] {len(false_scenes)} factually incorrect scene(s) found. "
                f"Strict mode: aborting."
            )

    # Apply corrections to the original scenes
    corrected_scenes = _apply_corrections(scenes, results)

    report = _build_report(results, corrected_scenes)

    if report["all_clear"]:
        logger.success(
            f"[FactChecker] All scenes passed! "
            f"avg confidence={report['avg_confidence']}/10"
        )
    else:
        logger.warning(
            f"[FactChecker] {report['false_count']} false scene(s) corrected. "
            f"avg confidence={report['avg_confidence']}/10"
        )

    return report
