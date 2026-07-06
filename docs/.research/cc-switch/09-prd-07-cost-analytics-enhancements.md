# PRD-07: Cost Analytics Enhancements — pricing overrides, catalog refresh, budgets

- **Status:** Draft — for assessment
- **Date:** 2026-07-05
- **Origin:** [cc-switch gap analysis](02-gap-analysis.md) — gap #8 (PARTIAL)
- **Related PRDs:** [PRD-01 BYOK](03-prd-01-byok-completion.md) (org-scoped config reads share the same factory path) · [PRD-02 Settings Console](04-prd-02-provider-settings-console.md) (UI surface) · [PRD-06 Config versioning](08-prd-06-config-versioning-import-export.md) (pricing overrides should be versioned like other config)

## 1. Problem & motivation

pdlcflow already tracks cost better than most: every completion emits a `llm.tokens_spent`
clickstream event with a `usd_estimate` (`app/clickstream/callbacks.py:26-39`), and the same
estimate feeds the OTel `pdlc.llm.cost_usd` metric (`app/runtime/llm_backend.py:109-126`) shown
on the Grafana/Streamlit Nexus dashboards. But three promises are unkept:

1. **The pricing override doesn't exist.** `app/llm/pricing.py:3-5` says *"Tenants can override
   via `org_llm_config.pricing_override` (added in Phase B)"* — there is no such column
   (`app/db/models.py:259-271`) and `estimate_usd()` takes no org context
   (`app/llm/pricing.py:34`). Orgs on negotiated/discounted rates, relay gateways, or fine-tuned
   models get wrong numbers with no recourse.
2. **The price table is frozen at design time.** `PRICES` (`app/llm/pricing.py:11-31`) is a
   hardcoded dict of ~20 (provider, model) pairs. New models estimate to $0.0 silently (the
   `return 0.0` path, `pricing.py:38-39`), which reads as "free" on the dashboard.
3. **No budgets.** `initiatives.budget_usd` exists as a column (`app/db/models.py:81`) but
   nothing watches spend against anything. Orgs discover overruns after the fact.

**What cc-switch does here:** custom per-model pricing, models.dev batch pricing import with
search, billing based on real upstream models, filter-driven spend dashboards, and per-provider
balance/quota queries (inventory §6). Its lesson: users don't just want spend *displayed*, they
want to *correct the price sheet* and be *warned before the bill*.

**Explicit stance carried over:** pricing remains estimate-only for dashboards — *never used for
billing decisions*. That disclaimer (`pricing.py:4-5`) stays verbatim in code and appears in the
console UI.

## 2. Goals / Non-goals

**Goals**
- G1: Org-level per-(provider, model) pricing overrides, editable via admin API + console.
- G2: A refreshable pricing catalog: shipped as a data file per release (hermetic default), with
  an optional admin-triggered online refresh (models.dev-style) for deployments that opt in.
- G3: Org monthly budgets with soft threshold alerts (clickstream event + console banner).
- G4: Unknown models are visible as *unpriced*, not silently $0.

**Non-goals**
- NG1: Billing-grade metering, invoicing, or payment integration.
- NG2: Hard budget enforcement (blocking turns when over budget) — soft alerts only in v1;
  enforcement is listed as an open question.
- NG3: Live balance/quota queries against provider accounts (cc-switch does this; it requires
  per-provider account APIs and is deferred — see §13).
- NG4: Per-initiative budget tracking (the `initiatives.budget_usd` column) — same mechanism
  could extend there later; out of scope for v1.

## 3. Users & user stories

- **Org admin (multi-tenant SaaS or self-host):**
  - "As an org admin, I set the real price we pay for `openai/gpt-5.4` (we have a committed-use
    discount) so the dashboard's spend numbers match our invoice ballpark."
  - "As an org admin, I set a $500/month budget and get an alert banner at 50/80/100%."
- **Instance operator:**
  - "As an operator, I update the shipped pricing catalog by upgrading pdlcflow, or trigger a
    catalog refresh from the console without a release."
