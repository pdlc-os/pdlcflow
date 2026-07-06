import { create } from 'zustand';

import { api } from '@/lib/api';
import { beginPkce, expectedState, takeVerifier } from '@/lib/pkce';
import {
  clearSession,
  type Identity,
  loadIdentity,
  onUnauthorized,
  setSession,
} from '@/lib/token';
import { useThread } from '@/store/useThread';

type AuthMode = 'local' | 'oidc';

interface AuthStore {
  identity: Identity | null;
  mode: AuthMode; // whether to render the password form or the SSO redirect
  needsLogin: boolean; // a 401 (or a manual "Sign in") shows the login overlay
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  loginSso: () => Promise<void>; // OIDC auth-code + PKCE redirect
  completeSso: () => Promise<boolean>; // handle the ?code= callback; true if handled
  refreshMode: () => Promise<void>;
  logout: () => void;
  promptLogin: () => void;
  dismissLogin: () => void;
}

export const useAuth = create<AuthStore>((set) => ({
  identity: loadIdentity(),
  mode: 'local',
  needsLogin: false,
  error: null,

  refreshMode: async () => {
    try {
      const { mode } = await api.authMode();
      set({ mode });
    } catch {
      /* leave default 'local' */
    }
  },

  login: async (email, password) => {
    set({ error: null });
    try {
      const res = await api.login(email, password);
      setSession(res.access_token, res.identity);
      // Bind the Studio's org to the token's org so requests match the principal.
      useThread.setState({ orgId: res.identity.org_id });
      set({ identity: res.identity, needsLogin: false, error: null });
    } catch {
      set({ error: 'Invalid email or password' });
    }
  },

  loginSso: async () => {
    set({ error: null });
    try {
      const cfg = await api.oidcConfig();
      const { challenge, state } = await beginPkce();
      const redirectUri = cfg.redirect_uri || window.location.origin + '/';
      const url = new URL(cfg.authorization_endpoint);
      url.searchParams.set('response_type', 'code');
      url.searchParams.set('client_id', cfg.client_id);
      url.searchParams.set('redirect_uri', redirectUri);
      url.searchParams.set('scope', cfg.scopes);
      url.searchParams.set('code_challenge', challenge);
      url.searchParams.set('code_challenge_method', 'S256');
      url.searchParams.set('state', state);
      window.location.assign(url.toString());
    } catch {
      set({ error: 'SSO is unavailable' });
    }
  },

  completeSso: async () => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const state = params.get('state');
    if (!code) return false;
    const verifier = takeVerifier();
    const expected = expectedState();
    // Clean the code/state out of the URL regardless of outcome.
    window.history.replaceState({}, '', window.location.pathname);
    if (!verifier || (expected && state !== expected)) {
      set({ error: 'SSO sign-in could not be verified', needsLogin: true });
      return true;
    }
    try {
      const res = await api.oidcExchange(code, verifier, window.location.origin + '/');
      setSession(res.access_token, res.identity);
      useThread.setState({ orgId: res.identity.org_id });
      set({ identity: res.identity, needsLogin: false, error: null });
    } catch {
      set({ error: 'SSO sign-in failed', needsLogin: true });
    }
    return true;
  },

  logout: () => {
    clearSession();
    set({ identity: null });
  },

  promptLogin: () => set({ needsLogin: true }),
  dismissLogin: () => set({ needsLogin: false, error: null }),
}));

// Detect the server's auth mode + handle an OIDC redirect callback on load.
void useAuth.getState().refreshMode();
void useAuth.getState().completeSso();

// A 401 from any API call surfaces the login overlay + drops the stale identity.
onUnauthorized(() => useAuth.setState({ needsLogin: true, identity: null }));

// On load, if we have a stored session, adopt its org so commands match the token.
const _stored = loadIdentity();
if (_stored) useThread.setState({ orgId: _stored.org_id });
