from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from agents.topics_history import _is_duplicate, get_used_topics
from config import settings
from utils.llm import make_llm

_BACKLOG_FILE = settings.output_dir / "mode5_topic_ideas.json"
_ALLOWED_SUB_MODES = {"book_night", "unwritten_chapter"}
_ALLOWED_STATUSES = {"suggested", "clicked", "started", "completed", "failed", "archived"}
_BACKLOG_TTL_DAYS = 30


def _load_backlog() -> dict[str, Any]:
    if _BACKLOG_FILE.exists():
        try:
            data = json.loads(_BACKLOG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {"ideas": []}


def _save_backlog(data: dict[str, Any]) -> None:
    _BACKLOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _BACKLOG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_dt(text: str) -> datetime | None:
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _is_backlog_fresh(row: dict[str, Any]) -> bool:
    if str(row.get("status") or "").strip().lower() == "completed":
        return True
    dt = _parse_dt(str(row.get("suggested_at") or ""))
    if not dt:
        return True
    return dt >= (datetime.now() - timedelta(days=_BACKLOG_TTL_DAYS))


def _combined_entries_with_backlog() -> list[dict[str, str]]:
    existing = list(get_used_topics())
    data = _load_backlog()
    for row in data.get("ideas", []):
        if not isinstance(row, dict) or not _is_backlog_fresh(row):
            continue
        status = str(row.get("status") or "suggested").strip().lower()
        if status not in _ALLOWED_STATUSES:
            continue
        topic = str(row.get("topic") or "").strip()
        title = str(row.get("project_title") or "").strip()
        if not topic and not title:
            continue
        existing.append({"topic": topic, "video_angle": title})
    return existing


def _serialize_idea_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "idea_id": str(row.get("idea_id") or "").strip(),
        "topic": str(row.get("topic") or "").strip(),
        "project_title": str(row.get("project_title") or "").strip(),
        "hook": str(row.get("hook") or "").strip(),
        "sub_mode": str(row.get("sub_mode") or "").strip(),
        "quality_score": int(row.get("quality_score") or 0),
        "status": str(row.get("status") or "suggested").strip().lower(),
    }


def get_cached_mode5_topics(sub_mode: str, limit: int = 8) -> list[dict[str, Any]]:
    sm = (sub_mode or "").strip().lower()
    if sm not in _ALLOWED_SUB_MODES:
        raise ValueError("Unsupported mode5 sub_mode for topic ideas")
    wanted = max(1, min(12, int(limit or 8)))
    data = _load_backlog()
    rows: list[dict[str, Any]] = []
    for row in data.get("ideas", []):
        if not isinstance(row, dict):
            continue
        if str(row.get("sub_mode") or "").strip().lower() != sm:
            continue
        if not _is_backlog_fresh(row):
            continue
        if str(row.get("status") or "").strip().lower() != "suggested":
            continue
        rows.append(row)
    rows.sort(
        key=lambda r: (
            int(r.get("quality_score") or 0),
            str(r.get("updated_at") or r.get("suggested_at") or ""),
            str(r.get("idea_id") or ""),
        ),
        reverse=True,
    )
    rows = rows[:wanted]
    return [_serialize_idea_row(r) for r in rows]


def _archive_active_suggestions(data: dict[str, Any], sub_mode: str) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    for row in data.get("ideas", []):
        if not isinstance(row, dict):
            continue
        if str(row.get("sub_mode") or "").strip().lower() != sub_mode:
            continue
        if str(row.get("status") or "").strip().lower() == "suggested":
            row["status"] = "archived"
            row["updated_at"] = now


def _normalize_candidate(raw: dict[str, Any], sub_mode: str) -> dict[str, str] | None:
    topic = re.sub(r"\s+", " ", str(raw.get("topic") or "")).strip()
    project_title = re.sub(r"\s+", " ", str(raw.get("project_title") or "")).strip()
    hook = re.sub(r"\s+", " ", str(raw.get("hook") or "")).strip()
    if len(topic) < 8:
        return None
    if len(project_title) < 5:
        project_title = topic[:120]
    return {
        "topic": topic[:360],
        "project_title": project_title[:180],
        "hook": hook[:240],
        "sub_mode": sub_mode,
    }


