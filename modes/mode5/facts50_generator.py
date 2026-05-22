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
# Один JSON на 77 фактов часто обрывается/ломается — генерируем пачками.
_FACTS_PHASE1_BATCH_DEFAULT = 16
_COMBINING_ACUTE = "\u0301"
_BAD_FACT_PATTERNS = (
    re.compile(r"\bдополнительн(?:ый|ого|ые)\s+факт", re.IGNORECASE),
    re.compile(r"\badditional\s+fact\b", re.IGNORECASE),
    re.compile(r"\bfact\s+number\s+\d+\b", re.IGNORECASE),
)
_NEGATIVE_FACT_PATTERNS = (
    re.compile(r"\bdoes not have\b", re.IGNORECASE),
    re.compile(r"\bdo not have\b", re.IGNORECASE),
    re.compile(r"\bdid not have\b", re.IGNORECASE),
    re.compile(r"\bno widely recognized\b", re.IGNORECASE),
    re.compile(r"\bnot a widely recognized\b", re.IGNORECASE),
    re.compile(r"\bне имеет\b", re.IGNORECASE),
    re.compile(r"\bнет широко известн", re.IGNORECASE),
    re.compile(r"\bотсутствует широко\b", re.IGNORECASE),
)
# (tag_name, pattern, max_facts_with_this_tag in one episode)
_THEMATIC_BUCKETS: list[tuple[str, re.Pattern[str], int]] = [
    ("amazon_biome", re.compile(r"\bamazon\b", re.IGNORECASE), 2),
    ("rainforest", re.compile(r"\brainforest\b|\bjungle\b", re.IGNORECASE), 2),
    ("wetland", re.compile(r"\bwetland\b|\bpantanal\b", re.IGNORECASE), 2),
    ("savanna", re.compile(r"\bsavanna\b|\bgrassland\b|\bcerrado\b", re.IGNORECASE), 2),
    ("carnival", re.compile(r"\bcarnival\b|\bcarnaval\b", re.IGNORECASE), 2),
    ("rio_landmarks", re.compile(
        r"\brio de janeiro\b|\bcopacabana\b|\bipanema\b|\bsugarloaf\b|\bcorcovado\b|christ the redeemer",
        re.IGNORECASE,
    ), 2),
    ("beaches", re.compile(r"\bbeaches?\b|\bcoastline\b|\bbeachgoers?\b", re.IGNORECASE), 2),
    ("named_dish", re.compile(
        r"\bfeijoada\b|\bacaraj[eé]\b|\bcaipirinha\b|\bmoqueca\b|\bbrigadeiro\b|\ba[cç]a[ií]\b|pão de queijo",
        re.IGNORECASE,
    ), 3),
    ("football_world_cup", re.compile(r"\bfifa\b|world cup|football tradition", re.IGNORECASE), 2),
]
_LEADING_FACT_NUMBERING = re.compile(
    r"^(?:"
    r"\d{1,2}[\.\)\:\-]\s+"
    r"|(?:fact|факт)\s*(?:number\s*)?#?\d{1,3}\s*[\.\)\:\-]\s+"
    r"|(?:first|second|third|one|two|three|перв(?:ый|ого)|втор(?:ой|ого)|трет(?:ий|ьего))\s+(?:fact|факт)\b[\s,\.:;-]*"
    r")",
    re.IGNORECASE,
)
_FACTS50_STOCK_CLOSER_BAN = (
    "Banned stock closers in ANY language (and close paraphrases): "
    "This dynamic interplay; shapes the legal landscape; influences the daily lives; "
    "underscores the importance; serves as a testament; reflects the ongoing; "
    "highlights the significance; plays a crucial role; continues to evolve; "
    "lies in its ability to provide; serene escape while also offering; "
    "В конечном счёте; Таким образом as a repeated paragraph closer. "
    "End each fact paragraph on one concrete point from that fact, not a generic moral."
)
_DISTINCTIVE_FACT_TERMS = (
    "unesco",
    "юнеско",
    "world heritage",
    "всемирного наследия",
    "vatican",
    "ватикан",
    "uffizi",
    "уффици",
    "ватиканские музеи",
    "vatican museums",
)


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
        logger.debug(
            "[Mode5 facts50] JSON parse failed after all strategies; response head: {}",
            s[:800],
        )
        raise last_err
    raise ValueError("Could not parse LLM JSON")


