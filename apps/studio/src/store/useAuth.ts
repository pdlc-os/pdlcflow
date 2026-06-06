import { create } from 'zustand';

import { api } from '@/lib/api';
import {
  clearSession,
  type Identity,
  loadIdentity,
  onUnauthorized,
  setSession,
} from '@/lib/token';
import { useThread } from '@/store/useThread';

interface AuthStore {
  identity: Identity | null;
  needsLogin: boolean; // a 401 (or a manual "Sign in") shows the login overlay
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  promptLogin: () => void;
  dismissLogin: () => void;
}

export const useAuth = create<AuthStore>((set) => ({
  identity: loadIdentity(),
  needsLogin: false,
  error: null,

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

  logout: () => {
    clearSession();
    set({ identity: null });
  },

  promptLogin: () => set({ needsLogin: true }),
  dismissLogin: () => set({ needsLogin: false, error: null }),
}));

// A 401 from any API call surfaces the login overlay + drops the stale identity.
onUnauthorized(() => useAuth.setState({ needsLogin: true, identity: null }));

// On load, if we have a stored session, adopt its org so commands match the token.
const _stored = loadIdentity();
if (_stored) useThread.setState({ orgId: _stored.org_id });
