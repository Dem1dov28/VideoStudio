"""
Mode 7 Video Assembler — Assemble animal keyboard videos.

Simple assembly with crossfades and background music.
No TTS, no subtitles — videos come with AI-generated ambient audio from FastGen.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from loguru import logger
from moviepy import AudioFileClip, VideoClip, VideoFileClip
from moviepy import CompositeAudioClip, afx, concatenate_audioclips, concatenate_videoclips
from PIL import Image

from config import settings


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


def _clip_with_bottom_crop(vc: VideoFileClip, target_w: int, target_h: int, fps: int, bottom_crop: float) -> VideoClip:
    """Wrap VideoFileClip with bottom crop + resize to fill (hide watermarks)."""
    vid_dur = float(vc.duration)

    def make_frame(t: float) -> np.ndarray:
        t_vid = min(t, vid_dur - 0.001) if vid_dur > 0 else 0
        frame = vc.get_frame(t_vid)
        if frame is None or frame.size == 0:
            return np.zeros((target_h, target_w, 3), dtype=np.uint8)
        img = Image.fromarray(frame)
        img = _resize_fill(img, target_w, target_h, bottom_crop=bottom_crop)
        return np.array(img)

    return VideoClip(make_frame, duration=vid_dur).with_fps(fps)


def _make_crossfade(clip_a, clip_b, duration: float, fps: int):
    """Smooth transition between clips."""
    dur_a = float(clip_a.duration)
    dur_b = float(clip_b.duration)
    half = duration / 2.0

    def smoothstep(x):
        x = max(0.0, min(1.0, x))
        return x * x * (3.0 - 2.0 * x)

    def make_frame(t):
        raw = t / duration if duration > 0 else 1.0
        alpha = smoothstep(raw)
        half_a = min(half, dur_a)
        half_b = min(half, dur_b)
        ta = max(0.0, dur_a - half_a) + raw * half_a
        tb = raw * half_b
        fa = clip_a.get_frame(ta).astype("float32")
        fb = clip_b.get_frame(tb).astype("float32")
        return ((1.0 - alpha) * fa + alpha * fb).astype("uint8")

    return VideoClip(make_frame, duration=duration).with_fps(fps)


def _assemble_with_crossfades(clips: list, T: float, fps: int):
    if len(clips) == 1 or T <= 0:
        return concatenate_videoclips(clips, method="compose")
    half = T / 2.0
    parts = []
    for i, clip in enumerate(clips):
        is_first, is_last = i == 0, i == len(clips) - 1
        t_start = 0.0 if is_first else half
        t_end = clip.duration if is_last else max(clip.duration - half, half + 0.1)
        t_end = min(t_end, clip.duration - 0.01)
        trimmed = clip.subclipped(t_start, t_end)
        parts.append(trimmed)
        if not is_last:
            parts.append(_make_crossfade(trimmed, clips[i + 1], T, fps))
    return concatenate_videoclips(parts, method="compose")


def assemble_mode7_video(
    video_paths: list[Path | str],
    output_path: Path,
    title: str | None = None,
) -> Path:
    """
    Assemble final video from animal keyboard clips.

    FastGen videos already contain AI-generated ambient audio.
    We PRESERVE that audio at 100% volume and ADD quiet background music at 10%.
    No TTS, no subtitles.
    """
    target_w, target_h = settings.video_resolution
    fps = settings.video_fps
    T = max(0.0, settings.video_transition_duration)
    bottom_crop = max(0, min(0.2, getattr(settings, "video_bottom_crop", 0.05)))

    # Keep original VideoFileClips alive so their audio is accessible
    original_vcs: list[VideoFileClip] = []
    clips: list = []
    original_audios: list = []

    for p in video_paths:
        path = Path(p)
        if not path.exists():
            logger.warning(f"[Mode7 Assembler] Skip missing: {path}")
            continue
        vc = VideoFileClip(str(path))
        original_vcs.append(vc)

        # Save original audio from FastGen video (ambient sounds)
        if vc.audio is not None:
            dur = max(0.0, vc.duration - 0.05)
            original_audios.append(vc.audio.subclipped(0, min(vc.audio.duration, dur)))
        else:
            original_audios.append(None)

        # Visual-only clip (cropped/resized, watermark hidden)
        clip = _clip_with_bottom_crop(vc, target_w, target_h, fps, bottom_crop)
        clips.append(clip)

    if not clips:
        raise ValueError("No valid video clips to assemble")

    logger.info(f"[Mode7 Assembler] Assembling {len(clips)} clips (T={T}s)")

    # Assemble video (visual only — crossfades strip audio)
    final = _assemble_with_crossfades(clips, T, fps)

    # ─── Build combined audio from original FastGen clips ───
    valid_audios = [a for a in original_audios if a is not None]
    combined_video_audio = None
    if valid_audios:
        try:
            combined_video_audio = concatenate_audioclips(valid_audios)
            max_dur = min(final.duration, combined_video_audio.duration) - 0.05
            combined_video_audio = combined_video_audio.subclipped(0, max(0.1, max_dur))
            logger.info(f"[Mode7 Assembler] Preserved FastGen audio from {len(valid_audios)} clips")
        except Exception as e:
            logger.warning(f"[Mode7 Assembler] Could not combine video audios: {e}")
            combined_video_audio = None

    # ─── Background music at 10% volume ───
    bg_audio = None
    try:
        from agents.video_editor.moviepy_editor import _pick_background_music
        music_path = _pick_background_music(topic="relaxing satisfying ambient", duration=final.duration)
        if music_path:
            bg = AudioFileClip(str(music_path))
            if bg.duration < final.duration:
                loops = int(final.duration / bg.duration) + 1
                bg = concatenate_audioclips([bg] * loops)
            fade_dur = min(2.0, final.duration * 0.1)
            bg = bg.subclipped(0, min(final.duration, bg.duration) - 0.05)
            bg = bg.with_effects([
                afx.MultiplyVolume(0.1),   # Very quiet — 10% so ambient sounds stay clear
                afx.AudioFadeIn(fade_dur),
                afx.AudioFadeOut(fade_dur),
            ])
            bg_audio = bg
            logger.info(f"[Mode7 Assembler] Added background music at 10%: {music_path.name}")
    except Exception as e:
        logger.warning(f"[Mode7 Assembler] Background music failed: {e}")

    # ─── Mix: FastGen ambient audio (100%) + background music (10%) ───
    if combined_video_audio and bg_audio:
        final_audio = CompositeAudioClip([combined_video_audio, bg_audio])
        final = final.with_audio(final_audio)
        logger.info("[Mode7 Assembler] Audio: FastGen ambient 100% + music 10%")
    elif combined_video_audio:
        final = final.with_audio(combined_video_audio)
        logger.info("[Mode7 Assembler] Audio: FastGen ambient only (no music)")
    elif bg_audio:
        final = final.with_audio(bg_audio)
        logger.warning("[Mode7 Assembler] Audio: music only (FastGen audio was missing)")
    else:
        logger.warning("[Mode7 Assembler] No audio available")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"[Mode7 Assembler] Rendering → {output_path}")
    
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
        final.close()
        for c in clips:
            try:
                c.close()
            except Exception:
                pass
        for vc in original_vcs:
            try:
                vc.close()
            except Exception:
                pass

    logger.success(f"[Mode7 Assembler] Done → {output_path}")
    return output_path
