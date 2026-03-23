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
];

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
  // Mode 4: цитата + фото личности (язык определяется автоматически)
  const [mode4Quote, setMode4Quote] = useState('');
  const [mode4PersonName, setMode4PersonName] = useState('');
  const [mode4Photo, setMode4Photo] = useState(null);
  // Mode 5: длинные видео
  const [mode5Topic, setMode5Topic] = useState('');
  const [mode5Lang, setMode5Lang] = useState('ru'); // ru | en

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
        language: 'auto',
        mode4_quote: mode4Quote.trim(),
        mode4_person_name: mode4PersonName.trim(),
        mode4_photo_path: mode4Photo.path,
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
                {mode === 3 ? 'Реставрация дома' : mode === 4 ? 'Цитата + фото' : mode === 5 ? 'Длинные видео' : 'Создать видео'}
              </h1>
              <p className="text-[#71717a] text-sm">
                {mode === 3
                  ? 'Маленький дом, одна комната-студия. AI создаст промпты и фото. 8 фрагментов: intro, 3 экстерьер, 3 интерьер (как снаружи), финал (скриншот clip 3 → снаружи→внутри). Музыка.'
                  : mode === 4
                    ? 'Цитата известной личности + фото. Агент пишет кинематографичный промпт, генерируется 1 или 2 видеофрагмента. Без озвучки и музыки, только субтитры (в настройках).'
                    : mode === 5
                      ? '~1 час видео: AI пишет большой сценарий, генерирует картинки при смене сюжета, озвучивает. Без субтитров. RU или EN.'
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
                  <p className="text-xs text-brand-400/80 mb-2">Введите цитату на любом языке — система определит язык и покажет субтитры в нём</p>
                  <textarea
                    className="input text-base min-h-[100px] resize-y"
                    placeholder="Русский: Безумцы прокладывают пути... / English: The only way to do great work... / Deutsch: Einmal ist keinmal..."
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
                      {mode !== 3 && mode !== 4 && (
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

                      {(mode !== 3 && mode !== 5) || mode === 4 ? (
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

                      {(mode !== 3 && mode !== 4) && (
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
              {mode === 5 ? (
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

            {mode !== 3 && mode !== 4 && (
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
