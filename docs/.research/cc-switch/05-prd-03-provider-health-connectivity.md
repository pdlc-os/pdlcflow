# PRD-03: Provider Health & Connectivity Testing

| | |
|---|---|
| **Status** | Draft — for assessment |
| **Date** | 2026-07-05 |
| **Origin** | [cc-switch gap analysis](02-gap-analysis.md), gap #4 |
| **Related PRDs** | [PRD-01 BYOK](03-prd-01-byok-completion.md) (tests saved tenant keys) · [PRD-02 Console](04-prd-02-provider-settings-console.md) (Test button + health badges) · [PRD-05 Resilient Routing](07-prd-05-resilient-llm-routing.md) (consumes health status for failover) |

## 1. Problem & motivation

pdlcflow has **no way to answer "will this provider config actually work?"** short of running a
real PDLC turn and watching it fail:

- The Studio "Test" button is a decorative no-op (`apps/studio/src/routes/admin/models.tsx:48-53`)
  with no backend endpoint behind it.
- `/health/ready` hardcodes `{"llm": "stub"}` (`services/pdlc-engine/app/routes/health.py:13-16`
  — the comment says "Phase B will check DB + Redis + Bedrock connectivity here"; Phase B never
  did).
- The `doctor` utility command is a hermetic in-memory *workflow* health check
  (`packages/pdlc-graph/pdlc_graph/graphs/utility/doctor.py`), unrelated to providers.

So a mistyped model ID, a revoked key, a wrong Azure endpoint, or a region without model access
is discovered **mid-turn by an agent persona**, surfacing as a failed node deep in a thread —
the worst possible place. With PRD-01 adding tenant keys and PRD-02 adding a console, the cost
of a bad save goes up: an org admin can now break their whole org in one PUT.

**What cc-switch does here:** lightweight HTTP-reachability health checks per provider
(v3.16.3), health-status tracking feeding its failover engine, and endpoint testing surfaced on
provider cards. pdlcflow's translation: an admin-scoped, pre-save **probe endpoint** plus an
optional cached **per-org provider health status**, both feeding the console now and the
failover engine (PRD-05) later.

## 2. Goals / Non-goals

**Goals**

- G1: `POST /admin/models/test` validates a *candidate* config (provider, model, region,
  endpoint, key) end-to-end before it is saved, returning ok/latency/error-class in ≤ ~10 s
  worst case.
- G2: The probe can test the **saved** config (resolving the stored `secret_ref` via PRD-01)
  or an **inline** candidate key — so both "check current setup" and "validate before rotate"
  work.
- G3: Probe results are classifiable: an admin can tell *auth failure* from *no such model*
  from *endpoint unreachable* without reading provider-specific stack traces.
- G4: Last probe result per (org, scope) is persisted so the console can show a status chip
  without re-probing on every page load.
- G5: `/health/ready`'s `llm` check becomes real for the **instance default** path — reporting
  degraded (not unready) when the instance provider fails its probe.
- G6: Hermetic CI: the prober is injectable; no test ever talks to a real provider.

**Non-goals**

- Continuous background probing of every org's provider on a schedule — deferred (see §5.6;
  PRD-05's circuit breaker derives health from *real traffic*, which is better signal than
  synthetic probes).
- Latency benchmarking / speed-ranking of providers (cc-switch's "speed test" as a comparative
  feature) — a single probe latency is reported, ranking is not.
- Health-based routing decisions (PRD-05).
- Probing CLI providers (`claude_code` etc.) — excluded from the admin surface entirely.

## 3. Users & user stories

- **Org admin** — "Before I save this Anthropic key, I click Test and see '✓ 620 ms,
  claude-sonnet-4-6' — or '✗ auth_error: key rejected'."
- **Org admin** — "The Models page shows my org's provider was healthy as of 5 minutes ago."
- **Platform operator** — "`/health/ready` tells my orchestrator the instance can reach its
  default LLM — as a `degraded` signal, not a pod-killing failure."
- **Support engineer** — "When a tenant reports failures, I look at their last probe result and
  error class before digging into traces."

## 4. Functional requirements

