<!-- nav:top -->
[🏠 Wiki Home](README.md)

# API Reference

The pdlc-engine (`services/pdlc-engine/`) is a FastAPI app. All REST endpoints
are mounted under `/v1` except the health probes (root) and the WebSocket
(`/ws/...`). Auth is currently open (Cognito/JWT enforcement is deferred).

Router mounts (`app/main.py`):

```
health      → (root)
commands    → /v1
approval-gates → /v1
admin       → /v1/admin
migrate     → /v1
websocket   → /ws
```

---

## Commands

### `POST /v1/commands`

Start (or resume) a graph thread for a slash command. The engine builds the
initial `PDLCState`, runs the meta-graph to its first pause via the
GraphRunner, and returns the thread id plus any pending interaction.

**Request** (`InvokeCommandRequest`):

```json
{
  "command": "brainstorm",
  "org_id": "uuid", "project_id": "uuid",
  "args": [],
  "feature": "dark mode",
  "interaction_mode": "sketch",
  "seed_state": { }
}
```

- `command` — one of the **17**: `init`, `brainstorm`, `build`, `ship`,
  `decide`, `whatif`, `doctor`, `rollback`, `hotfix`, `night-shift`, `pause`,
  `resume`, `abandon`, `release`, `override`, `pdlc`, `setup`.
- `interaction_mode` — `sketch` (default) or `socratic`.
- `seed_state` — optional initial-state seed (e.g. `{tasks:[…]}` for `/build`,
  or `{utility_args:{…}}` for utilities). Tenancy + phase keys are always
  re-asserted and cannot be overridden.

The phase is derived from the command (`init/setup → Initialization`,
`brainstorm → Inception`, `build → Construction`, `ship → Operation`);
`night-shift` sets `night_shift_active`; utility commands set
`utility_command`.

**Response** (`InvokeCommandResponse`):

```json
{ "thread_id": "org:project:session", "started": true, "pending": { } }
```

