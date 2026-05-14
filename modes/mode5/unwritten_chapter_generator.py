"""
Mode 5 «The Unwritten Chapter»: тема расследования -> структура из 5–7 блоков ->
длинная документальная озвучка по каждому блоку в стиле архивного расследования.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from agents.video_editor.tts import NONSPOKEN_LEN_FILLER_CHAR, append_nonspeaking_length_pad
from config import settings
from modes.mode5.evidence_snippets import (
    clip_evidence,
    gather_mode5_grounding_snippets,
    sources_block_unwritten,
)
from modes.mode5.outline_generator import (
    _flatten_outline,
    _normalize_narrations,
    _outline_narration_batch_size,
    _pad_narrations_to_rows,
    _parse_json_obj,
    _scenario_llm,
    trim_outline_to_first_n_subchapters,
)
from modes.mode5.narration_quality import adjacent_repetition_pairs
from modes.mode5.text_length import spoken_plain_len
from modes.mode5.quality_gate import remediate_mode5_narrations
from utils.retry_policy import retry_async

_MIN_TOPIC_CHARS = 8
_MIN_BLOCKS = 5
_MAX_BLOCKS = 7
_MIN_TARGET_MINUTES = 30
_MAX_TARGET_MINUTES = 50
_DEFAULT_TARGET_MINUTES = 40
_WORDS_PER_MIN = 145
_DEFAULT_WORDS_TOTAL = _DEFAULT_TARGET_MINUTES * _WORDS_PER_MIN
_MIN_CHARS_VOICEAPI = 520
_LLM_NETWORK_RETRIES = 4
_LLM_NETWORK_RETRY_BASE_DELAY_SEC = 1.2
_MAX_EVIDENCE_NARRATION_CHARS = 4500

_BLOCK_ROLE_RU = [
    "Официальная версия",
    "Первое расхождение",
    "Архивный след",
    "Человеческая ставка",
    "Критический разворот",
    "Последствия и тени",
    "Вывод и современный контекст",
]
_BLOCK_ROLE_EN = [
    "Official Narrative",
    "First Contradiction",
    "Archival Trace",
    "Human Stakes",
    "Critical Turn",
    "Aftermath",
    "Modern Context",
]


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


def _unwritten_narr_batch_max_tokens(batch_len: int, chars_hi: int) -> int:
    est = 1800 + batch_len * int(chars_hi * 0.42)
    return min(32000, max(4096, est))


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
        llm_kw: dict[str, Any] = {}
        if max_tokens is not None:
            llm_kw["max_tokens"] = max_tokens
        llm = _scenario_llm(temperature=temp, **llm_kw)
        try:
            msg = await retry_async(
                lambda: llm.ainvoke(
                    [SystemMessage(content=sys_prompt), HumanMessage(content=human_prompt)]
                ),
                operation_name=f"mode5_unwritten_llm_attempt_{idx}",
                attempts=_LLM_NETWORK_RETRIES,
                base_delay_sec=_LLM_NETWORK_RETRY_BASE_DELAY_SEC,
                max_delay_sec=12.0,
                jitter_sec=0.35,
                is_retryable=_is_transient_llm_error,
            )
        except Exception as e:
            last_err = e
            raise
        raw = msg.content if isinstance(msg.content, str) else str(msg.content)
        try:
            return _parse_json_obj(raw)
        except Exception as e:
            last_err = e
            preview = re.sub(r"\s+", " ", raw or "").strip()[:500]
            logger.warning(
                f"[Mode5 unwritten] JSON parse failed on attempt {idx}: {e}. Raw preview: {preview}"
            )
            continue
    if last_err is not None:
        raise last_err
    raise ValueError("Mode 5 (The Unwritten Chapter): empty JSON parse state")


def _normalize_outline(raw: dict[str, Any], *, lang: str) -> dict[str, Any]:
    wt = str(raw.get("working_title") or "").strip() or (
        "Нерассказанная глава" if lang == "ru" else "The Unwritten Chapter"
    )
    logline = str(raw.get("logline") or "").strip()
    blocks = raw.get("blocks")
    if not isinstance(blocks, list):
        blocks = []

    chapters: list[dict[str, Any]] = []
    for idx, block in enumerate(blocks, 1):
        if not isinstance(block, dict):
            continue
        title = str(block.get("title") or "").strip()
        role_label = str(block.get("role_label") or "").strip()
        angle = str(block.get("angle") or "").strip()
        micro = str(block.get("micro_conclusion") or "").strip()
        frame = str(block.get("frame_description") or "").strip()
        evidence = str(block.get("evidence_anchor") or "").strip()
        visual_anchor = str(block.get("visual_anchor") or "").strip()
        human_stakes = str(block.get("human_stakes") or "").strip()
        if not title:
            title = f"Блок {idx}" if lang == "ru" else f"Block {idx}"
        if not role_label:
            role_arr = _BLOCK_ROLE_RU if lang == "ru" else _BLOCK_ROLE_EN
            role_label = role_arr[min(idx - 1, len(role_arr) - 1)]
        if not visual_anchor:
            visual_anchor = frame
        if not evidence:
            evidence = (
                "Архивный документ, дата или свидетель, который можно проверить."
                if lang == "ru"
                else "A verifiable archival document, date, or witness anchor."
            )
        if not human_stakes:
            human_stakes = (
                "Показать, кто и чем рисковал в этой части истории."
                if lang == "ru"
                else "Show what people risked in this part of the story."
            )
        coverage = " ".join(x for x in (angle, micro, frame) if x).strip()
        if not coverage:
            coverage = (
                "Архивный разбор с аккуратным переходом к следующему блоку."
                if lang == "ru"
                else "Archival investigation with a clean transition to the next block."
            )
        sub_title = role_label
        chapters.append(
            {
                "title": title,
                "role_label": role_label,
                "subchapters": [
                    {
                        "title": sub_title,
                        "coverage": coverage,
                        "evidence_anchor": evidence[:220],
                        "visual_anchor": visual_anchor[:220],
                        "human_stakes": human_stakes[:220],
                        "micro_conclusion": micro[:240],
                        "frame_description": frame[:240],
                    }
                ],
            }
        )

    return {"working_title": wt, "logline": logline, "chapters": chapters}


def _outline_blocks_valid(outline: dict[str, Any]) -> bool:
    chapters = outline.get("chapters") or []
    if not (_MIN_BLOCKS <= len(chapters) <= _MAX_BLOCKS):
        return False
    for ch in chapters:
        if not str(ch.get("title") or "").strip():
            return False
        subs = ch.get("subchapters") or []
        if len(subs) != 1:
            return False
        sc = subs[0] if isinstance(subs[0], dict) else {}
        if not str(sc.get("micro_conclusion") or "").strip():
            return False
        if not str(sc.get("evidence_anchor") or "").strip():
            return False
        # visual_anchor is optional metadata; human_stakes is required by schema.
        if not str(sc.get("human_stakes") or "").strip():
            return False
    return True


def _micro_from_coverage(cov: str, lang: str) -> str:
    """Guarantee non-empty micro_conclusion for programmatic merge/split (validators require it)."""
    c = re.sub(r"\s+", " ", (cov or "").strip())
    if len(c) >= 40:
        return c[:240]
    return (
        "Промежуточный вывод по этому слою материала."
        if lang == "ru"
        else "Interim reading of this layer of evidence."
    )


def _merge_unwritten_chapters_at(chapters: list[dict[str, Any]], idx: int, *, lang: str) -> list[dict[str, Any]]:
    if idx < 0 or idx + 1 >= len(chapters):
        return chapters
    a, b = chapters[idx], chapters[idx + 1]
    sa = (a.get("subchapters") or [{}])[0]
    sb = (b.get("subchapters") or [{}])[0]
    if not isinstance(sa, dict):
        sa = {}
    if not isinstance(sb, dict):
        sb = {}
    t1 = str(a.get("title") or "").strip()
    t2 = str(b.get("title") or "").strip()
    merged_title = (t1 + " · " + t2).strip()[:240]
    rl = str(a.get("role_label") or str(b.get("role_label") or "")).strip()
    cov_a = str(sa.get("coverage") or "")
    cov_b = str(sb.get("coverage") or "")
    merged_cov = f"{cov_a} {cov_b}".strip()[:3500]
    mc = str(sb.get("micro_conclusion") or sa.get("micro_conclusion") or "").strip()[:240]
    if not mc:
        mc = _micro_from_coverage(merged_cov, lang)
    ea = f"{str(sa.get('evidence_anchor') or '')}; {str(sb.get('evidence_anchor') or '')}".strip()[:220]
    va = f"{str(sa.get('visual_anchor') or '')}; {str(sb.get('visual_anchor') or '')}".strip()[:220]
    hs = f"{str(sa.get('human_stakes') or '')}; {str(sb.get('human_stakes') or '')}".strip()[:220]
    if not ea:
        ea = (
            "Сводный архивный якорь для объединённого блока."
            if lang == "ru"
            else "Combined archival anchor for merged block."
        )
    if not va:
        va = (
            "Единый визуальный якорь: архив/документальная среда."
            if lang == "ru"
            else "Single visual anchor: archival documentary environment."
        )
    if not hs:
        hs = (
            "Кто и чем рискует в объединённой линии расследования."
            if lang == "ru"
            else "What people risk along the merged thread of the story."
        )
    merged_sub = {
        "title": str(sa.get("title") or sb.get("title") or "")[:240],
        "coverage": merged_cov,
        "evidence_anchor": ea,
        "visual_anchor": va,
        "human_stakes": hs,
        "micro_conclusion": mc,
        "frame_description": f"{str(sa.get('frame_description') or '')}; {str(sb.get('frame_description') or '')}"
        .strip()[:240],
    }
    merged_ch: dict[str, Any] = {"title": merged_title, "role_label": rl, "subchapters": [merged_sub]}
    return chapters[:idx] + [merged_ch] + chapters[idx + 2 :]


def _split_unwritten_chapter_at(chapters: list[dict[str, Any]], idx: int, *, lang: str) -> list[dict[str, Any]]:
    if idx < 0 or idx >= len(chapters):
        return chapters
    ch = chapters[idx]
    sc = (ch.get("subchapters") or [{}])[0]
    if not isinstance(sc, dict):
        sc = {}
    cov = str(sc.get("coverage") or "").strip()
    if len(cov) < 80:
        return chapters
    mid = max(40, len(cov) // 2)
    dot = cov.rfind(". ", 20, min(len(cov) - 1, mid + 100))
    if dot >= 20:
        left_cov = cov[: dot + 1].strip()
        right_cov = cov[dot + 2 :].strip()
    else:
        dot2 = cov.find(". ", mid)
        if dot2 > 0:
            left_cov = cov[: dot2 + 1].strip()
            right_cov = cov[dot2 + 2 :].strip()
        else:
            left_cov = cov[:mid].strip()
            right_cov = cov[mid:].strip()
    if not left_cov or not right_cov:
        return chapters
    base_title = str(ch.get("title") or "").strip()
    suf1, suf2 = (" (часть 1)", " (часть 2)") if lang == "ru" else (" (part 1)", " (part 2)")
    mc_left = str(sc.get("micro_conclusion") or "").strip()[:200]
    if not mc_left:
        mc_left = _micro_from_coverage(left_cov, lang)
    mc_right = str(sc.get("micro_conclusion") or "").strip()[:200]
    if not mc_right:
        mc_right = _micro_from_coverage(right_cov, lang)
    ch1: dict[str, Any] = {
        "title": (base_title + suf1).strip()[:240],
        "role_label": str(ch.get("role_label") or "").strip(),
        "subchapters": [
            {
                **sc,
                "coverage": left_cov,
                "micro_conclusion": mc_left,
            }
        ],
    }
    ch2: dict[str, Any] = {
        "title": (base_title + suf2).strip()[:240],
        "role_label": str(ch.get("role_label") or "").strip(),
        "subchapters": [
            {
                **sc,
                "coverage": right_cov,
                "micro_conclusion": mc_right,
            }
        ],
    }
    return chapters[:idx] + [ch1, ch2] + chapters[idx + 1 :]


def _programmatic_enforce_unwritten_block_count(outline: dict[str, Any], *, lang: str) -> dict[str, Any]:
    chs = list(outline.get("chapters") or [])
    prev_n = -1
    for _ in range(16):
        n = len(chs)
        if _MIN_BLOCKS <= n <= _MAX_BLOCKS:
            return {**outline, "chapters": chs}
        if n == prev_n:
            break
        prev_n = n
        if n > _MAX_BLOCKS:
            chs = _merge_unwritten_chapters_at(chs, 0, lang=lang)
            logger.warning("[Mode5 unwritten] Merged two adjacent blocks programmatically (too many blocks).")
            continue
        if 0 < n < _MIN_BLOCKS:
            best_i = 0
            best_len = 0
            for i, ch in enumerate(chs):
                sc = (ch.get("subchapters") or [{}])[0]
                L = len(str((sc or {}).get("coverage") or ""))
                if L > best_len:
                    best_len = L
                    best_i = i
            if best_len < 80:
                break
            chs = _split_unwritten_chapter_at(chs, best_i, lang=lang)
            logger.warning("[Mode5 unwritten] Split one block programmatically (too few blocks).")
            continue
        break
    return {**outline, "chapters": chs}


def _pad_narration(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    return append_nonspeaking_length_pad(t, _MIN_CHARS_VOICEAPI)


def _strip_code_fence_like(s: str) -> str:
    t = (s or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t).strip()
    return t


async def _expand_one_unwritten_narration(
    text: str,
    *,
    min_chars: int,
    max_chars: int,
    lang_name: str,
    block_line: str,
    topic_query: str,
    attempt: int,
) -> str:
    base = (text or "").replace(NONSPOKEN_LEN_FILLER_CHAR, "").strip()
    if spoken_plain_len(base) >= int(min_chars * 0.92):
        return base
    floor = max(min_chars, int(min_chars * (1.05 if attempt >= 2 else 1.0)))
    mt = min(14000, 900 + int(floor * 2.15))
    sys = SystemMessage(
        content=(
            f"You lengthen ONE calm documentary investigation paragraph for voiceover. Output language: {lang_name} only.\n"
            f"The paragraph must be at least {floor} characters (plain letters/spaces/punctuation — not counting filler).\n"
            "Keep the same investigative arc and tone; do NOT add new named statistics, declassified memo numbers, "
            "precise dates, long quotes, or specific archival references that are not already implied in the text.\n"
            "You may add: careful transitions, reframing the same tension, rhetorical questions, and a softer bridge to the next idea.\n"
            "One continuous paragraph, no bullet points, no title line, no markdown fences."
        )
    )
    hum = HumanMessage(
        content=(
            f"Investigation topic:\n{topic_query}\n\n"
            f"Block:\n{block_line}\n\n"
            f"Current narration ({spoken_plain_len(base)} chars):\n{base}\n\n"
            f"Rewrite into a longer single paragraph (≥{floor} chars)."
        )
    )
    llm = _scenario_llm(temperature=0.34 if attempt == 1 else 0.28, max_tokens=mt)
    resp = await llm.ainvoke([sys, hum])
    raw = resp.content if isinstance(resp.content, str) else str(resp.content)
    out = _strip_code_fence_like(raw).strip().strip('"').strip("'")
    if spoken_plain_len(out) < max(spoken_plain_len(base), int(min_chars * 0.55)):
        return base
    if spoken_plain_len(out) > max_chars + 800:
        out = out[: max_chars + 800].rsplit(".", 1)[0] + "."
    return out


async def _expand_unwritten_narrations_to_target(
    narrations: list[str],
    flat_rows: list[dict[str, Any]],
    *,
    narr_lo: int,
    narr_hi: int,
    lang_name: str,
    topic_query: str,
    control: dict | None,
) -> list[str]:
    _ = control
    sem = asyncio.Semaphore(max(2, int(getattr(settings, "mode5_facts50_parallel", 32) or 32)))

    async def _one(i: int, t: str) -> str:
        async with sem:
            if i >= len(flat_rows):
                return t
            row = flat_rows[i]
            line = f"{row.get('chapter_title', '')} / {row.get('subchapter_title', '')}".strip()
            cur = (t or "").replace(NONSPOKEN_LEN_FILLER_CHAR, "").strip()
            for att in (1, 2):
                if spoken_plain_len(cur) >= int(narr_lo * 0.92):
                    break
                nxt = await _expand_one_unwritten_narration(
                    cur,
                    min_chars=narr_lo,
                    max_chars=narr_hi,
                    lang_name=lang_name,
                    block_line=line,
                    topic_query=topic_query,
                    attempt=att,
                )
                if spoken_plain_len(nxt) <= spoken_plain_len(cur) + 80:
                    break
                cur = nxt
            if spoken_plain_len(cur) < int(narr_lo * 0.88):
                logger.warning(
                    f"[Mode5 unwritten] Block {i + 1} still short after expand: "
                    f"{spoken_plain_len(cur)} chars (target lo={narr_lo})"
                )
            return cur

    return list(await asyncio.gather(*(_one(i, t) for i, t in enumerate(narrations))))


async def _dedupe_unwritten_neighboring_blocks(
    items: list[str],
    *,
    flat_rows: list[dict[str, Any]],
    lang_name: str,
    topic_query: str,
) -> list[str]:
    out = list(items)
    pairs = adjacent_repetition_pairs(out, threshold=0.08)
    if not pairs:
        return out
    for idx, score in pairs[: max(1, min(4, len(pairs)))]:
        if idx <= 0 or idx >= len(out):
            continue
        row = flat_rows[idx] if idx < len(flat_rows) else {}
        sys = SystemMessage(
            content=(
                f"You are a script editor for The Unwritten Chapter. Output language: {lang_name} only.\n"
                "Rewrite ONLY the current block to reduce repetition with the previous block while preserving meaning, "
                "facts, anchors, tone, and approximate length. Do not add new dates, names, statistics, quotes, or sources. "
                "Keep one continuous voiceover paragraph. No markdown."
            )
        )
        hum = HumanMessage(
            content=(
                f"Topic:\n{topic_query}\n\n"
                f"Current block label:\n{row.get('chapter_title', '')} / {row.get('subchapter_title', '')}\n\n"
                f"Previous block (do not repeat wording):\n{out[idx - 1][:2200]}\n\n"
                f"Current block to rewrite (overlap score {score:.3f}):\n{out[idx][:2600]}\n\n"
                "Return only the rewritten current block."
            )
        )
        try:
            llm = _scenario_llm(temperature=0.24, max_tokens=min(10000, 1200 + int(len(out[idx]) * 0.8)))
            resp = await llm.ainvoke([sys, hum])
            raw = resp.content if isinstance(resp.content, str) else str(resp.content)
            candidate = _strip_code_fence_like(raw).strip().strip('"').strip("'")
            if spoken_plain_len(candidate) >= int(spoken_plain_len(out[idx]) * 0.62):
                out[idx] = candidate
                logger.info(f"[Mode5 unwritten] Deduped neighboring block {idx + 1} (overlap={score:.3f})")
        except Exception as e:
            logger.warning(f"[Mode5 unwritten] Neighbor dedup skipped for block {idx + 1}: {e}")
    return out


async def generate_unwritten_chapter_script(
    topic: str,
    language: str,
    *,
    control: dict | None = None,
) -> tuple[dict[str, Any], list[str], str]:
    from pipeline_control import checkpoint

    topic_clean = re.sub(r"\s+", " ", (topic or "").strip())
    if len(topic_clean) < _MIN_TOPIC_CHARS:
        raise ValueError(
            "Mode 5 (The Unwritten Chapter): укажите тему расследования (не меньше 8 символов)."
        )

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

    await checkpoint(control)
    evidence_outline, evidence_sources = await gather_mode5_grounding_snippets(topic_clean)
    if evidence_outline:
        logger.info(f"[Mode5 unwritten] Grounding snippets ({len(evidence_outline)} chars) from: {evidence_sources}")
    else:
        logger.warning("[Mode5 unwritten] No external grounding snippets — stay conservative in narration")

    sources_outline = sources_block_unwritten(evidence_outline)
    evidence_narr_clip = clip_evidence(evidence_outline, _MAX_EVIDENCE_NARRATION_CHARS)
    sources_narr = sources_block_unwritten(evidence_narr_clip)

    truthfulness = (
        "\nTruthfulness: When EXTERNAL_SOURCES are present, align broad facts and names with them; never contradict a clear snippet. "
        "When absent, avoid inventing specific document IDs, verbatim quotes, or precise stats. "
        "This is documentary planning, not a primary archive transcript."
    )

    sys1 = f"""You are a documentary writer for YouTube channel "The Unwritten Chapter".
