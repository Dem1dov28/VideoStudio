"""Text-to-speech via configurable provider (Edge-TTS / VK Cloud / ElevenLabs)."""

from __future__ import annotations

import asyncio
import re
import tempfile
from pathlib import Path

import httpx
from loguru import logger

from config import settings


# ─────────────────────────────────────────────────────────────────────────────
# Russian stress correction dictionary
# ─────────────────────────────────────────────────────────────────────────────
# Unicode combining acute accent U+0301 is placed after the stressed vowel.
# Edge-TTS neural voices respect it for correct prosody.

_STRESS_MAP: dict[str, str] = {
    # Глаголы
    "начать":       "нача́ть",
    "начали":       "на́чали",
    "начало":       "нача́ло",
    "понять":       "поня́ть",
    "поняли":       "по́няли",
    "звонит":       "звони́т",
    "звонят":       "звоня́т",
    "создала":      "созда́ла",
    "создали":      "со́здали",
    "взяла":        "взяла́",
    "взяли":        "взя́ли",
    "жила":         "жила́",
    "могла":        "могла́",
    "могли":        "могли́",
    "хотела":       "хоте́ла",
    "хотели":       "хоте́ли",
    "баловать":     "балова́ть",
    "облегчить":    "облегчи́ть",
    "включить":     "включи́ть",
    "включит":      "включи́т",
    "уведомить":    "уведоми́ть",
    # Существительные
    "алфавит":      "алфави́т",
    "договор":      "догово́р",
    "договоры":     "догово́ры",
    "договоров":    "догово́ров",
    "каталог":      "катало́г",
    "километр":     "киломе́тр",
    "километров":   "киломе́тров",
    "сантиметр":    "сантиме́тр",
    "сантиметров":  "сантиме́тров",
    "квартал":      "кварта́л",
    "средства":     "сре́дства",
    "стоимость":    "сто́имость",
    "предмет":      "предме́т",
    "обеспечение":  "обеспе́чение",
    "обогащение":   "обогаще́ние",
    "мышление":     "мышле́ние",
    "намерение":    "наме́рение",
    "положение":    "положе́ние",
    "исследование": "иссле́дование",
    "явления":      "явле́ния",
    "щавель":       "щаве́ль",
    "свёкла":       "свёкла",
    "торты":        "то́рты",
    "банты":        "ба́нты",
    "шарфы":        "ша́рфы",
    "цемент":       "цеме́нт",
    "феномен":      "фено́мен",
    "ходатайство":  "хода́тайство",
    "каучук":       "каучу́к",
    "жалюзи":       "жалюзи́",
    "апостроф":     "апостро́ф",
    "мусоропровод": "мусоропрово́д",
    "газопровод":   "газопрово́д",
    "водопровод":   "водопрово́д",
    "нефтепровод":  "нефтепрово́д",
    # Наука и космос
    "температура":  "температу́ра",
    "атмосфера":    "атмосфе́ра",
    "поверхность":  "пове́рхность",
    "планета":      "плане́та",
    "планеты":      "плане́ты",
    "магнитное":    "магни́тное",
    "солнечной":    "со́лнечной",
    "гравитации":   "гравита́ции",
    "вулканов":     "вулка́нов",
    "кратеры":      "кра́теры",
    "миллионов":    "миллио́нов",
    "миллиардов":   "миллиа́рдов",
    "ученые":       "учёные",
    "экспорт":      "э́кспорт",
    "импорт":       "и́мпорт",
    "процент":      "проце́нт",
    "процентов":    "проце́нтов",
    "создание":     "созда́ние",
    "развитие":     "разви́тие",
    "средство":     "сре́дство",
    # Прилагательные и др.
    "красивее":     "краси́вее",
    "новорожденный": "новорождённый",
    "были":         "бы́ли",
    "было":         "бы́ло",
}

_COMBINING_ACUTE = "\u0301"

