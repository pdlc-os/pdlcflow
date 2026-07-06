<!-- nav:top -->
[🏠 Onboarding](README.md) · [📚 Full Wiki](../wiki/README.md) · [🗺️ Visual journey](journey.html)

# 3 · Going deeper

Onboarding gets you productive. The **[20-page wiki](../wiki/README.md)** makes
you fluent. Rather than read it front-to-back, take it in three tiers — read a
tier, go use pdlcflow for a while, come back for the next.

## Tier 1 — Get it running & grasp the shape

Read these first. After them you can install, configure, launch, and drive the
Studio, and you understand the core loop.

| Page | Why |
|---|---|
| [01 · Overview & Architecture](../wiki/01-overview.md) | What pdlcflow is and how the engine / Studio / Nexus / LLM pieces fit. |
| [02 · Installation](../wiki/02-installation.md) | Prerequisites, Docker Compose, migrations, MinIO. |
| [03 · Configuration & Backends](../wiki/03-configuration.md) | Every env flag; in-memory vs Postgres/Redis/S3; self-host vs SaaS; auth (local vs OIDC/SSO). |
| [04 · Launching & Health](../wiki/04-launching.md) | Bringing the stack up, dev mode, health/readiness checks. |
| [05 · Core PDLC Flow](../wiki/05-core-flow.md) | **The keystone** — the 4 phases, the 9 approval gates in order, meta-graph routing. |
| [13 · Using the Studio](../wiki/13-studio.md) | The browser UI: chat, gates, the visual companion, mission control. |

## Tier 2 — Use the methodology day-to-day

Read these once you're running features. They explain what happens *inside* each
phase and the specialized flows.

| Page | Why |
|---|---|
| [06 · The Agents (Personas)](../wiki/06-agents.md) | The 10 personas, their roles, model tiers, and auto-selection by task labels. |
| [07 · Party Mode](../wiki/07-party-mode.md) | Multi-persona "party" meetings, triage, and the minutes-of-meeting output. |
| [08 · Inception](../wiki/08-inception.md) | Discover → Define → Design → Plan; Socratic vs Sketch interaction; the visual companion. |
| [09 · Construction](../wiki/09-construction.md) | The TDD build loop, the 3-Strike → Strike Panel escalation, the 7 test layers. |
| [10 · Operation](../wiki/10-operation.md) | Ship → Verify → Reflect; semver; deploy; the 3-layer production-deploy ban. |
| [11 · Night-Shift](../wiki/11-night-shift.md) | The autonomous Build→Ship runtime, the Contract Party gate, the Sentinel, mission control. |
| [12 · Utility Commands](../wiki/12-utilities.md) | `/decide /doctor /whatif /pause /resume /abandon /release /override /rollback /hotfix /compact`. |
| [15 · Migrating an upstream project](../wiki/15-migration.md) | The `scan / push / taxonomy / backfill` import pipeline (brownfield). |

## Tier 3 — Extend, operate & integrate

Reference-grade. Reach for these when you're integrating, operating at scale, or
extending the platform.

| Page | Why |
|---|---|
| [14 · Monitoring & Analytics](../wiki/14-monitoring.md) | Telemetry, the Nexus Console rollups, the cross-org ban. |
| [16 · API & WebSocket Reference](../wiki/16-api-reference.md) | Every REST endpoint + the thread WebSocket (for scripting / integration). |
| [17 · Evals Framework](../wiki/17-evals.md) | Per-agent scoring, groundedness/hallucination, drift, LLM-as-judge, eval CI. |
| [18 · Data Model & Hierarchy](../wiki/18-data-model.md) | Org · Domain · Squad · Repo · Initiative · Program · Project · Conversation — and row-level security. |
| [19 · Observability](../wiki/19-observability.md) | OpenTelemetry traces + metrics; the Collector/Tempo/Prometheus stack; Grafana + the Streamlit Nexus dashboard. |
| [20 · MCP Tool Servers](../wiki/20-mcp-tools.md) | Give agents external tools: the org-scoped MCP registry, allowlists, persona/phase bindings, the security model. |

## Suggested reading orders

- **"I just want to build features":** Tier 1 → [08 Inception](../wiki/08-inception.md) → [09 Construction](../wiki/09-construction.md) → [10 Operation](../wiki/10-operation.md). Done.
- **"I'm the platform operator":** Tier 1 → [03 Configuration](../wiki/03-configuration.md) (deep) → [18 Data Model](../wiki/18-data-model.md) → [14 Monitoring](../wiki/14-monitoring.md) → [19 Observability](../wiki/19-observability.md).
- **"I'm integrating pdlcflow with our tools":** [16 API Reference](../wiki/16-api-reference.md) → [20 MCP Tools](../wiki/20-mcp-tools.md) → [15 Migration](../wiki/15-migration.md).
- **"I want the autonomous loop":** [05 Core Flow](../wiki/05-core-flow.md) → [11 Night-Shift](../wiki/11-night-shift.md) → [17 Evals](../wiki/17-evals.md).

---
<!-- nav:bottom -->
◀ [2a · Setup walkthrough](2a-setup-walkthrough.md) · **Next → [4 · Bringing your own spec](4-bringing-your-own-spec.md)** · [📚 Full Wiki](../wiki/README.md)
