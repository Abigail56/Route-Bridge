'use client';

import { createContext, useContext, useEffect, useMemo, useState } from 'react';

type ThemeChoice = 'system' | 'light' | 'dark';
type ThemeContextValue = { theme: ThemeChoice; setTheme: (theme: ThemeChoice) => void };

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<ThemeChoice>('system');

  useEffect(() => {
    const saved = window.localStorage.getItem('routebridge-theme') as ThemeChoice | null;
    if (saved === 'system' || saved === 'light' || saved === 'dark') setTheme(saved);
  }, []);

  useEffect(() => {
    window.localStorage.setItem('routebridge-theme', theme);
    const root = document.documentElement;
    const resolved = theme === 'system'
      ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
      : theme;
    root.dataset.theme = resolved;
    root.dataset.themeChoice = theme;
  }, [theme]);

  useEffect(() => {
    if (theme !== 'system') return;
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const update = () => { document.documentElement.dataset.theme = media.matches ? 'dark' : 'light'; };
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, [theme]);

  const value = useMemo(() => ({ theme, setTheme }), [theme]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) throw new Error('useTheme must be used inside ThemeProvider');
  return context;
}
