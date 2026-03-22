import { useState } from 'react';
import { RiPlayCircleLine, RiDownloadLine, RiTimeLine } from 'react-icons/ri';
import { motion } from 'framer-motion';

function formatDate(ts) {
  return new Date(ts * 1000).toLocaleDateString('ru-RU', {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
  });
}

export default function VideoCard({ video, onClick }) {
  const [hovered, setHovered] = useState(false);

  return (
    <motion.div
      whileHover={{ y: -2 }}
      transition={{ duration: 0.15 }}
      className="card overflow-hidden cursor-pointer group"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={() => onClick(video)}
    >
      {/* Thumbnail area */}
      <div className="relative aspect-[9/16] max-h-52 bg-[#0d0d14] overflow-hidden">
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-5xl opacity-20">🎬</div>
        </div>
        <motion.div
          animate={{ opacity: hovered ? 1 : 0 }}
          className="absolute inset-0 bg-brand-600/20 flex items-center justify-center"
        >
          <RiPlayCircleLine className="text-white text-4xl drop-shadow-lg" />
        </motion.div>
      </div>

      {/* Info */}
      <div className="p-3 space-y-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-mono text-[#52525b]">#{video.session_id.slice(-6)}</span>
          <span className="text-xs text-[#71717a]">{video.size_mb} MB</span>
        </div>

        <div className="flex items-center gap-1.5 text-[#71717a]">
          <RiTimeLine className="text-xs flex-shrink-0" />
          <span className="text-[10px]">{formatDate(video.created_at)}</span>
        </div>

        <a
          href={video.url}
          download
          onClick={(e) => e.stopPropagation()}
          className="flex items-center gap-1.5 text-brand-400 hover:text-brand-300 text-xs font-medium transition-colors"
        >
          <RiDownloadLine className="text-sm" />
          Скачать
        </a>
      </div>
    </motion.div>
  );
}