def _facts_phase1_batch_size() -> int:
    raw = int(getattr(settings, "mode5_facts50_phase1_batch_size", _FACTS_PHASE1_BATCH_DEFAULT) or _FACTS_PHASE1_BATCH_DEFAULT)
    return max(8, min(26, raw))


def _scenario_llm(*, temperature: float = 0.45, max_tokens: int = 8192):
    model = getattr(settings, "openrouter_scenario_model", None) or settings.openrouter_model
    return make_llm(temperature=temperature, model=model, max_tokens=max_tokens)


async def _invoke_json(system: str, human: str, *, max_attempts: int = 2) -> dict[str, Any]:
    last_err: BaseException | None = None
    temps = (0.45, 0.25)
    for attempt in range(max(1, max_attempts)):
        temp = temps[min(attempt, len(temps) - 1)]
        llm = _scenario_llm(temperature=temp)
        payload = human
        if attempt > 0:
            payload = (
                human
                + "\n\nIMPORTANT: Return ONLY one valid JSON object. "
                "Escape double quotes inside strings. No markdown fences, no commentary."
            )
        try:
            msg = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=payload)])
            raw = msg.content if isinstance(msg.content, str) else str(msg.content)
            return _parse_json_obj(raw)
        except Exception as e:
            last_err = e
            logger.warning("[Mode5 facts50] JSON invoke attempt {} failed: {}", attempt + 1, e)
    assert last_err is not None
    raise last_err


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


def _strip_generation_artifacts(text: str) -> str:
    """Remove technical TTS artifacts and a few common malformed phrases from visible/generated text."""
    out = re.sub(r"\s+", " ", (text or "").replace(_COMBINING_ACUTE, "").strip())
    out = re.sub(r"\bВенецианский\s+карнавальный\b", "Венецианский карнавал", out, flags=re.IGNORECASE)
    return out


def _is_negative_fact(text: str) -> bool:
    """Facts that only say what does NOT exist — not valid list items."""
    t = _strip_generation_artifacts(text)
    if any(p.search(t) for p in _NEGATIVE_FACT_PATTERNS):
        return True
    if re.search(r";\s*however,\s*", t, re.IGNORECASE) and re.search(
        r"\bdoes not have\b|\bdo not have\b", t, re.IGNORECASE
    ):
        return True
    return False


def _has_placeholder_fact(text: str) -> bool:
    t = _strip_generation_artifacts(text)
    if len(t) < 35:
        return True
    if _is_negative_fact(t):
        return True
    return any(p.search(t) for p in _BAD_FACT_PATTERNS)


def _fact_theme_tags(text: str) -> set[str]:
    t = _strip_generation_artifacts(text)
    return {name for name, pat, _ in _THEMATIC_BUCKETS if pat.search(t)}


def _theme_limit_for(tag: str) -> int:
    for name, _, limit in _THEMATIC_BUCKETS:
        if name == tag:
            return limit
    return 99


def _theme_bucket_saturated(line: str, facts: list[str]) -> bool:
    new_tags = _fact_theme_tags(line)
    if not new_tags:
        return False
    for tag in new_tags:
        count = sum(1 for f in facts if tag in _fact_theme_tags(f))
        if count >= _theme_limit_for(tag):
            return True
    return False


def _line_passes_fact_filters(line: str, facts: list[str], *, strict_dedup: bool) -> bool:
    line = _strip_generation_artifacts(line)
    if not line or _has_placeholder_fact(line):
        return False
    if _theme_bucket_saturated(line, facts):
        return False
    return all(not _facts_near_duplicate(line, prev, strict=strict_dedup) for prev in facts)


_FACT_STOPWORDS = {
    "это", "как", "или", "для", "что", "при", "его", "её", "она", "они", "the", "and", "that", "with",
    "this", "from", "about", "into", "una", "une", "und", "der", "die", "das", "des", "les", "los", "las",
    # Shared boilerplate in country/topic fact lists — must not trigger false "duplicate"
    "united", "states", "state", "american", "america", "country", "nation", "national", "world",
    "largest", "million", "billion", "people", "population", "known", "famous", "among", "across",
    "during", "between", "through", "within", "around", "often", "also", "many", "more", "than",
    "over", "such", "their", "there", "which", "these", "those", "being", "other", "first",
    "сша", "америк", "страна", "население", "миллион", "крупнейш", "известн",
}