- **Squad lead / viewer:** "I look at the Nexus dashboard and trust that per-model spend uses
  the org's corrected prices."

## 4. Functional requirements

| ID | Requirement | MoSCoW |
|---|---|---|
| FR-1 | Add `pricing_override JSONB` to `org_llm_config`; shape `{"<provider>/<model_id>": {"in": <usd_per_1M>, "out": <usd_per_1M>}}` | Must |
| FR-2 | `estimate_usd` resolution order: org override → catalog exact `(provider, model)` → catalog `(provider, "*")` → **unpriced** | Must |
| FR-3 | Admin API: GET effective price sheet (catalog + org overrides merged, provenance-tagged), PUT/DELETE overrides | Must |
| FR-4 | Move `PRICES` from a Python dict to a versioned data file (`pricing_catalog.json`) packaged with the engine; loaded at boot; same values ⇒ byte-identical estimates | Must |
| FR-5 | Unpriced completions emit `usd_estimate: null` (not `0.0`) in `llm.tokens_spent`, and the dashboards render an "unpriced models" indicator | Must |
| FR-6 | Org monthly budget: `monthly_limit_usd` + alert thresholds (default 50/80/100%); crossing a threshold emits a `budget.threshold` clickstream event once per month per threshold | Must |
| FR-7 | Console banner (Nexus admin) when the current month's estimate crosses a threshold | Should |
| FR-8 | Admin-triggered online catalog refresh (fetch a models.dev-style JSON, diff-preview, apply) — gated by a settings flag, never automatic, never in CI | Should |
| FR-9 | Pricing-override changes are audit-logged (who/when/what) — via PRD-06's config-version mechanism when it lands, else a minimal `event` emission | Should |
| FR-10 | Per-initiative budget alerts reusing `initiatives.budget_usd` | Won't (v1) |

## 5. Detailed design

### 5.1 Data model / migrations

```sql
-- migration 000X_pricing_budgets
ALTER TABLE org_llm_config ADD COLUMN pricing_override JSONB;  -- promised by pricing.py:3-5

CREATE TABLE org_budgets (
  org_id        UUID PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
  monthly_limit_usd NUMERIC(12,2) NOT NULL,
  alert_pcts    JSONB NOT NULL DEFAULT '[50, 80, 100]',
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- RLS: same org-scoped policy + FORCE as org_llm_config (mirror 0002_rls / 0003_rls_force)

CREATE TABLE org_budget_alerts (          -- dedupe ledger: one alert per org/month/threshold
  org_id     UUID NOT NULL,
  month      DATE NOT NULL,               -- first of month
  pct        INT  NOT NULL,
  fired_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (org_id, month, pct)
);
```

`pricing_override` lives on `org_llm_config` (not a new table) because that row is already the
org's LLM identity, is RLS-FORCEd, and is already read by the factory's `_org_default` query
(`app/llm/factory.py:166-187`) — one extra selected column, no new read path.

### 5.2 Catalog as data file

- `app/llm/pricing_catalog.json` — `{ "version": "2026.07", "prices": { "anthropic/claude-opus-4-8": {"in": 15.0, "out": 75.0}, ... } }`.
- `pricing.py` loads it once at import into the same `PRICES` structure; the module keeps
  `estimate_usd` as the single entry point so `callbacks.py:9` and `llm_backend.py:111` don't
  change imports.
- Release process: catalog updates ride normal releases (like any code change). Optional online
  refresh (FR-8): `POST /admin/pricing/catalog/refresh` fetches `settings.pricing_catalog_url`,
  shows a diff, and on confirm writes the fetched catalog to the DB table
  `pricing_catalog_override(id, fetched_at, body JSONB)` — the *instance-level* override layer,
  read after the shipped file. Gated by `PDLC_PRICING_REFRESH_ENABLED=false` default so hermetic
  deployments never see network.

### 5.3 `estimate_usd` with org context

Two call sites today: `app/clickstream/callbacks.py:36` and `app/runtime/llm_backend.py:114`.
Neither has org pricing at hand. Design:

