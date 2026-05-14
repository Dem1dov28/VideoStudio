"""Text-to-speech через VoiceAPI (один endpoint, без смены провайдера)."""

from __future__ import annotations

import asyncio
import json
import random
import re
import tempfile
import time
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


# VoiceAPI (csv666) отклоняет короткие запросы: «Minimum text length is 500 characters».
VOICEAPI_MIN_PLAIN_CHARS = 500

# Невидимый символ: обычно не озвучивается TTS, но увеличивает len() для лимита API без смыслового «хвоста».
NONSPOKEN_LEN_FILLER_CHAR = "\u200b"


def append_nonspeaking_length_pad(
    text: str,
    min_len: int,
    *,
    filler: str = NONSPOKEN_LEN_FILLER_CHAR,
) -> str:
    """Дополняет строку до min_len без дополнительного смысла (только невидимые символы)."""
    s = text or ""
    if len(s) >= min_len:
        return s
    need = min_len - len(s)
    return s + filler * need


def _pad_plain_to_voiceapi_minimum(plain: str, *, language: str = "ru", pad_salt: int = 0) -> str:
    """Дополняет уже подготовленный plain-текст до лимита VoiceAPI без озвучиваемых вставок."""
    _ = (language, pad_salt)  # сохраняем сигнатуру для вызывающего кода
    p = (plain or "").strip()
    return append_nonspeaking_length_pad(p, VOICEAPI_MIN_PLAIN_CHARS)


def plain_text_for_voiceapi_tts(text: str, *, language: str = "ru", pad_salt: int = 0) -> str:
    """sanitize + stress + невидимое дополнение до минимума для VoiceAPI /tasks."""
    prepared = prepare_tts_plain_text(text)
    return _pad_plain_to_voiceapi_minimum(prepared, language=language, pad_salt=pad_salt)


def _voiceapi_headers() -> dict[str, str]:
    api_key = (settings.voiceapi_api_key or "").strip()
    if not api_key:
        raise ValueError("VOICEAPI_API_KEY is empty. Set it in .env.")
    return {"X-API-Key": api_key}


def _voiceapi_inline_template(voice: str | None = None) -> dict | None:
    voice_id = (voice or settings.voiceapi_voice_id or "").strip()
    public_owner_id = (settings.voiceapi_public_owner_id or "").strip()
    if not voice_id or not public_owner_id:
        return None
    return _voiceapi_inline_template_from_voice_ids(
        voice_id=voice_id,
        public_owner_id=public_owner_id,
    )


def _voiceapi_inline_template_from_voice_ids(
    *,
    voice_id: str,
    public_owner_id: str,
    model_id: str | None = None,
) -> dict:
    """Build VoiceAPI inline template with our tuned voice settings."""
    return {
        "model_id": (model_id or settings.voiceapi_model_id or "eleven_multilingual_v2").strip(),
        "voice_id": voice_id.strip(),
        "public_owner_id": public_owner_id.strip(),
        "voice_settings": {
            "stability": float(settings.voiceapi_stability),
            "similarity_boost": float(settings.voiceapi_similarity_boost),
            "use_speaker_boost": bool(settings.voiceapi_speaker_boost),
            "speed": float(settings.voiceapi_speed),
        },
    }


def _voiceapi_base_url() -> str:
    """Единственный base URL озвучки (без mirror / backup)."""
    u = (settings.voiceapi_base_url or "").strip().rstrip("/")
    return u or "https://voiceapi.csv666.ru"


def _voiceapi_exc_detail(exc: BaseException) -> str:
    """httpx/httpcore иногда дают пустой str(exc); для логов показываем тип и repr."""
    msg = str(exc).strip()
    if msg:
        return f"{type(exc).__name__}: {msg}"
    return f"{type(exc).__name__}: {exc!r}"


# Транзиентные сетевые сбои при long-poll к VoiceAPI (обрыв чтения, reset peer и т.д.).
_VOICEAPI_TRANSIENT_HTTPX: tuple[type[BaseException], ...] = (
    httpx.ReadError,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    httpx.WriteError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
)


