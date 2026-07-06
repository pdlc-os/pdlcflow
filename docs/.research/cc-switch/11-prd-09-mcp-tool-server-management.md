# PRD-09: MCP Tool-Server Management for Agents

- **Status:** Draft — for assessment
- **Date:** 2026-07-05
- **Origin:** [cc-switch gap analysis](02-gap-analysis.md) — gap #10 (GAP, strategic)
- **Related PRDs:** [PRD-01 BYOK](03-prd-01-byok-completion.md) (secretstore-ref pattern reused
  for server auth) · [PRD-02 Settings Console](04-prd-02-provider-settings-console.md) (console
  panel) · [PRD-08 Egress](10-prd-08-egress-network-controls.md) (HTTP MCP calls ride the same
  egress config)

## 1. Problem & motivation

pdlcflow's agents are **closed-world**: personas produce text via `llm_port.complete()`
(`packages/pdlc-graph/pdlc_graph/llm_port.py:97-128`) and the graphs post-process it
deterministically. There is no mechanism for an agent to call an external tool — no web search
for Muse's ideation, no Jira/Linear lookup for Neo's planning, no internal-API introspection for
Atlas's review. Grep confirms zero MCP references anywhere in the codebase
([current state §7](01-pdlcflow-current-state.md)).

**What cc-switch does here:** a unified MCP panel managing servers across five apps, with
bidirectional config sync, deep-link import, server templates, and *binding servers to specific
apps* (inventory §4). Its lesson translates directly: MCP config is fragmented and painful;
centralizing it with explicit app (here: persona/phase) bindings is the winning UX.

For pdlcflow the translation is bigger than config management — it is **net-new agent
capability**: an org-scoped MCP server registry, admin CRUD + console panel, persona/phase
bindings, and engine-side execution so LangGraph nodes can actually call the bound tools. That
is why the gap analysis sequences this last: it changes what agents can *do*, not just how they
are configured, and it carries the sharpest security surface of the whole roadmap.

## 2. Goals / Non-goals

**Goals**
- G1: Org-scoped MCP server registry (transport, endpoint/command, auth, allowed-tool list),
  RLS-isolated like every other org resource.
- G2: Admin CRUD API + Nexus console panel, including a "test connection / list tools" probe.
- G3: Bind servers to personas and/or PDLC phases; unbound servers are inert.
- G4: Engine-side execution: graph nodes can list and call bound tools through a new injectable
  port in `pdlc-graph`, keeping the graph package hermetic (no `mcp` SDK dependency).
- G5: Multi-tenant-safe by construction: HTTP transport only when auth is enforced; stdio
  gated to single-user self-host exactly like CLI providers.
- G6: Full audit: every tool call is a clickstream event with org/persona/server/tool/duration.

**Non-goals**
- NG1: An agentic tool-use *loop* rewrite (full ReAct with model-driven tool selection across
  arbitrary steps). M2 scopes execution to explicit, node-authored tool calls; a model-driven
  loop is a later evolution (§13.1).