| ID | Requirement | MoSCoW |
|---|---|---|
| FR-1 | `POST /admin/models/test` accepts a candidate `{provider, model_id? or tier?, region?, endpoint?, api_key? or use_saved_key?, scope?}` and runs a live minimal completion against it. | Must |
| FR-2 | Response schema: `{ok, latency_ms, error_class, tested_model, message}` (see §5.3). | Must |
| FR-3 | Probe = 1-token chat completion (`max_tokens=1`), not a models-list call (rationale §5.2). | Must |
| FR-4 | Hard timeout budget: `PDLC_LLM_PROBE_TIMEOUT_S` (default 10); on expiry → `error_class: "timeout"`. | Must |
| FR-5 | `use_saved_key: true` resolves the stored `secret_ref` for the given scope (org default or persona) via the PRD-01 path; inline `api_key` takes precedence when both are present. | Must |
| FR-6 | Error taxonomy mapped from SDK exceptions: `auth_error`, `model_not_found`, `access_denied`, `endpoint_unreachable`, `rate_limited`, `timeout`, `bad_request`, `unknown`. | Must |
| FR-7 | Last result per (org_id, scope) upserted to a `llm_provider_health` table; `GET /admin/models/health` returns them for the console's status chips. | Should |
| FR-8 | `/health/ready`'s `llm` field reports the cached instance-default probe result (`ok`/`degraded`/`unprobed`); never turns readiness false by itself. | Should |
| FR-9 | Probe requests are rate-limited per org (e.g. 10/min) — they cost real (tiny) provider spend and could be abused as an oracle. | Should |
| FR-10 | Candidate `endpoint` values are validated against an egress policy before probing (SSRF guard, §6). | Must |
| FR-11 | Prober is an injectable port with a no-op/fake default, mirroring `set_emitter`/`set_tracer` (`packages/pdlc-graph/pdlc_graph/instrumentation.py:38`, `tracing.py:55`) so CI stays network-free. | Must |
| FR-12 | Probe emits a clickstream event `admin.provider.probed` `{provider, ok, error_class, latency_ms}` — no key material, no endpoint echo for saved configs. | Could |

## 5. Detailed design

### 5.1 Probe mechanics

Reuse the factory's own builder path so the probe exercises **exactly what a turn would run**:

```python
# app/llm/probe.py
def run_probe(cfg: ProviderConfig, model_id: str, timeout_s: float) -> ProbeResult:
    builder = _BUILDERS[cfg.provider]              # app/llm/factory.py:61
    model = builder(cfg, model_id)                 # same construction as a real call
    t0 = time.monotonic()
    model.invoke("ping", max_tokens=1, timeout=timeout_s)   # bound via provider kwargs where supported
    return ProbeResult(ok=True, latency_ms=int((time.monotonic() - t0) * 1000), tested_model=model_id)
```

wrapped in the exception-mapping layer (§5.4) and an outer `asyncio.wait_for`/thread timeout as
the universal budget (SDK-level timeouts are inconsistent across providers). `model_id` comes
from the request's explicit `model_id`, else `resolve_model_id(provider, tier or "balanced",
tier_map_override)` (`app/llm/tier_map.py:75`) — so tier-map edits are testable per tier.

### 5.2 Why a 1-token completion, not a models-list call

| | models-list (`/v1/models`, `list_foundation_models`, …) | 1-token completion |
|---|---|---|
| Validates auth | ✓ | ✓ |
| Validates *invoke* permission | ✗ (Bedrock/Vertex list-vs-invoke are different IAM actions) | ✓ |
| Validates the specific model id | ✗ (listed ≠ granted; Azure deployments unlisted) | ✓ |
| Validates region/endpoint routing | partial | ✓ |
| Uniform across our 7 providers | ✗ (no list API on Azure deployments; Ollama differs) | ✓ (every langchain chat model has `.invoke`) |
| Cost | free | ~$0.0001 (a few input tokens + 1 output token) |
| Latency signal comparable to real traffic | ✗ | ✓ |

The completion probe is strictly more truthful for marginal cost; cc-switch itself moved from
reachability pings toward request-shaped checks (its rectifier/failover layers key off real
request outcomes). Decision: **completion probe** (FR-3).

### 5.3 API contract

`POST /v1/admin/models/test` (behind `admin_org("/admin/models/test")`):

```jsonc
// request — candidate (pre-save) test from the console
{ "provider": "anthropic", "model_id": "claude-sonnet-4-6",
  "api_key": "sk-ant-...",            // optional, write-only
  "region": null, "endpoint": null }

