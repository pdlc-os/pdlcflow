import { create } from 'zustand';

/** Selected hierarchy scope (domain → squad → repo, + initiative), persisted.
 *  org/project live in useThread; this holds the rest of the nav selection. */
type ScopeKey = 'domain' | 'squad' | 'initiative' | 'repo';

const k = (key: ScopeKey) => `pdlcflow-scope-${key}`;
const load = (key: ScopeKey) => (typeof window !== 'undefined' ? localStorage.getItem(k(key)) : null);
const persist = (key: ScopeKey, v: string | null) => {
  if (typeof window === 'undefined') return;
  if (v) localStorage.setItem(k(key), v);
  else localStorage.removeItem(k(key));
};

interface ScopeStore {
  domainId: string | null;
  squadId: string | null;
  initiativeId: string | null;
  repoId: string | null;
  setScope: (key: ScopeKey, id: string | null) => void;
}

export const useScope = create<ScopeStore>((set) => ({
  domainId: load('domain'),
  squadId: load('squad'),
  initiativeId: load('initiative'),
  repoId: load('repo'),
  setScope: (key, id) => {
    persist(key, id);
    set({ [`${key}Id`]: id } as Partial<ScopeStore>);
  },
}));
