import { Link, Outlet } from 'react-router-dom';
import { LogOut, Monitor, Moon, Sun } from 'lucide-react';

import type { Theme } from '@/lib/theme';
import { useTheme } from '@/store/useTheme';
import { useAuth } from '@/store/useAuth';
import { LoginView } from '@/components/LoginView';
import { ScopeNav } from '@/components/ScopeNav';
import { StatusLine } from '@/components/StatusLine';
import { SideDrawer } from '@/components/SideDrawer';

// Cycle light → dark → system → light.
const NEXT_THEME: Record<Theme, Theme> = { light: 'dark', dark: 'system', system: 'light' };

export function AppShell() {
  const { theme, setTheme } = useTheme();
  const { identity, needsLogin, logout, promptLogin } = useAuth();
  return (
    <div className="flex h-full flex-col">
      <header className="flex h-12 items-center gap-2 border-b border-border px-4 text-sm">
        <Link to="/" className="mr-1 font-semibold tracking-tight">pdlcflow</Link>
        <ScopeNav />
        <span className="ml-3 rounded-full bg-accent/10 px-2 py-0.5 text-xs text-accent">
          Inception · Discover
        </span>
        <div className="ml-auto flex items-center gap-3 text-muted-fg">
          <Link to="/admin/live" className="hover:text-fg">Nexus Console</Link>
          {identity ? (
            <span className="flex items-center gap-1.5">
              <span className="text-xs text-fg" title={`${identity.email} · ${identity.role}`}>
                {identity.email}
              </span>
              <button aria-label="Sign out" onClick={logout} className="rounded-md p-1 hover:bg-border/60">
                <LogOut className="h-4 w-4" />
              </button>
            </span>
          ) : (
            <button onClick={promptLogin} className="text-xs hover:text-fg">Sign in</button>
          )}
          <button
            aria-label={`Theme: ${theme} (click to change)`}
            title={`Theme: ${theme}`}
            onClick={() => setTheme(NEXT_THEME[theme])}
            className="rounded-md p-1 hover:bg-border/60"
          >
            {theme === 'light' ? (
              <Sun className="h-4 w-4" />
            ) : theme === 'dark' ? (
              <Moon className="h-4 w-4" />
            ) : (
              <Monitor className="h-4 w-4" />
            )}
          </button>
        </div>
      </header>

      {needsLogin && <LoginView />}

      <div className="flex flex-1 overflow-hidden">
        <SideDrawer />
        <main className="flex-1 overflow-auto px-6 py-4">
          <Outlet />
        </main>
      </div>

      <StatusLine />
    </div>
  );
}
