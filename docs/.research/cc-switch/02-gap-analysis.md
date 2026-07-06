# Gap Analysis — cc-switch capabilities vs pdlcflow

> Synthesis artifact — 2026-07-05. Compares the functional capabilities of
> [cc-switch](00-cc-switch-capability-inventory.md) against
> [pdlcflow's current state](01-pdlcflow-current-state.md), classifies each capability's
> applicability to pdlcflow, and indexes the PRDs written for the applicable gaps.
> Roadmap & sequencing: [99-roadmap.md](99-roadmap.md).

## Framing: same problem, different altitude

cc-switch and pdlcflow attack the same underlying problem — *"I use many LLM providers; managing
which one is active, whether it works, and what it costs is painful"* — at different altitudes:

- **cc-switch** solves it for an individual developer's desktop: it rewrites local CLI config
  files, one machine, one user, one click.
- **pdlcflow** solves it for a multi-tenant SaaS: provider choice is org-scoped data in Postgres,
  resolved per-persona/per-tier at LLM-call time, isolated by RLS.

So a capability "missing" in pdlcflow is rarely portable as-is; it must be **translated** into
the server-side multi-tenant idiom. The translation is stated explicitly for every gap below.
Where cc-switch's capability makes no sense server-side (system tray, auto-update of a desktop
binary), it is classified **Not applicable** rather than forced.

The strategic takeaway from the comparison: **pdlcflow's provider backend is ahead of its
surface.** The data model, resolution chain, secrets store, and cost telemetry all exist — but
the admin UI is a dead mockup, BYOK is wired only halfway, and there is zero operational tooling
(test, failover, backup, presets) around the config. cc-switch's success shows that the
*operational ergonomics* of provider management — not the raw capability — is what users value.
The roadmap therefore front-loads "make what exists real" before "add new surface area."

---

## Capability-by-capability disposition

Legend — **GAP**: missing & applicable, PRD written · **PARTIAL**: exists but incomplete, PRD
written for the completion · **PRESENT**: no action · **N/A**: domain mismatch, no PRD.

