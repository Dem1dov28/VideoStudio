"""Shared helpers for measuring TTS-relevant text length (excludes VoiceAPI length padding)."""

from __future__ import annotations

from agents.video_editor.tts import NONSPOKEN_LEN_FILLER_CHAR

_WORDS_PER_MIN = {"ru": 135.0, "en": 150.0}


def mode5_approx_speech_sec(text: str, language: str) -> float:
    """Rough TTS duration from word count (same scale as chunk budgeting in Mode5 pipeline)."""
    lang = str(language or "ru").strip().lower()
    wpm = _WORDS_PER_MIN["en" if lang.startswith("en") else "ru"]
    words = len(str(text or "").split())
    if words <= 0:
        return 4.0
    return (words / wpm) * 60.0


def mode5_trim_strings_by_estimated_speech(
    strings: list[str],
    *,
    language: str,
    target_sec: float,
) -> list[str]:
    """
    Keep a prefix of strings until cumulative estimated speech reaches target_sec.
    Always returns at least one string when input is non-empty (same rules as pipeline test_run).
    """
    if target_sec <= 0.0 or not strings:
        return list(strings)
    acc = 0.0
    out: list[str] = []
    for s in strings:
        est = mode5_approx_speech_sec(s, language)
        out.append(s)
        acc += est
        if acc >= target_sec:
            break
    if not out:
        out = [strings[0]]
    return out


def spoken_plain_len(text: str) -> int:
    """Length of text that affects TTS (invisible VoiceAPI padding is not counted)."""
    return len((text or "").replace(NONSPOKEN_LEN_FILLER_CHAR, "").strip())