def _fact_tokens(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]+", _strip_generation_artifacts(text).lower())
    return {w for w in words if len(w) >= 4 and w not in _FACT_STOPWORDS}


def _fact_overlap(a: str, b: str) -> float:
    ta = _fact_tokens(a)
    tb = _fact_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / float(min(len(ta), len(tb)))


def _significant_numbers(text: str) -> set[str]:
    """Multi-digit figures that often signal the same fact repeated with new wording."""
    return set(re.findall(r"\b[0-9]{3,}\b", _strip_generation_artifacts(text)))


def _facts_near_duplicate(a: str, b: str, *, strict: bool) -> bool:
    """
    Detect duplicate/near-duplicate facts.
    strict=False while merging LLM batches (looser — avoid rejecting everything on shared topic words).
    strict=True for final repair / narration dedup.
    """
    ov = _fact_overlap(a, b)
    nums = _significant_numbers(a) & _significant_numbers(b)
    if strict:
        if ov >= 0.42:
            return True
        if nums and ov >= 0.22:
            return True
        if _shares_distinctive_term(a, b) and ov >= 0.26:
            return True
        return False
    if ov >= 0.62:
        return True
    if nums and ov >= 0.48:
        return True
    if _shares_distinctive_term(a, b) and ov >= 0.40:
        return True
    return False


def _facts_likely_same_topic(a: str, b: str) -> bool:
    return _facts_near_duplicate(a, b, strict=True)


def _strip_leading_fact_numbering(text: str) -> str:
    t = (text or "").strip()
    for _ in range(4):
        nxt = _LEADING_FACT_NUMBERING.sub("", t, count=1).strip()
        if nxt == t:
            break
        t = nxt
    return t


def _shares_distinctive_term(a: str, b: str) -> bool:
    la = f" {_strip_generation_artifacts(a).lower()} "
    lb = f" {_strip_generation_artifacts(b).lower()} "
    return any(term in la and term in lb for term in _DISTINCTIVE_FACT_TERMS)


def _bad_fact_indices(facts: list[str]) -> list[int]:
    bad: set[int] = {i for i, fact in enumerate(facts) if _has_placeholder_fact(fact)}
    for i, fact in enumerate(facts):
        for tag in _fact_theme_tags(fact):
            prior = sum(1 for j in range(i) if tag in _fact_theme_tags(facts[j]))
            if prior >= _theme_limit_for(tag):
                bad.add(i)
                break
    for i in range(len(facts)):
        if i in bad:
            continue
        for j in range(i):
            if _facts_likely_same_topic(facts[i], facts[j]):
                bad.add(i)
                break
    return sorted(bad)


def _accept_fact_at_index(facts: list[str], idx: int, candidate: str, *, strict: bool) -> bool:
    """Apply candidate at idx if it is unique vs all other slots."""
    others = [f for j, f in enumerate(facts) if j != idx]
    if not _line_passes_fact_filters(candidate, others, strict_dedup=strict):
        if strict and _line_passes_fact_filters(candidate, others, strict_dedup=False):
            facts[idx] = _strip_generation_artifacts(candidate)
            return True
        return False
    facts[idx] = _strip_generation_artifacts(candidate)
    return True


def _append_unique_facts(
    facts: list[str],
    batch: list[str],
    *,
    target: int,
    strict: bool = False,
) -> int:
    """Merge batch into facts with dedup; return count added."""
    added = 0
    for line in batch:
        if len(facts) >= target:
            break
        if _line_passes_fact_filters(line, facts, strict_dedup=strict):
            facts.append(_strip_generation_artifacts(line))
            added += 1
    return added


