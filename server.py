"""
FastAPI web server for AI Content Factory.

Run:  uvicorn server:app --reload --port 8000 --reload-exclude .venv --reload-exclude MyVideo
"""

from __future__ import annotations

import asyncio
import functools
import json
import os
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from urllib.parse import quote

from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel, field_validator, model_validator

from config import settings
from casino_routes import register_casino_routes

# ── Session store ─────────────────────────────────────────────────────────────
_sessions: dict[str, dict] = {}

# ── YouTube OAuth (state → unix time) ─────────────────────────────────────────
_youtube_oauth_states: dict[str, float] = {}

# Statuses: running | paused | done | error | cancelled


# ── Log capture per session ───────────────────────────────────────────────────

class _SessionSink:
    """Loguru sink that pushes structured log records into a per-session queue."""

    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop) -> None:
        self._q = queue
        self._loop = loop

    def __call__(self, message) -> None:
        rec = message.record
        entry = {
            "type": "log",
            "time": rec["time"].strftime("%H:%M:%S"),
            "level": rec["level"].name,       # DEBUG INFO SUCCESS WARNING ERROR
            "text": rec["message"],
        }
        try:
            if self._loop.is_closed():
                return
            asyncio.run_coroutine_threadsafe(self._q.put(entry), self._loop)
        except (RuntimeError, asyncio.CancelledError):
            pass
        except Exception:
            # Не роняем поток loguru при закрытии loop / пиковой нагрузке (FastGen в фоне)
            pass


# ── Pipeline runner ───────────────────────────────────────────────────────────


def _session_topic_from_request(req: "StartRequest") -> str:
    """Короткая подпись сессии для списка «В работе» и статуса."""
    m = getattr(req, "mode", None)
    if m == 10:
        bt = (getattr(req, "mode10_beach_type", None) or "").strip()
        cs = (getattr(req, "mode10_coast_setting", None) or "").strip()
        if bt or cs:
            return f"Уборка пляжа: {bt or '?'} / {cs or '?'}"[:100]
        return "Уборка пляжа (таймлапс)"
    if m == 11:
        st = (getattr(req, "mode11_structure_type", None) or "").strip()
        if st:
            return f"Памятник: {st}"[:100]
        return "Памятники (деконструкция)"
    if m == 8:
        hs = (getattr(req, "mode8_house_style", None) or "").strip()
        loc = (getattr(req, "mode8_location", None) or "").strip()
        if hs or loc:
            return f"Таймлапс: {hs or '?'} / {loc or '?'}"[:100]
        return "Таймлапс строительства"
    if m == 7:
        at = (getattr(req, "mode7_animal_type", None) or "").strip() or "random"
        return f"ASMR Keyboard ({at})"
    if m == 6:
        n = int(getattr(req, "mode6_num_characters", 3) or 3)
        return f"Cartoon drama · персонажей: {n}"
    if m == 4:
        from modes.mode4.quote_format import format_quote_caption

        q = getattr(req, "mode4_quote", None) or ""
        pn = getattr(req, "mode4_person_name", None) or ""
        cap = format_quote_caption(q, pn)
        base = (cap[:200] if cap else "Цитата").rstrip()
        ol = (getattr(req, "mode4_only_lang", None) or "").strip().lower()
        if ol == "ru":
            return f"{base} · RU"
        if ol == "en":
            return f"{base} · EN"
        return f"{base} · RU+EN"
    if m == 13:
        return "Аудио → слайды (режим 13)"
    if m == 5:
        header = (getattr(req, "mode5_video_header_title", None) or "").strip()
        txt = (getattr(req, "mode5_script_text", None) or "").strip()
        if header:
            return header[:100]
        if txt:
            return f"Long-form: {txt[:90]}"
        return "Ручной long-form (режим 5)"
    return (
        req.topic
        or getattr(req, "mode3_topic", None)
        or (getattr(req, "mode4_quote", None) or "")[:80]
        or ""
    )


async def _run_pipeline_task(
    session_id: str,
    req: "StartRequest",
    queue: asyncio.Queue,
    control: dict,
) -> None:
    session = _sessions[session_id]
    sink_id: int | None = None
    try:
        loop = asyncio.get_event_loop()
        sink = _SessionSink(queue, loop)
        sink_id = logger.add(sink, format="{message}", level="DEBUG", enqueue=False)

        settings.ensure_dirs()

        from orchestrator.swarm import run_pipeline

        result = await run_pipeline(
            topic=req.topic,
            num_scenes=req.num_scenes,
            use_swarm=False,
            session_id=session_id,
            local_only=req.local_only,
            auto_topic=req.auto_topic,
            use_scenario=req.use_scenario,
            show_subtitles=req.show_subtitles,
            prebuilt_scenario=req.scenario,
            mode=req.mode,
            language=getattr(req, "language", "ru") or "ru",
            custom_title_bg_path=req.custom_title_bg_path,
            custom_outro_bg_path=req.custom_outro_bg_path,
            reference_image_path=req.reference_image_path,
            mode3_start_image_path=req.mode3_start_image_path,
            mode3_end_image_path=req.mode3_end_image_path,
            mode3_topic=req.mode3_topic,
            mode4_quote=getattr(req, "mode4_quote", None),
            mode4_person_name=getattr(req, "mode4_person_name", None),
            mode4_photo_path=getattr(req, "mode4_photo_path", None),
            mode4_only_lang=getattr(req, "mode4_only_lang", None),
            mode4_show_author_on_video=getattr(req, "mode4_show_author_on_video", True),
            mode4_video_header_title=getattr(req, "mode4_video_header_title", None),
            mode4_subtitle_style=getattr(req, "mode4_subtitle_style", "karaoke") or "karaoke",
            mode4_multiclip=getattr(req, "mode4_multiclip", False),
            mode4_segments=getattr(req, "mode4_segments", None),
            mode4_skip_final_assembly=getattr(req, "mode4_skip_final_assembly", True),
            mode5_script_text=getattr(req, "mode5_script_text", None),
            mode5_language=getattr(req, "mode5_language", None),
            mode5_chunk_seconds=int(getattr(req, "mode5_chunk_seconds", 300) or 300),
            mode5_segment_seconds=int(getattr(req, "mode5_segment_seconds", 15) or 15),
            mode5_skip_final_assembly=bool(getattr(req, "mode5_skip_final_assembly", True)),
            mode5_max_parallel_images=int(getattr(req, "mode5_max_parallel_images", 10) or 10),
            mode5_video_header_title=getattr(req, "mode5_video_header_title", None),
            mode5_bible_mode=bool(getattr(req, "mode5_bible_mode", False)),
            mode5_sub_mode=getattr(req, "mode5_sub_mode", "manual") or "manual",
            mode6_num_characters=getattr(req, "mode6_num_characters", 3),
            mode7_keyboards=getattr(req, "mode7_keyboards", None),
            mode7_animal_type=getattr(req, "mode7_animal_type", None),
            mode8_house_style=getattr(req, "mode8_house_style", None),
            mode8_location=getattr(req, "mode8_location", None),
            mode8_num_stages=getattr(req, "mode8_num_stages", 5),
            mode8_num_floors=getattr(req, "mode8_num_floors", 2),
            mode9_vehicle_type=getattr(req, "mode9_vehicle_type", None),
            mode9_location=getattr(req, "mode9_location", None),
            mode9_num_stages=getattr(req, "mode9_num_stages", 5),
            mode10_beach_type=getattr(req, "mode10_beach_type", None),
            mode10_coast_setting=getattr(req, "mode10_coast_setting", None),
            mode10_num_stages=getattr(req, "mode10_num_stages", 5),
            mode11_structure_type=getattr(req, "mode11_structure_type", None),
            mode11_num_stages=getattr(req, "mode11_num_stages", 5),
            mode13_audio_path=getattr(req, "mode13_audio_path", None),
            mode13_voice_preset=getattr(req, "mode13_voice_preset", "studio") or "studio",
            mode13_language=getattr(req, "mode13_language", None),
            mode13_show_subtitles=getattr(req, "mode13_show_subtitles", True),
            mode13_skip_final_assembly=getattr(req, "mode13_skip_final_assembly", True),
            mode13_chunk_seconds=int(getattr(req, "mode13_chunk_seconds", 300) or 300),
            mode13_segment_seconds=int(getattr(req, "mode13_segment_seconds", 30) or 30),
            mode13_video_header_title=getattr(req, "mode13_video_header_title", None),
            mode13_voice_gain_db=float(getattr(req, "mode13_voice_gain_db", 0.0) or 0.0),
            mode13_voice_tempo_scale=float(getattr(req, "mode13_voice_tempo_scale", 1.0) or 1.0),
            mode13_voice_pitch_semitones=float(getattr(req, "mode13_voice_pitch_semitones", 0.0) or 0.0),
            mode13_voice_ai_cleanup=float(getattr(req, "mode13_voice_ai_cleanup", 0.0) or 0.0),
            mode13_voice_noise_suppression=float(
                getattr(req, "mode13_voice_noise_suppression", 50.0) or 50.0
            ),
            mode13_voice_level_normalize=float(
                getattr(req, "mode13_voice_level_normalize", 50.0) or 50.0
            ),
            mode13_voice_highpass_hz=getattr(req, "mode13_voice_highpass_hz", None),
            mode13_voice_deesser=float(getattr(req, "mode13_voice_deesser", 0.0) or 0.0),
            mode13_voice_clarity=float(getattr(req, "mode13_voice_clarity", 0.0) or 0.0),
            mode13_voice_mud_cut=float(getattr(req, "mode13_voice_mud_cut", 0.0) or 0.0),
            mode13_voice_compression=float(getattr(req, "mode13_voice_compression", 0.0) or 0.0),
            control=control,
        )

        if control.get("cancelled"):
            return
        session["status"] = "done"
        session["result"] = {
            "video_path": result.get("video_path"),
            "video_paths": result.get("video_paths"),
            "topic": result.get("topic"),
            "quote_caption": result.get("quote_caption"),
            "quote_caption_ru": result.get("quote_caption_ru"),
            "quote_caption_en": result.get("quote_caption_en"),
            "trend": result.get("trend"),
            "session_id": session_id,
            "publishing": result.get("publishing"),
            "mode4_multiclip_ready": result.get("mode4_multiclip_ready"),
            "mode4_clip_filenames": result.get("mode4_clip_filenames"),
            "mode4_show_subtitles": result.get("mode4_show_subtitles"),
            "mode4_segments": result.get("mode4_segments"),
            "mode5_review_ready": result.get("mode5_review_ready"),
            "mode5_clip_filenames": result.get("mode5_clip_filenames"),
            "mode5_chunks_meta": result.get("mode5_chunks_meta"),
            "mode5_sub_mode": result.get("mode5_sub_mode"),
            "mode5_can_resume": result.get("mode5_can_resume"),
            "mode5_checkpoint_stage": result.get("mode5_checkpoint_stage"),
            "mode5_resume_reason": result.get("mode5_resume_reason"),
            "mode13_review_ready": result.get("mode13_review_ready"),
            "mode13_clip_filenames": result.get("mode13_clip_filenames"),
            "mode13_show_subtitles": result.get("mode13_show_subtitles"),
            "mode13_chunks_meta": result.get("mode13_chunks_meta"),
        }
        await queue.put({"type": "done", **session["result"]})
        try:
            from agents.topics_history import upsert_start_request_for_session

            req_snap = session.get("request")
            if req_snap:
                upsert_start_request_for_session(
                    session_id, session.get("topic") or "", req_snap
                )
        except Exception as ex:
            logger.warning(f"[TopicsHistory] upsert_start_request failed: {ex}")

    except asyncio.CancelledError:
        logger.info(f"Pipeline task cancelled for session {session_id}")
        session["status"] = "cancelled"
        control["cancelled"] = True
        try:
            await queue.put({"type": "error", "error": "Генерация отменена"})
        except Exception:
            # Queue might be closed during shutdown
            pass
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"Pipeline error: {exc}\n{tb}")
        session["status"] = "error"
        session["error"] = str(exc)
        try:
            await queue.put({"type": "error", "error": str(exc)})
        except Exception:
            # Queue might be closed during shutdown
            pass
        try:
            from agents.topics_history import upsert_start_request_for_session

            req_snap = session.get("request")
            if req_snap:
                upsert_start_request_for_session(
                    session_id, session.get("topic") or "", req_snap
                )
        except Exception as ex:
            logger.warning(f"[TopicsHistory] upsert_start_request on error failed: {ex}")
    finally:
        if sink_id is not None:
            logger.remove(sink_id)


def _drain_async_queue(q: asyncio.Queue) -> None:
    while True:
        try:
            q.get_nowait()
        except asyncio.QueueEmpty:
            return


