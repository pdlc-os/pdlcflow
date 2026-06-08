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
  session_id?: string;
  seed_state?: Record<string, unknown>;
}

export interface ResolveBody {
  approved?: boolean;
  comment?: string;
  edit?: Record<string, unknown>;
  answers?: string[];
}

// ── Nexus Console (admin analytics) ───────────────────────────────────────
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

  narrative: (orgId: string, opts?: { from?: string; to?: string; projectId?: string }) => {
    const q = new URLSearchParams({ org_id: orgId });
    if (opts?.from) q.set('from', opts.from);
    if (opts?.to) q.set('to', opts.to);
    if (opts?.projectId) q.set('project_id', opts.projectId);
    return json<NarrativeResponse>(`/admin/narrative?${q.toString()}`);
  },

  contextUsage: (orgId: string, projectId?: string) => {
    const q = new URLSearchParams({ org_id: orgId });
    if (projectId) q.set('project_id', projectId);
    return json<ContextUsage>(`/admin/context?${q.toString()}`);
  },

  listThreads: (orgId: string, projectId?: string) => {
    const q = new URLSearchParams({ org_id: orgId });
    if (projectId) q.set('project_id', projectId);
    return json<{ threads: ThreadSummary[] }>(`/admin/threads?${q.toString()}`);
  },

  openThread: (orgId: string, threadId: string) =>
    json<ThreadDetail>(`/admin/threads/${encodeURIComponent(threadId)}?org_id=${encodeURIComponent(orgId)}`),
};

export interface ThreadSummary {
  thread_id: string;
  project_id: string | null;
  label: string;
  turns: number;
  last_ts: string;
}

export interface ThreadDetail {
  thread_id: string;
  transcript: { seq: number; role: string; text: string; ts: string }[];
  pending: Pending | null;
}

export interface ContextUsage {
  model_id: string | null;
  context_window: number;
  peak_prompt_tokens: number;
  last_prompt_tokens: number;
  cumulative_tokens: number;
  pct_used: number;
  near_limit: boolean;
  calls: number;
}

export interface WorkSummary {
  window: { from: string | null; to: string | null };
  project_id: string | null;
  total_events: number;
  by_actor_type: { human: number; agent: number; system: number };
  by_event_type: Record<string, number>;
  by_agent: Record<string, { events: number; tokens: number }>;
  tokens: number;
  usd: number;
  notable: AdminEvent[];
}

export interface NarrativeResponse {
  summary: WorkSummary;
  narrative: string;
}

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

// ── Entity CRUD (/v1/domains|squads|initiatives|repositories|projects) ─────────
export interface Domain { id: string; name: string }
export interface Squad { id: string; name: string; slug: string; domain_id: string | null }
export interface Initiative { id: string; name: string; status: string }
export interface Repo {
  id: string; name: string; url: string; squad_id: string;
  default_branch: string; provider: string; has_token: boolean;
}
export interface ServerProject {
  id: string; name: string; slug: string; squad_id: string; repository_id: string | null;
}

const e = encodeURIComponent;
const post = <T>(path: string, body: unknown) =>
  json<T>(path, { method: 'POST', body: JSON.stringify(body) });

export const entities = {
  domains: (org: string) => json<{ domains: Domain[] }>(`/domains?org_id=${e(org)}`),
  createDomain: (org: string, name: string) => post<Domain>(`/domains?org_id=${e(org)}`, { name }),

  squads: (org: string) => json<{ squads: Squad[] }>(`/squads?org_id=${e(org)}`),
  createSquad: (org: string, name: string, domain_id?: string | null) =>
    post<Squad>(`/squads?org_id=${e(org)}`, { name, domain_id }),

  initiatives: (org: string) => json<{ initiatives: Initiative[] }>(`/initiatives?org_id=${e(org)}`),
  createInitiative: (org: string, name: string) =>
    post<Initiative>(`/initiatives?org_id=${e(org)}`, { name }),

  repositories: (org: string, squadId?: string) =>
    json<{ repositories: Repo[] }>(`/repositories?org_id=${e(org)}${squadId ? `&squad_id=${e(squadId)}` : ''}`),
  createRepository: (org: string, body: { squad_id: string; name: string; url: string; token?: string; default_branch?: string; provider?: string }) =>
    post<Repo>(`/repositories?org_id=${e(org)}`, body),
  deleteRepository: (org: string, id: string) =>
    json<{ deleted: string }>(`/repositories/${e(id)}?org_id=${e(org)}`, { method: 'DELETE' }),

  projects: (org: string) => json<{ projects: ServerProject[] }>(`/projects?org_id=${e(org)}`),
  createProject: (org: string, body: { name: string; squad_id: string; repository_id?: string | null }) =>
    post<ServerProject>(`/projects?org_id=${e(org)}`, body),

  repoFiles: (org: string, repoId: string, path = '') =>
    json<{ path: string; entries: RepoEntry[] }>(
      `/repositories/${e(repoId)}/files?org_id=${e(org)}&path=${e(path)}`),
  repoFile: (org: string, repoId: string, path: string) =>
    json<{ path: string; name: string; content: string }>(
      `/repositories/${e(repoId)}/file?org_id=${e(org)}&path=${e(path)}`),
};

export interface RepoEntry { name: string; path: string; type: 'file' | 'dir'; size: number }

export interface Upload {
  id: string; filename: string; size: number; content_type: string | null;
  is_text: boolean; uri: string; text: string | null;
}

/** Upload a chat attachment (multipart; lets the browser set the boundary). */
export async function uploadFile(
  org: string, projectId: string, conversationId: string, file: File,
): Promise<Upload> {
  const token = getToken();
  const fd = new FormData();
  fd.append('file', file);
  fd.append('project_id', projectId);
  fd.append('conversation_id', conversationId);
  const r = await fetch(`${BASE}/uploads?org_id=${e(org)}`, {
    method: 'POST',
    headers: token ? { authorization: `Bearer ${token}` } : {},
    body: fd,
  });
  if (!r.ok) throw new Error(`${r.status} upload failed`);
  return r.json() as Promise<Upload>;
}