You investigate controversial historical, political, social, and scientific topics in a calm detective-archivist tone.

Return ONLY valid JSON:
{{
  "working_title": "string",
  "logline": "string",
  "blocks": [
    {{
      "title": "string",
      "role_label": "string",
      "angle": "string",
      "evidence_anchor": "string — one concrete anchor (date / declassified memo / witness / place / record reference)",
      "human_stakes": "string — what people stand to lose or gain in this block",
      "micro_conclusion": "string",
      "visual_anchor": "string — optional metadata, concise scene clue",
      "frame_description": "string — optional metadata"
    }}
  ]
}}

Hard constraints:
- Language for all strings: {lang_name}.
- Exactly {_MIN_BLOCKS}-{_MAX_BLOCKS} blocks.
- The whole episode should target {_MIN_TARGET_MINUTES}-{_MAX_TARGET_MINUTES} minutes (default around {_DEFAULT_TARGET_MINUTES} min).
- Block order should progress from official version -> contradictions -> evidence -> human impact -> reveal -> modern context.
- No shouting, no clickbait, no conspiracy certainty without nuance.
- Every block must include concrete evidence_anchor + human_stakes.
- visual_anchor/frame_description are optional planning metadata and may be left empty.{truthfulness}"""

    human1 = f"Topic X for investigation:\n{topic_clean}{sources_outline}\n\nBuild the blocks JSON now."

    await checkpoint(control)
    try:
        raw_outline = await _invoke_json(sys1, human1, temperature=0.34, max_tokens=12000)
    except Exception as e:
        logger.error(f"[Mode5 unwritten] Outline generation failed: {e}")
        raise ValueError("Mode 5 (The Unwritten Chapter): не удалось построить структуру расследования.") from e

    outline = _normalize_outline(raw_outline, lang=lang)
    n_blocks = len(outline.get("chapters") or [])

    async def _try_repair(repair_sys: str, repair_human: str, temp: float) -> None:
        """Like book_night: a failed repair must not abort the whole script."""
        nonlocal outline, n_blocks, raw_outline
        try:
            await checkpoint(control)
            raw_outline = await _invoke_json(repair_sys, repair_human, temperature=temp, max_tokens=12000)
            outline = _normalize_outline(raw_outline, lang=lang)
            n_blocks = len(outline.get("chapters") or [])
        except Exception as e:
            logger.error(f"[Mode5 unwritten] Outline repair attempt failed: {e}")

    if not _outline_blocks_valid(outline):
        repair_sys = (
            sys1
            + "\nYour previous output violated constraints. Return corrected JSON with full block schema and all required anchors."
        )
        await _try_repair(repair_sys, human1 + "\n\nReturn corrected JSON only.", 0.3)

    if not _outline_blocks_valid(outline):
        repair_sys = (
            sys1
            + f"\nYour JSON had {n_blocks} blocks after normalization. "
            f"Fix ALL constraints: exactly {_MIN_BLOCKS}–{_MAX_BLOCKS} blocks; each block must have "
            "evidence_anchor, human_stakes, micro_conclusion (all non-empty strings)."
        )
        await _try_repair(repair_sys, human1 + "\n\nReturn corrected JSON only.", 0.28)

    if not _outline_blocks_valid(outline):
        repair_sys = (
            sys1
            + "\nCRITICAL: subchapters must not appear in your JSON — use the \"blocks\" array only. "
            f"Return exactly {_MIN_BLOCKS}–{_MAX_BLOCKS} blocks with the schema from the original instruction."
        )
        await _try_repair(repair_sys, human1 + "\n\nReturn corrected JSON only.", 0.26)

    if not _outline_blocks_valid(outline):
        prev = n_blocks
        outline = _programmatic_enforce_unwritten_block_count(outline, lang=lang)
        n_blocks = len(outline.get("chapters") or [])
        if _outline_blocks_valid(outline) and n_blocks != prev:
            logger.warning(
                f"[Mode5 unwritten] Outline adjusted programmatically to block bounds (was {prev} blocks, now {n_blocks})."
            )

    if not _outline_blocks_valid(outline):
        raise ValueError(
            f"Mode 5 (The Unwritten Chapter): структура блоков невалидна ({n_blocks} блоков или пропущены anchors)."
        )

    rows = _flatten_outline(outline)

    if control and control.get("_mode5_test_run"):
        from modes.mode5.text_length import mode5_trim_strings_by_estimated_speech

        tgt = float(control.get("_mode5_test_target_sec") or 300.0)
        tgt = max(60.0, min(7200.0, tgt))
        proxies = [
            " ".join(
                str(row.get(k) or "").strip()
                for k in (
                    "chapter_title",
                    "subchapter_title",
                    "coverage",
                    "evidence_anchor",
                    "human_stakes",
                )
            ).strip()
            or "block"
            for row in rows
        ]
        kept = mode5_trim_strings_by_estimated_speech(proxies, language=lang, target_sec=tgt)
        k = len(kept)
        if k < len(rows):
            rows = rows[:k]
            outline = trim_outline_to_first_n_subchapters(outline, k)
            logger.info(
                f"[Mode5 unwritten] test_run: generating first {k} block(s) (~{tgt:.0f}s speech budget)"
            )

    words_per_block = max(560, int(_DEFAULT_WORDS_TOTAL / max(1, len(rows))))
    chars_lo = int(words_per_block * 5.2)
    chars_hi = int(words_per_block * 6.4)
    sent_lo = 12
    sent_hi = 24
    outline_json = json.dumps(outline, ensure_ascii=False, indent=2)
    narr_batch_size = _outline_narration_batch_size(len(rows), chars_hi)

    async def narrate_batch(start: int, end: int) -> list[str]:
        batch = rows[start:end]
        if not batch:
            return []
        batch_mt = _unwritten_narr_batch_max_tokens(len(batch), chars_hi)
        sys2 = f"""You write a long-form investigation voiceover in {lang_name} for "The Unwritten Chapter".
