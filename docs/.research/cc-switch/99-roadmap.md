# Roadmap — Building cc-switch-inspired capabilities into pdlcflow

> Prioritization & sequencing artifact — 2026-07-05. Sequences the ten PRDs from the
> [gap analysis](02-gap-analysis.md). Each PRD is a self-contained assessment doc; this file is
> the ordering argument.

## Prioritization framework

Each gap is scored on four axes:

1. **Trust/correctness debt** — does the gap make something that *looks* shipped behave wrongly?
   (Highest weight: silent misbehavior costs more than missing features.)
2. **Unblocking power** — how many later PRDs depend on it?
3. **User-visible value per eng-week** — cc-switch's lesson is that ergonomics around existing
   capability (one-click switch, presets, Test button) drives adoption more than net-new depth.
4. **Strategic scope creep risk** — big net-new subsystems (MCP) go last, after the foundation
   they'd sit on is proven.

## The sequence

| Seq | PRD | Title | Size | Depends on | Why here |
|---|---|---|---|---|---|
| 1 | [PRD-01](03-prd-01-byok-completion.md) | BYOK completion | **S** (~1 wk) | — | Fixes a *silent correctness bug*: tenants can store keys that are then ignored, billing the operator's key. Backend-only, small, and a hard prerequisite for the console's key-entry field, presets that need keys, and multi-provider failover. Nothing else should ship before the config the UI will edit actually takes effect. |
| 2 | [PRD-03](05-prd-03-provider-health-connectivity.md) | Provider health & connectivity testing | **S–M** (1–2 wk) | PRD-01 (probes must use the tenant's resolved key) | The console's "Test" button needs a backend before the console is wired; health status is also the substrate PRD-05's circuit breaker consumes. Cheap to build once BYOK resolution exists. |
| 3 | [PRD-02](04-prd-02-provider-settings-console.md) | Provider Settings Console | **M** (2–3 wk) | PRD-01, PRD-03 | The single most user-visible payoff: turns the dead mockup into cc-switch's core loop (view → test → switch, one click). Sequenced after 01/03 so it launches complete — shipping the UI first would expose the BYOK bug and a dead Test button. Ends Wave 1: *everything that already exists is now real.* |
| 4 | [PRD-04](06-prd-04-provider-preset-catalog.md) | Preset catalog + OpenAI-compatible gateways | **M** (2–3 wk) | PRD-02 (surface), PRD-03 (validate preset on apply) | cc-switch's biggest adoption lever translated: one-click provider onboarding, and the `openai_compatible` builder opens the entire relay/gateway + local-inference ecosystem without per-vendor code. Multiplies the console's value immediately after it ships. |
| 5 | [PRD-05](07-prd-05-resilient-llm-routing.md) | Resilient routing: failover, circuit breaker, rate limits | **M–L** (3–4 wk) | PRD-01 (per-tenant keys per chain link), PRD-03 (health signal), PRD-04 (more providers → more fallback options) | Reliability step-change: provider incidents become logged fallbacks instead of broken turns. Also retires the always-True rate-limiter stub. Needs the health substrate and benefits from a populated provider pool, hence after 03/04. |
| 6 | [PRD-06](08-prd-06-config-versioning-import-export.md) | Config versioning, audit, backup & import/export | **M** (2–3 wk) | PRD-02 (history/rollback UI lives in the console) | Enterprise-trust feature: who changed the org's model config, rollback, and environment promotion. More valuable once the console (3) and presets (4) make config churn frequent. Closes Wave 2: *provider management is operationally mature.* |
| 7 | [PRD-07](09-prd-07-cost-analytics-enhancements.md) | Cost analytics: pricing overrides, catalog refresh, budgets | **M** (~2 wk) | PRD-04 (unknown gateway models need custom pricing to cost anything) | Pays the `pricing_override` promissory note in `pricing.py`, and gateway models from PRD-04 are unpriceable without it — natural successor. Budgets/alerts ride the existing `usd_estimate` stream and Nexus dashboards. |
| 8 | [PRD-08](10-prd-08-egress-network-controls.md) | Egress network controls (proxy, CA, headers) | **S** (~1 wk) | — (independent) | Small, surgical, enterprise-unblocking. Deliberately scheduled late because it has no dependents — but it is **parallelizable any time** a self-hosting prospect needs it; treat its slot as float. |
| 9 | [PRD-10](12-prd-10-prompt-persona-packs.md) | Prompt & persona pack management | **M** (2–3 wk) | PRD-06's versioning pattern (reuses it) | First step beyond provider config into *content* config. Reuses the versioning/import-export machinery from PRD-06, so building it after 06 is materially cheaper. |
| 10 | [PRD-09](11-prd-09-mcp-tool-server-management.md) | MCP tool-server management for agents | **L** (4–6 wk, phased M1–M3) | PRD-01 (secretstore auth refs), PRD-02 (console panel), PRD-06 (config audit) | The strategic net-new capability — agents gain external tools. Largest scope, real multi-tenant security surface (server-side tool execution), and it *changes what pdlcflow is*, not just how it's configured. Goes last so it lands on a mature config/console/audit foundation, phased M1 (registry) → M2 (single-persona execution) → M3 (general binding). |

## Waves at a glance

```
Wave 1 — Make what exists real            Wave 2 — Operational maturity        Wave 3 — Expansion
──────────────────────────────            ─────────────────────────────        ──────────────────
PRD-01 BYOK (S)                           PRD-04 Presets+gateways (M)          PRD-07 Cost (M)
  └─▶ PRD-03 Health/Test (S–M)              └─▶ PRD-05 Resilient routing (M–L) PRD-08 Egress (S, float)
        └─▶ PRD-02 Console (M)            PRD-06 Versioning/export (M)         PRD-10 Prompt packs (M)
                                                                               PRD-09 MCP (L, phased)
~4–6 eng-weeks                            ~7–10 eng-weeks                      ~9–12 eng-weeks
```

Total: roughly **20–28 eng-weeks** of single-engineer effort end-to-end; Waves are internally
parallelizable across two engineers (e.g. Wave 1: one on PRD-01→03 backend, one starting PRD-02
UI scaffolding against the existing admin API).

## Release mapping (suggested)

- **v1.11** — Wave 1 (BYOK + health + console). Marketed as "Provider Management" — the
  cc-switch-equivalent core loop.
- **v1.12** — Wave 2 (presets/gateways + failover + versioning). Marketed as "Provider
  resilience & the open provider ecosystem."
- **v1.13+** — Wave 3 items shipped individually; MCP (PRD-09) is its own headline release when
  M2 lands.

## Explicit de-prioritizations

Recorded so they aren't re-litigated: local format-conversion proxy, desktop-shell features
(tray/auto-update/portable), managing third-party CLI config files, and config cloud-sync to
WebDAV/S3 — see "What pdlcflow should NOT copy" in [02-gap-analysis.md](02-gap-analysis.md).
i18n for the web console is real but belongs to a different track than this comparison.

## Revisit triggers

Re-order if any of these occur:
- A design-partner/self-host prospect is blocked on corporate egress → pull PRD-08 forward
  (it's independent).
- Provider incidents visibly break user turns in production → pull PRD-05 ahead of PRD-04.
- Agent tool-use becomes the top competitive gap → start PRD-09 M1 (registry only) in parallel
  with Wave 2; M2+ still wants the mature foundation.