| # | cc-switch capability | pdlcflow status | Disposition | PRD |
|---|---|---|---|---|
| 1 | Multi-provider config store (keys, URLs, models) | `org_llm_config`/`agent_llm_config` + admin REST | PRESENT (backend) | — |
| 2 | Per-user API keys ("bring your own key") | `secret_ref` column + secretstore exist; factory never reads them → tenant keys silently ignored | **PARTIAL** (broken link) | [PRD-01](03-prd-01-byok-completion.md) |
| 3 | Interactive settings UI / one-click switch | `admin/models.tsx` is a static mockup; no API client methods | **PARTIAL** (mockup) | [PRD-02](04-prd-02-provider-settings-console.md) |
| 4 | Provider health monitoring + endpoint speed test | None; "Test" button dead; `/health/ready` returns `{"llm": "stub"}` | **GAP** | [PRD-03](05-prd-03-provider-health-connectivity.md) |
| 5 | 50+ provider presets, searchable, one-click add; relay/gateway (OpenAI-compatible base-URL) support | Only hardcoded `DEFAULT_TIER_MAP`; no preset catalog; no generic OpenAI-compatible endpoint provider | **GAP** | [PRD-04](06-prd-04-provider-preset-catalog.md) |
| 6 | Auto-failover with circuit breaker, health-based routing | Hardcoded final fallback only; no retry-across-providers; rate limiter is a stub | **GAP** | [PRD-05](07-prd-05-resilient-llm-routing.md) |
| 7 | Config backup/restore, atomic writes, import/export, deep-link import | Nothing for provider config (analytics export is unrelated) | **GAP** | [PRD-06](08-prd-06-config-versioning-import-export.md) |
| 8 | Custom per-model pricing, models.dev pricing import, balance/quota queries | Static `PRICES` dict; `pricing_override` referenced in docstring but column doesn't exist; no quota/budget | **PARTIAL** | [PRD-07](09-prd-07-cost-analytics-enhancements.md) |
| 9 | Proxy settings / egress control (custom headers, UA, connection pooling) | Zero proxy awareness; enterprise egress-through-proxy impossible to configure explicitly | **GAP** | [PRD-08](10-prd-08-egress-network-controls.md) |
| 10 | Unified MCP server management, bind servers to apps | Zero MCP anywhere; pdlcflow agents currently have no external-tool mechanism | **GAP** (strategic) | [PRD-09](11-prd-09-mcp-tool-server-management.md) |
| 11 | Prompts & skills management (registry install, versioned, cross-app sync, backups) | Personas' prompts are baked into the graph package; no org-level customization, no packs | **GAP** | [PRD-10](12-prd-10-prompt-persona-packs.md) |
| 12 | Session manager (browse/search/resume/delete history) | Threads under projects + continue-with-full-history shipped (PR #76); delete/search partial but core present | PRESENT (mostly) | — |
| 13 | Usage/cost dashboard with trends & filters | Clickstream + Grafana/Streamlit Nexus dashboards (PR #78) — richer than cc-switch | PRESENT | — |
| 14 | Format conversion proxy (Anthropic ↔ OpenAI wire formats) | Not needed — langchain adapters already normalize per provider | N/A (solved differently) | — |
| 15 | Managing external CLIs' config files (Claude Code/Codex/Gemini CLI as *targets*) | Inverted relationship: pdlcflow *consumes* those CLIs as LLM backends (`claude_code`, `codex`, `gemini_cli` providers) | N/A | — |
| 16 | Managed CLI-tool lifecycle (install/update the CLIs) | N/A for a server product; `deploy/pdlcflow` manages its own stack | N/A | — |
| 17 | System tray, themes, auto-launch, auto-updater, portable builds | Desktop-shell concerns; pdlcflow is a web console + server | N/A | — |
| 18 | i18n (zh-CN/zh-TW/en/ja/de) | English-only web UI. Real someday-feature, but independent of this comparison's domain | N/A (defer; track separately) | — |
| 19 | Cloud sync of config (WebDAV/S3) | Server product: Postgres *is* the source of truth; covered instead by backup/export (PRD-06) + existing pg backup story | N/A (subsumed by PRD-06) | — |

## The ten gaps, in one paragraph each

1. **BYOK completion (PRD-01).** The single most important fix. Multi-tenant SaaS economics
   require tenants to bring their own API keys; today a tenant can *store* a key
   (`secret_ref` + secretstore) but the factory never resolves it, so every tenant silently
   burns the instance operator's key. This is a correctness/trust bug wearing a feature's
   clothes. Small, backend-only, unblocks everything else.

2. **Provider Settings Console (PRD-02).** cc-switch's core lesson: switching must be
   one-click. pdlcflow has the API but a dead mockup UI. Make `admin/models.tsx` real —
   org default, per-persona overrides, tier-map editing, key entry (via PRD-01), Test button
   (via PRD-03), guarded switch with optimistic UI.

3. **Provider health & connectivity testing (PRD-03).** A `POST /admin/models/test` that runs a
   cheap live probe (auth validity + latency + model availability) against a candidate config
   *before* it's saved, plus a background health status per configured provider. Feeds the UI
   badge and, later, failover.

4. **Preset catalog + OpenAI-compatible gateways (PRD-04).** A curated, versioned preset
   catalog (provider + endpoint + recommended tier_map + pricing hints) applied in one click,
   plus a generic `openai_compatible` provider builder (custom base_url) that opens pdlcflow to
   the entire relay/gateway ecosystem (SiliconFlow, DeepSeek, Kimi, GLM, local vLLM/LiteLLM…)
   without a code change per vendor — cc-switch's biggest adoption lever, translated.

5. **Resilient routing (PRD-05).** Failover chains with a circuit breaker per (org, provider),
   health-aware selection, and a real Redis token-bucket rate limiter to replace the
   always-True stub. Turns "the provider had an incident" from a broken turn into a logged
   fallback.

6. **Config versioning, backup & import/export (PRD-06).** Every change to
   org/agent LLM config becomes an immutable version row (who/when/what), with one-click
   rollback, org-level export/import of provider sets (secrets excluded by reference), and
   environment-promotion support (dev → prod org).

7. **Cost analytics enhancements (PRD-07).** Ship the promised `pricing_override` column,
   admin-editable per-model pricing, a pricing-catalog refresh path (models.dev-style import),
   and org budgets/alerts on the existing `usd_estimate` stream.

8. **Egress network controls (PRD-08).** Explicit outbound proxy configuration
   (instance-level, optionally org-level), custom CA bundle, and per-provider extra headers —
   table-stakes for enterprise self-hosting behind corporate egress.

9. **MCP tool-server management (PRD-09).** The strategic one: an org-scoped MCP server
   registry (URL/command, auth, allowed tools), bound to personas/phases, executed by the
   engine's LangGraph nodes. This is net-new agent capability, not just config plumbing —
   sequenced last for that reason.

10. **Prompt/persona packs (PRD-10).** Org-level overrides of persona system prompts with
    versioning, activation switching, and pack import/export — cc-switch's prompts/skills
    feature translated to pdlcflow's persona model.

## What pdlcflow should NOT copy

- **The local proxy architecture** — pdlcflow is already server-side; interposing another proxy
  duplicates langchain's normalization. Failover belongs in the factory/backend layer (PRD-05).
- **Desktop-shell features** (tray, auto-update, portable ZIP) — wrong product shape.
- **Managing third-party CLI config files** — inverted dependency; pdlcflow consumes CLIs as
  providers.
- **Config cloud-sync to Dropbox/WebDAV** — Postgres is the source of truth; PRD-06's
  export/import + standard DB backups cover the need without a second sync system.

## Sequencing preview

Full rationale in [99-roadmap.md](99-roadmap.md). Short version — three waves:

- **Wave 1 — Make what exists real:** PRD-01 (BYOK) → PRD-03 (health/test) → PRD-02 (console).
- **Wave 2 — Operational maturity:** PRD-04 (presets + gateways) → PRD-05 (resilient routing)
  → PRD-06 (versioning/import-export).
- **Wave 3 — Expansion:** PRD-07 (cost) → PRD-08 (egress) → PRD-10 (prompt packs) → PRD-09 (MCP).
