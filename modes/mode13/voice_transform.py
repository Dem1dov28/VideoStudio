"""Смена «голоса» и подготовка озвучки: ffmpeg (тембр, темп, шумы, уровень).

Цепочка собрана так, чтобы уменьшить «роботизацию» и шум от шумодава:
- шумодав (afftdn) и срез НЧ — до сдвига тона;
- качественный resample после asetrate;
- выравнивание громкости (dynaudnorm) — в конце, после темпа.

«Идеальный» в смысле продакшена = пресет studio (без смены тембра, мягкая очистка).
Полная перезапись голоса без артефактов одним ffmpeg невозможна — для этого нужны отдельные AI-модели.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger

from utils.ffmpeg_resolve import require_ffmpeg_or_raise

# original: только моно 48 kHz WAV без фильтров.
# studio: максимально аккуратная очистка + ровный уровень, тембр как в записи.
# natural: только НЧ + лёгкая нормализация, без afftdn.
# calm: чуть медленнее + мягкий шумодав (обновлённая цепочка).
# soft/medium/strong: тембр выше (asetrate/atempo), лёгкая обработка до/после.

_PRESETS: dict[str, dict[str, Any]] = {
    "studio": {"pitch": 1.0, "tempo": 1.0, "clean": "studio"},
    "calm": {"pitch": 1.0, "tempo": 0.90, "clean": "full"},
    "natural": {"pitch": 1.0, "tempo": 1.0, "clean": "natural"},
    "soft": {"pitch": 1.05, "tempo": 1.0, "clean": "light"},
    "medium": {"pitch": 1.09, "tempo": 1.0, "clean": "light"},
    "strong": {"pitch": 1.14, "tempo": 1.0, "clean": "light"},
}

# Качественный ресемплинг после asetrate (меньше «звона», чем настройки по умолчанию).
_ARESAMPLE_HQ = "aresample=48000:filter_size=64:cutoff=0.95"
_ARNNDN_MODEL_WARNED = False


def _escape_filter_path(path: Path) -> str:
    raw = str(path.resolve()).replace("\\", "/")
    return raw.replace(":", r"\:")


def _resolve_arnndn_model_path() -> Path | None:
    candidates: list[Path] = []
    try:
        from config import settings

        explicit = (getattr(settings, "mode13_arnndn_model_path", None) or "").strip()
        if explicit:
            candidates.append(Path(explicit))
        root = Path(settings.project_root)
    except Exception:
        root = Path(__file__).resolve().parents[2]

    env_model = (os.environ.get("MODE13_ARNNDN_MODEL_PATH") or "").strip()
    if env_model:
        candidates.append(Path(env_model))

    search_dirs = [
        root / "models" / "arnndn",
        root / "arnndn-models",
        root / "models",
        root,
    ]
    for base in search_dirs:
        candidates.extend(
            [
                base / "std.rnnn",
                base / "bd.rnnn",
                base / "cb.rnnn",
            ]
        )
        try:
            candidates.extend(sorted(base.glob("*.rnnn")))
        except OSError:
            continue

    seen: set[str] = set()
    for cand in candidates:
        try:
            resolved = cand.expanduser().resolve()
        except OSError:
            continue
        rs = str(resolved)
        if rs in seen:
            continue
        seen.add(rs)
        if resolved.is_file():
            return resolved
    return None


def _build_ai_cleanup_filter(ai_cleanup_0_100: float) -> str:
    strength = max(0.0, min(100.0, float(ai_cleanup_0_100)))
    if strength < 0.5:
        return ""

    model = _resolve_arnndn_model_path()
    if not model:
        global _ARNNDN_MODEL_WARNED
        if not _ARNNDN_MODEL_WARNED:
            logger.warning(
                "[Mode13] AI cleanup requested, but arnndn model was not found. "
                "Set MODE13_ARNNDN_MODEL_PATH or place a .rnnn model in models/arnndn."
            )
            _ARNNDN_MODEL_WARNED = True
        return ""

    mix = 0.55 + (strength / 100.0) * 0.40
    return f"arnndn=m='{_escape_filter_path(model)}':mix={mix:.2f}"


def _build_pre_post_dynamic(
    clean: str,
    *,
    ai_cleanup_0_100: float,
    noise_0_100: float,
    norm_0_100: float,
    highpass_hz: int | None,
    deesser_0_100: float,
    clarity_0_100: float,
    mud_cut_0_100: float,
    compression_0_100: float,
) -> tuple[str, str]:
    """
    Сборка pre/post из ползунков (0–100).
    noise: 0 ≈ без afftdn; 100 — сильный шумодав.
    norm: целевая loudness-нормализация (EBU R128, single-pass).
    highpass_hz: None — частота по типу clean; иначе явная (40–200 Гц).
    """
    c = (clean or "none").strip().lower()
    hp_default = {"natural": 60, "studio": 55, "light": 70, "full": 65, "none": 55}
    hp = int(highpass_hz) if highpass_hz is not None and 40 <= int(highpass_hz) <= 200 else hp_default.get(c, 55)

    pre_parts: list[str] = [f"highpass=f={hp}"]
    ai_filter = _build_ai_cleanup_filter(ai_cleanup_0_100)
    if ai_filter:
        pre_parts.append(ai_filter)
    n = max(0.0, min(100.0, float(noise_0_100)))
    if n >= 0.5:
        nr = max(1, min(8, int(round(1.0 + (n / 100.0) * 7.0))))
        nf = int(round(-36.0 + (n / 100.0) * 11.0))
        pre_parts.append(f"afftdn=nf={nf}:nr={nr}:tn=0")
    pre = ",".join(pre_parts)

    post_parts: list[str] = []

    mud = max(0.0, min(100.0, float(mud_cut_0_100)))
    if mud >= 0.5:
        mud_cut_db = 1.0 + (mud / 100.0) * 6.0
        post_parts.append(f"equalizer=f=260:t=h:w=220:g=-{mud_cut_db:.1f}")

    clr = max(0.0, min(100.0, float(clarity_0_100)))
    if clr >= 0.5:
        clarity_db = 0.8 + (clr / 100.0) * 5.2
        post_parts.append(f"equalizer=f=3200:t=h:w=1900:g={clarity_db:.1f}")

    ds = max(0.0, min(100.0, float(deesser_0_100)))
    if ds >= 0.5:
        deesser_db = 1.0 + (ds / 100.0) * 8.0
        post_parts.append(f"equalizer=f=6500:t=h:w=3200:g=-{deesser_db:.1f}")

    comp = max(0.0, min(100.0, float(compression_0_100)))
    if comp >= 0.5:
        threshold = 0.22 - (comp / 100.0) * 0.15
        ratio = 1.5 + (comp / 100.0) * 2.5
        attack = 12.0 - (comp / 100.0) * 7.0
        release = 180.0 - (comp / 100.0) * 90.0
        post_parts.append(
            "acompressor="
            f"threshold={max(0.05, threshold):.3f}:"
            f"ratio={ratio:.2f}:"
            f"attack={max(3.0, attack):.1f}:"
            f"release={max(60.0, release):.1f}:"
            "makeup=1"
        )

    v = max(0.0, min(100.0, float(norm_0_100)))
    loudness_i = -18.5 + (v / 100.0) * 3.5
    loudness_lra = 12.0 - (v / 100.0) * 5.0
    post_parts.append(f"loudnorm=I={loudness_i:.1f}:LRA={loudness_lra:.1f}:TP=-1.5")
    post = ",".join(post_parts)
    return pre, post


def _clean_profile(name: str) -> tuple[str, str]:
    """
    Возвращает (pre_pitch, post_all) — фильтры до сдвига тона и финальная обработка.
    pre: highpass + опционально afftdn на исходной частоте.
    post: dynaudnorm после темпа/питча — меньше взаимных артефактов.
    """
    c = (name or "none").strip().lower()
    if c == "none":
        return "", ""
    if c == "natural":
        return "highpass=f=60", "dynaudnorm=f=1500:g=3"
    if c == "studio":
        # Очень мягкий шумодав; длинное окно и маленький gain — без «пампинга» шума.
        return (
            "highpass=f=55,"
            "afftdn=nf=-32:nr=3:tn=0"
        ), "dynaudnorm=f=2000:g=2.5"
    if c == "light":
        return (
            "highpass=f=70,"
            "afftdn=nf=-30:nr=4:tn=0"
        ), "dynaudnorm=f=1200:g=5"
    if c == "full":
        return (
            "highpass=f=65,"
            "afftdn=nf=-28:nr=5:tn=0"
        ), "dynaudnorm=f=1200:g=5"
    return "", ""


def _atempo_chain(factor: float) -> list[str]:
    """atempo принимает 0.5–2.0; разбиваем произвольный коэффициент."""
    t = float(factor)
    if t >= 0.999:
        return []
    out: list[str] = []
    while t < 0.5:
        out.append("atempo=0.5")
        t /= 0.5
    while t > 2.0:
        out.append("atempo=2.0")
        t /= 2.0
    if t < 0.999:
        out.append(f"atempo={t:.6f}")
    return out


def _apply_voice_tuning(
    cfg: dict[str, Any],
    *,
    tempo_scale: float = 1.0,
    pitch_semitones: float = 0.0,
    ai_cleanup: float | None = None,
    noise_suppression: float | None = None,
    level_normalize: float | None = None,
    highpass_hz: int | None = None,
    deesser: float | None = None,
    clarity: float | None = None,
    mud_cut: float | None = None,
    compression: float | None = None,
) -> dict[str, Any]:
    out = dict(cfg)
    if ai_cleanup is not None:
        out["ai_cleanup"] = max(0.0, min(100.0, float(ai_cleanup)))
    if noise_suppression is not None:
        out["noise_suppression"] = max(0.0, min(100.0, float(noise_suppression)))
    if level_normalize is not None:
        out["level_normalize"] = max(0.0, min(100.0, float(level_normalize)))
    if highpass_hz is not None and int(highpass_hz) >= 40:
        out["highpass_hz"] = int(highpass_hz)
    if deesser is not None:
        out["deesser"] = max(0.0, min(100.0, float(deesser)))
    if clarity is not None:
        out["clarity"] = max(0.0, min(100.0, float(clarity)))
    if mud_cut is not None:
        out["mud_cut"] = max(0.0, min(100.0, float(mud_cut)))
    if compression is not None:
        out["compression"] = max(0.0, min(100.0, float(compression)))
    ts = float(tempo_scale)
    if abs(ts - 1.0) > 1e-6:
        out["tempo"] = max(0.5, min(1.35, float(out["tempo"]) * ts))
    st = float(pitch_semitones)
    if abs(st) > 1e-6:
        out["pitch"] = max(0.85, min(1.22, float(out["pitch"]) * (2.0 ** (st / 12.0))))
    return out


def _append_volume(af: str, gain_db: float) -> str:
    if abs(float(gain_db)) < 0.05:
        return af
    v = f"volume={float(gain_db):.2f}dB"
    return f"{af},{v}" if af else v


def _build_af(cfg: dict[str, Any]) -> str:
    pitch = float(cfg["pitch"])
    tempo = float(cfg.get("tempo", 1.0))
    clean = str(cfg.get("clean", "none"))
    if cfg.get("noise_suppression") is not None and cfg.get("level_normalize") is not None:
        hp = cfg.get("highpass_hz")
        hp_i = int(hp) if hp is not None and int(hp) >= 40 else None
        pre, post = _build_pre_post_dynamic(
            clean,
            ai_cleanup_0_100=float(cfg.get("ai_cleanup", 0.0)),
            noise_0_100=float(cfg["noise_suppression"]),
            norm_0_100=float(cfg["level_normalize"]),
            highpass_hz=hp_i,
            deesser_0_100=float(cfg.get("deesser", 0.0)),
            clarity_0_100=float(cfg.get("clarity", 0.0)),
            mud_cut_0_100=float(cfg.get("mud_cut", 0.0)),
            compression_0_100=float(cfg.get("compression", 0.0)),
        )
    else:
        pre, post = _clean_profile(clean)

    chunks: list[str] = []
    if pre:
        chunks.append(pre)

    if abs(pitch - 1.0) >= 1e-5:
        if not pre:
            chunks.append("highpass=f=55")
        inv = 1.0 / pitch
        chunks.append(f"asetrate=48000*{pitch:.6f}")
        chunks.append(_ARESAMPLE_HQ)
        chunks.append(f"atempo={inv:.6f}")
    else:
        if not pre:
            chunks.append("highpass=f=55")

    chunks.extend(_atempo_chain(tempo))

    if post:
        chunks.append(post)

    return ",".join(chunks)


def convert_upload_to_mono_wav48(input_path: Path, output_wav: Path) -> None:
    """Публичная обёртка: любой поддерживаемый ffmpeg формат → моно 48 kHz s16le WAV."""
    _remux_to_wav_mono48(input_path, output_wav)


def _remux_to_wav_mono48(input_path: Path, output_wav: Path) -> None:
    """Без audio-фильтров: только моно + 48 kHz s16le для чанков и Whisper."""
    ff = require_ffmpeg_or_raise()
    cmd = [
        ff,
        "-y",
        "-i",
        str(input_path),
        "-ac",
        "1",
        "-ar",
        "48000",
        "-sample_fmt",
        "s16",
        str(output_wav),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=3600)
    except subprocess.CalledProcessError as e:
        err = (e.stderr or e.stdout or str(e))[:800]
        raise RuntimeError(
            f"ffmpeg не смог сконвертировать аудио в WAV (режим «как в файле»).\n{err}"
        ) from e


def transform_voice_to_wav(
    input_path: Path,
    output_wav: Path,
    preset: str = "studio",
    *,
    gain_db: float = 0.0,
    tempo_scale: float = 1.0,
    pitch_semitones: float = 0.0,
    ai_cleanup: float | None = None,
    noise_suppression: float | None = None,
    level_normalize: float | None = None,
    highpass_hz: int | None = None,
    deesser: float | None = None,
    clarity: float | None = None,
    mud_cut: float | None = None,
    compression: float | None = None,
) -> None:
    """Моно WAV 48 kHz PCM через ffmpeg. Без ffmpeg — RuntimeError с понятным текстом."""
    output_wav.parent.mkdir(parents=True, exist_ok=True)

    key = (preset or "studio").strip().lower()
    if key == "original":
        ff = require_ffmpeg_or_raise()
        if abs(float(gain_db)) < 0.05:
            _remux_to_wav_mono48(input_path, output_wav)
        else:
            cmd = [
                ff,
                "-y",
                "-i",
                str(input_path),
                "-af",
                _append_volume("", float(gain_db)),
                "-ac",
                "1",
                "-ar",
                "48000",
                "-sample_fmt",
                "s16",
                str(output_wav),
            ]
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=3600)
        if not output_wav.is_file() or output_wav.stat().st_size < 64:
            raise RuntimeError("ffmpeg не создал корректный WAV — пустой или отсутствующий файл.")
        logger.info(f"[Mode13] Voice passthrough (original) → {output_wav.name}")
        return

    ff = require_ffmpeg_or_raise()
    base = dict(_PRESETS.get(key, _PRESETS["studio"]))
    ai = 0.0 if ai_cleanup is None else max(0.0, min(100.0, float(ai_cleanup)))
    ns = 50.0 if noise_suppression is None else max(0.0, min(100.0, float(noise_suppression)))
    ln = 50.0 if level_normalize is None else max(0.0, min(100.0, float(level_normalize)))
    ds = 0.0 if deesser is None else max(0.0, min(100.0, float(deesser)))
    cl = 0.0 if clarity is None else max(0.0, min(100.0, float(clarity)))
    mc = 0.0 if mud_cut is None else max(0.0, min(100.0, float(mud_cut)))
    cp = 0.0 if compression is None else max(0.0, min(100.0, float(compression)))
    cfg = _apply_voice_tuning(
        base,
        tempo_scale=float(tempo_scale),
        pitch_semitones=float(pitch_semitones),
        ai_cleanup=ai,
        noise_suppression=ns,
        level_normalize=ln,
        highpass_hz=highpass_hz,
        deesser=ds,
        clarity=cl,
        mud_cut=mc,
        compression=cp,
    )
    af = _append_volume(_build_af(cfg), float(gain_db))

    cmd = [
        ff,
        "-y",
        "-i",
        str(input_path),
        "-af",
        af,
        "-ac",
        "1",
        "-ar",
        "48000",
        "-sample_fmt",
        "s16",
        str(output_wav),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=3600)
    except subprocess.CalledProcessError as e:
        err = (e.stderr or e.stdout or str(e))[:800]
        raise RuntimeError(
            f"ffmpeg не смог обработать аудио (смена тембра). Проверьте файл и кодеки.\n{err}"
        ) from e
    except FileNotFoundError as e:
        raise RuntimeError(
            "ffmpeg не найден. Задайте FFMPEG_PATH в .env или добавьте ffmpeg в PATH."
        ) from e

    if not output_wav.is_file() or output_wav.stat().st_size < 64:
        raise RuntimeError("ffmpeg не смог создать корректный WAV — пустой или отсутствующий файл.")

    logger.info(f"[Mode13] Voice transform OK ({preset}) → {output_wav.name}")


def render_voice_preview_wav(
    input_path: Path,
    output_wav: Path,
    preset: str,
    *,
    gain_db: float = 0.0,
    tempo_scale: float = 1.0,
    pitch_semitones: float = 0.0,
    ai_cleanup: float | None = None,
    noise_suppression: float | None = None,
    level_normalize: float | None = None,
    highpass_hz: int | None = None,
    deesser: float | None = None,
    clarity: float | None = None,
    mud_cut: float | None = None,
    compression: float | None = None,
    max_seconds: float = 45.0,
) -> None:
    """Короткий отрывок с теми же фильтрами, что и в пайплайне — для предпрослушивания в UI."""
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    dur = max(5.0, min(120.0, float(max_seconds)))
    key = (preset or "studio").strip().lower()
    ff = require_ffmpeg_or_raise()

    if key == "original":
        if abs(float(gain_db)) < 0.05:
            cmd = [
                ff,
                "-y",
                "-t",
                str(dur),
                "-i",
                str(input_path),
                "-ac",
                "1",
                "-ar",
                "48000",
                "-sample_fmt",
                "s16",
                str(output_wav),
            ]
        else:
            cmd = [
                ff,
                "-y",
                "-t",
                str(dur),
                "-i",
                str(input_path),
                "-af",
                _append_volume("", float(gain_db)),
                "-ac",
                "1",
                "-ar",
                "48000",
                "-sample_fmt",
                "s16",
                str(output_wav),
            ]
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
        return

    base = dict(_PRESETS.get(key, _PRESETS["studio"]))
    ai = 0.0 if ai_cleanup is None else max(0.0, min(100.0, float(ai_cleanup)))
    ns = 50.0 if noise_suppression is None else max(0.0, min(100.0, float(noise_suppression)))
    ln = 50.0 if level_normalize is None else max(0.0, min(100.0, float(level_normalize)))
    ds = 0.0 if deesser is None else max(0.0, min(100.0, float(deesser)))
    cl = 0.0 if clarity is None else max(0.0, min(100.0, float(clarity)))
    mc = 0.0 if mud_cut is None else max(0.0, min(100.0, float(mud_cut)))
    cp = 0.0 if compression is None else max(0.0, min(100.0, float(compression)))
    cfg = _apply_voice_tuning(
        base,
        tempo_scale=float(tempo_scale),
        pitch_semitones=float(pitch_semitones),
        ai_cleanup=ai,
        noise_suppression=ns,
        level_normalize=ln,
        highpass_hz=highpass_hz,
        deesser=ds,
        clarity=cl,
        mud_cut=mc,
        compression=cp,
    )
    af = _append_volume(_build_af(cfg), float(gain_db))
    cmd = [
        ff,
        "-y",
        "-t",
        str(dur),
        "-i",
        str(input_path),
        "-af",
        af,
        "-ac",
        "1",
        "-ar",
        "48000",
        "-sample_fmt",
        "s16",
        str(output_wav),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
