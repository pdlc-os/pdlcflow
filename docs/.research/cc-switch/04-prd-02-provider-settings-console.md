# PRD-02: Provider Settings Console

| | |
|---|---|
| **Status** | Draft — for assessment |
| **Date** | 2026-07-05 |
| **Origin** | [cc-switch gap analysis](02-gap-analysis.md), gap #3 |
| **Related PRDs** | [PRD-01 BYOK Completion](03-prd-01-byok-completion.md) (key entry field, `has_key`) · [PRD-03 Health & Connectivity](05-prd-03-provider-health-connectivity.md) (Test button backend) · [PRD-04 Preset Catalog](06-prd-04-provider-preset-catalog.md) (one-click presets layer on this console) |

## 1. Problem & motivation

pdlcflow has a complete, working admin REST surface for per-org model configuration —
`GET/PUT /admin/models/org-default`, `GET/PUT/DELETE /admin/models/agent-overrides/{persona}`
(`services/pdlc-engine/app/routes/admin/models.py`) — and **no way to use it**. The only UI,
`apps/studio/src/routes/admin/models.tsx`, is a 57-line static mockup: `ProviderRow` renders a
`<select>`, an `<input>`, and a "Test" button with **no state, no fetch, no handlers**
(`models.tsx:34-56`). `apps/studio/src/lib/api.ts` has zero client methods for the models
routes. Practically, "switching your org's provider" today means hand-crafting an authenticated
PUT with curl.

**What cc-switch does here:** its core value is exactly this surface — one-click provider
switching from a GUI, per-role model mapping (sonnet/opus/haiku ↔ pdlcflow's
premium/balanced/economy tiers), active-provider protection, and a Test affordance. cc-switch
proves that the ergonomics of switching, not the plumbing, is what users pay attention to.
pdlcflow's translation: make the existing mockup a real org-scoped settings console in Studio's
Nexus admin area.

## 2. Goals / Non-goals

**Goals**

- G1: An org admin can view and change the org default provider + tier map, and per-persona
  overrides, entirely from the console; changes take effect on the next LLM call (that is
  already the backend semantic — factory re-reads config per call, `app/llm/factory.py:102-107`).
- G2: API-key entry/rotation/clearing per scope (org default, per-persona), building on PRD-01's
  `api_key` write-only field and `has_key` flag.
- G3: "Test" button per row actually validates the candidate config before save (PRD-03's
  `POST /admin/models/test`), with latency + error shown inline.
- G4: Guardrails: unsaved-change tracking, confirm dialog on org-wide provider switch,
  "inherit" clearly distinguished from an explicit override, Sentinel row stays disabled
  (deterministic evaluator, no model — as the mockup already notes, `models.tsx:16`).
- G5: Sensible empty state: when no org row exists (`GET` returns `null`,
  `routes/admin/models.py:61`), show the effective instance default so the admin knows what
  they're currently inheriting.

**Non-goals**

- Preset catalog / searchable vendor list (PRD-04 — this console is the substrate it lands on).
- Health badges from background monitoring (PRD-03 stretch; this PRD only wires the on-demand
  Test button).
- Config history/rollback UI (PRD-06).
- Non-admin (member-facing) visibility of model settings.
- CLI providers in the picker — the admin API's `Provider` literal already excludes
  `claude_code`/`codex`/`gemini_cli` (`routes/admin/models.py:25`) because they are single-user
  self-host only (`factory.py:115-129`); the console mirrors that.

## 3. Users & user stories

- **Org admin** — "As an org admin, I switch my org from Bedrock to Anthropic direct in two
  clicks and see it confirmed."
- **Org admin** — "As an org admin, I pin the `jarvis` persona to `gpt-5.5` on OpenAI while
  everything else stays on the org default, and I can see at a glance which personas are
  overridden vs inheriting."
- **Org admin** — "Before saving a new key/endpoint, I hit Test and see ✓ 412 ms or a
  human-readable failure."
- **Platform operator (self-host)** — "With auth off, I pass `?org_id=` (the existing
  `admin_org` behavior, `routes/admin/_guard.py`) and manage the single org the same way."

## 4. Functional requirements

