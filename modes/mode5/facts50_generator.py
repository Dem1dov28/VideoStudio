"""
Mode 5 «facts50»: двухфазная генерация сценария — 77 фактов, затем озвучка по каждому.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from agents.video_editor.tts import append_nonspeaking_length_pad
from config import settings
from utils.json_parse import extract_first_json
from utils.llm import make_llm

FACTS50_TARGET = 77
# Запас над минимумом VoiceAPI (500), чтобы после sanitize текст не оказался короче лимита.
_MIN_NARRATION_CHARS = 520
_FACTS_VERIFY_BATCH = 20
_NARRATION_BATCH = 26


def _strip_code_fence(text: str) -> str:
    s = (text or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


def _parse_json_obj(raw: str) -> dict[str, Any]:
    """
    LLM часто ломает JSON (неэкранированные кавычки в длинных строках ~10k+ символов).
    Сначала первый полный объект (хвост после `}` игнорируется), затем json_repair.
    """
    s = _strip_code_fence(raw).strip()
    if not s:
        raise ValueError("Empty LLM response for JSON")

    last_err: BaseException | None = None

    try:
        extracted = extract_first_json(s)
        data = json.loads(extracted)
        if isinstance(data, dict):
            return data
    except Exception as e:
        last_err = e

    try:
        data = json.loads(s)
        if isinstance(data, dict):
            return data
    except Exception as e:
        last_err = e

    try:
        from json_repair import loads as json_repair_loads

        data = json_repair_loads(s)
        if isinstance(data, dict):
            logger.warning("[Mode5 facts50] JSON repaired via json_repair (model output was not strict JSON)")
            return data
    except ImportError:
        pass
    except Exception as e:
        last_err = e

    if last_err is not None:
        raise last_err
    raise ValueError("Could not parse LLM JSON")


def _scenario_llm():
    model = getattr(settings, "openrouter_scenario_model", None) or settings.openrouter_model
    return make_llm(temperature=0.45, model=model)


async def _invoke_json(system: str, human: str) -> dict[str, Any]:
    llm = _scenario_llm()
    msg = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=human)])
    raw = msg.content if isinstance(msg.content, str) else str(msg.content)
    return _parse_json_obj(raw)


def _normalize_fact_lines(obj: dict[str, Any]) -> list[str]:
    facts = obj.get("facts")
    if not isinstance(facts, list):
        return []
    out: list[str] = []
    for item in facts:
        if isinstance(item, str) and item.strip():
            out.append(re.sub(r"\s+", " ", item.strip()))
        elif isinstance(item, dict):
            t = item.get("title") or item.get("fact") or item.get("text")
            if isinstance(t, str) and t.strip():
                out.append(re.sub(r"\s+", " ", t.strip()))
    return out


def _normalize_narrations(obj: dict[str, Any]) -> list[str]:
    arr = obj.get("narrations")
    if not isinstance(arr, list):
        return []
    out: list[str] = []
    for item in arr:
        if isinstance(item, str) and item.strip():
            out.append(re.sub(r"\s+", " ", item.strip()))
    return out


def _pad_facts_to_target(facts: list[str], *, target: int, language: str, topic: str) -> list[str]:
    """Ensure exactly `target` fact lines even when LLM under-produces."""
    out = list(facts[:target])
    topic_clean = re.sub(r"\s+", " ", (topic or "").strip()) or "the topic"
    while len(out) < target:
        i = len(out) + 1
        if language.lower() == "ru":
            out.append(f"Дополнительный факт {i} по теме «{topic_clean}».")
        else:
            out.append(f"Additional fact {i} about {topic_clean}.")
    return out


def _pad_narrations_to_facts(facts: list[str], narrations: list[str], *, language: str) -> list[str]:
    """Ensure len == len(facts); pad or trim."""
    n = len(facts)
    cur = list(narrations[:n])
    while len(cur) < n:
        i = len(cur)
        cur.append(
            facts[i]
            if language.lower() == "ru"
            else f"Fact number {i + 1}: {facts[i]}. More details coming in the next version of this script."
        )
    return cur


async def _verify_facts_batch(
    topic_clean: str,
    lang_name: str,
    batch_facts: list[str],
) -> list[str]:
    """
    Fact safety pass: rewrite uncertain/mythical claims into broadly verifiable facts.
    Keeps length and order of the batch.
    """
    verify_sys = f"""You are a strict factual editor.