async def _run_mode5_resume_task(session_id: str, queue: asyncio.Queue, control: dict) -> None:
    """Фоновое продолжение facts50 после ошибки; пишет в ту же очередь, что и основной пайплайн (SSE)."""
    session = _sessions[session_id]
    sink_id: int | None = None
    try:
        loop = asyncio.get_event_loop()
        sink = _SessionSink(queue, loop)
        sink_id = logger.add(sink, format="{message}", level="DEBUG", enqueue=False)
        settings.ensure_dirs()

        from agents.topics_history import get_start_request_for_session
        from modes.mode5.pipeline import resume_mode5_pipeline

        req_hist = get_start_request_for_session(session_id)
        skip_fa = True
        if isinstance(req_hist, dict):
            skip_fa = bool(req_hist.get("mode5_skip_final_assembly", True))

        result = await resume_mode5_pipeline(
            session_id,
            skip_final_assembly=skip_fa,
            control=control,
        )
        if control.get("cancelled"):
            return
        session["status"] = "done"
        session["result"] = {
            "video_path": result.get("video_path"),
            "video_paths": result.get("video_paths"),
            "topic": result.get("topic"),
            "quote_caption": result.get("quote_caption"),
            "quote_caption_ru": result.get("quote_caption_ru"),
            "quote_caption_en": result.get("quote_caption_en"),
            "trend": result.get("trend"),
            "session_id": session_id,
            "publishing": result.get("publishing"),
            "mode5_review_ready": result.get("mode5_review_ready"),
            "mode5_clip_filenames": result.get("mode5_clip_filenames"),
            "mode5_chunks_meta": result.get("mode5_chunks_meta"),
            "mode5_sub_mode": result.get("mode5_sub_mode"),
            "mode5_can_resume": result.get("mode5_can_resume"),
            "mode5_checkpoint_stage": result.get("mode5_checkpoint_stage"),
            "mode5_resume_reason": result.get("mode5_resume_reason"),
        }
        await queue.put({"type": "done", **session["result"]})
        try:
            from agents.topics_history import upsert_start_request_for_session

            req_snap = session.get("request")
            if req_snap:
                upsert_start_request_for_session(session_id, session.get("topic") or "", req_snap)
        except Exception as ex:
            logger.warning(f"[TopicsHistory] upsert_start_request (mode5 resume) failed: {ex}")
    except asyncio.CancelledError:
        logger.info(f"Mode5 resume task cancelled for session {session_id}")
        session["status"] = "cancelled"
        control["cancelled"] = True
        try:
            await queue.put({"type": "error", "error": "Генерация отменена"})
        except Exception:
            pass
    except Exception as exc:
        import traceback

        tb = traceback.format_exc()
        logger.error(f"Mode5 resume error: {exc}\n{tb}")
        session["status"] = "error"
        session["error"] = str(exc)
        try:
            await queue.put({"type": "error", "error": str(exc)})
        except Exception:
            pass
    finally:
        if sink_id is not None:
            logger.remove(sink_id)


# ── FastAPI app ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Graceful startup and shutdown handler."""
    # Startup
    logger.info("[Server] Starting up...")
    # До первого пайплайна pydub может импортироваться из других модулей — убрать предупреждение про ffmpeg в PATH
    from utils.ffmpeg_resolve import configure_pydub_ffmpeg

    if configure_pydub_ffmpeg():
        logger.debug("[Server] pydub: ffmpeg/ffprobe пути заданы (PATH / FFMPEG_PATH / imageio-ffmpeg)")
    # Background worker: server-side queue processing
    from utils.queue_manager import get_queue_manager
    from utils.rate_limiter import get_rate_limiter

    queue_mgr = get_queue_manager()
    limiter = get_rate_limiter()

    queue_kick = asyncio.Event()
    app.state.queue_kick = queue_kick

    async def _try_start_from_queue() -> bool:
        # Hourly limit is the only gate: if quota remains, start next from queue
        # (may run several pipelines in parallel when limit > 1).
        allowed, _reason = limiter.check_allowed()
        if not allowed:
            return False

        item = queue_mgr.pop_next()
        if not item:
            return False

        try:
            req = StartRequest.model_validate(item.payload)
            _normalize_mode_specific_request(req)
            _validate_start_request(req)
            session_id = str(int(time.time() * 1000))
            q: asyncio.Queue = asyncio.Queue()
            pause_event = asyncio.Event()
            pause_event.set()
            control = {
                "pause_event": pause_event,
                "cancelled": False,
                "fastgen_cancel_event": threading.Event(),
            }

            _sessions[session_id] = {
                "status": "running",
                "queue": q,
                "result": None,
                "error": None,
                "started_at": time.time(),
                "control": control,
                "topic": _session_topic_from_request(req),
                "mode": req.mode,
                "request": req.model_dump(),
            }

            async def _wrapped():
                try:
                    await _run_pipeline_task(session_id, req, q, control)
                finally:
                    # whenever a session ends, try to start next
                    queue_kick.set()

            _sessions[session_id]["task"] = asyncio.create_task(_wrapped())
            limiter.increment_usage()
            logger.info(f"[QueueWorker] Started from queue: session={session_id} mode={req.mode}")
            return True
        except Exception as e:
            permanent = isinstance(e, HTTPException) and int(getattr(e, "status_code", 0)) == 400
            queue_mgr.push_front(item, status="error" if permanent else "queued", last_error=str(e))
            logger.warning(f"[QueueWorker] Failed to start queued item (re-queued): {e}")
            return False

    async def _queue_worker():
        logger.info(f"[QueueWorker] Enabled. Queue file: {queue_mgr.path}")
        while True:
            try:
                # Wake up on: completion, periodic tick, or around hour boundary
                try:
                    await asyncio.wait_for(queue_kick.wait(), timeout=10)
                except asyncio.TimeoutError:
                    pass
                queue_kick.clear()

                # Try start as many as possible, but respecting concurrency+limit
                started_any = False
                for _ in range(5):
                    started = await _try_start_from_queue()
                    if not started:
                        break
                    started_any = True
                    await asyncio.sleep(0.5)

                if started_any:
                    continue
            except asyncio.CancelledError:
                raise
            except Exception as ex:
                logger.warning(f"[QueueWorker] Loop error: {ex}")
                await asyncio.sleep(2)

    worker_task = asyncio.create_task(_queue_worker())
    yield
    # Shutdown
    logger.info("[Server] Shutting down gracefully...")
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    except Exception:
        pass
    # Give running pipelines time to cleanup (FastGen browser etc.)
    await asyncio.sleep(0.5)
    logger.info("[Server] Shutdown complete")

app = FastAPI(title="Content Factory API", version="1.0", lifespan=lifespan)

# Периодический опрос с фронта — не засоряют INFO (оставьте LOGURU_LEVEL=DEBUG при отладке).
_API_LOG_DEBUG_PATHS = frozenset({
    "/api/rate-limit/status",
    "/api/queue/status",
    "/api/pipeline/sessions",
})


@app.middleware("http")
async def _log_requests(request, call_next):
    """Логирование API: каждый запрос + ошибки."""
    t0 = time.perf_counter()
    path = request.url.path
    method = request.method
    origin = request.headers.get("origin", "none")
    try:
        response = await call_next(request)
        elapsed = (time.perf_counter() - t0) * 1000
        status = response.status_code
        if path.startswith("/api/"):
            if status >= 400:
                logger.warning(f"[API] {method} {path} → {status} ({elapsed:.0f}ms)")
            elif path in _API_LOG_DEBUG_PATHS:
                logger.debug(f"[API] {method} {path} → {status} ({elapsed:.0f}ms)")
            else:
                logger.info(f"[API] {method} {path} → {status} ({elapsed:.0f}ms)")
        return response
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        logger.error(f"[API] {method} {path} FAILED {elapsed:.0f}ms: {e}")
        raise


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_casino_routes(app)


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class ScenarioRequest(BaseModel):
    topic: str
    num_scenes: int = 5
    trend_context: dict | None = None
    mode: int = 1
    language: str = "ru"


class KeyframeVideoRequest(BaseModel):
    """Request for generating video from start and end keyframes."""
    prompt: str
    start_frame_path: str  # Path to start frame image
    end_frame_path: str    # Path to end frame image
    output_dir: str | None = None  # Optional custom output directory


class LibraryRegenerateBody(BaseModel):
    """Тело POST /api/videos/{sid}/regenerate: для Mode 4 — какой файл пересоздать."""
    filename: str | None = None


class YouTubeUploadBody(BaseModel):
    """Публикация на YouTube Shorts: библиотека (История) или соц-ролик «Казино» — один эндпоинт."""

    session_id: str | None = None
    filename: str | None = None
    lang: str | None = None
    privacy_status: str = "public"
    # primary = YOUTUBE_OAUTH_TOKEN, secondary = YOUTUBE_OAUTH_TOKEN_B (другой канал / тот же Gmail)
    channel_profile: str = "primary"
    # --- Казино (TikTok-канал): те же OAuth-токены, что у библиотеки ---
    social_channel_id: str | None = None
    social_video_key: str | None = None
    branding_corner: str | None = "tr"
    title: str | None = None
    description: str | None = None
    keywords: str | None = None
    tags: str | None = None
    category_id: str | None = None

    @model_validator(mode="after")
    def _library_or_social(self) -> "YouTubeUploadBody":
        sid = (self.session_id or "").strip()
        sc = (self.social_channel_id or "").strip()
        sk = (self.social_video_key or "").strip()
        if sc or sk:
            if not sc or not sk:
                raise ValueError("Для соц-ролика укажи и social_channel_id, и social_video_key")
            return self
        if not sid:
            raise ValueError("Укажи session_id (библиотека) или пару social_channel_id + social_video_key (Казино)")
        return self

    @field_validator("privacy_status")
    @classmethod
    def _privacy(cls, v: str) -> str:
        allowed = frozenset({"private", "unlisted", "public"})
        if v not in allowed:
            raise ValueError("privacy_status: private | unlisted | public")
        return v

    @field_validator("channel_profile")
    @classmethod
    def _chprof(cls, v: str) -> str:
        from agents.publisher.youtube_multi import try_load_youtube_profiles

        x = (v or "primary").strip().lower()
        profs = try_load_youtube_profiles(settings)
        if profs is None:
            if x not in ("primary", "secondary"):
                raise ValueError("channel_profile: primary | secondary")
            return x
        allowed = {p.normalized_id() for p in profs}
        if x not in allowed:
            raise ValueError(
                f"channel_profile: одно из {', '.join(sorted(allowed))}"
            )
        return x

    @field_validator("lang")
    @classmethod
    def _lang(cls, v: str | None) -> str | None:
        if v is None:
            return None
        x = v.strip().lower()
        if x not in ("ru", "en"):
            raise ValueError("lang: ru | en")
        return x


class StartRequest(BaseModel):
    topic: str | None = None
    auto_topic: bool = False
    num_scenes: int = 5
    use_scenario: bool = True
    local_only: bool = True
    show_subtitles: bool = True
    show_watermark: bool = False  # водяной знак отключён
    scenario: dict | None = None
    mode: int = 1
    language: str = "ru"
    custom_title_bg_path: str | None = None
    custom_outro_bg_path: str | None = None
    reference_image_path: str | None = None  # image-to-video: passed to fast-gen for scene generation
    # Mode 3: восстановление старых домов
    mode3_start_image_path: str | None = None  # дом ДО реставрации (если загружает пользователь)
    mode3_end_image_path: str | None = None   # дом ПОСЛЕ (целевой вид)
    mode3_topic: str | None = None            # или текстовое описание — AI сгенерирует оба изображения
    # Mode 4: цитата + фото личности
    mode4_quote: str | None = None
    mode4_person_name: str | None = None
    mode4_photo_path: str | None = None
    # Mode 4: null = RU+EN; "ru" | "en" = один ролик
    mode4_only_lang: str | None = None
    mode4_show_author_on_video: bool = True
    mode4_video_header_title: str | None = None
    # "karaoke" | "plain_whisper" (несколько фрагментов: белый текст по Whisper, синхрон с речью)
    mode4_subtitle_style: str = "karaoke"
    mode4_multiclip: bool = False
    mode4_segments: list[str] | None = None
    mode4_skip_final_assembly: bool = True
    # Mode 5: ручной long-form текст -> ElevenLabs -> review before final assembly
    mode5_script_text: str | None = None
    mode5_language: str | None = None
    mode5_chunk_seconds: int = 300
    mode5_segment_seconds: int = 15
    mode5_skip_final_assembly: bool = True
    mode5_max_parallel_images: int = 10
    mode5_video_header_title: str | None = None
    mode5_bible_mode: bool = False
    # manual | bible | facts50 | outline | book_night | unwritten_chapter (legacy: mode5_bible_mode)
    mode5_sub_mode: str = "manual"
    # Mode 6: viral cartoon drama
    mode6_num_characters: int = 3
    # Mode 7: ASMR animal keyboard videos
    mode7_keyboards: list[str] | None = None
    mode7_animal_type: str | None = None
    # Mode 8: House Building Timelapse
    mode8_house_style: str | None = None  # "modern", "contemporary", "minimalist", "scandinavian", "cottage", "villa", "farmhouse", "colonial", "victorian", "mediterranean", "cabin", "log_house", "chalet", "adobe", "mansion", "estate"
    mode8_location: str | None = None  # "suburbs", "urban_edge", "planned_community", "forest", "wooded_area", "seaside", "lakefront", "riverside", "countryside", "farmland", "vineyard", "mountains", "hillside", "valley", "desert", "oasis", "tropical", "island"
    mode8_num_stages: int = 5
    mode8_num_floors: int = 2
    # Mode 9: Vehicle Assembly Timelapse
    mode9_vehicle_type: str | None = None  # "airplane_passenger", "airplane_private", "car_modern", "car_sport", "truck_cargo", "tractor", "excavator", "ship_cargo", "yacht", "helicopter", "drone", and 21 more...
    mode9_location: str | None = None  # "construction_site", "factory", "shipyard", "hangar", "empty_field", "forest_clearing", "desert", "mountain_valley", "city_outskirts", "port", and 9 more...
    mode9_num_stages: int = 5
    # Mode 10: уборка пляжа (таймлапс, как mode 8)
    mode10_beach_type: str | None = None
    mode10_coast_setting: str | None = None
    mode10_num_stages: int = 5
    # Mode 11: популярные сооружения (деконструкция)
    mode11_structure_type: str | None = None
    # None = взять num_scenes (очередь / старые клиенты); иначе явно 5 или 7 после нормализации
    mode11_num_stages: int | None = None
    # Mode 13: загрузка аудио → смена тембра → картинки по 30 с → превью по 5 мин
    mode13_audio_path: str | None = None
    mode13_voice_preset: str = "studio"
    mode13_language: str | None = None
    mode13_show_subtitles: bool = True
    mode13_skip_final_assembly: bool = True
    mode13_chunk_seconds: int = 300
    mode13_segment_seconds: int = 30
    mode13_video_header_title: str | None = None
    # Ручная настройка звука (mode 13): то же, что ползунки на форме
    mode13_voice_gain_db: float = 0.0
    mode13_voice_tempo_scale: float = 1.0
    mode13_voice_pitch_semitones: float = 0.0
    mode13_voice_ai_cleanup: float = 0.0
    mode13_voice_noise_suppression: float = 50.0
    mode13_voice_level_normalize: float = 50.0
    mode13_voice_highpass_hz: int | None = None
    mode13_voice_deesser: float = 0.0
    mode13_voice_clarity: float = 0.0
    mode13_voice_mud_cut: float = 0.0
    mode13_voice_compression: float = 0.0

    @field_validator("mode4_only_lang", mode="before")
    @classmethod
    def _normalize_mode4_only_lang(cls, v):  # noqa: ANN001
        if v is None or v == "":
            return None
        if isinstance(v, str) and v.lower() in ("ru", "en"):
            return v.lower()
        raise ValueError("mode4_only_lang must be 'ru', 'en', or null")

    @field_validator("mode4_subtitle_style", mode="before")
    @classmethod
    def _normalize_mode4_subtitle_style(cls, v):  # noqa: ANN001
        if v is None or v == "":
            return "karaoke"
        s = str(v).strip().lower()
        if s in ("karaoke", "plain_whisper", "plain"):
            return "plain_whisper" if s in ("plain_whisper", "plain") else "karaoke"
        raise ValueError("mode4_subtitle_style must be 'karaoke' or 'plain_whisper'")

    @field_validator("mode5_sub_mode", mode="before")
    @classmethod
    def _normalize_mode5_sub_mode(cls, v):  # noqa: ANN001
        if v is None or (isinstance(v, str) and not str(v).strip()):
            return "manual"
        s = str(v).strip().lower()
        if s in ("manual", "bible", "facts50", "outline", "book_night", "unwritten_chapter"):
            return s
        return "manual"


