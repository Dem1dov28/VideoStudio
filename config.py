"""Central configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
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

    # ── fast-gen.ai ───────────────────────────────────────────────────────────
    # API ключ с сайта fast-gen.ai (вход через /generator → поле "Введите API ключ")
    fastgen_api_key: str = Field("", alias="FASTGEN_API_KEY")
    # Модель: Imagen 4 - Whisk | Imagen 4 - Whisk Nano | Banana Pro - Flow4x |
    #         Nano Banana 2 - FlowNew4x | Nano Banana Pro - GeminiBeta
    fastgen_model: str = Field("Imagen 4 - Whisk", alias="FASTGEN_MODEL")
    # false = видимый браузер (для отладки), true = фоновый (продакшн)
    fastgen_headless: bool = Field(False, alias="FASTGEN_HEADLESS")
    # Сколько секунд ждать появления нового превью на fast-gen.ai (иногда >2 мин)
    fastgen_image_timeout: int = Field(300, alias="FASTGEN_IMAGE_TIMEOUT")
    # Сколько раз повторить клик «Генерировать» при таймауте
    fastgen_max_attempts: int = Field(3, alias="FASTGEN_MAX_ATTEMPTS")

    # ── HuggingFace (fallback, free) ──────────────────────────────────────────
    hf_token: str = Field("", alias="HF_TOKEN")

    # ── OpenAI direct (only for DALL-E 3, optional) ───────────────────────────
    openai_api_key: str = Field("", alias="OPENAI_API_KEY")

    # ── Image generation strategy ─────────────────────────────────────────────
    # "fastgen" = fast-gen.ai (нужен FASTGEN_API_KEY)
    # "hf"      = HuggingFace FLUX.1-schnell (нужен HF_TOKEN, бесплатно)
    # "dalle"   = OpenAI DALL-E 3 (нужен OPENAI_API_KEY)
    image_gen_strategy: str = Field("fastgen", alias="IMAGE_GEN_STRATEGY")

    # ── Video settings ────────────────────────────────────────────────────────
    video_format: str = Field("vertical", alias="VIDEO_FORMAT")
    video_fps: int = Field(30, alias="VIDEO_FPS")
    video_duration_per_image: float = Field(3.0, alias="VIDEO_DURATION_PER_IMAGE")
    video_transition_duration: float = Field(0.5, alias="VIDEO_TRANSITION_DURATION")
    # moviepy = soft dissolve in Python (one encode). xfade = FFmpeg presets (N+1 encodes, needs ffmpeg on PATH).
    video_transition_engine: str = Field("moviepy", alias="VIDEO_TRANSITION_ENGINE")
    # Comma-separated FFmpeg xfade names, cycled: slideleft,zoomin,smoothleft
    video_transition_styles: str = Field(
        "slideleft,zoomin,smoothleft",
        alias="VIDEO_TRANSITION_STYLES",
    )
    # Crop bottom X of video (0.0–0.2) to hide Veo watermark. 0.05 = hide bottom 5%.
    video_bottom_crop: float = Field(0.05, alias="VIDEO_BOTTOM_CROP")
    # Word-highlight subtitles synced to scene timeline (no Whisper — equal time per word).
    subtitle_karaoke: bool = Field(True, alias="SUBTITLE_KARAOKE")
    # TTS provider: edge | vkcloud | elevenlabs (edge = бесплатный, без API, работает из РФ)
    tts_provider: str = Field("edge", alias="TTS_PROVIDER")

    # Edge-TTS (Microsoft, бесплатно, без ключей)
    edge_tts_voice: str = Field("ru-RU-SvetlanaNeural", alias="EDGE_TTS_VOICE")
    edge_tts_voice_en: str = Field("en-US-JennyNeural", alias="EDGE_TTS_VOICE_EN")
    edge_tts_rate: str = Field("+10%", alias="EDGE_TTS_RATE")
    edge_tts_rate_en: str = Field("-10%", alias="EDGE_TTS_RATE_EN")  # медленнее для английского
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
        return self.output_dir / "videos"

    @property
    def uploads_dir(self) -> Path:
        return self.output_dir / "uploads"

    # ── Video resolution ─────────────────────────────────────────────────────
    # "720" = 720×1280 (fast, good for TikTok/Reels — ~2.5× faster render)
    # "1080" = 1080×1920 (full HD, slow Python rendering)
    video_quality: str = Field("720", alias="VIDEO_QUALITY")

    @property
    def video_resolution(self) -> tuple[int, int]:
        if self.video_format == "vertical":
            return (720, 1280) if self.video_quality == "720" else (1080, 1920)
        return (1280, 720) if self.video_quality == "720" else (1920, 1080)

    def ensure_dirs(self) -> None:
        for d in [self.images_dir, self.audio_dir, self.videos_dir, self.uploads_dir, self.music_dir, self.sounds_dir, self.music_cache_dir]:
            d.mkdir(parents=True, exist_ok=True)

    model_config = {"env_file": ".env", "populate_by_name": True}


settings = Settings()