// request — test what's currently saved for a scope
{ "scope": "org-default", "use_saved_key": true }        // or "scope": "agent:jarvis"

// response
{ "ok": false, "latency_ms": 1240, "error_class": "model_not_found",
  "tested_model": "claude-sonet-4-6",
  "message": "Provider rejected the model id (check spelling / account access)." }
```

`message` is a **sanitized, human-written string per error class** — never the raw SDK
exception (which can echo headers/URLs). `GET /v1/admin/models/health` returns
`[{scope, provider, ok, latency_ms, error_class, checked_at}]` from the table below.

### 5.4 Error mapping

A per-provider exception table in `app/llm/probe.py` maps SDK exception types/status codes →
`error_class`: 401/403-auth → `auth_error`; 404-model / Bedrock `ValidationException` on
modelId / Azure `DeploymentNotFound` → `model_not_found`; Bedrock `AccessDeniedException` →
`access_denied`; connection/DNS errors → `endpoint_unreachable`; 429 → `rate_limited`; the
outer budget → `timeout`; anything else → `unknown` (with exception type name only, no
message passthrough). This table is the encoded support knowledge and is unit-testable with
synthetic exceptions — no network needed.

### 5.5 Persistence (FR-7)

New table via alembic revision `0007_provider_health` (next after `0006_hierarchy.py`):

```sql
create table llm_provider_health (
  org_id uuid not null references organizations(id) on delete cascade,
  scope text not null,                 -- 'org-default' | 'agent:<persona>' | 'instance'
  provider text not null,
  ok boolean not null,
  latency_ms integer,
  error_class text,
  checked_at timestamptz not null,
  primary key (org_id, scope)
);
```

RLS-enabled + FORCEd like its siblings (pattern from `0002_rls.py`/`0003_rls_force.py`). The
`instance` scope row uses the reserved system org id already used for instance-level rows
elsewhere (or a nullable-org variant if none exists — resolve in implementation; the RLS
policy must still hold).

### 5.6 Background monitoring — deliberately minimal

One optional asyncio loop probing only the **instance default** config every
`PDLC_LLM_HEALTH_INTERVAL_S` (default `0` = disabled), feeding FR-8. Per-org scheduled probing
is **rejected for now**: N orgs × M scopes of synthetic spend and key usage, on keys tenants
pay for, with worse signal than PRD-05's traffic-derived circuit-breaker state. The
`llm_provider_health` table is written by on-demand tests now and by PRD-05's breaker
transitions later — same console surface, better data.

### 5.7 Injectable prober port (FR-11)

`app/llm/probe.py` exposes `set_prober(fn)` / `reset_prober()`; default implementation is the
real one in production but the **route** always calls through the module hook — tests inject
`fake_prober(cfg, model_id) -> ProbeResult` and the whole route/console stack is exercised with
zero network. This mirrors the graph package's `set_emitter` (`instrumentation.py:38`) and
`set_tracer` (`tracing.py:55-58`) seams; unlike those, it lives engine-side since probing is an
engine concern.

## 6. Security & tenancy

- **Admin-gated**: `admin_org` guard as all models routes; probes run under the caller's org
  context; health reads are RLS-scoped.
- **SSRF (FR-10)**: a candidate `endpoint` is an arbitrary URL the server will connect to.
  Guard: scheme allowlist (`https`, plus `http` only when the host is explicitly allowed for
  Ollama/self-host), resolve host and reject link-local/metadata/loopback/RFC-1918 ranges
  unless `PDLC_ALLOW_PRIVATE_LLM_ENDPOINTS=true` (self-host with local Ollama needs it; SaaS
  keeps it off). Shared with PRD-08's egress policy when that lands.
- **Key handling**: inline `api_key` is used for the single probe and discarded — never stored,
  never logged, never in the health table. `use_saved_key` path never returns whether the key
  merely *exists* beyond PRD-01's `has_key`.
- **Oracle/abuse**: FR-9 per-org rate limit; probes are also admin-only, so exposure is limited
  to org admins burning their own quota.
- **Response hygiene**: sanitized `message` strings only (§5.3); raw exceptions go to server
  logs at debug level with key material scrubbed by construction (keys are kwargs, not URLs).

## 7. Rollout & migration

1. Migration `0007_provider_health` (additive table).
2. Ship the endpoint + console wiring (PRD-02's Test button) together; health chips (FR-7 GET)
   can trail by a release.
3. `/health/ready` change is additive (`llm: "unprobed"` when the loop is disabled — the
   default — preserving today's effective behavior).
4. Docs: wiki configuration page gains `PDLC_LLM_PROBE_TIMEOUT_S`, `PDLC_LLM_HEALTH_INTERVAL_S`,
   `PDLC_ALLOW_PRIVATE_LLM_ENDPOINTS`.

## 8. Testing strategy (hermetic)

- **Route tests** with an injected fake prober: candidate test happy path; `use_saved_key`
  resolves via a fake secrets store (PRD-01's test fixture); timeout class; rate limit; health
  upsert + GET; RLS isolation (org A cannot read org B's health rows — same pattern as existing
  RLS tests).
- **Error-mapping unit tests**: synthetic SDK exceptions (constructed, not raised by real SDKs
  where construction is heavy — a small shim per provider) → expected `error_class`. No
  network.
- **SSRF guard unit tests**: metadata IP, loopback, RFC-1918, DNS-to-private (mock resolver),
  scheme violations → rejected; allowed when the self-host flag is on.
- **`/health/ready` test**: unprobed default unchanged; degraded when the cached instance probe
  failed.
- **One opt-in live smoke** (not in CI): `scripts/probe_smoke.py` an operator can run against
  real creds — mirrors how other creds-needing paths are validated in this repo (`wire_llm`
  itself is off by default, `app/config.py:74`).

## 9. Effort estimate

**M — ~1.5–2 engineer-weeks.** Probe module + error taxonomy ≈ 0.5 w (the taxonomy research per
provider is the real cost); route + health table + migration + RLS ≈ 0.5 w; SSRF guard + rate
limit ≈ 0.3 w; tests ≈ 0.5 w. Console wiring is counted in PRD-02.

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Error taxonomy drifts as SDKs change exception shapes | Table-driven mapping with `unknown` fallback; taxonomy tests pinned per SDK version bump |
| Probe spend on tenant keys surprises admins | It's admin-initiated, ~1 token, documented in the console tooltip; rate-limited (FR-9) |
| SSRF guard blocks legitimate self-host Ollama | Explicit `PDLC_ALLOW_PRIVATE_LLM_ENDPOINTS` escape hatch, on in the self-host compose defaults |
| A "healthy" probe ≠ healthy under load (rate limits, context length) | Positioned as *connectivity* check in UI copy; PRD-05's traffic-derived breaker covers the rest |
| Timeout budget too tight for cold Bedrock/Vertex routes | Configurable; default 10 s chosen above typical p99 first-call latency |

## 11. Success metrics

- ≥ 90% of misconfiguration classes reproduced in staging map to a non-`unknown` error class.
- Probe p50 wall time < 2 s for healthy major providers.
- Reduction in "turn failed on first LLM call after config change" incidents (clickstream:
  `error` events within N minutes of an `admin.models` change) after PRD-02+03 ship together.
- Zero CI network calls (enforced by the existing hermetic test posture).

## 12. Dependencies

- **PRD-01** for `use_saved_key` (soft — inline-key testing works without it).
- Consumed by **PRD-02** (Test button, health chips) and **PRD-05** (health table as the
  breaker's persistence).
- Existing: `_BUILDERS`/`ProviderConfig` (`app/llm/factory.py:61-83`), `resolve_model_id`
  (`app/llm/tier_map.py:75`), admin guard, alembic chain, RLS helpers.

## 13. Open questions

1. Probe prompt content: literal `"ping"` vs a fixed system-less minimal message — any provider
   that rejects single-word prompts? (Verify during implementation; keep it constant so latency
   is comparable.)
2. Should probe results feed the OTel metrics pipe (`pdlc.provider.probe` histogram) for the
   Grafana board? Cheap to add; lean yes once PRD-05 consumes the same signal.
3. `instance` scope row's org id under RLS — reserved system org vs separate non-RLS table?
   Needs a look at how other instance-level state is stored (resolve in design review).
4. Is 10/min/org the right probe rate limit, and should it share the (currently stubbed)
   limiter in `app/llm/rate_limit.py` once PRD-05 makes it real?
