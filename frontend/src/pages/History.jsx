import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { RiVideoLine, RiLoader4Line, RiCloseLine } from 'react-icons/ri';
import { api } from '../services/api';
import VideoCard from '../components/VideoCard';

export default function History() {
  const [videos, setVideos]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    api.listVideos()
      .then(r => setVideos(r.videos || []))
      .catch(console.error)
      .finally(() => setLoading(false));
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

      {loading ? (
        <div className="flex items-center justify-center py-24 text-[#71717a] gap-2">
          <RiLoader4Line className="animate-spin text-xl" />
          <span className="text-sm">Загружаем...</span>
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
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4"
        >
          {videos.map((v, i) => (
            <motion.div
              key={v.session_id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04 }}
            >
              <VideoCard video={v} onClick={setSelected} />
            </motion.div>
          ))}
        </motion.div>
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
                <span className="text-sm font-semibold text-white">
                  #{selected.session_id.slice(-8)}
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
                  <source src={selected.url} type="video/mp4" />
                </video>
              </div>
              <div className="p-4 flex gap-2">
                <a
                  href={selected.url}
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
