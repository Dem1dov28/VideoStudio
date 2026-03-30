"""
Mode 9 Video Assembler — Assemble vehicle assembly timelapse videos.

Features:
- Quick crossfades (0.5-1s) between stages
- Workshop/industrial ambient audio
- No TTS, no subtitles (pure visual satisfaction)
- Preserves FastGen-generated assembly sounds
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
    """Assemble clips with crossfade transitions."""
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


def assemble_mode9_video(
    video_paths: list[Path | str],
    output_path: Path,
    title: str | None = None,
    crossfade_duration: float = 0.2,  # 0.2 sec for sharp but smooth transitions
    speed_multiplier: float = 1.5,   # 1.5x speed for viral dynamics
    use_speed_ramping: bool = True,  # Cinematic speed variation
    final_hold_duration: float = 1.5,  # Hold last frame for retention
    preview_image_path: Path | str | None = None,  # NEW: Clickbait preview to append
    preview_duration: float = 0.3,  # Preview display duration (seconds)
) -> tuple[Path, float]:
    """
    Assemble final vehicle assembly timelapse video.

    FastGen videos already contain AI-generated construction ambient audio.
    We PRESERVE that audio at 100% volume and ADD quiet background music at 10%.
    No TTS, no subtitles.

    Args:
        video_paths: List of video file paths
        output_path: Output file path
        title: Video title (for logging)
        crossfade_duration: Transition duration (default 0.2s for viral style)
        speed_multiplier: Base speed multiplier (default 1.5x for dynamics)
        use_speed_ramping: Apply cinematic speed variation (slow start/end, fast middle)
        final_hold_duration: Hold last frame for better retention (default 1.5s)
        preview_image_path: Path to clickbait preview image to append at end (optional)
        preview_duration: How long to show preview at end (default 0.3s)

    Returns:
        Tuple of (output_path, final_duration_seconds)
    """
    target_w, target_h = settings.video_resolution
    fps = settings.video_fps
    # TIMELAPSE STYLE: Short 0.2s crossfade for viral-style sharp transitions
    T = max(0.0, min(crossfade_duration, 0.5))  # Max 0.5s, default 0.2s
    bottom_crop = max(0, min(0.2, getattr(settings, "video_bottom_crop", 0.05)))

    # Keep original VideoFileClips alive so their audio is accessible
    original_vcs: list[VideoFileClip] = []
    clips: list = []
    original_audios: list = []

    for p in video_paths:
        path = Path(p)
        if not path.exists():
            logger.warning(f"[Mode9 Assembler] Skip missing: {path}")
            continue
        vc = VideoFileClip(str(path))
        original_vcs.append(vc)

        # Save original audio from FastGen video (construction sounds)
        if vc.audio is not None:
            dur = max(0.0, vc.duration - 0.05)
            original_audios.append(vc.audio.subclipped(0, min(vc.audio.duration, dur)))
        else:
            original_audios.append(None)

        # Visual-only clip (cropped/resized, watermark hidden)
        clip = _clip_with_bottom_crop(vc, target_w, target_h, fps, bottom_crop)
        clips.append(clip)

    if not clips:
        raise ValueError("[Mode9 Assembler] No valid video clips to assemble")

    logger.info(f"[Mode9 Assembler] Assembling {len(clips)} clips (T={T}s)")

    # Assemble video (visual only — crossfades strip audio)
    final = _assemble_with_crossfades(clips, T, fps)

    # Apply speed multiplier for viral dynamics (1.5x default)
    if speed_multiplier != 1.0:
        from moviepy import vfx
        final = final.with_effects([vfx.MultiplySpeed(speed_multiplier)])
        logger.info(f"[Mode9 Assembler] Applied {speed_multiplier}x speed for viral dynamics")

    # ===== SPEED RAMPING (Commented out: TimeMirror is incorrect for ramping) =====
    # if use_speed_ramping:
    #     try:
    #         from moviepy import vfx
    #         total_dur = final.duration
    #         phase1_end = total_dur * 0.1
    #         phase2_end = total_dur * 0.8
    #
    #         def speed_ramp(t):
    #             if t < phase1_end: return 1.0
    #             elif t < phase2_end: return 1.8
    #             else: return 0.8
    #
    #         # TimeMirror is not for speed ramping in MoviePy 2.x
    #         # final = final.with_effects([vfx.MultiplySpeed(speed_ramp)])
    #     except Exception as e:
    #         logger.warning(f"[Mode9 Assembler] Speed ramping failed: {e}")

    # ===== FINAL HOLD: Increase retention =====
    if final_hold_duration > 0:
        try:
            # Get last frame and create a freeze frame
            last_frame_time = max(0, final.duration - 0.05)
            last_frame = final.get_frame(last_frame_time)
            
            # Create a static clip from last frame
            from moviepy import ImageClip
            freeze_frame = ImageClip(last_frame).set_duration(final_hold_duration).with_fps(fps)
            freeze_frame = freeze_frame.resized((target_w, target_h))
            
            # Append freeze frame
            final = concatenate_videoclips([final, freeze_frame], method="compose")
            logger.info(f"[Mode9 Assembler] Added FINAL HOLD: {final_hold_duration}s freeze frame for retention")
        except Exception as e:
            logger.warning(f"[Mode9 Assembler] Final hold failed: {e}")

    # Build combined audio from original FastGen clips
    valid_audios = [a for a in original_audios if a is not None]
    combined_video_audio = None
    if valid_audios:
        try:
            combined_video_audio = concatenate_audioclips(valid_audios)
            # Apply speed multiplier to audio too
            if speed_multiplier != 1.0:
                from moviepy import afx as audio_fx
                combined_video_audio = combined_video_audio.with_effects([
                    audio_fx.MultiplySpeed(speed_multiplier)
                ])
            max_dur = min(final.duration, combined_video_audio.duration) - 0.05
            combined_video_audio = combined_video_audio.subclipped(0, max(0.1, max_dur))
            logger.info(f"[Mode9 Assembler] Preserved FastGen audio from {len(valid_audios)} clips (speed: {speed_multiplier}x)")
        except Exception as e:
            logger.warning(f"[Mode9 Assembler] Could not combine video audios: {e}")
            combined_video_audio = None

    # Background music at 10% volume (ambient, construction-friendly)
    bg_audio = None
    try:
        from agents.video_editor.moviepy_editor import _pick_background_music
        music_path = _pick_background_music(
            topic="ambient construction work site",
            duration=final.duration,
        )
        if music_path:
            bg = AudioFileClip(str(music_path))
            if bg.duration < final.duration:
                loops = int(final.duration / bg.duration) + 1
                bg = concatenate_audioclips([bg] * loops)
            fade_dur = min(2.0, final.duration * 0.1)
            bg = bg.subclipped(0, min(final.duration, bg.duration) - 0.05)
            bg = bg.with_effects([
                afx.MultiplyVolume(0.1),   # Very quiet — 10% so construction sounds stay clear
                afx.AudioFadeIn(fade_dur),
                afx.AudioFadeOut(fade_dur),
            ])
            bg_audio = bg
            logger.info(f"[Mode9 Assembler] Added background music at 10%: {music_path.name}")
    except Exception as e:
        logger.warning(f"[Mode9 Assembler] Background music failed: {e}")

    # Mix: FastGen construction audio (100%) + background music (10%)
    if combined_video_audio and bg_audio:
        final_audio = CompositeAudioClip([combined_video_audio, bg_audio])
        final = final.with_audio(final_audio)
        logger.info("[Mode9 Assembler] Audio: FastGen construction 100% + music 10%")
    elif combined_video_audio:
        final = final.with_audio(combined_video_audio)
        logger.info("[Mode9 Assembler] Audio: FastGen construction only (no music)")
    elif bg_audio:
        final = final.with_audio(bg_audio)
        logger.warning("[Mode9 Assembler] Audio: music only (FastGen audio was missing)")
    else:
        logger.warning("[Mode9 Assembler] No audio available")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"[Mode9 Assembler] Rendering -> {output_path}")
    
    # ═══════════════════════════════════════════════════════════════════════
    # APPEND CLICKBAIT PREVIEW BEFORE FINAL RENDER (OPTIONAL)
    # ═══════════════════════════════════════════════════════════════════════
    
    # Explicitly check preview_image_path BEFORE closing final
    logger.info(f"[Mode9 Assembler] Preview path check: {preview_image_path}")
    if preview_image_path:
        logger.info(f"[Mode9 Assembler] Preview file exists: {Path(preview_image_path).exists()}")
    
    if preview_image_path and Path(preview_image_path).exists():
        try:
            logger.info(f"[Mode9 Assembler] Appending clickbait preview ({preview_duration}s)...")
            
            from PIL import Image
            from moviepy import ImageClip, concatenate_videoclips
            
            # Load preview image and resize to match video
            preview_img = Image.open(str(preview_image_path))
            preview_clip = ImageClip(np.array(preview_img)).with_duration(preview_duration).with_fps(fps)
            preview_clip = preview_clip.resized((target_w, target_h))
            
            # Concatenate with main video
            final_with_preview = concatenate_videoclips([final, preview_clip], method="compose")
            
            # Preserve audio from main video (preview will be silent or can add sound effect)
            final_with_preview = final_with_preview.with_audio(final.audio if final.audio else None)
            
            # Use final_with_preview instead of final
            final_to_render = final_with_preview
            logger.success(f"[Mode9 Assembler] Preview appended (+{preview_duration}s)")
            
        except Exception as e:
            logger.error(f"[Mode9 Assembler] Preview append failed: {e}")
            final_to_render = final  # Fallback to original
    else:
        final_to_render = final  # No preview

    try:
        final_to_render.write_videofile(
            str(output_path),
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            threads=4,
            preset="fast",
            logger=None,
        )
    finally:
        final_to_render.close()
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

    logger.success(f"[Mode9 Assembler] Done -> {output_path} (duration: {final_to_render.duration:.2f}s)")
    
    return output_path, float(final.duration) + (preview_duration if preview_image_path and Path(preview_image_path).exists() else 0)
