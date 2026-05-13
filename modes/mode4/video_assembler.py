"""
Mode 4 Video Assembler — 1 или 2 видеофрагмента, crop, субтитры.

Аудио: только из FastGen (никаких доп. звуков, TTS, музыки).
Субтитры: синхронизированы с голосом FastGen через Whisper (word-level).

Windows: write_videofile в subprocess — иначе WinError 32 при удалении temp-файлов.
"""

from __future__ import annotations

import sys
import uuid
from multiprocessing import Process, Queue
from pathlib import Path

import numpy as np
from loguru import logger
from moviepy import VideoClip, VideoFileClip
from PIL import Image

from agents.video_editor.subtitles import (
    apply_whisper_word_start_lead,
    get_mode4_quote_font_size,
    render_mode4_quote_karaoke_overlay,
    render_quote_header_overlay,
    render_static_quote_caption_overlay,
    render_subtitle_overlay,
)
from config import settings


def _estimate_karaoke_word_timestamps(
    script: str | None,
    duration: float,
    *,
    speech_range: tuple[float, float] | None = None,
) -> tuple[list[tuple[float, float]] | None, list[str] | None]:
    """
    Fallback для mode4, когда faster-whisper не установлен или не дал таймкоды:
    строим приблизительную пословную разметку, чтобы не терять золотое караоке полностью.
    """
    text = (script or "").strip()
    if not text or duration <= 0.25:
        return (None, None)
    words = text.split()
    if not words:
        return (None, None)
    if speech_range is not None:
        start0, end0 = speech_range
        start0 = max(0.0, min(float(start0), max(0.0, duration - 0.05)))
        end0 = max(start0 + 0.12, min(float(end0), duration))
        lead_in = start0
        usable = max(0.12, end0 - start0)
    else:
        lead_in = min(0.16, duration * 0.12)
        usable = max(0.12, duration - lead_in)
    weights = [max(1.0, min(12.0, len(w.strip(".,!?;:()[]{}\"'«»")))) for w in words]
    total = sum(weights) or float(len(words))
    cur = lead_in
    ts: list[tuple[float, float]] = []
    for weight in weights:
        span = usable * (weight / total)
        start = cur
        end = min(duration, max(start + 0.05, cur + span))
        ts.append((start, end))
        cur = end
    if ts:
        last_start, _last_end = ts[-1]
        ts[-1] = (last_start, min(duration, lead_in + usable))
    return (ts, words)


def _expected_spoken_word_count(script: str | None) -> int:
    """Грубая оценка числа произносимых слов в скрипте для проверки качества Whisper."""
    text = (script or "").strip()
    if not text:
        return 0
    return len([w for w in text.split() if w.strip()])


def _whisper_result_too_sparse_for_script(
    script: str | None,
    tts_words: list[str] | None,
) -> bool:
    """
    FastGen иногда генерирует/Whisper иногда распознаёт только хвост фразы.
    Если принять такой частичный ASR за правду, полный текст субтитров будет натянут
    на 5-10 распознанных слов и «поедет» именно на поздних фрагментах.
    """
    expected = _expected_spoken_word_count(script)
    got = len(tts_words or [])
    if expected < 8:
        return False
    # Для нормального клипа Whisper обычно близок к длине скрипта; запас оставляем
    # на склейки, пропуски артиклей и пунктуацию. 8 слов из 21 — явный частичный ASR.
    return got < max(5, int(round(expected * 0.55)))


def _clip_duration(path: Path) -> float:
    vc_probe = VideoFileClip(str(path))
    try:
        return float(vc_probe.duration)
    finally:
        vc_probe.close()


