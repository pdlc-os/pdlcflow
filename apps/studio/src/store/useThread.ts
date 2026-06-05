import { create } from 'zustand';

interface Message {
  id: string;
  role: 'user' | 'agent' | 'system';
  persona?: string;
  text: string;
  steps?: Array<{ kind: 'tool' | 'llm' | 'verdict' | 'pitch'; summary: string }>;
}

interface ThreadStore {
  threadId: string | null;
  messages: Message[];
  open: (threadId: string) => void;
  appendToken: (chunk: string) => void;
  appendStep: (step: Message['steps'][number]) => void;
  appendMessage: (m: Message) => void;
  close: () => void;
}

export const useThread = create<ThreadStore>((set) => ({
  threadId: null,
  messages: [],
  open: (threadId) => set({ threadId, messages: [] }),
  appendToken: (chunk) =>
    set((s) => {
      const last = s.messages[s.messages.length - 1];
      if (!last || last.role !== 'agent') {
        return {
          messages: [...s.messages, { id: crypto.randomUUID(), role: 'agent', text: chunk }],
        };
      }
      return {
        messages: [
          ...s.messages.slice(0, -1),
          { ...last, text: last.text + chunk },
        ],
      };
    }),
  appendStep: (step) =>
    set((s) => {
      const last = s.messages[s.messages.length - 1];
      if (!last) return s;
      return {
        messages: [
          ...s.messages.slice(0, -1),
          { ...last, steps: [...(last.steps ?? []), step] },
        ],
      };
    }),
  appendMessage: (m) => set((s) => ({ messages: [...s.messages, m] })),
  close: () => set({ threadId: null, messages: [] }),
}));
