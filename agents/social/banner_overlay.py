"""FFmpeg overlay: banner image/video in a corner (from CAS banner.py)."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

CORNER_KEYS = frozenset({"tr", "tl", "br", "bl", "mr", "ml"})

_CORNER_EXPR = {
    "tr": "W-w-{m}:{m}",
    "tl": "{m}:{m}",
    "br": "W-w-{m}:H-h-{m}",
    "bl": "{m}:H-h-{m}",
    "mr": "W-w-{m}:(H-h)/2",
    "ml": "{m}:(H-h)/2",
}


def is_valid_corner(corner: str) -> bool:
    return corner in CORNER_KEYS


def _overlay_position(corner: str, margin: int) -> str:
    if corner not in _CORNER_EXPR:
        raise ValueError(f"corner must be one of {list(_CORNER_EXPR)}, got {corner!r}")
    return _CORNER_EXPR[corner].format(m=margin)


def overlay_banner(
    input_video: Path | str,
    banner: Path | str,
    output_video: Path | str,
    *,
    corner: str = "tr",
    margin: int = 10,
    banner_width: int | None = 200,
    video_codec: str = "libx264",
    audio_codec: str = "aac",
    crf: int = 20,
    audio_bitrate: str = "192k",
    banner_is_video: bool = False,
    strip_overlay_black: bool = True,
    overlay_black_similarity: float = 0.08,
    overlay_black_blend: float = 0.02,
) -> Path:
    inp = Path(input_video)
    ban = Path(banner)
    out = Path(output_video)
    out.parent.mkdir(parents=True, exist_ok=True)

    xy = _overlay_position(corner, margin)

    sim = float(overlay_black_similarity)
    blend = float(overlay_black_blend)
    if not (0.0 <= sim <= 1.0 and 0.0 <= blend <= 1.0):
        raise ValueError("overlay_black_similarity and overlay_black_blend must be between 0 and 1")

    if banner_width and banner_width > 0:
        banner_chain = f"[1:v]scale={banner_width}:-1"
    else:
        banner_chain = "[1:v]"
    if banner_is_video and strip_overlay_black:
        banner_chain += f",colorkey=0x000000:{sim:g}:{blend:g}"
    banner_chain += "[b];"
    filter_chain = f"{banner_chain}[0:v][b]overlay={xy}"

    if banner_is_video:
        # Loop banner to main length; overlay shortest=1 then ends with the main video (not with one banner pass).
        filter_chain += ":shortest=1"
    filter_chain += ":format=auto[v]"

    cmd: list[str] = [
        "ffmpeg",
        "-y",
        "-i",
        str(inp),
    ]
    if banner_is_video:
        cmd.extend(["-stream_loop", "-1"])
    cmd.extend(
        [
            "-i",
            str(ban),
            "-filter_complex",
            filter_chain,
            "-map",
            "[v]",
            "-map",
            "0:a?",
            "-c:v",
            video_codec,
            "-crf",
            str(crf),
            "-c:a",
            audio_codec,
            "-b:a",
            audio_bitrate,
            "-movflags",
            "+faststart",
            str(out),
        ]
    )
    logger.debug("ffmpeg %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.error("ffmpeg stderr: %s", proc.stderr)
        raise RuntimeError(f"ffmpeg failed (code {proc.returncode}): {proc.stderr[-2000:]}")

    if not out.is_file():
        raise FileNotFoundError(f"Expected output missing: {out}")
    return out


def ffmpeg_available() -> bool:
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            check=True,
            timeout=10,
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