async def _voiceapi_retrying_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    label: str,
) -> httpx.Response:
    """Идемпотентный GET с backoff при обрыве соединения (poll status / fetch result)."""
    max_attempts = max(1, int(getattr(settings, "voiceapi_transient_retry_attempts", 8) or 8))
    base = max(0.5, float(getattr(settings, "voiceapi_retry_base_sec", 2.0) or 2.0))
    max_delay = max(base, float(getattr(settings, "voiceapi_retry_max_sec", 30.0) or 30.0))
    last: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return await client.get(url, headers=headers)
        except _VOICEAPI_TRANSIENT_HTTPX as e:
            last = e
            if attempt >= max_attempts - 1:
                raise
            wait = min(max_delay, base * (2**attempt))
            logger.warning(
                "[TTS:VoiceAPI] {} — transient {} (attempt {}/{}), retry in {:.1f}s: {}",
                label,
                type(e).__name__,
                attempt + 1,
                max_attempts,
                wait,
                _voiceapi_exc_detail(e),
            )
            await asyncio.sleep(wait)
    assert last is not None
    raise last


async def _voiceapi_retrying_post(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    json_body: dict,
    label: str,
) -> httpx.Response:
    """POST /tasks с backoff при обрыве соединения (RemoteProtocolError и т.п.)."""
    max_attempts = max(1, int(getattr(settings, "voiceapi_transient_retry_attempts", 8) or 8))
    base = max(0.5, float(getattr(settings, "voiceapi_retry_base_sec", 2.0) or 2.0))
    max_delay = max(base, float(getattr(settings, "voiceapi_retry_max_sec", 30.0) or 30.0))
    last: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return await client.post(url, headers=headers, json=json_body)
        except _VOICEAPI_TRANSIENT_HTTPX as e:
            last = e
            if attempt >= max_attempts - 1:
                raise
            wait = min(max_delay, base * (2**attempt))
            logger.warning(
                "[TTS:VoiceAPI] {} — transient {} on POST (attempt {}/{}), retry in {:.1f}s: {}",
                label,
                type(e).__name__,
                attempt + 1,
                max_attempts,
                wait,
                _voiceapi_exc_detail(e),
            )
            await asyncio.sleep(wait)
    assert last is not None
    raise last


_VOICEAPI_TEMPLATE_RESOLVE_CACHE: dict[str, dict[str, str]] = {}
_VOICEAPI_TEMPLATE_RESOLVE_LOCK = asyncio.Lock()
_VOICEAPI_TEMPLATE_RESOLVE_FAILED: set[str] = set()
_VOICEAPI_SYNTH_SEMAPHORE: asyncio.Semaphore | None = None
# Serialize POST /tasks so parallel Mode5 chunks don't stampede the provider when retries/backoff align.
_VOICEAPI_POST_TASKS_LOCK = asyncio.Lock()


def _voiceapi_effective_concurrency() -> int:
    """
    Сколько задач VoiceAPI этот процесс может держать одновременно (POST→…→result).

    Провайдер (см. https://voiceapi.csv666.ru/docs — до 5 одновременных TTS) возвращает 429, если активных задач >= лимита
    («Please complete existing tasks…»). Один процесс не знает про задачи других
    клиентов — закладываем headroom.
    """
    provider_limit = max(2, int(getattr(settings, "voiceapi_provider_active_task_limit", 5) or 5))
    headroom = max(0, int(getattr(settings, "voiceapi_active_task_headroom", 0) or 0))
    configured = max(1, int(getattr(settings, "voiceapi_max_concurrency", 5) or 5))
    safe_cap = max(1, provider_limit - headroom)
    return min(configured, safe_cap)


def voiceapi_mode5_recommended_tts_parallel() -> int:
    """Параллелизм чанков Mode5 на этапе TTS (согласован с лимитом активных задач VoiceAPI)."""
    return _voiceapi_effective_concurrency()


def _voiceapi_synth_semaphore() -> asyncio.Semaphore:
    global _VOICEAPI_SYNTH_SEMAPHORE
    size = _voiceapi_effective_concurrency()
    sem = _VOICEAPI_SYNTH_SEMAPHORE
    if sem is None:
        _VOICEAPI_SYNTH_SEMAPHORE = asyncio.Semaphore(size)
    return _VOICEAPI_SYNTH_SEMAPHORE


