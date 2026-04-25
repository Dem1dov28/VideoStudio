"""
Mode 5 Pipeline — ручной long-form текст -> TTS (VoiceAPI) по чанкам ->
окна ~30 с -> картинки в едином стиле -> превью по чанкам -> review/regenerate -> финальная склейка.
"""

from __future__ import annotations

import asyncio
import functools
import json
import random
import threading
from datetime import datetime, timezone
import re
import shutil
import subprocess
import time
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Awaitable, Callable

from loguru import logger

from agents.video_editor.music_gen import generate_background_music
from agents.video_editor.tts import plain_text_for_voiceapi_tts, synthesize
from agents.video_editor.whisper_timestamps import get_word_timestamps_from_audio_path
from config import settings
from modes.mode13.pipeline import (
    VISUAL_POLICY_LONGFORM_FLEX,
    _build_image_prompt_async,
    _derive_style_suffix,
    _ffmpeg_concat,
    _generate_one_image,
    _text_for_window,
    _windows_for_duration,
)
from modes.mode13.visual_bible import derive_mode5_visual_bible, mode5_art_direction_tail_horizontal
from modes.mode5.facts50_visual_style import derive_facts50_unified_style_suffix
from modes.mode5.video_assembler import assemble_mode5_video
from utils.ffmpeg_resolve import require_ffmpeg_or_raise, resolve_ffmpeg_executable
from utils.wav_pcm import slice_wav_time_range

MODE5_PLAN = "mode5_plan.json"

MODE5_CKPT_STUB = "stub"
MODE5_CKPT_AFTER_TTS = "after_tts"
MODE5_CKPT_AFTER_IMAGES = "after_images"
MODE5_CKPT_AFTER_SLICES = "after_slices"
MODE5_CKPT_AFTER_PREVIEWS = "after_previews"
MODE5_CKPT_COMPLETED = "completed"

_mode5_plan_io_locks: dict[str, threading.Lock] = {}


def _mode5_plan_io_lock(session_id: str) -> threading.Lock:
    if session_id not in _mode5_plan_io_locks:
        _mode5_plan_io_locks[session_id] = threading.Lock()
    return _mode5_plan_io_locks[session_id]


def _touch_mode5_checkpoint(plan: dict[str, Any], stage: str, **extra: Any) -> None:
    payload: dict[str, Any] = {
        "stage": stage,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "schema": 1,
    }
    if extra:
        payload["extra"] = {k: v for k, v in extra.items() if v is not None}
    plan["pipeline_checkpoint"] = payload


def _mode5_visual_policy(sub_mode: str | None) -> str:
    sm = (sub_mode or "").strip().lower()
    if sm == "facts50":
        return "facts50"
    if sm == "book_night":
        return "book_night"
    if sm == "unwritten_chapter":
        return "unwritten_chapter"
    if sm == "outline":
        return VISUAL_POLICY_LONGFORM_FLEX
    # Manual/bible must still obey strict mode5 single-scene and anti-book rules.
    return "mode5"


def _unwritten_chunk_anchor_by_index(outline_doc: dict[str, Any] | None) -> dict[int, dict[str, str]]:
    out: dict[int, dict[str, str]] = {}
    if not isinstance(outline_doc, dict):
        return out
    idx = 0
    for ch in outline_doc.get("chapters") or []:
        if not isinstance(ch, dict):
            continue
        ct = str(ch.get("title") or "").strip()
        for sc in ch.get("subchapters") or []:
            if not isinstance(sc, dict):
                continue
            ev = str(sc.get("evidence_anchor") or "").strip()
            va = str(sc.get("visual_anchor") or "").strip()
            hs = str(sc.get("human_stakes") or "").strip()
            mc = str(sc.get("micro_conclusion") or "").strip()
            anchor_parts = [
                f"Block title: {ct}" if ct else "",
                f"Evidence anchor: {ev}" if ev else "",
                f"Visual anchor: {va}" if va else "",
                f"Human stakes: {hs}" if hs else "",
                f"Target micro-conclusion: {mc}" if mc else "",
            ]
            out[idx] = {
                "prompt_prefix": " | ".join([x for x in anchor_parts if x])[:1000],
                "evidence_anchor": ev[:280],
                "visual_anchor": va[:280],
                "human_stakes": hs[:280],
            }
            idx += 1
    return out


def _chunk_block_prompt_prefix(chunk: dict[str, Any] | None, explicit: str = "") -> str:
    prefix = str(explicit or "").strip()
    if prefix:
        return prefix[:1000]
    if not isinstance(chunk, dict):
        return ""
    parts = []
    chapter_title = str(chunk.get("chapter_title") or "").strip()
    subchapter_title = str(chunk.get("subchapter_title") or "").strip()
    evidence_anchor = str(chunk.get("evidence_anchor") or "").strip()
    visual_anchor = str(chunk.get("visual_anchor") or "").strip()
    human_stakes = str(chunk.get("human_stakes") or "").strip()
    if chapter_title or subchapter_title:
        label = " — ".join([x for x in (chapter_title, subchapter_title) if x])
        parts.append(f"Block title: {label}")
    if evidence_anchor:
        parts.append(f"Evidence anchor: {evidence_anchor}")
    if visual_anchor:
        parts.append(f"Visual anchor: {visual_anchor}")
    if human_stakes:
        parts.append(f"Human stakes: {human_stakes}")
    return " | ".join(parts)[:1000]
CHUNK_SEC_DEFAULT = 300
SEG_SEC_DEFAULT = 15
_WORDS_PER_MIN = {"ru": 135.0, "en": 150.0}
_MIN_CHUNK_TEXT_LEN = 80
_MIN_CHUNK_TEXT_LEN_FACTS50 = 40
_MODE5_VARIATION_SHOTS = (
    "wide establishing shot",
    "medium environmental shot",
    "close-up detail shot",
    "over-the-shoulder perspective",
    "low-angle cinematic shot",
    "high-angle overview",
    "rule-of-thirds side composition",
    "foreground-depth layered composition",
)
_MODE5_INTRO_ANIMATION_DESCRIPTION = (
    "Animation direction: seamless loop, identical opening and closing frame, "
    "very subtle cinematic ambient motion, gentle parallax drift, no sudden cuts, "
    "no fast camera moves, no flicker, no morphing artifacts."
)
_MODE5_PROMPT_BAN_PATTERNS = (
    r"\bcollage\b",
    r"\bcarousel\b",
    r"\bgallery\b",
    r"\bcontact[\s-]?sheet\b",
    r"\b(?:multi|multiple)[-\s]?(?:panel|photo|image|frame|picture)s?\b",
    r"\b(?:grid|mosaic)\b.{0,40}\b(?:photo|image|picture|frame)s?\b",
    r"\bopen book\b",
    r"\bpage spread\b",
    r"\bmanuscript\b",
    r"\blibrary shelf\b",
    r"\breading desk\b",
    r"\btable with book\b",
    r"\bbook on (?:a )?table\b",
    r"\bbook on (?:a )?desk\b",
)
_MODE5_PROMPT_GUARD = (
    "Hard override for mode5: one dominant full-frame scene only. "
    "Use a single uninterrupted composition in one frame; avoid tiled or segmented layouts. "
    "No reading trope (open book, page spread, manuscript, desk-with-book). "
    "No text/UI/logos/watermarks in frame. "
    "Keep one series style, but vary camera angle/framing/subject setup between adjacent frames."
)


def _mode5_output_format() -> str:
    fmt = str(getattr(settings, "mode5_video_format", "horizontal") or "horizontal").strip().lower()
    return "horizontal" if fmt == "horizontal" else "vertical"


def _mode5_image_aspect_ratio() -> str:
    return "16:9" if _mode5_output_format() == "horizontal" else "9:16"


def _mode5_parallel_images_cap() -> int:
    v = int(getattr(settings, "mode5_max_parallel_images", 10) or 10)
    return max(1, min(32, v))


def _clamp_mode5_parallel_images(value: int | None) -> int:
    cap = _mode5_parallel_images_cap()
    if value is None:
        return cap
    try:
        v = int(value)
    except (TypeError, ValueError):
        return cap
    v = max(1, v)
    return min(cap, v)


def _mode5_locked_style(plan: dict[str, Any]) -> str:
    locked = str(plan.get("style_lock") or "").strip()
    if locked:
        if str(plan.get("style_suffix") or "").strip() != locked:
            plan["style_suffix"] = locked
        return locked
    base = str(plan.get("style_suffix") or "").strip()
    if base:
        plan["style_lock"] = base
    return base


def _mode5_prompt_fingerprint(text: str) -> str:
    tokens = [t for t in re.findall(r"[a-zA-Zа-яА-Я0-9]+", (text or "").lower()) if len(t) >= 4]
    if not tokens:
        return "neutral scene"
    return " ".join(tokens[:6])


