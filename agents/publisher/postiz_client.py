"""Postiz REST API client for social media publishing."""

from __future__ import annotations

import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings


class PostizClient:
    def __init__(self) -> None:
        self._base = settings.postiz_base_url.rstrip("/")
        self._headers = {
            "Authorization": settings.postiz_api_key,
            "Content-Type": "application/json",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    async def _post(self, path: str, json: dict) -> dict:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{self._base}{path}", headers=self._headers, json=json)
            r.raise_for_status()
            return r.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    async def _get(self, path: str) -> dict | list:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{self._base}{path}", headers=self._headers)
            r.raise_for_status()
            return r.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    async def upload_file(self, file_path: Path) -> dict:
        mime, _ = mimetypes.guess_type(str(file_path))
        mime = mime or "application/octet-stream"
        auth_headers = {"Authorization": settings.postiz_api_key}
        async with httpx.AsyncClient(timeout=300) as client:
            with open(file_path, "rb") as f:
                r = await client.post(
                    f"{self._base}/upload",
                    headers=auth_headers,
                    files={"file": (file_path.name, f, mime)},
                )
            r.raise_for_status()
            data = r.json()
            logger.info(f"Uploaded {file_path.name} -> {data.get('path', '')}")
            return data

    async def list_integrations(self) -> list[dict]:
        return await self._get("/integrations")

    async def create_post(
        self,
        content: str,
        integration_id: str,
        platform_type: str,
        media: list[dict] | None = None,
        platform_settings: dict | None = None,
        schedule_at: datetime | None = None,
    ) -> dict:
        date = (
            schedule_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            if schedule_at
            else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        )
        post_type = "now" if schedule_at is None else "schedule"
        settings_obj: dict[str, Any] = {"__type": platform_type}
        if platform_settings:
            settings_obj.update(platform_settings)
        payload = {
            "type": post_type,
            "date": date,
            "shortLink": False,
            "tags": [],
            "posts": [{
                "integration": {"id": integration_id},
                "value": [{"content": content, "image": media or []}],
                "settings": settings_obj,
            }],
        }
        result = await self._post("/posts", payload)
        logger.info(f"Post created on {platform_type}: {result}")
        return result


async def publish_to_all_platforms(
    video_path: Path,
    caption: str,
    hashtags: list[str],
    schedule_at: datetime | None = None,
) -> dict[str, Any]:
    client = PostizClient()
    full_caption = caption + "\n\n" + " ".join(f"#{h}" for h in hashtags)

    logger.info(f"Uploading video: {video_path.name}")
    media_info = await client.upload_file(video_path)
    media = [{"id": media_info["id"], "path": media_info["path"]}]

    results: dict[str, Any] = {}
    platforms = [
        ("TikTok", settings.postiz_tiktok_integration_id, "tiktok",
         {"privacy_level": "PUBLIC_TO_EVERYONE", "comment": True, "duet": False, "stitch": False}),
        ("Instagram", settings.postiz_instagram_integration_id, "instagram",
         {"post_type": "reels"}),
        ("YouTube", settings.postiz_youtube_integration_id, "youtube",
         {"title": caption[:100], "type": "shorts", "selfDeclaredMadeForKids": False, "tags": hashtags[:10]}),
        ("Telegram", settings.postiz_telegram_integration_id, "telegram", {}),
    ]

    for platform_name, integration_id, platform_type, extra_settings in platforms:
        if not integration_id:
            logger.debug(f"Skipping {platform_name}: integration ID not configured")
            continue
        try:
            response = await client.create_post(
                content=full_caption,
                integration_id=integration_id,
                platform_type=platform_type,
                media=media,
                platform_settings=extra_settings,
                schedule_at=schedule_at,
            )
            results[platform_name] = {"status": "ok", "response": response}
            logger.success(f"Published to {platform_name}")
        except Exception as exc:
            logger.error(f"Failed to publish to {platform_name}: {exc}")
            results[platform_name] = {"status": "error", "error": str(exc)}

    return results