class RegenerateClipIndexBody(BaseModel):
    index: int


class AssembleClipsBody(BaseModel):
    show_subtitles: bool | None = None


class Mode13RegenerateSegmentBody(BaseModel):
    chunk_index: int
    segment_index: int


class Mode5RegenerateImageBody(BaseModel):
    chunk_index: int
    segment_index: int


class Mode5RegenerateChunkBody(BaseModel):
    chunk_index: int
    text: str


class Mode5TopicIdeasBody(BaseModel):
    sub_mode: str = "book_night"
    limit: int = 8
    seed: str | None = None

    @field_validator("sub_mode", mode="before")
    @classmethod
    def _normalize_sub_mode(cls, v):  # noqa: ANN001
        s = str(v or "").strip().lower()
        if s in ("book_night", "unwritten_chapter"):
            return s
        raise ValueError("sub_mode must be book_night or unwritten_chapter")

    @field_validator("limit", mode="before")
    @classmethod
    def _normalize_limit(cls, v):  # noqa: ANN001
        try:
            n = int(v)
        except Exception:
            n = 8
        return max(1, min(12, n))


class Mode13VoicePreviewBody(BaseModel):
    """Предпрослушивание обработки голоса (первые ~45 с). path — файл из /api/upload/audio."""

    path: str
    preset: str = "studio"
    gain_db: float = 0.0
    tempo_scale: float = 1.0
    pitch_semitones: float = 0.0
    ai_cleanup: float = 0.0
    noise_suppression: float = 50.0
    level_normalize: float = 50.0
    highpass_hz: int | None = None
    deesser: float = 0.0
    clarity: float = 0.0
    mud_cut: float = 0.0
    compression: float = 0.0
    max_seconds: float = 45.0


class Mode5IdeaStatusBody(BaseModel):
    idea_id: str
    status: str = "clicked"

    @field_validator("idea_id", mode="before")
    @classmethod
    def _normalize_idea_id(cls, v):  # noqa: ANN001
        s = str(v or "").strip()
        if not s:
            raise ValueError("idea_id is required")
        return s

    @field_validator("status", mode="before")
    @classmethod
    def _normalize_status(cls, v):  # noqa: ANN001
        s = str(v or "").strip().lower()
        if s in ("suggested", "clicked", "started", "completed", "failed", "archived"):
            return s
        raise ValueError("status must be suggested, clicked, started, completed, failed, or archived")


def _safe_uploads_audio_path(path_str: str) -> Path | None:
    """Только файлы внутри settings.uploads_dir (защита от path traversal)."""
    if not path_str or not isinstance(path_str, str):
        return None
    try:
        p = Path(path_str).expanduser().resolve()
        root = Path(settings.uploads_dir).resolve()
        p.relative_to(root)
    except ValueError:
        return None
    if not p.is_file():
        return None
    return p


def _effective_mode5_sub_mode(req: StartRequest) -> str:
    raw = (getattr(req, "mode5_sub_mode", None) or "manual")
    if not isinstance(raw, str):
        return "manual"
    s = raw.strip().lower()
    if s not in ("manual", "bible", "facts50", "outline", "book_night", "unwritten_chapter"):
        s = "manual"
    if s == "manual" and getattr(req, "mode5_bible_mode", False):
        return "bible"
    return s


def _validate_start_request(req: StartRequest) -> None:
    """Проверки перед запуском пайплайна (общие для /pipeline/start и перегенерации)."""
    if req.mode == 12:
        raise HTTPException(
            400,
            "Режим 12 отключён. Несколько фрагментов — в режиме 4 «Цитата + фото»: "
            "несколько абзацев в поле цитаты через пустую строку, один язык (RU или EN).",
        )
    if req.mode == 3:
        has_images = bool(req.mode3_start_image_path and req.mode3_end_image_path)
        has_topic = bool(req.mode3_topic and str(req.mode3_topic).strip())
        if not has_images and not has_topic:
            raise HTTPException(
                400,
                "Mode 3: загрузите 2 фото (дом ДО и ПОСЛЕ) или опишите дом текстом для автогенерации",
            )
    elif req.mode == 4:
        if not getattr(req, "mode4_quote", "") or not getattr(req, "mode4_photo_path", ""):
            raise HTTPException(
                400,
                "Mode 4: введите цитату и загрузите фото",
            )
        if getattr(req, "mode4_multiclip", False):
            ol4 = (getattr(req, "mode4_only_lang", None) or "").strip().lower()
            if ol4 not in ("ru", "en"):
                raise HTTPException(
                    400,
                    "Несколько фрагментов: выберите «Только русская» или «Только английская» (не «оба сразу»).",
                )
            raw_mc = [str(s).strip() for s in (getattr(req, "mode4_segments", None) or []) if str(s).strip()]
            if len(raw_mc) == 1:
                raise HTTPException(
                    400,
                    "Задайте минимум 2 блока текста (пустая строка между блоками) или оставьте ручные фрагменты пустыми для авторазбиения.",
                )
    elif req.mode == 13:
        ap = (getattr(req, "mode13_audio_path", None) or "").strip()
        if not ap:
            raise HTTPException(400, "Mode 13: загрузите аудиофайл")
        if not Path(ap).is_file():
            raise HTTPException(400, "Mode 13: файл аудио не найден на сервере")
    elif req.mode == 5:
        sub5 = _effective_mode5_sub_mode(req)
        txt = (getattr(req, "mode5_script_text", None) or "").strip()
        if sub5 == "outline":
            from modes.mode5.outline_generator import MIN_OUTLINE_BRIEF_CHARS

            if len(txt) < MIN_OUTLINE_BRIEF_CHARS:
                raise HTTPException(
                    400,
                    f"Mode 5: для «плана из описания» введите краткое описание сюжета (от {MIN_OUTLINE_BRIEF_CHARS} символов).",
                )
        elif sub5 == "book_night" and len(txt) < 8:
            raise HTTPException(
                400,
                "Mode 5: для «книга на ночь» введите название книги (от 8 символов).",
            )
        elif sub5 == "facts50" and len(txt) < 8:
            raise HTTPException(
                400,
                "Mode 5: для «77 фактов» введите тему или заголовок (от 8 символов).",
            )
        elif sub5 == "unwritten_chapter" and len(txt) < 8:
            raise HTTPException(
                400,
                "Mode 5: для «The Unwritten Chapter» укажите тему расследования (от 8 символов).",
            )
        elif sub5 not in ("facts50", "outline", "book_night", "unwritten_chapter") and len(txt) < 80:
            raise HTTPException(400, "Mode 5: вставьте полноценный текст для озвучки")
        lang5 = (getattr(req, "mode5_language", None) or getattr(req, "language", "auto") or "auto").strip().lower()
        if lang5 not in ("ru", "en", "auto", ""):
            raise HTTPException(400, "Mode 5: язык должен быть auto, ru или en")
    elif req.mode in (6, 7, 8, 9, 10, 11):
        pass
    elif req.mode != 13 and not req.topic and not req.auto_topic:
        raise HTTPException(400, "Provide 'topic' or set 'auto_topic: true'")


def _normalize_mode_specific_request(req: StartRequest) -> None:
    """Force mode-specific invariants that must not depend on UI payload."""
    if req.mode == 11:
        raw = req.mode11_num_stages
        if raw is None:
            raw = req.num_scenes
        try:
            n = int(raw)
        except (TypeError, ValueError):
            n = 5
        req.mode11_num_stages = 7 if n >= 7 else 5
        req.num_scenes = req.mode11_num_stages
        req.show_subtitles = False
    if req.mode == 5:
        from modes.mode5.pipeline import detect_mode5_language

        req.show_subtitles = False
        req.use_scenario = False
        req.auto_topic = False
        req.num_scenes = 1
        sub5 = _effective_mode5_sub_mode(req)
        req.mode5_sub_mode = sub5
        req.mode5_bible_mode = sub5 == "bible"
        script_text = (req.mode5_script_text or "").strip()
        hdr = (req.mode5_video_header_title or "").strip()
        preferred_lang = (req.mode5_language or req.language or "auto").strip().lower() or "auto"
        lang_blob = f"{script_text} {hdr}".strip() if sub5 in ("facts50", "outline", "book_night", "unwritten_chapter") else script_text
        req.language = detect_mode5_language(lang_blob, preferred_lang)
        req.mode5_language = req.language
        req.topic = (
            hdr
            or script_text
            or (
                "50 фактов"
                if sub5 == "facts50"
                else "Лонгрид по описанию"
                if sub5 == "outline"
                else "Книга на ночь"
                if sub5 == "book_night"
                else "The Unwritten Chapter"
                if sub5 == "unwritten_chapter"
                else "Ручной long-form"
            )
        ).strip() or (
            "50 фактов"
            if sub5 == "facts50"
            else "Лонгрид по описанию"
            if sub5 == "outline"
            else "Книга на ночь"
            if sub5 == "book_night"
            else "The Unwritten Chapter"
            if sub5 == "unwritten_chapter"
            else "Ручной long-form"
        )


def _ensure_regenerate_assets_exist(req: StartRequest) -> None:
    """Файлы из сохранённого запроса должны существовать на диске."""
    if req.mode == 4 and req.mode4_photo_path and not Path(req.mode4_photo_path).is_file():
        raise HTTPException(
            400,
            "Файл фото для цитаты не найден. Создайте видео заново с главной страницы.",
        )
    if req.mode == 5:
        pass
    if req.mode == 3:
        if req.mode3_start_image_path and not Path(req.mode3_start_image_path).is_file():
            raise HTTPException(400, "Фото «дом ДО» не найдено — перегенерация невозможна.")
        if req.mode3_end_image_path and not Path(req.mode3_end_image_path).is_file():
            raise HTTPException(400, "Фото «дом ПОСЛЕ» не найдено — перегенерация невозможна.")
    if req.mode == 13:
        ap = (getattr(req, "mode13_audio_path", None) or "").strip()
        if ap and not Path(ap).is_file():
            raise HTTPException(400, "Аудиофайл режима 13 не найден. Загрузите снова или создайте видео заново.")
    if req.reference_image_path and not Path(req.reference_image_path).is_file():
        raise HTTPException(400, "Референсное изображение не найдено на сервере.")
    if req.custom_title_bg_path and not Path(req.custom_title_bg_path).is_file():
        raise HTTPException(400, "Файл фона титра не найден.")
    if req.custom_outro_bg_path and not Path(req.custom_outro_bg_path).is_file():
        raise HTTPException(400, "Файл фона аутро не найден.")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/api/upload/image")