| ID | Requirement | MoSCoW |
|---|---|---|
| FR-1 | Load state on mount: org default (`GET /admin/models/org-default`) + overrides (`GET /admin/models/agent-overrides`); render all 10 personas, marking those without an override row as "— inherit —". | Must |
| FR-2 | Org-default editor: provider select, tier-map editor (3 model-id inputs: premium/balanced/economy), optional region + endpoint fields, Save. | Must |
| FR-3 | Tier-map inputs prefill with the provider's defaults when the provider changes and no override exists — requires a new read-only endpoint `GET /admin/models/defaults` exposing `DEFAULT_TIER_MAP` + provider list (`app/llm/tier_map.py:16`). | Must |
| FR-4 | Per-persona rows: provider select (incl. "— inherit —"), model-id input, Save per row, Clear-override action (DELETE). | Must |
| FR-5 | API key field per scope: password input, shown as "●●● key set" chip when `has_key`; entering a value and saving rotates; explicit "Remove key" action (PRD-01 DELETE endpoints). Key is never prefilled. | Must |
| FR-6 | Test button per row calls `POST /admin/models/test` with the row's *current (possibly unsaved)* values; renders ✓ + latency or ✗ + error class inline. Disabled while a test is in flight. | Must |
| FR-7 | Dirty tracking: rows visually mark unsaved edits; navigating away with dirty rows warns. | Should |
| FR-8 | Confirm dialog on org-default provider change ("This changes the model behind every agent for your whole org on their next turn"). | Should |
| FR-9 | Save results in optimistic UI + toast on success; on failure the row reverts and shows the error. | Should |
| FR-10 | Empty state (no org row): banner "Inheriting instance default (<provider>)" using `GET /admin/models/defaults`' `instance_default` field. | Should |
| FR-11 | Region/endpoint fields shown contextually (region for bedrock/vertex/azure; endpoint for ollama/azure) rather than always. | Could |
| FR-12 | Sentinel row rendered but permanently disabled with the existing explanation. | Must |

## 5. Detailed design

### 5.1 Backend additions (small)

Only one new endpoint (the rest exists or comes from PRD-01/PRD-03):

`GET /v1/admin/models/defaults` (behind `admin_org`, read-only):

```jsonc
{
  "providers": ["bedrock", "anthropic", "vertex", "azure", "openai", "gemini", "ollama"],
  "personas":  ["atlas", "bolt", ..., "sentinel"],
  "tier_maps": { "bedrock": {"premium": "anthropic.claude-opus-4-8", ...}, ... },  // DEFAULT_TIER_MAP, CLI providers omitted
  "instance_default": { "provider": "bedrock", "region": "us-east-1" }             // from settings.default_llm_provider
}
```

~25 LOC in `routes/admin/models.py`; sources: `tier_map.DEFAULT_TIER_MAP`,
`settings.default_llm_provider` (`app/config.py:53`), the existing `Provider`/`Persona`
literals. Also (from PRD-01) GET responses gain `has_key`, and `GET /agent-overrides` already
returns the full override list (`routes/admin/models.py:84-95`).

### 5.2 API client (`apps/studio/src/lib/api.ts`)

New types + methods on the existing `admin` object (matching its `orgId`-query idiom,
`api.ts:140-189`):

