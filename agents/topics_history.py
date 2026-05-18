"""
Topics History — persistent journal of generated video topics.

Stores used topics in  output/topics_history.json  so the Trends Analyzer
can skip topics that have already been covered. After each successful run the
server may attach start_request (StartRequest JSON) for «Перегенерировать» in the video library.

Format:
{
  "topics": [
    {
      "topic":        "Нейтронные звёзды",
      "video_angle":  "Топ-5 фактов о нейтронных звёздах",
      "session_id":   "1774000000000",
      "video_path":   "output/videos/1774.../video_1774....mp4",
      "generated_at": "2026-03-19T17:45:00"
    },
    ...
  ]
}
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from loguru import logger

from config import settings

_HISTORY_FILE = settings.output_dir / "topics_history.json"


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load() -> dict:
    if _HISTORY_FILE.exists():
        try:
            return json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"topics": []}


def _save(data: dict) -> None:
    _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    _HISTORY_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _normalize(text: str) -> str:
    """Lowercase + collapse whitespace + remove punctuation for fuzzy matching."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _similarity(a: str, b: str) -> float:
    """
    Jaccard similarity on character trigrams between two NORMALIZED strings.
    Returns 0.0–1.0.
    """
    ng_a = _ngrams(a, 3)
    ng_b = _ngrams(b, 3)
    if not ng_a or not ng_b:
        return 0.0
    return len(ng_a & ng_b) / len(ng_a | ng_b)


def _is_duplicate(new_topic: str, existing: list[dict], threshold: float = 0.45) -> bool:
    """
    Return True if `new_topic` is too similar to any existing topic.

    Strategy (checked in order):
      1. Exact normalized match  → always duplicate
      2. One string is a substring of the other  → duplicate
      3. Trigram Jaccard ≥ threshold comparing new against
         old *topic* and old *video_angle* independently → duplicate
    """
    norm_new = _normalize(new_topic)
    words_new = set(norm_new.split())

    for entry in existing:
        norm_topic = _normalize(entry.get("topic", ""))
        norm_angle = _normalize(entry.get("video_angle", ""))

        # 1. Exact match
        if norm_new == norm_topic or norm_new == norm_angle:
            logger.debug(f"[TopicsHistory] Exact duplicate: {new_topic!r}")
            return True

        # 2. Substring containment (handles "О нейтронных звёздах" ⊂ topic)
        if norm_new in norm_topic or norm_topic in norm_new:
            logger.debug(f"[TopicsHistory] Substring duplicate: {new_topic!r} ~ {entry['topic']!r}")
            return True

        # 3. Key word overlap: if >60% of words in new are in old topic, it's a duplicate
        if words_new and norm_topic:
            words_old = set(norm_topic.split())
            if len(words_new & words_old) / max(len(words_new), 1) >= 0.6:
                logger.debug(
                    f"[TopicsHistory] Word-overlap duplicate: "
                    f"{new_topic!r} ~ {entry['topic']!r}"
                )
                return True

        # 4. Trigram similarity against topic
        sim_topic = _similarity(norm_new, norm_topic)
        if sim_topic >= threshold:
            logger.debug(
                f"[TopicsHistory] Trigram duplicate "
                f"(sim={sim_topic:.0%}): {new_topic!r} ≈ {entry['topic']!r}"
            )
            return True

        # 5. Trigram similarity against video_angle
        if norm_angle:
            sim_angle = _similarity(norm_new, norm_angle)
            if sim_angle >= threshold:
                logger.debug(
                    f"[TopicsHistory] Angle-duplicate "
                    f"(sim={sim_angle:.0%}): {new_topic!r} ≈ {entry['video_angle']!r}"
                )
                return True

    return False


def _ngrams(text: str, n: int) -> set[str]:
    return {text[i: i + n] for i in range(len(text) - n + 1)}


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_used_topics() -> list[dict]:
    """Return the full list of previously generated topic entries."""
    return _load().get("topics", [])


def get_start_request_for_session(session_id: str) -> dict | None:
    """Снимок тела StartRequest для перегенерации из библиотеки видео."""
    for e in get_used_topics():
        if e.get("session_id") != session_id:
            continue
        snap = e.get("start_request")
        if isinstance(snap, dict) and snap:
            return snap
    return None


def attach_start_request_to_session(session_id: str, payload: dict) -> bool:
    """Привязать параметры пайплайна к записи истории (после успешной генерации)."""
    if not payload:
        return False
    data = _load()
    found = False
    for e in data.get("topics", []):
        if e.get("session_id") == session_id:
            e["start_request"] = dict(payload)
            found = True
    if found:
        _save(data)
    return found


def upsert_start_request_for_session(session_id: str, topic: str, payload: dict) -> bool:
    """
    Сохранить StartRequest для перезапуска с Progress и перегенерации из «Видео».
    Если записи с таким session_id ещё нет (часто режим 13 / обрыв до mark_topic_used) — создаётся.
    """
    if not session_id or not isinstance(payload, dict) or not payload:
        return False
    data = _load()
    topics = data.setdefault("topics", [])
    label = (topic or "").strip() or f"Видео #{session_id[-8:]}"
    for e in topics:
        if e.get("session_id") == session_id:
            e["start_request"] = dict(payload)
            if label and not (e.get("topic") or "").strip():
                e["topic"] = label
            _save(data)
            return True
    topics.append(
        {
            "topic": label,
            "video_angle": "",
            "session_id": session_id,
            "video_path": "",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "start_request": dict(payload),
        }
    )
    _save(data)
    logger.info(f"[TopicsHistory] upsert start_request for session {session_id} (new history row)")
    return True