async def upload_image(file: UploadFile = File(...)):
    """Upload image for title/outro card. Returns server path to use in pipeline."""
    ALLOWED = {"image/jpeg", "image/png", "image/webp", "image/jpg"}
    if file.content_type and file.content_type.lower() not in ALLOWED:
        raise HTTPException(400, f"Allowed: JPEG, PNG, WebP. Got: {file.content_type}")
    settings.ensure_dirs()
    suffix = Path(file.filename or "image").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    name = f"{int(time.time() * 1000)}_{id(file) % 10000}{suffix}"
    path = settings.uploads_dir / name
    try:
        content = await file.read()
        if len(content) > 20 * 1024 * 1024:
            raise HTTPException(400, "File too large (max 20 MB)")
        path.write_bytes(content)
        return {"path": str(path.resolve())}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/upload/audio")
async def upload_audio(file: UploadFile = File(...)):
    """Загрузка аудио для mode 13: сразу конвертация в моно 48 kHz WAV (как в пайплайне)."""
    from modes.mode13.voice_transform import convert_upload_to_mono_wav48

    allowed_suffix = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".webm", ".flac", ".opus"}
    settings.ensure_dirs()
    suffix = Path(file.filename or "audio").suffix.lower()
    if suffix not in allowed_suffix:
        suffix = ".mp3"
    ts = int(time.time() * 1000)
    uid = id(file) % 10000
    raw_path = settings.uploads_dir / f"{ts}_{uid}_raw{suffix}"
    mono_path = settings.uploads_dir / f"{ts}_{uid}_mono48.wav"
    try:
        content = await file.read()
        if len(content) > 200 * 1024 * 1024:
            raise HTTPException(400, "File too large (max 200 MB)")
        raw_path.write_bytes(content)
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,
                functools.partial(convert_upload_to_mono_wav48, raw_path, mono_path),
            )
        except Exception as ex:
            raw_path.unlink(missing_ok=True)
            mono_path.unlink(missing_ok=True)
            raise HTTPException(
                500,
                f"Не удалось конвертировать аудио в моно WAV (нужен ffmpeg). {ex}",
            ) from ex
        raw_path.unlink(missing_ok=True)
        return {"path": str(mono_path.resolve()), "mono": True}
    except HTTPException:
        raise
    except Exception as e:
        raw_path.unlink(missing_ok=True)
        mono_path.unlink(missing_ok=True)
        raise HTTPException(500, str(e)) from e


@app.get("/api/upload/audio-serve")
async def serve_upload_audio(path: str = Query(..., description="Абсолютный путь из ответа upload/audio")):
    """Раздача загруженного WAV для <audio src> в UI."""
    p = _safe_uploads_audio_path(path)
    if not p:
        raise HTTPException(404, "Файл не найден или недоступен")
    return FileResponse(str(p), media_type="audio/wav", filename=p.name)


@app.post("/api/mode13/voice-preview")
async def mode13_voice_preview(body: Mode13VoicePreviewBody):
    """Короткий WAV с теми же фильтрами, что при генерации — для предпрослушивания."""
    from modes.mode13.voice_transform import render_voice_preview_wav

    inp = _safe_uploads_audio_path(body.path.strip())
    if not inp:
        raise HTTPException(400, "Некорректный или отсутствующий путь к аудио")

    gain_db = max(-24.0, min(24.0, float(body.gain_db)))
    tempo_scale = max(0.75, min(1.25, float(body.tempo_scale)))
    pitch_semitones = max(-8.0, min(8.0, float(body.pitch_semitones)))
    max_sec = max(10.0, min(90.0, float(body.max_seconds)))
    ai_cleanup = max(0.0, min(100.0, float(body.ai_cleanup)))
    noise_sup = max(0.0, min(100.0, float(body.noise_suppression)))
    level_n = max(0.0, min(100.0, float(body.level_normalize)))
    deesser = max(0.0, min(100.0, float(body.deesser)))
    clarity = max(0.0, min(100.0, float(body.clarity)))
    mud_cut = max(0.0, min(100.0, float(body.mud_cut)))
    compression = max(0.0, min(100.0, float(body.compression)))
    hp = body.highpass_hz
    hp_use = int(hp) if hp is not None and 40 <= int(hp) <= 200 else None

    vp = (body.preset or "studio").strip().lower()
    if vp not in ("original", "studio", "calm", "natural", "soft", "medium", "strong"):
        vp = "studio"

    loop = asyncio.get_event_loop()
    fd, tmp_name = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    out_p = Path(tmp_name)
    try:

        def _run() -> None:
            render_voice_preview_wav(
                inp,
                out_p,
                vp,
                gain_db=gain_db,
                tempo_scale=tempo_scale,
                pitch_semitones=pitch_semitones,
                ai_cleanup=ai_cleanup,
                noise_suppression=noise_sup,
                level_normalize=level_n,
                highpass_hz=hp_use,
                deesser=deesser,
                clarity=clarity,
                mud_cut=mud_cut,
                compression=compression,
                max_seconds=max_sec,
            )

        await loop.run_in_executor(None, _run)
        data = out_p.read_bytes()
        if len(data) < 64:
            raise HTTPException(500, "Пустой превью-файл")
        return Response(content=data, media_type="audio/wav")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Превью аудио: {e}") from e
    finally:
        out_p.unlink(missing_ok=True)


@app.post("/api/pipeline/start")
async def start_pipeline(req: StartRequest):
    _normalize_mode_specific_request(req)
    _validate_start_request(req)

    # Check rate limit before starting
    from utils.rate_limiter import get_rate_limiter
    limiter = get_rate_limiter()
    
    allowed, reason = limiter.check_allowed()
    if not allowed:
        status = limiter.get_status()
        return JSONResponse(
            status_code=429,
            content={
                "error": "rate_limit_reached",
                "message": reason,
                "rate_limit": status,
                "suggestion": "add_to_queue",
            },
        )

    session_id = str(int(time.time() * 1000))
    queue: asyncio.Queue = asyncio.Queue()
    pause_event = asyncio.Event()
    pause_event.set()  # running by default
    control = {
        "pause_event": pause_event,
        "cancelled": False,
        "fastgen_cancel_event": threading.Event(),
    }

    _sessions[session_id] = {
        "status": "running",
        "queue": queue,
        "result": None,
        "error": None,
        "started_at": time.time(),
        "control": control,
        "topic": _session_topic_from_request(req),
        "mode": req.mode,
        "request": req.model_dump(),  # для перезапуска с теми же параметрами
    }

    task = asyncio.create_task(_run_pipeline_task(session_id, req, queue, control))
    _sessions[session_id]["task"] = task
    
    # Increment rate limit counter after successful start
    limiter.increment_usage()
    
    return {"session_id": session_id}


# ── Queue API (server-side) ───────────────────────────────────────────────────

class QueueAddRequest(BaseModel):
    payload: dict


@app.post("/api/queue/add")
async def queue_add(body: QueueAddRequest):
    from utils.queue_manager import get_queue_manager

    mgr = get_queue_manager()
    item = mgr.add(body.payload or {})
    queue_kick = getattr(app.state, "queue_kick", None)
    if queue_kick is not None:
        queue_kick.set()
    return {"queued": True, "item": item.__dict__, "queue_size": len(mgr.snapshot())}


@app.get("/api/queue/status")
async def queue_status():
    from utils.queue_manager import get_queue_manager

    mgr = get_queue_manager()
    return {"queue": mgr.snapshot(), "queue_size": len(mgr.snapshot())}


@app.delete("/api/queue/{item_id}")
async def queue_delete(item_id: str):
    from utils.queue_manager import get_queue_manager

    mgr = get_queue_manager()
    ok = mgr.remove(item_id)
    if not ok:
        raise HTTPException(404, "Queue item not found")
    return {"deleted": True, "item_id": item_id, "queue_size": len(mgr.snapshot())}


class QueueMoveRequest(BaseModel):
    direction: str


@app.post("/api/queue/{item_id}/move")
async def queue_move(item_id: str, body: QueueMoveRequest):
    from utils.queue_manager import get_queue_manager

    mgr = get_queue_manager()
    ok = mgr.move(item_id, (body.direction or "").strip().lower())
    if not ok:
        raise HTTPException(400, "Invalid move or item not found")
    return {"moved": True, "item_id": item_id, "queue_size": len(mgr.snapshot())}


@app.get("/api/pipeline/{session_id}/stream")
async def stream_logs(session_id: str):
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    async def event_gen():
        q: asyncio.Queue = session["queue"]
        # Replay buffered messages if any
        try:
            while True:
                try:
                    entry = await asyncio.wait_for(q.get(), timeout=20)
                    yield f"data: {json.dumps(entry)}\n\n"
                    if entry.get("type") in ("done", "error"):
                        return
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        except asyncio.CancelledError:
            # Клиент закрыл вкладку / оборвал SSE — не превращать в 500 для всего ASGI
            return

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/pipeline/{session_id}/status")
async def get_status(session_id: str):
    session = _sessions.get(session_id)
    if not session:
        # Fallback for persisted Mode 5 sessions (History -> Progress after server restart).
        try:
            from modes.mode5.pipeline import mode5_status_from_plan

            result = mode5_status_from_plan(session_id)
            return {
                "session_id": session_id,
                "status": "done",
                "result": result,
                "error": None,
                "topic": result.get("topic", ""),
                "mode": 5,
            }
        except Exception:
            raise HTTPException(404, "Session not found")
    result = session.get("result")
    if int(session.get("mode") or 0) == 5 and session.get("status") in ("error", "cancelled"):
        try:
            from modes.mode5.pipeline import load_mode5_plan, mode5_resume_snapshot_for_plan

            plan = load_mode5_plan(session_id)
            snap = mode5_resume_snapshot_for_plan(session_id, plan)
            merged: dict = dict(result) if isinstance(result, dict) else {}
            merged.setdefault("session_id", session_id)
            merged["mode5_can_resume"] = bool(snap.get("can_resume"))
            merged["mode5_checkpoint_stage"] = snap.get("stage")
            merged["mode5_resume_reason"] = snap.get("reason") or None
            if merged.get("mode5_sub_mode") is None:
                merged["mode5_sub_mode"] = plan.get("sub_mode")
            result = merged
        except Exception:
            pass
    return {
        "session_id": session_id,
        "status": session.get("status", "unknown"),
        "result": result,
        "error": session.get("error"),
        "topic": session.get("topic", ""),
        "mode": session.get("mode", 1),
    }


@app.get("/api/pipeline/{session_id}/start-request")
async def get_pipeline_start_request(session_id: str):
    """Снимок тела StartRequest для подстановки в форму «Создать видео» (активная сессия или история)."""
    session = _sessions.get(session_id)
    if session:
        snap = session.get("request")
        if isinstance(snap, dict) and snap:
            return {"request": snap}
    from agents.topics_history import get_start_request_for_session

    snap = get_start_request_for_session(session_id)
    if isinstance(snap, dict) and snap:
        return {"request": snap}
    raise HTTPException(404, "Параметры запуска для этой сессии не найдены")


@app.post("/api/mode4/{session_id}/regenerate-clip")
async def mode4_regenerate_clip_ep(session_id: str, body: RegenerateClipIndexBody):
    from modes.mode4.multiclip import regenerate_mode4_multiclip_clip

    try:
        return await regenerate_mode4_multiclip_clip(session_id, body.index)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except RuntimeError as e:
        raise HTTPException(500, str(e)) from e


@app.post("/api/mode4/{session_id}/assemble")
async def mode4_assemble_ep(session_id: str, body: AssembleClipsBody):
    from modes.mode4.multiclip import assemble_mode4_multiclip_final_sync

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            functools.partial(assemble_mode4_multiclip_final_sync, session_id, body.show_subtitles),
        )
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    sess = _sessions.get(session_id)
    if sess and isinstance(sess.get("result"), dict):
        r = sess["result"]
        r["video_path"] = result.get("video_path")
        r["video_paths"] = result.get("video_paths")
        r["topic"] = result.get("topic")
        r["quote_caption"] = result.get("quote_caption")
        r["quote_caption_ru"] = result.get("quote_caption_ru")
        r["quote_caption_en"] = result.get("quote_caption_en")
        r["mode4_multiclip_ready"] = False
        r.pop("mode4_clip_filenames", None)
        r.pop("mode4_show_subtitles", None)
        r.pop("mode4_segments", None)
    return result


@app.post("/api/mode13/{session_id}/regenerate-segment")
async def mode13_regenerate_segment_ep(session_id: str, body: Mode13RegenerateSegmentBody):
    from modes.mode13.pipeline import regenerate_mode13_segment

    try:
        return await regenerate_mode13_segment(session_id, body.chunk_index, body.segment_index)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/mode5/{session_id}/regenerate-image")
async def mode5_regenerate_image_ep(session_id: str, body: Mode5RegenerateImageBody):
    from modes.mode5.pipeline import regenerate_mode5_image

    try:
        return await regenerate_mode5_image(session_id, body.chunk_index, body.segment_index)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/mode5/{session_id}/regenerate-chunk")
async def mode5_regenerate_chunk_ep(session_id: str, body: Mode5RegenerateChunkBody):
    from modes.mode5.pipeline import regenerate_mode5_chunk

    try:
        result = await regenerate_mode5_chunk(session_id, body.chunk_index, body.text)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    sess = _sessions.get(session_id)
    if sess and isinstance(sess.get("result"), dict):
        r = sess["result"]
        if "chunk_meta" in result and isinstance(r.get("mode5_chunks_meta"), list):
            metas = list(r["mode5_chunks_meta"])
            idx = result.get("chunk_index")
            if isinstance(idx, int) and 0 <= idx < len(metas):
                metas[idx] = result["chunk_meta"]
                r["mode5_chunks_meta"] = metas
    return result


