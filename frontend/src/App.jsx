import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import { LanguageProvider } from './context/LanguageContext';
import { ModeProvider } from './context/ModeContext';
import { RateLimitProvider } from './context/RateLimitContext';
import Layout from './components/Layout';
import History from './pages/History';
import Topics from './pages/Topics';

const Generate = lazy(() => import('./pages/Generate'));
const Casino = lazy(() => import('./pages/Casino'));
const Progress = lazy(() => import('./pages/Progress'));

function Spinner() {
  return (
    <div className="flex flex-col items-center justify-center gap-4 h-full min-h-[60vh]">
      <div className="relative h-12 w-12">
        <div className="absolute inset-0 rounded-full border-2 border-white/[0.08]" />
        <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-brand-500 border-r-brand-400/50 animate-spin" />
        <div className="absolute inset-2 rounded-full bg-brand-500/15 blur-md" />
      </div>
      <p className="text-xs font-medium text-[#7c7c8e] tracking-wide">Загрузка интерфейса…</p>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <LanguageProvider>
        <ModeProvider>
          <RateLimitProvider>
            <Layout>
              <Suspense fallback={<Spinner />}>
                <Routes>
                  <Route path="/"         element={<Generate />} />
                  <Route path="/run/:sid" element={<Progress />} />
                  <Route path="/history"  element={<History />} />
                  <Route path="/topics"   element={<Topics />} />
                  <Route path="/casino" element={<Casino />} />
                  <Route path="*"         element={<Navigate to="/" replace />} />
                </Routes>
              </Suspense>
            </Layout>
          </RateLimitProvider>
        </ModeProvider>
      </LanguageProvider>
    </BrowserRouter>
  );
}
