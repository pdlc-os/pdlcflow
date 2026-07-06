# pdlcflow — Current-State Capability Map (provider/config domain)

> Research artifact — 2026-07-05. Codebase audit of pdlcflow's existing capabilities in the
> functional areas cc-switch covers. Companion docs:
> [00-cc-switch-capability-inventory.md](00-cc-switch-capability-inventory.md),
> [02-gap-analysis.md](02-gap-analysis.md).

Scope note: pdlcflow is a server-side multi-tenant LangGraph SaaS. Its "provider config" lives in
Postgres + env + an admin REST API, resolved at LLM-call time. cc-switch is a desktop app that
rewrites local CLI config files. So the overlap is conceptual, not architectural — pdlcflow has
the data model but almost no interactive tooling around it.

## 1. LLM provider management — STRONG

- `services/pdlc-engine/app/llm/factory.py` — `LLMProviderFactory` with a `_BUILDERS` dict
  registering **10 providers**: bedrock, anthropic, vertex, azure, openai, gemini, ollama, plus 3
  subscription CLIs (claude_code, codex, gemini_cli).
- Resolution order (`factory.py:99-113`): **agent-level override → org default → instance default
  (env) → hardcoded Bedrock/Claude fallback**. Provider-neutral tiers
  (`premium|balanced|economy`) map to concrete model IDs via `llm/tier_map.py`
  (`DEFAULT_TIER_MAP`, overridable per-tenant).
- Per-provider builders in `llm/providers/*.py` are thin langchain wrappers. **API key
  precedence** (e.g. `providers/anthropic.py:16`, `openai.py:16`, `azure.py:22`, `gemini.py:16`):
  use per-tenant `cfg.secret_value` if set, else the SDK's own env var (`ANTHROPIC_API_KEY`,
  `OPENAI_API_KEY`, etc.). Base URLs/endpoints: Ollama `cfg.endpoint or http://localhost:11434`
  (`ollama.py:14`); Azure/Vertex/Bedrock use region/endpoint from config.
- Providers are **registered in code only** — you cannot add a *new provider type* at runtime,
  but you can add/edit provider *selections + model IDs + region/endpoint* per org/agent at
  runtime (see §2). No preset catalog beyond the built-in tier_map defaults.
- CLI providers are hard-gated (`factory.py:_guard_cli`, `config.py:65`): require
  `PDLC_ENABLE_CLI_PROVIDERS=true` AND refuse to run when `PDLC_AUTH_REQUIRED` is on
  (single-user self-host only, since they bill one local subscription).

## 2. Per-tenant / per-org model config — PRESENT (DB + REST), key injection HALF-WIRED

- Tables `org_llm_config` and `agent_llm_config` — declared in `db/models.py:259-293` (created
  via `Base.metadata.create_all` in migration `0001_init.py`), RLS-isolated + FORCEd
  (`0002_rls.py`, `0003_rls_force.py`). Columns: provider, region, endpoint, **secret_ref**,
  tier_map (org) / model_id (agent). CHECK constraint limits provider to the 7 non-CLI providers.
- Admin REST API fully functional server-side: `routes/admin/models.py` — GET/PUT
  `/admin/models/org-default`, GET/PUT/DELETE `/admin/models/agent-overrides/{persona}`. Upserts
  into the tables under the admin's org context. Mounted via `routes/admin/__init__.py` behind
  `require_admin`.
- **IMPORTANT GAP (BYOK):** the schema has a `secret_ref` column and a full pluggable secrets
  backend exists (`secretstore/__init__.py`: Fernet-encrypted / Vault KV v2 / env), BUT the
  factory's `_org_default` and `_agent_override` queries (`factory.py:150-187`) select only
  provider/model_id/region/endpoint/tier_map — they **never read `secret_ref` nor call
  `secrets.resolve()`**, so `ProviderConfig.secret_value` is always None in the tenant path. Net
  effect: per-tenant *provider/model/region/endpoint* selection works, but per-tenant **API keys
  are stored-capable yet not actually injected** — every provider falls back to the
  instance-wide env key. Architecturally staged (`secret_value` consumed by all providers) but
  the DB→factory wiring is missing.

## 3. Settings UI — MOCKUP ONLY (not functional)

- Only one relevant screen: `apps/studio/src/routes/admin/models.tsx`. It renders an org-default
  row + per-agent override rows with a provider `<select>`, a model-id `<input>`, and a **"Test"
  button** — but it is a **pure static mockup**: no `useState`, no fetch, no `onChange`, no
  submit handler. `lib/api.ts` has **no** models/provider/org-default client methods. So there is
  no working UI for provider config, model selection, or API-key entry today — the backend API in
  §2 is unused by the frontend.

## 4. Model routing / switching — PRESENT (config-driven, not one-click)

