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

## Phase H — SaaS hardening (✅ self-host stack — real adapters behind seams; verified via docker-compose, not in CI)

Delivered incrementally (one PR per bundle). Auth deferred. Every adapter is flag-gated and falls back to the in-memory default, so the hermetic suite + dev stay green; the real paths are verified by `docker compose up` (no Docker/Postgres/Redis in CI).

### Bundle 1 — Durability core (✅)
- [x] **PostgresSaver checkpointer** (`build_checkpointer`): pooled `psycopg` connection (conn-string converted from the SQLAlchemy `+asyncpg` URL), `setup()` on boot, behind `PDLC_USE_POSTGRES_CHECKPOINTER`. Robust fallback to `MemorySaver` if Postgres is unreachable — the engine always boots. Deps added: `langgraph-checkpoint-postgres`, `psycopg[binary]`, `psycopg-pool` (langgraph core stays 0.2.76 — no breaking bump).
- [x] **Arq opt-in dispatch** (`app/runtime/dispatch.py`): `InlineDispatcher` (default — synchronous, unchanged REST contract) vs `ArqDispatcher` (enqueues `start_graph`/`resume_graph` for the worker, which shares Postgres state; pending arrives over the bus). Behind `PDLC_USE_ARQ_DISPATCH`. Command + resolve routes now go through the dispatcher.
- [x] 4 durability unit tests (conn-string conversion, MemorySaver fallback, dispatcher selection); full repo suite green (153 — engine 44). `.env.example` documents the flags.
- [ ] Cross-process pending delivery for the Arq path needs the Redis bus (bundle 2).

