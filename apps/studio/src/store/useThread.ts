import { create } from 'zustand';

import { admin, api, type Pending } from '@/lib/api';
import type { Frame, NightShiftFrame } from '@/lib/ws';

export interface TranscriptItem {
  id: string;
  role: 'user' | 'agent' | 'system';
  text: string;
}

export interface Streaming {
  persona?: string;
  text: string;
}

type Status = 'idle' | 'running' | 'awaiting' | 'complete' | 'error';

interface ThreadStore {
  // Demo tenancy — a real session would source these from auth.
  orgId: string;
  projectId: string;

  threadId: string | null;
  pending: Pending | null;
  status: Status;
  transcript: TranscriptItem[];
  result: Record<string, unknown> | null;  // completion summary (night-shift outcome, etc.)
  verdicts: NightShiftFrame[];  // live night-shift Sentinel verdict stream
  streaming: Streaming | null;  // live "drafting" preview (token frames)

  start: (command: string, opts?: { feature?: string; mode?: 'sketch' | 'socratic' }) => Promise<void>;
  answer: (answers: string[]) => Promise<void>;
  resolveApproval: (approved: boolean, comment?: string) => Promise<void>;
  setPending: (p: Pending | null) => void;
  setResult: (r: Record<string, unknown> | null) => void;
  appendVerdict: (v: NightShiftFrame) => void;
  streamToken: (f: Extract<Frame, { type: 'token' }>) => void;
  openThread: (threadId: string) => Promise<void>;
  newThread: () => void;
  setProject: (projectId: string) => void;
  reset: () => void;
}

const COMMANDS_WITH_VISUAL_SEED = new Set(['brainstorm']);

function say(role: TranscriptItem['role'], text: string): TranscriptItem {
  return { id: crypto.randomUUID(), role, text };
}

// Stable identity across reloads (so conversation history persists). A real
// multi-user deployment sources orgId from the JWT; project/thread persist here.
function persisted(key: string): string {
  if (typeof window === 'undefined') return crypto.randomUUID();
  let v = localStorage.getItem(key);
  if (!v) {
    v = crypto.randomUUID();
    localStorage.setItem(key, v);
  }
  return v;
}

const _persistThread = (id: string | null) => {
  if (typeof window === 'undefined') return;
  if (id) localStorage.setItem('pdlcflow-thread', id);
  else localStorage.removeItem('pdlcflow-thread');
};

export const useThread = create<ThreadStore>((set, get) => ({
  orgId: persisted('pdlcflow-org'),
  projectId: persisted('pdlcflow-project'),
  threadId: typeof window !== 'undefined' ? localStorage.getItem('pdlcflow-thread') : null,
  pending: null,
  status: 'idle',
  transcript: [],
  result: null,
  verdicts: [],
  streaming: null,

  // A new pending/result clears the live preview (the generation that produced it is done).
  setPending: (p) => set({ pending: p, status: p ? 'awaiting' : get().status, streaming: p ? null : get().streaming }),
  setResult: (r) => set({ result: r, streaming: null }),
  appendVerdict: (v) => set((s) => ({ verdicts: [...s.verdicts, v] })),
  streamToken: (f) =>
    set((s) => {
      if (f.start) return { streaming: { persona: f.persona, text: '' } };
      if (f.chunk) return { streaming: { persona: s.streaming?.persona ?? f.persona, text: (s.streaming?.text ?? '') + f.chunk } };
      return {}; // done: leave the buffer until the next pending/result clears it
    }),

  start: async (command, opts) => {
    const { orgId, projectId } = get();
    set({
      status: 'running',
      pending: null,
      result: null,
      verdicts: [],
      streaming: null,
      transcript: [say('user', `/${command}${opts?.feature ? ` ${opts.feature}` : ''}`)],
    });
    try {
      const res = await api.invokeCommand({
        command,
        org_id: orgId,
        project_id: projectId,
        feature: opts?.feature,
        interaction_mode: opts?.mode ?? 'socratic',
        // Seed the visual flag so UX Discovery (and its companion) fires.
        seed_state: COMMANDS_WITH_VISUAL_SEED.has(command) ? { visual: true } : undefined,
      });
      _persistThread(res.thread_id);
      set((s) => ({
        threadId: res.thread_id,
        pending: res.pending,
        status: res.pending ? 'awaiting' : 'complete',
        streaming: null,
        transcript: [
          ...s.transcript,
          say('system', res.pending ? describe(res.pending) : 'Thread completed.'),
        ],
      }));
    } catch (e) {
      set((s) => ({ status: 'error', transcript: [...s.transcript, say('system', String(e))] }));
    }
  },

  answer: async (answers) => {
    const p = get().pending;
    if (!p) return;
    set({ status: 'running' });
    await advance(set, get, p.id, { answers }, say('user', answers.filter(Boolean).join(' · ')));
  },

  resolveApproval: async (approved, comment) => {
    const p = get().pending;
    if (!p) return;
    set({ status: 'running' });
    await advance(set, get, p.id, { approved, comment }, say('user', approved ? 'Approved' : 'Rejected'));
  },

  openThread: async (threadId) => {
    const { orgId } = get();
    set({ status: 'running', transcript: [], pending: null, result: null, streaming: null });
    try {
      const d = await admin.openThread(orgId, threadId);
      _persistThread(threadId);
      set({
        threadId,
        transcript: d.transcript.map((e) => ({
          id: crypto.randomUUID(),
          role: e.role as TranscriptItem['role'],
          text: e.text,
        })),
        pending: d.pending,
        status: d.pending ? 'awaiting' : 'complete',
      });
    } catch (e) {
      set({ status: 'error', transcript: [say('system', String(e))] });
    }
  },

  newThread: () => {
    _persistThread(null);
    set({ threadId: null, pending: null, status: 'idle', transcript: [], result: null, verdicts: [], streaming: null });
  },

  // Switch the active project (persisted) and clear the thread view — callers may
  // then openThread() to load a specific conversation, or start() a fresh one.
  setProject: (projectId) => {
    if (typeof window !== 'undefined') localStorage.setItem('pdlcflow-project', projectId);
    _persistThread(null);
    set({ projectId, threadId: null, pending: null, status: 'idle', transcript: [], result: null, verdicts: [], streaming: null });
  },

  reset: () =>
    set({ threadId: null, pending: null, status: 'idle', transcript: [], result: null, verdicts: [], streaming: null }),
}));

async function advance(
  set: (partial: Partial<ThreadStore> | ((s: ThreadStore) => Partial<ThreadStore>)) => void,
  get: () => ThreadStore,
  gateId: string,
  body: { approved?: boolean; comment?: string; answers?: string[] },
  echo: TranscriptItem,
) {
  try {
    const res = await api.resolveGate(gateId, body);
    set((s) => ({
      pending: res.pending,
      status: res.pending ? 'awaiting' : 'complete',
      streaming: null,
      transcript: [
        ...s.transcript,
        echo,
        say('system', res.pending ? describe(res.pending) : 'Operation lifecycle complete. 🎉'),
      ],
    }));
  } catch (e) {
    set((s) => ({ status: 'error', transcript: [...s.transcript, say('system', String(e))] }));
  }
}

function describe(p: Pending): string {
  if (p.kind === 'approval') return `Approval gate: ${p.gate_kind}`;
  const ctx = p.payload.context ? ` — ${p.payload.context}` : '';
  return `Question round${ctx}`;
}
