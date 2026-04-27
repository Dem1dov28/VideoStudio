"""Central configuration loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    # ── OpenRouter (LLM) ──────────────────────────────────────────────────────
    openrouter_api_key: str = Field(..., alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        "https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL"
    )
    openrouter_model: str = Field("openai/gpt-4o-mini", alias="OPENROUTER_MODEL")
    # Отдельная модель для сценариев «Почему X?» — для достоверности фактов лучше gpt-4o
    openrouter_scenario_model: str | None = Field(None, alias="OPENROUTER_SCENARIO_MODEL")
    # Vision-модель для Mode 3 (анализ фото дома) — gpt-4o-mini / gpt-4o
    openrouter_vision_model: str = Field("openai/gpt-4o-mini", alias="OPENROUTER_VISION_MODEL")

    # ── fast-gen.ai ───────────────────────────────────────────────────────────
    # API ключ с сайта fast-gen.ai (вход через /generator → поле "Введите API ключ")
    fastgen_api_key: str = Field("", alias="FASTGEN_API_KEY")
    # Модель: значение option[value=…] или подпись в UI (см. лог [FastGen] Available model options).
    # Пример value: GEM_PIX_2 (вместо устаревшего NARWHAL).
    fastgen_model: str = Field("GEM_PIX_2", alias="FASTGEN_MODEL")
    # false = видимый браузер (для отладки), true = фоновый (продакшн)
    fastgen_headless: bool = Field(False, alias="FASTGEN_HEADLESS")
    # Сколько секунд ждать появления нового превью на fast-gen.ai (иногда >2 мин)
    fastgen_image_timeout: int = Field(300, alias="FASTGEN_IMAGE_TIMEOUT")
    # Сколько раз повторить при таймауте/ошибке (изображения и видео; img+ref в т.ч. multiclip)
    fastgen_max_attempts: int = Field(8, alias="FASTGEN_MAX_ATTEMPTS")
    # Сколько раз полностью перезапускать контекст браузера при фатальном сбое FastGen.
    # Отдельно от FASTGEN_MAX_ATTEMPTS (внутренние повторы на той же вкладке).
    fastgen_outer_restart_attempts: int = Field(5, alias="FASTGEN_OUTER_RESTART_ATTEMPTS")
    # Email и пароль для fast-gen.ai (для Playwright авторизации)
    fastgen_email: str = Field("", alias="FASTGEN_EMAIL")
    fastgen_password: str = Field("", alias="FASTGEN_PASSWORD")
    # Сколько видео генерировать параллельно (каждое в своём окне браузера). 12 = все сразу.
    fastgen_video_parallel_workers: int = Field(15, alias="FASTGEN_VIDEO_PARALLEL_WORKERS")
    # Сколько изображений генерировать параллельно (Mode 1 и др.).
    fastgen_image_parallel_workers: int = Field(10, alias="FASTGEN_IMAGE_PARALLEL_WORKERS")
    # Img2img: доля шума 0.0–1.0 (как в SD denoising strength). Ниже = больше похоже на референс.
    # Рекомендации из гайдов: ~0.15–0.35 для сохранения композиции; None = не трогать UI FastGen.
    # Если на сайте слайдер 0–100, в .env можно указать 25 (= 0.25).
    fastgen_img2img_strength: float | None = Field(None, alias="FASTGEN_IMG2IMG_STRENGTH")
    # Папка для загрузок Chromium при скачивании с fast-gen.ai (без диалога «Выберите путь»).
    # Пусто = MyVideo/_fastgen_chrome_downloads (рядом с видео).
    fastgen_chrome_download_dir: str = Field("", alias="FASTGEN_CHROME_DOWNLOAD_DIR")
    # Блокировать window.showDirectoryPicker / showSaveFilePicker в Playwright (иначе Chrome
    # показывает «Укажите, где этот сайт может сохранять изменения» на каждом ролике).
    # Видео всё равно забирается пайплайном через blob. false — только для ручной отладки в браузере.
    fastgen_block_fs_access_api: bool = Field(True, alias="FASTGEN_BLOCK_FS_ACCESS_API")
    # Соотношение сторон на вкладке Image в FastGen (mode 13 и др.). Видео в FastGen берёт ориентацию из VIDEO_FORMAT.
    fastgen_aspect_ratio: str = Field("16:9", alias="FASTGEN_ASPECT_RATIO")
    # Ненастроенный по умолчанию HTTP-прокси к генератору: если задан — картинки/видео через httpx (см. fastgen_http, .env.example).
    fastgen_http_base_url: str = Field("", alias="FASTGEN_HTTP_BASE_URL")
    # media_gen_api: X-API-Key + тот же FASTGEN_API_KEY (лицензия)
    fastgen_http_auth_style: str = Field("api_key", alias="FASTGEN_HTTP_AUTH_STYLE")  # api_key | bearer | none
    fastgen_http_api_key_header: str = Field("X-API-Key", alias="FASTGEN_HTTP_API_KEY_HEADER")
    # OpenAPI v2 по умолчанию (fastgen_http.py)
    fastgen_http_image_path: str = Field("/api/v2/images", alias="FASTGEN_HTTP_IMAGE_PATH")
    fastgen_http_video_path: str = Field("/api/v2/videos", alias="FASTGEN_HTTP_VIDEO_PATH")
    fastgen_http_keyframe_path: str = Field("", alias="FASTGEN_HTTP_KEYFRAME_PATH")
    fastgen_http_media_provider: str = Field("google_fx", alias="FASTGEN_HTTP_MEDIA_PROVIDER")
    fastgen_storage_base_url: str = Field("https://storage.fast-gen.ai", alias="FASTGEN_STORAGE_BASE_URL")
    # Видео через v4 (Veo Flow / Flower) ближе к UI Playwright; v2 legacy — только если false.
    fastgen_http_enable_v4_video: bool = Field(True, alias="FASTGEN_HTTP_ENABLE_V4_VIDEO")
    fastgen_http_v4_poll_path_template: str = Field(
        "/api/v4/operations/{operation_id}", alias="FASTGEN_HTTP_V4_POLL_PATH_TEMPLATE"
    )
    fastgen_http_v4_flow_ingredients_path: str = Field(
        "/api/v4/flow/video/from-ingredients", alias="FASTGEN_HTTP_V4_FLOW_INGREDIENTS_PATH"
    )
    fastgen_http_v4_flower_from_image_path: str = Field(
        "/api/v4/flower/video/from-image", alias="FASTGEN_HTTP_V4_FLOWER_FROM_IMAGE_PATH"
    )
    fastgen_http_v4_flower_from_text_path: str = Field(
        "/api/v4/flower/video/from-text", alias="FASTGEN_HTTP_V4_FLOWER_FROM_TEXT_PATH"
    )
    fastgen_http_v4_flow_from_text_path: str = Field(
        "/api/v4/flow/video/from-text", alias="FASTGEN_HTTP_V4_FLOW_FROM_TEXT_PATH"
    )
    fastgen_http_v4_flow_keyframes_path: str = Field(
        "/api/v4/flow/video/from-keyframes", alias="FASTGEN_HTTP_V4_FLOW_KEYFRAMES_PATH"
    )
    fastgen_http_timeout_sec: float = Field(600.0, alias="FASTGEN_HTTP_TIMEOUT_SEC")
    fastgen_http_poll_interval_sec: float = Field(2.0, alias="FASTGEN_HTTP_POLL_INTERVAL_SEC")
    fastgen_http_poll_max_sec: float = Field(900.0, alias="FASTGEN_HTTP_POLL_MAX_SEC")
    fastgen_http_job_id_path: str = Field("operation_id", alias="FASTGEN_HTTP_JOB_ID_PATH")
    fastgen_http_poll_path_template: str = Field(
        "/api/v2/videos/status/{operation_id}", alias="FASTGEN_HTTP_POLL_PATH_TEMPLATE"
    )
    fastgen_http_poll_status_path: str = Field("status", alias="FASTGEN_HTTP_POLL_STATUS_PATH")
    fastgen_http_poll_done_values: str = Field("success", alias="FASTGEN_HTTP_POLL_DONE_VALUES")
    fastgen_http_poll_failed_values: str = Field("error", alias="FASTGEN_HTTP_POLL_FAILED_VALUES")
    fastgen_http_result_url_path: str = Field("url", alias="FASTGEN_HTTP_RESULT_URL_PATH")
    fastgen_http_extra_json: str = Field("", alias="FASTGEN_HTTP_EXTRA_JSON")
    fastgen_http_prompt_field: str = Field("prompt", alias="FASTGEN_HTTP_PROMPT_FIELD")
    fastgen_http_model_field: str = Field("model", alias="FASTGEN_HTTP_MODEL_FIELD")
    fastgen_http_aspect_field: str = Field("aspect_ratio", alias="FASTGEN_HTTP_ASPECT_FIELD")
    fastgen_http_refs_field: str = Field("references", alias="FASTGEN_HTTP_REFS_FIELD")

    # ── HuggingFace (fallback, free) ──────────────────────────────────────────
    hf_token: str = Field("", alias="HF_TOKEN")

    # ── OpenAI direct (only for DALL-E 3, optional) ───────────────────────────
    openai_api_key: str = Field("", alias="OPENAI_API_KEY")

    # ── Image generation strategy ─────────────────────────────────────────────
    # "fastgen" = fast-gen.ai (нужен FASTGEN_API_KEY)
    # "hf"      = HuggingFace FLUX.1-schnell (нужен HF_TOKEN, бесплатно)
    # "dalle"   = OpenAI DALL-E 3 (нужен OPENAI_API_KEY)
    image_gen_strategy: str = Field("fastgen", alias="IMAGE_GEN_STRATEGY")

    # ── Vite / фронт (общий корневой .env; бэкенд значение не использует) ─────
    vite_api_url: str = Field("", alias="VITE_API_URL")

    # ── Video settings ────────────────────────────────────────────────────────
    # Optimized for viral short-form (2025-2026):
    # - YouTube Shorts: 55s = 3x views vs 15s (optimal: 50-60s)
    # - Instagram Reels: 7-30s for viral, 30-90s for engagement
    # - TikTok: 15-60s, 15-30s peak performance
    video_format: str = Field("vertical", alias="VIDEO_FORMAT")
    video_fps: int = Field(30, alias="VIDEO_FPS")
    video_duration_per_image: float = Field(3.0, alias="VIDEO_DURATION_PER_IMAGE")  # 5 scenes × 3s = 15s base
    video_transition_duration: float = Field(0.5, alias="VIDEO_TRANSITION_DURATION")
    # moviepy = soft dissolve in Python (one encode). xfade = FFmpeg presets (N+1 encodes, needs ffmpeg on PATH).
    video_transition_engine: str = Field("moviepy", alias="VIDEO_TRANSITION_ENGINE")
    # Полный путь к ffmpeg (например C:\\ffmpeg\\bin\\ffmpeg.exe), если не в PATH — иначе WinError 2.
    ffmpeg_path: str = Field("", alias="FFMPEG_PATH")
    # faster-whisper: размер модели (пусто = авто по GPU/CPU). Mode 4 / 12 / 13.
    whisper_model_size: str = Field("", alias="WHISPER_MODEL_SIZE")
    # Каталог кэша весов Whisper (пусто = каталог по умолчанию faster-whisper)
    whisper_download_root: str = Field("", alias="WHISPER_DOWNLOAD_ROOT")
    # Mode 13: сколько слайдов грузить в провайдер изображений одновременно (FastGen/HF/DALL·E).
    mode13_image_gen_concurrency: int = Field(3, alias="MODE13_IMAGE_GEN_CONCURRENCY")
    # Mode 13: параллельных LLM-запросов для промптов слайдов (тот же результат, меньше простой).
    mode13_prompt_llm_concurrency: int = Field(6, alias="MODE13_PROMPT_LLM_CONCURRENCY")
    # Mode 13: потоков при сборке превью MP4 по чанкам (MoviePy + ffmpeg).
    mode13_preview_mp4_workers: int = Field(4, alias="MODE13_PREVIEW_MP4_WORKERS")
    # Mode 13: сколько сегментов объединять в один LLM-запрос для визуального брифа (меньше запросов = быстрее).
    mode13_scene_brief_batch_size: int = Field(12, alias="MODE13_SCENE_BRIEF_BATCH_SIZE")
    # Mode 13: не вызывать LLM для брифа сцены — быстрее, но выше риск «книга с текстом» в картинке.
    mode13_scene_brief_skip_llm: bool = Field(False, alias="MODE13_SCENE_BRIEF_SKIP_LLM")
    # Mode 13: ориентация готового MP4 (по умолчанию горизонтально — под FastGen / промпты 16:9).
    mode13_video_format: str = Field("horizontal", alias="MODE13_VIDEO_FORMAT")
    # Mode 13: путь к модели arnndn (.rnnn) для AI-очистки речи. Если пусто, ищем в models/arnndn и arnndn-models.
    mode13_arnndn_model_path: str = Field("", alias="MODE13_ARNNDN_MODEL_PATH")
    # Comma-separated FFmpeg xfade names, cycled: slideleft,zoomin,smoothleft
    video_transition_styles: str = Field(
        "slideleft,zoomin,smoothleft",
        alias="VIDEO_TRANSITION_STYLES",
    )
    # Crop bottom X of video (0.0–0.2) to hide Veo watermark. 0.05 = hide bottom 5%.
    video_bottom_crop: float = Field(0.05, alias="VIDEO_BOTTOM_CROP")
    # Word-highlight subtitles synced to scene timeline (no Whisper — equal time per word).
    subtitle_karaoke: bool = Field(True, alias="SUBTITLE_KARAOKE")
    # Сдвиг пословных таймкодов Whisper (сек): положительный — подсветка позже (если опережает голос).
    subtitle_whisper_time_shift_sec: float = Field(0.0, alias="SUBTITLE_WHISPER_TIME_SHIFT_SEC")
    # Начало каждого слова чуть раньше (сек) — меньше визуального отставания от речи; 0 = выкл.
    subtitle_whisper_word_start_lead_sec: float = Field(0.06, alias="SUBTITLE_WHISPER_WORD_START_LEAD_SEC")
    # Mode 4 (цитаты): масштаб шрифта субтитров/подписи цитаты. 1.0 = базовый, 1.6 = заметно крупнее.
    mode4_quote_subtitle_scale: float = Field(1.6, alias="MODE4_QUOTE_SUBTITLE_SCALE")
    # Mode 4: подписи моделей на вкладке Video (fast-gen.ai), как в UI; после N неудач Flow — Flower.
    mode4_veo_video_model_flow: str = Field("Veo 3.1 - Flow", alias="MODE4_VEO_VIDEO_MODEL_FLOW")
    mode4_veo_video_model_flower: str = Field("Veo 3.1 - Flower", alias="MODE4_VEO_VIDEO_MODEL_FLOWER")
    mode4_veo_flow_attempts_before_flower: int = Field(3, alias="MODE4_VEO_FLOW_ATTEMPTS_BEFORE_FLOWER", ge=1, le=20)
    # Legacy TTS voice setting (for backward compatibility)
    tts_voice: str = Field("ru-RU-SvetlanaNeural", alias="TTS_VOICE")

    # Edge-TTS (Microsoft, бесплатно, без ключей)
    edge_tts_voice: str = Field("ru-RU-SvetlanaNeural", alias="EDGE_TTS_VOICE")
    edge_tts_voice_en: str = Field("en-US-JennyNeural", alias="EDGE_TTS_VOICE_EN")
    edge_tts_rate: str = Field("+10%", alias="EDGE_TTS_RATE")
    edge_tts_rate_en: str = Field("-10%", alias="EDGE_TTS_RATE_EN")  # медленнее для английского
    # Mode 5: отдельный мужской голос и более естественный темп для long-form narration.
    mode5_tts_voice: str = Field("ru-RU-DmitryNeural", alias="MODE5_TTS_VOICE")
    mode5_tts_voice_en: str = Field("en-US-GuyNeural", alias="MODE5_TTS_VOICE_EN")
    mode5_tts_rate: str = Field("-32%", alias="MODE5_TTS_RATE")
    mode5_tts_pitch: str = Field("-8Hz", alias="MODE5_TTS_PITCH")
    mode5_vkcloud_voice_model: str = Field("aidar", alias="MODE5_VKCLOUD_VOICE_MODEL")
    mode5_elevenlabs_voice_id: str = Field("ErXwobaYiN019PkySvjV", alias="MODE5_ELEVENLABS_VOICE_ID")
    # Mode 5: максимальное число параллельных генераций картинок на окна (потолок в pipeline = 10).
    mode5_max_parallel_images: int = Field(10, alias="MODE5_MAX_PARALLEL_IMAGES", ge=1, le=10)
    # Mode 5: бэкенд генерации картинок.
    # - "api"        -> только HTTP API (fastgen_http)
    # - "playwright" -> только браузерный путь (fastgen_playwright)
    # - "auto"       -> текущее автоповедение общего генератора
    mode5_image_backend: str = Field("api", alias="MODE5_IMAGE_BACKEND")
    edge_tts_pitch: str = Field("+0Hz", alias="EDGE_TTS_PITCH")
    # Fade-in (s) в начале TTS — сглаживает «рваное» начало, особенно для EN
    tts_audio_fade_in: float = Field(0.12, alias="TTS_AUDIO_FADE_IN")

    # VK Cloud Voice configuration
    vkcloud_voice_token: str = Field("", alias="VKCLOUD_VOICE_TOKEN")
    vkcloud_voice_model: str = Field("mar_ia", alias="VKCLOUD_VOICE_MODEL")
    vkcloud_voice_encoder: str = Field("mp3", alias="VKCLOUD_VOICE_ENCODER")
    vkcloud_voice_speed: float = Field(1.0, alias="VKCLOUD_VOICE_SPEED")

    # ElevenLabs TTS configuration.
    elevenlabs_api_key: str = Field("", alias="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str = Field("EXAVITQu4vr4xnSDxMaL", alias="ELEVENLABS_VOICE_ID")
    elevenlabs_model_id: str = Field("eleven_multilingual_v2", alias="ELEVENLABS_MODEL_ID")
    elevenlabs_stability: float = Field(0.35, alias="ELEVENLABS_STABILITY")
    elevenlabs_similarity_boost: float = Field(0.75, alias="ELEVENLABS_SIMILARITY_BOOST")
    elevenlabs_style: float = Field(0.25, alias="ELEVENLABS_STYLE")
    elevenlabs_speaker_boost: bool = Field(True, alias="ELEVENLABS_SPEAKER_BOOST")

    # VoiceAPI (csv666) TTS configuration.
    # Docs: POST /tasks -> GET /tasks/{id}/status -> GET /tasks/{id}/result
    voiceapi_api_key: str = Field("", alias="VOICEAPI_API_KEY")
    voiceapi_base_url: str = Field("https://voiceapi.csv666.ru", alias="VOICEAPI_BASE_URL")
    # Prefer saved template UUID from the bot if you already tuned the voice there.
    voiceapi_template_uuid: str = Field("", alias="VOICEAPI_TEMPLATE_UUID")
    # Inline template fallback (requires BOTH voice_id and public_owner_id).
    voiceapi_voice_id: str = Field("", alias="VOICEAPI_VOICE_ID")
    voiceapi_public_owner_id: str = Field("", alias="VOICEAPI_PUBLIC_OWNER_ID")
    voiceapi_model_id: str = Field("eleven_multilingual_v2", alias="VOICEAPI_MODEL_ID")
    voiceapi_stability: float = Field(0.72, alias="VOICEAPI_STABILITY")
    voiceapi_similarity_boost: float = Field(0.78, alias="VOICEAPI_SIMILARITY_BOOST")
    voiceapi_speaker_boost: bool = Field(False, alias="VOICEAPI_SPEAKER_BOOST")
    voiceapi_speed: float = Field(0.92, alias="VOICEAPI_SPEED")
    # Provider chunks long text server-side; keep in documented range 500-2000.
    voiceapi_chunk_size: int | None = Field(1000, alias="VOICEAPI_CHUNK_SIZE")
    voiceapi_pause_enabled: bool = Field(False, alias="VOICEAPI_PAUSE_ENABLED")
    voiceapi_pause_max_pause_symb: int = Field(2000, alias="VOICEAPI_PAUSE_MAX_PAUSE_SYMB")
    voiceapi_pause_time: float = Field(1.0, alias="VOICEAPI_PAUSE_TIME")
    voiceapi_auto_paragraph_pause: bool = Field(False, alias="VOICEAPI_AUTO_PARAGRAPH_PAUSE")
    voiceapi_stress_enabled: bool = Field(False, alias="VOICEAPI_STRESS_ENABLED")
    voiceapi_poll_interval_sec: float = Field(2.0, alias="VOICEAPI_POLL_INTERVAL_SEC")
    voiceapi_timeout_sec: float = Field(300.0, alias="VOICEAPI_TIMEOUT_SEC")
    # Rate-limit safety: cap concurrent /tasks creation and retry on 429.
    voiceapi_max_concurrency: int = Field(3, alias="VOICEAPI_MAX_CONCURRENCY")
    voiceapi_create_max_attempts: int = Field(6, alias="VOICEAPI_CREATE_MAX_ATTEMPTS")
    voiceapi_retry_base_sec: float = Field(2.0, alias="VOICEAPI_RETRY_BASE_SEC")
    voiceapi_retry_max_sec: float = Field(30.0, alias="VOICEAPI_RETRY_MAX_SEC")
    # Повторы GET/POST при ReadError / RemoteProtocolError / обрыве соединения.
    voiceapi_transient_retry_attempts: int = Field(8, alias="VOICEAPI_TRANSIENT_RETRY_ATTEMPTS", ge=1, le=30)
    # Context-aware auto stress model can overcorrect in some topics; keep OFF by default.
    tts_auto_stress: bool = Field(False, alias="TTS_AUTO_STRESS")

    # ── Pipeline mode ────────────────────────────────────────────────────────
    # "mode1" = Top-5 facts with AI-generated images
    # "mode2" = Почему X? with Pexels stock video
    pipeline_mode: str = Field("mode1", alias="PIPELINE_MODE")

    # ── Pexels (Mode 2 stock video) ──────────────────────────────────────────
    pexels_api_key: str = Field("", alias="PEXELS_API_KEY")

    # ── Pipeline feature flags ────────────────────────────────────────────────
    # Fact checker: verify scientific accuracy of each scene before rendering
    use_fact_check: bool = Field(True, alias="USE_FACT_CHECK")
    # Strict mode: abort pipeline if any scene is factually incorrect
    fact_check_strict: bool = Field(False, alias="FACT_CHECK_STRICT")
    # Channel concept: affects scoring and prompts ("izlom" | "atlas" | "generic")
    channel_concept: str = Field("izlom", alias="CHANNEL_CONCEPT")

    # ── Postiz (social media publishing) ─────────────────────────────────────
    postiz_api_key: str = Field("", alias="POSTIZ_API_KEY")
    postiz_base_url: str = Field(
        "https://api.postiz.com/public/v1", alias="POSTIZ_BASE_URL"
    )
    postiz_tiktok_integration_id: str = Field("", alias="POSTIZ_TIKTOK_INTEGRATION_ID")
    postiz_instagram_integration_id: str = Field("", alias="POSTIZ_INSTAGRAM_INTEGRATION_ID")
    postiz_youtube_integration_id: str = Field("", alias="POSTIZ_YOUTUBE_INTEGRATION_ID")
    postiz_telegram_integration_id: str = Field("", alias="POSTIZ_TELEGRAM_INTEGRATION_ID")

    # ── YouTube Data API (прямая загрузка Shorts, без Postiz) ─────────────────
    # Реестр нескольких каналов / нескольких GCP-проектов: JSON с парами client_secrets+token на слот.
    # Пусто = режим только из .env (YOUTUBE_OAUTH_CLIENT_SECRETS + токены).
    youtube_profiles_config_path: str = Field("", alias="YOUTUBE_PROFILES_CONFIG")
    youtube_oauth_client_secrets_path: str = Field("", alias="YOUTUBE_OAUTH_CLIENT_SECRETS")
    youtube_oauth_token_path: str = Field("youtube_token.json", alias="YOUTUBE_OAUTH_TOKEN")
    # Второй канал: отдельный файл + второй OAuth. По умолчанию выключено (один канал).
    # Включить: YOUTUBE_OAUTH_TOKEN_B=youtube_token_channel2.json
    youtube_oauth_token_path_b: str = Field("", alias="YOUTUBE_OAUTH_TOKEN_B")
    # Подписи в UI (например @Seconds-Construction). Пусто = «Канал 1» / «Канал 2».
    youtube_channel_primary_label: str = Field("", alias="YOUTUBE_CHANNEL_PRIMARY_LABEL")
    youtube_channel_secondary_label: str = Field("", alias="YOUTUBE_CHANNEL_SECONDARY_LABEL")
    youtube_oauth_redirect_uri: str = Field(
        "http://localhost:8000/api/youtube/oauth/callback",
        alias="YOUTUBE_OAUTH_REDIRECT_URI",
    )
    # Куда редирект после OAuth (браузер пользователя; не путать с redirect URI в Google — тот на :8000)
    frontend_public_url: str = Field("http://localhost:5173", alias="FRONTEND_PUBLIC_URL")

    # ── Scheduler ─────────────────────────────────────────────────────────────
    # Peak hours for Russian/CIS audience: Tue-Thu+Sat 19:00 MSK
    scheduler_cron: str = Field("0 19 * * 2-4,6", alias="SCHEDULER_CRON")

    # ── Video overlays ────────────────────────────────────────────────────────
    # Text shown as watermark on all scene clips; empty = disabled
    watermark_text: str = Field("", alias="WATERMARK_TEXT")
    # Image watermark: path to PNG/JPG in project root. If set, used instead of text.
    # Пример: watermark.png, logo.jpg. Ищем в корне проекта.
    watermark_image_path: str | None = Field(None, alias="WATERMARK_IMAGE_PATH")
    # Apply impact sound effect on key fact scenes
    use_sound_effects: bool = Field(True, alias="USE_SOUND_EFFECTS")

    # Fact Miner: build evidence per scene before ScenarioWriter
    use_fact_miner: bool = Field(True, alias="USE_FACT_MINER")

    # ── AI Music generation ───────────────────────────────────────────────────
    # true = use MusicGen (facebook/musicgen-small) to generate topic-specific music
    # false = use files from music_dir (or no music if dir is empty)
    use_ai_music: bool = Field(True, alias="USE_AI_MUSIC")
    # Duration of AI-generated music track in seconds (keep ≤ 30 for fast CPU gen)
    ai_music_duration: int = Field(15, alias="AI_MUSIC_DURATION")
    # Base thematic bed duration before looping (2-3 min works well for long videos).
    ai_music_base_duration_sec: int = Field(180, alias="AI_MUSIC_BASE_DURATION_SEC")
    # Per-segment generation length for MusicGen (model works best around 20-30s).
    ai_music_segment_duration_sec: int = Field(30, alias="AI_MUSIC_SEGMENT_DURATION_SEC")

    # ── Paths ─────────────────────────────────────────────────────────────────
    output_dir: Path = Field(Path("output"), alias="OUTPUT_DIR")
    music_dir: Path = Field(Path("music"), alias="MUSIC_DIR")
    sounds_dir: Path = Field(Path("sounds"), alias="SOUNDS_DIR")
    music_cache_dir: Path = Field(Path("output/music_cache"), alias="MUSIC_CACHE_DIR")

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parent

    @property
    def intro_video(self) -> Path | None:
        """Тематическое видео для вступления вместо статичной картинки."""
        root = self.project_root
        for name in ("intro.mp4", "title.mp4", "intro.MP4"):
            p = root / name
            if p.exists():
                return p
        return None

    @property
    def outro_video(self) -> Path | None:
        """Видео для концовки (подпишись/лайк)."""
        root = self.project_root
        for name in ("outro.mp4", "ending.mp4", "IMG_0962.MP4", "outro.MP4"):
            p = root / name
            if p.exists():
                return p
        return None

    @property
    def watermark_image(self) -> Path | None:
        """Resolve watermark image: WATERMARK_IMAGE_PATH or watermark.png/logo.png in project root."""
        root = self.project_root
        if self.watermark_image_path:
            p = Path(self.watermark_image_path)
            if not p.is_absolute():
                p = root / p
            if p.exists():
                return p.resolve()
        for name in ("watermark.png", "watermark.jpg", "watermark.jpeg", "watermark.webp", "logo.png", "Screenshot_18.png"):
            p = root / name
            if p.exists():
                return p
        return None

    @property
    def images_dir(self) -> Path:
        return self.output_dir / "images"

    @property
    def audio_dir(self) -> Path:
        return self.output_dir / "audio"

    @property
    def videos_dir(self) -> Path:
        """Папка для готовых видео в корне проекта."""
        return self.project_root / "MyVideo"

    @property
    def youtube_client_secrets_file(self) -> Path | None:
        p = (self.youtube_oauth_client_secrets_path or "").strip()
        if not p:
            return None
        path = Path(p)
        return path.resolve() if path.is_absolute() else (self.project_root / path).resolve()

    @property
    def youtube_token_file(self) -> Path:
        p = Path(self.youtube_oauth_token_path or "youtube_token.json")
        return p.resolve() if p.is_absolute() else (self.project_root / p).resolve()

    @property
    def youtube_token_file_secondary(self) -> Path | None:
        p = (self.youtube_oauth_token_path_b or "").strip()
        if p in ("", "none", "-", "false", "0"):
            return None
        path = Path(p)
        resolved = path.resolve() if path.is_absolute() else (self.project_root / path).resolve()
        if resolved == self.youtube_token_file.resolve():
            return None
        return resolved

    def youtube_token_path_for_profile(self, profile: str) -> Path:
        """Путь к JSON токена для профиля (реестр YOUTUBE_PROFILES_CONFIG или legacy primary/secondary)."""
        from agents.publisher.youtube_multi import get_youtube_profile, try_load_youtube_profiles

        key = (profile or "primary").strip().lower()
        profs = try_load_youtube_profiles(self)
        if profs is not None:
            return get_youtube_profile(self, key).token_path
        if key in ("secondary", "second", "b", "2"):
            sec = self.youtube_token_file_secondary
            if sec is None:
                raise ValueError("YOUTUBE_OAUTH_TOKEN_B не задан в .env")
            return sec
        if key in ("primary", "main", "a", "1", ""):
            return self.youtube_token_file
        raise ValueError("channel_profile: primary | secondary")

    @property
    def uploads_dir(self) -> Path:
        return self.output_dir / "uploads"

    # ── Video resolution ─────────────────────────────────────────────────────
    # "720" = 720×1280 (fast, good for TikTok/Reels — ~2.5× faster render)
    # "1080" = 1080×1920 (full HD, slow Python rendering)
    video_quality: str = Field("720", alias="VIDEO_QUALITY")

    # Mode 5: long-form episodes are horizontal by default.
    mode5_video_format: str = Field("horizontal", alias="MODE5_VIDEO_FORMAT")
    # Mode 5: мягкий визуальный dissolve между соседними сегментами (сек), без overlap аудио.
    # Mode 5 visual transitions between segments (seconds).
    mode5_transition_sec: float = Field(0.95, alias="MODE5_TRANSITION_SEC")
    # Mode 5: включать zoompan-движение. false = статичный кадр (стабильно, без «дергания»).
    # Mode 5: включать очень мягкое zoom/pan-движение.
    mode5_enable_zoom: bool = Field(True, alias="MODE5_ENABLE_ZOOM")
    # Mode 5 «50 фактов»: один замороженный кадр на весь факт (без zoompan), быстрее кодирование.
    mode5_facts50_static_still: bool = Field(True, alias="MODE5_FACTS50_STATIC_STILL")
    # Сколько фактов одновременно: TTS + LLM/картинки (ограничьте при лимитах API).
    mode5_facts50_parallel: int = Field(10, alias="MODE5_FACTS50_PARALLEL", ge=1, le=32)
    # После фактов: длительность "sleep tail" (сек) с тематической музыкой.
    mode5_facts50_sleep_tail_sec: int = Field(0, alias="MODE5_FACTS50_SLEEP_TAIL_SEC")
    # Громкость хвоста относительно исходной дорожки (0.0-1.0).
    mode5_facts50_sleep_tail_volume: float = Field(0.34, alias="MODE5_FACTS50_SLEEP_TAIL_VOLUME")
    # Смена тематического кадра в sleep-tail (сек), по умолчанию 5 минут.
    mode5_facts50_sleep_tail_image_interval_sec: int = Field(300, alias="MODE5_FACTS50_SLEEP_TAIL_IMAGE_INTERVAL_SEC")

    @property
    def video_resolution(self) -> tuple[int, int]:
        if self.video_format == "vertical":
            return (720, 1280) if self.video_quality == "720" else (1080, 1920)
        return (1280, 720) if self.video_quality == "720" else (1920, 1080)

    @property
    def mode5_video_resolution(self) -> tuple[int, int]:
        """Разрешение рендера mode 5 (по умолчанию horizontal)."""
        fmt = getattr(self, "mode5_video_format", "horizontal").strip().lower()
        if fmt == "vertical":
            return (720, 1280) if self.video_quality == "720" else (1080, 1920)
        return (1280, 720) if self.video_quality == "720" else (1920, 1080)

    @property
    def mode13_video_resolution(self) -> tuple[int, int]:
        """Разрешение рендера mode 13 (независимо от глобального VIDEO_FORMAT)."""
        fmt = getattr(self, "mode13_video_format", "horizontal").strip().lower()
        if fmt == "vertical":
            return (720, 1280) if self.video_quality == "720" else (1080, 1920)
        return (1280, 720) if self.video_quality == "720" else (1920, 1080)

    def ensure_dirs(self) -> None:
        for d in [self.images_dir, self.audio_dir, self.videos_dir, self.uploads_dir, self.music_dir, self.sounds_dir, self.music_cache_dir]:
            d.mkdir(parents=True, exist_ok=True)

    model_config = SettingsConfigDict(
        # Абсолютный путь: иначе при запуске uvicorn не из корня проекта .env не находится
        env_file=str(Path(__file__).resolve().parent / ".env"),
        env_file_encoding="utf-8",
        populate_by_name=True,
        # Старые ключи вроде TTS_PROVIDER / VOICEAPI_BACKUP_BASE_URL не ломают загрузку.
        extra="ignore",
    )


settings = Settings()