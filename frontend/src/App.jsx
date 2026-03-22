import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import { LanguageProvider } from './context/LanguageContext';
import { ModeProvider } from './context/ModeContext';
import Layout from './components/Layout';

const Generate = lazy(() => import('./pages/Generate'));
const Progress = lazy(() => import('./pages/Progress'));
const History  = lazy(() => import('./pages/History'));
const Topics   = lazy(() => import('./pages/Topics'));

function Spinner() {
  return (
    <div className="flex items-center justify-center h-full min-h-[60vh]">
      <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <LanguageProvider>
        <ModeProvider>
          <Layout>
            <Suspense fallback={<Spinner />}>
              <Routes>
                <Route path="/"         element={<Generate />} />
                <Route path="/run/:sid" element={<Progress />} />
                <Route path="/history"  element={<History />} />
                <Route path="/topics"   element={<Topics />} />
                <Route path="*"         element={<Navigate to="/" replace />} />
              </Routes>
            </Suspense>
          </Layout>
        </ModeProvider>
      </LanguageProvider>
    </BrowserRouter>
  );
}
