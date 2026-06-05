// Typed REST client — matches the pdlc-engine adapter surface (Phase D).

const BASE = '/v1';

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) },
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} ${path}`);
  return r.json() as Promise<T>;
}

// A pending interaction the graph paused on (an approval gate or a question
// round). `payload` carries gate/question detail and an optional `visual` spec
// the BrainstormVisualCompanion renders. Mirrors app/runtime/ports.py.
export interface VisualOption {
  choice: string;
  title: string;
  description: string;
}
export interface VisualScreen {
  type: 'options' | 'mermaid' | 'mockup';
  title: string;
  subtitle?: string;
  key?: string | null;
  options?: VisualOption[];
  mermaid?: string;
  body?: string;
}
export interface VisualSpec {
  screens: VisualScreen[];
}

export interface Pending {
  id: string;
  thread_id: string;
  org_id: string;
  project_id: string;
  kind: 'approval' | 'user_input_required';
  gate_kind: string | null;
  payload: {
    questions?: string[];
    drafts?: string[] | null;
    context?: string | null;
    visual?: VisualSpec | null;
    summary?: string;
    [k: string]: unknown;
  };
  status: string;
}

export interface CommandResponse {
  thread_id: string;
  started: boolean;
  pending: Pending | null;
}

export interface ResolveResponse {
  ok: boolean;
  thread_id: string;
  pending: Pending | null;
}

export interface InvokeBody {
  command: string;
  org_id: string;
  project_id: string;
  args?: string[];
  feature?: string;
  interaction_mode?: 'sketch' | 'socratic';
  seed_state?: Record<string, unknown>;
}

export interface ResolveBody {
  approved?: boolean;
  comment?: string;
  edit?: Record<string, unknown>;
  answers?: string[];
}

export const api = {
  health: () => json<{ status: string }>('/../health'),

  invokeCommand: (body: InvokeBody) =>
    json<CommandResponse>('/commands', { method: 'POST', body: JSON.stringify(body) }),

  listGates: (params?: { org_id?: string; project_id?: string }) => {
    const q = new URLSearchParams();
    if (params?.org_id) q.set('org_id', params.org_id);
    if (params?.project_id) q.set('project_id', params.project_id);
    const qs = q.toString();
    return json<Pending[]>(`/approval-gates${qs ? `?${qs}` : ''}`);
  },

  resolveGate: (id: string, body: ResolveBody) =>
    json<ResolveResponse>(`/approval-gates/${id}/resolve`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
};
