import { useEffect, useState, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { RiArrowLeftLine, RiDownloadLine, RiVideoLine, RiCheckboxCircleLine } from 'react-icons/ri';
import { subscribeToStream } from '../services/api';
import LogConsole from '../components/LogConsole';
import StepIndicator from '../components/StepIndicator';

export default function Progress() {
  const { sid } = useParams();
  const navigate = useNavigate();

  const [logs, setLogs]   = useState([]);
  const [done, setDone]   = useState(null);   // result object
  const [error, setError] = useState('');
  const cleanupRef = useRef(null);

  useEffect(() => {
    const cleanup = subscribeToStream(
      sid,
      (entry) => setLogs(prev => [...prev, entry]),
      (result) => setDone(result),
      (err)    => setError(String(err)),
    );
    cleanupRef.current = cleanup;
    return cleanup;
  }, [sid]);

  // Video URL from result
  const videoUrl = done?.video_path
    ? `/api/video/${done.session_id || sid}/${done.video_path?.split(/[/\\]/).pop()}`
    : null;

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
          {done ? '🎉 Видео готово!' : error ? '❌ Ошибка' : '⚙️ Генерация...'}
        </h1>
        {done?.topic && (
          <p className="text-[#71717a] text-sm mt-1">{done.topic}</p>
        )}
        <p className="text-[#52525b] text-xs font-mono mt-1">session: {sid}</p>
      </div>

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

      {/* Done — video player */}
      <AnimatePresence>
        {done && videoUrl && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            className="card overflow-hidden mb-4"
          >
            <div className="p-4 border-b border-[#27272f] flex items-center gap-2">
              <RiCheckboxCircleLine className="text-emerald-400 text-xl" />
              <span className="text-sm font-semibold text-white">Видео создано</span>
            </div>
            <div className="flex justify-center bg-black p-4">
              <video
                controls
                autoPlay
                className="max-h-[60vh] rounded-lg shadow-2xl"
                style={{ maxWidth: '300px' }}
              >
                <source src={videoUrl} type="video/mp4" />
              </video>
            </div>
            <div className="p-4 flex gap-3">
              <a
                href={videoUrl}
                download
                className="btn-primary flex items-center gap-2 text-sm"
              >
                <RiDownloadLine /> Скачать MP4
              </a>
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
