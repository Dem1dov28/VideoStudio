import { useEffect, useState, useRef, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { RiArrowLeftLine, RiDownloadLine, RiVideoLine, RiCheckboxCircleLine, RiPauseLine, RiPlayLine, RiStopLine, RiRestartLine } from 'react-icons/ri';
import { subscribeToStream, api } from '../services/api';
import LogConsole from '../components/LogConsole';
import StepIndicator from '../components/StepIndicator';

export default function Progress() {
  const { sid } = useParams();
  const navigate = useNavigate();

  const [logs, setLogs]   = useState([]);
  const [done, setDone]   = useState(null);   // result object
  const [error, setError] = useState('');
  const [status, setStatus] = useState('running');  // running | paused | cancelled
  const [busy, setBusy]   = useState(false);
  const cleanupRef = useRef(null);

  useEffect(() => {
    api.getPipelineStatus(sid).then(r => {
      setStatus(r.status || 'running');
      if (r.status === 'done' && r.result) {
        setDone(r.result);
      } else if (r.status === 'error' && r.error) {
        setError(r.error);
      }
    }).catch(() => {});
  }, [sid]);

  useEffect(() => {
    const cleanup = subscribeToStream(
      sid,
      (entry) => setLogs(prev => [...prev, entry]),
      (result) => setDone(result),
      (err)    => { setError(String(err)); setStatus('error'); },
    );
    cleanupRef.current = cleanup;
    return cleanup;
  }, [sid]);

  // Video URL(s) from result — один файл или несколько (Mode 4 bilingual)
  const videoUrls = useMemo(() => {
    if (!done) return [];
    const base = done.session_id || sid;
    const paths = done.video_paths && done.video_paths.length > 0
      ? done.video_paths
      : done.video_path
        ? [done.video_path]
        : [];
    const prefix = import.meta.env.VITE_API_URL || '';
    return paths.map(p => {
      const fname = (p || "").split(/[/\\]/).pop();
      return {
        url: `${prefix}/api/video/${base}/${fname}`,
        label: (p || "").includes("video_ru") ? "RU" : (p || "").includes("video_en") ? "EN" : null,
      };
    });
  }, [done, sid]);

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
        <h1 className="text-xl font-bold text-white">
          {done ? '🎉 Видео готово!' : error ? '❌ Ошибка' : status === 'paused' ? '⏸️ На паузе' : '⚙️ Генерация...'}
        </h1>
        {done?.topic && (
          <p className="text-[#71717a] text-sm mt-1">{done.topic}</p>
        )}
        <p className="text-[#52525b] text-xs font-mono mt-1">session: {sid}</p>
      </div>

      {/* Pause / Resume / Cancel */}
      {!done && !error && (
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
                  <a
                    href={url}
                    download={`video_${label || idx}.mp4`}
                    className="btn-secondary flex items-center gap-2 text-sm self-start"
                  >
                    <RiDownloadLine /> Скачать {label ? label : ''} MP4
                  </a>
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

      {/* Log console */}
      <LogConsole logs={logs} className="mb-4" />
    </div>
  );
}
