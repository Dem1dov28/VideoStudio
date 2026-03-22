import { NavLink, useLocation } from 'react-router-dom';
import { RiVideoAddLine, RiHistoryLine, RiSparklingLine, RiBookmarkLine } from 'react-icons/ri';
import { motion } from 'framer-motion';
import { useLanguage } from '../context/LanguageContext';
import { useMode } from '../context/ModeContext';

const NAV = [
  { to: '/',        icon: RiVideoAddLine,  label: 'Создать' },
  { to: '/history', icon: RiHistoryLine,   label: 'Видео' },
  { to: '/topics',  icon: RiBookmarkLine,  label: 'Темы' },
];

export default function Layout({ children }) {
  const { mode, setMode } = useMode();
  const { lang, setLang } = useLanguage();
  const { pathname } = useLocation();

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

        {/* Mode switcher — между логотипом и навигацией */}
        <div className="px-4 py-3 border-b border-[#27272f]">
          <div className="text-[10px] font-semibold text-[#52525b] uppercase tracking-wider mb-2">
            Режим
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setMode(1)}
              title="Топ-5 фактов — AI генерирует картинки"
              className={`flex-1 py-2.5 rounded-lg text-sm font-medium transition-all ${
                mode === 1
                  ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                  : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
              }`}
            >
              5 фактов
            </button>
            <button
              onClick={() => setMode(2)}
              title="Почему X? — AI генерирует видео"
              className={`flex-1 py-2.5 rounded-lg text-sm font-medium transition-all ${
                mode === 2
                  ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                  : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
              }`}
            >
              Почему X?
            </button>
          </div>
        </div>

        {/* Language */}
        <div className="px-4 py-3 border-b border-[#27272f]">
          <div className="text-[10px] font-semibold text-[#52525b] uppercase tracking-wider mb-2">
            Язык
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setLang('ru')}
              title="Русский"
              className={`flex-1 py-2.5 rounded-lg text-sm font-medium transition-all ${
                lang === 'ru'
                  ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                  : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
              }`}
            >
              RU
            </button>
            <button
              onClick={() => setLang('en')}
              title="English"
              className={`flex-1 py-2.5 rounded-lg text-sm font-medium transition-all ${
                lang === 'en'
                  ? 'bg-brand-600/20 text-brand-400 border border-brand-600/40'
                  : 'text-[#71717a] hover:text-[#e4e4f0] border border-[#27272f] hover:border-[#3f3f50]'
              }`}
            >
              EN
            </button>
          </div>
        </div>

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
          key={pathname}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}
          className="h-full"
        >
          {children}
        </motion.div>
      </main>
    </div>
  );
}
