# Stub-Implementation Roadmap — deep-scan findings

> **Date:** 2026-07-06 · **Scope:** full repo (engine, graph package, event-schema, studio,
> pdlc-migrate, nexus-dashboard, infra, CI) as of `main` @ v1.13.0 (post cc-switch roadmap).
> **Method:** three parallel deep scans (engine / graph+schema / frontend+tools+infra), every
> injectable port cross-checked against the engine's actual boot wiring
> (`services/pdlc-engine/app/main.py` lifespan), and the six highest-impact claims
> re-verified by hand before this document was written.
>
> **What is NOT in this list:** the hermetic injectable defaults that are *by design* —
> the offline LLM stub, null tracer, null tool backend, in-memory artifact/task/gate/bus
> stores, deterministic eval judge. Those all have real adapters that wire in behind flags.
> This list contains only components where the **real implementation was never built**, code
> that **pretends to succeed**, dead code, and enforced-nowhere contracts.

## Summary table

| # | Item | Area | Severity | Effort |
|---|------|------|----------|--------|
| ~~T1-1~~ ✅ | Real test runner (SubprocessTestRunner, self-host gated) — **done** | pdlc-graph + engine | 🔴 Integrity | L |
| ~~T1-2~~ ✅ | Real VCS merge (GitVCS: clone+merge+push+tag, real sha) — **done** | pdlc-graph + engine | 🔴 Integrity | M |
| ~~T1-3~~ ✅ | Real deploy execution (deploy seam + CommandDeployer; honest sim otherwise) — **done** | pdlc-graph + engine | 🔴 Integrity | L |
| ~~T1-4~~ ✅ | Real security scanners (security_scan_port + SubprocessScanner; gate blocks on findings) — **done** | pdlc-graph | 🔴 Integrity | M |
| ~~T1-5~~ ✅ | Migrate import persists tasks/decisions/deployments; received-vs-persisted response — **done** | engine + migrate | 🔴 Integrity | M |
| ~~T1-6~~ ✅ | FirehoseSink real delivery (was silent no-op) — **done** (quick-wins) | engine | 🔴 Integrity | S |
| ~~T2-1~~ ✅ | `/health/ready` real db/redis probes — **done** (quick-wins) | engine | 🟠 Operational | S |
| ~~T2-2~~ ✅ | Python CI teeth: ruff+pytest blocking (mypy ratchet kept) — **done** | CI | 🟠 Operational | S |
| ~~T2-3~~ ✅ | Sentinel `_stalled` real (progress-fingerprint) + smoke-failed marker reachable — **done** | pdlc-graph | 🟠 Operational | M |
| T2-4 (partial ✅) | `PDLC_AUTH_MODE` boot-guard done (no longer inert); real OIDC still open | engine | 🟠 Operational | L |
| ~~T2-5~~ ✅ | CDK image from context w/ GHCR default — **done** (quick-wins) | infra | 🟠 Operational | S |
| ~~T3-1~~ ✅ | MCP stdio execution (stdio_client dispatch, double-gated) — **done** | engine | 🟡 Feature | M |
| T3-2 | Initialization phase is a passthrough (no Constitution/Intent/Roadmap flow) | pdlc-graph | 🟡 Feature | L |
| ~~T3-3~~ ✅ | Migrate entity resolution (names → UUIDs, idempotent, DB-gated) — **done** | migrate + engine | 🟡 Feature | M |
| T3-4 | MemoryFileViewer is a live mockup in every project sidebar | studio | 🟡 Feature | M |
| ~~T3-5~~ ✅ | Per-org RPM quotas (org_quotas + resolver + console control) — **done** | engine + studio | 🟡 Feature | M |
| T3-6 | RoadmapBoard + SettingsDrawer orphan scaffolds; SketchSocraticToggle unpersisted | studio | 🟡 Feature | M–L |
| ~~T4-1~~ ✅ | Event-schema sync: registry backfilled (57 types), payloads added/fixed, check script + CI test — **done** | event-schema | 🟢 Hygiene | S |
| ~~T4-2~~ ✅ | Dead code deleted (LLMTokenTallyCallback, pdlc_graph/tools/*, 3 orphaned Studio components) — **done** | multi | 🟢 Hygiene | S |
| ~~T4-3~~ ✅ | Docstring truth (azure, analytics) — **done** (quick-wins) | engine | 🟢 Hygiene | S |
| T4-4 | Terraform modules validate-only (never deploy-tested) | infra | 🟢 Note | — |

**The theme of Tier 1:** the PDLC *workflow* engine (gates, phases, artifacts, telemetry,
provider platform) is real, but the **outermost side-effects of Construction/Operation —
run tests, merge, deploy, verify — are still simulations presented as results.** A completed
Ship today reports a merge SHA that was never created, a deploy URL that doesn't exist,
smoke tests that ran against a fake URL on a simulated runner, and a security sweep that is
hardcoded clean. These are the highest-value items in the repo.

---

## Tier 1 — Integrity gaps (the system reports things that did not happen)

### T1-1 · Real test runner — production test results are fabricated

- **Files:** `packages/pdlc-graph/pdlc_graph/test_runner_port.py:41` (`SimulatedTestRunner`);
  consumers: `graphs/build/loop.py:126,138` (TDD red→green→refactor),
  `graphs/build/test_phase.py:38` (the 7 test layers), `graphs/ship/verify.py:65` (smoke).
- **Claimed vs actual:** the port docstring (line 6) says the engine injects a subprocess
  runner via `set_test_runner` at boot. **No such wiring exists** — `set_test_runner` is
  called only from pdlc-graph's own tests; there is no `SubprocessTestRunner` (or any real
  runner) anywhere in `services/`. Every production build/ship "runs tests" on
  `SimulatedTestRunner`, which passes/fails by a scripted `attempt >= fail_until` counter
  and emits `[sim]` reports.
- **Impact:** TDD enforcement, the 7-layer test phase, 3-Strike escalation triggers, and
  ship smoke-signoff are all driven by fabricated results in real deployments.
- **Implementation sketch:**
  1. New `services/pdlc-engine/app/runtime/test_backend.py` with a `SubprocessTestRunner`
     implementing the port protocol: run a configured command per layer
     (e.g. `{"unit": "uv run pytest -q", ...}` from per-repo/org config or a
     `PDLC_TEST_CMD_<LAYER>` map), working dir = the checked-out repo (needs the repo
     workspace concept — see T1-2's checkout), capture exit code + tail of output as the
     report, hard timeout per layer.
  2. `wire_test_runner(settings)` in the lifespan, flag `PDLC_WIRE_TEST_RUNNER`
     (default off — keeps today's behavior explicit, mirrors `wire_llm`).
  3. Security posture: command execution on the engine host ⇒ gate like stdio MCP
     (refuse in multi-user mode unless explicitly allowed; sandbox/container execution is
     the SaaS follow-on — document).
  4. Update `graphs/build/test_phase.py` report rendering to carry the real output tail.
- **Acceptance:** with the flag on and a repo configured, a `/build` run executes the real
  suite (verifiable in the report artifact + duration); with the flag off, behavior is
  byte-identical to today; the simulator remains the hermetic default.
- **Effort:** L (~1.5–2 wk incl. the workspace/checkout dependency). **Depends on:** T1-2's
  repo-checkout mechanics (shared workspace).

### T1-2 · Real VCS merge — Ship reports merges that never happened

- **Files:** `packages/pdlc-graph/pdlc_graph/vcs_port.py:24` (`SimulatedVCS.merge_to_main`
  returns `sha256(...)[:10]`); consumers `graphs/ship/ship.py:122`,
  `graphs/utility/hotfix.py`.
- **Claimed vs actual:** docstring (line 8) claims the engine injects a real git/gh
  implementation at boot. **None exists** (`set_vcs` only in tests; no `GitVCS`/`GhVCS` in
  `services/`). Ship's `merge_and_deploy_approve` gate is followed by a "merge" that
  invents a SHA and a tag.
- **Impact:** the human approves gate #6 and receives confirmation of a merge + tag that do
  not exist in any repository. Merge-commit-only enforcement is enforced against a
  simulation.
- **Implementation sketch:**
  1. `services/pdlc-engine/app/runtime/vcs_backend.py`: `GitHubVCS` implementing the port —
     resolve the project's `repository_id` → `repositories` row → token via
     `token_secret_ref` (secretstore, already the established pattern) → either
     (a) GitHub REST merge API (`PUT /repos/{owner}/{repo}/merges` + create tag/release) —
     no local checkout needed for the merge itself, or (b) local clone + `git merge --no-ff`
     + push for parity with upstream pdlc. Recommend (a) first: no host git dependency,
     token-scoped, works in SaaS.
  2. Enforce merge-commit-only at the API call level; return the REAL sha to the graph.
  3. `wire_vcs(settings)` behind `PDLC_WIRE_VCS` (default off). Failure semantics: raise
     into the ship node → the gate-resume fails visibly (a failed merge must never be
     reported as success).
  4. Extend the port for `create_tag`/`open_pr` as needed by ship.py's actual call shape.
- **Acceptance:** with the flag on, gate #6 approval produces a verifiable merge commit +
  tag in the connected GitHub repo, and the sha in DEPLOYMENTS.md matches GitHub; flag off
  ⇒ unchanged.
- **Effort:** M (~1 wk). **Depends on:** repositories/token plumbing (exists).

### T1-3 · Real deploy execution — no deploy port exists; URL is hardcoded

- **Files:** `packages/pdlc-graph/pdlc_graph/deploy_port.py` (tier inference + prod-ban +
  in-memory register only — **there is no execution seam at all**);
  `graphs/ship/ship.py:130` — `deploy_url = f"https://{slug}.example.app"` hardcoded;
  `graphs/ship/verify.py:61` smoke-checks that fake URL.
- **Claimed vs actual:** Ship renders DEPLOYMENTS.md with a URL on a placeholder domain and
  marks the deploy succeeded; nothing is deployed anywhere. The (excellent) three-layer
  production-deploy *ban* is real; the deploy itself is not.
- **Impact:** "shipped + deployed + smoke-verified" is a complete simulation end-to-end.
- **Implementation sketch:**
  1. Add an execution seam to `deploy_port`: `set_deployer(fn)` with a
     `deploy(target, ref, project) -> {url, id}` protocol and a simulated default (current
     behavior, explicitly labeled).
  2. Engine backend `app/runtime/deploy_backend.py` v1: **webhook/command deployer** — per
     org/project config (`deploy_targets` table or JSONB on projects): a URL to POST
     (CI/CD webhook: GitHub Actions `workflow_dispatch`, ArgoCD, etc.) or a command
     (self-host, gated like stdio MCP). The returned/configured environment URL replaces
     the hardcode; verify.py smoke-tests the real URL.
  3. Deploy status polling (async) is a v2; v1 fire-and-record with the webhook response.
  4. `PDLC_WIRE_DEPLOY` flag, default off. Prod-ban layers stay in front of execution.
- **Acceptance:** with a target configured, gate #6 approval triggers the webhook (observable
  in the CI/CD system), DEPLOYMENTS.md carries the real environment URL, and verify's smoke
  step hits it; flag off ⇒ simulated, but DEPLOYMENTS.md/verify output must now say
  `[simulated]` instead of implying a real deploy (small honesty fix worth doing even
  before the real deployer).
- **Effort:** L (~1.5–2 wk). **Depends on:** none hard; pairs naturally with T1-2.

### T1-4 · Security & UX verify gates hardcode clean verdicts

- **Files:** `packages/pdlc-graph/pdlc_graph/graphs/ship/verify.py:56` (`security_checks`
  returns `{"dependency_audit": "clean", "secret_scan": "clean", ..., "passed": True}`
  unconditionally; only a Phantom LLM *note* is real), `verify.py:88` (`ux_verify`
  hardcodes `passed: True, p0_findings: 0`).
- **Impact:** gate #7 (`smoke_signoff`) presents a structurally-always-green security sweep;
  the "blocking" path for failed required checks can never trigger from these two checks.
- **Implementation sketch:**
  1. Introduce a `security_scan_port` (same idiom as test_runner_port): protocol
     `run(kind, workspace) -> {passed, findings[]}`; hermetic default returns
     `passed: None / skipped: True` — **honestly marked "not run"**, not "clean".
  2. Engine backend: dependency audit via `pip-audit`/`npm audit` subprocess, secret scan
     via `gitleaks`/`trufflehog` if present on PATH (graceful "tool unavailable" report),
     both against the repo workspace (T1-1/T1-2 dependency). Gate blocking wiring already
     exists — feed it real `passed` values.
  3. `ux_verify`: either drive it from the eval harness (an LLM-judged UX heuristic pass —
     cheap, honest about being a judgment) or mark it `skipped` until a real check exists.
  4. Immediate mini-fix (independent of the port): change the hardcoded `"clean"` labels to
     `"skipped"` so reports stop lying. One-line honesty patch.
- **Acceptance:** a repo with a known-vulnerable dep fails `dependency_audit` and flags the
  gate blocking; hermetic runs show `skipped`, never `clean`.
- **Effort:** M (~1 wk after T1-1's workspace exists; the honesty mini-fix is 10 minutes).

### T1-5 · Migrate import silently drops tasks/decisions/deployments

- **Files:** `services/pdlc-engine/app/routes/migrate.py:150–156` (returns
  `len(payload.tasks)` etc. as counts), `migrate.py:13` (docstring admits: "echoed back in
  the response counts"), `tools/pdlc-migrate` push path.
- **Claimed vs actual:** the import response reports nonzero `tasks/decisions/deployments`
  counts, but only **events + memory_files** are persisted. The docstring documents the
  deferral, but the API response shape misleads — a migration operator reasonably reads
  those counts as "imported".
- **Impact:** upstream `pdlc` projects lose their task history (`.beads/tasks.json`),
  decision registry, and deployment records on migration, with a success-shaped response.
- **Implementation sketch:**
  1. Tasks → `get_task_store().create(...)` per task (the Postgres task store exists;
     preserve `bd-NN` via `external_id` — already supported per STATUS Phase H bundle 3).
  2. Decisions → append to the project's Decision Registry artifact
     (`render_decisions`/DECISIONS.md via the artifact port) — matches `/decide`'s storage.
  3. Deployments → DEPLOYMENTS.md artifact via the artifact port (the durable record the
     ship flow uses).
  4. Response: split counts into `{received, persisted}` per kind so partial support can
     never masquerade again. Idempotency: key tasks on external_id, decisions/deployments
     on content-hash (mirror the event `uuid5` dedup approach).
- **Acceptance:** the integration migrate test round-trips tasks (visible in the task
  store), DECISIONS.md and DEPLOYMENTS.md exist post-import, re-import is idempotent, and
  the response distinguishes received vs persisted.
- **Effort:** M (~3–4 days).

### T1-6 · FirehoseSink is a live-selectable silent no-op

- **Files:** `services/pdlc-engine/app/clickstream/sinks/firehose.py:19–22` (`write()` is
  `return None`; the real `put_record_batch` call sits in a comment);
  selectable at `app/config.py` (`clickstream_sink` Literal includes `"firehose"`) and
  `app/clickstream/emitter.py:135`.
- **Impact:** `PDLC_CLICKSTREAM_SINK=firehose` (the documented AWS SaaS path,
  `deploy/.env.example` line ~92) drops every durable event with no warning. The
  in-process analytics fan-out keeps the Nexus Console alive, which *masks* the loss —
  you notice when you try to query S3/Glue and find nothing.
- **Implementation sketch:** implement the commented call — lazy boto3 `firehose` client,
  batch ≤500 records per `put_record_batch`, retry `FailedPutCount>0` once, `\n`-delimited
  JSON records; on client/permission errors log **loudly once** (not per batch). ~30 LOC +
  a moto-or-fake-client hermetic test asserting record shape/batching. Alternative if AWS
  isn't a near-term target: **remove** `"firehose"` from the Literal and fail fast at boot,
  so the option can't silently no-op (honesty > feature).
- **Acceptance:** either events land in the Firehose stream (integration/manual against
  localstack), or selecting the sink is impossible/fails loudly.
- **Effort:** S (~half day).

---

## Tier 2 — Operational & liveness gaps

### T2-1 · `/health/ready` db/redis checks are hardcoded

- **Files:** `services/pdlc-engine/app/routes/health.py:23` —
  `{"db": "stub", "redis": "stub", "llm": <real>}`. The `llm` field became real in PRD-03;
  db/redis never did.
- **Impact:** an orchestrator's readiness gate routes traffic to pods whose Postgres/Redis
  are down.
- **Implementation sketch:** cheap cached probes (5–10 s TTL, executed lazily on request,
  timeout ≤250 ms each): db → `SELECT 1` via the sync engine when
  `task_store=postgres`/checkpointer on, else `"unconfigured"`; redis → `PING` when any
  redis-backed feature is on, else `"unconfigured"`. Report `ok | degraded | unconfigured`.
  Decide and document whether `status` flips to non-ready when db is down (recommend: yes
  for db when Postgres is the configured store; never for redis — matches the fail-open
  philosophy).
- **Acceptance:** stop Postgres in compose → `/health/ready` reports `db: degraded` (and
  non-ready if configured); hermetic tests cover unconfigured/ok/degraded via injected
  fakes.
- **Effort:** S (~2–3 hrs).

### T2-2 · Python CI can never fail

- **Files:** `.github/workflows/ci.yml:31,34,37` — `ruff check || true`,
  `mypy || true`, `pytest || true` ("ratchet — non-blocking until B-I lands"; B–I landed
  long ago).
- **Impact:** lint/type/test regressions in all four Python workspace members merge green.
  Partially compensated by the hard-failing `evals` and `integration` jobs — but the main
  hermetic suite (380+ tests) is advisory.
- **Implementation sketch:** drop `|| true` from ruff + pytest now (both are green on
  main — verified this session repeatedly). For mypy, check whether it currently passes;
  if not, keep `|| true` on mypy only, with a tracked issue (a real ratchet, not a blanket
  one).
- **Acceptance:** a PR with a failing test or lint error cannot merge.
- **Effort:** S (~1 hr incl. a local mypy run to decide its fate).

### T2-3 · Sentinel `_stalled` always False; most night-shift aborts unreachable

- **Files:** `packages/pdlc-graph/pdlc_graph/sentinel/evaluator.py:65` (self-labeled
  "Phase A stub: always False"); `graphs/night_shift.py:34` (`_state_md` synthesizes only
  smoke-failed/complete markers — abort conditions like merge-conflict,
  prod-deploy-attempted, env-untagged depend on `ns_markers` that nothing appends).
- **Impact:** the autonomous night-shift's stagnation guard can never fire; a stuck run
  spins until some other condition trips. Several of the 12 documented ABORT_CONDITIONS
  are structurally unreachable.
- **Implementation sketch:**
  1. `_stalled`: track per-run progress heartbeats (e.g. last task-state change / last node
     timestamp carried in state); stalled = no progress in N node transitions or M wall
     minutes (wall-clock needs a timestamp injected into state by the runner — keep the
     evaluator pure by comparing state-carried timestamps).
  2. Marker plumbing: have the build/ship wrappers append real `ns_markers` on the events
     that exist today (strike-panel convened → marker; VCS merge failure (post T1-2) →
     merge-conflict marker; deploy_port ban trip → prod-deploy-attempted marker).
  3. Test each abort condition's reachability explicitly (the matrix test style used for
     guards elsewhere).
- **Acceptance:** a night-shift run with an artificially stalled build aborts with the
  stagnation verdict; each ABORT_CONDITION has a test proving it can fire.
- **Effort:** M (~3–4 days). **Depends on:** T1-2 for the merge-conflict marker (partial).

### T2-4 · Cognito/SSO unimplemented; `PDLC_AUTH_MODE` is an inert knob

- **Files:** `services/pdlc-engine/app/auth/cognito.py:15`
  (`NotImplementedError("cognito auth lands in Phase H")`) — and **nothing imports it**;
  no code reads `settings.auth_mode` (`app/config.py:24–25`).
- **Impact:** `PDLC_AUTH_MODE=cognito` silently keeps local JWT — a deployment that
  believes it enabled SSO hasn't. The SaaS SSO story (Cognito per the CDK stacks, OIDC per
  the Terraform README) doesn't exist app-side.
- **Implementation sketch (two-step):**
  1. **Immediate honesty fix (S):** boot-time check — if `auth_mode != "local"`, either
     fail fast or log an unmissable error; OR remove `"cognito"` from the Literal until
     implemented. Kills the silent-misconfig risk in 10 lines.
  2. **Real implementation (L):** generic OIDC (covers Cognito + Identity Platform +
     AD B2C, matching the multi-cloud posture): JWKS fetch/cache + issuer/audience
     validation in `get_principal` when `auth_mode="oidc"`, org/role from configurable
     claims, first-login user provisioning. Config: issuer URL, audience, claim mappings.
     Studio: redirect-based login (auth-code + PKCE) alongside the password form.
- **Acceptance (step 2):** login via a real OIDC provider end-to-end; org/role enforcement
  identical to local mode; local mode untouched.
- **Effort:** S for the honesty fix; L (~2 wk incl. Studio) for real OIDC.

### T2-5 · CDK compute stack has a placeholder image

- **Files:** `infra/cdk/lib/compute-stack.ts:25,34` —
  `placeholder/pdlc-engine:phase-a` hardcoded for both API and worker Fargate services.
- **Impact:** the CDK SaaS path cannot deploy a working service as-is (Terraform modules
  take `api_image` as a variable and don't have this problem).
- **Implementation sketch:** take the image from CDK context/props
  (`-c apiImage=ghcr.io/pdlc-os/pdlcflow-api:1.13.0`) with a default of the current GHCR
  `latest`; same for the worker (same image, different command — mirror compose). Also
  sweep the other 7 stacks for similar placeholders while in there.
- **Acceptance:** `cdk synth` renders the GHCR refs; a deploy-test is optional
  (document as with Terraform if not performed).
- **Effort:** S (~1–2 hrs).

---

## Tier 3 — Feature completions (declared surface not yet real)

### T3-1 · MCP stdio execution

- **Files:** `services/pdlc-engine/app/runtime/mcp_backend.py:200–202` — returns
  `{"ok": False, "error": "stdio execution not implemented in v1"}`; yet registration
  (`routes/admin/mcp.py:88`), the `PDLC_ENABLE_STDIO_MCP` flag, the guard, the console
  transport picker, and the `filesystem` template all accept stdio.
- **Impact:** a single-user self-hoster can enable the flag, register the filesystem
  template, bind it — and every tool call fails at runtime. Config surface promises what
  execution doesn't deliver. (Known v1 scoping decision from PRD-09; now the follow-up.)
- **Implementation sketch:** in `_call_client`-equivalent for stdio: `mcp` SDK
  `stdio_client(StdioServerParameters(command, args, env=minimal))` → `ClientSession` →
  `call_tool`, same timeout/truncation caps. Process lifecycle: spawn-per-call v1 (simple,
  slow) or a per-(org,server) process cache with idle reap (better; mirrors the negative
  cache). Keep the double guard. Alternative if deprioritized: hide stdio from the
  console/templates and reject at registration with "not yet implemented" so the surface
  stops over-promising.
- **Acceptance:** with the flag on, the filesystem template's `read_file` works end-to-end
  in a single-user deployment; multi-user refusal matrix unchanged.
- **Effort:** M (~3 days with process cache).

### T3-2 · Initialization phase is a passthrough

- **Files:** `packages/pdlc-graph/pdlc_graph/graphs/init.py:12` — one node, emits
  `phase.entered`, returns `{"sub_phase": "Initialization"}`. Reachable in production via
  `meta._route` (default phase). The Constitution / Intent / Roadmap authoring flow
  ("lands in Phase B") was never built.
- **Impact:** `/init` and first-time project setup do nothing visible; the methodology's
  Initialization artifacts (constitution, intent, roadmap seed) don't exist in pdlcflow.
- **Implementation sketch:** model on the Define sub-phase: 2–3 `interaction.ask` rounds
  (product intent, constraints/constitution choices, initial roadmap items) → renderers
  (`render_constitution`, `render_intent`, `render_roadmap`) → artifact port → one approval
  gate (`init_approve` — note: today's canon is "8 gates"; adding a 9th touches docs +
  the gate list) → set phase to Inception. Check upstream `pdlc`'s init skill for the
  authoritative step list before building.
- **Acceptance:** `/init` produces CONSTITUTION.md / INTENT.md / ROADMAP.md artifacts
  through a gated interactive flow; hermetic tests mirror the brainstorm-flow test style.
- **Effort:** L (~1–1.5 wk). **Decide first:** whether upstream parity demands this now.

### T3-3 · Migrate entity resolution (names → UUIDs)

- **Files:** `tools/pdlc-migrate` `taxonomy.py` (collects free-text `initiative` /
  `application` names), `push.py:73–77` (forwards verbatim);
  `services/pdlc-engine/app/routes/migrate.py:117–131` (never resolves; events get only
  `domains`); envelope slots exist (`event_schema/envelope.py` `initiative_id`,
  `application_id` — stay `None`).
- **Impact:** migrated history contributes nothing to 2 of 7 rollup dimensions
  (initiative, application) — the exact "backfill makes Nexus non-empty on day one" promise
  is only 5/7 true.
- **Implementation sketch:** in the import handler, upsert-by-name within the org:
  `initiatives` (name → id, create with `status='active'` if absent) and `applications`
  (name → id, `kind='service'` default), then stamp `initiative_id`/`application_id` onto
  each imported event before ingest. Idempotent via the org-scoped unique names. Include in
  the response (`created_entities`).
- **Acceptance:** post-migration, the Nexus initiative/application rollups show the
  imported project's history; re-import creates no duplicates.
- **Effort:** M (~2 days). Pairs naturally with T1-5 in one "migrate fidelity" PR.

### T3-4 · MemoryFileViewer is a live mockup

- **Files:** `apps/studio/src/components/MemoryFileViewer.tsx:1–17` — hardcoded file-name
  list + literal "Inline Monaco viewer lands in Phase B."; rendered in every project
  sidebar (`routes/projects/[id].tsx:102`).
- **Impact:** same class as the old Models mockup — visible, dead UI in the main flow.
- **Implementation sketch:** the data exists — memory bodies live in the artifact store and
  `RepoMemory` already browses repo files. v1: list the project's artifacts (needs a small
  `GET /v1/projects/{id}/artifacts` route over the artifact store's namespace listing —
  check whether the store exposes list; filesystem/S3 both can) and render selected content
  in the existing read-only viewer style (Monaco optional; `<pre>` first). Or: fold it into
  RepoMemory as a second tab and delete the component.
- **Acceptance:** the sidebar lists real artifacts (PRD.md, DECISIONS.md, …) for the active
  project and opens their content; empty state honest.
- **Effort:** M (~2–3 days incl. the list route).

### T3-5 · Per-org RPM quota overrides ("Quotas page")

- **Files:** `services/pdlc-engine/app/llm/rate_limit.py:9–12` — docstring promises
  "buckets set at tenant onboarding; the Nexus Quotas page exposes the knobs (Phase H)".
  Only global `PDLC_LLM_RPM_DEFAULT` exists.
- **Impact:** no per-tenant quota differentiation; one global knob for all orgs.
- **Implementation sketch:** `rpm_limit` column on `org_budgets` (it's the org's
  cost/usage-controls row; avoids a new table) or `org_llm_config`; `RateLimit.acquire`
  gains a per-org limit lookup with the same 60 s TTL cache pattern as pricing overrides;
  surface next to the budget card in the console ("Pricing & budget" panel — no new page
  needed); versioned via the existing config-version hook if placed on `org_llm_config`.
- **Acceptance:** org A at 10 RPM throttles at 10 while org B (default) doesn't;
  console-editable.
- **Effort:** M (~2 days).

### T3-6 · Studio orphan scaffolds (decide: build or delete)

- **Files:** `apps/studio/src/components/RoadmapBoard.tsx` (kanban with 4 hardcoded empty
  columns, no data source, imported nowhere), `SettingsDrawer.tsx` ("Lands in Phase B"
  text only), `SketchSocraticToggle.tsx` (works locally, never persists interaction_mode to
  the backend, wired nowhere).
- **Impact:** none today (orphaned) — but they encode intended features:
  - **RoadmapBoard** = the Beads/task-board view. Real version: feed from the task store
    (`GET /v1/projects/{id}/tasks` route needed) with wave/status columns. Effort M.
  - **SettingsDrawer** = per-project/per-user preferences (incl. a home for the
    Sketch/Socratic default). Effort M (needs a small preferences store).
  - **SketchSocraticToggle** = should write `interaction_mode` into command invocations
    (the API already accepts `interaction_mode` in `InvokeBody`) — smallest real fix: wire
    it into the composer and pass through. Effort S.
- **Recommendation:** wire SketchSocraticToggle (S, real value), build RoadmapBoard when
  task visibility matters, delete or build SettingsDrawer deliberately — don't leave
  scaffolds orphaned. Track as three separate decisions.

---

## Tier 4 — Hygiene & debt

### T4-1 · Event-schema drift (registry doc, payloads, missing check script)

- **Files:** `packages/event-schema/event_schema/registry.md` (documents ~39 of the now-58
  `EVENT_TYPES`; all 17+ types added during the observability/provider work are missing);
  `payloads.py` (no payload classes for `admin.*`, `budget.*`, `llm.failover`,
  `llm.rate_limited`, `llm_config.*`, `prompt.*`, `prompt_pack.*`, `tool.called`; note the
  `tool.invoked`/`tool.blocked`/`tool.called` naming split);
  `scripts/check_event_registry.py` **does not exist** despite being referenced by
  `envelope.py:161`'s contributor note and `docs/wiki/14-monitoring.md`.
- **Fix:** (1) write the check script (parse registry.md's event names, diff against
  `EVENT_TYPES`, exit 1 on drift) and add it to CI; (2) update registry.md with the 17+
  missing types (payload fields are already defined by their emitters — copy shapes from
  the emitting code cited in this doc); (3) add the typed payload classes or explicitly
  document which families are envelope-only; (4) resolve the `tool.called` vs
  `tool.invoked` naming overlap (recommend: keep both, document `tool.invoked/blocked` as
  the legacy graph-tool events and `tool.called` as MCP).
- **Effort:** S (~half day). High leverage: the missing script is why drift accumulated.

### T4-2 · Dead-code sweep

Safe deletions (verified zero references outside their own files/tests):
- `services/pdlc-engine/app/clickstream/callbacks.py` — `LLMTokenTallyCallback` +
  `_extract_usage`: never constructed; superseded by `llm_backend._emit_spend`.
- `packages/pdlc-graph/pdlc_graph/tools/` — `git_tool.py`, `gh_tool.py`, `deploy_tool.py`,
  `memory_file_tool.py`, `test_runner.py`: all return "stub: not yet wired" strings and
  have **zero** references anywhere. Note: T1-1/T1-2 supersede their intent via ports —
  delete rather than implement.
- `apps/studio/src/components/` — `ThemeToggle.tsx` (superseded by AppShell's inline
  toggle), `StepCard.tsx`, `PartyMeetingVisualizer.tsx` (functional but imported nowhere —
  delete or wire deliberately; PartyMeetingVisualizer may be worth wiring into the party
  MOM rendering instead of deleting).
- **Effort:** S (~1–2 hrs incl. test runs).

### T4-3 · Doc-drift micro-fixes

- `services/pdlc-engine/app/llm/providers/azure.py:1–9` — docstring claims a
  Claude-via-Azure fallback resolver that doesn't exist (`factory.py` maps azure →
  AzureChatOpenAI unconditionally). Rewrite the docstring to match reality (Azure = GPT
  deployments; Claude-on-Azure unsupported).
- `services/pdlc-engine/app/analytics/store.py:6` — docstring says "ClickHouse/Postgres-
  backed"; no ClickHouse store exists. Fix the docstring (or file ClickHouse as an explicit
  future item — it's a SaaS-scale concern, not a gap today).
- **Effort:** S (~30 min).

### T4-4 · Terraform modules are validate-only (standing note)

- `infra/terraform/README.md:51` already says it honestly: all three cloud modules pass
  `tofu validate` but have never been applied. Not a stub — but the first real cloud deploy
  should be treated as a milestone with a checklist (state backend, secrets, DNS, image
  refs) rather than assumed working. No action until a cloud deploy is planned.

---

## Suggested sequencing

1. **Quick-wins batch (1 day):** T2-2 CI teeth · T2-1 readiness probes · T1-6 Firehose
   (implement or remove) · T2-4 step-1 auth_mode honesty · T1-4 mini-fix ("clean"→"skipped")
   · T2-5 CDK image · T4-3 docstrings. Small, independent, each removes a lie.
2. **Migrate fidelity PR:** T1-5 + T3-3 together (persist everything + resolve entities).
3. **Schema hygiene PR:** T4-1 (check script first, then the doc/payload backfill) + T4-2
   dead-code sweep.
4. **The execution arc (the big one):** T1-2 VCS merge → T1-1 test runner → T1-3 deploy
   execution → T1-4 real scanners → T2-3 sentinel markers. This is "Construction/Operation
   stop simulating" — arguably the next roadmap-scale effort after cc-switch, and worth its
   own PRD treatment before coding.
5. **Feature decisions as demanded:** T3-1 stdio MCP · T3-2 Initialization flow · T3-4
   MemoryFileViewer · T3-5 quotas · T3-6 scaffold triage · T2-4 real OIDC.
