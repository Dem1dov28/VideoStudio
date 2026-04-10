"""Bulk download of TikTok profiles via yt-dlp (playlist / user extractor)."""

from __future__ import annotations

import logging
import os
import re
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, cast
from urllib.parse import urlparse, urlunparse

from agents.social.social_store import (
    SocialChannelRecord,
    SocialChannelStore,
    SocialChannelStatus,
    SocialVideoRecord,
    video_key_safe,
)
from agents.social.yt_dlp_opts import build_ydl_opts

logger = logging.getLogger(__name__)

StepCallback = Callable[[str, str | None], None]


def _ytdlp_quiet() -> bool:
    raw = os.environ.get("VS_SOCIAL_YTDLP_QUIET") or os.environ.get("CAS_SOCIAL_YTDLP_QUIET", "1")
    return raw.lower() in ("1", "true", "yes")


def normalize_profile_url(url: str) -> tuple[str, str]:
    """
    Return (canonical_url_without_query_fragment, platform).
    Только TikTok; platform всегда 'tiktok' при успехе.
    """
    raw = url.strip()
    if not raw:
        raise ValueError("Пустой URL")
    if "://" not in raw:
        raw = "https://" + raw
    p = urlparse(raw)
    scheme = p.scheme if p.scheme in ("http", "https") else "https"
    netloc = (p.netloc or "").strip().lower()
    if not netloc:
        raise ValueError("Некорректный URL (нет хоста)")

    path = p.path or "/"
    path = re.sub(r"/{2,}", "/", path).rstrip("/")
    if not path:
        path = "/"

    if "tiktok.com" in netloc:
        netloc = "www.tiktok.com"
        clean = urlunparse((scheme, netloc, path, "", "", ""))
        return clean, "tiktok"

    raise ValueError(
        "Поддерживаются только URL профиля TikTok, например https://www.tiktok.com/@username",
    )


def channel_workdir(data_root: Path, channel_id: str) -> Path:
    return (data_root / "social" / channel_id).resolve()


def _append_log(workdir: Path, line: str) -> None:
    try:
        workdir.mkdir(parents=True, exist_ok=True)
        (workdir / "run.log").open("a", encoding="utf-8").write(line + "\n")
    except Exception as e:
        logger.warning("social run.log write failed: %s", e)


def _rel_under_data(data_root: Path, abs_path: Path) -> str:
    root = data_root.resolve()
    resolved = abs_path.resolve()
    rel = resolved.relative_to(root)
    return rel.as_posix()


def _yt_cookie_tuple(cookies_browser: str | None) -> tuple[str, ...] | None:
    t = (cookies_browser or "").strip()
    if not t:
        return None
    return (t,)


