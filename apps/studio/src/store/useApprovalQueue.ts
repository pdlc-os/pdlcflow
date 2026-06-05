import { create } from 'zustand';

interface OpenGate {
  id: string;
  gate_kind: string;
  artifact_uri?: string;
  summary?: string[];
  opened_at: string;
}

interface ApprovalQueueStore {
  open: OpenGate[];
  add: (g: OpenGate) => void;
  remove: (id: string) => void;
  reset: (gates: OpenGate[]) => void;
}

export const useApprovalQueue = create<ApprovalQueueStore>((set) => ({
  open: [],
  add: (g) => set((s) => ({ open: [...s.open, g] })),
  remove: (id) => set((s) => ({ open: s.open.filter((g) => g.id !== id) })),
  reset: (gates) => set({ open: gates }),
}));
