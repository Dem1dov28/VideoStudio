"""
TikTok «Казино» API: /api/social/* + вспомогательные эндпоинты для UI.
Порт логики из CAS (без jobs/history CAS).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from loguru import logger
from pydantic import BaseModel

from agents.publisher.youtube_direct import get_valid_credentials, upload_video_file
from agents.social.banner_overlay import ffmpeg_available, is_valid_corner, overlay_banner
from agents.social.social_bulk import (
    channel_workdir,
    normalize_profile_url,
    run_social_channel_download,
)
from agents.social.social_store import SocialChannelRecord, SocialChannelStore, SocialVideoRecord
from config import settings

# ── Defaults (как CAS / youtubeUploadDefaults) ───────────────────────────────
DEFAULT_YOUTUBE_TITLE = "🤑ССЫЛКА В ШАПКЕ ПРОФИЛЯ🤑"
DEFAULT_YOUTUBE_DESCRIPTION = """🎰 Очередная нарезка казино – смотри до конца, будет жарко!

💎 Все ссылки на бонусы и лучшие казино – в шапке профиля (клик на аватарку).

📢 Подпишись, чтобы не пропустить новые моменты: #нарезкиказино #игравпрофиле #джекпот #Shorts"""
DEFAULT_YOUTUBE_KEYWORDS = (
    "нарезки казино, крупные выигрыши, слот 777, джекпот срыв, игра в профиле, эмоции игроков, лучшие моменты казино."
)
DEFAULT_YOUTUBE_TAGS = (
    "Shorts, нарезки казино, крупные выигрыши, слот 777, джекпот, казино онлайн, casino highlights, big win, slot machine, jackpot"
)
DEFAULT_YOUTUBE_PRIVACY = "public"
DEFAULT_YOUTUBE_CATEGORY_ID = "22"
YOUTUBE_TAG_MAX_COUNT = 15

SOCIAL_YOUTUBE_BRANDING_FILENAME = "0408.mp4"
_SOCIAL_BRANDING_MARGIN = 10
_SOCIAL_BRANDING_WIDTH = 200

_workers = max(1, int(os.environ.get("VS_SOCIAL_WORKERS", "2")))
_social_executor = ThreadPoolExecutor(max_workers=_workers, thread_name_prefix="vs_social")
_social_uploads_lock = threading.Lock()
_social_uploads_inflight: set[str] = set()
_social_stop_lock = threading.Lock()
_social_stop_events: dict[str, threading.Event] = {}


def _data_dir() -> Path:
    p = settings.project_root / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _social_store() -> SocialChannelStore:
    return SocialChannelStore(_data_dir() / "social_channels.json")


def _default_social_max_videos() -> int | None:
    raw = os.environ.get("VS_SOCIAL_MAX_VIDEOS", "").strip()
    if not raw:
        return None
    try:
        n = int(raw)
        return max(1, min(n, 100_000))
    except ValueError:
        return None


def _merge_youtube_tags(*comma_parts: str, limit: int | None = None) -> list[str]:
    cap = YOUTUBE_TAG_MAX_COUNT if limit is None else max(1, min(int(limit), 500))
    seen: set[str] = set()
    out: list[str] = []
    for part in comma_parts:
        for raw in part.split(","):
            t = raw.strip()
            if not t:
                continue
            key = t.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(t)
            if len(out) >= cap:
                return out
    return out


