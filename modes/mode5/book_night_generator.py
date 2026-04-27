"""
Mode 5 «book_night»: название книги → план по настоящей структуре книги (главы/подглавы) →
озвучка по каждой подглаве. Число подглав задаёт оглавление книги (в допустимом диапазоне).
Суммарный объём текста **подгоняется под тот же порядок, что и режим «77 фактов»** (~1.5 ч озвучки): при малом
числе подглав каждый блок длиннее; при большом — короче, но в сумме остаёмся около того же total chars.
"""

from __future__ import annotations

import asyncio
import copy
import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from config import settings
from agents.video_editor.tts import NONSPOKEN_LEN_FILLER_CHAR, append_nonspeaking_length_pad

from modes.mode5.facts50_generator import (
    FACTS50_TARGET,
    _MIN_NARRATION_CHARS,
    _NARRATION_BATCH as _FACTS50_NARRATION_BATCH,
)
from modes.mode5.narration_quality import adjacent_repetition_pairs
from modes.mode5.outline_generator import (
    _count_subchapters,
    _flatten_outline,
    _normalize_narrations,
    _normalize_outline,
    _outline_from_flat_rows,
    _pad_narrations_to_rows,
    _parse_json_obj,
)
from modes.mode5.quality_gate import remediate_mode5_narrations
from utils.llm import make_llm

from agents.fact_miner.fetch import gather_evidence

_MIN_BOOK_CHAPTERS = 4
_MAX_BOOK_CHAPTERS = 16
_MIN_SUBS_PER_CHAPTER = 2
_MAX_SUBS_PER_CHAPTER = 40
# Сколько подглав всего — от реальной логики книги, не фиксированное «77».
_MIN_BOOK_SUBS_TOTAL = 10
_MAX_BOOK_SUBS_TOTAL = 80

# Wikipedia + DDG extracts; not the book text — caps keep prompts bounded.
_MAX_EVIDENCE_OUTLINE_CHARS = 9000
_MAX_EVIDENCE_NARRATION_CHARS = 4500

# Суммарная длина **озвучиваемого** текста как у «77 фактов» (факты50: 800–1500 на факт; берём верхнюю половину диапазона — модель часто недобирает).
_FACTS50_REFERENCE_TOTAL_CHARS = int(FACTS50_TARGET * 1320)
_LLM_NETWORK_RETRIES = 4
_LLM_NETWORK_RETRY_BASE_DELAY_SEC = 1.2


def _is_transient_llm_error(err: BaseException) -> bool:
    name = type(err).__name__.lower()
    text = f"{name} {err}".lower()
    needles = (
        "apiconnectionerror",
        "connecterror",
        "connection error",
        "connectionerror",
        "getaddrinfo failed",
        "temporary failure in name resolution",
        "dns",
        "timeout",
        "timed out",
        "service unavailable",
        "502",
        "503",
        "504",
    )
    return any(n in text for n in needles)


def _narration_depth_scale(n_top_level_chapters: int) -> float:
    """Меньше верхних глав книги → выше масштаб (длиннее/глубже текст на одну подглаву)."""
    nc = max(_MIN_BOOK_CHAPTERS, min(int(n_top_level_chapters), _MAX_BOOK_CHAPTERS))
    span = float(_MAX_BOOK_CHAPTERS - _MIN_BOOK_CHAPTERS)
    if span <= 0:
        return 1.0
    t = (_MAX_BOOK_CHAPTERS - nc) / span  # при 4 главах t≈1, при 16 — t≈0
    return 0.88 + t * 0.36  # ~0.88 (много глав) … ~1.24 (мало глав)


def _book_night_narration_targets(
    n_top_level_chapters: int,
    n_subchapters_total: int,
) -> tuple[int, int, int, int]:
    """
    Цели для озвучки одной подглавы: (char_lo, char_hi, min_sentences, max_sentences).
    Суммарно по всем подглавам стремимся к тому же порядку объёма, что и 77 фактов (~1.5 ч озвучки),
    поэтому при малом числе подглав каждая должна быть существенно длиннее «короткого клипа».
    """
    n_sub = max(1, int(n_subchapters_total))
    per_mid = float(_FACTS50_REFERENCE_TOTAL_CHARS) / float(n_sub)
    s = _narration_depth_scale(n_top_level_chapters)
    # Немного тянем вверх при «мало верхних глав» — больше смысла на подглаву внутри того же общего бюджета.
    per_mid *= 0.92 + 0.08 * min(1.0, max(0.0, s - 0.88) / 0.36)

    hi_raw = int(per_mid * 1.1)
    lo_raw = int(per_mid * 0.9)
    hi = min(7200, max(900, hi_raw))
    lo = max(800, min(hi - 400, lo_raw))
    if lo > hi - 350:
        lo = max(800, hi - 500)

    # Предложения: длиннее блок — больше предложений (в пределах разумного для одного абзаца).
    sent_lo = 7 if per_mid >= 1400 else 6
    if per_mid >= 2800:
        sent_lo = 10
    if per_mid >= 4500:
        sent_lo = 12
    sent_hi = min(28, max(sent_lo + 4, int(8 + per_mid / 420.0)))
    return lo, hi, sent_lo, sent_hi


