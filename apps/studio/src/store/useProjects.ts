import { create } from 'zustand';

/**
 * Client-side project registry (localStorage). Release A bridge: lets you create
 * + name projects and drive the chat/nav without the server-side Project entity.
 * Release B (the schema redesign) promotes this to a real, org-scoped entity.
 */
export interface ProjectMeta {
  id: string;
  name: string;
}

const KEY = 'pdlcflow-projects';

function load(): ProjectMeta[] {
  if (typeof window === 'undefined') return [];
  try {
    return JSON.parse(localStorage.getItem(KEY) || '[]') as ProjectMeta[];
  } catch {
    return [];
  }
}

function save(list: ProjectMeta[]) {
  if (typeof window !== 'undefined') localStorage.setItem(KEY, JSON.stringify(list));
}

function shortId(id: string): string {
  return id.length > 8 ? `proj-${id.slice(0, 6)}` : id;
}

interface ProjectsStore {
  projects: ProjectMeta[];
  create: (name: string) => ProjectMeta;
  ensure: (id: string, name?: string) => void;
  nameFor: (id: string) => string;
}

export const useProjects = create<ProjectsStore>((set, get) => ({
  projects: load(),

  create: (name) => {
    const p: ProjectMeta = { id: crypto.randomUUID(), name: name.trim() || 'Untitled project' };
    const next = [p, ...get().projects];
    save(next);
    set({ projects: next });
    return p;
  },

  // Register a project id we encountered (e.g. a deep link) so it shows in the nav.
  ensure: (id, name) => {
    if (!id || get().projects.some((p) => p.id === id)) return;
    const next = [...get().projects, { id, name: name || shortId(id) }];
    save(next);
    set({ projects: next });
  },

  nameFor: (id) => get().projects.find((p) => p.id === id)?.name ?? shortId(id),
}));
