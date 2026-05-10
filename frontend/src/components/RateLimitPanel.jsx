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
    <div className="relative px-3 py-3 border-b border-white/[0.06]">
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between mb-1 px-2 py-1.5 rounded-lg hover:bg-white/[0.04] transition-colors"
      >
        <div className="text-[10px] font-semibold text-[#7c7c8e] uppercase tracking-wider flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand-500/15 text-brand-400 ring-1 ring-brand-500/25">
            <RiTimeLine className="text-sm" />
          </span>
          Лимит генерации
        </div>
        <motion.span
          animate={{ rotate: isExpanded ? 180 : 0 }}
          transition={{ duration: 0.2 }}
          className="text-[#5c5c6e] text-xs"
        >
          ▾
        </motion.span>
      </button>

      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22 }}
            className="overflow-hidden"
          >
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] backdrop-blur-md px-3 py-3 mt-1 space-y-3">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="text-xs text-[#ececf4]">
                    Доступно:{' '}
                    <span className="font-bold text-brand-400 tabular-nums">
                      {unlimited ? '∞' : remaining}
                    </span>
                    {unlimited ? (
                      <span className="text-[#7c7c8e] font-normal"> (выкл.)</span>
                    ) : (
                      <span className="text-[#7c7c8e] font-normal"> из {safeLimit}</span>
                    )}
                  </div>
                  <div className="text-[10px] text-[#7c7c8e] tabular-nums">исп. {used}</div>
                </div>

                <div className="w-full bg-black/40 rounded-full h-2 overflow-hidden ring-1 ring-white/[0.06]">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${progressPercent}%` }}
                    transition={{ duration: 0.35 }}
                    className={`h-2 rounded-full transition-colors ${
                      unlimited
                        ? 'bg-emerald-500/85'
                        : remaining === 0
                          ? 'bg-red-500'
                          : remaining === 1
                            ? 'bg-amber-500'
                            : 'bg-gradient-to-r from-brand-500 to-brand-400'
                    }`}
                  />
                </div>
              </div>

              <div>
                <label className="text-[10px] text-[#7c7c8e] block mb-1.5 font-medium">Лимит в час</label>
                <select
                  value={safeLimit}
                  onChange={(e) => setLimit(Number(e.target.value))}
                  className="w-full px-3 py-2 bg-black/35 border border-white/[0.08] rounded-xl text-xs text-[#ececf4] focus:outline-none focus:border-brand-500/45 focus:ring-2 focus:ring-brand-500/15 transition-shadow"
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

              {queue.length > 0 && (
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-[10px] text-[#7c7c8e] font-medium">В очереди: {queue.length}</div>
                    <div className="text-[10px] text-brand-400 flex items-center gap-0.5 font-semibold">
                      <RiAddLine className="text-xs" />
                      Автозапуск
                    </div>
                  </div>

                  <div className="space-y-1.5 max-h-32 overflow-y-auto custom-scrollbar">
                    {queue.map((item, idx) => (
                      <motion.div
                        key={item.id}
                        initial={{ opacity: 0, x: -8 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: 8 }}
                        className="flex items-center justify-between px-2.5 py-2 rounded-xl border border-white/[0.06] bg-black/25 hover:border-red-500/25 transition-colors group"
                      >
                        <div className="flex-1 min-w-0 mr-2">
                          <div className="text-xs text-[#ececf4] truncate font-medium">
                            {item.topic || `Видео #${String(item.id).slice(-6)}`}
                          </div>
                          <div className="text-[10px] text-[#6b6b7e]">
                            Mode {item.mode} •{' '}
                            {new Date(
                              item.created_at ? item.created_at * 1000 : item.timestamp,
                            ).toLocaleTimeString()}
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() => removeFromQueue(idx)}
                          className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 hover:bg-red-500/15 rounded-lg text-red-400"
                          title="Удалить из очереди"
                        >
                          <RiCloseLine className="text-sm" />
                        </button>
                      </motion.div>
                    ))}
                  </div>
                </div>
              )}

              {queue.length === 0 && (
                <div className="text-center py-1">
                  <div className="text-[10px] text-[#5c5c6e]">Очередь пуста</div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
