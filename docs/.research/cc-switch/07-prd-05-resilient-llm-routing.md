# PRD-05: Resilient LLM Routing — Failover, Circuit Breaker, Rate Limiting

> **Status:** Draft — for assessment · **Date:** 2026-07-05
> **Origin:** [cc-switch gap analysis](02-gap-analysis.md), row 6
> **Related PRDs:** consumes [PRD-03 Health/Connectivity](05-prd-03-provider-health-connectivity.md)
> status; requires [PRD-01 BYOK](03-prd-01-byok-completion.md) for per-tenant fallback creds;
> chain editing UI in [PRD-02 Console](04-prd-02-provider-settings-console.md);
> fallback history surfaces via [PRD-06 versioning/audit](08-prd-06-config-versioning-import-export.md).

## 1. Problem & motivation

cc-switch ships **auto-failover with a circuit breaker**: providers are queued, health-tracked,
and when the active one fails the proxy falls back automatically — an incident becomes a log
line instead of a broken session. cc-switch v3.16.3 added lightweight provider health checks
feeding that decision.

pdlcflow today is brittle at exactly this seam:

- The factory's resolution chain (`app/llm/factory.py:102-107`) is a *configuration* fallback
  (agent override → org default → instance default → hardcoded Bedrock,
  `factory.py:200-201`) — it picks **one** provider per call and never retries on a
  **runtime** failure. A 429 or provider outage propagates straight out of
  `FactoryCompletionBackend.complete()` (`app/runtime/llm_backend.py:77-81` re-raises), failing
  the graph turn and stranding the thread mid-phase.