def _sanitize_mode5_image_prompt(prompt: str) -> str:
    original = (prompt or "").strip()
    if not original:
        return original
    flagged = any(re.search(p, original, flags=re.IGNORECASE) for p in _MODE5_PROMPT_BAN_PATTERNS)
    cleaned = original
    if flagged:
        for p in _MODE5_PROMPT_BAN_PATTERNS:
            cleaned = re.sub(p, " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return f"{cleaned}\n\n{_MODE5_PROMPT_GUARD}"


def _session_dir(session_id: str) -> Path:
    return settings.videos_dir / session_id


def _mode5_dir(session_id: str) -> Path:
    d = _session_dir(session_id) / "clips" / "mode5"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_mode5_placeholder_image(path: Path, *, aspect_ratio: str | None = None) -> None:
    """
    Last-resort fallback: write a neutral placeholder frame so one failed image does not
    abort the entire already-generated pipeline.
    """
    ff = resolve_ffmpeg_executable()
    if not ff:
        raise RuntimeError("ffmpeg not found for mode5 placeholder image fallback")
    ratio = str(aspect_ratio or _mode5_image_aspect_ratio()).strip()
    size = "1280x720" if ratio == "16:9" else "720x1280"
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ff,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=#242833:s={size}",
        "-frames:v",
        "1",
        str(path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _rel_session(session_root: Path, path: Path) -> str:
    return path.resolve().relative_to(session_root.resolve()).as_posix()


def detect_mode5_language(text: str, preferred: str | None = None) -> str:
    pref = (preferred or "").strip().lower()
    if pref in {"ru", "en"}:
        return pref
    sample = " ".join((text or "").split())[:4000]
    if not sample:
        return "ru"
    cyr = sum(1 for ch in sample if "\u0400" <= ch <= "\u04ff")
    lat = sum(1 for ch in sample.lower() if "a" <= ch <= "z")
    if cyr >= 8 and cyr >= lat:
        return "ru"
    if lat >= 8 and lat > cyr:
        return "en"
    common_ru = (" и ", " что ", " это ", " как ", " для ", " его ", " она ", " был ", " были ")
    common_en = (" the ", " and ", " of ", " to ", " in ", " was ", " were ", " with ", " that ")
    low = f" {sample.lower()} "
    ru_hits = sum(low.count(token) for token in common_ru)
    en_hits = sum(low.count(token) for token in common_en)
    return "en" if en_hits > ru_hits else "ru"


def load_mode5_plan(session_id: str) -> dict[str, Any]:
    p = _session_dir(session_id) / MODE5_PLAN
    if not p.is_file():
        raise FileNotFoundError(f"{MODE5_PLAN} not found for session {session_id}")
    return json.loads(p.read_text(encoding="utf-8"))


def _save_mode5_plan(
    session_id: str,
    plan: dict[str, Any],
    *,
    checkpoint: str | None = None,
    **checkpoint_extra: Any,
) -> None:
    """Atomic JSON write; optional checkpoint touch in the same critical section (thread-safe)."""
    with _mode5_plan_io_lock(session_id):
        if checkpoint is not None:
            _touch_mode5_checkpoint(plan, checkpoint, **checkpoint_extra)
        root = _session_dir(session_id)
        root.mkdir(parents=True, exist_ok=True)
        dst = root / MODE5_PLAN
        tmp = root / f".{MODE5_PLAN}.tmp"
        body = json.dumps(plan, ensure_ascii=False, indent=2)
        tmp.write_text(body, encoding="utf-8")
        tmp.replace(dst)


def _checkpoint_stage(plan: dict[str, Any]) -> str | None:
    ck = plan.get("pipeline_checkpoint")
    if not isinstance(ck, dict):
        return None
    st = ck.get("stage")
    return str(st).strip() if st is not None else None


def _mode5_chunk_images_complete(session_root: Path, ch: dict[str, Any]) -> bool:
    for seg in ch.get("segments") or []:
        rel = str(seg.get("image") or "").strip()
        if not rel:
            return False
        if not (session_root / rel).is_file():
            return False
    return True


def _mode5_chunk_slices_complete(session_root: Path, ch: dict[str, Any]) -> bool:
    for seg in ch.get("segments") or []:
        rel = str(seg.get("audio") or "").strip()
        if not rel:
            continue
        if not (session_root / rel).is_file():
            return False
    return True


def _default_mode5_chunk_audio_paths(session_id: str, chunk_index: int) -> tuple[Path, Path]:
    m5 = _mode5_dir(session_id)
    return (
        m5 / f"chunk_{chunk_index:03d}.mp3",
        m5 / f"chunk_{chunk_index:03d}.wav",
    )


def _resolve_mode5_chunk_audio_paths(
    session_id: str, ch: dict[str, Any]
) -> tuple[Path | None, Path | None]:
    session_root = _session_dir(session_id)
    idx = int(ch.get("index") or 0)
    default_mp3, default_wav = _default_mode5_chunk_audio_paths(session_id, idx)
    rel_mp3 = str(ch.get("chunk_audio") or "").strip()
    rel_wav = str(ch.get("chunk_audio_wav") or "").strip()
    mp3_path = (session_root / rel_mp3) if rel_mp3 else default_mp3
    wav_path = (session_root / rel_wav) if rel_wav else default_wav
    return (mp3_path if mp3_path.is_file() else None, wav_path if wav_path.is_file() else None)


def _all_chunk_previews_on_disk(session_root: Path, chunks: list[dict[str, Any]]) -> bool:
    if not chunks:
        return False
    for ch in chunks:
        rel = str(ch.get("preview_relpath") or "").strip()
        if not rel or not (session_root / rel).is_file():
            return False
    return True


def _mode5_segment_image_counts(
    session_root: Path, plan: dict[str, Any]
) -> tuple[int, int, int, int]:
    """
    Returns (segments_with_image_file, segments_total, chunks_fully_imaged, chunks_with_any_segment).
    """
    chunks = list(plan.get("chunks") or [])
    seg_done = 0
    seg_total = 0
    chunks_with_segs = 0
    chunks_fully_imaged = 0
    for ch in chunks:
        segs = list(ch.get("segments") or [])
        if not segs:
            continue
        chunks_with_segs += 1
        ok = True
        for seg in segs:
            seg_total += 1
            img = str(seg.get("image") or "").strip()
            if img and (session_root / img).is_file():
                seg_done += 1
            else:
                ok = False
        if ok:
            chunks_fully_imaged += 1
    return seg_done, seg_total, chunks_fully_imaged, chunks_with_segs


def _mode5_previews_on_disk_count(session_root: Path, chunks: list[dict[str, Any]]) -> int:
    n = 0
    for ch in chunks:
        rel = str(ch.get("preview_relpath") or "").strip()
        if rel and (session_root / rel).is_file():
            n += 1
    return n


def _mode5_progress_hint_payload(session_root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    """Human-readable progress for /review-state while previews or final video are not done."""
    final_mp4 = session_root / "video_mode5.mp4"
    if final_mp4.is_file():
        return {
            "mode5_progress_hint": None,
            "mode5_segments_imaged": None,
            "mode5_segments_total": None,
            "mode5_chunks_imaged": None,
            "mode5_chunks_with_segments": None,
            "mode5_previews_on_disk": None,
        }
    chunks = list(plan.get("chunks") or [])
    n_ch = len(chunks)
    seg_done, seg_total, ch_img, ch_w_seg = _mode5_segment_image_counts(session_root, plan)
    prev_done = _mode5_previews_on_disk_count(session_root, chunks)
    ck = plan.get("pipeline_checkpoint")
    stage = (ck.get("stage") or "").strip() if isinstance(ck, dict) else ""

    hint: str | None = None
    if seg_total == 0:
        if stage == MODE5_CKPT_STUB:
            hint = "Параллельная озвучка чанков (TTS)…"
        elif stage == MODE5_CKPT_AFTER_TTS:
            hint = "Озвучка на диске, готовятся сегменты и картинки…"
        elif n_ch > 0:
            hint = "Готовится разметка и иллюстрации…"
    elif seg_done < seg_total:
        hint = (
            f"Идёт генерация картинок: {seg_done} из {seg_total} кадров "
            f"(частей с полным набором кадров: {ch_img} из {ch_w_seg})…"
        )
    elif n_ch > 0 and prev_done < n_ch:
        hint = "Сборка превью по частям (короткие mp4 для проверки)…"

    return {
        "mode5_progress_hint": hint,
        "mode5_segments_imaged": seg_done,
        "mode5_segments_total": seg_total,
        "mode5_chunks_imaged": ch_img,
        "mode5_chunks_with_segments": ch_w_seg,
        "mode5_previews_on_disk": prev_done,
    }


def mode5_resume_snapshot_for_plan(session_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    """Whether POST continue-generation can proceed using saved mode5 artifacts on disk."""
    stage = _checkpoint_stage(plan)
    root = _session_dir(session_id)
    final_mp4 = root / "video_mode5.mp4"
    if final_mp4.is_file():
        return {"can_resume": False, "stage": stage, "reason": "final_video_exists"}
    chunks = list(plan.get("chunks") or [])
    if not chunks:
        return {"can_resume": False, "stage": stage, "reason": "no_chunks"}
    sm = (plan.get("sub_mode") or "").strip().lower()
    if sm == "unwritten_chapter" and stage in (MODE5_CKPT_STUB, MODE5_CKPT_AFTER_IMAGES):
        return {"can_resume": True, "stage": stage, "reason": "resume_before_tts"}
    for ch in chunks:
        _mp3_path, wav_path = _resolve_mode5_chunk_audio_paths(session_id, ch)
        if wav_path is None:
            return {"can_resume": False, "stage": stage, "reason": "missing_chunk_wav"}
    if _all_chunk_previews_on_disk(root, chunks):
        return {"can_resume": False, "stage": stage or MODE5_CKPT_COMPLETED, "reason": "previews_complete"}
    if stage == MODE5_CKPT_STUB:
        return {"can_resume": True, "stage": stage, "reason": "resume_from_stub"}
    return {"can_resume": True, "stage": stage, "reason": ""}


def mode5_resume_snapshot(session_id: str) -> dict[str, Any]:
    try:
        plan = load_mode5_plan(session_id)
    except FileNotFoundError:
        return {"can_resume": False, "stage": None, "reason": "plan_not_found"}
    return mode5_resume_snapshot_for_plan(session_id, plan)


def _attach_mode5_resume_flags_from_plan(
    session_id: str, plan: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    snap = mode5_resume_snapshot_for_plan(session_id, plan)
    out = {**payload}
    out["mode5_can_resume"] = bool(snap.get("can_resume"))
    out["mode5_checkpoint_stage"] = snap.get("stage")
    out["mode5_resume_reason"] = snap.get("reason") or None
    return out


def _attach_mode5_resume_flags(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    plan = load_mode5_plan(session_id)
    return _attach_mode5_resume_flags_from_plan(session_id, plan, payload)


def _wav_duration_sec(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
    if rate <= 0:
        raise ValueError(f"Invalid WAV framerate: {path}")
    return frames / float(rate)


def _convert_audio_to_wav(src: Path, dst: Path) -> None:
    ff = resolve_ffmpeg_executable()
    if not ff:
        raise RuntimeError("ffmpeg not found for mode 5 audio conversion")
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ff,
        "-y",
        "-i",
        str(src),
        "-ac",
        "1",
        "-ar",
        "22050",
        "-f",
        "wav",
        str(dst),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=3600)


def _split_into_sentences(text: str) -> list[str]:
    compact = re.sub(r"\r\n?", "\n", text or "").strip()
    if not compact:
        return []
    blocks = [b.strip() for b in re.split(r"\n{2,}", compact) if b.strip()]
    out: list[str] = []
    for block in blocks:
        parts = re.split(r"(?<=[.!?…])\s+(?=[A-ZА-ЯЁ0-9\"'«(])", block)
        for part in parts:
            p = re.sub(r"\s+", " ", part).strip()
            if p:
                out.append(p)
    return out


def _fallback_word_chunks(text: str, approx_words: int) -> list[str]:
    words = [w for w in re.split(r"\s+", text.strip()) if w]
    if not words:
        return []
    chunk_words = max(80, approx_words)
    out: list[str] = []
    i = 0
    while i < len(words):
        part = words[i : i + chunk_words]
        out.append(" ".join(part).strip())
        i += chunk_words
    return out


def _estimate_chunks_from_script(text: str, *, language: str, chunk_seconds: int) -> list[str]:
    sents = _split_into_sentences(text)
    wpm = _WORDS_PER_MIN.get((language or "ru").strip().lower(), 140.0)
    approx_words = max(120, int(round(chunk_seconds * wpm / 60.0)))
    if not sents:
        return _fallback_word_chunks(text, approx_words)
    chunks: list[str] = []
    cur: list[str] = []
    cur_words = 0
    for sent in sents:
        words_n = len(sent.split())
        if cur and cur_words + words_n > approx_words:
            chunks.append(" ".join(cur).strip())
            cur = [sent]
            cur_words = words_n
        else:
            cur.append(sent)
            cur_words += words_n
    if cur:
        chunks.append(" ".join(cur).strip())
    merged: list[str] = []
    for chunk in chunks:
        if merged and len(chunk) < _MIN_CHUNK_TEXT_LEN:
            merged[-1] = f"{merged[-1]} {chunk}".strip()
        else:
            merged.append(chunk)
    return merged or [text.strip()]


def _fallback_window_texts(text: str, windows: list[tuple[float, float]]) -> list[str]:
    words = [w for w in re.split(r"\s+", text.strip()) if w]
    if not windows:
        return []
    if not words:
        return [""] * len(windows)
    per = max(1, len(words) // len(windows))
    out: list[str] = []
    pos = 0
    for i in range(len(windows)):
        if i == len(windows) - 1:
            block = words[pos:]
        else:
            block = words[pos : pos + per]
        pos += per
        out.append(" ".join(block).strip())
    return out


def _segments_for_chunk(
    chunk_text: str,
    duration_sec: float,
    seg_sec: int,
    wts: list[tuple[float, float]] | None,
    words: list[str] | None,
) -> list[dict[str, Any]]:
    windows = _windows_for_duration(duration_sec, float(seg_sec))
    if not windows:
        return []
    texts: list[str] = []
    if wts and words:
        texts = [_text_for_window(wts, words, t0, t1) for t0, t1 in windows]
    if not any(t.strip() for t in texts):
        texts = _fallback_window_texts(chunk_text, windows)
    out: list[dict[str, Any]] = []
    for si, ((t0, t1), txt) in enumerate(zip(windows, texts)):
        out.append({"s": si, "t0": t0, "t1": t1, "text": txt.strip()})
    return out


def _segments_for_chunk_from_text(
    chunk_text: str,
    seg_sec: int,
    *,
    language: str,
) -> list[dict[str, Any]]:
    compact = re.sub(r"\s+", " ", (chunk_text or "").strip())
    if not compact:
        return []
    lang = (language or "ru").strip().lower()
    wpm = _WORDS_PER_MIN.get(lang, 140.0)
    target_words = max(30, int(round(max(8, int(seg_sec or SEG_SEC_DEFAULT)) * wpm / 60.0)))
    sents = _split_into_sentences(compact)
    if not sents:
        sents = _fallback_word_chunks(compact, target_words)
    blocks: list[str] = []
    cur: list[str] = []
    cur_words = 0
    for sent in sents:
        wn = len(sent.split())
        if cur and cur_words + wn > target_words:
            blocks.append(" ".join(cur).strip())
            cur = [sent]
            cur_words = wn
        else:
            cur.append(sent)
            cur_words += wn
    if cur:
        blocks.append(" ".join(cur).strip())
    blocks = [b for b in blocks if b.strip()]
    if not blocks:
        blocks = [compact]

    words_per_block = [max(1, len(b.split())) for b in blocks]
    total_words = max(1, sum(words_per_block))
    est_total = max(float(len(blocks) * max(8, int(seg_sec or SEG_SEC_DEFAULT))), (total_words / wpm) * 60.0)
    t = 0.0
    out: list[dict[str, Any]] = []
    for si, (txt, wn) in enumerate(zip(blocks, words_per_block)):
        part = est_total * (wn / total_words)
        t1 = est_total if si == len(blocks) - 1 else min(est_total, t + part)
        out.append({"s": si, "t0": max(0.0, t), "t1": max(t + 0.05, t1), "text": txt.strip()})
        t = t1
    return out


def _retime_existing_segments_for_audio(
    segments: list[dict[str, Any]],
    *,
    duration_sec: float,
) -> None:
    n = len(segments)
    dur = max(0.05, float(duration_sec or 0.0))
    if n <= 0:
        return
    weights = [max(1, len(str(seg.get("text") or "").split())) for seg in segments]
    total_w = max(1, sum(weights))
    t = 0.0
    for i, seg in enumerate(segments):
        share = dur * (weights[i] / total_w)
        t1 = dur if i == (n - 1) else min(dur, t + share)
        seg["t0"] = max(0.0, t)
        seg["t1"] = max(t + 0.05, t1)
        t = t1


def _segments_for_facts50_chunk(
    fact_hint: str,
    chunk_text: str,
    duration_sec: float,
    *,
    overlay_title: str,
) -> list[dict[str, Any]]:
    t1 = max(0.05, float(duration_sec))
    hint = re.sub(r"\s+", " ", (fact_hint or "").strip())
    spoken = re.sub(r"\s+", " ", (chunk_text or "").strip())
    if hint and spoken:
        # Keep strict fact anchor, but also feed the spoken moment for better visual alignment.
        text = f"{hint}. Spoken context: {spoken[:900]}"
    else:
        text = hint or spoken
    return [{"s": 0, "t0": 0.0, "t1": t1, "text": text, "overlay_title": overlay_title}]


def _fact_overlay_title(index: int) -> str:
    """Подпись на кадре: всегда латиница Fact 1, Fact 2, … (независимо от языка озвучки)."""
    return f"Fact {index + 1}"


def _fact_spoken_prefix(index: int, language: str) -> str:
    n = index + 1
    if (language or "").strip().lower() == "ru":
        return f"Факт {n}."
    return f"Fact {n}."


def _ensure_fact_spoken_prefix(index: int, text: str, language: str) -> str:
    clean = re.sub(r"\s+", " ", (text or "").strip())
    prefix = _fact_spoken_prefix(index, language)
    if not clean:
        return prefix
    low = clean.lower()
    if low.startswith(f"fact {index + 1}".lower()) or low.startswith(f"факт {index + 1}".lower()):
        return clean
    return f"{prefix} {clean}".strip()


def _facts50_intro_text(topic: str, language: str) -> str:
    """
    Короткое настроение + тема. Без формулы «N фактов о …» — её дублирует финал и озвучка фактов.
    """
    clean_topic = re.sub(r"\s+", " ", (topic or "").strip())
    if (language or "").strip().lower() == "ru":
        return (
            "Устройтесь поудобнее. Дальше — спокойный рассказ: один факт за другим, без суеты, в темпе для фона и сна. "
            f"Тема этого выпуска — «{clean_topic}»."
        )
    return (
        "Settle in. What follows is a calm voiceover—one fact after another, unhurried, meant as gentle background. "
        f"Tonight's thread is: {clean_topic}."
    )


def _facts50_outro_text(_topic: str, language: str) -> str:
    """
    Мягкое завершение без повторения той же формулы, что была во вступлении (без «N фактов по теме …»).
    Тему намеренно не произносим снова — она уже в интро и в теле фактов.
    """
    if (language or "").strip().lower() == "ru":
        variants = [
            "Спасибо, что были со мной до конца. Пусть останется лёгкое настроение — и спокойной ночи.",
            "На сегодня у меня всё. Дышите ровно; если захотите продолжения — задайте новую тему, сделаем ещё один выпуск.",
            "Я поблагодарю за внимание и отпущу вас отдыхать. До встречи в следующем спокойном выпуске.",
        ]
        return random.choice(variants)
    variants = [
        "Thank you for listening all the way through. Wishing you a quiet night.",
        "That's all from me for now. Breathe easy—when you want more, pick a new topic and we'll make another episode.",
        "I'll leave you here. Rest well, and I'll see you in the next calm installment.",
    ]
    return random.choice(variants)


def _facts50_fact_index_for_chunk(chunks: list[dict[str, Any]], chunk_index: int) -> int:
    fact_pos = 0
    for i, ch in enumerate(chunks):
        if i == chunk_index:
            return fact_pos
        if not bool(ch.get("is_intro")) and not bool(ch.get("is_outro")):
            fact_pos += 1
    return fact_pos


def _chunk_meta_public(ch: dict[str, Any]) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "index": ch["index"],
        "duration_sec": ch["duration_sec"],
        "num_segments": len(ch.get("segments") or []),
        "text": ch.get("text", ""),
        "segments": [
            {
                "index": seg.get("s"),
                "text": seg.get("text", ""),
                "t0": seg.get("t0"),
                "t1": seg.get("t1"),
            }
            for seg in (ch.get("segments") or [])
        ],
    }
    ct = ch.get("chapter_title")
    st = ch.get("subchapter_title")
    if isinstance(ct, str) and ct.strip():
        meta["chapter_title"] = ct.strip()
    if isinstance(st, str) and st.strip():
        meta["subchapter_title"] = st.strip()
    for k in ("visual_anchor", "evidence_anchor", "human_stakes"):
        v = ch.get(k)
        if isinstance(v, str) and v.strip():
            meta[k] = v.strip()
    return meta


def _result_payload(
    session_id: str,
    plan: dict[str, Any],
    *,
    review_ready: bool,
    final_video: str | None = None,
) -> dict[str, Any]:
    chunks = plan.get("chunks") or []
    preview_filenames = [ch.get("preview_relpath") for ch in chunks if ch.get("preview_relpath")]
    label = (plan.get("header_title") or "").strip() or f"Ручной long-form ({len(chunks)} частей)"
    return {
        "session_id": session_id,
        "video_path": final_video,
        "video_paths": [final_video] if final_video else [],
        "topic": label,
        "quote_caption": label,
        "quote_caption_ru": label[:220],
        "quote_caption_en": None,
        "trend": None,
        "report": None,
        "publishing": None,
        "mode5_review_ready": review_ready,
        "mode5_clip_filenames": preview_filenames if review_ready else [],
        "mode5_chunks_meta": [_chunk_meta_public(ch) for ch in chunks] if review_ready else [],
        "mode5_sub_mode": plan.get("sub_mode") or "manual",
    }


def _mode5_review_pending_snapshot(session_id: str) -> dict[str, Any]:
    """Stable JSON when mode5_plan.json is not on disk yet (e.g. before first save)."""
    plan_shell: dict[str, Any] = {"chunks": [], "sub_mode": None}
    payload = _result_payload(session_id, plan_shell, review_ready=False)
    payload["mode5_total_chunks"] = 0
    payload["mode5_ready_chunks"] = 0
    payload["mode5_partial"] = True
    payload["mode5_plan_pending"] = True
    payload["mode5_progress_hint"] = "Старт конвейера: первый план появится через несколько секунд…"
    payload["mode5_segments_imaged"] = None
    payload["mode5_segments_total"] = None
    payload["mode5_chunks_imaged"] = None
    payload["mode5_chunks_with_segments"] = None
    payload["mode5_previews_on_disk"] = None
    return payload


async def _generate_chunk_images(
    session_id: str,
    chunk: dict[str, Any],
    style_suffix: str,
    *,
    max_parallel_images: int,
    refresh_all: bool = False,
    visual_policy: str = "default",
    visual_bible: dict[str, Any] | None = None,
    block_prompt_prefix: str = "",
    on_segment_ready: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None,
) -> None:
    session_root = _session_dir(session_id)
    cap = _mode5_parallel_images_cap()
    sem = asyncio.Semaphore(max(1, min(cap, int(max_parallel_images or cap))))
    chunk_index = int(chunk.get("index", -1))
    prompt_prefix = _chunk_block_prompt_prefix(chunk, explicit=block_prompt_prefix)
    segments = list(chunk.get("segments") or [])

    def _segment_variation_hint(seg_idx: int, seg: dict[str, Any]) -> str:
        s = int(seg.get("s", 0) or 0)
        shot = _MODE5_VARIATION_SHOTS[(chunk_index + s) % len(_MODE5_VARIATION_SHOTS)]
        alt = _MODE5_VARIATION_SHOTS[(chunk_index + s + 3) % len(_MODE5_VARIATION_SHOTS)]
        total = max(1, len(segments))
        recent_blocks: list[str] = []
        for back in (1, 2):
            prev_idx = seg_idx - back
            if prev_idx < 0 or prev_idx >= len(segments):
                continue
            prev_seg = segments[prev_idx]
            prev_s = int(prev_seg.get("s", prev_idx) or prev_idx)
            prev_shot = _MODE5_VARIATION_SHOTS[(chunk_index + prev_s) % len(_MODE5_VARIATION_SHOTS)]
            prev_fp = _mode5_prompt_fingerprint(str(prev_seg.get("text") or ""))
            recent_blocks.append(f"seg {prev_idx + 1}: {prev_shot}, theme {prev_fp}")
        avoid_recent = "; ".join(recent_blocks) if recent_blocks else "none"
        return (
            f"Variation target for this frame (segment {s + 1}/{total}): use {shot}; "
            f"avoid repeating composition from neighboring segments; prefer a distinct camera setup such as {alt}; "
            f"avoid reusing recent fingerprints ({avoid_recent}); "
            "do not repeat the same subject-location-prop triad from the previous 2 frames; "
            "keep the same global art direction and character/world continuity."
        )

    async def _one(seg_idx: int, seg: dict[str, Any]) -> tuple[dict[str, Any], BaseException | None]:
        seg_prompt_text = seg.get("text", "")
        if prompt_prefix:
            seg_prompt_text = f"{prompt_prefix}\n\nSegment meaning:\n{seg_prompt_text}"
        prompt = await _build_image_prompt_async(
            seg_prompt_text,
            style_suffix,
            output_format=_mode5_output_format(),
            variation_hint=_segment_variation_hint(seg_idx, seg),
            extra_suffix="Fresh alternative composition, same art direction." if refresh_all else "",
            visual_policy=visual_policy,
            visual_bible=visual_bible,
        )
        prompt = _sanitize_mode5_image_prompt(prompt)
        seg["image_prompt"] = prompt
        img_path = session_root / seg["image"]
        async with sem:
            try:
                await _generate_one_image(prompt, img_path, aspect_ratio=_mode5_image_aspect_ratio())
                seg["image_fallback"] = False
                seg.pop("image_fallback_reason", None)
                return seg, None
            except Exception as e:
                return seg, e

    tasks: list[asyncio.Task[tuple[dict[str, Any], BaseException | None]]] = []
    for seg_idx, seg in enumerate(segments):
        if not seg.get("image"):
            continue
        img_path = session_root / seg["image"]
        if refresh_all or not img_path.is_file():
            tasks.append(asyncio.create_task(_one(seg_idx, seg)))
    if not tasks:
        return

    # Try to reuse any already existing image from this chunk/session before hard-failing.
    session_existing = [
        p for p in (session_root / "clips" / "mode5").glob("img_c*_s*.jpg") if p.is_file()
    ]
    for fut in asyncio.as_completed(tasks):
        seg, err = await fut
        if err is not None:
            target = session_root / seg["image"]
            fallback_src: Path | None = None
            for other in chunk.get("segments") or []:
                if other is seg or not other.get("image"):
                    continue
                candidate = session_root / other["image"]
                if candidate.is_file():
                    fallback_src = candidate
                    break
            if fallback_src is None and session_existing:
                fallback_src = session_existing[0]
            try:
                if fallback_src is not None:
                    shutil.copy2(fallback_src, target)
                    seg["image_fallback_reason"] = f"copied fallback: {type(err).__name__}"
                else:
                    _write_mode5_placeholder_image(target, aspect_ratio=_mode5_image_aspect_ratio())
                    seg["image_fallback_reason"] = f"placeholder fallback: {type(err).__name__}"
                seg["image_fallback"] = True
                logger.warning(
                    f"[Mode5] Image fallback used for chunk={chunk_index} seg={seg.get('s')}: {err}"
                )
            except Exception as fallback_err:
                raise RuntimeError(
                    f"[Mode5] Failed image generation and fallback for chunk={chunk_index} seg={seg.get('s')}: "
                    f"{err}; fallback_error={fallback_err}"
                ) from fallback_err
        if on_segment_ready is not None:
            maybe = on_segment_ready(seg)
            if asyncio.iscoroutine(maybe):
                await maybe


def _render_chunk_audio_slices(session_id: str, chunk: dict[str, Any]) -> None:
    session_root = _session_dir(session_id)
    chunk_wav = session_root / chunk["chunk_audio_wav"]
    for seg in chunk.get("segments") or []:
        out_wav = session_root / seg["audio"]
        slice_wav_time_range(chunk_wav, float(seg["t0"]), float(seg["t1"]), out_wav)


def _is_global_intro_segment(chunk_index: int, segment_index: int) -> bool:
    return chunk_index == 0 and segment_index == 0


def _mode5_intro_video_path(session_id: str) -> Path:
    return _mode5_dir(session_id) / "intro_loop_c0_s0.mp4"


def _mode5_intro_animation_enabled(plan: dict[str, Any]) -> bool:
    return (plan.get("sub_mode") or "").strip().lower() == "unwritten_chapter"


def _build_mode5_intro_video_prompt(plan: dict[str, Any], seg0: dict[str, Any]) -> str:
    """
    Отдельный prompt для анимированного intro-видео (только unwritten_chapter):
    берет смысл первого сегмента + явное описание желаемой анимации.
    """
    scene_text = re.sub(r"\s+", " ", str(seg0.get("text") or "").strip())
    scene_text = scene_text[:420]
    source_image_prompt = re.sub(r"\s+", " ", str(seg0.get("image_prompt") or "").strip())
    source_image_prompt = source_image_prompt[:700]
    style_tail = re.sub(r"\s+", " ", str(plan.get("style_suffix") or "").strip())
    style_tail = style_tail[:320]

    parts = [
        "Create a loopable intro video from provided start/end keyframes.",
        _MODE5_INTRO_ANIMATION_DESCRIPTION,
    ]
    if scene_text:
        parts.append(f"Scene context: {scene_text}")
    if source_image_prompt:
        parts.append(f"Visual source context: {source_image_prompt}")
    if style_tail:
        parts.append(f"Style guardrails: {style_tail}")
    parts.append("Keep composition stable and realistic. Preserve identity and scene structure.")
    return " ".join(parts)


async def _ensure_mode5_looped_intro_video(
    session_id: str,
    plan: dict[str, Any],
    *,
    force: bool = False,
) -> None:
    chunks = list(plan.get("chunks") or [])
    if not chunks:
        return
    first_chunk = chunks[0]
    segs = list(first_chunk.get("segments") or [])
    if not segs:
        return
    seg0 = segs[0]
    if not _mode5_intro_animation_enabled(plan):
        seg0.pop("video", None)
        seg0["asset_type"] = "image"
        return
    session_root = _session_dir(session_id)
    img_rel = str(seg0.get("image") or "").strip()
    aud_rel = str(seg0.get("audio") or "").strip()
    if not img_rel or not aud_rel:
        return
    img_path = session_root / img_rel
    aud_path = session_root / aud_rel
    if not img_path.is_file() or not aud_path.is_file():
        return

    existing_rel = str(seg0.get("video") or "").strip()
    if existing_rel and not force and (session_root / existing_rel).is_file():
        seg0["asset_type"] = "video"
        return

    out_path = _mode5_intro_video_path(session_id)
    if out_path.is_file() and not force:
        seg0["video"] = _rel_session(session_root, out_path)
        seg0["asset_type"] = "video"
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        http_base = str(getattr(settings, "fastgen_http_base_url", "") or "").strip()
        if not http_base:
            logger.warning(
                "[Mode5] Intro keyframe API disabled: FASTGEN_HTTP_BASE_URL is empty, fallback to image motion"
            )
            seg0.pop("video", None)
            seg0["asset_type"] = "image"
            return
        from agents.content_generator import fastgen_http

        video_path = await fastgen_http.generate_video_from_keyframes(
            prompt=_build_mode5_intro_video_prompt(plan, seg0),
            output_dir=out_path.parent,
            start_frame_path=img_path,
            end_frame_path=img_path,
            index=0,
            video_aspect_ratio=_mode5_image_aspect_ratio(),
        )
        resolved = Path(video_path) if video_path else None
        if resolved and resolved.is_file():
            if resolved.resolve() != out_path.resolve():
                shutil.copy2(resolved, out_path)
            seg0["video"] = _rel_session(session_root, out_path)
            seg0["asset_type"] = "video"
            logger.info("[Mode5] Intro looped video prepared: {}", out_path)
            return
        logger.warning("[Mode5] Intro keyframe video was not generated, fallback to image motion")
    except Exception as err:
        logger.warning(f"[Mode5] Intro keyframe generation failed, fallback to image motion: {err}")
    seg0.pop("video", None)
    seg0["asset_type"] = "image"


def _build_chunk_preview_sync(session_id: str, chunk_index: int, plan: dict[str, Any]) -> Path:
    session_root = _session_dir(session_id)
    ch = plan["chunks"][chunk_index]
    show_sub = bool(plan.get("show_subtitles", True))
    sm = (plan.get("sub_mode") or "").strip().lower()
    ci = int(ch.get("index", chunk_index))
    segment_data: list[dict[str, Path | str]] = []
    subtitle_texts: list[str] = []
    top_labels: list[str] = []
    for seg in ch.get("segments") or []:
        img = session_root / seg["image"]
        aud = session_root / seg["audio"]
        if not img.is_file():
            raise FileNotFoundError(f"Missing image: {img}")
        if not aud.is_file():
            raise FileNotFoundError(f"Missing audio: {aud}")
        si = int(seg.get("s", len(segment_data)))
        is_intro = _is_global_intro_segment(ci, si)
        video_rel = str(seg.get("video") or "").strip()
        video_abs = (session_root / video_rel) if video_rel else None
        is_intro_video = is_intro and sm == "unwritten_chapter"
        if is_intro_video and video_abs and video_abs.is_file():
            segment_data.append(
                {
                    "asset_type": "video",
                    "video_path": video_abs,
                    "audio_path": aud,
                }
            )
        else:
            segment_data.append(
                {
                    "asset_type": "image",
                    "image_path": img,
                    "audio_path": aud,
                }
            )
        subtitle_texts.append(seg.get("text", "") if show_sub else "")
        if sm == "facts50" and (bool(ch.get("is_intro")) or bool(ch.get("is_outro"))):
            label = ""
        else:
            label = (seg.get("overlay_title") or "").strip()
            if sm == "facts50" and not label:
                fact_idx = _facts50_fact_index_for_chunk(plan.get("chunks") or [], int(ch.get("index", ci)))
                label = _fact_overlay_title(fact_idx)
        top_labels.append(label)
    out_mp4 = session_root / ch["preview_relpath"]
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    use_static = sm == "facts50" and bool(getattr(settings, "mode5_facts50_static_still", True))
    assemble_mode5_video(
        segment_data,
        out_mp4,
        subtitle_texts=subtitle_texts,
        top_labels=top_labels,
        facts50_static_still=use_static,
    )
    return out_mp4


def _build_all_chunk_previews_parallel(session_id: str, plan: dict[str, Any]) -> None:
    chunks = plan.get("chunks") or []
    if not chunks:
        return
    workers = max(1, min(8, int(getattr(settings, "mode13_preview_mp4_workers", 4) or 4)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futs = {
            executor.submit(_build_chunk_preview_sync, session_id, idx, plan): idx
            for idx in range(len(chunks))
        }
        for fut in as_completed(futs):
            idx = futs[fut]
            fut.result()
            if 0 <= idx < len(chunks):
                chunks[idx]["preview_ready"] = True
                # Persist incremental progress so UI can show ready clips while pipeline is still running.
                _save_mode5_plan(session_id, plan)


def _rebuild_mode5_missing_previews(session_id: str, plan: dict[str, Any]) -> int:
    """
    Пересобрать только отсутствующие mode5_preview_*.mp4 из уже сохранённых картинок и аудио-слайсов.
    Нужно после ручного удаления файлов, сбоя диска или прерванной параллельной сборки превью.
    """
    session_root = _session_dir(session_id)
    chunks = plan.get("chunks") or []
    rebuilt = 0
    for ci, ch in enumerate(chunks):
        rel = str(ch.get("preview_relpath") or "").strip()
        if not rel:
            continue
        p = session_root / rel
        if p.is_file():
            continue
        logger.warning("[Mode5] Preview missing for chunk {} — rebuilding {}", ci, p)
        _build_chunk_preview_sync(session_id, ci, plan)
        ch["preview_ready"] = True
        rebuilt += 1
    if rebuilt:
        _save_mode5_plan(session_id, plan)
        logger.info("[Mode5] Rebuilt {} missing chunk preview(s)", rebuilt)
    return rebuilt


async def _generate_mode5_sleep_tail_theme_images(
    session_id: str,
    plan: dict[str, Any],
    topic: str,
    n: int,
    fallback_still: Path,
) -> list[Path]:
    """One thematic still per sleep-tail segment; fail-soft copies previous or fallback."""
    style = _mode5_locked_style(plan)
    m5 = _mode5_dir(session_id)
    out: list[Path] = []
    prev_ok: Path | None = fallback_still if fallback_still.is_file() else None

    for i in range(n):
        idx = i + 1
        dest = m5 / f"sleep_tail_theme_{idx:03d}.jpg"
        scene_hint = (
            f"Thematic calm still for background viewing while listening to ambient music. Topic: {topic}. "
            f"Visual {idx} of {n}: distinct composition, same soft semi-cartoon documentary mood. "
            "No text, no letters, no subtitles."
        )
        try:
            prompt = await _build_image_prompt_async(
                scene_hint,
                style,
                output_format=_mode5_output_format(),
                extra_suffix="Gentle atmosphere for long rest viewing; avoid harsh contrast.",
                visual_policy="facts50",
            )
            prompt = _sanitize_mode5_image_prompt(prompt)
            await _generate_one_image(prompt, dest, aspect_ratio=_mode5_image_aspect_ratio())
        except Exception as e:
            logger.warning(f"[Mode5] sleep tail theme image {idx} failed: {e}")
        if dest.is_file():
            out.append(dest)
            prev_ok = dest
        elif prev_ok is not None:
            shutil.copy2(prev_ok, dest)
            out.append(dest)
        else:
            if not fallback_still.is_file():
                raise FileNotFoundError("sleep tail fallback still missing")
            shutil.copy2(fallback_still, dest)
            out.append(dest)
            prev_ok = dest
    return out


def _append_mode5_sleep_tail(session_id: str, plan: dict[str, Any], final_path: Path) -> Path:
    """
    For facts50 and book_night: append long sleep-oriented thematic music tail after spoken audio
    (same env MODE5_FACTS50_SLEEP_TAIL_SEC — «хвост» как у 77 фактов по длительности файла).
    Fail-soft: on any error returns original final_path unchanged.
    """
    sm5 = (plan.get("sub_mode") or "").strip().lower()
    if sm5 not in ("facts50", "book_night", "unwritten_chapter"):
        return final_path
    tail_sec = max(0, int(getattr(settings, "mode5_facts50_sleep_tail_sec", 0) or 0))
    if tail_sec <= 0:
        return final_path
    if not final_path.is_file():
        return final_path

    try:
        session_root = _session_dir(session_id)
        ff = resolve_ffmpeg_executable()
        if not ff:
            logger.warning("[Mode5] Sleep tail skipped: ffmpeg not found")
            return final_path

        topic = (
            str(plan.get("facts_topic") or "").strip()
            or str(plan.get("header_title") or "").strip()
            or str(plan.get("script_text") or "").strip()[:240]
            or "sleep ambient"
        )
        base_music_sec = max(60, min(300, int(getattr(settings, "ai_music_base_duration_sec", 180) or 180)))
        music_path = generate_background_music(
            topic=topic,
            duration=base_music_sec,
            base_duration=base_music_sec,
            cache_dir=settings.music_cache_dir,
        )
        if music_path is None or not Path(music_path).is_file():
            logger.warning("[Mode5] Sleep tail skipped: music generation unavailable")
            return final_path

        still_path: Path | None = None
        for ch in reversed(list(plan.get("chunks") or [])):
            for seg in reversed(list(ch.get("segments") or [])):
                rel = str(seg.get("image") or "").strip()
                if not rel:
                    continue
                p = session_root / rel
                if p.is_file():
                    still_path = p
                    break
            if still_path is not None:
                break
        if still_path is None:
            still_path = session_root / "mode5_sleep_tail_still.jpg"
            # Fallback: grab near-last frame from final video.
            subprocess.run(
                [
                    ff,
                    "-y",
                    "-sseof",
                    "-1",
                    "-i",
                    str(final_path),
                    "-frames:v",
                    "1",
                    str(still_path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        target_w, target_h = settings.mode5_video_resolution
        fps = max(24, min(60, int(settings.video_fps or 24)))
        volume = max(0.0, min(1.0, float(getattr(settings, "mode5_facts50_sleep_tail_volume", 0.34) or 0.34)))
        tail_path = session_root / "mode5_sleep_tail.mp4"
        fade_out_start = max(0.0, float(tail_sec) - 6.0)
        vf = (
            f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease:flags=lanczos,"
            f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black,format=yuv420p"
        )
        af = (
            f"volume={volume},"
            "afade=t=in:st=0:d=2.5,"
            f"afade=t=out:st={fade_out_start:.2f}:d=6"
        )

        interval = max(60, int(getattr(settings, "mode5_facts50_sleep_tail_image_interval_sec", 300) or 300))
        segment_durs: list[float] = []
        rem = float(tail_sec)
        while rem > 0:
            segment_durs.append(min(float(interval), rem))
            rem -= segment_durs[-1]
        n_seg = len(segment_durs)

        def _mux_still_tail(still: Path) -> None:
            subprocess.run(
                [
                    ff,
                    "-y",
                    "-loop",
                    "1",
                    "-i",
                    str(still),
                    "-stream_loop",
                    "-1",
                    "-i",
                    str(music_path),
                    "-t",
                    str(tail_sec),
                    "-vf",
                    vf,
                    "-r",
                    str(fps),
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "160k",
                    "-af",
                    af,
                    "-shortest",
                    str(tail_path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        try:
            theme_paths = asyncio.run(
                _generate_mode5_sleep_tail_theme_images(
                    session_id, plan, topic, n_seg, still_path
                )
            )
            if len(theme_paths) != n_seg:
                raise RuntimeError("sleep tail theme image count mismatch")
        except Exception as e:
            logger.warning(f"[Mode5] Sleep tail thematic images failed, using single still: {e}")
            _mux_still_tail(still_path)
        else:
            seg_mp4s: list[Path] = []
            try:
                for i, dur in enumerate(segment_durs):
                    seg_out = session_root / f"mode5_sleep_tail_seg_{i:03d}.mp4"
                    subprocess.run(
                        [
                            ff,
                            "-y",
                            "-loop",
                            "1",
                            "-i",
                            str(theme_paths[i]),
                            "-t",
                            str(dur),
                            "-vf",
                            vf,
                            "-r",
                            str(fps),
                            "-c:v",
                            "libx264",
                            "-preset",
                            "medium",
                            "-pix_fmt",
                            "yuv420p",
                            "-an",
                            str(seg_out),
                        ],
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    seg_mp4s.append(seg_out)

                concat_list = session_root / "mode5_sleep_tail_concat.txt"
                concat_list.write_text(
                    "\n".join(f"file '{p.resolve()}'" for p in seg_mp4s) + "\n",
                    encoding="utf-8",
                )
                video_only = session_root / "mode5_sleep_tail_video_concat.mp4"
                subprocess.run(
                    [
                        ff,
                        "-y",
                        "-f",
                        "concat",
                        "-safe",
                        "0",
                        "-i",
                        str(concat_list),
                        "-c",
                        "copy",
                        str(video_only),
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                subprocess.run(
                    [
                        ff,
                        "-y",
                        "-i",
                        str(video_only),
                        "-stream_loop",
                        "-1",
                        "-i",
                        str(music_path),
                        "-t",
                        str(tail_sec),
                        "-map",
                        "0:v:0",
                        "-map",
                        "1:a:0",
                        "-c:v",
                        "copy",
                        "-c:a",
                        "aac",
                        "-b:a",
                        "160k",
                        "-af",
                        af,
                        str(tail_path),
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception as e:
                logger.warning(f"[Mode5] Sleep tail segment mux failed, using single still: {e}")
                _mux_still_tail(still_path)
            finally:
                for p in seg_mp4s:
                    try:
                        p.unlink(missing_ok=True)
                    except OSError:
                        pass
                for tmp in (
                    session_root / "mode5_sleep_tail_concat.txt",
                    session_root / "mode5_sleep_tail_video_concat.mp4",
                ):
                    try:
                        tmp.unlink(missing_ok=True)
                    except OSError:
                        pass

        out = session_root / "video_mode5_with_sleep_tail.mp4"
        _ffmpeg_concat([final_path, tail_path], out)
        shutil.move(str(out), str(final_path))
        logger.success(f"[Mode5] Added sleep tail ({tail_sec}s) after facts")
        return final_path
    except Exception as e:
        logger.warning(f"[Mode5] Sleep tail skipped due to error: {e}")
        return final_path


async def _synthesize_chunk(
    session_id: str,
    chunk_index: int,
    text: str,
    *,
    language: str,
) -> tuple[Path, Path, float, list[tuple[float, float]] | None, list[str] | None, str]:
    session_root = _session_dir(session_id)
    m5 = _mode5_dir(session_id)
    mp3_path = m5 / f"chunk_{chunk_index:03d}.mp3"
    wav_path = m5 / f"chunk_{chunk_index:03d}.wav"
    # VoiceAPI: минимум ~500 символов; Whisper и сегменты — тот же текст, что ушёл в TTS (без двойной подготовки).
    tts_plain = plain_text_for_voiceapi_tts(text, language=language, pad_salt=chunk_index)
    await synthesize(text, mp3_path, language=language, voiceapi_plain=tts_plain)
    await asyncio.to_thread(_convert_audio_to_wav, mp3_path, wav_path)
    dur = await asyncio.to_thread(_wav_duration_sec, wav_path)
    wts, words = await asyncio.to_thread(
        get_word_timestamps_from_audio_path,
        wav_path,
        script=tts_plain,
        language=language,
        vad_filter=False,
    )
    return mp3_path, wav_path, dur, wts, words, tts_plain


def _rebuild_chunk_segment_paths(session_id: str, chunk: dict[str, Any]) -> None:
    session_root = _session_dir(session_id)
    m5 = _mode5_dir(session_id)
    for seg in chunk.get("segments") or []:
        si = int(seg["s"])
        img_path = m5 / f"img_c{chunk['index']}_s{si}.jpg"
        aud_path = m5 / f"seg_c{chunk['index']}_s{si}.wav"
        seg["image"] = _rel_session(session_root, img_path)
        seg["audio"] = _rel_session(session_root, aud_path)
        if not _is_global_intro_segment(int(chunk["index"]), si):
            seg.pop("video", None)
        seg.pop("asset_type", None)


async def _revoice_chunk(
    session_id: str,
    plan: dict[str, Any],
    chunk_index: int,
    text: str,
    *,
    language: str,
    segment_seconds: int,
    max_parallel_images: int,
) -> dict[str, Any]:
    session_root = _session_dir(session_id)
    chunk = plan["chunks"][chunk_index]
    clean_text = re.sub(r"\s+", " ", (text or "").strip())
    min_len = (
        _MIN_CHUNK_TEXT_LEN_FACTS50 if (plan.get("sub_mode") or "").strip().lower() == "facts50" else _MIN_CHUNK_TEXT_LEN
    )
    if len(clean_text) < min_len:
        raise ValueError("Mode 5: текст чанка слишком короткий для переозвучки")
    if (plan.get("sub_mode") or "").strip().lower() == "facts50":
        chunks = plan.get("chunks") or []
        if not bool(chunk.get("is_intro")) and not bool(chunk.get("is_outro")):
            fact_idx = _facts50_fact_index_for_chunk(chunks, chunk_index)
            clean_text = _ensure_fact_spoken_prefix(fact_idx, clean_text, language)
    mp3_path, wav_path, dur, wts, words, tts_plain = await _synthesize_chunk(
        session_id,
        chunk_index,
        clean_text,
        language=language,
    )
    chunk["text"] = tts_plain
    chunk["chunk_audio"] = _rel_session(session_root, mp3_path)
    chunk["chunk_audio_wav"] = _rel_session(session_root, wav_path)
    chunk["duration_sec"] = dur
    if (plan.get("sub_mode") or "").strip().lower() == "facts50":
        chunks = plan.get("chunks") or []
        if bool(chunk.get("is_intro")) or bool(chunk.get("is_outro")):
            overlay_title = ""
        else:
            fact_idx = _facts50_fact_index_for_chunk(chunks, chunk_index)
            overlay_title = _fact_overlay_title(fact_idx)
        chunk["segments"] = _segments_for_facts50_chunk(
            str(chunk.get("fact_hint") or ""),
            tts_plain,
            dur,
            overlay_title=overlay_title,
        )
    else:
        chunk["segments"] = _segments_for_chunk(tts_plain, dur, segment_seconds, wts, words)
    _rebuild_chunk_segment_paths(session_id, chunk)
    locked_style = _mode5_locked_style(plan)
    await _generate_chunk_images(
        session_id,
        chunk,
        locked_style,
        max_parallel_images=max_parallel_images,
        refresh_all=True,
        visual_policy=_mode5_visual_policy(str(plan.get("sub_mode"))),
        visual_bible=plan.get("visual_bible") if isinstance(plan.get("visual_bible"), dict) else None,
        block_prompt_prefix=_chunk_block_prompt_prefix(chunk),
    )
    _render_chunk_audio_slices(session_id, chunk)
    await _ensure_mode5_looped_intro_video(
        session_id,
        plan,
        force=chunk_index == 0,
    )
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: _build_chunk_preview_sync(session_id, chunk_index, plan))
    _save_mode5_plan(session_id, plan)
    return {
        "ok": True,
        "chunk_index": chunk_index,
        "preview_relpath": chunk["preview_relpath"],
        "chunk_meta": _chunk_meta_public(chunk),
    }


async def run_mode5_pipeline(
    script_text: str,
    *,
    session_id: str,
    language: str = "ru",
    skip_final_assembly: bool = True,
    chunk_seconds: int = CHUNK_SEC_DEFAULT,
    segment_seconds: int = SEG_SEC_DEFAULT,
    max_parallel_images: int | None = None,
    video_header_title: str | None = None,
    bible_mode: bool = False,
    sub_mode: str = "manual",
    control: dict | None = None,
) -> dict[str, Any]:
    from pipeline_control import checkpoint

    require_ffmpeg_or_raise()
    if not (getattr(settings, "voiceapi_api_key", "") or "").strip():
        raise ValueError("Mode 5: пустой VOICEAPI_API_KEY в .env")
    if not (getattr(settings, "voiceapi_template_uuid", "") or "").strip():
        raise ValueError("Mode 5: пустой VOICEAPI_TEMPLATE_UUID в .env (голос настраивается только через шаблон)")

    sm = (sub_mode or "manual").strip().lower()
    if sm not in ("manual", "bible", "facts50", "outline", "book_night", "unwritten_chapter"):
        sm = "manual"
    if sm == "manual" and bible_mode:
        sm = "bible"

    topic_input = re.sub(r"\s+", " ", (script_text or "").strip())
    facts_outline: list[str] | None = None
    outline_doc: dict[str, Any] | None = None
    chunk_texts: list[str] = []

    if sm == "facts50":
        if len(topic_input) < 8:
            raise ValueError("Mode 5 (77 фактов): введите тему или заголовок (например: 77 фактов о Франции)")
        language = detect_mode5_language(
            f"{topic_input} {(video_header_title or '').strip()}",
            language,
        )
        from modes.mode5.facts50_generator import generate_facts50_script

        facts_outline, narrations = await generate_facts50_script(topic_input, language, control=control)
        intro_text = _facts50_intro_text(topic_input, language)
        outro_text = _facts50_outro_text(topic_input, language)
        chunk_texts = [intro_text] + list(narrations) + [outro_text]
        script_clean = "\n\n".join(narrations)
        logger.info(f"[Mode5] facts50: {len(chunk_texts)} narration chunk(s) including intro/outro")
    elif sm == "outline":
        from modes.mode5.outline_generator import MIN_OUTLINE_BRIEF_CHARS

        if len(topic_input) < MIN_OUTLINE_BRIEF_CHARS:
            raise ValueError(
                f"Mode 5 (план из описания): введите краткое описание сюжета (от {MIN_OUTLINE_BRIEF_CHARS} символов): "
                "место, настроение, герой или ситуация, куда может завести история — модель развернёт план и текст от этого."
            )
        language = detect_mode5_language(
            f"{topic_input} {(video_header_title or '').strip()}",
            language,
        )
        from modes.mode5.outline_generator import generate_outline_longform_script

        outline_doc, chunk_texts, script_clean = await generate_outline_longform_script(
            topic_input, language, control=control
        )
        logger.info(
            f"[Mode5] outline: {len(outline_doc.get('chapters') or [])} chapter(s), "
            f"{len(chunk_texts)} narration chunk(s) from subchapters"
        )
    elif sm == "book_night":
        if len(topic_input) < 8:
            raise ValueError(
                "Mode 5 (книга на ночь): введите название книги (от 8 символов), например «7 навыков высокоэффективных людей, Стивен Кови»"
            )
        language = detect_mode5_language(
            f"{topic_input} {(video_header_title or '').strip()}",
            language,
        )
        from modes.mode5.book_night_generator import generate_book_night_script

        outline_doc, chunk_texts, script_clean = await generate_book_night_script(
            topic_input, language, control=control
        )
        logger.info(
            f"[Mode5] book_night: {len(outline_doc.get('chapters') or [])} book chapter(s), "
            f"{len(chunk_texts)} subsection narration(s)"
        )
    elif sm == "unwritten_chapter":
        if len(topic_input) < 8:
            raise ValueError(
                "Mode 5 (The Unwritten Chapter): укажите тему расследования (от 8 символов)."
            )
        language = detect_mode5_language(
            f"{topic_input} {(video_header_title or '').strip()}",
            language,
        )
        from modes.mode5.unwritten_chapter_generator import generate_unwritten_chapter_script

        outline_doc, chunk_texts, script_clean = await generate_unwritten_chapter_script(
            topic_input, language, control=control
        )
        logger.info(
            f"[Mode5] unwritten_chapter: {len(outline_doc.get('chapters') or [])} block(s), "
            f"{len(chunk_texts)} narration chunk(s)"
        )
    else:
        script_clean = topic_input
        if len(script_clean) < _MIN_CHUNK_TEXT_LEN:
            raise ValueError("Mode 5: вставьте полноценный текст для озвучки")
        language = detect_mode5_language(script_clean, language)

    chunk_sec = max(120, min(900, int(chunk_seconds or CHUNK_SEC_DEFAULT)))
    seg_sec = max(10, min(90, int(segment_seconds or SEG_SEC_DEFAULT)))
    # book_night / unwritten_chapter: 15s windows explode image count and can run for many hours.
    # Keep a practical floor unless user explicitly chooses larger values.
    if sm in ("book_night", "unwritten_chapter") and seg_sec < 30:
        logger.info(
            f"[Mode5] {sm}: segment_seconds={seg_sec} too small, using 30 to reduce image workload"
        )
        seg_sec = 30
    header_stripped = (video_header_title or "").strip() or None

    session_root = _session_dir(session_id)
    session_root.mkdir(parents=True, exist_ok=True)
    _mode5_dir(session_id)
    mpi = _clamp_mode5_parallel_images(max_parallel_images)

    logger.info(f"=== Mode 5 Pipeline | sub_mode={sm} | session={session_id} ===")
    await checkpoint(control)

    if sm not in ("facts50", "outline", "book_night", "unwritten_chapter"):
        chunk_texts = _estimate_chunks_from_script(script_clean, language=language, chunk_seconds=chunk_sec)
        if not chunk_texts:
            raise ValueError(
                "Mode 5 (ручной текст): не удалось разбить сценарий на чанки для озвучки. "
                "Убедитесь, что в тексте есть обычные слова (не один набор символов без пробелов), "
                "или добавьте абзацы — и попробуйте снова."
            )
        logger.info(f"[Mode5] Planned {len(chunk_texts)} chunk(s) from manual script")

    visual_bible: dict[str, Any] | None = None
    if sm == "facts50":
        style_suffix = await derive_facts50_unified_style_suffix(
            topic_input,
            list(facts_outline or []),
            script_clean,
            output_format=_mode5_output_format(),
            control=control,
        )
        visual_bible = await derive_mode5_visual_bible(
            narration_sample=(script_clean[:12000] if script_clean else topic_input),
            sub_mode=sm,
            topic_or_title=topic_input,
            locked_series_style=style_suffix,
        )
    else:
        style_sample = script_clean[:12000] if len(script_clean) > 12000 else script_clean
        topic_line = (topic_input or (video_header_title or "") or "").strip()
        visual_bible = await derive_mode5_visual_bible(
            narration_sample=style_sample,
            sub_mode=sm,
            topic_or_title=topic_line,
            locked_series_style=None,
        )
        if visual_bible and (str(visual_bible.get("series_style") or "").strip()):
            style_suffix = str(visual_bible["series_style"]).strip()
            if _mode5_output_format() == "horizontal":
                style_suffix += mode5_art_direction_tail_horizontal()
            else:
                style_suffix += " Maintain consistent vertical full-frame composition across the series."
        else:
            style_suffix = await _derive_style_suffix(
                style_sample,
                output_format=_mode5_output_format(),
                visual_policy=_mode5_visual_policy(sm),
            )
            if not visual_bible or not str(visual_bible.get("frame_rules") or "").strip():
                visual_bible = None
        if sm == "bible":
            style_suffix = (
                f"{style_suffix}. "
                "Prioritize Biblical context for visual prompts: scripture-grounded settings, "
                "ancient Judea and Near East environments, modest historically plausible clothing, "
                "sacred atmosphere, symbolic but respectful Christian iconography, and avoid modern artifacts."
            )
    style_suffix = re.sub(r"\s+", " ", (style_suffix or "").strip())
    style_lock = style_suffix
    await checkpoint(control)

    outline_labels: list[tuple[str, str]] = []
    unwritten_anchor_map: dict[int, dict[str, str]] = {}
    if sm in ("outline", "book_night", "unwritten_chapter") and isinstance(outline_doc, dict):
        from modes.mode5.outline_generator import get_chunk_outline_labels

        outline_labels = get_chunk_outline_labels(outline_doc)
        if sm == "unwritten_chapter":
            unwritten_anchor_map = _unwritten_chunk_anchor_by_index(outline_doc)

    # Persist stub plan before long parallel TTS so /review-state does not 404 while audio generates.
    if sm == "facts50" and chunk_texts:
        stub_chunks: list[dict[str, Any]] = []
        for i, ct in enumerate(chunk_texts):
            is_intro = i == 0
            is_outro = i == (len(chunk_texts) - 1)
            fh = ct if (is_intro or is_outro) else ""
            if (not is_intro) and (not is_outro) and isinstance(facts_outline, list) and (i - 1) < len(facts_outline):
                fh = str(facts_outline[i - 1] or "").strip()
            preview_path = session_root / f"mode5_preview_{i:03d}.mp4"
            stub_chunks.append(
                {
                    "index": i,
                    "text": ct,
                    "fact_hint": fh or None,
                    "is_intro": is_intro,
                    "is_outro": is_outro,
                    "preview_relpath": _rel_session(session_root, preview_path),
                    "preview_ready": False,
                    "segments": [],
                }
            )
        stub_plan: dict[str, Any] = {
            "version": 1,
            "session_id": session_id,
            "script_text": script_clean,
            "language": language,
            "show_subtitles": False,
            "chunk_seconds": chunk_sec,
            "segment_seconds": seg_sec,
            "max_parallel_images": mpi,
            "header_title": header_stripped,
            "bible_mode": False,
            "sub_mode": sm,
            "facts_topic": topic_input,
            "facts_outline": facts_outline,
            "style_suffix": style_suffix,
            "style_lock": style_lock,
            "visual_bible": visual_bible,
            "chunks": stub_chunks,
        }
        _save_mode5_plan(session_id, stub_plan, checkpoint=MODE5_CKPT_STUB)
    elif chunk_texts and sm != "facts50":
        stub_chunks_lf: list[dict[str, Any]] = []
        for i, ct in enumerate(chunk_texts):
            preview_path = session_root / f"mode5_preview_{i:03d}.mp4"
            row: dict[str, Any] = {
                "index": i,
                "text": ct,
                "fact_hint": None,
                "preview_relpath": _rel_session(session_root, preview_path),
                "preview_ready": False,
                "segments": [],
            }
            if sm in ("outline", "book_night", "unwritten_chapter") and i < len(outline_labels):
                row["chapter_title"] = outline_labels[i][0]
                row["subchapter_title"] = outline_labels[i][1]
            if sm == "unwritten_chapter":
                meta = unwritten_anchor_map.get(i) or {}
                ap = str(meta.get("prompt_prefix") or "").strip()
                if ap:
                    row["block_prompt_prefix"] = ap
                for key in ("visual_anchor", "evidence_anchor", "human_stakes"):
                    val = str(meta.get(key) or "").strip()
                    if val:
                        row[key] = val
            stub_chunks_lf.append(row)
        stub_plan_lf: dict[str, Any] = {
            "version": 1,
            "session_id": session_id,
            "script_text": script_clean,
            "language": language,
            "show_subtitles": False,
            "chunk_seconds": chunk_sec,
            "segment_seconds": seg_sec,
            "max_parallel_images": mpi,
            "header_title": header_stripped,
            "bible_mode": sm == "bible",
            "sub_mode": sm,
            "facts_topic": (
                topic_input.strip() if sm in ("book_night", "unwritten_chapter") and topic_input else None
            ),
            "facts_outline": None,
            "outline_structure": outline_doc if sm in ("outline", "book_night", "unwritten_chapter") else None,
            "style_suffix": style_suffix,
            "style_lock": style_lock,
            "visual_bible": visual_bible,
            "chunks": stub_chunks_lf,
        }
        _save_mode5_plan(session_id, stub_plan_lf, checkpoint=MODE5_CKPT_STUB)

    chunks_plan: list[dict[str, Any]] = []

    if sm == "facts50":
        # Параллельно до N фактов: TTS и затем картинки (типичный паттерн — asyncio + семафор под лимиты API).
        par = max(1, min(32, int(getattr(settings, "mode5_facts50_parallel", 10))))
        sem_tts = asyncio.Semaphore(par)

        async def _facts50_tts(ci: int, chunk_text: str):
            async with sem_tts:
                is_intro = ci == 0
                is_outro = ci == (len(chunk_texts) - 1)
                if is_intro or is_outro:
                    source_text = chunk_text
                else:
                    source_text = _ensure_fact_spoken_prefix(ci - 1, chunk_text, language)
                pack = await _synthesize_chunk(session_id, ci, source_text, language=language)
                return ci, pack

        logger.info(f"[Mode5 facts50] TTS parallel workers={par} ({len(chunk_texts)} facts)")
        tts_pairs = await asyncio.gather(
            *[_facts50_tts(ci, ct) for ci, ct in enumerate(chunk_texts)]
        )
        await checkpoint(control)
        tts_by_ci = {p[0]: p[1] for p in tts_pairs}

        for ci in range(len(chunk_texts)):
            mp3_path, wav_path, dur, wts, words, tts_plain = tts_by_ci[ci]
            is_intro = ci == 0
            is_outro = ci == (len(chunk_texts) - 1)
            fact_hint = tts_plain if (is_intro or is_outro) else ""
            if (not is_intro) and (not is_outro) and isinstance(facts_outline, list) and (ci - 1) < len(facts_outline):
                fact_hint = str(facts_outline[ci - 1] or "").strip()
            overlay_title = "" if (is_intro or is_outro) else _fact_overlay_title(ci - 1)
            segs = _segments_for_facts50_chunk(
                fact_hint,
                tts_plain,
                dur,
                overlay_title=overlay_title,
            )
            preview_path = session_root / f"mode5_preview_{ci:03d}.mp4"
            chunks_plan.append(
                {
                    "index": ci,
                    "text": tts_plain,
                    "fact_hint": fact_hint or None,
                    "is_intro": is_intro,
                    "is_outro": is_outro,
                    "chunk_audio": _rel_session(session_root, mp3_path),
                    "chunk_audio_wav": _rel_session(session_root, wav_path),
                    "duration_sec": dur,
                    "preview_relpath": _rel_session(session_root, preview_path),
                    "segments": segs,
                }
            )

        for ch in chunks_plan:
            _rebuild_chunk_segment_paths(session_id, ch)

        plan = load_mode5_plan(session_id)
        plan["chunks"] = chunks_plan
        if visual_bible is not None:
            plan["visual_bible"] = visual_bible
        _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_AFTER_TTS)

        sem_img = asyncio.Semaphore(par)

        async def _facts50_images(ch: dict[str, Any]) -> None:
            async with sem_img:
                idx = int(ch["index"])
                logger.info(
                    f"[Mode5 facts50] Images chunk {idx + 1}/{len(chunks_plan)} "
                    f"({len(ch.get('segments') or [])} window(s))"
                )
                await _generate_chunk_images(
                    session_id,
                    ch,
                    style_suffix,
                    max_parallel_images=mpi,
                    refresh_all=True,
                    visual_policy=_mode5_visual_policy(sm),
                    visual_bible=visual_bible,
                )
                _save_mode5_plan(
                    session_id, plan, checkpoint=MODE5_CKPT_AFTER_IMAGES, chunk_index=idx
                )

        await asyncio.gather(*[_facts50_images(ch) for ch in chunks_plan])

        for ch in chunks_plan:
            _render_chunk_audio_slices(session_id, ch)
        await _ensure_mode5_looped_intro_video(session_id, plan, force=False)
        _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_AFTER_SLICES)
        await checkpoint(control)

    else:
        # Long-form manual / bible / outline / book_night / unwritten_chapter:
        # keep prompt/segment quality tied to real TTS output, but overlap image generation
        # of ready chunks with TTS still running on the remaining chunks.
        par = max(1, min(16, int(getattr(settings, "mode5_facts50_parallel", 10) or 10)))
        sem_tts = asyncio.Semaphore(par)
        # _generate_chunk_images already fans out segment image requests inside one chunk,
        # so keep one chunk-level image lane to avoid explosive API concurrency.
        sem_img = asyncio.Semaphore(1)

        plan = load_mode5_plan(session_id)
        if visual_bible is not None:
            plan["visual_bible"] = visual_bible
        chunks_plan = plan.get("chunks") or []

        async def _longform_pipeline_chunk(ci: int, chunk_text: str) -> None:
            async with sem_tts:
                logger.info(f"[Mode5] Chunk {ci + 1}/{len(chunk_texts)}: TTS (voiceapi/template) synthesis")
                await checkpoint(control)
                mp3_path, wav_path, dur, wts, words, tts_plain = await _synthesize_chunk(
                    session_id,
                    ci,
                    chunk_text,
                    language=language,
                )

            segs = _segments_for_chunk(tts_plain, dur, seg_sec, wts, words)
            preview_path = session_root / f"mode5_preview_{ci:03d}.mp4"
            ch_entry: dict[str, Any] = {
                "index": ci,
                "text": tts_plain,
                "fact_hint": None,
                "chunk_audio": _rel_session(session_root, mp3_path),
                "chunk_audio_wav": _rel_session(session_root, wav_path),
                "duration_sec": dur,
                "preview_relpath": _rel_session(session_root, preview_path),
                "preview_ready": False,
                "segments": segs,
            }
            if sm in ("outline", "book_night", "unwritten_chapter") and ci < len(outline_labels):
                ch_entry["chapter_title"] = outline_labels[ci][0]
                ch_entry["subchapter_title"] = outline_labels[ci][1]
            if sm == "unwritten_chapter":
                meta = unwritten_anchor_map.get(ci) or {}
                ap = str(meta.get("prompt_prefix") or "").strip()
                if ap:
                    ch_entry["block_prompt_prefix"] = ap
                for key in ("visual_anchor", "evidence_anchor", "human_stakes"):
                    val = str(meta.get(key) or "").strip()
                    if val:
                        ch_entry[key] = val
            _rebuild_chunk_segment_paths(session_id, ch_entry)
            chunks_plan[ci] = ch_entry
            _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_AFTER_TTS, chunk_index=ci)

            async with sem_img:
                logger.info(
                    f"[Mode5] Chunk {ci + 1}/{len(chunk_texts)}: image generation for {len(ch_entry['segments'])} window(s)"
                )
                await _generate_chunk_images(
                    session_id,
                    ch_entry,
                    style_suffix,
                    max_parallel_images=mpi,
                    refresh_all=True,
                    visual_policy=_mode5_visual_policy(sm),
                    visual_bible=visual_bible,
                    block_prompt_prefix=str(ch_entry.get("block_prompt_prefix") or ""),
                )
                _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_AFTER_IMAGES, chunk_index=ci)
                await asyncio.to_thread(_render_chunk_audio_slices, session_id, ch_entry)
                _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_AFTER_SLICES, chunk_index=ci)
            await checkpoint(control)

        if sm == "unwritten_chapter":
            for ci, chunk_text in enumerate(chunk_texts):
                txt = re.sub(r"\s+", " ", (chunk_text or "").strip())
                segs = _segments_for_chunk_from_text(txt, seg_sec, language=language)
                preview_path = session_root / f"mode5_preview_{ci:03d}.mp4"
                ch_entry: dict[str, Any] = {
                    "index": ci,
                    "text": txt,
                    "fact_hint": None,
                    "preview_relpath": _rel_session(session_root, preview_path),
                    "preview_ready": False,
                    "segments": segs,
                }
                if ci < len(outline_labels):
                    ch_entry["chapter_title"] = outline_labels[ci][0]
                    ch_entry["subchapter_title"] = outline_labels[ci][1]
                meta = unwritten_anchor_map.get(ci) or {}
                ap = str(meta.get("prompt_prefix") or "").strip()
                if ap:
                    ch_entry["block_prompt_prefix"] = ap
                for key in ("visual_anchor", "evidence_anchor", "human_stakes"):
                    val = str(meta.get(key) or "").strip()
                    if val:
                        ch_entry[key] = val
                _rebuild_chunk_segment_paths(session_id, ch_entry)
                chunks_plan[ci] = ch_entry
                _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_STUB, chunk_index=ci)

            for ci, ch_entry in enumerate(chunks_plan):
                logger.info(
                    f"[Mode5] Chunk {ci + 1}/{len(chunk_texts)}: image generation for {len(ch_entry.get('segments') or [])} window(s)"
                )

                async def _on_seg_ready(_seg: dict[str, Any], idx: int = ci) -> None:
                    _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_AFTER_IMAGES, chunk_index=idx)

                await _generate_chunk_images(
                    session_id,
                    ch_entry,
                    style_suffix,
                    max_parallel_images=mpi,
                    refresh_all=True,
                    visual_policy=_mode5_visual_policy(sm),
                    visual_bible=visual_bible,
                    block_prompt_prefix=str(ch_entry.get("block_prompt_prefix") or ""),
                    on_segment_ready=_on_seg_ready,
                )
                _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_AFTER_IMAGES, chunk_index=ci)
                await checkpoint(control)

            async def _tts_after_images(ci: int, ch_entry: dict[str, Any]) -> None:
                async with sem_tts:
                    logger.info(f"[Mode5] Chunk {ci + 1}/{len(chunk_texts)}: TTS after images")
                    mp3_path, wav_path, dur, _wts, _words, tts_plain = await _synthesize_chunk(
                        session_id,
                        ci,
                        str(ch_entry.get("text") or ""),
                        language=language,
                    )
                ch_entry["text"] = tts_plain
                ch_entry["chunk_audio"] = _rel_session(session_root, mp3_path)
                ch_entry["chunk_audio_wav"] = _rel_session(session_root, wav_path)
                ch_entry["duration_sec"] = dur
                _retime_existing_segments_for_audio(ch_entry["segments"], duration_sec=dur)
                _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_AFTER_TTS, chunk_index=ci)
                await asyncio.to_thread(_render_chunk_audio_slices, session_id, ch_entry)
                _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_AFTER_SLICES, chunk_index=ci)
                await checkpoint(control)

            await asyncio.gather(*[_tts_after_images(ci, ch) for ci, ch in enumerate(chunks_plan)])
        else:
            await asyncio.gather(
                *[_longform_pipeline_chunk(ci, ct) for ci, ct in enumerate(chunk_texts)]
            )
        await checkpoint(control)
        await _ensure_mode5_looped_intro_video(session_id, plan, force=False)

    for ch in plan.get("chunks") or []:
        ch["preview_ready"] = False
    # Save early so the frontend can poll partial progress and already-ready previews.
    _save_mode5_plan(session_id, plan)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        functools.partial(_build_all_chunk_previews_parallel, session_id, plan),
    )
    _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_AFTER_PREVIEWS)

    if skip_final_assembly:
        _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_COMPLETED)
        logger.success(f"=== Mode 5 Pipeline REVIEW READY | session={session_id} ===")
        return _attach_mode5_resume_flags_from_plan(
            session_id, plan, _result_payload(session_id, plan, review_ready=True)
        )

    final_path = session_root / "video_mode5.mp4"
    await loop.run_in_executor(None, functools.partial(_rebuild_mode5_missing_previews, session_id, plan))
    preview_paths = [session_root / ch["preview_relpath"] for ch in (plan.get("chunks") or [])]
    await loop.run_in_executor(None, lambda: _ffmpeg_concat(preview_paths, final_path))
    final_path = await loop.run_in_executor(None, lambda: _append_mode5_sleep_tail(session_id, plan, final_path))
    rel_final = _rel_session(session_root, final_path)
    _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_COMPLETED)
    logger.success(f"=== Mode 5 Pipeline DONE | video={final_path} ===")
    return _attach_mode5_resume_flags_from_plan(
        session_id,
        plan,
        _result_payload(session_id, plan, review_ready=False, final_video=rel_final),
    )


async def resume_mode5_pipeline(
    session_id: str,
    *,
    skip_final_assembly: bool = True,
    control: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Продолжить mode5 после сбоя: на диске уже есть mode5_plan.json с озвучкой и (частично) картинками.
    Пропускает готовые файлы (refresh_all=False), дорисовывает недостающее, затем превью как в основном пайплайне.
    """
    from pipeline_control import checkpoint

    require_ffmpeg_or_raise()
    if not (getattr(settings, "voiceapi_api_key", "") or "").strip():
        raise ValueError("Mode 5: пустой VOICEAPI_API_KEY в .env")
    if not (getattr(settings, "voiceapi_template_uuid", "") or "").strip():
        raise ValueError("Mode 5: пустой VOICEAPI_TEMPLATE_UUID в .env (голос настраивается только через шаблон)")

    snap0 = mode5_resume_snapshot(session_id)
    if not snap0.get("can_resume"):
        reason = str(snap0.get("reason") or "unknown")
        raise ValueError(f"Продолжение недоступно: {reason}")

    plan = load_mode5_plan(session_id)
    sm = (plan.get("sub_mode") or "").strip().lower()
    session_root = _session_dir(session_id)
    chunks = list(plan.get("chunks") or [])
    style_suffix = _mode5_locked_style(plan)
    mpi = _clamp_mode5_parallel_images(plan.get("max_parallel_images"))
    language = str(plan.get("language") or "ru").strip() or "ru"
    stage = _checkpoint_stage(plan)

    if not (sm == "unwritten_chapter" and stage in (MODE5_CKPT_STUB, MODE5_CKPT_AFTER_IMAGES)):
        for ch in chunks:
            idx = int(ch.get("index") or 0)
            mp3_path, wav_path = _resolve_mode5_chunk_audio_paths(session_id, ch)
            if wav_path is None:
                raise FileNotFoundError(f"Нет WAV для части {idx}: chunk_{idx:03d}.wav")
            if mp3_path is None:
                raise FileNotFoundError(f"Нет MP3 для части {idx}: chunk_{idx:03d}.mp3")
            ch["chunk_audio"] = _rel_session(session_root, mp3_path)
            ch["chunk_audio_wav"] = _rel_session(session_root, wav_path)

    if sm != "facts50":
        from modes.mode5.outline_generator import get_chunk_outline_labels

        seg_sec = int(plan.get("segment_seconds") or SEG_SEC_DEFAULT)
        outline_doc = plan.get("outline_structure") if isinstance(plan.get("outline_structure"), dict) else None
        outline_labels = (
            get_chunk_outline_labels(outline_doc)
            if sm in ("outline", "book_night", "unwritten_chapter") and isinstance(outline_doc, dict)
            else []
        )
        unwritten_anchor_map = (
            _unwritten_chunk_anchor_by_index(outline_doc)
            if sm == "unwritten_chapter" and isinstance(outline_doc, dict)
            else {}
        )

        rebuilt_segments = False
        for ci, ch in enumerate(chunks):
            text = str(ch.get("text") or "").strip()
            if not text:
                raise ValueError(f"Mode 5 resume: пустой текст чанка {ci}")
            _mp3_path, wav_path = _resolve_mode5_chunk_audio_paths(session_id, ch)
            if wav_path is None and sm != "unwritten_chapter":
                raise FileNotFoundError(f"Mode 5 resume: нет WAV для чанка {ci}")
            dur = float(ch.get("duration_sec") or 0.0)
            if wav_path is not None and dur <= 0:
                dur = await asyncio.to_thread(_wav_duration_sec, wav_path)
            if wav_path is not None:
                ch["duration_sec"] = dur
            if not list(ch.get("segments") or []):
                if wav_path is not None:
                    wts, words = await asyncio.to_thread(
                        get_word_timestamps_from_audio_path,
                        wav_path,
                        script=text,
                        language=language,
                        vad_filter=False,
                    )
                    ch["segments"] = _segments_for_chunk(text, dur, seg_sec, wts, words)
                else:
                    ch["segments"] = _segments_for_chunk_from_text(text, seg_sec, language=language)
                rebuilt_segments = True
            if sm in ("outline", "book_night", "unwritten_chapter") and ci < len(outline_labels):
                ch["chapter_title"] = outline_labels[ci][0]
                ch["subchapter_title"] = outline_labels[ci][1]
            if sm == "unwritten_chapter":
                meta = unwritten_anchor_map.get(ci) or {}
                ap = str(meta.get("prompt_prefix") or "").strip()
                if ap:
                    ch["block_prompt_prefix"] = ap
                for key in ("visual_anchor", "evidence_anchor", "human_stakes"):
                    val = str(meta.get(key) or "").strip()
                    if val:
                        ch[key] = val
            _rebuild_chunk_segment_paths(session_id, ch)

        if rebuilt_segments or stage in (MODE5_CKPT_STUB, MODE5_CKPT_AFTER_IMAGES):
            _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_AFTER_TTS)

        for ci, ch in enumerate(chunks):
            if not _mode5_chunk_images_complete(session_root, ch):
                logger.info(
                    f"[Mode5 resume] Chunk {ci + 1}/{len(chunks)}: image generation for {len(ch.get('segments') or [])} window(s)"
                )
                await _generate_chunk_images(
                    session_id,
                    ch,
                    style_suffix,
                    max_parallel_images=mpi,
                    refresh_all=False,
                    visual_policy=_mode5_visual_policy(sm),
                    visual_bible=plan.get("visual_bible") if isinstance(plan.get("visual_bible"), dict) else None,
                    block_prompt_prefix=str(ch.get("block_prompt_prefix") or ""),
                    on_segment_ready=(
                        lambda _seg, cidx=ci: _save_mode5_plan(
                            session_id, plan, checkpoint=MODE5_CKPT_AFTER_IMAGES, chunk_index=cidx
                        )
                    ),
                )
                _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_AFTER_IMAGES, chunk_index=ci)
            if sm == "unwritten_chapter":
                _mp3_path, wav_path = _resolve_mode5_chunk_audio_paths(session_id, ch)
                if wav_path is None:
                    logger.info(f"[Mode5 resume] Chunk {ci + 1}/{len(chunks)}: TTS after images")
                    mp3_path_new, wav_path_new, dur, _wts, _words, tts_plain = await _synthesize_chunk(
                        session_id,
                        ci,
                        str(ch.get("text") or ""),
                        language=language,
                    )
                    ch["text"] = tts_plain
                    ch["chunk_audio"] = _rel_session(session_root, mp3_path_new)
                    ch["chunk_audio_wav"] = _rel_session(session_root, wav_path_new)
                    ch["duration_sec"] = dur
                    _retime_existing_segments_for_audio(ch["segments"], duration_sec=dur)
                    _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_AFTER_TTS, chunk_index=ci)
            if not _mode5_chunk_slices_complete(session_root, ch):
                _render_chunk_audio_slices(session_id, ch)
                _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_AFTER_SLICES, chunk_index=ci)
            await checkpoint(control)

        await _ensure_mode5_looped_intro_video(session_id, plan, force=False)
        _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_AFTER_SLICES)
        await checkpoint(control)

        for ch in plan.get("chunks") or []:
            ch["preview_ready"] = False
        _save_mode5_plan(session_id, plan)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            functools.partial(_build_all_chunk_previews_parallel, session_id, plan),
        )
        _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_AFTER_PREVIEWS)

        if skip_final_assembly:
            _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_COMPLETED)
            logger.success(f"=== Mode 5 RESUME REVIEW READY | session={session_id} ===")
            return _attach_mode5_resume_flags_from_plan(
                session_id, plan, _result_payload(session_id, plan, review_ready=True)
            )

        final_path = session_root / "video_mode5.mp4"
        await loop.run_in_executor(None, functools.partial(_rebuild_mode5_missing_previews, session_id, plan))
        preview_paths = [session_root / ch["preview_relpath"] for ch in (plan.get("chunks") or [])]
        await loop.run_in_executor(None, lambda: _ffmpeg_concat(preview_paths, final_path))
        final_path = await loop.run_in_executor(None, lambda: _append_mode5_sleep_tail(session_id, plan, final_path))
        rel_final = _rel_session(session_root, final_path)
        _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_COMPLETED)
        logger.success(f"=== Mode 5 RESUME DONE | video={final_path} ===")
        return _attach_mode5_resume_flags_from_plan(
            session_id,
            plan,
            _result_payload(session_id, plan, review_ready=False, final_video=rel_final),
        )

    par = max(1, min(32, int(getattr(settings, "mode5_facts50_parallel", 10))))
    sem_img = asyncio.Semaphore(par)

    if not all(_mode5_chunk_images_complete(session_root, ch) for ch in chunks):

        async def _resume_one_images(ch: dict[str, Any]) -> None:
            async with sem_img:
                idx = int(ch["index"])
                logger.info(
                    f"[Mode5 facts50 resume] Images chunk {idx + 1}/{len(chunks)} "
                    f"({len(ch.get('segments') or [])} window(s))"
                )
                await _generate_chunk_images(
                    session_id,
                    ch,
                    style_suffix,
                    max_parallel_images=mpi,
                    refresh_all=False,
                    visual_policy=_mode5_visual_policy(sm),
                    visual_bible=plan.get("visual_bible") if isinstance(plan.get("visual_bible"), dict) else None,
                    block_prompt_prefix=str(ch.get("block_prompt_prefix") or ""),
                )
                _save_mode5_plan(
                    session_id, plan, checkpoint=MODE5_CKPT_AFTER_IMAGES, chunk_index=idx
                )

        await asyncio.gather(*[_resume_one_images(ch) for ch in chunks])
        await checkpoint(control)

    for ch in chunks:
        if not _mode5_chunk_slices_complete(session_root, ch):
            _render_chunk_audio_slices(session_id, ch)
    await _ensure_mode5_looped_intro_video(session_id, plan, force=False)
    _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_AFTER_SLICES)
    await checkpoint(control)

    for ch in plan.get("chunks") or []:
        ch["preview_ready"] = False
    _save_mode5_plan(session_id, plan)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        functools.partial(_build_all_chunk_previews_parallel, session_id, plan),
    )
    _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_AFTER_PREVIEWS)

    if skip_final_assembly:
        _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_COMPLETED)
        logger.success(f"=== Mode 5 RESUME REVIEW READY | session={session_id} ===")
        return _attach_mode5_resume_flags_from_plan(
            session_id, plan, _result_payload(session_id, plan, review_ready=True)
        )

    final_path = session_root / "video_mode5.mp4"
    await loop.run_in_executor(None, functools.partial(_rebuild_mode5_missing_previews, session_id, plan))
    preview_paths = [session_root / ch["preview_relpath"] for ch in (plan.get("chunks") or [])]
    await loop.run_in_executor(None, lambda: _ffmpeg_concat(preview_paths, final_path))
    final_path = await loop.run_in_executor(None, lambda: _append_mode5_sleep_tail(session_id, plan, final_path))
    rel_final = _rel_session(session_root, final_path)
    _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_COMPLETED)
    logger.success(f"=== Mode 5 RESUME DONE | video={final_path} ===")
    return _attach_mode5_resume_flags_from_plan(
        session_id,
        plan,
        _result_payload(session_id, plan, review_ready=False, final_video=rel_final),
    )


async def regenerate_mode5_image(
    session_id: str,
    chunk_index: int,
    segment_index: int,
) -> dict[str, Any]:
    plan = load_mode5_plan(session_id)
    chunks = plan.get("chunks") or []
    if chunk_index < 0 or chunk_index >= len(chunks):
        raise ValueError("Invalid chunk_index")
    chunk = chunks[chunk_index]
    segs = chunk.get("segments") or []
    if segment_index < 0 or segment_index >= len(segs):
        raise ValueError("Invalid segment_index")
    seg = segs[segment_index]
    seg_prompt_text = seg.get("text", "")
    prompt_prefix = _chunk_block_prompt_prefix(chunk)
    if prompt_prefix:
        seg_prompt_text = f"{prompt_prefix}\n\nSegment meaning:\n{seg_prompt_text}"
    locked_style = _mode5_locked_style(plan)
    prompt = await _build_image_prompt_async(
        seg_prompt_text,
        locked_style,
        output_format=_mode5_output_format(),
        variation_hint=(
            f"Variation target for this regenerated frame: use a new camera angle and composition "
            f"compared to neighboring segments, while preserving the same global style."
        ),
        extra_suffix="Fresh alternative composition, same art direction.",
        visual_policy=_mode5_visual_policy(str(plan.get("sub_mode"))),
        visual_bible=plan.get("visual_bible") if isinstance(plan.get("visual_bible"), dict) else None,
    )
    prompt = _sanitize_mode5_image_prompt(prompt)
    seg["image_prompt"] = prompt
    session_root = _session_dir(session_id)
    img_path = session_root / seg["image"]
    await _generate_one_image(prompt, img_path, aspect_ratio=_mode5_image_aspect_ratio())
    if _is_global_intro_segment(chunk_index, segment_index):
        await _ensure_mode5_looped_intro_video(session_id, plan, force=True)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: _build_chunk_preview_sync(session_id, chunk_index, plan))
    _save_mode5_plan(session_id, plan)
    return {
        "ok": True,
        "chunk_index": chunk_index,
        "segment_index": segment_index,
        "preview_relpath": chunk["preview_relpath"],
    }


async def regenerate_mode5_chunk(
    session_id: str,
    chunk_index: int,
    text: str,
) -> dict[str, Any]:
    plan = load_mode5_plan(session_id)
    chunks = plan.get("chunks") or []
    if chunk_index < 0 or chunk_index >= len(chunks):
        raise ValueError("Invalid chunk_index")
    return await _revoice_chunk(
        session_id,
        plan,
        chunk_index,
        text,
        language=(plan.get("language") or "ru"),
        segment_seconds=int(plan.get("segment_seconds") or SEG_SEC_DEFAULT),
        max_parallel_images=_clamp_mode5_parallel_images(
            int(raw) if (raw := plan.get("max_parallel_images")) is not None else None
        ),
    )


def assemble_mode5_final_sync(session_id: str) -> dict[str, Any]:
    plan = load_mode5_plan(session_id)
    session_root = _session_dir(session_id)
    _rebuild_mode5_missing_previews(session_id, plan)
    previews = [session_root / ch["preview_relpath"] for ch in (plan.get("chunks") or [])]
    for p in previews:
        if not p.is_file():
            raise FileNotFoundError(
                f"Missing preview after rebuild attempt: {p}. "
                "Check that segment images and audio exist for this chunk (regenerate images or re-voice the chunk)."
            )
    final_path = session_root / "video_mode5.mp4"
    _ffmpeg_concat(previews, final_path)
    final_path = _append_mode5_sleep_tail(session_id, plan, final_path)
    rel = _rel_session(session_root, final_path)
    return _result_payload(session_id, plan, review_ready=False, final_video=rel)


def mode5_status_from_plan(session_id: str) -> dict[str, Any]:
    """
    Rebuild Mode 5 status payload from persisted plan when in-memory session is missing.
    Used by /api/pipeline/{sid}/status for History -> Progress navigation after restart.
    """
    plan = load_mode5_plan(session_id)
    session_root = _session_dir(session_id)
    final_path = session_root / "video_mode5.mp4"
    if final_path.is_file():
        rel = _rel_session(session_root, final_path)
        return _attach_mode5_resume_flags_from_plan(
            session_id, plan, _result_payload(session_id, plan, review_ready=False, final_video=rel)
        )
    return _attach_mode5_resume_flags_from_plan(
        session_id, plan, _result_payload(session_id, plan, review_ready=True)
    )


def mode5_review_snapshot(session_id: str) -> dict[str, Any]:
    """
    Return currently ready Mode 5 previews from persisted plan, even before pipeline completion.
    """
    try:
        plan = load_mode5_plan(session_id)
    except FileNotFoundError:
        return _mode5_review_pending_snapshot(session_id)
    session_root = _session_dir(session_id)
    chunks = list(plan.get("chunks") or [])
    ready_chunks: list[dict[str, Any]] = []
    for ch in chunks:
        rel = str(ch.get("preview_relpath") or "").strip()
        if not rel:
            continue
        p = session_root / rel
        if p.is_file() or bool(ch.get("preview_ready")):
            ready_chunks.append(ch)
    payload = _result_payload(session_id, {**plan, "chunks": ready_chunks}, review_ready=bool(ready_chunks))
    payload["mode5_total_chunks"] = len(chunks)
    payload["mode5_ready_chunks"] = len(ready_chunks)
    payload["mode5_partial"] = True
    snap = mode5_resume_snapshot_for_plan(session_id, plan)
    payload["mode5_can_resume"] = bool(snap.get("can_resume"))
    payload["mode5_checkpoint_stage"] = snap.get("stage")
    payload["mode5_resume_reason"] = snap.get("reason") or None
    prog = _mode5_progress_hint_payload(session_root, plan)
    payload.update(prog)
    return payload