# Optional better Russian stress setter (context-aware).
# We prefer `ruaccent-predictor` (lighter than russtress), but keep manual fallback.
_RUACCENTOR = None
try:
    import sys

    try:
        # ruaccent prints emoji during init; some Windows consoles can't encode it.
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    from ruaccent import load_accentor  # type: ignore

    import contextlib
    import io

    # Silence ruaccent init logs (emoji/progress messages) in console.
    with contextlib.redirect_stdout(io.StringIO()):
        _RUACCENTOR = load_accentor()
except Exception:
    _RUACCENTOR = None


_VOWELS = "аеёиоуыэюяАЕЁИОУЫЭЮЯ"


def _apostrophes_to_combining(text: str) -> str:
    """
    Accent predictors often mark stress with an apostrophe after the stressed vowel,
    e.g. "приве'т". Convert:
      vowel + ' -> vowel + U+0301
    Edge-TTS respects combining acute U+0301 for correct prosody.
    """
    text = re.sub(rf"([{_VOWELS}])['’]", r"\1" + _COMBINING_ACUTE, text)
    text = text.replace("'", "").replace("’", "")
    return text


def _apply_stress(text: str) -> str:
    """
    Apply Russian lexical stress marks for correct TTS prosody.

    Priority:
      1) ruaccent-predictor (context-aware) -> converting its apostrophe marks to U+0301
      2) manual _STRESS_MAP fallback (limited coverage)
    """
    if settings.tts_auto_stress and _RUACCENTOR is not None:
        try:
            # ruaccent returns apostrophe format by default with `format='apostrophe'`.
            stressed = _RUACCENTOR(text, format="apostrophe")
            return _apostrophes_to_combining(stressed)
        except Exception:
            # Fall back to manual mapping if auto model fails on some input.
            pass

    # Manual limited fallback.
    for word, stressed in _STRESS_MAP.items():
        pattern = re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)

        def _replace(m: re.Match, s: str = stressed) -> str:
            orig = m.group()
            if orig and orig[0].isupper():
                return s[0].upper() + s[1:]
            return s

        text = pattern.sub(_replace, text)
    return text


# ─────────────────────────────────────────────────────────────────────────────
# Voiceover text cleanup (URLs, markup, slashes — otherwise TTS reads them aloud
# and SSML adds a pause after every ".", inflating duration massively)
# ─────────────────────────────────────────────────────────────────────────────

def sanitize_voiceover_text(text: str) -> str:
    """
    Strip junk from narration before TTS or before showing in the scenario editor.

    Removes HTML/XML, URLs, markdown, JSON escape artefacts, long runs of dots,
    and path-like slashes so the voice does not read «слэш», «точка», etc.
    """
    if not text:
        return ""
    s = text.strip()

    # HTML / SGML tags
    s = re.sub(r"<[^>]+>", " ", s)
    # Entities: &nbsp; &#47; &lt;
    s = re.sub(r"&#\d+;", " ", s)
    s = re.sub(r"&#x[0-9a-fA-F]+;", " ", s)
    s = re.sub(r"&[a-zA-Z][a-zA-Z0-9]*;", " ", s)

    # URLs (http, https, www)
    s = re.sub(r"https?://[^\s\]\)\"'<>]+", " ", s, flags=re.I)
    s = re.sub(r"\bwww\.[^\s\]\)\"'<>]+", " ", s, flags=re.I)

    # Markdown: [text](url) -> text
    s = re.sub(r"\[([^\]]{0,500})\]\([^)]*\)", r"\1", s)
    s = re.sub(r"```[\s\S]*?```", " ", s)
    s = re.sub(r"`[^`]{0,800}`", " ", s)
    s = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", s)
    s = re.sub(r"_{1,2}([^_]+)_{1,2}", r"\1", s)
    s = re.sub(r"#{1,6}\s*", "", s)

    # JSON / code escape sequences left in prose
    s = re.sub(r'\\([nrt"\'\\])', " ", s)
    s = s.replace("\\", " ")

    # Long runs of periods (avoid TTS dragging through "dot dot dot…")
    s = re.sub(r"\.{4,}", "…", s)

    # Double+ slashes (paths, URL tails)
    s = re.sub(r"/{2,}", " ", s)
    # Slash as separator with spaces: "foo / bar"
    s = re.sub(r"\s+/\s+", ", ", s)

    s = re.sub(r"\s{2,}", " ", s).strip()
    return s


