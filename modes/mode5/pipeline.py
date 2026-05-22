"""
Mode 5 Pipeline — ручной long-form текст -> TTS (VoiceAPI) по чанкам ->
окна ~30 с -> картинки в едином стиле -> (опционально) превью по чанкам -> review/regenerate ->
финальная склейка или сразу один финальный рендер без промежуточных mp4 по частям.
"""

from __future__ import annotations

import asyncio
import base64
import functools
import hashlib
import json
import os
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

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from agents.video_editor.music_gen import generate_background_music
from agents.video_editor.tts import (
    NONSPOKEN_LEN_FILLER_CHAR,
    plain_text_for_voiceapi_tts,
    synthesize,
    voiceapi_mode5_recommended_tts_parallel,
)
from agents.video_editor.whisper_timestamps import get_word_timestamps_from_audio_path
from config import settings
from modes.mode13.pipeline import (
    _ffmpeg_concat,
    _generate_one_image as _generate_one_image_mode13,
    _text_for_window,
    _windows_for_duration,
)
from modes.mode5.prompt_builder import (
    build_mode5_image_prompt,
    mode5_style_id_for_sub_mode,
    mode5_style_lock_for_sub_mode,
    normalize_mode5_sub_mode,
)
from modes.mode5.book_cover_fetch import try_fetch_openlibrary_cover
from modes.mode5.publishing_metadata import (
    generate_mode5_publishing_metadata,
    generate_mode5_thumbnail_prompt,
)
from modes.mode5.video_assembler import assemble_mode5_video, mode5_watermark_bottom_crop_ratio
from utils.ffmpeg_resolve import require_ffmpeg_or_raise, resolve_ffmpeg_executable
from utils.llm import make_llm
from utils.wav_pcm import slice_wav_time_range

MODE5_PLAN = "mode5_plan.json"

# Жёсткий потолок параллельных image-gen для MODE5 (см. лимиты провайдера).
MODE5_PARALLEL_IMAGES_HARD_MAX = 64

MODE5_CKPT_STUB = "stub"
MODE5_CKPT_AFTER_TTS = "after_tts"
MODE5_CKPT_AFTER_IMAGES = "after_images"
MODE5_CKPT_AFTER_SLICES = "after_slices"
MODE5_CKPT_AFTER_PREVIEWS = "after_previews"
MODE5_CKPT_COMPLETED = "completed"
_MODE5_STAGE_ORDER = [
    MODE5_CKPT_STUB,
    MODE5_CKPT_AFTER_TTS,
    MODE5_CKPT_AFTER_IMAGES,
    MODE5_CKPT_AFTER_SLICES,
    MODE5_CKPT_AFTER_PREVIEWS,
    MODE5_CKPT_COMPLETED,
]
_MODE5_STAGE_INDEX = {name: idx for idx, name in enumerate(_MODE5_STAGE_ORDER)}

_mode5_plan_io_locks: dict[str, threading.Lock] = {}
_mode5_plan_io_locks_guard = threading.Lock()


def _mode5_plan_io_lock(session_id: str) -> threading.Lock:
    with _mode5_plan_io_locks_guard:
        if session_id not in _mode5_plan_io_locks:
            _mode5_plan_io_locks[session_id] = threading.Lock()
        return _mode5_plan_io_locks[session_id]


def _ensure_mode5_live_defaults(plan: dict[str, Any]) -> None:
    if not isinstance(plan.get("live_queue"), list):
        plan["live_queue"] = []
    if not isinstance(plan.get("pending_rebuilds"), list):
        plan["pending_rebuilds"] = []
    if not isinstance(plan.get("live_events"), list):
        plan["live_events"] = []
    if not str(plan.get("live_policy") or "").strip():
        plan["live_policy"] = "hybrid"
    plan["pipeline_paused"] = bool(plan.get("pipeline_paused"))
    for ch in list(plan.get("chunks") or []):
        if not isinstance(ch, dict):
            continue
        ch.setdefault("status", "pending")
        ch.setdefault("version", 1)
        ch.setdefault("audio_status", "pending")
        ch.setdefault("images_status", "pending")
        ch.setdefault("preview_status", "pending")
        ch.setdefault("locked", False)
        for seg in list(ch.get("segments") or []):
            if not isinstance(seg, dict):
                continue
            seg.setdefault("image_version", 1)
            seg.setdefault("audio_version", 1)
            seg.setdefault("last_action", "auto")
            seg.setdefault("dirty_reason", "")


