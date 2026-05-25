import { useState, useEffect, useRef, useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  RiSparklingLine, RiArrowRightLine, RiArrowLeftLine,
  RiLoader4Line, RiEditLine, RiCheckboxCircleLine,
  RiRefreshLine, RiImageAddLine, RiCloseLine,
  RiFileTextLine, RiBookOpenLine, RiLightbulbLine, RiDraftLine,
  RiMoonLine, RiFileSearchLine, RiMovie2Line, RiPaletteLine,
  RiAddLine, RiDeleteBinLine, RiScissorsCutLine,
} from 'react-icons/ri';
import { useLanguage } from '../context/LanguageContext';
import { useMode } from '../context/ModeContext';
import { useRateLimit } from '../context/RateLimitContext';
import { api } from '../services/api';
import { applyStartRequestToForm } from '../utils/prefillFromStartRequest';
import { splitTextBlocks, normalizeMode4OnlyLang } from '../utils/modeSegmentUtils';
import {
  getMode4PersonNameSuggestions,
  recordMode4PersonName,
} from '../utils/mode4PersonNameHistory';
import ScenarioEditor from '../components/ScenarioEditor';

const HOUSE_TYPES = [
  { id: 'log_carelia', label: 'Сруб у озера в Карелии — сосновый лес, стеклянная вода' },
  { id: 'brick_hill_wheat', label: 'Кирпичная усадьба на холме над пшеничным полем' },
  { id: 'alpine_chalet', label: 'Альпийское шале — горы, зелёный луг, снежные пики' },
  { id: 'victorian_cliff', label: 'Викторианский дом на скалистом побережье' },
  { id: 'izba_birch_edge', label: 'Изба на опушке берёзовой рощи' },
  { id: 'italian_tuscany', label: 'Итальянская вилла среди оливковых рощ Тосканы' },
  { id: 'norwegian_fjord', label: 'Норвежский домик у фьорда — обрывы, вода' },
  { id: 'russian_estate_pond', label: 'Русская усадьба с прудом и ивами' },
  { id: 'prairie_farmhouse', label: 'Фермерский дом в американской прерии на закате' },
  { id: 'japanese_zen', label: 'Японский дом в саду камней и бамбука' },
  { id: 'greek_santorini', label: 'Греческий домик на Санторини — белая скала, Эгейское море' },
  { id: 'dutch_canal', label: 'Дом на канале в Голландии — тюльпаны, мельница' },
  { id: 'carved_dacha', label: 'Дача с резными наличниками у лесного ручья' },
  { id: 'lighthouse_keepers', label: 'Домик смотрителя маяка на скалистом берегу' },
  { id: 'tropical_jungle', label: 'Хижина в тропическом лесу — пальмы, водопад рядом' },
];

/** Синхронно с modes/mode5/outline_generator.MIN_OUTLINE_BRIEF_CHARS */
const MODE5_OUTLINE_MIN_BRIEF_CHARS = 40;
const MODE5_BIBLE_MIN_TOTAL_CHARS = 80;