Tone and delivery:
- Calm, confident, archival detective style; no shouting, no sensationalism.
- Moderate pace for narration (~145 words/minute target).
- Use rhetorical questions, controlled repetition, and clean transitions.
- Each block must contain 1-2 concrete factual anchors and end with a micro-conclusion + bridge to the next block.
- Use the provided evidence_anchor, visual_anchor, human_stakes, and micro_conclusion naturally inside the narration once when they are present.
- Do not invent new dates, memo IDs, names, statistics, long quotes, or archival references beyond the provided anchors and external snippets.
- Do not include explicit visual labels like "КАДР:" / "FRAME:" in spoken text.
- Keep narration text purely voiceover-ready; visual intent is already handled by planning metadata.
{truthfulness}

Length target per block:
- Roughly {chars_lo}-{chars_hi} characters of substantive narration.
- About {sent_lo}-{sent_hi} sentences.
- Keep total scale coherent for {_MIN_TARGET_MINUTES}-{_MAX_TARGET_MINUTES} min with balanced length across blocks.

Output ONLY valid JSON:
{{"narrations": ["...", ...]}}
with exactly {len(batch)} strings in the same order."""

        lines = []
        for i, row in enumerate(batch):
            global_idx = start + i + 1
            lines.append(
                f"{global_idx}. Block title: {row['chapter_title']}\n"
                f"   Planning brief: {row.get('coverage') or '(none)'}\n"
                f"   Evidence anchor: {row.get('evidence_anchor') or '(none)'}\n"
                f"   Visual anchor: {row.get('visual_anchor') or '(none)'}\n"
                f"   Human stakes: {row.get('human_stakes') or '(none)'}\n"
                f"   Required micro-conclusion: {row.get('micro_conclusion') or '(none)'}"
            )
        prev_tail = "\n\n".join([x for x in narrations[-2:] if str(x).strip()])
        prev_tail_block = (
            f"Previous generated context tail (for continuity, do not repeat verbatim):\n{prev_tail}\n\n"
            if prev_tail
            else ""
        )
        human2 = (
            f"Topic:\n{topic_clean}\n\n"
            f"Outline context (do not read aloud):\n{outline_json}\n\n"
            f"{sources_narr}\n\n"
            f"{prev_tail_block}"
            "Write narration for these blocks:\n"
            + "\n".join(lines)
        )
        await checkpoint(control)
        try:
            obj = await _invoke_json(sys2, human2, temperature=0.56, max_tokens=batch_mt)
            narr = _normalize_narrations(obj)
        except Exception as e:
            logger.warning(f"[Mode5 unwritten] Narration batch {start}-{end} primary parse failed: {e}")
            narr = []
        if len(narr) != len(batch):
            repair = sys2 + f"\nYou returned {len(narr)} strings; must be exactly {len(batch)}."
            try:
                obj = await _invoke_json(
                    repair,
                    human2 + "\n\nReturn corrected JSON only.",
                    temperature=0.46,
                    max_tokens=batch_mt,
                )
                narr = _normalize_narrations(obj)
            except Exception as e:
                logger.warning(f"[Mode5 unwritten] Narration batch {start}-{end} repair failed: {e}")
        if len(narr) != len(batch):
            narr = _pad_narrations_to_rows(batch, narr, language=lang)
            narr = narr[: len(batch)]
        return [str(x or "").strip() for x in narr]

    narrations: list[str] = []
    for start in range(0, len(rows), narr_batch_size):
        end = min(len(rows), start + narr_batch_size)
        narrations.extend(await narrate_batch(start, end))
    await checkpoint(control)
    if len(narrations) != len(rows):
        narrations = _pad_narrations_to_rows(rows, narrations, language=lang)
        narrations = narrations[: len(rows)]

    narrations = await _expand_unwritten_narrations_to_target(
        narrations,
        rows,
        narr_lo=chars_lo,
        narr_hi=chars_hi,
        lang_name=lang_name,
        topic_query=topic_clean,
        control=control,
    )
    narrations = [_pad_narration(x) for x in narrations]
    await checkpoint(control)

    async def _cohere_blocks(items: list[str]) -> list[str]:
        if not items:
            return []
        cohere_mt = min(32000, 4000 + len(items) * int(chars_hi * 0.5))
        sys3 = f"""You are a careful script editor for The Unwritten Chapter in {lang_name}.
