"""Прямая публикация на YouTube через Data API v3 (OAuth 2.0 + videos.insert)."""

from __future__ import annotations

import errno
import re
import time
from pathlib import Path
from typing import Any

import certifi
import google_auth_httplib2
import httplib2
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload
from loguru import logger

YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
# Нужен для channels.list(mine) — подсказка канала в UI; без него будет 403.
YOUTUBE_READONLY_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
SCOPES = [YOUTUBE_UPLOAD_SCOPE, YOUTUBE_READONLY_SCOPE]


def _authorized_http_for_youtube(creds: Credentials) -> google_auth_httplib2.AuthorizedHttp:
    """
    Свой httplib2 + certifi; TLS max 1.2 — на части Win/OpenSSL ломается resumption
    (SSL: INVALID_SESSION_ID) с TLS 1.3 / session tickets.
    """
    h2_kw: dict[str, Any] = {"timeout": 600, "ca_certs": certifi.where()}
    try:
        h2_kw["tls_maximum_version"] = "TLSv1_2"
    except Exception:
        pass
    raw = httplib2.Http(**h2_kw)
    # httplib2 при любом 308 пытается follow redirect и требует Location; у Google
    # resumable upload ответ «308 Resume Incomplete» без Location — это не редирект.
    # Убираем 308 из redirect_codes, чтобы отдать ответ в googleapiclient.http.
    raw.redirect_codes = frozenset(x for x in raw.redirect_codes if x != 308)
    return google_auth_httplib2.AuthorizedHttp(creds, http=raw)


def _is_ssl_session_glitch(exc: BaseException) -> bool:
    s = str(exc).lower()
    return "ssl" in s or "invalid_session" in s.replace(" ", "_")


def _is_transient_network_error(exc: BaseException) -> bool:
    """
    WinError 10054 / RST / обрыв с Google API на Windows + старые SSL-глюки httplib2.
    """
    if _is_ssl_session_glitch(exc):
        return True
    if isinstance(exc, (ConnectionResetError, BrokenPipeError)):
        return True
    if isinstance(exc, OSError):
        if getattr(exc, "winerror", None) == 10054:
            return True
        no = getattr(exc, "errno", None)
        if no in (errno.ECONNRESET, errno.ECONNABORTED, errno.EPIPE):
            return True
    s = str(exc).lower()
    if "10054" in s or "forcibly closed" in s or "удаленный хост" in s:
        return True
    if "connection reset" in s or "broken pipe" in s:
        return True
    return False


def ensure_shorts_hashtag(description: str) -> str:
    d = (description or "").strip()
    if "#shorts" in d.lower():
        return d
    if d:
        return f"{d}\n\n#Shorts"
    return "#Shorts"


def normalize_tags(raw: list[str] | None, max_tags: int = 14) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    for t in raw:
        s = re.sub(r"[\s,;]+", " ", str(t).strip()).strip()
        if not s:
            continue
        s = s[:30]
        if s.lower() not in {x.lower() for x in out}:
            out.append(s)
        if len(out) >= max_tags:
            break
    return out


def publishing_to_snippet(
    publishing: dict | None,
    *,
    video_title_fallback: str,
    lang: str | None,
    video_lang: str | None,
) -> tuple[str, str, list[str]]:
    """
    Возвращает (title, description, tags).
    Поддержка: {ru: {...}, en: {...}} или плоский {title, description, hashtags, tags}.
    """
    chosen: dict | None = None
    if isinstance(publishing, dict):
        if "title" in publishing and ("ru" not in publishing and "en" not in publishing):
            chosen = publishing
        else:
            prefer = (lang or video_lang or "en").lower()
            if prefer == "en" and isinstance(publishing.get("en"), dict):
                chosen = publishing["en"]
            elif isinstance(publishing.get("ru"), dict):
                chosen = publishing["ru"]
            elif isinstance(publishing.get("en"), dict):
                chosen = publishing["en"]

    if not chosen:
        t = (video_title_fallback or "Short")[:100]
        return t, ensure_shorts_hashtag(""), []

    title = (chosen.get("title") or video_title_fallback or "Short").replace("\n", " ").strip()[:100]
    description = (chosen.get("description") or "").strip()
    hashtags = chosen.get("hashtags") or []
    if isinstance(hashtags, str):
        hashtags = [hashtags]
    tag_list = chosen.get("tags")
    if isinstance(tag_list, str):
        tag_list = [x.strip() for x in tag_list.split(",") if x.strip()]
    if not isinstance(tag_list, list):
        tag_list = []
    tags = normalize_tags(tag_list)
    hash_line = " ".join(f"#{h.lstrip('#')}" for h in hashtags if str(h).strip()) if hashtags else ""
    if hash_line:
        description = f"{description}\n\n{hash_line}".strip() if description else hash_line
    description = ensure_shorts_hashtag(description)
    return title, description, tags


