"""
Mode 5 Video Assembler — длинное видео: изображение + озвучка по сегментам.
Без субтитров. Плавные переходы между сегментами.
"""

from __future__ import annotations

import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np
from loguru import logger
from moviepy import (
    AudioFileClip,
    VideoClip,
    VideoFileClip,
    concatenate_audioclips,
    concatenate_videoclips,
)
from PIL import Image, ImageDraw

from agents.video_editor.subtitles import render_subtitle_overlay
from agents.video_editor.fonts import load_ui_font
from config import settings
from utils.ffmpeg_resolve import resolve_ffmpeg_executable


# Cinematic pan-only motion patterns (no zoom animation).
# Each tuple:
#   (pan_x_start, pan_x_end, pan_y_start, pan_y_end)
#
# pan_x is crop center in [0..1]:
#   0.5 = centered, <0.5 = left, >0.5 = right.
_MOTION_PATTERNS: list[tuple[float, float, float, float]] = [
    # One-way horizontal drift across each segment (faster, no direction flip jerk).
    (0.12, 0.88, 0.50, 0.50),
]

_MIN_SEGMENT_AUDIO_SEC = 0.25


def _smoothstep(x: float) -> float:
    x = max(0.0, min(1.0, x))
    # Smootherstep: zero 1st derivative at endpoints (more fluid dissolve).
    return x * x * x * (x * (6.0 * x - 15.0) + 10.0)


def _make_crossfade(clip_a: VideoClip, clip_b: VideoClip, duration: float, fps: int) -> VideoClip:
    dur_a = float(clip_a.duration)
    dur_b = float(clip_b.duration)
    half = duration / 2.0

    def make_frame(t: float) -> np.ndarray:
        raw = t / duration if duration > 0 else 1.0
        alpha = _smoothstep(raw)
        half_a = min(half, dur_a)
        half_b = min(half, dur_b)
        ta = max(0.0, dur_a - half_a) + raw * half_a
        tb = raw * half_b
        fa = clip_a.get_frame(ta).astype(np.float32)
        fb = clip_b.get_frame(tb).astype(np.float32)
        return ((1.0 - alpha) * fa + alpha * fb).astype(np.uint8)

    return VideoClip(make_frame, duration=duration).with_fps(fps)


def _assemble_with_crossfades_visual(clips: list[VideoClip], t: float, fps: int) -> VideoClip:
    """Assemble visual track with smooth dissolve transitions."""
    if len(clips) == 1 or t <= 0:
        return concatenate_videoclips(clips, method="compose")

    half = t / 2.0
    parts: list[VideoClip] = []
    for i, clip in enumerate(clips):
        is_first, is_last = i == 0, i == len(clips) - 1
        t_start = 0.0 if is_first else half
        # Non-overlapped part: first clip starts at 0, others start at `half`;
        # non-last clips end at `dur - half` so the overlap is reserved for crossfade.
        t_end = clip.duration if is_last else (clip.duration - half)
        t_end = min(t_end, clip.duration)
        t_start = min(t_start, t_end)
        # Avoid zero/negative-length subclips.
        if t_end > t_start + 1e-3:
            parts.append(clip.subclipped(t_start, t_end))
        if not is_last:
            parts.append(_make_crossfade(clip, clips[i + 1], t, fps))
    return concatenate_videoclips(parts, method="compose")


