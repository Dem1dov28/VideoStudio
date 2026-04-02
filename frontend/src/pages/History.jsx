import { useEffect, useState, useReducer } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  RiVideoLine,
  RiLoader4Line,
  RiCloseLine,
  RiFileCopyLine,
  RiRestartLine,
} from 'react-icons/ri';
import { api } from '../services/api';
import VideoCard from '../components/VideoCard';

const initialState = { videos: [], loading: true, error: false };

/** Убрать суффикс « (RU)» / « (EN)» из заголовка карточки — иногда там полный текст цитаты. */
function titleAsQuoteFallback(v) {
  const t = typeof v?.title === 'string' ? v.title.trim() : '';
  if (!t) return '';
  return t.replace(/\s*\((RU|EN)\)\s*$/i, '').trim() || t;
}

/** Текст подписи цитаты для выбранной карточки (RU/EN по языку ролика). */
function quoteCaptionForCard(v) {
  if (!v) return '';
  const ru = typeof v.quote_caption_ru === 'string' ? v.quote_caption_ru.trim() : '';
  const en = typeof v.quote_caption_en === 'string' ? v.quote_caption_en.trim() : '';
  const fallback = titleAsQuoteFallback(v);
  if (v.video_lang === 'en') return en || ru || fallback;
  if (v.video_lang === 'ru') return ru || en || fallback;
  return ru || en || fallback;
}

