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
  const [showPublishing, setShowPublishing] = useState(false);

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

  // Copy to clipboard helper
  async function copyToClipboard(text, label) {
    try {
      await navigator.clipboard.writeText(text);
      alert(`${label} скопирован в буфер обмена!`);
    } catch (err) {
      // Fallback for older browsers
      const textarea = document.createElement('textarea');
      textarea.value = text;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      alert(`${label} скопирован в буфер обмена!`);
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
        
        {/* Publishing metadata button */}
        {video.publishing && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setShowPublishing(!showPublishing);
            }}
            className="w-full flex items-center justify-center gap-1.5 text-brand-400 hover:text-brand-300 text-xs font-medium transition-colors py-1.5 px-2 rounded border border-brand-400/30 hover:border-brand-300 bg-brand-400/10"
          >
            📝 {showPublishing ? 'Скрыть' : 'Для YouTube'}
          </button>
        )}
        
        {/* Publishing metadata panel */}
        {showPublishing && video.publishing && (
          <div className="space-y-3 pt-2 border-t border-[#27272f]">
            {/* Title */}
            <div>
              <label className="block text-[10px] font-semibold text-[#71717a] uppercase tracking-wider mb-1">
                Название
              </label>
              <div className="flex gap-1.5">
                <input
                  type="text"
                  value={video.publishing.title || ''}
                  readOnly
                  className="flex-1 bg-[#0d0d14] border border-[#27272f] rounded px-2 py-1 text-xs text-white"
                />
                <button
                  type="button"
                  onClick={() => copyToClipboard(video.publishing.title || '', 'Название')}
                  className="text-[10px] bg-brand-400/20 hover:bg-brand-400/30 text-brand-300 px-2 py-1 rounded transition-colors"
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
                  value={(video.publishing.hashtags || []).join(' ')}
                  readOnly
                  className="flex-1 bg-[#0d0d14] border border-[#27272f] rounded px-2 py-1 text-xs text-white"
                />
                <button
                  type="button"
                  onClick={() => copyToClipboard((video.publishing.hashtags || []).join(' '), 'Хештеги')}
                  className="text-[10px] bg-brand-400/20 hover:bg-brand-400/30 text-brand-300 px-2 py-1 rounded transition-colors"
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
                  value={video.publishing.description || ''}
                  readOnly
                  rows={3}
                  className="flex-1 bg-[#0d0d14] border border-[#27272f] rounded px-2 py-1 text-xs text-white resize-none"
                />
                <button
                  type="button"
                  onClick={() => copyToClipboard(video.publishing.description || '', 'Описание')}
                  className="text-[10px] bg-brand-400/20 hover:bg-brand-400/30 text-brand-300 px-2 py-1 rounded transition-colors self-start mt-0.5"
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
                  value={(video.publishing.tags || []).join(', ')}
                  readOnly
                  className="flex-1 bg-[#0d0d14] border border-[#27272f] rounded px-2 py-1 text-xs text-white"
                />
                <button
                  type="button"
                  onClick={() => copyToClipboard((video.publishing.tags || []).join(', '), 'Теги')}
                  className="text-[10px] bg-brand-400/20 hover:bg-brand-400/30 text-brand-300 px-2 py-1 rounded transition-colors"
                >
                  Копия
                </button>
              </div>
            </div>
          </div>
        )}
        
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