def _book_night_narration_batch_size(n_sub: int, narr_hi: int) -> int:
    """Меньше подглав в батче, если каждая должна быть очень длинной (лимит ответа модели)."""
    if narr_hi >= 5500:
        return max(1, min(3, n_sub))
    if narr_hi >= 4000:
        return max(1, min(5, n_sub))
    if narr_hi >= 2800:
        return max(2, min(8, n_sub))
    return max(2, min(_FACTS50_NARRATION_BATCH, n_sub))


def _book_night_narration_max_tokens(batch_len: int, narr_hi: int) -> int:
    """Грубая оценка токенов на JSON с несколькими длинными абзацами."""
    est = 1800 + batch_len * int(narr_hi * 0.42)
    return min(32000, max(4096, est))


def _spoken_plain_len(text: str) -> int:
    """Длина текста, который реально влияет на TTS (невидимый паддинг VoiceAPI не считается)."""
    return len((text or "").replace(NONSPOKEN_LEN_FILLER_CHAR, "").strip())


def _ensure_book_night_voiceapi_floor(text: str, *, language: str) -> str:
    """Только минимум для VoiceAPI; «длину эпизода» даёт осмысленный текст после expand, не \\u200b."""
    _ = language
    t = (text or "").strip()
    return append_nonspeaking_length_pad(t, _MIN_NARRATION_CHARS)


async def _expand_one_book_night_narration(
    text: str,
    *,
    min_chars: int,
    max_chars: int,
    lang_name: str,
    subsection_line: str,
    book_query: str,
    attempt: int,
) -> str:
    """Добавляет осмысленный объём; без новых «фактов из книги» (статистика, даты, имена)."""
    base = (text or "").replace(NONSPOKEN_LEN_FILLER_CHAR, "").strip()
    if _spoken_plain_len(base) >= int(min_chars * 0.92):
        return base
    floor = max(min_chars, int(min_chars * (1.05 if attempt >= 2 else 1.0)))
    mt = min(14000, 900 + int(floor * 2.15))
    sys = SystemMessage(
        content=(
            f"You lengthen ONE calm sleep-time audiobook paragraph. Output language: {lang_name} only.\n"
            f"The paragraph must be at least {floor} characters (plain letters/spaces/punctuation — not counting filler).\n"
            "Keep the same ideas and tone; do NOT add new statistics, named studies, dates, dialogue, long quotes, or invented book details. "
            "You may add: gentle transitions, reframing the same thought in other words, sensory atmosphere, and a softer closing. "
            "One continuous paragraph, no bullet points, no title line, no markdown fences."
        )
    )
    hum = HumanMessage(
        content=(
            f"Book (user request):\n{book_query}\n\n"
            f"Subsection:\n{subsection_line}\n\n"
            f"Current narration ({_spoken_plain_len(base)} chars):\n{base}\n\n"
            f"Rewrite into a longer single paragraph (≥{floor} chars)."
        )
    )
    llm = _scenario_llm(temperature=0.34 if attempt == 1 else 0.28, max_tokens=mt)
    resp = await llm.ainvoke([sys, hum])
    raw = resp.content if isinstance(resp.content, str) else str(resp.content)
    out = _strip_code_fence_like(raw).strip().strip('"').strip("'")
    if _spoken_plain_len(out) < max(_spoken_plain_len(base), int(min_chars * 0.55)):
        return base
    if _spoken_plain_len(out) > max_chars + 800:
        out = out[: max_chars + 800].rsplit(".", 1)[0] + "."
    return out


def _strip_code_fence_like(s: str) -> str:
    t = (s or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t).strip()
    return t


async def _expand_book_night_narrations_to_target(
    narrations: list[str],
    flat_rows: list[dict[str, Any]],
    *,
    narr_lo: int,
    narr_hi: int,
    lang_name: str,
    book_query: str,
    control: dict | None,
) -> list[str]:
    """Параллельно дотягиваем блоки, где модель сильно укоротила текст (\\u200b длину озвучки не даёт)."""
    _ = control
    sem = asyncio.Semaphore(max(2, min(8, int(getattr(settings, "mode5_facts50_parallel", 8) or 8))))

    async def _one(i: int, t: str) -> str:
        async with sem:
            if i >= len(flat_rows):
                return t
            row = flat_rows[i]
            line = f"{row.get('chapter_title', '')} / {row.get('subchapter_title', '')}".strip()
            cur = (t or "").replace(NONSPOKEN_LEN_FILLER_CHAR, "").strip()
            for att in (1, 2):
                if _spoken_plain_len(cur) >= int(narr_lo * 0.92):
                    break
                nxt = await _expand_one_book_night_narration(
                    cur,
                    min_chars=narr_lo,
                    max_chars=narr_hi,
                    lang_name=lang_name,
                    subsection_line=line,
                    book_query=book_query,
                    attempt=att,
                )
                if _spoken_plain_len(nxt) <= _spoken_plain_len(cur) + 80:
                    break
                cur = nxt
            if _spoken_plain_len(cur) < int(narr_lo * 0.88):
                logger.warning(
                    f"[Mode5 book_night] Subsection {i + 1} still short after expand: "
                    f"{_spoken_plain_len(cur)} chars (target lo={narr_lo})"
                )
            return cur

    return list(await asyncio.gather(*(_one(i, t) for i, t in enumerate(narrations))))


