"""
FastAPI web server for AI Content Factory.

Run:  uvicorn server:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path

from urllib.parse import quote

from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel, field_validator

from config import settings

# ── Session store ─────────────────────────────────────────────────────────────
_sessions: dict[str, dict] = {}

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
        asyncio.run_coroutine_threadsafe(self._q.put(entry), self._loop)


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
        }
        await queue.put({"type": "done", **session["result"]})
        try:
            from agents.topics_history import attach_start_request_to_session

            req_snap = session.get("request")
            if req_snap:
                attach_start_request_to_session(session_id, req_snap)
        except Exception as ex:
            logger.warning(f"[TopicsHistory] attach_start_request failed: {ex}")

    except asyncio.CancelledError:
        session["status"] = "cancelled"
        control["cancelled"] = True
        await queue.put({"type": "error", "error": "Генерация отменена"})
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"Pipeline error: {exc}\n{tb}")
        session["status"] = "error"
        session["error"] = str(exc)
        await queue.put({"type": "error", "error": str(exc)})
    finally:
        if sink_id is not None:
            logger.remove(sink_id)


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="Content Factory API", version="1.0")


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
    # Mode 6: viral cartoon drama
    mode6_num_characters: int = 3
    # Mode 7: ASMR animal keyboard videos
    mode7_keyboards: list[str] | None = None
    mode7_animal_type: str | None = None
    # Mode 8: House Building Timelapse
    mode8_house_style: str | None = None  # "modern", "contemporary", "minimalist", "scandinavian", "cottage", "villa", "farmhouse", "colonial", "victorian", "mediterranean", "cabin", "log_house", "chalet", "adobe", "mansion", "estate"
    mode8_location: str | None = None  # "suburbs", "urban_edge", "planned_community", "forest", "wooded_area", "seaside", "lakefront", "riverside", "countryside", "farmland", "vineyard", "mountains", "hillside", "valley", "desert", "oasis", "tropical", "island"
    mode8_num_stages: int = 5
    # Mode 9: Vehicle Assembly Timelapse
    mode9_vehicle_type: str | None = None  # "airplane_passenger", "airplane_private", "car_modern", "car_sport", "truck_cargo", "tractor", "excavator", "ship_cargo", "yacht", "helicopter", "drone", and 21 more...
    mode9_location: str | None = None  # "construction_site", "factory", "shipyard", "hangar", "empty_field", "forest_clearing", "desert", "mountain_valley", "city_outskirts", "port", and 9 more...
    mode9_num_stages: int = 5
    # Mode 10: уборка пляжа (таймлапс, как mode 8)
    mode10_beach_type: str | None = None
    mode10_coast_setting: str | None = None
    mode10_num_stages: int = 5

    @field_validator("mode4_only_lang", mode="before")
    @classmethod
    def _normalize_mode4_only_lang(cls, v):  # noqa: ANN001
        if v is None or v == "":
            return None
        if isinstance(v, str) and v.lower() in ("ru", "en"):
            return v.lower()
        raise ValueError("mode4_only_lang must be 'ru', 'en', or null")


def _validate_start_request(req: StartRequest) -> None:
    """Проверки перед запуском пайплайна (общие для /pipeline/start и перегенерации)."""
    if req.mode == 3:
        has_images = bool(req.mode3_start_image_path and req.mode3_end_image_path)
        has_topic = bool(req.mode3_topic and str(req.mode3_topic).strip())
        if not has_images and not has_topic:
            raise HTTPException(
                400,
                "Mode 3: загрузите 2 фото (дом ДО и ПОСЛЕ) или опишите дом текстом для автогенерации",
            )
    elif req.mode == 4:
        if not getattr(req, "mode4_quote", "") or not getattr(req, "mode4_person_name", "") or not getattr(
            req, "mode4_photo_path", ""
        ):
            raise HTTPException(
                400,
                "Mode 4: введите имя личности, цитату и загрузите фото",
            )
    elif req.mode == 5:
        if not req.topic or not req.topic.strip():
            raise HTTPException(400, "Mode 5: введите тему для длинного видео")
    elif req.mode in (6, 7, 8, 9, 10):
        pass
    elif not req.topic and not req.auto_topic:
        raise HTTPException(400, "Provide 'topic' or set 'auto_topic: true'")


def _ensure_regenerate_assets_exist(req: StartRequest) -> None:
    """Файлы из сохранённого запроса должны существовать на диске."""
    if req.mode == 4 and req.mode4_photo_path and not Path(req.mode4_photo_path).is_file():
        raise HTTPException(
            400,
            "Файл фото для цитаты не найден. Создайте видео заново с главной страницы.",
        )
    if req.mode == 3:
        if req.mode3_start_image_path and not Path(req.mode3_start_image_path).is_file():
            raise HTTPException(400, "Фото «дом ДО» не найдено — перегенерация невозможна.")
        if req.mode3_end_image_path and not Path(req.mode3_end_image_path).is_file():
            raise HTTPException(400, "Фото «дом ПОСЛЕ» не найдено — перегенерация невозможна.")
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


@app.post("/api/pipeline/start")
async def start_pipeline(req: StartRequest):
    _validate_start_request(req)

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
    return {"session_id": session_id}


@app.get("/api/pipeline/{session_id}/stream")
async def stream_logs(session_id: str):
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    async def event_gen():
        q: asyncio.Queue = session["queue"]
        # Replay buffered messages if any
        while True:
            try:
                entry = await asyncio.wait_for(q.get(), timeout=20)
                yield f"data: {json.dumps(entry)}\n\n"
                if entry.get("type") in ("done", "error"):
                    return
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/pipeline/{session_id}/status")
async def get_status(session_id: str):
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return {
        "session_id": session_id,
        "status": session["status"],
        "result": session.get("result"),
        "error": session.get("error"),
        "topic": session.get("topic", ""),
        "mode": session.get("mode", 1),
    }


@app.get("/api/pipeline/sessions")
async def list_pipeline_sessions():
    """Список активных сессий (running, paused) — для показа в UI."""
    active = [
        {
            "session_id": sid,
            "status": s["status"],
            "topic": s.get("topic", "") or f"#{sid[-8:]}",
            "mode": s.get("mode", 1),
            "started_at": s.get("started_at"),
        }
        for sid, s in _sessions.items()
        if s["status"] in ("running", "paused")
    ]
    logger.info(f"[API /pipeline/sessions] returning {len(active)} active")
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
            for mp4 in session_dir.glob("*.mp4"):
                sid = session_dir.name
                key = (sid, mp4.name)
                if key in seen:
                    continue
                seen.add(key)
                # Для video_ru.mp4 / video_en.mp4 — заголовок на языке ролика; миниатюра с того же файла
                stem = mp4.stem
                base = topics_by_session.get(sid) or f"Цитата #{sid[-8:]}"
                cap_en = quote_caption_en_by_session.get(sid)
                if stem == "video_ru":
                    title = base if base else f"Видео #{sid[-8:]}"
                    if not title.endswith("(RU)") and " (RU)" not in title:
                        title = f"{title} (RU)"
                elif stem == "video_en":
                    title = (cap_en or f"{base} (EN)").strip()
                else:
                    title = topics_by_session.get(sid) or f"Видео #{sid[-8:]}"
                stat = mp4.stat()
                cap_ru = topics_by_session.get(sid)
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


@app.delete("/api/videos/{session_id}")
async def delete_video(session_id: str):
    """Удалить видео с диска и из истории."""
    import shutil

    removed = False
    videos_dir = settings.videos_dir

    # Удалить плоский файл
    flat_path = videos_dir / f"video_{session_id}.mp4"
    if flat_path.exists():
        flat_path.unlink()
        removed = True

    # Удалить legacy папку session_id (видео + клипы)
    session_dir = videos_dir / session_id
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

    _validate_start_request(req)
    _ensure_regenerate_assets_exist(req)

    videos_dir = settings.videos_dir
    flat_path = videos_dir / f"video_{session_id}.mp4"
    if flat_path.exists():
        flat_path.unlink()
    session_dir = videos_dir / session_id
    if session_dir.exists():
        shutil.rmtree(session_dir)

    remove_topic(session_id)
    _sessions.pop(session_id, None)

    new_sid = str(int(time.time() * 1000))
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
    """Resolve path: flat video_{sid}.mp4 или legacy session_id/filename."""
    videos_dir = settings.videos_dir
    flat_path = videos_dir / f"video_{session_id}.mp4"
    if flat_path.exists():
        return flat_path
    legacy_path = videos_dir / session_id / filename
    if legacy_path.exists():
        return legacy_path
    return None


def _pick_legacy_thumbnail_path(legacy_dir: Path) -> Path | None:
    """Предпочесть финальные video_ru / video_en, не клип clip_*.mp4."""
    mp4s = sorted(legacy_dir.glob("*.mp4"))
    if not mp4s:
        return None
    for name in ("video_ru.mp4", "video_en.mp4"):
        p = legacy_dir / name
        if p.exists():
            return p
    # без финалов — любой файл кроме очевидных клипов (если есть другой)
    non_clip = [p for p in mp4s if not p.name.lower().startswith("clip_")]
    return non_clip[0] if non_clip else mp4s[0]


@app.get("/api/video/{session_id}/thumbnail")
async def serve_video_thumbnail(
    session_id: str,
    video_file: str | None = Query(None, alias="file"),
):
    """Первый кадр видео как JPEG (аватарка). Параметр file= — имя mp4 в папке сессии (для RU/EN)."""
    videos_dir = settings.videos_dir
    flat_path = videos_dir / f"video_{session_id}.mp4"
    legacy = videos_dir / session_id
    path: Path | None = None
    if video_file and legacy.is_dir():
        safe_name = Path(video_file).name
        if safe_name.endswith(".mp4"):
            candidate = (legacy / safe_name).resolve()
            try:
                candidate.relative_to(legacy.resolve())
            except ValueError:
                raise HTTPException(400, "Invalid file path") from None
            if candidate.is_file():
                path = candidate
    if path is None and flat_path.exists():
        path = flat_path
    if path is None and legacy.is_dir():
        path = _pick_legacy_thumbnail_path(legacy)
    if not path or not path.exists():
        raise HTTPException(404, "Video not found")
    try:
        from moviepy import VideoFileClip
        vc = VideoFileClip(str(path))
        frame = vc.get_frame(0)
        vc.close()
        import io
        from PIL import Image
        img = Image.fromarray(frame)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        buf.seek(0)
        return Response(content=buf.getvalue(), media_type="image/jpeg")
    except Exception as e:
        logger.warning(f"Thumbnail failed: {e}")
        raise HTTPException(500, "Could not generate thumbnail")


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
        uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
