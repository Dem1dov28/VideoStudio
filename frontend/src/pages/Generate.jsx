import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  RiSparklingLine, RiSettings3Line, RiArrowRightLine, RiArrowLeftLine,
  RiLoader4Line, RiEditLine, RiCheckboxCircleLine,
  RiRefreshLine, RiImageAddLine, RiCloseLine,
} from 'react-icons/ri';
import { useLanguage } from '../context/LanguageContext';
import { useMode } from '../context/ModeContext';
import { api } from '../services/api';
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

const TOPICS_PRESETS = [
  'Топ-5 фактов о чёрных дырах',
  'Почему мы видим сны: наука',
  'Как работает квантовый компьютер',
  'Тайны глубокого океана',
  'Психология первого впечатления',
  'Как устроен человеческий мозг',
];

/* ── toggle ──────────────────────────────────────────────────────────────── */
function Toggle({ value, onChange }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!value)}
      className={`w-11 h-6 rounded-full transition-all duration-200 ${value ? 'bg-brand-600' : 'bg-[#27272f]'}`}
    >
      <motion.div
        animate={{ x: value ? 20 : 2 }}
        className="w-5 h-5 rounded-full bg-white shadow-sm"
      />
    </button>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════ */
const MODES = [
  { id: 1, label: '5 фактов', desc: 'AI пишет сценарий и генерирует картинки', icon: '📊' },
  { id: 2, label: 'Почему X?', desc: '5 вопросов с видеоклипами и озвучкой', icon: '❓' },
  { id: 3, label: 'Реставрация домов', desc: 'Маленький дом, одна комната-студия → 8 фрагментов', icon: '🏠' },
  { id: 4, label: 'Цитата + фото', desc: 'Цитата известной личности и фото → кинематографичный видеофрагмент', icon: '💬' },
  { id: 5, label: 'Длинные видео', desc: '~1 час: большой сценарий, озвучка, картинки при смене сюжета', icon: '📹' },
  { id: 6, label: 'Cartoon Drama', desc: 'Абсурдные вирусные истории с овощными персонажами', icon: '🥦' },
  { id: 7, label: 'ASMR Keyboard', desc: 'Животные нажимают клавиши: мёд, желе, лёд, шоколад', icon: '🐱' },
  { id: 8, label: 'House Timelapse', desc: 'Строительство дома: пустой участок → готовый дом', icon: '🏗️' },
  { id: 9, label: 'Vehicle Assembly', desc: 'Сборка транспорта: рама → двигатель → кузов → готовый автомобиль', icon: '🚗' },
  { id: 10, label: 'Уборка пляжа', desc: 'Timelapse: грязный пляж → уборка → чистый берег', icon: '🏖️' },
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

export default function Generate() {
  const navigate = useNavigate();
  const { mode, setMode } = useMode();
  const { lang, setLang } = useLanguage();

  /* form state */
  const [topic, setTopic]           = useState('');
  const [scenes, setScenes]         = useState(5);
  const [useScenario, setScenario]  = useState(true);
  const [localOnly, setLocalOnly]   = useState(true);
  const [showSubtitles, setShowSubtitles] = useState(true);
  const [showSettings, setSettings] = useState(false);
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
  const [mode4Photo, setMode4Photo] = useState(null);
  const [mode4OutputLang, setMode4OutputLang] = useState('both'); // 'both' | 'ru' | 'en'
  // Mode 5: длинные видео
  const [mode5Topic, setMode5Topic] = useState('');
  const [mode5Lang, setMode5Lang] = useState('ru'); // ru | en
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
  const [mode8UseKeyframes, setMode8UseKeyframes] = useState(false);
  const [mode8StartFrame, setMode8StartFrame] = useState(null);
  const [mode8EndFrame, setMode8EndFrame] = useState(null);
  // Mode 9: Vehicle Assembly Timelapse
  const [mode9VehicleType, setMode9VehicleType] = useState('random');
  const [mode9Location, setMode9Location] = useState('random');
  const [mode9NumStages, setMode9NumStages] = useState(5);
  // Mode 10: beach cleanup timelapse
  const [mode10BeachType, setMode10BeachType] = useState('tropical');
  const [mode10CoastSetting, setMode10CoastSetting] = useState('morning_calm');
  const [mode10NumStages, setMode10NumStages] = useState(5);

  /* scenario editing state */
  const [step, setStep]             = useState('select_mode');   // 'select_mode' | 'form' | 'generating_scenario' | 'editing' | 'launching'
  const [scenario, setScenario2]    = useState(null);
  const [startedSession, setStartedSession] = useState(null);

  const [error, setError] = useState('');

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
        show_subtitles: showSubtitles,
        show_watermark: false,
        scenario: scenario,
        mode,
        language: lang,
        reference_image_path: referenceImage?.path || null,
      };
      const res = await api.startPipeline(payload);
      setStep('form');
      setStartedSession(res.session_id);
    } catch (e) {
      setError(e.message);
      setStep('editing');
    }
  }

  /* Mode 5: длинные видео — прямой запуск */
  async function handleMode5Launch() {
    if (!mode5Topic.trim()) {
      setError('Введите тему для видео');
      return;
    }
    setError('');
    setStep('launching');
    try {
      const payload = {
        topic: mode5Topic.trim(),
        auto_topic: false,
        num_scenes: 1,
        use_scenario: false,
        local_only: localOnly,
        show_subtitles: false,
        show_watermark: false,
        scenario: null,
        mode: 5,
        language: mode5Lang,
      };
      const res = await api.startPipeline(payload);
      setStep('form');
      setStartedSession(res.session_id);
    } catch (e) {
      setError(e.message);
      setStep('form');
    }
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
      const res = await api.startPipeline(payload);
      setStep('form');
      setStartedSession(res.session_id);
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
      const res = await api.startPipeline(payload);
      setStep('form');
      setStartedSession(res.session_id);
    } catch (e) {
      setError(e.message);
      setStep('form');
    }
  }

  /* Mode 8: House Building Timelapse — прямой запуск */
  async function handleMode8Launch() {
    if (mode8UseKeyframes) {
      if (!mode8StartFrame?.path) {
        setError('Загрузите начальный кадр');
        return;
      }
      if (!mode8EndFrame?.path) {
        setError('Загрузите конечный кадр');
        return;
      }
    }
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
        mode8_house_style: mode8UseKeyframes ? null : (mode8HouseStyle === 'random' ? null : mode8HouseStyle),
        mode8_location: mode8UseKeyframes ? null : (mode8Location === 'random' ? null : mode8Location),
        mode8_num_stages: mode8NumStages,
        mode8_use_keyframes: mode8UseKeyframes,
        mode8_start_frame_path: mode8UseKeyframes ? mode8StartFrame?.path : null,
        mode8_end_frame_path: mode8UseKeyframes ? mode8EndFrame?.path : null,
      };
      const res = await api.startPipeline(payload);
      setStep('form');
      setStartedSession(res.session_id);
    } catch (e) {
      setError(e.message);
      setStep('form');
    }
  }

  /* Mode 10: уборка пляжа — прямой запуск (как mode 8 без keyframes) */
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
      const res = await api.startPipeline(payload);
      setStep('form');
      setStartedSession(res.session_id);
    } catch (e) {
      setError(e.message);
      setStep('form');
    }
  }

  /* Mode 9: Vehicle Assembly Timelapse — прямой запуск */
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
      const res = await api.startPipeline(payload);
      setStep('form');
      setStartedSession(res.session_id);
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
    if (!mode4PersonName.trim()) {
      setError('Введите имя личности');
      return;
    }
    if (!mode4Photo?.path) {
      setError('Загрузите фото личности');
      return;
    }
    setError('');
    setStep('launching');
    try {
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
        mode4_only_lang: mode4OutputLang === 'both' ? null : mode4OutputLang,
      };
      const res = await api.startPipeline(payload);
      setStep('form');
      setStartedSession(res.session_id);
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
      const res = await api.startPipeline(payload);
      setStep('form');
      setStartedSession(res.session_id);
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
      const res = await api.startPipeline({
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
      });
      setStep('form');
      setStartedSession(res.session_id);
    } catch (e) {
      setError(e.message);
      setStep('form');
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

            {/* Header */}
            <div className="mb-6">
              <h1 className="text-2xl font-bold text-white mb-1">
                {mode === 3 ? 'Реставрация дома' : mode === 4 ? 'Цитата + фото' : mode === 5 ? 'Длинные видео' : mode === 6 ? 'Cartoon Drama' : mode === 7 ? 'ASMR Keyboard' : mode === 8 ? 'House Timelapse' : mode === 9 ? 'Vehicle Assembly' : mode === 10 ? 'Уборка пляжа' : 'Создать видео'}
              </h1>
              <p className="text-[#71717a] text-sm">
                {mode === 3
                  ? 'Маленький дом, одна комната-студия. AI создаст промпты и фото. 8 фрагментов: intro, 3 экстерьер, 3 интерьер (как снаружи), финал (скриншот clip 3 → снаружи→внутри). Музыка.'
                  : mode === 4
                    ? 'Цитата и имя автора на русском. Можно сгенерировать оба ролика (RU + EN), только русскую или только английскую версию. Озвучка FastGen, субтитры — в настройках.'
                    : mode === 5
                      ? '~1 час видео: AI пишет большой сценарий, генерирует картинки при смене сюжета, озвучивает. Без субтитров. RU или EN.'
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
                                : 'AI-агенты напишут сценарий, сгенерируют изображения и смонтируют видео.'}
              </p>
            </div>

            {/* Mode 5: длинные видео */}
            {mode === 5 ? (
              <div className="space-y-4">
                <div className="card p-5">
                  <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-3">
                    Тема длинного видео
                  </label>
                  <input
                    className="input text-base"
                    placeholder="Например: История Древнего Рима от основания до падения"
                    value={mode5Topic}
                    onChange={e => setMode5Topic(e.target.value)}
                  />
                  <p className="text-xs text-[#52525b] mt-2">
                    AI напишет сценарий ~1 час, сгенерирует изображения при смене сюжета, озвучит. Язык — в настройках.
                  </p>
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
                {/* Keyframes toggle */}
                <div className="card p-5">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-sm font-semibold text-[#e4e4f0]">Ключ. кадры</div>
                      <div className="text-xs text-[#71717a]">Генерация видео по начальному и конечному кадру</div>
                    </div>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={mode8UseKeyframes}
                      onClick={() => setMode8UseKeyframes(!mode8UseKeyframes)}
                      className={`inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent shadow-sm transition-colors ${
                        mode8UseKeyframes ? 'bg-brand-600' : 'bg-[#27272f]'
                      }`}
                    >
                      <span
                        className={`pointer-events-none block h-4 w-4 rounded-full bg-white shadow-sm transition-transform ${
                          mode8UseKeyframes ? 'translate-x-4' : 'translate-x-0'
                        }`}
                      />
                    </button>
                  </div>
                </div>

                {mode8UseKeyframes ? (
                  /* Keyframe mode: start + end frame upload */
                  <>
                    {/* Start frame upload */}
                    <div className="card p-5">
                      <div className="text-sm font-semibold text-[#e4e4f0] mb-1">Начальный кадр</div>
                      <div className="text-xs text-[#71717a] mb-3">Загрузите изображение для начального кадра видео</div>
                      <div
                        className="h-24 flex flex-col items-center justify-center rounded-lg border-2 border-dashed transition-colors cursor-pointer gap-2 border-[#27272f] hover:border-[#71717a]"
                        onClick={() => document.getElementById('mode8-start-frame')?.click()}
                      >
                        {mode8StartFrame?.preview ? (
                          <img src={mode8StartFrame.preview} alt="Start frame" className="h-20 w-32 object-cover rounded" />
                        ) : (
                          <>
                            <RiImageAddLine className="text-2xl text-[#71717a]" />
                            <span className="text-xs text-[#71717a]">Нажмите для загрузки</span>
                          </>
                        )}
                      </div>
                      <input
                        id="mode8-start-frame"
                        type="file"
                        accept="image/jpeg,image/png,image/webp"
                        className="hidden"
                        onChange={async (e) => {
                          const f = e.target.files?.[0];
                          if (!f) return;
                          setUploadingRef(true);
                          try {
                            const { path } = await api.uploadImage(f);
                            setMode8StartFrame({ path, preview: URL.createObjectURL(f) });
                          } catch (err) { setError(err.message); }
                          finally { setUploadingRef(false); e.target.value = ''; }
                        }}
                      />
                      {mode8StartFrame && (
                        <button
                          type="button"
                          onClick={() => setMode8StartFrame(null)}
                          className="mt-2 text-xs text-[#71717a] hover:text-red-400"
                        >
                          Удалить
                        </button>
                      )}
                    </div>

                    {/* End frame upload */}
                    <div className="card p-5">
                      <div className="text-sm font-semibold text-[#e4e4f0] mb-1">Конечный кадр</div>
                      <div className="text-xs text-[#71717a] mb-3">Загрузите изображение для конечного кадра видео</div>
                      <div
                        className="w-full aspect-square flex flex-col items-center justify-center rounded-lg border-2 border-dashed transition-colors cursor-pointer border-[#27272f] hover:border-[#71717a]"
                        onClick={() => document.getElementById('mode8-end-frame')?.click()}
                      >
                        {mode8EndFrame?.preview ? (
                          <img src={mode8EndFrame.preview} alt="End frame" className="h-full w-full object-cover rounded-lg" />
                        ) : (
                          <>
                            <RiImageAddLine className="text-3xl text-[#71717a]" />
                            <span className="text-sm text-[#71717a]">Нажмите для загрузки</span>
                          </>
                        )}
                      </div>
                      <input
                        id="mode8-end-frame"
                        type="file"
                        accept="image/jpeg,image/png,image/webp"
                        className="hidden"
                        onChange={async (e) => {
                          const f = e.target.files?.[0];
                          if (!f) return;
                          setUploadingRef(true);
                          try {
                            const { path } = await api.uploadImage(f);
                            setMode8EndFrame({ path, preview: URL.createObjectURL(f) });
                          } catch (err) { setError(err.message); }
                          finally { setUploadingRef(false); e.target.value = ''; }
                        }}
                      />
                      {mode8EndFrame && (
                        <button
                          type="button"
                          onClick={() => setMode8EndFrame(null)}
                          className="mt-2 text-xs text-[#71717a] hover:text-red-400"
                        >
                          Удалить
                        </button>
                      )}
                    </div>
                  </>
                ) : (
                  /* Default mode: style/location selection */
                  <>
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
                  </>
                )}

                {/* Timelapse Info card */}
                <div className="card p-4 bg-gradient-to-br from-amber-900/20 to-orange-900/10 border-amber-700/30">
                  <div className="text-sm font-semibold text-amber-300 mb-2">🏗️ Timelapse Режим</div>
                  <p className="text-xs text-[#a1a1aa]">
                    {mode8UseKeyframes
                      ? 'AI сгенерирует плавный переход от начального кадра к конечному в стиле timelapse.'
                      : 'Видео в стиле ускоренной съёмки строительства. Фотореалистичный стиль, как снято на камеру телефона. Звуки строительной площадки.'}
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
            ) : mode === 4 ? (
              <div className="space-y-4">
                <div className="card p-5">
                  <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-3">
                    Имя личности
                  </label>
                  <input
                    className="input text-base"
                    placeholder="Например: Фёдор Достоевский"
                    value={mode4PersonName}
                    onChange={e => setMode4PersonName(e.target.value)}
                  />
                </div>
                <div className="card p-5">
                  <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-3">
                    Цитата
                  </label>
                  <p className="text-xs text-brand-400/80 mb-2">Цитату и имя вводите на русском; для английского ролика агент переведёт текст</p>
                  <textarea
                    className="input text-base min-h-[100px] resize-y"
                    placeholder="Например: Безумцы прокладывают пути, по которым потом с ума сходят нормальные люди."
                    value={mode4Quote}
                    onChange={e => setMode4Quote(e.target.value)}
                  />
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
                        onClick={() => setMode4OutputLang(opt.id)}
                        className={`text-left px-4 py-3 rounded-xl border transition-all ${
                          mode4OutputLang === opt.id
                            ? 'border-brand-500 bg-brand-600/15 ring-1 ring-brand-500/40'
                            : 'border-[#27272f] bg-[#14141c] hover:border-[#3f3f46]'
                        }`}
                      >
                        <div className="text-sm font-semibold text-[#e4e4f0]">{opt.title}</div>
                        <div className="text-[10px] text-[#71717a] mt-1 leading-snug">{opt.sub}</div>
                      </button>
                    ))}
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
              </div>
            )}

            {/* Settings */}
            <div className="card overflow-hidden">
              <button
                type="button"
                onClick={() => setSettings(s => !s)}
                className="w-full flex items-center justify-between px-5 py-3.5 text-sm text-[#71717a] hover:text-[#e4e4f0] transition-colors"
              >
                <div className="flex items-center gap-2">
                  <RiSettings3Line className="text-base" />
                  <span className="font-medium">Настройки</span>
                </div>
                <motion.span animate={{ rotate: showSettings ? 180 : 0 }} transition={{ duration: 0.2 }}>▾</motion.span>
              </button>

              <AnimatePresence>
                {showSettings && (
                  <motion.div
                    initial={{ height: 0 }}
                    animate={{ height: 'auto' }}
                    exit={{ height: 0 }}
                    className="overflow-hidden"
                  >
                    <div className="px-5 pb-5 border-t border-[#27272f] pt-4 space-y-4">
                      {mode !== 3 && mode !== 4 && mode !== 6 && mode !== 7 && mode !== 8 && mode !== 9 && mode !== 10 && (
                      <div>
                        <div className="flex justify-between mb-2">
                          <label className="text-xs font-medium text-[#a1a1aa]">Количество сцен</label>
                          <span className="text-xs font-bold text-brand-400">{scenes}</span>
                        </div>
                        <input
                          type="range" min={3} max={8} value={scenes}
                          onChange={e => setScenes(+e.target.value)}
                          className="w-full accent-brand-500"
                        />
                        <div className="flex justify-between text-[10px] text-[#52525b] mt-1">
                          <span>3 (быстро)</span><span>8 (детально)</span>
                        </div>
                      </div>
                      )}

                      <div className="flex items-center justify-between">
                        <div>
                          <div className="text-sm font-medium text-[#e4e4f0]">Только локально</div>
                          <div className="text-xs text-[#71717a]">Не публиковать в соцсети</div>
                        </div>
                        <Toggle value={localOnly} onChange={setLocalOnly} />
                      </div>

                      {((mode !== 3 && mode !== 5 && mode !== 7 && mode !== 8 && mode !== 9 && mode !== 10) || mode === 4) ? (
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="text-sm font-medium text-[#e4e4f0]">Субтитры</div>
                          <div className="text-xs text-[#71717a]">
                            {mode === 4 ? 'Показывать цитату на видео' : 'Показывать текст озвучки на видео'}
                          </div>
                        </div>
                        <Toggle value={showSubtitles} onChange={setShowSubtitles} />
                      </div>
                      ) : null}

                      {mode !== 3 && mode !== 4 && mode !== 7 && mode !== 8 && mode !== 9 && mode !== 10 && (
                      <div>
                        <div className="text-sm font-medium text-[#e4e4f0] mb-2">Язык субтитров</div>
                        <div className="text-xs text-[#71717a] mb-2">Язык озвучки и текста на видео</div>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => setLang('ru')}
                            title="Русский"
                            className={`flex-1 py-2.5 rounded-lg text-sm font-medium transition-all ${
                              lang === 'ru'
                                ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                                : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                            }`}
                          >
                            RU
                          </button>
                          <button
                            type="button"
                            onClick={() => setLang('en')}
                            title="English"
                            className={`flex-1 py-2.5 rounded-lg text-sm font-medium transition-all ${
                              lang === 'en'
                                ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                                : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                            }`}
                          >
                            EN
                          </button>
                        </div>
                      </div>
                      )}
                      {mode === 5 && (
                      <div>
                        <div className="text-sm font-medium text-[#e4e4f0] mb-2">Язык озвучки</div>
                        <div className="text-xs text-[#71717a] mb-2">Язык озвучки (RU или EN)</div>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => setMode5Lang('ru')}
                            title="Русский"
                            className={`flex-1 py-2.5 rounded-lg text-sm font-medium transition-all ${
                              mode5Lang === 'ru'
                                ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                                : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                            }`}
                          >
                            RU
                          </button>
                          <button
                            type="button"
                            onClick={() => setMode5Lang('en')}
                            title="English"
                            className={`flex-1 py-2.5 rounded-lg text-sm font-medium transition-all ${
                              mode5Lang === 'en'
                                ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                                : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
                            }`}
                          >
                            EN
                          </button>
                        </div>
                      </div>
                      )}

                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

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
                  Сгенерировать timelapse
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
              ) : mode === 8 ? (
                <button
                  onClick={handleMode8Launch}
                  disabled={isLoading || (mode8UseKeyframes && (!mode8StartFrame?.path || !mode8EndFrame?.path))}
                  className="btn-primary flex-1 flex items-center justify-center gap-2 text-base py-4"
                >
                  <RiSparklingLine className="text-lg" />
                  {mode8UseKeyframes ? 'Сгенерировать видео' : 'Сгенерировать timelapse'}
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
                  disabled={isLoading || !mode5Topic.trim()}
                  className="btn-primary flex-1 flex items-center justify-center gap-2 text-base py-4"
                >
                  <RiSparklingLine className="text-lg" />
                  Сгенерировать длинное видео
                </button>
              ) : mode === 4 ? (
                <button
                  onClick={handleMode4Launch}
                  disabled={isLoading || !mode4Quote.trim() || !mode4PersonName.trim() || !mode4Photo?.path}
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

            {mode !== 3 && mode !== 4 && mode !== 6 && mode !== 7 && mode !== 8 && mode !== 9 && mode !== 10 && (
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