def _system_prompt_for(sub_mode: str) -> str:
    mode_line = {
        "facts50": "Mode facts50: suggest broad factual themes suitable for 77 concise facts.",
        "outline": "Mode outline: suggest high-concept story or documentary synopsis seeds.",
        "book_night": "Mode book_night: suggest known book titles or clear book directions for calm long summaries.",
        "unwritten_chapter": "Mode unwritten_chapter: suggest investigation themes for documentary archival style.",
    }.get(sub_mode, "Mode long-form.")
    return (
        "You generate unique long-form video topic ideas for a creator app.\n"
        f"{mode_line}\n"
        "Return ONLY valid JSON array. Each item must be an object:\n"
        '{"topic":"...", "project_title":"...", "hook":"..."}\n'
        "Rules:\n"
        "- Write in Russian.\n"
        "- topic: clear input for generator field.\n"
        "- project_title: short title for project header.\n"
        "- hook: one short line why this idea is interesting.\n"
        "- Avoid duplicates and close paraphrases of provided blocked topics.\n"
        "- No markdown, no numbering."
    )


async def _llm_candidates(sub_mode: str, count: int, blocked: list[str], seed: str) -> list[dict[str, str]]:
    llm = make_llm(temperature=0.2)
    block_lines = "\n".join(f"- {x}" for x in blocked[:140]) if blocked else "- (none)"
    msg = await llm.ainvoke(
        [
            SystemMessage(content=_system_prompt_for(sub_mode)),
            HumanMessage(
                content=(
                    f"SEED={seed}\n"
                    f"Generate exactly {count} ideas for sub_mode={sub_mode}.\n"
                    "Blocked topics/titles (do not repeat):\n"
                    f"{block_lines}\n"
                )
            ),
        ]
    )
    raw = msg.content if isinstance(msg.content, str) else str(msg.content)
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text).strip()
    try:
        parsed = json.loads(text)
    except Exception:
        s = text.find("[")
        e = text.rfind("]") + 1
        if s >= 0 and e > s:
            parsed = json.loads(text[s:e])
        else:
            logger.warning(f"[mode5_topic_ideas] Could not parse JSON: {text[:220]}")
            return []
    if not isinstance(parsed, list):
        return []
    return [row for row in parsed if isinstance(row, dict)]