```ts
export interface OrgDefault {
  provider: string;
  tier_map: Record<'premium' | 'balanced' | 'economy', string>;
  region: string | null;
  endpoint: string | null;
  has_key: boolean;
}
export interface AgentOverride {
  agent_persona: string;
  provider: string;
  model_id: string;
  region: string | null;
  endpoint: string | null;
  has_key: boolean;
}
export interface ModelDefaults {
  providers: string[];
  personas: string[];
  tier_maps: Record<string, Record<string, string>>;
  instance_default: { provider: string; region: string | null };
}
export interface TestResult {          // PRD-03 schema
  ok: boolean; latency_ms: number | null; error_class: string | null;
  tested_model: string | null; message: string | null;
}

export const admin = {
  // …existing methods…
  modelDefaults: (orgId: string) =>
    json<ModelDefaults>(`/admin/models/defaults?org_id=${encodeURIComponent(orgId)}`),
  getOrgDefault: (orgId: string) =>
    json<OrgDefault | null>(`/admin/models/org-default?org_id=${encodeURIComponent(orgId)}`),
  putOrgDefault: (orgId: string, body: Partial<OrgDefault> & { api_key?: string }) =>
    json<{ ok: boolean; has_key: boolean }>(
      `/admin/models/org-default?org_id=${encodeURIComponent(orgId)}`,
      { method: 'PUT', body: JSON.stringify(body) }),
  deleteOrgKey: (orgId: string) =>
    json<{ ok: boolean }>(`/admin/models/org-default/key?org_id=${encodeURIComponent(orgId)}`,
      { method: 'DELETE' }),
  listAgentOverrides: (orgId: string) =>
    json<AgentOverride[]>(`/admin/models/agent-overrides?org_id=${encodeURIComponent(orgId)}`),
  putAgentOverride: (orgId: string, persona: string, body: Partial<AgentOverride> & { api_key?: string }) =>
    json<{ ok: boolean }>(
      `/admin/models/agent-overrides/${encodeURIComponent(persona)}?org_id=${encodeURIComponent(orgId)}`,
      { method: 'PUT', body: JSON.stringify(body) }),
  deleteAgentOverride: (orgId: string, persona: string) =>
    json<{ ok: boolean }>(
      `/admin/models/agent-overrides/${encodeURIComponent(persona)}?org_id=${encodeURIComponent(orgId)}`,
      { method: 'DELETE' }),
  deleteAgentKey: (orgId: string, persona: string) =>
    json<{ ok: boolean }>(
      `/admin/models/agent-overrides/${encodeURIComponent(persona)}/key?org_id=${encodeURIComponent(orgId)}`,
      { method: 'DELETE' }),
  testProvider: (orgId: string, body: object) =>
    json<TestResult>(`/admin/models/test?org_id=${encodeURIComponent(orgId)}`,
      { method: 'POST', body: JSON.stringify(body) }),
};
```

The `json<T>` helper (`api.ts:7-24`) already handles auth headers and 401 → login overlay; note
it currently doesn't set `body` pass-through for non-GET — it does via `init` spread, matching
how command invocation calls do it elsewhere in the file.

### 5.3 Component state flow (`apps/studio/src/routes/admin/models.tsx` — rewrite)

State shape (plain `useState` + `useEffect`, matching the repo's existing data-fetch idiom in
Studio routes — no react-query in the stack today):

```
AdminModels
├── defaults: ModelDefaults | null        (loaded once)
├── orgDefault: OrgDefaultDraft           (server value + local edits + dirty flag)
├── overrides: Map<persona, OverrideDraft>(server rows merged over all-persona skeleton)
├── testState: Map<rowKey, 'idle'|'testing'|TestResult>
└── saveState: Map<rowKey, 'idle'|'saving'|'error'>
```

Flow:

1. **Mount** → `Promise.all([admin.modelDefaults, admin.getOrgDefault, admin.listAgentOverrides])`
   → build drafts. `orgId` comes from the same session/org context the other admin routes use.
2. **Edit** → update draft, set `dirty`. Provider change in org default → if tier_map untouched
   by user, replace with `defaults.tier_maps[provider]` (FR-3).
3. **Save org default** → if provider changed from server value → confirm dialog (FR-8) →
   `admin.putOrgDefault(orgId, draft)` (include `api_key` only if the key input is non-empty)
   → on success clear dirty, set `has_key` from response, clear key input, toast.
4. **Save override** → `admin.putAgentOverride`; **Clear** → `admin.deleteAgentOverride` →
   row returns to "— inherit —".
5. **Test** → assemble candidate from the *draft* (not server state); if the key input is empty
   and `has_key`, send `use_saved_key: true` (PRD-03); set row `testing`; render result chip.
6. **Dirty guard** → `beforeunload` + router-level prompt when any draft dirty (FR-7).