def _facts_phase1_system_prompt(*, need: int, lang_name: str) -> str:
    return f"""You write structured factual entertainment scripts for short-form / long compilations.
The user gives a HEADLINE or THEME (e.g. "facts about France"). You must produce EXACTLY {need} distinct, interesting, verifiable facts related to that theme.
Rules:
- Facts should be varied (history, culture, geography, science, language, food, people, quirks) when the theme allows.
- Each fact is ONE informative line (about 100-220 characters). Do NOT prefix lines with "1.", "Fact 1:", or any ordinal — numbering is handled outside the JSON.
- Each new fact must cover a different angle, entity, event, place, or statistic — never a close paraphrase of an earlier line in the batch or in "Already have" list.
- **No negative facts**: never write what the country "does not have", "is not known for", or debunk a false rumor — only positive, informative facts.
- **Theme spread**: do not add another fact about the same city landmark cluster, the same biome (e.g. second Amazon/Pantanal/Cerrado angle), the same festival, or the same named dish if that thread already appears twice in "Already have". Pick a fresh subtopic.
- **Language facts**: if mentioning official language, be precise (e.g. "the only Portuguese-speaking country in South America" — not "the only country in South America that speaks Portuguese", which is misleading).
- Avoid repeating the same idea. No URLs or markdown.
- Do not include myths, rumors, conspiracy claims, or uncertain claims presented as truth.
- Prefer broadly accepted facts from general knowledge; if uncertain, choose a safer fact.
- Output ONLY valid JSON: {{"facts": ["...", "..."]}} with exactly {need} strings.
Language for the fact lines: {lang_name}."""


async def _generate_facts_phase1(
    topic_clean: str,
    lang_name: str,
    control: dict | None,
) -> list[str]:
    """Generate FACTS50_TARGET facts in smaller JSON batches (more reliable than one 77-item blob)."""
    from pipeline_control import checkpoint

    batch_size = _facts_phase1_batch_size()
    facts: list[str] = []
    batch_idx = 0

    while len(facts) < FACTS50_TARGET:
        need = min(batch_size, FACTS50_TARGET - len(facts))
        batch_idx += 1
        sys = _facts_phase1_system_prompt(need=need, lang_name=lang_name)
        human_parts = [f"Theme / headline:\n{topic_clean}"]
        if facts:
            human_parts.append(
                f"\nAlready have {len(facts)} facts — add {need} NEW ones; "
                "do not repeat or closely paraphrase any line below:\n"
                + json.dumps(facts[-min(40, len(facts)):], ensure_ascii=False)
            )
        human = "\n".join(human_parts)

        await checkpoint(control)
        try:
            obj = await _invoke_json(sys, human)
        except Exception as e:
            logger.error(
                "[Mode5 facts50] Phase 1 batch {} (have {}) JSON failed: {}",
                batch_idx,
                len(facts),
                e,
            )
            raise ValueError(
                "Mode 5 (77 фактов): не удалось разобрать ответ модели (фаза 1). Повторите запуск."
            ) from e

        batch = [_strip_generation_artifacts(x) for x in _normalize_fact_lines(obj)]
        if len(batch) != need:
            logger.warning(
                "[Mode5 facts50] Phase 1 batch {} returned {} facts, expected {}",
                batch_idx,
                len(batch),
                need,
            )
            repair_sys = sys + f"\nYou returned {len(batch)} items. Fix to EXACTLY {need}."
            repair_human = human + "\n\nReturn corrected JSON only."
            try:
                obj = await _invoke_json(repair_sys, repair_human)
                batch = [_strip_generation_artifacts(x) for x in _normalize_fact_lines(obj)]
            except Exception as e:
                logger.error("[Mode5 facts50] Phase 1 batch {} repair failed: {}", batch_idx, e)

        added = _append_unique_facts(facts, batch, target=FACTS50_TARGET, strict=False)
        if added == 0 and need > 0:
            logger.warning(
                "[Mode5 facts50] Phase 1 batch {}: 0/{}/{} facts accepted after dedup (have {}) — retrying",
                batch_idx,
                len(batch),
                need,
                len(facts),
            )
            for retry in range(1, 4):
                retry_human = (
                    human
                    + f"\n\nCRITICAL (attempt {retry}/3): every line you just returned was too close to facts we already have. "
                    f"Write {need} NEW facts about **different** entities, places, events, people, or statistics. "
                    "Do not rephrase population, national parks, holidays, flags, or other topics already in the list."
                )
                try:
                    obj = await _invoke_json(sys, retry_human)
                    batch = [_strip_generation_artifacts(x) for x in _normalize_fact_lines(obj)]
                except Exception as e:
                    logger.warning("[Mode5 facts50] Phase 1 batch {} retry {} failed: {}", batch_idx, retry, e)
                    continue
                added = _append_unique_facts(facts, batch, target=FACTS50_TARGET, strict=False)
                if added > 0:
                    break
            if added == 0:
                prev_len = len(facts)
                try:
                    facts = await _complete_facts_to_target(
                        facts,
                        target=min(FACTS50_TARGET, prev_len + need),
                        lang_name=lang_name,
                        topic=topic_clean,
                    )
                    added = len(facts) - prev_len
                except Exception as e:
                    logger.warning("[Mode5 facts50] Phase 1 complete-fallback failed: {}", e)
            if added == 0:
                raise ValueError(
                    "Mode 5 (77 фактов): модель не добавила новых уникальных фактов на этом шаге. "
                    "Попробуйте другую формулировку темы или повторите запуск."
                )

    if len(facts) > FACTS50_TARGET:
        facts = facts[:FACTS50_TARGET]
    elif len(facts) < FACTS50_TARGET:
        facts = await _complete_facts_to_target(
            facts,
            target=FACTS50_TARGET,
            lang_name=lang_name,
            topic=topic_clean,
        )

    if len(facts) != FACTS50_TARGET:
        raise ValueError(
            f"Mode 5 (77 фактов): модель вернула {len(facts)} фактов вместо {FACTS50_TARGET}. Попробуйте ещё раз."
        )
    return facts


