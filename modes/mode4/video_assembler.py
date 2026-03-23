"""
Mode 4 Video Assembler — 1 или 2 видеофрагмента, crop, субтитры.

Аудио: только из FastGen (никаких доп. звуков, TTS, музыки).
Субтитры: синхронизированы с голосом FastGen через Whisper (word-level).

Windows: write_videofile в subprocess — иначе WinError 32 при удалении temp-файлов.
"""

from __future__ import annotations

import sys
from multiprocessing import Process, Queue
from pathlib import Path

import numpy as np
from loguru import logger
from moviepy import VideoClip, VideoFileClip
from PIL import Image

from agents.video_editor.subtitles import render_subtitle_overlay
from config import settings


def _compute_letterbox_bounds(arr: np.ndarray, black_threshold: int = 25) -> tuple[int, int, int, int] | None:
    """Compute content bounds (top, bottom, left, right). None = no crop."""
    h, w = arr.shape[:2]
    if h < 3 or w < 3:
        return None
    gray = arr[:, :, :3].astype(np.float32).mean(axis=2) if arr.ndim >= 3 else arr.astype(np.float32)
    row_means = gray.mean(axis=1)
    col_means = gray.mean(axis=0)
    top, bottom, left, right = 0, h, 0, w
    for i in range(h):
        if row_means[i] > black_threshold:
            top = max(0, i - 1)
            break
    for i in range(h - 1, -1, -1):
        if row_means[i] > black_threshold:
            bottom = min(h, i + 2)
            break
    for j in range(w):
        if col_means[j] > black_threshold:
            left = max(0, j - 1)
            break
    for j in range(w - 1, -1, -1):
        if col_means[j] > black_threshold:
            right = min(w, j + 2)
            break
    if bottom - top < 10 or right - left < 10:
        return None
    return (top, bottom, left, right)


def _resize_fill(img: Image.Image, w: int, h: int, bottom_crop: float = 0.0) -> Image.Image:
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


def _make_subtitle_clip(
    video_path: Path,
    target_w: int,
    target_h: int,
    fps: int,
    subtitle_text: str,
    bottom_crop: float,
    word_timestamps: list[tuple[float, float]] | None = None,
    tts_words: list[str] | None = None,
) -> tuple[VideoClip, VideoFileClip]:
    """Видео + субтитры. Аудио только из FastGen. Субтитры синхронны с голосом (word_timestamps)."""
    vc = VideoFileClip(str(video_path))
    vid_dur = float(vc.duration)
    bounds_cache: list[tuple[int, int, int, int] | None] = [None]

    def make_frame(t: float) -> np.ndarray:
        t_vid = min(t, vid_dur - 0.001) if vid_dur > 0 else 0
        t_vid = min(t_vid, vid_dur - 0.001) if vid_dur > 0 else 0
        frame = vc.get_frame(t_vid)
        if frame is None or frame.size == 0:
            return np.zeros((target_h, target_w, 3), dtype=np.uint8)
        if bounds_cache[0] is None:
            bounds_cache[0] = _compute_letterbox_bounds(frame) or (0, frame.shape[0], 0, frame.shape[1])
        top, bottom, left, right = bounds_cache[0]
        frame = frame[top:bottom, left:right]
        img = Image.fromarray(frame)
        img = _resize_fill(img, target_w, target_h, bottom_crop=bottom_crop)
        arr = np.array(img)

        if subtitle_text and subtitle_text.strip():
            ov = render_subtitle_overlay(
                subtitle_text, target_w, target_h, t, vid_dur,
                karaoke=False, word_timestamps=word_timestamps, tts_words=tts_words,
            )
            dur = vid_dur
            fi = max(0, min(1, t / 0.45)) ** 2 * (3 - 2 * max(0, min(1, t / 0.45)))
            fo = max(0, min(1, (dur - t) / 0.45)) ** 2 * (3 - 2 * max(0, min(1, (dur - t) / 0.45)))
            alpha = fi * fo
            if alpha < 1.0:
                ov = ov.copy()
                ov[:, :, 3] = (ov[:, :, 3] * alpha).astype(np.uint8)
            arr = _alpha_blit(arr, ov)
        return arr

    clip = VideoClip(make_frame, duration=vid_dur).with_fps(fps)
    if vc.audio is not None:
        clip = clip.with_audio(vc.audio)
    return (clip, vc)


def _assemble_mode4_impl(
    video_paths: list[Path | str],
    subtitle_texts: list[str],
    output_path: Path,
) -> Path:
    """Внутренняя реализация — вызывается в subprocess на Windows."""
    from agents.video_editor.whisper_timestamps import get_word_timestamps_from_video

    target_w, target_h = settings.video_resolution
    fps = settings.video_fps
    bottom_crop = max(0, min(0.2, getattr(settings, "video_bottom_crop", 0.05)))

    clips: list[VideoClip] = []
    vc_refs: list[VideoFileClip] = []
    for i, p in enumerate(video_paths):
        path = Path(p)
        if not path.exists():
            logger.warning(f"[Mode4 Assembler] Skip missing: {path}")
            continue
        sub = subtitle_texts[i] if i < len(subtitle_texts) else ""
        wt, tw = (None, None)
        if sub and sub.strip():
            wt, tw = get_word_timestamps_from_video(path, script=sub)
            if wt and tw:
                logger.info(f"[Mode4 Assembler] Whisper sync: {len(wt)} words (synced with FastGen voice)")
        clip, vc = _make_subtitle_clip(path, target_w, target_h, fps, sub, bottom_crop, wt, tw)
        clips.append(clip)
        vc_refs.append(vc)

    if not clips:
        raise ValueError("No valid video clips to assemble")

    from moviepy import concatenate_videoclips
    final = concatenate_videoclips(clips, method="compose")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"[Mode4 Assembler] Rendering → {output_path} ({len(clips)} clip(s), with audio)")
    try:
        final.write_videofile(
            str(output_path),
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            audio_fps=48000,
            audio_bitrate="192k",
            threads=4,
            preset="fast",
            ffmpeg_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart"],
            logger=None,
        )
        if not output_path.exists() or output_path.stat().st_size < 1024:
            raise RuntimeError(f"[Mode4 Assembler] Output invalid or empty: {output_path}")
    finally:
        final.close()
        for c in clips:
            try:
                c.close()
            except Exception:
                pass
        for vc in vc_refs:
            try:
                vc.close()
            except Exception:
                pass

    logger.success(f"[Mode4 Assembler] Done → {output_path}")
    return output_path


def _run_in_process(paths: list, texts: list, out: Path, err_q: Queue) -> None:
    try:
        _assemble_mode4_impl(paths, texts, out)
    except Exception as e:
        err_q.put(e)


def assemble_mode4_video(
    video_paths: list[Path | str],
    subtitle_texts: list[str],
    output_path: Path,
) -> Path:
    """
    Собирает видео. На Windows — в subprocess (избегаем WinError 32 с temp-файлами).
    """
    if sys.platform == "win32":
        q: Queue = Queue()
        p = Process(
            target=_run_in_process,
            args=(
                [str(Path(x)) for x in video_paths],
                subtitle_texts,
                output_path,
                q,
            ),
        )
        p.start()
        p.join()
        if not q.empty():
            raise q.get_nowait()
    else:
        _assemble_mode4_impl(video_paths, subtitle_texts, output_path)
    return output_path
