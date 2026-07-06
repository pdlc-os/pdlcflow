# PRD-04: Provider Preset Catalog & OpenAI-Compatible Gateways

> **Status:** Draft — for assessment · **Date:** 2026-07-05
> **Origin:** [cc-switch gap analysis](02-gap-analysis.md), row 5
> **Related PRDs:** depends on [PRD-01 BYOK](03-prd-01-byok-completion.md),
> [PRD-02 Settings Console](04-prd-02-provider-settings-console.md),
> [PRD-03 Health/Test](05-prd-03-provider-health-connectivity.md);
> feeds [PRD-07 Cost Analytics](09-prd-07-cost-analytics-enhancements.md).

## 1. Problem & motivation

cc-switch's single biggest adoption lever is its **50+ built-in provider presets**: a user picks
"DeepSeek" or "SiliconFlow" from a searchable list, pastes a key, and is running — no JSON, no
docs-diving, no knowing which base URL or model IDs a vendor uses. Combined with generic
OpenAI-compatible endpoint support, this opened cc-switch to the entire relay/gateway ecosystem
without per-vendor code.

pdlcflow has the opposite experience today:

- Configuring an org's provider requires knowing the exact provider enum value, region/endpoint
  semantics, and hand-writing a full `tier_map` (`{"premium": "...", "balanced": "...",
  "economy": "..."}`) of concrete model IDs (`routes/admin/models.py:32-37`). The only defaults
  live in code (`llm/tier_map.py:16-72`, `DEFAULT_TIER_MAP`) and are invisible to the admin API.
- pdlcflow supports exactly 7 API providers, hardcoded three ways: the factory's `_BUILDERS`
  dict (`llm/factory.py:61-72`), the admin route's `Provider` Literal
  (`routes/admin/models.py:25`), and DB CHECK constraints on both config tables
  (`db/models.py:267-271`, `290-293`). There is **no way to point pdlcflow at OpenRouter,
  DeepSeek, Kimi/Moonshot, GLM, SiliconFlow, LiteLLM, or a local vLLM server** — all of which
  speak the OpenAI wire protocol — without a code change and a DB migration per vendor.

Two features, one PRD, because the preset catalog is what makes the generic provider *usable*:
an `openai_compatible` provider with no preset catalog forces admins to hand-type base URLs and
model IDs; a catalog with no generic provider can only describe the 7 providers we already have.

## 2. Goals / Non-goals

**Goals**

- G1. Ship a curated, versioned **preset catalog** as in-repo data, exposed read-only via the
  admin API and browsable/searchable in the Settings Console.
- G2. One-click **apply preset to org**: a single call that upserts `org_llm_config` with the
  preset's provider/endpoint/tier_map, leaving only the API key for the admin to supply.
- G3. New generic **`openai_compatible` provider** (custom `base_url` + key) usable as org
  default or per-agent override, opening pdlcflow to relay gateways and self-hosted
  OpenAI-protocol servers with zero per-vendor code.
- G4. Presets carry **pricing hints** so `usd_estimate` stays meaningful for gateway models
  (full pricing-override machinery is PRD-07; this PRD only ships hints the catalog can seed).

**Non-goals**

- NG1. No runtime-editable catalog (tenant-defined presets). The catalog is vendored data
  updated by pdlcflow releases; org-level custom config is just… the existing config.
- NG2. No Anthropic-protocol generic provider (`anthropic_compatible`) in v1 — demand unproven;
  the design leaves room.
- NG3. No automatic model discovery (`GET /v1/models` probing) in v1 — noted as an open
  question; PRD-03's test endpoint can validate a chosen model instead.
- NG4. No billing/quota logic (PRD-07).

## 3. Users & user stories

- **Org admin (SaaS tenant):** "As an org admin, I want to pick 'OpenRouter' from a list, paste
  my key, and have premium/balanced/economy mapped to sensible models, so that onboarding takes
  one minute instead of a support ticket."
- **Self-hoster:** "As a self-hoster running vLLM on my LAN, I want to point pdlcflow at
  `http://gpu-box:8000/v1` and name my model, so that I can run pdlcflow fully locally with an
  OpenAI-protocol server instead of only Ollama."
- **Cost-sensitive squad lead:** "As a squad lead, I want the `economy` tier routed to a cheap
  gateway model while `premium` stays on Claude, so that bulk work is cheap without giving up
  quality where it matters." (Achieved by applying a preset then editing the tier_map —
  PRD-02's console.)
- **pdlcflow maintainer:** "As a maintainer, I want adding a vendor to be a data PR (one catalog
  entry + CI validation), so that vendor coverage scales without touching the factory."

