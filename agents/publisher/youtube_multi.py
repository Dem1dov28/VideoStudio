"""
Несколько каналов YouTube под одним Google Cloud проектом / одним client_secret.

Алгоритм:
  • Один OAuth client (JSON из Console) на всё приложение.
  • Каждый «слот» канала = отдельный файл токена (refresh в JSON).
  • videos.insert не принимает channel_id для обычных аккаунтов: куда уйдёт ролик,
    задаётся тем, какой канал/brand выбран при входе Google для ЭТОГО файла.
  • primary → YOUTUBE_OAUTH_TOKEN, secondary → YOUTUBE_OAUTH_TOKEN_B (если задан).

Сброс: POST /api/youtube/reset — удаляет файлы + revoke у Google.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config import Settings


def iter_youtube_token_slots(settings: "Settings") -> list[tuple[str, Path]]:
    """
    Слоты (profile_id, path) без дубликатов путей.
    profile_id: «primary» | «secondary»
    """
    primary = settings.youtube_token_file
    out: list[tuple[str, Path]] = [("primary", primary)]
    sec = settings.youtube_token_file_secondary
    if sec is None:
        return out
    if sec.resolve() == primary.resolve():
        return out
    out.append(("secondary", sec))
    return out


def has_secondary_slot(settings: "Settings") -> bool:
    return len(iter_youtube_token_slots(settings)) > 1
