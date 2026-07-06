import { useEffect, useState } from 'react';

import { useAuth } from '@/store/useAuth';

/** Modal login overlay — shown on a 401 or when the user clicks "Sign in".
 *  Always dismissable (Cancel / Esc / backdrop): in self-hosted simulation mode
 *  auth is optional, so the user must be able to escape back to the app. */
export function LoginView() {
  const { login, loginSso, mode, error, dismissLogin } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);

  // Esc closes the overlay.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') dismissLogin();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [dismissLogin]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    await login(email, password);
    setBusy(false);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={dismissLogin}
    >
      <form
        onSubmit={submit}
        onClick={(e) => e.stopPropagation()}
        className="w-80 rounded-xl border border-border bg-bg p-5 shadow-xl"
      >
        <h2 className="mb-1 text-lg font-semibold tracking-tight">Sign in to pdlcflow</h2>
        <p className="mb-4 text-xs text-muted-fg">
          Sign in to continue. Press Esc or Cancel to dismiss.
        </p>
        {mode === 'oidc' && (
          <>
            <button
              type="button"
              onClick={() => void loginSso()}
              className="mb-3 w-full rounded-md bg-accent px-3 py-2 text-sm font-medium text-accent-fg"
            >
              Sign in with SSO
            </button>
            {error && <p className="mb-2 text-xs text-red-500">{error}</p>}
            <p className="text-center text-xs text-muted-fg">
              Your organization uses single sign-on.
            </p>
          </>
        )}
        {mode !== 'oidc' && (
        <>
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
          <button
            type="button"
            onClick={dismissLogin}
            className="text-xs text-muted-fg hover:text-fg"
          >
            Cancel
          </button>
        </div>
        </>
        )}
      </form>
    </div>
  );
}
