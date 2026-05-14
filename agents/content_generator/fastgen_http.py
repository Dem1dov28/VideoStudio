"""
HTTP-клиент FastGen media_gen_api: **v2** для картинок; для видео по умолчанию **v4**
(Flow `…/flow/video/from-ingredients` + Flower `…/flower/video/from-image` / from-text), как в UI Playwright.

Картинки: POST /api/v2/images (синхронно, result = data URI).
Видео v2 (если FASTGEN_HTTP_ENABLE_V4_VIDEO=false): POST /api/v2/videos + GET …/videos/status/{operation_id}.
Видео v4: POST /api/v4/… → operation_id, poll GET /api/v4/operations/{operation_id}.

Авторизация: X-API-Key = FASTGEN_API_KEY. FASTGEN_HTTP_BASE_URL — origin без хвоста /api.
"""

from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import re
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from agents.content_generator.fastgen_exceptions import FastGenCancelled, VideoGenerationError
from agents.content_generator.fastgen_global_media import async_fastgen_global_media_slot
from agents.content_generator.fastgen_prompts import (
    _fastgen_aspect_ratio_normalized,
    _resolve_video_tab_aspect_ratio,
    prepare_fastgen_prompt_for_image,
    prepare_fastgen_prompt_for_video,
)
from config import settings

_PROVIDER = "google_fx"
_DATA_URI_RE = re.compile(r"^data:([^;]+);base64,(.+)$", re.DOTALL)

# Повтор при HTTP 500 generation.content_policy («известные лица»): усиливаем анонимность сцены.
_CONTENT_POLICY_IMAGE_RETRY_SUFFIX = (
    "REGENERATION (content policy): do not depict any real public figure, celebrity, politician, athlete, or religious leader. "
    "No recognizable face or body likeness. Preserve the original scene intent, location, and topic-linked objects; "
    "if people are needed, use anonymous generic role-based characters with non-identifiable facial features."
)
_FILE_REF_RE = re.compile(r"^file:[a-f0-9]{32}$")
_MAX_INLINE_BYTES = 4 * 1024 * 1024  # ~4 MiB raw — дальше storage


def _cancel_requested(cancel_event: threading.Event | None) -> bool:
    return cancel_event is not None and cancel_event.is_set()


def _unique_frame_dest(output_dir: Path, base_suffix: str) -> Path:
    return output_dir / f"frame_{time.time_ns()}_{uuid.uuid4().hex[:12]}_{base_suffix}.jpg"


def _base_url() -> str:
    return (getattr(settings, "fastgen_http_base_url", None) or "").strip().rstrip("/")


def _require_base() -> str:
    b = _base_url()
    if not b:
        raise RuntimeError("FASTGEN_HTTP_BASE_URL is not set")
    return b


def _api_key() -> str:
    return (settings.fastgen_api_key or "").strip()


def _build_headers() -> dict[str, str]:
    h: dict[str, str] = {"Accept": "application/json"}
    style = (getattr(settings, "fastgen_http_auth_style", None) or "api_key").strip().lower()
    key = _api_key()
    if style == "none" or not key:
        return h
    if style in ("api_key", "x-api-key", "license"):
        name = (getattr(settings, "fastgen_http_api_key_header", None) or "X-API-Key").strip()
        h[name] = key
    else:
        h["Authorization"] = f"Bearer {key}"
    return h


def _content_policy_relaxed_image_prompt(prepared_prompt: str) -> str:
    """Один раз дополняем уже подготовленный FastGen промпт."""
    base = (prepared_prompt or "").rstrip()
    if not base:
        return _CONTENT_POLICY_IMAGE_RETRY_SUFFIX
    return f"{base}\n\n{_CONTENT_POLICY_IMAGE_RETRY_SUFFIX}"


def _is_fastgen_content_policy_error(exc: BaseException) -> bool:
    if isinstance(exc, VideoGenerationError):
        ad = getattr(exc, "api_detail", None)
        if isinstance(ad, dict):
            code = str(ad.get("code") or "").strip().lower()
            if code in {"generation.content_policy", "content_policy"}:
                return True
            err = str(ad.get("error") or "").lower()
            if "prominent people" in err or "well-known individuals" in err:
                return True
    low = str(exc).lower()
    return (
        "content_policy" in low
        or "prominent people" in low
        or "well-known individuals" in low
        or "цензура" in low
    )


