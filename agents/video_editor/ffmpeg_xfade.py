"""
Chain MP4 segments with FFmpeg ``xfade`` (video) + ``acrossfade`` (audio).

Used when ``VIDEO_TRANSITION_ENGINE=xfade`` for Shorts-style transitions
(slide, zoom, smooth, …). Requires ``ffmpeg`` on PATH.

Enhanced with video-processing-editing skill best practices:
- Color space normalization (BT.709)
- Optimized encoding settings for social media
- Proper audio crossfade with triangular curves
- Faststart for web streaming
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Safe presets (all supported by typical FFmpeg 4.2+ builds)
XFADE_PRESETS = frozenset({
    "fade",
    "dissolve",
    "slideleft",
    "slideright",
    "slideup",
    "slidedown",
    "wipeleft",
    "wiperight",
    "zoomin",
    "smoothleft",
    "smoothright",
    "circleopen",
    "radial",
})


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _xfade_offsets(durations: list[float], t: float) -> list[float]:
    """Offset argument for each xfade step (see FFmpeg xfade docs)."""
    if len(durations) < 2:
        return []
    t = max(0.05, min(t, min(durations) * 0.45))
    offs: list[float] = []
    merged = durations[0]
    for i in range(len(durations) - 1):
        offs.append(max(0.01, merged - t))
        merged += durations[i + 1] - t
    return offs


def _sanitize_transition(name: str) -> str:
    n = name.strip().lower()
    return n if n in XFADE_PRESETS else "fade"


def merge_segments_xfade(
    segment_paths: list[Path],
    durations: list[float],
    transitions: list[str],
    t: float,
    output_path: Path,
) -> bool:
    """
    Concatenate N segments with per-edge xfade transitions.

    ``transitions`` length must be ``N - 1``; names are sanitised to known presets.
    """
    n = len(segment_paths)
    if n == 0:
        return False
    if n != len(durations):
        raise ValueError("durations length must match segment_paths")
    if n == 1:
        shutil.copy2(segment_paths[0], output_path)
        return True
    if len(transitions) != n - 1:
        raise ValueError("transitions must have length N-1")

    if not ffmpeg_available():
        logger.warning("[xfade] ffmpeg not found on PATH")
        return False

    t_eff = max(0.05, min(t, min(durations) * 0.45))
    offsets = _xfade_offsets(durations, t_eff)

    parts_v: list[str] = []
    parts_a: list[str] = []
    cur_v, cur_a = "0:v", "0:a"
    for i in range(n - 1):
        nxt_v, nxt_a = f"{i + 1}:v", f"{i + 1}:a"
        tr = _sanitize_transition(transitions[i])
        off = offsets[i]
        if i < n - 2:
            lab_v, lab_a = f"v{i}", f"a{i}"
        else:
            lab_v, lab_a = "vout", "aout"
        parts_v.append(
            f"[{cur_v}][{nxt_v}]xfade=transition={tr}:duration={t_eff:.4f}:offset={off:.4f}[{lab_v}]"
        )
        parts_a.append(
            f"[{cur_a}][{nxt_a}]acrossfade=d={t_eff:.4f}:c1=tri:c2=tri[{lab_a}]"
        )
        cur_v, cur_a = lab_v, lab_a

    fc = ";".join(parts_v + parts_a)
    cmd = ["ffmpeg", "-y"]
    for p in segment_paths:
        cmd.extend(["-i", str(p.resolve())])
    # Platform-optimized export settings from video-processing-editing skill
    cmd.extend(
        [
            "-filter_complex",
            fc,
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            # Video encoding: H.264 with balanced quality/speed
            "-c:v",
            "libx264",
            "-preset",
            "medium",  # Balance between speed and quality (was "fast")
            "-crf",
            "18",  # High quality (was 20)
            # Color space: BT.709 for broad compatibility
            "-pix_fmt",
            "yuv420p",
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            "-colorspace",
            "bt709",
            # Audio: AAC with good quality for voice+music
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",  # Standard sample rate
            # Faststart for web streaming
            "-movflags",
            "+faststart",
            str(output_path.resolve()),
        ]
    )

    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,
            check=False,
        )
        if r.returncode != 0:
            logger.warning("[xfade] ffmpeg failed: %s", (r.stderr or r.stdout)[-800:])
            return False
        return True
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.warning("[xfade] ffmpeg error: %s", e)
        return False


def cycle_transitions(pattern: list[str], count: int) -> list[str]:
    """Build ``count`` transition names by cycling ``pattern``."""
    if not pattern:
        return ["fade"] * count
    return [pattern[i % len(pattern)] for i in range(count)]
