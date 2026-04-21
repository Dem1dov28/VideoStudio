import { useState } from 'react';
import { RiCloseLine, RiTimeLine, RiAddLine } from 'react-icons/ri';
import { useRateLimit, ALLOWED_HOURLY_LIMITS } from '../context/RateLimitContext';
import { motion, AnimatePresence } from 'framer-motion';

export default function RateLimitPanel() {
  const { limit, used, remaining, queue, setLimit, removeFromQueue } = useRateLimit();
  const [isExpanded, setIsExpanded] = useState(true);

  const safeLimit = ALLOWED_HOURLY_LIMITS.includes(limit) ? limit : 2;
  const unlimited = safeLimit === 0;
  const progressPercent = unlimited
    ? 100
    : Math.min(100, safeLimit ? ((remaining ?? 0) / safeLimit) * 100 : 0);

  return (
    <div className="px-4 py-3 border-b border-[#27272f]">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between mb-2"
      >
        <div className="text-[10px] font-semibold text-[#52525b] uppercase tracking-wider flex items-center gap-1.5">
          <RiTimeLine className="text-brand-400" />
          Лимит генерации
        </div>
        <motion.div
          animate={{ rotate: isExpanded ? 180 : 0 }}
          transition={{ duration: 0.2 }}
          className="text-[#52525b]"
        >
          ▼
        </motion.div>
      </button>

      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            {/* Available count */}
            <div className="mb-3">
              <div className="flex items-center justify-between mb-1">
                <div className="text-xs text-[#e4e4f0]">
                  Доступно:{' '}
                  <span className="font-bold text-brand-400">
                    {unlimited ? '∞' : remaining}
                  </span>
                  {unlimited ? (
                    <span className="text-[#71717a] font-normal"> (лимит выкл.)</span>
                  ) : (
                    <> из {safeLimit}</>
                  )}
                </div>
                <div className="text-[10px] text-[#71717a]">
                  Использовано: {used}
                </div>
              </div>
              
              {/* Progress bar */}
              <div className="w-full bg-[#27272f] rounded-full h-2">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${progressPercent}%` }}
                  transition={{ duration: 0.3 }}
                  className={`h-2 rounded-full transition-all ${
                    unlimited
                      ? 'bg-emerald-500/80'
                      : remaining === 0
                      ? 'bg-red-500'
                      : remaining === 1
                      ? 'bg-amber-500'
                      : 'bg-brand-500'
                  }`}
                />
              </div>
            </div>

            {/* Limit selector */}
            <div className="mb-3">
              <label className="text-[10px] text-[#71717a] block mb-1">
                Лимит в час:
              </label>
              <select
                value={safeLimit}
                onChange={(e) => setLimit(Number(e.target.value))}
                className="w-full px-2 py-1.5 bg-[#1a1a24] border border-[#27272f] rounded-lg text-xs text-[#e4e4f0] focus:outline-none focus:border-brand-500/50"
              >
                <option value={0}>Без лимита</option>
                <option value={1}>1 видео/час</option>
                <option value={2}>2 видео/час</option>
                <option value={3}>3 видео/час</option>
                <option value={5}>5 видео/час</option>
                <option value={10}>10 видео/час</option>
                <option value={15}>15 видео/час</option>
                <option value={30}>30 видео/час</option>
              </select>
            </div>

            {/* Queue */}
            {queue.length > 0 && (
              <div>
                <div className="flex items-center justify-between mb-1">
                  <div className="text-[10px] text-[#71717a]">
                    В очереди: {queue.length}
                  </div>
                  <div className="text-[10px] text-brand-400 flex items-center gap-0.5">
                    <RiAddLine className="text-xs" />
                    Автозапуск
                  </div>
                </div>
                
                <div className="space-y-1 max-h-32 overflow-y-auto custom-scrollbar">
                  {queue.map((item, idx) => (
                    <motion.div
                      key={item.id}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: 10 }}
                      className="flex items-center justify-between px-2 py-1.5 bg-[#1a1a24]/50 rounded-lg border border-[#27272f]/50 hover:border-red-500/30 transition-colors group"
                    >
                      <div className="flex-1 min-w-0 mr-2">
                        <div className="text-xs text-[#e4e4f0] truncate">
                          {item.topic || `Видео #${String(item.id).slice(-6)}`}
                        </div>
                        <div className="text-[10px] text-[#71717a]">
                          Mode {item.mode} • {new Date(item.created_at ? item.created_at * 1000 : item.timestamp).toLocaleTimeString()}
                        </div>
                      </div>
                      <button
                        onClick={() => removeFromQueue(idx)}
                        className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-red-500/20 rounded"
                        title="Удалить из очереди"
                      >
                        <RiCloseLine className="text-red-400 text-sm" />
                      </button>
                    </motion.div>
                  ))}
                </div>
              </div>
            )}

            {/* Empty state */}
            {queue.length === 0 && (
              <div className="text-center py-2">
                <div className="text-[10px] text-[#52525b]">
                  Очередь пуста
                </div>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
