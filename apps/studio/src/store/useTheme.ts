import { create } from 'zustand';

import { applyTheme, getStoredTheme, setTheme as persistTheme, Theme } from '@/lib/theme';

interface ThemeStore {
  theme: Theme;
  setTheme: (t: Theme) => void;
}

export const useTheme = create<ThemeStore>((set) => ({
  theme: getStoredTheme(),
  setTheme: (t) => {
    persistTheme(t);
    applyTheme(t);
    set({ theme: t });
  },
}));
