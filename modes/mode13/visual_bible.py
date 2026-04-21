"""
Единый «визуальный манифест» для mode 5: одна модель смотрит на образец озвучки и метаданные,
определяет тип видео (факты, книга, природа, история, современность…) и выдаёт согласованные
правила для всех кадров — вместо жёсткого шаблона «одна эпоха для всего».
"""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from utils.json_parse import extract_first_json
from utils.llm import make_llm


def mode5_art_direction_tail_horizontal() -> str:
    """Короткое напоминание о формате; жёсткие негативы — в _mode13_hard_rules_suffix при сборке image prompt."""
    return " Maintain consistent horizontal 16:9 full-frame composition across the series."


def _strip_json_fence(s: str) -> str:
    t = (s or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t).strip()
    return t


def _parse_bible_obj(raw: str) -> dict[str, str] | None:
    s = _strip_json_fence(raw)
    if not s:
        return None
    try:
        blob = extract_first_json(s)
        data = json.loads(blob)
    except Exception:
        try:
            data = json.loads(s)
        except Exception:
            return None
    if not isinstance(data, dict):
        return None
    out: dict[str, str] = {}
    for k in ("series_style", "frame_rules", "scene_cue"):
        v = data.get(k)
        out[k] = (str(v).strip() if v is not None else "")[:6000]
    return out


async def derive_mode5_visual_bible(
    *,
    narration_sample: str,
    sub_mode: str,
    topic_or_title: str,
    locked_series_style: str | None = None,
) -> dict[str, str] | None:
    """
    Один LLM-вызов: понять «что это за видео» и как рисовать все кадры.

    - Если передан locked_series_style (например facts50 уже выбрал стиль), series_style в JSON
      должен быть пустой строкой; заполняются frame_rules и scene_cue под этот стиль.
    - Иначе series_style = единое художественное направление (3–6 предложений), плюс frame_rules и scene_cue.

    Возвращает dict с ключами series_style, frame_rules, scene_cue или None при ошибке.
    """
    sample = re.sub(r"\s+", " ", (narration_sample or "").strip())[:12000]
    meta_topic = re.sub(r"\s+", " ", (topic_or_title or "").strip())[:500]
    sm = (sub_mode or "manual").strip().lower()
    locked = (locked_series_style or "").strip()
    has_lock = len(locked) >= 20

    lock_block = (
        f"LOCKED_SERIES_STYLE (already chosen — output series_style as empty string \"\"; "
        f"only write frame_rules and scene_cue that obey this look, do not contradict):\n{locked[:3500]}\n\n"
        if has_lock
        else ""
    )

    sys = SystemMessage(
        content=(
            "You are the sole **visual director** for an automated long-form video pipeline. "
            "Your job is to READ the narration sample + metadata and infer what this program actually is "
            "(science facts, nature documentary tone, modern self-help / business book, historical essay, "
            "fiction bedtime story, religious reading, manual speech, etc.).\n\n"
            "Output **only** valid JSON with exactly these string keys:\n"
            '{ "series_style": string, "frame_rules": string, "scene_cue": string }\n\n'
            "Rules:\n"
            "- series_style: If LOCKED_SERIES_STYLE is provided below, set series_style to exactly \"\" (empty). "
            "Otherwise write 3–6 English sentences: unified palette, lighting, realism vs painterly, lens mood. "
            "Must fit the inferred genre/era. Do NOT repeat long negative lists here (no text/logos/UI) — "
            "those belong only in frame_rules.\n"
            "- frame_rules: 2–6 English sentences that apply to **every** still: era fidelity and anachronisms; "
            "when narration is clearly modern (cities, labs, offices, contemporary habits), demand believable contemporary visuals; "
            "when it is clearly ancient/medieval/biblical, demand period-accurate worlds; for pure nature topics, "
            "wildlife/landscapes without humans if that matches the words. "
            "Include here once: no readable text, letters, logos, watermarks, or UI in frame; no celebrity likenesses. "
            "Explicitly forbid anachronisms (no medieval market for smartphone-era self-help; no glass towers for Bronze Age text).\n"
            "- scene_cue: ONE English sentence telling the per-segment illustrator how to pick each frame from a "
            "spoken excerpt (literal filmable beat vs metaphor; crowd vs intimate; etc.).\n\n"
            "All string values in English. No markdown, no code fences."
        )
    )
    hum = HumanMessage(
        content=(
            f"{lock_block}"
            f"mode5_sub_mode (pipeline hint): {sm}\n"
            f"topic_or_header: {meta_topic or '(none)'}\n\n"
            "If mode5_sub_mode is book_night: scenes must depict lived environments and actions from the ideas, "
            "not physical books/pages/readers as the subject.\n\n"
            "NARRATION_SAMPLE (may be Russian or English):\n"
            f"{sample if sample else '(empty — infer only from sub_mode and topic)'}\n\n"
            "Return the JSON object now."
        )
    )

    try:
        llm = make_llm(temperature=0.34, max_tokens=1200)
        resp = await llm.ainvoke([sys, hum])
        raw = resp.content if isinstance(resp.content, str) else str(resp.content)
        obj = _parse_bible_obj(raw)
        if not obj:
            return None
        if has_lock:
            obj["series_style"] = ""
        fr = (obj.get("frame_rules") or "").strip()
        sc = (obj.get("scene_cue") or "").strip()
        ss = (obj.get("series_style") or "").strip()
        if not has_lock and len(ss) < 40:
            logger.warning("[visual_bible] series_style too short; discarding bible")
            return None
        if len(fr) < 30:
            logger.warning("[visual_bible] frame_rules too short; discarding bible")
            return None
        if len(sc) < 15:
            obj["scene_cue"] = (
                "Pick one concrete filmable instant from the excerpt; match the era and genre implied by the series; "
                "no text surfaces as the subject."
            )
        return obj
    except Exception as e:
        logger.warning(f"[visual_bible] derive_mode5_visual_bible failed: {e}")
        return None