```python
# pricing.py
def estimate_usd(provider, model_id, usage, overrides: dict | None = None) -> float | None:
    key = f"{provider}/{model_id}"
    if overrides and key in overrides:
        p = overrides[key]
    elif key in _CATALOG: p = _CATALOG[key]
    elif f"{provider}/*" in _CATALOG: p = _CATALOG[f"{provider}/*"]
    else: return None                     # FR-5: unpriced, not $0
    return (usage["input"] * p["in"] + usage["output"] * p["out"]) / 1_000_000
```

Override delivery: the factory already resolves org config per call. Extend
`LLMProviderFactory.resolve()` (`factory.py:99-113`) to also return the org's
`pricing_override` (selected in `_org_default`), cached per-org with a short TTL (60 s) to avoid
a second query per completion. `FactoryCompletionBackend._record` (`llm_backend.py:108-126`) and
`LLMTokenTallyCallback` (constructed with provider/model in `callbacks.py:16-22`) receive the
override dict at construction/resolve time. Signature change is additive (`overrides=None`
keeps all existing tests green).

`None` propagation: `record_llm(usd=...)` treats `None` as 0 for the OTel counter but sets a
`pdlc.unpriced=true` span attribute; the clickstream payload carries `"usd_estimate": null` so
SQL rollups can `COUNT(*) FILTER (WHERE usd_estimate IS NULL)`.

### 5.4 Budget evaluation

No new pipeline: the月 spend is already derivable from the `events` table
(`app/db/models.py:297-319`, `event_type = 'llm.tokens_spent'`, `payload->>'usd_estimate'`).
Evaluation point: inside the Postgres clickstream sink path, after inserting a
`llm.tokens_spent` event, a lightweight check (per org, memoized 5 min) compares
month-to-date sum vs `org_budgets`. Crossing a threshold not yet in `org_budget_alerts`
inserts the ledger row (PK dedupes concurrent workers) and emits `budget.threshold`:

```json
{ "event_type": "budget.threshold", "payload": {
    "pct": 80, "month": "2026-07", "spent_usd": 412.55, "limit_usd": 500.0 } }
```

Console banner (FR-7): the Nexus admin live route already streams events; the studio shows a
dismissible banner for the current month's highest fired threshold.

### 5.5 API contract

```
GET  /admin/pricing            → { "catalog_version": "2026.07",
                                   "effective": { "openai/gpt-5.4": {"in": 2.0, "out": 12.0, "source": "override"},
                                                  "anthropic/claude-opus-4-8": {"in": 15.0, "out": 75.0, "source": "catalog"} } }
PUT  /admin/pricing/overrides  ← { "openai/gpt-5.4": {"in": 2.0, "out": 12.0} }   → { "ok": true }
DELETE /admin/pricing/overrides/{provider}/{model_id}                              → { "ok": true }
GET  /admin/budget             → { "monthly_limit_usd": 500.0, "alert_pcts": [50,80,100],
                                   "month_to_date_usd": 412.55, "fired": [50, 80] } | null
PUT  /admin/budget             ← { "monthly_limit_usd": 500.0, "alert_pcts": [50,80,100] } → { "ok": true }
POST /admin/pricing/catalog/refresh  (403 unless PDLC_PRICING_REFRESH_ENABLED)     → { "diff": {...} } then { "applied": true }
```

New router `app/routes/admin/pricing.py`, mounted in `app/routes/admin/__init__.py` beside
`models_router` (`__init__.py:29`), inheriting `require_admin` (`__init__.py:21`); handlers
follow the `set_org_context` + sync-engine idiom of `routes/admin/models.py:55-60`.

### 5.6 UI notes

Extends the Settings Console (PRD-02): a "Pricing & Budget" tab — effective price sheet with
source badges (catalog / override / unpriced), inline edit per row, budget card with
month-to-date progress bar and threshold chips. Disclaimer text: *"Estimates for dashboards
only — never used for billing."*