def _ytdlp_version() -> str:
    try:
        from yt_dlp.version import __version__ as v

        return v
    except Exception:
        try:
            r = subprocess.run(
                ["yt-dlp", "--version"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            return (r.stdout or "").strip() or "unknown"
        except Exception:
            return "unknown"


def _ensure_under_data(path: Path) -> Path:
    root = _data_dir().resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as e:
        raise HTTPException(status_code=403, detail="invalid media path") from e
    return resolved


def _is_upload_limit_exceeded(exc: BaseException) -> bool:
    s = str(exc).lower()
    return "uploadlimitexceeded" in s.replace(" ", "") or "exceeded the number of videos" in s


# ── Pydantic (как CAS) ───────────────────────────────────────────────────────


class SocialVideoPublic(BaseModel):
    key: str
    extractor: str
    video_id: str
    title: str
    page_url: str
    rel_path: str | None = None
    status: str
    downloaded_at: str | None = None
    error: str | None = None
    file_ready: bool = False
    youtube_id: str | None = None


class SocialChannelPublic(BaseModel):
    id: str
    profile_url: str
    normalized_url: str
    platform: str
    created_at: str
    updated_at: str
    status: str
    step: str | None = None
    detail: str | None = None
    error: str | None = None
    stats_completed: int
    stats_failed: int
    tiktok_headers: bool = False
    max_videos: int | None = None
    cookies_browser_set: bool = False
    cookies_browser: str | None = None
    cookies_file: str | None = None
    videos: list[SocialVideoPublic]


class SocialChannelSummary(BaseModel):
    id: str
    profile_url: str
    normalized_url: str
    platform: str
    created_at: str
    updated_at: str
    status: str
    step: str | None = None
    detail: str | None = None
    error: str | None = None
    stats_completed: int
    stats_failed: int
    video_count: int
    tiktok_headers: bool = False
    max_videos: int | None = None
    cookies_browser_set: bool = False
    cookies_file_set: bool = False


class SocialChannelCreateBody(BaseModel):
    profile_url: str
    cookies_browser: str = ""
    cookies_file: str = ""
    tiktok_headers: bool = False
    max_videos: int | None = None


class SocialChannelPatchBody(BaseModel):
    cookies_browser: str = ""
    cookies_file: str = ""


def _social_video_public(data_root: Path, v: SocialVideoRecord) -> SocialVideoPublic:
    ready = False
    if v.rel_path:
        p = (data_root / v.rel_path).resolve()
        ready = p.is_file()
    return SocialVideoPublic(
        key=v.key,
        extractor=v.extractor,
        video_id=v.video_id,
        title=v.title,
        page_url=v.page_url,
        rel_path=v.rel_path,
        status=v.status,
        downloaded_at=v.downloaded_at,
        error=v.error,
        file_ready=ready,
        youtube_id=v.youtube_id,
    )


def _social_channel_public(rec: SocialChannelRecord, data_root: Path) -> SocialChannelPublic:
    return SocialChannelPublic(
        id=rec.id,
        profile_url=rec.profile_url,
        normalized_url=rec.normalized_url,
        platform=rec.platform,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
        status=rec.status,
        step=rec.step,
        detail=rec.detail,
        error=rec.error,
        stats_completed=rec.stats_completed,
        stats_failed=rec.stats_failed,
        tiktok_headers=rec.tiktok_headers,
        max_videos=rec.max_videos,
        cookies_browser_set=bool((rec.cookies_browser or "").strip()),
        cookies_browser=((rec.cookies_browser or "").strip() or None),
        cookies_file=((rec.cookies_file or "").strip() or None),
        videos=[_social_video_public(data_root, x) for x in rec.videos],
    )


def _social_channel_summary(rec: SocialChannelRecord) -> SocialChannelSummary:
    return SocialChannelSummary(
        id=rec.id,
        profile_url=rec.profile_url,
        normalized_url=rec.normalized_url,
        platform=rec.platform,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
        status=rec.status,
        step=rec.step,
        detail=rec.detail,
        error=rec.error,
        stats_completed=rec.stats_completed,
        stats_failed=rec.stats_failed,
        video_count=len(rec.videos),
        tiktok_headers=rec.tiktok_headers,
        max_videos=rec.max_videos,
        cookies_browser_set=bool((rec.cookies_browser or "").strip()),
        cookies_file_set=bool((rec.cookies_file or "").strip()),
    )


def _resolve_social_media_path(channel_id: str, video_key: str) -> Path:
    st = _social_store()
    rec = st.get(channel_id)
    if not rec:
        raise HTTPException(status_code=404, detail="channel not found")
    for v in rec.videos:
        if v.key == video_key:
            if not v.rel_path:
                raise HTTPException(status_code=404, detail="file not yet available")
            p = (_data_dir() / v.rel_path).resolve()
            return _ensure_under_data(p)
    raise HTTPException(status_code=404, detail="video not found")


def _upload_social_video_sync(
    channel_id: str,
    video_key: str,
    *,
    channel_profile: str,
    branding_corner: str,
    title: str = "",
    description: str = "",
    keywords: str = "",
    tags: str = "",
    privacy: str = "",
    category_id: str = "",
) -> tuple[str, str, str]:
    st = _social_store()
    ch = st.get(channel_id)
    if not ch:
        raise ValueError("channel not found")
    vmatch: SocialVideoRecord | None = None
    for v in ch.videos:
        if v.key == video_key:
            vmatch = v
            break
    if not vmatch:
        raise ValueError("video not found")
    if vmatch.youtube_id:
        raise ValueError("already uploaded")
    if vmatch.status != "ok":
        raise ValueError("video not ready for upload")
    path = _resolve_social_media_path(channel_id, video_key)
    brand = settings.project_root / SOCIAL_YOUTUBE_BRANDING_FILENAME
    upload_path = path
    tmp_overlay: Path | None = None
    if brand.is_file():
        if not is_valid_corner(branding_corner):
            raise ValueError(f"invalid branding_corner: {branding_corner!r}")
        if not ffmpeg_available():
            raise RuntimeError("ffmpeg не найден — нужен для монтажа 0408.mp4 перед заливкой")
        fd, tmp_name = tempfile.mkstemp(suffix=".mp4")
        os.close(fd)
        tmp_overlay = Path(tmp_name)
        try:
            overlay_banner(
                path,
                brand,
                tmp_overlay,
                corner=branding_corner,
                margin=_SOCIAL_BRANDING_MARGIN,
                banner_width=_SOCIAL_BRANDING_WIDTH,
                banner_is_video=True,
            )
        except Exception:
            if tmp_overlay.is_file():
                tmp_overlay.unlink(missing_ok=True)
            raise
        upload_path = tmp_overlay

    from agents.publisher.youtube_multi import get_youtube_profile

    yp = get_youtube_profile(settings, channel_profile)
    token_path = yp.token_path
    cs = yp.client_secrets_path
    if not cs.is_file():
        raise ValueError(f"OAuth client JSON для профиля «{yp.id}» не найден: {cs}")

    creds = get_valid_credentials(cs, token_path)
    if not creds:
        raise ValueError(f"Нет валидного токена для профиля «{channel_profile}»")

    title_f = (title or "").strip() or DEFAULT_YOUTUBE_TITLE
    description_f = (description or "").strip() or DEFAULT_YOUTUBE_DESCRIPTION
    keywords_f = (keywords or "").strip() or DEFAULT_YOUTUBE_KEYWORDS
    tags_f = (tags or "").strip() or DEFAULT_YOUTUBE_TAGS
    privacy_f = (privacy or "").strip() or DEFAULT_YOUTUBE_PRIVACY
    category_f = (category_id or "").strip() or DEFAULT_YOUTUBE_CATEGORY_ID
    if privacy_f not in ("private", "unlisted", "public"):
        raise ValueError("invalid privacy")
    tag_list = _merge_youtube_tags(keywords_f, tags_f)

    try:
        resp = upload_video_file(
            creds,
            upload_path,
            title=title_f,
            description=description_f,
            tags=tag_list or None,
            privacy_status=privacy_f,
            category_id=category_f,
        )
        yt_id = str((resp or {}).get("id") or "")
        if not yt_id:
            raise ValueError("upload returned no video id")
        raw_snip = (resp or {}).get("snippet") or {}
        ch_id = str(raw_snip.get("channelId") or "") if isinstance(raw_snip, dict) else ""
        if not st.update_video_youtube(channel_id, video_key, yt_id):
            raise ValueError("failed to persist youtube id")
        return yt_id, ch_id, title_f
    finally:
        if tmp_overlay is not None and tmp_overlay.is_file():
            tmp_overlay.unlink(missing_ok=True)


def run_social_youtube_upload_with_lock(
    channel_id: str,
    video_key: str,
    *,
    channel_profile: str,
    branding_corner: str,
    title: str = "",
    description: str = "",
    keywords: str = "",
    tags: str = "",
    privacy: str = "",
    category_id: str = "",
) -> tuple[str, str, str]:
    """
    Заливка соц-ролика (оверлей 0408 + youtube_direct.upload_video_file).
    Один inflight на пару channel_id+video_key. Возвращает (video_id, youtube_channel_id, title_used).
    """
    corner_f = (branding_corner or "tr").strip()
    if not is_valid_corner(corner_f):
        raise ValueError("invalid branding_corner")
    social_sid = f"{channel_id}\x1f{video_key}"
    with _social_uploads_lock:
        if social_sid in _social_uploads_inflight:
            raise ValueError("upload already in progress for this social video")
        _social_uploads_inflight.add(social_sid)
    try:
        return _upload_social_video_sync(
            channel_id,
            video_key,
            channel_profile=channel_profile,
            branding_corner=corner_f,
            title=title,
            description=description,
            keywords=keywords,
            tags=tags,
            privacy=privacy,
            category_id=category_id,
        )
    finally:
        with _social_uploads_lock:
            _social_uploads_inflight.discard(social_sid)


def register_casino_routes(app: FastAPI) -> None:
    @app.get("/api/social/channels", response_model=list[SocialChannelSummary])
    def social_list() -> list[SocialChannelSummary]:
        st = _social_store()
        return [_social_channel_summary(c) for c in st.list_channels()]

    @app.get("/api/social/channels/{channel_id}", response_model=SocialChannelPublic)
    def social_get(channel_id: str) -> SocialChannelPublic:
        st = _social_store()
        c = st.get(channel_id)
        if not c:
            raise HTTPException(status_code=404, detail="not found")
        return _social_channel_public(c, _data_dir())

    @app.patch("/api/social/channels/{channel_id}", response_model=SocialChannelPublic)
    def social_patch(channel_id: str, body: SocialChannelPatchBody) -> SocialChannelPublic:
        st = _social_store()
        c = st.get(channel_id)
        if not c:
            raise HTTPException(status_code=404, detail="not found")
        if c.status in ("queued", "running"):
            raise HTTPException(status_code=409, detail="stop download before editing")

        def _patch(ch: SocialChannelRecord) -> None:
            ch.cookies_browser = body.cookies_browser.strip() or None
            ch.cookies_file = body.cookies_file.strip() or None

        st.update_channel(channel_id, mutator=_patch)
        out = st.get(channel_id)
        if not out:
            raise HTTPException(status_code=500, detail="social channel lost after patch")
        return _social_channel_public(out, _data_dir())

    @app.post("/api/social/channels", response_model=SocialChannelPublic)
    async def social_create(body: SocialChannelCreateBody) -> SocialChannelPublic:
        try:
            norm, plat = normalize_profile_url(body.profile_url)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        if body.max_videos is not None:
            max_v = max(1, min(int(body.max_videos), 100_000))
        else:
            max_v = _default_social_max_videos()

        cid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        cookies_stored = (body.cookies_browser.strip() or None)
        cookies_file_stored = (body.cookies_file.strip() or None)
        rec = SocialChannelRecord(
            id=cid,
            profile_url=body.profile_url.strip(),
            normalized_url=norm,
            platform=plat,  # type: ignore[arg-type]
            created_at=now,
            updated_at=now,
            status="queued",
            step="queue",
            detail="В очереди на загрузку",
            error=None,
            stats_completed=0,
            stats_failed=0,
            videos=[],
            cookies_browser=cookies_stored,
            cookies_file=cookies_file_stored,
            tiktok_headers=bool(body.tiktok_headers),
            max_videos=max_v,
        )
        store = _social_store()
        store.upsert_channel(rec)
        ev = threading.Event()
        with _social_stop_lock:
            _social_stop_events[cid] = ev

        def _run() -> None:
            try:
                run_social_channel_download(
                    store=_social_store(),
                    channel_id=cid,
                    data_root=_data_dir(),
                    cookies_browser=cookies_stored,
                    cookies_file=cookies_file_stored,
                    tiktok_headers=bool(body.tiktok_headers),
                    max_videos=max_v,
                    stop_event=ev,
                    on_step=None,
                )
            finally:
                with _social_stop_lock:
                    _social_stop_events.pop(cid, None)

        loop = asyncio.get_running_loop()
        loop.run_in_executor(_social_executor, _run)
        out = store.get(cid)
        if not out:
            raise HTTPException(status_code=500, detail="social channel lost after create")
        return _social_channel_public(out, _data_dir())

    @app.post("/api/social/channels/{channel_id}/cancel")
    def social_cancel(channel_id: str) -> dict[str, str]:
        st = _social_store()
        c = st.get(channel_id)
        if not c:
            raise HTTPException(status_code=404, detail="not found")
        if c.status not in ("queued", "running"):
            raise HTTPException(status_code=400, detail="not active")

        with _social_stop_lock:
            ev = _social_stop_events.get(channel_id)
            if ev is not None:
                ev.set()
        return {"status": "ok"}

    @app.post("/api/social/channels/{channel_id}/start", response_model=SocialChannelPublic)
    async def social_start(channel_id: str) -> SocialChannelPublic:
        st = _social_store()
        c = st.get(channel_id)
        if not c:
            raise HTTPException(status_code=404, detail="not found")
        if c.status in ("queued", "running"):
            raise HTTPException(status_code=409, detail="already active")
        with _social_stop_lock:
            if channel_id in _social_stop_events:
                raise HTTPException(status_code=409, detail="internal: stop event exists")

        def _patch(ch: SocialChannelRecord) -> None:
            ch.status = "queued"
            ch.step = "queue"
            ch.detail = "В очереди на загрузку"
            ch.error = None

        st.update_channel(channel_id, mutator=_patch)
        ev = threading.Event()
        with _social_stop_lock:
            _social_stop_events[channel_id] = ev
        cookies_stored = ((c.cookies_browser or "").strip() or None)
        cookies_file_stored = ((c.cookies_file or "").strip() or None)
        tiktok_h = bool(c.tiktok_headers)
        max_v = c.max_videos

        def _run() -> None:
            try:
                run_social_channel_download(
                    store=_social_store(),
                    channel_id=channel_id,
                    data_root=_data_dir(),
                    cookies_browser=cookies_stored,
                    cookies_file=cookies_file_stored,
                    tiktok_headers=tiktok_h,
                    max_videos=max_v,
                    stop_event=ev,
                    on_step=None,
                )
            finally:
                with _social_stop_lock:
                    _social_stop_events.pop(channel_id, None)

        loop = asyncio.get_running_loop()
        loop.run_in_executor(_social_executor, _run)
        out = st.get(channel_id)
        if not out:
            raise HTTPException(status_code=500, detail="social channel lost")
        return _social_channel_public(out, _data_dir())

    @app.delete("/api/social/channels/{channel_id}")
    def social_delete(channel_id: str, wipe: bool = Query(False)) -> dict[str, bool]:
        st = _social_store()
        c = st.get(channel_id)
        if not c:
            raise HTTPException(status_code=404, detail="not found")
        if c.status in ("queued", "running"):
            raise HTTPException(status_code=409, detail="cancel download first")
        if wipe:
            wd = channel_workdir(_data_dir(), channel_id)
            if wd.is_dir():
                shutil.rmtree(wd, ignore_errors=True)
        if not st.delete_channel(channel_id):
            raise HTTPException(status_code=404, detail="not found")
        return {"deleted": True}

    @app.head("/api/social/channels/{channel_id}/videos/{video_key}/file")
    def social_video_head(channel_id: str, video_key: str) -> Response:
        path = _resolve_social_media_path(channel_id, video_key)
        st = path.stat()
        return Response(
            status_code=200,
            media_type="video/mp4",
            headers={
                "content-length": str(st.st_size),
                "accept-ranges": "bytes",
                "content-disposition": f'inline; filename="social_{video_key[:32]}.mp4"',
            },
        )

    @app.get("/api/social/channels/{channel_id}/videos/{video_key}/file")
    def social_video_get(channel_id: str, video_key: str) -> FileResponse:
        path = _resolve_social_media_path(channel_id, video_key)
        return FileResponse(
            path,
            media_type="video/mp4",
            filename=f"social_{video_key[:48]}.mp4",
            content_disposition_type="inline",
        )

    @app.get("/api/casino/health")
    def casino_health() -> dict[str, Any]:
        return casino_health_payload()

    @app.get("/api/youtube/channels")
    async def youtube_channels_for_profile(profile: str = Query("primary")) -> list[dict[str, str]]:
        """Список каналов YouTube для выбранного токена (как «Каналы по API» в CAS)."""
        from agents.publisher.youtube_multi import get_youtube_profile

        key = (profile or "primary").strip().lower()
        try:
            yp = get_youtube_profile(settings, key)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        token_path = yp.token_path
        cs = yp.client_secrets_path
        if not cs.is_file():
            raise HTTPException(400, f"OAuth client JSON не найден для «{key}»: {cs}")
        creds = await asyncio.to_thread(get_valid_credentials, cs, token_path)
        if not creds:
            raise HTTPException(401, f"Нет токена для профиля «{key}»")
        from agents.publisher.youtube_direct import list_managed_channels_preview

        rows = await asyncio.to_thread(list_managed_channels_preview, creds)
        return [{"id": r["id"], "title": r.get("title") or "", "custom_url": r.get("custom_url") or ""} for r in rows]


def casino_health_payload() -> dict[str, Any]:
    """Собирается для GET /api/casino/health."""
    from agents.publisher.youtube_multi import try_load_youtube_profiles, uses_youtube_registry

    root = settings.project_root
    brand = root / SOCIAL_YOUTUBE_BRANDING_FILENAME
    profs = try_load_youtube_profiles(settings)

    def _token_ok_for_profile(path: Path, cs_path: Path) -> bool:
        if not path.is_file() or not cs_path.is_file():
            return False
        try:
            c = get_valid_credentials(cs_path, path)
            return bool(c and (c.valid or getattr(c, "refresh_token", None)))
        except Exception:
            return False

    accounts: list[dict[str, Any]] = []
    if profs:
        for p in profs:
            accounts.append(
                {
                    "id": p.id,
                    "label": p.label,
                    "gcp_project": p.gcp_project or "",
                    "token_ok": _token_ok_for_profile(p.token_path, p.client_secrets_path),
                    "upload_channel_id": "",
                    "upload_channel_title": "",
                    "oauth_channel_count": 0,
                    "multi_channel_google": False,
                }
            )
    cs = settings.youtube_client_secrets_file
    if profs:
        cs_ok = any(p.client_secrets_path.is_file() for p in profs)
    else:
        cs_ok = bool(cs and cs.is_file())

    return {
        "ffmpeg": ffmpeg_available(),
        "ytdlp_version": _ytdlp_version(),
        "client_secret_path": str(cs) if cs else "",
        "client_secret_exists": cs_ok,
        "youtube_uses_registry": uses_youtube_registry(settings),
        "social_youtube_branding_exists": brand.is_file(),
        "youtube_accounts": accounts,
        "youtube_token_duplicate_groups": [],
        "youtube_upload_channel_duplicate_groups": [],
    }
