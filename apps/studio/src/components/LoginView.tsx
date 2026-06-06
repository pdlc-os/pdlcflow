import { useState } from 'react';

import { useAuth } from '@/store/useAuth';

/** Modal login overlay — shown on a 401 or when the user clicks "Sign in". */
export function LoginView() {
  const { login, error, dismissLogin, identity } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    await login(email, password);
    setBusy(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <form
        onSubmit={submit}
        className="w-80 rounded-xl border border-border bg-bg p-5 shadow-xl"
      >
        <h2 className="mb-1 text-lg font-semibold tracking-tight">Sign in to pdlcflow</h2>
        <p className="mb-4 text-xs text-muted-fg">
          Authentication is enabled — sign in to continue.
        </p>
        <label className="mb-2 block text-xs text-muted-fg">
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoFocus
            required
            className="mt-1 w-full rounded-md border border-border bg-muted/30 px-2 py-1.5 text-sm text-fg outline-none focus:border-accent"
          />
        </label>
        <label className="mb-3 block text-xs text-muted-fg">
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="mt-1 w-full rounded-md border border-border bg-muted/30 px-2 py-1.5 text-sm text-fg outline-none focus:border-accent"
          />
        </label>
        {error && <p className="mb-2 text-xs text-red-500">{error}</p>}
        <div className="flex items-center justify-between">
          <button
            type="submit"
            disabled={busy}
            className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-fg disabled:opacity-50"
          >
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
          {/* Dismiss is allowed only when there's still a valid session (manual prompt). */}
          {identity && (
            <button
              type="button"
              onClick={dismissLogin}
              className="text-xs text-muted-fg hover:text-fg"
            >
              Cancel
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