Layout keeps the mockup's structure (org-default card + per-agent card, `models.tsx:19-29`),
each `ProviderRow` gaining: model inputs (3 tier inputs for the org row, 1 model-id input for
persona rows — mirroring the backend's shapes `OrgDefault.tier_map` vs `AgentOverride.model_id`),
key field with `has_key` chip, contextual region/endpoint (FR-11), Save/Clear/Test buttons,
result chip.

### 5.4 Edge cases

- **No org row + persona overrides exist**: legal server state; org card shows the
  instance-default banner while override rows show their values.
- **Concurrent admins**: last-write-wins (matches backend upsert semantics,
  `routes/admin/models.py:70-77`); PRD-06 adds versioning later. Refetch after every save
  keeps drift small.
- **Persona list source of truth**: render from `defaults.personas`, not a hardcoded array —
  removes the duplicated `PERSONAS` const (`models.tsx:5-8`).

## 6. Security & tenancy

- All calls hit routes behind `admin_org()` (`routes/admin/_guard.py`) — admin/owner role under
  auth, explicit `org_id` param without. The console passes `org_id` exactly as the other Nexus
  admin screens do (`api.ts:140-189`).
- Key input is `type="password"`, `autocomplete="off"`, cleared after save, never persisted to
  client storage; the UI only ever knows `has_key`. No key material in URLs (keys travel only
  in PUT bodies).
- Test requests may carry a candidate key (pre-save validation) — same POST-body treatment;
  see PRD-03 §6 for server-side handling and SSRF constraints on candidate endpoints.

## 7. Rollout & migration

- Pure additive UI + one read-only endpoint. No migration, no flag needed; ships dark for orgs
  that never open Settings → Models.
- Sequence after PRD-01 (key field + `has_key`) and ideally after PRD-03 (else ship with the
  Test button hidden behind a `defaults.test_available` capability flag so the console doesn't
  block on the probe work).
- Wiki: update `03-configuration.md` "per-tenant model config" section to point at the console
  instead of raw curl.

## 8. Testing strategy (hermetic)

- **Backend**: route test for `GET /admin/models/defaults` (shape + CLI providers excluded).
  Existing models-route tests already cover CRUD.
- **Frontend**: component tests with the repo's existing frontend test setup, mocking the
  `admin.*` client: load→render (10 personas, inherit markers), provider-change→tier-map
  prefill, save happy path + failure revert, key chip states (none / set / rotated), dirty
  guard, Sentinel disabled, confirm-dialog on provider switch.
- **Contract drift guard**: a TS type test (or generated-types check) asserting
  `OrgDefault`/`AgentOverride` client types match the Pydantic response models — cheap
  insurance since this PRD triples the models-route client surface.
- No E2E-against-live-LLM anywhere; Test-button flows mock `testProvider`.

## 9. Effort estimate

**M — ~2 engineer-weeks.** Frontend rewrite of `models.tsx` (~350 LOC) + client methods/types
(~80 LOC) + component tests ≈ 1.2 w; backend defaults endpoint + tests ≈ 0.3 w; polish
(dialogs, toasts, dirty guard) ≈ 0.5 w. Assumes PRD-01/PRD-03 APIs exist (else −Test/−key
scope shrinks it to S).

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Admin switches org provider without valid creds → every turn in the org starts failing | FR-6/FR-8: Test-before-save affordance + confirm dialog naming the blast radius; PRD-03 probe validates the exact candidate |
| Tier-map free-text model IDs typo'd | Prefill from `DEFAULT_TIER_MAP` (FR-3) + Test button exercises the *resolved* model; PRD-04 presets remove most free-typing later |
| Client/server type drift as the API grows | Contract test in §8; single source for persona/provider lists (FR-3 endpoint) |
| Last-write-wins between two admins | Acceptable now (single-org admin teams are small); PRD-06 versioning restores any clobbered state |

## 11. Success metrics

- An org can be moved provider→provider end-to-end (change, test, save, next turn uses it) in
  < 60 s without touching curl — demo-scriptable.
- 0 raw-API (curl) provider changes needed in supported workflows.
- Test-button usage precedes > 50% of saves that change provider/key (telemetry via existing
  clickstream admin events) — indicates the guardrail works.
- No increase in "org misconfigured" support incidents after switch (proxy: error-rate on
  `llm.calls` for orgs that changed config, visible in the Nexus dashboard).

## 12. Dependencies

- **PRD-01** (api_key field, `has_key`, key DELETE endpoints) — hard dependency for key UX.
- **PRD-03** (`POST /admin/models/test`) — hard dependency for the Test button (or ship
  behind capability flag).
- Existing: admin models routes, `admin_org` guard, Studio auth/session plumbing, `json<T>`
  client helper.

## 13. Open questions

1. Should per-persona rows allow tier selection (persona keeps org provider but forces
   `economy`)? Backend has no such column today (`agent_llm_config.model_id` is concrete,
   `db/models.py:281`); defer unless demand appears.
2. Where does this live in Nexus IA — current route is `admin/models`; does it merge with a
   future broader "Settings" section when PRD-04/06 add presets and history tabs? Proposed:
   keep `Models` page, add tabs later.
3. Self-host no-auth mode: is a bare org-id text input acceptable at the top of the page (as
   other admin screens do), or should Studio grow an org switcher first? Proposed: match the
   existing screens; don't block on an org switcher.
