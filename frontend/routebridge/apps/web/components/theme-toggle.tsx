'use client';

import { useTheme } from './theme-provider';

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  return (
    <label className="theme-control" title="Choose display theme">
      <span aria-hidden="true">◐</span>
      <select aria-label="Theme" value={theme} onChange={(event) => setTheme(event.target.value as 'system' | 'light' | 'dark')}>
        <option value="system">Default</option>
        <option value="light">Light</option>
        <option value="dark">Dark</option>
      </select>
    </label>
  );
}
