import { useEffect, useRef } from 'react';
import { clsx } from 'clsx';

const LEVEL_STYLE = {
  DEBUG:   'text-[#71717a]',
  INFO:    'text-sky-400',
  SUCCESS: 'text-emerald-400',
  WARNING: 'text-amber-400',
  ERROR:   'text-red-400',
};

const LEVEL_PREFIX = {
  DEBUG:   '·',
  INFO:    '▸',
  SUCCESS: '✓',
  WARNING: '⚠',
  ERROR:   '✗',
};

export default function LogConsole({ logs, className, sessionId }) {
  const scrollRef = useRef(null);

  // Прокручиваем только внутренний контейнер логов, без scrollIntoView — иначе при новых
  // строках браузер прокручивает всю страницу вниз, если пользователь смотрит превью выше.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [logs]);

  // Получаем уникальные session_id из логов для отображения
  const uniqueSessions = [...new Set(logs.filter(l => l.session_id).map(l => l.session_id))];
  const displaySessionId = sessionId || (uniqueSessions.length === 1 ? uniqueSessions[0] : null);
  const sessionLabel = displaySessionId ? displaySessionId.slice(-8) : 'pipeline';

  return (
    <div className={clsx(
      'rounded-2xl overflow-hidden border border-white/[0.06] bg-black/40 backdrop-blur-xl shadow-[0_8px_32px_-8px_rgba(0,0,0,0.55)] ring-1 ring-white/[0.03]',
      className
    )}>
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-white/[0.06] bg-white/[0.03]">
        <div className="flex gap-1.5">
          <div className="w-3 h-3 rounded-full bg-[#ff5f57]/95 shadow-sm" />
          <div className="w-3 h-3 rounded-full bg-[#febc2e]/95 shadow-sm" />
          <div className="w-3 h-3 rounded-full bg-[#28c840]/95 shadow-sm" />
        </div>
        <span className="text-xs text-[#7c7c8e] font-mono ml-2">{sessionLabel}.log</span>
        <span className="ml-auto text-[10px] text-[#5c5c6e] font-mono tabular-nums">{logs.length} lines</span>
      </div>

      {/* Log lines */}
      <div ref={scrollRef} className="p-4 h-80 overflow-y-auto space-y-0.5 font-mono scrollbar-subtle">
        {logs.length === 0 ? (
          <div className="text-[#5c5c6e] text-xs">Waiting for pipeline to start...</div>
        ) : (
          logs.map((log, i) => (
            <div key={i} className="flex gap-2">
              <span className="text-[#3f3f50] text-[10px] w-16 flex-shrink-0 mt-px">{log.time}</span>
              <span className={clsx('text-[10px] w-4 flex-shrink-0 mt-px font-bold', LEVEL_STYLE[log.level] || 'text-[#71717a]')}>
                {LEVEL_PREFIX[log.level] || '·'}
              </span>
              <span className={clsx('log-line text-[11px]', LEVEL_STYLE[log.level] || 'text-[#a1a1aa]')}>
                {log.text}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