def _publishing_dict_usable(pub: object) -> bool:
    """True if publishing payload has at least title/description/tags (RU/EN or flat)."""
    if not isinstance(pub, dict) or not pub:
        return False
    for key in ("ru", "en"):
        block = pub.get(key)
        if isinstance(block, dict) and (
            (block.get("title") or "").strip()
            or (block.get("description") or "").strip()
            or block.get("tags")
        ):
            return True
    return bool(
        (str(pub.get("title") or "").strip())
        or (str(pub.get("description") or "").strip())
        or pub.get("tags")
    )


def get_publishing_by_session() -> dict[str, dict]:
    """Return a dict mapping session_id to publishing metadata."""
    topics = get_used_topics()
    result: dict[str, dict] = {}
    for t in topics:
        sid = t.get("session_id")
        pub = t.get("publishing")
        if sid and _publishing_dict_usable(pub):
            result[str(sid)] = pub

    # Mode 5 и др.: publishing.json в папке сессии часто есть, а в topics_history — нет.
    videos_dir = settings.videos_dir
    if not videos_dir.is_dir():
        return result
    try:
        for d in videos_dir.iterdir():
            if not d.is_dir() or d.name.startswith("_"):
                continue
            sid = d.name
            if _publishing_dict_usable(result.get(sid)):
                continue
            for pf in (d / "publishing.json", d / "mode5_plan.json"):
                if not pf.is_file():
                    continue
                try:
                    disk = json.loads(pf.read_text(encoding="utf-8"))
                except Exception:
                    continue
                pub = disk.get("publishing") if pf.name == "mode5_plan.json" else disk
                if isinstance(pub, dict) and _publishing_dict_usable(pub):
                    result[sid] = pub
                    break
    except Exception as ex:
        logger.debug(f"[TopicsHistory] publishing metadata scan: {ex}")
    return result


def is_topic_used(topic: str, video_angle: str = "") -> bool:
    """Return True if this topic (or a close variant) was already generated."""
    existing = get_used_topics()
    combined = f"{topic} {video_angle}".strip()
    return _is_duplicate(combined, existing)


def mark_topic_used(
    topic: str,
    session_id: str,
    video_path: str = "",
    video_angle: str = "",
    quote_caption_en: str | None = None,
    publishing: dict | None = None,
) -> None:
    """
    Record a topic as used after a successful video generation.

    Args:
        topic:       The topic string (may be the AI-written title).
        session_id:  Pipeline session identifier.
        video_path:  Path to the generated mp4.
        video_angle: Optional more specific angle (from TrendsAgent).
        quote_caption_en: Optional English caption (Mode 4 library).
        publishing:  Optional publishing metadata (title, description, hashtags, tags).
    """
    data = _load()
    entry = {
        "topic":        topic,
        "video_angle":  video_angle,
        "session_id":   session_id,
        "video_path":   video_path,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    if quote_caption_en:
        entry["quote_caption_en"] = quote_caption_en
    if publishing:
        entry["publishing"] = publishing
    data["topics"].append(entry)
    _save(data)
    logger.info(f"[TopicsHistory] Recorded: {topic!r}  (total: {len(data['topics'])})")


def filter_unused_topics(
    candidates: list[dict],
    topic_key: str = "topic",
    angle_key: str = "video_angle",
) -> list[dict]:
    """
    Filter a list of topic dicts, removing those already used.

    Args:
        candidates:  List of dicts (e.g. TrendingTopic from TrendsAgent).
        topic_key:   Dict key for the topic string.
        angle_key:   Dict key for the video angle string.

    Returns:
        Subset of `candidates` that have NOT been generated yet.
    """
    existing = get_used_topics()
    if not existing:
        return candidates   # nothing used yet

    fresh = []
    for c in candidates:
        combined = f"{c.get(topic_key, '')} {c.get(angle_key, '')}".strip()
        if not _is_duplicate(combined, existing):
            fresh.append(c)
        else:
            logger.info(f"[TopicsHistory] Skipping already-used topic: {c.get(topic_key)!r}")

    if not fresh:
        logger.warning(
            "[TopicsHistory] All candidate topics already used! "
            "Returning all candidates to avoid empty list."
        )
        return candidates  # safety fallback

    logger.info(
        f"[TopicsHistory] {len(fresh)}/{len(candidates)} topics are fresh "
        f"(skipped {len(candidates) - len(fresh)} duplicates)"
    )
    return fresh


def remove_topic(session_id: str) -> bool:
    """
    Remove a specific topic entry by session_id.

    Returns True if the entry was found and removed, False otherwise.
    """
    data = _load()
    before = len(data["topics"])
    data["topics"] = [t for t in data["topics"] if t.get("session_id") != session_id]
    after = len(data["topics"])
    if after < before:
        _save(data)
        logger.info(f"[TopicsHistory] Removed session {session_id} ({before - after} entries)")
        return True
    logger.warning(f"[TopicsHistory] session_id {session_id!r} not found in history")
    return False


def print_history() -> None:
    """Pretty-print the full topic history to the console."""
    topics = get_used_topics()
    if not topics:
        print("No topics generated yet.")
        return
    print(f"\n{'─'*60}")
    print(f"  Topics History ({len(topics)} entries)")
    print(f"{'─'*60}")
    for i, t in enumerate(topics, 1):
        print(f"  {i:>3}. [{t.get('generated_at', '?')[:10]}] {t['topic']}")
        if t.get("video_angle") and t["video_angle"] != t["topic"]:
            print(f"       angle: {t['video_angle']}")
        print(f"       session: {t.get('session_id', '?')}")
    print(f"{'─'*60}\n")
