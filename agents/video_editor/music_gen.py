"""
AI background music generator using Meta's MusicGen (facebook/musicgen-small).

The module generates a short ambient/electronic track tailored to the video's
topic and caches it as a WAV file so repeated runs with the same topic reuse
the same audio without re-generating.

Model: facebook/musicgen-small (~300 MB, CPU-friendly, ~30-60 s generation)
Fallback: silent (no music) if transformers / torch are not installed.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from loguru import logger

# ─────────────────────────────────────────────────────────────────────────────
# Mood / prompt mapping for "Излом" style
# ─────────────────────────────────────────────────────────────────────────────

_MOOD_KEYWORDS: list[tuple[list[str], str]] = [
    # keywords (ru + en) → music style description
    (["космос", "вселенн", "галактик", "квантов", "планет", "space", "universe", "galaxy", "quantum", "planet"],
     "dark ambient electronic, deep space atmosphere, slow pulsing synth pads, mysterious"),
    (["мозг", "нейрон", "психолог", "сознани", "разум", "интеллект", "brain", "neuron", "psycholog", "mind", "intellect"],
     "cerebral electronic music, pulsing neuro beats, tense atmospheric synth, sci-fi"),
    (["история", "цивилизац", "древн", "египет", "рим", "война", "history", "civilization", "ancient", "war"],
     "cinematic orchestral ambient, epic dark strings, slow majestic tempo"),
    (["биолог", "эволюц", "животн", "гриб", "растени", "клетк", "biolog", "evolution", "animal", "dog", "cat", "plant"],
     "organic ambient electronic, nature sounds, soft pulsing rhythm, mysterious"),
    (["питани", "еда", "пища", "nutrition", "food", "diet", "eating"],
     "warm uplifting ambient, soft acoustic feel, gentle rhythm, positive mood"),
    (["физик", "химия", "реакц", "атом", "молекул", "вещество", "physics", "chemistry", "atom", "molecule"],
     "electronic science ambient, clean minimal beats, futuristic synth arpeggios"),
    (["математик", "числ", "теорем", "вероятност", "math", "number", "theorem", "probability"],
     "minimal electronic ambient, clean precise rhythms, mathematical patterns, calm"),
    (["сон", "сновиден", "sleep", "dream"],
     "soft dreamy ambient, ethereal pads, gentle floating texture, calming"),
]

_DEFAULT_MUSIC_PROMPT = (
    "mysterious dark ambient electronic music, subtle tension, pulsing synth pads, "
    "slow tempo 80 BPM, cinematic and atmospheric, suitable for science documentary"
)


def _build_music_prompt(topic: str) -> str:
    """Choose a music style based on keywords in the video topic."""
    topic_lower = topic.lower()
    for keywords, prompt in _MOOD_KEYWORDS:
        if any(kw in topic_lower for kw in keywords):
            return prompt
    return _DEFAULT_MUSIC_PROMPT


def _topic_cache_key(topic: str, duration: int) -> str:
    """Stable short hash for caching generated music by topic + duration."""
    return hashlib.md5(f"{topic.strip().lower()}_{duration}".encode()).hexdigest()[:12]


# ─────────────────────────────────────────────────────────────────────────────
# MusicGen generation
# ─────────────────────────────────────────────────────────────────────────────

def generate_background_music(
    topic: str,
    duration: int = 60,
    cache_dir: Path | None = None,
) -> Path | None:
    """
    Generate (or load cached) background music for the given video topic.

    Args:
        topic:     Video topic string (used to pick music mood and for caching).
        duration:  Desired music length in seconds (default 60).
        cache_dir: Directory to cache WAV files. Defaults to output/music_cache.

    Returns:
        Path to the generated WAV file, or None on failure.
    """
    if cache_dir is None:
        cache_dir = Path("output") / "music_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    cache_key = _topic_cache_key(topic, duration)
    cached_path = cache_dir / f"music_{cache_key}.wav"

    if cached_path.exists():
        logger.info(f"[MusicGen] Using cached music: {cached_path.name}")
        return cached_path

    try:
        import torch
        from transformers import AutoProcessor, MusicgenForConditionalGeneration
    except ImportError:
        logger.warning(
            "[MusicGen] 'transformers' or 'torch' not installed. "
            "Run: pip install transformers torch  — falling back to no music."
        )
        return None

    prompt = _build_music_prompt(topic)
    logger.info(f"[MusicGen] Generating ~{duration}s music for topic: '{topic[:50]}'")
    logger.info(f"[MusicGen] Prompt: {prompt}")
    logger.info("[MusicGen] Loading facebook/musicgen-small (~300 MB first run) ...")

    try:
        model_name = "facebook/musicgen-small"
        processor = AutoProcessor.from_pretrained(model_name)
        model = MusicgenForConditionalGeneration.from_pretrained(model_name)
        model.eval()

        # MusicGen generates at 32 kHz; max_new_tokens ≈ 50 tokens/s.
        # Model limit ~1503 tokens (30s) due to sinusoidal positional embeddings.
        # Longer videos: we generate 30s, moviepy loops it.
        max_tokens = min(int(duration) * 50, 1500)

        inputs = processor(
            text=[prompt],
            padding=True,
            return_tensors="pt",
        )

        logger.info(f"[MusicGen] Generating audio ({max_tokens} tokens ≈ {max_tokens // 50}s) ...")
        with torch.no_grad():
            audio_values = model.generate(**inputs, max_new_tokens=max_tokens)

        # audio_values: (batch, channels, samples) — take first batch, mono
        audio_np = audio_values[0, 0].numpy()
        sample_rate = model.config.audio_encoder.sampling_rate  # 32000

        # If the clip is shorter than requested, loop it
        target_samples = duration * sample_rate
        if len(audio_np) < target_samples:
            import numpy as np
            loops = int(target_samples / len(audio_np)) + 1
            audio_np = np.tile(audio_np, loops)
        audio_np = audio_np[:target_samples]

        # Normalise to [-1, 1] then save as 16-bit WAV
        import numpy as np
        peak = np.abs(audio_np).max()
        if peak > 0:
            audio_np = audio_np / peak * 0.85

        import scipy.io.wavfile as wavfile
        audio_int16 = (audio_np * 32767).astype(np.int16)
        wavfile.write(str(cached_path), sample_rate, audio_int16)

        logger.success(f"[MusicGen] Saved: {cached_path} ({duration}s, {sample_rate} Hz)")
        return cached_path

    except Exception as exc:
        logger.warning(f"[MusicGen] Generation failed: {exc} — continuing without music")
        return None
