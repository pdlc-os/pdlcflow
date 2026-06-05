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
- [x] **Engine adapters** — the Inception graph now runs end-to-end through the API:
  - `app/runtime/`: a `GraphRunner` drives the real `meta_graph` (compiled with an injectable checkpointer) across interrupt/resume turns; injectable `GateStore` (records approval gates + question rounds) and `EventBus` (WebSocket fan-out), both with in-memory defaults.
  - `/v1/commands` builds the initial `PDLCState` and starts the graph to its first pause; `GET /v1/approval-gates` lists open interactions (project-scoped); `POST /v1/approval-gates/{id}/resolve` resumes via `Command(resume=…)` (approvals → `{approved,…}`, question rounds → `{answers:[…]}`); the WebSocket replays + streams thread frames.
  - Boot wiring in `main.py` lifespan + the Arq worker (`start_graph` / `resume_graph` delegate to the same runner); LLM completions route through the provider factory only when `wire_llm` is set (dev/test stay on the offline stub).
  - 6 new hermetic engine tests drive the whole command → gate → resume loop (all four gates, in order) with no Postgres/Redis/AWS; engine suite green (14).
- [ ] **Production swaps** (Phase H): default `MemorySaver` → `PostgresSaver` (`use_postgres_checkpointer`, needs `langgraph-checkpoint-postgres`); in-memory gate store → `approval_gates` rows; in-memory bus → Redis Pub/Sub; inline command dispatch → Arq enqueue; S3/Postgres adapters for the artifact/task ports. All are injectable seams today.

Note: the Inception parties are **Progressive Thinking / Threat-Model / Design-Laws** (per upstream `skills/brainstorm/`); the plan's earlier "Wave Kickoff / Design Roundtable" are Construction-phase parties and land in Phase C.

## Phase C — Construction loop (✅ graph engine + REST; real runners pending)

- [x] `pdlc_graph/graphs/build/` — the Construction subgraph (`preflight → build_loop → review_party → review_gate → test_phase → wrap_up`), composed over `PDLCState` and routed from `meta_graph`.
- [x] **TDD enforcement** — `test_runner_port.assert_red_before_green` raises `TDDViolation` if implementation is attempted before a failing test is recorded; the build loop runs red → green → refactor per task.
- [x] **Test-runner port** — injectable, deterministic `SimulatedTestRunner` default (offline, replay-safe); real subprocess runner injected at boot via `set_test_runner`. Drives the 7 layers (unit/integration/contract/e2e/security/perf/ux); required-layer failures pause for accept/fix/defer (auto under night-shift).
- [x] **3-Strike → Strike Panel** — per-task auto-fix capped at 3 attempts; the 3rd convenes the Strike Panel (Neo + Echo + domain agent via the party orchestrator), surfaces 3 ranked approaches, and pauses for the human to pick (counter resets after). Night-shift auto-picks the recommended approach.
- [x] **Construction parties** — Wave Kickoff (per wave ≥2 tasks) + Design Roundtable (per-task triage), via the generic orchestrator.
- [x] **Review** — Party Review (Neo/Echo/Phantom/Jarvis + Muse when a UX review exists) → `render_review` REVIEW.md → the single Construction approval gate (#5, `review_md_approve`); Critical findings flag the gate as blocking so night-shift refuses.
- [x] Reachable through the live API: `POST /v1/commands {command:"build", seed_state:{tasks:[…]}}` drives the Strike Panel + review gate via the resolve endpoint to completion.
- [x] 6 hermetic graph tests (TDD guard, render, happy path, 3-strike resume, required-layer failure, night-shift) + 1 engine REST test; full repo suite green (58 — graph 37, engine 15).
- [ ] **Real integrations** (Phase D / tools pass): subprocess test runner adapter; `gh`/`git` tool implementations; merge-commit-only enforcement lives at the gh layer with the actual merge in Operation/Ship (gate #6).

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