async def _complete_facts_to_target(
    facts: list[str],
    *,
    target: int,
    lang_name: str,
    topic: str,
) -> list[str]:
    """Ask the model for real missing facts instead of inserting placeholder lines."""
    out = [_strip_generation_artifacts(x) for x in facts[:target] if not _has_placeholder_fact(x)]
    while len(out) < target:
        need = target - len(out)
        sys = f"""You complete a list of distinct factual one-liners.
Output language: {lang_name}.
Rules:
- Add exactly {need} NEW, real, broadly verifiable facts about the same topic.
- Do not repeat any existing fact, entity angle, statistic, museum/site, or wording.
- No negative facts (do not say what the country lacks or does not have).
- No placeholders like "additional fact"; every line must be a finished informative fact.
- No numbering prefixes, no markdown.
- Keep each line about 100-220 characters.
- Output ONLY valid JSON: {{"facts": ["...", "..."]}} with exactly {need} strings."""
        human = (
            f"Topic:\n{topic}\n\n"
            "Existing facts to avoid repeating:\n"
            + json.dumps(out, ensure_ascii=False)
        )
        obj = await _invoke_json(sys, human)
        additions = [_strip_generation_artifacts(x) for x in _normalize_fact_lines(obj)]
        for add in additions:
            if len(out) >= target:
                break
            if _line_passes_fact_filters(add, out, strict_dedup=False):
                out.append(add)
        if len(out) < target and not additions:
            raise ValueError("model returned no usable replacement facts")
    return out[:target]


def _bad_narration_indices(narrations: list[str], facts: list[str]) -> list[int]:
    """Duplicate or near-duplicate narration blocks (including re-expanding the same fact topic)."""
    bad: set[int] = set()
    n = min(len(narrations), len(facts))
    for i in range(n):
        for j in range(i):
            na = narrations[i]
            nb = narrations[j]
            if _facts_likely_same_topic(na, nb) or _facts_likely_same_topic(facts[i], facts[j]):
                bad.add(i)
                break
            if _fact_overlap(na[:500], nb[:500]) >= 0.38:
                bad.add(i)
                break
    return sorted(bad)


