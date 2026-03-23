import { useState } from 'react';
import { RiPlayCircleLine, RiDownloadLine, RiTimeLine, RiDeleteBinLine } from 'react-icons/ri';
import { motion } from 'framer-motion';
import { api } from '../services/api';

function formatDate(ts) {
  if (ts == null) return '—';
  const d = new Date(typeof ts === 'number' ? ts * 1000 : ts);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('ru-RU', {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
  });
}

export default function VideoCard({ video, onClick, onDelete }) {
  const [hovered, setHovered] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const base = import.meta.env.VITE_API_URL || '';
  const thumbUrl = video?.thumbnail_url ? base + video.thumbnail_url : null;

  if (!video?.session_id) return null;

  async function handleDelete(e) {
    e.stopPropagation();
    if (deleting) return;
    if (!confirm('Удалить видео с компьютера?')) return;
    setDeleting(true);
    try {
      await api.deleteVideo(video.session_id);
      onDelete?.(video.session_id);
    } catch (err) {
      alert(err.message);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <motion.div
      whileHover={{ y: -2 }}
      transition={{ duration: 0.15 }}
      className="card overflow-hidden cursor-pointer group"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={() => onClick(video)}
    >
      {/* Thumbnail / avatar */}
      <div className="relative aspect-[9/16] max-h-52 bg-[#0d0d14] overflow-hidden">
        {thumbUrl ? (
          <img
            src={thumbUrl}
            alt=""
            loading="lazy"
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-5xl opacity-20">🎬</div>
          </div>
        )}
        <motion.div
          animate={{ opacity: hovered ? 1 : 0 }}
          className="absolute inset-0 bg-brand-600/20 flex items-center justify-center"
        >
          <RiPlayCircleLine className="text-white text-4xl drop-shadow-lg" />
        </motion.div>
      </div>

      {/* Info */}
      <div className="p-3 space-y-2">
        <div className="font-medium text-sm text-[#e4e4f0] line-clamp-2" title={video.title}>
          {video.title || `Видео #${video.session_id.slice(-8)}`}
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-[#71717a]">{video.size_mb ?? '—'} MB</span>
          <span className="text-[10px] text-[#52525b]">{formatDate(video.created_at)}</span>
        </div>
        <div className="flex items-center gap-2">
          <a
            href={video?.url ? base + video.url : '#'}
            download
            onClick={(e) => e.stopPropagation()}
            className="flex items-center gap-1.5 text-brand-400 hover:text-brand-300 text-xs font-medium transition-colors"
          >
            <RiDownloadLine className="text-sm" />
            Скачать
          </a>
          <button
            type="button"
            onClick={handleDelete}
            disabled={deleting}
            className="flex items-center gap-1.5 text-[#71717a] hover:text-red-400 text-xs transition-colors disabled:opacity-50"
          >
            <RiDeleteBinLine className="text-sm" />
            Удалить
          </button>
        </div>
      </div>
    </motion.div>
  );
}