async function copyTextToClipboard(text) {
  const s = text == null ? '' : String(text);
  if (!s.trim()) return;
  try {
    await navigator.clipboard.writeText(s);
  } catch {
    const textarea = document.createElement('textarea');
    textarea.value = s;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
  }
}

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
  const navigate = useNavigate();
  const [state, dispatch] = useReducer(historyReducer, initialState);
  const [selected, setSelected] = useState(null);
  const [regenBusy, setRegenBusy] = useState(false);
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
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6 sm:py-10 min-h-0">
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
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 sm:gap-4 items-start content-start">
          {videos.filter(v => v?.session_id).map((v, i) => (
            <div
              key={`${v.session_id}-${v.filename || i}`}
              className="min-w-0 self-start w-full"
            >
              <VideoCard
                video={v}
                onClick={setSelected}
                onDelete={(sid, fname) =>
                  dispatch({
                    type: 'success',
                    videos: videos.filter((x) =>
                      fname
                        ? !(x.session_id === sid && x.filename === fname)
                        : x.session_id !== sid,
                    ),
                  })
                }
              />
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
            className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-start sm:items-center justify-center p-3 sm:p-4 overflow-y-auto overscroll-contain"
            onClick={() => setSelected(null)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="card max-w-5xl w-full max-h-[calc(100dvh-1.25rem)] md:max-h-[min(92vh,100dvh-1.5rem)] md:h-[min(92vh,100dvh-1.5rem)] grid grid-cols-1 md:grid-cols-2 md:grid-rows-1 min-h-0 overflow-y-auto md:overflow-hidden my-2 sm:my-auto"
              onClick={e => e.stopPropagation()}
            >
              {/* Video section (right side on desktop) */}
              <div className="md:col-start-2 md:row-start-1 bg-black flex flex-col min-h-0 md:h-full">
                <div className="flex items-center justify-between p-4 border-b border-[#27272f] md:border-b-0">
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
                <div className="flex-1 min-h-0 bg-black flex items-center justify-center p-2 sm:p-3 overflow-hidden max-h-[min(30svh,200px)] sm:max-h-[min(36svh,240px)] md:max-h-none md:min-h-[12rem]">
                  <video
                    controls
                    autoPlay
                    className="rounded-lg max-h-full max-w-full w-auto h-auto object-contain"
                  >
                    <source src={api.videoUrl(selected?.session_id, selected?.filename)} type="video/mp4" />
                  </video>
                </div>
                {(() => {
                  const qt = quoteCaptionForCard(selected);
                  if (!qt) return null;
                  return (
                    <div className="px-3 sm:px-4 py-2.5 border-t border-[#27272f] shrink-0 bg-[#0a0a0f]">
                      <div className="flex items-start gap-2">
                        <p className="text-sm text-[#e4e4f0] leading-snug flex-1 min-w-0 max-h-[28vh] sm:max-h-[22vh] overflow-y-auto">
                          {qt}
                        </p>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            copyTextToClipboard(qt);
                          }}
                          className="shrink-0 flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded-lg bg-brand-400/20 hover:bg-brand-400/30 text-brand-300 transition-colors"
                          title="Копировать цитату"
                        >
                          <RiFileCopyLine className="text-base" />
                          Копировать
                        </button>
                      </div>
                    </div>
                  );
                })()}
                <div className="p-3 sm:p-4 border-t border-[#27272f] flex flex-col gap-2 shrink-0">
                  <a
                    href={api.videoUrl(selected?.session_id, selected?.filename)}
                    download
                    className="btn-primary flex items-center justify-center gap-2 text-sm w-full"
                  >
                    ⬇ Скачать
                  </a>
                  {selected?.can_regenerate && (
                    <button
                      type="button"
                      disabled={regenBusy}
                      onClick={async (e) => {
                        e.stopPropagation();
                        if (!selected?.session_id) return;
                        const fn = (selected.filename || '').toLowerCase();
                        const enOnly = fn === 'video_en.mp4';
                        const ruOnly = fn === 'video_ru.mp4';
                        const msg = enOnly
                          ? 'Перегенерировать только английскую версию? Русский ролик сохранится в новой сессии вместе с новым EN.'
                          : ruOnly
                            ? 'Перегенерировать только русскую версию? Английский ролик сохранится в новой сессии вместе с новым RU.'
                            : 'Перегенерировать это видео с теми же параметрами? Текущие файлы сессии будут удалены.';
                        if (!confirm(msg)) return;
                        setRegenBusy(true);
                        try {
                          const res = await api.regenerateVideo(selected.session_id, {
                            filename: selected.filename || undefined,
                          });
                          const newSid = res?.session_id;
                          if (newSid) {
                            setSelected(null);
                            navigate(`/run/${newSid}`);
                          }
                        } catch (err) {
                          alert(err.message || 'Не удалось запустить перегенерацию');
                        } finally {
                          setRegenBusy(false);
                        }
                      }}
                      className="btn-secondary flex items-center justify-center gap-2 text-sm w-full"
                    >
                      <RiRestartLine className="text-lg" />
                      {regenBusy ? 'Запуск…' : 'Перегенерировать'}
                    </button>
                  )}
                  {selected && !selected.can_regenerate && (
                    <p className="text-[10px] text-[#52525b] text-center leading-snug">
                      Перегенерация недоступна: нет сохранённых параметров.
                    </p>
                  )}
                </div>
              </div>
              
              {/* Text content section (left side on desktop) */}
              <div className="md:col-start-1 md:row-start-1 bg-[#0d0d14] overflow-y-auto min-h-0 md:h-full md:max-h-full">
                {selected &&
                  (() => {
                    const quoteText = quoteCaptionForCard(selected);
                    if (!quoteText) return null;
                    return (
                      <div className="hidden md:block p-5 border-b border-[#27272f]">
                        <div className="flex items-center justify-between gap-2 mb-2">
                          <h3 className="text-xs font-semibold text-[#71717a] uppercase tracking-wider">
                            Цитата
                          </h3>
                          <button
                            type="button"
                            onClick={() => copyTextToClipboard(quoteText)}
                            className="text-xs font-medium px-2.5 py-1 rounded bg-brand-400/20 hover:bg-brand-400/30 text-brand-300 transition-colors"
                          >
                            Копировать цитату
                          </button>
                        </div>
                        <p className="text-[#e4e4f0] text-sm leading-relaxed whitespace-pre-wrap">
                          {quoteText}
                        </p>
                      </div>
                    );
                  })()}
                {selected?.publishing ? (
                  <div className="p-5 space-y-6">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-base font-bold text-white">Публикация</h3>
                      <button
                        type="button"
                        onClick={() => {
                          const ru = selected.publishing.ru;
                          const en = selected.publishing.en;
                          const text = `🇷🇺 Русская версия

Название: ${ru?.title || ''}

Описание: ${ru?.description || ''}

Теги: ${(ru?.tags || []).join(', ')}

🇬🇧 English Version

Title: ${en?.title || ''}

Description: ${en?.description || ''}

Tags: ${(en?.tags || []).join(', ')}`;
                          navigator.clipboard.writeText(text);
                        }}
                        className="text-sm bg-brand-400/20 hover:bg-brand-400/30 text-brand-300 px-3 py-1.5 rounded transition-colors font-medium"
                        title="Копировать всё"
                      >
                        📋 Копировать всё
                      </button>
                    </div>
                    
                    {/* Russian Version */}
                    {selected.publishing.ru && (
                      <div className="space-y-4">
                        <div className="flex items-center gap-2 border-b border-[#27272f] pb-2">
                          <span className="text-lg">🇷🇺</span>
                          <h4 className="text-sm font-semibold text-brand-300 uppercase tracking-wider">Русская версия</h4>
                        </div>
                        
                        {/* Title RU */}
                        <div>
                          <label className="block text-[10px] font-semibold text-[#71717a] uppercase tracking-wider mb-1.5">
                            Название
                          </label>
                          <div className="flex gap-2">
                            <input
                              type="text"
                              value={selected.publishing.ru.title || ''}
                              readOnly
                              className="flex-1 bg-[#1a1a2e] border border-[#27272f] rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-400/50"
                            />
                            <button
                              type="button"
                              onClick={() => {
                                navigator.clipboard.writeText(selected.publishing.ru.title || '');
                              }}
                              className="text-sm bg-brand-400/20 hover:bg-brand-400/30 text-brand-300 px-3 py-2 rounded transition-colors whitespace-nowrap font-medium"
                              title="Скопировать"
                            >
                              📋
                            </button>
                          </div>
                        </div>
                        
                        {/* Description RU */}
                        <div>
                          <label className="block text-[10px] font-semibold text-[#71717a] uppercase tracking-wider mb-1.5">
                            Описание
                          </label>
                          <div className="flex gap-2">
                            <textarea
                              value={selected.publishing.ru.description || ''}
                              readOnly
                              rows={6}
                              className="flex-1 bg-[#1a1a2e] border border-[#27272f] rounded px-3 py-2 text-sm text-white resize-none focus:outline-none focus:border-brand-400/50"
                            />
                            <button
                              type="button"
                              onClick={() => {
                                navigator.clipboard.writeText(selected.publishing.ru.description || '');
                              }}
                              className="text-sm bg-brand-400/20 hover:bg-brand-400/30 text-brand-300 px-3 py-2 rounded transition-colors whitespace-nowrap font-medium self-start"
                              title="Скопировать"
                            >
                              📋
                            </button>
                          </div>
                        </div>
                        
                        {/* Tags RU */}
                        <div>
                          <label className="block text-[10px] font-semibold text-[#71717a] uppercase tracking-wider mb-1.5">
                            Теги
                          </label>
                          <div className="flex gap-2">
                            <input
                              type="text"
                              value={(selected.publishing.ru.tags || []).join(', ')}
                              readOnly
                              className="flex-1 bg-[#1a1a2e] border border-[#27272f] rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-400/50"
                            />
                            <button
                              type="button"
                              onClick={() => {
                                navigator.clipboard.writeText((selected.publishing.ru.tags || []).join(', '));
                              }}
                              className="text-sm bg-brand-400/20 hover:bg-brand-400/30 text-brand-300 px-3 py-2 rounded transition-colors whitespace-nowrap font-medium"
                              title="Скопировать"
                            >
                              📋
                            </button>
                          </div>
                        </div>
                      </div>
                    )}
                    
                    {/* English Version */}
                    {selected.publishing.en && (
                      <div className="space-y-4">
                        <div className="flex items-center gap-2 border-t border-[#27272f] pt-4">
                          <span className="text-lg">🇬🇧</span>
                          <h4 className="text-sm font-semibold text-brand-300 uppercase tracking-wider">English Version</h4>
                        </div>
                        
                        {/* Title EN */}
                        <div>
                          <label className="block text-[10px] font-semibold text-[#71717a] uppercase tracking-wider mb-1.5">
                            Title
                          </label>
                          <div className="flex gap-2">
                            <input
                              type="text"
                              value={selected.publishing.en.title || ''}
                              readOnly
                              className="flex-1 bg-[#1a1a2e] border border-[#27272f] rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-400/50"
                            />
                            <button
                              type="button"
                              onClick={() => {
                                navigator.clipboard.writeText(selected.publishing.en.title || '');
                              }}
                              className="text-sm bg-brand-400/20 hover:bg-brand-400/30 text-brand-300 px-3 py-2 rounded transition-colors whitespace-nowrap font-medium"
                              title="Copy"
                            >
                              📋
                            </button>
                          </div>
                        </div>
                        
                        {/* Description EN */}
                        <div>
                          <label className="block text-[10px] font-semibold text-[#71717a] uppercase tracking-wider mb-1.5">
                            Description
                          </label>
                          <div className="flex gap-2">
                            <textarea
                              value={selected.publishing.en.description || ''}
                              readOnly
                              rows={6}
                              className="flex-1 bg-[#1a1a2e] border border-[#27272f] rounded px-3 py-2 text-sm text-white resize-none focus:outline-none focus:border-brand-400/50"
                            />
                            <button
                              type="button"
                              onClick={() => {
                                navigator.clipboard.writeText(selected.publishing.en.description || '');
                              }}
                              className="text-sm bg-brand-400/20 hover:bg-brand-400/30 text-brand-300 px-3 py-2 rounded transition-colors whitespace-nowrap font-medium self-start"
                              title="Copy"
                            >
                              📋
                            </button>
                          </div>
                        </div>
                        
                        {/* Tags EN */}
                        <div>
                          <label className="block text-[10px] font-semibold text-[#71717a] uppercase tracking-wider mb-1.5">
                            Tags
                          </label>
                          <div className="flex gap-2">
                            <input
                              type="text"
                              value={(selected.publishing.en.tags || []).join(', ')}
                              readOnly
                              className="flex-1 bg-[#1a1a2e] border border-[#27272f] rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-400/50"
                            />
                            <button
                              type="button"
                              onClick={() => {
                                navigator.clipboard.writeText((selected.publishing.en.tags || []).join(', '));
                              }}
                              className="text-sm bg-brand-400/20 hover:bg-brand-400/30 text-brand-300 px-3 py-2 rounded transition-colors whitespace-nowrap font-medium"
                              title="Copy"
                            >
                              📋
                            </button>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="p-5">
                    <p className="text-[#71717a] text-sm">Нет данных для публикации</p>
                  </div>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
