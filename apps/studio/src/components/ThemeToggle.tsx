import { Monitor, Moon, Sun } from 'lucide-react';

import { useTheme } from '@/store/useTheme';

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const cycle = () =>
    setTheme(theme === 'light' ? 'dark' : theme === 'dark' ? 'system' : 'light');
  const Icon = theme === 'dark' ? Moon : theme === 'light' ? Sun : Monitor;
  return (
    <button
      onClick={cycle}
      aria-label="Theme"
      className="rounded-md p-1 text-muted-fg hover:bg-border/60 hover:text-fg"
    >
      <Icon className="h-4 w-4" />
    </button>
  );
}