def _mode5_push_live_event(plan: dict[str, Any], event_type: str, **payload: Any) -> None:
    _ensure_mode5_live_defaults(plan)
    events = plan["live_events"]
    events.append(
        {
            "event": event_type,
            "at": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
    )
    if len(events) > 300:
        del events[:-300]


def _mode5_queue_action(
    plan: dict[str, Any], action: str, *, action_id: str | None = None, **payload: Any
) -> tuple[str, bool]:
    _ensure_mode5_live_defaults(plan)
    req_id = str(action_id or "").strip()
    if req_id:
        for row in list(plan["live_queue"]):
            if str(row.get("action_id") or "") == req_id:
                return req_id, True
    action_id_final = req_id or f"{int(time.time() * 1000)}_{random.randint(1000, 9999)}"
    plan["live_queue"].append(
        {
            "action_id": action_id_final,
            "action": action,
            "status": "applied",
            "payload": payload,
            "applied_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    if len(plan["live_queue"]) > 200:
        plan["live_queue"] = plan["live_queue"][-200:]
    return action_id_final, False


def _mode5_find_action(plan: dict[str, Any], action_id: str | None) -> dict[str, Any] | None:
    aid = str(action_id or "").strip()
    if not aid:
        return None
    for row in reversed(list(plan.get("live_queue") or [])):
        if str(row.get("action_id") or "") == aid:
            return row
    return None


def _mode5_assert_duplicate_matches(
    existing: dict[str, Any] | None,
    *,
    action: str,
    chunk_index: int | None = None,
    segment_index: int | None = None,
    preview_index: int | None = None,
) -> None:
    if existing is None:
        return
    existing_action = str(existing.get("action") or "").strip()
    payload = existing.get("payload") if isinstance(existing.get("payload"), dict) else {}
    if existing_action != action:
        raise ValueError("action_id already used for another action")
    if chunk_index is not None and int(payload.get("chunk_index", -1)) != int(chunk_index):
        raise ValueError("action_id already used for another chunk")
    if segment_index is not None and int(payload.get("segment_index", -1)) != int(segment_index):
        raise ValueError("action_id already used for another segment")
    if preview_index is not None and int(payload.get("preview_index", -1)) != int(preview_index):
        raise ValueError("action_id already used for another preview index")


def _update_mode5_plan_atomic(
    session_id: str,
    mutator: Callable[[dict[str, Any]], None],
    *,
    checkpoint: str | None = None,
    **checkpoint_extra: Any,
) -> dict[str, Any]:
    with _mode5_plan_io_lock(session_id):
        plan = load_mode5_plan(session_id)
        _ensure_mode5_live_defaults(plan)
        mutator(plan)
        if checkpoint is not None:
            chunk_scoped = checkpoint_extra.get("chunk_index") is not None
            _validate_mode5_stage_transition(plan, checkpoint, chunk_scoped=chunk_scoped)
            stage_for_write = _checkpoint_stage_for_write(
                plan, checkpoint, chunk_scoped=chunk_scoped
            )
            _record_mode5_stage_metric(plan, stage_for_write)
            _touch_mode5_checkpoint(plan, stage_for_write, **checkpoint_extra)
        root = _session_dir(session_id)
        root.mkdir(parents=True, exist_ok=True)
        dst = root / MODE5_PLAN
        tmp = root / f".{MODE5_PLAN}.tmp"
        body = json.dumps(plan, ensure_ascii=False, indent=2)
        tmp.write_text(body, encoding="utf-8")
        tmp.replace(dst)
        return plan


def set_mode5_pipeline_paused(session_id: str, paused: bool) -> dict[str, Any]:
    """Persist the user's global Mode 5 pause intent across backend restarts."""

    def _mutate(plan: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        plan["pipeline_paused"] = bool(paused)
        if paused:
            plan["pipeline_paused_at"] = now
        else:
            plan["pipeline_resumed_at"] = now

    return _update_mode5_plan_atomic(session_id, _mutate)


def write_mode5_early_pause_placeholder(
    session_id: str,
    request: dict[str, Any],
    *,
    topic_hint: str = "",
) -> dict[str, Any]:
    """
    Persist a minimal mode5_plan.json when the user pauses before the pipeline wrote its first checkpoint.
    After a server restart, POST /api/mode5/{id}/continue-generation can restart from these parameters.
    """
    if not isinstance(request, dict):
        raise ValueError("mode5_early_pause: request snapshot must be a dict")
    script = re.sub(
        r"\s+",
        " ",
        str(request.get("mode5_script_text") or request.get("topic") or topic_hint or "").strip(),
    )
    if len(script) < 1:
        raise ValueError("mode5_early_pause: need non-empty mode5_script_text or topic in request snapshot")
    sm = str(request.get("mode5_sub_mode") or "manual").strip().lower()
    if sm not in ("manual", "bible", "facts50", "outline", "book_night", "unwritten_chapter"):
        sm = "manual"
    chunk_sec = max(120, min(900, int(request.get("mode5_chunk_seconds") or CHUNK_SEC_DEFAULT)))
    seg_sec = max(10, min(90, int(request.get("mode5_segment_seconds") or SEG_SEC_DEFAULT)))
    if sm in ("book_night", "unwritten_chapter") and seg_sec < 30:
        seg_sec = 30
    test_run = bool(request.get("mode5_test_run", False))
    test_target = max(60, min(7200, int(request.get("mode5_test_duration_sec") or 300)))
    plan_test_meta: dict[str, Any] = (
        {"test_run": True, "test_target_sec": int(test_target)}
        if test_run
        else {"test_run": False, "test_target_sec": None}
    )
    header = (str(request.get("mode5_video_header_title") or "").strip() or None)
    mpi = _clamp_mode5_parallel_images(int(request.get("mode5_max_parallel_images") or 10))
    ib = _normalize_mode5_image_backend(
        request.get("mode5_image_backend")
        if request.get("mode5_image_backend") is not None
        else getattr(settings, "mode5_image_backend", "playwright")
    )
    language = str(request.get("mode5_language") or "ru").strip() or "ru"
    bible_mode = bool(request.get("mode5_bible_mode", False))
    facts_topic = script if sm in ("facts50", "book_night", "unwritten_chapter") else None
    now = datetime.now(timezone.utc).isoformat()
    plan: dict[str, Any] = {
        "version": 1,
        "session_id": session_id,
        "script_text": script,
        "source_input_text": script,
        "language": language,
        "show_subtitles": False,
        "chunk_seconds": chunk_sec,
        "segment_seconds": seg_sec,
        "max_parallel_images": mpi,
        "image_backend": ib,
        "header_title": header,
        "bible_mode": bible_mode,
        "sub_mode": sm,
        "facts_topic": facts_topic,
        "facts_outline": None,
        "outline_structure": None,
        "await_intro_confirmation": False,
        "intro_preview_video": None,
        "intro_preview_videos": [],
        "skip_final_assembly": bool(request.get("mode5_skip_final_assembly", True)),
        "skip_chunk_previews": bool(request.get("mode5_skip_chunk_previews", False)),
        "sequential_chunks": bool(request.get("mode5_sequential_chunks", False)),
        "chunks": [],
        "early_pause_before_chunks": True,
        "pipeline_paused": True,
        "pipeline_paused_at": now,
        **plan_test_meta,
    }
    _ensure_mode5_live_defaults(plan)
    _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_STUB)
    return plan


def apply_mode5_intro_preview_order(
    session_id: str,
    ordered_rels: list[str],
) -> dict[str, Any]:
    """
    Reorder intro confirmation preview clips (same files, new order).
    Order maps to timeline block indices: slot 0 → earliest block_sec slice, etc.
    """
    root = _session_dir(session_id)

    def _norm_rel(raw: str) -> str:
        s = str(raw or "").strip().replace("\\", "/")
        while s.startswith("/"):
            s = s[1:]
        if not s or ".." in s.split("/"):
            raise ValueError("Некорректный путь к превью")
        return s

    new_order = [_norm_rel(x) for x in ordered_rels if str(x or "").strip()]
    if not new_order:
        raise ValueError("Пустой список превью")

    def _mutate(plan: dict[str, Any]) -> None:
        if not bool(plan.get("await_intro_confirmation")):
            raise ValueError(
                "Изменение порядка доступно только до подтверждения стартовых роликов"
            )
        cur = [
            _norm_rel(x)
            for x in (plan.get("intro_preview_videos") or [])
            if str(x or "").strip()
        ]
        if not cur:
            raise ValueError("В плане нет превью для переупорядочивания")
        if len(new_order) != len(cur):
            raise ValueError("Длина списка должна совпадать с числом сгенерированных превью")
        if sorted(new_order) != sorted(cur):
            raise ValueError("Можно менять только порядок — набор файлов должен совпадать")
        for rel in new_order:
            if not (root / rel).is_file():
                raise ValueError(f"Файл превью не найден: {rel}")
        plan["intro_preview_videos"] = new_order
        plan["intro_preview_video"] = new_order[0]

    plan_out = _update_mode5_plan_atomic(session_id, _mutate)
    rels = list(plan_out.get("intro_preview_videos") or [])
    first = str(plan_out.get("intro_preview_video") or "").strip() or (rels[0] if rels else "")
    return {
        "ok": True,
        "intro_preview_videos": rels,
        "mode5_intro_preview_videos": rels,
        "intro_preview_video": first,
        "mode5_intro_preview_video": first or None,
    }


def _touch_mode5_checkpoint(plan: dict[str, Any], stage: str, **extra: Any) -> None:
    payload: dict[str, Any] = {
        "stage": stage,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "schema": 1,
    }
    if extra:
        payload["extra"] = {k: v for k, v in extra.items() if v is not None}
    plan["pipeline_checkpoint"] = payload


def _record_mode5_stage_metric(plan: dict[str, Any], stage: str) -> None:
    metrics = plan.get("mode5_metrics")
    if not isinstance(metrics, dict):
        metrics = {}
        plan["mode5_metrics"] = metrics
    now = time.time()
    prev_stage = metrics.get("last_stage")
    prev_ts = metrics.get("last_stage_ts")
    per_stage = metrics.get("stage_seconds")
    if not isinstance(per_stage, dict):
        per_stage = {}
        metrics["stage_seconds"] = per_stage
    if isinstance(prev_stage, str) and isinstance(prev_ts, (int, float)):
        delta = max(0.0, now - float(prev_ts))
        per_stage[prev_stage] = round(float(per_stage.get(prev_stage, 0.0)) + delta, 3)
    metrics["last_stage"] = stage
    metrics["last_stage_ts"] = now
    counts = metrics.get("stage_entries")
    if not isinstance(counts, dict):
        counts = {}
        metrics["stage_entries"] = counts
    counts[stage] = int(counts.get(stage, 0)) + 1


def _mode5_metrics(plan: dict[str, Any]) -> dict[str, Any]:
    metrics = plan.get("mode5_metrics")
    if not isinstance(metrics, dict):
        metrics = {}
        plan["mode5_metrics"] = metrics
    return metrics


def _record_mode5_operation_seconds(
    plan: dict[str, Any],
    name: str,
    started_at: float,
    *,
    count: int | None = None,
) -> None:
    elapsed = max(0.0, time.monotonic() - started_at)
    metrics = _mode5_metrics(plan)
    ops = metrics.get("operation_seconds")
    if not isinstance(ops, dict):
        ops = {}
        metrics["operation_seconds"] = ops
    ops[name] = round(float(ops.get(name, 0.0)) + elapsed, 3)
    runs = metrics.get("operation_runs")
    if not isinstance(runs, dict):
        runs = {}
        metrics["operation_runs"] = runs
    runs[name] = int(runs.get(name, 0)) + 1
    if count is not None:
        counts = metrics.get("operation_counts")
        if not isinstance(counts, dict):
            counts = {}
            metrics["operation_counts"] = counts
        counts[name] = int(counts.get(name, 0)) + int(count)
    logger.info("[Mode5 metrics] {} took {:.1f}s", name, elapsed)


def _validate_mode5_stage_transition(
    plan: dict[str, Any], next_stage: str, *, chunk_scoped: bool = False
) -> None:
    prev = _checkpoint_stage(plan)
    if next_stage not in _MODE5_STAGE_INDEX:
        raise ValueError(f"Mode5 checkpoint transition invalid: unknown next stage {next_stage}")
    if chunk_scoped:
        # Chunk-level checkpoints may arrive out of order due to parallel processing.
        return
    if prev is None:
        if next_stage != MODE5_CKPT_STUB:
            raise ValueError(f"Mode5 checkpoint transition invalid: None -> {next_stage}")
        return
    if prev not in _MODE5_STAGE_INDEX:
        raise ValueError(f"Mode5 checkpoint transition invalid: unknown previous stage {prev}")
    # Allow idempotent saves of the same stage and forward-only progression.
    if _MODE5_STAGE_INDEX[next_stage] < _MODE5_STAGE_INDEX[prev]:
        raise ValueError(f"Mode5 checkpoint regression is not allowed: {prev} -> {next_stage}")


def _checkpoint_stage_for_write(
    plan: dict[str, Any], next_stage: str, *, chunk_scoped: bool = False
) -> str:
    if not chunk_scoped:
        return next_stage
    prev = _checkpoint_stage(plan)
    if prev not in _MODE5_STAGE_INDEX:
        return next_stage
    # For chunk-scoped updates keep the furthest global stage reached so far.
    if _MODE5_STAGE_INDEX[next_stage] < _MODE5_STAGE_INDEX[prev]:
        return prev
    return next_stage


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


CHUNK_SEC_DEFAULT = 300
SEG_SEC_DEFAULT = 15
_MIN_CHUNK_TEXT_LEN = 80


def _truncate_mode5_chunk_texts_for_test(
    chunk_texts: list[str],
    *,
    language: str,
    target_sec: float,
) -> tuple[list[str], float]:
    """
    Keep a prefix of chunks until cumulative estimated speech reaches target_sec.
    Always returns at least one chunk when input is non-empty.
    """
    from modes.mode5.text_length import mode5_approx_speech_sec, mode5_trim_strings_by_estimated_speech

    if target_sec <= 0.0 or not chunk_texts:
        return list(chunk_texts), 0.0
    out = mode5_trim_strings_by_estimated_speech(chunk_texts, language=language, target_sec=target_sec)
    acc = sum(mode5_approx_speech_sec(ct, language) for ct in out)
    return out, acc


def _facts50_eval_is_outro(ci: int, n_chunks: int, orig_full: int | None) -> bool:
    """Last chunk is outro only when the full intro+…+outro chain was kept (test runs may cut before outro)."""
    if ci != n_chunks - 1:
        return False
    if orig_full is None:
        return True
    return n_chunks >= orig_full
_MIN_CHUNK_TEXT_LEN_FACTS50 = 40
# Block-loop / intro motion: модель должна отдать клип, который FFmpeg потом крутит `-stream_loop`;
# если первый и последний кадр расходятся — на стыке лупа будет «прыжок».
_MODE5_INTRO_ANIMATION_DESCRIPTION = (
    "Loop contract: first and last frame must match for seamless repeat. "
    "Start-state rule: frame 1 is already inside ongoing ambient motion (mid-cycle), not a static neutral pose. "
    "Camera locked: no pan/tilt/dolly/zoom/handheld shake. "
    "Animate only in-scene micro-motion with very low amplitude and ultra-smooth easing "
    "(foreground, midground, background + one subtle ambient pulse). "
    "Smoothness rule: no abrupt acceleration, no sharp direction flips, no jerky starts/stops; "
    "motion should feel like slow continuous breathing. "
    "Displacement rule: keep visible movement subtle (roughly micro/parallax range, not large travel across frame). "
    "Calmness rule: no talking behavior at all — no lip-sync, no mouth articulation, no speech-like head bobbing, "
    "no active dialogue gestures, no conversational staging. "
    "People, if present, remain serene and mostly still with only subtle breathing/posture micro-motion. "
    "Identity lock: keep exactly the same objects/actors/materials from start to end; no new elements and no disappearing elements. "
    "Keep geometry stable: no warped faces/hands, no bending architecture, no elastic distortions, no frame wobble. "
    "No cuts, no scene replacement, no morphing, no ghosting, no new or disappearing objects."
)
_MODE5_INTRO_SUBMODE_STYLE_NUANCE: dict[str, str] = {
    "manual": (
        "Sub-mode nuance: balanced whimsical-editorial look, neutral palette rhythm, practical readability first."
    ),
    "bible": (
        "Sub-mode nuance: reverent dreamy warmth with soft amber/chiaroscuro and period-authentic material textures."
    ),
    "facts50": (
        "Sub-mode nuance: whimsical editorial-documentary feel with crisp factual readability and concrete evidence props."
    ),
    "outline": (
        "Sub-mode nuance: restrained explanatory mood, tidy composition, and clear educational readability."
    ),
    "book_night": (
        "Sub-mode nuance: extra dreamy cozy-night atmosphere, gentle glow, intimate calm, and soft painterly depth."
    ),
    "unwritten_chapter": (
        "Sub-mode nuance: moody archival-dream tone with muted sepia/olive palette and investigative ambience."
    ),
}
_MODE5_BLOCK_LOOP_STILL_STYLE_OVERRIDE = (
    "BLOCK_LOOP_STILL_OVERRIDE: render as beautiful painterly-cinematic imagery with slight animation-style stylization "
    "(semi-cartoon feeling, expressive color and atmosphere), while preserving stable scene geometry and believable depth. "
    "Pack the frame with depth: foreground props, midground action, background architecture or nature so parallax motion has layers to work with — avoid a sparse empty box room. "
    "Keep the frame loop-friendly (clear focal plane, avoid chaotic motion-blur smear)."
)
# Bump when block-loop still/motion prompt contract changes so narr_fp cache invalidates.
_MODE5_BLOCK_LOOP_CACHE_SALT = "painterly_loop_v18_keyframe_start_end_still"
_MODE5_SUPPORTED_LANGS = {"ru", "en", "es", "fr", "de"}
def _mode5_output_format() -> str:
    fmt = str(getattr(settings, "mode5_video_format", "horizontal") or "horizontal").strip().lower()
    return "horizontal" if fmt == "horizontal" else "vertical"


def _mode5_image_aspect_ratio() -> str:
    return "16:9" if _mode5_output_format() == "horizontal" else "9:16"


def _mode5_parallel_images_cap() -> int:
    v = int(getattr(settings, "mode5_max_parallel_images", 10) or 10)
    return max(1, min(MODE5_PARALLEL_IMAGES_HARD_MAX, v))


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


def _mode5_longform_chunk_image_parallel() -> int:
    """
    Chunk-level image lanes for long-form Mode5.
    Segment-level fan-out still controlled by _generate_chunk_images.
    """
    return max(1, int(getattr(settings, "mode5_longform_chunk_image_parallel", 10) or 10))


def _mode5_facts50_image_parallel() -> int:
    return max(1, int(getattr(settings, "mode5_facts50_image_parallel", 10) or 10))


def _mode5_intro_pool_parallel() -> int:
    return max(1, int(getattr(settings, "mode5_intro_pool_parallel", 8) or 8))


def _mode5_block_loop_parallel() -> int:
    return max(1, int(getattr(settings, "mode5_block_loop_parallel", 10) or 10))


def _mode5_sleep_tail_image_parallel() -> int:
    return max(1, int(getattr(settings, "mode5_sleep_tail_image_parallel", 10) or 10))


def _mode5_tts_chunk_parallel_cap() -> int:
    """Сколько чанков Mode5 одновременно в фазе TTS (до согласования с VoiceAPI)."""
    return max(1, int(getattr(settings, "mode5_facts50_parallel", 32) or 32))


def _normalize_mode5_image_backend(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"api", "playwright", "auto"}:
        return raw
    if raw:
        logger.warning(f"[Mode5] Unknown mode5 image backend={raw!r}, fallback to 'playwright'")
    return "playwright"


async def _generate_one_image(
    prompt: str,
    dest: Path,
    *,
    aspect_ratio: str | None = None,
    image_backend: str | None = None,
    cancel_event: threading.Event | None = None,
) -> Path:
    """
    Mode5-specific router for image backend:
    - api        -> fastgen HTTP API
    - playwright -> browser automation
    - auto       -> legacy shared mode13 strategy
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    backend = _normalize_mode5_image_backend(
        image_backend if image_backend is not None else getattr(settings, "mode5_image_backend", "playwright")
    )

    attempts = max(
        1,
        min(
            3,
            int(getattr(settings, "mode5_image_text_guard_attempts", 2) or 2),
        ),
    )
    guard_enabled = bool(getattr(settings, "mode5_image_text_guard_enabled", True))

    async def _render_once(prompt_text: str) -> Path:
        if backend == "auto":
            return await _generate_one_image_mode13(prompt_text, dest, aspect_ratio=aspect_ratio)
        if backend == "api":
            from agents.content_generator import fastgen_http

            paths = await fastgen_http.generate_images_fastgen(
                [prompt_text],
                dest.parent,
                parallel=False,
                cancel_event=cancel_event,
                aspect_ratio=aspect_ratio,
            )
        else:  # backend == "playwright"
            from agents.content_generator import fastgen_playwright

            paths = await fastgen_playwright.generate_images_fastgen(
                [prompt_text],
                dest.parent,
                parallel=False,
                cancel_event=cancel_event,
                aspect_ratio=aspect_ratio,
            )

        if not paths:
            raise RuntimeError(f"[Mode5] Empty image result for backend={backend}")
        src = Path(paths[0])
        if not src.is_file():
            raise RuntimeError(f"[Mode5] Generated image not found for backend={backend}: {src}")
        if src.resolve() != dest.resolve():
            shutil.move(str(src), str(dest))
        return dest

    current_prompt = prompt
    for idx in range(attempts):
        out = await _render_once(current_prompt)
        if not guard_enabled:
            return out
        has_text = await _mode5_image_has_readable_text(out)
        if not has_text:
            return out
        if idx + 1 < attempts:
            logger.warning(
                f"[Mode5] Text detected in image ({dest.name}), retry {idx + 2}/{attempts}"
            )
            current_prompt = (
                f"{prompt}. Retry constraint #{idx + 2}: "
                "absolutely no visible letters, numbers, symbols, signage, logos, labels, subtitles, or watermark."
            )
            continue
        raise RuntimeError(f"[Mode5] Readable text detected in generated image after {attempts} attempt(s): {dest}")
    return dest


def _mode5_image_to_data_url(path: Path) -> str:
    ext = path.suffix.lower()
    mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
    raw = path.read_bytes()
    b64 = base64.standard_b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


async def _mode5_image_has_readable_text(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        model = getattr(settings, "openrouter_vision_model", "") or getattr(settings, "openrouter_model", "")
        llm = make_llm(temperature=0.0, model=model, max_tokens=220)
        msg = HumanMessage(
            content=[
                {
                    "type": "text",
                    "text": (
                        "Check this image for any readable text. "
                        "Return strict JSON only: {\"has_text\": true|false}. "
                        "Readable text means letters/numbers/words on signs, papers, logos, subtitles, watermarks."
                    ),
                },
                {"type": "image_url", "image_url": {"url": _mode5_image_to_data_url(path)}},
            ]
        )
        resp = await asyncio.wait_for(
            llm.ainvoke([SystemMessage(content="You are a strict vision QA checker. JSON only."), msg]),
            timeout=30.0,
        )
        raw = (getattr(resp, "content", "") or "").strip()
        data = json.loads(raw)
        return bool(data.get("has_text"))
    except Exception as e:
        logger.warning(f"[Mode5] Text guard fallback (skip) for {path.name}: {e}")
        return False


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


def _ensure_mode5_style_lock(plan: dict[str, Any]) -> str:
    mode_key = normalize_mode5_sub_mode(plan.get("sub_mode"))
    expected = mode5_style_lock_for_sub_mode(mode_key)
    locked = str(plan.get("style_lock") or "").strip()
    if not locked:
        locked = expected
    plan["style_lock"] = locked
    plan["style_suffix"] = locked
    plan["style_id"] = mode5_style_id_for_sub_mode(mode_key)
    return locked


def _mode5_chunk_context_text(chunk: dict[str, Any], seg_idx: int, *, window: int = 1) -> str:
    segments = list(chunk.get("segments") or [])
    if not segments:
        return ""
    lo = max(0, seg_idx - max(0, int(window)))
    hi = min(len(segments), seg_idx + max(0, int(window)) + 1)
    out: list[str] = []
    for i in range(lo, hi):
        if i == seg_idx:
            continue
        txt = re.sub(r"\s+", " ", str(segments[i].get("text") or "").strip())
        if txt:
            out.append(txt[:280])
    return " | ".join(out)[:900]


def _mode5_theme_anchor_context(plan: dict[str, Any], chunk: dict[str, Any], seg: dict[str, Any]) -> str:
    """Structured anchors so image prompts stay literal and theme-linked."""
    anchors: list[str] = []
    topic = re.sub(r"\s+", " ", str(plan.get("facts_topic") or "").strip())
    header = re.sub(r"\s+", " ", str(plan.get("header_title") or "").strip())
    visual_brief = re.sub(r"\s+", " ", str(plan.get("visual_topic_brief") or "").strip())
    chapter = re.sub(r"\s+", " ", str(chunk.get("chapter_title") or "").strip())
    subchapter = re.sub(r"\s+", " ", str(chunk.get("subchapter_title") or "").strip())
    text = re.sub(r"\s+", " ", str(seg.get("text") or "").strip())
    if topic:
        anchors.append(f"THEME_TOPIC: {topic[:180]}")
        anchors.append(
            f"STRICT_TOPIC_LOCK: scene must be unmistakably about '{topic[:140]}'; "
            "use topic-specific location/material culture/props; avoid generic office/lab/laptop defaults unless explicitly asked."
        )
    if header:
        anchors.append(f"VIDEO_TITLE: {header[:180]}")
    if visual_brief:
        anchors.append(f"LLM_VISUAL_BRIEF: {visual_brief[:260]}")
    if chapter:
        anchors.append(f"CHAPTER: {chapter[:180]}")
    if subchapter:
        anchors.append(f"SUBCHAPTER: {subchapter[:180]}")
    if text:
        anchors.append(f"SEGMENT_LITERAL_SOURCE: {text[:260]}")
    anchors.append(
        "VISUAL_ANCHOR_RULE: choose one specific location and 2-4 concrete props directly implied by the segment source; "
        "avoid symbolic/metaphoric substitutes and avoid generic stock interiors."
    )
    return " | ".join(anchors)[:900]


def _mode5_clean_prompt_text(text: str) -> str:
    # Remove zero-width/control chars that can poison prompt quality.
    t = str(text or "")
    t = re.sub(r"[\u200B-\u200F\u202A-\u202E\u2060-\u206F\uFEFF]", " ", t)
    t = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _mode5_strip_visual_brief_location(visual_brief: str) -> str:
    """
    Remove location=... segment from visual brief.
    Useful when story variant already defines a specific location to avoid prompt conflicts.
    """
    vb = _mode5_clean_prompt_text(visual_brief)
    if not vb:
        return vb
    # Typical shape: "location=...; key_props=...; avoid=..."
    vb = re.sub(r"(?:^|;\s*)location\s*=\s*[^;]+;?\s*", "", vb, flags=re.IGNORECASE).strip(" ;")
    vb = re.sub(r"\s*;\s*;\s*", "; ", vb)
    return vb


def _mode5_intro_lighting_line(sub_mode: str | None, story_prompt: str) -> str:
    story = _mode5_clean_prompt_text(story_prompt).lower()
    if any(k in story for k in ("dawn", "sunrise", "early morning", "утро", "рассвет")):
        return (
            "Lighting and mood: soft low-contrast dawn ambience, gentle warm-cool balance, cozy and soothing, "
            "no harsh highlights, no visual aggression."
        )
    if any(k in story for k in ("daylight", "noon", "midday", "день")):
        return (
            "Lighting and mood: soft low-contrast daylight ambience, calm and soothing, "
            "no harsh highlights, no visual aggression."
        )
    return (
        "Lighting and mood: warm low-contrast evening ambience, cozy and soothing, "
        "no harsh highlights, no visual aggression."
    )


async def _mode5_visual_topic_brief(topic_seed: str, sub_mode: str | None) -> str:
    """
    Ask LLM to convert video title/topic into concrete visual anchors.
    Returns compact plain text, fail-soft to original topic.
    """
    seed = _mode5_clean_prompt_text(str(topic_seed or ""))
    if not seed:
        return ""
    try:
        llm = make_llm(temperature=0.15, max_tokens=260)
        sys = SystemMessage(
            content=(
                "You are a visual art director for factual video thumbnails/backgrounds. "
                "Return strict JSON only."
            )
        )
        hum = HumanMessage(
            content=(
                "Convert this video topic into concrete visual anchors for one realistic scene. "
                "No abstract metaphors. Include only: location, key_props, forbidden_defaults. "
                "forbidden_defaults should list generic scenes that must be avoided unless explicitly in topic. "
                "Respond JSON: {\"visual_brief\":\"...\"}. Keep visual_brief <= 220 chars.\n\n"
                f"sub_mode={normalize_mode5_sub_mode(sub_mode)}\n"
                f"topic={seed}"
            )
        )
        resp = await asyncio.wait_for(llm.ainvoke([sys, hum]), timeout=35.0)
        raw = (getattr(resp, "content", "") or "").strip()
        data = json.loads(raw)
        vb = data.get("visual_brief")
        if isinstance(vb, dict):
            location = _mode5_clean_prompt_text(str(vb.get("location") or ""))[:100]
            props_raw = vb.get("key_props")
            if isinstance(props_raw, list):
                props = [_mode5_clean_prompt_text(str(x))[:40] for x in props_raw if str(x).strip()]
            else:
                props = []
            forb_raw = vb.get("forbidden_defaults")
            if isinstance(forb_raw, list):
                forb = [_mode5_clean_prompt_text(str(x))[:36] for x in forb_raw if str(x).strip()]
            else:
                forb = []
            parts: list[str] = []
            if location:
                parts.append(f"location={location}")
            if props:
                parts.append("key_props=" + ", ".join(props[:5]))
            if forb:
                parts.append("avoid=" + ", ".join(forb[:5]))
            brief = "; ".join(parts)
        elif isinstance(vb, list):
            brief = "; ".join([_mode5_clean_prompt_text(str(x))[:70] for x in vb if str(x).strip()])
        else:
            brief = _mode5_clean_prompt_text(str(vb or ""))
        return brief[:220] if brief else seed[:220]
    except Exception as e:
        logger.warning(f"[Mode5] visual-topic-brief fallback to seed: {e}")
        return seed[:220]


# Substrings we strip elsewhere via sanitizer when they appear in model output but not in user topic (avoid naming these in LLM instructions).
_MODE5_JAPAN_PLACE_MARKERS: tuple[str, ...] = (
    "japan",
    "japanese",
    "tokyo",
    "kyoto",
    "osaka",
    "hokkaido",
    "honshu",
    "hiroshima",
    "япон",
    "токио",
    "киото",
)


def _mode5_topic_mentions_japan(topic_text: str) -> bool:
    low = _mode5_clean_prompt_text(topic_text).lower()
    return any(m in low for m in _MODE5_JAPAN_PLACE_MARKERS)


def _mode5_prompt_has_japan_place_sticky(prompt_text: str) -> bool:
    low = _mode5_clean_prompt_text(prompt_text).lower()
    return any(m in low for m in _MODE5_JAPAN_PLACE_MARKERS)


async def _mode5_intro_photo_story_prompts(
    topic_seed: str,
    sub_mode: str | None,
    count: int,
    *,
    run_nonce: str | None = None,
) -> list[str]:
    """
    Generate 1/5 concrete visual story prompts from title/topic via LLM.
    """
    seed = re.sub(r"\s+", " ", str(topic_seed or "").strip())
    n = max(1, min(5, int(count or 1)))
    if not seed:
        return ["" for _ in range(n)]
    nonce = _mode5_clean_prompt_text(str(run_nonce or ""))[:80]

    def _topic_is_geo_locked(topic_text: str) -> bool:
        low = _mode5_clean_prompt_text(topic_text).lower()
        geo_markers = (
            "facts about",
            "travel",
            "country",
            "city",
            "japan",
            "france",
            "russia",
            "italy",
            "germany",
            "moscow",
            "paris",
            "tokyo",
            "kyoto",
            "about japan",
            "about france",
            "about russia",
            "о японии",
            "о франции",
            "о россии",
            "факт",
            "facts",
        )
        return any(m in low for m in geo_markers)

    def _neutral_reading_corner_story(topic_text: str) -> str:
        return (
            f"A serene early morning scene in a cozy reading corner at home, with one person quietly reading and "
            f"topic-linked props arranged naturally. Topic focus: {topic_text[:160]}."
        )[:420]

    def _sanitize_non_geo_story_prompt(prompt_text: str, topic_text: str) -> str:
        s = _mode5_clean_prompt_text(prompt_text)
        if not s:
            return s
        prompt_low = s.lower()
        if (not _mode5_topic_mentions_japan(topic_text)) and _mode5_prompt_has_japan_place_sticky(s):
            return _neutral_reading_corner_story(topic_text)
        if _topic_is_geo_locked(topic_text):
            return s[:420]
        # When topic is non-geographic (e.g., books/self-help), block sticky geo defaults.
        geo_defaults = (
            "kyoto",
            "japan",
            "tokyo",
            "osaka",
            "paris",
            "france",
            "moscow",
            "russia",
        )
        if not any(g in prompt_low for g in geo_defaults):
            return s[:420]
        return _neutral_reading_corner_story(topic_text)

    def _extract_json_dict(raw_text: str) -> dict[str, Any] | None:
        raw = (raw_text or "").strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(lines[1:-1] if lines and lines[-1].startswith("```") else lines[1:])
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return None
        try:
            obj = json.loads(m.group())
        except Exception:
            return None
        return obj if isinstance(obj, dict) else None

    try:
        llm = make_llm(temperature=0.62, max_tokens=1200)
        sys = SystemMessage(
            content=(
                "You are a world-class visual concept director for documentary/cinematic stills. "
                "Return strict JSON only."
            )
        )
        hum = HumanMessage(
            content=(
                "Given a video title/topic, produce concrete still-image prompts.\n"
                f"Need exactly {n} prompts.\n"
                "Rules:\n"
                "- each prompt must be one literal, filmable scene;\n"
                "- all prompts must stay in the same topic;\n"
                "- prompts must be different in сюжет/setting/composition;\n"
                "- each prompt must contain a specific location description (city/place/landmark/region) grounded in topic;\n"
                "- no abstract metaphors;\n"
                "- sleep-friendly tone: avoid rush-hour chaos, panic, conflict, aggression, visual overload;\n"
                "- prefer calm atmospheric scenes with clear focal subject and readable background depth;\n"
                "- avoid generic office/lab/laptop defaults unless explicitly required by topic.\n"
                "Return JSON: {\"prompts\":[\"...\", \"...\"]}\n\n"
                f"sub_mode={normalize_mode5_sub_mode(sub_mode)}\n"
                f"title_or_topic={seed}\n"
                f"variation_seed={nonce or 'default'}"
            )
        )
        resp = await asyncio.wait_for(llm.ainvoke([sys, hum]), timeout=45.0)
        raw = (getattr(resp, "content", "") or "").strip()
        data = _extract_json_dict(raw) or {}
        arr = data.get("prompts")
        if isinstance(arr, list):
            out = []
            for x in arr:
                s = re.sub(r"\s+", " ", str(x or "").strip())
                if s:
                    out.append(_sanitize_non_geo_story_prompt(s, seed))
            if len(out) >= n:
                return out[:n]
    except Exception as e:
        logger.warning(f"[Mode5] intro photo story prompts fallback: {e}")
    base = seed[:260]
    return [
        _sanitize_non_geo_story_prompt(
            (
                f"Location-focused variant seed {nonce or 'default'}: {base}. "
                f"Distinct scene variant #{i + 1} with explicitly different location/composition."
            ),
            seed,
        )
        for i in range(n)
    ]


def _mode5_motion_anchor_pack(scene_text: str, sub_mode: str | None) -> str:
    """
    Build deterministic motion anchors so still-generation and animation target the same elements.
    """
    sm = normalize_mode5_sub_mode(sub_mode)
    txt = re.sub(r"\s+", " ", str(scene_text or "").lower())

    fg = "fabric edges, hanging details, thin foreground foliage"
    mg = "hands-held props, small posture shifts, nearby utility objects"
    bg = "distant foliage, particles, soft light-and-shadow breathing"

    if any(k in txt for k in ("winter", "snow", "blizzard", "ice", "зима", "снег", "лед")):
        bg = "snow particles, light mist, distant tree-line sway"
    elif any(k in txt for k in ("sea", "ocean", "river", "water", "lake", "море", "река", "вода", "озеро")):
        bg = "water surface shimmer, gentle reflections, distant atmosphere haze"
    elif any(k in txt for k in ("city", "street", "square", "moscow", "paris", "город", "улиц", "площад")):
        bg = "soft atmospheric haze, subtle flag/fabric sway, slow light breathing"
    elif any(k in txt for k in ("archive", "desk", "library", "архив", "стол", "библиотек")):
        mg = "paper edges, desk lamp glow breathing, tiny tool reposition micro-motion"
        bg = "dust particles and soft shadow pass"

    is_outdoor = any(
        k in txt
        for k in (
            "garden",
            "pathway",
            "forest",
            "park",
            "street",
            "square",
            "beach",
            "shore",
            "mountain",
            "village",
            "kyoto",
            "сад",
            "парк",
            "улиц",
            "площад",
            "берег",
            "лес",
        )
    )

    if sm == "facts50":
        mg = "fact-carrying props and measurable tools, with tiny controlled movement only"
    elif sm == "book_night":
        if is_outdoor:
            fg = "nearby foliage edges, cloth folds, small hanging natural details"
            bg = "soft atmospheric haze, gentle light breathing, fine floating particles"
        else:
            fg = "curtains, blanket folds, lamp-side hanging details"
            bg = "warm low-contrast light breathing and fine dust particles"

    return (
        f"foreground={fg}; midground={mg}; background={bg}; "
        "locked_elements=human identity, face geometry, architecture, major props layout"
    )[:420]


def _build_mode5_intro_single_motion_prompt(
    *,
    sub_mode: str | None,
    topic_seed: str,
    visual_brief: str,
    story_prompt: str,
    variant_index: int,
    variants_total: int,
) -> str:
    mode_line = _mode5_submode_animation_directive(sub_mode)
    seed = re.sub(r"\s+", " ", (topic_seed or "").strip())[:320]
    brief = re.sub(r"\s+", " ", (visual_brief or "").strip())[:260]
    story = re.sub(r"\s+", " ", (story_prompt or "").strip())[:420]
    motion_anchors = _mode5_motion_anchor_pack(f"{seed}. {brief}. {story}", normalize_mode5_sub_mode(sub_mode))
    parts = [
        "Create one high-quality loopable animation from the provided still image.",
        "Keep scene identity stable: same location, props, subject roles, and composition from the still.",
        f"Animate ONLY these anchor groups from the still: {motion_anchors}",
        mode_line,
        _MODE5_INTRO_ANIMATION_DESCRIPTION,
        f"Topic: {seed}",
        f"LLM visual brief: {brief}",
        f"Still story variant {variant_index + 1}/{variants_total}: {story}",
        "No readable text, no logos, no UI.",
    ]
    return " ".join(parts)


def _build_mode5_intro_still_prompt(
    *,
    sub_mode: str | None,
    topic_seed: str,
    visual_brief: str,
    story_prompt: str,
    variant_index: int,
    variants_total: int,
) -> str:
    """
    Compact high-signal prompt for intro stills:
    - avoid policy duplication from full segment prompt builder,
    - force sleepy atmospheric semi-cartoon style,
    - keep strict topic binding.
    """
    topic = _mode5_clean_prompt_text(topic_seed)[:220]
    brief = _mode5_clean_prompt_text(visual_brief)[:220]
    story = _mode5_clean_prompt_text(story_prompt)[:320]
    # Story variant is the primary single-scene source; avoid dual-location conflicts
    # by stripping location from visual brief when both are present.
    if story and re.search(r"\blocation\s*=", brief, flags=re.IGNORECASE):
        brief = _mode5_strip_visual_brief_location(brief)[:220]
    sm = normalize_mode5_sub_mode(sub_mode)
    motion_anchors = _mode5_motion_anchor_pack(f"{topic}. {brief}. {story}", sm)
    style_nuance = _MODE5_INTRO_SUBMODE_STYLE_NUANCE.get(
        sm, _MODE5_INTRO_SUBMODE_STYLE_NUANCE["manual"]
    )
    style_line = (
        "Style target: beautiful painterly-cartoon look (soft semi-cartoon stylization), calm dreamy atmosphere for sleep video."
    )
    if sm == "facts50":
        style_line = (
            "Style target: painterly-cartoon documentary look (soft semi-cartoon stylization), calm and factual, with clear real-world detail."
        )
    parts = [
        "Create one high-quality cinematic still frame.",
        style_line,
        style_nuance,
        _mode5_intro_lighting_line(sub_mode, story),
        "Scene must be literal and topic-accurate, not abstract.",
        "Use one clear location and 3-6 topic-linked props across foreground/midground/background.",
        f"Animation-ready composition rule: explicitly include stable movable elements for later motion: {motion_anchors}",
        "No generic defaults (office/lab/laptop) unless explicitly required by story.",
        "Keep composition restful and uncluttered; avoid crowded rush-hour energy unless explicitly required by topic.",
        f"Topic: {topic}",
        f"Visual brief: {brief}",
        f"Story variant {variant_index + 1}/{variants_total}: {story}",
        "Horizontal landscape composition (16:9).",
        "No readable text, no logos, no UI, no watermark.",
    ]
    return " ".join(parts)


def _sanitize_mode5_image_prompt(prompt: str) -> str:
    cleaned = re.sub(r"\s+", " ", (prompt or "").strip())
    if not cleaned:
        return cleaned
    forbidden_replacements = {
        r"\bCURRENT_SEGMENT\b": "scene source",
        r"\bCHUNK_CONTEXT\b": "continuity context",
        r"\bMode profile\s*:[^.;]*(?:[.;]|$)": "",
        r"\bLocked style id\s*:[^.;]*(?:[.;]|$)": "",
        r"\bScene slots\s*:": "Scene construction:",
        r"\bTechnical rules\s*:": "Frame rules:",
        r"\bScene source\s*:": "The scene is based on",
        r"\bContinuity context\s*:": "Nearby narration for continuity:",
        r"\bMode-specific direction\s*:": "Visual direction:",
        r"\bPriority rule\s*:": "",
        r"\bAnti-abstract rule\s*:": "",
        r"\bCritical single-scene rule\s*:": "",
        r"\bScene construction\s*:": "Scene construction:",
        r"\bQuality constraints\s*:": "Quality:",
        r"\bFrame format\s*:": "Frame format:",
    }
    for pattern, repl in forbidden_replacements.items():
        cleaned = re.sub(pattern, repl, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.;:-")
    # Keep one concise post-sanitize guard to avoid prompt bloat; common no-text/single-frame
    # rules are already enforced in FastGen prepare layer.
    literal_guard = (
        "Literal-theme guard: the location and main props must be directly connected to the current narration segment. "
        "No abstract symbolism, no conceptual substitutions, and no unrelated decorative filler."
    )
    if "literal-theme guard" not in cleaned.lower():
        cleaned = f"{cleaned}. {literal_guard}"
    return cleaned


def _session_dir(session_id: str) -> Path:
    return settings.videos_dir / session_id


def _mode5_dir(session_id: str) -> Path:
    d = _session_dir(session_id) / "clips" / "mode5"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_mode5_placeholder_image(path: Path) -> None:
    """
    Last-resort fallback: write a neutral placeholder frame so one failed image does not
    abort the entire already-generated pipeline.
    """
    ff = resolve_ffmpeg_executable()
    if not ff:
        raise RuntimeError("ffmpeg not found for mode5 placeholder image fallback")
    tw, th = settings.mode5_video_resolution
    size = f"{tw}x{th}"
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
    if pref in _MODE5_SUPPORTED_LANGS:
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


def _mode5_visible_text(text: str) -> str:
    """Text shown in plan/review/image prompts: no VoiceAPI padding or stress marks."""
    return re.sub(r"\s+", " ", (text or "").replace(NONSPOKEN_LEN_FILLER_CHAR, "").replace("\u0301", "").strip())


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
        _ensure_mode5_live_defaults(plan)
        if checkpoint is not None:
            chunk_scoped = checkpoint_extra.get("chunk_index") is not None
            _validate_mode5_stage_transition(plan, checkpoint, chunk_scoped=chunk_scoped)
            stage_for_write = _checkpoint_stage_for_write(
                plan, checkpoint, chunk_scoped=chunk_scoped
            )
            _record_mode5_stage_metric(plan, stage_for_write)
            _touch_mode5_checkpoint(plan, stage_for_write, **checkpoint_extra)
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


def _mode5_skip_chunk_previews(plan: dict[str, Any]) -> bool:
    return bool(plan.get("skip_chunk_previews"))


def _mode5_sequential_chunks(plan: dict[str, Any] | None) -> bool:
    return bool((plan or {}).get("sequential_chunks"))


def _mode5_chunk_lane_parallel(requested: int, plan: dict[str, Any] | None = None) -> int:
    """Chunk-level parallelism (TTS / images / preview MP4 lanes). Segment fan-out inside a chunk is unchanged."""
    if _mode5_sequential_chunks(plan):
        return 1
    return max(1, int(requested or 1))


async def _mode5_await_chunk_coroutines(coros: list[Any], plan: dict[str, Any] | None = None) -> list[Any]:
    if not coros:
        return []
    if _mode5_sequential_chunks(plan):
        out: list[Any] = []
        for c in coros:
            out.append(await c)
        return out
    return list(await asyncio.gather(*coros))


def _mode5_append_chunk_render_rows(
    session_id: str,
    chunk_index: int,
    plan: dict[str, Any],
    *,
    segment_data: list[dict[str, Path | str]],
    subtitle_texts: list[str],
    top_labels: list[str],
) -> None:
    """Сегменты одного чанка в формате assemble_mode5_video (для превью чанка или одного финала)."""
    session_root = _session_dir(session_id)
    ch = plan["chunks"][chunk_index]
    show_sub = bool(plan.get("show_subtitles", True))
    sm = (plan.get("sub_mode") or "").strip().lower()
    ci = int(ch.get("index", chunk_index))
    for seg in ch.get("segments") or []:
        img_rel = str(seg.get("image") or "").strip()
        img = (session_root / img_rel) if img_rel else None
        aud = session_root / seg["audio"]
        video_rel = str(seg.get("video") or "").strip()
        video_abs = (session_root / video_rel) if video_rel else None
        use_video = (
            video_abs is not None
            and video_abs.is_file()
            and str(seg.get("asset_type") or "").strip().lower() == "video"
        )
        if not aud.is_file():
            raise FileNotFoundError(f"Missing audio: {aud}")
        if (not use_video) and (img is None or (not img.is_file())):
            raise FileNotFoundError(f"Missing image: {img}")
        si = int(seg.get("s", len(segment_data)))
        if use_video:
            segment_data.append(
                {
                    "asset_type": "video",
                    "video_path": video_abs,
                    "audio_path": aud,
                    "loop_offset_sec": 0.0,
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
            vid = str(seg.get("video") or "").strip()
            if img and (session_root / img).is_file():
                seg_done += 1
            elif vid and (session_root / vid).is_file():
                seg_done += 1
            else:
                ok = False
        if ok:
            chunks_fully_imaged += 1
    return seg_done, seg_total, chunks_fully_imaged, chunks_with_segs


_MODE5_PREVIEW_MIN_BYTES = 4096


def _mode5_previews_on_disk_count(
    session_root: Path, chunks: list[dict[str, Any]], *, strict: bool = False
) -> int:
    n = 0
    for ch in chunks:
        rel = str(ch.get("preview_relpath") or "").strip()
        if rel and _mode5_preview_file_ready(session_root / rel, strict=strict):
            n += 1
    return n


def _mode5_preview_file_ready(path: Path, *, strict: bool = True) -> bool:
    """strict=False: быстрая проверка для списков; strict=True: ffprobe перед финальной склейкой."""
    if not path.is_file():
        return False
    try:
        size = path.stat().st_size
    except OSError:
        return False
    if size < _MODE5_PREVIEW_MIN_BYTES:
        return False
    if not strict:
        return True
    try:
        return _mode5_probe_video_duration_sec(path) > 0.1
    except Exception:
        return False


def mode5_preview_readiness(
    session_id: str, plan: dict[str, Any] | None = None, *, strict: bool = True
) -> dict[str, Any]:
    plan = plan or load_mode5_plan(session_id)
    session_root = _session_dir(session_id)
    chunks = list(plan.get("chunks") or [])
    ready_relpaths: list[str] = []
    pending_relpaths: list[str] = []
    for ch in chunks:
        rel = str(ch.get("preview_relpath") or "").strip()
        if not rel:
            pending_relpaths.append("")
            continue
        if _mode5_preview_file_ready(session_root / rel, strict=strict):
            ready_relpaths.append(rel)
        else:
            pending_relpaths.append(rel)
    total = len(chunks)
    ready = len(ready_relpaths)
    return {
        "ready_count": ready,
        "total_count": total,
        "can_assemble": total > 0 and ready == total,
        "ready_relpaths": ready_relpaths,
        "pending_relpaths": pending_relpaths,
    }


def _mode5_intro_videos_disk_counts(session_root: Path, plan: dict[str, Any]) -> tuple[int, int]:
    """Сколько intro-превью уже записано на диск (ожидаемые пути из плана)."""
    raw = list(plan.get("intro_preview_videos") or [])
    rels = [str(x).strip() for x in raw if str(x).strip()]
    if not rels:
        one = str(plan.get("intro_preview_video") or "").strip()
        if one:
            rels = [one]
    total = len(rels)
    if total == 0:
        return 0, 0
    on_disk = sum(1 for r in rels if (session_root / r).is_file())
    return on_disk, total


def _mode5_chunks_wav_ready_count(session_id: str, plan: dict[str, Any]) -> tuple[int, int]:
    """Чанки с реальным chunk wav на диске (озвучка чанка готова)."""
    chunks = list(plan.get("chunks") or [])
    n = len(chunks)
    if n == 0:
        return 0, 0
    ready = 0
    for ch in chunks:
        _mp3, wav = _resolve_mode5_chunk_audio_paths(session_id, ch)
        if wav is not None:
            ready += 1
    return ready, n


def _mode5_ui_phase_from_metrics(
    *,
    has_final_mp4: bool,
    stage: str,
    seg_done: int,
    seg_total: int,
    n_ch: int,
    prev_done: int,
    plan: dict[str, Any],
    wav_ready: int = 0,
    wav_total: int = 0,
) -> str:
    """Стабильная метка фазы для UI (не зависит от формулировки hint)."""
    if has_final_mp4:
        return "final_mp4_on_disk"
    if bool(plan.get("await_intro_confirmation")) and stage == MODE5_CKPT_STUB and seg_total == 0:
        return "intro_await_confirm"
    if (
        wav_ready > 0
        and wav_total > 0
        and stage == MODE5_CKPT_STUB
        and seg_total == 0
    ):
        return "tts_chunks_parallel"
    if bool(plan.get("preflight_only")) and stage == MODE5_CKPT_STUB and seg_total == 0:
        return "intro_preflight_generating"
    if seg_total == 0 and stage == MODE5_CKPT_STUB:
        return "tts_chunks_parallel"
    if seg_total == 0 and stage == MODE5_CKPT_AFTER_TTS:
        return "post_tts_segmentation"
    if seg_total == 0 and n_ch > 0:
        return "structure_and_segments"
    if seg_total > 0 and seg_done < seg_total:
        return "segment_images"
    if n_ch > 0 and prev_done < n_ch:
        if bool(plan.get("skip_chunk_previews")):
            return "final_assembly_no_chunk_previews"
        return "chunk_mp4_previews"
    # Нет явной подсказки — ориентир по чекпоинту
    tail = {
        MODE5_CKPT_AFTER_IMAGES: "after_images",
        MODE5_CKPT_AFTER_SLICES: "after_slices",
        MODE5_CKPT_AFTER_PREVIEWS: "after_previews",
        MODE5_CKPT_COMPLETED: "completed",
    }.get(stage, "running")
    return f"checkpoint_{tail}"


def _mode5_progress_hint_payload(session_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    """Human-readable progress for /review-state while previews or final video are not done."""
    session_root = _session_dir(session_id)
    final_mp4 = session_root / "video_mode5.mp4"
    intro_on, intro_total = _mode5_intro_videos_disk_counts(session_root, plan)
    wav_ready, wav_total = _mode5_chunks_wav_ready_count(session_id, plan)
    if final_mp4.is_file():
        phase = _mode5_ui_phase_from_metrics(
            has_final_mp4=True,
            stage=_checkpoint_stage(plan) or "",
            seg_done=0,
            seg_total=0,
            n_ch=0,
            prev_done=0,
            plan=plan,
        )
        return {
            "mode5_progress_hint": None,
            "mode5_segments_imaged": None,
            "mode5_segments_total": None,
            "mode5_chunks_imaged": None,
            "mode5_chunks_with_segments": None,
            "mode5_previews_on_disk": None,
            "mode5_ui_phase": phase,
            "mode5_intro_previews_on_disk": intro_on,
            "mode5_intro_previews_expected": intro_total,
            "mode5_chunks_voice_ready": wav_ready,
            "mode5_chunks_voice_total": wav_total,
        }
    chunks = list(plan.get("chunks") or [])
    n_ch = len(chunks)
    seg_done, seg_total, ch_img, ch_w_seg = _mode5_segment_image_counts(session_root, plan)
    prev_done = _mode5_previews_on_disk_count(session_root, chunks)
    readiness = mode5_preview_readiness(session_id, plan)
    ck = plan.get("pipeline_checkpoint")
    stage = (ck.get("stage") or "").strip() if isinstance(ck, dict) else ""

    if readiness["can_assemble"]:
        phase = _mode5_ui_phase_from_metrics(
            has_final_mp4=False,
            stage=stage or MODE5_CKPT_AFTER_PREVIEWS,
            seg_done=seg_done,
            seg_total=seg_total,
            n_ch=n_ch,
            prev_done=n_ch,
            plan=plan,
        )
        return {
            "mode5_progress_hint": "Все части готовы — можно запускать финальный монтаж.",
            "mode5_segments_imaged": seg_done,
            "mode5_segments_total": seg_total,
            "mode5_chunks_imaged": ch_img,
            "mode5_chunks_with_segments": ch_w_seg,
            "mode5_previews_on_disk": readiness["ready_count"],
            "mode5_ui_phase": phase,
            "mode5_intro_previews_on_disk": intro_on,
            "mode5_intro_previews_expected": intro_total,
            "mode5_chunks_voice_ready": wav_ready,
            "mode5_chunks_voice_total": wav_total,
        }

    hint: str | None = None
    if seg_total == 0:
        if stage == MODE5_CKPT_STUB:
            # STUB встречается и до любого TTS: префлайт с анимированными превью вступления,
            # ожидание подтверждения пользователя, затем уже параллельная озвучка чанков.
            if bool(plan.get("await_intro_confirmation")):
                hint = (
                    "Проверьте анимированные превью стиля и подтвердите продолжение. "
                    "Озвучка и монтаж основного видео до подтверждения не запускаются."
                )
            elif bool(plan.get("preflight_only")) and wav_ready <= 0:
                hint = (
                    "Генерируются короткие анимированные превью стиля. "
                    "Параллельная озвучка всего ролика начнётся только после вашего подтверждения."
                )
            elif wav_total > 0:
                hint = f"Параллельная озвучка чанков: {wav_ready} из {wav_total}…"
            else:
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
        if bool(plan.get("skip_chunk_previews")):
            hint = "Финальная сборка длинного видео (без превью по частям)…"
        else:
            hint = "Сборка превью по частям (короткие mp4 для проверки)…"

    phase = _mode5_ui_phase_from_metrics(
        has_final_mp4=False,
        stage=stage,
        seg_done=seg_done,
        seg_total=seg_total,
        n_ch=n_ch,
        prev_done=prev_done,
        plan=plan,
        wav_ready=wav_ready,
        wav_total=wav_total,
    )

    return {
        "mode5_progress_hint": hint,
        "mode5_segments_imaged": seg_done,
        "mode5_segments_total": seg_total,
        "mode5_chunks_imaged": ch_img,
        "mode5_chunks_with_segments": ch_w_seg,
        "mode5_previews_on_disk": prev_done,
        "mode5_ui_phase": phase,
        "mode5_intro_previews_on_disk": intro_on,
        "mode5_intro_previews_expected": intro_total,
        "mode5_chunks_voice_ready": wav_ready,
        "mode5_chunks_voice_total": wav_total,
    }


def dismiss_mode5_review(session_id: str) -> dict[str, Any]:
    """Убрать сессию из сайдбара «Проверка» без финального монтажа (превью остаются на диске)."""

    def _mutate(plan: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        plan["review_dismissed"] = True
        plan["review_dismissed_at"] = now
        plan["pipeline_paused"] = False
        plan["await_intro_confirmation"] = False

    return _update_mode5_plan_atomic(session_id, _mutate)


def mode5_resume_snapshot_for_plan(session_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    """Whether POST continue-generation can proceed using saved mode5 artifacts on disk."""
    stage = _checkpoint_stage(plan)
    if bool(plan.get("review_dismissed")):
        return {"can_resume": False, "stage": stage, "reason": "review_dismissed"}
    root = _session_dir(session_id)
    final_mp4 = root / "video_mode5.mp4"
    if final_mp4.is_file():
        return {"can_resume": False, "stage": stage, "reason": "final_video_exists"}
    chunks = list(plan.get("chunks") or [])
    if bool(plan.get("await_intro_confirmation")) and stage == MODE5_CKPT_STUB:
        # Continue is allowed only after preflight has materialized chunk stubs.
        if not chunks:
            if bool(plan.get("preflight_only")) and bool(plan.get("intro_preview_videos")):
                # Legacy plans (without persisted chunk stubs) are recoverable in resume fallback path.
                return {"can_resume": True, "stage": stage, "reason": "awaiting_intro_confirmation"}
            return {"can_resume": False, "stage": stage, "reason": "preflight_not_ready"}
        return {"can_resume": True, "stage": stage, "reason": "awaiting_intro_confirmation"}
    if not chunks:
        if bool(plan.get("early_pause_before_chunks")) and stage == MODE5_CKPT_STUB:
            return {"can_resume": True, "stage": stage, "reason": "early_pause_before_chunks"}
        return {"can_resume": False, "stage": stage, "reason": "no_chunks"}
    sm = (plan.get("sub_mode") or "").strip().lower()
    if stage == MODE5_CKPT_STUB:
        # STUB plans intentionally may contain only chunk text stubs. The resume path
        # bootstraps missing TTS/WAV files from these texts before continuing.
        return {"can_resume": True, "stage": stage, "reason": "resume_from_stub"}
    if sm == "unwritten_chapter" and stage in (MODE5_CKPT_STUB, MODE5_CKPT_AFTER_IMAGES):
        return {"can_resume": True, "stage": stage, "reason": "resume_before_tts"}
    for ch in chunks:
        _mp3_path, wav_path = _resolve_mode5_chunk_audio_paths(session_id, ch)
        if wav_path is None:
            return {"can_resume": False, "stage": stage, "reason": "missing_chunk_wav"}
    if _all_chunk_previews_on_disk(root, chunks):
        # Previews may be complete while final assembly/publish stage is still missing.
        return {"can_resume": True, "stage": stage or MODE5_CKPT_AFTER_PREVIEWS, "reason": "previews_complete"}
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
    readiness = mode5_preview_readiness(session_id, plan, strict=False)
    out["mode5_total_chunks"] = readiness["total_count"]
    out["mode5_ready_chunks"] = readiness["ready_count"]
    out["mode5_can_assemble"] = readiness["can_assemble"]
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
    lang = (language or "").strip().lower()
    if lang == "ru":
        return f"Факт {n}."
    if lang == "es":
        return f"Hecho {n}."
    if lang == "fr":
        return f"Fait {n}."
    if lang == "de":
        return f"Fakt {n}."
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
    lang = (language or "").strip().lower()
    if lang == "ru":
        return (
            "Устройтесь поудобнее. Дальше — спокойный рассказ: один факт за другим, без суеты, в темпе для фона и сна. "
            f"Тема этого выпуска — «{clean_topic}»."
        )
    if lang == "es":
        return (
            "Ponte comodo. A continuacion, un relato tranquilo: un dato tras otro, sin prisa, con ritmo suave para fondo y descanso. "
            f"El tema de este episodio es: {clean_topic}."
        )
    if lang == "fr":
        return (
            "Installez-vous confortablement. La suite est un recit calme: un fait apres l'autre, sans precipitation, "
            f"dans un rythme doux. Le theme de cet episode est: {clean_topic}."
        )
    if lang == "de":
        return (
            "Mach es dir bequem. Es folgt eine ruhige Erzahlung: eine Tatsache nach der anderen, ohne Eile, "
            f"in einem sanften Tempo. Das Thema dieser Folge ist: {clean_topic}."
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
    lang = (language or "").strip().lower()
    if lang == "ru":
        variants = [
            "Спасибо, что были со мной до конца. Пусть останется лёгкое настроение — и спокойной ночи.",
            "На сегодня у меня всё. Дышите ровно; если захотите продолжения — задайте новую тему, сделаем ещё один выпуск.",
            "Я поблагодарю за внимание и отпущу вас отдыхать. До встречи в следующем спокойном выпуске.",
        ]
        return random.choice(variants)
    if lang == "es":
        variants = [
            "Gracias por escuchar hasta el final. Te deseo una noche tranquila.",
            "Eso es todo por hoy. Respira con calma; cuando quieras, elegimos un nuevo tema.",
            "Te dejo descansar. Nos vemos en el proximo episodio sereno.",
        ]
        return random.choice(variants)
    if lang == "fr":
        variants = [
            "Merci d'avoir ecoute jusqu'au bout. Je vous souhaite une nuit paisible.",
            "C'est tout pour aujourd'hui. Respirez calmement; si vous voulez, on choisira un nouveau theme.",
            "Je vous laisse vous reposer. A bientot pour un prochain episode calme.",
        ]
        return random.choice(variants)
    if lang == "de":
        variants = [
            "Danke, dass du bis zum Ende zugehort hast. Ich wunsche dir eine ruhige Nacht.",
            "Das war's fur heute. Atme ruhig; wenn du magst, machen wir als nachstes ein neues Thema.",
            "Ich lasse dich hier zur Ruhe kommen. Bis zur nachsten entspannten Folge.",
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


def _chunk_duration_sec(ch: dict[str, Any]) -> float:
    raw = ch.get("duration_sec")
    if raw is not None:
        try:
            return max(0.0, float(raw))
        except (TypeError, ValueError):
            pass
    total = 0.0
    for seg in ch.get("segments") or []:
        try:
            t0 = float(seg.get("t0") or 0.0)
            t1 = float(seg.get("t1") or 0.0)
        except (TypeError, ValueError):
            continue
        if t1 > t0:
            total += t1 - t0
    return total


def _chunk_meta_public(ch: dict[str, Any]) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "index": ch["index"],
        "duration_sec": _chunk_duration_sec(ch),
        "num_segments": len(ch.get("segments") or []),
        "text": ch.get("text", ""),
        "segments": [
            {
                "index": seg.get("s"),
                "text": seg.get("text", ""),
                "t0": seg.get("t0"),
                "t1": seg.get("t1"),
                "image": seg.get("image"),
                "audio": seg.get("audio"),
                "image_prompt": seg.get("image_prompt"),
                "image_version": seg.get("image_version", 1),
                "audio_version": seg.get("audio_version", 1),
                "last_action": seg.get("last_action", "auto"),
                "dirty_reason": seg.get("dirty_reason", ""),
            }
            for seg in (ch.get("segments") or [])
        ],
        "status": ch.get("status", "pending"),
        "version": ch.get("version", 1),
        "audio_status": ch.get("audio_status", "pending"),
        "images_status": ch.get("images_status", "pending"),
        "preview_status": ch.get("preview_status", "pending"),
        "locked": bool(ch.get("locked", False)),
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
    if ch.get("block_loop_id") is not None:
        try:
            meta["block_loop_id"] = int(ch.get("block_loop_id"))
        except (TypeError, ValueError):
            pass
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
        "publishing": plan.get("publishing") if isinstance(plan.get("publishing"), dict) else None,
        "mode5_publish_thumbnail": str(plan.get("publish_thumbnail_rel") or "").strip() or None,
        "mode5_review_ready": review_ready,
        "mode5_clip_filenames": preview_filenames if review_ready else [],
        "mode5_chunks_meta": [_chunk_meta_public(ch) for ch in chunks] if review_ready else [],
        "mode5_sub_mode": plan.get("sub_mode") or "manual",
        "mode5_metrics": plan.get("mode5_metrics") if isinstance(plan.get("mode5_metrics"), dict) else None,
        "mode5_live_queue": plan.get("live_queue") if isinstance(plan.get("live_queue"), list) else [],
        "mode5_live_events": plan.get("live_events") if isinstance(plan.get("live_events"), list) else [],
        "mode5_live_policy": plan.get("live_policy") or "hybrid",
        "mode5_pending_rebuilds": plan.get("pending_rebuilds") if isinstance(plan.get("pending_rebuilds"), list) else [],
        "mode5_test_run": bool(plan.get("test_run")),
        "mode5_test_target_sec": plan.get("test_target_sec"),
        "mode5_block_loop_enabled": bool(_mode5_block_loop_applies(plan)),
        "mode5_block_loop_pool_size": _mode5_block_loop_pool_size(),
        "mode5_await_intro_confirmation": bool(plan.get("await_intro_confirmation")),
        "mode5_intro_preview_video": plan.get("intro_preview_video"),
        "mode5_intro_preview_videos": list(plan.get("intro_preview_videos") or []),
        "mode5_preflight_only": bool(plan.get("preflight_only")),
        "mode5_pipeline_paused": bool(plan.get("pipeline_paused")),
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
    payload["mode5_await_intro_confirmation"] = False
    payload["mode5_intro_preview_video"] = None
    payload["mode5_intro_preview_videos"] = []
    payload["mode5_ui_phase"] = "plan_file_pending"
    payload["mode5_intro_previews_on_disk"] = 0
    payload["mode5_intro_previews_expected"] = 0
    payload["mode5_chunks_voice_ready"] = 0
    payload["mode5_chunks_voice_total"] = 0
    return payload


def _mode5_script_excerpt_for_publish(plan: dict[str, Any], *, max_chars: int = 3200) -> str:
    chunks = list(plan.get("chunks") or [])
    lines: list[str] = []
    for ch in chunks[:12]:
        txt = re.sub(r"\s+", " ", str(ch.get("text") or "").strip())
        if txt:
            lines.append(txt[:420])
    joined = " ".join(lines).strip()
    return joined[:max_chars]


def _mode5_duration_minutes(plan: dict[str, Any]) -> int:
    chunks = list(plan.get("chunks") or [])
    total_sec = 0.0
    for ch in chunks:
        try:
            total_sec += float(ch.get("duration_sec") or 0.0)
        except Exception:
            continue
    return max(1, int(round(total_sec / 60.0))) if total_sec > 0 else max(1, len(chunks) * 4)


async def _mode5_generate_publish_assets(
    session_id: str,
    plan: dict[str, Any],
    *,
    force_thumbnail: bool = False,
) -> None:
    session_root = _session_dir(session_id)
    m5dir = _mode5_dir(session_id)
    m5dir.mkdir(parents=True, exist_ok=True)
    topic = re.sub(r"\s+", " ", str(plan.get("header_title") or plan.get("facts_topic") or "").strip())
    if not topic:
        topic = "Sleep long-form video"
    sub_mode = normalize_mode5_sub_mode(plan.get("sub_mode"))
    excerpt = _mode5_script_excerpt_for_publish(plan)
    duration_min = _mode5_duration_minutes(plan)

    try:
        ru, en = await asyncio.gather(
            generate_mode5_publishing_metadata(
                topic=topic,
                sub_mode=sub_mode,
                script_excerpt=excerpt,
                duration_min=duration_min,
                language="ru",
            ),
            generate_mode5_publishing_metadata(
                topic=topic,
                sub_mode=sub_mode,
                script_excerpt=excerpt,
                duration_min=duration_min,
                language="en",
            ),
        )
        plan["publishing"] = {"ru": ru, "en": en}
    except Exception as e:
        logger.warning(f"[Mode5] publishing metadata generation failed: {e}")

    existing_thumb_rel = str(plan.get("publish_thumbnail_rel") or "").strip()
    thumb_path = session_root / existing_thumb_rel if existing_thumb_rel else (m5dir / "youtube_thumbnail.jpg")
    if (not force_thumbnail) and thumb_path.is_file():
        plan["publish_thumbnail_rel"] = _rel_session(session_root, thumb_path)
        return

    from agents.content_generator import fastgen_playwright

    try:
        cover_ref: Path | None = None
        if (
            sub_mode in ("book_night", "unwritten_chapter")
            and bool(getattr(settings, "mode5_thumbnail_openlibrary_cover", True))
        ):
            cand = m5dir / "_thumbnail_book_cover_ref.jpg"
            got = await asyncio.to_thread(try_fetch_openlibrary_cover, topic, cand)
            if got and cand.is_file():
                cover_ref = cand
            else:
                try:
                    cand.unlink(missing_ok=True)
                except OSError:
                    pass

        thumb_prompt = await generate_mode5_thumbnail_prompt(
            topic=topic,
            sub_mode=sub_mode,
            script_excerpt=excerpt,
            use_reference_cover=cover_ref is not None,
        )
        thumb_prompt = _mode5_clean_prompt_text(thumb_prompt)
        if cover_ref is not None:
            generated = await fastgen_playwright.generate_images_with_references_fastgen(
                [(thumb_prompt, [cover_ref])],
                m5dir,
                parallel=False,
            )
        else:
            generated = await fastgen_playwright.generate_images_fastgen(
                [thumb_prompt],
                m5dir,
                parallel=False,
                aspect_ratio="16:9",
            )
        src = Path(generated[0]) if generated and generated[0] else None
        if src is None or (not src.is_file()):
            raise RuntimeError("thumbnail image path missing")
        if src.resolve() != thumb_path.resolve():
            shutil.copy2(src, thumb_path)
            try:
                src.unlink()
            except OSError:
                pass
        plan["publish_thumbnail_rel"] = _rel_session(session_root, thumb_path)
    except Exception as e:
        logger.warning(f"[Mode5] publish thumbnail generation failed: {e}")


def _mode5_generate_publish_assets_sync(
    session_id: str,
    plan: dict[str, Any],
    *,
    force_thumbnail: bool = False,
) -> None:
    asyncio.run(_mode5_generate_publish_assets(session_id, plan, force_thumbnail=force_thumbnail))


async def _generate_chunk_images(
    session_id: str,
    chunk: dict[str, Any],
    style_suffix: str,
    *,
    sub_mode: str,
    max_parallel_images: int,
    image_backend: str | None = None,
    refresh_all: bool = False,
    on_segment_ready: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None,
    topic_seed_override: str | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    session_root = _session_dir(session_id)
    topic_seed = (
        _mode5_clean_prompt_text(topic_seed_override or "")
        or _mode5_clean_prompt_text(str(chunk.get("facts_topic") or ""))
        or _mode5_clean_prompt_text(str(chunk.get("header_title") or ""))
        or _mode5_clean_prompt_text(str(chunk.get("fact_hint") or ""))
        or _mode5_clean_prompt_text(str(chunk.get("text") or ""))
    )
    visual_brief = await _mode5_visual_topic_brief(topic_seed, sub_mode)
    plan_like = {
        "facts_topic": chunk.get("facts_topic"),
        "header_title": chunk.get("header_title"),
        "visual_topic_brief": visual_brief,
    }
    cap = _mode5_parallel_images_cap()
    sem = asyncio.Semaphore(max(1, min(cap, int(max_parallel_images or cap))))
    chunk_index = int(chunk.get("index") or 0)
    segments = list(chunk.get("segments") or [])

    async def _one(seg_idx: int, seg: dict[str, Any]) -> tuple[dict[str, Any], BaseException | None]:
        seg_prompt_text = _mode5_clean_prompt_text(str(seg.get("text") or ""))
        if normalize_mode5_sub_mode(sub_mode) == "facts50":
            fact_hint = _mode5_clean_prompt_text(str(chunk.get("fact_hint") or ""))
            if fact_hint:
                seg_prompt_text = fact_hint
        context_parts = [
            _mode5_theme_anchor_context(plan_like, chunk, seg),
            _mode5_chunk_context_text(chunk, seg_idx, window=1),
        ]
        chunk_context = " | ".join([x for x in context_parts if x])[:900]
        prompt = build_mode5_image_prompt(
            sub_mode=sub_mode,
            segment_text=seg_prompt_text,
            chunk_context=chunk_context,
            style_lock=style_suffix,
            output_format=_mode5_output_format(),
        )
        prompt = _sanitize_mode5_image_prompt(prompt)
        seg["image_prompt"] = prompt
        img_path = session_root / seg["image"]
        async with sem:
            try:
                await _generate_one_image(
                    prompt,
                    img_path,
                    aspect_ratio=_mode5_image_aspect_ratio(),
                    image_backend=image_backend,
                    cancel_event=cancel_event,
                )
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

    for fut in asyncio.as_completed(tasks):
        seg, err = await fut
        if err is not None:
            target = session_root / seg["image"]
            try:
                retry_prompt = (
                    f"{str(seg.get('image_prompt') or '').strip()}. "
                    "Retry topic lock: keep exactly the same segment topic, same literal location class, and same topic-linked props. "
                    "Do not switch to a generic room/lab/office/hospital unless the segment explicitly asks for it."
                ).strip()
                async with sem:
                    await _generate_one_image(
                        retry_prompt,
                        target,
                        aspect_ratio=_mode5_image_aspect_ratio(),
                        image_backend=image_backend,
                        cancel_event=cancel_event,
                    )
                seg["image_fallback"] = True
                seg["image_fallback_reason"] = f"topic-locked retry fallback: {type(err).__name__}"
                logger.warning(
                    f"[Mode5] Image topic-locked retry fallback used for chunk={chunk_index} seg={seg.get('s')}: {err}"
                )
            except Exception:
                try:
                    _write_mode5_placeholder_image(target)
                    seg["image_fallback"] = True
                    seg["image_fallback_reason"] = f"placeholder fallback: {type(err).__name__}"
                    logger.warning(
                        f"[Mode5] Placeholder fallback used for chunk={chunk_index} seg={seg.get('s')}: {err}"
                    )
                    if normalize_mode5_sub_mode(sub_mode) == "facts50":
                        raise RuntimeError(
                            f"[Mode5] Facts50 image generation failed; placeholder fallback disabled to avoid gray screens: {err}"
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

    block_title = re.sub(r"\s+", " ", str(seg0.get("overlay_title") or "").strip())[:180]
    parts = [
        "Create a loopable intro video from provided start/end keyframes.",
        _MODE5_INTRO_ANIMATION_DESCRIPTION,
        "Keep one continuous shot for the full clip: no edits, no jump cuts, no shot changes.",
        "Micro-motion only: subtle breathing atmosphere, tiny camera drift, gentle depth movement.",
    ]
    if block_title:
        parts.append(f"Intro block title context: {block_title}")
    if scene_text:
        parts.append(f"Scene context: {scene_text}")
    if source_image_prompt:
        parts.append(f"Visual source context: {source_image_prompt}")
    if style_tail:
        parts.append(f"Style guardrails: {style_tail}")
    parts.append(
        "Keep composition stable and realistic. Preserve identity, props, geometry, and scene structure. "
        "No readable text overlays, no logos, no UI elements."
    )
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
            flow_max_attempts=settings.fastgen_veo_flow_max_attempts,
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


def _mode5_block_loop_series_anchor(plan: dict[str, Any]) -> str:
    """Книга / тема / название выпуска — для символических отсылок в block-loop (без читаемого текста на кадре)."""
    p = plan or {}
    raw = str(p.get("facts_topic") or "").strip() or str(p.get("header_title") or "").strip()
    if raw:
        return raw[:280]
    os = p.get("outline_structure")
    if isinstance(os, dict):
        wt = str(os.get("working_title") or "").strip()
        if wt:
            return wt[:280]
    sc = str(p.get("script_text") or "").strip()
    if sc:
        return sc[:280]
    return ""


def _mode5_intro_topic_lock(topic_seed: str) -> str:
    """
    Extract a concrete topic entity for strict intro-preview scene anchoring.
    Example: "77 facts about Russia" -> "Russia".
    """
    seed = re.sub(r"\s+", " ", str(topic_seed or "").strip())
    if not seed:
        return ""
    low = seed.lower()
    patterns = [
        r"^\s*\d+\s*facts?\s+about\s+(.+?)\s*$",
        r"^\s*top\s*\d+\s*facts?\s+about\s+(.+?)\s*$",
        r"^\s*\d+\s*факт[аов]?\s+о\s+(.+?)\s*$",
        r"^\s*топ\s*\d+\s*факт[аов]?\s+о\s+(.+?)\s*$",
    ]
    for pat in patterns:
        m = re.match(pat, low, flags=re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            if raw:
                return raw[:180]
    return seed[:180]


def _mode5_block_loop_applies(plan: dict[str, Any]) -> bool:
    if not bool(getattr(settings, "mode5_block_loop_video_enabled", False)):
        return False
    backend = _normalize_mode5_image_backend(
        plan.get("image_backend")
        if plan.get("image_backend") is not None
        else getattr(settings, "mode5_image_backend", "playwright")
    )
    if backend == "api" and not str(getattr(settings, "fastgen_http_base_url", "") or "").strip():
        return False
    sm = (plan.get("sub_mode") or "").strip().lower()
    if sm == "facts50":
        return bool(getattr(settings, "mode5_block_loop_include_facts50", False))
    return bool(sm)


def _mode5_submode_animation_directive(sub_mode: str | None) -> str:
    sm = normalize_mode5_sub_mode(sub_mode)
    if sm == "facts50":
        return (
            "Sub-mode facts50 directive: prioritize factual clarity and visual proof. "
            "Animate concrete evidence carriers (tools, processes, measurable actions) instead of decorative mood motion."
        )
    if sm == "outline":
        return (
            "Sub-mode outline directive: each block is a chapter beat. "
            "Keep chapter-specific location and props stable, and animate beat-relevant elements that explain the current point."
        )
    if sm == "book_night":
        return (
            "Sub-mode book_night directive: calm reflective nocturnal mood with cozy lived-in details. "
            "Use gentle intimate motion (lamp breathing, curtain sway, subtle hand/object shifts), avoid thriller energy."
        )
    if sm == "unwritten_chapter":
        return (
            "Sub-mode unwritten_chapter directive: investigative documentary tension. "
            "Animate evidence workflow details (folders, map markers, desk lamp, dust, tape/tools) and keep procedural realism."
        )
    if sm == "bible":
        return (
            "Sub-mode bible directive: period-authentic biblical world. "
            "Animate historically plausible environmental elements (cloth, firelight, wind, crowd/background life) with reverent restraint."
        )
    return (
        "Sub-mode manual directive: literal documentary realism with theme-linked place and props; "
        "animate only meaningful in-scene elements tied to narration."
    )


async def _mode5_animate_still_to_motion_clip(
    *,
    motion_prompt: str,
    output_dir: Path,
    still_path: Path,
    clip_index: int,
    backend: str,
    cancel_event: threading.Event | None = None,
) -> Path | None:
    """
    Still → короткий motion-клип для loop: FastGen «Ключ. кадры» (start=end=still).
    Fallback — «Обычный» режим с одним референсом, если keyframes не удались.
    """
    from agents.content_generator import fastgen_http, fastgen_playwright

    aspect = _mode5_image_aspect_ratio()
    flow_n = settings.fastgen_veo_flow_max_attempts
    still = Path(still_path)
    if not still.is_file():
        return None

    async def _from_keyframes() -> Path | None:
        if backend == "api":
            raw = await fastgen_http.generate_video_from_keyframes(
                motion_prompt,
                output_dir,
                still,
                still,
                index=clip_index,
                cancel_event=cancel_event,
                flow_max_attempts=flow_n,
                video_aspect_ratio=aspect,
            )
        else:
            raw = await fastgen_playwright.generate_video_from_keyframes(
                motion_prompt,
                output_dir,
                still,
                still,
                index=clip_index,
                cancel_event=cancel_event,
                flow_max_attempts=flow_n,
                video_aspect_ratio=aspect,
            )
        p = Path(raw) if raw else None
        return p if p and p.is_file() else None

    async def _from_single_ref() -> Path | None:
        if backend == "api":
            raw = await fastgen_http.generate_single_video_fastgen(
                motion_prompt,
                output_dir,
                clip_index,
                reference_image_path=still,
                cancel_event=cancel_event,
                mode4_veo_flow_flower=False,
                flow_max_attempts=flow_n,
                video_aspect_ratio=aspect,
            )
        else:
            raw = await fastgen_playwright.generate_single_video_fastgen(
                motion_prompt,
                output_dir,
                clip_index,
                reference_image_path=still,
                cancel_event=cancel_event,
                mode4_veo_flow_flower=False,
                flow_max_attempts=flow_n,
                video_aspect_ratio=aspect,
            )
        p = Path(raw) if raw else None
        return p if p and p.is_file() else None

    clip = await _from_keyframes()
    if clip:
        logger.info(
            "[Mode5] still→motion clip {} via keyframes (start=end={})",
            clip_index,
            still.name,
        )
        return clip
    logger.warning(
        "[Mode5] still→motion clip {}: keyframes failed after {} attempts; trying normal+reference",
        clip_index,
        flow_n,
    )
    clip = await _from_single_ref()
    if clip:
        logger.info("[Mode5] still→motion clip {} via Flow+reference (fallback)", clip_index)
    return clip


async def _mode5_animate_still_preview_clip(
    *,
    motion_prompt: str,
    output_dir: Path,
    still_path: Path,
    clip_index: int,
    backend: str,
    cancel_event: threading.Event | None = None,
) -> Path | None:
    """Короткая анимация still → mp4 для intro preview (keyframes start=end=still)."""
    return await _mode5_animate_still_to_motion_clip(
        motion_prompt=motion_prompt,
        output_dir=output_dir,
        still_path=still_path,
        clip_index=clip_index,
        backend=backend,
        cancel_event=cancel_event,
    )


async def _generate_mode5_intro_confirmation_pool(
    *,
    session_id: str,
    sub_mode: str | None,
    style_lock: str,
    topic_seed: str,
    pool_size_override: int | None = None,
    image_backend: str | None = None,
    cancel_event: threading.Event | None = None,
) -> list[str]:
    """
    Generate fixed pool of animated preview clips before full long-mode pipeline starts.
    Returns session-relative mp4 paths (can be empty on failure).
    """
    backend = _normalize_mode5_image_backend(
        image_backend if image_backend is not None else getattr(settings, "mode5_image_backend", "playwright")
    )
    http_base = str(getattr(settings, "fastgen_http_base_url", "") or "").strip()
    if backend == "api" and not http_base:
        raise RuntimeError("FASTGEN_HTTP_BASE_URL is required for MODE5_IMAGE_BACKEND=api")

    m5dir = _mode5_dir(session_id)
    session_root = _session_dir(session_id)
    pool_size = int(pool_size_override) if pool_size_override is not None else _mode5_block_loop_pool_size()
    pool_size = max(1, min(20, pool_size))
    seed = re.sub(r"\s+", " ", (topic_seed or "").strip())[:1200] or "long-form topic"
    visual_brief = await _mode5_visual_topic_brief(seed, sub_mode)
    run_nonce = f"{int(time.time() * 1000)}_{random.randint(1000, 9999)}"
    story_prompts = await _mode5_intro_photo_story_prompts(
        seed, sub_mode, pool_size, run_nonce=run_nonce
    )
    topic_lock = _mode5_intro_topic_lock(seed)
    parallel = min(pool_size, _mode5_intro_pool_parallel())
    sem = asyncio.Semaphore(parallel)
    out_rels_by_index: list[str | None] = [None] * pool_size

    async def _generate_one_intro(i: int) -> None:
        story_seed = story_prompts[i] if i < len(story_prompts) else seed
        still_path = m5dir / f"block_loop_{i:04d}_still.jpg"
        out_path = m5dir / f"block_loop_{i:04d}.mp4"
        img_prompt = _build_mode5_intro_still_prompt(
            sub_mode=sub_mode,
            topic_seed=f"{seed}. STRICT TOPIC LOCK: {topic_lock or seed[:120]}",
            visual_brief=visual_brief,
            story_prompt=story_seed,
            variant_index=i,
            variants_total=pool_size,
        )
        img_prompt = _sanitize_mode5_image_prompt(img_prompt)
        async with sem:
            await _generate_one_image(
                img_prompt,
                still_path,
                aspect_ratio=_mode5_image_aspect_ratio(),
                image_backend=backend,
                cancel_event=cancel_event,
            )
        if not still_path.is_file():
            raise RuntimeError(f"Mode5 intro still image was not generated (variant {i + 1}/{pool_size}).")

        motion_prompt = _build_mode5_intro_single_motion_prompt(
            sub_mode=sub_mode,
            topic_seed=seed,
            visual_brief=visual_brief,
            story_prompt=story_seed,
            variant_index=i,
            variants_total=pool_size,
        )
        async with sem:
            clip = await _mode5_animate_still_preview_clip(
                motion_prompt=motion_prompt,
                output_dir=m5dir,
                still_path=still_path,
                clip_index=99001 + i,
                backend=backend,
                cancel_event=cancel_event,
            )
        if not clip or not clip.is_file():
            raise RuntimeError(
                f"Mode5 intro preview variant {i + 1}/{pool_size} was not generated "
                f"(backend={backend}, still={still_path.name})."
            )
        try:
            _mode5_reencode_intro_preview_for_web(clip, out_path)
        except Exception as enc_err:
            logger.warning(f"[Mode5] intro preview reencode failed; fallback copy: {enc_err}")
            shutil.copy2(clip, out_path)
        if clip.resolve() != out_path.resolve():
            try:
                clip.unlink()
            except OSError:
                pass
        out_rels_by_index[i] = _rel_session(session_root, out_path)

    logger.info("[Mode5] Intro confirmation pool: generating {} item(s), parallel={}", pool_size, parallel)
    await asyncio.gather(*[_generate_one_intro(i) for i in range(pool_size)])
    return [rel for rel in out_rels_by_index if rel]


async def _regenerate_mode5_intro_confirmation_item(
    *,
    session_id: str,
    sub_mode: str | None,
    topic_seed: str,
    target_index: int,
    total_variants: int,
    image_backend: str | None = None,
) -> str:
    """Regenerate a single intro preview clip by index without touching other pool items."""
    backend = _normalize_mode5_image_backend(
        image_backend if image_backend is not None else getattr(settings, "mode5_image_backend", "playwright")
    )
    http_base = str(getattr(settings, "fastgen_http_base_url", "") or "").strip()
    if backend == "api" and not http_base:
        raise RuntimeError("FASTGEN_HTTP_BASE_URL is required for MODE5_IMAGE_BACKEND=api")

    if target_index < 0:
        raise ValueError("target_index must be >= 0")
    total = max(1, int(total_variants or 1))
    idx = int(target_index)
    m5dir = _mode5_dir(session_id)
    session_root = _session_dir(session_id)
    seed = re.sub(r"\s+", " ", (topic_seed or "").strip())[:1200] or "long-form topic"
    visual_brief = await _mode5_visual_topic_brief(seed, sub_mode)
    # Generate one story seed for this specific variant only.
    run_nonce = f"{int(time.time() * 1000)}_{idx}_{random.randint(1000, 9999)}"
    story_prompts = await _mode5_intro_photo_story_prompts(
        seed,
        sub_mode,
        1,
        run_nonce=run_nonce,
    )
    story_seed = story_prompts[0] if story_prompts else seed
    topic_lock = _mode5_intro_topic_lock(seed)

    still_path = m5dir / f"block_loop_{idx:04d}_still.jpg"
    out_path = m5dir / f"block_loop_{idx:04d}.mp4"
    img_prompt = _build_mode5_intro_still_prompt(
        sub_mode=sub_mode,
        topic_seed=f"{seed}. STRICT TOPIC LOCK: {topic_lock or seed[:120]}",
        visual_brief=visual_brief,
        story_prompt=story_seed,
        variant_index=idx,
        variants_total=total,
    )
    img_prompt = _sanitize_mode5_image_prompt(img_prompt)
    await _generate_one_image(
        img_prompt,
        still_path,
        aspect_ratio=_mode5_image_aspect_ratio(),
        image_backend=backend,
    )
    if not still_path.is_file():
        raise RuntimeError("Mode5 intro still image was not generated.")

    motion_prompt = _build_mode5_intro_single_motion_prompt(
        sub_mode=sub_mode,
        topic_seed=seed,
        visual_brief=visual_brief,
        story_prompt=story_seed,
        variant_index=idx,
        variants_total=total,
    )
    clip = await _mode5_animate_still_preview_clip(
        motion_prompt=motion_prompt,
        output_dir=m5dir,
        still_path=still_path,
        clip_index=99001 + idx,
        backend=backend,
    )
    if not clip or not clip.is_file():
        raise RuntimeError(
            f"Mode5 intro preview variant {idx + 1}/{total} was not generated (backend={backend})."
        )
    try:
        _mode5_reencode_intro_preview_for_web(clip, out_path)
    except Exception as enc_err:
        logger.warning(f"[Mode5] intro preview reencode failed; fallback copy: {enc_err}")
        shutil.copy2(clip, out_path)
    if clip.resolve() != out_path.resolve():
        try:
            clip.unlink()
        except OSError:
            pass
    return _rel_session(session_root, out_path)


def _build_mode5_block_loop_video_prompt(
    *,
    sub_mode: str | None,
    block_index: int,
    block_sec: float,
    narration_snippet: str,
    prev_snippet: str,
    book_anchor: str = "",
) -> str:
    prev = re.sub(r"\s+", " ", (prev_snippet or "").strip())[:520]
    narr = re.sub(r"\s+", " ", (narration_snippet or "").strip())[:2000]
    minutes = max(1, int(block_sec // 60))
    anchor = re.sub(r"\s+", " ", (book_anchor or "").strip())[:280]
    motion_anchors = _mode5_motion_anchor_pack(f"{narr}. {anchor}", normalize_mode5_sub_mode(sub_mode))
    mode_line = _mode5_submode_animation_directive(sub_mode)
    parts = [
        "Create a loopable painterly-cinematic motion clip from the provided start and end keyframes.",
        "Keep a subtle animation-style look (soft semi-cartoon stylization) while preserving stable geometry and readable depth.",
        "Location must be narratively specific: pick a place that directly matches the spoken theme for this block, not a generic interior.",
        "Prop discipline: foreground/midground/background elements must be theme-relevant (tools, artifacts, decor, textures tied to narration).",
        "Keep the camera fixed; animate depth layers and environmental micro-motion only so the loop feels like living scenery, not a sliding photograph.",
        "Design one clear animation beat-map for the loop: primary motion subject, secondary support motion, and ambient background pulse.",
        f"Motion anchor lock: animate only these scene elements and keep all others stable: {motion_anchors}",
        "Avoid primitive motion: no single-direction global drift, no synchronized all-elements sway, no flat wallpaper movement.",
        mode_line,
        _MODE5_INTRO_ANIMATION_DESCRIPTION,
        f"This clip will be tiled for about {minutes} minutes of narration; motion must stay subtle and perfectly loopable.",
        f"Narration theme for this block: {narr}",
    ]
    if anchor:
        parts.append(
            "Tie the scene directly to this book/series topic using literal location and concrete props from that world; "
            "no readable titles, author names, book covers, or logos: "
            + anchor
        )
    if block_index > 0 and prev:
        parts.append(
            "Visually differentiate this block from the previous one: new focal subject, lighting, palette, or setting. "
            f"Do not repeat this prior motif: {prev}"
        )
    parts.append(
        "No readable text, no logos, no UI. Start and end keyframes must align so the loop is invisible when repeated."
    )
    return " ".join(parts)


def _build_mode5_block_loop_motion_from_still_prompt(
    *,
    sub_mode: str | None,
    block_index: int,
    block_sec: float,
    narration_snippet: str,
    prev_snippet: str,
    book_anchor: str = "",
) -> str:
    """Промпт для image→video: painterly/semi-cartoon block still, микродвижение и бесшовный loop при тайлинге."""
    prev = re.sub(r"\s+", " ", (prev_snippet or "").strip())[:520]
    narr = re.sub(r"\s+", " ", (narration_snippet or "").strip())[:2000]
    minutes = max(1, int(block_sec // 60))
    anchor = re.sub(r"\s+", " ", (book_anchor or "").strip())[:280]
    motion_anchors = _mode5_motion_anchor_pack(f"{narr}. {anchor}", normalize_mode5_sub_mode(sub_mode))
    mode_line = _mode5_submode_animation_directive(sub_mode)
    parts = [
        "Animate the provided painterly/semi-cartoon keyframe into a short clip built for seamless looping when tiled.",
        "Do not change to an unrelated location or replace theme props with generic room filler.",
        "Preserve the exact composition, character shapes, props, line style, and color script from the still; "
        "add only in-frame ambient motion (layers swaying, light breathing, particles) that completes one full cycle "
        "back to the identical rest pose at the last frame — camera locked, no whole-frame drift.",
        "Motion direction: create at least two independent motion tracks with different tempo/phase so the shot feels alive, "
        "while each track stays subtle and readable.",
        f"Motion anchor lock: animate only these scene elements from the still: {motion_anchors}",
        mode_line,
        _MODE5_INTRO_ANIMATION_DESCRIPTION,
        f"This clip will repeat for about {minutes} minutes under narration — the join between end and start must be invisible.",
        f"Mood and story beat for this block (spoken): {narr}",
    ]
    if anchor:
        parts.append(
            "Use this book/topic as a literal scene constraint for place and props (not abstract symbolism) — "
            "never readable titles, spines, screens with text, or logos: "
            + anchor
        )
    if block_index > 0 and prev:
        parts.append(
            "Shift mood or palette from the previous block so chapters feel distinct; do not copy the prior motif: "
            + prev
        )
    parts.append("No readable text, no logos, no UI.")
    return " ".join(parts)


def _build_mode5_block_loop_motion_half_a_prompt(
    *,
    sub_mode: str | None,
    block_index: int,
    block_sec: float,
    narration_snippet: str,
    prev_snippet: str,
    book_anchor: str = "",
) -> str:
    """Часть 1/2: motion от opening still к «середине» цикла; последний кадр = старт части 2."""
    prev = re.sub(r"\s+", " ", (prev_snippet or "").strip())[:520]
    narr = re.sub(r"\s+", " ", (narration_snippet or "").strip())[:2000]
    minutes = max(1, int(block_sec // 60))
    anchor = re.sub(r"\s+", " ", (book_anchor or "").strip())[:280]
    mode_line = _mode5_submode_animation_directive(sub_mode)
    parts = [
        "PART 1 of 2 for a closed-loop wallpaper clip (will be concatenated with part 2). "
        "Animate this painterly/semi-cartoon opening keyframe as the FIRST HALF of a single ambient cycle: "
        "only in-frame element motion (parallax layers, sway, shimmer, particles) with camera locked — no frame-wide pan/zoom.",
        "Keep location and major props tied to the narration topic; no generic substitute room.",
        "Preserve art style, line quality, and palette from the still; push motion through foreground/midground details, not sliding the whole painting.",
        "Part-1 rhythm: establish motion motifs (for example fabric sway + light pulse + particles) and reach a controlled mid-cycle peak.",
        mode_line,
        "The LAST frame must be a clean, stable midpoint of that cycle (readable silhouette) — part 2 completes the second half back to the opening still.",
        _MODE5_INTRO_ANIMATION_DESCRIPTION,
        f"Narration context (~{minutes} min block): {narr}",
    ]
    if anchor:
        parts.append(
            "Keep environment and props literally tied to this book/topic (no readable text, covers, logos): " + anchor
        )
    if block_index > 0 and prev:
        parts.append("Visually distinct from prior block; avoid repeating: " + prev)
    parts.append("No readable text, no logos, no UI.")
    return " ".join(parts)


def _build_mode5_block_loop_motion_half_b_keyframe_prompt(
    *,
    sub_mode: str | None,
    block_index: int,
    block_sec: float,
    narration_snippet: str,
    prev_snippet: str,
    book_anchor: str = "",
) -> str:
    """Часть 2/2: keyframes start = midpoint (конец части 1), end = opening still — замыкает цикл."""
    prev = re.sub(r"\s+", " ", (prev_snippet or "").strip())[:520]
    narr = re.sub(r"\s+", " ", (narration_snippet or "").strip())[:2000]
    minutes = max(1, int(block_sec // 60))
    anchor = re.sub(r"\s+", " ", (book_anchor or "").strip())[:280]
    mode_line = _mode5_submode_animation_directive(sub_mode)
    parts = [
        "PART 2 of 2 for a closed-loop wallpaper clip (concatenated after part 1). "
        "Interpolate from the provided START keyframe (the shared midpoint image that must match the last frame of part 1) "
        "to the provided END keyframe (the original opening painterly frame).",
        "This is the SECOND HALF of the same ambient cycle as part 1: continue the same element motion language "
        "(sway, parallax, light, particles) with camera still locked — do not introduce a new opposite camera move.",
        "Keep the same topic-linked place and object set; only motion state changes are allowed.",
        "Part-2 rhythm: resolve the established motion motifs back to rest state with clean easing and no abrupt reversals.",
        mode_line,
        "Motion must decelerate smoothly into the end pose so it matches the end keyframe pixel-loyally: "
        "same composition, characters, props, and lighting as the opening still.",
        "When part1+part2 play in order and the file loops, the viewer should not perceive a jump at any join.",
        _MODE5_INTRO_ANIMATION_DESCRIPTION,
        f"Narration context (~{minutes} min block): {narr}",
    ]
    if anchor:
        parts.append("Thematic continuity via same literal place/props (no readable text): " + anchor)
    if block_index > 0 and prev:
        parts.append("Avoid repeating prior block motif: " + prev)
    parts.append("No readable text, no logos, no UI.")
    return " ".join(parts)


def _build_mode5_block_loop_bridge_still_prompt(
    *,
    sub_mode: str | None,
    block_index: int,
    block_sec: float,
    narration_snippet: str,
    book_anchor: str = "",
) -> str:
    """
    Отдельный JPEG «середина цикла»: тот же мир, что opening still, но чуть сдвинутое состояние для start/end-видео.
    Генерируется через image+reference(still), затем part A = video(still→bridge), part B = video(bridge→still).
    """
    narr = re.sub(r"\s+", " ", (narration_snippet or "").strip())[:1200]
    minutes = max(1, int(block_sec // 60))
    anchor = re.sub(r"\s+", " ", (book_anchor or "").strip())[:240]
    mode_line = _mode5_submode_animation_directive(sub_mode)
    parts = [
        "BLOCK_LOOP_MID_KEYFRAME: using the attached opening frame as the strict reference for characters, "
        "scale, palette, line style, location, and prop layout, generate exactly ONE new full-frame still that is the "
        "MIDPOINT of a subtle ambient-motion cycle (halfway between the reference's rest pose and a gentle peak of motion).",
        "Do not replace the location with a generic room: preserve theme-linked environment and theme-linked props from the reference.",
        mode_line,
        "Same environment and story beat; only micro-changes: cloth or hair offset, foliage or fabric sway, steam or dust, "
        "soft light shift, small particle positions — no new objects, no teleporting elements, no camera reframing, "
        "no crop change, no different room.",
        f"This midpoint image will be the shared boundary between two FastGen start/end video clips for ~{minutes} min of narration.",
        f"Spoken context that must map to a literal place/props/action: {narr}",
    ]
    if anchor:
        parts.append("Thematic echo only (no readable titles, spines, screens, logos): " + anchor)
    if block_index > 0:
        parts.append("Keep a fresh composition versus prior blocks while still matching the attached reference.")
    parts.append(
        "Absolutely no visible text, letters, numbers, UI, logos, or watermarks. "
        "One continuous painterly frame only — not a collage or split layout."
    )
    return " ".join(parts)


def _mode5_probe_video_duration_sec(path: Path) -> float:
    ff = resolve_ffmpeg_executable()
    probe = None
    if ff:
        candidate = Path(ff).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
        if candidate.is_file():
            probe = str(candidate)
    probe = probe or shutil.which("ffprobe")
    if not probe:
        raise RuntimeError("ffprobe not found")
    cmd = [
        probe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=90)
    return max(0.05, float((r.stdout or "1").strip()))


def _mode5_effective_loop_duration_sec(path: Path) -> float:
    """
    Remove likely static tail from generated short loops.
    Keeps a safe minimum so we never over-trim short clips.
    """
    dur = _mode5_probe_video_duration_sec(path)
    # Не использовать «or 1.6»: при 0.0 Python считает falsy и подставлялась бы обрезка хвоста всегда.
    try:
        trim_tail = float(getattr(settings, "mode5_loop_trim_tail_sec", 0.0))
    except (TypeError, ValueError):
        trim_tail = 0.0
    trim_tail = max(0.0, min(3.0, trim_tail))
    if trim_tail <= 1e-3:
        return dur
    # Keep at least 55% of the original, and never less than 2.6s.
    min_keep = max(2.6, dur * 0.55)
    effective = max(min_keep, dur - trim_tail)
    # Also trim to the first detected freeze-start if model settles too early.
    freeze_start = _mode5_detect_freeze_start_sec(path)
    if freeze_start is not None:
        # Keep a small safety margin before fully static region.
        effective = min(effective, max(1.8, freeze_start - 0.08))
    return min(dur, effective)


def _mode5_detect_freeze_start_sec(path: Path) -> float | None:
    """
    Detect first freeze region in clip using ffmpeg freezedetect.
    Returns freeze start seconds or None.
    """
    ff = resolve_ffmpeg_executable()
    if not ff or (not path.is_file()):
        return None
    # Slightly lenient noise threshold; tuned for generated clips with tiny compression shimmer.
    freeze_noise = float(getattr(settings, "mode5_freeze_detect_noise", 0.0018) or 0.0018)
    freeze_noise = max(0.0005, min(0.01, freeze_noise))
    freeze_min_dur = float(getattr(settings, "mode5_freeze_detect_min_sec", 0.35) or 0.35)
    freeze_min_dur = max(0.12, min(2.0, freeze_min_dur))
    cmd = [
        ff,
        "-v",
        "info",
        "-i",
        str(path),
        "-vf",
        f"freezedetect=n={freeze_noise:.6f}:d={freeze_min_dur:.3f}",
        "-an",
        "-f",
        "null",
        "-",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=180)
        blob = f"{r.stdout or ''}\n{r.stderr or ''}"
        m = re.search(r"freeze_start:\s*([0-9]+(?:\.[0-9]+)?)", blob)
        if not m:
            return None
        return max(0.0, float(m.group(1)))
    except Exception:
        return None


def _mode5_trim_loop_tail_inplace(path: Path) -> None:
    """
    Trim the dead tail of a generated loop clip in-place.
    """
    ff = resolve_ffmpeg_executable()
    if not ff:
        raise RuntimeError("ffmpeg not found")
    if not path.is_file():
        return
    src_dur = _mode5_probe_video_duration_sec(path)
    keep_dur = _mode5_effective_loop_duration_sec(path)
    if keep_dur >= src_dur - 0.12:
        return
    tmp = path.with_suffix(".trimtmp.mp4")
    cmd = [
        ff,
        "-y",
        "-i",
        str(path),
        "-t",
        f"{keep_dur:.3f}",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(tmp),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=1800)
    tmp.replace(path)


def _mode5_extract_last_frame_jpeg(video: Path, dest: Path) -> None:
    """Последний кадр (с небольшим отступом от EOF, чтобы не поймать чёрный кадр)."""
    ff = resolve_ffmpeg_executable()
    if not ff:
        raise RuntimeError("ffmpeg not found")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dur = _mode5_probe_video_duration_sec(video)
    tail = max(0.0, dur - 0.06)
    cmd = [
        ff,
        "-y",
        "-ss",
        f"{tail:.4f}",
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(dest),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)


def _mode5_concat_two_block_loop_parts(a: Path, b: Path, out: Path) -> None:
    """Склейка A+B в один H.264 с выравниванием под mode5 разрешение и более высоким качеством."""
    ff = resolve_ffmpeg_executable()
    if not ff:
        raise RuntimeError("ffmpeg not found")
    tw, th = settings.mode5_video_resolution
    crf = int(getattr(settings, "mode5_block_loop_concat_crf", 17) or 17)
    crf = max(15, min(28, crf))
    preset = str(getattr(settings, "mode5_block_loop_concat_preset", "slow") or "slow").strip()
    if preset not in (
        "ultrafast",
        "superfast",
        "veryfast",
        "faster",
        "fast",
        "medium",
        "slow",
        "slower",
        "veryslow",
    ):
        preset = "slow"
    out.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        f"[0:v]scale={tw}:{th}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[v0];"
        f"[1:v]scale={tw}:{th}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[v1];"
        f"[v0][v1]concat=n=2:v=1:a=0[outv]"
    )
    cmd = [
        ff,
        "-y",
        "-i",
        str(a),
        "-i",
        str(b),
        "-filter_complex",
        vf,
        "-map",
        "[outv]",
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(out),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=3600)


def _mode5_reencode_intro_preview_for_web(src: Path, out: Path) -> None:
    """
    Intro preview for UI: one trimmed loop cycle, then N identical copies concatenated
    (default N=2) so the join between repeats is visible (~8s + ~8s).
    """
    ff = resolve_ffmpeg_executable()
    if not ff:
        raise RuntimeError("ffmpeg not found")
    tw, th = settings.mode5_video_resolution
    cycles = int(getattr(settings, "mode5_intro_preview_loop_cycles", 2) or 2)
    cycles = max(1, min(4, cycles))
    crop_ratio = mode5_watermark_bottom_crop_ratio()
    src_keep_sec = _mode5_effective_loop_duration_sec(src)
    out.parent.mkdir(parents=True, exist_ok=True)
    core_src = out.with_suffix(".loopcore.mp4")
    cmd = [
        ff,
        "-y",
        "-stream_loop",
        "-1",
        "-i",
        str(src),
        "-t",
        f"{src_keep_sec:.3f}",
        "-map",
        "0:v:0",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(core_src),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=1800)
    try:
        if cycles == 1:
            cmd = [
                ff,
                "-y",
                "-i",
                str(core_src),
                "-map",
                "0:v:0",
                "-vf",
                f"crop=iw:ih-ceil(ih*{crop_ratio:.4f}):0:0,"
                f"scale={tw}:{th}:force_original_aspect_ratio=decrease:flags=lanczos,"
                f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-an",
                str(out),
            ]
            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=1800)
        elif cycles == 2:
            _mode5_concat_two_block_loop_parts(core_src, core_src, out)
        else:
            lst = out.with_suffix(".concat_list.txt")
            lines = ["ffconcat version 1.0\n"]
            for _ in range(cycles):
                lines.append(f"file '{core_src.resolve().as_posix()}'\n")
            lst.write_text("".join(lines), encoding="utf-8")
            vf = (
                f"crop=iw:ih-ceil(ih*{crop_ratio:.4f}):0:0,"
                f"scale={tw}:{th}:force_original_aspect_ratio=decrease:flags=lanczos,"
                f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p"
            )
            cmd = [
                ff,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(lst),
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-an",
                str(out),
            ]
            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=3600)
            try:
                lst.unlink(missing_ok=True)
            except OSError:
                pass
        logger.info(
            "[Mode5] Intro preview {}: {:.2f}s/cycle × {} cycles (seam check at joins)",
            out.name,
            src_keep_sec,
            cycles,
        )
    finally:
        try:
            core_src.unlink(missing_ok=True)
        except OSError:
            pass


def _mode5_block_loop_can_reuse_smart_cache(
    *,
    out_path: Path,
    still_path: Path,
    fp_path: Path,
    fp_payload: str,
    force: bool,
) -> bool:
    if force:
        return False
    if not out_path.is_file() or not still_path.is_file() or not fp_path.is_file():
        return False
    try:
        want = fp_path.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    if want != fp_payload.strip():
        return False
    try:
        vm = float(out_path.stat().st_mtime)
        sm = float(still_path.stat().st_mtime)
    except OSError:
        return False
    return vm >= sm - 1.0


def _mode5_block_rows_max_image_mtime(
    session_root: Path,
    rows: list[tuple[dict[str, Any], dict[str, Any], float, float]],
) -> float | None:
    """Максимальный mtime JPEG по всем сегментам блока; None если путь отсутствует."""
    latest: float | None = None
    for _ch, seg, _t0, _d in rows:
        rel = str(seg.get("image") or "").strip()
        if not rel:
            return None
        p = session_root / rel
        if not p.is_file():
            return None
        try:
            m = float(p.stat().st_mtime)
        except OSError:
            return None
        latest = m if latest is None else max(latest, m)
    return latest


def _mode5_block_loop_pool_size() -> int:
    n = int(getattr(settings, "mode5_block_loop_pool_size", 5) or 5)
    return max(1, min(20, n))


async def _ensure_mode5_block_loop_videos(
    session_id: str,
    plan: dict[str, Any],
    *,
    force: bool = False,
    target_block_ids: set[int] | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    """
    Для длинного Mode5: один короткий motion-клип на «блок» wall-clock (MODE5_BLOCK_LOOP_SECONDS),
    общий файл для всех сегментов блока. При сборке превью/финала этот MP4 только зацикливается под
    длину каждого seg_*.wav; озвучка остаётся прежней — отдельный WAV на сегмент, склейка по порядку
    (см. assemble_mode5_video: seg_audio + concatenate_audioclips).

    При ``mode5_block_loop_still_then_animate`` (по умолчанию True): для каждого блока сначала FastGen‑still,
    затем motion через FastGen «Ключ. кадры» (start=end=тот же still) для замкнутого loop; при сбое — «Обычный»
    режим с одним референсом. При ``mode5_block_loop_two_part_loop`` — два клипа (A+B, см. конфиг); иначе один keyframe‑клип.
    Затем тот же MP4 зацикливается на ``mode5_block_loop_seconds``.

    Кэш: smart — по ``narr_fp`` + mtime still/mp4; legacy — mtime сегментных JPEG vs mp4.
    """
    if not _mode5_block_loop_applies(plan):
        return
    backend = _normalize_mode5_image_backend(
        plan.get("image_backend")
        if plan.get("image_backend") is not None
        else getattr(settings, "mode5_image_backend", "playwright")
    )
    http_base = str(getattr(settings, "fastgen_http_base_url", "") or "").strip()
    if backend == "api" and not http_base:
        logger.warning("[Mode5] Block loop video: FASTGEN_HTTP_BASE_URL пуст для backend=api — пропускаем motion-блоки")
        return

    session_root = _session_dir(session_id)
    m5dir = _mode5_dir(session_id)
    m5dir.mkdir(parents=True, exist_ok=True)

    def _remove_block_files(bid: int) -> None:
        for p in (
            m5dir / f"block_loop_{bid:04d}.mp4",
            m5dir / f"block_loop_{bid:04d}_still.jpg",
            m5dir / f"block_loop_{bid:04d}.narr_fp",
            m5dir / f"block_loop_{bid:04d}_bridge.jpg",
            m5dir / f"block_loop_{bid:04d}_half_a.mp4",
            m5dir / f"block_loop_{bid:04d}_half_b.mp4",
        ):
            if p.is_file():
                try:
                    p.unlink()
                except OSError:
                    pass

    chunks = sorted(plan.get("chunks") or [], key=lambda c: int(c.get("index") or 0))
    block_sec = float(getattr(settings, "mode5_block_loop_seconds", 1800.0) or 1800.0)
    block_sec = max(60.0, min(14400.0, block_sec))
    pool_size = _mode5_block_loop_pool_size()
    # In test mode we must keep exactly one animated block.
    if bool(plan.get("test_run")):
        pool_size = 1
    chunk_texts = [
        re.sub(r"\s+", " ", str(ch.get("text") or ch.get("fact_hint") or "").strip())
        for ch in chunks
        if re.sub(r"\s+", " ", str(ch.get("text") or ch.get("fact_hint") or "").strip())
    ]

    def _seed_narration_for_block(block_id: int) -> str:
        if not chunk_texts:
            return re.sub(r"\s+", " ", str(plan.get("facts_topic") or plan.get("header_title") or "").strip())[:2400]
        picks = [chunk_texts[i] for i in range(block_id, len(chunk_texts), max(1, pool_size))]
        if not picks:
            picks = chunk_texts[: min(3, len(chunk_texts))]
        return " ".join(picks)[:2400]

    timeline: list[tuple[dict[str, Any], dict[str, Any], float, float]] = []
    cumulative = 0.0
    for ch in chunks:
        segs = sorted((ch.get("segments") or []), key=lambda s: int(s.get("s", 0)))
        for seg in segs:
            aud_rel = str(seg.get("audio") or "").strip()
            if not aud_rel:
                continue
            ap = session_root / aud_rel
            if not ap.is_file():
                continue
            dur = _wav_duration_sec(ap)
            t0 = cumulative
            timeline.append((ch, seg, t0, dur))
            cumulative += dur

    if not timeline:
        logger.info("[Mode5] Block loop video: WAV timeline missing, generating pool independently from audio")

    # Intro-confirm contract: after approval, reuse approved intro preview videos
    # as block-loop sources instead of spawning new still/video generations.
    intro_pool = [str(x).strip() for x in (plan.get("intro_preview_videos") or []) if str(x).strip()]
    intro_single = str(plan.get("intro_preview_video") or "").strip()
    if (not intro_pool) and intro_single:
        intro_pool = [intro_single]
    intro_pool_existing: list[str] = []
    for rel in intro_pool:
        p = session_root / rel
        if p.is_file():
            intro_pool_existing.append(rel)
    if intro_pool_existing and not force:
        normalized_intro_pool: list[str] = []
        for idx, src_rel in enumerate(intro_pool_existing):
            src_abs = session_root / src_rel
            if not src_abs.is_file():
                continue
            norm_abs = m5dir / f"block_loop_intro_core_{idx:04d}.mp4"
            norm_rel = _rel_session(session_root, norm_abs)
            need_refresh = True
            if norm_abs.is_file():
                try:
                    need_refresh = float(norm_abs.stat().st_mtime) + 0.2 < float(src_abs.stat().st_mtime)
                except OSError:
                    need_refresh = True
            if need_refresh:
                try:
                    shutil.copy2(src_abs, norm_abs)
                    _mode5_trim_loop_tail_inplace(norm_abs)
                except Exception as trim_err:
                    logger.warning(
                        "[Mode5] Intro preview core {} trim failed, fallback to source: {}",
                        idx,
                        trim_err,
                    )
                    norm_rel = src_rel
            normalized_intro_pool.append(norm_rel)
        if not normalized_intro_pool:
            normalized_intro_pool = intro_pool_existing
        for ch, seg, t0, _dur in timeline:
            bid_raw = int(t0 // block_sec)
            bid = min(bid_raw, max(0, pool_size - 1))
            src_rel = normalized_intro_pool[min(bid, len(normalized_intro_pool) - 1)]
            seg["video"] = src_rel
            seg["asset_type"] = "video"
            ch["block_loop_id"] = int(bid)
        mode_tag = "test run" if bool(plan.get("test_run")) else "standard run"
        logger.info(
            "[Mode5] {}: reusing approved intro preview pool as block-loop source(s), count={}",
            mode_tag,
            len(normalized_intro_pool),
        )
        return

    blocks: dict[int, list[tuple[dict[str, Any], dict[str, Any], float, float]]] = {}
    for ch, seg, t0, dur in timeline:
        bid_raw = int(t0 // block_sec)
        bid = min(bid_raw, pool_size - 1)
        blocks.setdefault(bid, []).append((ch, seg, t0, dur))

    target_ids: set[int] | None = (
        {int(x) for x in target_block_ids} if target_block_ids else None
    )
    if target_ids:
        missing = [x for x in sorted(target_ids) if x < 0 or x >= pool_size]
        if missing:
            raise ValueError(f"Mode5 block loop: unknown block ids {missing}")

    if force:
        if target_ids:
            for bid in sorted(target_ids):
                _remove_block_files(bid)
                for _ch, seg, _t0, _d in blocks.get(bid, []):
                    seg.pop("video", None)
                    seg.pop("asset_type", None)
        else:
            for bid in range(pool_size):
                _remove_block_files(bid)
            for ch in plan.get("chunks") or []:
                for seg in ch.get("segments") or []:
                    seg.pop("video", None)
                    seg.pop("asset_type", None)

    book_anchor = _mode5_block_loop_series_anchor(plan)
    from agents.content_generator import fastgen_http, fastgen_playwright

    smart_still = bool(getattr(settings, "mode5_block_loop_still_then_animate", True))
    block_ids = [
        bid
        for bid in range(pool_size)
        if target_ids is None or bid in target_ids
    ]
    parallel = min(len(block_ids), _mode5_block_loop_parallel()) if block_ids else 1
    block_sem = asyncio.Semaphore(max(1, parallel))
    logger.info("[Mode5] Block loop video: {} block(s), parallel={}", len(block_ids), parallel)

    async def _process_block_loop(bid: int) -> None:
        async with block_sem:
            await _process_block_loop_unbounded(bid)

    async def _process_block_loop_unbounded(bid: int) -> None:
        rows = blocks.get(bid, [])
        for ch, _seg, _t0, _d in rows:
            ch["block_loop_id"] = int(bid)
        out_path = m5dir / f"block_loop_{bid:04d}.mp4"
        still_path = m5dir / f"block_loop_{bid:04d}_still.jpg"
        fp_path = m5dir / f"block_loop_{bid:04d}.narr_fp"
        rel = _rel_session(session_root, out_path)

        # IMPORTANT: block-loop generation must be content-driven and independent from per-segment audio slices.
        # Audio timeline is used only later for mapping/overlay, not as the source of block generation intent.
        narr = _seed_narration_for_block(bid)
        fp_payload = hashlib.sha256(
            (narr + "\n" + _MODE5_BLOCK_LOOP_CACHE_SALT + "\n" + book_anchor).encode("utf-8", errors="ignore")
        ).hexdigest()

        reuse_cached_mp4 = False
        if not force:
            if smart_still and _mode5_block_loop_can_reuse_smart_cache(
                out_path=out_path,
                still_path=still_path,
                fp_path=fp_path,
                fp_payload=fp_payload,
                force=False,
            ):
                reuse_cached_mp4 = True
            elif not smart_still and out_path.is_file():
                try:
                    video_mtime = float(out_path.stat().st_mtime)
                except OSError:
                    video_mtime = 0.0
                img_mtime_max = _mode5_block_rows_max_image_mtime(session_root, rows)
                if img_mtime_max is not None and img_mtime_max <= video_mtime + 1.5:
                    reuse_cached_mp4 = True
                elif img_mtime_max is not None:
                    logger.info(
                        "[Mode5] Block loop {:04d}: изображения новее {}, пересоздаём motion",
                        bid,
                        out_path.name,
                    )
                    try:
                        out_path.unlink()
                    except OSError:
                        pass

        if reuse_cached_mp4:
            for ch, seg, _t0, _d in rows:
                seg["video"] = rel
                seg["asset_type"] = "video"
            return

        img_a = session_root / rows[0][1]["image"] if rows else None
        img_b = session_root / rows[-1][1]["image"] if rows else None
        motion_ok = False

        if smart_still:
            try:
                fp_disk = ""
                if fp_path.is_file():
                    fp_disk = fp_path.read_text(encoding="utf-8", errors="ignore").strip()
                need_new_still = force or (not still_path.is_file()) or (fp_disk != fp_payload.strip())
                if need_new_still:
                    _bridge_u = m5dir / f"block_loop_{bid:04d}_bridge.jpg"
                    _half_au = m5dir / f"block_loop_{bid:04d}_half_a.mp4"
                    _half_bu = m5dir / f"block_loop_{bid:04d}_half_b.mp4"
                    for p in (out_path, still_path, fp_path, _bridge_u, _half_au, _half_bu):
                        if p.is_file():
                            try:
                                p.unlink()
                            except OSError:
                                pass
                    style_lock = _ensure_mode5_style_lock(plan)
                    minutes = max(1, int(block_sec // 60))
                    book_line = ""
                    if book_anchor:
                        book_line = (
                            f"The episode centers on this book or topic (literal scene cues only — no readable titles, "
                            f"spines, screens, or logos): «{book_anchor}». "
                            "Translate it into concrete location and concrete props that are directly implied by the narration excerpt. "
                        )
                    still_ctx = (
                        f"BLOCK_LOOP_HERO_STILL for ~{minutes} minutes of narration in one block. "
                        "One striking beautiful painterly-cinematic frame with slight animation-style flavor "
                        "(soft semi-cartoon stylization), meant to become a subtly animated wallpaper. "
                        "Keep scene geometry stable and depth readable. "
                        + book_line
                        + "Location must be directly connected to this block theme; choose a specific place that naturally fits the narration. "
                        "Ensure key visible objects are theme-relevant props, not random filler décor. "
                        + "Composition must feel busy and intentional: foreground + midground + background each carrying "
                        "motifs from the spoken theme (objects, weather, architecture, crafts, nature, textiles) — "
                        "not a generic plain wall or empty beige room unless the narration explicitly demands it. "
                        "Rich mood light, imaginative layout, clear focal idea; leave pockets of calmer negative space so "
                        "ambient loop motion can read. No readable text, no logos, no UI."
                    )
                    still_ctx = (
                        f"{still_ctx} Animation-ready anchor pack: "
                        f"{_mode5_motion_anchor_pack(narr + '. ' + book_anchor, normalize_mode5_sub_mode(plan.get('sub_mode')))}."
                    )
                    img_prompt = build_mode5_image_prompt(
                        sub_mode=normalize_mode5_sub_mode(plan.get("sub_mode")),
                        segment_text=narr[:2000],
                        chunk_context=still_ctx,
                        style_lock=style_lock,
                        output_format=_mode5_output_format(),
                    )
                    img_prompt = _sanitize_mode5_image_prompt(img_prompt)
                    if _MODE5_BLOCK_LOOP_STILL_STYLE_OVERRIDE not in img_prompt:
                        img_prompt = f"{img_prompt} {_MODE5_BLOCK_LOOP_STILL_STYLE_OVERRIDE}"
                    logger.info("[Mode5] Block loop {:04d}: FastGen still (блок ~{} мин)", bid, minutes)
                    if backend == "api":
                        still_list = await fastgen_http.generate_images_fastgen(
                            [img_prompt],
                            m5dir,
                            parallel=False,
                            cancel_event=cancel_event,
                            aspect_ratio=_mode5_image_aspect_ratio(),
                        )
                    else:
                        still_list = await fastgen_playwright.generate_images_fastgen(
                            [img_prompt],
                            m5dir,
                            parallel=False,
                            cancel_event=cancel_event,
                            aspect_ratio=_mode5_image_aspect_ratio(),
                        )
                    if not still_list or not still_list[0]:
                        raise RuntimeError("still image list empty")
                    src_sp = Path(still_list[0])
                    if not src_sp.is_file():
                        raise RuntimeError("still image missing on disk")
                    shutil.copy2(src_sp, still_path)
                    try:
                        if src_sp.resolve() != still_path.resolve():
                            src_sp.unlink()
                    except OSError:
                        pass

                need_new_video = force or (not out_path.is_file()) or need_new_still
                if still_path.is_file() and out_path.is_file() and not need_new_still:
                    try:
                        if float(out_path.stat().st_mtime) < float(still_path.stat().st_mtime) - 0.5:
                            need_new_video = True
                    except OSError:
                        need_new_video = True

                if need_new_video and still_path.is_file():
                    if out_path.is_file():
                        try:
                            out_path.unlink()
                        except OSError:
                            pass
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    motion_prompt = _build_mode5_block_loop_motion_from_still_prompt(
                        sub_mode=plan.get("sub_mode"),
                        block_index=bid,
                        block_sec=block_sec,
                        narration_snippet=narr,
                        prev_snippet=_seed_narration_for_block(max(0, bid - 1))[:500] if bid > 0 else "",
                        book_anchor=book_anchor,
                    )
                    clip_idx = 8000 + int(bid)
                    raw_clip = await _mode5_animate_still_to_motion_clip(
                        motion_prompt=motion_prompt,
                        output_dir=m5dir,
                        still_path=still_path,
                        clip_index=clip_idx,
                        backend=backend,
                        cancel_event=cancel_event,
                    )
                    resolved_mv = Path(raw_clip) if raw_clip else None
                    if not resolved_mv or not resolved_mv.is_file():
                        raise RuntimeError("block loop keyframe motion clip empty")
                    if resolved_mv.resolve() != out_path.resolve():
                        shutil.copy2(resolved_mv, out_path)
                    _mode5_trim_loop_tail_inplace(out_path)
                    try:
                        if resolved_mv.resolve() != out_path.resolve():
                            resolved_mv.unlink()
                    except OSError:
                        pass
                    logger.info(
                        "[Mode5] Block loop {:04d}: still→keyframes motion ready: {} ({} segs)",
                        bid,
                        out_path.name,
                        len(rows),
                    )

                    fp_path.write_text(fp_payload, encoding="utf-8")
                    for _ch, seg, _t0, _d in rows:
                        seg["video"] = rel
                        seg["asset_type"] = "video"
                    motion_ok = True
            except Exception as smart_err:
                logger.warning(
                    "[Mode5] Block loop {}: still→keyframes motion не удалось — fallback segment JPEGs: {}",
                    bid,
                    smart_err,
                )

        if motion_ok:
            return

        if not img_a or not img_b or (not img_a.is_file()) or (not img_b.is_file()):
            logger.warning("[Mode5] Block loop {}: нет keyframe-изображений, оставляем image", bid)
            for _ch, seg, _t0, _d in rows:
                seg.pop("video", None)
                seg.pop("asset_type", None)
            return

        prompt = _build_mode5_block_loop_video_prompt(
            sub_mode=plan.get("sub_mode"),
            block_index=bid,
            block_sec=block_sec,
            narration_snippet=narr,
            prev_snippet=_seed_narration_for_block(max(0, bid - 1))[:500] if bid > 0 else "",
            book_anchor=book_anchor,
        )
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if backend == "api":
                video_path = await fastgen_http.generate_video_from_keyframes(
                    prompt=prompt,
                    output_dir=out_path.parent,
                    start_frame_path=img_a,
                    end_frame_path=img_b if img_b.resolve() != img_a.resolve() else img_a,
                    index=1000 + bid,
                    cancel_event=cancel_event,
                    flow_max_attempts=settings.fastgen_veo_flow_max_attempts,
                    video_aspect_ratio=_mode5_image_aspect_ratio(),
                )
            else:
                video_path = await fastgen_playwright.generate_video_from_keyframes(
                    prompt=prompt,
                    output_dir=out_path.parent,
                    start_frame_path=img_a,
                    end_frame_path=img_b if img_b.resolve() != img_a.resolve() else img_a,
                    index=1000 + bid,
                    cancel_event=cancel_event,
                    flow_max_attempts=settings.fastgen_veo_flow_max_attempts,
                    video_aspect_ratio=_mode5_image_aspect_ratio(),
                )
            resolved = Path(video_path) if video_path else None
            if resolved and resolved.is_file():
                if resolved.resolve() != out_path.resolve():
                    shutil.copy2(resolved, out_path)
                    _mode5_trim_loop_tail_inplace(out_path)
                for _ch, seg, _t0, _d in rows:
                    seg["video"] = rel
                    seg["asset_type"] = "video"
                logger.info("[Mode5] Block loop video готов (keyframes): {} ({} сегм.)", out_path.name, len(rows))
            else:
                raise RuntimeError("empty path")
        except Exception as err:
            logger.warning("[Mode5] Block loop {}: генерация не удалась — image: {}", bid, err)
            for _ch, seg, _t0, _d in rows:
                seg.pop("video", None)
                seg.pop("asset_type", None)

    await asyncio.gather(*[_process_block_loop(bid) for bid in block_ids])


def _build_chunk_preview_sync(session_id: str, chunk_index: int, plan: dict[str, Any]) -> Path:
    session_root = _session_dir(session_id)
    ch = plan["chunks"][chunk_index]
    sm = (plan.get("sub_mode") or "").strip().lower()
    segment_data: list[dict[str, Path | str]] = []
    subtitle_texts: list[str] = []
    top_labels: list[str] = []
    _mode5_append_chunk_render_rows(
        session_id,
        chunk_index,
        plan,
        segment_data=segment_data,
        subtitle_texts=subtitle_texts,
        top_labels=top_labels,
    )
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


def _build_mode5_final_direct_sync(session_id: str, plan: dict[str, Any]) -> Path:
    """Один проход MoviePy по всем сегментам всех чанков — без mode5_preview_*.mp4."""
    session_root = _session_dir(session_id)
    sm = (plan.get("sub_mode") or "").strip().lower()
    chunks = list(plan.get("chunks") or [])
    segment_data: list[dict[str, Path | str]] = []
    subtitle_texts: list[str] = []
    top_labels: list[str] = []
    for idx in range(len(chunks)):
        _mode5_append_chunk_render_rows(
            session_id,
            idx,
            plan,
            segment_data=segment_data,
            subtitle_texts=subtitle_texts,
            top_labels=top_labels,
        )
    out_mp4 = session_root / "video_mode5.mp4"
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


def _mode5_refresh_final_video_from_plan_sync(session_id: str, plan: dict[str, Any]) -> Path:
    """Пересобрать video_mode5.mp4 напрямую из плана и при необходимости дописать sleep-tail."""
    session_root = _session_dir(session_id)
    _build_mode5_final_direct_sync(session_id, plan)
    final_path = session_root / "video_mode5.mp4"
    return _append_mode5_sleep_tail(session_id, plan, final_path)


def _build_all_chunk_previews_parallel(session_id: str, plan: dict[str, Any]) -> None:
    chunks = plan.get("chunks") or []
    if not chunks:
        return
    if _mode5_sequential_chunks(plan):
        for idx in range(len(chunks)):
            _build_chunk_preview_sync(session_id, idx, plan)
            if 0 <= idx < len(chunks):
                chunks[idx]["preview_ready"] = True
                _save_mode5_plan(session_id, plan)
        return
    workers = _mode5_chunk_lane_parallel(
        int(getattr(settings, "mode5_preview_mp4_workers", 16) or 16),
        plan,
    )
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


async def _finalize_mode5_outputs(
    session_id: str,
    plan: dict[str, Any],
    *,
    skip_final_assembly: bool,
    review_log_message: str,
    done_log_message: str,
) -> dict[str, Any]:
    """
    Shared idempotent final stage used by both run/resume branches.
    """
    session_root = _session_dir(session_id)
    skip_pv = _mode5_skip_chunk_previews(plan)

    if not skip_pv:
        for ch in plan.get("chunks") or []:
            ch["preview_ready"] = False
        _save_mode5_plan(session_id, plan)

    loop = asyncio.get_event_loop()

    if skip_pv:
        for ch in plan.get("chunks") or []:
            ch["preview_status"] = "skipped"
            ch["preview_ready"] = False
        _save_mode5_plan(session_id, plan)
        direct_started = time.monotonic()
        await loop.run_in_executor(
            None,
            functools.partial(_build_mode5_final_direct_sync, session_id, plan),
        )
        _record_mode5_operation_seconds(
            plan,
            "final_direct_moviepy",
            direct_started,
            count=len(plan.get("chunks") or []),
        )
        final_path = session_root / "video_mode5.mp4"
        sleep_tail_started = time.monotonic()
        final_path = await loop.run_in_executor(
            None, lambda: _append_mode5_sleep_tail(session_id, plan, final_path)
        )
        _record_mode5_operation_seconds(plan, "sleep_tail", sleep_tail_started)
        rel_final = _rel_session(session_root, final_path)
        publishing_started = time.monotonic()
        await _mode5_generate_publish_assets(session_id, plan, force_thumbnail=False)
        _record_mode5_operation_seconds(plan, "publishing_assets", publishing_started)
        _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_COMPLETED)
        logger.success(f"{done_log_message} | video={final_path} (direct, no chunk previews)")
        return _attach_mode5_resume_flags_from_plan(
            session_id,
            plan,
            _result_payload(session_id, plan, review_ready=False, final_video=rel_final),
        )

    previews_started = time.monotonic()
    await loop.run_in_executor(
        None,
        functools.partial(_build_all_chunk_previews_parallel, session_id, plan),
    )
    _record_mode5_operation_seconds(
        plan,
        "preview_mp4_build",
        previews_started,
        count=len(plan.get("chunks") or []),
    )
    _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_AFTER_PREVIEWS)

    if skip_final_assembly:
        _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_COMPLETED)
        logger.success(f"{review_log_message} | session={session_id}")
        return _attach_mode5_resume_flags_from_plan(
            session_id, plan, _result_payload(session_id, plan, review_ready=True)
        )

    final_path = session_root / "video_mode5.mp4"
    await loop.run_in_executor(None, functools.partial(_rebuild_mode5_missing_previews, session_id, plan))
    preview_paths = [session_root / ch["preview_relpath"] for ch in (plan.get("chunks") or [])]
    concat_started = time.monotonic()
    await loop.run_in_executor(None, lambda: _ffmpeg_concat(preview_paths, final_path))
    _record_mode5_operation_seconds(plan, "final_concat", concat_started, count=len(preview_paths))
    sleep_tail_started = time.monotonic()
    final_path = await loop.run_in_executor(None, lambda: _append_mode5_sleep_tail(session_id, plan, final_path))
    _record_mode5_operation_seconds(plan, "sleep_tail", sleep_tail_started)
    rel_final = _rel_session(session_root, final_path)
    publishing_started = time.monotonic()
    await _mode5_generate_publish_assets(session_id, plan, force_thumbnail=False)
    _record_mode5_operation_seconds(plan, "publishing_assets", publishing_started)
    _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_COMPLETED)
    logger.success(f"{done_log_message} | video={final_path}")
    return _attach_mode5_resume_flags_from_plan(
        session_id,
        plan,
        _result_payload(session_id, plan, review_ready=False, final_video=rel_final),
    )


async def _generate_mode5_sleep_tail_theme_images(
    session_id: str,
    plan: dict[str, Any],
    topic: str,
    n: int,
    fallback_still: Path,
) -> list[Path]:
    """One thematic still per sleep-tail segment; fail-soft copies previous or fallback."""
    style = _ensure_mode5_style_lock(plan)
    m5 = _mode5_dir(session_id)
    out: list[Path | None] = [None] * max(0, int(n))
    parallel = min(max(1, int(n)), _mode5_sleep_tail_image_parallel()) if n > 0 else 1
    sem = asyncio.Semaphore(parallel)

    async def _generate_one_tail_image(i: int) -> None:
        idx = i + 1
        dest = m5 / f"sleep_tail_theme_{idx:03d}.jpg"
        scene_hint = (
            f"Thematic calm still for background viewing while listening to ambient music. Topic: {topic}. "
            f"Visual {idx} of {n}: distinct composition, same soft realistic documentary mood. "
            "No text, no letters, no subtitles."
        )
        try:
            prompt = build_mode5_image_prompt(
                sub_mode=normalize_mode5_sub_mode(plan.get("sub_mode")),
                segment_text=scene_hint,
                chunk_context="sleep tail thematic extension",
                style_lock=style,
                output_format=_mode5_output_format(),
            )
            prompt = _sanitize_mode5_image_prompt(prompt)
            async with sem:
                await _generate_one_image(
                    prompt,
                    dest,
                    aspect_ratio=_mode5_image_aspect_ratio(),
                    image_backend=plan.get("image_backend"),
                )
        except Exception as e:
            logger.warning(f"[Mode5] sleep tail theme image {idx} failed: {e}")
        if dest.is_file():
            out[i] = dest

    await asyncio.gather(*[_generate_one_tail_image(i) for i in range(max(0, int(n)))])

    filled: list[Path] = []
    prev_ok: Path | None = fallback_still if fallback_still.is_file() else None
    for i in range(max(0, int(n))):
        idx = i + 1
        dest = m5 / f"sleep_tail_theme_{idx:03d}.jpg"
        if out[i] is not None and dest.is_file():
            filled.append(dest)
            prev_ok = dest
        elif prev_ok is not None:
            shutil.copy2(prev_ok, dest)
            filled.append(dest)
        else:
            if not fallback_still.is_file():
                raise FileNotFoundError("sleep tail fallback still missing")
            shutil.copy2(fallback_still, dest)
            filled.append(dest)
            prev_ok = dest
    return filled


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
                workers = max(1, int(getattr(settings, "mode5_preview_mp4_workers", 16) or 16))

                def _render_tail_segment(i: int, dur: float) -> Path:
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
                    return seg_out

                with ThreadPoolExecutor(max_workers=workers) as executor:
                    futs = {
                        executor.submit(_render_tail_segment, i, dur): i
                        for i, dur in enumerate(segment_durs)
                    }
                    ordered: list[Path | None] = [None] * len(segment_durs)
                    for fut in as_completed(futs):
                        idx = futs[fut]
                        ordered[idx] = fut.result()
                    seg_mp4s = [p for p in ordered if p is not None]

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
    _ensure_mode5_live_defaults(plan)
    chunk["status"] = "regenerating"
    chunk["audio_status"] = "regenerating"
    chunk["images_status"] = "regenerating"
    chunk["preview_status"] = "regenerating"
    chunk["locked"] = True
    _mode5_push_live_event(plan, "chunk_state_changed", chunk_index=chunk_index, status="regenerating")
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
    visible_text = _mode5_visible_text(tts_plain)
    chunk["text"] = visible_text
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
            visible_text,
            dur,
            overlay_title=overlay_title,
        )
    else:
        chunk["segments"] = _segments_for_chunk(visible_text, dur, segment_seconds, wts, words)
    _rebuild_chunk_segment_paths(session_id, chunk)
    locked_style = _ensure_mode5_style_lock(plan)
    await _generate_chunk_images(
        session_id,
        chunk,
        locked_style,
        sub_mode=normalize_mode5_sub_mode(plan.get("sub_mode")),
        max_parallel_images=max_parallel_images,
        image_backend=plan.get("image_backend"),
        refresh_all=True,
        topic_seed_override=str(plan.get("facts_topic") or plan.get("header_title") or ""),
    )
    _render_chunk_audio_slices(session_id, chunk)
    if _mode5_block_loop_applies(plan):
        await _ensure_mode5_block_loop_videos(session_id, plan, force=True)
    else:
        await _ensure_mode5_looped_intro_video(
            session_id,
            plan,
            force=chunk_index == 0,
        )
    loop = asyncio.get_event_loop()
    if _mode5_skip_chunk_previews(plan):
        await loop.run_in_executor(
            None,
            lambda: _mode5_refresh_final_video_from_plan_sync(session_id, plan),
        )
        chunk["preview_status"] = "skipped"
    else:
        await loop.run_in_executor(None, lambda: _build_chunk_preview_sync(session_id, chunk_index, plan))
        chunk["preview_status"] = "ready"
    chunk["status"] = "ready"
    chunk["audio_status"] = "ready"
    chunk["images_status"] = "ready"
    if not _mode5_skip_chunk_previews(plan):
        chunk["preview_status"] = "ready"
    chunk["locked"] = False
    chunk["version"] = int(chunk.get("version") or 1) + 1
    for seg in chunk.get("segments") or []:
        seg["audio_version"] = int(seg.get("audio_version") or 1) + 1
        seg["last_action"] = "regenerate_audio"
        seg["dirty_reason"] = ""
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
    skip_chunk_previews: bool = False,
    sequential_chunks: bool = False,
    chunk_seconds: int = CHUNK_SEC_DEFAULT,
    segment_seconds: int = SEG_SEC_DEFAULT,
    max_parallel_images: int | None = None,
    image_backend: str | None = None,
    video_header_title: str | None = None,
    bible_mode: bool = False,
    sub_mode: str = "manual",
    test_run: bool = False,
    test_duration_sec: int = 300,
    control: dict | None = None,
) -> dict[str, Any]:
    from pipeline_control import checkpoint, fastgen_cancel_event

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

    test_target = max(60, min(7200, int(test_duration_sec or 300)))
    gen_control = dict(control or {})
    fg_cancel_event = fastgen_cancel_event(control)
    if bool(test_run):
        gen_control["_mode5_test_run"] = True
        gen_control["_mode5_test_target_sec"] = float(test_target)

    topic_input = re.sub(r"\s+", " ", (script_text or "").strip())
    skip_intro_confirmation = bool((control or {}).get("_mode5_skip_intro_confirmation"))
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

        facts_outline, narrations = await generate_facts50_script(topic_input, language, control=gen_control)
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
            topic_input, language, control=gen_control
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
            topic_input, language, control=gen_control
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
            topic_input, language, control=gen_control
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
    ib = _normalize_mode5_image_backend(
        image_backend if image_backend is not None else getattr(settings, "mode5_image_backend", "playwright")
    )

    logger.info(
        f"=== Mode 5 Pipeline | sub_mode={sm} | image_backend={ib} | session={session_id} ==="
    )
    if bool(getattr(settings, "mode5_block_loop_video_enabled", False)) and not str(
        getattr(settings, "fastgen_http_base_url", "") or ""
    ).strip():
        logger.info(
            "[Mode5] Зацикленное motion по блокам выключено: задайте FASTGEN_HTTP_BASE_URL и ключ в .env "
            "(иначе остаются статичные кадры по сегменту ~30 с)."
        )
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

    mode_key = normalize_mode5_sub_mode(sm)
    style_suffix = mode5_style_lock_for_sub_mode(mode_key)
    style_suffix = re.sub(r"\s+", " ", (style_suffix or "").strip())
    style_lock = style_suffix
    style_id = mode5_style_id_for_sub_mode(mode_key)
    await checkpoint(control)

    outline_labels: list[tuple[str, str]] = []
    unwritten_anchor_map: dict[int, dict[str, str]] = {}
    if sm in ("outline", "book_night", "unwritten_chapter") and isinstance(outline_doc, dict):
        from modes.mode5.outline_generator import get_chunk_outline_labels

        outline_labels = get_chunk_outline_labels(outline_doc)
        if sm == "unwritten_chapter":
            unwritten_anchor_map = _unwritten_chunk_anchor_by_index(outline_doc)

    facts50_orig_n: int | None = None
    if bool(test_run) and chunk_texts:
        if sm == "facts50":
            facts50_orig_n = len(chunk_texts)
        chunk_texts, test_est_sec = _truncate_mode5_chunk_texts_for_test(
            chunk_texts,
            language=language,
            target_sec=float(test_target),
        )
        outline_labels = outline_labels[: len(chunk_texts)]
        if unwritten_anchor_map:
            unwritten_anchor_map = {
                i: unwritten_anchor_map[i]
                for i in range(len(chunk_texts))
                if i in unwritten_anchor_map
            }
        logger.info(
            f"[Mode5] test_run: target={test_target}s, chunks={len(chunk_texts)}, ~est_speech={test_est_sec:.0f}s"
        )

    plan_test_meta: dict[str, Any] = (
        {"test_run": True, "test_target_sec": int(test_target)}
        if bool(test_run)
        else {"test_run": False, "test_target_sec": None}
    )

    preflight_applies = _mode5_block_loop_applies(
        {
            "sub_mode": sm,
            "image_backend": (
                image_backend
                if image_backend is not None
                else getattr(settings, "mode5_image_backend", "playwright")
            ),
        }
    )
    # Preflight gate is meaningful only when approved intro previews
    # will be reused in the downstream render path.
    if (
        bool(getattr(settings, "mode5_intro_confirm_enabled", True))
        and preflight_applies
        and not skip_intro_confirmation
    ):
        if bool(sm):
            style_lock_pre = re.sub(r"\s+", " ", (mode5_style_lock_for_sub_mode(normalize_mode5_sub_mode(sm)) or "").strip())
            header_stripped_pre = (video_header_title or "").strip() or None
            pre_pool_size = 1 if bool(test_run) else _mode5_block_loop_pool_size()
            pre_backend = _normalize_mode5_image_backend(
                image_backend if image_backend is not None else getattr(settings, "mode5_image_backend", "playwright")
            )
            pre_chunks: list[dict[str, Any]] = []
            for i, ct in enumerate(chunk_texts):
                text_stub = re.sub(r"\s+", " ", str(ct or "").strip())
                row: dict[str, Any] = {
                    "index": i,
                    "text": text_stub,
                    "fact_hint": None,
                    "preview_relpath": _rel_session(session_root, session_root / f"mode5_preview_{i:03d}.mp4"),
                    "segments": [],
                }
                if sm == "facts50":
                    is_intro = i == 0
                    is_outro = _facts50_eval_is_outro(i, len(chunk_texts), facts50_orig_n)
                    row["is_intro"] = bool(is_intro)
                    row["is_outro"] = bool(is_outro)
                    if (not is_intro) and (not is_outro) and isinstance(facts_outline, list) and (i - 1) < len(facts_outline):
                        row["fact_hint"] = str(facts_outline[i - 1] or "").strip()
                    else:
                        row["fact_hint"] = text_stub
                pre_chunks.append(row)
            pre_plan: dict[str, Any] = {
                "version": 1,
                "session_id": session_id,
                "script_text": topic_input,
                "source_input_text": topic_input,
                "language": language,
                "show_subtitles": False,
                "chunk_seconds": max(120, min(900, int(chunk_seconds or CHUNK_SEC_DEFAULT))),
                "segment_seconds": max(10, min(90, int(segment_seconds or SEG_SEC_DEFAULT))),
                "max_parallel_images": _clamp_mode5_parallel_images(max_parallel_images),
                "image_backend": _normalize_mode5_image_backend(
                    image_backend if image_backend is not None else getattr(settings, "mode5_image_backend", "playwright")
                ),
                "header_title": header_stripped_pre,
                "bible_mode": sm == "bible",
                "sub_mode": sm,
                "facts_topic": topic_input if sm in ("facts50", "book_night", "unwritten_chapter") else None,
                "style_suffix": style_lock_pre,
                "style_lock": style_lock_pre,
                "style_id": mode5_style_id_for_sub_mode(normalize_mode5_sub_mode(sm)),
                "await_intro_confirmation": False,
                "intro_preview_video": None,
                "intro_preview_videos": [],
                "preflight_only": True,
                "skip_final_assembly": bool(skip_final_assembly),
                "skip_chunk_previews": bool(skip_chunk_previews),
                "sequential_chunks": bool(sequential_chunks),
                "test_run": bool(test_run),
                "test_target_sec": int(test_target) if bool(test_run) else None,
                "chunks": pre_chunks,
            }
            _save_mode5_plan(session_id, pre_plan, checkpoint=MODE5_CKPT_STUB)
            effective_intro_backend = pre_backend
            try:
                intro_started = time.monotonic()
                intro_rels = await _generate_mode5_intro_confirmation_pool(
                    session_id=session_id,
                    sub_mode=sm,
                    style_lock=style_lock_pre,
                    topic_seed=topic_input or (header_stripped_pre or ""),
                    pool_size_override=pre_pool_size,
                    image_backend=effective_intro_backend,
                    cancel_event=fg_cancel_event,
                )
                _record_mode5_operation_seconds(
                    pre_plan, "intro_confirmation_pool", intro_started, count=pre_pool_size
                )
            except Exception as preview_err:
                if effective_intro_backend == "api":
                    logger.warning(
                        "[Mode5] Intro preflight failed with image backend=api ({}); retrying preview pool with playwright.",
                        preview_err,
                    )
                    effective_intro_backend = "playwright"
                    intro_started = time.monotonic()
                    intro_rels = await _generate_mode5_intro_confirmation_pool(
                        session_id=session_id,
                        sub_mode=sm,
                        style_lock=style_lock_pre,
                        topic_seed=topic_input or (header_stripped_pre or ""),
                        pool_size_override=pre_pool_size,
                        image_backend=effective_intro_backend,
                        cancel_event=fg_cancel_event,
                    )
                    _record_mode5_operation_seconds(
                        pre_plan, "intro_confirmation_pool", intro_started, count=pre_pool_size
                    )
                else:
                    raise RuntimeError(f"Mode5 intro preflight failed: {preview_err}") from preview_err
            if not intro_rels:
                raise RuntimeError("Mode5 intro preflight produced no preview videos")
            pre_plan["image_backend"] = effective_intro_backend
            pre_plan["await_intro_confirmation"] = True
            pre_plan["intro_preview_video"] = intro_rels[0]
            pre_plan["intro_preview_videos"] = intro_rels
            _save_mode5_plan(session_id, pre_plan, checkpoint=MODE5_CKPT_STUB)
            waiting = _attach_mode5_resume_flags_from_plan(
                session_id,
                pre_plan,
                _result_payload(session_id, pre_plan, review_ready=False),
            )
            waiting["mode5_progress_hint"] = (
                "Сначала проверьте анимированные превью. После подтверждения начнётся генерация фактов/текста, озвучки и монтажа."
            )
            waiting["mode5_waiting_confirmation"] = True
            return waiting

    # Persist stub plan before long parallel TTS so /review-state does not 404 while audio generates.
    if sm == "facts50" and chunk_texts:
        stub_chunks: list[dict[str, Any]] = []
        for i, ct in enumerate(chunk_texts):
            is_intro = i == 0
            is_outro = _facts50_eval_is_outro(i, len(chunk_texts), facts50_orig_n)
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
            "image_backend": ib,
            "header_title": header_stripped,
            "bible_mode": False,
            "sub_mode": sm,
            "facts_topic": topic_input,
            "facts_outline": facts_outline,
            "style_suffix": style_suffix,
            "style_lock": style_lock,
            "style_id": style_id,
            "await_intro_confirmation": False,
            "intro_preview_video": None,
            "intro_preview_videos": [],
            "chunks": stub_chunks,
            **plan_test_meta,
            "skip_final_assembly": bool(skip_final_assembly),
            "skip_chunk_previews": bool(skip_chunk_previews),
            "sequential_chunks": bool(sequential_chunks),
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
            "image_backend": ib,
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
            "style_id": style_id,
            "await_intro_confirmation": False,
            "intro_preview_video": None,
            "intro_preview_videos": [],
            "chunks": stub_chunks_lf,
            **plan_test_meta,
            "skip_final_assembly": bool(skip_final_assembly),
            "skip_chunk_previews": bool(skip_chunk_previews),
            "sequential_chunks": bool(sequential_chunks),
        }
        _save_mode5_plan(session_id, stub_plan_lf, checkpoint=MODE5_CKPT_STUB)

    chunks_plan: list[dict[str, Any]] = []
    plan = load_mode5_plan(session_id)

    if sm == "facts50":
        # Параллельно до N фактов: TTS и затем картинки (типичный паттерн — asyncio + семафор под лимиты API).
        par = _mode5_chunk_lane_parallel(_mode5_tts_chunk_parallel_cap(), plan)
        par = min(par, voiceapi_mode5_recommended_tts_parallel())
        sem_tts = asyncio.Semaphore(par)

        async def _facts50_tts(ci: int, chunk_text: str):
            async with sem_tts:
                is_intro = ci == 0
                is_outro = _facts50_eval_is_outro(ci, len(chunk_texts), facts50_orig_n)
                if is_intro or is_outro:
                    source_text = chunk_text
                else:
                    source_text = _ensure_fact_spoken_prefix(ci - 1, chunk_text, language)
                pack = await _synthesize_chunk(session_id, ci, source_text, language=language)
                return ci, pack

        logger.info(
            f"[Mode5 facts50] TTS workers={par} ({len(chunk_texts)} facts)"
            f"{' [sequential chunks]' if _mode5_sequential_chunks(plan) else ''}"
        )
        tts_started = time.monotonic()
        tts_pairs = await _mode5_await_chunk_coroutines(
            [_facts50_tts(ci, ct) for ci, ct in enumerate(chunk_texts)],
            plan,
        )
        await checkpoint(control)
        tts_by_ci = {p[0]: p[1] for p in tts_pairs}

        for ci in range(len(chunk_texts)):
            mp3_path, wav_path, dur, wts, words, tts_plain = tts_by_ci[ci]
            visible_text = _mode5_visible_text(tts_plain)
            is_intro = ci == 0
            is_outro = _facts50_eval_is_outro(ci, len(chunk_texts), facts50_orig_n)
            fact_hint = visible_text if (is_intro or is_outro) else ""
            if (not is_intro) and (not is_outro) and isinstance(facts_outline, list) and (ci - 1) < len(facts_outline):
                fact_hint = str(facts_outline[ci - 1] or "").strip()
            overlay_title = "" if (is_intro or is_outro) else _fact_overlay_title(ci - 1)
            segs = _segments_for_facts50_chunk(
                fact_hint,
                visible_text,
                dur,
                overlay_title=overlay_title,
            )
            preview_path = session_root / f"mode5_preview_{ci:03d}.mp4"
            chunks_plan.append(
                {
                    "index": ci,
                    "text": visible_text,
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

        plan["chunks"] = chunks_plan
        plan["skip_chunk_previews"] = bool(skip_chunk_previews)
        plan["skip_final_assembly"] = bool(skip_final_assembly)
        plan["sequential_chunks"] = bool(sequential_chunks)
        _record_mode5_operation_seconds(plan, "tts_facts50", tts_started, count=len(chunk_texts))
        _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_AFTER_TTS)

        img_par = _mode5_chunk_lane_parallel(_mode5_facts50_image_parallel(), plan)
        sem_img = asyncio.Semaphore(img_par)
        logger.info("[Mode5 facts50] Image chunk lanes={} (TTS lanes={})", img_par, par)

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
                    sub_mode=mode_key,
                    max_parallel_images=mpi,
                    image_backend=plan.get("image_backend"),
                    refresh_all=True,
                    topic_seed_override=str(plan.get("facts_topic") or plan.get("header_title") or ""),
                    cancel_event=fg_cancel_event,
                )
                _save_mode5_plan(
                    session_id, plan, checkpoint=MODE5_CKPT_AFTER_IMAGES, chunk_index=idx
                )

        images_started = time.monotonic()
        await _mode5_await_chunk_coroutines([_facts50_images(ch) for ch in chunks_plan], plan)
        _record_mode5_operation_seconds(plan, "images_facts50", images_started, count=len(chunks_plan))

        for ch in chunks_plan:
            _render_chunk_audio_slices(session_id, ch)
        if _mode5_block_loop_applies(plan):
            block_started = time.monotonic()
            await _ensure_mode5_block_loop_videos(
                session_id,
                plan,
                force=False,
                cancel_event=fg_cancel_event,
            )
            _record_mode5_operation_seconds(plan, "block_loop_videos", block_started)
        else:
            await _ensure_mode5_looped_intro_video(session_id, plan, force=False)
        _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_AFTER_SLICES)
        await checkpoint(control)

    else:
        # Long-form manual / bible / outline / book_night / unwritten_chapter:
        # keep prompt/segment quality tied to real TTS output, but overlap image generation
        # of ready chunks with TTS still running on the remaining chunks.
        par = _mode5_chunk_lane_parallel(_mode5_tts_chunk_parallel_cap(), plan)
        par = min(par, voiceapi_mode5_recommended_tts_parallel())
        sem_tts = asyncio.Semaphore(par)
        # _generate_chunk_images already fans out segment image requests inside one chunk,
        # so keep one chunk-level image lane to avoid explosive API concurrency.
        sem_img = asyncio.Semaphore(_mode5_chunk_lane_parallel(_mode5_longform_chunk_image_parallel(), plan))

        plan["skip_chunk_previews"] = bool(skip_chunk_previews)
        plan["skip_final_assembly"] = bool(skip_final_assembly)
        plan["sequential_chunks"] = bool(sequential_chunks)
        chunks_plan = plan.get("chunks") or []

        async def _longform_pipeline_chunk(ci: int, chunk_text: str) -> None:
            async with sem_tts:
                logger.info(f"[Mode5] Chunk {ci + 1}/{len(chunk_texts)}: TTS (voiceapi/template) synthesis")
                await checkpoint(control)
                tts_started = time.monotonic()
                mp3_path, wav_path, dur, wts, words, tts_plain = await _synthesize_chunk(
                    session_id,
                    ci,
                    chunk_text,
                    language=language,
                )
                _record_mode5_operation_seconds(plan, "tts_longform", tts_started, count=1)

            visible_text = _mode5_visible_text(tts_plain)
            segs = _segments_for_chunk(visible_text, dur, seg_sec, wts, words)
            preview_path = session_root / f"mode5_preview_{ci:03d}.mp4"
            ch_entry: dict[str, Any] = {
                "index": ci,
                "text": visible_text,
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
                images_started = time.monotonic()
                await _generate_chunk_images(
                    session_id,
                    ch_entry,
                    style_suffix,
                    sub_mode=mode_key,
                    max_parallel_images=mpi,
                    image_backend=plan.get("image_backend"),
                    refresh_all=True,
                    topic_seed_override=str(plan.get("facts_topic") or plan.get("header_title") or ""),
                    cancel_event=fg_cancel_event,
                )
                _record_mode5_operation_seconds(plan, "images_longform", images_started, count=1)
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

                images_started = time.monotonic()
                await _generate_chunk_images(
                    session_id,
                    ch_entry,
                    style_suffix,
                    sub_mode=mode_key,
                    max_parallel_images=mpi,
                    image_backend=plan.get("image_backend"),
                    refresh_all=True,
                    on_segment_ready=_on_seg_ready,
                    topic_seed_override=str(plan.get("facts_topic") or plan.get("header_title") or ""),
                    cancel_event=fg_cancel_event,
                )
                _record_mode5_operation_seconds(plan, "images_unwritten", images_started, count=1)
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
                ch_entry["text"] = _mode5_visible_text(tts_plain)
                ch_entry["chunk_audio"] = _rel_session(session_root, mp3_path)
                ch_entry["chunk_audio_wav"] = _rel_session(session_root, wav_path)
                ch_entry["duration_sec"] = dur
                _retime_existing_segments_for_audio(ch_entry["segments"], duration_sec=dur)
                _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_AFTER_TTS, chunk_index=ci)
                await asyncio.to_thread(_render_chunk_audio_slices, session_id, ch_entry)
                _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_AFTER_SLICES, chunk_index=ci)
                await checkpoint(control)

            await _mode5_await_chunk_coroutines(
                [_tts_after_images(ci, ch) for ci, ch in enumerate(chunks_plan)],
                plan,
            )
        else:
            await _mode5_await_chunk_coroutines(
                [_longform_pipeline_chunk(ci, ct) for ci, ct in enumerate(chunk_texts)],
                plan,
            )
        await checkpoint(control)
        if _mode5_block_loop_applies(plan):
            block_started = time.monotonic()
            await _ensure_mode5_block_loop_videos(
                session_id,
                plan,
                force=False,
                cancel_event=fg_cancel_event,
            )
            _record_mode5_operation_seconds(plan, "block_loop_videos", block_started)
        else:
            await _ensure_mode5_looped_intro_video(session_id, plan, force=False)

    return await _finalize_mode5_outputs(
        session_id,
        plan,
        skip_final_assembly=skip_final_assembly,
        review_log_message="=== Mode 5 Pipeline REVIEW READY ===",
        done_log_message="=== Mode 5 Pipeline DONE ===",
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
    from pipeline_control import checkpoint, fastgen_cancel_event

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
    fg_cancel_event = fastgen_cancel_event(control)
    if not list(plan.get("chunks") or []) and bool(plan.get("early_pause_before_chunks")):
        logger.info("[Mode5 resume] early_pause_before_chunks: restarting full pipeline from saved parameters")
        return await run_mode5_pipeline(
            str(plan.get("source_input_text") or plan.get("script_text") or ""),
            session_id=session_id,
            language=str(plan.get("language") or "ru"),
            skip_final_assembly=bool(plan.get("skip_final_assembly", True)),
            skip_chunk_previews=bool(plan.get("skip_chunk_previews", False)),
            sequential_chunks=bool(plan.get("sequential_chunks", False)),
            chunk_seconds=int(plan.get("chunk_seconds") or CHUNK_SEC_DEFAULT),
            segment_seconds=int(plan.get("segment_seconds") or SEG_SEC_DEFAULT),
            max_parallel_images=int(plan.get("max_parallel_images") or 10),
            image_backend=plan.get("image_backend"),
            video_header_title=str(plan.get("header_title") or "").strip() or None,
            bible_mode=bool(plan.get("bible_mode", False)),
            sub_mode=str(plan.get("sub_mode") or "manual"),
            test_run=bool(plan.get("test_run", False)),
            test_duration_sec=int(plan.get("test_target_sec") or 300),
            control=control,
        )
    if bool(plan.get("await_intro_confirmation")):
        plan["await_intro_confirmation"] = False
        _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_STUB)
        plan = load_mode5_plan(session_id)
    sm = (plan.get("sub_mode") or "").strip().lower()
    mode_key = normalize_mode5_sub_mode(sm)
    session_root = _session_dir(session_id)
    chunks = list(plan.get("chunks") or [])
    style_suffix = _ensure_mode5_style_lock(plan)
    mpi = _clamp_mode5_parallel_images(plan.get("max_parallel_images"))
    language = str(plan.get("language") or "ru").strip() or "ru"
    stage = _checkpoint_stage(plan)
    skip_segment_images_on_resume = bool(
        _mode5_block_loop_applies(plan)
        and (plan.get("intro_preview_videos") or plan.get("intro_preview_video"))
    )

    # Intro-confirm flow stops at STUB before any TTS/WAV exists.
    # On continue, bootstrap chunk audio + segments from saved stub texts first,
    # then proceed with the normal resume logic below.
    if stage == MODE5_CKPT_STUB:
        plan["preflight_only"] = False
        plan["await_intro_confirmation"] = False
        chunks_boot = list(plan.get("chunks") or [])
        on_disk = sum(
            1 for ch in chunks_boot if _resolve_mode5_chunk_audio_paths(session_id, ch)[1] is not None
        )
        logger.info(
            "[Mode5 resume] bootstrap from STUB: TTS {} already on disk, {} to synthesize",
            on_disk,
            max(0, len(chunks_boot) - on_disk),
        )
        if not chunks_boot:
            # Backward-compat for old preflight plans created before chunk stubs were persisted.
            if bool(plan.get("preflight_only")):
                logger.warning(
                    "[Mode5 resume] legacy stub without chunks; rebuilding plan via run_mode5_pipeline(skip intro gate)"
                )
                return await run_mode5_pipeline(
                    str(plan.get("source_input_text") or plan.get("script_text") or ""),
                    session_id=session_id,
                    language=str(plan.get("language") or "ru"),
                    skip_final_assembly=bool(plan.get("skip_final_assembly", True)),
                    skip_chunk_previews=bool(plan.get("skip_chunk_previews", False)),
                    sequential_chunks=bool(plan.get("sequential_chunks", False)),
                    chunk_seconds=int(plan.get("chunk_seconds") or CHUNK_SEC_DEFAULT),
                    segment_seconds=int(plan.get("segment_seconds") or SEG_SEC_DEFAULT),
                    max_parallel_images=int(plan.get("max_parallel_images") or 10),
                    image_backend=plan.get("image_backend"),
                    video_header_title=plan.get("header_title"),
                    bible_mode=bool(plan.get("bible_mode", False)),
                    sub_mode=str(plan.get("sub_mode") or "manual"),
                    test_run=bool(plan.get("test_run", False)),
                    test_duration_sec=int(plan.get("test_target_sec") or 300),
                    control={**(control or {}), "_mode5_skip_intro_confirmation": True},
                )
            raise ValueError("Mode5 resume: no chunks in stub plan")
        tts_par = _mode5_chunk_lane_parallel(_mode5_tts_chunk_parallel_cap(), plan)
        tts_par = min(tts_par, voiceapi_mode5_recommended_tts_parallel())
        sem_resume_tts = asyncio.Semaphore(tts_par)

        seg_sec_boot = int(plan.get("segment_seconds") or SEG_SEC_DEFAULT)

        async def _bootstrap_fill_segments_from_wav(
            ch: dict[str, Any],
            *,
            wav_path: Path,
            mp3_path: Path | None,
            visible_text: str,
        ) -> None:
            ci = int(ch.get("index") or 0)
            dur = float(ch.get("duration_sec") or 0.0)
            if dur <= 0:
                dur = await asyncio.to_thread(_wav_duration_sec, wav_path)
            default_mp3, _ = _default_mode5_chunk_audio_paths(session_id, ci)
            mp3_eff = mp3_path if mp3_path is not None and mp3_path.is_file() else default_mp3
            wts, words = await asyncio.to_thread(
                get_word_timestamps_from_audio_path,
                wav_path,
                script=visible_text,
                language=language,
                vad_filter=False,
            )
            ch["text"] = visible_text
            if mp3_eff.is_file():
                ch["chunk_audio"] = _rel_session(session_root, mp3_eff)
            ch["chunk_audio_wav"] = _rel_session(session_root, wav_path)
            ch["duration_sec"] = dur
            ch["audio_status"] = "done"
            if sm == "facts50":
                is_intro = bool(ch.get("is_intro"))
                is_outro = bool(ch.get("is_outro"))
                fact_hint = str(ch.get("fact_hint") or "").strip() or (
                    visible_text if (is_intro or is_outro) else ""
                )
                overlay_title = "" if (is_intro or is_outro) else _fact_overlay_title(ci - 1)
                ch["segments"] = _segments_for_facts50_chunk(
                    fact_hint,
                    visible_text,
                    dur,
                    overlay_title=overlay_title,
                )
            else:
                ch["segments"] = _segments_for_chunk(
                    visible_text,
                    dur,
                    seg_sec_boot,
                    wts,
                    words,
                )
            _rebuild_chunk_segment_paths(session_id, ch)

        async def _bootstrap_one(ch: dict[str, Any]) -> None:
            ci = int(ch.get("index") or 0)
            text = str(ch.get("text") or "").strip()
            if not text:
                raise ValueError(f"Mode5 resume: empty chunk text at index {ci}")
            mp3_existing, wav_existing = _resolve_mode5_chunk_audio_paths(session_id, ch)
            if wav_existing is not None:
                visible_text = _mode5_visible_text(text)
                await _bootstrap_fill_segments_from_wav(
                    ch,
                    wav_path=wav_existing,
                    mp3_path=mp3_existing,
                    visible_text=visible_text,
                )
            else:
                async with sem_resume_tts:
                    mp3_path, wav_path, dur, wts, words, tts_plain = await _synthesize_chunk(
                        session_id,
                        ci,
                        text,
                        language=language,
                    )
                visible_text = _mode5_visible_text(tts_plain)
                ch["text"] = visible_text
                ch["chunk_audio"] = _rel_session(session_root, mp3_path)
                ch["chunk_audio_wav"] = _rel_session(session_root, wav_path)
                ch["duration_sec"] = dur
                ch["audio_status"] = "done"
                if sm == "facts50":
                    is_intro = bool(ch.get("is_intro"))
                    is_outro = bool(ch.get("is_outro"))
                    fact_hint = str(ch.get("fact_hint") or "").strip() or (
                        visible_text if (is_intro or is_outro) else ""
                    )
                    overlay_title = "" if (is_intro or is_outro) else _fact_overlay_title(ci - 1)
                    ch["segments"] = _segments_for_facts50_chunk(
                        fact_hint,
                        visible_text,
                        dur,
                        overlay_title=overlay_title,
                    )
                else:
                    ch["segments"] = _segments_for_chunk(
                        visible_text,
                        dur,
                        seg_sec_boot,
                        wts,
                        words,
                    )
                _rebuild_chunk_segment_paths(session_id, ch)
            _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_STUB)

        await _mode5_await_chunk_coroutines([_bootstrap_one(ch) for ch in chunks_boot], plan)
        _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_AFTER_TTS)
        stage = MODE5_CKPT_AFTER_TTS

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
            if skip_segment_images_on_resume:
                logger.info(
                    "[Mode5 resume] Chunk {}/{}: skip segment image generation (using approved block-loop still/video)",
                    ci + 1,
                    len(chunks),
                )
            elif not _mode5_chunk_images_complete(session_root, ch):
                logger.info(
                    f"[Mode5 resume] Chunk {ci + 1}/{len(chunks)}: image generation for {len(ch.get('segments') or [])} window(s)"
                )
                await _generate_chunk_images(
                    session_id,
                    ch,
                    style_suffix,
                    sub_mode=mode_key,
                    max_parallel_images=mpi,
                    image_backend=plan.get("image_backend"),
                    refresh_all=False,
                    on_segment_ready=(
                        lambda _seg, cidx=ci: _save_mode5_plan(
                            session_id, plan, checkpoint=MODE5_CKPT_AFTER_IMAGES, chunk_index=cidx
                        )
                    ),
                    topic_seed_override=str(plan.get("facts_topic") or plan.get("header_title") or ""),
                    cancel_event=fg_cancel_event,
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
                    visible_text = _mode5_visible_text(tts_plain)
                    ch["text"] = visible_text
                    ch["chunk_audio"] = _rel_session(session_root, mp3_path_new)
                    ch["chunk_audio_wav"] = _rel_session(session_root, wav_path_new)
                    ch["duration_sec"] = dur
                    _retime_existing_segments_for_audio(ch["segments"], duration_sec=dur)
                    _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_AFTER_TTS, chunk_index=ci)
            if not _mode5_chunk_slices_complete(session_root, ch):
                _render_chunk_audio_slices(session_id, ch)
                _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_AFTER_SLICES, chunk_index=ci)
            await checkpoint(control)

        if _mode5_block_loop_applies(plan):
            block_started = time.monotonic()
            await _ensure_mode5_block_loop_videos(
                session_id,
                plan,
                force=False,
                cancel_event=fg_cancel_event,
            )
            _record_mode5_operation_seconds(plan, "block_loop_videos", block_started)
        else:
            await _ensure_mode5_looped_intro_video(session_id, plan, force=False)
        _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_AFTER_SLICES)
        await checkpoint(control)

        return await _finalize_mode5_outputs(
            session_id,
            plan,
            skip_final_assembly=skip_final_assembly,
            review_log_message="=== Mode 5 RESUME REVIEW READY ===",
            done_log_message="=== Mode 5 RESUME DONE ===",
        )

    par = _mode5_chunk_lane_parallel(_mode5_facts50_image_parallel(), plan)
    sem_img = asyncio.Semaphore(par)
    logger.info("[Mode5 facts50 resume] Image chunk lanes={}", par)

    if (not skip_segment_images_on_resume) and (not all(_mode5_chunk_images_complete(session_root, ch) for ch in chunks)):

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
                    sub_mode=mode_key,
                    max_parallel_images=mpi,
                    image_backend=plan.get("image_backend"),
                    refresh_all=False,
                    topic_seed_override=str(plan.get("facts_topic") or plan.get("header_title") or ""),
                    cancel_event=fg_cancel_event,
                )
                _save_mode5_plan(
                    session_id, plan, checkpoint=MODE5_CKPT_AFTER_IMAGES, chunk_index=idx
                )

        await _mode5_await_chunk_coroutines([_resume_one_images(ch) for ch in chunks], plan)
        await checkpoint(control)

    for ch in chunks:
        if not _mode5_chunk_slices_complete(session_root, ch):
            _render_chunk_audio_slices(session_id, ch)
    if _mode5_block_loop_applies(plan):
        block_started = time.monotonic()
        await _ensure_mode5_block_loop_videos(
            session_id,
            plan,
            force=False,
            cancel_event=fg_cancel_event,
        )
        _record_mode5_operation_seconds(plan, "block_loop_videos", block_started)
    else:
        await _ensure_mode5_looped_intro_video(session_id, plan, force=False)
    _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_AFTER_SLICES)
    await checkpoint(control)

    return await _finalize_mode5_outputs(
        session_id,
        plan,
        skip_final_assembly=skip_final_assembly,
        review_log_message="=== Mode 5 RESUME REVIEW READY ===",
        done_log_message="=== Mode 5 RESUME DONE ===",
    )


async def regenerate_mode5_image(
    session_id: str,
    chunk_index: int,
    segment_index: int,
    *,
    action_id: str | None = None,
) -> dict[str, Any]:
    plan = load_mode5_plan(session_id)
    _ensure_mode5_live_defaults(plan)
    existing = _mode5_find_action(plan, action_id)
    if existing is not None:
        _mode5_assert_duplicate_matches(
            existing,
            action="regenerate-image",
            chunk_index=chunk_index,
            segment_index=segment_index,
        )
        chunks = plan.get("chunks") or []
        if chunk_index < 0 or chunk_index >= len(chunks):
            raise ValueError("Invalid chunk_index")
        chunk = chunks[chunk_index]
        return {
            "ok": True,
            "action_id": str(existing.get("action_id") or action_id),
            "duplicate": True,
            "chunk_index": chunk_index,
            "segment_index": segment_index,
            "preview_relpath": chunk.get("preview_relpath"),
            "chunk_meta": _chunk_meta_public(chunk),
        }
    chunks = plan.get("chunks") or []
    if chunk_index < 0 or chunk_index >= len(chunks):
        raise ValueError("Invalid chunk_index")
    chunk = chunks[chunk_index]
    segs = chunk.get("segments") or []
    if segment_index < 0 or segment_index >= len(segs):
        raise ValueError("Invalid segment_index")
    seg = segs[segment_index]
    chunk["status"] = "dirty"
    chunk["images_status"] = "regenerating"
    chunk["preview_status"] = "dirty"
    seg["last_action"] = "regenerate_image"
    seg["dirty_reason"] = "image_regenerated_requires_preview_rebuild"
    seg_prompt_text = seg.get("text", "")
    locked_style = _ensure_mode5_style_lock(plan)
    context_parts = [
        _mode5_theme_anchor_context(plan, chunk, seg),
        _mode5_chunk_context_text(chunk, segment_index, window=1),
    ]
    chunk_context = " | ".join([x for x in context_parts if x])[:900]
    prompt = build_mode5_image_prompt(
        sub_mode=normalize_mode5_sub_mode(plan.get("sub_mode")),
        segment_text=seg_prompt_text,
        chunk_context=chunk_context,
        style_lock=locked_style,
        output_format=_mode5_output_format(),
    )
    prompt = _sanitize_mode5_image_prompt(prompt)
    seg["image_prompt"] = prompt
    session_root = _session_dir(session_id)
    img_path = session_root / seg["image"]
    await _generate_one_image(
        prompt,
        img_path,
        aspect_ratio=_mode5_image_aspect_ratio(),
        image_backend=plan.get("image_backend"),
    )
    seg["image_version"] = int(seg.get("image_version") or 1) + 1
    if _mode5_block_loop_applies(plan):
        await _ensure_mode5_block_loop_videos(session_id, plan, force=True)
    elif _is_global_intro_segment(chunk_index, segment_index):
        await _ensure_mode5_looped_intro_video(session_id, plan, force=True)
    loop = asyncio.get_event_loop()
    if _mode5_skip_chunk_previews(plan):
        await loop.run_in_executor(
            None,
            lambda: _mode5_refresh_final_video_from_plan_sync(session_id, plan),
        )
        chunk["preview_status"] = "skipped"
    else:
        await loop.run_in_executor(None, lambda: _build_chunk_preview_sync(session_id, chunk_index, plan))
        chunk["preview_status"] = "ready"
    chunk["status"] = "ready"
    chunk["images_status"] = "ready"
    seg["dirty_reason"] = ""
    if not _mode5_skip_chunk_previews(plan):
        pending = list(plan.get("pending_rebuilds") or [])
        if chunk_index not in pending:
            pending.append(chunk_index)
        plan["pending_rebuilds"] = pending
    queue_res: dict[str, Any] = {"action_id": "", "duplicate": False}
    skip_pv = _mode5_skip_chunk_previews(plan)

    def _mutate(latest: dict[str, Any]) -> None:
        chunks_latest = latest.get("chunks") or []
        chunks_src = plan.get("chunks") or []
        if chunk_index < 0 or chunk_index >= len(chunks_latest) or chunk_index >= len(chunks_src):
            raise ValueError("Invalid chunk_index")
        chunks_latest[chunk_index] = chunks_src[chunk_index]
        if not skip_pv:
            pending_latest = set(int(x) for x in list(latest.get("pending_rebuilds") or []))
            pending_latest.add(int(chunk_index))
            latest["pending_rebuilds"] = sorted(pending_latest)
        else:
            rem = {int(chunk_index)}
            latest["pending_rebuilds"] = sorted(
                set(int(x) for x in (latest.get("pending_rebuilds") or [])) - rem
            )
        _mode5_push_live_event(
            latest,
            "image_generated",
            chunk_index=chunk_index,
            segment_index=segment_index,
            image=str((chunks_src[chunk_index].get("segments") or [])[segment_index].get("image") or ""),
        )
        if not skip_pv:
            _mode5_push_live_event(
                latest,
                "preview_generated",
                chunk_index=chunk_index,
                preview_relpath=chunks_src[chunk_index].get("preview_relpath"),
            )
            _mode5_push_live_event(latest, "rebuild_required", chunk_index=chunk_index, target="final")
        aid, dup = _mode5_queue_action(
            latest,
            "regenerate-image",
            action_id=action_id,
            chunk_index=chunk_index,
            segment_index=segment_index,
        )
        queue_res["action_id"] = aid
        queue_res["duplicate"] = dup

    plan_latest = _update_mode5_plan_atomic(session_id, _mutate)
    chunk_latest = (plan_latest.get("chunks") or [])[chunk_index]
    return {
        "ok": True,
        "action_id": queue_res["action_id"],
        "duplicate": bool(queue_res["duplicate"]),
        "chunk_index": chunk_index,
        "segment_index": segment_index,
        "preview_relpath": chunk_latest.get("preview_relpath"),
        "chunk_meta": _chunk_meta_public(chunk_latest),
    }


async def regenerate_mode5_chunk(
    session_id: str,
    chunk_index: int,
    text: str,
    *,
    action_id: str | None = None,
) -> dict[str, Any]:
    plan = load_mode5_plan(session_id)
    _ensure_mode5_live_defaults(plan)
    existing = _mode5_find_action(plan, action_id)
    if existing is not None:
        _mode5_assert_duplicate_matches(
            existing,
            action="regenerate-chunk",
            chunk_index=chunk_index,
        )
        chunks = plan.get("chunks") or []
        if chunk_index < 0 or chunk_index >= len(chunks):
            raise ValueError("Invalid chunk_index")
        chunk = chunks[chunk_index]
        return {
            "ok": True,
            "action_id": str(existing.get("action_id") or action_id),
            "duplicate": True,
            "chunk_index": chunk_index,
            "preview_relpath": chunk.get("preview_relpath"),
            "chunk_meta": _chunk_meta_public(chunk),
        }
    chunks = plan.get("chunks") or []
    if chunk_index < 0 or chunk_index >= len(chunks):
        raise ValueError("Invalid chunk_index")
    out = await _revoice_chunk(
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
    queue_res: dict[str, Any] = {"action_id": "", "duplicate": False}

    def _mutate(latest: dict[str, Any]) -> None:
        chunks_latest = latest.get("chunks") or []
        chunks_src = plan.get("chunks") or []
        if chunk_index < 0 or chunk_index >= len(chunks_latest) or chunk_index >= len(chunks_src):
            raise ValueError("Invalid chunk_index")
        chunks_latest[chunk_index] = chunks_src[chunk_index]
        latest["pending_rebuilds"] = [x for x in (latest.get("pending_rebuilds") or []) if int(x) != int(chunk_index)]
        _mode5_push_live_event(latest, "audio_generated", chunk_index=chunk_index)
        _mode5_push_live_event(
            latest,
            "preview_generated",
            chunk_index=chunk_index,
            preview_relpath=chunks_src[chunk_index].get("preview_relpath"),
        )
        aid, dup = _mode5_queue_action(
            latest, "regenerate-chunk", action_id=action_id, chunk_index=chunk_index
        )
        queue_res["action_id"] = aid
        queue_res["duplicate"] = dup

    plan_latest = _update_mode5_plan_atomic(session_id, _mutate)
    chunk_latest = (plan_latest.get("chunks") or [])[chunk_index]
    out["preview_relpath"] = chunk_latest.get("preview_relpath")
    out["chunk_meta"] = _chunk_meta_public(chunk_latest)
    out["action_id"] = queue_res["action_id"]
    out["duplicate"] = bool(queue_res["duplicate"])
    return out


async def regenerate_mode5_audio(
    session_id: str,
    chunk_index: int,
    *,
    action_id: str | None = None,
) -> dict[str, Any]:
    plan = load_mode5_plan(session_id)
    _ensure_mode5_live_defaults(plan)
    existing = _mode5_find_action(plan, action_id)
    if existing is not None:
        _mode5_assert_duplicate_matches(
            existing,
            action="regenerate-audio",
            chunk_index=chunk_index,
        )
        chunks = plan.get("chunks") or []
        if chunk_index < 0 or chunk_index >= len(chunks):
            raise ValueError("Invalid chunk_index")
        chunk = chunks[chunk_index]
        return {
            "ok": True,
            "action_id": str(existing.get("action_id") or action_id),
            "duplicate": True,
            "chunk_index": chunk_index,
            "preview_relpath": chunk.get("preview_relpath"),
            "chunk_meta": _chunk_meta_public(chunk),
        }
    chunks = plan.get("chunks") or []
    if chunk_index < 0 or chunk_index >= len(chunks):
        raise ValueError("Invalid chunk_index")
    text = str(chunks[chunk_index].get("text") or "").strip()
    if not text:
        raise ValueError("Mode 5: empty chunk text for audio regenerate")
    out = await _revoice_chunk(
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
    queue_res: dict[str, Any] = {"action_id": "", "duplicate": False}

    def _mutate(latest: dict[str, Any]) -> None:
        chunks_latest = latest.get("chunks") or []
        chunks_src = plan.get("chunks") or []
        if chunk_index < 0 or chunk_index >= len(chunks_latest) or chunk_index >= len(chunks_src):
            raise ValueError("Invalid chunk_index")
        chunks_latest[chunk_index] = chunks_src[chunk_index]
        latest["pending_rebuilds"] = [x for x in (latest.get("pending_rebuilds") or []) if int(x) != int(chunk_index)]
        _mode5_push_live_event(latest, "audio_generated", chunk_index=chunk_index)
        _mode5_push_live_event(
            latest,
            "preview_generated",
            chunk_index=chunk_index,
            preview_relpath=chunks_src[chunk_index].get("preview_relpath"),
        )
        aid, dup = _mode5_queue_action(
            latest, "regenerate-audio", action_id=action_id, chunk_index=chunk_index
        )
        queue_res["action_id"] = aid
        queue_res["duplicate"] = dup

    plan_latest = _update_mode5_plan_atomic(session_id, _mutate)
    chunk_latest = (plan_latest.get("chunks") or [])[chunk_index]
    out["preview_relpath"] = chunk_latest.get("preview_relpath")
    out["chunk_meta"] = _chunk_meta_public(chunk_latest)
    out["action_id"] = queue_res["action_id"]
    out["duplicate"] = bool(queue_res["duplicate"])
    return out


def _mode5_block_map_by_chunk_index(
    session_id: str,
    plan: dict[str, Any],
) -> tuple[dict[int, list[int]], dict[int, list[int]]]:
    """Return (chunk_index -> block_ids, block_id -> sorted chunk indices) by cumulative audio timeline."""
    session_root = _session_dir(session_id)
    chunks = sorted(plan.get("chunks") or [], key=lambda c: int(c.get("index") or 0))
    block_sec = float(getattr(settings, "mode5_block_loop_seconds", 1800.0) or 1800.0)
    block_sec = max(60.0, min(14400.0, block_sec))
    pool_size = _mode5_block_loop_pool_size()
    chunk_to_blocks: dict[int, set[int]] = {}
    block_to_chunks: dict[int, set[int]] = {}
    cumulative = 0.0
    for ch in chunks:
        ch_idx = int(ch.get("index") or 0)
        segs = sorted((ch.get("segments") or []), key=lambda s: int(s.get("s", 0)))
        for seg in segs:
            aud_rel = str(seg.get("audio") or "").strip()
            if not aud_rel:
                continue
            ap = session_root / aud_rel
            if not ap.is_file():
                continue
            dur = _wav_duration_sec(ap)
            bid_raw = int(cumulative // block_sec)
            bid = min(bid_raw, pool_size - 1)
            chunk_to_blocks.setdefault(ch_idx, set()).add(bid)
            block_to_chunks.setdefault(bid, set()).add(ch_idx)
            cumulative += dur
    chunk_to_blocks_sorted = {k: sorted(v) for k, v in chunk_to_blocks.items()}
    block_to_chunks_sorted = {k: sorted(v) for k, v in block_to_chunks.items()}
    return chunk_to_blocks_sorted, block_to_chunks_sorted


async def regenerate_mode5_block_loop_video(
    session_id: str,
    chunk_index: int,
    *,
    action_id: str | None = None,
) -> dict[str, Any]:
    plan = load_mode5_plan(session_id)
    _ensure_mode5_live_defaults(plan)
    if not _mode5_block_loop_applies(plan):
        raise ValueError("Mode5 block-loop animation is not enabled for this session")
    existing = _mode5_find_action(plan, action_id)
    if existing is not None:
        _mode5_assert_duplicate_matches(
            existing,
            action="regenerate-block-loop",
            chunk_index=chunk_index,
        )
        c2bs, b2c = _mode5_block_map_by_chunk_index(session_id, plan)
        bids = list(c2bs.get(int(chunk_index), []))
        affected_set: set[int] = set()
        for _bid in bids:
            affected_set.update(int(x) for x in b2c.get(int(_bid), []))
        affected = sorted(affected_set)
        return {
            "ok": True,
            "action_id": str(existing.get("action_id") or action_id),
            "duplicate": True,
            "chunk_index": int(chunk_index),
            "block_loop_id": int(bids[0]) if bids else None,
            "block_loop_ids": [int(x) for x in bids],
            "affected_chunks": affected,
        }
    c2bs, b2c = _mode5_block_map_by_chunk_index(session_id, plan)
    if int(chunk_index) not in c2bs:
        raise ValueError("Invalid chunk_index for block-loop regeneration")
    target_bids = [int(x) for x in c2bs[int(chunk_index)]]
    affected_set: set[int] = set()
    for bid in target_bids:
        affected_set.update(int(x) for x in b2c.get(int(bid), []))
    affected_chunks = sorted(affected_set) if affected_set else [int(chunk_index)]

    await _ensure_mode5_block_loop_videos(
        session_id,
        plan,
        force=True,
        target_block_ids=set(target_bids),
    )
    loop = asyncio.get_event_loop()
    if _mode5_skip_chunk_previews(plan):
        await loop.run_in_executor(
            None,
            lambda: _mode5_refresh_final_video_from_plan_sync(session_id, plan),
        )
    else:
        for ch_idx in affected_chunks:
            await loop.run_in_executor(None, lambda ci=ch_idx: _build_chunk_preview_sync(session_id, ci, plan))

    queue_res: dict[str, Any] = {"action_id": "", "duplicate": False}
    skip_pv = _mode5_skip_chunk_previews(plan)

    def _mutate(latest: dict[str, Any]) -> None:
        chunks_latest = latest.get("chunks") or []
        chunks_src = plan.get("chunks") or []
        for ch_idx in affected_chunks:
            if ch_idx < 0 or ch_idx >= len(chunks_latest) or ch_idx >= len(chunks_src):
                continue
            chunks_latest[ch_idx] = chunks_src[ch_idx]
        if not skip_pv:
            pending_latest = set(int(x) for x in list(latest.get("pending_rebuilds") or []))
            pending_latest.update(int(x) for x in affected_chunks)
            latest["pending_rebuilds"] = sorted(pending_latest)
        else:
            rem = set(int(x) for x in affected_chunks)
            latest["pending_rebuilds"] = sorted(
                set(int(x) for x in (latest.get("pending_rebuilds") or [])) - rem
            )
        _mode5_push_live_event(
            latest,
            "block_loop_regenerated",
            chunk_index=int(chunk_index),
            block_loop_id=int(target_bids[0]) if target_bids else None,
            block_loop_ids=target_bids,
            affected_chunks=affected_chunks,
        )
        if not skip_pv:
            _mode5_push_live_event(latest, "rebuild_required", chunk_index=int(chunk_index), target="final")
        aid, dup = _mode5_queue_action(
            latest,
            "regenerate-block-loop",
            action_id=action_id,
            chunk_index=int(chunk_index),
            block_loop_id=int(target_bids[0]) if target_bids else None,
            block_loop_ids=target_bids,
            affected_chunks=affected_chunks,
        )
        queue_res["action_id"] = aid
        queue_res["duplicate"] = dup

    plan_latest = _update_mode5_plan_atomic(session_id, _mutate)
    metas = [_chunk_meta_public(ch) for ch in (plan_latest.get("chunks") or [])]
    return {
        "ok": True,
        "action_id": queue_res["action_id"],
        "duplicate": bool(queue_res["duplicate"]),
        "chunk_index": int(chunk_index),
        "block_loop_id": int(target_bids[0]) if target_bids else None,
        "block_loop_ids": target_bids,
        "affected_chunks": affected_chunks,
        "chunks_meta": metas,
    }


async def regenerate_mode5_intro_preview(
    session_id: str,
    preview_index: int,
    *,
    action_id: str | None = None,
) -> dict[str, Any]:
    plan = load_mode5_plan(session_id)
    _ensure_mode5_live_defaults(plan)
    if not bool(plan.get("await_intro_confirmation")):
        raise ValueError("Intro preview regeneration is available only before confirmation")
    rels = list(plan.get("intro_preview_videos") or [])
    if not rels:
        raise ValueError("No intro preview videos available")
    if preview_index < 0 or preview_index >= len(rels):
        raise ValueError("Invalid preview_index")

    existing = _mode5_find_action(plan, action_id)
    if existing is not None:
        _mode5_assert_duplicate_matches(
            existing,
            action="regenerate-intro-preview",
            preview_index=int(preview_index),
        )
        return {
            "ok": True,
            "action_id": str(existing.get("action_id") or action_id),
            "duplicate": True,
            "preview_index": int(preview_index),
            "intro_preview_videos": rels,
        }

    sm = str(plan.get("sub_mode") or "manual").strip().lower()
    topic_seed = (
        str(plan.get("facts_topic") or "").strip()
        or str(plan.get("header_title") or "").strip()
        or str(plan.get("source_input_text") or plan.get("script_text") or "").strip()
    )
    regenerated_rel = await _regenerate_mode5_intro_confirmation_item(
        session_id=session_id,
        sub_mode=sm,
        topic_seed=topic_seed,
        target_index=int(preview_index),
        total_variants=len(rels),
        image_backend=plan.get("image_backend"),
    )
    rels[preview_index] = regenerated_rel
    queue_res: dict[str, Any] = {"action_id": "", "duplicate": False}

    def _mutate(latest: dict[str, Any]) -> None:
        latest_rels = list(latest.get("intro_preview_videos") or [])
        if preview_index < 0 or preview_index >= len(latest_rels):
            raise ValueError("Invalid preview_index")
        latest_rels[preview_index] = rels[preview_index]
        latest["intro_preview_videos"] = latest_rels
        latest["intro_preview_video"] = latest_rels[0] if latest_rels else None
        _mode5_push_live_event(
            latest,
            "intro_preview_regenerated",
            preview_index=int(preview_index),
            preview_relpath=rels[preview_index],
        )
        aid, dup = _mode5_queue_action(
            latest,
            "regenerate-intro-preview",
            action_id=action_id,
            preview_index=int(preview_index),
        )
        queue_res["action_id"] = aid
        queue_res["duplicate"] = dup

    updated = _update_mode5_plan_atomic(session_id, _mutate)
    return {
        "ok": True,
        "action_id": queue_res["action_id"],
        "duplicate": bool(queue_res["duplicate"]),
        "preview_index": int(preview_index),
        "intro_preview_videos": list(updated.get("intro_preview_videos") or []),
        "mode5_intro_preview_videos": list(updated.get("intro_preview_videos") or []),
    }


async def rebuild_mode5_chunk_preview(
    session_id: str,
    chunk_index: int,
    *,
    action_id: str | None = None,
) -> dict[str, Any]:
    plan = load_mode5_plan(session_id)
    _ensure_mode5_live_defaults(plan)
    existing = _mode5_find_action(plan, action_id)
    if existing is not None:
        _mode5_assert_duplicate_matches(
            existing,
            action="rebuild-chunk-preview",
            chunk_index=chunk_index,
        )
        chunks = plan.get("chunks") or []
        if chunk_index < 0 or chunk_index >= len(chunks):
            raise ValueError("Invalid chunk_index")
        chunk = chunks[chunk_index]
        return {
            "ok": True,
            "action_id": str(existing.get("action_id") or action_id),
            "duplicate": True,
            "chunk_index": chunk_index,
            "preview_relpath": chunk.get("preview_relpath"),
            "chunk_meta": _chunk_meta_public(chunk),
        }
    chunks = plan.get("chunks") or []
    if chunk_index < 0 or chunk_index >= len(chunks):
        raise ValueError("Invalid chunk_index")
    chunk = chunks[chunk_index]
    chunk["preview_status"] = "regenerating"
    chunk["status"] = "regenerating"
    loop = asyncio.get_event_loop()
    if _mode5_skip_chunk_previews(plan):
        await loop.run_in_executor(
            None,
            lambda: _mode5_refresh_final_video_from_plan_sync(session_id, plan),
        )
        chunk["preview_status"] = "skipped"
    else:
        await loop.run_in_executor(None, lambda: _build_chunk_preview_sync(session_id, chunk_index, plan))
        chunk["preview_status"] = "ready"
    chunk["status"] = "ready"
    chunk["version"] = int(chunk.get("version") or 1) + 1
    pending = [x for x in (plan.get("pending_rebuilds") or []) if int(x) != int(chunk_index)]
    plan["pending_rebuilds"] = pending
    queue_res: dict[str, Any] = {"action_id": "", "duplicate": False}

    def _mutate(latest: dict[str, Any]) -> None:
        chunks_latest = latest.get("chunks") or []
        chunks_src = plan.get("chunks") or []
        if chunk_index < 0 or chunk_index >= len(chunks_latest) or chunk_index >= len(chunks_src):
            raise ValueError("Invalid chunk_index")
        chunks_latest[chunk_index] = chunks_src[chunk_index]
        latest["pending_rebuilds"] = [x for x in (latest.get("pending_rebuilds") or []) if int(x) != int(chunk_index)]
        _mode5_push_live_event(
            latest,
            "preview_generated",
            chunk_index=chunk_index,
            preview_relpath=chunks_src[chunk_index].get("preview_relpath"),
        )
        aid, dup = _mode5_queue_action(
            latest, "rebuild-chunk-preview", action_id=action_id, chunk_index=chunk_index
        )
        queue_res["action_id"] = aid
        queue_res["duplicate"] = dup

    plan_latest = _update_mode5_plan_atomic(session_id, _mutate)
    chunk_latest = (plan_latest.get("chunks") or [])[chunk_index]
    return {
        "ok": True,
        "action_id": queue_res["action_id"],
        "duplicate": bool(queue_res["duplicate"]),
        "chunk_index": chunk_index,
        "preview_relpath": chunk_latest.get("preview_relpath"),
        "chunk_meta": _chunk_meta_public(chunk_latest),
    }


async def regenerate_mode5_publish_thumbnail(
    session_id: str,
    *,
    action_id: str | None = None,
) -> dict[str, Any]:
    plan = load_mode5_plan(session_id)
    _ensure_mode5_live_defaults(plan)
    existing = _mode5_find_action(plan, action_id)
    if existing is not None:
        _mode5_assert_duplicate_matches(existing, action="regenerate-publish-thumbnail")
        rel = str(plan.get("publish_thumbnail_rel") or "").strip()
        return {
            "ok": True,
            "action_id": str(existing.get("action_id") or action_id),
            "duplicate": True,
            "thumbnail_relpath": rel or None,
            "publishing": plan.get("publishing") if isinstance(plan.get("publishing"), dict) else None,
        }

    await _mode5_generate_publish_assets(session_id, plan, force_thumbnail=True)
    rel = str(plan.get("publish_thumbnail_rel") or "").strip()
    queue_res: dict[str, Any] = {"action_id": "", "duplicate": False}

    def _mutate(latest: dict[str, Any]) -> None:
        if isinstance(plan.get("publishing"), dict):
            latest["publishing"] = plan.get("publishing")
        if rel:
            latest["publish_thumbnail_rel"] = rel
        _mode5_push_live_event(latest, "publish_thumbnail_regenerated", thumbnail_relpath=rel or None)
        aid, dup = _mode5_queue_action(
            latest,
            "regenerate-publish-thumbnail",
            action_id=action_id,
            thumbnail_relpath=rel or None,
        )
        queue_res["action_id"] = aid
        queue_res["duplicate"] = dup

    latest = _update_mode5_plan_atomic(session_id, _mutate, checkpoint=MODE5_CKPT_COMPLETED)
    return {
        "ok": True,
        "action_id": queue_res["action_id"],
        "duplicate": bool(queue_res["duplicate"]),
        "thumbnail_relpath": rel or None,
        "publishing": latest.get("publishing") if isinstance(latest.get("publishing"), dict) else None,
    }


def set_mode5_chunk_lock(
    session_id: str,
    chunk_index: int,
    locked: bool,
    *,
    action_id: str | None = None,
) -> dict[str, Any]:
    plan = load_mode5_plan(session_id)
    _ensure_mode5_live_defaults(plan)
    existing = _mode5_find_action(plan, action_id)
    if existing is not None:
        _mode5_assert_duplicate_matches(
            existing,
            action="pause-chunk" if locked else "resume-chunk",
            chunk_index=chunk_index,
        )
        chunks = plan.get("chunks") or []
        if chunk_index < 0 or chunk_index >= len(chunks):
            raise ValueError("Invalid chunk_index")
        chunk = chunks[chunk_index]
        return {
            "ok": True,
            "action_id": str(existing.get("action_id") or action_id),
            "duplicate": True,
            "chunk_index": chunk_index,
            "locked": bool(chunk.get("locked")),
            "chunk_meta": _chunk_meta_public(chunk),
        }
    queued_action_id = {"value": ""}

    def _mutate(latest: dict[str, Any]) -> None:
        chunks_latest = latest.get("chunks") or []
        if chunk_index < 0 or chunk_index >= len(chunks_latest):
            raise ValueError("Invalid chunk_index")
        chunk_latest = chunks_latest[chunk_index]
        was_locked = bool(chunk_latest.get("locked"))
        chunk_latest["locked"] = bool(locked)
        if locked:
            if not was_locked:
                chunk_latest["status_before_lock"] = str(chunk_latest.get("status") or "ready")
            chunk_latest["status"] = "paused"
        else:
            prev_status = str(chunk_latest.get("status_before_lock") or "").strip()
            if prev_status and prev_status != "paused":
                chunk_latest["status"] = prev_status
            elif not str(chunk_latest.get("status") or "").strip() or str(chunk_latest.get("status")) == "paused":
                chunk_latest["status"] = "ready"
            chunk_latest.pop("status_before_lock", None)
        _mode5_push_live_event(
            latest,
            "chunk_state_changed",
            chunk_index=chunk_index,
            status=chunk_latest["status"],
        )
        queued_action_id["value"], _ = _mode5_queue_action(
            latest,
            "pause-chunk" if locked else "resume-chunk",
            action_id=action_id,
            chunk_index=chunk_index,
        )

    plan_latest = _update_mode5_plan_atomic(session_id, _mutate)
    chunk = (plan_latest.get("chunks") or [])[chunk_index]
    return {
        "ok": True,
        "action_id": queued_action_id["value"],
        "duplicate": False,
        "chunk_index": chunk_index,
        "locked": bool(locked),
        "chunk_meta": _chunk_meta_public(chunk),
    }


def rebuild_mode5_final_sync(session_id: str, *, action_id: str | None = None) -> dict[str, Any]:
    plan = load_mode5_plan(session_id)
    _ensure_mode5_live_defaults(plan)
    existing = _mode5_find_action(plan, action_id)
    if existing is not None:
        _mode5_assert_duplicate_matches(existing, action="rebuild-final")
        session_root = _session_dir(session_id)
        final_path = session_root / "video_mode5.mp4"
        rel = _rel_session(session_root, final_path) if final_path.is_file() else None
        out = _result_payload(session_id, plan, review_ready=not bool(rel), final_video=rel)
        out["action_id"] = str(existing.get("action_id") or action_id)
        out["duplicate"] = True
        return out
    session_root = _session_dir(session_id)
    queue_res: dict[str, Any] = {"action_id": "", "duplicate": False}

    if _mode5_skip_chunk_previews(plan):
        final_path = _mode5_refresh_final_video_from_plan_sync(session_id, plan)
        _mode5_generate_publish_assets_sync(session_id, plan, force_thumbnail=False)
        rel = _rel_session(session_root, final_path)

        def _mutate_direct(latest: dict[str, Any]) -> None:
            latest["pending_rebuilds"] = []
            if isinstance(plan.get("publishing"), dict):
                latest["publishing"] = plan.get("publishing")
            if str(plan.get("publish_thumbnail_rel") or "").strip():
                latest["publish_thumbnail_rel"] = str(plan.get("publish_thumbnail_rel")).strip()
            _mode5_push_live_event(latest, "final_generated", chunk_index=None, video_path=rel)
            aid, dup = _mode5_queue_action(
                latest, "rebuild-final", action_id=action_id, video_path=rel
            )
            queue_res["action_id"] = aid
            queue_res["duplicate"] = dup

        plan_latest = _update_mode5_plan_atomic(
            session_id, _mutate_direct, checkpoint=MODE5_CKPT_COMPLETED
        )
        out = _result_payload(session_id, plan_latest, review_ready=False, final_video=rel)
        out["action_id"] = queue_res["action_id"]
        out["duplicate"] = bool(queue_res["duplicate"])
        return out

    _rebuild_mode5_missing_previews(session_id, plan)
    readiness = mode5_preview_readiness(session_id, plan)
    if not bool(readiness.get("can_assemble")):
        ready = int(readiness.get("ready_count") or 0)
        total = int(readiness.get("total_count") or 0)
        raise ValueError(
            f"Mode 5 previews are not ready for final rebuild yet: {ready}/{total} valid chunks."
        )
    previews = [session_root / rel for rel in readiness["ready_relpaths"]]
    final_path = session_root / "video_mode5.mp4"
    _ffmpeg_concat(previews, final_path)
    final_path = _append_mode5_sleep_tail(session_id, plan, final_path)
    _mode5_generate_publish_assets_sync(session_id, plan, force_thumbnail=False)
    rel = _rel_session(session_root, final_path)

    def _mutate(latest: dict[str, Any]) -> None:
        latest["pending_rebuilds"] = []
        if isinstance(plan.get("publishing"), dict):
            latest["publishing"] = plan.get("publishing")
        if str(plan.get("publish_thumbnail_rel") or "").strip():
            latest["publish_thumbnail_rel"] = str(plan.get("publish_thumbnail_rel")).strip()
        _mode5_push_live_event(
            latest, "final_generated", chunk_index=None, video_path=rel
        )
        aid, dup = _mode5_queue_action(
            latest, "rebuild-final", action_id=action_id, video_path=rel
        )
        queue_res["action_id"] = aid
        queue_res["duplicate"] = dup

    plan_latest = _update_mode5_plan_atomic(
        session_id, _mutate, checkpoint=MODE5_CKPT_COMPLETED
    )
    out = _result_payload(session_id, plan_latest, review_ready=False, final_video=rel)
    out["action_id"] = queue_res["action_id"]
    out["duplicate"] = bool(queue_res["duplicate"])
    return out


def assemble_mode5_final_sync(session_id: str) -> dict[str, Any]:
    plan = load_mode5_plan(session_id)
    session_root = _session_dir(session_id)
    if _mode5_skip_chunk_previews(plan):
        final_path = _mode5_refresh_final_video_from_plan_sync(session_id, plan)
        _mode5_generate_publish_assets_sync(session_id, plan, force_thumbnail=False)
        rel = _rel_session(session_root, final_path)
        _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_COMPLETED)
        return _result_payload(session_id, plan, review_ready=False, final_video=rel)
    _rebuild_mode5_missing_previews(session_id, plan)
    readiness = mode5_preview_readiness(session_id, plan)
    if not bool(readiness.get("can_assemble")):
        ready = int(readiness.get("ready_count") or 0)
        total = int(readiness.get("total_count") or 0)
        raise ValueError(
            f"Mode 5 previews are not ready for final assembly yet: {ready}/{total} valid chunks."
        )
    previews = [session_root / rel for rel in readiness["ready_relpaths"]]
    final_path = session_root / "video_mode5.mp4"
    _ffmpeg_concat(previews, final_path)
    final_path = _append_mode5_sleep_tail(session_id, plan, final_path)
    _mode5_generate_publish_assets_sync(session_id, plan, force_thumbnail=False)
    rel = _rel_session(session_root, final_path)
    _save_mode5_plan(session_id, plan, checkpoint=MODE5_CKPT_COMPLETED)
    return _result_payload(session_id, plan, review_ready=False, final_video=rel)


def mode5_sidebar_flags_from_plan(session_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    """Лёгкий снимок для /api/pipeline/sessions без полного result_payload."""
    _ensure_mode5_live_defaults(plan)
    if bool(plan.get("review_dismissed")):
        label = (plan.get("header_title") or "").strip() or f"Long-form #{session_id[-8:]}"
        return {
            "topic": label,
            "mode5_runtime_status": "done",
            "mode5_waiting_confirmation": False,
            "mode5_await_intro_confirmation": False,
            "mode5_review_ready": False,
            "mode5_can_resume": False,
            "mode5_pipeline_paused": False,
            "mode5_can_assemble": False,
            "mode5_ready_chunks": 0,
            "mode5_total_chunks": 0,
            "review_dismissed": True,
        }
    snap = mode5_resume_snapshot_for_plan(session_id, plan)
    readiness = mode5_preview_readiness(session_id, plan, strict=False)
    label = (plan.get("header_title") or "").strip() or f"Long-form #{session_id[-8:]}"
    has_dirty = any(
        str(ch.get("status") or "") in {"dirty", "regenerating"} or bool(ch.get("locked"))
        for ch in list(plan.get("chunks") or [])
    )
    has_pending = bool(list(plan.get("pending_rebuilds") or []))
    session_root = _session_dir(session_id)
    final_path = session_root / "video_mode5.mp4"
    has_final = final_path.is_file() and not has_dirty and not has_pending
    waiting_confirmation = bool(plan.get("await_intro_confirmation"))
    review_ready = bool(readiness.get("can_assemble")) and not has_final
    if bool(plan.get("pipeline_paused")) and bool(snap.get("can_resume")):
        runtime_status = "paused"
    elif has_dirty or has_pending:
        runtime_status = "running"
    else:
        runtime_status = "done"
    return {
        "topic": label,
        "mode5_runtime_status": runtime_status,
        "mode5_waiting_confirmation": waiting_confirmation,
        "mode5_await_intro_confirmation": waiting_confirmation,
        "mode5_review_ready": review_ready,
        "mode5_can_resume": bool(snap.get("can_resume")),
        "mode5_pipeline_paused": bool(plan.get("pipeline_paused")),
        "mode5_can_assemble": bool(readiness.get("can_assemble")) and not has_final,
        "mode5_ready_chunks": readiness["ready_count"],
        "mode5_total_chunks": readiness["total_count"],
    }


def mode5_status_from_plan(session_id: str) -> dict[str, Any]:
    """
    Rebuild Mode 5 status payload from persisted plan when in-memory session is missing.
    Used by /api/pipeline/{sid}/status for History -> Progress navigation after restart.
    """
    plan = load_mode5_plan(session_id)
    _ensure_mode5_live_defaults(plan)
    session_root = _session_dir(session_id)
    final_path = session_root / "video_mode5.mp4"
    has_dirty = any(
        str(ch.get("status") or "") in {"dirty", "regenerating"} or bool(ch.get("locked"))
        for ch in list(plan.get("chunks") or [])
    )
    has_pending_rebuilds = bool(list(plan.get("pending_rebuilds") or []))
    if final_path.is_file():
        # If content became dirty after final build, do not report final as authoritative.
        if not has_dirty and not has_pending_rebuilds:
            rel = _rel_session(session_root, final_path)
            out = _attach_mode5_resume_flags_from_plan(
                session_id, plan, _result_payload(session_id, plan, review_ready=False, final_video=rel)
            )
            out["mode5_runtime_status"] = "done"
            out.update(_mode5_progress_hint_payload(session_id, plan))
            return out
    out = _attach_mode5_resume_flags_from_plan(
        session_id, plan, _result_payload(session_id, plan, review_ready=True)
    )
    if bool(plan.get("pipeline_paused")) and bool(out.get("mode5_can_resume")):
        out["mode5_runtime_status"] = "paused"
    else:
        out["mode5_runtime_status"] = "running" if (has_dirty or has_pending_rebuilds) else "done"
    out.update(_mode5_progress_hint_payload(session_id, plan))
    return out


def mode5_review_snapshot(session_id: str) -> dict[str, Any]:
    """
    Return currently ready Mode 5 previews from persisted plan, even before pipeline completion.
    """
    try:
        plan = load_mode5_plan(session_id)
    except FileNotFoundError:
        return _mode5_review_pending_snapshot(session_id)
    session_root = _session_dir(session_id)
    _ensure_mode5_live_defaults(plan)
    chunks = list(plan.get("chunks") or [])
    ready_chunks: list[dict[str, Any]] = []
    for ch in chunks:
        rel = str(ch.get("preview_relpath") or "").strip()
        if not rel:
            continue
        p = session_root / rel
        ch["preview_ready"] = _mode5_preview_file_ready(p)
        if ch["preview_ready"]:
            ready_chunks.append(ch)
    payload = _result_payload(session_id, {**plan, "chunks": ready_chunks}, review_ready=bool(ready_chunks))
    payload["mode5_total_chunks"] = len(chunks)
    payload["mode5_ready_chunks"] = len(ready_chunks)
    payload["mode5_can_assemble"] = len(chunks) > 0 and len(ready_chunks) == len(chunks)
    payload["mode5_partial"] = True
    snap = mode5_resume_snapshot_for_plan(session_id, plan)
    payload["mode5_can_resume"] = bool(snap.get("can_resume"))
    payload["mode5_checkpoint_stage"] = snap.get("stage")
    payload["mode5_resume_reason"] = snap.get("reason") or None
    payload["mode5_pipeline_paused"] = bool(plan.get("pipeline_paused"))
    payload["mode5_unfinished_actions"] = [
        {
            "chunk_index": int(ch.get("index") or 0),
            "status": str(ch.get("status") or "pending"),
            "locked": bool(ch.get("locked")),
        }
        for ch in chunks
        if str(ch.get("status") or "") in {"regenerating", "dirty"} or bool(ch.get("locked"))
    ]
    prog = _mode5_progress_hint_payload(session_id, plan)
    payload.update(prog)
    return payload
