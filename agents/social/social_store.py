"""Persistent store for bulk TikTok profile downloads."""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Literal

logger = logging.getLogger(__name__)

STORE_VERSION = 1

SocialChannelStatus = Literal["idle", "queued", "running", "done", "error", "cancelled"]
SocialVideoStatus = Literal["pending", "downloading", "ok", "failed", "skipped"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def video_key_safe(extractor: str | None, video_id: str | None) -> str:
    """Stable path segment for API routes / filenames (no slashes)."""
    ex = (extractor or "media").strip()
    ex = re.sub(r"[^a-zA-Z0-9]+", "_", ex)[:24].strip("_").lower() or "media"
    v = (video_id or "").strip()
    v = re.sub(r"[^a-zA-Z0-9_-]+", "_", v)[:96].strip("_")
    if not v:
        v = uuid.uuid4().hex[:12]
    return f"{ex}_{v}"


@dataclass
class SocialVideoRecord:
    key: str
    extractor: str
    video_id: str
    title: str
    page_url: str
    rel_path: str | None
    status: SocialVideoStatus
    downloaded_at: str | None
    error: str | None = None
    youtube_id: str | None = None

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> SocialVideoRecord:
        return cls(
            key=str(d["key"]),
            extractor=str(d.get("extractor") or ""),
            video_id=str(d.get("video_id") or ""),
            title=str(d.get("title") or ""),
            page_url=str(d.get("page_url") or ""),
            rel_path=d.get("rel_path"),
            status=str(d.get("status") or "pending"),  # type: ignore[arg-type]
            downloaded_at=d.get("downloaded_at"),
            error=d.get("error"),
            youtube_id=d.get("youtube_id"),
        )


@dataclass
class SocialChannelRecord:
    id: str
    profile_url: str
    normalized_url: str
    platform: Literal["tiktok", "other"]
    created_at: str
    updated_at: str
    status: SocialChannelStatus
    step: str | None
    detail: str | None
    error: str | None
    stats_completed: int
    stats_failed: int
    videos: list[SocialVideoRecord] = field(default_factory=list)
    # Имя браузера для yt-dlp cookiesfrombrowser (как на вкладке «Новое видео»).
    cookies_browser: str | None = None
    # Путь к Netscape cookies.txt — надёжнее на Windows, чем читать БД Chrome (часто locked).
    cookies_file: str | None = None
    tiktok_headers: bool = False
    max_videos: int | None = None

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["videos"] = [v.to_json() for v in self.videos]
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> SocialChannelRecord:
        videos: list[SocialVideoRecord] = []
        for x in d.get("videos") or []:
            if isinstance(x, dict):
                try:
                    videos.append(SocialVideoRecord.from_json(x))
                except Exception:
                    pass
        cb = d.get("cookies_browser")
        cookies_browser = str(cb).strip() if cb else None
        cfile = d.get("cookies_file")
        cookies_file = str(cfile).strip() if cfile else None
        mv_raw = d.get("max_videos")
        max_videos: int | None = None
        if mv_raw is not None and str(mv_raw).strip() != "":
            try:
                max_videos = int(mv_raw)
            except (TypeError, ValueError):
                max_videos = None
        plat = str(d.get("platform") or "other")
        if plat == "instagram":
            plat = "other"
        return cls(
            id=str(d["id"]),
            profile_url=str(d["profile_url"]),
            normalized_url=str(d["normalized_url"]),
            platform=plat,  # type: ignore[arg-type]
            created_at=str(d["created_at"]),
            updated_at=str(d["updated_at"]),
            status=str(d.get("status") or "idle"),  # type: ignore[arg-type]
            step=d.get("step"),
            detail=d.get("detail"),
            error=d.get("error"),
            stats_completed=int(d.get("stats_completed") or 0),
            stats_failed=int(d.get("stats_failed") or 0),
            videos=videos if videos else [],
            cookies_browser=cookies_browser,
            cookies_file=cookies_file,
            tiktok_headers=bool(d.get("tiktok_headers")),
            max_videos=max_videos,
        )


Mutator = Callable[[SocialChannelRecord], None]


class SocialChannelStore:
    def __init__(self, file_path: Path | str) -> None:
        self.path = Path(file_path)
        self._lock = Lock()

    def _read_root(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"version": STORE_VERSION, "channels": []}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return {"version": STORE_VERSION, "channels": []}
            if "channels" not in raw or not isinstance(raw["channels"], list):
                raw["channels"] = []
            raw.setdefault("version", STORE_VERSION)
            return raw
        except Exception as e:
            logger.warning("social store read failed: %s", e)
            return {"version": STORE_VERSION, "channels": []}

    def _write_root(self, root: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        root["version"] = STORE_VERSION
        text = json.dumps(root, ensure_ascii=False, indent=2)
        self.path.write_text(text, encoding="utf-8")

    def _channels_list(self, root: dict[str, Any]) -> list[SocialChannelRecord]:
        out: list[SocialChannelRecord] = []
        for x in root.get("channels", []):
            if isinstance(x, dict):
                try:
                    out.append(SocialChannelRecord.from_json(x))
                except Exception as e:
                    logger.warning("skip bad social channel row: %s", e)
        return out

    def list_channels(self) -> list[SocialChannelRecord]:
        with self._lock:
            return sorted(self._channels_list(self._read_root()), key=lambda c: c.created_at, reverse=True)

    def get(self, channel_id: str) -> SocialChannelRecord | None:
        with self._lock:
            for c in self._channels_list(self._read_root()):
                if c.id == channel_id:
                    return c
        return None

    def upsert_channel(self, record: SocialChannelRecord) -> None:
        with self._lock:
            root = self._read_root()
            rows = self._channels_list(root)
            rows = [r for r in rows if r.id != record.id]
            rows.append(record)
            root["channels"] = [r.to_json() for r in rows]
            self._write_root(root)

    def update_channel(
        self,
        channel_id: str,
        *,
        mutator: Mutator,
    ) -> SocialChannelRecord | None:
        """Apply mutator(record) -> None (in-place edit). Returns updated record or None."""
        with self._lock:
            root = self._read_root()
            rows = self._channels_list(root)
            found: SocialChannelRecord | None = None
            for i, r in enumerate(rows):
                if r.id == channel_id:
                    found = r
                    break
            if not found:
                return None
            mutator(found)
            found.updated_at = _utc_now()
            root["channels"] = [r.to_json() for r in rows]
            self._write_root(root)
            return found

    def delete_channel(self, channel_id: str) -> bool:
        with self._lock:
            root = self._read_root()
            rows = self._channels_list(root)
            n = len(rows)
            rows = [r for r in rows if r.id != channel_id]
            if len(rows) == n:
                return False
            root["channels"] = [r.to_json() for r in rows]
            self._write_root(root)
            return True

    def find_by_normalized_url(self, normalized_url: str) -> SocialChannelRecord | None:
        with self._lock:
            for c in self._channels_list(self._read_root()):
                if c.normalized_url == normalized_url:
                    return c
        return None

    def update_video_youtube(self, channel_id: str, video_key: str, youtube_id: str) -> bool:
        with self._lock:
            root = self._read_root()
            rows = self._channels_list(root)
            for ch in rows:
                if ch.id != channel_id:
                    continue
                for v in ch.videos:
                    if v.key == video_key:
                        v.youtube_id = youtube_id
                        ch.updated_at = _utc_now()
                        root["channels"] = [r.to_json() for r in rows]
                        self._write_root(root)
                        return True
            return False

    def pop_video(self, channel_id: str, video_key: str) -> SocialVideoRecord | None:
        """
        Delete video row from a channel and return removed record.
        Returns None when channel/video is missing.
        """
        with self._lock:
            root = self._read_root()
            rows = self._channels_list(root)
            for ch in rows:
                if ch.id != channel_id:
                    continue
                for i, v in enumerate(ch.videos):
                    if v.key != video_key:
                        continue
                    removed = ch.videos.pop(i)
                    ch.updated_at = _utc_now()
                    root["channels"] = [r.to_json() for r in rows]
                    self._write_root(root)
                    return removed
                return None
            return None