### Bundle 2 — Live streaming (Redis pub/sub bus) (✅)
- [x] **RedisEventBus** (`app/runtime/redis_bus.py`): `publish` (sync) appends to a capped per-channel Redis list (reconnect replay) + PUBLISHes the frame; `listen` (async, used by the WS) replays the bounded list then subscribes to pub/sub — so a frame published by the Arq worker reaches a socket held open by the API. Behind `PDLC_USE_REDIS_BUS`; in-memory bus stays the default.
- [x] **EventBus unified `listen()`**: both buses expose an async `listen(channel)` iterator (in-memory polls history; Redis replays + subscribes). The WS handler is now transport-agnostic (`async for frame in bus.listen(...)`) with a concurrent client-drain task.
- [x] **Live night-shift verdicts**: a new `instrumentation.emit_event` lets the Sentinel nodes emit the real verdict value; the emitter fans `night_shift.*` events out to `thread:{id}` (skipping node-enter noise). The mission-control panel renders the live verdict stream (build/ship stages, abort highlighted); `useThread.verdicts` + `ws.ts` `NightShiftFrame` + ProjectView wired.
- [x] Hermetic test (`test_night_shift_stream`): a `/night-shift` run fans build+ship verdicts + completion to the thread channel, and a late-attaching WS replays them. Studio tsc + build clean; full repo suite green (175 — engine 45).
- [ ] Redis transport verified via docker-compose (no Redis in CI).
### Bundle 3 — Persistence (✅)
- [x] **Artifact stores** (`app/persistence/artifacts.py`): `FilesystemArtifactStore` (self-host volume, fully tested) + `S3ArtifactStore` (boto3, MinIO endpoint-compatible, lazy client). Behind `PDLC_ARTIFACT_STORE=memory|filesystem|s3`; injected into the pdlc_graph artifact port at boot.
- [x] **Postgres task store** (`app/persistence/tasks.py`): durable Beads replacement over the `tasks` table (sync SQLAlchemy). Preserves a supplied `external_id` (migration) else mints `bd-N`; `claim` is an atomic UPDATE guarded by the unique partial index on (project_id, branch). Behind `PDLC_TASK_STORE`.
- [x] **Port threading**: `TaskStore.create` now takes `org_id` (tenant-correct for RLS in bundle 4); `add_dependency`/`claim` are project-scoped + a `depends_on` array column on the model. In-memory store + the Plan sub-phase updated; graph suite green.
- [x] **Postgres analytics** (`app/analytics/postgres_store.py`): the rollup/timeline/live/totals interface answered from SQL over `events` (token/USD from payload jsonb), org-scoped. `PostgresSink` now actually inserts event rows (incl. the Phase G traceability columns). Behind `PDLC_ANALYTICS_BACKEND`.
- [x] **db/session.py** (cached sync psycopg engine); `wire_persistence` injects all three with in-memory fallback so boot never crashes; wired in lifespan + worker. Compose gains **MinIO** + an `artifacts` volume; `.env.example` documents the flags.
- [x] 4 persistence tests + 4 task-store tests (filesystem round-trip, wiring injection, postgres-flags-don't-crash-boot, S3 uri parsing; org_id/external_id/atomic-claim). Full repo suite green (183 — graph 109, engine 49). ruff clean.
- [ ] Postgres/S3/MinIO paths verified via docker-compose (not in CI).
### Bundle 4 — Migrations + RLS (✅)
- [x] **Real schema migration**: `0001_init` now builds the full 25-table schema from the SQLAlchemy models (`Base.metadata.create_all` + the `pgcrypto`/`citext` extensions); `env.py` already sets `target_metadata`. Runs via `alembic upgrade head` in compose. (`alembic revision --autogenerate` against a live DB can later refine indexes.)
- [x] **RLS policies**: `0002_rls` enables row-level security + an `org_id = current_setting('app.org_id')` isolation policy on every org-scoped table. `db.rls.set_org_context` (sync) binds `app.org_id` per transaction; applied on the Postgres task-store write + all analytics queries.
- [x] **admin.access.denied**: added to the taxonomy (**38 events**; registry + envelope updated). Admin data routes now take an optional `org_id`, emit the audit event, and return **403** when it's missing (was 422) — the cross-org ban with an audit trail.
- [x] 5 migration/RLS/guard tests (metadata tables, `depends_on` column, `SET LOCAL` SQL, 403 guard, valid audit event) + the admin 422→403 update. App boots; `GET /v1/admin/live` without org → 403. Full repo suite green (188 — engine 54, graph 109, event-schema 5, migrate 20). ruff clean.
- [ ] **Enforcement hardening** (documented follow-on): RLS is ENABLED but not FORCEd (the app connects as table owner, so non-forced RLS is bypassed). Full enforcement needs a dedicated non-owner DB role + `force row level security` + threading `org_id` through the project-scoped read methods (`list`/`claim`).

### Integration CI (✅ exercises the real paths)
- [x] A blocking **`integration`** job in `.github/workflows/ci.yml`: Postgres + Redis service containers + a MinIO step, `alembic upgrade head`, then `pytest -m integration`. 6 integration tests validate what the hermetic suite can't — Postgres checkpointer durability across runner instances, the Postgres task store (external_id + atomic branch-claim via the unique partial index), Postgres analytics rollups over real events, the Redis bus publish/replay/subscribe, and the S3/MinIO artifact round-trip. Tests are `@pytest.mark.integration`, skipped locally unless `PDLC_RUN_INTEGRATION=1` (so the hermetic suite stays infra-free).

**Phase H summary:** all four bundles landed (durability, live streaming, persistence, migrations+RLS) as real, flag-gated adapters with in-memory fallback — the hermetic suite + dev stay green; the Postgres/Redis/S3/MinIO paths are exercised via `docker compose up`. Auth enforcement remains deferred (open API). The architecture is now production-shaped for self-host; remaining SaaS-only items (Cognito/SSO, per-tenant KMS, ClickHouse, multi-AZ, RLS FORCE) are scaffolded/documented.

## Phase I — Migration tooling (✅ scan/push/taxonomy/backfill + engine import)

- [x] **scan** — parses an upstream `docs/pdlc/memory/` project: memory files, decisions (DECISIONS.md), tasks (`.beads/tasks.json`, `bd-NN` preserved), deployments (DEPLOYMENTS.md), phase history (STATE.md), roadmap (F-NNN). Existing `Manifest`/`.summary` contract kept.
- [x] **backfill** — synthesizes deterministic, idempotent `synthetic:true` events from the phase history + decision log (uuid5 ids from content); every event has a valid `event_type` and the feature's `roadmap_id`.
- [x] **taxonomy** — pure `assign_taxonomy_core` (initiative/application/domains, derives domains from `domain:*` labels) + an interactive Typer wrapper.
- [x] **push** — `build_import_payload` (pure) + `push_payload` (httpx; injectable ASGI transport for hermetic tests) → the new engine endpoint.
- [x] **engine `POST /v1/migrate/import`** — ingests events → analytics store (dedup on `event_id` ⇒ idempotent re-import) and memory bodies → artifact store; returns per-kind counts.
- [x] Verified live: `scan → push (9 memory/4 tasks/2 decisions/1 deploy) → backfill (8 events) → re-push (0 new, idempotent) → /v1/admin/live` shows the imported history. **Backfill makes Atlas Console non-empty on day one** (plan §12), via the live feed + roadmap/domain drill-downs.
- [x] 18 new migrate tests + 3 engine import tests; full repo suite green (170 — graph 105, engine 40, event-schema 5, migrate 20). ruff clean.
- [ ] **Entity resolution** (Phase H): `initiative`/`application` rollups need taxonomy names resolved to entity UUIDs (the events carry string `roadmap_id`/`domains`, which work today; `initiative_id`/`application_id` are UUID dimensions). Real S3/Postgres targets for the import.

## Studio — live wiring + visual companion (✅ Inception path; full chat WS streaming pending)

## Studio — live wiring + visual companion (✅ Inception path; full chat WS streaming pending)

- [x] **Visual companion** (`apps/studio/src/components/BrainstormVisualCompanion.tsx`) — rendered as a panel in the **same browser view** as the chat (no separate localhost:7352 server; plan §14.13). Backend rides the existing interrupt payload: `pdlc_graph/visual.py` builds render-agnostic screen specs that flow through `pending.payload.visual` → gate store → WS, with zero new engine endpoints.
- [x] UX Discovery emits clickable **option screens** (choosing a card answers the question); the Plan gate emits the **dependency-tree** screen. Wired via `interaction.ask(visual=…)` and the plan gate payload.
- [x] Studio wired to the live engine: `lib/api.ts` + `lib/ws.ts` match the adapter surface; `useThread` drives command → pending → resolve; `ChatPanel` starts commands; `QuestionCard` + `ApprovalGateModal` render question rounds + gates with the companion alongside; `ProjectView` orchestrates + subscribes to the thread WS channel.
- [x] Verified: `tsc --noEmit` clean, `vite build` succeeds, and the full `/brainstorm` → Socratic rounds → UX Discovery (companion) → gate flow served end-to-end through the Vite dev proxy (the browser's exact path). 4 backend visual tests; full repo suite green (83).
- [x] **Live token streaming** (post-v1): `PDLC_STREAM_TOKENS` publishes `token` frames (start/chunk/done) from `llm_port.complete()` to the thread channel; the Studio renders a transient `StreamingPreview` ("…is drafting") that clears on the next gate/result. Works with the stub (chunked) + real models (`model.stream()`). Off by default.
- [ ] Remaining Studio work: ESLint v9 flat-config is a pre-existing scaffold gap (CI lint is non-blocking).

## Phase J — Eval framework (✅ starter harness; measure-only by default)

- [x] **Eval engine** (`packages/pdlc-graph/pdlc_graph/evals/`): a registry of named evals, a runner that fires the evals registered for a trigger, an `EvalContext`/`EvalResult` model, and a **judge seam** (`judge_port`) mirroring `llm_port` — a deterministic stub judge for hermetic CI, with a factory-backed **LLM-as-judge** injected at boot (`PDLC_JUDGE_TIER`, needs `PDLC_WIRE_LLM`).
- [x] **6 categories covered**: per-agent output scoring (`agent_output_quality`, role rubrics), groundedness/faithfulness/hallucination (`groundedness`), citation + faithful-relay enforcement (`citation`, `faithful_relay`), drift/regression (`drift` + golden set), LLM-as-judge/rubric scoring (judge seam + `rubrics.py`), and eval CI (hermetic `evals` job).
- [x] **Wired at major steps**: `instrumentation.evaluate(...)` called from Define (PRD), Design (design docs), Construction review, and Reflect (episode); strict **no-op unless `PDLC_RUN_EVALS=true`** so the 188 prior tests are untouched.
- [x] **Telemetry + surface**: `eval.scored` / `eval.blocked` events (taxonomy → **40**); analytics `eval_summary` (in-memory + Postgres) + `GET /v1/admin/evals/summary` (avg score + pass rate, by eval & by agent; org-scoped, 403 on cross-org).
- [x] **Enforcement posture**: measure-only by default; **opt-in blocking** per eval via `PDLC_EVAL_BLOCKING` (emits `eval.blocked` + `blocking_failures()` helper; hard gate-halt is a documented one-line opt-in).
- [x] **Two recommended evals added**: `spec_adherence` (LLM-judge — does the design/plan satisfy every PRD requirement?, wired at Design with the PRD as a source) and `prod_safety` (deterministic — deploy never targets production under night-shift, wired at Ship). **7 evals total.**
- [x] **Nightly real-LLM run + drift tracking**: a golden suite (`evals/golden/suite.json`) + committed baseline; `scripts/run_eval_suite.py` scores it and fails on regression vs baseline; `.github/workflows/evals-nightly.yml` runs daily — a hermetic `drift` job (stub, regression-gated) + a `real` job (real LLM-as-judge, report-only, gated on `RUN_REAL_EVALS` var + provider secrets). A hermetic `test_golden_suite_has_no_drift_vs_baseline` keeps the baseline honest in CI.
- [x] 15 eval tests (12 graph + 3 engine), `@pytest.mark.eval`; full repo suite green (**203**); ruff clean. CI gains a hermetic `evals` job (`pytest -m eval`) + the nightly workflow.
- [x] Docs: [`docs/wiki/17-evals.md`](docs/wiki/17-evals.md) — framework, enabled evals, golden-suite/drift + nightly, recommended-evals roadmap, and how to add new evals.
- [ ] Follow-ons (documented): activate the real-LLM nightly (set `RUN_REAL_EVALS` + secrets); semantic (embedding) drift; durable score-over-time store + charts; promote groundedness/spec_adherence/prod_safety to blocking after baselining; the remaining recommended evals in the wiki.

## Phase 1 auth enforcement (✅ flag-gated; org from token)

- [x] **Enforcement** behind `PDLC_AUTH_REQUIRED` (default off → open API, all prior tests/Studio unaffected). When on: `/v1/commands`, `/v1/approval-gates`, `/v1/admin/*`, `/v1/migrate/import` + the thread WebSocket require a Bearer JWT (WS via `?token=`); **org_id is derived from the token** (mismatch → 403); admin/analytics routes require the admin/owner role.
- [x] **Login + accounts**: `POST /v1/auth/login` (issues JWT), `GET /v1/auth/me`, admin-only `POST /v1/auth/users`. Env-bootstrapped first admin (`PDLC_BOOTSTRAP_ADMIN_EMAIL/PASSWORD`). User store port: in-memory (dev/test) + Postgres (`users`/`org_members`, +`password_hash` column). bcrypt hashing (dropped passlib — broke on bcrypt 4.x).
- [x] **Guard**: `get_principal` (flag-aware) + `resolve_org` (cross-org ban + role) unify the auth-on/auth-off paths so the prior cross-org-ban behavior is identical when off. ruff `flake8-bugbear` allowlist added for the FastAPI `Depends`/`Query` idiom.
- [x] 9 auth tests (password roundtrip, auth-off open, login→token→authed call, bad creds 401, cross-org 403, admin role 401/403, /me, bootstrap). Full repo suite green (**217**); ruff clean; bootstrap→login→/me verified end-to-end.
- [ ] Next: Phase 2 (Studio login flow) and Phase 3 (RLS FORCE: non-owner DB role + thread org through the remaining reads + integration tests). Cognito/OIDC scaffolded.

## Phase 2 — Studio login (✅ end-to-end auth in the browser)

- [x] **Login overlay** (`components/LoginView.tsx`): email/password → `POST /v1/auth/login`; JWT + identity persisted to `localStorage` (`lib/token.ts`).
- [x] **Token transport**: `lib/api.ts` attaches `Authorization: Bearer` on every REST call + surfaces the overlay on `401`; `lib/ws.ts` appends `?token=` to the thread WebSocket.
- [x] **Org from token**: `store/useAuth.ts` binds `useThread.orgId` to the signed-in identity's org (so requests match the principal); restored from `localStorage` on load.
- [x] **Shell**: header shows the user + Sign out, or a Sign in button (proactive); a 401 re-opens login. **Auth off (default) → no token sent, Studio unchanged.**
- [x] Studio `tsc` + `vite build` clean. With this, `PDLC_AUTH_REQUIRED=true` works end-to-end in the browser.
- [ ] Next: Phase 3 (RLS FORCE — non-owner DB role + org threaded through the remaining reads + integration tests). Cognito/OIDC SSO login is a later add.

## Phase 3 — RLS FORCE (✅ DB-enforced tenant isolation, verified vs real Postgres)

- [x] **Non-superuser app role**: the app connects as `pdlc_app` (`PDLC_DB_URL`) so RLS applies (superusers bypass it); migrations run as the owner (`PDLC_MIGRATION_DB_URL`, used by `env.py`). Compose `postgres-init/01-app-role.sql` creates the role + `ALTER DEFAULT PRIVILEGES` so owner-created tables auto-grant it DML.
- [x] **`0003_rls_force`**: `FORCE ROW LEVEL SECURITY` on the tenant-content tables (squads/initiatives/applications/domains/projects/tasks/memory_files/approval_gates/*_llm_config/events); **org_members dropped from RLS** (login resolves org-by-email pre-context; documented `SECURITY DEFINER` follow-on).
- [x] **org threaded through every query path**: `TaskStore.add_dependency/list/claim` now take `org_id` (+ in-memory store, `plan.py`, tests); `PostgresTaskStore` + `PostgresAnalyticsStore` + `PostgresSink` (grouped by org) call `set_org_context` per transaction.
- [x] **Verified against real Postgres** (docker): migrations 0001→0002→0003 apply; `test_rls_force_blocks_cross_org_as_non_owner_role` proves that, as `pdlc_app`, cross-org reads return **zero rows** and cross-org inserts are **rejected**. 5 Postgres integration tests pass live; full hermetic suite green (**217**); ruff clean. `greenlet` added (async-SQLAlchemy/alembic).
- [ ] Follow-ons: `SECURITY DEFINER` auth-lookup so org_members can also be RLS-locked; rotate the `pdlc_app` dev password; Cognito/OIDC SSO.

**Auth + RLS arc complete (Phases 1–3):** app-layer auth derives org from the JWT, the Studio logs in, and Postgres independently enforces the same org boundary — defense in depth. All flag-gated; default-off keeps dev/CI hermetic.

## Phase 3.1 — RLS-lock org_members via SECURITY DEFINER login (✅ verified vs real Postgres)

- [x] **`0004_auth_lookup`**: a narrow `SECURITY DEFINER` `auth_lookup(email)` (owned by the superuser → bypasses RLS for the pre-context login lookup; `EXECUTE` granted only to `pdlc_app`, revoked from PUBLIC), then **org_members re-ENABLED + FORCEd** with its policy. Closes the one gap left by 0003.
- [x] **`PostgresUserStore`**: `get_by_email` now calls `auth_lookup(...)` (so login works under the lock); `create_user` sets `app.org_id` before the org_members insert (WITH CHECK).
- [x] **Verified live** (docker): `test_org_members_rls_locked_but_login_works_via_definer` — as `pdlc_app`, `auth_lookup` resolves a user's org with no context, but a direct `org_members` read is org-scoped (own org sees its member; other org invisible; no-context sees nothing). `test_postgres_user_store_create_and_login_roundtrip` exercises the adapter end-to-end. Full hermetic suite green (217); ruff clean.
- [ ] Follow-ons: rotate the `pdlc_app` dev password; Cognito/OIDC SSO. The DB-level tenant-isolation guarantee now covers **every** org-scoped table (no caveats).

## Distribution — deploy from published images (✅ no clone required)

- [x] **`release-images` workflow**: on a version tag (or manual dispatch), builds + pushes multi-arch (`amd64`+`arm64`) `ghcr.io/pdlc-os/pdlcflow-api` and `pdlcflow-studio` images to GHCR (semver + `latest`).
- [x] **`deploy/`**: a standalone `docker-compose.yml` (image refs, no `build:`), an interactive **`setup.sh`** (prompts for the few real choices, generates secrets, writes `.env` — with the pdlcflow/PDLC banner), `.env.example` for manual config, the env-driven `postgres-init/01-app-role.sh`, and a README. Users `curl` 3 files → `setup.sh` → `docker compose up` → migrate.
- [x] **Verified end-to-end with real Docker**: fresh-built images boot the full standalone stack — env-driven `pdlc_app` role created (non-super), migrations 0001→0004 apply as owner, app runs as `pdlc_app` under RLS (`POST /v1/commands` → 200), `/health` ok, Studio 200, admin cross-org → 403.
- [x] Postgres role-init converted to an **env-driven shell script** (`PDLC_APP_DB_PASSWORD`) in both compose setups — no committed-file editing. Root README + wiki updated.

## Artifact tenant isolation (✅ org-namespaced + sanitized)

- [x] Artifacts (PRD/design/review/episode/…) are now namespaced **`{org_id}/{project_id}/{path}`** (filesystem dir + S3 key). The **org is set per turn by the runner** from the thread id (authoritative = the JWT-bound org when auth is on) via a `set_current_org` context — NOT from the node call — so a forged `project_id` can't cross tenants. `put_artifact(project_id, path, content)` signature unchanged (org injected from context) → zero node-call churn.
- [x] `project_id`/`path` sanitized (reject `..`/absolute), filesystem `get`/`put` pinned under the base dir (crafted `file://` uri can't escape); S3 keys org-prefixed; migrate route binds the org too.
- [x] Tests: graph `test_artifact_isolation` (context-org, default, traversal/`project_id` rejection) + engine `test_persistence` (tenant separation, traversal block, **end-to-end** `/doctor` command writes only under `{base}/{org}/{project}/`). Full hermetic suite green (**223**); ruff clean.
- [ ] Deeper layer (documented): projects-table `project↔org` ownership check; per-tenant KMS for S3 (SaaS).

## LLM tiers — generic names + real per-tenant/per-agent overrides (✅ verified vs Postgres)

- [x] **Provider-neutral tier names**: renamed opus/sonnet/haiku → **premium / balanced / economy** everywhere (persona frontmatter `tier:`, loader, `tier_map`, factory `Tier`, judge tier, stub, docs). Anthropic-family providers still resolve to Opus/Sonnet/Haiku; OpenAI/Gemini/etc. auto-map highest/general/economy.
- [x] **Overrides wired for real** (were Phase-A stubs): the factory now reads `org_llm_config` (per-tenant provider + tier_map) and `agent_llm_config` (per-agent exact model_id) with RLS context; the completion backend resolves the tenant from the turn context (`current_org()`); the Atlas Console **Models API** (`/v1/admin/models/*`) persists + reads them.
- [x] **Verified on real Postgres** (docker): `test_llm_overrides_resolve_from_db` (factory reads org + agent overrides) + `test_admin_models_route_persists_and_reads` (HTTP round-trip). Hermetic suite green (230); ruff clean.
- [x] Documented in the configuration wiki with resolution order, the admin API table + curl examples, the DB tables, and **source-file paths/links** (`app/llm/tier_map.py`, `app/llm/factory.py`, `app/routes/admin/models.py`, `app/db/models.py`).