@app.post("/api/mode5/{session_id}/assemble")
async def mode5_assemble_ep(session_id: str):
    from modes.mode5.pipeline import assemble_mode5_final_sync

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            functools.partial(assemble_mode5_final_sync, session_id),
        )
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    sess = _sessions.get(session_id)
    if sess and isinstance(sess.get("result"), dict):
        r = sess["result"]
        r["video_path"] = result.get("video_path")
        r["video_paths"] = result.get("video_paths")
        r["topic"] = result.get("topic")
        r["quote_caption"] = result.get("quote_caption")
        r["quote_caption_ru"] = result.get("quote_caption_ru")
        r["quote_caption_en"] = result.get("quote_caption_en")
        r["mode5_review_ready"] = False
        r.pop("mode5_clip_filenames", None)
        r.pop("mode5_chunks_meta", None)
        if isinstance(result.get("mode5_sub_mode"), str):
            r["mode5_sub_mode"] = result["mode5_sub_mode"]
    return result


@app.get("/api/mode5/{session_id}/review-state")
async def mode5_review_state_ep(session_id: str):
    from modes.mode5.pipeline import mode5_review_snapshot

    try:
        return mode5_review_snapshot(session_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/mode5/{session_id}/continue-generation")
async def mode5_continue_generation_ep(session_id: str):
    """Продолжить mode5 с последнего сохранённого этапа (TTS/картинки/слайсы на диске)."""
    from modes.mode5.pipeline import load_mode5_plan, mode5_resume_snapshot

    snap = mode5_resume_snapshot(session_id)
    if not snap.get("can_resume"):
        raise HTTPException(
            400,
            detail=str(snap.get("reason") or "cannot_resume"),
        )

    existing = _sessions.get(session_id)
    if existing:
        t = existing.get("task")
        if existing.get("status") == "running" and t is not None and not t.done():
            raise HTTPException(409, "Для этой сессии уже идёт генерация")

    try:
        plan = load_mode5_plan(session_id)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e

    topic = (
        (plan.get("header_title") or plan.get("facts_topic") or "").strip()
        or f"Mode 5 ({session_id})"
    )

    from agents.topics_history import get_start_request_for_session

    req_hist = get_start_request_for_session(session_id)
    req_final = None
    if isinstance(existing, dict) and isinstance(existing.get("request"), dict):
        req_final = existing["request"]
    elif isinstance(req_hist, dict):
        req_final = req_hist
    if not isinstance(req_final, dict):
        req_final = {"mode": 5, "mode5_skip_final_assembly": True}

    if isinstance(existing, dict) and isinstance(existing.get("queue"), asyncio.Queue):
        queue = existing["queue"]
        _drain_async_queue(queue)
    else:
        queue = asyncio.Queue()

    pause_event = asyncio.Event()
    pause_event.set()
    control = {
        "pause_event": pause_event,
        "cancelled": False,
        "fastgen_cancel_event": threading.Event(),
    }

    _sessions[session_id] = {
        "status": "running",
        "queue": queue,
        "result": (existing or {}).get("result") if isinstance(existing, dict) else None,
        "error": None,
        "started_at": time.time(),
        "control": control,
        "topic": topic,
        "mode": 5,
        "request": req_final,
    }
    task = asyncio.create_task(_run_mode5_resume_task(session_id, queue, control))
    _sessions[session_id]["task"] = task
    return {"session_id": session_id, "continuing": True}


@app.post("/api/mode5/topic-ideas")
async def mode5_topic_ideas_ep(body: Mode5TopicIdeasBody):
    from agents.mode5_topic_ideas import suggest_mode5_topics

    try:
        ideas = await suggest_mode5_topics(body.sub_mode, body.limit, body.seed)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        logger.exception("[API /mode5/topic-ideas] failed")
        raise HTTPException(500, f"Mode 5 ideas failed: {e}") from e
    return {
        "sub_mode": body.sub_mode,
        "seed": body.seed,
        "ideas": ideas,
    }


@app.get("/api/mode5/topic-ideas")
async def mode5_topic_ideas_cached_ep(
    sub_mode: str = Query(...),
    limit: int = Query(8),
):
    from agents.mode5_topic_ideas import get_cached_mode5_topics

    try:
        ideas = get_cached_mode5_topics(sub_mode, limit)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {
        "sub_mode": sub_mode,
        "ideas": ideas,
    }


@app.post("/api/mode5/topic-ideas/consume")
async def mode5_topic_ideas_consume_ep(body: Mode5IdeaStatusBody):
    from agents.mode5_topic_ideas import update_mode5_idea_status

    try:
        ok = update_mode5_idea_status(body.idea_id, body.status)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if not ok:
        raise HTTPException(404, "idea_id not found")
    return {"idea_id": body.idea_id, "status": body.status, "updated": True}


@app.post("/api/mode13/{session_id}/assemble")
async def mode13_assemble_ep(session_id: str, body: AssembleClipsBody):
    from modes.mode13.pipeline import assemble_mode13_final_sync

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            functools.partial(assemble_mode13_final_sync, session_id, body.show_subtitles),
        )
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    sess = _sessions.get(session_id)
    if sess and isinstance(sess.get("result"), dict):
        r = sess["result"]
        r["video_path"] = result.get("video_path")
        r["video_paths"] = result.get("video_paths")
        r["topic"] = result.get("topic")
        r["quote_caption"] = result.get("quote_caption")
        r["quote_caption_ru"] = result.get("quote_caption_ru")
        r["quote_caption_en"] = result.get("quote_caption_en")
        r["mode13_review_ready"] = False
        r.pop("mode13_clip_filenames", None)
        r.pop("mode13_show_subtitles", None)
        r.pop("mode13_chunks_meta", None)
    return result


@app.get("/api/pipeline/sessions")
async def list_pipeline_sessions():
    """Список сессий для сайдбара: running/paused, проверка клипов, ошибка/отмена (чтобы не «пропадали»)."""
    active = []
    for sid, s in _sessions.items():
        st = s.get("status")
        result = s.get("result") if isinstance(s.get("result"), dict) else {}
        review_pending = bool(
            st == "done"
            and (
                result.get("mode4_multiclip_ready")
                or result.get("mode13_review_ready")
            )
        )
        terminal_visible = st in ("error", "cancelled")
        if st not in ("running", "paused") and not review_pending and not terminal_visible:
            continue
        active.append(
            {
                "session_id": sid,
                "status": st,
                "topic": s.get("topic", "") or f"#{sid[-8:]}",
                "mode": s.get("mode", 1),
                "started_at": s.get("started_at"),
                "review_pending": review_pending,
            }
        )
    logger.debug(f"[API /pipeline/sessions] returning {len(active)} active")
    return {"sessions": sorted(active, key=lambda x: x.get("started_at") or 0, reverse=True)}


@app.post("/api/pipeline/{session_id}/pause")
async def pause_pipeline(session_id: str):
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session["status"] != "running":
        raise HTTPException(400, f"Cannot pause: status is {session['status']}")
    control = session.get("control", {})
    pause_event = control.get("pause_event")
    if pause_event:
        pause_event.clear()
    session["status"] = "paused"
    return {"status": "paused", "session_id": session_id}


@app.post("/api/pipeline/{session_id}/resume")
async def resume_pipeline(session_id: str):
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session["status"] != "paused":
        raise HTTPException(400, f"Cannot resume: status is {session['status']}")
    control = session.get("control", {})
    pause_event = control.get("pause_event")
    if pause_event:
        pause_event.set()
    session["status"] = "running"
    return {"status": "running", "session_id": session_id}


@app.post("/api/pipeline/{session_id}/cancel")
async def cancel_pipeline(session_id: str):
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session["status"] in ("done", "error", "cancelled"):
        raise HTTPException(400, f"Pipeline already finished: {session['status']}")
    control = session.get("control", {})
    control["cancelled"] = True
    fce = control.get("fastgen_cancel_event")
    if isinstance(fce, threading.Event):
        fce.set()
    task = session.get("task")
    if task and not task.done():
        task.cancel()
    session["status"] = "cancelled"
    session["error"] = session.get("error") or "Генерация отменена"
    return {"status": "cancelled", "session_id": session_id}


@app.post("/api/pipeline/{session_id}/restart")
async def restart_pipeline(session_id: str):
    """Перезапуск генерации с теми же параметрами. Создаёт новую сессию и сбрасывает результат предыдущей."""
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    req_data = session.get("request")
    if not req_data:
        raise HTTPException(400, "Перезапуск недоступен: параметры этой сессии не сохранены (старая версия)")

    import shutil

    # Сбросить выходные файлы предыдущей сессии
    videos_dir = settings.videos_dir
    flat_path = videos_dir / f"video_{session_id}.mp4"
    if flat_path.exists():
        flat_path.unlink()
        logger.info(f"[Restart] Removed {flat_path}")
    session_dir = videos_dir / session_id
    if session_dir.exists():
        shutil.rmtree(session_dir)
        logger.info(f"[Restart] Removed session dir {session_dir}")

    # Новая сессия с теми же параметрами
    req = StartRequest(**req_data)
    _normalize_mode_specific_request(req)
    _validate_start_request(req)
    _ensure_regenerate_assets_exist(req)
    new_sid = str(int(time.time() * 1000))
    queue: asyncio.Queue = asyncio.Queue()
    pause_event = asyncio.Event()
    pause_event.set()
    control = {
        "pause_event": pause_event,
        "cancelled": False,
        "fastgen_cancel_event": threading.Event(),
    }

    _sessions[new_sid] = {
        "status": "running",
        "queue": queue,
        "result": None,
        "error": None,
        "started_at": time.time(),
        "control": control,
        "topic": _session_topic_from_request(req),
        "mode": req.mode,
        "request": req_data,
    }

    task = asyncio.create_task(_run_pipeline_task(new_sid, req, queue, control))
    _sessions[new_sid]["task"] = task

    logger.info(f"[Restart] Restarted session {session_id} → {new_sid}")
    return {"session_id": new_sid, "previous_session_id": session_id}


