"""Поиск исполняемого файла ffmpeg (WinError 2, если только «ffmpeg» без PATH)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

# pydub при import проверяет shutil.which("ffmpeg") — без каталога в PATH сразу RuntimeWarning
_ffmpeg_bin_prepended_to_path = False


def resolve_ffmpeg_executable() -> str | None:
    """
    Порядок: FFMPEG_PATH в settings → переменная окружения FFMPEG_PATH → shutil.which('ffmpeg')
    → типичные пути на Windows.
    """
    candidates: list[Path] = []

    try:
        from config import settings

        raw = (getattr(settings, "ffmpeg_path", None) or "").strip()
        if raw:
            candidates.append(Path(raw))
    except Exception:
        pass

    envp = (os.environ.get("FFMPEG_PATH") or "").strip()
    if envp:
        candidates.append(Path(envp))

    w = shutil.which("ffmpeg")
    if w:
        candidates.append(Path(w))

    try:
        import imageio_ffmpeg

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled:
            candidates.append(Path(bundled))
    except Exception:
        pass

    if os.name == "nt":
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pfx86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        la = os.environ.get("LOCALAPPDATA", "")
        extra = [
            Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
            Path(pf) / "ffmpeg" / "bin" / "ffmpeg.exe",
            Path(pfx86) / "ffmpeg" / "bin" / "ffmpeg.exe",
        ]
        if la:
            extra.append(Path(la) / "ffmpeg" / "bin" / "ffmpeg.exe")
        candidates.extend(extra)

    seen: set[str] = set()
    for c in candidates:
        try:
            r = c.expanduser()
            if not r.is_file():
                continue
            rs = str(r.resolve())
            if rs in seen:
                continue
            seen.add(rs)
            return rs
        except OSError:
            continue
    return None


def require_ffmpeg_or_raise() -> str:
    """Для режима 13 и любых операций, где pydub/moviepy ждут ffmpeg в PATH."""
    exe = resolve_ffmpeg_executable()
    if not exe:
        raise RuntimeError(
            "Режим 13 требует ffmpeg: установите пакет imageio-ffmpeg (идёт с moviepy), "
            "либо добавьте ffmpeg в PATH, либо укажите в .env:\n"
            "FFMPEG_PATH=C:/ffmpeg/bin/ffmpeg.exe"
        )
    configure_pydub_ffmpeg()
    return exe


def configure_pydub_ffmpeg() -> str | None:
    """Задать pydub AudioSegment.converter/ffprobe, чтобы from_file/export не ловили WinError 2."""
    global _ffmpeg_bin_prepended_to_path
    exe = resolve_ffmpeg_executable()
    if not exe:
        return None
    bindir = str(Path(exe).resolve().parent)
    if not _ffmpeg_bin_prepended_to_path:
        os.environ["PATH"] = bindir + os.pathsep + os.environ.get("PATH", "")
        _ffmpeg_bin_prepended_to_path = True
    try:
        from pydub import AudioSegment

        AudioSegment.converter = exe
        parent = Path(exe).parent
        probe = parent / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
        if probe.is_file():
            AudioSegment.ffprobe = str(probe)
        else:
            which_probe = shutil.which("ffprobe")
            if which_probe:
                AudioSegment.ffprobe = which_probe
    except Exception:
        return exe
    return exe
