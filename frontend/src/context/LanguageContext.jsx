import { createContext, useContext, useState, useEffect } from 'react';

const LANG_KEY = 'content-factory-lang';

const LanguageContext = createContext({
  lang: 'ru',
  setLang: () => {},
});

export function LanguageProvider({ children }) {
  const [lang, setLangState] = useState(() => {
    try {
      const stored = localStorage.getItem(LANG_KEY);
      return stored === 'en' ? 'en' : 'ru';
    } catch {
      return 'ru';
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(LANG_KEY, lang);
    } catch {}
  }, [lang]);

  const setLang = (l) => setLangState(l === 'en' ? 'en' : 'ru');

  return (
    <LanguageContext.Provider value={{ lang, setLang }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error('useLanguage must be used within LanguageProvider');
  return ctx;
}
