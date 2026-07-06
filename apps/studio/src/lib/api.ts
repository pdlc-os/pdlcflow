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

  // ── Models settings (org default + per-agent overrides + probes) ─────────
  modelDefaults: (orgId: string) =>
    json<ModelDefaults>(`/admin/models/defaults?org_id=${encodeURIComponent(orgId)}`),

  getOrgDefault: (orgId: string) =>
    json<OrgDefault | null>(`/admin/models/org-default?org_id=${encodeURIComponent(orgId)}`),

  putOrgDefault: (orgId: string, body: OrgDefaultBody) =>
    json<{ ok: boolean; has_key: boolean }>(
      `/admin/models/org-default?org_id=${encodeURIComponent(orgId)}`,
      { method: 'PUT', body: JSON.stringify(body) },
    ),

  deleteOrgKey: (orgId: string) =>
    json<{ ok: boolean }>(
      `/admin/models/org-default/key?org_id=${encodeURIComponent(orgId)}`,
      { method: 'DELETE' },
    ),

  listAgentOverrides: (orgId: string) =>
    json<AgentOverride[]>(`/admin/models/agent-overrides?org_id=${encodeURIComponent(orgId)}`),

  putAgentOverride: (orgId: string, persona: string, body: AgentOverrideBody) =>
    json<{ ok: boolean; persona: string; has_key: boolean }>(
      `/admin/models/agent-overrides/${encodeURIComponent(persona)}?org_id=${encodeURIComponent(orgId)}`,
      { method: 'PUT', body: JSON.stringify(body) },
    ),

  deleteAgentOverride: (orgId: string, persona: string) =>
    json<{ ok: boolean }>(
      `/admin/models/agent-overrides/${encodeURIComponent(persona)}?org_id=${encodeURIComponent(orgId)}`,
      { method: 'DELETE' },
    ),

  deleteAgentKey: (orgId: string, persona: string) =>
    json<{ ok: boolean }>(
      `/admin/models/agent-overrides/${encodeURIComponent(persona)}/key?org_id=${encodeURIComponent(orgId)}`,
      { method: 'DELETE' },
    ),

  testProvider: (orgId: string, body: ProbeBody) =>
    json<TestResult>(
      `/admin/models/test?org_id=${encodeURIComponent(orgId)}`,
      { method: 'POST', body: JSON.stringify(body) },
    ),

  listPresets: (orgId: string, q?: string) =>
    json<PresetCatalog>(
      `/admin/models/presets?org_id=${encodeURIComponent(orgId)}${q ? `&q=${encodeURIComponent(q)}` : ''}`,
    ),

  listVersions: (orgId: string, scope?: string, limit = 20) =>
    json<{ versions: ConfigVersion[] }>(
      `/admin/models/versions?org_id=${encodeURIComponent(orgId)}${scope ? `&scope=${encodeURIComponent(scope)}` : ''}&limit=${limit}`,
    ),

  rollbackVersion: (orgId: string, versionId: string) =>
    json<{ ok: boolean; restored_scope: string; secret_requires_reentry: boolean }>(
      `/admin/models/versions/${encodeURIComponent(versionId)}/rollback?org_id=${encodeURIComponent(orgId)}`,
      { method: 'POST' },
    ),

  exportModels: (orgId: string) =>
    json<object>(`/admin/models/export?org_id=${encodeURIComponent(orgId)}`),

  importModels: (orgId: string, doc: object, opts?: { dryRun?: boolean; strategy?: 'merge' | 'replace' }) =>
    json<ImportResult>(
      `/admin/models/import?org_id=${encodeURIComponent(orgId)}` +
        `${opts?.dryRun ? '&dry_run=true' : ''}&strategy=${opts?.strategy ?? 'merge'}`,
      { method: 'POST', body: JSON.stringify(doc) },
    ),

  getPricing: (orgId: string) =>
    json<PricingSheet>(`/admin/pricing?org_id=${encodeURIComponent(orgId)}`),

  putPricingOverrides: (orgId: string, overrides: Record<string, PriceInOut>) =>
    json<{ ok: boolean; keys: number }>(
      `/admin/pricing/overrides?org_id=${encodeURIComponent(orgId)}`,
      { method: 'PUT', body: JSON.stringify(overrides) },
    ),

  getBudget: (orgId: string) =>
    json<BudgetInfo | null>(`/admin/budget?org_id=${encodeURIComponent(orgId)}`),

  putBudget: (orgId: string, body: { monthly_limit_usd: number; alert_pcts?: number[] }) =>
    json<{ ok: boolean }>(`/admin/budget?org_id=${encodeURIComponent(orgId)}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),

  getQuota: (orgId: string) =>
    json<QuotaInfo>(`/admin/budget/quota?org_id=${encodeURIComponent(orgId)}`),

  putQuota: (orgId: string, rpmLimit: number | null) =>
    json<{ ok: boolean; rpm_limit: number | null }>(
      `/admin/budget/quota?org_id=${encodeURIComponent(orgId)}`,
      { method: 'PUT', body: JSON.stringify({ rpm_limit: rpmLimit }) },
    ),

  // ── Persona prompt overrides (PRD-10) ────────────────────────────────────
  listPersonaPrompts: (orgId: string) =>
    json<{ personas: PromptSummary[] }>(`/admin/prompts?org_id=${encodeURIComponent(orgId)}`),

  getPersonaPrompt: (orgId: string, persona: string) =>
    json<PromptDetail>(
      `/admin/prompts/${encodeURIComponent(persona)}?org_id=${encodeURIComponent(orgId)}`,
    ),

  getPromptVersion: (orgId: string, persona: string, version: number) =>
    json<{ version: number; status: string; body: string }>(
      `/admin/prompts/${encodeURIComponent(persona)}/versions/${version}?org_id=${encodeURIComponent(orgId)}`,
    ),

  createPromptDraft: (orgId: string, persona: string, body: string) =>
    json<{ ok: boolean; version: number }>(
      `/admin/prompts/${encodeURIComponent(persona)}?org_id=${encodeURIComponent(orgId)}`,
      { method: 'POST', body: JSON.stringify({ body }) },
    ),

  activatePromptVersion: (orgId: string, persona: string, version: number) =>
    json<{ ok: boolean; active_version: number }>(
      `/admin/prompts/${encodeURIComponent(persona)}/versions/${version}/activate?org_id=${encodeURIComponent(orgId)}`,
      { method: 'POST' },
    ),

  deactivatePrompt: (orgId: string, persona: string) =>
    json<{ ok: boolean }>(
      `/admin/prompts/${encodeURIComponent(persona)}/deactivate?org_id=${encodeURIComponent(orgId)}`,
      { method: 'POST' },
    ),

  exportPromptPack: (orgId: string) =>
    json<PromptPack>(`/admin/prompts/export?org_id=${encodeURIComponent(orgId)}`),

  importPromptPack: (orgId: string, pack: object, dryRun = false) =>
    json<{ plan?: Record<string, string>; created?: Record<string, number> }>(
      `/admin/prompts/import?org_id=${encodeURIComponent(orgId)}${dryRun ? '&dry_run=true' : ''}`,
      { method: 'POST', body: JSON.stringify(pack) },
    ),

  // ── MCP tool servers (PRD-09) ────────────────────────────────────────────
  listMCPServers: (orgId: string) =>
    json<{ servers: MCPServer[] }>(`/admin/mcp/servers?org_id=${encodeURIComponent(orgId)}`),

  listMCPTemplates: (orgId: string) =>
    json<{ templates: MCPTemplate[] }>(`/admin/mcp/templates?org_id=${encodeURIComponent(orgId)}`),

  createMCPServer: (orgId: string, body: MCPServerBody) =>
    json<{ ok: boolean; id: string }>(
      `/admin/mcp/servers?org_id=${encodeURIComponent(orgId)}`,
      { method: 'POST', body: JSON.stringify(body) },
    ),

  updateMCPServer: (orgId: string, id: string, body: MCPServerBody) =>
    json<{ ok: boolean }>(
      `/admin/mcp/servers/${encodeURIComponent(id)}?org_id=${encodeURIComponent(orgId)}`,
      { method: 'PUT', body: JSON.stringify(body) },
    ),

  deleteMCPServer: (orgId: string, id: string) =>
    json<{ ok: boolean }>(
      `/admin/mcp/servers/${encodeURIComponent(id)}?org_id=${encodeURIComponent(orgId)}`,
      { method: 'DELETE' },
    ),

  testMCPServer: (orgId: string, id: string) =>
    json<{ ok: boolean; latency_ms?: number; tools?: { name: string; description: string }[]; error?: string }>(
      `/admin/mcp/servers/${encodeURIComponent(id)}/test?org_id=${encodeURIComponent(orgId)}`,
      { method: 'POST' },
    ),

  setMCPBindings: (orgId: string, id: string, bindings: MCPBinding[]) =>
    json<{ ok: boolean }>(
      `/admin/mcp/servers/${encodeURIComponent(id)}/bindings?org_id=${encodeURIComponent(orgId)}`,
      { method: 'PUT', body: JSON.stringify({ bindings }) },
    ),
};

export interface MCPBinding {
  persona: string;
  phase: string | null;
}

export interface MCPServer {
  id: string;
  name: string;
  transport: 'http' | 'stdio';
  url: string | null;
  command: string | null;
  args: string[];
  allowed_tools: string[];
  enabled: boolean;
  has_auth: boolean;
  bindings: MCPBinding[];
}

/** auth_token is WRITE-ONLY (omit on update = keep the stored one). */
export interface MCPServerBody {
  name: string;
  transport: 'http' | 'stdio';
  url?: string | null;
  command?: string | null;
  args?: string[];
  auth_token?: string;
  allowed_tools: string[];
  enabled: boolean;
}

export interface MCPTemplate {
  id: string;
  name: string;
  transport: 'http' | 'stdio';
  url?: string;
  command?: string;
  args?: string[];
  allowed_tools: string[];
  note: string;
}

export interface PromptSummary {
  persona: string;
  versions: number;
  active_version: number | null;
  overridden: boolean;
}

export interface PromptDetail {
  persona: string;
  packaged_default: string;
  versions: { version: number; status: string; created_at: string; activated_at: string | null }[];
}

export interface PromptPack {
  format: string;
  exported_at: string;
  prompts: Record<string, { body: string; source_version: number }>;
}

export interface PriceInOut {
  in: number;
  out: number;
}

export interface PricingSheet {
  catalog_version: string;
  disclaimer: string;
  effective: Record<string, PriceInOut & { source: 'catalog' | 'preset' | 'override' }>;
}

export interface BudgetInfo {
  monthly_limit_usd: number;
  alert_pcts: number[];
  month_to_date_usd: number;
  fired: number[];
}

export interface QuotaInfo {
  rpm_limit: number | null;
  rpm_default: number;
  enforced: boolean;
}

// Models settings types — mirror app/routes/admin/models.py response models.
export type TierName = 'premium' | 'balanced' | 'economy';

export interface FallbackEntryView {
  provider: string;
  region: string | null;
  endpoint: string | null;
  tier_map: Record<TierName, string> | null;
  has_key: boolean;
}

/** Chain entry on PUT: api_key is WRITE-ONLY (omit = carry the stored key over). */
export interface FallbackEntryBody {
  provider: string;
  region?: string | null;
  endpoint?: string | null;
  tier_map?: Record<TierName, string> | null;
  api_key?: string;
}

export interface OrgDefault {
  provider: string;
  tier_map: Record<TierName, string>;
  region: string | null;
  endpoint: string | null;
  has_key: boolean;
  failover_chain: FallbackEntryView[];
}

/** PUT body: api_key is WRITE-ONLY (omit = keep the stored key). */
export interface OrgDefaultBody {
  provider: string;
  tier_map: Record<TierName, string>;
  region?: string | null;
  endpoint?: string | null;
  api_key?: string;
  failover_chain?: FallbackEntryBody[];
}

export interface ConfigVersion {
  id: string;
  scope: string;
  change_kind: 'update' | 'delete' | 'rollback' | 'import' | 'preset_apply';
  actor_label: string | null;
  created_at: string;
  diff: { field: string; from: unknown; to: unknown }[];
}

export interface ImportPlanItem {
  scope: string;
  action: 'create' | 'overwrite' | 'skip' | 'error' | 'pending';
  reasons: string[];
  secret: string;
}

export interface ImportResult {
  ok?: boolean;
  applied?: number;
  plan: ImportPlanItem[];
  strategy?: string;
}

export interface AgentOverride {
  agent_persona: string;
  provider: string;
  model_id: string;
  region: string | null;
  endpoint: string | null;
  has_key: boolean;
}

export interface AgentOverrideBody {
  agent_persona: string;
  provider: string;
  model_id: string;
  region?: string | null;
  endpoint?: string | null;
  api_key?: string;
}

export interface ModelDefaults {
  providers: string[];
  personas: string[];
  tier_maps: Record<string, Record<TierName, string>>;
  instance_default: { provider: string; region: string | null };
}

/** POST /admin/models/test — candidate (provider…) or saved scope. */
export interface ProbeBody {
  provider?: string;
  model_id?: string;
  tier?: TierName;
  region?: string | null;
  endpoint?: string | null;
  api_key?: string;
  scope?: string; // 'org-default' | `agent:${persona}`
  use_saved_key?: boolean;
}

export interface TestResult {
  ok: boolean;
  latency_ms: number | null;
  error_class: string | null;
  tested_model: string | null;
  message: string;
}

export interface Preset {
  id: string;
  label: string;
  provider: string;
  endpoint: string | null;
  region: string | null;
  tier_map: Record<TierName, string>;
  docs_url: string | null;
  key_hint: string | null;
  tags: string[];
  needs_secret: boolean;
}

export interface PresetCatalog {
  catalog_version: string;
  presets: Preset[];
}

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

  continueThread: (body: { thread_id: string; org_id: string; prompt: string }) =>
    json<{ thread_id: string; response: string }>('/commands/continue', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

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
const patch = <T>(path: string, body: unknown) =>
  json<T>(path, { method: 'PATCH', body: JSON.stringify(body) });
const del = <T>(path: string) => json<T>(path, { method: 'DELETE' });

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

  // rename + delete (org-scoped). `kind` is the route segment.
  rename: (kind: 'domains' | 'squads' | 'initiatives' | 'projects', org: string, id: string, name: string) =>
    patch<{ id: string; name: string }>(`/${kind}/${e(id)}?org_id=${e(org)}`, { name }),
  remove: (kind: 'domains' | 'squads' | 'initiatives' | 'projects', org: string, id: string) =>
    del<{ deleted: string }>(`/${kind}/${e(id)}?org_id=${e(org)}`),

  repoFiles: (org: string, repoId: string, path = '') =>
    json<{ path: string; entries: RepoEntry[] }>(
      `/repositories/${e(repoId)}/files?org_id=${e(org)}&path=${e(path)}`),
  repoFile: (org: string, repoId: string, path: string) =>
    json<{ path: string; name: string; content: string }>(
      `/repositories/${e(repoId)}/file?org_id=${e(org)}&path=${e(path)}`),

  // Project memory artifacts (PRD/design/decisions/deployments/uploads/…).
  projectArtifacts: (org: string, projectId: string) =>
    json<{ project_id: string; artifacts: string[] }>(
      `/projects/${e(projectId)}/artifacts?org_id=${e(org)}`),
  projectArtifact: (org: string, projectId: string, path: string) =>
    json<{ path: string; content: string }>(
      `/projects/${e(projectId)}/artifacts/content?org_id=${e(org)}&path=${e(path)}`),

  projectTasks: (org: string, projectId: string) =>
    json<{ project_id: string; tasks: ProjectTask[] }>(
      `/projects/${e(projectId)}/tasks?org_id=${e(org)}`),
};

export interface ProjectTask {
  external_id: string;
  title: string;
  status: string;
  labels: string[];
  branch: string | null;
  claimed_by: string | null;
}

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
