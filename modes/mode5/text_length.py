"""Shared helpers for measuring TTS-relevant text length (excludes VoiceAPI length padding)."""

from __future__ import annotations

from agents.video_editor.tts import NONSPOKEN_LEN_FILLER_CHAR


def spoken_plain_len(text: str) -> int:
    """Length of text that affects TTS (invisible VoiceAPI padding is not counted)."""
    return len((text or "").replace(NONSPOKEN_LEN_FILLER_CHAR, "").strip())