Rewrite each block lightly for coherence and rhythm while preserving facts and meaning.
Rules:
- Keep calm archival documentary tone.
- Preserve concrete anchors; do not invent new specific facts.
- Keep each block ending with a soft bridge.
- Return valid JSON: {{"narrations": ["...", ...]}} with exactly {len(items)} strings.{truthfulness}"""
        body = "\n".join([f"{i+1}. {txt[:1400]}" for i, txt in enumerate(items)])
        try:
            obj = await _invoke_json(
                sys3,
                f"Blocks:\n{body}\n\nReturn corrected JSON only.",
                temperature=0.25,
                max_tokens=cohere_mt,
            )
            arr = _normalize_narrations(obj)
        except Exception as e:
            logger.warning(f"[Mode5 unwritten] Coherence pass skipped after JSON failure: {e}")
            return items
        if len(arr) != len(items):
            return items
        return [_pad_narration(x) for x in arr]

    narrations = await _cohere_blocks(narrations)
    narrations = await _dedupe_unwritten_neighboring_blocks(
        narrations,
        flat_rows=rows,
        lang_name=lang_name,
        topic_query=topic_clean,
    )
    narrations = [_pad_narration(x) for x in narrations]
    if bool(getattr(settings, "mode5_quality_gate_enabled", True)):
        narrations, quality_report = remediate_mode5_narrations(narrations, language=lang)
        outline["quality_report"] = quality_report

    script_clean = "\n\n".join([x for x in narrations if str(x).strip()])
    logger.success(
        f"[Mode5 unwritten] Generated {len(outline.get('chapters') or [])} blocks for: {topic_clean[:80]}"
    )
    return outline, narrations, script_clean