def _script_timing_from_whisper_speech_window(
    script: str | None,
    duration: float,
    word_timestamps: list[tuple[float, float]] | None,
    *,
    sparse_whisper: bool,
) -> tuple[list[tuple[float, float]] | None, list[str] | None]:
    """
    Stable mode for plain_whisper.

    Whisper's word text is unstable on generated clips: it may omit the beginning, merge
    phrases, or recognize only a tail. For plain subtitles we only need a smooth readable
    progression, not exact karaoke. Use Whisper only to locate the speech window when it
    looks complete enough; distribute the expected script words inside that window.
    """
    speech_range: tuple[float, float] | None = None
    if not sparse_whisper and word_timestamps and len(word_timestamps) >= 2:
        s = max(0.0, float(word_timestamps[0][0]))
        e = min(duration, float(word_timestamps[-1][1]))
        if e - s >= 0.5:
            speech_range = (s, e)
    return _estimate_karaoke_word_timestamps(
        script,
        duration,
        speech_range=speech_range,
    )


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


def _clamp_word_timestamps_to_duration(
    wt: list[tuple[float, float]], dur: float
) -> list[tuple[float, float]]:
    """Таймкоды не выходят за длину клипа — иначе караоке «уезжает» в конце."""
    if dur <= 0 or not wt:
        return wt
    out: list[tuple[float, float]] = []
    eps = 0.02
    for a, b in wt:
        a = max(0.0, min(float(a), max(0.0, dur - eps)))
        b = max(0.0, min(float(b), dur))
        if b < a + eps:
            b = min(dur, a + eps)
        out.append((a, b))
    return out


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
    *,
    static_caption: bool = False,
    spoken_script: str | None = None,
    author_name: str | None = None,
    subclip_range: tuple[float, float] | None = None,
    header_title: str | None = None,
    plain_timed_subtitles: bool = False,
) -> tuple[VideoClip, VideoFileClip]:
    """Видео + субтитры. Аудио только из FastGen. Караоке по Whisper или статическая подпись."""
    vc = VideoFileClip(str(video_path))
    vid_dur = float(vc.duration)
    quote_scale = max(
        0.7, min(2.0, float(getattr(settings, "mode4_quote_subtitle_scale", 1.6) or 1.6))
    )
    subclip_start_applied: float | None = None
    if subclip_range is not None:
        t0, t1 = subclip_range
        t0 = max(0.0, min(t0, vid_dur - 0.12))
        t1 = max(t0 + 0.12, min(t1, vid_dur))
        subclip_start_applied = t0
        vc = vc.subclipped(t0, t1)
        vid_dur = float(vc.duration)
    wts = list(word_timestamps) if word_timestamps else None
    # Whisper / оценка дают время от начала исходного файла; после subclipped(t0,·)
    # кадр в локальном t соответствует файлу (t0+t), иначе караоке «замирает» до t0.
    if subclip_start_applied is not None and wts:
        off = float(subclip_start_applied)
        wts = [(float(a) - off, float(b) - off) for a, b in wts]
    if wts and vid_dur > 0:
        wts = _clamp_word_timestamps_to_duration(wts, vid_dur)
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
            if static_caption:
                ov = render_static_quote_caption_overlay(
                    subtitle_text, target_w, target_h, t, vid_dur,
                )
            elif plain_timed_subtitles and wts and tts_words:
                ov = render_subtitle_overlay(
                    subtitle_text,
                    target_w,
                    target_h,
                    t,
                    vid_dur,
                    karaoke=False,
                    word_timestamps=wts,
                    tts_words=tts_words,
                    transition_state={},
                    timed_plain=True,
                    timed_plain_font_scale=quote_scale,
                )
                dur = vid_dur
                fi = max(0, min(1, t / 0.45)) ** 2 * (3 - 2 * max(0, min(1, t / 0.45)))
                fo = max(0, min(1, (dur - t) / 0.45)) ** 2 * (
                    3 - 2 * max(0, min(1, (dur - t) / 0.45))
                )
                alpha = fi * fo
                if alpha < 1.0:
                    ov = ov.copy()
                    ov[:, :, 3] = (ov[:, :, 3] * alpha).astype(np.uint8)
            elif (
                wts
                and tts_words
                and spoken_script
                and spoken_script.strip()
            ):
                ov = render_mode4_quote_karaoke_overlay(
                    spoken_script.strip(),
                    author_name,
                    target_w,
                    target_h,
                    t,
                    vid_dur,
                    wts,
                    tts_words,
                )
            elif wts and tts_words:
                ov = render_subtitle_overlay(
                    subtitle_text,
                    target_w,
                    target_h,
                    t,
                    vid_dur,
                    karaoke=False,
                    word_timestamps=wts,
                    tts_words=tts_words,
                    transition_state={},
                    timed_plain=True,
                    timed_plain_font_scale=quote_scale,
                )
                dur = vid_dur
                fi = max(0, min(1, t / 0.45)) ** 2 * (3 - 2 * max(0, min(1, t / 0.45)))
                fo = max(0, min(1, (dur - t) / 0.45)) ** 2 * (
                    3 - 2 * max(0, min(1, (dur - t) / 0.45))
                )
                alpha = fi * fo
                if alpha < 1.0:
                    ov = ov.copy()
                    ov[:, :, 3] = (ov[:, :, 3] * alpha).astype(np.uint8)
            else:
                ov = render_static_quote_caption_overlay(
                    subtitle_text, target_w, target_h, t, vid_dur,
                )
            arr = _alpha_blit(arr, ov)
        ht = (header_title or "").strip()
        if ht:
            hdr = render_quote_header_overlay(ht, target_w, target_h, t, vid_dur)
            arr = _alpha_blit(arr, hdr)
        return arr

    clip = VideoClip(make_frame, duration=vid_dur).with_fps(fps)
    if vc.audio is not None:
        clip = clip.with_audio(vc.audio)
    return (clip, vc)


