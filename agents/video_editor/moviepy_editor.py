"""
Video assembly with MoviePy 2.x.

v3 additions (viral-optimised):
  - Sound effects: boom on opening, whoosh on transitions, impact on key reveals
  - Hook banner: large animated text overlay on the first 3 s of scene 1
  - Channel watermark in the top-left corner on all scene clips
  - Subtitles: pill + optional karaoke; design tokens + Inter font
  - Transitions: MoviePy dissolve (default) or FFmpeg xfade presets (optional)
"""

from __future__ import annotations

import random
import shutil
import tempfile
from pathlib import Path
from typing import NamedTuple

import numpy as np
from loguru import logger

from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    VideoClip,
    VideoFileClip,
    concatenate_audioclips,
    concatenate_videoclips,
)
from moviepy import afx
from moviepy.audio.AudioClip import AudioArrayClip
from PIL import Image, ImageDraw, ImageEnhance

from agents.video_editor import design_tokens as dt
from agents.video_editor.ffmpeg_xfade import (
    cycle_transitions,
    ffmpeg_available,
    merge_segments_xfade,
)
from agents.video_editor.fonts import load_ui_font
from agents.video_editor.sound_effects import SoundEffects
from agents.video_editor.subtitles import render_subtitle_overlay
from agents.video_editor.music_gen import generate_background_music
from config import settings

try:
    import pyphen as _pyphen
    _RU_HYPHENATOR = _pyphen.Pyphen(lang="ru_RU")
except Exception:
    _RU_HYPHENATOR = None

# Use OpenCV for fast per-frame resize if available; fall back to Pillow
try:
    import cv2 as _cv2
    def _fast_resize(arr: np.ndarray, w: int, h: int) -> np.ndarray:
        return _cv2.resize(arr, (w, h), interpolation=_cv2.INTER_LINEAR)
except ImportError:
    def _fast_resize(arr: np.ndarray, w: int, h: int) -> np.ndarray:  # type: ignore[misc]
        return np.array(Image.fromarray(arr).resize((w, h), Image.BILINEAR))


# ─────────────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────────────

class SceneData(NamedTuple):
    image_path: str
    subtitle_text: str
    audio_path: str | None


# ─────────────────────────────────────────────────────────────────────────────
# Color grading & vignette
# ─────────────────────────────────────────────────────────────────────────────

def _color_grade(img: Image.Image) -> Image.Image:
    """
    Apply cinematic color grading optimized for social media.
    Based on video-processing-editing best practices.
    """
    # Subtle contrast boost for depth (1.12 → 1.08 for more natural look)
    img = ImageEnhance.Contrast(img).enhance(1.08)
    # Vibrance boost without oversaturation (1.20 → 1.15)
    img = ImageEnhance.Color(img).enhance(1.15)
    # Slight brightness lift for mobile screens (1.03 → 1.05)
    img = ImageEnhance.Brightness(img).enhance(1.05)
    # Sharpness enhancement for crisp text and details
    img = ImageEnhance.Sharpness(img).enhance(1.10)
    return img


def _apply_vignette(arr: np.ndarray, strength: float = 0.40) -> np.ndarray:
    h, w = arr.shape[:2]
    Y, X = np.ogrid[:h, :w]
    cx, cy = w / 2, h / 2
    dist = np.sqrt(((X - cx) / (w * 0.65)) ** 2 + ((Y - cy) / (h * 0.65)) ** 2)
    mask = np.clip(1.0 - strength * (dist ** 1.5), 0.0, 1.0)
    return (arr * mask[..., np.newaxis]).astype(np.uint8)


# ─────────────────────────────────────────────────────────────────────────────
# Font + audio helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_card_font(size: int):
    """Bold UI font (Inter from assets/fonts with fallback)."""
    return load_ui_font(size, bold=True)


def _ensure_stereo_audio(clip: VideoClip) -> VideoClip:
    """FFmpeg acrossfade needs an audio stream on every segment."""
    if clip.audio is not None:
        return clip
    dur = max(0.05, float(clip.duration or 0.1))
    sr = 44100
    n = max(1, int(dur * sr))
    arr = np.zeros((n, 2), dtype=np.float32)
    return clip.with_audio(AudioArrayClip(arr, fps=sr))


# ─────────────────────────────────────────────────────────────────────────────
# Image helpers
# ─────────────────────────────────────────────────────────────────────────────

def _resize_fill(img: Image.Image, w: int, h: int) -> Image.Image:
    ratio = max(w / img.width, h / img.height)
    nw, nh = int(img.width * ratio), int(img.height * ratio)
    img = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


# ─────────────────────────────────────────────────────────────────────────────
# Ken Burns — 8 motion styles
# ─────────────────────────────────────────────────────────────────────────────

_KB_STYLES = [
    "zoom_in", "zoom_out",
    "pan_left", "pan_right",
    "zoom_pan_lr", "zoom_pan_rl",
    "zoom_pan_diag_tl", "zoom_pan_diag_br",
]


