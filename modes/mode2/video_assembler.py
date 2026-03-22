"""
Mode 2 Video Assembler — trim clips to audio duration, assemble with crossfades.

Uses moviepy for trimming and crossfades. Reuses TTS from agents.video_editor.tts
and subtitles from agents.video_editor.subtitles.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

import numpy as np
from loguru import logger
from moviepy import AudioFileClip, CompositeAudioClip, CompositeVideoClip, VideoClip, VideoFileClip
from moviepy import afx, concatenate_audioclips, concatenate_videoclips
from PIL import Image

from agents.video_editor.subtitles import render_subtitle_overlay
from config import settings

class Mode2SceneData(NamedTuple):
    video_path: str | None
    audio_path: str
    subtitle_text: str
    word_timestamps: list[tuple[float, float]] | None = None
    tts_words: list[str] | None = None


def _compute_letterbox_bounds(arr: np.ndarray, black_threshold: int = 25) -> tuple[int, int, int, int] | None:
    """Compute content bounds (top, bottom, left, right). None = no crop (use full frame)."""
    h, w = arr.shape[:2]
    if h < 3 or w < 3:
        return None
    gray = arr[:, :, :3].astype(np.float32).mean(axis=2) if arr.ndim >= 3 else arr.astype(np.float32)
    row_means = gray.mean(axis=1)
    col_means = gray.mean(axis=0)
    top = 0
    for i in range(h):
        if row_means[i] > black_threshold:
            top = max(0, i - 1)
            break
    bottom = h
    for i in range(h - 1, -1, -1):
        if row_means[i] > black_threshold:
            bottom = min(h, i + 2)
            break
    left = 0
    for j in range(w):
        if col_means[j] > black_threshold:
            left = max(0, j - 1)
            break
    right = w
    for j in range(w - 1, -1, -1):
        if col_means[j] > black_threshold:
            right = min(w, j + 2)
            break
    if bottom - top < 10 or right - left < 10:
        return None
    return (top, bottom, left, right)


def _remove_letterboxing(arr: np.ndarray, black_threshold: int = 25, bounds: tuple[int, int, int, int] | None = None) -> np.ndarray:
    """Crop black bars. If bounds provided, use them (stable per-clip, avoids frame-to-frame jitter)."""
    if bounds is not None:
        top, bottom, left, right = bounds
        return arr[top:bottom, left:right]
    b = _compute_letterbox_bounds(arr, black_threshold)
    if b is None:
        return arr
    return arr[b[0]:b[1], b[2]:b[3]]


def _resize_fill(img: Image.Image, w: int, h: int, bottom_crop: float = 0.0) -> Image.Image:
    """Scale to fill target; optionally crop bottom fraction first (to hide watermarks)."""
    if bottom_crop > 0 and bottom_crop < 1:
        keep_h = int(img.height * (1.0 - bottom_crop))
        if keep_h > 0:
            img = img.crop((0, 0, img.width, keep_h))
    ratio = max(w / img.width, h / img.height)
    nw, nh = int(img.width * ratio), int(img.height * ratio)
    img = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def _alpha_blit(base: np.ndarray, overlay_rgba: np.ndarray) -> np.ndarray:
    a = overlay_rgba[:, :, 3:4].astype(np.float32) / 255.0
    fg = overlay_rgba[:, :, :3].astype(np.float32)
    return (base.astype(np.float32) * (1.0 - a) + fg * a).astype(np.uint8)


def _smoothstep(x: float) -> float:
    """Smooth ease-in-out (0..1) — reduces abruptness at transition edges."""
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def _make_crossfade(clip_a: VideoClip, clip_b: VideoClip, duration: float, fps: int) -> VideoClip:
    dur_a = float(clip_a.duration)
    dur_b = float(clip_b.duration)
    half = duration / 2.0

    def make_frame(t: float) -> np.ndarray:
        raw = t / duration if duration > 0 else 1.0
        alpha = _smoothstep(raw)  # плавное нарастание вместо линейного
        half_a = min(half, dur_a)
        half_b = min(half, dur_b)
        ta = max(0.0, dur_a - half_a) + raw * half_a  # ta линейно, blend плавный
        tb = raw * half_b
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
        t_end = min(t_end, clip.duration - 0.01)
        t_start = min(t_start, t_end - 0.05)

        if t_end > t_start + 0.05:
            clip_audio = clip.audio
            clip_no_audio = clip.without_audio() if clip_audio is not None else clip
            trimmed = clip_no_audio.subclipped(t_start, t_end)
            if clip_audio is not None:
                aud_dur = clip_audio.duration if clip_audio.duration is not None else clip.duration
                a_start = min(t_start, max(0.0, aud_dur - 0.02))
                a_end = min(t_end, max(a_start + 0.01, aud_dur - 0.01))
                if a_end > a_start + 0.02:
                    trimmed = trimmed.with_audio(clip_audio.subclipped(a_start, a_end))
            parts.append(trimmed)

        if not is_last:
            parts.append(_make_crossfade(clip, clips[i + 1], T, fps))

    return concatenate_videoclips(parts, method="compose")


def _make_scene_clip_from_video(
    video_path: str,
    duration: float,
    target_w: int,
    target_h: int,
    fps: int,
    subtitle_text: str,
    audio_path: str | None,
    word_timestamps: list[tuple[float, float]] | None = None,
    tts_words: list[str] | None = None,
    watermark_arr: np.ndarray | None = None,
) -> VideoClip:
    """
    Load video file, resize to target, trim to duration, add subtitle overlay, attach audio.
    """
    vc = VideoFileClip(video_path)
    vc = vc.without_audio()
    vid_dur = float(vc.duration)

    # Letterbox bounds: compute once to avoid frame-to-frame jitter (рывки)
    _letterbox_cache: list[tuple[int, int, int, int] | None] = [None]

    # Resize: crop bottom (hide Veo watermark), then fill target (no distortion)
    bottom_crop = max(0, min(0.2, getattr(settings, "video_bottom_crop", 0.05)))
    sub_transition: dict = {}
    def make_frame(t: float) -> np.ndarray:
        t_vid = min(t, vid_dur - 0.001) if vid_dur > 0 else 0
        frame = vc.get_frame(t_vid)
        if frame is None or frame.size == 0:
            return np.zeros((target_h, target_w, 3), dtype=np.uint8)
        if _letterbox_cache[0] is None:
            _letterbox_cache[0] = _compute_letterbox_bounds(frame) or (0, frame.shape[0], 0, frame.shape[1])
        frame = _remove_letterboxing(frame, bounds=_letterbox_cache[0])
        img = Image.fromarray(frame)
        img = _resize_fill(img, target_w, target_h, bottom_crop=bottom_crop)
        arr = np.array(img)

        if subtitle_text and subtitle_text.strip():
            ov = render_subtitle_overlay(
                subtitle_text,
                target_w,
                target_h,
                t,
                duration,
                word_timestamps=word_timestamps,
                tts_words=tts_words,
                transition_state=sub_transition,
            )
            SUB_FADE = 0.45
            if SUB_FADE > 0:
                fi_raw = max(0.0, min(1.0, t / SUB_FADE))
                fo_raw = max(0.0, min(1.0, (duration - t) / SUB_FADE))
                # smoothstep для плавного появления/исчезновения
                fi = fi_raw * fi_raw * (3.0 - 2.0 * fi_raw)
                fo = fo_raw * fo_raw * (3.0 - 2.0 * fo_raw)
                alpha = fi * fo
                if alpha < 1.0:
                    ov = ov.copy()
                    ov[:, :, 3] = (ov[:, :, 3] * alpha).astype(np.uint8)
            arr = _alpha_blit(arr, ov)
        if watermark_arr is not None:
            arr = _alpha_blit(arr, watermark_arr)
        return arr

    # Длительность = аудио целиком; если видео короче — замораживаем последний кадр
    clip = VideoClip(make_frame, duration=duration).with_fps(fps)
    # Note: vc stays open — make_frame uses it during render; GC will clean up

    if audio_path and Path(audio_path).exists():
        try:
            ac = AudioFileClip(audio_path)
            ac = ac.subclipped(0, min(clip.duration, ac.duration))
            fade = getattr(settings, "tts_audio_fade_in", 0.12)
            if fade > 0 and ac.duration > fade * 2:
                ac = ac.with_effects([afx.AudioFadeIn(min(fade, ac.duration * 0.15))])
            clip = clip.with_audio(ac)
        except Exception as e:
            logger.warning(f"[Mode2 Assembler] Audio load failed: {e}")

    return clip


def _make_placeholder_clip(
    duration: float,
    target_w: int,
    target_h: int,
    fps: int,
    subtitle_text: str,
    audio_path: str | None,
    word_timestamps: list[tuple[float, float]] | None = None,
    tts_words: list[str] | None = None,
    watermark_arr: np.ndarray | None = None,
) -> VideoClip:
    """Fallback when no video file — solid gradient + subtitle."""
    from agents.video_editor.moviepy_editor import _gradient_bg

    img = _gradient_bg(target_w, target_h, (10, 6, 22), (20, 10, 45))
    arr = np.array(img)
    sub_transition: dict = {}

    def make_frame(t: float) -> np.ndarray:
        frame = arr.copy()
        if subtitle_text and subtitle_text.strip():
            ov = render_subtitle_overlay(
                subtitle_text,
                target_w,
                target_h,
                t,
                duration,
                word_timestamps=word_timestamps,
                tts_words=tts_words,
                transition_state=sub_transition,
            )
            SUB_FADE = 0.45
            if SUB_FADE > 0:
                fi_raw = max(0.0, min(1.0, t / SUB_FADE))
                fo_raw = max(0.0, min(1.0, (duration - t) / SUB_FADE))
                fi = fi_raw * fi_raw * (3.0 - 2.0 * fi_raw)
                fo = fo_raw * fo_raw * (3.0 - 2.0 * fo_raw)
                alpha = fi * fo
                if alpha < 1.0:
                    ov = ov.copy()
                    ov[:, :, 3] = (ov[:, :, 3] * alpha).astype(np.uint8)
            frame = _alpha_blit(frame, ov)
        if watermark_arr is not None:
            frame = _alpha_blit(frame, watermark_arr)
        return frame

    clip = VideoClip(make_frame, duration=duration).with_fps(fps)
    if audio_path and Path(audio_path).exists():
        try:
            ac = AudioFileClip(audio_path)
            ac = ac.subclipped(0, min(clip.duration, ac.duration))
            fade = getattr(settings, "tts_audio_fade_in", 0.12)
            if fade > 0 and ac.duration > fade * 2:
                ac = ac.with_effects([afx.AudioFadeIn(min(fade, ac.duration * 0.15))])
            clip = clip.with_audio(ac)
        except Exception:
            pass
    return clip


def assemble_mode2_video(
    scene_data: list[Mode2SceneData],
    output_path: Path,
    title: str | None = None,
    hook: str | None = None,
    outro: str | None = None,
    title_audio_path: str | None = None,
    outro_audio_path: str | None = None,
    title_bg_path: str | None = None,
    outro_bg_path: str | None = None,
    title_word_timestamps: list[tuple[float, float]] | None = None,
    outro_word_timestamps: list[tuple[float, float]] | None = None,
    title_tts_words: list[str] | None = None,
    outro_tts_words: list[str] | None = None,
    intro_video_path: Path | None = None,
) -> Path:
    """
    Assemble Mode 2 «Почему X?» video from trimmed clips + TTS + subtitles.

    Args:
        scene_data: List of (video_path, audio_path, subtitle_text).
        output_path: Output mp4 path.
        title, hook, outro: Optional card text.
        title_audio_path, outro_audio_path: Optional TTS for title/outro.
        title_bg_path, outro_bg_path: Optional background images for title/outro cards.
    """
    target_w, target_h = settings.video_resolution
    fps = settings.video_fps
    T = max(0.0, settings.video_transition_duration)

    wm_arr: np.ndarray | None = None  # водяной знак отключён

    all_clips: list[VideoClip] = []
    clip_durations: list[float] = []

    # Фрагмент 1 — тематическое вступление (тема видео); фрагменты 2–6 — факты
    for i, s in enumerate(scene_data):
        audio_dur = 3.0
        if s.audio_path and Path(s.audio_path).exists():
            try:
                ac = AudioFileClip(s.audio_path)
                audio_dur = max(0.5, float(ac.duration))
                ac.close()
            except Exception:
                pass

        # Интро короче: меньше хвост, если название не длинное
        tail = 0.2 if i == 0 else 0.3
        clip_dur = audio_dur + tail

        if s.video_path and Path(s.video_path).exists():
            clip = _make_scene_clip_from_video(
                s.video_path,
                clip_dur,
                target_w,
                target_h,
                fps,
                s.subtitle_text,
                s.audio_path,
                word_timestamps=s.word_timestamps,
                tts_words=s.tts_words,
                watermark_arr=wm_arr,
            )
        else:
            clip = _make_placeholder_clip(
                clip_dur,
                target_w,
                target_h,
                fps,
                s.subtitle_text,
                s.audio_path,
                word_timestamps=s.word_timestamps,
                tts_words=s.tts_words,
                watermark_arr=wm_arr,
            )

        all_clips.append(clip)
        clip_durations.append(clip.duration)

    # Outro slide removed

    # Concatenate with crossfades
    logger.info(f"[Mode2 Assembler] Assembling {len(all_clips)} clips (T={T}s)")
    final = _assemble_with_crossfades(all_clips, T, fps)

    # Topic-appropriate background music — generate last when video duration known
    from agents.video_editor.moviepy_editor import _pick_background_music
    music_path = _pick_background_music(topic=title, duration=final.duration)
    if music_path:
        try:
            bg = AudioFileClip(str(music_path))
            if bg.duration < final.duration:
                loops = int(final.duration / bg.duration) + 1
                bg = concatenate_audioclips([bg] * loops)
            bg = bg.subclipped(0, min(final.duration, bg.duration) - 0.01)
            music_vol = 0.10 if final.audio else 0.30
            fade_dur = min(2.0, final.duration * 0.08)
            bg = bg.with_effects([
                afx.MultiplyVolume(music_vol),
                afx.AudioFadeIn(fade_dur),
                afx.AudioFadeOut(fade_dur),
            ])
            layers = [final.audio, bg] if final.audio else [bg]
            composite = CompositeAudioClip(layers)
            safe_dur = final.duration - 0.05
            if composite.duration is not None and composite.duration > safe_dur:
                composite = composite.subclipped(0, safe_dur)
            final = final.with_audio(composite)
            logger.info(f"[Mode2 Assembler] Added music: {music_path.name}")
        except Exception as e:
            logger.warning(f"[Mode2 Assembler] Music failed: {e}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"[Mode2 Assembler] Rendering → {output_path}")
    try:
        final.write_videofile(
            str(output_path),
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            threads=4,
            preset="fast",
            logger=None,
        )
    finally:
        try:
            final.close()
        except Exception:
            pass
        for c in all_clips:
            try:
                c.close()
            except Exception:
                pass

    logger.success(f"[Mode2 Assembler] Done → {output_path}")
    return output_path
