"""
FastAPI web server for AI Content Factory.

Run:  uvicorn server:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel

from config import settings

# ── Session store ─────────────────────────────────────────────────────────────
_sessions: dict[str, dict] = {}


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

async def _run_pipeline_task(
    session_id: str,
    req: "StartRequest",
    queue: asyncio.Queue,
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
        )

        session["status"] = "done"
        session["result"] = {
            "video_path": result.get("video_path"),
            "topic": result.get("topic"),
            "trend": result.get("trend"),
            "session_id": session_id,
        }
        await queue.put({"type": "done", **session["result"]})

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
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
    if not req.topic and not req.auto_topic:
        raise HTTPException(400, "Provide 'topic' or set 'auto_topic: true'")

    session_id = str(int(time.time() * 1000))
    queue: asyncio.Queue = asyncio.Queue()

    _sessions[session_id] = {
        "status": "running",
        "queue": queue,
        "result": None,
        "error": None,
        "started_at": time.time(),
    }

    asyncio.create_task(_run_pipeline_task(session_id, req, queue))
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
    }


@app.get("/api/videos")
async def list_videos():
    videos_dir = settings.videos_dir
    videos = []
    if videos_dir.exists():
        for session_dir in sorted(
            videos_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True
        ):
            for mp4 in session_dir.glob("*.mp4"):
                stat = mp4.stat()
                videos.append({
                    "session_id": session_dir.name,
                    "filename": mp4.name,
                    "size_mb": round(stat.st_size / 1024 / 1024, 1),
                    "created_at": stat.st_mtime,
                    "url": f"/api/video/{session_dir.name}/{mp4.name}",
                })
    return {"videos": videos}


@app.get("/api/video/{session_id}/{filename}")
async def serve_video(session_id: str, filename: str):
    path = settings.videos_dir / session_id / filename
    if not path.exists():
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
    """Return list of already-generated topics."""
    from agents.topics_history import get_used_topics
    return {"topics": get_used_topics()}


@app.delete("/api/topics/history")
async def clear_topics_history():
    """Clear the entire topics history."""
    from agents.topics_history import _HISTORY_FILE
    if _HISTORY_FILE.exists():
        _HISTORY_FILE.unlink()
    return {"cleared": True}


@app.delete("/api/topics/history/{session_id}")
async def remove_topic_from_history(session_id: str):
    """Remove a single topic entry by session_id."""
    from agents.topics_history import remove_topic
    found = remove_topic(session_id)
    if not found:
        raise HTTPException(404, f"Session {session_id!r} not found in history")
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

    _sessions[new_sid] = {
        "status": "running",
        "queue": queue,
        "result": None,
        "error": None,
        "started_at": time.time(),
    }

    asyncio.create_task(_run_pipeline_task(new_sid, req, queue))
    return {"session_id": new_sid, "topic": topic}


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0"}


# ── Serve built React frontend ─────────────────────────────────────────────────

_dist = Path(__file__).parent / "frontend" / "dist"

if _dist.exists():
    app.mount("/assets", StaticFiles(directory=str(_dist / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        return FileResponse(str(_dist / "index.html"))


if __name__ == "__main__":
    import uvicorn
    # reload=False prevents file-change restarts from killing running pipelines
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