- The per-tenant rate limiter is a stub: `RateLimit.acquire()` **always returns True**
  (`app/llm/rate_limit.py:16-20`), with the real Redis token-bucket design described only in
  its docstring. Nothing calls it. One runaway org can exhaust a shared instance key's
  provider quota (made worse until PRD-01 lands, since all orgs share the operator's key).
- There is no health signal: nothing records that a provider has been failing, so every turn
  re-discovers the outage at full timeout cost.

For a product whose core promise is *long-running multi-agent workflows*, a transient provider
incident should degrade quality-of-service (slower, different model), not correctness (failed
turn, human has to notice and retry).

## 2. Goals / Non-goals

**Goals**

- G1. **Org-level failover chain**: an ordered list of fallback provider configs tried in
  sequence when the primary fails with a retriable error.
- G2. **Circuit breaker** keyed `(org_id, provider)`: after N failures, skip the provider for a
  cooldown; half-open probes restore it — so a dead provider costs one timeout per cooldown,
  not one per call.
- G3. **Health-aware selection**: PRD-03's background health status demotes unhealthy chain
  entries before a call is even attempted.
- G4. **Real rate limiting**: implement the documented Redis token bucket and actually enforce
  it in the completion path.
- G5. **Full telemetry**: every fallback, breaker transition, and rate-limit rejection is a
  clickstream event + OTel metric, visible in Grafana/Streamlit Nexus.

**Non-goals**

- NG1. No mid-stream failover (resuming a half-generated answer on another provider). Failover
  applies before the first streamed token only (§5.5).
- NG2. No cost- or latency-optimizing router ("cheapest healthy provider") — chain order is
  explicit admin intent. Smart routing is a possible v2.
- NG3. No request hedging (parallel duplicate calls).
- NG4. No cross-provider *semantic* equivalence guarantees — a fallback model is a different
  model; prompts are provider-neutral already (plain system+human messages,
  `llm_backend.py:59-65`).
- NG5. Instance-level (non-tenant) global rate limiting / spend caps — PRD-07 budgets.

## 3. Users & user stories

- **Org admin:** "As an org admin, I want to declare 'primary Anthropic, fall back to Bedrock,
  then to OpenRouter' so that a provider incident doesn't stall my squads' overnight runs."
- **Squad member:** "As a squad member, I want a turn that hit a fallback to complete and be
  *labeled* as degraded (which provider actually served it), so I can judge whether to re-run."
- **Instance operator:** "As an operator, I want per-org RPM caps enforced in Redis so one
  tenant's runaway loop can't starve everyone (or blow the shared key's quota)."
- **SRE:** "As an SRE, I want breaker-state and fallback-rate metrics in Prometheus so I can
  alert on 'org X has been on fallback for 30 min'."

## 4. Functional requirements

| ID | Requirement | MoSCoW |
|----|-------------|--------|
| FR-1 | `org_llm_config` gains an ordered `failover_chain` (0–3 entries; each: provider, region, endpoint, secret_ref, tier_map). Primary remains the existing row's columns. | Must |
| FR-2 | On a **retriable** error (taxonomy FR-3) from candidate *i*, the backend re-resolves and retries with candidate *i+1*, same persona/tier (tier→model via each candidate's own tier_map). | Must |
| FR-3 | Error taxonomy: 429 / 5xx / timeouts / connection errors → **failover**; 401/403 (auth) → **no failover**, surface + flag config unhealthy; 4xx validation (400/404/422, e.g. bad model id) → **no failover**, surface (config bug, not incident). | Must |
| FR-4 | Circuit breaker per `(org_id, provider)` in Redis: closed → open after ≥5 failures in 60 s; open for 30 s (skip provider); half-open admits 1 probe call; success closes, failure re-opens. All thresholds settings-tunable. | Must |
| FR-5 | Chain entries whose PRD-03 health status is `unhealthy` are demoted to last (not skipped — health data can be stale). | Should |
| FR-6 | `RateLimit.acquire()` implements the documented design: `INCR llm:{org}:{provider}:{tier}:rpm:{epoch_minute}` + `EXPIRE 60`, compared to the org's RPM (default from settings; per-org override deferred to the existing "Quotas page (Phase H)" plan, `rate_limit.py:4-5`). Enforced in `complete()`/`stream()` before the model call; rejection raises `RateLimited` (surfaced as a paused/retryable turn, not a crash). | Must |
| FR-7 | Telemetry: clickstream events `llm.failover` {from_provider, to_provider, reason, attempt}, `llm.breaker` {provider, transition}, `llm.rate_limited` {provider, tier}; OTel counters `pdlc.llm.fallbacks` {from_provider,to_provider,reason}, `pdlc.llm.breaker_transitions` {provider,transition}, `pdlc.llm.rate_limited` {provider,tier} — extending the existing `pdlc.llm.*` family (`app/observability/tracing.py:13-16`). Spans: failed attempts get `record_exception` + `pdlc.llm.attempt` attribute; the serving attempt carries `pdlc.llm.fallback_rank`. | Must |
| FR-8 | The turn's final answer records which provider/model actually served it (already flows through `_record`, `llm_backend.py:108-126` — provider/model labels must be the *serving* candidate's). | Must |
| FR-9 | Failover disabled ⇢ behavior is byte-identical to today (empty chain = no new code paths). Default: empty chain, breaker on, rate limit off unless `PDLC_RATE_LIMIT_ENABLED`. | Must |
| FR-10 | Console: chain editor (ordered list, drag to reorder, per-entry Test via PRD-03) + live breaker/health badges. | Should |
| FR-11 | When Redis is unavailable, breaker + rate limiter fail **open** (allow calls, log warning) — resilience machinery must never be the outage. | Must |

## 5. Detailed design

### 5.1 Where failover lives

**In `FactoryCompletionBackend`, not inside the factory.** The factory stays a pure
config→model resolver; the backend owns the retry loop because it already owns spans, timing,
usage extraction, and error handling (`llm_backend.py:67-106`). New collaborator:

```python
class ResilientRouter:
    """Yields candidate ProviderConfigs in try-order for (org, persona, tier)."""
    def candidates(self, org_id, persona, tier) -> list[ResolvedCandidate]: ...
    def report(self, org_id, provider, outcome: Literal["ok","retriable","fatal"]) -> None: ...
```

`LLMProviderFactory` gains `resolve_chain(persona, tier, tenant) ->
list[tuple[BaseChatModel, provider, model_id]]` — candidate 0 is exactly today's
`resolve()` result (`factory.py:99-113`); candidates 1..n come from `failover_chain` rows.
The existing `resolve()` delegates to `resolve_chain(...)[0]`, so `hasattr(self._factory,
"resolve")` compatibility in `llm_backend.py:51-54` is preserved.

`complete()` becomes:

```python
for rank, (model, provider, model_id) in enumerate(candidates):
    if not breaker.allow(org, provider):        # FR-4 (skip open breakers)
        continue
    if not await_ok(rate_limit.acquire(org, provider, tier)):  # FR-6
        raise RateLimited(...)
    with observability.llm_span(persona, eff_tier) as span:
        try:
            result = model.invoke(messages)
        except Exception as exc:
            breaker.record_failure(org, provider)
            self._record(span, ..., ok=False)
            if rank == last or classify(exc) is not RETRIABLE:
                raise
            emit_failover_event(...); continue   # FR-7
        breaker.record_success(org, provider)
        self._record(span, persona, provider, model_id, ...)   # serving labels, FR-8
        return result.content
```

Each attempt gets its own `pdlc.llm.<persona>` span (failed ones marked via
`record_exception`), all nested under the same `pdlc.node.*` span — the trace shows the
failover story naturally.

### 5.2 Error classification (FR-3)

`app/llm/errors.py` → `classify(exc) -> Literal["retriable", "auth", "fatal"]`. LangChain
providers raise heterogeneous exceptions; classify by (a) `status_code`/`code` attributes
where present (openai/anthropic SDK errors expose them), (b) exception-type name matching
(`RateLimitError`, `APITimeoutError`, `ServiceUnavailable`…), (c) `httpx`/`requests` transport
errors → retriable, (d) default **fatal** (fail closed — misclassifying a prompt-content error
as retriable would burn the whole chain on a doomed request). Table-driven; unit-tested per
provider SDK.

### 5.3 Circuit breaker (FR-4)

Redis (already a dependency: `redis>=5.0` + arq in `services/pdlc-engine/pyproject.toml:15-16`,
`settings.redis_url` at `app/config.py:24`, compose service `infra/compose/docker-compose.yml:22`).

Keys, all with TTLs so state self-heals:

```
llm:cb:{org}:{provider}:failures   # ZSET of failure timestamps (window prune) — or INCR+EXPIRE 60
llm:cb:{org}:{provider}:state      # "open" (EX 30) | "half_open" (EX 10); absent = closed
```

`allow()` = state absent, or half-open token won via `SET NX` (exactly one probe).
Settings: `rate/breaker knobs under `PDLC_LLM_BREAKER_*` (threshold=5, window_s=60,
cooldown_s=30). Keyed per-org so one org's bad gateway (PRD-04 custom endpoints!) never trips
another org's view of the same provider name. Redis down → `allow()` returns True (FR-11).

### 5.4 Rate limiter (FR-6)

Implement exactly the docstring design in `rate_limit.py`: fixed-window
`INCR` + `EXPIRE 60` on `llm:{org}:{provider}:{tier}:rpm:{epoch_minute}`; compare to RPM.
Fixed-window (not sliding) is deliberate: one round-trip, and burst-at-boundary error is
acceptable for a quota knob. Sync facade over the async client to fit the backend's sync call
path (or `asyncio.run_coroutine_threadsafe` against the app loop — implementation detail for
the spike). `RateLimited` maps to a **paused/retryable** turn outcome at the graph-runner
level, mirroring how gates pause rather than fail.

### 5.5 Streaming (`stream()`, `llm_backend.py:86-106`)

Failover window = until the first non-empty content chunk is yielded. Implementation: pull the
first chunk *inside* the candidate loop before yielding anything; once a token has been
surfaced to the live-token bus, an error mid-stream propagates as today (NG1) — replaying a
partial generation on a different model would splice two models' prose into one artifact.

### 5.6 Data model & migration

Alembic `0009_failover_chain.py` (after PRD-04's 0008): add
`org_llm_config.failover_chain JSONB NOT NULL DEFAULT '[]'`. JSONB (vs. child table) because
the chain is small (≤3), ordered, always read whole with the parent row
(`factory.py:_org_default`, one query — becomes `select …, failover_chain`), and RLS is
inherited for free. Validation lives in the API layer (`routes/admin/models.py`
`OrgDefault` model gains `failover_chain: list[FallbackEntry] = []`, provider values checked
against the same shared constant as PRD-04 §5.3, `openai_compatible` entries require
endpoint + tier_map). Per-entry `secret_ref` resolves through PRD-01's same secretstore path.

### 5.7 Telemetry details (FR-7)

- Metric label cardinality: **no org_id in metric labels** (unbounded); org lives in span
  attributes + clickstream events, matching the existing convention
  (`pdlc.llm.*` labels are persona/provider/model/tier only, `tracing.py:13-16`).
- Clickstream events ride the existing emitter path (same envelope as `llm.tokens_spent` from
  `app/clickstream/callbacks.py`), so BI exports and the Streamlit Nexus dashboard pick them up
  without schema work.
- Grafana: add a "Resilience" row to the provisioned dashboard — fallback rate, breaker-open
  gauge by provider, rate-limited count.

## 6. Security & tenancy

- Chain entries are org-scoped rows behind the same RLS-FORCEd table; per-entry `secret_ref`
  never leaves the server, never appears in events/spans (only provider *names* do).
- Breaker/rate-limit Redis keys are namespaced by org; no cross-tenant signal leakage
  (breaker state is per-org even for the same provider).
- Failover must not silently downgrade a tenant to the **operator's** instance key: chain
  candidates use their own `secret_ref`; entries without one are only legal when the provider
  is keyless (bedrock/vertex/ollama) — validated at write time. (Depends on PRD-01.)

## 7. Rollout & migration

1. Migration 0009 (additive, default `'[]'`) — zero behavior change.
2. Engine release with `failover_chain` honored + breaker on-by-default (a breaker over a
   chain of length 1 only affects repeated hard failures — strictly better), rate limiter
   behind `PDLC_RATE_LIMIT_ENABLED=false` default.
3. Console chain editor (with PRD-02).
4. Enable rate limiting per deployment once RPM defaults are agreed.

Kill switch: `PDLC_LLM_FAILOVER_ENABLED=false` reverts to single-candidate resolution.

## 8. Testing strategy

Hermetic (no network, no Redis in unit tier) via the repo's injectable-port style:

- **Fake models**: scripted `BaseChatModel` stubs (fail-with(exc) / succeed-with(usage)) —
  drive the candidate loop: retriable→fallback-serves, auth→no-fallback, fatal→no-fallback,
  exhausted-chain→last error propagates, serving-labels correctness (FR-8).
- **Breaker**: `fakeredis` (or an in-memory port implementing the 3 ops) — threshold, cooldown
  expiry, single half-open probe under concurrency, Redis-down fail-open (FR-11).
- **Rate limiter**: fakeredis fixed-window semantics; boundary-minute rollover; disabled path
  untouched.
- **Streaming**: first-chunk failover; post-first-token error propagates; token publisher
  receives nothing from failed candidates.
- **Classification**: table test over constructed SDK exception types per provider.
- **Byte-identical guard** (FR-9): existing `llm_backend` tests re-run with empty chain +
  breaker/ratelimit disabled — zero behavioral diff; the offline-stub path
  (`wire_llm=False`) never touches any of this.
- **Telemetry**: in-memory OTel reader (pattern already used for the PR-#78 metric tests) +
  spy emitter asserting event payloads.

## 9. Effort estimate

**L — ~3–4 eng-weeks.** Candidate loop + classification (1 w), breaker + rate limiter + Redis
plumbing incl. sync/async seam (1 w), migration/API/validation + telemetry + dashboards (1 w),
console chain editor (0.5–1 w, on PRD-02 scaffolding). The sync/async seam (sync backend,
async Redis) is the main uncertainty.

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Misclassification burns the chain on doomed requests (e.g. context-too-long read as 5xx) | Default-fatal classification; per-SDK table tests; `llm.failover` events make patterns visible |
| Cross-model output inconsistency within one thread (opus artifact, fallback continues in a weaker model) | Serving model recorded per event/span (FR-8); console badge on degraded turns; admins order chains with capability in mind (docs) |
| Latency stacking: full chain of timeouts ≈ 3× timeout before failing | Breaker short-circuits repeat offenders; per-attempt client timeout tightened (candidate-level timeout override, settings) |
| Redis becomes a hard dependency of the hot path | FR-11 fail-open + all state in TTL'd keys; unit tier runs Redis-free |
| Half-open thundering herd | `SET NX` single-probe token |
| Rate limiter double-counts failed-over attempts | Acquire once per *attempt* by design (each attempt is a real upstream call) — documented; alternative (per-turn) rejected as it under-protects quotas |

## 11. Success metrics

- Turn failure rate attributable to provider errors drops ≥ 80% for orgs with a configured
  chain (measure: `error`-outcome `pdlc.turns` with LLM-error cause, before/after).
- Mean time-to-recovery from a provider incident: < 1 breaker cooldown (30 s) instead of
  "until a human notices".
- `pdlc.llm.fallbacks` visible and alertable in Grafana; zero silent fallbacks (every fallback
  has a clickstream event).
- With empty chains and flags off: 0 regressions (existing suite byte-identical).

## 12. Dependencies

- **PRD-01 (BYOK)** — hard for SaaS: chain entries need per-tenant `secret_ref` resolution
  (§6); without it fallback providers would silently use operator env keys.
- **PRD-03 (Health/Connectivity)** — soft: FR-5 demotion consumes its status; failover works
  without it (breaker is the reactive layer, health the proactive one). Sequence PRD-03 first.
- **PRD-02 (Console)** — chain editor + badges; API-only failover is fully functional without
  it.
- **PRD-04 (Presets/gateways)** — interaction, not dependency: gateway endpoints raise the
  value of per-org breakers and of strict SSRF validation on chain entries.

## 13. Open questions

1. Should per-**agent** overrides (`agent_llm_config`) get their own chains, or does an agent
   override fall back into the org chain on failure? (Proposal: agent override is candidate 0,
   org chain provides 1..n — keeps one chain per org.)
2. `RateLimited` surfacing: pause-the-turn (gate-like, resumable) vs. fail-the-turn with
   retry-after — needs a product decision with the graph-runner owner.
3. Breaker scope for `openai_compatible`: key by provider name or by endpoint host? (Two
   gateways both named `openai_compatible` share a breaker today — proposal: key by
   `provider + endpoint_host`.)
4. Do we want an org-level "sticky fallback" (stay on the fallback for N minutes after a trip,
   rather than re-probing primary every cooldown) to avoid flapping mid-thread?