def create_flow(client_secrets_path: Path, redirect_uri: str, state: str | None = None) -> Flow:
    # Без PKCE: authorize и callback используют разные экземпляры Flow — иначе fetch_token
    # не получает code_verifier → (invalid_grant) Missing code verifier.
    # Для web client с client_secret PKCE не обязателен.
    return Flow.from_client_secrets_file(
        str(client_secrets_path),
        scopes=SCOPES,
        redirect_uri=redirect_uri,
        state=state,
        autogenerate_code_verifier=False,
    )


def save_token_from_code(
    client_secrets_path: Path,
    token_path: Path,
    redirect_uri: str,
    code: str,
    state: str,
) -> None:
    flow = create_flow(client_secrets_path, redirect_uri, state=state)
    for attempt in range(3):
        try:
            flow.fetch_token(code=code)
            break
        except Exception as e:
            if _is_transient_network_error(e) and attempt < 2:
                logger.warning(f"[YouTube] OAuth fetch_token сеть, повтор {attempt + 1}/3: {e}")
                time.sleep(0.9 * (attempt + 1))
                continue
            raise
    token_path.parent.mkdir(parents=True, exist_ok=True)
    creds = flow.credentials
    with open(token_path, "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    logger.success(f"[YouTube] OAuth token сохранён: {token_path}")


def load_credentials(token_path: Path) -> Credentials | None:
    if not token_path.is_file():
        return None
    try:
        return Credentials.from_authorized_user_file(str(token_path), SCOPES)
    except Exception as e:
        logger.warning(f"[YouTube] Не удалось прочитать token: {e}")
        return None


def list_managed_channels_preview(creds: Credentials) -> list[dict[str, str]]:
    """
    channels.list(mine=true). Не гарантирует, в какой канал уйдёт upload — это задаётся
    grant’ом OAuth; при нескольких каналах список подсказочный.
    Ретраи: на Windows часто WinError 10054 (RST) при первом запросе к API.
    """
    for attempt in range(3):
        try:
            http = _authorized_http_for_youtube(creds)
            youtube = build("youtube", "v3", http=http, cache_discovery=False)
            req = youtube.channels().list(part="snippet", mine=True, maxResults=50)
            resp = req.execute()
            out: list[dict[str, str]] = []
            for it in (resp or {}).get("items") or []:
                sn = it.get("snippet") or {}
                cu = (sn.get("customUrl") or "").strip()
                out.append(
                    {
                        "id": (it.get("id") or "").strip(),
                        "title": (sn.get("title") or "").strip(),
                        "custom_url": cu,
                    }
                )
            return out
        except Exception as e:
            if _is_transient_network_error(e) and attempt < 2:
                logger.warning(
                    f"[YouTube] channels.list сеть оборвалась, повтор {attempt + 1}/3: {e}"
                )
                time.sleep(0.85 * (attempt + 1))
                continue
            logger.warning(f"[YouTube] channels.list preview: {e}")
            return []
    return []


def get_valid_credentials(client_secrets_path: Path, token_path: Path) -> Credentials | None:
    creds = load_credentials(token_path)
    if not creds:
        return None
    if creds.expired and creds.refresh_token:
        for attempt in range(3):
            try:
                creds.refresh(Request())
                with open(token_path, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())
                break
            except Exception as e:
                if _is_transient_network_error(e) and attempt < 2:
                    time.sleep(0.8 * (attempt + 1))
                    continue
                logger.error(f"[YouTube] Refresh token не удался: {e}")
                return None
    return creds


def upload_video_file(
    creds: Credentials,
    video_path: Path,
    *,
    title: str,
    description: str,
    tags: list[str] | None,
    privacy_status: str,
    category_id: str = "22",
    made_for_kids: bool = False,
) -> dict[str, Any]:
    if not video_path.is_file():
        raise FileNotFoundError(str(video_path))

    body: dict[str, Any] = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": made_for_kids,
        },
    }
    t = normalize_tags(tags)
    if t:
        body["snippet"]["tags"] = t

    http = _authorized_http_for_youtube(creds)
    youtube = build("youtube", "v3", http=http, cache_discovery=False)
    # MediaFileUpload держит файл открытым до __del__ (GC) — на Windows unlink временного
    # файла после загрузки падает с WinError 32. Явный with закрывает дескриптор до return.
    with open(video_path, "rb") as fh:
        media = MediaIoBaseUpload(
            fh, mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024
        )
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:
            status = None
            attempt = 0
            while attempt < 3:
                try:
                    status, response = request.next_chunk()
                    break
                except Exception as e:
                    attempt += 1
                    if not _is_transient_network_error(e) or attempt >= 3:
                        raise
                    logger.warning(f"[YouTube] сеть при chunk, повтор {attempt}/3: {e}")
                    time.sleep(1.0 * attempt)
            if status and getattr(status, "progress", None) is not None:
                logger.debug(f"[YouTube] upload progress {int(status.progress() * 100)}%")

    vid = (response or {}).get("id", "")
    logger.success(f"[YouTube] Видео загружено, id={vid}")
    return {"id": vid, "snippet": (response or {}).get("snippet"), "raw": response}


def format_http_error(exc: HttpError) -> str:
    try:
        content = exc.content.decode() if exc.content else str(exc)
    except Exception:
        content = str(exc)
    return content[:2000]
