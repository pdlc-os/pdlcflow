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

## Phase D — Operation loop (✅ graph engine + REST; real deploy/git pending)

- [x] `pdlc_graph/graphs/ship/` — the Operation subgraph (`ship → verify → reflect`), composed over `PDLCState` and routed from `meta_graph` (built by an agent team, integrated solo).
- [x] **Ship** (`merge_and_deploy_approve`, gate #6): semver bump from conventional commits (`versioning.next_version`), CHANGELOG render, deploy-target selection, the gate, then merge (`vcs_port`, **merge-commit-only enforced**) + deploy + DEPLOYMENTS record.
- [x] **Verify** (`smoke_signoff`, gate #7): security checks + smoke tests (via the test-runner port) + conditional UX verify; failed required checks flag the gate blocking so night-shift refuses.
- [x] **Reflect** (`episode_approve`, gate #8): retro + episode render, the gate, metrics rollup, roadmap-claim release, and `operation_complete` (Idle handoff).
- [x] **Three-layer production-deploy ban** (`deploy_port`): filter-at-selection (`select_deploy_targets`), refuse-at-activate (`assert_deploy_allowed`), + the existing Sentinel `prod-deploy-attempted` runtime check. Tier inference is token-boundary-matched.
- [x] Ports wired: `deploy_port` (register + tier + ban), `vcs_port` (merge enforcement), `versioning`; `deploy_tool`/`gh_tool` now delegate to them.
- [x] Reachable through the live API: `POST /v1/commands {command:"ship", seed_state:{…}}` walks all three Operation gates via the resolve endpoint to completion.
- [x] New hermetic tests across ship/verify/reflect (renderers, gate pause/resume, prod-candidate drop, night-shift) + 2 integration + 1 engine REST test; full repo suite green (79 — graph 57, engine 16, event-schema 4, migrate 2).
- [ ] **Real integrations** (Phase H / tools pass): subprocess-backed deploy + actual `git`/`gh` merge; S3/Postgres adapters for the deploy register + artifacts.

## Phase E — Utilities (✅ graph engine + REST)

- [x] `pdlc_graph/graphs/utility/` — all 10 commands as per-command node modules, dispatched by `state["utility_command"]` (built by an agent team, integrated solo). `meta._route` sends any utility command to the subgraph; the commands route sets the flag for the 10 utilities.
- [x] **Lifecycle** (pure): `/pause`, `/resume`, `/abandon`, `/release` — state transitions + roadmap-claim release.
- [x] **Decisions & safety**: `/decide` (appends to the Decision Registry + renders DECISIONS.md), `/doctor` (health-check report + render), `/whatif` (read-only hypothetical — asserted not to mutate state), `/override` (Tier-1 double-RED confirmation via interrupt; human-only, refused under night-shift).
- [x] **Recovery**: `/rollback` (revert record + deploy register), `/hotfix` (compressed build→ship with one confirmation; honors the production-deploy ban).
- [x] Reachable through the live API: `POST /v1/commands {command:"doctor"|"pause"|"override"|…}` — pure utilities complete in one call; interrupting ones (`/override`, `/hotfix`) resume via the resolve endpoint. (Override accepts the engine's `{answers:[…]}` resume shape.)
- [x] 30 utility unit tests + 7 integration + 3 engine REST; full repo suite green (123 — graph 98, engine 19, event-schema 4, migrate 2). ruff clean.

## Phase F — Night Shift (✅ runtime + REST + mission-control panel)

- [x] `pdlc_graph/graphs/night_shift.py` — the full state machine: `preflight → contract_party → activate → build → sentinel → ship → sentinel → completed | aborted | declined`. Wraps the real `build_graph`/`ship_graph` (which already auto-approve every gate under `night_shift_active`) with Sentinel checks between phases.
- [x] **Contract Party** is the one human gate — a raw `interrupt()` (not `gates.approval_gate`, so it never auto-approves); everything downstream runs autonomously.
- [x] **Sentinel** fires on the internal edges via the Phase-A evaluator, reading `ns-progress:`/`ns-abort:` markers synthesized from run state; routes continue / complete / abort.
- [x] **Auto-decision matrix**: every inner gate (the 8) auto-resolves under night-shift — already wired in `gates.approval_gate` (B–D) and exercised here end-to-end.
- [x] **Three-layer prod-deploy ban** holds: Ship pre-filters candidates, the contract/preflight refuses a production target, and the Sentinel aborts on `prod-deploy-attempted`.
- [x] **Mission-control panel** (`NightShiftMissionControl.tsx`) wired into the Studio project view — shows the run lifecycle + outcome (the contract gate renders via the shared modal). The completion summary rides the WS `thread.completed` frame. (Live per-verdict streaming over Redis is Phase H.)
- [x] Reachable via `POST /v1/commands {command:"night-shift", seed_state:{…}}` → contract gate → autonomous build+ship to completion.
- [x] 5 runtime tests (happy path, decline, preflight abort, prod refusal, Sentinel abort) + 2 engine REST; full repo suite green (130 — graph 103, engine 21, event-schema 4, migrate 2). Studio tsc + build clean.

## Phase G — Admin dashboard + analytics pipeline (✅ in-memory analytics + REST + SPA)

- [x] **Telemetry enrichment**: feature-level traceability dimensions — `roadmap_id` (F-NNN), `prd_id`, `user_story_id` (US-001), `plan_step` (plus the existing `application_id`) — now ride on every event (`event_schema` envelope, `PDLCState`, events DB model, emitter). Rollups can pivot down to a roadmap item / PRD / user story / plan step, not just the application.
- [x] **Analytics read store** (`app/analytics`): in-memory, fed by the emitter (a second fan-out alongside the durable sink); `rollup(dimension, …)` over initiative/application/squad/domain/roadmap/user_story/agent with events + tokens + USD, plus `feature_timeline`, `live`, `totals`. ClickHouse/Postgres injected at boot (Phase H).
- [x] **7 admin routes** wired to real rollups: `/admin/{live, initiatives/rollup, domains/rollup, squads/scoreboard, agents/heatmap, features/{roadmap_id}/timeline, exports/rollup.csv}` (+ models). **Cross-org ban** enforced — data routes require `org_id` (missing → 422).
- [x] **Atlas Console SPA**: all 7 pages render the rollups (tables + Recharts bar charts; CSV export link; live feed auto-refresh), org-scoped via the session store.
- [x] **Telemetry correctness fix**: `@instrumented_node` no longer treats langgraph's `GraphInterrupt`/`GraphBubbleUp` (control flow) as an error — previously every gate/question emitted a spurious `error` event. Verified live: a brainstorm run now emits 0 error events.
- [x] Verified live over HTTP: a real run → emitter → analytics → admin routes (events surfaced, 10-persona heatmap, cross-org 422). 16 engine admin tests + 2 instrumentation + 1 envelope traceability test; full repo suite green (149 — graph 105, engine 37, event-schema 5, migrate 2). Studio tsc + build clean.
- [ ] **Production swaps** (Phase H): ClickHouse/Postgres-backed analytics store (the in-memory one is per-process); Firehose→S3→Glue pipeline; the `admin.access.denied` event + audit.

## Phase H — SaaS hardening (☐)

Cognito + SSO; RLS policies in real migrations; rate limiting active; multi-AZ failover; per-tenant KMS CMK; SOC2-grade audit trail; backup + restore drill.

## Phase I — Migration tooling (☐)

Real `scan` / `push` / `taxonomy` / `backfill`; historical event synthesis from upstream episodes + decision logs.

## Studio — live wiring + visual companion (✅ Inception path; full chat WS streaming pending)

- [x] **Visual companion** (`apps/studio/src/components/BrainstormVisualCompanion.tsx`) — rendered as a panel in the **same browser view** as the chat (no separate localhost:7352 server; plan §14.13). Backend rides the existing interrupt payload: `pdlc_graph/visual.py` builds render-agnostic screen specs that flow through `pending.payload.visual` → gate store → WS, with zero new engine endpoints.
- [x] UX Discovery emits clickable **option screens** (choosing a card answers the question); the Plan gate emits the **dependency-tree** screen. Wired via `interaction.ask(visual=…)` and the plan gate payload.
- [x] Studio wired to the live engine: `lib/api.ts` + `lib/ws.ts` match the adapter surface; `useThread` drives command → pending → resolve; `ChatPanel` starts commands; `QuestionCard` + `ApprovalGateModal` render question rounds + gates with the companion alongside; `ProjectView` orchestrates + subscribes to the thread WS channel.
- [x] Verified: `tsc --noEmit` clean, `vite build` succeeds, and the full `/brainstorm` → Socratic rounds → UX Discovery (companion) → gate flow served end-to-end through the Vite dev proxy (the browser's exact path). 4 backend visual tests; full repo suite green (83).
- [ ] Remaining Studio work: live token streaming into the transcript (WS `token` frames), the night-shift mission-control panel, and the admin console data wiring. ESLint v9 flat-config is a pre-existing scaffold gap (CI lint is non-blocking).