`pending` is `null` if the thread ran to completion, else a pending-interaction
object (see [Pending shape](#pending-interaction-shape)).

---

## Approval gates

### `GET /v1/approval-gates`

List open interactions (approval gates + question rounds), optionally scoped.

**Query:** `org_id?`, `project_id?`
**Response:** `[Gate]`:

```json
[ { "id": "uuid", "thread_id": "…", "org_id": "…", "project_id": "…",
    "kind": "approval", "gate_kind": "prd_approve", "payload": { }, "status": "open" } ]
```

`kind` is `approval` (the 9 gates) or `user_input_required` (Socratic/Bloom's
question rounds). `gate_kind` is set for approvals.

### `POST /v1/approval-gates/{gate_id}/resolve`

Resolve a pending interaction; resumes the thread with `Command(resume=…)` and
returns the next pause (or `null` at completion).

**Request** (`ResolveRequest`) — shape depends on the interaction kind:

```json
// approval gate
{ "approved": true, "comment": "lgtm", "edit": { } }
// question round
{ "answers": ["…", "…"] }
```

**Response** (`ResolveResponse`):

```json
{ "ok": true, "thread_id": "…", "pending": { } }
```

Errors: `404` if the gate id is unknown; `409` if it is already resolved.

---

## Entities

Org-scoped CRUD for the [hierarchy](18-data-model.md). The org comes from the JWT
when auth is on, else an `org_id` query param; writes go through `set_org_context`
so RLS confines each tenant to its own rows. See the data model for how these relate.

| Method · Path | Body / Query | Response |
|---|---|---|
| `GET /v1/domains` | `org_id` | `{domains: [{id, name}]}` |
| `POST /v1/domains` | `{name}` | `{id, name}` |
| `GET /v1/squads` | `org_id` | `{squads: [{id, name, slug, domain_id}]}` |
| `POST /v1/squads` | `{name, domain_id?}` | `{id, name, slug, domain_id}` |
| `GET /v1/initiatives` | `org_id` | `{initiatives: [{id, name, status}]}` |
| `POST /v1/initiatives` | `{name, status?}` | `{id, name, status}` |
| `GET /v1/repositories` | `org_id`, `squad_id?` | `{repositories: [{id, name, url, squad_id, default_branch, provider, has_token}]}` |
| `POST /v1/repositories` | `{squad_id, name, url, token?, default_branch?, provider?}` | repo (token stored via the secrets backend, **never returned** — only `has_token`) |
| `DELETE /v1/repositories/{id}` | `org_id` | `{deleted}` |
| `GET /v1/repositories/{id}/files` | `org_id`, `path=""` | `{path, entries: [{name, path, type, size}]}` — GitHub contents |
| `GET /v1/repositories/{id}/file` | `org_id`, `path` | `{path, name, content}` |
| `GET /v1/projects` | `org_id` | `{projects: [{id, name, slug, squad_id, repository_id}]}` |
| `POST /v1/projects` | `{name, squad_id, repository_id?}` | `{id, name, slug, squad_id, repository_id}` |
| `POST /v1/uploads` | multipart: `file`, `project_id`, `conversation_id` | `{id, filename, stored_as, conversation_id, size, content_type, is_text, uri, text}` — chat attachment; stored at `uploads/{conversation}/{ts}-{nonce}-{name}`; `text` is the extracted content (utf-8 / pdf / docx / xlsx / pptx). 15 MB cap. |

---

## Admin (Nexus Console)

All under `/v1/admin`. **Data routes require `org_id`** — a missing/blank value
emits an `admin.access.denied` audit event and returns **403** (cross-org ban).

| Method · Path | Query | Response |
|---|---|---|
| `GET /v1/admin/live` | `org_id`, `limit=50` | `{events: [...]}` newest-first |
| `GET /v1/admin/initiatives/rollup` | `org_id`, `from?`, `to?` | `{rows: [{key,events,tokens,usd}]}` |
| `GET /v1/admin/domains/rollup` | `org_id`, `from?`, `to?` | `{rows: [...]}` |
| `GET /v1/admin/squads/scoreboard` | `org_id`, `from?`, `to?` | `{rows: [...]}` |
| `GET /v1/admin/agents/heatmap` | `org_id?` | `{personas: [10], cells: [...]}` |
| `GET /v1/admin/features/{roadmap_id}/timeline` | `org_id` | `{roadmap_id, events: [...]}` |
| `GET /v1/admin/narrative` | `org_id`, `from?`, `to?`, `project_id?` | `{summary: {...}, narrative}` — work stats (human/agent/system) + LLM narrative |
| `GET /v1/admin/context` | `org_id`, `project_id?` | `{model_id, context_window, peak_prompt_tokens, pct_used, near_limit, ...}` |
| `GET /v1/admin/threads` | `org_id`, `project_id?` | `{threads: [{thread_id, label, turns, last_ts}]}` |
| `GET /v1/admin/threads/{thread_id}` | `org_id` | `{thread_id, transcript: [{role, text, ts}], pending}` |
| `GET /v1/admin/evals/summary` | `org_id` | `{by_eval: {...}, by_agent: {...}}` |
| `GET /v1/admin/exports/rollup.csv` | `org_id`, `dimension`, `from?`, `to?` | `text/csv` |
| `GET /v1/admin/models/defaults` | `org_id` | `{providers, personas, tier_maps, instance_default}` — console prefill lists |
| `GET /v1/admin/models/presets` | `org_id`, `q?` | `{catalog_version, presets: [{id, label, provider, endpoint, tier_map, docs_url, key_hint, tags, needs_secret}]}` |
| `POST /v1/admin/models/presets/{id}/apply` | `org_id` | `{ok, applied: {provider, endpoint, region, tier_map}, needs_secret}` — one-click org default |
| `GET /v1/admin/models/org-default` | `org_id` | `OrgDefault \| null` (incl. `has_key`; never key/ref material) |
| `PUT /v1/admin/models/org-default` | `org_id`, body `OrgDefault` (+ write-only `api_key?`, `failover_chain?` ≤3 entries each with write-only `api_key?`) | `{ok, has_key}` |
| `DELETE /v1/admin/models/org-default/key` | `org_id` | `{ok: true}` — clears the stored BYOK key |
| `GET /v1/admin/models/agent-overrides` | `org_id` | `[AgentOverride]` (incl. `has_key`) |
| `PUT /v1/admin/models/agent-overrides/{persona}` | `org_id`, body `AgentOverride` (+ write-only `api_key?`) | `{ok, persona, has_key}` |
| `DELETE /v1/admin/models/agent-overrides/{persona}` | `org_id` | `{ok, persona}` |
| `DELETE /v1/admin/models/agent-overrides/{persona}/key` | `org_id` | `{ok, persona}` |
| `POST /v1/admin/models/test` | `org_id`, body candidate `{provider, model_id?/tier?, region?, endpoint?, api_key?}` or saved `{scope, use_saved_key?}` | `{ok, latency_ms, error_class, tested_model, message}` (10/min per org) |
| `GET /v1/admin/models/health` | `org_id` | `{health: [{scope, provider, ok, latency_ms, error_class, checked_at}]}` |
| `GET /v1/admin/models/versions` | `org_id`, `scope?`, `limit?` | `{versions: [{id, scope, change_kind, actor_label, created_at, diff}]}` — immutable config history (secrets render only as set/changed/cleared) |
| `POST /v1/admin/models/versions/{id}/rollback` | `org_id` | `{ok, restored_scope, secret_requires_reentry}` — appends a `rollback` version, never rewrites history |
| `GET /v1/admin/models/export` | `org_id` | Self-describing provider-set JSON — **never contains key material** (`enc:` refs stripped; `vault:`/`env:` export as pointers) |
| `POST /v1/admin/models/import` | `org_id`, `dry_run?`, `strategy=merge\|replace`, body = export document | dry-run: `{plan: [{scope, action, reasons, secret}]}`; apply: `{ok, applied, plan}` — atomic, reuses the write-path validators |
| `GET /v1/admin/pricing` | `org_id` | `{catalog_version, disclaimer, effective: {"provider/model": {in, out, source: catalog\|preset\|override}}}` |
| `PUT /v1/admin/pricing/overrides` | `org_id`, body `{"provider/model": {in, out}}` | `{ok, keys}` — full-replace of the org's override sheet (409 until a provider is configured) |
| `GET /v1/admin/budget` | `org_id` | `{monthly_limit_usd, alert_pcts, month_to_date_usd, fired} \| null` |
| `PUT /v1/admin/budget` | `org_id`, body `{monthly_limit_usd, alert_pcts?}` | `{ok}` — soft monthly budget; thresholds emit `budget.threshold` events |
| `GET /v1/admin/prompts` | `org_id` | `{personas: [{persona, versions, active_version, overridden}]}` (9 LLM personas; sentinel excluded) |
| `GET /v1/admin/prompts/{persona}` | `org_id` | `{persona, packaged_default, versions: [{version, status, …}]}` |
| `POST /v1/admin/prompts/{persona}` | `org_id`, body `{body}` | `{version}` — new immutable draft (≤32 KiB) |
| `POST /v1/admin/prompts/{persona}/versions/{v}/activate` | `org_id` | `{ok, active_version}` — archives the prior active |
| `POST /v1/admin/prompts/{persona}/deactivate` | `org_id` | `{ok}` — back to the packaged soul-spec |
| `GET /v1/admin/prompts/export` · `POST …/import` | `org_id`, `dry_run?` | prompt-pack JSON (`pdlcflow.prompt-pack/v1`); imports land as drafts |
| `GET/POST /v1/admin/mcp/servers` · `PUT/DELETE …/{id}` | `org_id`, body `{name, transport, url\|command+args, auth_token? (write-only), allowed_tools, enabled}` | MCP server registry — reads expose only `has_auth`; stdio rejected outside single-user self-host; URLs SSRF-checked |
| `POST /v1/admin/mcp/servers/{id}/test` | `org_id` | `{ok, latency_ms, tools: [{name, description}]}` — live tools/list probe |
| `PUT /v1/admin/mcp/servers/{id}/bindings` | `org_id`, body `{bindings: [{persona, phase?}]}` | Bind a server to personas (optionally per phase); unbound = inert |
| `GET /v1/admin/mcp/templates` | `org_id` | Static server presets (stdio hidden in multi-user mode) |

Notes:
- `from`/`to` are query aliases (mapped to `frm` internally).
- `dimension` ∈ `initiative | application | squad | domain | roadmap |
  user_story | agent`.
- The CSV columns are `key,events,tokens,usd`.
- `agents/heatmap` returns the fixed 10-persona list without an `org_id`; the
  `cells` are empty unless an `org_id` is supplied.

---

## Migrate

### `POST /v1/migrate/import`

Ingest an upstream pdlc project in one POST: `events[]` → analytics store (with
deterministic uuid5 ids ⇒ idempotent re-import), `memory_files[]` → artifact
store at `migrated/{project_id}/{kind}.md`.

**Request** (`ImportPayload`): `org_id`, `project_id`, `taxonomy`,
`memory_files[]`, `tasks[]`, `decisions[]`, `deployments[]`, `events[]` — see
[Migration](15-migration.md) for the full shape.

**Response** (per-kind counts; `events` is net-new):

```json
{ "events": 8, "memory_files": 9, "tasks": 4, "decisions": 2, "deployments": 1 }
```

---

## Health

| Method · Path | Response |
|---|---|
| `GET /health` | `{ "status": "ok", "phase": "A" }` |
| `GET /health/ready` | `{ "status": "ready", "checks": { "db": "stub", "redis": "stub", "llm": "stub" } }` |

(No `/v1` prefix.)

---

## WebSocket — `/ws/threads/{thread_id}`

Per-thread fan-out from the EventBus. On connect the handler sends a `hello`,
then streams frames from `bus.listen(channel)` — which **replays** the thread's
recent history (so a client attaching after a gate opened still sees it) then
yields live frames. Transport-agnostic: the in-memory bus polls history; the
Redis bus replays a bounded list then subscribes, so a frame published by the
Arq worker reaches a socket held open by the API.

Frames (`type` field):

| `type` | Payload | Emitted when |
|---|---|---|
| `hello` | `{thread_id}` | on connect |
| `interaction.opened` | `{interaction: <pending>}` | the graph opens a gate / question round |
| `thread.completed` | `{thread_id, summary}` | the thread reaches a terminal state |
| `night_shift.started` | `{...}` | a night-shift run begins |
| `night_shift.verdict` | `{stage, verdict, reason?}` | Sentinel emits a verdict |
| `night_shift.completed` | `{ok, ...}` | run finishes successfully |
| `night_shift.aborted` | `{reason, ...}` | run aborts |

The `thread.completed` `summary` carries non-null state keys among:
`phase`, `night_shift_outcome`, `night_shift_abort_reason`,
`night_shift_run_id`, `version`, `deploy_tier`, `deploy_url`,
`operation_complete`.

The client may send messages (they are drained and ignored); the connection
auto-reconnects with exponential backoff (`apps/studio/src/lib/ws.ts`).

---

## Pending-interaction shape

Both REST (`pending`) and the `interaction.opened` frame use this shape
(`app/runtime/ports.py` `PendingInteraction.as_dict()`):

```json
{
  "id": "uuid",
  "thread_id": "org:project:session",
  "org_id": "…", "project_id": "…",
  "kind": "approval",
  "gate_kind": "prd_approve",
  "payload": {
    "questions": ["…"], "drafts": [null], "context": "…",
    "summary": "…", "visual": { "screens": [ ] }
  },
  "status": "open"
}
```

- `kind` — `approval` (resolve with `{approved, comment, edit}`) or
  `user_input_required` (resolve with `{answers:[…]}`).
- `gate_kind` — for approvals, one of the **9 gates**: `init_approve`, `discover_summary`,
  `prd_approve`, `design_docs_approve`, `beads_tasklist_approve`,
  `review_md_approve`, `merge_and_deploy_approve`, `smoke_signoff`,
  `episode_approve` (plus the night-shift `night_shift_contract`).
- `payload.visual` — an optional render-agnostic screen spec the
  BrainstormVisualCompanion renders (option cards / mermaid / mockup).


---


---
<!-- nav:bottom -->
⏮ [First: Overview](01-overview.md) · ◀ [Prev: Migration — importing an upstream pdlc project](15-migration.md) · [🏠 Home](README.md) · [Next: Evals Framework](17-evals.md) ▶ · [Last: Evals Framework](17-evals.md) ⏭