def _assemble_mode4_impl(
    video_paths: list[Path | str],
    subtitle_texts: list[str],
    output_path: Path,
    static_subtitles: bool = False,
    spoken_scripts: list[str] | None = None,
    authors: list[str | None] | None = None,
    whisper_languages: list[str | None] | None = None,
    *,
    trim_clips_to_whisper_speech: bool = False,
    whisper_vad_filter: bool = True,
    header_title: str | None = None,
    plain_timed_subtitles: bool = False,
    clip_ranges: list[tuple[float, float] | None] | None = None,
) -> Path:
    """Внутренняя реализация — вызывается в subprocess на Windows."""
    from agents.video_editor.whisper_timestamps import get_word_timestamps_from_video

    target_w, target_h = settings.video_resolution
    fps = settings.video_fps
    bottom_crop = max(0, min(0.2, getattr(settings, "video_bottom_crop", 0.05)))
    quote_font_px = get_mode4_quote_font_size(target_w)

    clips: list[VideoClip] = []
    vc_refs: list[VideoFileClip] = []
    for i, p in enumerate(video_paths):
        path = Path(p)
        if not path.exists():
            logger.warning(f"[Mode4 Assembler] Skip missing: {path}")
            continue
        sub = subtitle_texts[i] if i < len(subtitle_texts) else ""
        spoken = (
            spoken_scripts[i]
            if spoken_scripts and i < len(spoken_scripts) and spoken_scripts[i]
            else None
        )
        author = authors[i] if authors and i < len(authors) else None
        whisper_script = (spoken or sub).strip() if not static_subtitles else ""
        wt, tw = (None, None)
        wlang = (
            whisper_languages[i]
            if whisper_languages and i < len(whisper_languages)
            else None
        )
        subclip_range: tuple[float, float] | None = None
        if clip_ranges and i < len(clip_ranges) and clip_ranges[i] is not None:
            subclip_range = clip_ranges[i]
        if sub and sub.strip() and not static_subtitles and whisper_script:
            wt, tw = get_word_timestamps_from_video(
                path,
                script=whisper_script,
                language=wlang,
                vad_filter=whisper_vad_filter,
            )
            if wt and tw:
                shift = float(getattr(settings, "subtitle_whisper_time_shift_sec", 0.0) or 0.0)
                if shift:
                    wt = [
                        (max(0.0, float(a) + shift), max(0.0, float(b) + shift))
                        for a, b in wt
                    ]
                lead = float(
                    getattr(settings, "subtitle_whisper_word_start_lead_sec", 0.0) or 0.0
                )
                if lead:
                    wt = apply_whisper_word_start_lead(wt, lead_sec=lead)
                logger.info(
                    f"[Mode4 Assembler] Whisper sync: {len(wt)} words (karaoke + voice)"
                )
                sparse_whisper = _whisper_result_too_sparse_for_script(whisper_script, tw)
                if plain_timed_subtitles:
                    est_dur = _clip_duration(path)
                    est_wt, est_tw = _script_timing_from_whisper_speech_window(
                        whisper_script,
                        est_dur,
                        wt,
                        sparse_whisper=sparse_whisper,
                    )
                    if est_wt and est_tw:
                        mode = "full-clip" if sparse_whisper else "speech-window"
                        logger.info(
                            "[Mode4 Assembler] Plain subtitle stable timing: "
                            f"{mode}, whisper={len(tw)}/{_expected_spoken_word_count(whisper_script)} words"
                        )
                        wt, tw = est_wt, est_tw
                elif sparse_whisper:
                    est_dur = _clip_duration(path)
                    est_wt, est_tw = _estimate_karaoke_word_timestamps(whisper_script, est_dur)
                    if est_wt and est_tw:
                        logger.warning(
                            "[Mode4 Assembler] Whisper transcript too sparse "
                            f"({len(tw)}/{_expected_spoken_word_count(whisper_script)} words) "
                            "-> estimated full-script sync"
                        )
                        wt, tw = est_wt, est_tw
            elif whisper_script and (spoken or plain_timed_subtitles):
                # Мультиклип plain_whisper: spoken_scripts=None — без этой ветки при сбое Whisper
                # остаётся static_quote_caption (весь текст сразу), хотя выбран «плоский» стиль.
                est_dur = _clip_duration(path)
                est_src = (spoken.strip() if (spoken and spoken.strip()) else whisper_script)
                wt, tw = _estimate_karaoke_word_timestamps(est_src, est_dur)
                if wt and tw:
                    logger.info(
                        f"[Mode4 Assembler] Whisper unavailable -> estimated "
                        f"{'plain_timed' if plain_timed_subtitles else 'karaoke'} sync: {len(wt)} words"
                    )
            if (
                trim_clips_to_whisper_speech
                and wt
                and len(wt) > 0
                and tw
            ):
                full_dur = _clip_duration(path)
                pad_start = 0.04
                pad_end = 0.07
                t0 = max(0.0, float(wt[0][0]) - pad_start)
                t1 = min(full_dur, float(wt[-1][1]) + pad_end)
                if t1 - t0 > 0.18:
                    subclip_range = (t0, t1)
                    logger.info(
                        f"[Mode4 Assembler] Trim clip to speech [{t0:.2f}s–{t1:.2f}s] "
                        f"(tight join, −{t0:.2f}s lead / −{full_dur - t1:.2f}s tail)"
                    )
        clip, vc = _make_subtitle_clip(
            path,
            target_w,
            target_h,
            fps,
            sub,
            bottom_crop,
            wt,
            tw,
            static_caption=static_subtitles and bool(sub and sub.strip()),
            spoken_script=spoken,
            author_name=author,
            subclip_range=subclip_range,
            header_title=header_title,
            plain_timed_subtitles=plain_timed_subtitles,
        )
        has_sub = bool(sub and str(sub).strip())
        if not has_sub:
            renderer_name = "none"
        elif static_subtitles:
            renderer_name = "static_quote_caption (forced)"
        elif plain_timed_subtitles and wt and tw:
            renderer_name = "plain_whisper_timed"
        elif wt and tw and spoken and spoken.strip():
            renderer_name = "quote_karaoke"
        elif wt and tw:
            renderer_name = "plain_timed_fallback"
        else:
            renderer_name = "static_quote_caption (fallback)"
        logger.info(
            "[Mode4 Assembler] Subtitle renderer: {} | scale={} | quote_font_px={} | sub={} | spoken={} | wt={}",
            renderer_name,
            float(getattr(settings, "mode4_quote_subtitle_scale", 1.6) or 1.6),
            quote_font_px,
            has_sub,
            bool(spoken and spoken.strip()),
            len(wt or []),
        )
        clips.append(clip)
        vc_refs.append(vc)

    if not clips:
        raise ValueError("No valid video clips to assemble")

    from moviepy import concatenate_videoclips
    final = concatenate_videoclips(clips, method="compose")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # MoviePy default: temp_audiofile_path="" → CWD + basename "video_ru" → same path for
    # every parallel job → moov errors / WinError 32. Isolate per output dir + UUID.
    temp_audio = output_path.parent / f"_m4_snd_{uuid.uuid4().hex}.mp4"
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
            temp_audiofile=str(temp_audio),
            temp_audiofile_path=str(output_path.parent),
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
        try:
            temp_audio.unlink(missing_ok=True)
        except OSError:
            pass

    logger.success(f"[Mode4 Assembler] Done → {output_path}")
    return output_path