- Tiers + per-agent personas + the 4-level resolution chain give real routing (§1). "Switching
  the active provider" = PUT to `/admin/models/org-default` or set an agent override; takes
  effect on the next call. There is a **hardcoded final fallback** (Bedrock/us-east-1,
  `factory.py:200`) but **no automatic failover/retry** between providers on error, and no
  health-based routing. `config.py` LLM knobs: `default_llm_provider`, `bedrock_region`,
  `ollama_endpoint`, `wire_llm` (must be on to actually route through the factory), `judge_tier`.
- Per-tenant RPM rate limiting is **stubbed** (`llm/rate_limit.py` — `acquire()` always returns
  True; real Redis token bucket described in the docstring but not implemented).

## 5. Config backup / versioning / import-export — NOT PRESENT

- No provider-config backup, snapshot, restore, or import/export of provider sets anywhere.
  `routes/admin/exports.py` exists but is **BI analytics CSV/DDL export** (clickstream rollups),
  unrelated to provider config. `pricing.py` docstring references an
  `org_llm_config.pricing_override` "added in Phase B" — **no such column exists**. No config
  versioning; the only versioning-adjacent feature is feature "time-travel" over the event log,
  unrelated.

## 6. Health / latency checks on providers — NOT PRESENT (for LLM connectivity)

- The Studio "Test" button is a decorative no-op with **no backend endpoint** — endpoint
  speed/latency testing does not exist.
- `routes/health.py`: `/health/ready` returns `{"llm": "stub"}` — it does **not** test LLM
  connectivity.
- The `doctor` utility (`packages/pdlc-graph/pdlc_graph/graphs/utility/doctor.py`) is
  **unrelated** to providers: it's a hermetic in-memory PDLC-workflow health check
  (has_feature/has_phase/no_blockers etc.), no git/network/LLM probing.

## 7. MCP support — NOT PRESENT

- Grep for "mcp" across `services/`, `packages/`, `apps/` (.py/.ts/.tsx/.md) returns **zero
  matches**. No MCP server config or management anywhere.

## 8. Proxy support — NOT PRESENT

- Grep for `http_proxy|https_proxy|proxy` across `services/` and `packages/` Python: **zero
  matches**. No HTTP(S) proxy settings for outbound LLM calls (would only work via ambient env
  vars the langchain SDKs happen to honor; nothing explicit).

## 9. Pricing / cost tracking — PRESENT (estimate-only)

- `llm/pricing.py` — static `PRICES` dict `(provider, model_id) → ($/1M in, $/1M out)` for all
  non-CLI providers; `estimate_usd()` with an Ollama `*`=0 wildcard. Explicitly "never used for
  billing decisions," admin-dashboard only.
- Wired via `clickstream/callbacks.py` — `LLMTokenTallyCallback.on_llm_end` emits a
  `llm.tokens_spent` event per completion with provider/model_id/tier/persona/tokens_in/out/
  **usd_estimate**. Rolled up for the Nexus dashboard (Grafana/Streamlit). No per-tenant
  `pricing_override` (planned, not built).

## 10. CLI (`deploy/pdlcflow`) — Docker lifecycle only

- Thin `docker compose` wrapper. Commands: `setup` (up -d), `start`, `stop`, `status` (ps),
  `remove` (down), `wipe` (down -v), and `observability up|down|status` (toggles
  `PDLC_OTEL_ENABLED` in `.env` and runs the OTel+Grafana+Streamlit-Nexus profile). **No**
  provider/model/switch/config subcommands — provider management is entirely via the
  (frontend-unused) admin REST API.

---

## Bottom line vs cc-switch

| cc-switch feature | pdlcflow |
|---|---|
| Multi-provider config (keys/URLs/models) | YES — DB tables + REST API (7 API providers + 3 subscription CLIs) |
| One-click provider switch | Partial — REST PUT, no UI, not one-click |
| Provider presets for vendors | Partial — built-in tier_map defaults only, no editable preset catalog |
| BYOK per-tenant API keys | **Staged but NOT wired** — `secret_ref` column + secretstore exist, factory never reads them |
| Config backup/restore before rewrite | NO |
| Import/export provider sets | NO |
| Endpoint speed/latency testing | NO ("Test" button is a dead mockup) |
| MCP server management | NO |
| Proxy settings | NO |
| Multi-app config (Claude Code/Codex/Gemini CLI) | Different sense — pdlcflow *uses* those CLIs as LLM backends; it does not manage their configs |
| System tray / i18n / auto-update | NO (server app, no desktop shell) |
| Settings UI | Mockup only, non-functional |
| Cost/pricing tracking | YES (estimate-only, richer than cc-switch) |

Key files: `services/pdlc-engine/app/llm/factory.py`, `llm/tier_map.py`, `llm/pricing.py`,
`llm/providers/*.py`, `llm/rate_limit.py`; `app/db/models.py:259-293`;
`app/routes/admin/models.py`; `app/secretstore/__init__.py`; `app/clickstream/callbacks.py`;
`apps/studio/src/routes/admin/models.tsx`; `deploy/pdlcflow`.
