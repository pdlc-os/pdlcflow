# cc-switch → pdlcflow gap study (2026-07-05)

Functional comparison of [cc-switch](https://github.com/farion1231/cc-switch) against pdlcflow,
gap identification, per-gap PRDs/designs, and a build-sequence roadmap. Tech stacks are
deliberately out of scope — this is a *capability* comparison.

Reading order:

1. [00-cc-switch-capability-inventory.md](00-cc-switch-capability-inventory.md) — what cc-switch does
2. [01-pdlcflow-current-state.md](01-pdlcflow-current-state.md) — what pdlcflow has today (code-audited)
3. [02-gap-analysis.md](02-gap-analysis.md) — capability-by-capability disposition (the synthesis)
4. PRDs 03–12 — one assessment-grade PRD + design per applicable gap:
   - [PRD-01 BYOK completion](03-prd-01-byok-completion.md)
   - [PRD-02 Provider Settings Console](04-prd-02-provider-settings-console.md)
   - [PRD-03 Provider health & connectivity testing](05-prd-03-provider-health-connectivity.md)
   - [PRD-04 Provider preset catalog & OpenAI-compatible gateways](06-prd-04-provider-preset-catalog.md)
   - [PRD-05 Resilient LLM routing](07-prd-05-resilient-llm-routing.md)
   - [PRD-06 Config versioning, backup & import/export](08-prd-06-config-versioning-import-export.md)
   - [PRD-07 Cost analytics enhancements](09-prd-07-cost-analytics-enhancements.md)
   - [PRD-08 Egress network controls](10-prd-08-egress-network-controls.md)
   - [PRD-09 MCP tool-server management](11-prd-09-mcp-tool-server-management.md)
   - [PRD-10 Prompt & persona packs](12-prd-10-prompt-persona-packs.md)
5. [99-roadmap.md](99-roadmap.md) — prioritization & sequencing (3 waves, release mapping)

Status: all PRDs are **Draft — for assessment**; none are commitments to build.
