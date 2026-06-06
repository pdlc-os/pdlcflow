// Typed REST client — matches the pdlc-engine adapter surface (Phase D).

import { clearSession, fireUnauthorized, getToken, type Identity } from './token';

const BASE = '/v1';

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const r = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      'content-type': 'application/json',
      ...(token ? { authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (r.status === 401) {
    // Auth is enforced and we have no/expired token — surface the login overlay.
    clearSession();
    fireUnauthorized();
  }
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

// ── Atlas Console (admin analytics) ───────────────────────────────────────
// Mirrors the REST contract under /v1/admin. Every data route requires org_id
// (a missing org_id is a 422 — the cross-org ban, plan §5.3).
export interface RollupRow {
  key: string;
  events: number;
  tokens: number;
  usd: number;
}

export interface AdminEvent {
  event_type: string;
  ts: string;
  roadmap_id?: string | null;
  actor?: string | null;
  [k: string]: unknown;
}

export interface LiveResponse {
  events: AdminEvent[];
}

export interface RollupResponse {
  rows: RollupRow[];
}

export interface AgentsHeatmap {
  personas: string[];
  cells: RollupRow[];
}

export interface FeatureTimeline {
  roadmap_id: string;
  events: AdminEvent[];
}

export type RollupDimension =
  | 'initiative'
  | 'application'
  | 'squad'
  | 'domain'
  | 'roadmap'
  | 'user_story'
  | 'agent';

export const admin = {
  live: (orgId: string, limit = 50) =>
    json<LiveResponse>(`/admin/live?org_id=${encodeURIComponent(orgId)}&limit=${limit}`),

  initiativesRollup: (orgId: string) =>
    json<RollupResponse>(`/admin/initiatives/rollup?org_id=${encodeURIComponent(orgId)}`),

  domainsRollup: (orgId: string) =>
    json<RollupResponse>(`/admin/domains/rollup?org_id=${encodeURIComponent(orgId)}`),

  squadsScoreboard: (orgId: string) =>
    json<RollupResponse>(`/admin/squads/scoreboard?org_id=${encodeURIComponent(orgId)}`),

  // org_id is optional here: the persona list needs no org; cells require one.
  agentsHeatmap: (orgId?: string) =>
    json<AgentsHeatmap>(
      `/admin/agents/heatmap${orgId ? `?org_id=${encodeURIComponent(orgId)}` : ''}`,
    ),

  featureTimeline: (orgId: string, roadmapId: string) =>
    json<FeatureTimeline>(
      `/admin/features/${encodeURIComponent(roadmapId)}/timeline?org_id=${encodeURIComponent(orgId)}`,
    ),

  exportsCsvUrl: (orgId: string, dimension: RollupDimension) =>
    `${BASE}/admin/exports/rollup.csv?org_id=${encodeURIComponent(orgId)}&dimension=${dimension}`,
};

export interface LoginResponse {
  access_token: string;
  token_type: string;
  identity: Identity;
}

export const api = {
  health: () => json<{ status: string }>('/../health'),

  login: (email: string, password: string) =>
    json<LoginResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  me: () => json<Identity>('/auth/me'),

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
