import { create } from 'zustand';

interface SessionStore {
  user: { id: string; email: string; role: string } | null;
  orgId: string | null;
  squadId: string | null;
  setIdentity: (u: SessionStore['user'], orgId: string, squadId: string | null) => void;
  clear: () => void;
}

export const useSession = create<SessionStore>((set) => ({
  user: null,
  orgId: null,
  squadId: null,
  setIdentity: (user, orgId, squadId) => set({ user, orgId, squadId }),
  clear: () => set({ user: null, orgId: null, squadId: null }),
}));
