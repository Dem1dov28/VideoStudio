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

export default function LogConsole({ logs, className }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  return (
    <div className={clsx(
      'bg-[#0d0d12] border border-[#1e1e2a] rounded-xl overflow-hidden',
      className
    )}>
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-[#1e1e2a] bg-[#111117]">
        <div className="flex gap-1.5">
          <div className="w-3 h-3 rounded-full bg-[#ff5f57]" />
          <div className="w-3 h-3 rounded-full bg-[#febc2e]" />
          <div className="w-3 h-3 rounded-full bg-[#28c840]" />
        </div>
        <span className="text-xs text-[#52525b] font-mono ml-2">pipeline.log</span>
        <span className="ml-auto text-[10px] text-[#3f3f50] font-mono">{logs.length} lines</span>
      </div>

      {/* Log lines */}
      <div className="p-4 h-80 overflow-y-auto space-y-0.5 font-mono">
        {logs.length === 0 ? (
          <div className="text-[#3f3f50] text-xs">Waiting for pipeline to start...</div>
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
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
