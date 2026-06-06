import { create } from 'zustand';

import { api, type Pending } from '@/lib/api';
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
  reset: () => void;
}

const COMMANDS_WITH_VISUAL_SEED = new Set(['brainstorm']);

function say(role: TranscriptItem['role'], text: string): TranscriptItem {
  return { id: crypto.randomUUID(), role, text };
}

export const useThread = create<ThreadStore>((set, get) => ({
  orgId: crypto.randomUUID(),
  projectId: crypto.randomUUID(),
  threadId: null,
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
