"""
Несколько каналов YouTube: реестр JSON (разные GCP-проекты / client_secret на слот)
или legacy — один client_secret + YOUTUBE_OAUTH_TOKEN [_B].

Каждый слот = свой файл токена; при реестре — ещё и свой client_secrets (OAuth refresh
должен идти тем же client_id, что выдал токен).

Сброс: POST /api/youtube/reset — удаляет файлы токенов + revoke у Google.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from config import Settings

_PROFILE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$", re.I)


@dataclass(frozen=True)
class YoutubeProfile:
    """Один слот публикации YouTube."""

    id: str
    label: str
    token_path: Path
    client_secrets_path: Path
    gcp_project: str = ""

    def normalized_id(self) -> str:
        return self.id.strip().lower()


def _resolve_path(root: Path, p: str) -> Path:
    path = Path(p.strip())
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _validate_profile_id(pid: str) -> str:
    s = pid.strip().lower()
    if not s or not _PROFILE_ID_RE.match(s):
        raise ValueError(
            f"некорректный id профиля YouTube: {pid!r} (латиница, цифры, _, -)"
        )
    return s


def _load_registry_file(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("youtube profiles JSON: ожидается объект с ключом profiles")
    arr = raw.get("profiles")
    if not isinstance(arr, list) or not arr:
        raise ValueError("youtube profiles JSON: profiles должен быть непустым массом")
    out: list[dict[str, Any]] = []
    for i, it in enumerate(arr):
        if not isinstance(it, dict):
            raise ValueError(f"youtube profiles JSON: profiles[{i}] не объект")
        out.append(it)
    return out


def _profiles_from_registry(settings: "Settings", registry_path: Path) -> list[YoutubeProfile]:
    root = settings.project_root
    items = _load_registry_file(registry_path)
    seen_ids: set[str] = set()
    seen_tokens: set[str] = set()
    out: list[YoutubeProfile] = []
    for i, it in enumerate(items):
        pid = _validate_profile_id(str(it.get("id") or "").strip())
        if pid in seen_ids:
            raise ValueError(f"youtube profiles: дубликат id «{pid}»")
        seen_ids.add(pid)
        label = (it.get("label") or "").strip() or pid
        cs_raw = (it.get("client_secrets") or "").strip()
        tok_raw = (it.get("token") or "").strip()
        if not cs_raw or not tok_raw:
            raise ValueError(
                f"youtube profiles[{i}] ({pid}): нужны client_secrets и token"
            )
        token_path = _resolve_path(root, tok_raw)
        client_secrets_path = _resolve_path(root, cs_raw)
        tp = str(token_path.resolve())
        if tp in seen_tokens:
            raise ValueError(f"youtube profiles: один файл токена на два слота: {tp}")
        seen_tokens.add(tp)
        gcp = (it.get("gcp_project") or it.get("project_label") or "").strip()
        out.append(
            YoutubeProfile(
                id=pid,
                label=label,
                token_path=token_path,
                client_secrets_path=client_secrets_path,
                gcp_project=gcp,
            )
        )
    return out


def _profiles_legacy_env(settings: "Settings") -> list[YoutubeProfile]:
    """primary + optional secondary, один YOUTUBE_OAUTH_CLIENT_SECRETS на все слоты."""
    root = settings.project_root
    cs = settings.youtube_client_secrets_file
    if cs is None:
        raise ValueError("YOUTUBE_OAUTH_CLIENT_SECRETS не задан")
    lab1 = (settings.youtube_channel_primary_label or "").strip() or "Канал 1"
    lab2 = (settings.youtube_channel_secondary_label or "").strip() or "Канал 2"
    primary_tok = settings.youtube_token_file
    out: list[YoutubeProfile] = [
        YoutubeProfile(
            id="primary",
            label=lab1,
            token_path=primary_tok,
            client_secrets_path=cs,
            gcp_project="",
        )
    ]
    sec = settings.youtube_token_file_secondary
    if sec is not None and sec.resolve() != primary_tok.resolve():
        out.append(
            YoutubeProfile(
                id="secondary",
                label=lab2,
                token_path=sec,
                client_secrets_path=cs,
                gcp_project="",
            )
        )
    return out


def youtube_profiles_registry_path(settings: "Settings") -> Path | None:
    p = (getattr(settings, "youtube_profiles_config_path", None) or "").strip()
    if not p or p in ("none", "-", "false", "0"):
        return None
    path = Path(p)
    return path.resolve() if path.is_absolute() else (settings.project_root / path).resolve()


def load_youtube_profiles(settings: "Settings") -> list[YoutubeProfile]:
    """
    Список профилей (порядок — как в реестре или primary→secondary).
    Реестр: если YOUTUBE_PROFILES_CONFIG задан и файл существует и читается.
    Иначе — legacy из .env (нужен YOUTUBE_OAUTH_CLIENT_SECRETS).
    """
    reg = youtube_profiles_registry_path(settings)
    if reg is not None and reg.is_file():
        try:
            return _profiles_from_registry(settings, reg)
        except (json.JSONDecodeError, OSError, ValueError) as e:
            raise ValueError(f"YOUTUBE_PROFILES_CONFIG ({reg}): {e}") from e
    return _profiles_legacy_env(settings)


def try_load_youtube_profiles(settings: "Settings") -> list[YoutubeProfile] | None:
    """Как load_youtube_profiles, но без исключения если legacy без client_secrets."""
    reg = youtube_profiles_registry_path(settings)
    if reg is not None and reg.is_file():
        try:
            return _profiles_from_registry(settings, reg)
        except (json.JSONDecodeError, OSError, ValueError) as e:
            raise ValueError(f"YOUTUBE_PROFILES_CONFIG ({reg}): {e}") from e
    cs = settings.youtube_client_secrets_file
    if cs is None or not cs.is_file():
        return None
    return _profiles_legacy_env(settings)


def uses_youtube_registry(settings: "Settings") -> bool:
    reg = youtube_profiles_registry_path(settings)
    return reg is not None and reg.is_file()


def get_youtube_profile(settings: "Settings", profile_id: str) -> YoutubeProfile:
    key = (profile_id or "").strip().lower()
    for p in load_youtube_profiles(settings):
        if p.normalized_id() == key:
            return p
    raise ValueError(f"неизвестный channel_profile: {profile_id!r}")


def list_youtube_profile_ids(settings: "Settings") -> list[str]:
    return [p.id for p in load_youtube_profiles(settings)]


def iter_youtube_token_slots(settings: "Settings") -> list[tuple[str, Path]]:
    """
    Совместимость: (profile_id, token_path) без client_secrets.
    """
    return [(p.id, p.token_path) for p in load_youtube_profiles(settings)]


def has_secondary_slot(settings: "Settings") -> bool:
    return len(load_youtube_profiles(settings)) > 1


def client_secrets_for_upload(settings: "Settings", profile_id: str) -> Path:
    return get_youtube_profile(settings, profile_id).client_secrets_path


def token_path_for_profile(settings: "Settings", profile_id: str) -> Path:
    return get_youtube_profile(settings, profile_id).token_path