def _resolve_netscape_cookiefile(path: str | None) -> str | None:
    raw = (path or "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    try:
        p = p.resolve(strict=False)
    except OSError:
        return None
    if not p.is_file():
        return None
    return str(p)


def run_social_channel_download(
    *,
    store: SocialChannelStore,
    channel_id: str,
    data_root: Path,
    cookies_browser: str | None,
    cookies_file: str | None,
    tiktok_headers: bool,
    max_videos: int | None,
    stop_event: threading.Event,
    on_step: StepCallback | None = None,
) -> None:
    """
    Synchronous long-running task: download full profile / tab into data/social/<id>/media/.
    Persists progress into store. Honor stop_event (raises KeyboardInterrupt into yt-dlp).
    """
    from yt_dlp import YoutubeDL

    rec = store.get(channel_id)
    if not rec:
        logger.error("social channel %s missing in store", channel_id)
        return

    if stop_event.is_set():

        def _early_cancel(ch: SocialChannelRecord) -> None:
            ch.status = "cancelled"
            ch.step = None
            ch.detail = "Остановлено до старта"
            ch.error = None

        store.update_channel(channel_id, mutator=_early_cancel)
        return

    work = channel_workdir(data_root, channel_id)
    media = work / "media"
    archive = work / "archive.txt"

    def step(phase: str, detail: str | None) -> None:
        if on_step:
            on_step(phase, detail)

        def _patch(ch: SocialChannelRecord) -> None:
            ch.step = phase
            ch.detail = detail

        store.update_channel(channel_id, mutator=_patch)
        if detail:
            _append_log(work, f"[{phase}] {detail}")

    def mark_running() -> None:
        def _patch(ch: SocialChannelRecord) -> None:
            ch.status = "running"
            ch.error = None
            ch.step = "starting"
            ch.detail = "Инициализация yt-dlp"

        store.update_channel(channel_id, mutator=_patch)

    if stop_event.is_set():

        def _late_cancel(ch: SocialChannelRecord) -> None:
            ch.status = "cancelled"
            ch.step = None
            ch.detail = "Остановлено до mark_running"
            ch.error = None

        store.update_channel(channel_id, mutator=_late_cancel)
        return

    mark_running()
    _append_log(work, f"--- run start normalized={rec.normalized_url} max_videos={max_videos}")

    cookiefile_arg = _resolve_netscape_cookiefile(cookies_file)
    if (cookies_file or "").strip() and not cookiefile_arg:
        bad = Path((cookies_file or "").strip()).expanduser()

        def _bad_file(ch: SocialChannelRecord) -> None:
            ch.status = "error"
            ch.step = None
            ch.detail = None
            ch.error = f"Файл cookies не найден: {bad}"

        store.update_channel(channel_id, mutator=_bad_file)
        _append_log(work, f"abort: cookies file missing {bad}")
        return

    media.mkdir(parents=True, exist_ok=True)
    tmpl = str(media / "%(extractor)s_%(id)s.%(ext)s")

    extra_headers: dict[str, str] = {}
    if tiktok_headers or rec.platform == "tiktok":
        extra_headers["Referer"] = "https://www.tiktok.com/"

    opts = build_ydl_opts(
        media,
        cookiefile=cookiefile_arg,
        cookies_from_browser=None if cookiefile_arg else _yt_cookie_tuple(cookies_browser),
        quiet=_ytdlp_quiet(),
        extra_http_headers=extra_headers or None,
    )
    opts["outtmpl"] = {"default": tmpl}
    opts["download_archive"] = str(archive)
    opts["ignoreerrors"] = True
    opts["merge_output_format"] = "mp4"
    opts["retries"] = 10
    opts["fragment_retries"] = 10
    if max_videos is not None and max_videos > 0:
        opts["playlistend"] = max_videos

    saw_error_detail: str | None = None
    _last_progress_store_ts: float = 0.0

    def progress_hook(d: dict[str, Any]) -> None:
        nonlocal saw_error_detail, _last_progress_store_ts
        if stop_event.is_set():
            _append_log(work, "cancel requested → KeyboardInterrupt")
            raise KeyboardInterrupt("social download cancelled")

        st = d.get("status")
        if st == "downloading":
            name = d.get("filename") or d.get("tmpfilename") or "…"
            info = d.get("info_dict") or {}
            t = info.get("title") or name
            pct = d.get("_percent_str") or d.get("_speed_str")
            detail = f"{t}"
            if pct:
                detail = f"{t} — {pct}"
            now_m = time.monotonic()
            if now_m - _last_progress_store_ts >= 1.5:
                _last_progress_store_ts = now_m
                step("download", detail[:500])
            vid = info.get("id")
            ext = info.get("extractor") or info.get("ie_key") or "media"
            if vid:
                key = video_key_safe(str(ext), str(vid))

                def _mark_dl(ch: SocialChannelRecord) -> None:
                    for v in ch.videos:
                        if v.key == key:
                            v.status = "downloading"
                            return
                    ch.videos.append(
                        SocialVideoRecord(
                            key=key,
                            extractor=str(ext),
                            video_id=str(vid),
                            title=str(info.get("title") or ""),
                            page_url=str(info.get("webpage_url") or info.get("original_url") or rec.normalized_url),
                            rel_path=None,
                            status="downloading",
                            downloaded_at=None,
                            error=None,
                        )
                    )

                store.update_channel(channel_id, mutator=_mark_dl)

        elif st == "finished":
            fp = d.get("filename")
            info = d.get("info_dict") or {}
            extractor = str(info.get("extractor") or info.get("ie_key") or "media")
            vid = str(info.get("id") or "")
            if not vid and fp:
                vid = Path(fp).stem
            title = str(info.get("title") or Path(fp or "").stem or "video")
            page_url = str(info.get("webpage_url") or info.get("original_url") or rec.normalized_url)
            key = video_key_safe(extractor, vid)
            rel: str | None = None
            pth: Path | None = Path(fp) if fp else None
            if pth and pth.is_file():
                try:
                    rel = _rel_under_data(data_root, pth)
                except ValueError:
                    rel = None

            def _finish_ok(ch: SocialChannelRecord) -> None:
                now = datetime.now(timezone.utc).isoformat()
                for v in ch.videos:
                    if v.key == key:
                        was_ok = v.status == "ok"
                        was_failed = v.status == "failed"
                        v.rel_path = rel
                        v.status = "ok"
                        v.title = title
                        v.page_url = page_url
                        v.extractor = extractor
                        v.video_id = vid
                        v.downloaded_at = now
                        v.error = None
                        if was_failed:
                            ch.stats_failed = max(0, ch.stats_failed - 1)
                        if not was_ok:
                            ch.stats_completed += 1
                        return
                ch.videos.append(
                    SocialVideoRecord(
                        key=key,
                        extractor=extractor,
                        video_id=vid,
                        title=title,
                        page_url=page_url,
                        rel_path=rel,
                        status="ok",
                        downloaded_at=now,
                        error=None,
                    )
                )
                ch.stats_completed += 1

            store.update_channel(channel_id, mutator=_finish_ok)
            step("download", f"Готово: {title[:120]}")

        elif st == "error":
            err = d.get("error") or "unknown"
            saw_error_detail = str(err)[:2000]
            info = d.get("info_dict") or {}
            extractor = str(info.get("extractor") or info.get("ie_key") or "media")
            vid = str(info.get("id") or "")

            def _fail_one(ch: SocialChannelRecord) -> None:
                if not vid:
                    ch.stats_failed += 1
                    return
                key = video_key_safe(extractor, vid)

                for v in ch.videos:
                    if v.key == key:
                        if v.status != "failed":
                            ch.stats_failed += 1
                        v.status = "failed"
                        v.error = str(err)[:1000]
                        return
                ch.stats_failed += 1
                ch.videos.append(
                    SocialVideoRecord(
                        key=key,
                        extractor=extractor,
                        video_id=vid,
                        title=str(info.get("title") or ""),
                        page_url=str(info.get("webpage_url") or rec.normalized_url),
                        rel_path=None,
                        status="failed",
                        downloaded_at=None,
                        error=str(err)[:1000],
                    )
                )

            store.update_channel(channel_id, mutator=_fail_one)
            step("download", f"Ошибка ролика: {str(err)[:200]}")

    opts["progress_hooks"] = [progress_hook]

    final_status: str = "done"
    final_err: str | None = None

    try:
        with YoutubeDL(opts) as ydl:
            ydl.download([rec.normalized_url])
    except KeyboardInterrupt as e:
        if stop_event.is_set() or "cancel" in str(e).lower():
            final_status = "cancelled"
            final_err = None
        else:
            final_status = "error"
            final_err = str(e) or "KeyboardInterrupt"
        _append_log(work, f"interrupted: {final_status} {final_err or ''}")
    except Exception as e:
        final_status = "error"
        final_err = str(e) or type(e).__name__
        _append_log(work, f"exception: {final_err}\n{traceback.format_exc()}")
        logger.exception("social download failed channel=%s", channel_id)
    else:
        if stop_event.is_set():
            final_status = "cancelled"
        _append_log(work, f"--- run end status={final_status}")

    def _finalize(ch: SocialChannelRecord) -> None:
        ch.status = cast(SocialChannelStatus, final_status)
        ch.step = None
        if final_status == "done":
            ch.detail = f"Завершено. Успешно: {ch.stats_completed}, ошибок: {ch.stats_failed}"
            ch.error = saw_error_detail if ch.stats_completed == 0 and saw_error_detail else None
        elif final_status == "cancelled":
            ch.detail = "Остановлено пользователем"
            ch.error = None
        else:
            ch.detail = None
            ch.error = final_err or saw_error_detail

    store.update_channel(channel_id, mutator=_finalize)