def _voiceapi_retry_after_seconds(
    resp: httpx.Response,
    attempt: int,
    *,
    for_http_429: bool = False,
) -> float:
    base_delay = max(0.5, float(getattr(settings, "voiceapi_retry_base_sec", 2.0) or 2.0))
    max_delay = max(base_delay, float(getattr(settings, "voiceapi_retry_max_sec", 30.0) or 30.0))
    cap_429 = max(max_delay, float(getattr(settings, "voiceapi_429_retry_after_cap_sec", 900.0) or 900.0))
    header = (resp.headers.get("Retry-After") or "").strip()
    if header:
        try:
            sec = float(header)
            if for_http_429:
                return max(0.5, min(cap_429, sec))
            return max(0.0, min(max_delay, sec))
        except Exception:
            pass
    return min(max_delay, base_delay * (2 ** max(0, int(attempt))))


def _voiceapi_rate_limit_sleep_sec(resp: httpx.Response, attempt: int) -> float:
    base = _voiceapi_retry_after_seconds(resp, attempt, for_http_429=True)
    jitter = random.uniform(0.0, min(4.0, 0.22 * base))
    return base + jitter


async def _voiceapi_resolve_template_voice(template_uuid: str) -> dict[str, str] | None:
    """
    Best-effort: resolve template_uuid → (voice_id, public_owner_id, model_id).

    This lets us apply our own voice settings even when the request normally uses
    `template_uuid` (which freezes template's internal voice_settings).
    """
    template_uuid = (template_uuid or "").strip()
    if not template_uuid:
        return None

    if template_uuid in _VOICEAPI_TEMPLATE_RESOLVE_FAILED:
        return None

    if template_uuid in _VOICEAPI_TEMPLATE_RESOLVE_CACHE:
        return _VOICEAPI_TEMPLATE_RESOLVE_CACHE[template_uuid]

    async with _VOICEAPI_TEMPLATE_RESOLVE_LOCK:
        if template_uuid in _VOICEAPI_TEMPLATE_RESOLVE_CACHE:
            return _VOICEAPI_TEMPLATE_RESOLVE_CACHE[template_uuid]

        def _extract_templates_list(payload: object) -> list[dict]:
            """Best-effort extraction of templates list from various response shapes."""
            if isinstance(payload, list):
                return [x for x in payload if isinstance(x, dict)]
            if not isinstance(payload, dict):
                return []

            # Common keys / nesting.
            for key in ("templates", "data", "items", "results"):
                v = payload.get(key)
                if isinstance(v, list):
                    return [x for x in v if isinstance(x, dict)]
                if isinstance(v, dict):
                    for key2 in ("templates", "items", "results"):
                        v2 = v.get(key2)
                        if isinstance(v2, list):
                            return [x for x in v2 if isinstance(x, dict)]

            # Fallback: pick first list of dicts.
            for v in payload.values():
                if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                    return v
            return []

        # GET /templates на единственном VOICEAPI_BASE_URL.
        any_templates_response = False
        base_url = _voiceapi_base_url()
        try:
            async with httpx.AsyncClient(
                timeout=max(15.0, float(settings.voiceapi_timeout_sec or 30.0)),
                follow_redirects=True,
                verify=False,
                http2=False,
            ) as client:
                resp = await client.get(
                    f"{base_url}/templates",
                    headers={**_voiceapi_headers(), "Accept": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()

            templates = _extract_templates_list(data)
            if templates:
                any_templates_response = True

            for item in templates:
                if not isinstance(item, dict):
                    continue
                item_uuid = str(
                    item.get("template_uuid")
                    or item.get("uuid")
                    or item.get("id")
                    or item.get("templateId")
                    or item.get("templateID")
                    or ""
                ).strip()
                if item_uuid != template_uuid:
                    continue

                s = item.get("settings") or {}
                if not isinstance(s, dict):
                    s = {}
                voice_id = str(
                    s.get("voice_id")
                    or s.get("voiceId")
                    or item.get("voice_id")
                    or item.get("voiceId")
                    or s.get("VOICE_ID")
                    or ""
                ).strip()
                public_owner_id = str(
                    s.get("public_owner_id")
                    or s.get("publicOwnerId")
                    or s.get("publicOwnerID")
                    or item.get("public_owner_id")
                    or item.get("publicOwnerId")
                    or s.get("PUBLIC_OWNER_ID")
                    or ""
                ).strip()
                model_id = str(
                    s.get("model_id")
                    or s.get("modelId")
                    or s.get("model")
                    or item.get("model_id")
                    or item.get("modelId")
                    or ""
                ).strip()

                if voice_id and public_owner_id:
                    resolved = {
                        "voice_id": voice_id,
                        "public_owner_id": public_owner_id,
                        "model_id": model_id,
                    }
                    _VOICEAPI_TEMPLATE_RESOLVE_CACHE[template_uuid] = resolved
                    return resolved
        except Exception:
            pass

        if not any_templates_response:
            logger.warning(
                "[TTS:VoiceAPI] /templates is not returning expected JSON for template_uuid={} "
                "(endpoints may be blocked).",
                template_uuid,
            )
        else:
            logger.warning(
                "[TTS:VoiceAPI] template_uuid={} not found in /templates response.",
                template_uuid,
            )
        _VOICEAPI_TEMPLATE_RESOLVE_FAILED.add(template_uuid)

    return None


def _voiceapi_smaller_chunk_size(chunk_size: int | None) -> int | None:
    """Reduce provider chunk_size within 500–2000 to ease slow/failing jobs."""
    if chunk_size is None:
        base = getattr(settings, "voiceapi_chunk_size", None)
        if base is None:
            return None
        chunk_size = int(base)
    cc = max(500, min(2000, int(chunk_size)))
    nxt = max(500, int(cc * 0.75))
    if nxt == cc and cc > 500:
        nxt = max(500, cc - 100)
    return nxt


def _voiceapi_poll_deadline_timeout_sec(plain: str) -> float:
    """
    Wall-clock budget for polling /tasks/{id}/status until ending*.
    Long plaintext (Mode5) needs more time than short quotes.
    """
    base = max(30.0, float(settings.voiceapi_timeout_sec or 900.0))
    n = len(plain or "")
    extra = min(1200.0, max(0, n - 800) * 0.09)
    return min(3600.0, base + extra)


async def _voiceapi_try_complete_existing_task(
    task_id: int,
    tmp_path: Path,
    base_url: str,
    *,
    budget_sec: float,
) -> bool:
    """
    Continue polling an already-created VoiceAPI task after the primary local deadline.

    The synthesizer uses a wall-clock budget; the provider may still be processing the same task.
    Creating POST /tasks again leaves the previous task «active» until it completes, which exhausts
    the provider's concurrent-task limit (typically 5) and triggers 429 on /tasks.

    Returns True if MP3 bytes were written to tmp_path.
    """
    if budget_sec <= 0:
        return False
    deadline = time.monotonic() + budget_sec
    poll_interval = max(0.5, float(settings.voiceapi_poll_interval_sec or 2.0))
    read_cap = max(120.0, min(3600.0, budget_sec))
    timeout = httpx.Timeout(connect=30.0, read=read_cap, write=30.0, pool=30.0)
    terminal_error_status: str | None = None

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, http2=False) as client:
            last_status = "waiting"
            while True:
                if time.monotonic() >= deadline:
                    return False
                status_resp = await _voiceapi_retrying_get(
                    client,
                    f"{base_url}/tasks/{task_id}/status",
                    headers={**_voiceapi_headers(), "Accept": "application/json"},
                    label=f"grace task {task_id} status",
                )
                if status_resp.status_code == 429:
                    wait_sec = _voiceapi_rate_limit_sleep_sec(status_resp, 0)
                    deadline += wait_sec
                    logger.warning(
                        "[TTS:VoiceAPI] grace GET /tasks/{}/status rate-limited (429); sleep {:.1f}s",
                        task_id,
                        wait_sec,
                    )
                    await asyncio.sleep(wait_sec)
                    continue
                status_resp.raise_for_status()
                status_data = status_resp.json()
                last_status = (status_data.get("status") or "").strip().lower()
                if last_status in {"ending", "ending_processed"}:
                    break
                if last_status in {"error", "error_handled"}:
                    terminal_error_status = last_status
                    break
                await asyncio.sleep(poll_interval)

            result_429_round = 0
            while True:
                if time.monotonic() >= deadline:
                    return False
                result_resp = await _voiceapi_retrying_get(
                    client,
                    f"{base_url}/tasks/{task_id}/result",
                    headers={**_voiceapi_headers(), "Accept": "audio/mpeg,application/zip,*/*"},
                    label=f"grace task {task_id} result",
                )
                if result_resp.status_code == 429:
                    result_429_round += 1
                    if result_429_round > 80:
                        return False
                    wait_sec = _voiceapi_rate_limit_sleep_sec(result_resp, result_429_round)
                    deadline += wait_sec
                    logger.warning(
                        "[TTS:VoiceAPI] grace GET /tasks/{}/result rate-limited (429); sleep {:.1f}s",
                        task_id,
                        wait_sec,
                    )
                    await asyncio.sleep(wait_sec)
                    continue
                if result_resp.status_code == 202:
                    await asyncio.sleep(poll_interval)
                    continue
                break

            if result_resp.status_code >= 400:
                return False
            result_resp.raise_for_status()
            content_type = (result_resp.headers.get("content-type") or "").lower()
            if "zip" in content_type:
                logger.warning(
                    "[TTS:VoiceAPI] grace poll task {} returned ZIP; cannot use as single MP3.",
                    task_id,
                )
                return False
            if terminal_error_status:
                logger.warning(
                    "[TTS:VoiceAPI] grace poll: task {} reported status={} but /result returned audio; using it.",
                    task_id,
                    terminal_error_status,
                )
            tmp_path.write_bytes(result_resp.content)
            logger.info(
                "[TTS:VoiceAPI] grace poll saved audio task_id={} → {} ({} bytes)",
                task_id,
                tmp_path.name,
                len(result_resp.content),
            )
            return True
    except Exception as exc:
        logger.warning(
            "[TTS:VoiceAPI] grace poll failed for task_id={}: {}",
            task_id,
            _voiceapi_exc_detail(exc),
        )
        return False


async def _voiceapi_synthesize(
    plain: str,
    tmp_path: Path,
    voice: str | None = None,
    *,
    chunk_size_override: int | None = None,
    retry_left: int | None = None,
    poll_timeout_retries_left: int | None = None,
    _nested: bool = False,
) -> None:
    if not _nested:
        async with _voiceapi_synth_semaphore():
            await _voiceapi_synthesize(
                plain,
                tmp_path,
                voice=voice,
                chunk_size_override=chunk_size_override,
                retry_left=retry_left,
                poll_timeout_retries_left=poll_timeout_retries_left,
                _nested=True,
            )
        return

    timeout = _voiceapi_poll_deadline_timeout_sec(plain)
    poll_interval = max(0.5, float(settings.voiceapi_poll_interval_sec or 2.0))
    if retry_left is None:
        retry_left = max(0, int(getattr(settings, "voiceapi_error_handled_retries", 2) or 0))
    if poll_timeout_retries_left is None:
        poll_timeout_retries_left = max(
            0, int(getattr(settings, "voiceapi_poll_timeout_retries", 3) or 0)
        )

    payload: dict = {"text": plain}
    template_uuid = (settings.voiceapi_template_uuid or "").strip()

    # Voice must be configured only via template_uuid.
    if not template_uuid:
        raise ValueError("VOICEAPI_TEMPLATE_UUID is empty. Voice must be configured only via template.")
    payload["template_uuid"] = template_uuid
    # Keep technical chunking (not a voice override) for long texts.
    chunk_size = chunk_size_override if chunk_size_override is not None else getattr(settings, "voiceapi_chunk_size", None)
    if chunk_size is not None:
        payload["chunk_size"] = max(500, min(2000, int(chunk_size)))

    create_429_budget_sec = float(
        getattr(settings, "voiceapi_create_429_total_budget_sec", 7200.0) or 0.0
    )
    active_tasks_min_wait = float(
        getattr(settings, "voiceapi_create_429_active_tasks_min_wait_sec", 180.0) or 0.0
    )
    abs_max_wait = max(
        60.0,
        float(getattr(settings, "voiceapi_create_429_absolute_max_wait_sec", 86400.0) or 86400.0),
    )
    base_url = _voiceapi_base_url()
    try:
        async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                http2=False,
            ) as client:
                create_resp: httpx.Response | None = None
                create_429_deadline: float | None = None
                if create_429_budget_sec > 0:
                    create_429_deadline = time.monotonic() + create_429_budget_sec
                create_started = time.monotonic()
                abs_deadline = create_started + abs_max_wait
                attempt = 0
                while True:
                    if time.monotonic() >= abs_deadline:
                        raise RuntimeError(
                            "VoiceAPI: POST /tasks остаётся HTTP 429 после ожидания "
                            f"{abs_max_wait:.0f}s (лимит активных задач на аккаунте). "
                            "Завершите или отмените другие задачи озвучки у провайдера и повторите."
                        )
                    attempt += 1
                    async with _VOICEAPI_POST_TASKS_LOCK:
                        create_resp = await _voiceapi_retrying_post(
                            client,
                            f"{base_url}/tasks",
                            headers={
                                **_voiceapi_headers(),
                                "Content-Type": "application/json",
                                "Accept": "application/json",
                            },
                            json_body=payload,
                            label=f"POST /tasks via {base_url}",
                        )
                    if create_resp.status_code != 429:
                        break

                    wait_sec = _voiceapi_rate_limit_sleep_sec(create_resp, attempt - 1)
                    active_tasks_full = False
                    try:
                        jd = create_resp.json()
                        detail_l = str(jd.get("detail") or "").lower()
                        if "active tasks" in detail_l or "complete existing tasks" in detail_l:
                            active_tasks_full = True
                    except Exception:
                        pass
                    if active_tasks_full:
                        if active_tasks_min_wait > 0:
                            wait_sec = max(wait_sec, active_tasks_min_wait)
                        wait_sec = min(900.0, wait_sec + min(420.0, 45.0 * max(0, attempt - 1)))

                    budget_note = ""
                    if create_429_deadline is not None:
                        slice_left = create_429_deadline - time.monotonic()
                        budget_note = f" | slice budget ~{max(0.0, slice_left):.0f}s"
                        # «Мягкий» slice-бюджет только укорачивает паузу для логов; выход — только по abs_deadline.
                        if slice_left > 0:
                            wait_sec = min(wait_sec, max(1.0, slice_left))

                    abs_left = abs_deadline - time.monotonic()
                    wait_sec = min(wait_sec, max(1.0, abs_left))

                    logger.warning(
                        "[TTS:VoiceAPI] /tasks rate-limited (429) via {} | attempt {} | wait {:.1f}s | abs left ~{:.0f}s{}",
                        base_url,
                        attempt,
                        wait_sec,
                        abs_left,
                        budget_note,
                    )
                    await asyncio.sleep(wait_sec)

                    # Страховка от зацикливания (ошибка логики); основной выход — abs_deadline в начале цикла.
                    if attempt >= 100000:
                        logger.error(
                            "[TTS:VoiceAPI] POST /tasks 429: hard cap attempts via {}",
                            base_url,
                        )
                        break
                assert create_resp is not None
                if create_resp.status_code == 429:
                    raise RuntimeError(
                        "VoiceAPI: не удалось создать задачу озвучки: постоянный HTTP 429 на POST /tasks. "
                        "Проверьте лимит активных задач у провайдера и при необходимости "
                        "увеличьте VOICEAPI_CREATE_429_ABSOLUTE_MAX_WAIT_SEC."
                    )
                if create_resp.status_code >= 400:
                    body_preview = (create_resp.text or "").strip().replace("\n", " ")
                    if len(body_preview) > 800:
                        body_preview = body_preview[:800] + " ..."
                    logger.error(
                        "[TTS:VoiceAPI] /tasks failed {} via {} | body={} | payload_meta={{template_uuid: {}, chunk_size: {}, text_len: {}}}",
                        create_resp.status_code,
                        base_url,
                        body_preview,
                        bool(payload.get("template_uuid")),
                        payload.get("chunk_size"),
                        len(plain),
                    )
                create_resp.raise_for_status()
                task_id = int(create_resp.json()["task_id"])
                logger.debug(f"[TTS] VoiceAPI task created id={task_id} via {base_url}")

                deadline = time.monotonic() + timeout
                last_status = "waiting"
                terminal_error_status: str | None = None
                terminal_error_payload: dict | None = None
                while True:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"VoiceAPI task {task_id} did not finish in {timeout:.0f}s")
                    status_resp = await _voiceapi_retrying_get(
                        client,
                        f"{base_url}/tasks/{task_id}/status",
                        headers={**_voiceapi_headers(), "Accept": "application/json"},
                        label=f"task {task_id} status",
                    )
                    if status_resp.status_code == 429:
                        wait_sec = _voiceapi_rate_limit_sleep_sec(status_resp, 0)
                        deadline += wait_sec
                        logger.warning(
                            "[TTS:VoiceAPI] GET /tasks/{}/status rate-limited (429); sleep {:.1f}s",
                            task_id,
                            wait_sec,
                        )
                        await asyncio.sleep(wait_sec)
                        continue
                    status_resp.raise_for_status()
                    status_data = status_resp.json()
                    last_status = (status_data.get("status") or "").strip().lower()
                    if last_status in {"ending", "ending_processed"}:
                        break
                    if last_status in {"error", "error_handled"}:
                        # Some providers may mark task as handled/error but still expose
                        # a downloadable audio result. Try /result before failing hard.
                        terminal_error_status = last_status
                        terminal_error_payload = status_data if isinstance(status_data, dict) else None
                        break
                    await asyncio.sleep(poll_interval)

                result_429_round = 0
                while True:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"VoiceAPI task {task_id} did not finish in {timeout:.0f}s")
                    result_resp = await _voiceapi_retrying_get(
                        client,
                        f"{base_url}/tasks/{task_id}/result",
                        headers={**_voiceapi_headers(), "Accept": "audio/mpeg,application/zip,*/*"},
                        label=f"task {task_id} result",
                    )
                    if result_resp.status_code == 429:
                        result_429_round += 1
                        if result_429_round > 80:
                            result_resp.raise_for_status()
                        wait_sec = _voiceapi_rate_limit_sleep_sec(result_resp, result_429_round)
                        deadline += wait_sec
                        logger.warning(
                            "[TTS:VoiceAPI] GET /tasks/{}/result rate-limited (429); sleep {:.1f}s (round {})",
                            task_id,
                            wait_sec,
                            result_429_round,
                        )
                        await asyncio.sleep(wait_sec)
                        continue
                    break
                if result_resp.status_code == 202:
                    if terminal_error_status:
                        if retry_left > 0:
                            current_chunk = payload.get("chunk_size")
                            next_chunk: int | None = None
                            if current_chunk is not None:
                                cc = max(500, min(2000, int(current_chunk)))
                                next_chunk = max(500, int(cc * 0.75))
                                if next_chunk == cc and cc > 500:
                                    next_chunk = max(500, cc - 100)
                            logger.warning(
                                "[TTS:VoiceAPI] task {} ended with status={} and empty result (202). "
                                "Retrying whole task with smaller chunk_size={} (retries left: {}).",
                                task_id,
                                terminal_error_status,
                                next_chunk if next_chunk is not None else payload.get("chunk_size"),
                                retry_left - 1,
                            )
                            await asyncio.sleep(1.0)
                            await _voiceapi_synthesize(
                                plain,
                                tmp_path,
                                voice=voice,
                                chunk_size_override=next_chunk,
                                retry_left=retry_left - 1,
                                poll_timeout_retries_left=poll_timeout_retries_left,
                                _nested=True,
                            )
                            return
                        status_preview = ""
                        if terminal_error_payload:
                            try:
                                status_preview = json.dumps(terminal_error_payload, ensure_ascii=False)[:800]
                            except Exception:
                                status_preview = str(terminal_error_payload)[:800]
                        raise RuntimeError(
                            f"VoiceAPI task {task_id} failed with status={terminal_error_status}"
                            + (f" payload={status_preview}" if status_preview else "")
                        )
                    raise RuntimeError(f"VoiceAPI task {task_id} is not ready yet after status={last_status}")
                if terminal_error_status and result_resp.status_code >= 400 and retry_left > 0:
                    current_chunk = payload.get("chunk_size")
                    next_chunk: int | None = None
                    if current_chunk is not None:
                        cc = max(500, min(2000, int(current_chunk)))
                        next_chunk = max(500, int(cc * 0.75))
                        if next_chunk == cc and cc > 500:
                            next_chunk = max(500, cc - 100)
                    logger.warning(
                        "[TTS:VoiceAPI] task {} ended with status={} and result HTTP {}. "
                        "Retrying whole task with smaller chunk_size={} (retries left: {}).",
                        task_id,
                        terminal_error_status,
                        result_resp.status_code,
                        next_chunk if next_chunk is not None else payload.get("chunk_size"),
                        retry_left - 1,
                    )
                    await asyncio.sleep(1.0)
                    await _voiceapi_synthesize(
                        plain,
                        tmp_path,
                        voice=voice,
                        chunk_size_override=next_chunk,
                        retry_left=retry_left - 1,
                        poll_timeout_retries_left=poll_timeout_retries_left,
                        _nested=True,
                    )
                    return
                result_resp.raise_for_status()
                content_type = (result_resp.headers.get("content-type") or "").lower()
                if "zip" in content_type:
                    raise RuntimeError(
                        "VoiceAPI returned ZIP instead of MP3. Reduce VOICEAPI_CHUNK_SIZE or adjust provider settings."
                    )
                if terminal_error_status:
                    logger.warning(
                        "[TTS:VoiceAPI] task {} reported status={} but /result returned audio; using returned audio.",
                        task_id,
                        terminal_error_status,
                    )
                tmp_path.write_bytes(result_resp.content)
                logger.debug(f"[TTS] VoiceAPI synthesized task={task_id} via {base_url} → {tmp_path.name}")
    except (TimeoutError, asyncio.TimeoutError):
        tid = locals().get("task_id")
        grace_mult = float(getattr(settings, "voiceapi_same_task_grace_multiplier", 1.0) or 0.0)
        if tid is not None and grace_mult > 0:
            grace_budget = _voiceapi_poll_deadline_timeout_sec(plain) * grace_mult
            logger.warning(
                "[TTS:VoiceAPI] primary poll budget exhausted for task_id={} after {:.0f}s (plain_len={}); "
                "grace poll SAME task {:.0f}s (no POST /tasks) via {}",
                tid,
                timeout,
                len(plain),
                grace_budget,
                base_url,
            )
            if await _voiceapi_try_complete_existing_task(
                int(tid), tmp_path, base_url, budget_sec=grace_budget
            ):
                return
        if poll_timeout_retries_left <= 0:
            logger.error(
                "[TTS] VoiceAPI poll deadline {:.0f}s exceeded (task_id={}, plain_len={}) via {}",
                timeout,
                tid,
                len(plain),
                base_url,
            )
            raise TimeoutError(f"VoiceAPI task {tid} did not finish in {timeout:.0f}s") from None
        next_chunk = _voiceapi_smaller_chunk_size(payload.get("chunk_size"))
        logger.warning(
            "[TTS:VoiceAPI] task {} still not done after grace; retrying NEW task chunk_size={} "
            "(poll timeout retries left: {}).",
            tid,
            next_chunk,
            poll_timeout_retries_left - 1,
        )
        await asyncio.sleep(2.0)
        await _voiceapi_synthesize(
            plain,
            tmp_path,
            voice=voice,
            chunk_size_override=next_chunk,
            retry_left=retry_left,
            poll_timeout_retries_left=poll_timeout_retries_left - 1,
            _nested=True,
        )
        return
    except Exception as exc:
        logger.error(
            "[TTS] VoiceAPI endpoint failed ({}): {}",
            base_url,
            _voiceapi_exc_detail(exc),
        )
        raise


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
    pitch: str | None = None,
    *,
    with_word_timestamps: bool = False,
    language: str = "ru",
    pad_salt: int | None = None,
    voiceapi_plain: str | None = None,
) -> tuple[Path, list[tuple[float, float]] | None, list[str]]:
    """
    Synthesize `text` to MP3 at `output_path`.

    Returns:
        (output_path, word_timestamps, tts_words) — для VoiceAPI таймкоды слов не заполняются
        (with_word_timestamps зарезервировано); tts_words для совместимости API.

    voiceapi_plain: если задан — отправляется в VoiceAPI как есть (уже sanitize+pad),
        чтобы не дублировать подготовку текста с вызывающим кодом (Mode 5).
    pad_salt: зарезервировано (совместимость); дополнение до лимита — невидимые символы.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if voiceapi_plain is not None:
        plain = (voiceapi_plain or "").strip()
    else:
        plain = plain_text_for_voiceapi_tts(text, language=language, pad_salt=pad_salt)
    word_timestamps: list[tuple[float, float]] | None = None
    tts_words: list[str] = []

    # Synthesize to a temp file first (so normalization can overwrite in-place)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        # Strict mode: only VoiceAPI + template UUID is supported.
        await _voiceapi_synthesize(plain, tmp_path, voice=None)

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
    rate: str | None = None,
    pitch: str | None = None,
) -> tuple[list[Path], list[list[tuple[float, float]] | None], list[list[str]]]:
    """
    Synthesize all texts in parallel.
    Returns (paths, timestamps, tts_words_list). tts_words_list[i] — слова из TTS для синхронизации.
    rate: override TTS speed (e.g. "-35%" for sleep stories).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    voice = _voice_for_language(language)
    tasks = [
        synthesize(
            text,
            output_dir / f"voice_{i:03d}.mp3",
            voice=voice,
            rate=rate,
            pitch=pitch,
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
