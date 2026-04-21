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
import math
import re
from pathlib import Path

from loguru import logger
from config import settings

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

_SLEEP_PROFILE = (
    "sleep-friendly ambient, very soft dynamics, no sharp transients, no aggressive percussion, "
    "no jump-scares, smooth evolving pads, low-energy texture, deeply calming"
)

_COUNTRY_HINTS: list[tuple[list[str], str]] = [
    (["france", "франц"], "subtle French atmosphere: distant Paris night ambience, soft musette-like accordion texture"),
    (["japan", "япони"], "subtle Japanese atmosphere: airy shakuhachi-like breathy tones and soft koto-like plucks"),
    (["italy", "итал"], "subtle Italian atmosphere: warm Mediterranean night ambience with gentle mandolin-like color"),
    (["spain", "испан"], "subtle Iberian atmosphere: very soft nylon-guitar color and warm evening ambience"),
    (["turkey", "турц"], "subtle Anatolian atmosphere: soft ney-like airy tone and gentle handpan texture"),
]


def _build_music_prompt(topic: str) -> str:
    """Choose a music style based on keywords in the video topic."""
    topic_lower = topic.lower()
    country_tail = ""
    for keywords, hint in _COUNTRY_HINTS:
        if any(kw in topic_lower for kw in keywords):
            country_tail = hint
            break

    base_prompt = _DEFAULT_MUSIC_PROMPT
    for keywords, prompt in _MOOD_KEYWORDS:
        if any(kw in topic_lower for kw in keywords):
            base_prompt = prompt
            break

    if country_tail:
        return f"{base_prompt}; {_SLEEP_PROFILE}; {country_tail}"
    return f"{base_prompt}; {_SLEEP_PROFILE}"


def _topic_cache_key(topic: str, duration: int) -> str:
    """Stable short hash for caching generated music by topic + duration."""
    return hashlib.md5(f"{topic.strip().lower()}_{duration}".encode()).hexdigest()[:12]


# ─────────────────────────────────────────────────────────────────────────────
# MusicGen generation
# ─────────────────────────────────────────────────────────────────────────────

def generate_background_music(
    topic: str,
    duration: int = 60,
    *,
    base_duration: int | None = None,
    cache_dir: Path | None = None,
) -> Path | None:
    """
    Generate (or load cached) background music for the given video topic.

    Args:
        topic:     Video topic string (used to pick music mood and for caching).
        duration:  Final desired length after looping.
        base_duration: Thematic base-bed length before looping.
        cache_dir: Directory to cache WAV files. Defaults to output/music_cache.

    Returns:
        Path to the generated WAV file, or None on failure.
    """
    if cache_dir is None:
        cache_dir = Path("output") / "music_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    target_duration = max(10, int(duration or 60))
    base_target = int(base_duration or getattr(settings, "ai_music_base_duration_sec", 180) or 180)
    base_target = max(30, min(600, base_target))
    segment_duration = int(getattr(settings, "ai_music_segment_duration_sec", 30) or 30)
    segment_duration = max(20, min(30, segment_duration))

    cache_key = _topic_cache_key(topic, target_duration)
    cache_key = hashlib.md5(f"{cache_key}_{base_target}_{segment_duration}".encode()).hexdigest()[:12]
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
    logger.info(
        f"[MusicGen] Generating themed bed ~{base_target}s and looping to {target_duration}s "
        f"for topic: '{topic[:50]}'"
    )
    logger.info(f"[MusicGen] Prompt: {prompt}")
    logger.info("[MusicGen] Loading facebook/musicgen-small (~300 MB first run) ...")

    try:
        model_name = "facebook/musicgen-small"
        processor = AutoProcessor.from_pretrained(model_name)
        model = MusicgenForConditionalGeneration.from_pretrained(model_name)
        model.eval()

        # MusicGen limit is about 30s per generation. Build a 2-3 min base from
        # several generated segments, blend them, then loop to target duration.
        max_tokens = min(int(segment_duration) * 50, 1500)
        inputs = processor(text=[prompt], padding=True, return_tensors="pt")
        sample_rate = model.config.audio_encoder.sampling_rate  # 32000
        segment_samples = int(segment_duration * sample_rate)
        num_segments = max(1, int(math.ceil(base_target / float(segment_duration))))
        logger.info(
            f"[MusicGen] Segment generation: {num_segments} × {segment_duration}s "
            f"(tokens={max_tokens})"
        )

        import numpy as np

        segments: list[np.ndarray] = []
        for i in range(num_segments):
            # Make neighboring segments slightly different while preserving mood.
            torch.manual_seed(1234 + i)
            with torch.no_grad():
                audio_values = model.generate(**inputs, max_new_tokens=max_tokens)
            seg = audio_values[0, 0].numpy()
            if len(seg) < segment_samples:
                loops = int(segment_samples / max(1, len(seg))) + 1
                seg = np.tile(seg, loops)
            seg = seg[:segment_samples].astype(np.float32, copy=False)
            # tiny fades reduce clicks when crossfading segment edges
            fade = max(1, int(sample_rate * 0.02))
            env_in = np.linspace(0.0, 1.0, fade, endpoint=False, dtype=np.float32)
            env_out = np.linspace(1.0, 0.0, fade, endpoint=False, dtype=np.float32)
            seg[:fade] *= env_in
            seg[-fade:] *= env_out
            segments.append(seg)

        def _concat_crossfade(parts: list[np.ndarray], crossfade_sec: float = 0.35) -> np.ndarray:
            if not parts:
                return np.zeros(segment_samples, dtype=np.float32)
            out = parts[0]
            cf = int(max(1, sample_rate * crossfade_sec))
            for nxt in parts[1:]:
                c = min(cf, len(out) // 2, len(nxt) // 2)
                if c <= 0:
                    out = np.concatenate([out, nxt], axis=0)
                    continue
                fade_out = np.linspace(1.0, 0.0, c, endpoint=False, dtype=np.float32)
                fade_in = np.linspace(0.0, 1.0, c, endpoint=False, dtype=np.float32)
                mixed = out[-c:] * fade_out + nxt[:c] * fade_in
                out = np.concatenate([out[:-c], mixed, nxt[c:]], axis=0)
            return out

        audio_np = _concat_crossfade(segments)
        base_target_samples = int(base_target * sample_rate)
        if len(audio_np) < base_target_samples:
            loops = int(base_target_samples / max(1, len(audio_np))) + 1
            audio_np = np.tile(audio_np, loops)
        audio_np = audio_np[:base_target_samples]
        sample_rate = model.config.audio_encoder.sampling_rate  # 32000

        # Loop the 2-3 min thematic bed to the final required length.
        target_samples = target_duration * sample_rate
        if len(audio_np) < target_samples:
            loops = int(target_samples / len(audio_np)) + 1
            audio_np = np.tile(audio_np, loops)
        audio_np = audio_np[:target_samples]

        # Normalise to [-1, 1] then save as 16-bit WAV
        peak = np.abs(audio_np).max()
        if peak > 0:
            audio_np = audio_np / peak * 0.85

        import scipy.io.wavfile as wavfile
        audio_int16 = (audio_np * 32767).astype(np.int16)
        wavfile.write(str(cached_path), sample_rate, audio_int16)

        logger.success(
            f"[MusicGen] Saved: {cached_path} (base={base_target}s, target={target_duration}s, {sample_rate} Hz)"
        )
        return cached_path

    except Exception as exc:
        logger.warning(f"[MusicGen] Generation failed: {exc} — continuing without music")
        return None
