// Theme detection + persistence. CSS tokens live in theme.css.

export type Theme = 'light' | 'dark' | 'system';

const KEY = 'pdlcflow-theme';

export function getStoredTheme(): Theme {
  if (typeof window === 'undefined') return 'system';
  return (localStorage.getItem(KEY) as Theme) ?? 'system';
}

export function setTheme(t: Theme): void {
  localStorage.setItem(KEY, t);
  applyTheme(t);
}

export function applyTheme(t: Theme): void {
  const html = document.documentElement;
  const effective =
    t === 'system'
      ? window.matchMedia('(prefers-color-scheme: dark)').matches
        ? 'dark'
        : 'light'
      : t;
  html.classList.toggle('dark', effective === 'dark');
}

export function watchSystemTheme(cb: () => void): () => void {
  const m = window.matchMedia('(prefers-color-scheme: dark)');
  m.addEventListener('change', cb);
  return () => m.removeEventListener('change', cb);
}
