"""yt-dlp options builder (from CAS download.py)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_ydl_opts(
    out_dir: Path | str,
    *,
    cookiefile: str | None = None,
    cookies_from_browser: tuple[str, ...] | None = None,
    quiet: bool = False,
    extra_http_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tmpl = str(out / "%(extractor)s_%(id)s.%(ext)s")
    opts: dict[str, Any] = {
        "outtmpl": {"default": tmpl},
        "merge_output_format": "mp4",
        "retries": 10,
        "fragment_retries": 10,
        "noprogress": quiet,
        "quiet": quiet,
        "no_warnings": quiet,
        "format": "bv*+ba/b",
    }
    if cookiefile:
        opts["cookiefile"] = cookiefile
    if cookies_from_browser:
        opts["cookiesfrombrowser"] = cookies_from_browser
    headers: dict[str, str] = {}
    if extra_http_headers:
        headers.update(extra_http_headers)
    if headers:
        opts["http_headers"] = headers
    return opts
