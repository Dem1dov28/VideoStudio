import { createContext, useContext, useState, useEffect } from 'react';

const MODE_KEY = 'content-factory-mode';

const ModeContext = createContext({
  mode: 1,
  setMode: () => {},
});

export function ModeProvider({ children }) {
  const [mode, setModeState] = useState(() => {
    try {
      const stored = localStorage.getItem(MODE_KEY);
      let v = stored ? parseInt(stored, 10) : 1;
      if (v === 12) v = 4;
      return [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13].includes(v) ? v : 1;
    } catch {
      return 1;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(MODE_KEY, String(mode));
    } catch {}
  }, [mode]);

  const setMode = (m) => {
    if (m === 12) m = 4;
    setModeState([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13].includes(m) ? m : 1);
  };

  return (
    <ModeContext.Provider value={{ mode, setMode }}>
      {children}
    </ModeContext.Provider>
  );
}

export function useMode() {
  const ctx = useContext(ModeContext);
  if (!ctx) throw new Error('useMode must be used within ModeProvider');
  return ctx;
}
