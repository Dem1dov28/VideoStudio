"""
Mode 5 «outline»: краткое описание от автора → структура (главы и подглавы) → длинный спокойный текст под каждую подглаву для TTS.
Мало подглав (как ночной лонгрид), каждый блок — развёрнутое повествование, не «короткий факт».
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from agents.video_editor.tts import append_nonspeaking_length_pad
from config import settings
from utils.json_parse import extract_first_json
from utils.llm import make_llm

from modes.mode5.facts50_generator import FACTS50_TARGET

_MIN_CHARS_VOICEAPI = 520
# Ночной / медитативный лонгрид: немного частей превью, много текста в каждой.
_MIN_CHAPTERS = 5
_MAX_CHAPTERS = 9
_MIN_SUBS_PER_CHAPTER = 2
_MAX_SUBS_PER_CHAPTER = 4
_MIN_SUBCHAPTERS_TOTAL = 10
_MAX_SUBCHAPTERS_TOTAL = 18
# Fallback верхняя граница батча (реальный размер — от длины блока, как у book_night).
_NARRATION_BATCH_CAP = 8

# Суммарный объём озвучки в том же порядке, что «77 фактов» / book_night (facts50_generator + book_night_generator).
_FACTS50_REFERENCE_TOTAL_CHARS = int(FACTS50_TARGET * 1320)

# Минимум символов во входе: не одно слово, а краткое описание задумки (синхронно с валидацией API/UI).
MIN_OUTLINE_BRIEF_CHARS = 40


def _outline_narration_targets(n_blocks: int) -> tuple[int, int, int, int]:
    """
    Цели на одну подглаву: (char_lo, char_hi, sent_lo, sent_hi).
    Делим общий «бюджет» ~77×1320 на число подглав — как в book_night без масштаба по числу верхних глав.
    """
    n_sub = max(1, int(n_blocks))
    per_mid = float(_FACTS50_REFERENCE_TOTAL_CHARS) / float(n_sub)
    hi_raw = int(per_mid * 1.1)
    lo_raw = int(per_mid * 0.9)
    hi = min(7200, max(900, hi_raw))
    lo = max(800, min(hi - 400, lo_raw))
    if lo > hi - 350:
        lo = max(800, hi - 500)
    sent_lo = 7 if per_mid >= 1400 else 6
    if per_mid >= 2800:
        sent_lo = 10
    if per_mid >= 4500:
        sent_lo = 12
    sent_hi = min(28, max(sent_lo + 4, int(8 + per_mid / 420.0)))
    return lo, hi, sent_lo, sent_hi


def _outline_narration_batch_size(n_sub: int, narr_hi: int) -> int:
    """Меньше подглав в одном запросе, если каждая должна быть очень длинной (как book_night)."""
    if narr_hi >= 5500:
        return max(1, min(3, n_sub))
    if narr_hi >= 4000:
        return max(1, min(5, n_sub))
    if narr_hi >= 2800:
        return max(2, min(8, n_sub))
    return max(2, min(_NARRATION_BATCH_CAP, n_sub))


def _strip_code_fence(text: str) -> str:
    s = (text or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


def _parse_json_obj(raw: str) -> dict[str, Any]:
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
            logger.warning("[Mode5 outline] JSON repaired via json_repair")
            return data
    except ImportError:
        pass
    except Exception as e:
        last_err = e
    if last_err is not None:
        raise last_err
    raise ValueError("Could not parse LLM JSON")


def _scenario_llm(*, temperature: float = 0.4):
    model = getattr(settings, "openrouter_scenario_model", None) or settings.openrouter_model
    return make_llm(temperature=temperature, model=model)


async def _invoke_json(system: str, human: str, *, temperature: float = 0.4) -> dict[str, Any]:
    llm = _scenario_llm(temperature=temperature)
    msg = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=human)])
    raw = msg.content if isinstance(msg.content, str) else str(msg.content)
    return _parse_json_obj(raw)


def _normalize_outline(obj: dict[str, Any]) -> dict[str, Any]:
    """Ensure chapters[].subchapters[] with title + coverage strings."""
    wt = str(obj.get("working_title") or obj.get("title") or "").strip()
    logline = str(obj.get("logline") or obj.get("angle") or "").strip()
    chapters_raw = obj.get("chapters")
    if not isinstance(chapters_raw, list):
        chapters_raw = []
    chapters: list[dict[str, Any]] = []
    for ch in chapters_raw:
        if not isinstance(ch, dict):
            continue
        ct = str(ch.get("title") or ch.get("chapter_title") or "").strip()
        subs_raw = ch.get("subchapters") or ch.get("sections") or []
        if not isinstance(subs_raw, list):
            subs_raw = []
        subs: list[dict[str, str]] = []
        for sc in subs_raw:
            if not isinstance(sc, dict):
                continue
            st = str(sc.get("title") or sc.get("subtitle") or "").strip()
            cov = str(sc.get("coverage") or sc.get("intent") or sc.get("brief") or "").strip()
            if st:
                subs.append({"title": st, "coverage": cov})
        if ct and subs:
            chapters.append({"title": ct, "subchapters": subs})
    return {"working_title": wt or "Видео", "logline": logline, "chapters": chapters}


def _count_subchapters(outline: dict[str, Any]) -> int:
    n = 0
    for ch in outline.get("chapters") or []:
        n += len(ch.get("subchapters") or [])
    return n


def _outline_constraints_met(outline: dict[str, Any]) -> bool:
    chs = outline.get("chapters") or []
    n_ch = len(chs)
    if n_ch < _MIN_CHAPTERS or n_ch > _MAX_CHAPTERS:
        return False
    n_sub = 0
    for ch in chs:
        subs = ch.get("subchapters") or []
        lc = len(subs)
        if lc < _MIN_SUBS_PER_CHAPTER or lc > _MAX_SUBS_PER_CHAPTER:
            return False
        n_sub += lc
    if n_sub < _MIN_SUBCHAPTERS_TOTAL or n_sub > _MAX_SUBCHAPTERS_TOTAL:
        return False
    return True


def _outline_from_flat_rows(
    rows: list[dict[str, Any]],
    *,
    working_title: str,
    logline: str,
) -> dict[str, Any]:
    """Rebuild outline JSON after trimming flat rows (preserves chapter boundaries by title)."""
    chapters: list[dict[str, Any]] = []
    cur_title: str | None = None
    cur_subs: list[dict[str, str]] = []
    for row in rows:
        ct = str(row.get("chapter_title") or "").strip()
        st = str(row.get("subchapter_title") or "").strip()
        cov = str(row.get("coverage") or "").strip()
        if not ct or not st:
            continue
        if ct != cur_title:
            if cur_title is not None:
                chapters.append({"title": cur_title, "subchapters": cur_subs})
            cur_title = ct
            cur_subs = []
        cur_subs.append({"title": st, "coverage": cov})
    if cur_title is not None and cur_subs:
        chapters.append({"title": cur_title, "subchapters": cur_subs})
    return {"working_title": working_title, "logline": logline, "chapters": chapters}


def get_chunk_outline_labels(outline: dict[str, Any]) -> list[tuple[str, str]]:
    """(chapter_title, subchapter_title) per chunk index, same order as narrations."""
    return [
        (str(r.get("chapter_title") or "").strip(), str(r.get("subchapter_title") or "").strip())
        for r in _flatten_outline(outline)
    ]


def _flatten_outline(outline: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ci, ch in enumerate(outline.get("chapters") or []):
        ctitle = str(ch.get("title") or "").strip()
        for sj, sc in enumerate(ch.get("subchapters") or []):
            rows.append(
                {
                    "chapter_index": ci,
                    "chapter_title": ctitle,
                    "sub_index": sj,
                    "subchapter_title": str(sc.get("title") or "").strip(),
                    "coverage": str(sc.get("coverage") or "").strip(),
                }
            )
    return rows


def _pad_narration(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    return append_nonspeaking_length_pad(t, _MIN_CHARS_VOICEAPI)


def _normalize_narrations(obj: dict[str, Any]) -> list[str]:
    arr = obj.get("narrations")
    if not isinstance(arr, list):
        return []
    out: list[str] = []
    for item in arr:
        if isinstance(item, str) and item.strip():
            out.append(re.sub(r"\s+", " ", item.strip()))
    return out


def _pad_narrations_to_rows(
    rows: list[dict[str, Any]], narrations: list[str], *, language: str
) -> list[str]:
    """Same role as facts50 _pad_narrations_to_facts: keep length aligned after a bad batch."""
    n = len(rows)
    cur = list(narrations[:n])
    lang_lo = (language or "ru").strip().lower()
    while len(cur) < n:
        i = len(cur)
        row = rows[i]
        title = str(row.get("subchapter_title") or "").strip()
        cov = str(row.get("coverage") or "").strip()
        hint = cov or title or "Continue the narration."
        if lang_lo == "ru":
            cur.append(f"Раздел «{title}». {hint}")
        else:
            cur.append(f"Section: {title}. {hint}")
    return cur


async def generate_outline_longform_script(
    topic: str,
    language: str,
    *,
    control: dict | None = None,
) -> tuple[dict[str, Any], list[str], str]:
    """
    Returns (outline_doc, chunk_texts, script_clean).
    chunk_texts: one spoken block per subchapter, same order as flatten outline.
    """
    from pipeline_control import checkpoint

    topic_clean = re.sub(r"\s+", " ", (topic or "").strip())
    if len(topic_clean) < MIN_OUTLINE_BRIEF_CHARS:
        raise ValueError(
            f"Mode 5 (план из описания): введите краткое описание сюжета или задумки (не меньше {MIN_OUTLINE_BRIEF_CHARS} символов): "
            "кто или что за мир, где действие, настроение, чем всё может закончиться — без этого модель не сможет честно развернуть историю."
        )

    lang = (language or "ru").strip().lower()
    if lang not in ("ru", "en"):
        lang = "ru"
    lang_name = "Russian" if lang == "ru" else "English"

    sys1 = f"""You are a senior story editor for calm **bedtime / night listening** — one long voiceover episode (quiet, unhurried).

