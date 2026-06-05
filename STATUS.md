# Status

Phase tracker for the migration roadmap defined in
[`docs/.research/.langgraph-bedrock-saas-migration-2026-06-05.md`](./docs/.research/.langgraph-bedrock-saas-migration-2026-06-05.md) §13.

## Phase A — Foundations (✅ this scaffold)

- [x] Monorepo workspace (pnpm + uv)
- [x] `packages/event-schema` — Pydantic envelope, 37 typed payloads, registry doc, round-trip tests, PII guard
- [x] `packages/pdlc-graph` — `PDLCState` TypedDict (12-section STATE.md mirror + taxonomy keys), meta-graph router, 6 phase-subgraph stubs, party-meeting orchestrator pattern, deterministic Sentinel evaluator, 10 verbatim persona soul-specs, tool stubs
- [x] `services/pdlc-engine` — FastAPI app, JWT auth (Cognito stub), `/v1/commands` + `/v1/approval-gates` + `/v1/admin/{live,initiatives,domains,squads,agents,features,exports,models}`, WebSocket handler, ClickstreamEmitter + JSONL/Postgres/Firehose sinks, LangChain token-tally callback, 7-provider LLM factory with two-level resolution, tier map, Redis rate-limit, Arq worker settings, SQLAlchemy 2.0 models (25 tables), Alembic init
- [x] `apps/studio` — React + Vite + Tailwind + shadcn/ui + Chainlit-inspired tokens (CSS custom properties, light/dark with system-preference detection), Studio + Atlas Console in one bundle, 12 stub components (`<ChatPanel>`, `<StepCard>`, `<SideDrawer>`, `<SettingsDrawer>`, `<StatusLine>`, `<ThemeToggle>`, `<PartyMeetingVisualizer>`, `<ApprovalGateModal>`, `<MemoryFileViewer>`, `<NightShiftMissionControl>`, `<RoadmapBoard>`, `<SketchSocraticToggle>`), 8 Atlas Console routes (Live, Initiatives, Domains, Squads, Agents, Features time-travel, Exports, Models), Zustand stores, WS client with auto-reconnect, typed API client
- [x] `infra/compose` — `docker-compose.yml` with api / worker / postgres / redis / studio + optional Caddy reverse proxy with auto-TLS, `.env.example` covering all 7 LLM providers
- [x] `infra/cdk` — AWS CDK app with 8 stacks (network, data, compute, edge, auth, events, bedrock, observability)
- [x] `tools/pdlc-migrate` — Typer CLI with `scan` / `push` / `taxonomy` / `backfill` subcommands and a `Manifest` data model
- [x] Architecture proposal in `docs/.research/.langgraph-bedrock-saas-migration-2026-06-05.md` (15 sections, 5 mermaid diagrams, files-list table, critical-files appendix)

## Phase B — Inception loop (✅ graph engine; engine adapters pending)

- [x] `pdlc_graph` foundation: injectable **LLM port** (deterministic offline stub; engine injects the factory-backed backend at boot), **artifact store** + **task store** ports (in-memory defaults; S3 / Postgres injected at boot), `interaction.ask` (Sketch/Socratic via `interrupt()`), `gates.approval_gate` (8 gates + night-shift auto-decision), MOM renderer, and a real **party orchestrator** (`Send` fan-out → persona pitches → consensus → MOM, with `triage_level` skip/lite/full).
- [x] **Discover** subgraph (steps 0–6): divergent ideation, 3 Socratic rounds, **Progressive Thinking** party (always), adversarial review, edge-case analysis, conditional **UX Discovery**, synthesis → `discover_summary` gate.
- [x] **Define** subgraph (steps 7–8): PRD drafted via the LLM port + assembled by the pure `render_prd`, persisted via the artifact port → `prd_approve` gate.
- [x] **Design** subgraph (steps 9–12): Bloom's Taxonomy questioning (3 rounds), ARCHITECTURE / data-model / api-contracts renderers, **Threat-Model** + **Design-Laws** parties (triage-gated), → `design_docs_approve` gate.
- [x] **Plan** subgraph (steps 13–19): deterministic task decomposition → task store (`bd-NN` ids) → dependency graph → Mermaid wave tree → `render_plan` → `beads_tasklist_approve` gate → Construction handoff.
- [x] `brainstorm_graph` composes the four sub-phases; `interrupt()` propagates through the nested subgraphs; the 4 gates resume via `Command(resume=…)`. Night-shift drives the whole chain to completion with no human turns.
- [x] 21 new hermetic tests (no network/DB/AWS); full `pdlc-graph` suite green (31), ruff clean.
- [ ] **Engine adapters** (overlaps Phase H): wire `/v1/commands` → Arq `start_graph`, persist `approval_gates` rows + WS push, resolve endpoint → `Command(resume=…)`, and inject the factory/S3/Postgres backends at boot. The graph layer is ready for these; today they are still Phase A stubs.

Note: the Inception parties are **Progressive Thinking / Threat-Model / Design-Laws** (per upstream `skills/brainstorm/`); the plan's earlier "Wave Kickoff / Design Roundtable" are Construction-phase parties and land in Phase C.

## Phase C — Construction loop (☐)

TDD enforcement (engine refuses code edits without a failing test first); real test runner integration across the 7 layers; 3-Strike escalation; Strike Panel party meeting; merge-commit-only enforcement at the gh tool layer.

## Phase D — Operation loop (☐)

Real ship subgraph; smoke runner; deploy register integration; reflect / episode generation; metrics rollup write-back.

## Phase E — Utilities (☐)

`/decide`, `/whatif`, `/doctor`, `/rollback`, `/hotfix`, `/abandon`, `/release`, `/override`, `/pause`, `/resume` — all wired to the utility subgraph.

## Phase F — Night Shift (☐)

Full night-shift state machine (preflight → contract_party → activate → loop → complete | abort); auto-decision matrix per gate; three-layer prod-deploy ban end-to-end; mission control UI subscribed to Redis verdicts.

## Phase G — Admin dashboard + analytics pipeline (☐)

All 7 admin routes with live data; ClickHouse provisioning + rollup queries; cost-pivot by provider × agent × initiative × domain; CSV / DDL export; cross-org analytics ban enforced at the engine.

## Phase H — SaaS hardening (☐)

Cognito + SSO; RLS policies in real migrations; rate limiting active; multi-AZ failover; per-tenant KMS CMK; SOC2-grade audit trail; backup + restore drill.

## Phase I — Migration tooling (☐)

Real `scan` / `push` / `taxonomy` / `backfill`; historical event synthesis from upstream episodes + decision logs.
