"""
Mode 5 Video Assembler — длинное видео: изображение + озвучка по сегментам.
Без субтитров. Плавные переходы между сегментами.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from loguru import logger
from moviepy import AudioFileClip, VideoClip, concatenate_videoclips
from PIL import Image

from config import settings


def _resize_fill(img: Image.Image, w: int, h: int) -> Image.Image:
    """Масштабировать изображение, заполняя кадр (crop по центру)."""
    ratio = max(w / img.width, h / img.height)
    nw, nh = int(img.width * ratio), int(img.height * ratio)
    img = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def _make_segment_clip(
    image_path: Path,
    audio_path: Path,
    target_w: int,
    target_h: int,
    fps: int,
) -> VideoClip:
    """Один сегмент: статичное изображение + озвучка."""
    img = Image.open(image_path).convert("RGB")
    img = _resize_fill(img, target_w, target_h)
    arr = np.array(img)

    audio = AudioFileClip(str(audio_path))
    duration = float(audio.duration)

    def make_frame(t: float) -> np.ndarray:
        return arr

    clip = VideoClip(make_frame, duration=duration).with_fps(fps)
    clip = clip.with_audio(audio)
    return clip


def assemble_mode5_video(
    segment_data: list[tuple[Path, Path]],
    output_path: Path,
) -> Path:
    """
    Собирает длинное видео из сегментов (image + audio).
    segment_data: list of (image_path, audio_path)
    """
    target_w, target_h = settings.mode5_video_resolution
    fps = settings.video_fps

    clips: list[VideoClip] = []
    for i, (img_path, audio_path) in enumerate(segment_data):
        if not img_path.exists() or not audio_path.exists():
            logger.warning(f"[Mode5] Skip missing: {img_path} or {audio_path}")
            continue
        clip = _make_segment_clip(img_path, audio_path, target_w, target_h, fps)
        clips.append(clip)

    if not clips:
        raise ValueError("[Mode5] No valid segments to assemble")

    logger.info(f"[Mode5] Assembling {len(clips)} segments → {output_path}")
    final = concatenate_videoclips(clips, method="compose")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        final.write_videofile(
            str(output_path),
            fps=fps,
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

    logger.success(f"[Mode5] Done → {output_path}")
    return output_path
