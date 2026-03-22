import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  RiSparklingLine, RiSettings3Line, RiArrowRightLine,
  RiLoader4Line, RiEditLine, RiCheckboxCircleLine,
  RiRefreshLine, RiImageAddLine, RiCloseLine,
} from 'react-icons/ri';
import { useLanguage } from '../context/LanguageContext';
import { useMode } from '../context/ModeContext';
import { api } from '../services/api';
import ScenarioEditor from '../components/ScenarioEditor';

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
export default function Generate() {
  const navigate = useNavigate();

  const { mode } = useMode();
  const { lang } = useLanguage();

  /* form state */
  const [topic, setTopic]           = useState('');
  const [scenes, setScenes]         = useState(5);
  const [useScenario, setScenario]  = useState(true);
  const [localOnly, setLocalOnly]   = useState(true);
  const [showSubtitles, setShowSubtitles] = useState(true);
  const [showSettings, setSettings] = useState(false);
  const [referenceImage, setReferenceImage] = useState(null); // { path, preview } — для fast-gen image-to-video
  const [uploadingRef, setUploadingRef] = useState(false);

  /* scenario editing state */
  const [step, setStep]             = useState('form');   // 'form' | 'generating_scenario' | 'editing' | 'launching'
  const [scenario, setScenario2]    = useState(null);

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
      navigate(`/run/${res.session_id}`);
    } catch (e) {
      setError(e.message);
      setStep('editing');
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
      navigate(`/run/${res.session_id}`);
    } catch (e) {
      setError(e.message);
      setStep('form');
    }
  }

  const isLoading = step === 'generating_scenario' || step === 'launching';

  /* ── render ─────────────────────────────────────────────────────────────── */
  return (
    <div className="max-w-2xl mx-auto px-6 py-10">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <h1 className="text-2xl font-bold text-white mb-1">Создать видео</h1>
        <p className="text-[#71717a] text-sm">
          AI-агенты напишут сценарий, сгенерируют изображения и смонтируют видео.
        </p>
      </motion.div>

      {/* ── STEP: FORM ───────────────────────────────────────────────────── */}
      <AnimatePresence mode="wait">
        {step === 'form' && (
          <motion.div
            key="form"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="space-y-4"
          >
            {/* Topic card */}
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

                      <div className="flex items-center justify-between">
                        <div>
                          <div className="text-sm font-medium text-[#e4e4f0]">Только локально</div>
                          <div className="text-xs text-[#71717a]">Не публиковать в соцсети</div>
                        </div>
                        <Toggle value={localOnly} onChange={setLocalOnly} />
                      </div>

                      <div className="flex items-center justify-between">
                        <div>
                          <div className="text-sm font-medium text-[#e4e4f0]">Субтитры</div>
                          <div className="text-xs text-[#71717a]">Показывать текст озвучки на видео</div>
                        </div>
                        <Toggle value={showSubtitles} onChange={setShowSubtitles} />
                      </div>

                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

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
              {/* primary: generate scenario first */}
              <button
                onClick={handleGenerateScenario}
                disabled={isLoading || !topic.trim()}
                className="btn-primary flex-1 flex items-center justify-center gap-2 text-base py-4"
              >
                <RiEditLine className="text-lg" />
                Написать сценарий
                <RiArrowRightLine className="text-lg ml-1" />
              </button>

              {/* secondary: skip preview */}
              <button
                onClick={handleDirectLaunch}
                disabled={isLoading || !topic.trim()}
                title="Запустить без предпросмотра сценария"
                className="px-4 py-4 rounded-xl border border-[#27272f] text-[#71717a] hover:text-[#e4e4f0] hover:border-[#3f3f50] transition-all text-sm font-medium"
              >
                <RiSparklingLine className="text-xl" />
              </button>
            </div>

            <p className="text-center text-xs text-[#52525b]">
              «Написать сценарий» — посмотреть и отредактировать перед генерацией
            </p>
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