The user input is a **SHORT DESCRIPTION / SYNOPSIS** (not just a one-line title). Treat it as the **canonical creative seed**: setting, mood, characters or viewpoint if any, situation, and any outcome the user hinted at. Your job is to **expand and dramatize** that seed into chapters and subchapters — invent scenes, beats, and texture that stay **fully consistent** with the synopsis; never contradict facts, names, or tone the user stated. If the synopsis is open-ended, choose gentle, coherent directions that fit it. Soft history, nature, science explained gently, myth or legend, reflective essay, or **gentle fiction** are all fine if the synopsis points that way. NO horror, gore, jump-scares, shouty clickbait, or harsh moralizing.

Output ONLY valid JSON with this exact shape:
{{
  "working_title": "string",
  "logline": "string — one sentence: promise + mood for the listener",
  "chapters": [
    {{
      "title": "string — concrete chapter title in {lang_name}",
      "subchapters": [
        {{"title": "string — concrete subchapter title", "coverage": "string — 1–3 sentences: what this block must evoke or explain (planning only; no fake quotes or precise fake stats)"}}
      ]
    }}
  ]
}}

Hard constraints:
- All strings in {lang_name}.
- Between {_MIN_CHAPTERS} and {_MAX_CHAPTERS} chapters inclusive.
- Each chapter has between {_MIN_SUBS_PER_CHAPTER} and {_MAX_SUBS_PER_CHAPTER} subchapters inclusive.
- Total subchapters across ALL chapters must be between {_MIN_SUBCHAPTERS_TOTAL} and {_MAX_SUBCHAPTERS_TOTAL} inclusive.
- Titles must be specific to the user's synopsis (forbidden: generic placeholders like «Chapter 1», «Part A», «Introduction» as the ONLY word).
- Order: calm setup → unfolding → soft turning points → peaceful landing (no aggressive CTA / «подпишись» energy).
- "coverage" is a writer's brief only; do NOT write the final narration here."""

    human1 = f"""Writer brief / short synopsis (from user — expand this into the full episode structure):\n{topic_clean}\n\nDesign the outline JSON now."""

    await checkpoint(control)
    try:
        raw1 = await _invoke_json(sys1, human1, temperature=0.35)
    except Exception as e:
        logger.error(f"[Mode5 outline] Phase 1 failed: {e}")
        raise ValueError("Mode 5 (план из описания): не удалось получить структуру от модели. Повторите запуск.") from e

    outline = _normalize_outline(raw1)
    repair_human = f"Same writer brief / synopsis (must remain the story seed):\n{topic_clean}\n\nReturn corrected JSON only."

    if not _outline_constraints_met(outline):
        n_ch0 = len(outline.get("chapters") or [])
        n_sub = _count_subchapters(outline)
        repair_sys = (
            sys1
            + f"\nYour previous JSON had {n_ch0} chapters and {n_sub} subchapters. "
            f"Fix ALL constraints: {_MIN_CHAPTERS}–{_MAX_CHAPTERS} chapters; "
            f"{_MIN_SUBS_PER_CHAPTER}–{_MAX_SUBS_PER_CHAPTER} subchapters per chapter; "
            f"total subchapters {_MIN_SUBCHAPTERS_TOTAL}–{_MAX_SUBCHAPTERS_TOTAL} inclusive."
        )
        try:
            await checkpoint(control)
            outline = _normalize_outline(await _invoke_json(repair_sys, repair_human, temperature=0.3))
        except Exception as e:
            logger.error(f"[Mode5 outline] Phase 1 repair failed: {e}")

    if not _outline_constraints_met(outline):
        n_sub = _count_subchapters(outline)
        if n_sub > _MAX_SUBCHAPTERS_TOTAL:
            repair2_sys = (
                sys1
                + f"\nYou still have {n_sub} subchapters (maximum {_MAX_SUBCHAPTERS_TOTAL}). "
                "Merge or remove weaker beats; keep every chapter within its subchapter limits and total within range."
            )
            try:
                await checkpoint(control)
                outline = _normalize_outline(await _invoke_json(repair2_sys, repair_human, temperature=0.28))
            except Exception as e:
                logger.error(f"[Mode5 outline] Phase 1 second repair failed: {e}")

    if not _outline_constraints_met(outline):
        n_ch = len(outline.get("chapters") or [])
        n_sub = _count_subchapters(outline)
        raise ValueError(
            "Mode 5 (план из описания): структура не прошла проверку "
            f"({_MIN_CHAPTERS}–{_MAX_CHAPTERS} глав, в каждой {_MIN_SUBS_PER_CHAPTER}–{_MAX_SUBS_PER_CHAPTER} подглав, "
            f"всего {_MIN_SUBCHAPTERS_TOTAL}–{_MAX_SUBCHAPTERS_TOTAL} подглав). Сейчас: {n_ch} глав, {n_sub} подглав. "
            "Сузьте описание или повторите запуск."
        )

    flat_rows = _flatten_outline(outline)

    outline_json = json.dumps(outline, ensure_ascii=False, indent=2)
    total_blocks = len(flat_rows)
    char_lo, char_hi, sent_lo, sent_hi = _outline_narration_targets(total_blocks)
    if lang == "ru":
        length_rules = (
            f"Каждый блок: примерно {char_lo}–{char_hi} значимых символов связной речи ({sent_lo}–{sent_hi} предложений), "
            "если тема позволяет — суммарно по всем блокам тот же порядок объёма, что у режима «77 фактов» (~"
            f"{FACTS50_TARGET} коротких озвучек); допустим один перевод строки между двумя короткими абзацами для дыхания; "
            "без маркированных списков и без заголовков в тексте."
        )
    else:
        en_lo = max(700, int(char_lo * 0.78))
        en_hi = min(6200, int(char_hi * 0.86))
        if en_lo > en_hi - 300:
            en_lo = max(700, en_hi - 400)
        length_rules = (
            f"Each block: roughly {en_lo}–{en_hi} characters of substantive prose ({sent_lo}–{sent_hi} sentences) when the topic allows; "
            f"total spoken volume across all blocks should match the scale of the «{FACTS50_TARGET} facts» sleep episode (~{_FACTS50_REFERENCE_TOTAL_CHARS} chars combined); "
            "at most one blank line between two short paragraphs; no bullet lists or headings inside the spoken text."
        )

    async def narrate_batch(start: int, end: int) -> list[str]:
        batch = flat_rows[start:end]
        if not batch:
            return []
        sys2 = f"""You write long-form voiceover for **bedtime / night listening** in {lang_name}.
The episode has {total_blocks} subchapter blocks total; each block should feel like a substantial chapter of a calm audiobook, not a short social clip.

The human message includes the user's **original synopsis** first, then the outline JSON. The whole narration must **grow from that synopsis** through the outline: never contradict what the user wrote; you may add invented scenes, small details, and inner monologue only where they fit the synopsis and the subchapter "coverage".

For EACH subchapter in this batch, write ONE spoken block (same order as input).
- Tone: slow, warm, immersive — gentle storyteller or quiet documentary for sleep; NOT a trailer voice, NOT preaching.
- {length_rules}
- Build a clear mini-arc per block: settle in → develop images and ideas → land softly; end without cliffhanger stress.
- Stay faithful to each subchapter title and "coverage" brief; add sensory and emotional texture. Do NOT invent precise dates, statistics, named studies, or quotes unless common knowledge — prefer careful general wording when unsure.
- No meta lines («в этом выпуске…»), no URLs, no markdown headings in the spoken text.
- When natural, you may hint at position in the journey (blocks {start + 1}–{end} of {total_blocks}).
- If shorter than the range, the pipeline adds invisible padding for the audio API — do not pad with empty prose.
- Output ONLY valid JSON: {{"narrations": ["...", ...]}} with exactly {len(batch)} strings."""

        lines = []
        for i, row in enumerate(batch):
            global_idx = start + i + 1
            lines.append(
                f"{global_idx}. Chapter: {row['chapter_title']}\n"
                f"   Subchapter: {row['subchapter_title']}\n"
                f"   Coverage brief: {row['coverage'] or '(expand from title and chapter context)'}"
            )
        human2 = (
            f"User's original synopsis (canonical seed — keep story consistent):\n{topic_clean}\n\n"
            f"Full outline (context — do not read aloud):\n{outline_json}\n\n"
            f"Write narration ONLY for these {len(batch)} subchapters (in order):\n"
            + "\n".join(lines)
        )
        await checkpoint(control)
        obj = await _invoke_json(sys2, human2, temperature=0.55)
        narr = _normalize_narrations(obj)
        if len(narr) != len(batch):
            logger.warning(f"[Mode5 outline] Batch {start}-{end}: got {len(narr)} narrations, repair")
            repair = sys2 + f"\nYou returned {len(narr)} strings; must be exactly {len(batch)}."
            obj = await _invoke_json(repair, human2 + "\n\nReturn corrected JSON only.", temperature=0.45)
            narr = _normalize_narrations(obj)
        if len(narr) != len(batch):
            narr = _pad_narrations_to_rows(batch, narr, language=lang)
            narr = narr[: len(batch)]
        return [_pad_narration(x) for x in narr]

    narr_batch = _outline_narration_batch_size(len(flat_rows), char_hi)
    narrations: list[str] = []
    for start in range(0, len(flat_rows), narr_batch):
        end = min(len(flat_rows), start + narr_batch)
        narrations.extend(await narrate_batch(start, end))
    await checkpoint(control)
    if len(narrations) != len(flat_rows):
        narrations = _pad_narrations_to_rows(flat_rows, narrations, language=lang)
        narrations = narrations[: len(flat_rows)]
        narrations = [_pad_narration(x) for x in narrations]

    script_clean = "\n\n".join(narrations)
    logger.success(
        f"[Mode5 outline] Generated {len(outline.get('chapters') or [])} chapters, "
        f"{len(flat_rows)} subchapter narrations (~{char_lo}–{char_hi} chars/block, facts50-scale total) "
        f"for: {topic_clean[:80]}"
    )
    return outline, narrations, script_clean