async def _dedupe_book_night_neighboring_blocks(
    items: list[str],
    *,
    flat_rows: list[dict[str, Any]],
    lang_name: str,
    book_query: str,
) -> list[str]:
    out = list(items)
    pairs = adjacent_repetition_pairs(out, threshold=0.08)
    if not pairs:
        return out
    for idx, score in pairs[: max(1, min(6, len(pairs)))]:
        if idx <= 0 or idx >= len(out):
            continue
        row = flat_rows[idx] if idx < len(flat_rows) else {}
        sys = SystemMessage(
            content=(
                f"You are a careful editor for calm book-night narration. Output language: {lang_name} only.\n"
                "Rewrite ONLY the current subsection to reduce repeated wording and repeated thesis from the previous subsection. "
                "Advance the argument by one concrete step tied to the current subsection title. Preserve meaning, tone, and approximate length. "
                "Do not invent new book details, dates, studies, quotes, page numbers, dialogue, or anecdotes. "
                "One continuous paragraph, no markdown."
            )
        )
        hum = HumanMessage(
            content=(
                f"Book:\n{book_query}\n\n"
                f"Current subsection:\n{row.get('chapter_title', '')} / {row.get('subchapter_title', '')}\n"
                f"Plan:\n{row.get('coverage', '')}\n\n"
                f"Previous subsection (do not repeat wording/thesis):\n{out[idx - 1][:2200]}\n\n"
                f"Current subsection to rewrite (overlap score {score:.3f}):\n{out[idx][:2600]}\n\n"
                "Return only the rewritten current subsection."
            )
        )
        try:
            llm = _scenario_llm(temperature=0.24, max_tokens=min(10000, 1200 + int(len(out[idx]) * 0.8)))
            resp = await llm.ainvoke([sys, hum])
            raw = resp.content if isinstance(resp.content, str) else str(resp.content)
            candidate = _strip_code_fence_like(raw).strip().strip('"').strip("'")
            if _spoken_plain_len(candidate) >= int(_spoken_plain_len(out[idx]) * 0.62):
                out[idx] = candidate
                logger.info(f"[Mode5 book_night] Deduped neighboring subsection {idx + 1} (overlap={score:.3f})")
        except Exception as e:
            logger.warning(f"[Mode5 book_night] Neighbor dedup skipped for subsection {idx + 1}: {e}")
    return out


def _scenario_llm(*, temperature: float = 0.4, **kwargs: Any):
    model = getattr(settings, "openrouter_scenario_model", None) or settings.openrouter_model
    return make_llm(temperature=temperature, model=model, **kwargs)


def _clip_evidence(text: str, max_chars: int) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[:max_chars].rstrip() + "\n[…truncated]"


async def _book_grounding_evidence(book_query: str) -> tuple[str, list[str]]:
    """Short encyclopedic / web snippets — reduces invented 'facts from the book'."""
    try:
        evidence, sources = await gather_evidence(book_query)
    except Exception as e:
        logger.warning(f"[Mode5 book_night] gather_evidence failed: {e}")
        return "", []
    if not (evidence or "").strip():
        return "", sources
    return _clip_evidence(evidence, _MAX_EVIDENCE_OUTLINE_CHARS), sources


def _sources_block_for_human(evidence: str) -> str:
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
        "in \"coverage\" or anywhere else."
    )