async def _post_v2_images_resilient(
    client: httpx.AsyncClient,
    prepared_prompt: str,
    build_body: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    """До 2 попыток: при блокировке по известным лицам — тот же запрос с усиленным суффиксом."""
    cur = prepared_prompt
    for attempt in range(2):
        try:
            return await _post_v2_images(client, build_body(cur))
        except VideoGenerationError as e:
            if attempt == 0 and _is_fastgen_content_policy_error(e):
                cur = _content_policy_relaxed_image_prompt(prepared_prompt)
                logger.warning(
                    "[FastGen HTTP] v2/images content_policy — retry with stricter anonymous-scene constraints ({})",
                    e,
                )
                continue
            raise
    raise RuntimeError("[FastGen HTTP] _post_v2_images_resilient: unreachable")


def _merge_into_parameters(params: dict[str, Any]) -> dict[str, Any]:
    raw = (getattr(settings, "fastgen_http_extra_json", None) or "").strip()
    if not raw:
        return params
    try:
        extra = json.loads(raw)
        if isinstance(extra, dict):
            return {**params, **extra}
    except json.JSONDecodeError as e:
        logger.warning(f"[FastGen HTTP] FASTGEN_HTTP_EXTRA_JSON invalid: {e}")
    return params


def _image_aspect_enum(explicit: str | None = None) -> str:
    r = _fastgen_aspect_ratio_normalized(explicit)
    if r == "9:16":
        return "IMAGE_ASPECT_RATIO_PORTRAIT"
    if r == "4:3":
        return "IMAGE_ASPECT_RATIO_LANDSCAPE_FOUR_THREE"
    if r == "3:4":
        return "IMAGE_ASPECT_RATIO_PORTRAIT_THREE_FOUR"
    if r == "1:1":
        return "IMAGE_ASPECT_RATIO_SQUARE"
    return "IMAGE_ASPECT_RATIO_LANDSCAPE"


def _video_aspect_enum(explicit: str | None = None) -> str:
    r = _resolve_video_tab_aspect_ratio(explicit)
    if r == "9:16":
        return "VIDEO_ASPECT_RATIO_PORTRAIT"
    return "VIDEO_ASPECT_RATIO_LANDSCAPE"


def _video_aspect_v4_short(explicit: str | None = None) -> str:
    """Flower / часть v4 — только строки 16:9 | 9:16 (см. OpenAPI)."""
    r = _resolve_video_tab_aspect_ratio(explicit)
    return "9:16" if r == "9:16" else "16:9"


def _merge_v4_request_body(body: dict[str, Any]) -> dict[str, Any]:
    """FASTGEN_HTTP_EXTRA_JSON сливается в корень тела v4 (не в parameters как у v2)."""
    raw = (getattr(settings, "fastgen_http_extra_json", None) or "").strip()
    if not raw:
        return body
    try:
        extra = json.loads(raw)
        if isinstance(extra, dict):
            return {**body, **extra}
    except json.JSONDecodeError as e:
        logger.warning(f"[FastGen HTTP] FASTGEN_HTTP_EXTRA_JSON (v4 root) invalid: {e}")
    return body


def _normalize_google_fx_image_model() -> str:
    """
    FASTGEN_MODEL как в UI (value NARWHAL или подпись «Nano Banana 2 - Flow»)
    → enum v2/v4 Flow: GEM_PIX_2 | NARWHAL.
    IMAGEN_* intentionally disabled: forced fallback to NARWHAL.
    """
    raw = (getattr(settings, "fastgen_model", None) or "NARWHAL").strip()
    if not raw:
        return "NARWHAL"
    compact = re.sub(r"[^A-Za-z0-9]+", "_", raw).upper()
    if "NARWHAL" in compact or "BANANA_2" in compact or "NANO_BANANA_2" in compact:
        return "NARWHAL"
    if "IMAGEN" in compact or "IMAGEN4" in compact or "IMAGEN_4" in compact:
        logger.warning("[FastGen HTTP] IMAGEN_* is disabled for images; forcing NARWHAL")
        return "NARWHAL"
    if "GEM_PIX" in compact or "PIX_2" in compact or ("NANO" in compact and "PRO" in compact):
        return "GEM_PIX_2"
    if "BANANA_2" in compact or "NANO_BANANA_2" in compact:
        return "NARWHAL"
    u = raw.upper().replace(" ", "").replace("_", "")
    if u in ("NARWHAL", "NANOBANANA2", "NANO_BANANA_2"):
        return "NARWHAL"
    if u in ("GEMPIX2", "GEM_PIX_2"):
        return "GEM_PIX_2"
    return "NARWHAL"


def _resolve_image_model_for_prompt(prompt: str) -> str:
    """
    Mode5 (all submodes) must use NARWHAL (Nano Banana 2 - Flow) for v2 images.
    We enforce this by pipeline mode and by explicit mode5 guard marker in prompt.
    """
    low = (prompt or "").lower()
    if str(getattr(settings, "pipeline_mode", "") or "").strip().lower() == "mode5":
        return "NARWHAL"
    if "hard override for mode5" in low or "mode5 sequence" in low or "for mode5" in low:
        return "NARWHAL"
    return _normalize_google_fx_image_model()


def _mime_for_path(path: Path) -> str:
    mt, _ = mimetypes.guess_type(path.name)
    if mt:
        return mt
    suf = path.suffix.lower()
    if suf in (".jpg", ".jpeg"):
        return "image/jpeg"
    if suf == ".png":
        return "image/png"
    if suf == ".webp":
        return "image/webp"
    return "application/octet-stream"


def _file_to_data_uri(path: Path) -> str:
    raw = path.read_bytes()
    mime = _mime_for_path(path)
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


async def _storage_upload_file(client: httpx.AsyncClient, path: Path) -> str:
    """POST storage …/upload → file_hash (строка вида file:…)."""
    base = (getattr(settings, "fastgen_storage_base_url", None) or "https://storage.fast-gen.ai").strip().rstrip("/")
    url = f"{base}/upload"
    mime = _mime_for_path(path)
    data = path.read_bytes()
    files = {"file": (path.name, data, mime)}
    r = await client.post(url, headers=_build_headers(), files=files, timeout=120.0)
    r.raise_for_status()
    body = r.json()
    if not body.get("success"):
        raise VideoGenerationError(f"Storage upload failed: {body!r}")
    fh = body.get("file_hash")
    if not isinstance(fh, str) or not _FILE_REF_RE.match(fh):
        # API может вернуть без префикса file:
        if isinstance(fh, str) and re.match(r"^[a-f0-9]{32}$", fh):
            fh = f"file:{fh}"
        else:
            raise VideoGenerationError(f"Bad file_hash from storage: {body!r}")
    return fh


async def _image_input_for_path(client: httpx.AsyncClient, path: Path) -> str:
    """Data URI или file: после upload при большом файле."""
    try:
        sz = path.stat().st_size
    except OSError:
        sz = 0
    if sz <= _MAX_INLINE_BYTES:
        return _file_to_data_uri(path)
    return await _storage_upload_file(client, path)


def _decode_data_uri(s: str) -> bytes:
    m = _DATA_URI_RE.match(s.strip())
    if not m:
        raise VideoGenerationError(f"Expected data URI, got: {s[:80]}…")
    return base64.b64decode(m.group(2))


def _remix_categories(n: int) -> list[str]:
    order = ["MEDIA_CATEGORY_SUBJECT", "MEDIA_CATEGORY_SCENE", "MEDIA_CATEGORY_STYLE"]
    return [order[i % 3] for i in range(n)]


def _v2_image_body_generate(prompt: str, aspect_ratio: str | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {
        "prompt": prompt,
        "aspect_ratio": _image_aspect_enum(aspect_ratio),
        "model": _resolve_image_model_for_prompt(prompt),
    }
    return {
        "provider": getattr(settings, "fastgen_http_media_provider", None) or _PROVIDER,
        "operation": "generate",
        "parameters": _merge_into_parameters(params),
    }


def _v2_image_body_transform(
    prompt: str, input_image: str, aspect_ratio: str | None = None
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "prompt": prompt,
        "input_image": input_image,
        "aspect_ratio": _image_aspect_enum(aspect_ratio),
        "model": _resolve_image_model_for_prompt(prompt),
    }
    return {
        "provider": getattr(settings, "fastgen_http_media_provider", None) or _PROVIDER,
        "operation": "transform",
        "parameters": _merge_into_parameters(params),
    }


def _v2_image_body_remix(
    prompt: str, refs: list[str], aspect_ratio: str | None = None
) -> dict[str, Any]:
    n = min(3, len(refs))
    cats = _remix_categories(n)
    ref_objs = [{"image": refs[i], "category": cats[i]} for i in range(n)]
    params: dict[str, Any] = {
        "prompt": prompt,
        "reference_images": ref_objs,
        "aspect_ratio": _image_aspect_enum(aspect_ratio),
        "model": _resolve_image_model_for_prompt(prompt),
    }
    return {
        "provider": getattr(settings, "fastgen_http_media_provider", None) or _PROVIDER,
        "operation": "remix",
        "parameters": _merge_into_parameters(params),
    }


async def _post_v2_images(client: httpx.AsyncClient, body: dict[str, Any]) -> dict[str, Any]:
    path = (getattr(settings, "fastgen_http_image_path", None) or "/api/v2/images").strip()
    url = _require_base() + (path if path.startswith("/") else "/" + path)
    timeout = float(getattr(settings, "fastgen_http_timeout_sec", 600) or 600)
    r = await client.post(
        url,
        json=body,
        headers={**_build_headers(), "Content-Type": "application/json"},
        timeout=timeout,
    )
    if r.status_code >= 400:
        try:
            detail = r.json()
        except Exception:
            detail = r.text[:500]
        api_d = detail if isinstance(detail, dict) else None
        raise VideoGenerationError(f"v2/images HTTP {r.status_code}: {detail}", api_detail=api_d)
    data = r.json()
    if not data.get("success"):
        api_d = data if isinstance(data, dict) else None
        raise VideoGenerationError(f"v2/images failed: {data!r}", api_detail=api_d)
    res = data.get("result")
    if not isinstance(res, str):
        raise VideoGenerationError(f"v2/images no result: {data!r}")
    return {"result": res, "raw": data}


async def _post_v2_videos(client: httpx.AsyncClient, body: dict[str, Any]) -> str:
    path = (getattr(settings, "fastgen_http_video_path", None) or "/api/v2/videos").strip()
    url = _require_base() + (path if path.startswith("/") else "/" + path)
    timeout = float(getattr(settings, "fastgen_http_timeout_sec", 600) or 600)
    r = await client.post(
        url,
        json=body,
        headers={**_build_headers(), "Content-Type": "application/json"},
        timeout=timeout,
    )
    if r.status_code >= 400:
        try:
            detail = r.json()
        except Exception:
            detail = r.text[:500]
        raise VideoGenerationError(f"v2/videos HTTP {r.status_code}: {detail}")
    data = r.json()
    if not data.get("success"):
        raise VideoGenerationError(f"v2/videos start failed: {data!r}")
    op_id = data.get("operation_id")
    if not isinstance(op_id, str) or not op_id:
        raise VideoGenerationError(f"v2/videos no operation_id: {data!r}")
    return op_id


async def _poll_v2_video(client: httpx.AsyncClient, operation_id: str, cancel_event: threading.Event | None) -> str:
    tmpl = (getattr(settings, "fastgen_http_poll_path_template", None) or "").strip()
    if not tmpl:
        tmpl = "/api/v2/videos/status/{operation_id}"
    poll_path = tmpl.replace("{operation_id}", operation_id).replace("{job_id}", operation_id)
    url = _require_base() + (poll_path if poll_path.startswith("/") else "/" + poll_path)
    interval = float(getattr(settings, "fastgen_http_poll_interval_sec", 2.0) or 2.0)
    max_wait = float(getattr(settings, "fastgen_http_poll_max_sec", 900.0) or 900.0)
    t0 = time.monotonic()
    failed = {x.strip().lower() for x in (getattr(settings, "fastgen_http_poll_failed_values", "") or "error").split(",") if x.strip()}
    failed.add("error")
    done = {x.strip().lower() for x in (getattr(settings, "fastgen_http_poll_done_values", "") or "success").split(",") if x.strip()}
    done.add("success")
    while time.monotonic() - t0 < max_wait:
        if _cancel_requested(cancel_event):
            raise FastGenCancelled()
        r = await client.get(url, headers=_build_headers(), timeout=60.0)
        r.raise_for_status()
        data = r.json()
        st = (data.get("status") or "").strip().lower()
        if st in failed:
            err = data.get("error") or data.get("detail") or data
            raise VideoGenerationError(f"Video op {operation_id}: {err}")
        if st in done:
            res = data.get("result")
            if isinstance(res, str) and res.startswith("data:"):
                return res
            raise VideoGenerationError(f"Video success but no data URI result: {data!r}")
        await asyncio.sleep(max(0.5, interval))
    raise TimeoutError(f"Video poll timeout {max_wait}s for {operation_id}")


def _v4_enabled() -> bool:
    return bool(getattr(settings, "fastgen_http_enable_v4_video", True))


async def _post_v4_start(client: httpx.AsyncClient, path: str, body: dict[str, Any]) -> str:
    url = _require_base() + (path if path.startswith("/") else "/" + path)
    timeout = float(getattr(settings, "fastgen_http_timeout_sec", 600) or 600)
    payload = _merge_v4_request_body(dict(body))
    r = await client.post(
        url,
        json=payload,
        headers={**_build_headers(), "Content-Type": "application/json"},
        timeout=timeout,
    )
    if r.status_code >= 400:
        try:
            detail = r.json()
        except Exception:
            detail = r.text[:800]
        raise VideoGenerationError(f"v4 {path} HTTP {r.status_code}: {detail}")
    data = r.json()
    op_id = data.get("operation_id")
    if not isinstance(op_id, str) or not op_id:
        raise VideoGenerationError(f"v4 start missing operation_id: {data!r}")
    return op_id


async def _poll_v4_operation(
    client: httpx.AsyncClient, operation_id: str, cancel_event: threading.Event | None
) -> str:
    tmpl = (getattr(settings, "fastgen_http_v4_poll_path_template", None) or "").strip()
    if not tmpl:
        tmpl = "/api/v4/operations/{operation_id}"
    poll_path = tmpl.replace("{operation_id}", operation_id).replace("{job_id}", operation_id)
    url = _require_base() + (poll_path if poll_path.startswith("/") else "/" + poll_path)
    interval = float(getattr(settings, "fastgen_http_poll_interval_sec", 2.0) or 2.0)
    max_wait = float(getattr(settings, "fastgen_http_poll_max_sec", 900.0) or 900.0)
    t0 = time.monotonic()
    failed = {
        x.strip().lower()
        for x in (getattr(settings, "fastgen_http_poll_failed_values", "") or "error").split(",")
        if x.strip()
    }
    failed.add("error")
    done = {
        x.strip().lower()
        for x in (getattr(settings, "fastgen_http_poll_done_values", "") or "success").split(",")
        if x.strip()
    }
    done.add("success")
    while time.monotonic() - t0 < max_wait:
        if _cancel_requested(cancel_event):
            raise FastGenCancelled()
        r = await client.get(url, headers=_build_headers(), timeout=60.0)
        r.raise_for_status()
        data = r.json()
        st = (data.get("status") or "").strip().lower()
        if st in failed:
            err = data.get("error") or data.get("detail") or data
            raise VideoGenerationError(f"v4 op {operation_id}: {err}")
        if st in done:
            res = data.get("result")
            s: str | None = None
            if isinstance(res, list) and res:
                s = res[0] if isinstance(res[0], str) else None
            elif isinstance(res, str):
                s = res
            if isinstance(s, str) and s.startswith("data:"):
                return s
            raise VideoGenerationError(f"v4 success but unexpected result: {data!r}")
        await asyncio.sleep(max(0.5, interval))
    raise TimeoutError(f"v4 poll timeout {max_wait}s for {operation_id}")


async def _generate_one_image(
    client: httpx.AsyncClient,
    prompt: str,
    output_dir: Path,
    index: int | None,
    cancel_event: threading.Event | None,
    reference_paths: list[Path] | None = None,
    aspect_ratio: str | None = None,
) -> Path | None:
    if _cancel_requested(cancel_event):
        return None

    async def _body() -> Path | None:
        full_prompt = prepare_fastgen_prompt_for_image(prompt)
        refs = [p for p in (reference_paths or []) if p.exists()]
        if len(refs) > 3:
            logger.warning(f"[FastGen HTTP] remix supports max 3 refs, using first 3 of {len(refs)}")
            refs = refs[:3]
        if refs:
            ref_inputs = [await _image_input_for_path(client, p) for p in refs]

            def _body_fn(cur: str) -> dict[str, Any]:
                return _v2_image_body_remix(cur, ref_inputs, aspect_ratio)

        else:

            def _body_fn(cur: str) -> dict[str, Any]:
                return _v2_image_body_generate(cur, aspect_ratio)

        out = await _post_v2_images_resilient(client, full_prompt, _body_fn)
        dest = _unique_frame_dest(output_dir, str(index) if index is not None else "0")
        dest.write_bytes(_decode_data_uri(out["result"]))
        return dest if dest.exists() else None

    async with async_fastgen_global_media_slot():
        return await _body()


async def _generate_one_video_v2(
    client: httpx.AsyncClient,
    full_prompt: str,
    output_dir: Path,
    index: int,
    reference_paths: list[Path] | None,
    cancel_event: threading.Event | None,
    *,
    keyframes: bool,
    start_frame: Path | None,
    end_frame: Path | None,
    video_aspect_ratio: str | None = None,
) -> Path | None:
    aspect = _video_aspect_enum(video_aspect_ratio)
    params_base: dict[str, Any] = {"prompt": full_prompt, "aspect_ratio": aspect}
    params = _merge_into_parameters(params_base)
    provider = getattr(settings, "fastgen_http_media_provider", None) or _PROVIDER

    if keyframes and start_frame and start_frame.exists():
        op = "generate_video_start_end"
        params["start_image"] = await _image_input_for_path(client, Path(start_frame))
        if end_frame and Path(end_frame).exists():
            params["end_image"] = await _image_input_for_path(client, Path(end_frame))
        body: dict[str, Any] = {"provider": provider, "operation": op, "parameters": params}
    else:
        refs = [p for p in (reference_paths or []) if p.exists()]
        if len(refs) > 3:
            logger.warning(f"[FastGen HTTP] ingredients max 3 refs, truncating from {len(refs)}")
            refs = refs[:3]
        if len(refs) >= 2:
            op = "generate_video_from_ingredients"
            params["reference_images"] = [await _image_input_for_path(client, p) for p in refs]
            body = {"provider": provider, "operation": op, "parameters": params}
        elif len(refs) == 1:
            op = "generate_video_from_image"
            params["input_image"] = await _image_input_for_path(client, refs[0])
            body = {"provider": provider, "operation": op, "parameters": params}
        else:
            op = "generate_video_from_prompt_flow"
            body = {"provider": provider, "operation": op, "parameters": params}

    op_id = await _post_v2_videos(client, body)
    data_uri = await _poll_v2_video(client, op_id, cancel_event)
    out = output_dir / f"clip_{index:03d}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(_decode_data_uri(data_uri))
    return out if out.exists() else None


async def _generate_one_video(
    client: httpx.AsyncClient,
    prompt: str,
    output_dir: Path,
    index: int,
    reference_paths: list[Path] | None,
    cancel_event: threading.Event | None,
    *,
    mode4_veo_flow_flower: bool = False,
    keyframes: bool = False,
    start_frame: Path | None = None,
    end_frame: Path | None = None,
    video_aspect_ratio: str | None = None,
) -> Path | None:
    async def _video_body() -> Path | None:
        full_prompt = prepare_fastgen_prompt_for_video(prompt)
        aspect = _video_aspect_enum(video_aspect_ratio)
        aspect_short = _video_aspect_v4_short(video_aspect_ratio)
        out = output_dir / f"clip_{index:03d}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)

        if not _v4_enabled():
            return await _generate_one_video_v2(
                client,
                full_prompt,
                output_dir,
                index,
                reference_paths,
                cancel_event,
                keyframes=keyframes,
                start_frame=start_frame,
                end_frame=end_frame,
                video_aspect_ratio=video_aspect_ratio,
            )

        # ── v4: keyframes (Flow) ───────────────────────────────────────────────
        if keyframes and start_frame and start_frame.exists():
            kf_path = (getattr(settings, "fastgen_http_v4_flow_keyframes_path", None) or "").strip()
            if not kf_path.startswith("/"):
                kf_path = "/" + kf_path
            body: dict[str, Any] = {
                "prompt": full_prompt,
                "start_image": await _image_input_for_path(client, Path(start_frame)),
                "aspect_ratio": aspect,
            }
            if end_frame and Path(end_frame).exists():
                body["end_image"] = await _image_input_for_path(client, Path(end_frame))
            op_id = await _post_v4_start(client, kf_path, body)
            data_uri = await _poll_v4_operation(client, op_id, cancel_event)
            out.write_bytes(_decode_data_uri(data_uri))
            return out if out.exists() else None

        refs = [p for p in (reference_paths or []) if p.exists()]
        if len(refs) > 3:
            logger.warning(f"[FastGen HTTP] ingredients max 3 refs, truncating from {len(refs)}")
            refs = refs[:3]

        flow_path = (getattr(settings, "fastgen_http_v4_flow_ingredients_path", None) or "").strip()
        if not flow_path.startswith("/"):
            flow_path = "/" + flow_path
        flower_img_path = (getattr(settings, "fastgen_http_v4_flower_from_image_path", None) or "").strip()
        if not flower_img_path.startswith("/"):
            flower_img_path = "/" + flower_img_path
        flow_txt_path = (getattr(settings, "fastgen_http_v4_flow_from_text_path", None) or "").strip()
        if not flow_txt_path.startswith("/"):
            flow_txt_path = "/" + flow_txt_path

        # ── v4: 2–3 референса → Flow ingredients ───────────────────────────────
        if len(refs) >= 2:
            imgs = [await _image_input_for_path(client, p) for p in refs]
            body = {"prompt": full_prompt, "reference_images": imgs, "aspect_ratio": aspect}
            op_id = await _post_v4_start(client, flow_path, body)
            data_uri = await _poll_v4_operation(client, op_id, cancel_event)
            out.write_bytes(_decode_data_uri(data_uri))
            return out if out.exists() else None

        # ── v4: один референс — Mode 4: Flow (Veo) N раз → Flower; остальные режимы: только Flow, как вкладка Video в UI
        if len(refs) == 1:
            img = await _image_input_for_path(client, refs[0])
            flow_n = max(1, int(getattr(settings, "mode4_veo_flow_attempts_before_flower", 3) or 3))
            max_a = max(1, int(settings.fastgen_max_attempts or 8))
            if mode4_veo_flow_flower:
                total = flow_n + max_a
                for attempt in range(total):
                    if _cancel_requested(cancel_event):
                        return None
                    try:
                        if attempt < flow_n:
                            body = {"prompt": full_prompt, "reference_images": [img], "aspect_ratio": aspect}
                            logger.info(
                                f"[FastGen HTTP] clip {index}: v4 Flow (как {getattr(settings, 'mode4_veo_video_model_flow', 'Flow')}) "
                                f"{attempt + 1}/{flow_n}"
                            )
                            op_id = await _post_v4_start(client, flow_path, body)
                        else:
                            body = {"prompt": full_prompt, "image": img, "aspect_ratio": aspect_short}
                            fn = attempt - flow_n + 1
                            logger.info(
                                f"[FastGen HTTP] clip {index}: v4 Flower (как {getattr(settings, 'mode4_veo_video_model_flower', 'Flower')}) "
                                f"{fn}/{max_a}"
                            )
                            op_id = await _post_v4_start(client, flower_img_path, body)
                        data_uri = await _poll_v4_operation(client, op_id, cancel_event)
                        out.write_bytes(_decode_data_uri(data_uri))
                        return out if out.exists() else None
                    except (FastGenCancelled, asyncio.CancelledError):
                        raise
                    except Exception as e:
                        logger.warning(f"[FastGen HTTP] clip {index} video attempt {attempt + 1}/{total}: {e}")
                        await asyncio.sleep(2.0)
                return None
            for attempt in range(max_a):
                if _cancel_requested(cancel_event):
                    return None
                try:
                    body = {"prompt": full_prompt, "reference_images": [img], "aspect_ratio": aspect}
                    logger.info(
                        f"[FastGen HTTP] clip {index}: v4 Flow ingredients (как видео по умолчанию в UI, без Flower) "
                        f"{attempt + 1}/{max_a}"
                    )
                    op_id = await _post_v4_start(client, flow_path, body)
                    data_uri = await _poll_v4_operation(client, op_id, cancel_event)
                    out.write_bytes(_decode_data_uri(data_uri))
                    return out if out.exists() else None
                except (FastGenCancelled, asyncio.CancelledError):
                    raise
                except Exception as e:
                    logger.warning(f"[FastGen HTTP] clip {index} video attempt {attempt + 1}/{max_a}: {e}")
                    await asyncio.sleep(2.0)
            return None

        # ── v4: только текст → Flow from-text (как Veo Flow по умолчанию в UI, не Flower) ──
        body = {"prompt": full_prompt, "aspect_ratio": aspect}
        op_id = await _post_v4_start(client, flow_txt_path, body)
        data_uri = await _poll_v4_operation(client, op_id, cancel_event)
        out.write_bytes(_decode_data_uri(data_uri))
        return out if out.exists() else None

    async with async_fastgen_global_media_slot():
        return await _video_body()


# --- public API ---


async def generate_images_fastgen(
    prompts: list[str],
    output_dir: Path,
    parallel: bool = True,
    cancel_event: threading.Event | None = None,
    aspect_ratio: str | None = None,
) -> list[Path]:
    _require_base()
    if not _api_key():
        raise RuntimeError("FASTGEN_API_KEY required for HTTP API (X-API-Key)")
    output_dir.mkdir(parents=True, exist_ok=True)
    workers = max(1, int(getattr(settings, "fastgen_image_parallel_workers", 10) or 10))
    timeout = httpx.Timeout(float(getattr(settings, "fastgen_http_timeout_sec", 600) or 600))

    attempts_n = max(1, int(getattr(settings, "fastgen_max_attempts", 8) or 8))

    async def one(i: int, p: str) -> Path | None:
        last_exc: BaseException | None = None
        async with httpx.AsyncClient(timeout=timeout) as client:
            for _ in range(attempts_n):
                if _cancel_requested(cancel_event):
                    raise FastGenCancelled()
                try:
                    r = await _generate_one_image(
                        client, p, output_dir, i, cancel_event, None, aspect_ratio
                    )
                    if r:
                        return r
                    last_exc = RuntimeError("generator returned no file path")
                    logger.warning(f"[FastGen HTTP] image {i}: empty path (retry)")
                except FastGenCancelled:
                    raise
                except Exception as e:
                    last_exc = e
                    logger.warning(f"[FastGen HTTP] image {i} retry: {e}")
                await asyncio.sleep(1.5)
            if last_exc:
                logger.error("[FastGen HTTP] image {} exhausted {} attempts: {}", i, attempts_n, last_exc)
            return None

    if parallel and len(prompts) > 1:
        sem = asyncio.Semaphore(min(workers, len(prompts)))

        async def bounded(j: int, pr: str) -> Path | None:
            async with sem:
                return await one(j, pr)

        results = await asyncio.gather(*[bounded(i, prompts[i]) for i in range(len(prompts))])
        failed_ix = [j for j, r in enumerate(results) if r is None]
        if failed_ix:
            if _cancel_requested(cancel_event):
                raise FastGenCancelled()
            raise RuntimeError(
                f"[FastGen HTTP] Some images failed to generate at indices {failed_ix} "
                f"(see warnings above; often HTTP 4xx/5xx, API detail, or content_policy)."
            )
        return list(results)  # type: ignore[return-value]

    all_paths: list[Path] = []
    async with httpx.AsyncClient(timeout=timeout) as client:
        for i, pr in enumerate(prompts):
            if _cancel_requested(cancel_event):
                raise FastGenCancelled()
            ok = False
            last_exc: BaseException | None = None
            for _ in range(attempts_n):
                if _cancel_requested(cancel_event):
                    raise FastGenCancelled()
                try:
                    r = await _generate_one_image(
                        client, pr, output_dir, i, cancel_event, None, aspect_ratio
                    )
                    if r:
                        all_paths.append(r)
                        ok = True
                        break
                    logger.warning(f"[FastGen HTTP] sequential image index {i}: empty path from API (retry)")
                    last_exc = RuntimeError("generator returned no file path")
                except FastGenCancelled:
                    raise
                except Exception as e:
                    last_exc = e
                    logger.warning(f"[FastGen HTTP] sequential image retry: {e}")
                await asyncio.sleep(1.5)
            if not ok:
                hint = f": {last_exc}" if last_exc else ""
                raise RuntimeError(
                    f"[FastGen HTTP] failed image at index {i} after {attempts_n} attempt(s){hint}"
                ) from last_exc
            await asyncio.sleep(0.3)
    return all_paths


async def generate_images_with_references_fastgen(
    prompts_with_refs: list[tuple[str, list[Path]]],
    output_dir: Path,
    parallel: bool = True,
    max_workers: int | None = None,
) -> list[Path]:
    _require_base()
    if not _api_key():
        raise RuntimeError("FASTGEN_API_KEY required for HTTP API (X-API-Key)")
    output_dir.mkdir(parents=True, exist_ok=True)
    workers = max_workers or int(getattr(settings, "fastgen_image_parallel_workers", 10) or 10)
    timeout = httpx.Timeout(float(getattr(settings, "fastgen_http_timeout_sec", 600) or 600))

    async def one(i: int, prompt: str, refs: list[Path]) -> Path | None:
        async with httpx.AsyncClient(timeout=timeout) as client:
            for _ in range(max(1, settings.fastgen_max_attempts)):
                try:
                    return await _generate_one_image(client, prompt, output_dir, i, None, refs)
                except Exception as e:
                    logger.warning(f"[FastGen HTTP] image+refs {i} retry: {e}")
                await asyncio.sleep(1.5)
            return None

    if parallel and len(prompts_with_refs) > 1:
        sem = asyncio.Semaphore(max(1, min(workers, len(prompts_with_refs))))

        async def bounded(i: int, pr: str, rf: list[Path]) -> Path | None:
            async with sem:
                return await one(i, pr, rf)

        return list(
            await asyncio.gather(
                *[bounded(i, prompts_with_refs[i][0], prompts_with_refs[i][1]) for i in range(len(prompts_with_refs))]
            )
        )

    out: list[Path] = []
    async with httpx.AsyncClient(timeout=timeout) as client:
        for i, (pr, refs) in enumerate(prompts_with_refs):
            for _ in range(max(1, settings.fastgen_max_attempts)):
                try:
                    r = await _generate_one_image(client, pr, output_dir, i, None, refs)
                    if r:
                        out.append(r)
                        break
                except Exception as e:
                    logger.warning(f"[FastGen HTTP] sequential image+refs retry: {e}")
                await asyncio.sleep(1.5)
    return out


async def generate_images_chain_fastgen(
    steps: list[tuple[str, int | None]],
    output_dir: Path,
    cancel_event: threading.Event | None = None,
) -> list[Path]:
    _require_base()
    if not _api_key():
        raise RuntimeError("FASTGEN_API_KEY required for HTTP API (X-API-Key)")
    output_dir.mkdir(parents=True, exist_ok=True)
    result: list[Path] = []
    timeout = httpx.Timeout(float(getattr(settings, "fastgen_http_timeout_sec", 600) or 600))
    async with httpx.AsyncClient(timeout=timeout) as client:
        for i, (prompt, ref_idx) in enumerate(steps):
            if _cancel_requested(cancel_event):
                raise FastGenCancelled()
            full_prompt = prepare_fastgen_prompt_for_image(prompt)
            ok = False
            for _ in range(max(1, settings.fastgen_max_attempts)):
                if _cancel_requested(cancel_event):
                    raise FastGenCancelled()
                try:
                    async with async_fastgen_global_media_slot():
                        if ref_idx is None:

                            def _b(cur: str) -> dict[str, Any]:
                                return _v2_image_body_generate(cur)

                            rjson = await _post_v2_images_resilient(client, full_prompt, _b)
                        else:
                            if ref_idx < 0 or ref_idx >= len(result):
                                raise ValueError(f"bad ref_idx {ref_idx} len={len(result)}")
                            inp = await _image_input_for_path(client, result[ref_idx])

                            def _b(cur: str) -> dict[str, Any]:
                                return _v2_image_body_transform(cur, inp)

                            rjson = await _post_v2_images_resilient(client, full_prompt, _b)
                        dest = _unique_frame_dest(output_dir, str(i))
                        dest.write_bytes(_decode_data_uri(rjson["result"]))
                        result.append(dest)
                    ok = True
                    break
                except FastGenCancelled:
                    raise
                except Exception as e:
                    logger.warning(f"[FastGen HTTP] chain step {i} retry: {e}")
                await asyncio.sleep(1.5)
            if not ok:
                raise RuntimeError(f"[FastGen HTTP] chain failed at step {i}")
            await asyncio.sleep(0.2)
    return result


async def generate_images_chain_from_seed_fastgen(
    seed_image: Path | str,
    steps: list[tuple[str, int]],
    output_dir: Path,
    cancel_event: threading.Event | None = None,
) -> list[Path]:
    _require_base()
    if not _api_key():
        raise RuntimeError("FASTGEN_API_KEY required for HTTP API (X-API-Key)")
    output_dir.mkdir(parents=True, exist_ok=True)
    chain: list[Path] = [Path(seed_image).resolve()]
    generated: list[Path] = []
    timeout = httpx.Timeout(float(getattr(settings, "fastgen_http_timeout_sec", 600) or 600))
    async with httpx.AsyncClient(timeout=timeout) as client:
        for i, (prompt, ref_idx) in enumerate(steps):
            if _cancel_requested(cancel_event):
                raise FastGenCancelled()
            if ref_idx < 0 or ref_idx >= len(chain):
                raise ValueError(f"Invalid ref_idx {ref_idx} for chain len {len(chain)}")
            ref_path = chain[ref_idx]
            full_prompt = prepare_fastgen_prompt_for_image(prompt)
            ok = False
            for _ in range(max(1, settings.fastgen_max_attempts)):
                if _cancel_requested(cancel_event):
                    raise FastGenCancelled()
                try:
                    async with async_fastgen_global_media_slot():
                        inp = await _image_input_for_path(client, ref_path)

                        def _b(cur: str) -> dict[str, Any]:
                            return _v2_image_body_transform(cur, inp)

                        rjson = await _post_v2_images_resilient(client, full_prompt, _b)
                        dest = _unique_frame_dest(output_dir, str(200 + i))
                        dest.write_bytes(_decode_data_uri(rjson["result"]))
                        chain.append(dest)
                        generated.append(dest)
                    ok = True
                    break
                except FastGenCancelled:
                    raise
                except Exception as e:
                    logger.warning(f"[FastGen HTTP] from-seed step {i + 1} retry: {e}")
                await asyncio.sleep(1.5)
            if not ok:
                raise RuntimeError(f"[FastGen HTTP] From-seed step {i + 1} failed: no image")
            await asyncio.sleep(0.2)
    return generated


async def generate_videos_fastgen(
    prompts: list[str],
    output_dir: Path,
    reference_image_path: str | Path | None = None,
    cancel_event: threading.Event | None = None,
    *,
    mode4_veo_flow_flower: bool = False,
) -> list[Path | None]:
    _require_base()
    if not _api_key():
        raise RuntimeError("FASTGEN_API_KEY required for HTTP API (X-API-Key)")
    output_dir.mkdir(parents=True, exist_ok=True)
    ref: Path | None = Path(reference_image_path) if reference_image_path else None
    refs_single = [ref] if ref and ref.exists() else None
    workers = min(len(prompts), max(1, int(getattr(settings, "fastgen_video_parallel_workers", 10) or 10)))
    sem = asyncio.Semaphore(workers)
    timeout = httpx.Timeout(float(getattr(settings, "fastgen_http_timeout_sec", 600) or 600))

    async def bounded(i: int, pr: str) -> Path | None:
        async with sem:
            async with httpx.AsyncClient(timeout=timeout) as client:
                for _ in range(max(1, settings.fastgen_max_attempts)):
                    try:
                        r = await _generate_one_video(
                            client, pr, output_dir, i, refs_single, cancel_event, mode4_veo_flow_flower=mode4_veo_flow_flower
                        )
                        if r:
                            return r
                    except (FastGenCancelled, asyncio.CancelledError):
                        raise
                    except Exception as e:
                        logger.warning(f"[FastGen HTTP] video {i} retry: {e}")
                    await asyncio.sleep(2.0)
                return None

    return list(await asyncio.gather(*[bounded(i, prompts[i]) for i in range(len(prompts))]))


async def generate_single_video_fastgen(
    prompt: str,
    output_dir: Path,
    index: int,
    reference_image_path: str | Path | None = None,
    *,
    reference_image_paths: list[str | Path] | None = None,
    cancel_event: threading.Event | None = None,
    mode4_veo_flow_flower: bool = False,
    video_aspect_ratio: str | None = None,
) -> Path | None:
    _require_base()
    if not _api_key():
        raise RuntimeError("FASTGEN_API_KEY required for HTTP API (X-API-Key)")
    paths: list[Path] | None = None
    if reference_image_paths:
        paths = [Path(p) for p in reference_image_paths if p and Path(p).exists()]
        if not paths:
            paths = None
    elif reference_image_path:
        p = Path(reference_image_path)
        paths = [p] if p.exists() else None
    timeout = httpx.Timeout(float(getattr(settings, "fastgen_http_timeout_sec", 600) or 600))
    async with httpx.AsyncClient(timeout=timeout) as client:
        for _ in range(max(1, settings.fastgen_max_attempts)):
            try:
                r = await _generate_one_video(
                    client,
                    prompt,
                    output_dir,
                    index,
                    paths,
                    cancel_event,
                    mode4_veo_flow_flower=mode4_veo_flow_flower,
                    video_aspect_ratio=video_aspect_ratio,
                )
                if r:
                    return r
            except (FastGenCancelled, asyncio.CancelledError):
                raise
            except Exception as e:
                logger.warning(f"[FastGen HTTP] single video retry: {e}")
            await asyncio.sleep(2.0)
    return None


async def generate_videos_fastgen_multi_ref(
    prompts: list[str],
    output_dir: Path,
    reference_image_paths: list[Path],
) -> list[Path | None]:
    _require_base()
    if not _api_key():
        raise RuntimeError("FASTGEN_API_KEY required for HTTP API (X-API-Key)")
    refs = [p for p in reference_image_paths if p.exists()]
    workers = min(len(prompts), max(1, int(getattr(settings, "fastgen_video_parallel_workers", 10) or 10)))
    sem = asyncio.Semaphore(workers)
    timeout = httpx.Timeout(float(getattr(settings, "fastgen_http_timeout_sec", 600) or 600))

    async def bounded(i: int, pr: str) -> Path | None:
        async with sem:
            async with httpx.AsyncClient(timeout=timeout) as client:
                return await _generate_one_video(client, pr, output_dir, i, refs, None)

    return list(await asyncio.gather(*[bounded(i, prompts[i]) for i in range(len(prompts))]))


async def generate_single_video_multi_ref(
    index: int,
    prompt: str,
    output_dir: Path,
    reference_image_paths: list[Path],
) -> Path | None:
    _require_base()
    if not _api_key():
        raise RuntimeError("FASTGEN_API_KEY required for HTTP API (X-API-Key)")
    refs = [p for p in reference_image_paths if p.exists()]
    timeout = httpx.Timeout(float(getattr(settings, "fastgen_http_timeout_sec", 600) or 600))
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await _generate_one_video(client, prompt, output_dir, index, refs, None)


async def generate_video_from_keyframes(
    prompt: str,
    output_dir: Path,
    start_frame_path: Path,
    end_frame_path: Path,
    index: int = 0,
    *,
    cancel_event: threading.Event | None = None,
    video_aspect_ratio: str | None = None,
) -> Path | None:
    _require_base()
    if not _api_key():
        raise RuntimeError("FASTGEN_API_KEY required for HTTP API (X-API-Key)")
    timeout = httpx.Timeout(float(getattr(settings, "fastgen_http_timeout_sec", 600) or 600))
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await _generate_one_video(
            client,
            prompt,
            output_dir,
            index,
            None,
            cancel_event,
            mode4_veo_flow_flower=False,
            keyframes=True,
            start_frame=Path(start_frame_path),
            end_frame=Path(end_frame_path),
            video_aspect_ratio=video_aspect_ratio,
        )
