"""
Word-level timestamps from video/audio via Whisper.
Used for Mode 4 quote videos — sync subtitles with FastGen voice.
If faster-whisper unavailable, returns (None, None) → fallback to word-length-weighted.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    pass


def get_word_timestamps_from_video(
    video_path: str | Path,
    script: str | None = None,
) -> tuple[list[tuple[float, float]] | None, list[str] | None]:
    """
    Извлекает аудио из видео, транскрибирует через Whisper, возвращает timestamps по словам.
    script: исходный текст цитаты — используется как initial_prompt для лучшего распознавания.
    Returns (word_timestamps, tts_words) или (None, None) при ошибке.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        logger.debug("[Whisper] faster-whisper not installed, using word-length fallback")
        return (None, None)

    path = Path(video_path)
    if not path.exists():
        return (None, None)

    try:
        from moviepy import VideoFileClip
        vc = VideoFileClip(str(path))
        if vc.audio is None:
            vc.close()
            return (None, None)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_wav = f.name
        try:
            vc.audio.write_audiofile(tmp_wav, fps=16000, logger=None)
            vc.close()
        except Exception:
            vc.close()
            try:
                Path(tmp_wav).unlink(missing_ok=True)
            except Exception:
                pass
            return (None, None)

        try:
            model = WhisperModel("base", device="cpu", compute_type="int8")
            initial_prompt = (script or "").strip()[:220] or None  # Whisper limit ~224 tokens
            segments, _ = model.transcribe(
                tmp_wav,
                word_timestamps=True,
                language=None,
                initial_prompt=initial_prompt,
            )
            word_timestamps: list[tuple[float, float]] = []
            tts_words: list[str] = []
            for seg in segments:
                if seg.words:
                    for w in seg.words:
                        word_timestamps.append((w.start, w.end))
                        tts_words.append(w.word or " ")
                else:
                    # Fallback: treat whole segment as one word
                    word_timestamps.append((seg.start, seg.end))
                    tts_words.append(seg.text.strip() or " ")
            if not word_timestamps or not tts_words:
                return (None, None)
            return (word_timestamps, tts_words)
        except Exception as e:
            logger.warning(f"[Whisper] Transcription failed: {e}")
            return (None, None)
        finally:
            try:
                Path(tmp_wav).unlink(missing_ok=True)
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"[Whisper] Failed to process {path}: {e}")
        return (None, None)
