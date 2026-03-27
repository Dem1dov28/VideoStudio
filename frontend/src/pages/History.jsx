import { useEffect, useState, useReducer } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { RiVideoLine, RiLoader4Line, RiCloseLine } from 'react-icons/ri';
import { api } from '../services/api';
import VideoCard from '../components/VideoCard';

const initialState = { videos: [], loading: true, error: false };

function historyReducer(state, action) {
  switch (action.type) {
    case 'loading':
      return { ...initialState, loading: true };
    case 'success':
      return { videos: action.videos || [], loading: false, error: false };
    case 'error':
      return { ...state, loading: false, error: action.isNetwork };
    default:
      return state;
  }
}

export default function History() {
  const [state, dispatch] = useReducer(historyReducer, initialState);
  const [selected, setSelected] = useState(null);
  const { videos, loading, networkError } = {
    videos: state.videos,
    loading: state.loading,
    networkError: state.error,
  };

  const load = () => {
    dispatch({ type: 'loading' });
    fetch('/api/videos')
      .then(r => {
        if (!r.ok) throw new Error(`${r.status}`);
        return r.json();
      })
      .then(r => {
        const list = Array.isArray(r?.videos) ? r.videos : [];
        dispatch({ type: 'success', videos: list });
      })
      .catch(e => {
        dispatch({ type: 'error', isNetwork: /failed to fetch|connection/i.test(e?.message || '') });
      });
  };

  useEffect(() => {
    let cancelled = false;
    dispatch({ type: 'loading' });
    fetch('/api/videos')
      .then(r => {
        if (!r.ok) throw new Error(`${r.status}`);
        return r.json();
      })
      .then(r => {
        const list = Array.isArray(r?.videos) ? r.videos : [];
        if (!cancelled) dispatch({ type: 'success', videos: list });
      })
      .catch(e => {
        if (!cancelled) dispatch({ type: 'error', isNetwork: /failed to fetch|connection/i.test(e?.message || '') });
      });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="max-w-4xl mx-auto px-6 py-10">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <h1 className="text-2xl font-bold text-white mb-1">История видео</h1>
        <p className="text-[#71717a] text-sm">
          {videos.length} видео сгенерировано
        </p>
      </motion.div>

      {loading && !networkError ? (
        <div className="flex items-center justify-center py-24 text-[#71717a] gap-2">
          <RiLoader4Line className="animate-spin text-xl" />
          <span className="text-sm">Загружаем...</span>
        </div>
      ) : networkError ? (
        <div className="text-center py-24 px-4">
          <p className="text-amber-400 text-sm mb-2">Сервер недоступен</p>
          <p className="text-[#52525b] text-xs mb-4">Запустите: python server.py</p>
          <button onClick={load} className="btn-secondary text-sm">Повторить</button>
        </div>
      ) : videos.length === 0 ? (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="text-center py-24"
        >
          <RiVideoLine className="text-5xl text-[#27272f] mx-auto mb-4" />
          <p className="text-[#71717a] text-sm">Видео пока нет.</p>
          <p className="text-[#52525b] text-xs mt-1">Создайте первое на главной странице.</p>
        </motion.div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
          {videos.filter(v => v?.session_id).map((v, i) => (
            <div key={`${v.session_id}-${v.filename || i}`}>
              <VideoCard video={v} onClick={setSelected} onDelete={(sid) => dispatch({ type: 'success', videos: videos.filter(x => x.session_id !== sid) })} />
            </div>
          ))}
        </div>
      )}

      {/* Video modal */}
      <AnimatePresence>
        {selected && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4"
            onClick={() => setSelected(null)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="card overflow-hidden max-w-sm w-full"
              onClick={e => e.stopPropagation()}
            >
              <div className="flex items-center justify-between p-4 border-b border-[#27272f]">
                <span className="text-sm font-semibold text-white truncate pr-4">
                  {selected?.title || `#${(selected?.session_id || '').slice(-8)}`}
                </span>
                <button
                  onClick={() => setSelected(null)}
                  className="text-[#71717a] hover:text-white transition-colors"
                >
                  <RiCloseLine className="text-xl" />
                </button>
              </div>
              <div className="bg-black flex justify-center p-4">
                <video
                  controls
                  autoPlay
                  className="rounded-lg max-h-[70vh]"
                  style={{ maxWidth: '280px' }}
                >
                  <source src={api.videoUrl(selected?.session_id, selected?.filename)} type="video/mp4" />
                </video>
              </div>
              
              {/* Publishing metadata panel */}
              {selected?.publishing && (
                <div className="p-4 space-y-3 border-t border-[#27272f] bg-[#0d0d14]">
                  {/* Title */}
                  <div>
                    <label className="block text-[10px] font-semibold text-[#71717a] uppercase tracking-wider mb-1">
                      Название
                    </label>
                    <div className="flex gap-1.5">
                      <input
                        type="text"
                        value={selected.publishing.title || ''}
                        readOnly
                        className="flex-1 bg-[#1a1a2e] border border-[#27272f] rounded px-2 py-1.5 text-xs text-white"
                      />
                      <button
                        type="button"
                        onClick={() => {
                          navigator.clipboard.writeText(selected.publishing.title || '');
                          alert('Название скопировано!');
                        }}
                        className="text-[10px] bg-brand-400/20 hover:bg-brand-400/30 text-brand-300 px-2.5 py-1.5 rounded transition-colors whitespace-nowrap"
                      >
                        Копия
                      </button>
                    </div>
                  </div>
                  
                  {/* Hashtags */}
                  <div>
                    <label className="block text-[10px] font-semibold text-[#71717a] uppercase tracking-wider mb-1">
                      Хештеги
                    </label>
                    <div className="flex gap-1.5">
                      <input
                        type="text"
                        value={(selected.publishing.hashtags || []).join(' ')}
                        readOnly
                        className="flex-1 bg-[#1a1a2e] border border-[#27272f] rounded px-2 py-1.5 text-xs text-white"
                      />
                      <button
                        type="button"
                        onClick={() => {
                          navigator.clipboard.writeText((selected.publishing.hashtags || []).join(' '));
                          alert('Хештеги скопированы!');
                        }}
                        className="text-[10px] bg-brand-400/20 hover:bg-brand-400/30 text-brand-300 px-2.5 py-1.5 rounded transition-colors whitespace-nowrap"
                      >
                        Копия
                      </button>
                    </div>
                  </div>
                  
                  {/* Description */}
                  <div>
                    <label className="block text-[10px] font-semibold text-[#71717a] uppercase tracking-wider mb-1">
                      Описание
                    </label>
                    <div className="flex gap-1.5">
                      <textarea
                        value={selected.publishing.description || ''}
                        readOnly
                        rows={3}
                        className="flex-1 bg-[#1a1a2e] border border-[#27272f] rounded px-2 py-1.5 text-xs text-white resize-none"
                      />
                      <button
                        type="button"
                        onClick={() => {
                          navigator.clipboard.writeText(selected.publishing.description || '');
                          alert('Описание скопировано!');
                        }}
                        className="text-[10px] bg-brand-400/20 hover:bg-brand-400/30 text-brand-300 px-2.5 py-1.5 rounded transition-colors whitespace-nowrap self-start mt-0.5"
                      >
                        Копия
                      </button>
                    </div>
                  </div>
                  
                  {/* Tags */}
                  <div>
                    <label className="block text-[10px] font-semibold text-[#71717a] uppercase tracking-wider mb-1">
                      Теги
                    </label>
                    <div className="flex gap-1.5">
                      <input
                        type="text"
                        value={(selected.publishing.tags || []).join(', ')}
                        readOnly
                        className="flex-1 bg-[#1a1a2e] border border-[#27272f] rounded px-2 py-1.5 text-xs text-white"
                      />
                      <button
                        type="button"
                        onClick={() => {
                          navigator.clipboard.writeText((selected.publishing.tags || []).join(', '));
                          alert('Теги скопированы!');
                        }}
                        className="text-[10px] bg-brand-400/20 hover:bg-brand-400/30 text-brand-300 px-2.5 py-1.5 rounded transition-colors whitespace-nowrap"
                      >
                        Копия
                      </button>
                    </div>
                  </div>
                </div>
              )}
              
              <div className="p-4 flex gap-2">
                <a
                  href={api.videoUrl(selected?.session_id, selected?.filename)}
                  download
                  className="btn-primary flex items-center gap-2 text-sm flex-1 justify-center"
                >
                  ⬇ Скачать
                </a>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