## 6. Security & tenancy

- `pricing_override` and `org_budgets` are org-rows under the same RLS + FORCE policies as
  `org_llm_config`; admin routes derive org from the token (`admin_org` guard,
  `routes/admin/models.py:53`). No cross-org read path.
- Catalog refresh is instance-scoped (operator-level) — restrict to the self-host admin / a new
  operator check; it must not be reachable by ordinary org admins in SaaS mode.
- Prices are not secrets; no secretstore involvement.

## 7. Rollout & migration

1. Migration adds column + two tables; `pricing_override` NULL ⇒ behavior identical to today
   except FR-5's `null`-instead-of-`0.0` for unknown models.
2. FR-5 is the only observable change for existing deployments — dashboards must be updated in
   the same release (Grafana panel + Streamlit query treat null as "unpriced" series).
3. Feature flags: none needed for overrides/budgets (data-driven, absent = off);
   `PDLC_PRICING_REFRESH_ENABLED` (default false) gates the only network path.

## 8. Testing strategy (hermetic)

- Pure-function tests for the new `estimate_usd` resolution order incl. `None` path — no I/O.
- Catalog loader test: packaged JSON parses, all keys well-formed, spot-check known prices.
- Route tests against the test DB (same harness as existing admin/models tests): override
  CRUD round-trip under RLS, budget PUT/GET, threshold ledger dedupe (insert same pct twice).
- Budget evaluator test with a seeded events table — no network, no clock dependence (month
  passed explicitly).
- Refresh endpoint: tested with a fake fetcher injected (the fetch function is a module-level
  seam, same pattern as the graph's injectable ports); CI never fetches.

## 9. Effort estimate

**M — ~2.5 eng-weeks.** Column+tables+RLS (0.5w), pricing resolution + call-site threading +
null handling (0.5w), admin API + tests (0.5w), budget evaluator + alerts (0.5w), console tab +
dashboard null-handling (0.5w). Catalog refresh endpoint +0.5w if included in v1.

## 10. Risks & mitigations

- **R1: `usd_estimate: null` breaks existing rollup SQL / dashboards.** Mitigate: audit all
  consumers (exports.py rollups, Grafana JSON, Streamlit queries) in the same PR; `COALESCE`
  where summing.
- **R2: per-call override lookup adds latency.** Mitigate: 60 s per-org TTL cache in the
  factory; overrides ride the existing `_org_default` query (no extra round-trip on the hot
  path).
- **R3: budget check on the event-insert path slows ingestion.** Mitigate: memoized 5-min
  evaluation window; check runs post-commit and failure is swallowed (alerts are best-effort).
- **R4: catalog refresh introduces a supply-chain-ish input.** Mitigate: diff-preview +
  explicit confirm, schema validation, flag default-off.

## 11. Success metrics

- % of `llm.tokens_spent` events priced (target: unpriced < 2% after one catalog release cycle).
- ≥1 org uses a pricing override within a month of release (self-host telemetry n/a — measure in
  SaaS or via issue feedback).
- Budget alerts fire correctly in staging simulation (exactly once per org/month/threshold).

## 12. Dependencies

- None hard. PRD-02 (console) for the UI surface; PRD-06 for audit-grade override history
  (soft — a clickstream event suffices until then).

## 13. Open questions

1. Hard enforcement: should 100% budget optionally *pause new turns* (a gate, in pdlc terms)?
   Deferred; requires product decision on failure UX mid-thread.
2. Balance/quota queries per provider (cc-switch §6): worth it for Bedrock/OpenAI where account
   APIs exist? Deferred — per-provider account APIs are inconsistent and need extra credentials
   scopes.
3. Cache-token pricing (Anthropic cache reads/writes are billed differently; cc-switch
   normalizes cache tokens): today `_extract_usage`/`_usage_from_message` only capture
   input/output (`callbacks.py:42-54`, `llm_backend.py:129-138`). Extend usage extraction first?
4. Should `pricing_override` participate in PRD-06 export/import bundles? (Leaning yes.)