- NG2: An MCP *marketplace* / registry search (cc-switch's skills.sh equivalent) — templates
  ship as a static preset list only.
- NG3: pdlcflow acting as an MCP *server* (exposing pdlc actions to external clients) —
  separate idea, separate PRD if ever.
- NG4: Per-user (as opposed to per-org) MCP servers.

## 3. Users & user stories

- **Org admin:** "I register our internal `docs-search` MCP server (HTTPS + bearer token),
  allow only its `search` tool, and bind it to Muse for the Inception phase. Brainstorms now
  cite real internal docs."
- **Org admin:** "I hit *Test* and see the server's tool list and latency before binding
  anything."
- **Self-host single user:** "I bind the filesystem stdio server to Bolt so build steps can
  read my repo checkout — accepting the single-user risk flag, same as CLI providers."
- **Platform operator:** "A tenant's misbehaving MCP server times out; turns degrade gracefully
  (tool returns an error string to the node) and the audit trail shows every call."
- **Compliance reviewer:** "I can enumerate exactly which external endpoints each org's agents
  can reach, from one table."

## 4. Functional requirements

| ID | Requirement | MoSCoW |
|---|---|---|
| FR-1 | `mcp_servers` registry: name, transport (`http` \| `stdio`), url/command+args, auth secret ref, allowed_tools, enabled | Must |
| FR-2 | Admin CRUD API `/admin/mcp/servers` + `/admin/mcp/bindings`, admin-guarded like `routes/admin/models.py` | Must |
| FR-3 | `POST /admin/mcp/servers/{id}/test` → connect, `tools/list`, latency; never persists on failure path | Must |
| FR-4 | Bindings: (server × persona) and (server × phase); a call is allowed iff persona binding matches AND (no phase binding exists OR current phase matches) | Must |
| FR-5 | Graph-side injectable `tool_port` with deterministic no-op/stub default (hermetic CI) | Must |
| FR-6 | Engine backend executes `tools/call` over Streamable HTTP with timeout, size caps, allowlist enforcement | Must |
| FR-7 | stdio transport refused when `auth_required` is on; requires `PDLC_ENABLE_STDIO_MCP=true` (mirror of `_guard_cli`, `app/llm/factory.py:116-129`) | Must |
| FR-8 | `tool.called` clickstream event per invocation (org, persona, server, tool, duration_ms, ok, bytes) | Must |
| FR-9 | Console panel: server list w/ status, add/edit form, test button, binding matrix | Should |
| FR-10 | Server templates (static presets: filesystem, fetch, github, …) prefilled in the add form | Should |
| FR-11 | OTel span per tool call (`pdlc.tool.<name>` nested under the node span, `pdlc_graph/tracing.py` port) | Should |
| FR-12 | Import/export of MCP server sets (rides PRD-06 bundle format) | Could |
| FR-13 | Model-driven multi-step tool loop (ReAct) | Won't (v1) |

## 5. Detailed design

### 5.1 Data model / migrations

```sql
CREATE TABLE mcp_servers (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id         UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  name           TEXT NOT NULL,
  transport      TEXT NOT NULL CHECK (transport IN ('http','stdio')),
  url            TEXT,            -- http: streamable-HTTP endpoint
  command        TEXT,            -- stdio: executable
  args           JSONB NOT NULL DEFAULT '[]',
  auth_secret_ref TEXT,           -- secretstore ref (enc:/vault:/env:), bearer token
  allowed_tools  TEXT[] NOT NULL DEFAULT '{}',   -- empty = deny all (explicit allowlist)
  enabled        BOOLEAN NOT NULL DEFAULT true,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (org_id, name),
  CHECK ((transport = 'http' AND url IS NOT NULL) OR (transport = 'stdio' AND command IS NOT NULL))
);

CREATE TABLE mcp_bindings (
  org_id     UUID NOT NULL,
  server_id  UUID NOT NULL REFERENCES mcp_servers(id) ON DELETE CASCADE,
  persona    TEXT,   -- one of the 10 personas (CHECK mirrors agent_llm_config, db/models.py:286-289)
  phase      TEXT,   -- Inception | Construction | Operation … (nullable)
  PRIMARY KEY (server_id, COALESCE(persona,''), COALESCE(phase,''))
);
-- RLS + FORCE on both, mirroring 0002_rls / 0003_rls_force.
```

Notes: `allowed_tools = '{}'` meaning *deny all* forces admins to consciously allow each tool
(the test probe's tool list makes this a checkbox exercise in the console). Auth reuses
`app/secretstore` (`__init__.py:84-100`) — the API accepts a plaintext token on create, calls
`get_secrets().put()`, stores only the ref, and never returns the plaintext (same write-only
contract PRD-01 establishes for provider keys).

### 5.2 Graph-side port — `pdlc_graph/tool_port.py`

Mirrors `llm_port` (`llm_port.py:36-74`) and `tracing` exactly: Protocol + no-op default +
`set_/reset_` injectors, zero SDK deps.

```python
class _ToolBackend(Protocol):
    def list_tools(self, persona: str) -> list[dict]: ...        # [{server, tool, description, schema}]
    def call_tool(self, persona: str, server: str, tool: str,
                  arguments: dict) -> dict: ...                  # {ok, content|error, duration_ms}

class _NullToolBackend:
    def list_tools(self, persona): return []
    def call_tool(self, persona, server, tool, arguments):
        return {"ok": False, "error": "no tool backend wired", "content": None}
```

Node usage (M2, one call-site pattern):

```python
from pdlc_graph import tool_port
hits = tool_port.call_tool("muse", "docs-search", "search", {"query": feature})
if hits["ok"]:
    prompt += f"\n\nRelevant internal docs:\n{hits['content']}"
```

Hermetic guarantee: with `_NullToolBackend`, `list_tools()` is empty so nodes skip the
tool-augmentation branch entirely — CI output stays byte-identical, same argument as the
tracer port (`tracing.py:1-17`). Tests needing tool output inject a deterministic fake via
`set_tool_backend`, mirroring `reset_completion_backend()` fixtures.

### 5.3 Engine backend — `app/runtime/mcp_backend.py`

- `MCPToolBackend` implements the port. Resolution per call: current org from
  `pdlc_graph.ports.current_org` (same trick as `FactoryCompletionBackend._tenant`,
  `app/runtime/llm_backend.py:33-42`) → load bound, enabled servers for (org, persona), with the
  phase read from the turn's state context → enforce `allowed_tools` → execute.
- Client: the official `mcp` Python SDK (`mcp.client.streamable_http`), new dependency of the
  **engine only** (`services/pdlc-engine/pyproject.toml`); the graph package gains nothing.
- Lifecycle: connections are opened lazily per (org, server) and cached with an idle TTL
  (~5 min); a failed server trips a 60 s negative cache so a dead endpoint doesn't add latency
  to every node.
- Limits: `PDLC_MCP_TIMEOUT_S` (default 30), response content truncated at
  `PDLC_MCP_MAX_RESULT_BYTES` (default 64 KiB) with an explicit `"[truncated]"` marker,
  max `PDLC_MCP_CALLS_PER_TURN` (default 20) enforced in the backend via a turn-scoped counter.
- Failure semantics: **a tool failure never raises into the node** — it returns
  `{ok: False, error}` and the node decides (mirror of "telemetry must not break a turn",
  `tracing.py:77-82`).
- Wiring: `wire_mcp_backend(settings)` in the engine lifespan next to `wire_llm_backend`
  (`app/runtime/llm_backend.py:141`), guarded by `PDLC_WIRE_MCP=false` default — the same
  boot-seam idiom as `wire_llm`/`stream_tokens` (`app/config.py:70-85`).
- Guard (FR-7), mirroring `_guard_cli` verbatim in spirit (`factory.py:116-129`):

```python
def _guard_stdio(transport: str) -> None:
    if transport != "stdio": return
    if not settings.enable_stdio_mcp:
        raise ValueError("stdio MCP servers require PDLC_ENABLE_STDIO_MCP=true "
                         "(single-user self-host only).")
    if settings.auth_required:
        raise ValueError("stdio MCP servers are not allowed in multi-user/SaaS mode "
                         "(PDLC_AUTH_REQUIRED is on) — they execute commands on the engine host.")
```

Enforced at **registration** (API rejects creating a stdio server when disallowed) *and* at
execution (defense in depth; config could predate a mode flip).

### 5.4 API contract

```
GET    /admin/mcp/servers                  → [ { id, name, transport, url, command, args,
                                                 allowed_tools, enabled, has_auth, bindings: [...] } ]
POST   /admin/mcp/servers                  ← { name, transport, url|command+args,
                                               auth_token?, allowed_tools }        → { id }
PUT    /admin/mcp/servers/{id}             (same shape; auth_token optional = keep existing)
DELETE /admin/mcp/servers/{id}
POST   /admin/mcp/servers/{id}/test        → { ok, latency_ms, tools: [{name, description}] }
                                             | { ok: false, error }
PUT    /admin/mcp/servers/{id}/bindings    ← { bindings: [{persona: "muse", phase: "Inception"},
                                               {persona: "atlas", phase: null}] }  → { ok: true }
```

Router `app/routes/admin/mcp.py`, mounted in `app/routes/admin/__init__.py` under
`require_admin` (`__init__.py:21`), org from the `admin_org` dependency + `set_org_context`
idiom (`routes/admin/models.py:53-60`). `has_auth: bool` in responses — the ref, let alone the
token, is never serialized.

### 5.5 Console panel (M3)

Studio route `admin/mcp.tsx`: server cards (name, transport badge, enabled toggle, last-test
status), add/edit drawer with template picker (FR-10), *Test* button rendering the returned
tool list as allowlist checkboxes, and a bindings matrix (personas × phases grid per server).
stdio option hidden entirely when the instance reports multi-user mode.

### 5.6 Observability

`tool.called` event through the standard emitter (payload per FR-8), plus a `pdlc.tool.<tool>`
span via the existing graph tracing port so tool latency shows up nested inside
`pdlc.node.<name>` spans in Tempo/Grafana (PR #78's signal tree gains one leaf type).

## 6. Security & tenancy

This PRD's risk surface is the largest in the roadmap; controls, in order of importance:

1. **stdio = code execution on the engine host.** Multi-tenant: refused outright (FR-7), both
   at write and at call time. Single-user self-host: double opt-in (flag + explicit transport
   choice), console shows the same red warning styling as CLI providers.
2. **SSRF via `url`.** An org admin could point an "MCP server" at internal infra
   (`http://postgres:5432`, cloud metadata IPs). Mitigate: scheme allowlist (https required
   when `auth_required`; http allowed only for self-host), deny-list of link-local/metadata/
   loopback/RFC-1918 targets when `auth_required` (configurable escape hatch
   `PDLC_MCP_ALLOW_PRIVATE_NETWORKS` for VPC-internal enterprise servers), and egress through
   PRD-08's proxy config where set.
3. **Prompt injection via tool output.** Tool results enter agent prompts. Mitigate: results
   are fenced with an explicit delimiter + provenance line when nodes interpolate them
   (convention documented in the port docstring), size-capped, and the Sentinel/eval layer
   (`PDLC_RUN_EVALS`) can score tool-augmented outputs. Residual risk acknowledged — this is
   industry-open; audit trail (FR-8) is the backstop.
4. **Credential handling.** Bearer tokens via secretstore refs only; write-only API; RLS +
   FORCE keeps refs org-private; resolution happens in the engine at call time.
5. **Tenant isolation of connections.** Connection cache keyed by (org_id, server_id); no
   cross-org reuse even for identical URLs.
6. **Resource abuse.** Per-turn call cap, timeout, result size cap (§5.3); per-org concurrency
   cap (default 4 in-flight tool calls).

## 7. Rollout & migration — phased

- **M1 — Registry & CRUD (no execution).** Tables + RLS, admin API, test-connection endpoint,
  secretstore integration, stdio guard at write time. Ships dark: nothing reads bindings yet.
- **M2 — Execution for one flagship flow.** `tool_port` in pdlc-graph, `MCPToolBackend`,
  `wire_mcp_backend` (flag default-off), Muse's discover step consumes `docs-search`-style
  bound tools (`graphs/brainstorm/discover.py:140` area), `tool.called` events + spans. Success
  here validates the port design before wider adoption.
- **M3 — General availability.** Bindings honored across all personas/phases wherever nodes
  opt in, console panel, templates, docs (`docs/wiki/` page + configuration rows).
- Rollback: `PDLC_WIRE_MCP=false` reverts to the null backend instantly; registry data is
  inert without the flag.

## 8. Testing strategy (hermetic)

- **Graph package:** `tool_port` unit tests (null backend determinism, set/reset fixtures);
  node tests inject a `FakeToolBackend` returning canned content — byte-stable assertions, no
  SDK, no network (identical pattern to `_StubBackend`, `llm_port.py:42-59`).
- **Engine:** backend tests against an **in-process fake MCP server** (the `mcp` SDK's server
  half over an in-memory/streamable-http transport on localhost within the test) — covers
  allowlist enforcement, timeout, truncation, negative-cache. If in-process HTTP is judged
  non-hermetic for CI, substitute a transport-level fake client; the backend takes the client
  factory as an injectable.
- **Guards:** stdio refusal matrix (flag × auth_required, 4 cases) — mirrors existing
  `_guard_cli` tests.
- **Routes:** CRUD + bindings round-trip under RLS (two orgs, cross-org 404), auth_token
  write-only behavior, SSRF deny-list cases.
- **CI invariant:** full graph suite passes with no `mcp` package installed (engine dep only,
  imported lazily inside the backend) — proving the hermetic seam, same as OTel.

## 9. Effort estimate

**L — ~5–6 eng-weeks total** (the roadmap's largest item). M1: 1.5w (tables/RLS/API/test
endpoint/secrets). M2: 2–2.5w (port, backend, limits, one flagship node, events/spans, fake-
server test rig). M3: 1.5–2w (console panel, bindings UX, templates, docs).

## 10. Risks & mitigations

- **R1: Security incident via SSRF/stdio.** The §6 controls; security review before M2 ships;
  stdio permanently confined to single-user mode.
- **R2: Tool latency degrades turn UX** (a 30 s hung tool inside a synchronous node). Mitigate:
  aggressive default timeout, negative cache, per-turn cap; expose latency in spans so it is
  diagnosable.
- **R3: Port design churn** if a future model-driven tool loop needs a different shape.
  Mitigate: M2's explicit-call design is the minimal contract (`list_tools`/`call_tool` is also
  exactly what a ReAct loop needs); keep the port surface tiny.
- **R4: `mcp` SDK maturity/protocol drift** (streamable HTTP is the current standard; SSE
  legacy servers exist). Mitigate: support streamable HTTP only in v1; templates list only
  compatible servers; SDK version pinned.
- **R5: Scope creep toward NG1.** The phasing gates it: M2 is one flow, evaluated, before M3.

## 11. Success metrics

- M1: an org registers + tests a real MCP server from the console API in < 5 min.
- M2: flagship flow (Muse + docs tool) produces measurably grounded output (eval-scored) with
  p95 tool-call latency < 2 s against a local server; zero CI regressions with the null backend.
- M3: ≥3 distinct servers bound across ≥3 personas in dogfooding; every call visible in
  clickstream + Tempo; zero cross-org access findings in security review.

## 12. Dependencies

- Secretstore (exists — `app/secretstore/__init__.py`). PRD-01's write-only secret API idiom.
- PRD-08 egress config for HTTP calls (soft — works without, required for proxy'd enterprises).
- Console shell from PRD-02 (M3 only).
- New engine dependency: `mcp` Python SDK.

## 13. Open questions

1. **Model-driven tool loop (NG1):** after M2, do we evolve `complete()` into a tool-aware
   agent loop (create_react_agent with MCP tools), or keep tools node-authored? Big
   architectural fork — needs its own design doc informed by M2 evidence.
2. **Phase taxonomy for bindings:** bind to the meta-graph's phase names (Inception/
   Construction/Operation/…) — confirm the canonical enum source (`graphs/meta.py` routing)
   before freezing the CHECK constraint.
3. **OAuth-style MCP auth** (some servers use OAuth flows, not bearer tokens): out of scope
   v1 — bearer/none only?
4. **Result caching:** should identical (server, tool, args) calls within one turn be memoized?
   (Leaning yes, trivial win under the per-turn cap.)
5. **pdlcflow-as-MCP-server** (expose gates/threads to external Claude/IDE clients): parked;
   revisit after M3.
