"""
Synthetic sound effects for viral video production.

Sounds are generated with numpy on first use and cached in the sounds/ directory.
Drop custom .mp3 / .wav files with the same names to override the generated ones.

Effects
-------
boom.wav    - Low-frequency hit for the opening title (0.65 s)
whoosh.wav  - Frequency-sweep noise for crossfade transitions (0.45 s)
impact.wav  - Sharp transient for key fact reveals (0.22 s)
snap.wav    - Ultra-short click for subtitle appearance (0.12 s)
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
from loguru import logger

_SR = 44100  # sample rate


# ─────────────────────────────────────────────────────────────────────────────
# Waveform generators
# ─────────────────────────────────────────────────────────────────────────────

def _save_wav(path: Path, samples: np.ndarray, sr: int = _SR) -> None:
    samples = np.clip(samples, -1.0, 1.0)
    pcm = (samples * 32767).astype(np.int16)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def _gen_boom(duration: float = 0.65) -> np.ndarray:
    n = int(duration * _SR)
    t = np.linspace(0, duration, n)
    sub  = np.sin(2 * np.pi * 52  * t) * np.exp(-t * 7.0) * 1.00
    mid  = np.sin(2 * np.pi * 200 * t) * np.exp(-t * 14.0) * 0.35
    high = np.sin(2 * np.pi * 800 * t) * np.exp(-t * 32.0) * 0.12
    noise = np.random.default_rng(0).standard_normal(n) * np.exp(-t * 20) * 0.10
    att = max(1, int(0.025 * _SR))
    env = np.ones(n); env[:att] = np.linspace(0, 1, att)
    return np.clip((sub + mid + high + noise) * env * 0.88, -1, 1)


def _gen_whoosh(duration: float = 0.45) -> np.ndarray:
    n = int(duration * _SR)
    t = np.linspace(0, duration, n)
    freq = np.linspace(1800, 220, n)
    phase = np.cumsum(2 * np.pi * freq / _SR)
    sweep = np.sin(phase) * 0.40
    noise = np.random.default_rng(1).standard_normal(n) * 0.35
    att = max(1, int(0.04 * _SR))
    dec  = max(att + 1, int(0.25 * _SR))
    env  = np.ones(n)
    env[:att]  = np.linspace(0, 1, att)
    env[dec:]  = np.linspace(1, 0, n - dec) ** 1.5
    return np.clip((sweep + noise) * env * 0.55, -1, 1)


def _gen_impact(duration: float = 0.22) -> np.ndarray:
    n = int(duration * _SR)
    t = np.linspace(0, duration, n)
    trans = np.sin(2 * np.pi * 140 * t) * np.exp(-t * 28) * 1.00
    sub   = np.sin(2 * np.pi * 65  * t) * np.exp(-t * 18) * 0.80
    noise = np.random.default_rng(2).standard_normal(n) * np.exp(-t * 22) * 0.45
    att = max(1, int(0.008 * _SR))
    env = np.ones(n); env[:att] = np.linspace(0, 1, att)
    return np.clip((trans + sub + noise) * env * 0.85, -1, 1)


def _gen_snap(duration: float = 0.12) -> np.ndarray:
    n = int(duration * _SR)
    t = np.linspace(0, duration, n)
    click = np.sin(2 * np.pi * 2200 * t) * np.exp(-t * 85) * 0.55
    noise = np.random.default_rng(3).standard_normal(n) * np.exp(-t * 65) * 0.28
    att = max(1, int(0.003 * _SR))
    env = np.ones(n); env[:att] = np.linspace(0, 1, att)
    return np.clip((click + noise) * env, -1, 1)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

_GENERATORS: dict[str, callable] = {
    "boom.wav":   _gen_boom,
    "whoosh.wav": _gen_whoosh,
    "impact.wav": _gen_impact,
    "snap.wav":   _gen_snap,
}


def ensure_sounds(sounds_dir: Path) -> None:
    """Generate all missing sound-effect files inside `sounds_dir`."""
    sounds_dir.mkdir(parents=True, exist_ok=True)
    for filename, gen in _GENERATORS.items():
        p = sounds_dir / filename
        if not p.exists():
            logger.info(f"[SoundFX] Generating {filename} ...")
            _save_wav(p, gen())


class SoundEffects:
    """Provides paths to all sound-effect files, generating them if needed."""

    def __init__(self, sounds_dir: Path) -> None:
        ensure_sounds(sounds_dir)
        self._dir = sounds_dir

    def _get(self, name: str) -> Path | None:
        p = self._dir / name
        return p if p.exists() else None

    @property
    def boom(self)   -> Path | None: return self._get("boom.wav")
    @property
    def whoosh(self) -> Path | None: return self._get("whoosh.wav")
    @property
    def impact(self) -> Path | None: return self._get("impact.wav")
    @property
    def snap(self)   -> Path | None: return self._get("snap.wav")
