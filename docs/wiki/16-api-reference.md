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

`kind` is `approval` (the 8 gates) or `user_input_required` (Socratic/Bloom's
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

## Admin (Atlas Console)

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
| `GET /v1/admin/exports/rollup.csv` | `org_id`, `dimension`, `from?`, `to?` | `text/csv` |
| `GET /v1/admin/models/org-default` | — | `OrgDefault \| null` (stub) |
| `PUT /v1/admin/models/org-default` | body `OrgDefault` | `{ok: true}` (stub) |
| `GET /v1/admin/models/agent-overrides` | — | `[AgentOverride]` (stub) |
| `PUT /v1/admin/models/agent-overrides/{persona}` | body `AgentOverride` | `{ok, persona}` (stub) |
| `POST /v1/admin/models/test` | `provider` | `{provider, ok, phase}` (stub) |

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
- `gate_kind` — for approvals, one of the **8 gates**: `discover_summary`,
  `prd_approve`, `design_docs_approve`, `beads_tasklist_approve`,
  `review_md_approve`, `merge_and_deploy_approve`, `smoke_signoff`,
  `episode_approve` (plus the night-shift `night_shift_contract`).
- `payload.visual` — an optional render-agnostic screen spec the
  BrainstormVisualCompanion renders (option cards / mermaid / mockup).


---
<!-- nav:bottom -->
⏮ [First: Overview](01-overview.md) · ◀ [Prev: Migration — importing an upstream pdlc project](15-migration.md) · [🏠 Home](README.md) · [Next: Home](README.md) ▶ · [Last: API Reference](16-api-reference.md) ⏭