def _ken_burns_clip(
    img_path: str,
    duration: float,
    target_w: int,
    target_h: int,
    fps: int,
    style: str = "zoom_in",
) -> VideoClip:
    pad = 1.15
    img = Image.open(img_path).convert("RGB")
    img = _resize_fill(img, int(target_w * pad), int(target_h * pad))
    img = _color_grade(img)
    arr = _apply_vignette(np.array(img))

    def _crop(p: float, cx: float, cy: float, zoom: float) -> np.ndarray:
        h, w = arr.shape[:2]
        view_w = int(target_w / zoom)
        view_h = int(target_h / zoom)
        # Use sub-pixel sampling to reduce jitter (int-only crop was quantizing movement).
        px, py = float(cx * w), float(cy * h)
        if "_cv2" in globals():
            # cv2.getRectSubPix keeps fractional center, returning a patch of (width, height).
            cropped = _cv2.getRectSubPix(arr, (view_w, view_h), (px, py))
        else:
            px_i, py_i = int(px), int(py)
            x0 = max(0, min(px_i - view_w // 2, w - view_w))
            y0 = max(0, min(py_i - view_h // 2, h - view_h))
            cropped = arr[y0 : y0 + view_h, x0 : x0 + view_w]

        # Resize to exact target size for consistent frame composition.
        return _fast_resize(cropped, target_w, target_h)

    def make_frame(t: float) -> np.ndarray:
        p = t / duration
        if   style == "zoom_in":          return _crop(p, 0.5, 0.5, 1.0 + 0.10 * p)
        elif style == "zoom_out":         return _crop(p, 0.5, 0.5, 1.10 - 0.10 * p)
        elif style == "pan_left":         return _crop(p, 0.60 - 0.20 * p, 0.5, 1.0)
        elif style == "pan_right":        return _crop(p, 0.40 + 0.20 * p, 0.5, 1.0)
        elif style == "zoom_pan_lr":      return _crop(p, 0.46 + 0.08 * p, 0.5, 1.0 + 0.08 * p)
        elif style == "zoom_pan_rl":      return _crop(p, 0.54 - 0.08 * p, 0.5, 1.0 + 0.08 * p)
        elif style == "zoom_pan_diag_tl": return _crop(p, 0.54 - 0.08 * p, 0.54 - 0.08 * p, 1.0 + 0.08 * p)
        elif style == "zoom_pan_diag_br": return _crop(p, 0.46 + 0.08 * p, 0.46 + 0.08 * p, 1.10 - 0.10 * p)
        else:                             return _crop(p, 0.5, 0.5, 1.0 + 0.10 * p)

    return VideoClip(make_frame, duration=duration).with_fps(fps)


# ─────────────────────────────────────────────────────────────────────────────
# Crossfade transition
# ─────────────────────────────────────────────────────────────────────────────

def _make_crossfade(clip_a: VideoClip, clip_b: VideoClip, duration: float, fps: int) -> VideoClip:
    dur_a = clip_a.duration
    dur_b = clip_b.duration

    def make_frame(t: float) -> np.ndarray:
        # MoviePy assembly trims each clip by `half = T/2` on both sides,
        # then inserts a crossfade of length `T`.
        # To avoid visible jumps, the crossfade must blend:
        #   clip_a: from (dur_a - half) -> dur_a
        #   clip_b: from 0 -> half
        # even though the crossfade segment itself lasts `T` seconds.
        alpha = t / duration if duration > 0 else 1.0
        half = duration / 2.0

        dur_a_f = float(dur_a)
        dur_b_f = float(dur_b)
        half_a = min(half, dur_a_f)
        half_b = min(half, dur_b_f)

        ta = max(0.0, dur_a_f - half_a) + alpha * half_a
        tb = alpha * half_b

        fa = clip_a.get_frame(ta).astype(np.float32)
        fb = clip_b.get_frame(tb).astype(np.float32)
        return ((1.0 - alpha) * fa + alpha * fb).astype(np.uint8)

    return VideoClip(make_frame, duration=duration).with_fps(fps)


def _assemble_with_crossfades(clips: list[VideoClip], T: float, fps: int) -> VideoClip:
    if len(clips) == 1 or T <= 0:
        return concatenate_videoclips(clips, method="compose")

    half = T / 2.0
    parts: list[VideoClip] = []

    for i, clip in enumerate(clips):
        is_first, is_last = i == 0, i == len(clips) - 1
        t_start = 0.0 if is_first else half
        t_end = clip.duration if is_last else max(clip.duration - half, half + 0.1)

        # Clamp to actual clip duration with a small safety margin
        t_end   = min(t_end,   clip.duration - 0.01)
        t_start = min(t_start, t_end - 0.05)

        if t_end > t_start + 0.05:
            # Strip audio before subclipping so that @apply_to_audio decorator
            # inside subclipped() doesn't try to apply the same end_time to the
            # audio clip (which may be shorter than the video clip).
            clip_audio = clip.audio
            clip_no_audio = clip.without_audio() if clip_audio is not None else clip
            trimmed = clip_no_audio.subclipped(t_start, t_end)
            if clip_audio is not None:
                aud_dur = clip_audio.duration if clip_audio.duration is not None else clip.duration
                a_start = min(t_start, max(0.0, aud_dur - 0.02))
                a_end   = min(t_end,   max(a_start + 0.01, aud_dur - 0.01))
                if a_end > a_start + 0.02:
                    trimmed = trimmed.with_audio(clip_audio.subclipped(a_start, a_end))
            parts.append(trimmed)

        if not is_last:
            parts.append(_make_crossfade(clip, clips[i + 1], T, fps))

    return concatenate_videoclips(parts, method="compose")


# ─────────────────────────────────────────────────────────────────────────────
# Gradient helpers
# ─────────────────────────────────────────────────────────────────────────────

def _gradient_bg(width: int, height: int, top: tuple, bottom: tuple) -> Image.Image:
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        r = int(top[0] + (bottom[0] - top[0]) * y / height)
        g = int(top[1] + (bottom[1] - top[1]) * y / height)
        b = int(top[2] + (bottom[2] - top[2]) * y / height)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    return img


def _draw_outlined_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font,
    fill: tuple,
    stroke_fill: tuple = (0, 0, 0),
    stroke_width: int = 3,
) -> None:
    draw.text(xy, text, font=font, fill=stroke_fill, stroke_width=stroke_width, stroke_fill=stroke_fill)
    draw.text(xy, text, font=font, fill=fill)


def _wrap_text_ru(
    text: str,
    *,
    draw: ImageDraw.ImageDraw,
    font,
    max_px: int,
) -> list[str]:
    """
    Wrap Russian text by words and, when needed, hyphenate long words.
    Never splits a word into raw chunks without a hyphen.
    """
    words = (text or "").split()
    if not words:
        return [text or ""]

    lines: list[str] = []
    current = ""

    def _w(s: str) -> int:
        bb = draw.textbbox((0, 0), s, font=font)
        return bb[2] - bb[0]

    def _hyphenate_word(word: str) -> list[str]:
        if _RU_HYPHENATOR is None:
            return [word]
        inserted = _RU_HYPHENATOR.inserted(word, hyphen="-")
        parts = [p for p in inserted.split("-") if p]
        return parts if len(parts) > 1 else [word]

    i = 0
    while i < len(words):
        word = words[i]
        candidate = (current + " " + word).strip()
        if _w(candidate) <= max_px:
            current = candidate
            i += 1
            continue

        # Doesn't fit as-is.
        if current:
            lines.append(current)
            current = ""
            continue

        # Single word doesn't fit on empty line -> try proper hyphenation.
        parts = _hyphenate_word(word)
        if len(parts) == 1:
            # Last resort: keep whole word (better than broken chunks).
            lines.append(word)
            i += 1
            continue

        # Build the largest prefix that fits with trailing hyphen.
        prefix = ""
        cut = 0
        for j in range(1, len(parts)):
            cand = "".join(parts[:j]) + "-"
            if _w(cand) <= max_px:
                prefix = cand
                cut = j
            else:
                break

        if not prefix or cut <= 0:
            # If even smallest hyphenated chunk doesn't fit, keep whole word.
            lines.append(word)
            i += 1
            continue

        lines.append(prefix)
        remainder = "".join(parts[cut:])
        words[i] = remainder

    if current:
        lines.append(current)
    return lines or [text]


# ─────────────────────────────────────────────────────────────────────────────
# Title / Outro cards
# ─────────────────────────────────────────────────────────────────────────────

def _make_title_card(
    title: str,
    hook: str,
    width: int,
    height: int,
    fps: int,
    duration: float = 1.8,
    *,
    subtitle_text: str | None = None,
    bg_image_path: str | None = None,
    hide_title_text: bool = False,
    word_timestamps: list[tuple[float, float]] | None = None,
    tts_words: list[str] | None = None,
    watermark_arr: np.ndarray | None = None,
) -> VideoClip:
    # Background: если есть тематическая картинка — используем её.
    if bg_image_path:
        try:
            bg = Image.open(bg_image_path).convert("RGB")
            bg = _resize_fill(bg, width, height)
            bg = _color_grade(bg)
            arr_bg = _apply_vignette(np.array(bg), strength=0.22)
            img = Image.fromarray(arr_bg)
        except Exception:
            img = _gradient_bg(width, height, (10, 6, 22), (20, 10, 45))
    else:
        img = _gradient_bg(width, height, (10, 6, 22), (20, 10, 45))

    draw = ImageDraw.Draw(img)
    if not hide_title_text:
        # Крупный заголовок для первого слайда.
        title_fs = max(64, min(120, width // 8))
        title_font = _load_card_font(title_fs)
        title_lines = _wrap_text_ru(
            title, draw=draw, font=title_font, max_px=int(width * 0.80),
        ) or [title[:20]]
        line_h = title_fs + 14
        title_y = int(height * 0.18) - len(title_lines) * line_h // 2
        for i, line in enumerate(title_lines):
            bbox = draw.textbbox((0, 0), line, font=title_font)
            x = (width - (bbox[2] - bbox[0])) // 2
            _draw_outlined_text(draw, (x, title_y + i * line_h), line, title_font,
                                fill=dt.TEXT_PRIMARY, stroke_fill=dt.STROKE_TITLE, stroke_width=4)
        if hook:
            hook_fs = max(34, min(58, width // 18))
            hook_font = _load_card_font(hook_fs)
            hook_lines = _wrap_text_ru(
                hook, draw=draw, font=hook_font, max_px=int(width * 0.86),
            ) or [hook[:30]]
            hook_y = int(height * 0.28)
            for i, line in enumerate(hook_lines):
                bbox = draw.textbbox((0, 0), line, font=hook_font)
                x = (width - (bbox[2] - bbox[0])) // 2
                _draw_outlined_text(draw, (x, hook_y + i * (hook_fs + 10)), line, hook_font,
                                    fill=dt.TEXT_HOOK_SECONDARY, stroke_fill=dt.STROKE_HOOK, stroke_width=3)

    arr = np.array(img)

    subtitle_text = (subtitle_text or "").strip()
    has_subtitle = bool(subtitle_text)
    SUB_FADE = 0.45
    sub_transition: dict = {}

    def make_frame(t: float) -> np.ndarray:
        fade_t = 0.25
        alpha = min(1.0, t / fade_t) * min(1.0, (duration - t) / fade_t)
        frame = (arr * alpha).astype(np.uint8)

        # Bottom subtitle (text-only style; no colored pill).
        if has_subtitle:
            ov = render_subtitle_overlay(
                subtitle_text,
                width,
                height,
                t,
                duration,
                word_timestamps=word_timestamps,
                tts_words=tts_words,
                transition_state=sub_transition,
            )
            if SUB_FADE > 0:
                fi_raw = max(0.0, min(1.0, t / SUB_FADE))
                fo_raw = max(0.0, min(1.0, (duration - t) / SUB_FADE))
                fi = fi_raw * fi_raw * (3.0 - 2.0 * fi_raw)
                fo = fo_raw * fo_raw * (3.0 - 2.0 * fo_raw)
                sub_alpha = fi * fo
            else:
                sub_alpha = 1.0
            if sub_alpha < 1.0:
                ov = ov.copy()
                ov[:, :, 3] = (ov[:, :, 3] * sub_alpha).astype(np.uint8)
            frame = _alpha_blit(frame, ov)
        if watermark_arr is not None:
            frame = _alpha_blit(frame, watermark_arr)
        return frame

    return VideoClip(make_frame, duration=duration).with_fps(fps)


def _make_intro_from_video(
    video_path: Path,
    duration: float,
    target_w: int,
    target_h: int,
    fps: int,
    *,
    subtitle_text: str | None = None,
    word_timestamps: list[tuple[float, float]] | None = None,
    tts_words: list[str] | None = None,
    watermark_arr: np.ndarray | None = None,
) -> VideoClip:
    """Тематическое видео для вступления. Длительность = TTS, звук = TTS."""
    vc = VideoFileClip(str(video_path))
    vc = vc.without_audio()
    vid_dur = float(vc.duration)
    sub_transition: dict = {}

    def make_frame(t: float) -> np.ndarray:
        t_vid = (t % vid_dur) if vid_dur > 0 else 0
        t_vid = min(t_vid, vid_dur - 0.001) if vid_dur > 0 else 0
        frame = vc.get_frame(t_vid)
        if frame is None or frame.size == 0:
            return np.zeros((target_h, target_w, 3), dtype=np.uint8)
        img = Image.fromarray(frame)
        img = _resize_fill(img, target_w, target_h)
        arr = np.array(img)
        if subtitle_text and subtitle_text.strip():
            ov = render_subtitle_overlay(
                subtitle_text, target_w, target_h, t, duration,
                word_timestamps=word_timestamps,
                tts_words=tts_words,
                transition_state=sub_transition,
            )
            arr = _alpha_blit(arr, ov)
        if watermark_arr is not None:
            arr = _alpha_blit(arr, watermark_arr)
        return arr

    clip = VideoClip(make_frame, duration=duration).with_fps(fps)
    return clip


def _make_outro_from_video(
    video_path: Path,
    target_w: int,
    target_h: int,
    fps: int,
    *,
    subtitle_text: str | None = None,
    word_timestamps: list[tuple[float, float]] | None = None,
    tts_words: list[str] | None = None,
    play_once: bool = True,
) -> VideoClip:
    """Видео для концовки со своим звуком. play_once=True → проигрывается ровно 1 раз полностью."""
    vc = VideoFileClip(str(video_path))
    vid_dur = float(vc.duration)
    duration = vid_dur if play_once else vid_dur
    has_audio = vc.audio is not None
    sub_transition: dict = {}

    def make_frame(t: float) -> np.ndarray:
        t_vid = t if play_once else (t % vid_dur if vid_dur > 0 else 0)
        t_vid = min(t_vid, vid_dur - 0.001) if vid_dur > 0 else 0
        frame = vc.get_frame(t_vid)
        if frame is None or frame.size == 0:
            return np.zeros((target_h, target_w, 3), dtype=np.uint8)
        img = Image.fromarray(frame)
        img = _resize_fill(img, target_w, target_h)
        arr = np.array(img)
        if subtitle_text and subtitle_text.strip():
            ov = render_subtitle_overlay(
                subtitle_text, target_w, target_h, t, duration,
                word_timestamps=word_timestamps,
                tts_words=tts_words,
                transition_state=sub_transition,
            )
            arr = _alpha_blit(arr, ov)
        return arr

    clip = VideoClip(make_frame, duration=duration).with_fps(fps)
    if has_audio:
        clip = clip.with_audio(vc.audio.subclipped(0, min(duration, vid_dur)))
    return clip


def _make_outro_card(
    outro: str,
    width: int,
    height: int,
    fps: int,
    duration: float = 1.8,
    *,
    subtitle_text: str | None = None,
    bg_image_path: str | None = None,
    word_timestamps: list[tuple[float, float]] | None = None,
    tts_words: list[str] | None = None,
) -> VideoClip:
    # Optional thematic background (likes/subscription).
    if bg_image_path:
        try:
            bg = Image.open(bg_image_path).convert("RGB")
            bg = _resize_fill(bg, width, height)
            bg = _color_grade(bg)
            arr_bg = _apply_vignette(np.array(bg), strength=0.22)
            img = Image.fromarray(arr_bg)
        except Exception:
            img = _gradient_bg(width, height, (12, 6, 26), (22, 10, 50))
    else:
        img = _gradient_bg(width, height, (12, 6, 26), (22, 10, 50))

    draw = ImageDraw.Draw(img)

    # User request: no visible text on the farewell slide.
    # Keep only the generated background image/gradient.

    arr = np.array(img)

    subtitle_text = (subtitle_text or "").strip()
    has_subtitle = bool(subtitle_text)
    SUB_FADE = 0.45
    sub_transition: dict = {}

    def make_frame(t: float) -> np.ndarray:
        fade_t = 0.25
        alpha = min(1.0, t / fade_t) * min(1.0, (duration - t) / fade_t)
        frame = (arr * alpha).astype(np.uint8)

        if has_subtitle:
            ov = render_subtitle_overlay(
                subtitle_text,
                width,
                height,
                t,
                duration,
                word_timestamps=word_timestamps,
                tts_words=tts_words,
                transition_state=sub_transition,
            )
            if SUB_FADE > 0:
                fi_raw = max(0.0, min(1.0, t / SUB_FADE))
                fo_raw = max(0.0, min(1.0, (duration - t) / SUB_FADE))
                fi = fi_raw * fi_raw * (3.0 - 2.0 * fi_raw)
                fo = fo_raw * fo_raw * (3.0 - 2.0 * fo_raw)
                sub_alpha = fi * fo
            else:
                sub_alpha = 1.0
            if sub_alpha < 1.0:
                ov = ov.copy()
                ov[:, :, 3] = (ov[:, :, 3] * sub_alpha).astype(np.uint8)
            frame = _alpha_blit(frame, ov)
        return frame

    return VideoClip(make_frame, duration=duration).with_fps(fps)


# ─────────────────────────────────────────────────────────────────────────────
# Scene counter overlay
# ─────────────────────────────────────────────────────────────────────────────

def _make_counter_overlay(n: int, total: int, width: int, height: int) -> np.ndarray:
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    text = f"{n} / {total}"
    fs = max(22, width // 38)
    font = _load_card_font(fs)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad_x, pad_y, margin = 14, 8, 20
    rx1 = width - tw - pad_x * 2 - margin
    ry1 = margin
    rx2 = width - margin
    ry2 = ry1 + th + pad_y * 2
    draw.rounded_rectangle([rx1, ry1, rx2, ry2], radius=dt.RADIUS_BADGE, fill=(0, 0, 0, 155))
    draw.rounded_rectangle(
        [rx1, ry1, rx2, ry2],
        radius=dt.RADIUS_BADGE,
        outline=(*dt.ACCENT_RGB, 180),
        width=2,
    )
    draw.text((rx1 + pad_x, ry1 + pad_y), text, font=font, fill=(*dt.TEXT_MUTED, 230))
    return np.array(img)


# ─────────────────────────────────────────────────────────────────────────────
# Fact label overlay (top center)
# ─────────────────────────────────────────────────────────────────────────────

def _make_fact_label_overlay(fact_num: int, width: int, height: int) -> np.ndarray:
    """Top label like: "Факт 1"."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    text = f"Факт {fact_num}"

    # Сделаем "Факт N" максимально заметным (сильнее, чем раньше).
    # Для 720px ширины это даст ~56-60px шрифта.
    fs = max(56, width // 18)
    font = _load_card_font(fs)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    # Text-only label: no background block (пожелание пользователя).
    x0 = (width - tw) // 2
    y0 = int(height * 0.025)  # чуть выше, чтобы влезал большой шрифт
    # Slight shadow for readability over bright scenes.
    draw.text(
        (x0, y0 + 2),
        text,
        font=font,
        fill=(0, 0, 0, 160),
    )
    draw.text(
        (x0, y0),
        text,
        font=font,
        fill=(*dt.TEXT_PRIMARY, 240),
        stroke_width=3,
        stroke_fill=(0, 0, 0, 180),
    )
    return np.array(img)


# ─────────────────────────────────────────────────────────────────────────────
# Watermark overlay  (top-left corner on all scene clips)
# ─────────────────────────────────────────────────────────────────────────────

def _make_watermark_image_overlay(image_path: Path, width: int, height: int) -> np.ndarray:
    """Returns RGBA array with image watermark in top-left (~12% frame height)."""
    bg = np.zeros((height, width, 4), dtype=np.uint8)
    try:
        wm = Image.open(image_path)
        if wm.mode != "RGBA":
            wm = wm.convert("RGBA")
        # Scale: max 12% of frame height
        max_h = int(height * 0.12)
        ratio = min(1.0, max_h / wm.height)
        nw, nh = int(wm.width * ratio), int(wm.height * ratio)
        nw, nh = max(1, nw), max(1, nh)
        wm = wm.resize((nw, nh), Image.LANCZOS)
        arr = np.array(wm)
        arr[:, :, 3] = (arr[:, :, 3].astype(np.float32) * 0.85).astype(np.uint8)
        # Place at top-left
        margin = max(12, width // 40)
        y1, y2 = margin, min(margin + nh, height)
        x1, x2 = margin, min(margin + nw, width)
        h_slice, w_slice = y2 - y1, x2 - x1
        if h_slice > 0 and w_slice > 0:
            patch = arr[:h_slice, :w_slice].astype(np.float32)
            a = patch[:, :, 3:4] / 255.0
            bg[y1:y2, x1:x2, :3] = (bg[y1:y2, x1:x2, :3].astype(np.float32) * (1 - a) + patch[:, :, :3] * a).astype(np.uint8)
            bg[y1:y2, x1:x2, 3] = np.maximum(bg[y1:y2, x1:x2, 3], patch[:, :, 3].astype(np.uint8))
        return bg
    except Exception as e:
        logger.warning(f"[Watermark] Could not load image {image_path}: {e}")
        return bg


def _make_watermark_overlay(text: str, width: int, height: int) -> np.ndarray:
    """Returns a static RGBA array with a channel watermark in the top-left."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if not text:
        return np.array(img)

    draw = ImageDraw.Draw(img)
    fs = max(20, width // 46)
    font = _load_card_font(fs)

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    pad_x, pad_y, margin = 10, 6, 18
    rx1 = margin
    ry1 = margin
    rx2 = rx1 + tw + pad_x * 2
    ry2 = ry1 + th + pad_y * 2

    draw.rounded_rectangle([rx1, ry1, rx2, ry2], radius=dt.RADIUS_WATERMARK, fill=(0, 0, 0, 120))
    draw.rounded_rectangle(
        [rx1, ry1, rx2, ry2],
        radius=dt.RADIUS_WATERMARK,
        outline=(*dt.ACCENT_RGB, 140),
        width=1,
    )
    draw.text((rx1 + pad_x, ry1 + pad_y), text, font=font, fill=(*dt.TEXT_HOOK_SECONDARY, 190))
    return np.array(img)


# ─────────────────────────────────────────────────────────────────────────────
# Hook banner overlay  (first 3 s of scene 1 — big TikTok-style text)
# ─────────────────────────────────────────────────────────────────────────────

def _add_hook_banner(
    clip: VideoClip,
    hook_text: str,
    width: int,
    height: int,
    fps: int,
    show_duration: float = 3.0,
) -> VideoClip:
    """
    Overlay a large bold hook text at the top of the clip for `show_duration` seconds.
    Scales in from 80% → 100% and fades out at the end.
    """
    if not hook_text or not hook_text.strip():
        return clip

    fs = max(52, min(90, width // 12))
    font = _load_card_font(fs)

    # Pre-render static RGBA banner
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    lines = _wrap_text_ru(
        hook_text,
        draw=draw,
        font=font,
        max_px=int(width * 0.82),
    ) or [hook_text[:25]]

    line_h = fs + 10
    total_h = len(lines) * line_h
    pad_v = 18
    bar_y = int(height * 0.06)         # 6% from top — above safe zone
    bar_h = total_h + pad_v * 2

    draw.rounded_rectangle(
        [int(width * 0.04), bar_y, int(width * 0.96), bar_y + bar_h],
        radius=dt.RADIUS_HOOK,
        fill=dt.HOOK_BAR_RGBA,
    )
    draw.rounded_rectangle(
        [int(width * 0.04), bar_y, int(width * 0.04) + 6, bar_y + bar_h],
        radius=4,
        fill=dt.ACCENT_RGBA,
    )

    y = bar_y + pad_v
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (width - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), line, font=font, fill=(*dt.TEXT_PRIMARY, 240),
                  stroke_width=4, stroke_fill=(*dt.STROKE_TITLE, 200))
        y += line_h

    static_arr = np.array(img)

    fade_in  = 0.20
    fade_out = 0.35
    dur = clip.duration

    def make_hook_frame(t: float) -> np.ndarray:
        if t > show_duration:
            return np.zeros((height, width, 4), dtype=np.uint8)
        fi = min(1.0, t / fade_in) if fade_in > 0 else 1.0
        fo = min(1.0, (show_duration - t) / fade_out) if t > show_duration - fade_out else 1.0
        # Scale: start at 0.92, settle at 1.0 over first 0.3 s
        scale = 0.92 + 0.08 * min(1.0, t / 0.30)
        alpha = fi * fo * scale
        frame = static_arr.copy().astype(np.float32)
        frame[:, :, 3] = frame[:, :, 3] * alpha
        return frame.astype(np.uint8)

    hook_clip = VideoClip(make_hook_frame, duration=dur).with_fps(fps)
    return CompositeVideoClip([clip, hook_clip])


# ─────────────────────────────────────────────────────────────────────────────
# Fast alpha compositing helper
# ─────────────────────────────────────────────────────────────────────────────

def _alpha_blit(base: np.ndarray, overlay_rgba: np.ndarray) -> np.ndarray:
    """Alpha-composite an RGBA overlay onto an RGB base (single numpy pass)."""
    a = overlay_rgba[:, :, 3:4].astype(np.float32) / 255.0
    fg = overlay_rgba[:, :, :3].astype(np.float32)
    return (base.astype(np.float32) * (1.0 - a) + fg * a).astype(np.uint8)


# ─────────────────────────────────────────────────────────────────────────────
# Pure-array generators for overlays (no VideoClip wrapping)
# ─────────────────────────────────────────────────────────────────────────────

def _make_hook_banner_arr(hook_text: str, width: int, height: int) -> np.ndarray:
    """Pre-render the hook banner as a static RGBA array."""
    fs = max(52, min(90, width // 12))
    font = _load_card_font(fs)

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    lines = _wrap_text_ru(
        hook_text,
        draw=draw,
        font=font,
        max_px=int(width * 0.82),
    ) or [hook_text[:25]]

    line_h = fs + 10
    total_h = len(lines) * line_h
    pad_v = 18
    bar_y = int(height * 0.06)
    bar_h = total_h + pad_v * 2
    y = bar_y + pad_v
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (width - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), line, font=font, fill=(*dt.TEXT_PRIMARY, 240),
                  stroke_width=4, stroke_fill=(*dt.STROKE_TITLE, 200))
        y += line_h
    return np.array(img)


# ─────────────────────────────────────────────────────────────────────────────
# Unified scene clip builder  (replaces 5× CompositeVideoClip nesting)
# ─────────────────────────────────────────────────────────────────────────────

def _make_scene_clip(
    img_path: str,
    duration: float,
    target_w: int,
    target_h: int,
    fps: int,
    style: str,
    subtitle_text: str,
    scene_num: int,
    total_scenes: int,
    watermark_arr: np.ndarray | None,
    hook_text: str | None = None,
    hook_duration: float = 3.0,
) -> VideoClip:
    """
    Build one scene clip with ALL overlays composited inside a single make_frame
    function.  Avoids 5-6 nested CompositeVideoClip layers and is 3-5× faster.

    Overlays:
      subtitle   – pill + karaoke, fades in over 0.30 s (rendered per frame)
      fact label – static (top center)
      watermark  – static (top-left)
      hook banner – animated alpha (first hook_duration seconds, scene 1 only)
    """
    # ── Pre-render static RGBA overlays ──────────────────────────────────────
    fact_arr: np.ndarray | None = _make_fact_label_overlay(scene_num, target_w, target_h)
    has_subtitle = bool(subtitle_text and subtitle_text.strip())
    hook_arr: np.ndarray | None = (
        _make_hook_banner_arr(hook_text, target_w, target_h)
        if hook_text and hook_text.strip() else None
    )

    # ── Ken Burns setup ───────────────────────────────────────────────────────
    pad = 1.15
    img = Image.open(img_path).convert("RGB")
    img = _resize_fill(img, int(target_w * pad), int(target_h * pad))
    img = _color_grade(img)
    arr = _apply_vignette(np.array(img))

    def _crop(p: float, cx: float, cy: float, zoom: float) -> np.ndarray:
        src_h, src_w = arr.shape[:2]
        # Keep sub-pixel centers to avoid "stepping" jitter.
        px = float(cx * src_w)
        py = float(cy * src_h)

        # Source window size (in source pixels). Final output is always target_w x target_h.
        view_w_src = float(target_w) / float(zoom)
        view_h_src = float(target_h) / float(zoom)

        if view_w_src >= src_w or view_h_src >= src_h:
            # Extreme zoom-out: just clamp to full frame and resize if needed.
            return _fast_resize(arr, target_w, target_h)

        x0 = px - view_w_src / 2.0
        y0 = py - view_h_src / 2.0
        x0 = max(0.0, min(x0, float(src_w) - view_w_src))
        y0 = max(0.0, min(y0, float(src_h) - view_h_src))

        # Sub-pixel resampling.
        # If cv2 is available: use vectorized bilinear via remap for smooth motion.
        if "_cv2" in globals():
            # Precompute grids once per scene clip.
            grid_x = getattr(_crop, "_grid_x", None)
            grid_y = getattr(_crop, "_grid_y", None)
            if grid_x is None or grid_y is None:
                gx = np.tile(np.arange(target_w, dtype=np.float32), (target_h, 1))
                gy = np.tile(np.arange(target_h, dtype=np.float32).reshape(-1, 1), (1, target_w))
                setattr(_crop, "_grid_x", gx)
                setattr(_crop, "_grid_y", gy)
                grid_x = gx
                grid_y = gy

            # Map output pixel coords to source coords.
            # x_src = x0 + j*(view_w_src/(target_w-1))
            # y_src = y0 + i*(view_h_src/(target_h-1))
            sx = view_w_src / max(1.0, float(target_w - 1))
            sy = view_h_src / max(1.0, float(target_h - 1))

            map_x = grid_x * sx + x0
            map_y = grid_y * sy + y0
            cropped = _cv2.remap(
                arr,
                map_x,
                map_y,
                interpolation=_cv2.INTER_LINEAR,
                borderMode=_cv2.BORDER_REFLECT_101,
            )
            return cropped

        # Fallback: integer crop + resize (less smooth).
        px_i, py_i = int(px), int(py)
        view_w_i = int(view_w_src)
        view_h_i = int(view_h_src)
        x0_i = max(0, min(px_i - view_w_i // 2, src_w - view_w_i))
        y0_i = max(0, min(py_i - view_h_i // 2, src_h - view_h_i))
        cropped = arr[y0_i : y0_i + view_h_i, x0_i : x0_i + view_w_i]
        return _fast_resize(cropped, target_w, target_h)

    # Subtitle timing constants
    SUB_FADE = 0.45
    # Hook banner timing constants
    HK_FADE_IN, HK_FADE_OUT = 0.20, 0.35
    sub_transition: dict = {}

    def make_frame(t: float) -> np.ndarray:
        p = min(1.0, t / duration)

        # 1. Ken Burns background
        # Reduce motion amplitude to minimize visible "jump" at scene boundaries.
        if   style == "zoom_in":           frame = _crop(p, 0.5, 0.5, 1.0 + 0.05 * p)
        elif style == "zoom_out":          frame = _crop(p, 0.5, 0.5, 1.05 - 0.05 * p)
        elif style == "pan_left":          frame = _crop(p, 0.60 - 0.10 * p, 0.5, 1.0)
        elif style == "pan_right":         frame = _crop(p, 0.40 + 0.10 * p, 0.5, 1.0)
        elif style == "zoom_pan_lr":       frame = _crop(p, 0.46 + 0.04 * p, 0.5, 1.0 + 0.04 * p)
        elif style == "zoom_pan_rl":       frame = _crop(p, 0.54 - 0.04 * p, 0.5, 1.0 + 0.04 * p)
        elif style == "zoom_pan_diag_tl":  frame = _crop(p, 0.54 - 0.04 * p, 0.54 - 0.04 * p, 1.0 + 0.04 * p)
        elif style == "zoom_pan_diag_br":  frame = _crop(p, 0.46 + 0.04 * p, 0.46 + 0.04 * p, 1.05 - 0.05 * p)
        else:                              frame = _crop(p, 0.5, 0.5, 1.0 + 0.05 * p)

        # 2. Subtitle (fade-in on whole overlay)
        if has_subtitle:
            ov = render_subtitle_overlay(
                subtitle_text,
                target_w,
                target_h,
                t,
                duration,
                transition_state=sub_transition,
            )
            # Fade in/out so during crossfades the previous subtitle doesn't overlap.
            if SUB_FADE > 0:
                fi_raw = max(0.0, min(1.0, t / SUB_FADE))
                fo_raw = max(0.0, min(1.0, (duration - t) / SUB_FADE))
                fi = fi_raw * fi_raw * (3.0 - 2.0 * fi_raw)
                fo = fo_raw * fo_raw * (3.0 - 2.0 * fo_raw)
                alpha = fi * fo
            else:
                alpha = 1.0
            if alpha < 1.0:
                ov = ov.copy()
                ov[:, :, 3] = (ov[:, :, 3] * alpha).astype(np.uint8)
            frame = _alpha_blit(frame, ov)

        # 3. Fact label (static)
        if fact_arr is not None:
            frame = _alpha_blit(frame, fact_arr)

        # 4. Watermark (static)
        if watermark_arr is not None:
            frame = _alpha_blit(frame, watermark_arr)

        # 5. Hook banner (animated, first hook_duration seconds)
        if hook_arr is not None and t <= hook_duration:
            fi = min(1.0, t / HK_FADE_IN) if t < HK_FADE_IN else 1.0
            fo = min(1.0, (hook_duration - t) / HK_FADE_OUT) if t > hook_duration - HK_FADE_OUT else 1.0
            scale = 0.92 + 0.08 * min(1.0, t / 0.30)
            a = fi * fo * scale
            ov = hook_arr.copy()
            ov[:, :, 3] = (ov[:, :, 3] * a).astype(np.uint8)
            frame = _alpha_blit(frame, ov)

        return frame

    return VideoClip(make_frame, duration=duration).with_fps(fps)


# ─────────────────────────────────────────────────────────────────────────────
# Music helper
# ─────────────────────────────────────────────────────────────────────────────

def _pick_background_music(
    topic: str | None = None,
    duration: float | None = None,
    *,
    music_dir_only: bool = False,
) -> Path | None:
    """
    Return a background music path.

    If USE_AI_MUSIC is enabled, generate a topic-specific track with MusicGen.
    duration: video length in seconds — pass to generate long enough music (no looping).
    Otherwise fall back to a random file from the music_dir.

    If music_dir_only is True, skip AI and use only files under music_dir (mp3/wav).
    """
    if not music_dir_only and settings.use_ai_music and topic:
        dur = int(duration) + 1 if duration is not None else settings.ai_music_duration
        path = generate_background_music(
            topic=topic,
            duration=dur,
            cache_dir=settings.music_cache_dir,
        )
        if path:
            return path

    files = list(settings.music_dir.glob("*.mp3")) + list(settings.music_dir.glob("*.wav"))
    return random.choice(files) if files else None


# ─────────────────────────────────────────────────────────────────────────────
# Sound effects mixer
# ─────────────────────────────────────────────────────────────────────────────

def _mix_sound_effects(
    sfx: SoundEffects,
    transition_times: list[float],
    scene_start_times: list[float],
    total_duration: float,
    # Keep SFX subtle: don't fight voiceover/music.
    vol_boom: float = 0.22,
    vol_whoosh: float = 0.02,
    vol_impact: float = 0.14,
) -> CompositeAudioClip | None:
    """
    Build a CompositeAudioClip from timed sound effects.

    - boom at t=0 (opening)
    - whoosh peaked near each crossfade midpoint (aligned with 50/50 frame blend)
    - impact at the start of each scene (except scene 1 which gets boom)
    """
    clips: list = []

    def _add(path: Path | None, t: float, vol: float) -> None:
        if path is None or not path.exists():
            return
        try:
            ac = AudioFileClip(str(path))
            # Gentle envelope so crossfade boundaries feel "premium".
            env_in = 0.03
            env_out = 0.08
            ac = ac.with_effects(
                [
                    afx.MultiplyVolume(vol),
                    afx.AudioFadeIn(env_in),
                    afx.AudioFadeOut(env_out),
                ]
            )
            ac = ac.with_start(max(0.0, t))
            clips.append(ac)
        except Exception as exc:
            logger.debug(f"[SoundFX] Could not add {path.name} at t={t:.2f}: {exc}")

    # Opening boom
    _add(sfx.boom, 0.0, vol_boom)

    # Whoosh aligned to crossfade *midpoint* (see _compute_timecodes).
    # Whoosh ~0.45s: start slightly before midpoint so the sweep peaks at the visual blend center.
    _whoosh_lead = 0.14
    for t in transition_times:
        _add(sfx.whoosh, max(0.0, t - _whoosh_lead), vol_whoosh)

    # Impact at scene starts (scene 2 onwards — scene 1 already has the boom)
    for t in scene_start_times[1:]:
        _add(sfx.impact, t, vol_impact)

    if not clips:
        return None

    return CompositeAudioClip(clips)


# ─────────────────────────────────────────────────────────────────────────────
# Timeline tracker (for sound effect placement)
# ─────────────────────────────────────────────────────────────────────────────

def _compute_timecodes(
    clip_durations: list[float],
    T: float,
) -> tuple[list[float], list[float]]:
    """
    Exact start times of each *trimmed* clip segment in the final video, and
    times to sync transition SFX with the *visual* crossfade.

    Assembly (see ``_assemble_with_crossfades``) trims T/2 from the end of
    every clip except the last, and T/2 from the start of every clip except the
    first, then inserts a crossfade of length T between neighbours. The
    *midpoint* of that crossfade (50/50 blend) is exactly at::

        sum(clip_durations[0 : i+1])

    i.e. the cumulative duration through the end of clip ``i`` in the *pre-cut*
    timeline — **not** ``current + dur - T/2`` (that is the *start* of the
    crossfade segment, which made whoosh fire too early and misaligned impacts).

    Returns:
        (clip_start_times, transition_sync_times)
        - clip_start_times[k]: when trimmed clip ``k`` begins in the export.
        - transition_sync_times[k]: when crossfade between ``k`` and ``k+1``
          reaches its midpoint (use for whoosh); length ``n-1``.
    """
    n = len(clip_durations)
    if n == 0:
        return [], []

    pref: list[float] = [0.0]
    for dur in clip_durations:
        pref.append(pref[-1] + float(dur))

    starts: list[float] = []
    transitions: list[float] = []

    if T <= 0 or n == 1:
        # Hard cuts: clip k starts at sum(d[0:k])
        starts = [pref[k] for k in range(n)]
        transitions = [pref[k + 1] for k in range(n - 1)]
        return starts, transitions

    # T > 0, n >= 2
    starts.append(0.0)
    for k in range(1, n):
        # Trimmed segment k begins after prior crossfade: sum(d[0:k]) + T/2
        starts.append(pref[k] + T / 2.0)

    # Midpoint of crossfade after clip k is at cumulative time through clip k
    transitions = [pref[k + 1] for k in range(n - 1)]
    return starts, transitions


# ─────────────────────────────────────────────────────────────────────────────
# Main assembly
# ─────────────────────────────────────────────────────────────────────────────

def assemble_video(
    scenes: list[SceneData],
    output_path: Path,
    title: str | None = None,
    hook: str | None = None,
    outro: str | None = None,
    topic: str | None = None,
    title_audio_path: str | None = None,
    outro_audio_path: str | None = None,
    title_subtitle_text: str | None = None,
    outro_subtitle_text: str | None = None,
    outro_bg_image_path: str | None = None,
) -> Path:
    """
    Assemble a complete vertical video from scene data.

    Args:
        scenes:      SceneData list (image + subtitle + audio).
        output_path: Destination mp4.
        title:       Title card topic text.
        hook:        Hook line for title card + first-scene banner.
        outro:       CTA text for outro card.
        topic:       Original topic string — used for AI music generation.
    """
    target_w, target_h = settings.video_resolution
    fps = settings.video_fps
    base_dur = settings.video_duration_per_image
    T = max(0.0, settings.video_transition_duration)

    # Sound effects (generated on first use)
    sfx = SoundEffects(settings.sounds_dir) if settings.use_sound_effects else None

    wm_arr: np.ndarray | None = None  # водяной знак отключён

    all_clips: list[VideoClip] = []
    clip_durations: list[float] = []
    scene_clip_indices: list[int] = []   # indices in all_clips that are scene clips (not cards)

    # Вступление отключено — сразу начинаем с фактов (scene clips)

    # ── Scene clips ───────────────────────────────────────────────────────────
    # Keep one Ken Burns motion style across the whole video for smoother
    # visual continuity (crossfades with different styles look "jerky").
    scene_style = random.choice(_KB_STYLES)
    total_scenes = len(scenes)

    for i, scene in enumerate(scenes):
        logger.info(f"[VideoEditor] Scene {i+1}/{total_scenes}: {scene.subtitle_text[:50]}")

        audio_clip: AudioFileClip | None = None
        clip_dur = base_dur
        if scene.audio_path and Path(scene.audio_path).exists():
            try:
                audio_clip = AudioFileClip(scene.audio_path)
                clip_dur = max(audio_clip.duration + 0.4, base_dur)
            except Exception as e:
                logger.warning(f"[VideoEditor] Could not load audio: {e}")

        style = scene_style
        hook_dur = min(3.0, clip_dur - 0.3)

        # Build the scene clip with ALL overlays combined in a single make_frame
        video = _make_scene_clip(
            img_path=scene.image_path,
            duration=clip_dur,
            target_w=target_w,
            target_h=target_h,
            fps=fps,
            style=style,
            subtitle_text=scene.subtitle_text,
            scene_num=i + 1,
            total_scenes=total_scenes,
            watermark_arr=wm_arr,
            hook_text=None,
            hook_duration=hook_dur,
        )

        # Voiceover (audio is attached separately — not part of frame rendering)
        if audio_clip is not None:
            video = video.with_audio(audio_clip)

        scene_clip_indices.append(len(all_clips))
        all_clips.append(video)
        clip_durations.append(clip_dur)

    # Outro slide removed

    # ── Stitch segments (FFmpeg xfade or MoviePy dissolve) ────────────────────
    logger.info(f"[VideoEditor] Assembling {len(all_clips)} clips (T={T}s) ...")
    tmp_root: Path | None = None
    final: VideoClip | None = None
    use_xfade = (
        T > 0
        and len(all_clips) > 1
        and settings.video_transition_engine.lower().strip() == "xfade"
        and ffmpeg_available()
    )

    if use_xfade:
        tmp_root = Path(tempfile.mkdtemp(prefix="ve_segments_"))
        seg_paths: list[Path] = []
        try:
            for i, clip in enumerate(all_clips):
                p = tmp_root / f"seg_{i:03d}.mp4"
                wc = _ensure_stereo_audio(clip)
                wc.write_videofile(
                    str(p),
                    fps=fps,
                    codec="libx264",
                    audio_codec="aac",
                    preset="fast",
                    threads=4,
                    logger=None,
                )
                wc.close()
                seg_paths.append(p)

            style_tokens = [
                x.strip()
                for x in settings.video_transition_styles.split(",")
                if x.strip()
            ]
            trans_names = cycle_transitions(style_tokens, len(seg_paths) - 1)
            merged_mp4 = tmp_root / "_xfade_merged.mp4"
            ok = merge_segments_xfade(seg_paths, clip_durations, trans_names, T, merged_mp4)
            if ok and merged_mp4.exists():
                for p in seg_paths:
                    p.unlink(missing_ok=True)
                final = VideoFileClip(str(merged_mp4))
                logger.info(f"[VideoEditor] FFmpeg xfade OK → styles {trans_names}")
            else:
                raise RuntimeError("merge_segments_xfade returned False")
        except Exception as exc:
            logger.warning(f"[VideoEditor] xfade failed ({exc}), using MoviePy dissolve")
            final = _assemble_with_crossfades(all_clips, T, fps)
    else:
        final = _assemble_with_crossfades(all_clips, T, fps)

    assert final is not None

    # ── Background music (generated last when video duration is known) ─────────
    music_path = _pick_background_music(topic=topic or title, duration=final.duration)
    audio_layers: list = []

    if final.audio:
        audio_layers.append(final.audio)

    if music_path:
        try:
            logger.info(f"[VideoEditor] Adding music: {music_path.name}")
            bg = AudioFileClip(str(music_path))
            if bg.duration < final.duration:
                loops = int(final.duration / bg.duration) + 1
                bg = concatenate_audioclips([bg] * loops)
            bg = bg.subclipped(0, min(final.duration, bg.duration) - 0.01)

            voice_present = any(s.audio_path and Path(s.audio_path).exists() for s in scenes)
            music_vol = 0.10 if voice_present else 0.30
            fade_dur = min(2.0, final.duration * 0.08)
            bg = bg.with_effects([
                afx.MultiplyVolume(music_vol),
                afx.AudioFadeIn(fade_dur),
                afx.AudioFadeOut(fade_dur),
            ])
            audio_layers.append(bg)
        except Exception as exc:
            logger.warning(f"[VideoEditor] Music failed: {exc}")

    # ── Sound effects ─────────────────────────────────────────────────────────
    if sfx is not None:
        try:
            clip_starts, transition_times = _compute_timecodes(clip_durations, T)
            # scene_start_times = timecodes of the actual scene clips within all_clips
            scene_starts = [clip_starts[idx] for idx in scene_clip_indices]

            sfx_audio = _mix_sound_effects(
                sfx,
                transition_times=transition_times,
                scene_start_times=scene_starts,
                total_duration=final.duration,
            )
            if sfx_audio is not None:
                sfx_clipped = sfx_audio.subclipped(0, min(final.duration, sfx_audio.duration) - 0.01)
                audio_layers.append(sfx_clipped)
                logger.info(f"[VideoEditor] Sound effects applied ({len(transition_times)} transitions)")
        except Exception as exc:
            logger.warning(f"[VideoEditor] Sound effects failed: {exc}")

    if audio_layers:
        if len(audio_layers) == 1:
            composite_audio = audio_layers[0]
        else:
            composite_audio = CompositeAudioClip(audio_layers)
        # Clamp audio to video duration to prevent floating-point overrun during export
        safe_audio_dur = final.duration - 0.05
        if composite_audio.duration is not None and composite_audio.duration > safe_audio_dur:
            composite_audio = composite_audio.subclipped(0, safe_audio_dur)
        final = final.with_audio(composite_audio)

    # ── Export ────────────────────────────────────────────────────────────────
    # Platform-optimized export settings from video-processing-editing skill
    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"[VideoEditor] Rendering → {output_path}")

    # Determine platform-optimized settings
    # Default: high quality for general use, optimized for social media
    export_settings = {
        "fps": fps,
        "codec": "libx264",
        "audio_codec": "aac",
        "threads": 4,
        "preset": "medium",  # Balance between speed and quality
        "logger": None,
        # Video quality settings (CRF 18 = visually lossless, 23 = good quality)
        "bitrate": "8000k",  # 8 Mbps for 1080p social media
        # Audio settings optimized for voice + music
        "audio_bitrate": "192k",
        "audio_fps": 48000,
        # Color space for broad compatibility (BT.709 standard)
        "ffmpeg_params": [
            "-pix_fmt", "yuv420p",
            "-color_primaries", "bt709",
            "-color_trc", "bt709",
            "-colorspace", "bt709",
            "-movflags", "+faststart",  # Enable progressive download
        ],
    }

    try:
        final.write_videofile(
            str(output_path),
            **export_settings
        )
    finally:
        try:
            final.close()
        except Exception:
            pass
        if tmp_root is not None and tmp_root.exists():
            shutil.rmtree(tmp_root, ignore_errors=True)

    logger.success(f"[VideoEditor] Done → {output_path}")
    return output_path