Task: for each input line, output one line that is historically/scientifically plausible and broadly verifiable.
Rules:
- Keep the same topic and roughly the same intent.
- Remove myths, rumors, conspiracies, supernatural claims, and unsupported absolutes.
- If a line is uncertain, rewrite it into a safer verified statement about the same topic.
- No fabricated names, dates, percentages, rankings, or quotes.
- Keep each line concise (about 100-220 characters).
- Output ONLY valid JSON: {{"facts": ["...", "..."]}} with exactly {len(batch_facts)} strings.
Language: {lang_name}."""
    verify_human = (
        f"Theme / headline:\n{topic_clean}\n\n"
        "Input facts to verify and correct:\n"
        + json.dumps(batch_facts, ensure_ascii=False)
    )
    obj = await _invoke_json(verify_sys, verify_human)
    out = _normalize_fact_lines(obj)
    if len(out) != len(batch_facts):
        raise ValueError(
            f"Fact verification batch length mismatch: {len(out)} != {len(batch_facts)}"
        )
    return out


async def _verify_facts(topic_clean: str, lang_name: str, facts: list[str]) -> list[str]:
    if not facts:
        return facts
    tasks = []
    for start in range(0, len(facts), _FACTS_VERIFY_BATCH):
        end = min(len(facts), start + _FACTS_VERIFY_BATCH)
        tasks.append(_verify_facts_batch(topic_clean, lang_name, facts[start:end]))
    chunks = await asyncio.gather(*tasks)
    merged: list[str] = []
    for chunk in chunks:
        merged.extend(chunk)
    if len(merged) != len(facts):
        raise ValueError(f"Fact verification total mismatch: {len(merged)} != {len(facts)}")
    return merged


def _ensure_min_narration_length(text: str, *, language: str) -> str:
    """Длина для API без озвучиваемых вставок: только невидимое дополнение при нехватке."""
    _ = language
    t = (text or "").strip()
    return append_nonspeaking_length_pad(t, _MIN_NARRATION_CHARS)


async def generate_facts50_script(
    topic: str,
    language: str,
    *,
    control: dict | None = None,
) -> tuple[list[str], list[str]]:
    """Returns (fact_one_liners, narration_paragraphs), each list of length FACTS50_TARGET."""
    from pipeline_control import checkpoint

    topic_clean = re.sub(r"\s+", " ", (topic or "").strip())
    if len(topic_clean) < 4:
        raise ValueError("Mode 5 (77 фактов): введите тему или заголовок")

    lang = (language or "ru").strip().lower()
    if lang not in ("ru", "en"):
        lang = "ru"
    lang_name = "Russian" if lang == "ru" else "English"

    sys1 = f"""You write structured factual entertainment scripts for short-form / long compilations.
The user gives a HEADLINE or THEME (e.g. "facts about France"). You must produce EXACTLY {FACTS50_TARGET} distinct, interesting, verifiable facts related to that theme.
Rules:
- Facts should be varied (history, culture, geography, science, language, food, people, quirks) when the theme allows.
- Each fact is ONE informative line (about 100-220 characters), no numbering prefix needed in the string.
- Avoid repeating the same idea. No URLs or markdown.
- Do not include myths, rumors, conspiracy claims, or uncertain claims presented as truth.
- Prefer broadly accepted facts from general knowledge; if uncertain, choose a safer fact.
- Output ONLY valid JSON: {{"facts": ["...", "..."]}} with exactly {FACTS50_TARGET} strings."""

    human1 = f"""Theme / headline:\n{topic_clean}\n\nLanguage for the fact lines: {lang_name} (same language as narrations)."""

    await checkpoint(control)
    try:
        obj1 = await _invoke_json(sys1, human1)
    except Exception as e:
        logger.error(f"[Mode5 facts50] Phase 1 JSON failed: {e}")
        raise ValueError("Mode 5 (77 фактов): не удалось разобрать ответ модели (фаза 1). Повторите запуск.") from e

    facts = _normalize_fact_lines(obj1)
    if len(facts) != FACTS50_TARGET:
        logger.warning(f"[Mode5 facts50] Phase 1 got {len(facts)} facts, retrying repair")
        repair_sys = sys1 + f"\nYou previously returned {len(facts)} items. Fix to EXACTLY {FACTS50_TARGET}."
        repair_human = f"Same theme:\n{topic_clean}\n\nPrevious JSON had wrong length. Output ONLY valid JSON with exactly {FACTS50_TARGET} strings in \"facts\"."
        try:
            obj1b = await _invoke_json(repair_sys, repair_human)
            facts = _normalize_fact_lines(obj1b)
        except Exception as e:
            logger.error(f"[Mode5 facts50] Phase 1 repair failed: {e}")
    if len(facts) > FACTS50_TARGET:
        # Модель иногда возвращает лишние факты; безопасно обрезаем до целевого количества.
        logger.warning(
            f"[Mode5 facts50] Phase 1 still has {len(facts)} facts after repair; trimming to {FACTS50_TARGET}"
        )
        facts = facts[:FACTS50_TARGET]
    elif len(facts) < FACTS50_TARGET:
        logger.warning(
            f"[Mode5 facts50] Phase 1 still has {len(facts)} facts after repair; padding to {FACTS50_TARGET}"
        )
        facts = _pad_facts_to_target(facts, target=FACTS50_TARGET, language=lang, topic=topic_clean)
    if len(facts) != FACTS50_TARGET:
        raise ValueError(f"Mode 5 (77 фактов): модель вернула {len(facts)} фактов вместо {FACTS50_TARGET}. Попробуйте ещё раз.")

    if control and control.get("_mode5_test_run"):
        tgt = float(control.get("_mode5_test_target_sec") or 300.0)
        tgt = max(60.0, min(7200.0, tgt))
        # В пайплайне добавляются отдельные intro/outro — оставляем запас под них.
        reserve_sec = 110.0
        per_fact_sec = 38.0
        k = max(3, min(len(facts), int(max(0.0, tgt - reserve_sec) / per_fact_sec)))
        if k < len(facts):
            facts = facts[:k]
            logger.info(f"[Mode5 facts50] test_run: generating {k} facts (~{tgt:.0f}s speech budget)")

    await checkpoint(control)
    try:
        facts = await _verify_facts(topic_clean, lang_name, facts)
    except Exception as e:
        logger.warning(f"[Mode5 facts50] Fact verification pass failed, using phase-1 facts as fallback: {e}")

    await checkpoint(control)

    async def narr_batch(start_i: int, end_i: int) -> list[str]:
        batch_facts = facts[start_i:end_i]
        sys2 = f"""You write voiceover narration for calm, scientific sleep-style documentary videos.