async def _repair_bad_narration_slots(
    narrations: list[str],
    facts: list[str],
    *,
    topic: str,
    lang_name: str,
    max_rounds: int = 2,
) -> list[str]:
    out = [_strip_leading_fact_numbering(_strip_generation_artifacts(x)) for x in narrations]
    facts_clean = [_strip_generation_artifacts(x) for x in facts]
    for round_idx in range(max(1, max_rounds)):
        bad = _bad_narration_indices(out, facts_clean)
        if not bad:
            return out
        sys = f"""You are a strict editor for calm documentary fact narration.
Output language: {lang_name}.
Rewrite ONLY the listed narration slots (zero-based indices).
Rules:
- Each replacement must expand ONLY the paired fact one-liner at the same index — no new statistics or names unless implied by that fact line.
- Do not repeat topics, landmarks, holidays, or statistics already covered in other slots.
- No numbering prefixes ("1.", "Fact 12"), no second intro, no outro, no generic closing filler.
- One continuous paragraph per slot, 6–10 sentences, calm tone.
{_FACTS50_STOCK_CLOSER_BAN}
- Output ONLY valid JSON: {{"replacements": {{"12": "...", "18": "..."}}}}."""
        paired = [
            {"index": i, "fact": facts_clean[i] if i < len(facts_clean) else "", "narration": out[i]}
            for i in bad
        ]
        human = (
            f"Topic:\n{topic}\n\n"
            f"Slots to rewrite (zero-based): {bad}\n\n"
            "Problem slots:\n"
            + json.dumps(paired, ensure_ascii=False)
            + "\n\nAll fact one-liners (avoid repeating their topics in rewrites):\n"
            + json.dumps(facts_clean, ensure_ascii=False)
        )
        obj = await _invoke_json(sys, human)
        repl = obj.get("replacements")
        if not isinstance(repl, dict):
            logger.warning("[Mode5 facts50] Narration repair round {}: no replacements", round_idx + 1)
            continue
        for key, value in repl.items():
            try:
                idx = int(key)
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(out) and isinstance(value, str) and value.strip():
                out[idx] = _strip_leading_fact_numbering(_strip_generation_artifacts(value))
    remaining = _bad_narration_indices(out, facts_clean)
    if remaining:
        logger.warning("[Mode5 facts50] Narration duplicates remain at indices {}", remaining[:12])
    return out


async def _replace_fact_slots_one_by_one(
    facts: list[str],
    indices: list[int],
    *,
    topic: str,
    lang_name: str,
) -> list[str]:
    """Last-resort: one LLM call per bad index with a bounded avoid-list."""
    out = list(facts)
    for idx in indices:
        if idx < 0 or idx >= len(out):
            continue
        if idx not in _bad_fact_indices(out):
            continue
        others = [f for j, f in enumerate(out) if j != idx]
        fixed = False
        for attempt in range(1, 5):
            sys = f"""You write ONE distinct factual one-liner for a 77-facts sleep video.
Output language: {lang_name}.
Rules:
- Exactly one finished fact, 100-220 characters, broadly verifiable.
- Must NOT repeat or closely paraphrase any line in the avoid-list.
- Pick a different entity, place, event, person, or statistic than those already used.
- No numbering prefix, no placeholder, no markdown.
- Output ONLY valid JSON: {{"facts": ["..."]}} with exactly 1 string."""
            human = (
                f"Topic:\n{topic}\n\n"
                f"Rewrite ONLY slot index {idx} (zero-based). Avoid repeating these {len(others)} existing facts:\n"
                + json.dumps(others, ensure_ascii=False)
            )
            if attempt > 1:
                human += (
                    f"\n\nAttempt {attempt}: previous replacement was still too similar. "
                    "Choose a clearly different subtopic."
                )
            try:
                obj = await _invoke_json(sys, human)
                batch = [_strip_generation_artifacts(x) for x in _normalize_fact_lines(obj)]
            except Exception as e:
                logger.warning("[Mode5 facts50] Single-slot fact repair {} failed: {}", idx, e)
                continue
            for line in batch:
                if _accept_fact_at_index(out, idx, line, strict=True):
                    fixed = True
                    break
                if _accept_fact_at_index(out, idx, line, strict=False):
                    fixed = True
                    logger.info("[Mode5 facts50] Slot {} accepted with loose dedup", idx)
                    break
            if fixed:
                break
        if not fixed:
            logger.warning("[Mode5 facts50] Could not replace duplicate fact slot {}", idx)
    return out