def _heuristic_score(item: dict[str, str], sub_mode: str) -> int:
    topic = item.get("topic") or ""
    title = item.get("project_title") or ""
    hook = item.get("hook") or ""
    score = 40
    score += min(20, len(topic) // 10)
    score += min(12, len(title) // 8)
    if hook:
        score += 6
    if sub_mode == "book_night" and ("," in topic or "—" in topic):
        score += 10
    if sub_mode == "unwritten_chapter" and any(k in topic.lower() for k in ("архив", "расслед", "войн", "верс", "документ")):
        score += 12
    if sub_mode == "facts50" and any(k in topic.lower() for k in ("фактов", "история", "тайн", "наук")):
        score += 8
    return max(1, min(100, score))


async def _llm_score_candidates(sub_mode: str, seed: str, items: list[dict[str, str]]) -> list[int]:
    if not items:
        return []
    llm = make_llm(temperature=0.0)
    lines = []
    for i, it in enumerate(items):
        lines.append(
            f"{i+1}. topic={it.get('topic','')} | project_title={it.get('project_title','')} | hook={it.get('hook','')}"
        )
    sys = (
        "Score each candidate idea for long-form mode quality.\n"
        "Return ONLY JSON array of integers 1..100 in same order.\n"
        f"sub_mode={sub_mode}, seed={seed}."
    )
    hum = "Candidates:\n" + "\n".join(lines)
    try:
        msg = await llm.ainvoke([SystemMessage(content=sys), HumanMessage(content=hum)])
        raw = msg.content if isinstance(msg.content, str) else str(msg.content)
        arr = json.loads(raw.strip())
        if isinstance(arr, list) and len(arr) == len(items):
            out: list[int] = []
            for x in arr:
                try:
                    out.append(max(1, min(100, int(x))))
                except Exception:
                    out.append(50)
            return out
    except Exception:
        logger.warning("[mode5_topic_ideas] LLM scoring failed, using heuristic only")
    return [50] * len(items)


def _stable_order_key(seed: str, topic: str, title: str) -> str:
    s = f"{seed}|{topic}|{title}"
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


async def suggest_mode5_topics(sub_mode: str, limit: int = 8, seed: str | None = None) -> list[dict[str, str]]:
    sm = (sub_mode or "").strip().lower()
    if sm not in _ALLOWED_SUB_MODES:
        raise ValueError("Unsupported mode5 sub_mode for topic ideas")
    wanted = max(1, min(12, int(limit or 8)))
    seed_norm = (seed or f"{sm}:{datetime.now().date().isoformat()}").strip()
    existing = _combined_entries_with_backlog()
    blocked: list[str] = []
    for row in existing:
        blocked.append(str(row.get("topic") or "").strip())
        blocked.append(str(row.get("video_angle") or "").strip())

    fresh: list[dict[str, str]] = []
    attempts = 0
    while len(fresh) < wanted and attempts < 4:
        attempts += 1
        need = max(5, (wanted - len(fresh)) * 3)
        candidates = await _llm_candidates(sm, need, blocked, seed_norm)
        for cand in candidates:
            norm = _normalize_candidate(cand, sm)
            if not norm:
                continue
            combined = f"{norm['topic']} {norm['project_title']}".strip()
            if _is_duplicate(combined, existing):
                continue
            if any(_is_duplicate(combined, [{"topic": x["topic"], "video_angle": x["project_title"]}]) for x in fresh):
                continue
            fresh.append(norm)
            blocked.extend([norm["topic"], norm["project_title"]])
            if len(fresh) >= wanted * 2:
                break

    if not fresh:
        raise ValueError("Не удалось подобрать новые темы без повторов. Попробуйте позже.")

    heur = [_heuristic_score(x, sm) for x in fresh]
    llm_scores = await _llm_score_candidates(sm, seed_norm, fresh)
    scored: list[dict[str, Any]] = []
    for idx, idea in enumerate(fresh):
        quality_score = int(round((heur[idx] * 0.6) + (llm_scores[idx] * 0.4)))
        row = dict(idea)
        row["quality_score"] = quality_score
        row["stable_key"] = _stable_order_key(seed_norm, idea["topic"], idea["project_title"])
        scored.append(row)
    scored.sort(key=lambda x: (-int(x.get("quality_score", 0)), str(x.get("stable_key") or "")))
    selected = scored[:wanted]

    backlog = _load_backlog()
    ideas = backlog.setdefault("ideas", [])
    _archive_active_suggestions(backlog, sm)
    now = datetime.now().isoformat(timespec="seconds")
    response: list[dict[str, str]] = []
    for idea in selected:
        idea_id = str(uuid.uuid4())
        ideas.append(
            {
                "idea_id": idea_id,
                "topic": idea["topic"],
                "project_title": idea["project_title"],
                "hook": idea.get("hook") or "",
                "sub_mode": sm,
                "status": "suggested",
                "quality_score": int(idea.get("quality_score") or 0),
                "seed": seed_norm,
                "suggested_at": now,
                "updated_at": now,
            }
        )
        response.append(
            {
                "idea_id": idea_id,
                "topic": idea["topic"],
                "project_title": idea["project_title"],
                "hook": idea.get("hook") or "",
                "sub_mode": sm,
                "quality_score": int(idea.get("quality_score") or 0),
                "status": "suggested",
            }
        )
    _save_backlog(backlog)
    logger.info(f"[mode5_topic_ideas] Suggested {len(response)} unique ideas for {sm}, seed={seed_norm}")
    return response


def update_mode5_idea_status(idea_id: str, status: str) -> bool:
    iid = str(idea_id or "").strip()
    st = str(status or "").strip().lower()
    if not iid:
        return False
    if st not in _ALLOWED_STATUSES:
        raise ValueError(f"Unsupported idea status: {status}")
    data = _load_backlog()
    ideas = data.get("ideas") or []
    now = datetime.now().isoformat(timespec="seconds")
    for row in ideas:
        if not isinstance(row, dict):
            continue
        if str(row.get("idea_id") or "").strip() == iid:
            row["status"] = st
            row["updated_at"] = now
            _save_backlog(data)
            return True
    return False