async def _invoke_json(
    system: str,
    human: str,
    *,
    temperature: float = 0.4,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    attempts = [
        (
            system,
            human,
            temperature,
        ),
        (
            system
            + "\nCRITICAL: Return one valid JSON object only. No prose before JSON. No markdown fences. "
            + "Escape all inner quotes inside strings correctly. Do not truncate strings.",
            human + "\n\nReturn compact valid JSON only.",
            max(0.0, float(temperature) - 0.12),
        ),
    ]
    last_err: Exception | None = None
    for idx, (sys_prompt, human_prompt, temp) in enumerate(attempts, 1):
        for net_try in range(1, _LLM_NETWORK_RETRIES + 1):
            kw: dict[str, Any] = {}
            if max_tokens is not None:
                kw["max_tokens"] = max_tokens
            llm = _scenario_llm(temperature=temp, **kw)
            try:
                msg = await llm.ainvoke(
                    [SystemMessage(content=sys_prompt), HumanMessage(content=human_prompt)]
                )
            except Exception as e:
                last_err = e
                if not _is_transient_llm_error(e) or net_try >= _LLM_NETWORK_RETRIES:
                    raise
                delay = _LLM_NETWORK_RETRY_BASE_DELAY_SEC * (2 ** (net_try - 1))
                logger.warning(
                    f"[Mode5 book_night] transient LLM error on attempt {idx}/{len(attempts)} "
                    f"net_try={net_try}/{_LLM_NETWORK_RETRIES}: {type(e).__name__}: {e}. "
                    f"Retry in {delay:.1f}s"
                )
                await asyncio.sleep(delay)
                continue
            raw = msg.content if isinstance(msg.content, str) else str(msg.content)
            try:
                return _parse_json_obj(raw)
            except Exception as e:
                last_err = e
                preview = re.sub(r"\s+", " ", raw or "").strip()[:500]
                logger.warning(
                    f"[Mode5 book_night] JSON parse failed on attempt {idx}: {e}. Raw preview: {preview}"
                )
                break
    if last_err is not None:
        raise last_err
    raise ValueError("Mode 5 (книга на ночь): empty JSON parse state")


def _book_night_outline_ok(outline: dict[str, Any]) -> bool:
    chs = outline.get("chapters") or []
    n_ch = len(chs)
    if n_ch < _MIN_BOOK_CHAPTERS or n_ch > _MAX_BOOK_CHAPTERS:
        return False
    n_sub = 0
    for ch in chs:
        subs = ch.get("subchapters") or []
        lc = len(subs)
        if lc < _MIN_SUBS_PER_CHAPTER or lc > _MAX_SUBS_PER_CHAPTER:
            return False
        n_sub += lc
    return _MIN_BOOK_SUBS_TOTAL <= n_sub <= _MAX_BOOK_SUBS_TOTAL


def _split_richest_chapter_for_min_count(outline: dict[str, Any], *, lang: str) -> dict[str, Any]:
    """Делит одну главу с наибольшим числом подглав пополам (≥2+2), чтобы увеличить число верхнеуровневых глав."""
    chs = copy.deepcopy(outline.get("chapters") or [])
    if not chs:
        return outline
    best_i = -1
    best_n = 0
    for i, ch in enumerate(chs):
        n = len(ch.get("subchapters") or [])
        if n >= 2 * _MIN_SUBS_PER_CHAPTER and n > best_n:
            best_n = n
            best_i = i
    if best_i < 0:
        return outline
    subs = list(chs[best_i].get("subchapters") or [])
    lo = _MIN_SUBS_PER_CHAPTER
    hi = len(subs) - _MIN_SUBS_PER_CHAPTER
    if hi < lo:
        return outline
    split_at = max(lo, min(len(subs) // 2, hi))
    part1, part2 = subs[:split_at], subs[split_at:]
    if len(part1) < lo or len(part2) < lo:
        return outline
    base = str(chs[best_i].get("title") or ("Часть" if lang == "ru" else "Part")).strip()
    if lang == "ru":
        t1, t2 = f"{base} (часть 1)", f"{base} (часть 2)"
    else:
        t1, t2 = f"{base} (part 1)", f"{base} (part 2)"
    new_chs = chs[:best_i] + [
        {"title": t1, "subchapters": part1},
        {"title": t2, "subchapters": part2},
    ] + chs[best_i + 1 :]
    return {**outline, "chapters": new_chs}


def _merge_smallest_adjacent_pair(outline: dict[str, Any]) -> dict[str, Any]:
    """Склеивает соседние главы с наименьшей суммой подглав, если сумма ≤ _MAX_SUBS_PER_CHAPTER."""
    chs = copy.deepcopy(outline.get("chapters") or [])
    if len(chs) < 2:
        return outline
    best_i: int | None = None
    best_sum = 10**9
    for i in range(len(chs) - 1):
        a = chs[i].get("subchapters") or []
        b = chs[i + 1].get("subchapters") or []
        s = len(a) + len(b)
        if s > _MAX_SUBS_PER_CHAPTER:
            continue
        if s < best_sum:
            best_sum = s
            best_i = i
    if best_i is None:
        return outline
    i = best_i
    merged_subs = list(chs[i].get("subchapters") or []) + list(chs[i + 1].get("subchapters") or [])
    t1 = str(chs[i].get("title") or "").strip()
    t2 = str(chs[i + 1].get("title") or "").strip()
    merged_title = (t1 + " · " + t2).strip()[:240]
    new_chs = chs[:i] + [{"title": merged_title, "subchapters": merged_subs}] + chs[i + 2 :]
    return {**outline, "chapters": new_chs}


def _programmatic_enforce_chapter_bounds(outline: dict[str, Any], *, lang: str) -> dict[str, Any]:
    """Последняя линия защиты: слишком мало верхних глав → деление самой «толстой»; слишком много → слияние соседей."""
    o = _normalize_outline(copy.deepcopy(outline))
    for _ in range(40):
        if _book_night_outline_ok(o):
            return o
        n_ch = len(o.get("chapters") or [])
        if n_ch < _MIN_BOOK_CHAPTERS:
            before = n_ch
            o = _normalize_outline(_split_richest_chapter_for_min_count(o, lang=lang))
            if len(o.get("chapters") or []) <= before:
                break
            continue
        if n_ch > _MAX_BOOK_CHAPTERS:
            before = n_ch
            o = _normalize_outline(_merge_smallest_adjacent_pair(o))
            if len(o.get("chapters") or []) >= before:
                break
            continue
        break
    return o


async def generate_book_night_script(
    book_query: str,
    language: str,
    *,
    control: dict | None = None,
) -> tuple[dict[str, Any], list[str], str]:
    """
    Returns (outline_doc, narrations, script_clean).
    Same outline JSON shape as «план из описания» for pipeline / get_chunk_outline_labels.
    """
    from pipeline_control import checkpoint

    q = re.sub(r"\s+", " ", (book_query or "").strip())
    if len(q) < 8:
        raise ValueError("Mode 5 (книга на ночь): введите название книги (от 8 символов), можно с автором")

    lang = (language or "ru").strip().lower()
    if lang not in ("ru", "en"):
        lang = "ru"
    lang_name = "Russian" if lang == "ru" else "English"

    await checkpoint(control)
    evidence_outline, evidence_sources = await _book_grounding_evidence(q)
    if evidence_outline:
        logger.info(f"[Mode5 book_night] Grounding snippets ({len(evidence_outline)} chars) from: {evidence_sources}")
    else:
        logger.warning("[Mode5 book_night] No external grounding snippets — model must stay high-level")

    evidence_narr = _clip_evidence(evidence_outline, _MAX_EVIDENCE_NARRATION_CHARS)
    grounding_snippets_block = (
        evidence_narr.strip()
        if evidence_narr.strip()
        else "(No snippets retrieved — be maximally conservative: no invented book facts, numbers, named studies, dates, dialogue, long quotes, or specific anecdotes.)"
    )

    sys1 = f"""You are a nonfiction book expert and editor for **sleep-time audiobook-style summaries**.
The user names a **book** (title, optionally author). You must design a chapter plan that **follows the real published structure** of that work as closely as possible: use authentic part/chapter/habit names when the book is well-known (e.g. Covey's habits, standard TOC translations). If the exact TOC is uncertain, approximate the widely accepted structure and keep order faithful to the original book — do NOT invent a random self-help outline unrelated to that title.

Truthfulness / anti-hallucination (mandatory):
- The user message may include EXTERNAL_SOURCES: third-party encyclopedia/search snippets only, not the book. When present, align author, topic, and broad themes with them; do **not** contradict a clear statement in those sources.
- Each "coverage" must only state ideas you could defend from: (1) EXTERNAL_SOURCES, (2) uncontroversial, widely published summaries of this title, or (3) the subsection/chapter titles themselves as structural anchors — **not** invented scenes, statistics, named papers, dates, page numbers, dialogue, or "the author writes that…" specifics unless they plainly appear in EXTERNAL_SOURCES.
- If EXTERNAL_SOURCES are missing or thin, keep "coverage" high-level and structural; never fill gaps with vivid made-up details.

Output ONLY valid JSON with this exact shape:
{{
  "working_title": "string — listening episode title in {lang_name}",
  "logline": "string — one sentence: calm promise for a night listener",
  "chapters": [
    {{
      "title": "string — chapter/part title as in the book (or faithful translation)",
      "subchapters": [
        {{"title": "string — subsection title", "coverage": "string — 1–2 sentences: ideas from the book this block must summarize (no long prose here)"}}
      ]
    }}
  ]
}}

Hard constraints:
- All strings in {lang_name}.
- Between {_MIN_BOOK_CHAPTERS} and {_MAX_BOOK_CHAPTERS} top-level chapters inclusive (book parts / main chapters).
- Each chapter has between {_MIN_SUBS_PER_CHAPTER} and {_MAX_SUBS_PER_CHAPTER} subchapters inclusive.
- Total subchapters across ALL chapters must be between {_MIN_BOOK_SUBS_TOTAL} and {_MAX_BOOK_SUBS_TOTAL} inclusive. Choose the count that **best matches how this book is really subdivided** (real TOC / parts / habits / sections). Do **not** pad with fake subsections or split one natural section into many slices just to hit a round number. If the book naturally has very few top-level units, use finer **authentic** subsection names (as in real editions) until you reach at least {_MIN_BOOK_SUBS_TOTAL}. If the outline would exceed {_MAX_BOOK_SUBS_TOTAL}, merge smaller adjacent units **without breaking reading order**.
- The JSON \"chapters\" array length must **never** be fewer than {_MIN_BOOK_CHAPTERS} or greater than {_MAX_BOOK_CHAPTERS}. If a printed TOC has only 2–3 top-level parts, **re-partition** the same book into at least {_MIN_BOOK_CHAPTERS} coherent major blocks (e.g. framing / early arc / middle / integration) using believable thematic or structural names — **do not output 2 or 3 objects** in \"chapters\". If you would exceed {_MAX_BOOK_CHAPTERS}, merge adjacent major parts so each remains a believable book section.
- Subchapters must map to consecutive reading order through the book (no random reordering).
- Depth vs **number of top-level chapters**: **Fewer** chapters (closer to {_MIN_BOOK_CHAPTERS}) → the same book is split into fewer big buckets, so each subchapter must carry **more** planned substance in "coverage" (still brief notes, but **denser** beats to unpack later). **More** chapters (closer to {_MAX_BOOK_CHAPTERS}) → **tighter** "coverage" per subchapter so blocks stay distinct for night listening.
- "coverage" is planning only; do NOT write the final narration here.
- Do not present invented quotes, page numbers, or precise statistics as facts; planning text only."""

    human1 = (
        f"""Book to summarize for a calm night listen (title / author as given by user):\n{q}"""
        + _sources_block_for_human(evidence_outline)
        + "\n\nDesign the outline JSON now."
    )

    await checkpoint(control)
    try:
        raw1 = await _invoke_json(sys1, human1, temperature=0.35)
    except Exception as e:
        logger.error(f"[Mode5 book_night] Phase 1 failed: {e}")
        raise ValueError("Mode 5 (книга на ночь): не удалось получить структуру книги от модели. Повторите запуск.") from e

    outline = _normalize_outline(raw1)
    repair_human = (
        f"Same book:\n{q}"
        + _sources_block_for_human(evidence_outline)
        + "\n\nReturn corrected JSON only."
    )

    if not _book_night_outline_ok(outline):
        n_ch0 = len(outline.get("chapters") or [])
        n_sub = _count_subchapters(outline)
        repair_sys = (
            sys1
            + f"\nYour JSON had {n_ch0} chapters and {n_sub} subchapters. "
            f"Fix ALL constraints: {_MIN_BOOK_CHAPTERS}–{_MAX_BOOK_CHAPTERS} chapters, "
            f"{_MIN_SUBS_PER_CHAPTER}–{_MAX_SUBS_PER_CHAPTER} subchapters per chapter, "
            f"total subchapters {_MIN_BOOK_SUBS_TOTAL}–{_MAX_BOOK_SUBS_TOTAL} (book-realistic count, not a fixed quota)."
        )
        try:
            await checkpoint(control)
            outline = _normalize_outline(await _invoke_json(repair_sys, repair_human, temperature=0.3))
        except Exception as e:
            logger.error(f"[Mode5 book_night] Phase 1 repair failed: {e}")

    if not _book_night_outline_ok(outline):
        n_sub = _count_subchapters(outline)
        if n_sub > _MAX_BOOK_SUBS_TOTAL:
            repair_merge = (
                sys1
                + f"\nYou have {n_sub} subchapters (maximum {_MAX_BOOK_SUBS_TOTAL}). "
                "Merge adjacent subsections where the book naturally groups them; preserve reading order; "
                f"target total between {_MIN_BOOK_SUBS_TOTAL} and {_MAX_BOOK_SUBS_TOTAL}."
            )
            try:
                await checkpoint(control)
                outline = _normalize_outline(await _invoke_json(repair_merge, repair_human, temperature=0.28))
            except Exception as e:
                logger.error(f"[Mode5 book_night] Phase 1 merge repair failed: {e}")
        elif 0 < n_sub < _MIN_BOOK_SUBS_TOTAL:
            repair2 = (
                sys1
                + f"\nYou have only {n_sub} subchapters (minimum {_MIN_BOOK_SUBS_TOTAL}). "
                "Split large chapters into **authentic** subsections (as in real editions or standard TOC), "
                f"preserving order, until total is between {_MIN_BOOK_SUBS_TOTAL} and {_MAX_BOOK_SUBS_TOTAL}."
            )
            try:
                await checkpoint(control)
                outline = _normalize_outline(await _invoke_json(repair2, repair_human, temperature=0.28))
            except Exception as e:
                logger.error(f"[Mode5 book_night] Phase 1 split repair failed: {e}")

    if not _book_night_outline_ok(outline):
        n_ch_bad = len(outline.get("chapters") or [])
        n_sub_bad = _count_subchapters(outline)
        if n_ch_bad < _MIN_BOOK_CHAPTERS or n_ch_bad > _MAX_BOOK_CHAPTERS:
            repair_ch = (
                sys1
                + f"\n\nCRITICAL: the \"chapters\" array had length {n_ch_bad}; it MUST be between {_MIN_BOOK_CHAPTERS} and {_MAX_BOOK_CHAPTERS} inclusive. "
                f"Total subchapters is {n_sub_bad} (must stay {_MIN_BOOK_SUBS_TOTAL}–{_MAX_BOOK_SUBS_TOTAL}; each chapter {_MIN_SUBS_PER_CHAPTER}–{_MAX_SUBS_PER_CHAPTER} subchapters). "
                "If too **few** top-level chapters: **split** one major part into two chapters and **move** subchapters, or add a missing real major division from the book's arc. "
                "If too **many** top-level chapters: **merge** two adjacent chapters into one (concatenate their \"subchapters\" in reading order). "
                "Return the **full** corrected JSON."
            )
            try:
                await checkpoint(control)
                outline = _normalize_outline(await _invoke_json(repair_ch, repair_human, temperature=0.25))
            except Exception as e:
                logger.error(f"[Mode5 book_night] Phase 1 chapter-count repair failed: {e}")

    if not _book_night_outline_ok(outline):
        prev_dims = (len(outline.get("chapters") or []), _count_subchapters(outline))
        outline = _programmatic_enforce_chapter_bounds(outline, lang=lang)
        new_dims = (len(outline.get("chapters") or []), _count_subchapters(outline))
        if _book_night_outline_ok(outline) and new_dims != prev_dims:
            logger.warning(
                "[Mode5 book_night] Outline adjusted programmatically to satisfy chapter/subchapter bounds "
                f"(was {prev_dims[0]} chapters / {prev_dims[1]} subs)."
            )

    if not _book_night_outline_ok(outline):
        n_ch = len(outline.get("chapters") or [])
        n_sub = _count_subchapters(outline)
        raise ValueError(
            f"Mode 5 (книга на ночь): число подглав должно быть от {_MIN_BOOK_SUBS_TOTAL} до {_MAX_BOOK_SUBS_TOTAL} "
            f"(по логике книги), глав — {_MIN_BOOK_CHAPTERS}–{_MAX_BOOK_CHAPTERS}. Сейчас: {n_ch} глав, {n_sub} подглав."
        )

    flat_rows = _flatten_outline(outline)
    n_total = len(flat_rows)
    if n_total < _MIN_BOOK_SUBS_TOTAL or n_total > _MAX_BOOK_SUBS_TOTAL:
        raise ValueError(
            f"Mode 5 (книга на ночь): после нормализации ожидалось {_MIN_BOOK_SUBS_TOTAL}–{_MAX_BOOK_SUBS_TOTAL} подглав, "
            f"получилось {n_total}."
        )

    outline_json = json.dumps(outline, ensure_ascii=False, indent=2)

    n_chapters_final = len(outline.get("chapters") or [])
    narr_lo, narr_hi, sent_lo, sent_hi = _book_night_narration_targets(n_chapters_final, n_total)
    depth_s = _narration_depth_scale(n_chapters_final)
    bn_batch = _book_night_narration_batch_size(n_total, narr_hi)
    est_total = n_total * (narr_lo + narr_hi) // 2
    logger.info(
        f"[Mode5 book_night] depth scale={depth_s:.2f} ({n_chapters_final} chapters, {n_total} subsections) → "
        f"~{narr_lo}–{narr_hi} chars, {sent_lo}–{sent_hi} sentences per block; batch_size={bn_batch}; "
        f"~{est_total} chars total (ref facts50 ≈ {_FACTS50_REFERENCE_TOTAL_CHARS})"
    )

    async def narr_batch(start_i: int, end_i: int) -> list[str]:
        batch = flat_rows[start_i:end_i]
        if not batch:
            return []
        sys2 = (
            f"""You write voiceover for **calm night listening** — a gentle audiobook-style summary of ONE famous nonfiction book.
Narration language: {lang_name}.

GROUNDING_SNIPPETS (third-party summaries only; incomplete; not the book text):
"""
            + grounding_snippets_block
            + f"""

Truthfulness / anti-hallucination (mandatory):
- Do NOT invent or assert: statistics, percentages, named studies or papers, specific dates, dialogue, character scenes, long verbatim quotes, page numbers, or made-up anecdotes presented as if from the book.
- Ground substantive specifics in GROUNDING_SNIPPETS when possible. Otherwise stay with generic, widely safe paraphrase tied to the subsection title and Plan line — **no new concrete pins** (no "a 2003 study", "on page 47", "the author met X on a train" unless that appears in GROUNDING).
- If unsure, omit the detail or use a soft hedge ("in broad terms…", "this part is often read as…") **without fabricating evidence**.
- Do not claim the book contains data, proofs, or named research unless GROUNDING_SNIPPETS support it.

For EACH subsection in the batch, write ONE continuous paragraph to be read aloud (no bullet points).
Style anchor (keep stable across batches): warm reflective narrator, gentle cadence, medium-long flowing sentences, no sudden tonal shifts.
- This outline has **{n_chapters_final}** top-level book chapters. **Fewer chapters → longer, richer paragraphs per subsection** (more of the book per block); **more chapters → slightly shorter paragraphs** so the night rhythm stays calm. Follow the character and sentence targets below.
- Tone: slow, warm, reflective — like a trusted narrator before sleep; NOT hype, NOT a book review with scores, NOT preaching.
- Summarize **ideas and mental models** faithfully at the level of justified content above; do NOT invent long direct quotes or dialogue. Paraphrase principles calmly.
- This subsection must not repeat the previous subsection's thesis; advance the book's argument by one concrete step tied to this subsection title.
- Structure: **{sent_lo}–{sent_hi}** sentences. Mini-arc: introduce the idea → explain in plain language → why it matters → soft closing.
- When helpful, mention this block's place in the journey (subsections {start_i + 1}–{end_i} of {n_total}).
- Plain text only. Aim for roughly **{narr_lo}–{narr_hi} characters** of narration per subsection when the material allows — **this episode is sized like a full «{FACTS50_TARGET} facts» sleep video overall**, so each block must carry enough substance; if shorter, invisible padding is added server-side — do not pad with empty prose.
- Output ONLY valid JSON: {{"narrations": ["...", ...]}} with exactly {len(batch)} strings in the same order as the input list."""
        )

        lines = []
        for i, row in enumerate(batch):
            g = start_i + i + 1
            lines.append(
                f"{g}. Book chapter: {row['chapter_title']}\n"
                f"   Subsection: {row['subchapter_title']}\n"
                f"   Plan: {row['coverage'] or '(summarize from chapter title and book context)'}"
            )
        human2 = (
            f"Book (user request):\n{q}\n\n"
            f"Full outline (do not read aloud):\n{outline_json}\n\n"
            f"Write narration ONLY for these {len(batch)} subsections (in order):\n"
            + "\n".join(lines)
        )
        mt = _book_night_narration_max_tokens(len(batch), narr_hi)
        await checkpoint(control)
        obj = await _invoke_json(sys2, human2, temperature=0.48, max_tokens=mt)
        narr = _normalize_narrations(obj)
        if len(narr) != len(batch):
            logger.warning(f"[Mode5 book_night] Batch {start_i}-{end_i}: got {len(narr)} narrations, repair")
            repair = sys2 + f"\nYou returned {len(narr)} strings; must be exactly {len(batch)}."
            obj = await _invoke_json(
                repair, human2 + "\n\nReturn corrected JSON only.", temperature=0.42, max_tokens=mt
            )
            narr = _normalize_narrations(obj)
        if len(narr) != len(batch):
            narr = _pad_narrations_to_rows(batch, narr, language=lang)
            narr = narr[: len(batch)]
        return [_ensure_book_night_voiceapi_floor(x, language=lang) for x in narr]

    tasks = []
    for start in range(0, n_total, bn_batch):
        end = min(n_total, start + bn_batch)
        tasks.append(narr_batch(start, end))
    narr_chunks = await asyncio.gather(*tasks)
    await checkpoint(control)
    narrations = [x for batch in narr_chunks for x in batch]
    if len(narrations) != n_total:
        narrations = _pad_narrations_to_rows(flat_rows, narrations, language=lang)
        narrations = narrations[:n_total]
    await checkpoint(control)
    narrations = await _expand_book_night_narrations_to_target(
        narrations,
        flat_rows,
        narr_lo=narr_lo,
        narr_hi=narr_hi,
        lang_name=lang_name,
        book_query=q,
        control=control,
    )
    narrations = await _dedupe_book_night_neighboring_blocks(
        narrations,
        flat_rows=flat_rows,
        lang_name=lang_name,
        book_query=q,
    )
    narrations = [_ensure_book_night_voiceapi_floor(x, language=lang) for x in narrations]

    total_spoken = sum(_spoken_plain_len(x) for x in narrations)
    logger.info(
        f"[Mode5 book_night] after length pass: ~{total_spoken} spoken chars total "
        f"(reference ≈ {_FACTS50_REFERENCE_TOTAL_CHARS}, {n_total} blocks)"
    )

    if bool(getattr(settings, "mode5_quality_gate_enabled", True)):
        narrations, quality_report = remediate_mode5_narrations(narrations, language=lang)
        outline["quality_report"] = quality_report
    script_clean = "\n\n".join(narrations)
    logger.success(
        f"[Mode5 book_night] {len(outline.get('chapters') or [])} book chapter(s), "
        f"{len(flat_rows)} subsection narrations for: {q[:80]}"
    )
    return outline, narrations, script_clean
