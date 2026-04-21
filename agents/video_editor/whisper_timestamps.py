"""
Word-level timestamps from video/audio via Whisper (faster-whisper).

Mode 4: максимальная синхронизация караоке с озвучкой FastGen.
- Кэш одной модели на процесс (не грузить large/medium на каждый ролик)
- GPU: large-v3 float16; CPU: medium int8; при ошибке — откат по цепочке
- Язык ru/en задаётся явно — точнее границы слов, чем автоопределение
- temperature=0, beam_size=5, vad_filter — стабильные таймкоды
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    pass

# Кэш модели внутри процесса (важно для Windows subprocess в mode4 assembler)
_whisper_model = None
_whisper_model_id: str = ""


def _try_load_model(name: str, device: str, compute_type: str):
    from config import settings
    from faster_whisper import WhisperModel

    dr = (settings.whisper_download_root or "").strip()
    return WhisperModel(
        name,
        device=device,
        compute_type=compute_type,
        download_root=dr or None,
    )


def _get_whisper_model():
    """Один раз загрузить максимально доступную по железу модель."""
    global _whisper_model, _whisper_model_id
    if _whisper_model is not None:
        return _whisper_model

    logger.info(
        "[Whisper] Первая загрузка модели: при необходимости идёт скачивание с Hugging Face "
        "(может занять несколько минут). Не перезагружайте uvicorn и не сохраняйте файлы в .venv — иначе загрузка прервётся."
    )

    from config import settings

    override = (settings.whisper_model_size or "").strip()
    if override in (
        "tiny",
        "base",
        "small",
        "medium",
        "large-v2",
        "large-v3",
    ):
        order = []
        try:
            import torch

            if torch.cuda.is_available():
                order.extend(
                    [
                        (override, "cuda", "float16"),
                        (override, "cuda", "int8_float16"),
                    ]
                )
        except ImportError:
            pass
        order.append((override, "cpu", "int8"))
    else:
        order = []
        try:
            import torch

            if torch.cuda.is_available():
                order.extend(
                    [
                        ("large-v3", "cuda", "float16"),
                        ("large-v3", "cuda", "int8_float16"),
                        ("medium", "cuda", "float16"),
                    ]
                )
        except ImportError:
            pass
        order.extend(
            [
                ("medium", "cpu", "int8"),
                ("small", "cpu", "int8"),
                ("base", "cpu", "int8"),
            ]
        )

    last_err: Exception | None = None
    for name, dev, ct in order:
        try:
            m = _try_load_model(name, dev, ct)
            _whisper_model = m
            _whisper_model_id = f"{name}|{dev}|{ct}"
            logger.info(f"[Whisper] Loaded model {_whisper_model_id} (max sync preset)")
            return m
        except Exception as e:
            last_err = e
            logger.debug(f"[Whisper] Skip {name} {dev} {ct}: {e}")
            continue

    if last_err:
        logger.warning(f"[Whisper] No model loaded: {last_err}")
    raise RuntimeError("faster-whisper: failed to load any model") from last_err


def get_word_timestamps_from_video(
    video_path: str | Path,
    script: str | None = None,
    *,
    language: str | None = None,
    vad_filter: bool = True,
) -> tuple[list[tuple[float, float]] | None, list[str] | None]:
    """
    Транскрипция аудио дорожки ролика → (word_timestamps, words).

    script: подсказка Whisper (начало цитаты), до ~220 символов.
    language: «ru» | «en» — задавать для Mode 4 (совпадает с языком ролика), иначе авто.
    vad_filter: False — не отрезать тихие участки (чаще совпадает караоке с началом речи).
    """
    try:
        import faster_whisper  # noqa: F401 — проверка установки
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
            vc.audio.write_audiofile(tmp_wav, fps=16000, nbytes=2, logger=None)
            vc.close()
        except Exception:
            vc.close()
            try:
                Path(tmp_wav).unlink(missing_ok=True)
            except Exception:
                pass
            return (None, None)

        try:
            model = _get_whisper_model()
            initial_prompt = (script or "").strip()[:480] or None
            lang = None
            if language and str(language).strip():
                lang = str(language).strip().lower()[:2]
                if lang not in ("ru", "en", "de", "fr", "es", "it", "pt", "pl", "uk"):
                    lang = None

            transcribe_kw: dict = dict(
                language=lang,
                task="transcribe",
                beam_size=5,
                temperature=0,
                word_timestamps=True,
                initial_prompt=initial_prompt,
                condition_on_previous_text=True,
            )
            if vad_filter:
                transcribe_kw["vad_filter"] = True
                transcribe_kw["vad_parameters"] = {"min_silence_duration_ms": 100}
            else:
                transcribe_kw["vad_filter"] = False

            segments, _info = model.transcribe(tmp_wav, **transcribe_kw)

            word_timestamps: list[tuple[float, float]] = []
            tts_words: list[str] = []
            for seg in segments:
                if seg.words:
                    for w in seg.words:
                        word_timestamps.append((w.start, w.end))
                        tts_words.append(w.word or " ")
                else:
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


def get_word_timestamps_from_audio_path(
    audio_path: str | Path,
    script: str | None = None,
    *,
    language: str | None = None,
    vad_filter: bool = False,
) -> tuple[list[tuple[float, float]] | None, list[str] | None]:
    """
    Транскрипция аудиофайла (любой формат, конвертация во временный WAV 16 kHz).
    """
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        logger.debug("[Whisper] faster-whisper not installed")
        return (None, None)

    path = Path(audio_path)
    if not path.is_file():
        return (None, None)

    tmp_wav: str | None = None
    try:
        from utils.ffmpeg_resolve import resolve_ffmpeg_executable

        ff = resolve_ffmpeg_executable()
        if not ff:
            logger.warning("[Whisper] ffmpeg not found (PATH / FFMPEG_PATH / imageio-ffmpeg)")
            return (None, None)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_wav = f.name
        cmd = [
            ff,
            "-y",
            "-i",
            str(path),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "wav",
            tmp_wav,
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=3600)
        if not Path(tmp_wav).is_file() or Path(tmp_wav).stat().st_size < 64:
            return (None, None)

        model = _get_whisper_model()
        initial_prompt = (script or "").strip()[:480] or None
        lang = None
        if language and str(language).strip():
            lang = str(language).strip().lower()[:2]
            if lang not in ("ru", "en", "de", "fr", "es", "it", "pt", "pl", "uk"):
                lang = None

        transcribe_kw: dict = dict(
            language=lang,
            task="transcribe",
            beam_size=5,
            temperature=0,
            word_timestamps=True,
            initial_prompt=initial_prompt,
            condition_on_previous_text=True,
        )
        if vad_filter:
            transcribe_kw["vad_filter"] = True
            transcribe_kw["vad_parameters"] = {"min_silence_duration_ms": 100}
        else:
            transcribe_kw["vad_filter"] = False

        segments, _info = model.transcribe(tmp_wav, **transcribe_kw)

        word_timestamps: list[tuple[float, float]] = []
        tts_words: list[str] = []
        for segm in segments:
            if segm.words:
                for w in segm.words:
                    word_timestamps.append((w.start, w.end))
                    tts_words.append(w.word or " ")
            else:
                word_timestamps.append((segm.start, segm.end))
                tts_words.append(segm.text.strip() or " ")
        if not word_timestamps or not tts_words:
            return (None, None)
        return (word_timestamps, tts_words)
    except Exception as e:
        logger.warning(f"[Whisper] Audio transcription failed: {e}")
        return (None, None)
    finally:
        if tmp_wav:
            try:
                Path(tmp_wav).unlink(missing_ok=True)
            except Exception:
                pass
