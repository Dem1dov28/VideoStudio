import { useEffect, useState, useReducer, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { RiVideoLine, RiLoader4Line, RiCloseLine, RiRestartLine } from 'react-icons/ri';
import { api } from '../services/api';
import { useNavigate, useSearchParams } from 'react-router-dom';
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
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [state, dispatch] = useReducer(historyReducer, initialState);
  const [selected, setSelected] = useState(null);
  const [regenBusy, setRegenBusy] = useState(false);
  const [ytStatus, setYtStatus] = useState(null);
  /** Пока true — не полагаемся на ytStatus (быстрый первый paint без «пропавшей» кнопки). */
  const [ytLoading, setYtLoading] = useState(true);
  const ytReqId = useRef(0);
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

  const refreshYoutubeStatus = useCallback(() => {
    const id = ++ytReqId.current;
    setYtLoading(true);
    const fallback = {
      client_configured: true,
      authorized: false,
      has_secondary: false,
      status_fetch_failed: true,
      profiles: {
        primary: {
          authorized: false,
          label: 'Канал 1',
          token_file: '',
          channels: [],
          channel_hint: '',
        },
      },
    };

    (async () => {
      let alreadyFull = false;
      try {
        // Сначала быстрый ответ с диска — кнопки/слоты видны без ожидания Google API.
        const q = await api.youtubeStatus(true);
        if (id !== ytReqId.current) return;
        setYtStatus(q);
      } catch (e1) {
        console.warn('[YouTube] quick status failed, try full:', e1);
        try {
          const f = await api.youtubeStatus(false);
          if (id !== ytReqId.current) return;
          setYtStatus(f);
          alreadyFull = true;
        } catch (e2) {
          console.warn('[YouTube] status недоступен:', e2);
          if (id !== ytReqId.current) return;
          setYtStatus(fallback);
        }
      } finally {
        if (id === ytReqId.current) setYtLoading(false);
      }

      if (alreadyFull || id !== ytReqId.current) return;
      // Подтянуть подсказки каналов (channels.list) без блокировки UI.
      api
        .youtubeStatus(false)
        .then((full) => {
          if (id !== ytReqId.current) return;
          setYtStatus(full);
        })
        .catch(() => {});
    })();
  }, []);

  useEffect(() => {
    refreshYoutubeStatus();
  }, [refreshYoutubeStatus]);

  useEffect(() => {
    const ok = searchParams.get('youtube_oauth');
    const err = searchParams.get('youtube_error');
    if (ok === 'ok') {
      alert('YouTube подключён — можно заливать Shorts.');
      setSearchParams({}, { replace: true });
      refreshYoutubeStatus();
      return;
    }
    if (err) {
      alert(`YouTube OAuth: ${decodeURIComponent(err)}`);
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams, refreshYoutubeStatus]);

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
        {ytLoading && (
          <p className="mt-3 text-[11px] text-[#a1a1aa] flex items-center gap-2">
            <RiLoader4Line className="animate-spin text-base shrink-0" />
            <span>YouTube: получаем статус аккаунтов…</span>
          </p>
        )}
        {ytStatus?.status_fetch_failed && !ytLoading && (
          <p className="mt-3 text-[11px] text-amber-400/90">
            Статус YouTube не удалось загрузить с сервера (сеть или ошибка API). Кнопка «Залить» видна;
            если заливка падает — смотри лог <code className="text-[#a1a1aa]">python server.py</code>.
          </p>
        )}
        {!ytLoading && ytStatus?.client_configured && (() => {
          const p = ytStatus.profiles;
          const needP = !p?.primary?.authorized;
          const needS = ytStatus.has_secondary && !p?.secondary?.authorized;
          if (!needP && !needS) return null;
          return (
            <div className="mt-4 flex flex-wrap items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2">
              <span className="text-xs text-amber-200/90">YouTube: войти в Google</span>
              {needP && (
                <button
                  type="button"
                  className="text-xs font-medium px-2 py-1 rounded bg-amber-500/20 hover:bg-amber-500/30 text-amber-100"
                  onClick={async () => {
                    try {
                      const r = await api.youtubeOAuthStart('primary');
                      if (r?.authorization_url) window.open(r.authorization_url, '_blank', 'noopener,noreferrer');
                    } catch (e) {
                      alert(e.message || String(e));
                    }
                  }}
                >
                  {ytStatus?.profiles?.primary?.label || 'Канал 1'}
                </button>
              )}
              {needS && (
                <button
                  type="button"
                  className="text-xs font-medium px-2 py-1 rounded bg-amber-500/20 hover:bg-amber-500/30 text-amber-100"
                  onClick={async () => {
                    try {
                      const r = await api.youtubeOAuthStart('secondary');
                      if (r?.authorization_url) window.open(r.authorization_url, '_blank', 'noopener,noreferrer');
                    } catch (e) {
                      alert(e.message || String(e));
                    }
                  }}
                >
                  {ytStatus?.profiles?.secondary?.label || 'Канал 2'}
                </button>
              )}
            </div>
          );
        })()}
        {!ytLoading && ytStatus?.client_configured && ytStatus?.profiles?.primary?.authorized &&
          (!ytStatus.has_secondary || ytStatus?.profiles?.secondary?.authorized) && (
          <p className="mt-3 text-xs text-emerald-400/90">
            YouTube API: {ytStatus.has_secondary ? 'оба канала подключены' : 'канал подключён'}
          </p>
        )}
        {!ytLoading && ytStatus?.client_configured && ytStatus?.profiles?.primary?.authorized &&
          ytStatus.has_secondary && !ytStatus?.profiles?.secondary?.authorized && (
          <p className="mt-3 text-[11px] text-[#a1a1aa]">
            Канал 1 готов. Для второго канала нажми «Канал 2» и при входе в Google выбери нужный канал / brand account.
          </p>
        )}
        {!ytLoading && ytStatus && !ytStatus.client_configured && (
          <p className="mt-3 text-[11px] text-[#52525b]">
            Прямой YouTube: укажи в .env <code className="text-[#71717a]">YOUTUBE_OAUTH_CLIENT_SECRETS</code> (см. .env.example)
          </p>
        )}
        {(ytLoading || ytStatus?.client_configured) && (
          <div className="mt-3">
            <button
              type="button"
              disabled={ytLoading}
              className="text-[11px] text-[#71717a] hover:text-red-400 underline underline-offset-2 disabled:opacity-40 disabled:cursor-not-allowed disabled:no-underline"
              onClick={async () => {
                if (
                  !confirm(
                    'Сбросить все сохранённые входы YouTube на этом компьютере? Файлы токенов удалятся, нужно снова нажать «Канал 1» / «Канал 2».',
                  )
                )
                  return;
                try {
                  const r = await api.youtubeResetTokens();
                  alert(
                    Array.isArray(r?.removed) && r.removed.length
                      ? `Удалено: ${r.removed.join(', ')}`
                      : 'Токенов на диске не было.',
                  );
                  refreshYoutubeStatus();
                } catch (e) {
                  alert(e.message || String(e));
                }
              }}
            >
              Сбросить все аккаунты YouTube
            </button>
          </div>
        )}
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
              <VideoCard
                video={v}
                onClick={setSelected}
                onDelete={(sid) => dispatch({ type: 'success', videos: videos.filter(x => x.session_id !== sid) })}
                youtubeStatus={ytStatus}
                youtubeLoading={ytLoading}
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
            className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4"
            onClick={() => setSelected(null)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="card overflow-hidden max-w-5xl w-full grid grid-cols-1 md:grid-cols-2"
              onClick={e => e.stopPropagation()}
            >
              {/* Video section (right side on desktop) */}
              <div className="md:col-start-2 md:row-start-1 bg-black flex flex-col">
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
                <div className="flex-1 bg-black flex items-center justify-center p-4">
                  <video
                    controls
                    autoPlay
                    className="rounded-lg max-h-[60vh] w-full"
                  >
                    <source src={api.videoUrl(selected?.session_id, selected?.filename)} type="video/mp4" />
                  </video>
                </div>
                <div className="p-4 border-t border-[#27272f]">
                  <a
                    href={api.videoUrl(selected?.session_id, selected?.filename)}
                    download
                    className="btn-primary flex items-center justify-center gap-2 text-sm w-full"
                  >
                    ⬇ Скачать
                  </a>
                </div>
              </div>
              
              {/* Text content section (left side on desktop) */}
              <div className="md:col-start-1 md:row-start-1 bg-[#0d0d14] overflow-y-auto max-h-[80vh]">
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
                
                {/* Download and Regenerate buttons */}
                <div className="p-4 flex flex-col gap-2 border-t border-[#27272f]">
                  <div className="flex gap-2">
                    <a
                      href={api.videoUrl(selected?.session_id, selected?.filename)}
                      download
                      className="btn-primary flex items-center gap-2 text-sm flex-1 justify-center"
                    >
                      ⬇ Скачать
                    </a>
                  </div>
                  {selected?.can_regenerate && (
                    <button
                      type="button"
                      disabled={regenBusy}
                      onClick={async () => {
                        if (!selected?.session_id) return;
                        const fn = (selected.filename || '').toLowerCase();
                        const enOnly = fn === 'video_en.mp4';
                        const ruOnly = fn === 'video_ru.mp4';
                        const msg = enOnly
                          ? 'Перегенерировать только английскую версию? Файлы этой сессии будут удалены, затем создастся новая сессия с одним EN-роликом.'
                          : ruOnly
                            ? 'Перегенерировать только русскую версию? Файлы этой сессии будут удалены, затем создастся новая сессия с одним RU-роликом.'
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
                        } catch (e) {
                          alert(e.message || 'Не удалось запустить перегенерацию');
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
                      Перегенерация недоступна: нет сохранённых параметров (создайте ролик ещё раз после обновления — дальше кнопка появится).
                    </p>
                  )}
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