def _get_video_metadata() -> list[dict]:
    """Список видео: плоская папка video_*.mp4 и legacy session/*.mp4."""
    videos_dir = settings.videos_dir
    topics_by_session: dict[str, str] = {}
    quote_caption_en_by_session: dict[str, str] = {}
    regen_sessions: set[str] = set()
    publishing_by_session: dict[str, dict] = {}
    try:
        from agents.topics_history import get_used_topics, get_publishing_by_session

        for t in get_used_topics():
            sid = t.get("session_id")
            if sid:
                topics_by_session[sid] = t.get("topic") or t.get("video_angle") or f"Видео #{sid[-8:]}"
                qen = t.get("quote_caption_en")
                if isinstance(qen, str) and qen.strip():
                    quote_caption_en_by_session[sid] = qen.strip()
                snap = t.get("start_request")
                if isinstance(snap, dict) and snap:
                    regen_sessions.add(sid)
        publishing_by_session = get_publishing_by_session()
    except Exception:
        pass

    videos = []
    seen = set()

    # 1) Плоская папка: video_{session_id}.mp4
    if videos_dir.exists():
        for mp4 in sorted(videos_dir.glob("video_*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                sid = mp4.stem.replace("video_", "")
                if sid in seen:
                    continue
                seen.add(sid)
                stat = mp4.stat()
                cap_ru = topics_by_session.get(sid)
                videos.append({
                    "session_id": sid,
                    "filename": mp4.name,
                    "title": topics_by_session.get(sid) or f"Видео #{sid[-8:]}",
                    "size_mb": round(stat.st_size / 1024 / 1024, 1),
                    "created_at": stat.st_mtime,
                    "url": f"/api/video/{sid}/{mp4.name}",
                    "thumbnail_url": f"/api/video/{sid}/thumbnail",
                    "can_regenerate": sid in regen_sessions,
                    "quote_caption_ru": cap_ru,
                    "quote_caption_en": quote_caption_en_by_session.get(sid),
                    "publishing": publishing_by_session.get(sid),
                })
            except Exception:
                pass

        # 2) Legacy: session_id/video_*.mp4 (или video_ru.mp4, video_en.mp4 — Mode 4 bilingual)
        for session_dir in videos_dir.iterdir():
            if not session_dir.is_dir() or session_dir.name.startswith("_"):
                continue
            sid = session_dir.name
            all_mp4 = [p for p in session_dir.glob("*.mp4") if _is_public_session_mp4(p.name)]
            final_m5 = session_dir / "video_mode5.mp4"
            has_final_m5 = final_m5.is_file()
            preview_m5 = sorted(
                (p for p in all_mp4 if p.name.startswith("mode5_preview_")),
                key=lambda p: p.name,
            )
            base = topics_by_session.get(sid) or f"Цитата #{sid[-8:]}"
            cap_en = quote_caption_en_by_session.get(sid)
            cap_ru = topics_by_session.get(sid)

            # Mode 5 long-form: один пункт в библиотеке — финал или одна «связка» превью + склейка.
            if has_final_m5:
                mp4 = final_m5
                key = (sid, mp4.name)
                if key not in seen:
                    seen.add(key)
                    stat = mp4.stat()
                    thumb_q = quote(mp4.name, safe="")
                    videos.append({
                        "session_id": sid,
                        "filename": mp4.name,
                        "title": topics_by_session.get(sid) or f"Видео #{sid[-8:]}",
                        "size_mb": round(stat.st_size / 1024 / 1024, 1),
                        "created_at": stat.st_mtime,
                        "url": f"/api/video/{sid}/{mp4.name}",
                        "thumbnail_url": f"/api/video/{sid}/thumbnail?file={thumb_q}",
                        "can_regenerate": sid in regen_sessions,
                        "quote_caption_ru": cap_ru,
                        "quote_caption_en": cap_en,
                        "video_lang": None,
                        "publishing": publishing_by_session.get(sid),
                        "mode5_has_final": True,
                    })
            elif preview_m5:
                bkey = (sid, "__mode5_bundle__")
                if bkey not in seen:
                    seen.add(bkey)
                    first = preview_m5[0]
                    created = max(p.stat().st_mtime for p in preview_m5)
                    total_sz = sum(p.stat().st_size for p in preview_m5)
                    thumb_q = quote(first.name, safe="")
                    n = len(preview_m5)
                    videos.append({
                        "session_id": sid,
                        "filename": first.name,
                        "title": f"{topics_by_session.get(sid) or f'Видео #{sid[-8:]}'} · {n} ч. (склеить в финал)",
                        "size_mb": round(total_sz / 1024 / 1024, 1),
                        "created_at": created,
                        "url": f"/api/video/{sid}/{first.name}",
                        "thumbnail_url": f"/api/video/{sid}/thumbnail?file={thumb_q}",
                        "can_regenerate": sid in regen_sessions,
                        "quote_caption_ru": cap_ru,
                        "quote_caption_en": cap_en,
                        "video_lang": None,
                        "publishing": publishing_by_session.get(sid),
                        "mode5_can_assemble": True,
                        "mode5_preview_count": n,
                    })

            for mp4 in all_mp4:
                if has_final_m5 and mp4.name.startswith("mode5_preview_"):
                    continue
                if preview_m5 and mp4.name.startswith("mode5_preview_"):
                    continue
                if has_final_m5 and mp4.name == "video_mode5.mp4":
                    continue
                if not _is_public_session_mp4(mp4.name):
                    continue
                key = (sid, mp4.name)
                if key in seen:
                    continue
                seen.add(key)
                stem = mp4.stem
                if stem == "video_ru":
                    title = base if base else f"Видео #{sid[-8:]}"
                    if not title.endswith("(RU)") and " (RU)" not in title:
                        title = f"{title} (RU)"
                elif stem == "video_en":
                    title = (cap_en or f"{base} (EN)").strip()
                else:
                    title = topics_by_session.get(sid) or f"Видео #{sid[-8:]}"
                stat = mp4.stat()
                thumb_q = quote(mp4.name, safe="")
                videos.append({
                    "session_id": sid,
                    "filename": mp4.name,
                    "title": title,
                    "size_mb": round(stat.st_size / 1024 / 1024, 1),
                    "created_at": stat.st_mtime,
                    "url": f"/api/video/{sid}/{mp4.name}",
                    "thumbnail_url": f"/api/video/{sid}/thumbnail?file={thumb_q}",
                    "can_regenerate": sid in regen_sessions,
                    "quote_caption_ru": cap_ru,
                    "quote_caption_en": cap_en,
                    "video_lang": "ru" if stem == "video_ru" else ("en" if stem == "video_en" else None),
                    "publishing": publishing_by_session.get(sid),
                })

    videos.sort(key=lambda v: v["created_at"], reverse=True)
    return videos


@app.get("/api/videos")
async def list_videos():
    data = _get_video_metadata()
    logger.info(f"[API /videos] returning {len(data)} videos")
    return {"videos": data}


def _read_google_credential_token_for_revoke(path: Path) -> str | None:
    """refresh_token (лучше) или access token из JSON от google.auth."""
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return raw.get("refresh_token") or raw.get("token")


def _revoke_google_token_blocking(token: str) -> None:
    try:
        import httpx

        r = httpx.post(
            "https://oauth2.googleapis.com/revoke",
            data={"token": token},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15.0,
        )
        if r.status_code not in (200, 400):
            logger.warning(f"[YouTube] revoke → {r.status_code}: {r.text[:200]}")
    except Exception as ex:
        logger.warning(f"[YouTube] revoke request failed: {ex}")


def _youtube_oauth_cleanup_states() -> None:
    now = time.time()
    for s in list(_youtube_oauth_states.keys()):
        raw = _youtube_oauth_states.get(s)
        t = raw["t"] if isinstance(raw, dict) else raw
        if now - t > 600:
            _youtube_oauth_states.pop(s, None)


def _session_topic_fallback(session_id: str) -> str:
    try:
        from agents.topics_history import get_used_topics

        for t in get_used_topics():
            if t.get("session_id") == session_id:
                return (t.get("topic") or t.get("video_angle") or session_id[-8:])[:200]
    except Exception:
        pass
    return f"Short {session_id[-8:]}"


def _youtube_channel_hint(channels: list[dict]) -> str:
    if not channels:
        return ""
    if len(channels) == 1:
        t = channels[0].get("title") or ""
        cu = (channels[0].get("custom_url") or "").strip().lstrip("@")
        if t and cu:
            return f"{t} (@{cu})"
        return t or (f"@{cu}" if cu else "")
    return f"{len(channels)} каналов (куда уйдёт ролик — тот канал, который был выбран при OAuth для этого файла токена)"


@app.get("/api/youtube/status")
async def youtube_api_status(quick: bool = Query(False)):
    """
    quick=true — только файлы токенов на диске, без Google API (не падает на channels.list/build).
    """
    from agents.publisher import youtube_direct
    from agents.publisher.youtube_multi import (
        try_load_youtube_profiles,
        uses_youtube_registry,
        youtube_profiles_registry_path,
    )

    profs = try_load_youtube_profiles(settings)
    if not profs:
        reg = youtube_profiles_registry_path(settings)
        return {
            "client_configured": False,
            "authorized": False,
            "authorized_any": False,
            "has_secondary": False,
            "uses_registry": bool(reg and reg.is_file()),
            "registry_path": str(reg) if reg else "",
            "profile_order": [],
            "profile_list": [],
            "profiles": {},
        }

    reg_path = youtube_profiles_registry_path(settings)
    uses_reg = uses_youtube_registry(settings)
    configured_global = any(p.client_secrets_path.is_file() for p in profs)

    def _auth_ok(path: Path) -> bool:
        if not path.is_file():
            return False
        try:
            creds = youtube_direct.load_credentials(path)
            return bool(creds and (creds.valid or creds.refresh_token))
        except Exception:
            return False

    profile_order = [p.id for p in profs]
    profiles: dict[str, dict] = {}
    profile_list: list[dict] = []

    for p in profs:
        cs = p.client_secrets_path
        ok = _auth_ok(p.token_path)
        entry: dict = {
            "id": p.id,
            "token_file": str(p.token_path),
            "authorized": ok,
            "label": p.label,
            "channels": [],
            "channel_hint": "",
            "client_secret_path": str(cs),
            "client_secret_configured": cs.is_file(),
            "gcp_project": p.gcp_project or "",
        }
        if ok and cs.is_file() and not quick:
            try:
                creds = await asyncio.to_thread(
                    youtube_direct.get_valid_credentials, cs, p.token_path
                )
                if creds:
                    chans = await asyncio.to_thread(
                        youtube_direct.list_managed_channels_preview, creds
                    )
                    entry["channels"] = chans
                    entry["channel_hint"] = _youtube_channel_hint(chans)
            except Exception as ex:
                logger.warning(f"[YouTube] status enrich {p.id}: {ex}")
        profiles[p.id] = {k: v for k, v in entry.items() if k != "id"}
        profile_list.append(entry)

    has_secondary = len(profs) > 1
    first_id = profile_order[0]
    authorized_first = bool(profiles.get(first_id, {}).get("authorized"))
    authorized_any = any(
        bool(profiles.get(pid, {}).get("authorized")) for pid in profile_order
    )
    legacy_primary = profiles.get("primary", {}).get("authorized")
    top_authorized = (
        legacy_primary if "primary" in profiles else authorized_first
    )

    return {
        "client_configured": configured_global,
        "authorized": bool(top_authorized),
        "authorized_any": authorized_any,
        "has_secondary": has_secondary,
        "uses_registry": uses_reg,
        "registry_path": str(reg_path) if reg_path else "",
        "profile_order": profile_order,
        "profile_list": profile_list,
        "profiles": profiles,
    }


@app.post("/api/youtube/reset")
async def youtube_reset_all_tokens():
    """
    Удаляет локальные youtube_token*.json (основной + второй, если настроен),
    пытается отозвать у Google (best-effort), сбрасывает pending OAuth state.
    """
    from agents.publisher.youtube_multi import try_load_youtube_profiles

    profs = try_load_youtube_profiles(settings)
    if not profs:
        raise HTTPException(
            400,
            "YouTube не настроен: укажи YOUTUBE_PROFILES_CONFIG или YOUTUBE_OAUTH_CLIENT_SECRETS",
        )

    paths = [p.token_path for p in profs]

    removed: list[str] = []
    for p in paths:
        tok = _read_google_credential_token_for_revoke(p)
        if tok:
            await asyncio.to_thread(_revoke_google_token_blocking, tok)
        if p.is_file():
            try:
                p.unlink()
                removed.append(str(p))
            except OSError as ex:
                logger.warning(f"[YouTube] не удалось удалить {p}: {ex}")

    _youtube_oauth_states.clear()
    logger.info(f"[RESET] YouTube OAuth: удалены файлы {removed}")
    return {"ok": True, "removed": removed}


@app.get("/api/youtube/oauth/authorize")
async def youtube_oauth_authorize(profile: str = Query("primary")):
    from agents.publisher import youtube_direct
    from agents.publisher.youtube_multi import get_youtube_profile, try_load_youtube_profiles

    profs = try_load_youtube_profiles(settings)
    if not profs:
        raise HTTPException(
            400,
            "YouTube не настроен: YOUTUBE_PROFILES_CONFIG или YOUTUBE_OAUTH_CLIENT_SECRETS",
        )
    key = (profile or "primary").strip().lower()
    try:
        yp = get_youtube_profile(settings, key)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    cs = yp.client_secrets_path
    if not cs.is_file():
        raise HTTPException(
            400,
            f"OAuth client JSON не найден для профиля «{key}»: {cs}",
        )

    _youtube_oauth_cleanup_states()
    try:
        flow = youtube_direct.create_flow(cs, settings.youtube_oauth_redirect_uri)
        auth_url, state = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            include_granted_scopes="true",
        )
    except Exception as e:
        logger.exception(f"[YouTube] authorization_url failed: {e}")
        raise HTTPException(500, f"OAuth URL: {e}") from e
    _youtube_oauth_states[state] = {"t": time.time(), "profile": yp.id}
    return {"authorization_url": auth_url, "state": state, "profile": yp.id}


@app.get("/api/youtube/oauth/callback")
async def youtube_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    base_ui = settings.frontend_public_url.rstrip("/")
    redir = f"{base_ui}/history"
    if error:
        return RedirectResponse(f"{redir}?youtube_error={quote(error)}")
    if not code or not state:
        return RedirectResponse(f"{redir}?youtube_error={quote('missing_code_or_state')}")
    raw_meta = _youtube_oauth_states.pop(state, None)
    if raw_meta is None:
        return RedirectResponse(f"{redir}?youtube_error={quote('invalid_state')}")
    if isinstance(raw_meta, dict):
        prof = str(raw_meta.get("profile", "primary")).lower()
        t0 = float(raw_meta.get("t", 0))
    else:
        prof, t0 = "primary", float(raw_meta)
    if time.time() - t0 > 600:
        return RedirectResponse(f"{redir}?youtube_error={quote('oauth_state_expired')}")
    try:
        from agents.publisher import youtube_direct
        from agents.publisher.youtube_multi import get_youtube_profile

        yp = get_youtube_profile(settings, prof)
        token_path = yp.token_path
        cs = yp.client_secrets_path
    except ValueError as e:
        return RedirectResponse(f"{redir}?youtube_error={quote(str(e)[:120])}")
    if not cs.is_file():
        return RedirectResponse(f"{redir}?youtube_error={quote('client_secrets_missing')}")
    try:
        youtube_direct.save_token_from_code(
            cs,
            token_path,
            settings.youtube_oauth_redirect_uri,
            code,
            state,
        )
    except Exception as e:
        logger.exception(f"[YouTube] OAuth callback failed: {e}")
        return RedirectResponse(f"{redir}?youtube_error={quote(str(e)[:200])}")
    return RedirectResponse(f"{redir}?youtube_oauth=ok")


def _youtube_upload_limit_exceeded(exc: BaseException) -> bool:
    s = str(exc).lower()
    return "uploadlimitexceeded" in s.replace(" ", "") or "exceeded the number of videos" in s


@app.post("/api/youtube/upload")
async def youtube_upload_short(body: YouTubeUploadBody):
    from agents.publisher import youtube_direct
    from agents.publisher.youtube_multi import get_youtube_profile
    from googleapiclient.errors import HttpError

    try:
        yp = get_youtube_profile(settings, body.channel_profile)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    cs = yp.client_secrets_path
    token_path = yp.token_path
    if not cs.is_file():
        raise HTTPException(
            400,
            f"OAuth client JSON для профиля «{yp.id}» не найден: {cs}",
        )

    creds = youtube_direct.get_valid_credentials(cs, token_path)
    if not creds:
        raise HTTPException(
            401,
            f"Нет токена для профиля «{body.channel_profile}»: открой /history и подключи этот канал (OAuth).",
        )

    # ── Казино: скачанный TikTok-ролик (тот же upload_video_file + оверлей, что в casino_routes) ──
    sc = (body.social_channel_id or "").strip()
    sk = (body.social_video_key or "").strip()
    if sc and sk:
        from casino_routes import run_social_youtube_upload_with_lock

        def _run_social() -> tuple[str, str, str]:
            return run_social_youtube_upload_with_lock(
                sc,
                sk,
                channel_profile=body.channel_profile,
                branding_corner=(body.branding_corner or "tr"),
                title=body.title or "",
                description=body.description or "",
                keywords=body.keywords or "",
                tags=body.tags or "",
                privacy=body.privacy_status,
                category_id=body.category_id or "",
            )

        try:
            vid, _ch_id, title_used = await asyncio.to_thread(_run_social)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except HttpError as e:
            msg = youtube_direct.format_http_error(e)
            logger.error(f"[YouTube] social upload HttpError: {msg}")
            if _youtube_upload_limit_exceeded(e):
                raise HTTPException(
                    status_code=429,
                    detail="YouTube лимит загрузок: аккаунт/канал превысил допустимое число видео за период.",
                ) from e
            raise HTTPException(502, f"YouTube API: {msg}") from e
        except RuntimeError as e:
            msg = str(e)
            if _youtube_upload_limit_exceeded(e):
                raise HTTPException(
                    status_code=429,
                    detail="YouTube лимит загрузок: аккаунт/канал превысил допустимое число видео за период.",
                ) from e
            raise HTTPException(502, msg) from e
        except Exception as e:
            logger.exception(f"[YouTube] social upload failed: {e}")
            raise HTTPException(500, str(e)) from e

        return {
            "ok": True,
            "video_id": vid,
            "url": f"https://www.youtube.com/shorts/{vid}" if vid else None,
            "title": title_used,
        }

    # ── библиотека (История видео) ──
    fn = (body.filename or "").strip() or f"video_{body.session_id}.mp4"
    path = _resolve_video_path(body.session_id, fn)
    if not path or not path.is_file():
        raise HTTPException(404, f"Видео не найдено: {fn}")

    pub_meta = None
    video_lang = None
    try:
        for v in _get_video_metadata():
            if v.get("session_id") == body.session_id and v.get("filename") == fn:
                pub_meta = v.get("publishing")
                video_lang = v.get("video_lang")
                break
        else:
            from agents.topics_history import get_publishing_by_session

            pub_meta = get_publishing_by_session().get(body.session_id)
    except Exception:
        pub_meta = None

    title, description, tags = youtube_direct.publishing_to_snippet(
        pub_meta,
        video_title_fallback=_session_topic_fallback(body.session_id),
        lang=body.lang,
        video_lang=video_lang,
    )

    try:
        result = await asyncio.to_thread(
            youtube_direct.upload_video_file,
            creds,
            path,
            title=title,
            description=description,
            tags=tags,
            privacy_status=body.privacy_status,
        )
    except TimeoutError as e:
        logger.error(f"[YouTube] upload timeout: {e}")
        raise HTTPException(
            504,
            "Загрузка в YouTube зависла по таймауту. Повтори попытку; если повторяется, переподключи OAuth и проверь сеть.",
        ) from e
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except HttpError as e:
        msg = youtube_direct.format_http_error(e)
        logger.error(f"[YouTube] upload HttpError: {msg}")
        raise HTTPException(502, f"YouTube API: {msg}") from e
    except Exception as e:
        if youtube_direct._is_transient_network_error(e):
            raise HTTPException(
                503,
                "Временная сетевая ошибка при обращении к YouTube API (DNS/соединение). Повтори попытку через несколько секунд.",
            ) from e
        logger.exception(f"[YouTube] upload failed: {e}")
        raise HTTPException(500, str(e)) from e

    vid = result.get("id") or ""
    return {
        "ok": True,
        "video_id": vid,
        "url": f"https://www.youtube.com/shorts/{vid}" if vid else None,
        "title": title,
    }


@app.delete("/api/videos/{session_id}")
async def delete_video(
    session_id: str,
    filename: str | None = Query(
        None,
        description="Удалить только этот файл в папке сессии (напр. video_en.mp4 для Mode 4).",
    ),
):
    """
    Удалить видео с диска и из истории.
    Query `filename`: удалить только этот mp4 в legacy-папке сессии (RU/EN независимо).
    Без filename — вся папка сессии или плоский video_{sid}.mp4.
    """
    import shutil

    fname = (filename or "").strip() or None
    if fname:
        fname = Path(fname).name
        if not fname.endswith(".mp4") or not _is_public_session_mp4(fname):
            raise HTTPException(400, "Некорректное имя файла")

    removed = False
    videos_dir = settings.videos_dir
    session_dir = videos_dir / session_id

    # Точечное удаление одного mp4 в legacy-папке (два ролика Mode 4 в одной сессии)
    if fname and session_dir.is_dir():
        target = (session_dir / fname).resolve()
        try:
            target.relative_to(session_dir.resolve())
        except ValueError:
            raise HTTPException(400, "Некорректный путь") from None
        if target.is_file():
            target.unlink()
            removed = True
            rest = [
                p
                for p in session_dir.glob("*.mp4")
                if p.is_file() and _is_public_session_mp4(p.name)
            ]
            if not rest:
                shutil.rmtree(session_dir)
                from agents.topics_history import remove_topic

                remove_topic(session_id)
            return {"deleted": True, "partial": True}
        # Финал часто в корне videos/ (video_{sid}.mp4), а session_id/ — только clips и т.д.
        if fname != f"video_{session_id}.mp4":
            raise HTTPException(404, "Video not found")

    # Удалить плоский файл
    flat_path = videos_dir / f"video_{session_id}.mp4"
    if flat_path.exists():
        flat_path.unlink()
        removed = True

    # Удалить legacy папку session_id целиком
    if session_dir.exists():
        shutil.rmtree(session_dir)
        removed = True

    if not removed:
        raise HTTPException(404, "Video not found")

    from agents.topics_history import remove_topic

    remove_topic(session_id)
    return {"deleted": True}


@app.post("/api/videos/{session_id}/regenerate")
async def regenerate_video_from_library(
    session_id: str,
    body: LibraryRegenerateBody = Body(default_factory=LibraryRegenerateBody),
):
    """
    Перегенерация по сохранённым параметрам (после успешной генерации они пишутся в topics_history).
    Удаляет старые файлы этой сессии и запускает новый пайплайн. Возвращает новый session_id.

    Mode 4: в теле можно передать {"filename": "video_en.mp4"} или video_ru.mp4 —
    пересоздаётся только этот ролик (тот же промпт-агент, один вызов FastGen).
    """
    import shutil

    from agents.topics_history import get_start_request_for_session, remove_topic

    payload = get_start_request_for_session(session_id)
    if not payload:
        raise HTTPException(
            404,
            "Для этого видео нет сохранённых параметров перегенерации. "
            "Сгенерируйте ролик ещё раз с главной страницы — после этого кнопка станет доступна.",
        )
    req_dict = dict(payload)
    if req_dict.get("mode") == 4:
        fn = (body.filename or "").strip().lower()
        if fn == "video_en.mp4":
            req_dict["mode4_only_lang"] = "en"
        elif fn == "video_ru.mp4":
            req_dict["mode4_only_lang"] = "ru"
        else:
            req_dict.pop("mode4_only_lang", None)
    else:
        req_dict.pop("mode4_only_lang", None)

    try:
        req = StartRequest.model_validate(req_dict)
    except Exception as e:
        raise HTTPException(400, f"Сохранённые параметры устарели или повреждены: {e}") from e

    _normalize_mode_specific_request(req)
    _validate_start_request(req)
    _ensure_regenerate_assets_exist(req)

    videos_dir = settings.videos_dir
    session_dir = videos_dir / session_id
    new_sid = str(int(time.time() * 1000))
    new_dir = videos_dir / new_sid

    # Mode 4: перегенерация одного языка — сохранить второй mp4 в новой папке сессии
    only_lang = (req.mode4_only_lang or "").strip().lower()
    if req.mode == 4 and only_lang in ("en", "ru") and session_dir.is_dir():
        if only_lang == "en":
            other = session_dir / "video_ru.mp4"
            if other.is_file():
                new_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(other, new_dir / "video_ru.mp4")
        elif only_lang == "ru":
            other = session_dir / "video_en.mp4"
            if other.is_file():
                new_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(other, new_dir / "video_en.mp4")

    flat_path = videos_dir / f"video_{session_id}.mp4"
    if flat_path.exists():
        flat_path.unlink()
    if session_dir.exists():
        shutil.rmtree(session_dir)

    remove_topic(session_id)
    _sessions.pop(session_id, None)
    queue: asyncio.Queue = asyncio.Queue()
    pause_event = asyncio.Event()
    pause_event.set()
    control = {
        "pause_event": pause_event,
        "cancelled": False,
        "fastgen_cancel_event": threading.Event(),
    }
    request_stored = req.model_dump()
    request_stored.pop("mode4_only_lang", None)

    _sessions[new_sid] = {
        "status": "running",
        "queue": queue,
        "result": None,
        "error": None,
        "started_at": time.time(),
        "control": control,
        "topic": _session_topic_from_request(req),
        "mode": req.mode,
        "request": request_stored,
    }
    task = asyncio.create_task(_run_pipeline_task(new_sid, req, queue, control))
    _sessions[new_sid]["task"] = task

    logger.info(f"[Regenerate] Library {session_id} → new session {new_sid} (mode {req.mode})")
    return {"session_id": new_sid, "previous_session_id": session_id}


def _resolve_video_path(session_id: str, filename: str) -> Path | None:
    """Resolve path: flat video_{sid}.mp4, legacy session_id/filename, или session_id/clips/clip_*.mp4."""
    videos_dir = settings.videos_dir
    flat_path = videos_dir / f"video_{session_id}.mp4"
    if flat_path.exists():
        return flat_path
    if ".." in filename:
        return None
    legacy_root = (videos_dir / session_id).resolve()
    if not legacy_root.is_dir():
        return None
    norm = filename.replace("\\", "/")
    parts = Path(norm).parts
    candidates: list[Path] = []
    if len(parts) == 1:
        candidates.append(legacy_root / parts[0])
        fn = parts[0]
        if fn.lower().startswith("clip_") and fn.endswith(".mp4"):
            candidates.append(legacy_root / "clips" / fn)
    elif len(parts) == 2 and parts[0] == "clips":
        candidates.append(legacy_root / "clips" / parts[1])
    for cand in candidates:
        try:
            rc = cand.resolve()
            rc.relative_to(legacy_root)
        except ValueError:
            continue
        if rc.is_file():
            return rc
    return None


def _is_public_session_mp4(filename: str) -> bool:
    """Служебные файлы (temp audio MoviePy `_m4_snd_*` и т.п.) не в библиотеку и не в превью."""
    return not Path(filename).name.startswith("_")


def _pick_legacy_thumbnail_path(legacy_dir: Path) -> Path | None:
    """Предпочесть финальные video_ru / video_en, не клип clip_*.mp4."""
    mp4s = sorted(p for p in legacy_dir.glob("*.mp4") if _is_public_session_mp4(p.name))
    if not mp4s:
        return None
    for name in ("video_ru.mp4", "video_en.mp4", "video_parable_ru.mp4", "video_parable_en.mp4", "video_parable.mp4"):
        p = legacy_dir / name
        if p.exists():
            return p
    # без финалов — любой файл кроме очевидных клипов (если есть другой)
    non_clip = [p for p in mp4s if not p.name.lower().startswith("clip_")]
    return non_clip[0] if non_clip else mp4s[0]


def _legacy_thumbnail_candidate_paths(legacy: Path, preferred: Path | None) -> list[Path]:
    """Порядок mp4 для превью: сначала выбранный файл, затем остальные финалы и клипы (без дубликатов)."""
    lr = legacy.resolve()
    out: list[Path] = []
    seen: set[str] = set()

    def push(p: Path | None) -> None:
        if p is None or not p.is_file():
            return
        try:
            rp = p.resolve()
            rp.relative_to(lr)
        except ValueError:
            return
        k = str(rp)
        if k in seen:
            return
        seen.add(k)
        out.append(rp)

    push(preferred)
    for name in ("video_ru.mp4", "video_en.mp4", "video_parable_ru.mp4", "video_parable_en.mp4", "video_parable.mp4"):
        push(lr / name)
    for p in sorted(legacy.glob("*.mp4")):
        if _is_public_session_mp4(p.name):
            push(p.resolve())
    clips = lr / "clips"
    if clips.is_dir():
        for p in sorted(clips.glob("clip_*.mp4"))[:48]:
            push(p.resolve())
    return out


def _jpeg_first_frame_moviepy(video_path: Path) -> bytes | None:
    """Первый кадр как JPEG, или None если файл битый / без moov / пустой."""
    try:
        from moviepy import VideoFileClip
        import io
        from PIL import Image

        vc = VideoFileClip(str(video_path))
        try:
            frame = vc.get_frame(0)
        finally:
            vc.close()
        img = Image.fromarray(frame)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception:
        return None


@app.get("/api/video/{session_id}/thumbnail")
async def serve_video_thumbnail(
    session_id: str,
    video_file: str | None = Query(None, alias="file"),
):
    """Первый кадр видео как JPEG (аватарка). Параметр file= — имя mp4 в папке сессии (для RU/EN)."""
    videos_dir = settings.videos_dir
    # Пробуем flat формат: video_{session_id}.mp4 или video_{session_id}_*.mp4
    flat_path = videos_dir / f"video_{session_id}.mp4"
    legacy = videos_dir / session_id
    path: Path | None = None

    # 1) Если передан video_file и есть legacy папка — корень или clips/
    if video_file and legacy.is_dir():
        safe_name = Path(video_file).name
        if safe_name.endswith(".mp4") and _is_public_session_mp4(safe_name):
            lr = legacy.resolve()
            for rel in (legacy / safe_name, legacy / "clips" / safe_name):
                candidate = rel.resolve()
                try:
                    candidate.relative_to(lr)
                except ValueError:
                    raise HTTPException(400, "Invalid file path") from None
                if candidate.is_file():
                    path = candidate
                    break

    # 2) Если не нашли в legacy, пробуем flat формат в корне videos_dir
    if path is None:
        # Проверяем video_{session_id}.mp4
        if flat_path.exists():
            path = flat_path
        else:
            # Проверяем video_{session_id}_*.mp4 (например, _with_preview)
            for candidate in videos_dir.glob(f"video_{session_id}_*.mp4"):
                if candidate.is_file():
                    path = candidate
                    break

    # 3) Если не нашли flat, пробуем legacy папку
    if path is None and legacy.is_dir():
        path = _pick_legacy_thumbnail_path(legacy)
    if not path or not path.exists():
        raise HTTPException(404, "Video not found")

    candidates: list[Path] = []
    if legacy.is_dir():
        try:
            path.resolve().relative_to(legacy.resolve())
            candidates = _legacy_thumbnail_candidate_paths(legacy, path)
        except ValueError:
            pass
    if not candidates:
        candidates = [path]

    last_fail: str | None = None
    for src in candidates:
        jpeg = _jpeg_first_frame_moviepy(src)
        if jpeg is not None:
            return Response(content=jpeg, media_type="image/jpeg")
        last_fail = src.name

    logger.debug(
        f"Thumbnail: no readable mp4 for session {session_id} (tried {len(candidates)}, last={last_fail})"
    )
    raise HTTPException(
        404,
        "Could not read video for thumbnail (file incomplete or corrupt — e.g. interrupted export)",
    )


@app.get("/api/video/{session_id}/{filename}")
async def serve_video(session_id: str, filename: str):
    path = _resolve_video_path(session_id, filename)
    if not path:
        raise HTTPException(404, "Video not found")
    return FileResponse(str(path), media_type="video/mp4")


@app.post("/api/scenario/generate")
async def generate_scenario(req: ScenarioRequest):
    """
    Generate a full scenario (script) for a given topic without starting the video pipeline.
    Returns the Scenario object so the frontend can display it for editing.
    """
    try:
        if req.mode == 2:
            from modes.mode2.scenario_writer import write_mode2_scenario
            scenario = await write_mode2_scenario(
                topic=req.topic or ("interesting facts" if getattr(req, "language", "ru") == "en" else "интересные факты"),
                num_scenes=req.num_scenes,
                language=getattr(req, "language", "ru") or "ru",
            )
            return {"scenario": scenario}

        from agents.scenario_writer.agent import run_scenario_writer_agent
        import re

        def _extract_top5_subject(t: str) -> str:
            t = (t or "").strip()
            m = re.match(
                r"^\s*Топ[-\s]*5\s*фактов\s+(?:о|про)\s*(.+?)\s*$",
                t,
                flags=re.IGNORECASE,
            )
            if m:
                return m.group(1).strip().rstrip(".")
            return t

        topic_subject = _extract_top5_subject(req.topic)
        fact_context = None

        if settings.use_fact_miner:
            from agents.fact_miner.agent import run_fact_miner_agent
            fact_context = await run_fact_miner_agent(
                topic=topic_subject,
                num_scenes=req.num_scenes,
                trend_context=req.trend_context,
            )
        scenario = await run_scenario_writer_agent(
            topic=topic_subject,
            num_scenes=req.num_scenes,
            trend_context=req.trend_context,
            fact_context=fact_context,
        )
        return {"scenario": scenario}
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/topics/history")
async def topics_history():
    """
    Список всех видео из всех режимов с названиями.
    Объединяет: реальные видео из MyVideo + данные из topics_history.
    """
    from datetime import datetime
    from agents.topics_history import get_used_topics
    topics_by_sid: dict[str, dict] = {}
    for t in get_used_topics():
        sid = t.get("session_id")
        if sid:
            topics_by_sid[sid] = dict(t)

    result = []
    videos = _get_video_metadata()
    logger.info(f"[API /topics/history] building from {len(videos)} videos")
    for v in videos:
        sid = v["session_id"]
        title = v["title"]
        created = v.get("created_at")
        gen_at = None
        if created:
            try:
                gen_at = datetime.fromtimestamp(created).isoformat(timespec="seconds")
            except Exception:
                pass

        entry = topics_by_sid.get(sid) or {}
        result.append({
            "session_id": sid,
            "topic": entry.get("topic") or title,
            "video_angle": entry.get("video_angle") or "",
            "generated_at": entry.get("generated_at") or gen_at or "",
        })
    logger.info(f"[API /topics/history] returning {len(result)} topics")
    return {"topics": result}


@app.delete("/api/topics/history")
async def clear_topics_history():
    """Clear the entire topics history."""
    from agents.topics_history import _HISTORY_FILE
    if _HISTORY_FILE.exists():
        _HISTORY_FILE.unlink()
    return {"cleared": True}


@app.delete("/api/topics/history/{session_id}")
async def remove_topic_from_history(session_id: str):
    """Удалить запись из журнала тем и видеофайл с диска."""
    import shutil
    from agents.topics_history import remove_topic
    remove_topic(session_id)
    # Удаляем и видеофайл, чтобы элемент исчез из списка
    videos_dir = settings.videos_dir
    flat_path = videos_dir / f"video_{session_id}.mp4"
    if flat_path.exists():
        flat_path.unlink()
    session_dir = videos_dir / session_id
    if session_dir.exists():
        shutil.rmtree(session_dir)
    return {"removed": True, "session_id": session_id}


@app.post("/api/topics/regenerate/{session_id}")
async def regenerate_topic(session_id: str):
    """
    Remove a topic from history and start a new pipeline run for the same topic.
    Returns a new session_id to track via SSE.
    """
    from agents.topics_history import get_used_topics, remove_topic

    # Find the original entry
    entry = next(
        (t for t in get_used_topics() if t.get("session_id") == session_id),
        None,
    )
    if not entry:
        raise HTTPException(404, f"Session {session_id!r} not found in history")

    topic    = entry.get("topic", "")
    angle    = entry.get("video_angle", "")

    # Remove from history so it can be re-generated without "duplicate" blocking
    remove_topic(session_id)

    # Start a fresh pipeline run
    req = StartRequest(
        topic=angle or topic,
        auto_topic=False,
        num_scenes=5,
        use_scenario=True,
        local_only=True,
    )

    new_sid = str(int(time.time() * 1000))
    queue: asyncio.Queue = asyncio.Queue()
    pause_event = asyncio.Event()
    pause_event.set()
    control = {
        "pause_event": pause_event,
        "cancelled": False,
        "fastgen_cancel_event": threading.Event(),
    }
    req_dict = req.model_dump()

    _sessions[new_sid] = {
        "status": "running",
        "queue": queue,
        "result": None,
        "error": None,
        "started_at": time.time(),
        "control": control,
        "topic": _session_topic_from_request(req),
        "mode": req.mode,
        "request": req_dict,
    }
    task = asyncio.create_task(_run_pipeline_task(new_sid, req, queue, control))
    _sessions[new_sid]["task"] = task
    return {"session_id": new_sid, "topic": topic}


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0"}


# ── Rate Limiter Endpoints ───────────────────────────────────────────────────

@app.get("/api/rate-limit/status")
async def get_rate_limit_status():
    """
    Get current rate limit status.
    
    Returns:
        {
            "limit": int (0 = без лимита, иначе 1, 2, 3, 5, 10, 15, 30),
            "used": int,
            "remaining": int | null (null если лимит отключён),
            "hour_key": str,
            "next_reset": str (ISO format)
        }
    """
    from utils.rate_limiter import get_rate_limiter
    limiter = get_rate_limiter()
    return limiter.get_status()


@app.post("/api/rate-limit/set")
async def set_rate_limit(limit: int = Body(..., embed=True)):
    """
    Set the hourly generation limit.
    
    Args:
        limit: Новое значение: 0 (без лимита) или 1, 2, 3, 5, 10, 15, 30
        
    Returns:
        {"success": bool, "limit": int}
    """
    from utils.rate_limiter import get_rate_limiter
    limiter = get_rate_limiter()
    
    success = limiter.set_limit(limit)
    
    if not success:
        raise HTTPException(
            400,
            f"Invalid limit: {limit}. Allowed: 0 (off), 1, 2, 3, 5, 10, 15, 30.",
        )
    
    return {"success": True, "limit": limit}


@app.post("/api/rate-limit/check")
async def check_rate_limit():
    """
    Check if a new video generation is allowed.
    
    Returns:
        {
            "allowed": bool,
            "reason": str,
            "used": int,
            "limit": int,
            "remaining": int
        }
    """
    from utils.rate_limiter import get_rate_limiter
    limiter = get_rate_limiter()
    
    allowed, reason = limiter.check_allowed()
    status = limiter.get_status()
    
    return {
        "allowed": allowed,
        "reason": reason,
        "used": status["used"],
        "limit": status["limit"],
        "remaining": status["remaining"]
    }


@app.post("/api/rate-limit/increment")
async def increment_rate_limit():
    """
    Increment the usage counter (call when starting a video generation).
    
    Returns:
        {
            "success": bool,
            "used": int,
            "remaining": int
        }
    """
    from utils.rate_limiter import get_rate_limiter
    limiter = get_rate_limiter()
    
    success = limiter.increment_usage()
    status = limiter.get_status()
    
    return {
        "success": success,
        "used": status["used"],
        "remaining": status["remaining"]
    }


@app.get("/api/debug/diag")
async def debug_diag():
    """Диагностика: что возвращают API, порядок маршрутов."""
    videos = _get_video_metadata()
    try:
        from agents.topics_history import get_used_topics
        topics = list(get_used_topics())
    except Exception:
        topics = []
    return {
        "api_ok": True,
        "content_type": "application/json",
        "videos_count": len(videos),
        "videos_sample": videos[:2] if videos else [],
        "topics_count": len(topics),
        "videos_dir": str(settings.videos_dir),
        "videos_dir_exists": settings.videos_dir.exists(),
    }


@app.post("/api/log/client-error")
async def log_client_error(data: dict):
    """Фронтенд шлёт сюда ошибки (Failed to fetch и т.д.) — видно в логах сервера."""
    msg = data.get("message", str(data))
    url = data.get("url", "")
    logger.warning(f"[CLIENT ERROR] {msg} | url={url}")
    return {}


@app.post("/api/video/keyframe")
async def generate_keyframe_video(req: KeyframeVideoRequest):
    """
    Generate video from start and end keyframe images.
    Uses fast-gen.ai keyframes mode for image-to-video transition.
    
    Args:
        req: KeyframeVideoRequest with prompt, start_frame_path, end_frame_path
    
    Returns:
        Path to generated video
    """
    from pathlib import Path as _PathLib
    
    start_path = _PathLib(req.start_frame_path)
    end_path = _PathLib(req.end_frame_path)
    
    if not start_path.exists():
        raise HTTPException(400, f"Start frame not found: {req.start_frame_path}")
    if not end_path.exists():
        raise HTTPException(400, f"End frame not found: {req.end_frame_path}")
    
    output_dir = _PathLib(req.output_dir) if req.output_dir else settings.videos_dir / "keyframes"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        from agents.content_generator.fastgen_scraper import generate_video_from_keyframes
        
        video_path = await generate_video_from_keyframes(
            prompt=req.prompt,
            output_dir=output_dir,
            start_frame_path=start_path,
            end_frame_path=end_path,
            index=0,
        )
        
        if video_path and video_path.exists():
            return {
                "success": True,
                "video_path": str(video_path),
                "video_url": f"/api/video/keyframes/{video_path.name}",
            }
        else:
            raise HTTPException(500, "Video generation failed")
            
    except Exception as e:
        logger.error(f"[Keyframe Video] Generation error: {e}")
        raise HTTPException(500, str(e))


# ── Serve built React frontend ─────────────────────────────────────────────────

_dist = Path(__file__).parent / "frontend" / "dist"

if _dist.exists():
    app.mount("/assets", StaticFiles(directory=str(_dist / "assets")), name="assets")
    logger.info(f"[Server] Frontend: {_dist} (SPA + /api/*)")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path == "api":
            logger.error(f"[ROUTING BUG] /api/ запрос попал в SPA! path={full_path!r}")
            raise HTTPException(status_code=404, detail="API route not found - routing misconfigured")
        return FileResponse(str(_dist / "index.html"))


if __name__ == "__main__":
    import multiprocessing as _mp
    # На Windows spawn дочерний Process (mode4 assembler) перезапускает этот скрипт — не запускать uvicorn во вторичном процессе
    if _mp.current_process().name == "MainProcess":
        import uvicorn
        
        logger.info("Starting VideoStudio server with graceful shutdown support...")
        
        uvicorn.run(
            "server:app",
            host="0.0.0.0",
            port=8000,
            reload=False,
            log_level="info",
            access_log=True,
            timeout_keep_alive=300,  # Keep connections alive longer during long operations
        )