function newMode5BibleChapter(overlayLabel = '') {
  return {
    id: `bch-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    overlayLabel,
    text: '',
  };
}
const MODE5_LANGUAGE_OPTIONS = [
  { id: 'auto', label: 'Авто' },
  { id: 'ru', label: 'Русский' },
  { id: 'en', label: 'English' },
  { id: 'es', label: 'Español' },
  { id: 'fr', label: 'Français' },
  { id: 'de', label: 'Deutsch' },
];

/** Карточки подрежима 5 — иконки и короткие подписи для сетки выбора */
const MODE5_SUBMODE_DEFS = [
  {
    id: 'manual',
    label: 'Ручной текст',
    hint: 'Ваш сценарий, разбивка по длительности чанка',
    Icon: RiFileTextLine,
  },
  {
    id: 'bible',
    label: 'Bible',
    hint: 'Текст по главам и своя подпись сверху для каждой',
    Icon: RiBookOpenLine,
  },
  {
    id: 'facts50',
    label: '77 фактов',
    hint: 'Только тема — AI пишет факты и озвучку по клипу',
    Icon: RiLightbulbLine,
  },
  {
    id: 'outline',
    label: 'План из описания',
    hint: 'Краткий сюжет → план и 10–18 блоков озвучки',
    Icon: RiDraftLine,
  },
  {
    id: 'book_night',
    label: 'Книга на ночь',
    hint: 'Книга по оглавлению — спокойные блоки как у «фактов»',
    Icon: RiMoonLine,
  },
  {
    id: 'unwritten_chapter',
    label: 'The Unwritten Chapter',
    hint: 'Тема расследования → документальный лонгрид 30–50 мин',
    Icon: RiFileSearchLine,
  },
];

const TOPICS_PRESETS = [
  'Топ-5 фактов о чёрных дырах',
  'Почему мы видим сны: наука',
  'Как работает квантовый компьютер',
  'Тайны глубокого океана',
  'Психология первого впечатления',
  'Как устроен человеческий мозг',
];

const MODE4_LOCATION_FALLBACKS = [
  'историческая библиотека с высокими окнами',
  'каменная набережная с ветром и водой',
  'внутренний двор старого университета',
  'зал с колоннами и приглушенным светом',
  'садовая аллея у старинного особняка',
  'монастырский клуатр с аркадами',
  'тихая терраса с видом на город',
];

/* ── toggle ──────────────────────────────────────────────────────────────── */
function Toggle({ value, onChange }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!value)}
      className={`w-11 h-6 rounded-full transition-all duration-200 ring-1 ring-inset ${
        value
          ? 'bg-gradient-to-r from-brand-500 to-brand-600 ring-brand-400/30 shadow-glow-sm'
          : 'bg-white/[0.08] ring-white/[0.06]'
      }`}
    >
      <motion.div
        animate={{ x: value ? 20 : 2 }}
        className="w-5 h-5 rounded-full bg-white shadow-md shadow-black/20"
      />
    </button>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════ */
const MODES = [
  { id: 1, label: '5 фактов', desc: 'AI пишет сценарий и генерирует картинки', icon: '📊' },
  { id: 2, label: 'Почему X?', desc: '5 вопросов с видеоклипами и озвучкой', icon: '❓' },
  { id: 3, label: 'Реставрация домов', desc: 'Маленький дом, одна комната-студия → 8 фрагментов', icon: '🏠' },
  { id: 4, label: 'Цитата + фото', desc: 'Цитата и фото → ролик; несколько абзацев через пустую строку — несколько клипов (~8 с), превью и финальный монтаж', icon: '💬' },
  { id: 5, label: 'Длинные видео', desc: '~1 час: большой сценарий, озвучка, картинки при смене сюжета', icon: '📹' },
  { id: 6, label: 'Cartoon Drama', desc: 'Абсурдные вирусные истории с овощными персонажами', icon: '🥦' },
  { id: 7, label: 'ASMR Keyboard', desc: 'Животные нажимают клавиши: мёд, желе, лёд, шоколад', icon: '🐱' },
  { id: 8, label: 'House Timelapse', desc: 'Строительство дома: пустой участок → готовый дом', icon: '🏗️' },
  { id: 9, label: 'Vehicle Assembly', desc: 'Сборка транспорта: рама → двигатель → кузов → готовый автомобиль', icon: '🚗' },
  { id: 10, label: 'Уборка пляжа', desc: 'Timelapse: грязный пляж → уборка → чистый берег', icon: '🏖️' },
  { id: 11, label: 'Выбор постройки', desc: 'Выбор постройки -> генерировать', icon: '🏛️' },
  { id: 13, label: 'Аудио → слайды', desc: 'Загрузка аудио, смена тембра, картинка каждые ~30 с, превью по ~5 мин, финальная склейка', icon: '🎙️' },
];

const KEYBOARD_LABELS = {
  honey: 'Мёд',
  caramel: 'Карамель',
  jelly: 'Желе',
  slime: 'Слизь',
  ice: 'Лёд',
  chocolate: 'Шоколад',
  cheese: 'Сыр',
  marshmallow: 'Маршмеллоу',
  liquid_metal: 'Жидкий металл',
};

const MODE11_STRUCTURES = [
  { key: 'colosseum', label: '🏟️ Колизей' },
  { key: 'eiffel_tower', label: '🗼 Эйфелева башня' },
  { key: 'great_wall', label: '🧱 Великая Китайская стена' },
  { key: 'giza_pyramids', label: '🔺 Пирамиды Гизы' },
  { key: 'taj_mahal', label: '🕌 Тадж-Махал' },
  { key: 'christ_redeemer', label: '✝️ Христос-Искупитель' },
  { key: 'statue_of_liberty', label: '🗽 Статуя Свободы' },
  { key: 'hanging_gardens', label: '🌿 Висячие сады Семирамиды' },
];

function isMode5AiSubMode(subMode) {
  return (
    subMode === 'facts50' ||
    subMode === 'outline' ||
    subMode === 'book_night' ||
    subMode === 'unwritten_chapter'
  );
}

export default function Generate() {
  const navigate = useNavigate();
  const location = useLocation();
  const prefillConsumedRef = useRef(false);
  const { mode, setMode } = useMode();
  const { lang, setLang } = useLanguage();
  const { checkAndStartVideo } = useRateLimit();

  /* form state */
  const [topic, setTopic]           = useState('');
  const [scenes, setScenes]         = useState(5);
  const [useScenario, setScenario]  = useState(true);
  const [localOnly, setLocalOnly]   = useState(true);
  const [showSubtitles, setShowSubtitles] = useState(true);
  const [referenceImage, setReferenceImage] = useState(null); // { path, preview } — для fast-gen image-to-video
  const [uploadingRef, setUploadingRef] = useState(false);
  // Mode 3: восстановление домов — выбрать тип дома или загрузить 2 фото
  const [mode3InputMode, setMode3InputMode] = useState('type'); // 'type' | 'upload'
  const [mode3HouseType, setMode3HouseType] = useState(''); // id из HOUSE_TYPES
  const [mode3StartImage, setMode3StartImage] = useState(null);
  const [mode3EndImage, setMode3EndImage] = useState(null);
  // Mode 4: цитата + фото; версия вывода: оба ролика или один язык
  const [mode4Quote, setMode4Quote] = useState('');
  const [mode4PersonName, setMode4PersonName] = useState('');
  const [mode4PersonNameSuggestRev, setMode4PersonNameSuggestRev] = useState(0);
  const [mode4Photo, setMode4Photo] = useState(null);
  const [mode4OutputLang, setMode4OutputLang] = useState('both'); // 'both' | 'ru' | 'en'
  const [mode4ShowAuthorOnVideo, setMode4ShowAuthorOnVideo] = useState(true);
  const [mode4HeaderTitle, setMode4HeaderTitle] = useState('');
  const [mode4SubtitleStyle, setMode4SubtitleStyle] = useState('karaoke'); // 'karaoke' | 'plain_whisper'
  const [mode4LocationOptions, setMode4LocationOptions] = useState([]);
  const [mode4LocationLoading, setMode4LocationLoading] = useState(false);
  const [mode4LocationHint, setMode4LocationHint] = useState('');
  const mode4LocationReqKeyRef = useRef('');
  const mode4LocationInFlightRef = useRef('');

  const mode4QuoteBlocks = useMemo(() => splitTextBlocks(mode4Quote), [mode4Quote]);
  const mode4Multiclip = mode4QuoteBlocks.length >= 2;
  const mode4PersonNameSuggestions = useMemo(() => {
    if (mode !== 4) return [];
    return getMode4PersonNameSuggestions(12);
  }, [mode, mode4PersonNameSuggestRev]);

  useEffect(() => {
    if (mode !== 4 || !mode4Multiclip || mode4OutputLang !== 'both') return;
    setMode4OutputLang('ru');
  }, [mode, mode4Multiclip, mode4OutputLang]);

  useEffect(() => {
    if (mode !== 4) return;
    const name = mode4PersonName.trim();
    if (name.length < 2) {
      setMode4LocationOptions([]);
      setMode4LocationHint('');
      return;
    }
    const key = `${name}::${mode4Quote.trim().slice(0, 220)}`;
    if (mode4LocationReqKeyRef.current === key) return;
    const timer = setTimeout(async () => {
      setMode4LocationLoading(true);
      mode4LocationInFlightRef.current = key;
      try {
        const res = await api.mode4LocationOptions(name, mode4Quote.trim(), 7);
        if (mode4LocationInFlightRef.current !== key) return;
        const rows = Array.isArray(res?.locations)
          ? res.locations.map((x) => String(x || '').trim()).filter(Boolean)
          : [];
        const safeRows = rows.length > 0 ? rows : MODE4_LOCATION_FALLBACKS;
        setMode4LocationOptions(safeRows);
        setMode4LocationHint((prev) => (prev && safeRows.includes(prev) ? prev : (safeRows[0] || '')));
        mode4LocationReqKeyRef.current = key;
      } catch (e) {
        if (mode4LocationInFlightRef.current !== key) return;
        setMode4LocationOptions(MODE4_LOCATION_FALLBACKS);
        setMode4LocationHint((prev) => prev || MODE4_LOCATION_FALLBACKS[0]);
      } finally {
        if (mode4LocationInFlightRef.current === key) {
          setMode4LocationLoading(false);
        }
      }
    }, 450);
    return () => clearTimeout(timer);
  }, [mode, mode4PersonName, mode4Quote]);
  // Mode 5: ручной long-form
  const [mode5Script, setMode5Script] = useState('');
  const [mode5ChunkSeconds, setMode5ChunkSeconds] = useState(300);
  const [mode5SegmentSeconds, setMode5SegmentSeconds] = useState(15);
  const [mode5ImageBackend, setMode5ImageBackend] = useState('api'); // api | playwright
  const [mode5HeaderTitle, setMode5HeaderTitle] = useState('');
  const [mode5Lang, setMode5Lang] = useState('auto');
  const [mode5SubMode, setMode5SubMode] = useState('manual');
  const [mode5BibleChapters, setMode5BibleChapters] = useState(() => [newMode5BibleChapter()]);
  const [mode5BibleImportText, setMode5BibleImportText] = useState('');
  const [mode5BibleImportLoading, setMode5BibleImportLoading] = useState(false);
  const [mode5Ideas, setMode5Ideas] = useState([]);
  const [mode5IdeasLoading, setMode5IdeasLoading] = useState(false);
  /** Выкл. по умолчанию — без запросов к модели, пока пользователь не включит. */
  const [mode5NeuralIdeasEnabled, setMode5NeuralIdeasEnabled] = useState(false);
  const [mode5IdeaLaunchKey, setMode5IdeaLaunchKey] = useState('');
  /** Общий флаг «тест ~5 мин» для режима 5 (не привязан к отдельной карточке подрежима). */
  const [mode5TestRun, setMode5TestRun] = useState(false);
  /** Без коротких mp4 по частям — сразу один финальный монтаж после картинок и озвучки. */
  const [mode5SkipChunkPreviews, setMode5SkipChunkPreviews] = useState(false);
  /** Озвучка, картинки и превью MP4 по одному чанку за раз (без параллели между частями). */
  const [mode5SequentialChunks, setMode5SequentialChunks] = useState(false);
  const [mode5BlockLoopPoolSize, setMode5BlockLoopPoolSize] = useState(1);
  const [mode5ThumbnailOverlayText, setMode5ThumbnailOverlayText] = useState('');
  useEffect(() => {
    if (mode !== 5) return;
    if (
      (mode5SubMode === 'book_night' || mode5SubMode === 'unwritten_chapter') &&
      mode5SegmentSeconds < 30
    ) {
      setMode5SegmentSeconds(30);
    }
  }, [mode, mode5SubMode, mode5SegmentSeconds]);
  useEffect(() => {
    if (mode !== 5 || mode5SubMode !== 'bible') return;
    setMode5BibleChapters(prev => (prev.length ? prev : [newMode5BibleChapter()]));
  }, [mode, mode5SubMode]);
  useEffect(() => {
    if (mode !== 5 || !isMode5AiSubMode(mode5SubMode) || !mode5NeuralIdeasEnabled) {
      setMode5Ideas([]);
      setMode5IdeasLoading(false);
    }
  }, [mode, mode5SubMode, mode5NeuralIdeasEnabled]);
  useEffect(() => {
    let cancelled = false;
    async function loadCachedIdeasOnly() {
      if (mode !== 5 || !isMode5AiSubMode(mode5SubMode) || !mode5NeuralIdeasEnabled) return;
      setMode5IdeasLoading(true);
      setMode5Ideas([]);
      setError('');
      try {
        const cached = await api.mode5CachedTopicIdeas(mode5SubMode, 8);
        const rows = Array.isArray(cached?.ideas) ? cached.ideas : [];
        if (cancelled) return;
        setMode5Ideas(rows);
      } catch (e) {
        if (!cancelled) setError(e.message || 'Не удалось загрузить темы');
      } finally {
        if (!cancelled) setMode5IdeasLoading(false);
      }
    }
    loadCachedIdeasOnly();
    return () => {
      cancelled = true;
    };
  }, [mode, mode5SubMode, mode5NeuralIdeasEnabled]);
  // Mode 6: cartoon drama
  const [mode6NumCharacters, setMode6NumCharacters] = useState(3);
  // Mode 7: ASMR animal keyboard videos
  const [mode7AnimalType, setMode7AnimalType] = useState('random'); // 'cat', 'dog', 'kitten', 'puppy', 'random'
  const [mode7Keyboards, setMode7Keyboards] = useState(['honey', 'caramel', 'jelly']); // Default: 3 keyboards
  const [mode7NumKeyboards, setMode7NumKeyboards] = useState(4); // 3-4 keyboards
  // Mode 8: House Building Timelapse
  const [mode8HouseStyle, setMode8HouseStyle] = useState('random');
  const [mode8Location, setMode8Location] = useState('random');
  const [mode8NumStages, setMode8NumStages] = useState(5);
  const [mode8NumFloors, setMode8NumFloors] = useState(2); // Number of floors
  // Mode 9: Vehicle Assembly Timelapse
  const [mode9VehicleType, setMode9VehicleType] = useState('random');
  const [mode9Location, setMode9Location] = useState('random');
  const [mode9NumStages, setMode9NumStages] = useState(5);
  // Mode 10: beach cleanup timelapse
  const [mode10BeachType, setMode10BeachType] = useState('tropical');
  const [mode10CoastSetting, setMode10CoastSetting] = useState('morning_calm');
  const [mode10NumStages, setMode10NumStages] = useState(5);
  // Mode 11: monument reverse deconstruction
  const [mode11StructureType, setMode11StructureType] = useState('colosseum');
  const [mode11NumStages, setMode11NumStages] = useState(5);
  const [mode13Audio, setMode13Audio] = useState(null); // { path, name }
  const [mode13VoicePreset, setMode13VoicePreset] = useState('studio'); // original | studio | calm | natural | soft | medium | strong
  const [mode13WhisperLang, setMode13WhisperLang] = useState(''); // '' | 'ru' | 'en'
  const [mode13ShowSubtitles, setMode13ShowSubtitles] = useState(true);
  const [mode13HeaderTitle, setMode13HeaderTitle] = useState('');
  const [mode13GainDb, setMode13GainDb] = useState(0);
  const [mode13AiCleanup, setMode13AiCleanup] = useState(0);
  const [mode13NoiseSupp, setMode13NoiseSupp] = useState(50);
  const [mode13LevelNorm, setMode13LevelNorm] = useState(50);
  const [mode13Deesser, setMode13Deesser] = useState(0);
  const [mode13Clarity, setMode13Clarity] = useState(0);
  const [mode13MudCut, setMode13MudCut] = useState(0);
  const [mode13Compression, setMode13Compression] = useState(0);
  const [mode13HpAuto, setMode13HpAuto] = useState(true);
  const [mode13HighpassHz, setMode13HighpassHz] = useState(60);
  const [mode13TempoPct, setMode13TempoPct] = useState(100);
  const [mode13PitchSemi, setMode13PitchSemi] = useState(0);
  const [mode13ListenVol, setMode13ListenVol] = useState(1);
  const [mode13PreviewBlobUrl, setMode13PreviewBlobUrl] = useState(null);
  const [mode13PreviewBusy, setMode13PreviewBusy] = useState(false);
  const [mode13PreviewError, setMode13PreviewError] = useState('');
  const mode13AudioRef = useRef(null);
  const [uploadingMode13Audio, setUploadingMode13Audio] = useState(false);

  /* scenario editing state */
  const [step, setStep]             = useState('select_mode');   // 'select_mode' | 'form' | 'generating_scenario' | 'editing' | 'launching'
  const [scenario, setScenario2]    = useState(null);
  const [startedSession, setStartedSession] = useState(null);

  const [error, setError] = useState('');
  const [prefillBanner, setPrefillBanner] = useState(false);

  useEffect(() => {
    const req = location.state?.startRequest;
    if (!req || typeof req !== 'object') {
      prefillConsumedRef.current = false;
      return;
    }
    if (prefillConsumedRef.current) return;
    prefillConsumedRef.current = true;
    applyStartRequestToForm(req, {
      setMode,
      setStep,
      setTopic,
      setScenes,
      setScenario,
      setLang,
      setLocalOnly,
      setShowSubtitles,
      setReferenceImage,
      setScenario2,
      setMode3InputMode,
      setMode3HouseType,
      setMode3StartImage,
      setMode3EndImage,
      setMode4Quote,
      setMode4PersonName,
      setMode4Photo,
      setMode4OutputLang,
      setMode4ShowAuthorOnVideo,
      setMode4HeaderTitle,
      setMode4SubtitleStyle,
      setMode4LocationHint,
      setMode4LocationOptions,
      setMode5Script,
      setMode5Lang,
      setMode5ChunkSeconds,
      setMode5SegmentSeconds,
      setMode5ImageBackend,
      setMode5HeaderTitle,
      setMode5SubMode,
      setMode5BibleChapters,
      setMode5TestRun,
      setMode5SkipChunkPreviews,
      setMode5SequentialChunks,
      setMode5BlockLoopPoolSize,
      setMode5ThumbnailOverlayText,
      setMode6NumCharacters,
      setMode7AnimalType,
      setMode7Keyboards,
      setMode7NumKeyboards,
      setMode8HouseStyle,
      setMode8Location,
      setMode8NumStages,
      setMode8NumFloors,
      setMode9VehicleType,
      setMode9Location,
      setMode9NumStages,
      setMode10BeachType,
      setMode10CoastSetting,
      setMode10NumStages,
      setMode11StructureType,
      setMode11NumStages,
      setMode13Audio,
      setMode13VoicePreset,
      setMode13WhisperLang,
      setMode13ShowSubtitles,
      setMode13HeaderTitle,
      setMode13GainDb,
      setMode13AiCleanup,
      setMode13NoiseSupp,
      setMode13LevelNorm,
      setMode13Deesser,
      setMode13Clarity,
      setMode13MudCut,
      setMode13Compression,
      setMode13HpAuto,
      setMode13HighpassHz,
      setMode13TempoPct,
      setMode13PitchSemi,
    }, { houseTypes: HOUSE_TYPES });
    setPrefillBanner(true);
    navigate('/', { replace: true, state: {} });
  }, [location.state, navigate, setMode]);

  const mode13MonoServeUrl = useMemo(() => {
    if (!mode13Audio?.path) return null;
    const b = import.meta.env.VITE_API_URL || '';
    return `${b}/api/upload/audio-serve?path=${encodeURIComponent(mode13Audio.path)}`;
  }, [mode13Audio?.path]);

  useEffect(() => {
    const el = mode13AudioRef.current;
    if (el) el.volume = Math.max(0, Math.min(1, mode13ListenVol));
  }, [mode13ListenVol, mode13PreviewBlobUrl, mode13MonoServeUrl]);

  useEffect(() => {
    let cancelled = false;
    if (!mode13Audio?.path) {
      setMode13PreviewBlobUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
      setMode13PreviewBusy(false);
      setMode13PreviewError('');
      return undefined;
    }
    const t = setTimeout(async () => {
      setMode13PreviewBusy(true);
      setMode13PreviewError('');
      try {
        const prevBody = {
          path: mode13Audio.path,
          preset: mode13VoicePreset,
          gain_db: mode13GainDb,
          tempo_scale: mode13TempoPct / 100,
          pitch_semitones: mode13PitchSemi,
          ai_cleanup: mode13AiCleanup,
          noise_suppression: mode13NoiseSupp,
          level_normalize: mode13LevelNorm,
          deesser: mode13Deesser,
          clarity: mode13Clarity,
          mud_cut: mode13MudCut,
          compression: mode13Compression,
        };
        if (!mode13HpAuto) prevBody.highpass_hz = mode13HighpassHz;
        const blob = await api.mode13VoicePreview(prevBody);
        if (cancelled) return;
        const url = URL.createObjectURL(blob);
        setMode13PreviewBlobUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return url;
        });
      } catch (err) {
        if (!cancelled) {
          setMode13PreviewError(err.message || 'Превью недоступно');
          setMode13PreviewBlobUrl((prev) => {
            if (prev) URL.revokeObjectURL(prev);
            return null;
          });
        }
      } finally {
        if (!cancelled) setMode13PreviewBusy(false);
      }
    }, 360);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [
    mode13Audio?.path,
    mode13VoicePreset,
    mode13GainDb,
    mode13AiCleanup,
    mode13NoiseSupp,
    mode13LevelNorm,
    mode13Deesser,
    mode13Clarity,
    mode13MudCut,
    mode13Compression,
    mode13HpAuto,
    mode13HighpassHz,
    mode13TempoPct,
    mode13PitchSemi,
  ]);

  /* Step A: generate scenario for preview */
  async function handleGenerateScenario() {
    if (!topic.trim()) {
      setError('Введите тему для видео');
      return;
    }
    setError('');
    setStep('generating_scenario');
    try {
      const res = await api.generateScenario({
        topic: topic.trim(),
        num_scenes: scenes,
        mode,
        language: lang,
      });
      setScenario2(res.scenario);
      setStep('editing');
    } catch (e) {
      setError(e.message);
      setStep('form');
    }
  }

  /* Step B: launch full pipeline with (possibly edited) scenario */
  async function handleLaunch() {
    setError('');
    setStep('launching');
    try {
      const payload = {
        topic: scenario?.title || topic.trim() || null,
        auto_topic: false,
        num_scenes: scenes,
        use_scenario: true,
        local_only: localOnly,
        show_subtitles: mode13ShowSubtitles,
        show_watermark: false,
        scenario: scenario,
        mode,
        language: lang,
        reference_image_path: referenceImage?.path || null,
      };
      
      // Use rate limit check
      const result = await checkAndStartVideo(payload);
      
      setStep('form');
      if (result.status === 'started') {
        setStartedSession(result.session_id);
      } else if (result.status === 'queued') {
        setError('Лимит исчерпан. Видео добавлено в очередь и запустится в следующем часе.');
        setStep('editing');
      }
    } catch (e) {
      setError(e.message);
      setStep('editing');
    }
  }

  /* Mode 5: длинные видео — прямой запуск */
  async function handleMode5SplitBibleImport() {
    const bulk = mode5BibleImportText.trim();
    if (bulk.length < 20) {
      setError('Вставьте текст для разбивки (от ~20 символов)');
      return;
    }
    setError('');
    setMode5BibleImportLoading(true);
    try {
      const res = await api.mode5SplitBibleChapters(bulk);
      const rows = Array.isArray(res?.chapters) ? res.chapters : [];
      if (!rows.length) {
        setError(
          'Не удалось разбить текст на главы. Добавьте заголовки «Chapter N», «Matthew 2» или «глава 2».',
        );
        return;
      }
      setMode5BibleChapters(
        rows.map((ch, idx) => {
          const row = newMode5BibleChapter();
          return {
            ...row,
            overlayLabel:
              String(ch.overlay_label ?? ch.overlayLabel ?? '').trim() || `Chapter ${idx + 1}`,
            text: String(ch.text ?? '').trim(),
          };
        }),
      );
    } catch (e) {
      setError(e.message || 'Не удалось разбить текст на главы');
    } finally {
      setMode5BibleImportLoading(false);
    }
  }

  async function handleMode5Launch(override = null) {
    const effectiveSubMode = override?.subMode ?? mode5SubMode;
    const isBible = effectiveSubMode === 'bible';
    const bibleFilled = isBible
      ? (override?.bibleChapters ?? mode5BibleChapters).filter(ch => ch.text.trim())
      : [];
    const scriptTrim = isBible
      ? bibleFilled.map(ch => ch.text.trim()).join('\n\n')
      : (override?.script ?? mode5Script).trim();
    const headerTrim = (override?.header ?? mode5HeaderTitle).trim();
    if (!scriptTrim) {
      setError(
        effectiveSubMode === 'outline'
          ? 'Введите краткое описание сюжета или задумки'
          : effectiveSubMode === 'unwritten_chapter'
            ? 'Укажите тему для расследования на 30–50 минут'
          : effectiveSubMode === 'book_night'
            ? 'Введите название книги (можно с автором)'
            : effectiveSubMode === 'facts50'
              ? 'Введите тему для 77 фактов'
              : isBible
                ? 'Добавьте хотя бы одну главу с текстом для озвучки'
                : 'Вставьте текст для озвучки',
      );
      return;
    }
    if (effectiveSubMode === 'outline' && scriptTrim.length < MODE5_OUTLINE_MIN_BRIEF_CHARS) {
      setError(
        `Для «плана из описания» напишите короткое описание не короче ${MODE5_OUTLINE_MIN_BRIEF_CHARS} символов: кто, где, настроение, что происходит — не только название ролика.`,
      );
      return;
    }
    if ((effectiveSubMode === 'facts50' || effectiveSubMode === 'book_night' || effectiveSubMode === 'unwritten_chapter') && scriptTrim.length < 8) {
      setError(
        effectiveSubMode === 'book_night'
          ? 'Для «книги на ночь» введите название книги (от 8 символов), можно с автором'
          : effectiveSubMode === 'unwritten_chapter'
            ? 'Для режима «The Unwritten Chapter» укажите тему расследования (от 8 символов)'
          : 'Для режима «77 фактов» введите тему подлиннее (например: 77 фактов о Франции)',
      );
      return;
    }
    if (isBible) {
      const totalChars = bibleFilled.reduce((n, ch) => n + ch.text.trim().length, 0);
      if (totalChars < MODE5_BIBLE_MIN_TOTAL_CHARS) {
        setError(
          `Суммарный текст глав должен быть не короче ~${MODE5_BIBLE_MIN_TOTAL_CHARS} символов`,
        );
        return;
      }
    } else if (
      effectiveSubMode !== 'facts50' &&
      effectiveSubMode !== 'outline' &&
      effectiveSubMode !== 'unwritten_chapter' &&
      effectiveSubMode !== 'book_night' &&
      scriptTrim.length < 80
    ) {
      setError('Для ручного режима нужен полноценный текст озвучки (не короче ~80 символов)');
      return;
    }
    setError('');
    if (override?.subMode) {
      setMode5SubMode(override.subMode);
    }
    setStep('launching');
    try {
      const topicLine =
        isMode5AiSubMode(effectiveSubMode)
          ? headerTrim ||
            scriptTrim ||
            (effectiveSubMode === 'outline'
              ? 'Лонгрид по описанию'
              : effectiveSubMode === 'book_night'
                ? 'Книга на ночь'
                : effectiveSubMode === 'unwritten_chapter'
                  ? 'The Unwritten Chapter'
                  : '77 фактов')
          : mode5HeaderTitle.trim() || 'Ручной long-form';
      const payload = {
        topic: topicLine,
        auto_topic: false,
        num_scenes: 1,
        use_scenario: false,
        local_only: localOnly,
        show_subtitles: ['bible', 'outline', 'book_night', 'unwritten_chapter'].includes(effectiveSubMode),
        show_watermark: false,
        scenario: null,
        mode: 5,
        language: mode5Lang,
        mode5_script_text: scriptTrim,
        mode5_language: mode5Lang,
        mode5_chunk_seconds: mode5ChunkSeconds,
        mode5_segment_seconds: mode5SegmentSeconds,
        mode5_image_backend: mode5ImageBackend,
        mode5_skip_final_assembly: true,
        mode5_skip_chunk_previews: mode5SkipChunkPreviews,
        mode5_sequential_chunks: mode5SequentialChunks,
        mode5_video_header_title: headerTrim,
        mode5_bible_mode: effectiveSubMode === 'bible',
        mode5_sub_mode: effectiveSubMode,
        mode5_bible_chapters: isBible
          ? bibleFilled.map((ch, idx) => ({
              overlay_label: ch.overlayLabel.trim() || `Chapter ${idx + 1}`,
              text: ch.text.trim(),
            }))
          : null,
        mode5_test_run: Boolean(override?.testRun ?? mode5TestRun),
        mode5_test_duration_sec: 300,
        mode5_block_loop_pool_size: Math.max(
          1,
          Math.min(20, Math.round(Number(mode5BlockLoopPoolSize) || 1)),
        ),
        mode5_thumbnail_overlay_text: mode5ThumbnailOverlayText.trim() || null,
      };
      
      // Use rate limit check
      const result = await checkAndStartVideo(payload);
      
      setStep('form');
      if (result.status === 'started') {
        setStartedSession(result.session_id);
      } else if (result.status === 'queued') {
        setError('Лимит исчерпан. Видео добавлено в очередь и запустится в следующем часе.');
      }
    } catch (e) {
      setError(e.message);
      setStep('form');
    }
  }

  async function handleSuggestMode5Ideas() {
    if (mode !== 5 || !isMode5AiSubMode(mode5SubMode) || !mode5NeuralIdeasEnabled) return;
    setError('');
    setMode5IdeasLoading(true);
    try {
      const seed = `${mode5SubMode}:${new Date().toISOString()}`;
      const res = await api.mode5TopicIdeas(mode5SubMode, 8, seed);
      const rows = Array.isArray(res?.ideas) ? res.ideas : [];
      if (!rows.length) throw new Error('Сервер не вернул идеи');
      setMode5Ideas(rows);
    } catch (e) {
      setError(e.message || 'Не удалось предложить темы');
    } finally {
      setMode5IdeasLoading(false);
    }
  }

  async function handleLaunchMode5FromIdea(idea, idx) {
    if (!idea || typeof idea !== 'object') return;
    const script = String(idea.topic || '').trim();
    const header = String(idea.project_title || '').trim();
    const ideaId = String(idea.idea_id || '').trim();
    if (!script) {
      setError('Идея пустая, попробуйте обновить список');
      return;
    }
    const key = `${idx}-${script}`;
    setMode5IdeaLaunchKey(key);
    setMode5Script(script);
    setMode5HeaderTitle(header);
    if (ideaId) {
      try {
        await api.mode5ConsumeIdea(ideaId, 'clicked');
      } catch (_) {
        // non-blocking: even if status update fails, launch should continue
      }
    }
    await handleMode5Launch({ script, header });
    if (ideaId) {
      try {
        await api.mode5ConsumeIdea(ideaId, 'started');
      } catch (_) {
        // non-blocking
      }
    }
    setMode5IdeaLaunchKey('');
  }

  /* Mode 6: cartoon drama — прямой запуск */
  async function handleMode6Launch() {
    setError('');
    setStep('launching');
    try {
      const payload = {
        topic: null,
        auto_topic: false,
        num_scenes: scenes,
        use_scenario: false,
        local_only: localOnly,
        show_subtitles: showSubtitles,
        show_watermark: false,
        scenario: null,
        mode: 6,
        language: lang,
        mode6_num_characters: mode6NumCharacters,
      };
      
      // Use rate limit check
      const result = await checkAndStartVideo(payload);
      
      setStep('form');
      if (result.status === 'started') {
        setStartedSession(result.session_id);
      } else if (result.status === 'queued') {
        setError('Лимит исчерпан. Видео добавлено в очередь и запустится в следующем часе.');
      }
    } catch (e) {
      setError(e.message);
      setStep('form');
    }
  }

  /* Mode 7: ASMR animal keyboard videos — прямой запуск */
  async function handleMode7Launch() {
    if (mode7Keyboards.length < 3) {
      setError('Выберите минимум 3 клавиатуры');
      return;
    }
    setError('');
    setStep('launching');
    try {
      const payload = {
        topic: null,
        auto_topic: false,
        num_scenes: mode7NumKeyboards,
        use_scenario: false,
        local_only: localOnly,
        show_subtitles: false,
        show_watermark: false,
        scenario: null,
        mode: 7,
        language: lang,
        mode7_animal_type: mode7AnimalType === 'random' ? null : mode7AnimalType,
        mode7_keyboards: mode7Keyboards,
      };
      
      // Use rate limit check
      const result = await checkAndStartVideo(payload);
      
      setStep('form');
      if (result.status === 'started') {
        setStartedSession(result.session_id);
      } else if (result.status === 'queued') {
        setError('Лимит исчерпан. Видео добавлено в очередь и запустится в следующем часе.');
      }
    } catch (e) {
      setError(e.message);
      setStep('form');
    }
  }

  /* Mode 8: House Building Timelapse */
  async function handleMode8Launch() {
    setError('');
    setStep('launching');
    try {
      const payload = {
        topic: null,
        auto_topic: false,
        num_scenes: mode8NumStages,
        use_scenario: false,
        local_only: localOnly,
        show_subtitles: false,
        show_watermark: false,
        scenario: null,
        mode: 8,
        language: lang,
        mode8_house_style: mode8HouseStyle === 'random' ? null : mode8HouseStyle,
        mode8_location: mode8Location === 'random' ? null : mode8Location,
        mode8_num_stages: mode8NumStages,
        mode8_num_floors: mode8NumFloors,
      };

      const result = await checkAndStartVideo(payload);

      setStep('form');
      if (result.status === 'started') {
        setStartedSession(result.session_id);
      } else if (result.status === 'queued') {
        setError('Лимит исчерпан. Видео добавлено в очередь и запустится в следующем часе.');
      }
    } catch (e) {
      setError(e.message);
      setStep('form');
    }
  }

  /* Mode 10: уборка пляжа */
  async function handleMode10Launch() {
    setError('');
    setStep('launching');
    try {
      const payload = {
        topic: null,
        auto_topic: false,
        num_scenes: mode10NumStages,
        use_scenario: false,
        local_only: localOnly,
        show_subtitles: false,
        show_watermark: false,
        scenario: null,
        mode: 10,
        language: lang,
        mode10_beach_type: mode10BeachType === 'random' ? null : mode10BeachType,
        mode10_coast_setting: mode10CoastSetting === 'random' ? null : mode10CoastSetting,
        mode10_num_stages: mode10NumStages,
      };

      const result = await checkAndStartVideo(payload);

      setStep('form');
      if (result.status === 'started') {
        setStartedSession(result.session_id);
      } else if (result.status === 'queued') {
        setError('Лимит исчерпан. Видео добавлено в очередь и запустится в следующем часе.');
      }
    } catch (e) {
      setError(e.message);
      setStep('form');
    }
  }

  /* Mode 11: reverse monument timelapse */
  async function handleMode11Launch() {
    setError('');
    setStep('launching');
    try {
      const payload = {
        topic: null,
        auto_topic: false,
        num_scenes: mode11NumStages,
        mode11_num_stages: mode11NumStages,
        use_scenario: false,
        local_only: localOnly,
        show_subtitles: false,
        show_watermark: false,
        scenario: null,
        mode: 11,
        language: 'ru',
        mode11_structure_type: mode11StructureType,
      };

      const result = await checkAndStartVideo(payload);

      setStep('form');
      if (result.status === 'started') {
        setStartedSession(result.session_id);
      } else if (result.status === 'queued') {
        setError('Лимит исчерпан. Видео добавлено в очередь и запустится в следующем часе.');
      }
    } catch (e) {
      setError(e.message);
      setStep('form');
    }
  }

  /* Mode 9: Vehicle Assembly Timelapse */
  async function handleMode9Launch() {
    setError('');
    setStep('launching');
    try {
      const payload = {
        topic: null,
        auto_topic: false,
        num_scenes: mode9NumStages,
        use_scenario: false,
        local_only: localOnly,
        show_subtitles: false,
        show_watermark: false,
        scenario: null,
        mode: 9,
        language: lang,
        mode9_vehicle_type: mode9VehicleType === 'random' ? null : mode9VehicleType,
        mode9_location: mode9Location === 'random' ? null : mode9Location,
        mode9_num_stages: mode9NumStages,
      };

      const result = await checkAndStartVideo(payload);

      setStep('form');
      if (result.status === 'started') {
        setStartedSession(result.session_id);
      } else if (result.status === 'queued') {
        setError('Лимит исчерпан. Видео добавлено в очередь и запустится в следующем часе.');
      }
    } catch (e) {
      setError(e.message);
      setStep('form');
    }
  }

  async function handleMode13Launch() {
    if (!mode13Audio?.path) {
      setError('Загрузите аудиофайл');
      return;
    }
    setError('');
    setStep('launching');
    try {
      const payload = {
        topic: 'Audio slideshow',
        auto_topic: false,
        num_scenes: 1,
        use_scenario: false,
        local_only: localOnly,
        show_subtitles: showSubtitles,
        show_watermark: false,
        scenario: null,
        mode: 13,
        language: 'ru',
        mode13_audio_path: mode13Audio.path,
        mode13_voice_preset: mode13VoicePreset,
        mode13_language: mode13WhisperLang === 'ru' || mode13WhisperLang === 'en' ? mode13WhisperLang : null,
        mode13_show_subtitles: mode13ShowSubtitles,
        mode13_skip_final_assembly: true,
        mode13_chunk_seconds: 300,
        mode13_segment_seconds: 30,
        mode13_video_header_title: mode13HeaderTitle.trim() || null,
        mode13_voice_gain_db: mode13GainDb,
        mode13_voice_tempo_scale: mode13TempoPct / 100,
        mode13_voice_pitch_semitones: mode13PitchSemi,
        mode13_voice_ai_cleanup: mode13AiCleanup,
        mode13_voice_noise_suppression: mode13NoiseSupp,
        mode13_voice_level_normalize: mode13LevelNorm,
        mode13_voice_deesser: mode13Deesser,
        mode13_voice_clarity: mode13Clarity,
        mode13_voice_mud_cut: mode13MudCut,
        mode13_voice_compression: mode13Compression,
        mode13_voice_highpass_hz: mode13HpAuto ? null : mode13HighpassHz,
      };
      const result = await checkAndStartVideo(payload);
      setStep('form');
      if (result.status === 'started') {
        setStartedSession(result.session_id);
      } else if (result.status === 'queued') {
        setError('Лимит исчерпан. Видео добавлено в очередь и запустится в следующем часе.');
      }
    } catch (e) {
      setError(e.message);
      setStep('form');
    }
  }

  /* Mode 4: цитата + фото — прямой запуск */
  async function handleMode4Launch() {
    if (!mode4Quote.trim()) {
      setError('Введите цитату');
      return;
    }
    if (!mode4Photo?.path) {
      setError('Загрузите фото личности');
      return;
    }
    if (mode4Multiclip && mode4QuoteBlocks.length < 2) {
      setError('Для нескольких фрагментов добавьте в цитате минимум 2 абзаца через пустую строку');
      return;
    }
    setError('');
    setStep('launching');
    try {
      const manualSegs = mode4Multiclip ? mode4QuoteBlocks : null;
      const normalizedMode4OnlyLang = normalizeMode4OnlyLang(mode4OutputLang, mode4Multiclip);
      const payload = {
        topic: 'Quote',
        auto_topic: false,
        num_scenes: 1,
        use_scenario: false,
        local_only: localOnly,
        show_subtitles: showSubtitles,
        show_watermark: false,
        scenario: null,
        mode: 4,
        language: 'both',
        mode4_quote: mode4Quote.trim(),
        mode4_person_name: mode4PersonName.trim(),
        mode4_photo_path: mode4Photo.path,
        mode4_only_lang: normalizedMode4OnlyLang,
        mode4_show_author_on_video: mode4ShowAuthorOnVideo,
        mode4_video_header_title: mode4HeaderTitle.trim() || null,
        mode4_subtitle_style: mode4SubtitleStyle,
        mode4_location_hint: mode4LocationHint || null,
        mode4_multiclip: mode4Multiclip,
        mode4_segments: manualSegs && manualSegs.length >= 2 ? manualSegs : null,
        ...(mode4Multiclip ? { mode4_skip_final_assembly: true } : {}),
      };
      
      // Use rate limit check
      const result = await checkAndStartVideo(payload);
      
      setStep('form');
      if (result.status === 'started') {
        recordMode4PersonName(mode4PersonName);
        setMode4PersonNameSuggestRev((x) => x + 1);
        setStartedSession(result.session_id);
      } else if (result.status === 'queued') {
        recordMode4PersonName(mode4PersonName);
        setMode4PersonNameSuggestRev((x) => x + 1);
        setError('Лимит исчерпан. Видео добавлено в очередь и запустится в следующем часе.');
      }
    } catch (e) {
      setError(e.message);
      setStep('form');
    }
  }

  /* Mode 3: восстановление домов — прямой запуск */
  async function handleMode3Launch() {
    const useType = mode3InputMode === 'type';
    if (useType && !mode3HouseType) {
      setError('Выберите тип дома');
      return;
    }
    if (!useType && (!mode3StartImage?.path || !mode3EndImage?.path)) {
      setError('Загрузите обе картинки: дом ДО и дом ПОСЛЕ реставрации');
      return;
    }
    setError('');
    setStep('launching');
    try {
      const houseLabel = useType ? HOUSE_TYPES.find(h => h.id === mode3HouseType)?.label || mode3HouseType : null;
      const payload = {
        topic: 'House Restoration',
        auto_topic: false,
        num_scenes: 5,
        use_scenario: false,
        local_only: localOnly,
        show_subtitles: false,
        show_watermark: false,
        scenario: null,
        mode: 3,
        language: 'en',
        mode3_start_image_path: useType ? null : mode3StartImage?.path,
        mode3_end_image_path: useType ? null : mode3EndImage?.path,
        mode3_topic: useType ? houseLabel : null,
      };
      
      // Use rate limit check
      const result = await checkAndStartVideo(payload);
      
      setStep('form');
      if (result.status === 'started') {
        setStartedSession(result.session_id);
      } else if (result.status === 'queued') {
        setError('Лимит исчерпан. Видео добавлено в очередь и запустится в следующем часе.');
      }
    } catch (e) {
      setError(e.message);
      setStep('form');
    }
  }

  /* Skip scenario preview — launch directly */
  async function handleDirectLaunch() {
    if (!topic.trim()) {
      setError('Введите тему для видео');
      return;
    }
    setError('');
    setStep('launching');
    try {
      const payload = {
        topic: topic.trim(),
        auto_topic: false,
        num_scenes: scenes,
        use_scenario: useScenario,
        local_only: localOnly,
        show_subtitles: showSubtitles,
        show_watermark: false,
        scenario: null,
        mode,
        language: lang,
        reference_image_path: referenceImage?.path || null,
      };
      
      // Use rate limit check
      const result = await checkAndStartVideo(payload);
      
      setStep('form');
      if (result.status === 'started') {
        setStartedSession(result.session_id);
      } else if (result.status === 'queued') {
        setError('Лимит исчерпан. Видео добавлено в очередь и запустится в следующем часе.');
      }
    } catch (e) {
      setError(e.message);
      setStep('select_mode');
    }
  }

  const isLoading = step === 'generating_scenario' || step === 'launching';

  function handleSelectMode(m) {
    setMode(m);
    setStep('form');
  }

  /* ── render ─────────────────────────────────────────────────────────────── */
  return (
    <div className="max-w-2xl mx-auto px-6 py-10">
      {/* ── STEP: SELECT MODE ─────────────────────────────────────────────── */}
      <AnimatePresence mode="wait">
        {step === 'select_mode' && (
          <motion.div
            key="select_mode"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="space-y-6"
          >
            <div className="mb-8">
              <h1 className="text-2xl font-bold text-white mb-1">Создать видео</h1>
              <p className="text-[#71717a] text-sm">Выберите режим создания — параметры будут разными</p>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              {MODES.map((m) => (
                <motion.button
                  key={m.id}
                  type="button"
                  onClick={() => handleSelectMode(m.id)}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  className="card p-6 text-left hover:border-brand-600/40 hover:bg-brand-600/5 transition-all group"
                >
                  <span className="text-3xl mb-3 block">{m.icon}</span>
                  <div className="text-base font-semibold text-white mb-1">{m.label}</div>
                  <div className="text-xs text-[#71717a] leading-relaxed">{m.desc}</div>
                </motion.button>
              ))}
            </div>
          </motion.div>
        )}

        {/* ── STEP: FORM (mode-specific) ──────────────────────────────────────── */}
        {step === 'form' && (
          <motion.div
            key="form"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="space-y-4"
          >
            {/* Back button */}
            <button
              type="button"
              onClick={() => setStep('select_mode')}
              className="flex items-center gap-2 text-sm text-[#71717a] hover:text-brand-400 mb-6 transition-colors"
            >
              <RiArrowLeftLine className="text-base" />
              Назад
            </button>

            {prefillBanner ? (
              <div className="mb-4 p-3 rounded-xl bg-amber-900/20 border border-amber-700/40 text-sm text-amber-100/95 flex flex-wrap items-center justify-between gap-2">
                <span>Параметры подставлены из прошлого запуска. Проверьте форму и запустите снова.</span>
                <button
                  type="button"
                  onClick={() => setPrefillBanner(false)}
                  className="text-xs font-medium text-amber-300 hover:text-amber-200 underline shrink-0"
                >
                  Скрыть
                </button>
              </div>
            ) : null}

            {/* Header */}
            <div className={mode === 5 ? 'mb-8' : 'mb-6'}>
              {mode === 5 ? (
                <div className="relative overflow-hidden rounded-2xl border border-[#2a2a38] bg-gradient-to-br from-[#15151f] via-[#121218] to-brand-900/[0.2] px-5 py-6 sm:px-8 sm:py-7 shadow-xl shadow-black/25">
                  <div className="pointer-events-none absolute -right-10 top-0 h-44 w-44 rounded-full bg-brand-500/18 blur-3xl" />
                  <div className="pointer-events-none absolute -left-12 bottom-0 h-36 w-36 rounded-full bg-violet-600/12 blur-3xl" />
                  <div className="relative flex flex-col gap-3">
                    <div className="inline-flex w-fit items-center gap-2 rounded-full border border-brand-500/35 bg-brand-600/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-brand-300">
                      <RiMovie2Line className="text-base text-brand-400 shrink-0" aria-hidden />
                      Режим 5 · Long-form
                    </div>
                    <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">
                      Длинные видео
                    </h1>
                    <p className="text-sm text-[#a1a1aa] max-w-3xl leading-relaxed">
                      Ручной текст, Bible, «77 фактов», план из описания, «книга на ночь» или документальное расследование — сценарий и озвучка по частям, превью каждого блока и финальный монтаж в одном потоке.
                    </p>
                  </div>
                </div>
              ) : (
                <>
                  <h1 className="text-2xl font-bold text-white mb-1">
                    {mode === 3 ? 'Реставрация дома' : mode === 4 ? 'Цитата + фото' : mode === 6 ? 'Cartoon Drama' : mode === 7 ? 'ASMR Keyboard' : mode === 8 ? 'House Timelapse' : mode === 9 ? 'Vehicle Assembly' : mode === 10 ? 'Уборка пляжа' : mode === 11 ? 'Выбор постройки' : mode === 13 ? 'Аудио → слайды' : 'Создать видео'}
                  </h1>
                  <p className="text-[#71717a] text-sm">
                    {mode === 3
                      ? 'Маленький дом, одна комната-студия. AI создаст промпты и фото. 8 фрагментов: intro, 3 экстерьер, 3 интерьер (как снаружи), финал (скриншот clip 3 → снаружи→внутри). Музыка.'
                      : mode === 4
                        ? 'Цитата и имя автора. Один абзац — один короткий ролик (RU+EN или один язык). Несколько абзацев через пустую строку — несколько клипов: только один язык (RU или EN), превью фрагментов и финальный монтаж; стиль субтитров — в настройках режима.'
                        : mode === 6
                          ? 'AI генерирует абсурдные вирусные истории с овощными персонажами. Драма, конфликт, шокирующие повороты. Идеально для TikTok/Reels/Shorts.'
                          : mode === 7
                            ? 'ASMR видео: животные нажимают клавиши разных поверхностей (мёд, желе, лёд, шоколад). Без голоса и субтитров — только качественные звуки нажатий.'
                            : mode === 8
                              ? 'Timelapse видео: пустой участок → фундамент → стены → крыша → готовый дом. Фотореалистичный стиль, как снято на смартфон.'
                              : mode === 9
                                ? 'Timelapse сборки транспорта: рама → двигатель → кузов → колёса → готовый автомобиль/самолёт/трактор. Фотореалистичный стиль.'
                                : mode === 10
                                  ? 'Timelapse уборки: загрязнённый пляж → сбор мусора, грабли, техника → чистый берег. Тот же пайплайн, что у стройки дома, но сюжет — экология.'
                                  : mode === 11
                                    ? 'Выберите постройку и нажмите «Генерировать». Сцены фиксируются в одной локации и одном ракурсе.'
                                    : mode === 13
                                      ? 'Загрузите длинное аудио: тембр слегка меняется фильтрами, текст извлекается Whisper по частям ~5 мин, картинки по ~30 с в едином стиле. Проверка превью, перегенерация отдельных слайдов, затем склейка в один ролик.'
                                      : 'AI-агенты напишут сценарий, сгенерируют изображения и смонтируют видео.'}
                  </p>
                </>
              )}
            </div>

            {/* Mode 5: длинные видео */}
            {mode === 5 ? (
              <div className="space-y-6">
                <div className="rounded-2xl border border-[#2e2e3c] bg-[#121218]/90 p-5 sm:p-6 shadow-lg shadow-black/20">
                  <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between mb-4">
                    <div>
                      <h2 className="text-sm font-semibold text-white tracking-tight">
                        Подрежим пайплайна
                      </h2>
                      <p className="text-xs text-[#71717a] mt-1 max-w-xl">
                        Сначала выберите подрежим, затем при необходимости включите тестовый прогон (~5 мин озвучки) переключателем ниже.
                      </p>
                    </div>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
                    {MODE5_SUBMODE_DEFS.map(({ id, label, hint, Icon }) => {
                      const active = mode5SubMode === id;
                      return (
                        <button
                          key={id}
                          type="button"
                          title={hint}
                          onClick={() => setMode5SubMode(id)}
                          className={`flex flex-col gap-2 p-4 text-left rounded-xl border transition-all duration-200 ${
                            active
                              ? 'border-brand-500/50 bg-gradient-to-br from-brand-600/20 via-brand-600/5 to-transparent shadow-[0_0_0_1px_rgba(139,92,246,0.25)]'
                              : 'border-[#2b2b38] bg-[#16161f]/80 hover:border-[#3f3f52] hover:bg-[#1a1a26]'
                          }`}
                        >
                          <div className="flex items-start gap-3">
                            <span
                              className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border ${
                                active
                                  ? 'border-brand-500/40 bg-brand-600/25 text-brand-300'
                                  : 'border-[#2f2f3d] bg-[#1c1c28] text-[#71717a]'
                              }`}
                            >
                              <Icon className="text-lg" aria-hidden />
                            </span>
                            <span className="min-w-0 flex-1">
                              <span className="block text-sm font-semibold text-[#f4f4fb] leading-snug">{label}</span>
                              <span className="mt-1 block text-[11px] leading-relaxed text-[#71717a]">{hint}</span>
                            </span>
                          </div>
                        </button>
                      );
                    })}
                  </div>

                  <div className="mt-5 pt-4 border-t border-white/[0.06] flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <div className="text-sm font-semibold text-[#ececf4]">Тестовый прогон (~5 мин)</div>
                      <p className="text-xs text-[#71717a] mt-0.5 max-w-md leading-relaxed">
                        Короткая озвучка без полного объёма — чтобы проверить подрежим. Выкл. — обычная полная генерация.
                      </p>
                    </div>
                    <Toggle value={mode5TestRun} onChange={setMode5TestRun} />
                  </div>
                  <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <div className="text-sm font-semibold text-[#ececf4]">Сразу один финальный ролик</div>
                      <p className="text-xs text-[#71717a] mt-0.5 max-w-md leading-relaxed">
                        Не собирать превью по частям для проверки — после иллюстраций сразу длинное{' '}
                        <code className="text-[#71717a]">video_mode5.mp4</code> одним проходом (дольше по времени, зато без промежуточного монтажа).
                      </p>
                    </div>
                    <Toggle value={mode5SkipChunkPreviews} onChange={setMode5SkipChunkPreviews} />
                  </div>
                  <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <div className="text-sm font-semibold text-[#ececf4]">Без параллельной генерации частей</div>
                      <p className="text-xs text-[#71717a] mt-0.5 max-w-md leading-relaxed">
                        Озвучка, иллюстрации и сборка превью{' '}
                        <code className="text-[#71717a]">mode5_preview_*.mp4</code> по одной части за раз — медленнее,
                        но меньше нагрузка на VoiceAPI, FastGen и CPU при монтаже.
                      </p>
                    </div>
                    <Toggle value={mode5SequentialChunks} onChange={setMode5SequentialChunks} />
                  </div>
                  <div className="mt-4 rounded-xl border border-[#2e2e3c] bg-[#14141d]/60 p-4">
                    <label className="block text-xs font-semibold uppercase tracking-wider text-[#a1a1aa] mb-2">
                      Анимированных клипов (block-loop)
                    </label>
                    <div className="flex items-center gap-3">
                      <input
                        type="number"
                        min={1}
                        max={20}
                        step={1}
                        className="input w-24 text-base bg-[#14141d]/90 border-[#323242]"
                        value={mode5BlockLoopPoolSize}
                        onChange={e => {
                          const n = Math.round(Number(e.target.value));
                          if (!Number.isFinite(n)) return;
                          setMode5BlockLoopPoolSize(Math.max(1, Math.min(20, n)));
                        }}
                      />
                      <span className="text-xs text-[#71717a] leading-relaxed">
                        Сколько коротких анимированных роликов сгенерировать до подтверждения intro.
                        Один клип ≈ 30 мин озвучки. Если итоговая озвучка короче — в монтаж попадут
                        только первые N клипов по вашему порядку; лишние не используются.
                      </span>
                    </div>
                  </div>
                </div>

                <div className="relative rounded-2xl border border-[#2e2e3c] bg-gradient-to-b from-[#16161f] to-[#121218] p-5 sm:p-6 overflow-hidden">
                  <div className="pointer-events-none absolute left-0 top-0 h-full w-1 bg-gradient-to-b from-brand-500/70 via-brand-500/30 to-transparent rounded-l-2xl" />
                  <div className="relative pl-2 sm:pl-3">
                    {mode5SubMode === 'bible' ? (
                      <div className="space-y-4">
                        <div className="rounded-xl border border-[#2b2b38] bg-[#14141d]/90 p-4">
                          <label className="block text-[11px] font-medium text-[#a1a1aa] mb-1.5">
                            Текст на превью YouTube
                          </label>
                          <input
                            type="text"
                            className="input text-sm bg-[#121218]/90 border-[#323242] focus:border-brand-500/60"
                            placeholder="Например: MATTHEW 5 — THE BEATITUDES"
                            value={mode5ThumbnailOverlayText}
                            onChange={e => setMode5ThumbnailOverlayText(e.target.value)}
                            maxLength={48}
                          />
                          <p className="text-[11px] text-[#71717a] mt-2 leading-relaxed">
                            Единственная надпись на превью YouTube — только этот текст, без «HOLY BIBLE» и других строк.
                            Если оставить пустым — на картинке не будет никакого текста.
                          </p>
                        </div>
                        <div className="rounded-xl border border-dashed border-[#3a3a4a] bg-[#121218]/70 p-4 space-y-3">
                          <div>
                            <label className="text-xs font-semibold uppercase tracking-wider text-[#a1a1aa]">
                              Импорт из одного текста
                            </label>
                            <p className="text-xs text-[#71717a] mt-1 max-w-xl leading-relaxed">
                              Вставьте несколько глав подряд — система разобьёт по заголовкам{' '}
                              <code className="text-[#71717a]">Chapter 2</code>,{' '}
                              <code className="text-[#71717a]">Matthew 3</code>,{' '}
                              <code className="text-[#71717a]">глава 4</code> и похожим маркерам.
                              Подписи сверху подставятся автоматически, их можно отредактировать ниже.
                            </p>
                          </div>
                          <textarea
                            className="input text-sm min-h-[140px] leading-relaxed bg-[#14141d]/90 border-[#323242] focus:border-brand-500/60"
                            placeholder={'Chapter 1. In the beginning God created the heaven and the earth...\n\nChapter 2. Thus the heavens and the earth were finished...'}
                            value={mode5BibleImportText}
                            onChange={e => setMode5BibleImportText(e.target.value)}
                          />
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="text-[10px] text-[#52525b] tabular-nums">
                              {mode5BibleImportText.length.toLocaleString()} симв.
                            </span>
                            <button
                              type="button"
                              onClick={handleMode5SplitBibleImport}
                              disabled={mode5BibleImportLoading || mode5BibleImportText.trim().length < 20}
                              className="inline-flex items-center gap-1.5 rounded-lg border border-brand-500/40 bg-brand-600/15 px-3 py-2 text-xs font-medium text-brand-200 hover:bg-brand-600/25 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                            >
                              {mode5BibleImportLoading ? (
                                <RiLoader4Line className="text-sm animate-spin" aria-hidden />
                              ) : (
                                <RiScissorsCutLine className="text-sm" aria-hidden />
                              )}
                              Разбить на главы
                            </button>
                          </div>
                        </div>

                        <div className="flex flex-wrap items-center justify-between gap-3 mb-1">
                          <div>
                            <label className="text-xs font-semibold uppercase tracking-wider text-[#a1a1aa]">
                              Главы для озвучки
                            </label>
                            <p className="text-xs text-[#71717a] mt-1 max-w-xl leading-relaxed">
                              Каждая глава — отдельная часть озвучки. Подпись сверху показывается на видео над субтитрами.
                            </p>
                          </div>
                          <button
                            type="button"
                            onClick={() => setMode5BibleChapters(prev => [...prev, newMode5BibleChapter()])}
                            className="inline-flex items-center gap-1.5 rounded-lg border border-[#323242] bg-[#16161f] px-3 py-2 text-xs font-medium text-[#d4d4dc] hover:border-brand-500/40 hover:text-white transition-colors"
                          >
                            <RiAddLine className="text-sm" aria-hidden />
                            Добавить главу
                          </button>
                        </div>
                        {mode5BibleChapters.map((chapter, idx) => (
                          <div
                            key={chapter.id}
                            className="rounded-xl border border-[#2b2b38] bg-[#14141d]/90 p-4 space-y-3"
                          >
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <span className="text-[11px] font-semibold uppercase tracking-wider text-[#71717a]">
                                Глава {idx + 1}
                              </span>
                              {mode5BibleChapters.length > 1 && (
                                <button
                                  type="button"
                                  onClick={() =>
                                    setMode5BibleChapters(prev =>
                                      prev.filter(ch => ch.id !== chapter.id),
                                    )
                                  }
                                  className="inline-flex items-center gap-1 text-[11px] text-[#71717a] hover:text-red-400 transition-colors"
                                >
                                  <RiDeleteBinLine aria-hidden />
                                  Удалить
                                </button>
                              )}
                            </div>
                            <div>
                              <label className="block text-[11px] font-medium text-[#a1a1aa] mb-1.5">
                                Подпись сверху на видео
                              </label>
                              <input
                                type="text"
                                className="input text-sm bg-[#121218]/90 border-[#323242] focus:border-brand-500/60"
                                placeholder={`Например: Matthew ${idx + 1}`}
                                value={chapter.overlayLabel}
                                onChange={e =>
                                  setMode5BibleChapters(prev =>
                                    prev.map(ch =>
                                      ch.id === chapter.id
                                        ? { ...ch, overlayLabel: e.target.value }
                                        : ch,
                                    ),
                                  )
                                }
                              />
                            </div>
                            <div>
                              <div className="flex items-baseline justify-between gap-2 mb-1.5">
                                <label className="text-[11px] font-medium text-[#a1a1aa]">
                                  Текст главы для озвучки
                                </label>
                                <span className="text-[10px] text-[#52525b] tabular-nums">
                                  {chapter.text.length.toLocaleString()} симв.
                                </span>
                              </div>
                              <textarea
                                className="input text-sm min-h-[160px] leading-relaxed bg-[#121218]/90 border-[#323242] focus:border-brand-500/60"
                                placeholder="Вставьте текст этой главы — целиком, как должен прозвучать в ролике."
                                value={chapter.text}
                                onChange={e =>
                                  setMode5BibleChapters(prev =>
                                    prev.map(ch =>
                                      ch.id === chapter.id ? { ...ch, text: e.target.value } : ch,
                                    ),
                                  )
                                }
                              />
                            </div>
                          </div>
                        ))}
                        <p className="text-xs text-[#71717a] leading-relaxed border-t border-[#27272f]/80 pt-3">
                          Сначала сгенерируется одно анимированное превью (~30 мин слота) — подтвердите его на странице прогресса.
                          Затем озвучка по главам и сборка; отдельные JPEG на каждые 15 с не создаются.
                          Сверху — ваша подпись, снизу субтитры.
                        </p>
                      </div>
                    ) : (
                      <>
                    <div className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
                      <label className="text-xs font-semibold uppercase tracking-wider text-[#a1a1aa]">
                        {mode5SubMode === 'outline'
                          ? 'Краткое описание сюжета'
                          : mode5SubMode === 'facts50' || mode5SubMode === 'book_night' || mode5SubMode === 'unwritten_chapter'
                            ? mode5SubMode === 'book_night'
                              ? 'Название книги'
                              : mode5SubMode === 'unwritten_chapter'
                                ? 'Тема расследования'
                                : 'Тема / заголовок'
                            : 'Текст для озвучки'}
                      </label>
                      <span className="text-[10px] font-medium text-[#52525b] tabular-nums">
                        {mode5Script.length.toLocaleString()} симв.
                      </span>
                    </div>
                    <textarea
                      className="input text-sm min-h-[260px] leading-relaxed bg-[#14141d]/90 border-[#323242] focus:border-brand-500/60"
                      placeholder={
                        mode5SubMode === 'facts50'
                          ? 'Например: 77 фактов о Франции — нейросеть придумает 77 интересных фактов и отдельный связный текст озвучки для каждого.'
                          : mode5SubMode === 'book_night'
                            ? 'Например: Семь навыков высокоэффективных людей, Стивен Кови — модель построит план по структуре книги и спокойно изложит суть по подглавам (их число — как в оглавлении, не фиксировано).'
                            : mode5SubMode === 'unwritten_chapter'
                              ? 'Например: Почему официальная версия Карибского кризиса скрывает реальные договоренности и влияние теневых переговоров. Укажите одну тему; сценарий 30–50 минут будет создан автоматически.'
                              : mode5SubMode === 'outline'
                                ? 'Например: Старый маяк на туманном острове. Смотритель живёт один, по вечерам зажигает лампу и слушает волны. Однажды к берегу прибивает странный предмет — не страшно, но меняет его рутину. Нужно именно описание, не одна фраза-название.'
                                : 'Вставьте сюда полный текст для озвучки. Система разобьёт его на чанки примерно по выбранной длительности и окна для картинок.'
                      }
                      value={mode5Script}
                      onChange={e => setMode5Script(e.target.value)}
                    />
                    <p className="text-xs text-[#71717a] mt-3 leading-relaxed border-t border-[#27272f]/80 pt-3">
                      {mode5SubMode === 'facts50'
                        ? 'После запуска сначала генерируется сценарий (факты + тексты), затем отдельные превью по клипам. Можно переозвучить фрагменты и собрать финальное видео кнопкой «Финальный монтаж».'
                        : mode5SubMode === 'book_night'
                          ? 'Сначала план по структуре выбранной книги, затем озвучка по каждой подглаве (объём блока — как у одного «факта» в режиме 77). Одна подглава = одно превью.'
                          : mode5SubMode === 'unwritten_chapter'
                            ? 'По одной теме генерируется расследовательский документальный сценарий: 5–7 блоков, микровыводы, подача в стиле архивного детектива, целевой объём 30–50 минут. Далее — review превью по частям.'
                            : mode5SubMode === 'outline'
                              ? 'По описанию строится план (главы и подглавы), затем спокойные тексты под каждую подглаву. Превью 10–18; суммарный объём озвучки сопоставим с режимом «77 фактов».'
                              : 'После старта — превью по чанкам: перегенерация кадров и переозвучка отдельных частей.'}
                    </p>
                      </>
                    )}
                  </div>
                </div>

                {isMode5AiSubMode(mode5SubMode) && (
                  <div className="rounded-2xl border border-[#2e2e3c] bg-[#121218] p-5 sm:p-6">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between mb-4">
                      <div className="min-w-0 flex-1">
                        <div className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-[#a1a1aa]">
                          <RiSparklingLine className="text-brand-400 text-base" aria-hidden />
                          Идеи от нейросети
                        </div>
                        <p className="text-xs text-[#71717a] mt-2 max-w-xl leading-relaxed">
                          По умолчанию выключено, чтобы не расходовать запросы к модели. После включения подтягиваются сохранённые темы; новая подборка — кнопкой «Новые темы». Клик по карточке подставит заголовок и запустит генерацию с учётом «Тестовый прогон» выше.
                        </p>
                      </div>
                      <div className="flex flex-col gap-3 sm:items-end shrink-0">
                        <div className="flex items-center gap-3 w-full sm:w-auto justify-between sm:justify-end rounded-xl border border-[#2c2c38] bg-[#16161f]/80 px-3 py-2">
                          <div className="text-left">
                            <div className="text-xs font-semibold text-[#ececf4]">Подборка тем</div>
                            <p className="text-[10px] text-[#71717a] mt-0.5 max-w-[200px] leading-snug">
                              Вкл. — кэш и кнопка «Новые темы» (тратит токены)
                            </p>
                          </div>
                          <Toggle value={mode5NeuralIdeasEnabled} onChange={setMode5NeuralIdeasEnabled} />
                        </div>
                        <button
                          type="button"
                          onClick={handleSuggestMode5Ideas}
                          disabled={
                            !mode5NeuralIdeasEnabled || mode5IdeasLoading || step === 'launching'
                          }
                          className="btn-secondary shrink-0 inline-flex items-center justify-center gap-2 text-sm py-2.5 px-4 disabled:opacity-45"
                        >
                          <RiRefreshLine className={mode5IdeasLoading ? 'animate-spin' : ''} />
                          {mode5IdeasLoading ? 'Обновляю…' : 'Новые темы'}
                        </button>
                      </div>
                    </div>
                    {!mode5NeuralIdeasEnabled ? (
                      <div className="rounded-xl border border-dashed border-[#333342] bg-[#16161f]/50 px-4 py-8 text-center">
                        <p className="text-sm text-[#71717a]">
                          Включите «Подборка тем», чтобы загрузить сохранённые идеи или запросить новые.
                        </p>
                      </div>
                    ) : mode5Ideas.length > 0 ? (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        {mode5Ideas.map((idea, idx) => {
                          const title = String(idea?.project_title || '').trim();
                          const topicLine = String(idea?.topic || '').trim();
                          const hook = String(idea?.hook || '').trim();
                          const key = `${idx}-${topicLine}`;
                          return (
                            <button
                              key={key}
                              type="button"
                              onClick={() => handleLaunchMode5FromIdea(idea, idx)}
                              disabled={!topicLine || step === 'launching' || mode5IdeaLaunchKey === key}
                              className="group text-left rounded-xl border border-[#2c2c38] bg-[#16161f]/90 p-4 transition-all hover:border-brand-500/45 hover:bg-[#1c1c28] hover:shadow-lg hover:shadow-brand-900/10 disabled:opacity-50 disabled:hover:border-[#2c2c38]"
                            >
                              <div className="text-sm font-semibold text-[#f4f4fb] group-hover:text-white leading-snug">
                                {title || topicLine}
                              </div>
                              {title ? (
                                <div className="text-xs text-brand-400/90 mt-2 font-medium line-clamp-2">{topicLine}</div>
                              ) : null}
                              {hook ? (
                                <div className="text-xs text-[#71717a] mt-2 line-clamp-2 leading-relaxed">{hook}</div>
                              ) : null}
                              <div className="mt-3 text-[10px] font-semibold uppercase tracking-wider text-brand-500/80 opacity-0 transition-opacity group-hover:opacity-100">
                                Запустить →
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="rounded-xl border border-dashed border-[#333342] bg-[#16161f]/50 px-4 py-8 text-center">
                        <p className="text-sm text-[#71717a]">
                          Сохранённых тем пока нет. Нажмите «Новые темы», чтобы сгенерировать подборку (расход токенов).
                        </p>
                      </div>
                    )}
                  </div>
                )}

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  <div className="rounded-2xl border border-[#2e2e3c] bg-[#121218] p-5 sm:p-6">
                    <div className="text-xs font-semibold uppercase tracking-wider text-[#a1a1aa] mb-3">
                      Язык генерации
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                      {MODE5_LANGUAGE_OPTIONS.map(({ id, label }) => (
                        <button
                          key={id}
                          type="button"
                          onClick={() => setMode5Lang(id)}
                          className={`rounded-xl py-2.5 px-3 text-sm font-semibold transition-all border ${
                            mode5Lang === id
                              ? 'border-brand-500/50 bg-brand-600/15 text-brand-300 shadow-inner shadow-brand-900/20'
                              : 'border-[#2b2b38] text-[#71717a] hover:border-[#404050] hover:text-[#e4e4f0] bg-[#16161f]'
                          }`}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                    <p className="text-[11px] text-[#71717a] mt-3 leading-relaxed">
                      Выбранный язык применяется к тексту, озвучке и метаданным mode 5.
                    </p>
                  </div>
                  <div className="rounded-2xl border border-[#2e2e3c] bg-[#121218] p-5 sm:p-6">
                    <div className="flex items-center gap-2 mb-4">
                      <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-[#323242] bg-[#181822] text-brand-400">
                        <RiPaletteLine className="text-lg" aria-hidden />
                      </span>
                      <div>
                        <div className="text-xs font-semibold uppercase tracking-wider text-[#a1a1aa]">
                          Генерация изображений
                        </div>
                        <p className="text-[11px] text-[#52525b] mt-0.5">Бэкенд для кадров в этом запуске</p>
                      </div>
                    </div>
                    <div className="flex flex-col sm:flex-row gap-2">
                      {[
                        { id: 'api', label: 'API', hint: 'Быстрее и стабильнее: fastgen_http' },
                        { id: 'playwright', label: 'Playwright', hint: 'Через браузер, как в старом mode12' },
                      ].map(({ id, label, hint }) => (
                        <button
                          key={id}
                          type="button"
                          title={hint}
                          onClick={() => setMode5ImageBackend(id)}
                          className={`flex-1 rounded-xl py-3 px-3 text-sm font-semibold transition-all border ${
                            mode5ImageBackend === id
                              ? 'border-brand-500/50 bg-brand-600/15 text-brand-300 shadow-inner shadow-brand-900/20'
                              : 'border-[#2b2b38] text-[#71717a] hover:border-[#404050] hover:text-[#e4e4f0] bg-[#16161f]'
                          }`}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                    <p className="text-[11px] text-[#52525b] mt-3 leading-relaxed">
                      Параметр сохраняется в теле запроса и истории сессии.
                    </p>
                  </div>

                  <div className="rounded-2xl border border-[#2e2e3c] bg-[#121218] p-5 sm:p-6 flex flex-col">
                    <label className="text-xs font-semibold uppercase tracking-wider text-[#a1a1aa] mb-2">
                      Заголовок проекта
                    </label>
                    <input
                      className="input text-base bg-[#14141d]/90 border-[#323242]"
                      placeholder="Например: История Древнего Рима"
                      value={mode5HeaderTitle}
                      onChange={e => setMode5HeaderTitle(e.target.value)}
                    />
                    <p className="text-[11px] text-[#71717a] leading-relaxed mt-auto pt-3">
                      Подпись сессии и заголовок на экране review.
                    </p>
                  </div>
                </div>
              </div>
            ) : mode === 6 ? (
              <div className="space-y-4">
                <div className="card p-5">
                  <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-3">
                    Количество персонажей
                  </label>
                  <div className="flex gap-2">
                    {[2, 3, 4].map(n => (
                      <button
                        key={n}
                        type="button"
                        onClick={() => setMode6NumCharacters(n)}
                        className={`flex-1 py-3 rounded-lg text-sm font-medium transition-all ${
                          mode6NumCharacters === n
                            ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                            : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                        }`}
                      >
                        {n} {n === 2 ? 'персонажа' : 'персонажей'}
                      </button>
                    ))}
                  </div>
                  <p className="text-xs text-[#52525b] mt-3">
                    AI выберет персонажей из базы (Брокколи, Баклажан, Помидор, Картошка и др.) и создаст абсурдную драму.
                  </p>
                </div>
                <div className="card p-5 bg-gradient-to-br from-purple-900/20 to-pink-900/20 border-purple-700/30">
                  <div className="text-sm font-semibold text-purple-300 mb-2">🎭 Примеры персонажей</div>
                  <div className="grid grid-cols-2 gap-2 text-xs text-[#a1a1aa]">
                    <div>🥦 <span className="text-purple-400">Брокколи</span> — альфа-лидер, доминант</div>
                    <div>🍆 <span className="text-purple-400">Баклажан</span> — соблазнитель</div>
                    <div>🍅 <span className="text-purple-400">Помидор</span> — главная героиня</div>
                    <div>🥔 <span className="text-purple-400">Картошка</span> — лузер, жертва</div>
                    <div>🥑 <span className="text-purple-400">Авокадо</span> — инфлюенсер</div>
                    <div>🧄 <span className="text-purple-400">Чеснок</span> — трикстер, хаос</div>
                  </div>
                </div>
              </div>
            ) : mode === 7 ? (
              <div className="space-y-4">
                {/* Animal selection */}
                <div className="card p-5">
                  <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-3">
                    Животное
                  </label>
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      { key: 'random', label: '🎲 Случайное' },
                      { key: 'cat', label: '🐱 Кот' },
                      { key: 'dog', label: '🐶 Собака' },
                      { key: 'kitten', label: '🐱 Котёнок' },
                      { key: 'puppy', label: '🐶 Щенок' },
                    ].map(opt => (
                      <button
                        key={opt.key}
                        type="button"
                        onClick={() => setMode7AnimalType(opt.key)}
                        className={`py-2.5 rounded-lg text-xs font-medium transition-all ${
                          mode7AnimalType === opt.key
                            ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                            : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>
                
                {/* Keyboard selection */}
                <div className="card p-5">
                  <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-3">
                    Клавиатуры (выберите 3-4)
                  </label>
                  <p className="text-xs text-[#52525b] mb-3">
                    Выберите поверхности для ASMR видео. Животное будет нажимать клавиши каждой.
                  </p>
                  <div className="grid grid-cols-2 gap-2">
                    {[
                      { key: 'honey', label: '🍯 Мёд', desc: 'липкий, тянется' },
                      { key: 'caramel', label: '🍬 Карамель', desc: 'упругая, сладкая' },
                      { key: 'jelly', label: '🍮 Желе', desc: 'дрожит, хлюпает' },
                      { key: 'slime', label: '🧪 Слизь', desc: 'тянется, хлюпает' },
                      { key: 'ice', label: '🧊 Лёд', desc: 'хрустит, трескается' },
                      { key: 'chocolate', label: '🍫 Шоколад', desc: 'тает, мягкий' },
                      { key: 'cheese', label: '🧀 Сыр', desc: 'упругий, пористый' },
                      { key: 'marshmallow', label: '☁️ Маршмеллоу', desc: 'воздушный, пружинит' },
                      { key: 'liquid_metal', label: '✨ Жидкий металл', desc: 'течёт, зеркальный' },
                    ].map(kb => (
                      <button
                        key={kb.key}
                        type="button"
                        onClick={() => {
                          const selected = mode7Keyboards;
                          if (selected.includes(kb.key)) {
                            setMode7Keyboards(selected.filter(k => k !== kb.key));
                          } else if (selected.length < 4) {
                            setMode7Keyboards([...selected, kb.key]);
                          }
                        }}
                        className={`py-2.5 px-3 rounded-lg text-xs font-medium transition-all text-left ${
                          mode7Keyboards.includes(kb.key)
                            ? 'bg-amber-600/20 text-amber-300 border border-amber-600/40'
                            : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                        }`}
                      >
                        <div className="font-medium">{kb.label}</div>
                        <div className="text-[10px] text-[#52525b]">{kb.desc}</div>
                      </button>
                    ))}
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    <span className="text-xs text-[#71717a]">Выбрано:</span>
                    <span className="text-xs font-medium text-amber-400">
                      {mode7Keyboards.length > 0 
                        ? mode7Keyboards.map(k => KEYBOARD_LABELS[k] || k).join(', ')
                        : 'Выберите минимум 3 клавиатуры'}
                    </span>
                    <span className="text-xs text-[#52525b]">({mode7Keyboards.length}/4)</span>
                  </div>
                </div>

                {/* ASMR Info card */}
                <div className="card p-4 bg-gradient-to-br from-purple-900/20 to-pink-900/10 border-purple-700/30">
                  <div className="text-sm font-semibold text-purple-300 mb-2">🎧 ASMR Режим</div>
                  <p className="text-xs text-[#a1a1aa]">
                    Видео без голоса и субтитров — только качественные ASMR звуки нажатий и отпускания клавиш.
                  </p>
                </div>
              </div>
            ) : mode === 8 ? (
              <div className="space-y-4">
                    {/* House style selection */}
                    <div className="card p-5">
                      <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-3">
                        Стиль дома
                      </label>

                      {/* 🎲 СЛУЧАЙНЫЙ */}
                      <div className="mb-4">
                        <button
                          type="button"
                          onClick={() => setMode8HouseStyle('random')}
                          className={`w-full py-2.5 rounded-lg text-xs font-medium transition-all ${
                            mode8HouseStyle === 'random'
                              ? 'bg-purple-600/20 text-purple-400 border border-purple-600/40'
                              : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                          }`}
                        >
                          🎲 Случайный стиль
                        </button>
                      </div>

                      {/* 🏙️ СОВРЕМЕННЫЕ */}
                      <div className="mb-4">
                        <div className="text-xs font-semibold text-brand-400 mb-2 uppercase">🏙️ Современные</div>
                        <div className="grid grid-cols-3 gap-2">
                          {[
                            { key: 'modern', label: '🏙️ Современный' },
                            { key: 'contemporary', label: '🏢 Контемпорари' },
                            { key: 'minimalist', label: '⬜ Минимализм' },
                            { key: 'scandinavian', label: '🇸🇪 Скандинавский' },
                          ].map(opt => (
                            <button
                              key={opt.key}
                              type="button"
                              onClick={() => setMode8HouseStyle(opt.key)}
                              className={`py-2.5 rounded-lg text-xs font-medium transition-all ${
                                mode8HouseStyle === opt.key
                                  ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                                  : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                              }`}
                            >
                              {opt.label}
                            </button>
                          ))}
                        </div>
                      </div>
                      
                      {/* 🏡 ТРАДИЦИОННЫЕ */}
                      <div className="mb-4">
                        <div className="text-xs font-semibold text-amber-400 mb-2 uppercase">🏡 Традиционные</div>
                        <div className="grid grid-cols-3 gap-2">
                          {[
                            { key: 'cottage', label: '🏡 Коттедж' },
                            { key: 'villa', label: '🏛️ Вилла' },
                            { key: 'farmhouse', label: '🌾 Ферма' },
                            { key: 'colonial', label: '🏛️ Колониальный' },
                            { key: 'victorian', label: '🏰 Викторианский' },
                            { key: 'mediterranean', label: '🏺 Средиземноморский' },
                          ].map(opt => (
                            <button
                              key={opt.key}
                              type="button"
                              onClick={() => setMode8HouseStyle(opt.key)}
                              className={`py-2.5 rounded-lg text-xs font-medium transition-all ${
                                mode8HouseStyle === opt.key
                                  ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                                  : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                              }`}
                            >
                              {opt.label}
                            </button>
                          ))}
                        </div>
                      </div>
                      
                      {/* 🌲 НАТУРАЛЬНЫЕ */}
                      <div className="mb-4">
                        <div className="text-xs font-semibold text-green-400 mb-2 uppercase">🌲 Натуральные</div>
                        <div className="grid grid-cols-3 gap-2">
                          {[
                            { key: 'cabin', label: '🌲 Домик в лесу' },
                            { key: 'log_house', label: '🪵 Бревенчатый' },
                            { key: 'chalet', label: '🏔️ Шале' },
                            { key: 'adobe', label: '🏜️ Адобе' },
                          ].map(opt => (
                            <button
                              key={opt.key}
                              type="button"
                              onClick={() => setMode8HouseStyle(opt.key)}
                              className={`py-2.5 rounded-lg text-xs font-medium transition-all ${
                                mode8HouseStyle === opt.key
                                  ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                                  : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                              }`}
                            >
                              {opt.label}
                            </button>
                          ))}
                        </div>
                      </div>
                      
                      {/* 🏛️ ЭЛИТНЫЕ */}
                      <div>
                        <div className="text-xs font-semibold text-purple-400 mb-2 uppercase">🏛️ Элитные</div>
                        <div className="grid grid-cols-3 gap-2">
                          {[
                            { key: 'mansion', label: '🏰 Особняк' },
                            { key: 'estate', label: '🌳 Поместье' },
                          ].map(opt => (
                            <button
                              key={opt.key}
                              type="button"
                              onClick={() => setMode8HouseStyle(opt.key)}
                              className={`py-2.5 rounded-lg text-xs font-medium transition-all ${
                                mode8HouseStyle === opt.key
                                  ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                                  : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                              }`}
                            >
                              {opt.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>

                    {/* Location selection */}
                    <div className= "card p-5">
                      <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-3">
                        Локация
                      </label>

                      {/* 🎲 СЛУЧАЙНАЯ */}
                      <div className="mb-4">
                        <button
                          type="button"
                          onClick={() => setMode8Location('random')}
                          className={`w-full py-2.5 rounded-lg text-xs font-medium transition-all ${
                            mode8Location === 'random'
                              ? 'bg-purple-600/20 text-purple-400 border border-purple-600/40'
                              : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                          }`}
                        >
                          🎲 Случайная локация
                        </button>
                      </div>

                      {/* 🏙️ ПРИГОРОДНЫЕ */}
                      <div className="mb-4">
                        <div className="text-xs font-semibold text-blue-400 mb-2 uppercase">🏙️ Пригородные</div>
                        <div className="grid grid-cols-3 gap-2">
                          {[
                            { key: 'suburbs', label: '🏘️ Пригород' },
                            { key: 'urban_edge', label: '🌆 Окраина' },
                            { key: 'planned_community', label: '🏘️ Район' },
                          ].map(opt => (
                            <button
                              key={opt.key}
                              type="button"
                              onClick={() => setMode8Location(opt.key)}
                              className={`py-2.5 rounded-lg text-xs font-medium transition-all ${
                                mode8Location === opt.key
                                  ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                                  : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                              }`}
                            >
                              {opt.label}
                            </button>
                          ))}
                        </div>
                      </div>
                      
                      {/* 🌲 ПРИРОДНЫЕ */}
                      <div className="mb-4">
                        <div className="text-xs font-semibold text-green-400 mb-2 uppercase">🌲 Природные</div>
                        <div className="grid grid-cols-3 gap-2">
                          {[
                            { key: 'forest', label: '🌲 Лес' },
                            { key: 'wooded_area', label: '🌳 Лесная зона' },
                            { key: 'seaside', label: '🌊 Побережье' },
                            { key: 'lakefront', label: '🏞️ Озеро' },
                            { key: 'riverside', label: '🌊 Река' },
                            { key: 'countryside', label: '🌾 Село' },
                            { key: 'farmland', label: '🚜 Поля' },
                            { key: 'vineyard', label: '🍇 Виноградник' },
                            { key: 'mountains', label: '⛰️ Горы' },
                          ].map(opt => (
                            <button
                              key={opt.key}
                              type="button"
                              onClick={() => setMode8Location(opt.key)}
                              className={`py-2.5 rounded-lg text-xs font-medium transition-all ${
                                mode8Location === opt.key
                                  ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                                  : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                              }`}
                            >
                              {opt.label}
                            </button>
                          ))}
                        </div>
                      </div>
                      
                      {/* 🏔️ ЛАНДШАФТНЫЕ */}
                      <div className="mb-4">
                        <div className="text-xs font-semibold text-amber-400 mb-2 uppercase">🏔️ Ландшафтные</div>
                        <div className="grid grid-cols-3 gap-2">
                          {[
                            { key: 'hillside', label: '⛰️ Холм' },
                            { key: 'valley', label: '🏞️ Долина' },
                          ].map(opt => (
                            <button
                              key={opt.key}
                              type="button"
                              onClick={() => setMode8Location(opt.key)}
                              className={`py-2.5 rounded-lg text-xs font-medium transition-all ${
                                mode8Location === opt.key
                                  ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                                  : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                              }`}
                            >
                              {opt.label}
                            </button>
                          ))}
                        </div>
                      </div>
                      
                      {/* 🏜️ ЭКЗОТИЧЕСКИЕ */}
                      <div>
                        <div className="text-xs font-semibold text-orange-400 mb-2 uppercase">🏜️ Экзотические</div>
                        <div className="grid grid-cols-3 gap-2">
                          {[
                            { key: 'desert', label: '🏜️ Пустыня' },
                            { key: 'oasis', label: '🌴 Оазис' },
                            { key: 'tropical', label: '🌴 Тропики' },
                            { key: 'island', label: '🏝️ Остров' },
                          ].map(opt => (
                            <button
                              key={opt.key}
                              type="button"
                              onClick={() => setMode8Location(opt.key)}
                              className={`py-2.5 rounded-lg text-xs font-medium transition-all ${
                                mode8Location === opt.key
                                  ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                                  : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                              }`}
                            >
                              {opt.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>

                    {/* Number of stages */}
                    <div className="card p-5">
                      <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-3">
                        Количество стадий строительства
                      </label>
                      <div className="flex gap-2">
                        {[5, 6, 7, 8].map(n => (
                          <button
                            key={n}
                            type="button"
                            onClick={() => setMode8NumStages(n)}
                            className={`flex-1 py-2.5 rounded-lg text-sm font-medium transition-all ${
                              mode8NumStages === n
                                ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                                : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                            }`}
                          >
                            {n} стадий
                          </button>
                        ))}
                      </div>
                      <p className="text-xs text-[#52525b] mt-3">
                        Каждая стадия — отдельный видеофрагмент: пустой участок → фундамент → стены → крыша → готовый дом.
                      </p>
                    </div>

                    {/* 🏢 Этажность дома */}
                    <div className="card p-5 mt-4">
                      <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-3">
                        Этажность дома
                      </label>
                      <div className="flex gap-2">
                        {[1, 2, 3].map(n => (
                          <button
                            key={n}
                            type="button"
                            onClick={() => setMode8NumFloors(n)}
                            className={`flex-1 py-2.5 rounded-lg text-sm font-medium transition-all ${
                              mode8NumFloors === n
                                ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                                : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                            }`}
                          >
                            {n} этаж{n === 1 ? '' : n === 2 ? 'а' : 'ей'}
                          </button>
                        ))}
                      </div>
                      <p className="text-xs text-[#52525b] mt-3">
                        Сколько этажей будет в доме после завершения строительства.
                      </p>
                    </div>

                {/* Timelapse Info card */}
                <div className="card p-4 bg-gradient-to-br from-amber-900/20 to-orange-900/10 border-amber-700/30">
                  <div className="text-sm font-semibold text-amber-300 mb-2">🏗️ Timelapse Режим</div>
                  <p className="text-xs text-[#a1a1aa]">
                    Видео в стиле ускоренной съёмки строительства. Фотореалистичный стиль, как снято на камеру телефона. Звуки строительной площадки.
                  </p>
                </div>
              </div>
            ) : mode === 9 ? (
              <div className="space-y-4">
                {/* Vehicle Type */}
                <div className="card p-5">
                  <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-3">
                    Тип транспорта
                  </label>

                  {/* 🎲 СЛУЧАЙНЫЙ */}
                  <div className="mb-4">
                    <button
                      type="button"
                      onClick={() => setMode9VehicleType('random')}
                      className={`w-full py-2.5 rounded-lg text-xs font-medium transition-all ${
                        mode9VehicleType === 'random'
                          ? 'bg-purple-600/20 text-purple-400 border border-purple-600/40'
                          : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                      }`}
                    >
                      🎲 Случайный транспорт
                    </button>
                  </div>

                  {/* ✈️ АВИАЦИЯ */}
                  <div className="mb-4">
                    <div className="text-xs font-semibold text-blue-400 mb-2 uppercase">✈️ Авиация</div>
                    <div className="grid grid-cols-3 gap-2">
                      {[
                        { key: 'airplane_passenger', label: '✈️ Пассажирский' },
                        { key: 'airplane_private', label: '🛩️ Частный джет' },
                        { key: 'airplane_fighter', label: '⚔️ Истребитель' },
                        { key: 'airplane_cargo', label: '📦 Грузовой' },
                        { key: 'helicopter', label: '🚁 Вертолёт' },
                        { key: 'drone', label: '🛰️ Дрон' },
                        { key: 'seaplane', label: '🌊 Гидросамолёт' },
                      ].map(opt => (
                        <button
                          key={opt.key}
                          type="button"
                          onClick={() => setMode9VehicleType(opt.key)}
                          className={`py-2.5 rounded-lg text-xs font-medium transition-all ${
                            mode9VehicleType === opt.key
                              ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                              : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                          }`}
                        >
                          {opt.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  
                  {/* 🚗 АВТОМОБИЛИ */}
                  <div className="mb-4">
                    <div className="text-xs font-semibold text-green-400 mb-2 uppercase">🚗 Автомобили</div>
                    <div className="grid grid-cols-3 gap-2">
                      {[
                        { key: 'car_modern', label: '🚗 Современный' },
                        { key: 'car_sport', label: '🏎️ Спорткар' },
                        { key: 'car_suv', label: '🚙 Внедорожник' },
                        { key: 'car_electric', label: '⚡ Электромобиль' },
                        { key: 'truck_cargo', label: '🚚 Грузовик' },
                        { key: 'truck_pickup', label: '🛻 Пикап' },
                        { key: 'bus_city', label: '🚌 Автобус' },
                      ].map(opt => (
                        <button
                          key={opt.key}
                          type="button"
                          onClick={() => setMode9VehicleType(opt.key)}
                          className={`py-2.5 rounded-lg text-xs font-medium transition-all ${
                            mode9VehicleType === opt.key
                              ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                              : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                          }`}
                        >
                          {opt.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  
                  {/* 🚜 СПЕЦТЕХНИКА */}
                  <div className="mb-4">
                    <div className="text-xs font-semibold text-amber-400 mb-2 uppercase">🚜 Спецтехника</div>
                    <div className="grid grid-cols-3 gap-2">
                      {[
                        { key: 'tractor', label: '🚜 Трактор' },
                        { key: 'excavator', label: '🏗️ Экскаватор' },
                        { key: 'bulldozer', label: '🚜 Бульдозер' },
                        { key: 'crane_construction', label: '🏢 Подъёмный кран' },
                        { key: 'concrete_mixer', label: '🚐 Бетономешалка' },
                        { key: 'road_roller', label: '🛣️ Каток' },
                        { key: 'loader', label: '🪣 Погрузчик' },
                      ].map(opt => (
                        <button
                          key={opt.key}
                          type="button"
                          onClick={() => setMode9VehicleType(opt.key)}
                          className={`py-2.5 rounded-lg text-xs font-medium transition-all ${
                            mode9VehicleType === opt.key
                              ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                              : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                          }`}
                        >
                          {opt.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  
                  {/* 🚢 ТРАНСПОРТ */}
                  <div className="mb-4">
                    <div className="text-xs font-semibold text-cyan-400 mb-2 uppercase">🚢 Водный транспорт</div>
                    <div className="grid grid-cols-3 gap-2">
                      {[
                        { key: 'ship_cargo', label: '🚢 Грузовое судно' },
                        { key: 'yacht', label: '⛵ Яхта' },
                        { key: 'fishing_boat', label: '🎣 Рыболовное' },
                        { key: 'submarine', label: '🔍 Подлодка' },
                        { key: 'ferry', label: '⛴️ Паром' },
                      ].map(opt => (
                        <button
                          key={opt.key}
                          type="button"
                          onClick={() => setMode9VehicleType(opt.key)}
                          className={`py-2.5 rounded-lg text-xs font-medium transition-all ${
                            mode9VehicleType === opt.key
                              ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                              : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                          }`}
                        >
                          {opt.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  
                  {/* 💨 ИНДУСТРИЯ */}
                  <div>
                    <div className="text-xs font-semibold text-purple-400 mb-2 uppercase">💨 Индустрия</div>
                    <div className="grid grid-cols-3 gap-2">
                      {[
                        { key: 'wind_turbine', label: '💨 Ветряк' },
                        { key: 'industrial_crane', label: '🏭 Пром. кран' },
                        { key: 'industrial_robot', label: '🤖 Пром. робот' },
                        { key: 'oil_rig', label: '⛽ Буровая' },
                        { key: 'solar_farm', label: '☀️ Солнечная ферма' },
                      ].map(opt => (
                        <button
                          key={opt.key}
                          type="button"
                          onClick={() => setMode9VehicleType(opt.key)}
                          className={`py-2.5 rounded-lg text-xs font-medium transition-all ${
                            mode9VehicleType === opt.key
                              ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                              : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                          }`}
                        >
                          {opt.label}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Location */}
                <div className="card p-5">
                  <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-3">
                    Место сборки
                  </label>

                  {/* 🎲 СЛУЧАЙНОЕ */}
                  <div className="mb-4">
                    <button
                      type="button"
                      onClick={() => setMode9Location('random')}
                      className={`w-full py-2.5 rounded-lg text-xs font-medium transition-all ${
                        mode9Location === 'random'
                          ? 'bg-purple-600/20 text-purple-400 border border-purple-600/40'
                          : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                      }`}
                    >
                      🎲 Случайное место
                    </button>
                  </div>

                  {/* 🏗️ ИНДУСТРИАЛЬНЫЕ */}
                  <div className="mb-4">
                    <div className="text-xs font-semibold text-red-400 mb-2 uppercase">🏗️ Индустриальные</div>
                    <div className="grid grid-cols-3 gap-2">
                      {[
                        { key: 'construction_site', label: '🏗️ Стройка' },
                        { key: 'factory', label: '🏭 Завод' },
                        { key: 'shipyard', label: '🚢 Верфь' },
                        { key: 'hangar', label: '🛩️ Ангар' },
                        { key: 'industrial_zone', label: '⚙️ Инд. зона' },
                      ].map(opt => (
                        <button
                          key={opt.key}
                          type="button"
                          onClick={() => setMode9Location(opt.key)}
                          className={`py-2.5 rounded-lg text-xs font-medium transition-all ${
                            mode9Location === opt.key
                              ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                              : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                          }`}
                        >
                          {opt.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  
                  {/* 🌿 ПРИРОДА */}
                  <div className="mb-4">
                    <div className="text-xs font-semibold text-green-400 mb-2 uppercase">🌿 Природные</div>
                    <div className="grid grid-cols-3 gap-2">
                      {[
                        { key: 'empty_field', label: '🌾 Поле' },
                        { key: 'forest_clearing', label: '🌲 Лесная поляна' },
                        { key: 'desert', label: '🏜️ Пустыня' },
                        { key: 'mountain_valley', label: '🏔️ Горная долина' },
                        { key: 'snowy_plain', label: '❄️ Снежная равнина' },
                      ].map(opt => (
                        <button
                          key={opt.key}
                          type="button"
                          onClick={() => setMode9Location(opt.key)}
                          className={`py-2.5 rounded-lg text-xs font-medium transition-all ${
                            mode9Location === opt.key
                              ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                              : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                          }`}
                        >
                          {opt.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  
                  {/* 🌆 УРБАН */}
                  <div className="mb-4">
                    <div className="text-xs font-semibold text-blue-400 mb-2 uppercase">🌆 Урбан</div>
                    <div className="grid grid-cols-3 gap-2">
                      {[
                        { key: 'city_outskirts', label: '🌆 Окраина' },
                        { key: 'parking_lot', label: '🅿️ Парковка' },
                        { key: 'abandoned_industrial', label: '🏚️ Заброшенный' },
                        { key: 'building_roof', label: '🏢 Крыша' },
                      ].map(opt => (
                        <button
                          key={opt.key}
                          type="button"
                          onClick={() => setMode9Location(opt.key)}
                          className={`py-2.5 rounded-lg text-xs font-medium transition-all ${
                            mode9Location === opt.key
                              ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                              : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                          }`}
                        >
                          {opt.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  
                  {/* 🌊 УНИКАЛЬНЫЕ */}
                  <div>
                    <div className="text-xs font-semibold text-cyan-400 mb-2 uppercase">🌊 Уникальные</div>
                    <div className="grid grid-cols-3 gap-2">
                      {[
                        { key: 'ocean_coast', label: '🌊 Побережье' },
                        { key: 'floating_platform', label: '🛟 Платформа' },
                        { key: 'island', label: '🏝️ Остров' },
                        { key: 'quarry', label: '⛏️ Карьер' },
                        { key: 'port', label: '⚓ Порт' },
                      ].map(opt => (
                        <button
                          key={opt.key}
                          type="button"
                          onClick={() => setMode9Location(opt.key)}
                          className={`py-2.5 rounded-lg text-xs font-medium transition-all ${
                            mode9Location === opt.key
                              ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                              : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                          }`}
                        >
                          {opt.label}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Number of Stages */}
                <div className="card p-5">
                  <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-3">
                    Количество этапов: {mode9NumStages}
                  </label>
                  <input
                    type="range"
                    min="5"
                    max="7"
                    step="1"
                    value={mode9NumStages}
                    onChange={e => setMode9NumStages(parseInt(e.target.value))}
                    className="w-full accent-brand-500"
                  />
                  <div className="flex justify-between text-xs text-[#52525b] mt-1">
                    <span>5</span>
                    <span>6</span>
                    <span>7</span>
                  </div>
                  <p className="text-xs text-[#52525b] mt-2">
                    Больше этапов = более детальная сборка
                  </p>
                </div>

                {/* Assembly Info card */}
                <div className="card p-4 bg-gradient-to-br from-blue-900/20 to-cyan-900/10 border-blue-700/30">
                  <div className="text-sm font-semibold text-blue-300 mb-2">🚗 Assembly Режим</div>
                  <p className="text-xs text-[#a1a1aa]">
                    Видео в стиле ускоренной съёмки сборки транспорта. Фотореалистичный стиль, как снято на камеру телефона. Звуки производства и механических работ.
                  </p>
                </div>
              </div>
            ) : mode === 10 ? (
              <div className="space-y-4">
                <div className="card p-5">
                  <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-3">
                    Тип пляжа
                  </label>
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      { key: 'random', label: '🎲 Случайный' },
                      { key: 'tropical', label: '🌴 Тропики' },
                      { key: 'urban', label: '🏙️ Городской' },
                      { key: 'rocky_cove', label: '🪨 Бухта' },
                      { key: 'resort', label: '🏖️ Курорт' },
                      { key: 'wild', label: '🌾 Дикий' },
                    ].map(opt => (
                      <button
                        key={opt.key}
                        type="button"
                        onClick={() => setMode10BeachType(opt.key)}
                        className={`py-2.5 rounded-lg text-xs font-medium transition-all ${
                          mode10BeachType === opt.key
                            ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                            : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="card p-5">
                  <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-3">
                    Свет и погода у берега
                  </label>
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      { key: 'random', label: '🎲 Случайно' },
                      { key: 'morning_calm', label: '🌅 Утро' },
                      { key: 'midday_bright', label: '☀️ Полдень' },
                      { key: 'golden_hour', label: '🌇 Золотой час' },
                      { key: 'overcast_soft', label: '☁️ Пасмурно' },
                      { key: 'breezy', label: '💨 Ветер' },
                    ].map(opt => (
                      <button
                        key={opt.key}
                        type="button"
                        onClick={() => setMode10CoastSetting(opt.key)}
                        className={`py-2.5 rounded-lg text-xs font-medium transition-all ${
                          mode10CoastSetting === opt.key
                            ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                            : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="card p-5">
                  <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-3">
                    Количество стадий уборки
                  </label>
                  <div className="flex gap-2">
                    {[5, 6, 7, 8].map(n => (
                      <button
                        key={n}
                        type="button"
                        onClick={() => setMode10NumStages(n)}
                        className={`flex-1 py-2.5 rounded-lg text-sm font-medium transition-all ${
                          mode10NumStages === n
                            ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                            : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                        }`}
                      >
                        {n} стадий
                      </button>
                    ))}
                  </div>
                  <p className="text-xs text-[#52525b] mt-3">
                    Каждая стадия — отдельный фрагмент: мусор → сбор → просев/грабли → вывоз → чистый пляж (по выбранному числу шагов).
                  </p>
                </div>

                <div className="card p-4 bg-gradient-to-br from-cyan-900/20 to-teal-900/10 border-cyan-700/30">
                  <div className="text-sm font-semibold text-cyan-300 mb-2">🏖️ Уборка пляжа</div>
                  <p className="text-xs text-[#a1a1aa]">
                    Timelapse в духе съёмки на телефон: волонтёры, мешки, грабли, иногда техника. Звук и музыка в спокойном морском ключе.
                  </p>
                </div>
              </div>
            ) : mode === 11 ? (
              <div className="space-y-4">
                <div className="card p-5">
                  <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-3">
                    Выбор постройки
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    {MODE11_STRUCTURES.map(opt => (
                      <button
                        key={opt.key}
                        type="button"
                        onClick={() => setMode11StructureType(opt.key)}
                        className={`py-2.5 rounded-lg text-xs font-medium transition-all ${
                          mode11StructureType === opt.key
                            ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                            : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="card p-5">
                  <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-3">
                    Число сцен
                  </label>
                  <div className="flex gap-2">
                    {[5, 7].map(n => (
                      <button
                        key={n}
                        type="button"
                        onClick={() => setMode11NumStages(n)}
                        className={`flex-1 py-2.5 rounded-lg text-sm font-medium transition-all ${
                          mode11NumStages === n
                            ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                            : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                        }`}
                      >
                        {n === 5 ? 'Быстро (5 сцен)' : 'Детально (7 сцен)'}
                      </button>
                    ))}
                  </div>
                  <p className="text-xs text-[#52525b] mt-3">
                    5 сцен — меньше клипов и быстрее. 7 сцен — полная шкала от целого монумента до площадки.
                  </p>
                </div>

                <div className="card p-4 bg-gradient-to-br from-amber-900/20 to-yellow-900/10 border-amber-700/30">
                  <div className="text-sm font-semibold text-amber-300 mb-2">🏛️ Выбор постройки → генерировать</div>
                  <p className="text-xs text-[#a1a1aa]">
                    Выберите один объект и запускайте генерацию. Локация и ракурс фиксированы на всех кадрах.
                  </p>
                </div>
              </div>
            ) : mode === 13 ? (
              <div className="space-y-4">
                <div className="card p-5">
                  <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-3">
                    Аудио (обязательно)
                  </label>
                  <p className="text-xs text-[#a1a1aa] mb-3">
                    MP3, WAV, M4A и др. До ~200 МБ. После загрузки файл сразу приводится к моно 48 kHz WAV (как в пайплайне). В режиме «Как в файле»
                    дальше без фильтров; в остальных — обработка тембра/темпа. Дорожка режется на части ~5 мин, слайды по ~30 с.
                  </p>
                  <div className="flex items-center gap-2 flex-wrap">
                    <label className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[#1a1a24] border border-[#27272f] hover:border-brand-600/40 cursor-pointer text-sm text-[#e4e4f0]">
                      <RiImageAddLine className="text-lg opacity-70" />
                      {uploadingMode13Audio ? 'Загрузка…' : mode13Audio ? 'Заменить файл' : 'Выбрать аудио'}
                      <input
                        type="file"
                        accept="audio/*,.mp3,.wav,.m4a,.aac,.ogg,.webm,.flac"
                        className="hidden"
                        onChange={async (e) => {
                          const f = e.target.files?.[0];
                          if (!f) return;
                          setUploadingMode13Audio(true);
                          try {
                            const { path } = await api.uploadAudio(f);
                            setMode13Audio({ path, name: f.name });
                          } catch (err) {
                            setError(err.message);
                          } finally {
                            setUploadingMode13Audio(false);
                            e.target.value = '';
                          }
                        }}
                      />
                    </label>
                    {mode13Audio ? (
                      <button
                        type="button"
                        onClick={() => {
                          setMode13PreviewBlobUrl((prev) => {
                            if (prev) URL.revokeObjectURL(prev);
                            return null;
                          });
                          setMode13PreviewError('');
                          setMode13Audio(null);
                        }}
                        className="p-2 rounded-lg text-[#71717a] hover:text-red-400"
                      >
                        <RiCloseLine />
                      </button>
                    ) : null}
                  </div>
                  {mode13Audio?.name ? (
                    <p className="mt-2 text-xs text-[#71717a] truncate" title={mode13Audio.name}>
                      {mode13Audio.name}
                    </p>
                  ) : null}
                </div>
                {mode13Audio?.path ? (
                  <div className="card p-5 space-y-4">
                    <div className="text-xs font-semibold text-[#71717a] uppercase tracking-wider">
                      Прослушивание
                    </div>
                    <audio
                      ref={mode13AudioRef}
                      src={mode13PreviewBlobUrl || mode13MonoServeUrl || undefined}
                      controls
                      className="w-full rounded-lg"
                    />
                    {mode13PreviewBusy ? (
                      <p className="text-xs text-[#a78bfa]">Обновление превью с обработкой…</p>
                    ) : null}
                    {mode13PreviewError ? (
                      <p className="text-xs text-amber-500/90">
                        {mode13PreviewError} — ниже можно слушать моно без фильтров.
                      </p>
                    ) : (
                      <p className="text-xs text-[#52525b]">
                        Превью (~45 с) совпадает с цепочкой при генерации; ползунки применяются через доли секунды.
                      </p>
                    )}
                    <div className="space-y-4 text-sm">
                      <p className="text-[11px] text-[#71717a] uppercase tracking-wider">Очистка и полировка голоса (ffmpeg)</p>
                      <label className="block">
                        <span className="text-[#a1a1aa] text-xs">AI cleanup / speech enhance: {mode13AiCleanup}%</span>
                        <span className="block text-[10px] text-[#52525b] mt-0.5">arnndn: умнее обычного шумодава, лучше для плохих записей. Для работы нужна `.rnnn` модель.</span>
                        <input
                          type="range"
                          min={0}
                          max={100}
                          step={1}
                          value={mode13AiCleanup}
                          onChange={(e) => setMode13AiCleanup(Number(e.target.value))}
                          className="w-full mt-1 accent-brand-500"
                        />
                      </label>
                      <label className="block">
                        <span className="text-[#a1a1aa] text-xs">Убирание шумов: {mode13NoiseSupp}%</span>
                        <span className="block text-[10px] text-[#52525b] mt-0.5">0 — почти без afftdn; 100 — сильнее (риск артефактов)</span>
                        <input
                          type="range"
                          min={0}
                          max={100}
                          step={1}
                          value={mode13NoiseSupp}
                          onChange={(e) => setMode13NoiseSupp(Number(e.target.value))}
                          className="w-full mt-1 accent-brand-500"
                        />
                      </label>
                      <label className="block">
                        <span className="text-[#a1a1aa] text-xs">Выравнивание громкости: {mode13LevelNorm}%</span>
                        <span className="block text-[10px] text-[#52525b] mt-0.5">loudnorm (EBU R128): ниже — мягче и тише; выше — плотнее и ближе к voice-over</span>
                        <input
                          type="range"
                          min={0}
                          max={100}
                          step={1}
                          value={mode13LevelNorm}
                          onChange={(e) => setMode13LevelNorm(Number(e.target.value))}
                          className="w-full mt-1 accent-brand-500"
                        />
                      </label>
                      <label className="block">
                        <span className="text-[#a1a1aa] text-xs">Де-эссер / шипящие: {mode13Deesser}%</span>
                        <span className="block text-[10px] text-[#52525b] mt-0.5">Прибирает резкие “с”, “ш”, “щ” в верхней середине</span>
                        <input
                          type="range"
                          min={0}
                          max={100}
                          step={1}
                          value={mode13Deesser}
                          onChange={(e) => setMode13Deesser(Number(e.target.value))}
                          className="w-full mt-1 accent-brand-500"
                        />
                      </label>
                      <label className="block">
                        <span className="text-[#a1a1aa] text-xs">Ясность / presence: {mode13Clarity}%</span>
                        <span className="block text-[10px] text-[#52525b] mt-0.5">Добавляет разборчивость и “выход вперёд” в миксе</span>
                        <input
                          type="range"
                          min={0}
                          max={100}
                          step={1}
                          value={mode13Clarity}
                          onChange={(e) => setMode13Clarity(Number(e.target.value))}
                          className="w-full mt-1 accent-brand-500"
                        />
                      </label>
                      <label className="block">
                        <span className="text-[#a1a1aa] text-xs">Уборка мути / low-mid cut: {mode13MudCut}%</span>
                        <span className="block text-[10px] text-[#52525b] mt-0.5">Подрезает область около 200–300 Гц, если голос “бубнит”</span>
                        <input
                          type="range"
                          min={0}
                          max={100}
                          step={1}
                          value={mode13MudCut}
                          onChange={(e) => setMode13MudCut(Number(e.target.value))}
                          className="w-full mt-1 accent-brand-500"
                        />
                      </label>
                      <label className="block">
                        <span className="text-[#a1a1aa] text-xs">Компрессия / плотность: {mode13Compression}%</span>
                        <span className="block text-[10px] text-[#52525b] mt-0.5">Делает голос ровнее и “радиоформатнее”, но перебор сушит динамику</span>
                        <input
                          type="range"
                          min={0}
                          max={100}
                          step={1}
                          value={mode13Compression}
                          onChange={(e) => setMode13Compression(Number(e.target.value))}
                          className="w-full mt-1 accent-brand-500"
                        />
                      </label>
                      <div className="flex flex-col gap-2">
                        <label className="flex items-center gap-2 text-xs text-[#a1a1aa] cursor-pointer">
                          <input
                            type="checkbox"
                            checked={mode13HpAuto}
                            onChange={(e) => setMode13HpAuto(e.target.checked)}
                            className="rounded border-[#3f3f46]"
                          />
                          Срез низа (highpass) как в пресете
                        </label>
                        {!mode13HpAuto ? (
                          <label className="block">
                            <span className="text-[#a1a1aa] text-xs">Частота среза: {mode13HighpassHz} Гц</span>
                            <input
                              type="range"
                              min={40}
                              max={120}
                              step={5}
                              value={mode13HighpassHz}
                              onChange={(e) => setMode13HighpassHz(Number(e.target.value))}
                              className="w-full mt-1 accent-brand-500"
                            />
                          </label>
                        ) : null}
                      </div>
                      {mode13VoicePreset === 'original' ? (
                        <p className="text-[10px] text-[#71717a]">
                          Для пресета `original` все эти обработки обходятся: остаётся только конвертация в mono WAV и ручной gain.
                        </p>
                      ) : null}
                      <p className="text-[11px] text-[#71717a] uppercase tracking-wider pt-1">Плеер и цепочка</p>
                      <label className="block">
                        <span className="text-[#a1a1aa] text-xs">Громкость плеера (сразу)</span>
                        <input
                          type="range"
                          min={0}
                          max={100}
                          value={Math.round(mode13ListenVol * 100)}
                          onChange={(e) => setMode13ListenVol(Number(e.target.value) / 100)}
                          className="w-full mt-1 accent-brand-500"
                        />
                      </label>
                      <label className="block">
                        <span className="text-[#a1a1aa] text-xs">
                          Усиление в цепочке: {mode13GainDb >= 0 ? '+' : ''}
                          {mode13GainDb.toFixed(1)} dB
                        </span>
                        <input
                          type="range"
                          min={-12}
                          max={12}
                          step={0.5}
                          value={mode13GainDb}
                          onChange={(e) => setMode13GainDb(Number(e.target.value))}
                          className="w-full mt-1 accent-brand-500"
                        />
                      </label>
                      <label className="block">
                        <span className="text-[#a1a1aa] text-xs">Темп относительно пресета: {mode13TempoPct}%</span>
                        <input
                          type="range"
                          min={85}
                          max={115}
                          step={1}
                          value={mode13TempoPct}
                          onChange={(e) => setMode13TempoPct(Number(e.target.value))}
                          className="w-full mt-1 accent-brand-500"
                        />
                      </label>
                      <label className="block">
                        <span className="text-[#a1a1aa] text-xs">
                          Тон (полутона): {mode13PitchSemi >= 0 ? '+' : ''}
                          {mode13PitchSemi.toFixed(1)}
                        </span>
                        <input
                          type="range"
                          min={-6}
                          max={6}
                          step={0.5}
                          value={mode13PitchSemi}
                          onChange={(e) => setMode13PitchSemi(Number(e.target.value))}
                          className="w-full mt-1 accent-brand-500"
                        />
                      </label>
                    </div>
                  </div>
                ) : null}
                <div className="card p-5">
                  <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-3">
                    Тембр / темп
                  </label>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                    {[
                      {
                        id: 'original',
                        title: 'Как в файле',
                        sub: 'Без фильтров — только моно 48 kHz для нарезки и Whisper',
                      },
                      {
                        id: 'studio',
                        title: 'Студийный',
                        sub: 'Чистый ровный голос: мягкий шумодав, без смены тембра (по умолчанию)',
                      },
                      {
                        id: 'calm',
                        title: 'Спокойный',
                        sub: 'Чуть медленнее + лёгкая обработка (раньше «как по умолчанию»)',
                      },
                      {
                        id: 'natural',
                        title: 'Как в записи + НЧ',
                        sub: 'Без шумодава, только срез низа и ровный уровень',
                      },
                      { id: 'soft', title: 'Мягко', sub: 'Чуть другой тембр' },
                      { id: 'medium', title: 'Средне', sub: 'Заметно иначе' },
                      { id: 'strong', title: 'Сильно', sub: 'Сильнее эффект (риск артефактов)' },
                    ].map((opt) => (
                      <button
                        key={opt.id}
                        type="button"
                        onClick={() => setMode13VoicePreset(opt.id)}
                        className={`text-left px-4 py-3 rounded-xl border transition-all ${
                          mode13VoicePreset === opt.id
                            ? 'border-brand-500 bg-brand-600/15 ring-1 ring-brand-500/40'
                            : 'border-[#27272f] bg-[#14141c] hover:border-[#3f3f46]'
                        }`}
                      >
                        <div className="text-sm font-semibold text-[#e4e4f0]">{opt.title}</div>
                        <div className="text-[10px] text-[#71717a] mt-1">{opt.sub}</div>
                      </button>
                    ))}
                  </div>
                </div>
                <div className="card p-5">
                  <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-3">
                    Язык речи (подсказка Whisper)
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {[
                      { id: '', title: 'Авто' },
                      { id: 'ru', title: 'Русский' },
                      { id: 'en', title: 'English' },
                    ].map((opt) => (
                      <button
                        key={opt.id || 'auto'}
                        type="button"
                        onClick={() => setMode13WhisperLang(opt.id)}
                        className={`px-3 py-2 rounded-lg text-sm border transition-all ${
                          mode13WhisperLang === opt.id
                            ? 'border-brand-500 bg-brand-600/15 text-white'
                            : 'border-[#27272f] text-[#a1a1aa] hover:border-[#3f3f46]'
                        }`}
                      >
                        {opt.title}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="card p-5">
                  <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-2">
                    Заголовок сверху <span className="font-normal normal-case">(как в режиме цитат, необязательно)</span>
                  </label>
                  <input
                    className="input text-base"
                    placeholder="Текст по центру вверху на всех слайдах"
                    value={mode13HeaderTitle}
                    onChange={(e) => setMode13HeaderTitle(e.target.value)}
                  />
                </div>
                <div className="card p-5 flex items-center justify-between">
                  <div>
                    <div className="text-sm font-medium text-[#e4e4f0]">Субтитры</div>
                    <div className="text-xs text-[#71717a] mt-0.5">
                      Показывать на слайде текст сегмента (как распознал Whisper).
                    </div>
                  </div>
                  <Toggle value={mode13ShowSubtitles} onChange={setMode13ShowSubtitles} />
                </div>
                <div className="card p-4 bg-gradient-to-br from-cyan-900/20 to-slate-900/10 border-cyan-700/30">
                  <div className="text-sm font-semibold text-cyan-300 mb-2">🎙️ Режим аудио</div>
                  <p className="text-xs text-[#a1a1aa]">
                    После генерации проверьте каждую ~5-минутную часть. Кнопки «Слайд N» перегенерируют отдельный 30-с кадр.
                    Затем нажмите финальный монтаж — все части склеятся в один MP4.
                  </p>
                </div>
              </div>
            ) : mode === 4 ? (
              <div className="space-y-4">
                <div className="card p-5">
                  <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-3">
                    Имя личности <span className="font-normal normal-case text-[#71717a]">(необязательно)</span>
                  </label>
                  <p className="text-xs text-[#a1a1aa] mb-2">
                    Для истории и описания на YouTube; на кадре можно скрыть галочкой ниже.
                  </p>
                  <datalist id="mode4-person-name-datalist">
                    {mode4PersonNameSuggestions.map((n) => (
                      <option key={n} value={n} />
                    ))}
                  </datalist>
                  <input
                    className="input text-base"
                    list="mode4-person-name-datalist"
                    autoComplete="off"
                    placeholder="Например: Фёдор Достоевский"
                    value={mode4PersonName}
                    onChange={e => setMode4PersonName(e.target.value)}
                  />
                  {mode4PersonNameSuggestions.length > 0 ? (
                    <div className="mt-2.5">
                      <p className="text-[10px] font-medium text-[#52525b] uppercase tracking-wide mb-1.5">
                        Чаще всего указываете
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {mode4PersonNameSuggestions.map((n) => (
                          <button
                            key={n}
                            type="button"
                            onClick={() => setMode4PersonName(n)}
                            className="px-2.5 py-1 rounded-lg text-xs border border-[#27272f] text-[#a1a1aa] hover:text-white hover:border-brand-500/50 hover:bg-brand-600/10 transition-colors max-w-full truncate"
                            title={n}
                          >
                            {n}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
                <div className="card p-5">
                  <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-3">
                    Локация для сцены
                  </label>
                  <p className="text-xs text-[#a1a1aa] mb-3">
                    После ввода имени LLM подбирает подходящие варианты под персонажа и эпоху. Выберите, что ближе по настроению.
                  </p>
                  {mode4PersonName.trim().length < 2 ? (
                    <p className="text-xs text-[#71717a]">Введите имя личности, чтобы получить варианты локаций.</p>
                  ) : mode4LocationLoading ? (
                    <p className="text-xs text-[#a1a1aa]">Подбираю варианты локаций…</p>
                  ) : mode4LocationOptions.length > 0 ? (
                    <div className="grid grid-cols-1 gap-2">
                      {mode4LocationOptions.map((opt) => (
                        <button
                          key={opt}
                          type="button"
                          onClick={() => setMode4LocationHint(opt)}
                          className={`text-left px-3 py-2 rounded-lg border text-sm transition-all ${
                            mode4LocationHint === opt
                              ? 'border-brand-500 bg-brand-600/15 ring-1 ring-brand-500/40 text-[#f4f4f5]'
                              : 'border-[#27272f] bg-[#14141c] text-[#d4d4d8] hover:border-[#3f3f46]'
                          }`}
                        >
                          {opt}
                        </button>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-amber-300">Не удалось получить варианты. Можно запускать, тогда сервер выберет сам.</p>
                  )}
                </div>
                <div className="card p-5">
                  <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-3">
                    Цитата
                  </label>
                  <p className="text-xs text-brand-400/80 mb-2">
                    Цитату и имя вводите на русском; для английского ролика агент переведёт текст.
                  </p>
                  <p className="text-xs text-[#a1a1aa] mb-2 leading-relaxed">
                    <span className="text-emerald-400/90 font-medium">Несколько фрагментов:</span> между абзацами вставьте
                    пустую строку (Enter дважды). Режим нескольких клипов включится сам, язык — только RU или EN.
                  </p>
                  <textarea
                    className="input text-base min-h-[100px] resize-y"
                    placeholder={`Первый абзац цитаты.\n\nВторой абзац — отдельный ролик.\n\nТретий…`}
                    value={mode4Quote}
                    onChange={(e) => setMode4Quote(e.target.value)}
                  />
                  {mode4QuoteBlocks.length >= 2 ? (
                    <p className="mt-2 text-xs text-emerald-400/90">
                      Будет {mode4QuoteBlocks.length} видеофрагментов (разделитель — пустая строка в этом поле).
                    </p>
                  ) : null}
                </div>
                <div className="card p-5">
                  <div className="text-sm font-semibold text-[#e4e4f0] mb-1">Фото личности</div>
                  <div className="text-xs text-[#71717a] mb-3">Агент проанализирует фото и напишет промпт в стиле личности</div>
                  <div className="flex items-center gap-2">
                    <label className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[#1a1a24] border border-[#27272f] hover:border-brand-600/40 cursor-pointer text-sm text-[#e4e4f0] transition-colors">
                      <RiImageAddLine className="text-lg" />
                      {uploadingRef ? 'Загрузка…' : (mode4Photo ? 'Заменить' : 'Выбрать фото')}
                      <input type="file" accept="image/jpeg,image/png,image/webp" className="hidden"
                        onChange={async (e) => {
                          const f = e.target.files?.[0];
                          if (!f) return;
                          setUploadingRef(true);
                          try {
                            const { path } = await api.uploadImage(f);
                            setMode4Photo({ path, preview: URL.createObjectURL(f) });
                          } catch (err) { setError(err.message); }
                          finally { setUploadingRef(false); e.target.value = ''; }
                        }} />
                    </label>
                    {mode4Photo && (
                      <button type="button" onClick={() => setMode4Photo(null)}
                        className="p-2 rounded-lg text-[#71717a] hover:text-red-400 hover:bg-red-900/20">
                        <RiCloseLine />
                      </button>
                    )}
                  </div>
                  {mode4Photo?.preview && (
                    <img src={mode4Photo.preview} alt="Личность" className="mt-2 w-40 h-28 object-cover rounded-lg border border-[#27272f]" />
                  )}
                  {mode4Photo?.path && !mode4Photo?.preview ? (
                    <p className="mt-2 text-xs text-amber-400/90">
                      Файл на сервере из прошлого запуска. При необходимости замените фото.
                    </p>
                  ) : null}
                </div>
                <div className="card p-5">
                  <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-3">
                    Какую версию сгенерировать
                  </label>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    {[
                      { id: 'both', title: 'Оба сразу', sub: 'video_ru + video_en' },
                      { id: 'ru', title: 'Только русская', sub: 'Озвучка и титры на русском' },
                      { id: 'en', title: 'Только английская', sub: 'Перевод цитаты и озвучка EN' },
                    ].map((opt) => (
                      <button
                        key={opt.id}
                        type="button"
                        disabled={mode4Multiclip && opt.id === 'both'}
                        onClick={() => !mode4Multiclip || opt.id !== 'both' ? setMode4OutputLang(opt.id) : null}
                        className={`text-left px-4 py-3 rounded-xl border transition-all ${
                          mode4OutputLang === opt.id
                            ? 'border-brand-500 bg-brand-600/15 ring-1 ring-brand-500/40'
                            : 'border-[#27272f] bg-[#14141c] hover:border-[#3f3f46]'
                        } ${mode4Multiclip && opt.id === 'both' ? 'opacity-40 cursor-not-allowed' : ''}`}
                      >
                        <div className="text-sm font-semibold text-[#e4e4f0]">{opt.title}</div>
                        <div className="text-[10px] text-[#71717a] mt-1 leading-snug">
                          {mode4Multiclip && opt.id === 'both' ? 'Недоступно при нескольких фрагментах' : opt.sub}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
                <div className="card p-5">
                  {mode4Multiclip ? (
                    <p className="text-xs text-emerald-400/90 leading-relaxed">
                      Обнаружено несколько абзацев в «Цитате» — будет {mode4QuoteBlocks.length} отдельных фрагментов.
                      Чтобы сделать один ролик, оставьте текст одним абзацем.
                    </p>
                  ) : (
                    <p className="text-xs text-[#a1a1aa] leading-relaxed">
                      Сейчас будет один ролик. Для нескольких фрагментов разделяйте абзацы пустой строкой в поле «Цитата».
                    </p>
                  )}
                </div>
                <div className="card p-5 space-y-4">
                  <label className="flex items-start gap-2 text-sm cursor-pointer select-none">
                    <input
                      type="checkbox"
                      className="mt-0.5 rounded border-[#3f3f46] bg-[#1a1a24] text-brand-600 focus:ring-brand-500"
                      checked={mode4ShowAuthorOnVideo}
                      onChange={(e) => setMode4ShowAuthorOnVideo(e.target.checked)}
                    />
                    <span className="text-[#d4d4d8] leading-snug">
                      Показывать автора на видео («…» – Автор внизу кадра)
                    </span>
                  </label>
                  <div>
                    <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-2">
                      Заголовок сверху <span className="font-normal normal-case">(необязательно)</span>
                    </label>
                    <input
                      className="input text-base"
                      placeholder="Текст по центру вверху на всём ролике"
                      value={mode4HeaderTitle}
                      onChange={(e) => setMode4HeaderTitle(e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-2">
                      Стиль субтитров
                    </label>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {[
                        {
                          id: 'karaoke',
                          title: 'Караоке',
                          sub: 'Крупные слова, мало на строку, золотая подсветка в такт речи (рекомендуется)',
                        },
                        {
                          id: 'plain_whisper',
                          title: 'Плоский Whisper',
                          sub: 'Белый текст блоками; меньше «киношности», чем караоке',
                        },
                      ].map((opt) => (
                        <button
                          key={opt.id}
                          type="button"
                          onClick={() => setMode4SubtitleStyle(opt.id)}
                          className={`text-left px-4 py-3 rounded-xl border transition-all ${
                            mode4SubtitleStyle === opt.id
                              ? 'border-brand-500 bg-brand-600/15 ring-1 ring-brand-500/40'
                              : 'border-[#27272f] bg-[#14141c] hover:border-[#3f3f46]'
                          }`}
                        >
                          <div className="text-sm font-semibold text-[#e4e4f0]">{opt.title}</div>
                          <div className="text-[10px] text-[#71717a] mt-1 leading-snug">
                            {opt.sub}
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            ) : mode === 3 ? (
              <div className="space-y-4">
                {/* Переключатель: описать / загрузить */}
                <div className="flex rounded-xl overflow-hidden border border-[#27272f] p-1 bg-[#1a1a24]">
                  <button
                    type="button"
                    onClick={() => setMode3InputMode('type')}
                    className={`flex-1 px-4 py-2.5 text-sm font-medium rounded-lg transition-all ${mode3InputMode === 'type' ? 'bg-brand-600 text-white' : 'text-[#71717a] hover:text-[#e4e4f0]'}`}
                  >
                    Выбрать тип дома
                  </button>
                  <button
                    type="button"
                    onClick={() => setMode3InputMode('upload')}
                    className={`flex-1 px-4 py-2.5 text-sm font-medium rounded-lg transition-all ${mode3InputMode === 'upload' ? 'bg-brand-600 text-white' : 'text-[#71717a] hover:text-[#e4e4f0]'}`}
                  >
                    Загрузить фото
                  </button>
                </div>

                {mode3InputMode === 'type' ? (
                  <div className="card p-5">
                    <div className="text-sm font-semibold text-[#e4e4f0] mb-1">Тип дома</div>
                    <div className="text-xs text-[#71717a] mb-3">Агент сам напишет максимально детальные промпты для фотореалистичной генерации</div>
                    <select
                      className="input text-base w-full cursor-pointer"
                      value={mode3HouseType}
                      onChange={e => setMode3HouseType(e.target.value)}
                    >
                      <option value="">— Выберите тип дома —</option>
                      {HOUSE_TYPES.map(h => (
                        <option key={h.id} value={h.id}>{h.label}</option>
                      ))}
                    </select>
                  </div>
                ) : (
                  <>
                    <div className="card p-5">
                      <div className="text-sm font-semibold text-[#e4e4f0] mb-1">Дом ДО реставрации</div>
                      <div className="text-xs text-[#71717a] mb-3">Запущенный, старый вид</div>
                      <div className="flex items-center gap-2">
                        <label className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[#1a1a24] border border-[#27272f] hover:border-brand-600/40 cursor-pointer text-sm text-[#e4e4f0] transition-colors">
                          <RiImageAddLine className="text-lg" />
                          {uploadingRef ? 'Загрузка…' : (mode3StartImage ? 'Заменить' : 'Выбрать фото')}
                          <input type="file" accept="image/jpeg,image/png,image/webp" className="hidden"
                            onChange={async (e) => {
                              const f = e.target.files?.[0];
                              if (!f) return;
                              setUploadingRef(true);
                              try {
                                const { path } = await api.uploadImage(f);
                                setMode3StartImage({ path, preview: URL.createObjectURL(f) });
                              } catch (err) { setError(err.message); }
                              finally { setUploadingRef(false); e.target.value = ''; }
                            }} />
                        </label>
                        {mode3StartImage && (
                          <button type="button" onClick={() => setMode3StartImage(null)}
                            className="p-2 rounded-lg text-[#71717a] hover:text-red-400 hover:bg-red-900/20">
                            <RiCloseLine />
                          </button>
                        )}
                      </div>
                      {mode3StartImage?.preview && (
                        <img src={mode3StartImage.preview} alt="До" className="mt-2 w-40 h-28 object-cover rounded-lg border border-[#27272f]" />
                      )}
                      {mode3StartImage?.path && !mode3StartImage?.preview ? (
                        <p className="mt-2 text-xs text-amber-400/90">Файл на сервере из прошлого запуска. При необходимости замените.</p>
                      ) : null}
                    </div>
                    <div className="card p-5">
                      <div className="text-sm font-semibold text-[#e4e4f0] mb-1">Дом ПОСЛЕ реставрации</div>
                      <div className="text-xs text-[#71717a] mb-3">Целевой вид, к которому стремимся</div>
                      <div className="flex items-center gap-2">
                        <label className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[#1a1a24] border border-[#27272f] hover:border-brand-600/40 cursor-pointer text-sm text-[#e4e4f0] transition-colors">
                          <RiImageAddLine className="text-lg" />
                          {uploadingRef ? 'Загрузка…' : (mode3EndImage ? 'Заменить' : 'Выбрать фото')}
                          <input type="file" accept="image/jpeg,image/png,image/webp" className="hidden"
                            onChange={async (e) => {
                              const f = e.target.files?.[0];
                              if (!f) return;
                              setUploadingRef(true);
                              try {
                                const { path } = await api.uploadImage(f);
                                setMode3EndImage({ path, preview: URL.createObjectURL(f) });
                              } catch (err) { setError(err.message); }
                              finally { setUploadingRef(false); e.target.value = ''; }
                            }} />
                        </label>
                        {mode3EndImage && (
                          <button type="button" onClick={() => setMode3EndImage(null)}
                            className="p-2 rounded-lg text-[#71717a] hover:text-red-400 hover:bg-red-900/20">
                            <RiCloseLine />
                          </button>
                        )}
                      </div>
                      {mode3EndImage?.preview && (
                        <img src={mode3EndImage.preview} alt="После" className="mt-2 w-40 h-28 object-cover rounded-lg border border-[#27272f]" />
                      )}
                      {mode3EndImage?.path && !mode3EndImage?.preview ? (
                        <p className="mt-2 text-xs text-amber-400/90">Файл на сервере из прошлого запуска. При необходимости замените.</p>
                      ) : null}
                    </div>
                  </>
                )}
              </div>
            ) : (
            /* Topic card — Mode 1 и 2 */
            <div className="card p-5">
              <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-3">
                Тема видео
              </label>
              <input
                className="input text-base"
                placeholder={mode === 1 ? 'Например: Топ-5 фактов о Марсе' : 'Например: животные, военная история, сон'}
                value={topic}
                onChange={e => setTopic(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleGenerateScenario()}
                autoFocus
              />
              <div className="flex flex-wrap gap-1.5 mt-3">
                {TOPICS_PRESETS.map(t => (
                  <button
                    key={t}
                    onClick={() => setTopic(t)}
                    className="text-[11px] px-2.5 py-1 rounded-full bg-[#1a1a24] border border-[#27272f] text-[#71717a] hover:text-[#e4e4f0] hover:border-[#3f3f50] transition-all"
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>
            )}

            {/* Изображение для генерации видео — отдельная карточка, только Mode 2 */}
            {mode === 2 && (
              <div className="card p-5">
                <div className="text-sm font-semibold text-[#e4e4f0] mb-1">Изображение для генерации видео</div>
                <div className="text-xs text-[#71717a] mb-3">Картинка передаётся в fast-gen.ai при создании видеоклипов сцен (image-to-video)</div>
                <div className="flex items-center gap-2">
                  <label className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[#1a1a24] border border-[#27272f] hover:border-brand-600/40 cursor-pointer text-sm text-[#e4e4f0] transition-colors">
                    <RiImageAddLine className="text-lg" />
                    {uploadingRef ? 'Загрузка…' : (referenceImage ? 'Заменить' : 'Выбрать изображение')}
                    <input type="file" accept="image/jpeg,image/png,image/webp" className="hidden"
                      onChange={async (e) => {
                        const f = e.target.files?.[0];
                        if (!f) return;
                        setUploadingRef(true);
                        try {
                          const { path } = await api.uploadImage(f);
                          setReferenceImage({ path, preview: URL.createObjectURL(f) });
                        } catch (err) { setError(err.message); }
                        finally { setUploadingRef(false); e.target.value = ''; }
                      }} />
                  </label>
                  {referenceImage && (
                    <button type="button" onClick={() => setReferenceImage(null)}
                      className="p-2 rounded-lg text-[#71717a] hover:text-red-400 hover:bg-red-900/20">
                      <RiCloseLine />
                    </button>
                  )}
                </div>
                {referenceImage?.preview && (
                  <img src={referenceImage.preview} alt="Reference" className="mt-2 w-32 h-20 object-cover rounded-lg border border-[#27272f]" />
                )}
                {referenceImage?.path && !referenceImage?.preview ? (
                  <p className="mt-2 text-xs text-amber-400/90">Референс на сервере из прошлого запуска. При необходимости выберите файл снова.</p>
                ) : null}
              </div>
            )}

            {/* Started in background */}
            {startedSession && (
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                className="p-4 rounded-xl bg-emerald-900/20 border border-emerald-700/40 flex items-center justify-between gap-4"
              >
                <span className="text-sm text-emerald-300">Генерация запущена в фоне</span>
                <button
                  type="button"
                  onClick={() => navigate(`/run/${startedSession}`)}
                  className="text-sm font-medium text-emerald-400 hover:text-emerald-300 underline"
                >
                  Перейти к прогрессу →
                </button>
              </motion.div>
            )}

            {/* Error */}
            {error && (
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="p-3 rounded-xl bg-red-900/20 border border-red-800/40 text-red-400 text-sm"
              >
                {error}
              </motion.div>
            )}

            {/* Actions */}
            <div className="flex gap-3">
              {mode === 9 ? (
                <button
                  onClick={handleMode9Launch}
                  disabled={isLoading}
                  className="btn-primary flex-1 flex items-center justify-center gap-2 text-base py-4"
                >
                  <RiSparklingLine className="text-lg" />
                  Генерировать
                </button>
              ) : mode === 10 ? (
                <button
                  onClick={handleMode10Launch}
                  disabled={isLoading}
                  className="btn-primary flex-1 flex items-center justify-center gap-2 text-base py-4"
                >
                  <RiSparklingLine className="text-lg" />
                  Сгенерировать timelapse
                </button>
              ) : mode === 11 ? (
                <button
                  onClick={handleMode11Launch}
                  disabled={isLoading}
                  className="btn-primary flex-1 flex items-center justify-center gap-2 text-base py-4"
                >
                  <RiSparklingLine className="text-lg" />
                  Сгенерировать timelapse
                </button>
              ) : mode === 8 ? (
                <button
                  onClick={handleMode8Launch}
                  disabled={isLoading}
                  className="btn-primary flex-1 flex items-center justify-center gap-2 text-base py-4"
                >
                  <RiSparklingLine className="text-lg" />
                  Сгенерировать timelapse
                </button>
              ) : mode === 7 ? (
                <button
                  onClick={handleMode7Launch}
                  disabled={isLoading}
                  className="btn-primary flex-1 flex items-center justify-center gap-2 text-base py-4"
                >
                  <RiSparklingLine className="text-lg" />
                  Сгенерировать видео
                </button>
              ) : mode === 6 ? (
                <button
                  onClick={handleMode6Launch}
                  disabled={isLoading}
                  className="btn-primary flex-1 flex items-center justify-center gap-2 text-base py-4"
                >
                  <RiSparklingLine className="text-lg" />
                  Сгенерировать драму
                </button>
              ) : mode === 5 ? (
                <button
                  onClick={handleMode5Launch}
                  disabled={
                    isLoading ||
                    (mode5SubMode === 'bible'
                      ? mode5BibleChapters.every(ch => !ch.text.trim()) ||
                        mode5BibleChapters.reduce((n, ch) => n + ch.text.trim().length, 0) < MODE5_BIBLE_MIN_TOTAL_CHARS
                      : !mode5Script.trim()) ||
                    (mode5SubMode === 'facts50' && mode5Script.trim().length < 8) ||
                    (mode5SubMode === 'book_night' && mode5Script.trim().length < 8) ||
                    (mode5SubMode === 'unwritten_chapter' && mode5Script.trim().length < 8) ||
                    (mode5SubMode === 'outline' && mode5Script.trim().length < MODE5_OUTLINE_MIN_BRIEF_CHARS) ||
                    (mode5SubMode === 'manual' && mode5Script.trim().length < 80)
                  }
                  className="btn-primary flex-1 flex items-center justify-center gap-2 text-base py-4"
                >
                  <RiSparklingLine className="text-lg" />
                  {(mode5SubMode === 'facts50'
                    ? 'Сгенерировать 77 фактов и превью'
                    : mode5SubMode === 'outline'
                      ? 'Сгенерировать план и превью'
                      : mode5SubMode === 'book_night'
                        ? 'Сгенерировать книгу на ночь'
                        : mode5SubMode === 'unwritten_chapter'
                          ? 'Сгенерировать расследование'
                          : mode5SubMode === 'bible'
                            ? 'Запустить Bible long-form'
                            : 'Запустить review long-form') + (mode5TestRun ? ' · тест ~5 мин' : '')}
                </button>
              ) : mode === 13 ? (
                <button
                  onClick={handleMode13Launch}
                  disabled={isLoading || !mode13Audio?.path || uploadingMode13Audio}
                  className="btn-primary flex-1 flex items-center justify-center gap-2 text-base py-4"
                >
                  <RiSparklingLine className="text-lg" />
                  Запустить обработку аудио
                </button>
              ) : mode === 4 ? (
                <button
                  onClick={handleMode4Launch}
                  disabled={
                    isLoading ||
                    !mode4Quote.trim() ||
                    !mode4Photo?.path ||
                    (mode4Multiclip && mode4QuoteBlocks.length < 2)
                  }
                  className="btn-primary flex-1 flex items-center justify-center gap-2 text-base py-4"
                >
                  <RiSparklingLine className="text-lg" />
                  Сгенерировать видео
                </button>
              ) : mode === 3 ? (
                <>
                  <button
                    onClick={handleMode3Launch}
                    disabled={isLoading || (mode3InputMode === 'type' ? !mode3HouseType : !mode3StartImage?.path || !mode3EndImage?.path)}
                    className="btn-primary flex-1 flex items-center justify-center gap-2 text-base py-4"
                  >
                    <RiSparklingLine className="text-lg" />
                    {mode3InputMode === 'type' ? 'Сгенерировать и создать видео' : 'Создать видео реставрации'}
                  </button>
                </>
              ) : (
                <>
                  <button
                    onClick={handleGenerateScenario}
                    disabled={isLoading || !topic.trim()}
                    className="btn-primary flex-1 flex items-center justify-center gap-2 text-base py-4"
                  >
                    <RiEditLine className="text-lg" />
                    Написать сценарий
                    <RiArrowRightLine className="text-lg ml-1" />
                  </button>
                  <button
                    onClick={handleDirectLaunch}
                    disabled={isLoading || !topic.trim()}
                    title="Запустить без предпросмотра сценария"
                    className="px-4 py-4 rounded-xl border border-[#27272f] text-[#71717a] hover:text-[#e4e4f0] hover:border-[#3f3f50] transition-all text-sm font-medium"
                  >
                    <RiSparklingLine className="text-xl" />
                  </button>
                </>
              )}
            </div>

            {mode !== 3 && mode !== 4 && mode !== 6 && mode !== 7 && mode !== 8 && mode !== 9 && mode !== 10 && mode !== 13 && (
            <p className="text-center text-xs text-[#52525b]">
              «Написать сценарий» — посмотреть и отредактировать перед генерацией
            </p>
            )}
          </motion.div>
        )}

        {/* ── STEP: GENERATING SCENARIO ──────────────────────────────────── */}
        {step === 'generating_scenario' && (
          <motion.div
            key="gen_scenario"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex flex-col items-center justify-center py-20 gap-4"
          >
            <RiLoader4Line className="animate-spin text-4xl text-brand-400" />
            <p className="text-[#a1a1aa] text-sm">Сценарист AI пишет сценарий…</p>
            <p className="text-[#52525b] text-xs">обычно 15–30 секунд</p>
          </motion.div>
        )}

        {/* ── STEP: EDITING SCENARIO ─────────────────────────────────────── */}
        {step === 'editing' && scenario && (
          <motion.div
            key="editing"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="space-y-6"
          >
            {/* banner */}
            <div className="flex items-center gap-3 p-4 rounded-xl bg-indigo-900/20 border border-indigo-700/40">
              <RiCheckboxCircleLine className="text-indigo-400 text-2xl flex-shrink-0" />
              <div>
                <div className="text-sm font-semibold text-indigo-300">Сценарий готов — можно редактировать</div>
                <div className="text-xs text-[#71717a] mt-0.5">
                  Измените текст озвучки или промт, затем нажмите «Создать видео»
                </div>
              </div>
            </div>

            {/* editor */}
            <ScenarioEditor scenario={scenario} onChange={setScenario2} />

            {/* error */}
            {error && (
              <div className="p-3 rounded-xl bg-red-900/20 border border-red-800/40 text-red-400 text-sm">
                {error}
              </div>
            )}

            {/* actions */}
            <div className="flex gap-3 sticky bottom-4">
              <button
                type="button"
                onClick={() => { setStep('form'); setScenario2(null); }}
                className="px-4 py-4 rounded-xl border border-[#27272f] text-[#71717a] hover:text-[#e4e4f0] transition-all flex items-center gap-2 text-sm font-medium"
              >
                ← Назад
              </button>
              <button
                type="button"
                onClick={() => { setScenario2(null); handleGenerateScenario(); }}
                className="px-4 py-4 rounded-xl border border-[#27272f] text-[#71717a] hover:text-[#e4e4f0] transition-all flex items-center gap-2 text-sm font-medium"
              >
                <RiRefreshLine /> Перегенерировать
              </button>
              <button
                onClick={handleLaunch}
                className="btn-primary flex-1 flex items-center justify-center gap-2 text-base py-4"
              >
                <RiSparklingLine className="text-lg" />
                Создать видео
                <RiArrowRightLine className="text-lg ml-1" />
              </button>
            </div>
          </motion.div>
        )}

        {/* ── STEP: LAUNCHING ────────────────────────────────────────────── */}
        {step === 'launching' && (
          <motion.div
            key="launching"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex flex-col items-center justify-center py-20 gap-4"
          >
            <RiLoader4Line className="animate-spin text-4xl text-brand-400" />
            <p className="text-[#a1a1aa] text-sm">Запускаем пайплайн…</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
