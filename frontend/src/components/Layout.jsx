import { useEffect, useState } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { RiVideoAddLine, RiHistoryLine, RiSparklingLine, RiBookmarkLine, RiLoader4Line } from 'react-icons/ri';
import { motion } from 'framer-motion';
import { api } from '../services/api';

const NAV = [
  { to: '/',        icon: RiVideoAddLine,  label: 'Создать' },
  { to: '/history', icon: RiHistoryLine,   label: 'Видео' },
  { to: '/topics',  icon: RiBookmarkLine,  label: 'Темы' },
];

const MODE_LABELS = { 1: '5 фактов', 2: 'Почему X?', 3: 'Реставрация', 4: 'Цитата' };

export default function Layout({ children }) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [activeSessions, setActiveSessions] = useState([]);

  useEffect(() => {
    let mounted = true;

    const fetchActive = () => {
      api.listPipelineSessions()
        .then(r => { if (mounted) setActiveSessions(r.sessions || []); })
        .catch(() => {}); // Failed to fetch — сервер перезапущен/недоступен
    };
    fetchActive();
    const id = setInterval(fetchActive, 8000);  // 8 сек — меньше нагрузка
    return () => { mounted = false; clearInterval(id); };
  }, []);

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="w-60 flex-shrink-0 flex flex-col border-r border-[#27272f] bg-[#0d0d14]">
        {/* Logo */}
        <div className="flex items-center gap-3 px-5 py-5 border-b border-[#27272f]">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center shadow-lg shadow-brand-900/50">
            <RiSparklingLine className="text-white text-lg" />
          </div>
          <div>
            <div className="text-sm font-bold text-white leading-tight">Content</div>
            <div className="text-xs text-brand-400 font-semibold tracking-wider">FACTORY</div>
          </div>
        </div>

        {/* Active sessions */}
        {activeSessions.length > 0 && (
          <div className="px-4 py-3 border-b border-[#27272f]">
            <div className="text-[10px] font-semibold text-[#52525b] uppercase tracking-wider mb-2">
              В работе ({activeSessions.length})
            </div>
            <div className="space-y-1">
              {activeSessions.map(s => (
                <button
                  key={s.session_id}
                  onClick={() => navigate(`/run/${s.session_id}`)}
                  className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left text-xs bg-brand-600/10 border border-brand-600/20 hover:border-brand-600/40 transition-colors"
                >
                  <RiLoader4Line className="flex-shrink-0 animate-spin text-brand-400 text-sm" />
                  <span className="truncate flex-1 text-[#e4e4f0]">
                    {s.topic || `#${s.session_id?.slice(-8)}`}
                  </span>
                  <span className="text-[10px] text-[#71717a] flex-shrink-0">
                    {MODE_LABELS[s.mode] || s.mode}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-1">
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-150 ${
                  isActive
                    ? 'bg-brand-600/20 text-brand-400 border border-brand-600/30'
                    : 'text-[#71717a] hover:text-[#e4e4f0] hover:bg-[#1a1a24]'
                }`
              }
            >
              <Icon className="text-base flex-shrink-0" />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-[#27272f]">
          <p className="text-[10px] text-[#52525b] leading-relaxed">
            AI-автоматизация<br />
            контент-производства
          </p>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-y-auto bg-[#09090b]">
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}
          className="h-full min-h-0"
        >
          {children}
        </motion.div>
      </main>
    </div>
  );
}