def _run_in_process(
    paths: list,
    texts: list,
    out: Path,
    static_subtitles: bool,
    err_q: Queue,
    spoken_scripts: list[str] | None,
    authors: list[str | None] | None,
    whisper_languages: list[str | None] | None,
    trim_clips_to_whisper_speech: bool,
    whisper_vad_filter: bool,
    header_title: str | None,
    plain_timed_subtitles: bool,
    clip_ranges: list[tuple[float, float] | None] | None,
) -> None:
    try:
        _assemble_mode4_impl(
            paths,
            texts,
            out,
            static_subtitles=static_subtitles,
            spoken_scripts=spoken_scripts,
            authors=authors,
            whisper_languages=whisper_languages,
            trim_clips_to_whisper_speech=trim_clips_to_whisper_speech,
            whisper_vad_filter=whisper_vad_filter,
            header_title=header_title,
            plain_timed_subtitles=plain_timed_subtitles,
            clip_ranges=clip_ranges,
        )
    except Exception as e:
        err_q.put(e)


def assemble_mode4_video(
    video_paths: list[Path | str],
    subtitle_texts: list[str],
    output_path: Path,
    static_subtitles: bool = False,
    *,
    spoken_scripts: list[str] | None = None,
    authors: list[str | None] | None = None,
    whisper_languages: list[str | None] | None = None,
    trim_clips_to_whisper_speech: bool = False,
    whisper_vad_filter: bool = True,
    header_title: str | None = None,
    plain_timed_subtitles: bool = False,
    clip_ranges: list[tuple[float, float] | None] | None = None,
) -> Path:
    """
    Собирает видео. На Windows — в subprocess (избегаем WinError 32 с temp-файлами).

    trim_clips_to_whisper_speech: обрезать клип по первому/последнему слову Whisper (экспериментально;
    может резать начало речи и ломать караоке — для притчи отключено).
    whisper_vad_filter: False — полная дорожка в Whisper без VAD (лучше первые слова и караоке).
    header_title: опциональный заголовок у верхнего края кадра (весь ролик).
    """
    if sys.platform == "win32":
        q: Queue = Queue()
        p = Process(
            target=_run_in_process,
            args=(
                [str(Path(x)) for x in video_paths],
                subtitle_texts,
                output_path,
                static_subtitles,
                q,
                spoken_scripts,
                authors,
                whisper_languages,
                trim_clips_to_whisper_speech,
                whisper_vad_filter,
                header_title,
                plain_timed_subtitles,
                clip_ranges,
            ),
        )
        p.start()
        p.join()
        if not q.empty():
            raise q.get_nowait()
    else:
        _assemble_mode4_impl(
            video_paths,
            subtitle_texts,
            output_path,
            static_subtitles=static_subtitles,
            spoken_scripts=spoken_scripts,
            authors=authors,
            whisper_languages=whisper_languages,
            trim_clips_to_whisper_speech=trim_clips_to_whisper_speech,
            whisper_vad_filter=whisper_vad_filter,
            header_title=header_title,
            plain_timed_subtitles=plain_timed_subtitles,
            clip_ranges=clip_ranges,
        )
    return output_path
