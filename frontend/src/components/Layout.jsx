import { useEffect, useState } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import {
  RiVideoAddLine,
  RiHistoryLine,
  RiSparklingLine,
  RiLoader4Line,
  RiPauseLine,
  RiDiceLine,
  RiCheckboxCircleLine,
  RiErrorWarningLine,
  RiStopCircleLine,
} from 'react-icons/ri';
import { motion } from 'framer-motion';
import { api } from '../services/api';
import RateLimitPanel from './RateLimitPanel';

const NAV = [
  { to: '/', icon: RiVideoAddLine, label: 'Создать' },
  { to: '/history', icon: RiHistoryLine, label: 'Видео' },
  { to: '/casino', icon: RiDiceLine, label: 'Казино' },
];

const MODE_LABELS = {
  1: '5 фактов',
  2: 'Почему X?',
  3: 'Реставрация',
  4: 'Цитата',
  5: 'Длинные',
  6: 'Релакс',
  7: '2 клипа',
  8: 'Было→стало',
  9: 'Keyframe',
  10: 'Пляж',
  11: 'Постройка',
  12: 'Притча',
  13: 'Аудио→слайды',
};

export default function Layout({ children }) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [activeSessions, setActiveSessions] = useState([]);
  const runMatch = pathname.match(/^\/run\/([^/]+)/);
  const activeRunSessionId = runMatch ? runMatch[1] : null;

  useEffect(() => {
    let mounted = true;
    let consecutiveErrors = 0;
    const MAX_CONSECUTIVE_ERRORS = 3;

    const fetchActive = () => {
      api
        .listPipelineSessions()
        .then((r) => {
          if (mounted) {
            setActiveSessions(r.sessions || []);
            consecutiveErrors = 0;
          }
        })
        .catch(() => {
          consecutiveErrors++;
          if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
            console.warn('[Layout] Server unavailable, stopping polling');
          }
        });
    };

    fetchActive();
    const id = setInterval(fetchActive, 8000);
    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="flex h-screen overflow-hidden">
      <aside className="relative w-[17rem] flex-shrink-0 flex flex-col border-r border-white/[0.06] bg-zinc-950/55 backdrop-blur-2xl shadow-[4px_0_48px_-12px_rgba(0,0,0,0.65)]">
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-brand-600/[0.07] via-transparent to-transparent" />

        <div className="relative flex items-center gap-3 px-5 py-6 border-b border-white/[0.06]">
          <div className="relative w-10 h-10 rounded-2xl bg-gradient-to-br from-brand-400 via-brand-600 to-brand-800 flex items-center justify-center shadow-glow-sm ring-1 ring-white/15">
            <RiSparklingLine className="text-white text-xl drop-shadow-md" />
          </div>
          <div>
            <div className="text-[15px] font-bold text-white leading-tight tracking-tight">Content</div>
            <div className="text-[11px] text-brand-400/95 font-semibold tracking-[0.2em] uppercase mt-0.5">
              Factory
            </div>
          </div>
        </div>

        {activeSessions.length > 0 && (
          <div className="relative px-3 py-3 border-b border-white/[0.06] max-h-[38vh] overflow-y-auto scrollbar-subtle">
            <div className="text-[10px] font-semibold text-[#6b6b7e] uppercase tracking-wider mb-2 px-2">
              Сессии ({activeSessions.length})
            </div>
            <div className="space-y-1.5">
              {activeSessions.map((s) => {
                const isCurrent = activeRunSessionId && s.session_id === activeRunSessionId;
                const isPaused = s.status === 'paused';
                const isError = s.status === 'error';
                const isCancelled = s.status === 'cancelled';
                const isReviewPending = !!s.review_pending;
                return (
                  <button
                    key={s.session_id}
                    onClick={() => navigate(`/run/${s.session_id}`)}
                    className={`w-full flex items-center gap-2 px-3 py-2.5 rounded-xl text-left text-xs border transition-all duration-200 ${
                      isCurrent
                        ? 'bg-brand-600/25 border-brand-500/50 ring-1 ring-brand-500/25 shadow-glow-sm'
                        : isError
                          ? 'bg-red-950/35 border-red-500/25 hover:border-red-400/35'
                          : isCancelled
                            ? 'bg-white/[0.03] border-white/[0.06] hover:border-white/[0.1]'
                            : 'bg-white/[0.04] border-white/[0.06] hover:bg-white/[0.06] hover:border-brand-500/25'
                    }`}
                  >
                    {isReviewPending ? (
                      <RiCheckboxCircleLine className="flex-shrink-0 text-emerald-400 text-sm" />
                    ) : isPaused ? (
                      <RiPauseLine className="flex-shrink-0 text-amber-400 text-sm" />
                    ) : isError ? (
                      <RiErrorWarningLine className="flex-shrink-0 text-red-400 text-sm" />
                    ) : isCancelled ? (
                      <RiStopCircleLine className="flex-shrink-0 text-[#71717a] text-sm" />
                    ) : (
                      <RiLoader4Line className="flex-shrink-0 animate-spin text-brand-400 text-sm" />
                    )}
                    <span className="truncate flex-1 text-[#e8e8f2] font-medium">
                      {s.topic || `#${s.session_id?.slice(-8)}`}
                    </span>
                    {isReviewPending ? (
                      <span className="text-[10px] text-emerald-400/90 flex-shrink-0">Проверка</span>
                    ) : isError ? (
                      <span className="text-[10px] text-red-400/90 flex-shrink-0">Ошибка</span>
                    ) : isCancelled ? (
                      <span className="text-[10px] text-[#71717a] flex-shrink-0">Стоп</span>
                    ) : null}
                    <span className="text-[10px] text-[#6b6b7e] flex-shrink-0">
                      {MODE_LABELS[s.mode] || s.mode}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <RateLimitPanel />

        <nav className="relative flex-1 px-3 py-4 space-y-1">
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-3 rounded-xl text-sm font-semibold tracking-tight transition-all duration-200 ${
                  isActive
                    ? 'bg-gradient-to-r from-brand-600/30 to-brand-600/10 text-white border border-brand-500/35 shadow-glow-sm'
                    : 'text-[#9494a8] hover:text-white hover:bg-white/[0.05] border border-transparent'
                }`
              }
            >
              <Icon className="text-lg flex-shrink-0 opacity-90" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="relative px-5 py-4 border-t border-white/[0.06]">
          <p className="text-[10px] text-[#5c5c6e] leading-relaxed font-medium">
            AI-автоматизация
            <br />
            контент-производства
          </p>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto min-h-0 bg-transparent">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
          className="h-full min-h-0"
        >
          {children}
        </motion.div>
      </main>
    </div>
  );
}