async def _repair_bad_fact_slots(
    facts: list[str],
    *,
    topic: str,
    lang_name: str,
    max_rounds: int = 4,
) -> list[str]:
    out = [_strip_generation_artifacts(x) for x in facts]
    for round_idx in range(max(1, max_rounds)):
        bad = _bad_fact_indices(out)
        if not bad:
            return out
        sys = f"""You are a strict editor for a 77-facts script.
Output language: {lang_name}.
Rewrite ONLY the listed bad fact slots (zero-based indices).
Rules:
- Each replacement must be a finished, concrete, broadly verifiable fact about the topic.
- Must use a DIFFERENT entity/place/event/statistic than every other line in the list.
- No negative facts; no second fact on the same landmark city / biome / festival / named-dish thread already covered.
- Preserve the JSON keys as string indices.
- No placeholders, no numbering prefixes, no markdown.
- Output ONLY valid JSON: {{"replacements": {{"12": "new fact", "18": "new fact"}}}}."""
        human = (
            f"Topic:\n{topic}\n\n"
            f"Bad zero-based indices to replace:\n{bad}\n\n"
            "Facts at those indices (too similar to earlier lines):\n"
            + json.dumps({str(i): out[i] for i in bad}, ensure_ascii=False)
            + "\n\nAll facts to avoid repeating (full list):\n"
            + json.dumps(out, ensure_ascii=False)
        )
        try:
            obj = await _invoke_json(sys, human)
        except Exception as e:
            logger.warning("[Mode5 facts50] Fact repair round {} invoke failed: {}", round_idx + 1, e)
            continue
        repl = obj.get("replacements")
        if not isinstance(repl, dict):
            logger.warning("[Mode5 facts50] Fact repair round {} returned no replacements object", round_idx + 1)
            continue
        for key, value in repl.items():
            try:
                idx = int(key)
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(out) and isinstance(value, str) and value.strip():
                if not _accept_fact_at_index(out, idx, value, strict=True):
                    _accept_fact_at_index(out, idx, value, strict=False)
    remaining = _bad_fact_indices(out)
    if remaining:
        logger.warning(
            "[Mode5 facts50] Fact repair: {} duplicate slots remain, trying one-by-one ({})",
            len(remaining),
            remaining[:12],
        )
        out = await _replace_fact_slots_one_by_one(
            out, remaining, topic=topic, lang_name=lang_name
        )
    remaining = _bad_fact_indices(out)
    if remaining:
        logger.warning(
            "[Mode5 facts50] Filling {} stubborn duplicate slots from fresh completions ({})",
            len(remaining),
            remaining[:12],
        )
        try:
            extended = await _complete_facts_to_target(
                out,
                target=len(out) + len(remaining),
                lang_name=lang_name,
                topic=topic,
            )
            tail = extended[len(out) :]
            for idx, repl in zip(remaining, tail):
                if not _accept_fact_at_index(out, idx, repl, strict=True):
                    _accept_fact_at_index(out, idx, repl, strict=False)
        except Exception as e:
            logger.warning("[Mode5 facts50] Final duplicate fill failed: {}", e)
    remaining = _bad_fact_indices(out)
    if remaining:
        logger.warning(
            "[Mode5 facts50] {} duplicate fact slots remain after all repair passes {}; continuing anyway",
            len(remaining),
            remaining[:12],
        )
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
- Never rewrite into a negative fact ("X does not have…"). Never debunk a rumor as the whole fact.
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
    lang_map = {
        "ru": "Russian",
        "en": "English",
        "es": "Spanish",
        "fr": "French",
        "de": "German",
    }
    if lang not in lang_map:
        lang = "ru"
    lang_name = lang_map[lang]

    facts = await _generate_facts_phase1(topic_clean, lang_name, control)
    facts = await _repair_bad_fact_slots(facts, topic=topic_clean, lang_name=lang_name)

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
        verified_facts = await _verify_facts(topic_clean, lang_name, facts)
        facts = await _repair_bad_fact_slots(verified_facts, topic=topic_clean, lang_name=lang_name)
    except Exception as e:
        logger.warning(f"[Mode5 facts50] Fact verification pass failed, using phase-1 facts as fallback: {e}")

    await checkpoint(control)

    n_facts = len(facts)

    async def narr_batch(start_i: int, end_i: int) -> list[str]:
        batch_facts = facts[start_i:end_i]
        cont = ""
        if start_i > 0:
            cont = (
                f"This batch is facts {start_i + 1}–{end_i} of {n_facts} in ONE continuous episode. "
                "Do NOT restart numbering at 1. Do NOT open paragraphs with 'Fact 1', '1.', or 'First fact'. "
                "Do not re-cover topics already narrated earlier in the episode.\n\n"
            )
        sys2 = f"""You write voiceover narration for calm, scientific sleep-style documentary videos.
Narration language: {lang_name}.
For EACH fact in the batch, write ONE continuous paragraph to be read aloud (no bullet points).
Style anchor (keep stable across all batches): calm documentary narrator, precise but warm, medium sentence length, no slang.
- Tone: slow, warm, logical — like a quiet narrator for sleep, NOT a dramatic trailer and NOT religious preaching.
- Structure: 6–10 sentences. Build a clear mini-arc: introduce the fact -> explain context -> significance -> one concrete closing sentence.
- End each paragraph on its own terms; do not tack on generic filler sentences just to lengthen the text.
{_FACTS50_STOCK_CLOSER_BAN}
- Do not add meta lines about "checking encyclopedias" or "sources" unless essential; avoid identical disclaimers at the end of every fact.
- The video has a SEPARATE spoken intro and outro. Inside fact paragraphs: do NOT welcome the listener, do NOT announce "today we have N facts about…", do NOT recap the episode format, do NOT thank the audience or sign off as if the episode is ending.
- The first fact in the full video is fact #{start_i + 1} in this batch when start_i==0: start directly with the substance of that fact—no second introduction to the series or headline.
- The last fact in the full video may appear in this batch: end on that fact's idea only—no lines like "that was all", "thank you for listening", "these were all the facts" (the outro handles closure).
- Never prefix paragraphs with ordinals or labels ("1.", "Fact 5", "The next fact"). The episode order is implicit.
- Keep narration strictly aligned with the provided verified fact line. If you are unsure about precise details, keep wording general instead of inventing specifics.
- For rivers and geography: if a fact names a tributary, you may briefly note its place in the larger river system — do not invent rankings.
- 6–10 sentences per fact, concrete and engaging; add context and comparisons, but do not fabricate names, years, quotes, or exact statistics beyond the fact line.
- Every paragraph must have its own closing wording. Do not repeatedly end with the same formula.
- Avoid overusing generic conclusion openers such as "Таким образом", "Так", "In this way", "Thus", "De este modo", "Ainsi", or "Auf diese Weise"; use them rarely, not as a template.
- Do not use visible stress marks or pronunciation marks in normal words.
- Do not turn a thin fact into tourist-brochure filler. Add one concrete context angle, then stop.
- If this fact's one-liner is already well covered by earlier narrations in the episode (same city, biome, festival, or dish), stay brief and add only one new angle — do not re-introduce the same landmark or holiday.
- Plain text only. Aim for roughly 800–1500 characters of real narration per fact when the material allows; if shorter, the pipeline adds invisible padding for the audio API—do not pad with empty prose.
- Output ONLY valid JSON: {{"narrations": ["paragraph1", "paragraph2", ...]}} with exactly {len(batch_facts)} strings in the same order as input facts."""

        human2 = (
            cont
            + f"Video theme / headline:\n{topic_clean}\n\n"
            f"Facts {start_i + 1}–{end_i} of {n_facts} (in order):\n"
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
        return [
            _ensure_min_narration_length(
                _strip_leading_fact_numbering(_strip_generation_artifacts(x)),
                language=lang,
            )
            for x in narr
        ]

    # Батчим озвучки параллельно по фактической длине ``facts`` (полный релиз или укороченный test_run).
    tasks = []
    for start in range(0, n_facts, _NARRATION_BATCH):
        end = min(n_facts, start + _NARRATION_BATCH)
        tasks.append(narr_batch(start, end))
    narr_chunks = await asyncio.gather(*tasks)
    await checkpoint(control)
    narrations = [x for batch in narr_chunks for x in batch]
    if len(narrations) != n_facts:
        narrations = _pad_narrations_to_facts(facts, narrations, language=lang)
        narrations = [_ensure_min_narration_length(_strip_generation_artifacts(x), language=lang) for x in narrations[:n_facts]]
    narrations = [
        _ensure_min_narration_length(
            _strip_leading_fact_numbering(_strip_generation_artifacts(x)),
            language=lang,
        )
        for x in narrations[:n_facts]
    ]
    try:
        narrations = await _repair_bad_narration_slots(
            narrations,
            facts,
            topic=topic_clean,
            lang_name=lang_name,
        )
    except Exception as e:
        logger.warning(f"[Mode5 facts50] Narration dedup repair skipped: {e}")
    narrations = [
        _ensure_min_narration_length(
            _strip_leading_fact_numbering(_strip_generation_artifacts(x)),
            language=lang,
        )
        for x in narrations[:n_facts]
    ]

    logger.success(f"[Mode5 facts50] Generated {n_facts} facts + narrations for: {topic_clean[:80]}")
    return facts, narrations