## 4. Functional requirements

| ID | Requirement | MoSCoW |
|----|-------------|--------|
| FR-1 | A preset catalog file ships in-repo and is loaded at engine boot; entries carry: `id`, `label`, `provider`, `endpoint` (nullable), `region` (nullable), `tier_map` (complete 3-tier map), `docs_url`, `key_hint` (e.g. "sk-or-…"), `pricing_hints` (optional per-model `$/1M in/out`), `tags` (searchable), `catalog_version`. | Must |
| FR-2 | `GET /admin/models/presets` lists entries; supports `?q=` substring search over id/label/tags. | Must |
| FR-3 | `POST /admin/models/presets/{id}/apply` upserts the org's `org_llm_config` from the preset (provider, endpoint, region, tier_map). Secret is NOT part of apply; the console chains PRD-01's key-entry call after. | Must |
| FR-4 | New provider value `openai_compatible`: builder constructs `ChatOpenAI(base_url=cfg.endpoint, api_key=cfg.secret_value, model=model_id)`. `endpoint` is **required**; requests without it are rejected at the API layer. | Must |
| FR-5 | DB CHECK constraints on `org_llm_config.provider` and `agent_llm_config.provider` are widened to include `openai_compatible` (Alembic migration). | Must |
| FR-6 | For `openai_compatible`, `tier_map` (org) / `model_id` (agent) is **mandatory** — there is no `DEFAULT_TIER_MAP` entry to fall back to, and the factory must fail with a clear config error, not a `KeyError`. | Must |
| FR-7 | `estimate_usd()` consults preset `pricing_hints` for `("openai_compatible", model_id)` before falling back to `0.0`, so gateway usage isn't silently free in dashboards. | Should |
| FR-8 | Catalog entries are validated in CI (schema check; every `tier_map` complete; every `openai_compatible` preset has an endpoint). | Should |
| FR-9 | Console: preset picker (search box + cards) on the Models settings page; "Apply" pre-fills the org-default form for review before save. | Should |
| FR-10 | `key_hint` and `docs_url` render in the console's key-entry step. | Could |
| FR-11 | Deep-link import of third-party preset JSON (cc-switch's `ccswitch://`) | Won't (v1) |

## 5. Detailed design

### 5.1 Catalog data

New file `services/pdlc-engine/app/llm/presets/catalog.json` (data, not code — reviewed like
code, shipped with the image):

```json
{
  "catalog_version": "2026.07",
  "presets": [
    {
      "id": "openrouter",
      "label": "OpenRouter",
      "provider": "openai_compatible",
      "endpoint": "https://openrouter.ai/api/v1",
      "region": null,
      "tier_map": {
        "premium": "anthropic/claude-opus-4.8",
        "balanced": "anthropic/claude-sonnet-4.6",
        "economy": "deepseek/deepseek-chat"
      },
      "docs_url": "https://openrouter.ai/docs",
      "key_hint": "sk-or-v1-…",
      "pricing_hints": {
        "deepseek/deepseek-chat": {"in": 0.27, "out": 1.10}
      },
      "tags": ["gateway", "multi-model", "openai-compatible"]
    },
    {
      "id": "bedrock-us",
      "label": "AWS Bedrock (us-east-1)",
      "provider": "bedrock",
      "endpoint": null,
      "region": "us-east-1",
      "tier_map": {
        "premium": "anthropic.claude-opus-4-8",
        "balanced": "anthropic.claude-sonnet-4-6",
        "economy": "anthropic.claude-haiku-4-5"
      },
      "docs_url": "https://docs.aws.amazon.com/bedrock/",
      "key_hint": null,
      "tags": ["aws", "claude", "first-party"]
    }
  ]
}
```

Initial roster (~15 entries): the 7 first-party providers with their `DEFAULT_TIER_MAP` values
(so the catalog subsumes `tier_map.py`'s knowledge and makes it API-visible), plus
`openai_compatible` presets for OpenRouter, DeepSeek, Moonshot/Kimi, Zhipu/GLM, SiliconFlow,
LiteLLM (localhost), vLLM (localhost), Ollama-OpenAI-mode. Loader:
`app/llm/presets/__init__.py` → `load_catalog() -> Catalog` (module-level cache, pydantic
validation at import; a malformed catalog fails boot loudly in CI, not silently at request
time).

### 5.2 Admin API

Extends `routes/admin/models.py` (same router, same `admin_org` guard):

```
GET /admin/models/presets?q=deepseek
→ 200 {"catalog_version": "2026.07", "presets": [{…FR-1 fields, minus pricing_hints…}]}

POST /admin/models/presets/openrouter/apply
→ 200 {"ok": true, "applied": {"provider": "openai_compatible",
        "endpoint": "https://openrouter.ai/api/v1", "tier_map": {…}},
        "needs_secret": true}
```

`apply` reuses the exact upsert SQL of `set_org_default` (`routes/admin/models.py:70-80`); it
does not touch `secret_ref`. `needs_secret` is true when the preset's provider consumes an API
key (everything except bedrock/vertex/ollama), telling the console to chain to PRD-01's
`PUT /admin/models/org-default/secret`.

### 5.3 The `openai_compatible` provider

New `app/llm/providers/openai_compatible.py`, mirroring `providers/openai.py:12-18`:

```python
def build(cfg, model_id: str) -> BaseChatModel:
    from langchain_openai import ChatOpenAI
    if not cfg.endpoint:
        raise ValueError("openai_compatible requires an endpoint (base_url)")
    kwargs: dict = {"model": model_id, "base_url": cfg.endpoint}
    if cfg.secret_value:
        kwargs["api_key"] = cfg.secret_value
    else:
        kwargs["api_key"] = "not-needed"  # local vLLM/LiteLLM without auth
    return ChatOpenAI(**kwargs)
```

Registration points (all three must move in lockstep — this PRD makes that list explicit and
adds a test asserting they agree):

1. `_BUILDERS` + the `Provider` Literal in `llm/factory.py:52-72`.
2. The admin route's `Provider` Literal (`routes/admin/models.py:25`).
3. DB CHECK constraints (migration, §5.4).

**tier_map safety (FR-6):** `resolve_model_id()` (`llm/tier_map.py:75-81`) does
`DEFAULT_TIER_MAP[provider]` when no override exists → today an `openai_compatible` org row
with a null/partial tier_map would raise `KeyError` mid-turn. Change: `resolve_model_id` raises
`ModelResolutionError("provider 'openai_compatible' has no default tier map; org tier_map is
required")`, and the API layer rejects `PUT /admin/models/org-default` /
`PUT /admin/models/agent-overrides/{persona}` payloads where `provider == "openai_compatible"`
and the map/model_id is missing — so the failure is at config-write time, not turn time.
`_guard_cli` (`factory.py:115-129`) is untouched — `openai_compatible` is a normal API
provider, allowed in multi-tenant mode.

**Pricing (FR-7):** `estimate_usd()` (`llm/pricing.py:34-41`) gains one lookup step: after the
static `PRICES` miss and before the `(provider, "*")` wildcard, consult
`load_catalog().pricing_hint(provider, model_id)`. Unknown gateway models still fall through to
`0.0` — PRD-07's `pricing_override` is the real fix; dashboards should label zero-cost gateway
rows "unpriced" rather than "$0.00" (console note).

### 5.4 Migration

Alembic `0008_openai_compatible.py` (following `0006_hierarchy.py`). The CHECK constraints in
`db/models.py:267-271`/`290-293` are **unnamed** (Postgres auto-names them
`org_llm_config_provider_check` etc.) — the migration must drop by the auto-generated name (or
introspect `pg_constraint`) and recreate **named** constraints
(`ck_org_llm_config_provider`, `ck_agent_llm_config_provider`) including
`'openai_compatible'`, so future widenings are deterministic. Downgrade restores the 7-value
list (guarded: fails if any row already uses the new value).

### 5.5 Console (UI notes)

On PRD-02's Models settings page: a "Start from a preset" affordance opens a searchable card
list (label, tags, docs link). Selecting one pre-fills the org-default form (provider, endpoint,
tier_map rows) in an *unsaved* state — the admin reviews, optionally edits tiers, supplies the
key (PRD-01 flow), hits Test (PRD-03), then Save. Preset apply via `POST …/apply` is the
API-first path; the console prefers pre-fill + normal save so Test-before-save works.

## 6. Security & tenancy

- Catalog is global, read-only, non-sensitive; no RLS needed. Applying writes only the calling
  admin's org row via the existing RLS-scoped upsert (`set_org_context`, RLS-FORCEd tables).
- `openai_compatible` endpoints are tenant-supplied URLs → **SSRF surface**. The engine will
  POST completions (with the tenant's own key) to an arbitrary URL. Mitigations: scheme
  allowlist (`https://` required when `settings.environment != "dev"`; `http://` allowed for
  self-host LAN), block link-local/metadata ranges (169.254.0.0/16, and cloud metadata hosts)
  at validation time, and log endpoint changes to the clickstream. PRD-08 (egress controls)
  hardens this further; PRD-06 gives the audit trail.
- Presets never contain secrets; `key_hint` is a format example, not a value.

## 7. Rollout & migration

1. Migration 0008 (constraint widening) — deployable ahead of code, no data change.
2. Engine release: builder + catalog + API. Feature is inert until an org applies a preset or
   selects the new provider; existing orgs unaffected.
3. Console release (PRD-02 dependency): preset picker.
4. Catalog updates ride normal releases; `catalog_version` surfaces in `GET …/presets` so the
   console can show freshness.

No backfill. `DEFAULT_TIER_MAP` stays authoritative for the 7 first-party providers (catalog
mirrors it; a CI check asserts the mirror doesn't drift).

## 8. Testing strategy

Hermetic, no network — consistent with the repo's injectable-port pattern:

- **Catalog:** schema-validation test over the real `catalog.json` (every preset: complete
  tier_map; endpoint present iff `openai_compatible`; pricing hints non-negative). Drift test:
  first-party presets' tier_maps == `DEFAULT_TIER_MAP`.
- **Builder:** unit test constructs the `openai_compatible` model with a fake `cfg` and asserts
  `ChatOpenAI` kwargs (base_url/api_key/model) without invoking it (mirror of existing provider
  builder tests); error path when `endpoint` is None.
- **Factory:** registration-agreement test (`_BUILDERS` keys == route Literal == migration's
  constraint list, via a shared constant); `resolve_model_id` raises `ModelResolutionError` (not
  KeyError) for `openai_compatible` without override.
- **API:** route tests with the in-memory/test DB — search filtering, apply-upsert result,
  validation rejection of `openai_compatible` without tier_map, SSRF validation rejections.
- **Migration:** alembic upgrade/downgrade round-trip in the existing migration test harness;
  insert an `openai_compatible` row post-upgrade.

## 9. Effort estimate

**M — ~2 eng-weeks.** Builder + factory/route/migration wiring (3d), catalog data + loader +
validation (2d), API endpoints + tests (2d), console preset picker (2-3d, assumes PRD-02
scaffolding exists). Catalog curation is ongoing editorial work thereafter (~data PR per
vendor).

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| SSRF via tenant-supplied endpoints | §6 validation; PRD-08 egress allowlist as defense-in-depth |
| Gateway wire-protocol quirks (partial OpenAI compat: missing usage_metadata, no streaming) | `_usage_from_message` already degrades to zeros (`llm_backend.py:129-138`); document per-preset caveats in `docs_url`; PRD-03 Test button catches hard failures pre-save |
| Preset rot (vendors rename models/URLs) | `catalog_version` + CI schema checks + community data PRs; presets are suggestions, org config is the truth |
| Cost blind spot for unpriced gateway models | FR-7 hints now; PRD-07 `pricing_override` as the durable fix; dashboards mark "unpriced" |
| Three registration points drift | Shared constant + agreement test (§8) |

## 11. Success metrics

- Time-to-first-successful-completion for a new org using a preset: **< 5 minutes** (from
  console open to green Test).
- ≥ 30% of newly configured orgs use a preset within one release of console availability.
- Zero engine code changes required for the next 5 vendor additions (data PRs only).
- Support tickets tagged "provider setup" trend to zero.

## 12. Dependencies

- **PRD-01 (BYOK)** — hard dependency for SaaS use: `openai_compatible` keys are per-tenant;
  without secret_ref resolution the provider only works self-host via `OPENAI_API_KEY`
  ambient env (wrong key for a gateway). Apply-flow's `needs_secret` chains into PRD-01's
  key-entry endpoint.
- **PRD-02 (Console)** — the preset picker lives there; API-only value without it is real but
  small.
- **PRD-03 (Health/Test)** — "Test before save" is the safety net for arbitrary gateways;
  strongly recommended to land first or together.
- Feeds **PRD-07** (pricing hints are the seed data for pricing overrides) and constrains
  **PRD-05** (failover chains may cross into gateway providers).

## 13. Open questions

1. Should `apply` also write per-persona overrides when a preset carries persona
   recommendations (e.g. a coding-tuned model for `bolt`)? Deferred — presets are org-level in
   v1.
2. `GET /v1/models` discovery for `openai_compatible` endpoints (cc-switch probes this for
   Codex): worth adding to PRD-03's test call as an optional enrichment?
3. Catalog in-repo vs. fetchable feed: in-repo chosen for hermeticity/supply-chain review; is a
   signed remote feed worth it once the roster passes ~50 entries?
4. Anthropic-protocol generic provider (`anthropic_compatible`) — any real demand (Bedrock
   proxies, LiteLLM already fronts it as OpenAI-compatible)?
