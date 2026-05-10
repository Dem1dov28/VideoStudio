import { useEffect, useState, useReducer, useRef, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  RiVideoLine,
  RiLoader4Line,
  RiCloseLine,
  RiFileCopyLine,
  RiRestartLine,
  RiDeleteBinLine,
} from 'react-icons/ri';
import { api } from '../services/api';
import VideoCard from '../components/VideoCard';
import { youtubeSlotsFromStatus } from '../utils/youtubeProfiles';

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
  const [searchParams, setSearchParams] = useSearchParams();
  const [state, dispatch] = useReducer(historyReducer, initialState);
  const [selected, setSelected] = useState(null);
  const [regenBusy, setRegenBusy] = useState(false);
  const [mode5AssembleBusy, setMode5AssembleBusy] = useState(false);
  const [clearAllBusy, setClearAllBusy] = useState(false);
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
      authorized_any: false,
      has_secondary: false,
      profile_order: [],
      profile_list: [],
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
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6 sm:py-10 min-h-0">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <div className="flex flex-wrap items-start justify-between gap-3 mb-1">
          <h1 className="text-2xl font-bold text-white">История видео</h1>
          {videos.length > 0 && !loading && !networkError && (
            <button
              type="button"
              disabled={clearAllBusy}
              onClick={async () => {
                if (
                  !confirm(
                    `Удалить все ${videos.length} видео с диска и убрать их из журнала тем? Действие необратимо.`,
                  )
                )
                  return;
                setClearAllBusy(true);
                try {
                  await api.clearAllVideos();
                  setSelected(null);
                  load();
                } catch (err) {
                  alert(err.message || 'Не удалось очистить историю');
                } finally {
                  setClearAllBusy(false);
                }
              }}
              className="flex items-center gap-2 text-sm font-medium px-3 py-2 rounded-xl border border-red-900/50 bg-red-950/25 text-red-300 hover:bg-red-950/40 hover:border-red-800/60 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
            >
              <RiDeleteBinLine className="text-lg shrink-0" />
              {clearAllBusy ? 'Удаляем…' : 'Очистить всё'}
            </button>
          )}
        </div>
        <p className="text-[#71717a] text-sm">
          {videos.length} видео сгенерировано
        </p>
        <p className="text-[11px] text-[#52525b] mt-2 max-w-xl leading-relaxed">
          Режим «77 фактов»: превью одной сессии показываются одной карточкой; кнопка «Склеить в одно видео» собирает{' '}
          <code className="text-[#71717a]">video_mode5.mp4</code> из всех частей (тот же монтаж, что на экране прогресса).
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
          const slots = youtubeSlotsFromStatus(ytStatus);
          const needOAuth = slots.filter(
            (s) => !s.authorized && s.client_secret_configured !== false,
          );
          if (!needOAuth.length) return null;
          return (
            <div className="mt-4 flex flex-wrap items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2">
              <span className="text-xs text-amber-200/90">YouTube: войти в Google</span>
              {needOAuth.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  className="text-xs font-medium px-2 py-1 rounded bg-amber-500/20 hover:bg-amber-500/30 text-amber-100"
                  onClick={async () => {
                    try {
                      const r = await api.youtubeOAuthStart(s.id);
                      if (r?.authorization_url) window.open(r.authorization_url, '_blank', 'noopener,noreferrer');
                    } catch (e) {
                      alert(e.message || String(e));
                    }
                  }}
                >
                  {s.label || s.id}
                  {s.gcp_project ? ` (${s.gcp_project})` : ''}
                </button>
              ))}
            </div>
          );
        })()}
        {!ytLoading && ytStatus?.client_configured && (() => {
          const slots = youtubeSlotsFromStatus(ytStatus);
          const allOk =
            slots.length > 0 && slots.every((s) => s.authorized);
          if (!allOk) return null;
          return (
            <p className="mt-3 text-xs text-emerald-400/90">
              YouTube API:{' '}
              {slots.length > 1 ? `подключены все слоты (${slots.length})` : 'канал подключён'}
            </p>
          );
        })()}
        {!ytLoading && ytStatus?.client_configured && (() => {
          const slots = youtubeSlotsFromStatus(ytStatus);
          const someOk = slots.some((s) => s.authorized);
          const allOk = slots.length > 0 && slots.every((s) => s.authorized);
          if (!someOk || allOk || slots.length <= 1) return null;
          return (
            <p className="mt-3 text-[11px] text-[#a1a1aa]">
              Часть слотов подключена. Для остальных нажми соответствующую кнопку выше и при входе в Google выбери нужный канал / brand account.
            </p>
          );
        })()}
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
                    'Сбросить все сохранённые входы YouTube на этом компьютере? Файлы токенов удалятся, нужно снова пройти OAuth для каждого слота.',
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
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 sm:gap-4 items-start content-start">
          {videos.filter(v => v?.session_id).map((v, i) => (
            <div
              key={`${v.session_id}-${v.filename || i}`}
              className="min-w-0 self-start w-full"
            >
              <VideoCard
                video={v}
                onClick={setSelected}
                onOpenProgress={(sid) => navigate(`/run/${sid}`)}
                onListRefresh={load}
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
                  {selected?.mode5_can_assemble && (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (!selected?.session_id) return;
                        setSelected(null);
                        navigate(`/run/${selected.session_id}`);
                      }}
                      className="btn-secondary flex items-center justify-center gap-2 text-sm w-full"
                    >
                      Открыть редактирование фрагментов
                    </button>
                  )}
                  {selected?.mode5_can_assemble && (
                    <button
                      type="button"
                      disabled={mode5AssembleBusy}
                      onClick={async (e) => {
                        e.stopPropagation();
                        const sid = selected?.session_id;
                        if (!sid) return;
                        setMode5AssembleBusy(true);
                        try {
                          await api.mode5Assemble(sid);
                          setSelected(null);
                          load();
                        } catch (err) {
                          alert(err.message || 'Не удалось склеить видео');
                        } finally {
                          setMode5AssembleBusy(false);
                        }
                      }}
                      className="btn-primary flex items-center justify-center gap-2 text-sm w-full bg-emerald-600 hover:bg-emerald-500 border-emerald-500/40"
                    >
                      {mode5AssembleBusy ? 'Монтаж…' : 'Склеить все части в одно видео'}
                    </button>
                  )}
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
                          const ruVar = (ru?.title_variants || []).map((t, i) => `  ${String.fromCharCode(65 + i)}: ${t}`).join('\n');
                          const enVar = (en?.title_variants || []).map((t, i) => `  ${String.fromCharCode(65 + i)}: ${t}`).join('\n');
                          const text = `🇷🇺 Русская версия

Название: ${ru?.title || ''}
${ruVar ? `Варианты:\n${ruVar}\n` : ''}
Описание: ${ru?.description || ''}

Теги: ${(ru?.tags || []).join(', ')}

Первый комментарий: ${ru?.first_comment || ''}

🇬🇧 English Version

Title: ${en?.title || ''}
${enVar ? `Variants:\n${enVar}\n` : ''}
Description: ${en?.description || ''}

Tags: ${(en?.tags || []).join(', ')}

First comment: ${en?.first_comment || ''}`;
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
                            Название (основное)
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
                        {Array.isArray(selected.publishing.ru.title_variants) && selected.publishing.ru.title_variants.length > 0 && (
                          <div className="space-y-2">
                            <label className="block text-[10px] font-semibold text-[#71717a] uppercase tracking-wider">
                              Варианты заголовка (A / B / C)
                            </label>
                            {selected.publishing.ru.title_variants.map((t, i) => (
                              <div key={i} className="flex gap-2 items-center">
                                <span className="text-xs text-[#52525b] w-6 font-mono shrink-0">{String.fromCharCode(65 + i)}</span>
                                <input
                                  type="text"
                                  value={t || ''}
                                  readOnly
                                  className="flex-1 bg-[#1a1a2e] border border-[#27272f] rounded px-3 py-2 text-sm text-white min-w-0"
                                />
                                <button
                                  type="button"
                                  onClick={() => navigator.clipboard.writeText(t || '')}
                                  className="text-sm bg-brand-400/20 hover:bg-brand-400/30 text-brand-300 px-3 py-2 rounded shrink-0"
                                >
                                  📋
                                </button>
                              </div>
                            ))}
                          </div>
                        )}
                        
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
                        {selected.publishing.ru.first_comment ? (
                          <div>
                            <label className="block text-[10px] font-semibold text-[#71717a] uppercase tracking-wider mb-1.5">
                              Первый комментарий
                            </label>
                            <div className="flex gap-2">
                              <textarea
                                value={selected.publishing.ru.first_comment || ''}
                                readOnly
                                rows={3}
                                className="flex-1 bg-[#1a1a2e] border border-[#27272f] rounded px-3 py-2 text-sm text-white resize-none"
                              />
                              <button
                                type="button"
                                onClick={() => navigator.clipboard.writeText(selected.publishing.ru.first_comment || '')}
                                className="text-sm bg-brand-400/20 hover:bg-brand-400/30 text-brand-300 px-3 py-2 rounded self-start"
                              >
                                📋
                              </button>
                            </div>
                          </div>
                        ) : null}
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
                            Title (primary)
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
                        {Array.isArray(selected.publishing.en.title_variants) && selected.publishing.en.title_variants.length > 0 && (
                          <div className="space-y-2">
                            <label className="block text-[10px] font-semibold text-[#71717a] uppercase tracking-wider">
                              Title variants (A / B / C)
                            </label>
                            {selected.publishing.en.title_variants.map((t, i) => (
                              <div key={i} className="flex gap-2 items-center">
                                <span className="text-xs text-[#52525b] w-6 font-mono shrink-0">{String.fromCharCode(65 + i)}</span>
                                <input
                                  type="text"
                                  value={t || ''}
                                  readOnly
                                  className="flex-1 bg-[#1a1a2e] border border-[#27272f] rounded px-3 py-2 text-sm text-white min-w-0"
                                />
                                <button
                                  type="button"
                                  onClick={() => navigator.clipboard.writeText(t || '')}
                                  className="text-sm bg-brand-400/20 hover:bg-brand-400/30 text-brand-300 px-3 py-2 rounded shrink-0"
                                >
                                  📋
                                </button>
                              </div>
                            ))}
                          </div>
                        )}
                        
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
                        {selected.publishing.en.first_comment ? (
                          <div>
                            <label className="block text-[10px] font-semibold text-[#71717a] uppercase tracking-wider mb-1.5">
                              First comment
                            </label>
                            <div className="flex gap-2">
                              <textarea
                                value={selected.publishing.en.first_comment || ''}
                                readOnly
                                rows={3}
                                className="flex-1 bg-[#1a1a2e] border border-[#27272f] rounded px-3 py-2 text-sm text-white resize-none"
                              />
                              <button
                                type="button"
                                onClick={() => navigator.clipboard.writeText(selected.publishing.en.first_comment || '')}
                                className="text-sm bg-brand-400/20 hover:bg-brand-400/30 text-brand-300 px-3 py-2 rounded self-start"
                              >
                                📋
                              </button>
                            </div>
                          </div>
                        ) : null}
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
