import { useEffect, useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  RiArrowLeftLine,
  RiDownloadLine,
  RiVideoLine,
  RiCheckboxCircleLine,
  RiPauseLine,
  RiPlayLine,
  RiStopLine,
  RiRestartLine,
  RiFileTextLine,
  RiFileCopyLine,
  RiCheckLine,
} from 'react-icons/ri';
import { subscribeToStream, api } from '../services/api';
import LogConsole from '../components/LogConsole';
import StepIndicator from '../components/StepIndicator';

const MODE_LABELS = { 1: '5 фактов', 2: 'Почему X?', 3: 'Реставрация', 4: 'Цитата', 5: 'Длинные', 6: 'Релакс', 7: '2 клипа', 8: 'Было→стало' };

function downloadTextFile(filename, text) {
  if (text == null || text === '') return;
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export default function Progress() {
  const { sid } = useParams();
  const navigate = useNavigate();

  const [logs, setLogs]   = useState([]);
  const [done, setDone]   = useState(null);   // result object
  const [error, setError] = useState('');
  const [status, setStatus] = useState('running');  // running | paused | cancelled | error
  const [busy, setBusy]   = useState(false);
  const [sessionTopic, setSessionTopic] = useState('');
  const [sessionMode, setSessionMode] = useState(1);
  const [copied, setCopied] = useState('');

  useEffect(() => {
    setLogs([]);
    setDone(null);
    setError('');
    setStatus('running');
    setBusy(false);
    setSessionTopic('');
    setSessionMode(1);
    setCopied('');

    let cancelled = false;

    (async () => {
      try {
        const r = await api.getPipelineStatus(sid);
        if (cancelled) return;
        setStatus(r.status || 'running');
        setSessionTopic(r.topic || '');
        setSessionMode(typeof r.mode === 'number' ? r.mode : 1);
        if (r.status === 'done' && r.result) {
          setDone({ ...r.result, session_id: r.result.session_id || sid });
        } else if (r.status === 'error' && r.error) {
          setError(r.error);
        } else if (r.status === 'cancelled') {
          setStatus('cancelled');
          setError(r.error || 'Генерация отменена');
        }
      } catch (e) {
        if (!cancelled) {
          setStatus('error');
          setError(e.message || 'Сессия не найдена на сервере');
        }
      }
    })();

    const cleanup = subscribeToStream(
      sid,
      (entry) => {
        if (!cancelled) setLogs((prev) => [...prev, entry]);
      },
      (result) => {
        if (!cancelled) {
          setDone({ ...result, session_id: result.session_id || sid });
        }
      },
      (err) => {
        if (!cancelled) {
          setError(String(err));
          setStatus('error');
        }
      },
    );

    return () => {
      cancelled = true;
      cleanup();
    };
  }, [sid]);

  // Video URL(s) from result — один файл или несколько (Mode 4 bilingual)
  const videoUrls = useMemo(() => {
    if (!done) return [];
    
    // Debug logging for troubleshooting
    console.log('[Progress] done result:', {
      video_path: done.video_path,
      video_paths: done.video_paths,
      session_id: done.session_id,
      publishing: done.publishing,
    });
    
    const base = done.session_id || sid;
    const paths = done.video_paths && done.video_paths.length > 0
      ? done.video_paths
      : done.video_path
        ? [done.video_path]
        : [];
    
    if (paths.length === 0) {
      console.warn('[Progress] No video paths found in result:', done);
    }
    
    const prefix = import.meta.env.VITE_API_URL || '';
    return paths.map(p => {
      const fname = (p || "").split(/[/\\]/).pop();
      return {
        url: `${prefix}/api/video/${base}/${fname}`,
        label: (p || "").includes("video_ru") ? "RU" : (p || "").includes("video_en") ? "EN" : null,
      };
    });
  }, [done, sid]);

  // Copy to clipboard helper
  const copyToClipboard = async (text, field) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(field);
      setTimeout(() => setCopied(''), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  return (
    <div className="max-w-2xl mx-auto px-6 py-10">
      {/* Back */}
      <button
        onClick={() => navigate('/')}
        className="flex items-center gap-1.5 text-[#71717a] hover:text-[#e4e4f0] text-sm mb-6 transition-colors"
      >
        <RiArrowLeftLine /> Назад
      </button>

      {/* Title */}
      <div className="mb-6">
        <div className="mb-4 p-3 rounded-xl bg-[#14141c] border border-[#27272f]">
          <p className="text-[10px] font-semibold text-brand-400/90 uppercase tracking-wider mb-1">
            Сейчас на экране
          </p>
          <p className="text-sm text-[#e4e4f0] font-medium leading-snug line-clamp-4">
            {sessionTopic || (done?.topic) || 'Загрузка описания…'}
          </p>
          <p className="text-xs text-[#71717a] mt-1.5 flex flex-wrap items-center gap-x-1">
            <span>Режим:</span>
            <span className="text-[#a1a1aa]">{MODE_LABELS[sessionMode] ?? sessionMode}</span>
            <span className="text-[#3f3f46]">·</span>
            <span className="font-mono text-[#52525b]">session …{sid?.slice(-8)}</span>
          </p>
        </div>
        <h1 className="text-xl font-bold text-white">
          {done
            ? '🎉 Видео готово!'
            : status === 'cancelled'
              ? '⏹️ Остановлено'
              : error
                ? '❌ Ошибка'
                : status === 'paused'
                  ? '⏸️ На паузе'
                  : '⚙️ Генерация...'}
        </h1>
        {!done?.quote_caption_ru && !done?.quote_caption_en && (done?.quote_caption || done?.topic) && (
          <p className="text-[#d4d4d8] text-sm mt-1 leading-relaxed whitespace-pre-wrap">
            {done.quote_caption || done.topic}
          </p>
        )}
      </div>

      {/* Pause / Resume / Cancel */}
      {!done && !error && status !== 'cancelled' && (
        <div className="flex gap-2 mb-4">
          {status === 'running' && (
            <button
              onClick={async () => {
                setBusy(true);
                try {
                  await api.pausePipeline(sid);
                  setStatus('paused');
                } catch (e) { setError(e.message); }
                finally { setBusy(false); }
              }}
              disabled={busy}
              className="btn-secondary flex items-center gap-2 text-sm"
            >
              <RiPauseLine /> Пауза
            </button>
          )}
          {status === 'paused' && (
            <button
              onClick={async () => {
                setBusy(true);
                try {
                  await api.resumePipeline(sid);
                  setStatus('running');
                } catch (e) { setError(e.message); }
                finally { setBusy(false); }
              }}
              disabled={busy}
              className="btn-primary flex items-center gap-2 text-sm"
            >
              <RiPlayLine /> Продолжить
            </button>
          )}
          <button
            onClick={async () => {
              setBusy(true);
              try {
                await api.cancelPipeline(sid);
                setStatus('cancelled');
                setError('Генерация отменена');
              } catch (e) { setError(e.message); }
              finally { setBusy(false); }
            }}
            disabled={busy || status === 'cancelled'}
            className="px-4 py-2 rounded-xl border border-red-800/40 text-red-400 hover:bg-red-900/20 text-sm font-medium transition-colors disabled:opacity-50"
          >
            <RiStopLine /> Отменить
          </button>
        </div>
      )}

      {/* Step indicator */}
      <div className="card p-5 mb-4">
        <StepIndicator logs={logs} done={!!done} error={!!error} />
      </div>

      {/* Error banner */}
      {error && (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="mb-4 p-4 rounded-xl bg-red-900/20 border border-red-800/40 text-red-400 text-sm font-mono"
        >
          {error}
        </motion.div>
      )}

      {/* Restart button — видно при done или error */}
      {(done || error) && (
        <div className="mb-4">
          <button
            onClick={async () => {
              setBusy(true);
              try {
                const res = await api.restartPipeline(sid);
                navigate(`/run/${res.session_id}`, { replace: true });
              } catch (e) {
                setError(e.message || 'Не удалось перезапустить');
              } finally {
                setBusy(false);
              }
            }}
            disabled={busy}
            className="btn-secondary flex items-center gap-2 text-sm"
          >
            <RiRestartLine /> Перезапустить с теми же параметрами
          </button>
        </div>
      )}

      {/* Done — video player(s) */}
      <AnimatePresence>
        {done && videoUrls.length > 0 && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            className="card overflow-hidden mb-4"
          >
            <div className="p-4 border-b border-[#27272f] flex items-center gap-2">
              <RiCheckboxCircleLine className="text-emerald-400 text-xl" />
              <span className="text-sm font-semibold text-white">Видео создано</span>
            </div>
            <div className="flex flex-col gap-6 p-4">
              {videoUrls.map(({ url, label }, idx) => (
                <div key={idx} className="flex flex-col gap-2">
                  {label && (
                    <span className="text-xs font-medium text-[#71717a] uppercase tracking-wider">{label}</span>
                  )}
                  <div className="flex justify-center bg-black p-4 rounded-lg">
                    <video
                      controls
                      autoPlay={idx === 0}
                      className="max-h-[60vh] rounded-lg shadow-2xl"
                      style={{ maxWidth: '300px' }}
                    >
                      <source src={url} type="video/mp4" />
                    </video>
                  </div>
                  {(() => {
                    const cap =
                      label === 'RU'
                        ? done?.quote_caption_ru
                        : label === 'EN'
                          ? done?.quote_caption_en
                          : done?.quote_caption || done?.quote_caption_ru || done?.topic;
                    if (!cap) return null;
                    return (
                      <p className="text-[#d4d4d8] text-sm leading-relaxed text-center px-1">
                        {cap}
                      </p>
                    );
                  })()}
                  <a
                    href={url}
                    download={`video_${label || idx}.mp4`}
                    className="btn-secondary flex items-center gap-2 text-sm self-start"
                  >
                    <RiDownloadLine /> Скачать {label ? `${label} ` : ''}MP4
                  </a>
                  {label === 'RU' && done?.quote_caption_ru && (
                    <button
                      type="button"
                      onClick={() => downloadTextFile(`quote_caption_ru_${sid?.slice(-8) || 'video'}.txt`, done.quote_caption_ru)}
                      className="btn-secondary flex items-center gap-2 text-sm self-start"
                    >
                      <RiFileTextLine /> Скачать подпись RU (.txt)
                    </button>
                  )}
                  {label === 'EN' && done?.quote_caption_en && (
                    <button
                      type="button"
                      onClick={() => downloadTextFile(`quote_caption_en_${sid?.slice(-8) || 'video'}.txt`, done.quote_caption_en)}
                      className="btn-secondary flex items-center gap-2 text-sm self-start"
                    >
                      <RiFileTextLine /> Скачать подпись EN (.txt)
                    </button>
                  )}
                </div>
              ))}
            </div>
            <div className="p-4 flex flex-wrap gap-3 border-t border-[#27272f]">
              <button
                onClick={async () => {
                  setBusy(true);
                  try {
                    const res = await api.restartPipeline(sid);
                    navigate(`/run/${res.session_id}`, { replace: true });
                  } catch (e) {
                    setError(e.message || 'Не удалось перезапустить');
                  } finally {
                    setBusy(false);
                  }
                }}
                disabled={busy}
                className="btn-secondary flex items-center gap-2 text-sm"
              >
                <RiRestartLine /> Перезапустить
              </button>
              <button
                onClick={() => navigate('/history')}
                className="btn-secondary flex items-center gap-2 text-sm"
              >
                <RiVideoLine /> История
              </button>
              <button
                onClick={() => navigate('/')}
                className="btn-secondary flex items-center gap-2 text-sm"
              >
                + Создать ещё
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Publishing Metadata */}
      <AnimatePresence>
        {done?.publishing && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            className="card overflow-hidden mb-4"
          >
            <div className="p-4 border-b border-[#27272f] flex items-center gap-2">
              <span className="text-lg">📝</span>
              <span className="text-sm font-semibold text-white">Данные для публикации</span>
            </div>
            <div className="p-4 space-y-4">
              {/* Title */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-medium text-[#71717a] uppercase tracking-wider">Название</span>
                  <button
                    onClick={() => copyToClipboard(done.publishing.title, 'title')}
                    className="text-[#71717a] hover:text-white transition-colors"
                  >
                    {copied === 'title' ? <RiCheckLine className="text-emerald-400" /> : <RiFileCopyLine />}
                  </button>
                </div>
                <p className="text-white text-sm font-medium">{done.publishing.title}</p>
              </div>

              {/* Description */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-medium text-[#71717a] uppercase tracking-wider">Описание</span>
                  <button
                    onClick={() => copyToClipboard(done.publishing.description, 'description')}
                    className="text-[#71717a] hover:text-white transition-colors"
                  >
                    {copied === 'description' ? <RiCheckLine className="text-emerald-400" /> : <RiFileCopyLine />}
                  </button>
                </div>
                <p className="text-[#a1a1aa] text-sm">{done.publishing.description}</p>
              </div>

              {/* Hashtags */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-medium text-[#71717a] uppercase tracking-wider">Хештеги</span>
                  <button
                    onClick={() => copyToClipboard(done.publishing.hashtags?.join(' '), 'hashtags')}
                    className="text-[#71717a] hover:text-white transition-colors"
                  >
                    {copied === 'hashtags' ? <RiCheckLine className="text-emerald-400" /> : <RiFileCopyLine />}
                  </button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {done.publishing.hashtags?.map((tag, i) => (
                    <span key={i} className="px-2 py-1 bg-[#27272f] rounded text-xs text-[#a1a1aa]">{tag}</span>
                  ))}
                </div>
              </div>

              {/* Tags */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-medium text-[#71717a] uppercase tracking-wider">Теги (YouTube Studio)</span>
                  <button
                    onClick={() => copyToClipboard(done.publishing.tags?.join(', '), 'tags')}
                    className="text-[#71717a] hover:text-white transition-colors"
                  >
                    {copied === 'tags' ? <RiCheckLine className="text-emerald-400" /> : <RiFileCopyLine />}
                  </button>
                </div>
                <p className="text-[#71717a] text-xs font-mono">{done.publishing.tags?.join(', ')}</p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Log console */}
      <LogConsole logs={logs} className="mb-4" />
    </div>
  );
}
