import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  RiBookmarkLine, RiLoader4Line, RiDeleteBin6Line,
  RiCheckLine, RiRefreshLine,
} from 'react-icons/ri';
import { api } from '../services/api';

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('ru-RU', {
    day: 'numeric', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

function ConfirmPopover({ message, onConfirm, onCancel }) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.92, y: 4 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.92 }}
      className="absolute right-0 top-8 z-10 w-64 card p-3 shadow-2xl shadow-black/60 border-red-900/40"
    >
      <p className="text-xs text-[#a1a1aa] mb-3">{message}</p>
      <div className="flex gap-2">
        <button
          onClick={onConfirm}
          className="flex-1 py-1.5 rounded-lg bg-red-900/40 hover:bg-red-900/60 text-red-400 text-xs font-semibold transition-all"
        >
          Да, удалить
        </button>
        <button
          onClick={onCancel}
          className="flex-1 py-1.5 rounded-lg bg-[#1a1a24] hover:bg-[#22222f] text-[#71717a] text-xs transition-all"
        >
          Отмена
        </button>
      </div>
    </motion.div>
  );
}

function TopicRow({ topic, index, total, onRemoved, onRegenerate }) {
  const [showDeleteConfirm, setDeleteConfirm] = useState(false);
  const [showRegenConfirm,  setRegenConfirm]  = useState(false);
  const [busy, setBusy] = useState(false);

  async function handleRemove() {
    setBusy(true);
    setDeleteConfirm(false);
    try {
      await api.removeTopic(topic.session_id);
      onRemoved(topic.session_id);
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleRegen() {
    setBusy(true);
    setRegenConfirm(false);
    try {
      const res = await api.regenerateTopic(topic.session_id);
      onRemoved(topic.session_id);         // remove from local list
      onRegenerate(res.session_id);        // navigate to progress page
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 10, height: 0, marginBottom: 0 }}
      transition={{ duration: 0.2 }}
      className="card px-5 py-4 flex items-start gap-4"
    >
      {/* Index */}
      <span className="text-sm font-bold text-brand-600/40 w-7 flex-shrink-0 text-right mt-0.5">
        {total - index}
      </span>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold text-white leading-snug">
          {topic.topic}
        </div>
        {topic.video_angle && topic.video_angle !== topic.topic && (
          <div className="text-xs text-[#71717a] mt-0.5 truncate">
            {topic.video_angle}
          </div>
        )}
        <div className="flex items-center gap-3 mt-1.5">
          <span className="text-[10px] text-[#52525b]">
            {formatDate(topic.generated_at)}
          </span>
          <span className="text-[10px] font-mono text-[#3f3f50]">
            #{(topic.session_id || '').slice(-8)}
          </span>
        </div>
      </div>

      {/* Badge */}
      <span className="badge bg-emerald-900/25 text-emerald-500 border border-emerald-800/30 flex-shrink-0 mt-0.5">
        ✓ готово
      </span>

      {/* Actions */}
      <div className="flex items-center gap-1.5 flex-shrink-0 relative">
        {busy ? (
          <RiLoader4Line className="animate-spin text-[#71717a] text-lg" />
        ) : (
          <>
            {/* Re-generate */}
            <div className="relative">
              <button
                onClick={() => { setRegenConfirm(v => !v); setDeleteConfirm(false); }}
                title="Перегенерировать"
                className="w-8 h-8 rounded-lg flex items-center justify-center text-[#71717a] hover:text-brand-400 hover:bg-brand-600/10 transition-all"
              >
                <RiRefreshLine className="text-base" />
              </button>
              <AnimatePresence>
                {showRegenConfirm && (
                  <ConfirmPopover
                    message={`Удалить из истории и запустить новую генерацию видео на тему «${topic.topic}»?`}
                    onConfirm={handleRegen}
                    onCancel={() => setRegenConfirm(false)}
                  />
                )}
              </AnimatePresence>
            </div>

            {/* Delete */}
            <div className="relative">
              <button
                onClick={() => { setDeleteConfirm(v => !v); setRegenConfirm(false); }}
                title="Удалить из истории"
                className="w-8 h-8 rounded-lg flex items-center justify-center text-[#71717a] hover:text-red-400 hover:bg-red-900/10 transition-all"
              >
                <RiDeleteBin6Line className="text-base" />
              </button>
              <AnimatePresence>
                {showDeleteConfirm && (
                  <ConfirmPopover
                    message={`Удалить «${topic.topic}» из истории? Тема сможет снова использоваться автоматически.`}
                    onConfirm={handleRemove}
                    onCancel={() => setDeleteConfirm(false)}
                  />
                )}
              </AnimatePresence>
            </div>
          </>
        )}
      </div>
    </motion.div>
  );
}

export default function Topics() {
  const navigate = useNavigate();
  const [topics, setTopics]     = useState([]);
  const [loading, setLoading]   = useState(true);
  const [clearing, setClearing] = useState(false);
  const [cleared, setCleared]   = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);

  const load = () => {
    setLoading(true);
    api.getTopicsHistory()
      .then(r => setTopics((r.topics || []).slice().reverse()))
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  function handleRemoved(sid) {
    setTopics(prev => prev.filter(t => t.session_id !== sid));
  }

  function handleRegenerate(newSid) {
    navigate(`/run/${newSid}`);
  }

  async function handleClearAll() {
    setClearing(true);
    setShowClearConfirm(false);
    try {
      await api.clearTopicsHistory();
      setTopics([]);
      setCleared(true);
      setTimeout(() => setCleared(false), 2500);
    } finally {
      setClearing(false);
    }
  }

  return (
    <div className="max-w-3xl mx-auto px-6 py-10">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-start justify-between mb-8"
      >
        <div>
          <h1 className="text-2xl font-bold text-white mb-1">Журнал тем</h1>
          <p className="text-[#71717a] text-sm">
            {topics.length > 0
              ? `${topics.length} тем сгенерировано — не будут повторяться`
              : 'Сгенерируй первое видео — тема сохранится здесь'}
          </p>
        </div>

        {/* Clear all button */}
        <div className="relative">
          <button
            onClick={() => setShowClearConfirm(v => !v)}
            disabled={clearing || topics.length === 0}
            className="flex items-center gap-2 btn-secondary text-sm disabled:opacity-40"
          >
            {cleared ? (
              <><RiCheckLine className="text-emerald-400" /> Очищено</>
            ) : clearing ? (
              <><RiLoader4Line className="animate-spin" /> Очищаю...</>
            ) : (
              <><RiDeleteBin6Line className="text-red-400" /> Очистить всё</>
            )}
          </button>

          <AnimatePresence>
            {showClearConfirm && (
              <motion.div
                initial={{ opacity: 0, scale: 0.92, y: 4 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.92 }}
                className="absolute right-0 top-10 z-10 w-72 card p-4 shadow-2xl shadow-black/60 border-red-900/40"
              >
                <p className="text-xs text-[#a1a1aa] mb-3">
                  Очистить всю историю? Пайплайн сможет снова выбирать любые темы.
                </p>
                <div className="flex gap-2">
                  <button onClick={handleClearAll} className="flex-1 py-2 rounded-lg bg-red-900/40 hover:bg-red-900/60 text-red-400 text-xs font-semibold transition-all">
                    Да, очистить всё
                  </button>
                  <button onClick={() => setShowClearConfirm(false)} className="flex-1 py-2 rounded-lg bg-[#1a1a24] text-[#71717a] text-xs transition-all hover:bg-[#22222f]">
                    Отмена
                  </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center py-24 text-[#71717a] gap-2">
          <RiLoader4Line className="animate-spin text-xl" />
          <span className="text-sm">Загружаем...</span>
        </div>
      ) : topics.length === 0 ? (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="text-center py-24"
        >
          <RiBookmarkLine className="text-5xl text-[#27272f] mx-auto mb-4" />
          <p className="text-[#71717a] text-sm">Журнал пуст.</p>
          <p className="text-[#52525b] text-xs mt-1">Сгенерируй первое видео — тема сохранится здесь.</p>
        </motion.div>
      ) : (
        <motion.div layout className="space-y-2">
          <AnimatePresence mode="popLayout">
            {topics.map((t, i) => (
              <TopicRow
                key={t.session_id || i}
                topic={t}
                index={i}
                total={topics.length}
                onRemoved={handleRemoved}
                onRegenerate={handleRegenerate}
              />
            ))}
          </AnimatePresence>
        </motion.div>
      )}

      {/* Legend */}
      {topics.length > 0 && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
          className="mt-6 p-4 rounded-xl bg-[#111117] border border-[#1e1e2a]"
        >
          <div className="flex flex-wrap gap-5 text-xs text-[#71717a]">
            <div className="flex items-center gap-2">
              <RiRefreshLine className="text-brand-400" />
              <span><span className="text-[#e4e4f0]">Перегенерировать</span> — удалит из истории и запустит новое видео по той же теме</span>
            </div>
            <div className="flex items-center gap-2">
              <RiDeleteBin6Line className="text-red-400" />
              <span><span className="text-[#e4e4f0]">Удалить</span> — убирает тему из истории</span>
            </div>
          </div>
        </motion.div>
      )}
    </div>
  );
}
