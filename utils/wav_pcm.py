"""Нарезка WAV без ffmpeg/ffprobe (stdlib wave). Ожидается PCM после ffmpeg (моно/стерео, 16-bit)."""

from __future__ import annotations

import wave
from pathlib import Path


def _open_read(path: Path) -> wave.Wave_read:
    return wave.open(str(path), "rb")


def split_wav_to_chunks(
    input_wav: Path,
    chunk_duration_sec: float,
    output_dir: Path,
    filename_prefix: str = "chunk",
) -> list[tuple[Path, float]]:
    """
    Последовательно читает WAV и пишет chunk_000.wav, …
    Возвращает [(path, duration_sec), ...].
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    chunk_duration_sec = max(0.01, float(chunk_duration_sec))
    out: list[tuple[Path, float]] = []

    with _open_read(input_wav) as wf:
        nch = wf.getnchannels()
        sw = wf.getsampwidth()
        fr = wf.getframerate()
        nframes = wf.getnframes()
        if fr <= 0 or sw <= 0 or nch <= 0:
            raise ValueError(f"Некорректный WAV: ch={nch} sw={sw} fr={fr}")

        bytes_per_frame = nch * sw
        chunk_frames = max(1, int(round(chunk_duration_sec * fr)))
        pos_frames = 0
        ci = 0

        while pos_frames < nframes:
            to_read = min(chunk_frames, nframes - pos_frames)
            wf.setpos(pos_frames)
            data = wf.readframes(to_read)
            if not data:
                break
            frames_written = len(data) // bytes_per_frame
            if frames_written <= 0:
                break
            dur = frames_written / float(fr)
            out_path = output_dir / f"{filename_prefix}_{ci:03d}.wav"
            with wave.open(str(out_path), "wb") as wo:
                wo.setnchannels(nch)
                wo.setsampwidth(sw)
                wo.setframerate(fr)
                wo.writeframes(data)
            out.append((out_path, dur))
            pos_frames += frames_written
            ci += 1

    if not out:
        raise ValueError(f"Пустой или нечитаемый WAV: {input_wav}")
    return out


def slice_wav_time_range(src: Path, t0_sec: float, t1_sec: float, dst: Path) -> None:
    """Вырезает [t0, t1) в секундах по таймлайну WAV."""
    with _open_read(src) as wf:
        nch = wf.getnchannels()
        sw = wf.getsampwidth()
        fr = wf.getframerate()
        nframes = wf.getnframes()
        bytes_per_frame = nch * sw

        f0 = int(max(0.0, t0_sec) * fr)
        f1 = int(min(nframes, max(f0 + 1, round(t1_sec * fr))))
        wf.setpos(f0)
        data = wf.readframes(f1 - f0)

    dst.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dst), "wb") as wo:
        wo.setnchannels(nch)
        wo.setsampwidth(sw)
        wo.setframerate(fr)
        wo.writeframes(data)