# ─────────────────────────────────────────────────────────────────────────────
# Plain text for Communicate (do NOT hand-build SSML — see module docstring)
# ─────────────────────────────────────────────────────────────────────────────

def prepare_tts_plain_text(text: str) -> str:
    """
    Sanitize + optional stress marks for ElevenLabs plain-text synthesis.
    """
    clean = sanitize_voiceover_text(text)
    processed = _apply_stress(clean)
    # Any stray angle brackets (broken tags, comparisons) would be escaped and
    # often read as junk; narration rarely needs literal < >
    processed = re.sub(r"[<>]", " ", processed)
    return re.sub(r"\s{2,}", " ", processed).strip()


# ─────────────────────────────────────────────────────────────────────────────
# Audio normalization (pydub)
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_mp3(src: Path, dst: Path) -> None:
    """
    Normalize peak level to –1 dBFS using pydub.
    Falls back to a simple copy if pydub is unavailable.
    """
    try:
        from pydub import AudioSegment
        from pydub.effects import normalize

        audio = AudioSegment.from_file(str(src))
        normalized = normalize(audio, headroom=1.0)   # –1 dBFS peak
        normalized.export(str(dst), format="mp3", bitrate="192k")
    except ImportError:
        # pydub not installed — just rename/copy
        import shutil
        shutil.copy2(str(src), str(dst))
    except Exception as exc:
        logger.warning(f"[TTS] Normalization failed ({exc}), using raw audio.")
        import shutil
        shutil.copy2(str(src), str(dst))


# ─────────────────────────────────────────────────────────────────────────────
# Core synthesis
# ─────────────────────────────────────────────────────────────────────────────