Narration language: {lang_name}.
For EACH fact in the batch, write ONE continuous paragraph to be read aloud (no bullet points).
Style anchor (keep stable across all batches): calm documentary narrator, precise but warm, medium sentence length, no slang.
- Tone: slow, warm, logical — like a quiet narrator for sleep, NOT a dramatic trailer and NOT religious preaching.
- Structure: 6–10 sentences. Build a clear mini-arc: introduce the fact -> explain context -> significance -> complete ending for that thought.
- End each paragraph on its own terms; do not tack on generic filler sentences just to lengthen the text.
- Do not add meta lines about "checking encyclopedias" or "sources" unless essential; avoid identical disclaimers at the end of every fact.
- The video has a SEPARATE spoken intro and outro. Inside fact paragraphs: do NOT welcome the listener, do NOT announce "today we have N facts about…", do NOT recap the episode format, do NOT thank the audience or sign off as if the episode is ending.
- The first fact in the full video is fact #{start_i + 1} in this batch when start_i==0: start directly with the substance of that fact—no second introduction to the series or headline.
- The last fact in the full video may appear in this batch: end on that fact's idea only—no lines like "that was all", "thank you for listening", "these were all the facts" (the outro handles closure).
- Ordinals: if useful, use a light in-flow transition; avoid title-style openers like "Fact one of seventy-seven about…".
- Keep narration strictly aligned with the provided verified fact line. If you are unsure about precise details, keep wording general instead of inventing specifics.
- 6–10 sentences per fact, concrete and engaging; add context and comparisons, but do not fabricate names, years, quotes, or exact statistics.
- Plain text only. Aim for roughly 800–1500 characters of real narration per fact when the material allows; if shorter, the pipeline adds invisible padding for the audio API—do not pad with empty prose.
- Output ONLY valid JSON: {{"narrations": ["paragraph1", "paragraph2", ...]}} with exactly {len(batch_facts)} strings in the same order as input facts."""

        human2 = (
            f"Video theme / headline:\n{topic_clean}\n\n"
            f"Facts {start_i + 1}–{end_i} (in order):\n"
            + json.dumps(batch_facts, ensure_ascii=False)
        )
        obj = await _invoke_json(sys2, human2)
        narr = _normalize_narrations(obj)
        if len(narr) != len(batch_facts):
            logger.warning(f"[Mode5 facts50] Batch {start_i}-{end_i}: got {len(narr)} narrations, repair")
            repair = (
                sys2
                + f"\nYou returned {len(narr)} strings; must be exactly {len(batch_facts)}."
            )
            obj = await _invoke_json(repair, human2 + "\n\nReturn corrected JSON only.")
            narr = _normalize_narrations(obj)
        if len(narr) != len(batch_facts):
            narr = _pad_narrations_to_facts(batch_facts, narr, language=lang)
        return [_ensure_min_narration_length(x, language=lang) for x in narr]

    # Батчим озвучки параллельно по фактической длине ``facts`` (полный релиз или укороченный test_run).
    n_facts = len(facts)
    tasks = []
    for start in range(0, n_facts, _NARRATION_BATCH):
        end = min(n_facts, start + _NARRATION_BATCH)
        tasks.append(narr_batch(start, end))
    narr_chunks = await asyncio.gather(*tasks)
    await checkpoint(control)
    narrations = [x for batch in narr_chunks for x in batch]
    if len(narrations) != n_facts:
        narrations = _pad_narrations_to_facts(facts, narrations, language=lang)
        narrations = [_ensure_min_narration_length(x, language=lang) for x in narrations[:n_facts]]

    logger.success(f"[Mode5 facts50] Generated {n_facts} facts + narrations for: {topic_clean[:80]}")
    return facts, narrations