def _wav_duration_sec(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
    if rate <= 0:
        raise ValueError(f"Invalid WAV framerate: {path}")
    return frames / float(rate)


def _alpha_blend_rgb(base: np.ndarray, overlay_rgba: np.ndarray) -> np.ndarray:
    if overlay_rgba.shape[-1] != 4:
        return base
    base_rgb = base[..., :3].astype(np.float32)
    over_rgb = overlay_rgba[..., :3].astype(np.float32)
    alpha = (overlay_rgba[..., 3:4].astype(np.float32) / 255.0)
    blended = base_rgb * (1.0 - alpha) + over_rgb * alpha
    return np.clip(blended, 0, 255).astype(np.uint8)


def _with_static_subtitle(
    clip: VideoFileClip,
    subtitle_text: str,
    target_w: int,
    target_h: int,
) -> VideoClip:
    text = (subtitle_text or "").strip()
    if not text:
        return clip
    duration = float(clip.duration or 0.0)
    fps = int(clip.fps or 60)

    def make_frame(t: float) -> np.ndarray:
        frame = clip.get_frame(t)
        overlay = render_subtitle_overlay(
            text,
            target_w,
            target_h,
            t,
            duration,
            karaoke=False,
            static_font_divisor=18,
        )
        return _alpha_blend_rgb(frame, overlay)

    wrapped = VideoClip(make_frame, duration=duration).with_fps(fps)
    if clip.audio is not None:
        wrapped = wrapped.with_audio(clip.audio)
    setattr(wrapped, "_source_clip", clip)
    return wrapped


def _with_top_label(
    clip: VideoFileClip,
    label_text: str,
    target_w: int,
    target_h: int,
) -> VideoClip:
    text = (label_text or "").strip()
    if not text:
        return clip
    duration = float(clip.duration or 0.0)
    fps = int(clip.fps or 60)
    font_size = max(34, int(target_h / 12))
    font = load_ui_font(font_size, bold=True)
    pad_y = max(24, int(target_h * 0.035))
    pad_x = max(20, int(target_w * 0.03))

    def make_frame(t: float) -> np.ndarray:
        frame = clip.get_frame(t)
        rgba = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(rgba)
        bb = draw.textbbox((0, 0), text, font=font, stroke_width=4)
        tw = max(1, bb[2] - bb[0])
        th = max(1, bb[3] - bb[1])
        box_w = tw + pad_x * 2
        box_h = th + pad_y // 2
        x0 = (target_w - box_w) // 2
        y0 = pad_y
        draw.rounded_rectangle((x0, y0, x0 + box_w, y0 + box_h), radius=18, fill=(0, 0, 0, 128))
        tx = x0 + pad_x
        ty = y0 + (box_h - th) // 2 - bb[1]
        draw.text(
            (tx, ty),
            text,
            font=font,
            fill=(245, 248, 255, 255),
            stroke_width=4,
            stroke_fill=(10, 14, 24, 235),
        )
        return _alpha_blend_rgb(frame, np.array(rgba))

    wrapped = VideoClip(make_frame, duration=duration).with_fps(fps)
    if clip.audio is not None:
        wrapped = wrapped.with_audio(clip.audio)
    setattr(wrapped, "_source_clip", clip)
    return wrapped


def _make_segment_clip_static_still(
    image_path: Path,
    audio_path: Path,
    target_w: int,
    target_h: int,
    render_fps: int,
) -> VideoFileClip:
    """
    Один неподвижный кадр на всю длительность аудио (без zoompan).
    Быстрее и визуально ровнее для «50 фактов»: на экране одно изображение без дрейфа.
    """
    ffmpeg = resolve_ffmpeg_executable()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found for mode5 static render")

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        temp_out = Path(tmp.name)

    duration = _wav_duration_sec(audio_path)
    vf = (
        f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black,"
        "format=yuv420p"
    )
    cmd = [
        ffmpeg,
        "-y",
        "-loop",
        "1",
        "-i",
        str(image_path),
        "-t",
        f"{duration:.6f}",
        "-vf",
        vf,
        "-r",
        str(render_fps),
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-pix_fmt",
        "yuv420p",
        str(temp_out),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=3600)
        return VideoFileClip(str(temp_out))
    except subprocess.CalledProcessError as exc:
        temp_out.unlink(missing_ok=True)
        stderr = (exc.stderr or "").strip()
        raise RuntimeError(f"FFmpeg mode5 static render failed: {stderr or exc}") from exc
    except Exception:
        temp_out.unlink(missing_ok=True)
        raise


def _make_segment_clip(
    image_path: Path,
    audio_path: Path,
    target_w: int,
    target_h: int,
    render_fps: int,
    pattern_index: int,
    *,
    static_still: bool = False,
) -> VideoFileClip:
    """
    Одна сцена через FFmpeg (БЕЗ аудио на клипе — аудио подмешивается в assemble).

    static_still: без zoompan, один замороженный кадр (режим 50 фактов).
    Иначе — zoompan с опциональным медленным pan (MODE5_ENABLE_ZOOM).
    """
    if static_still:
        return _make_segment_clip_static_still(
            image_path, audio_path, target_w, target_h, render_fps
        )

    ffmpeg = resolve_ffmpeg_executable()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found for smooth mode5 motion rendering")

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        temp_out = Path(tmp.name)

    use_motion = bool(getattr(settings, "mode5_enable_zoom", False))
    if use_motion:
        panx0, panx1, pany0, pany1 = _MOTION_PATTERNS[pattern_index % len(_MOTION_PATTERNS)]
    else:
        panx0, panx1, pany0, pany1 = (0.5, 0.5, 0.5, 0.5)
    duration = _wav_duration_sec(audio_path)
    total_frames = max(2, int(round(duration * render_fps)))
    # Use smoothstep easing so movement has zero velocity at segment endpoints.
    denom = max(1, total_frames - 1)
    target_aspect = target_w / float(target_h)
    upscale_w = 5000
    upscale_h = 2812
    scale_expr = (
        f"scale='if(gte(a,{target_aspect}),{upscale_w},-1)':"
        f"'if(gte(a,{target_aspect}),-1,{upscale_h})':flags=lanczos"
    )

    # progress in [0..1]
    r_expr = f"(on/{denom:.1f})"
    # Linear phase gives constant velocity (no micro-acceleration/deceleration).
    ease_expr = r_expr

    # For pan to be visible, zoompan needs an overscanned canvas (>1.0).
    # Keep it constant over time (no zoom animation), so we get pure smooth pan.
    zoom_expr = "1.100000"

    # Smooth pan fractions.
    panx_expr = f"{panx0:.6f} + ({panx1:.6f}-{panx0:.6f})*{ease_expr}"
    pany_expr = f"{pany0:.6f} + ({pany1:.6f}-{pany0:.6f})*{ease_expr}"

    # zoompan x/y are top-left coords. We start from centered crop and shift
    # horizontally/vertically by a fraction of the available zoomed-in area.
    x_expr = (
        "iw/2-(iw/zoom/2) + (iw - iw/zoom)*("
        f"{panx_expr}-0.5)"
    )
    y_expr = (
        "ih/2-(ih/zoom/2) + (ih - ih/zoom)*("
        f"{pany_expr}-0.5)"
    )

    # Expressions are safe even when motion is disabled because panx is centered.
    vf = (
        f"{scale_expr},"
        f"zoompan=z='{zoom_expr}':"
        f"x='{x_expr}':"
        f"y='{y_expr}':"
        f"d={total_frames}:s={target_w}x{target_h}:fps={render_fps},"
        "format=yuv420p[v]"
    )
    cmd = [
        ffmpeg,
        "-y",
        "-loop",
        "1",
        "-i",
        str(image_path),
        "-t",
        f"{duration:.6f}",
        "-filter_complex",
        vf,
        "-map",
        "[v]",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(render_fps),
        str(temp_out),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=3600)
        return VideoFileClip(str(temp_out))
    except subprocess.CalledProcessError as exc:
        temp_out.unlink(missing_ok=True)
        stderr = (exc.stderr or "").strip()
        raise RuntimeError(f"FFmpeg mode5 motion render failed: {stderr or exc}") from exc
    except Exception:
        temp_out.unlink(missing_ok=True)
        raise


def assemble_mode5_video(
    segment_data: list[tuple[Path, Path]],
    output_path: Path,
    subtitle_texts: list[str] | None = None,
    top_labels: list[str] | None = None,
    *,
    facts50_static_still: bool = False,
) -> Path:
    """
    Собирает длинное видео из сегментов (image + audio).
    segment_data: list of (image_path, audio_path)

    facts50_static_still: для «50 фактов» — неподвижный кадр и ниже FPS (быстрее кодирование).
    """
    target_w, target_h = settings.mode5_video_resolution
    if facts50_static_still and bool(getattr(settings, "mode5_facts50_static_still", True)):
        # Статичная картинка: 30 fps достаточно; быстрее, чем 60 fps zoompan.
        render_fps = max(24, min(30, int(settings.video_fps or 24)))
    else:
        # Движение zoompan: выше FPS снижает микродрожание.
        render_fps = max(int(settings.video_fps or 24), 60)
    transition_sec = max(0.0, min(1.2, float(getattr(settings, "mode5_transition_sec", 0.6) or 0.6)))
    use_static = bool(facts50_static_still and getattr(settings, "mode5_facts50_static_still", True))

    clips: list[VideoFileClip] = []
    audio_clips: list[AudioFileClip] = []
    temp_paths: list[Path] = []
    clip_durations: list[float] = []
    subtitle_texts = subtitle_texts or []
    top_labels = top_labels or []
    for i, (img_path, audio_path) in enumerate(segment_data):
        if not img_path.exists() or not audio_path.exists():
            logger.warning(f"[Mode5] Skip missing: {img_path} or {audio_path}")
            continue
        seg_dur = _wav_duration_sec(audio_path)
        if seg_dur < _MIN_SEGMENT_AUDIO_SEC:
            logger.warning(
                f"[Mode5] Skip tiny segment {audio_path.name}: {seg_dur:.3f}s < {_MIN_SEGMENT_AUDIO_SEC:.2f}s"
            )
            continue
        base_clip = _make_segment_clip(
            img_path,
            audio_path,
            target_w,
            target_h,
            render_fps,
            i,
            static_still=use_static,
        )
        clip = _with_static_subtitle(
            base_clip,
            subtitle_texts[i] if i < len(subtitle_texts) else "",
            target_w,
            target_h,
        )
        clip = _with_top_label(
            clip,
            top_labels[i] if i < len(top_labels) else "",
            target_w,
            target_h,
        )
        # Критично: держим аудио отдельным клипом и кодируем один раз только в финале.
        # Так убираются регулярные стыки/провалы каждые ~30с из-за повторного AAC на каждом сегменте.
        seg_audio = AudioFileClip(str(audio_path))
        clip = clip.with_audio(seg_audio)
        clips.append(clip)
        audio_clips.append(seg_audio)
        temp_paths.append(Path(base_clip.filename))
        clip_durations.append(seg_dur)

    if not clips:
        raise ValueError("[Mode5] No valid segments to assemble")

    logger.info(
        f"[Mode5] Assembling {len(clips)} segments → {output_path} "
        f"({'static still' if use_static else 'zoompan motion=' + ('on' if bool(getattr(settings, 'mode5_enable_zoom', False)) else 'off')} "
        f"{'' if use_static else f'pan_x={_MOTION_PATTERNS[0][0]:.2f}->{_MOTION_PATTERNS[0][1]:.2f}, '}"
        f"{'' if use_static else f'pan_y={_MOTION_PATTERNS[0][2]:.2f}->{_MOTION_PATTERNS[0][3]:.2f}, '}"
        f"fps={render_fps}, transition={transition_sec:.2f}s)"
    )
    effective_transition = transition_sec
    if len(clip_durations) >= 2 and transition_sec > 0:
        # Keep dissolve safely below short segment durations to avoid MoviePy frame-range errors.
        shortest = min(clip_durations)
        effective_transition = min(transition_sec, max(0.0, shortest * 0.45))
    if effective_transition < 0.05:
        effective_transition = 0.0

    if len(clips) == 1:
        final = clips[0]
    else:
        if effective_transition > 0:
            visual_clips = [c.without_audio() for c in clips]
            final = _assemble_with_crossfades_visual(visual_clips, effective_transition, render_fps)
            # Аудио — строго подряд, без overlap (чтобы не было «эха»/дублей на границах).
            merged_audio = concatenate_audioclips(audio_clips)
            final = final.with_audio(merged_audio)
        else:
            final = concatenate_videoclips(clips, method="compose")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        final.write_videofile(
            str(output_path),
            fps=render_fps,
            codec="libx264",
            audio_codec="aac",
            threads=4,
            preset="medium",
            logger=None,
        )
    finally:
        final.close()
        for c in clips:
            try:
                c.close()
            except Exception:
                pass
            src = getattr(c, "_source_clip", None)
            if src is not None:
                try:
                    src.close()
                except Exception:
                    pass
        for a in audio_clips:
            try:
                a.close()
            except Exception:
                pass
        for p in temp_paths:
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass

    logger.success(f"[Mode5] Done → {output_path}")
    return output_path