async def synthesize(
    text: str,
    output_path: Path,
    rate: str | None = None,
    voice: str | None = None,
    *,
    with_word_timestamps: bool = False,
    language: str = "ru",
) -> tuple[Path, list[tuple[float, float]] | None, list[str]]:
    """
    Synthesize `text` to MP3 at `output_path`.

    Returns:
        (output_path, word_timestamps, tts_words) — word_timestamps per word when
        with_word_timestamps=True and provider=edge, else None; tts_words for sync.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    plain = prepare_tts_plain_text(text)
    word_timestamps: list[tuple[float, float]] | None = None
    tts_words: list[str] = []

    # Synthesize to a temp file first (so normalization can overwrite in-place)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        provider = (settings.tts_provider or "edge").strip().lower()
        if provider == "edge":
            import edge_tts
            voice_name = (voice or settings.edge_tts_voice).strip()
            use_rate = rate if rate is not None else (
                getattr(settings, "edge_tts_rate_en", "-10%")
                if (language or "").strip().lower() == "en"
                else settings.edge_tts_rate
            )
            communicate = edge_tts.Communicate(
                plain,
                voice_name,
                rate=use_rate,
                pitch=settings.edge_tts_pitch,
                boundary="WordBoundary" if with_word_timestamps else "SentenceBoundary",
            )
            if with_word_timestamps:
                audio_chunks: list[bytes] = []
                async for chunk in communicate.stream():
                    if chunk.get("type") == "WordBoundary":
                        offset = chunk.get("offset", 0) or 0
                        dur = chunk.get("duration", 0) or 0
                        start_sec = offset / 1e7
                        end_sec = (offset + dur) / 1e7
                        word_timestamps = word_timestamps or []
                        word_timestamps.append((start_sec, end_sec))
                        w = (chunk.get("text") or "").strip()
                        if w:
                            tts_words.append(w)
                        else:
                            tts_words.append("")  # keep 1:1 with timestamps
                    elif chunk.get("type") == "audio" and chunk.get("data"):
                        audio_chunks.append(chunk["data"])
                tmp_path.write_bytes(b"".join(audio_chunks))
                if tts_words and len(tts_words) != len(word_timestamps or []):
                    tts_words = []  # fallback: используем split по тексту
                logger.debug(f"[TTS] Edge-TTS synthesized with {len(word_timestamps or [])} word boundaries → {tmp_path.name}")
            else:
                await communicate.save(str(tmp_path))
                logger.debug(f"[TTS] Edge-TTS synthesized ({voice_name}) → {tmp_path.name}")
        else:
            async with httpx.AsyncClient(timeout=120) as client:
                if provider == "vkcloud":
                    if not settings.vkcloud_voice_token:
                        raise ValueError("VKCLOUD_VOICE_TOKEN is empty. Set it in .env.")
                    url = "https://voice.mcs.mail.ru/tts"
                    headers = {"Authorization": f"Bearer {settings.vkcloud_voice_token}"}
                    data = {
                        "text": plain,
                        "model": settings.vkcloud_voice_model,
                        "encoder": settings.vkcloud_voice_encoder,
                        "tempo": str(settings.vkcloud_voice_speed),
                    }
                    resp = await client.post(url, headers=headers, data=data)
                    resp.raise_for_status()
                    tmp_path.write_bytes(resp.content)
                    logger.debug(f"[TTS] VK Cloud synthesized ({settings.vkcloud_voice_model}) → {tmp_path.name}")
                elif provider == "elevenlabs":
                    if not settings.elevenlabs_api_key:
                        raise ValueError("ELEVENLABS_API_KEY is empty. Set it in .env.")
                    voice_id = (voice or settings.elevenlabs_voice_id).strip()
                    if not voice_id:
                        raise ValueError("ELEVENLABS_VOICE_ID is empty. Set it in .env.")
                    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
                    headers = {
                        "xi-api-key": settings.elevenlabs_api_key,
                        "Accept": "audio/mpeg",
                        "Content-Type": "application/json",
                    }
                    payload = {
                        "text": plain,
                        "model_id": settings.elevenlabs_model_id,
                        "voice_settings": {
                            "stability": settings.elevenlabs_stability,
                            "similarity_boost": settings.elevenlabs_similarity_boost,
                            "style": settings.elevenlabs_style,
                            "use_speaker_boost": settings.elevenlabs_speaker_boost,
                        },
                    }
                    resp = await client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    tmp_path.write_bytes(resp.content)
                    logger.debug(f"[TTS] ElevenLabs synthesized ({voice_id}) → {tmp_path.name}")
                else:
                    raise ValueError(
                        f"Unsupported TTS_PROVIDER={provider!r}. Use edge, vkcloud or elevenlabs."
                    )

        _normalize_mp3(tmp_path, output_path)
        logger.debug(f"[TTS] Normalized → {output_path}")
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)

    return (output_path, word_timestamps, tts_words)


def _voice_for_language(lang: str) -> str | None:
    """Return TTS voice for language. None = use config default."""
    if (lang or "").strip().lower() == "en":
        return getattr(settings, "edge_tts_voice_en", "en-US-JennyNeural") or "en-US-JennyNeural"
    return None  # ru or other → use default from config


async def synthesize_all(
    texts: list[str],
    output_dir: Path,
    language: str = "ru",
    *,
    with_word_timestamps: bool = False,
) -> tuple[list[Path], list[list[tuple[float, float]] | None], list[list[str]]]:
    """
    Synthesize all texts in parallel.
    Returns (paths, timestamps, tts_words_list). tts_words_list[i] — слова из TTS для синхронизации.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    voice = _voice_for_language(language)
    tasks = [
        synthesize(
            text,
            output_dir / f"voice_{i:03d}.mp3",
            voice=voice,
            with_word_timestamps=with_word_timestamps,
            language=language,
        )
        for i, text in enumerate(texts)
    ]
    results = list(await asyncio.gather(*tasks))
    paths = [r[0] for r in results]
    timestamps = [r[1] for r in results]
    tts_words_list = [r[2] for r in results]
    return (paths, timestamps, tts_words_list)
