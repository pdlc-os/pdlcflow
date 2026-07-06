# Execution Arc — design (T1-1/2/3, T1-4, T2-3)

> The roadmap-scale item from [`stub-gaps-roadmap.md`](stub-gaps-roadmap.md): make
> Construction/Operation's outermost side-effects **real** instead of simulations
> presented as results. Today a completed Ship reports a merge SHA that was never
> created, a deploy to `*.example.app` that doesn't exist, and test/security
> results from a simulator. This wires real execution behind the existing ports.

## Decisions (confirmed)

- **Execution model: local subprocess on the engine host.** Clone the connected
  repo to a managed workspace; run tests/scans/build/deploy as subprocesses;
  merge with local git. This is **host code execution** → gated to **single-user
  self-host only**, exactly like stdio MCP and the subscription CLIs: requires
  `PDLC_ENABLE_EXECUTION=true` **and** refused when `PDLC_AUTH_REQUIRED` is on.
- **Deploy: real trigger.** A configured deploy command (or webhook) is executed;
  the real environment URL it yields is recorded and smoke-tested. The 3-layer
  production-deploy ban stays in front of execution.
- **Default off ⇒ nothing changes.** With the flag off (and always in hermetic
  CI), the simulated defaults (`SimulatedTestRunner`, `SimulatedVCS`, in-memory
  deploy register, "skipped" security labels) remain — byte-identical.

## The seams (already exist in pdlc-graph)

| Port | Simulated default | Real backend (this arc) |
|---|---|---|
| `test_runner_port.run_layer` | `SimulatedTestRunner` (scripted pass/fail) | `SubprocessTestRunner` — per-layer command in the workspace |
| `vcs_port.merge_to_main` | `SimulatedVCS` (fake sha) | `GitVCS` — local clone + `merge --no-ff` + tag + push |
| `deploy_port` | tier-infer + ban + in-memory register (no execution seam) | **new** `set_deployer` seam + `CommandDeployer` |
| security/UX verify | hardcoded `passed`/`skipped` | **new** `security_scan_port` + `SubprocessScanner` |
| `sentinel._stalled` | always `False` | real stagnation check + abort-marker plumbing |

## Shared foundation

### Execution context (graph, dep-free)
`pdlc_graph/execution_context.py` — a contextvar carrying
`{project_id, feature, branch}`, set per turn by the engine runner (from the
turn's state / thread id), read by the engine backends to resolve *which repo,
which branch*. `None` ⇒ backends fall back to simulation. Mirrors
`set_current_org`. The graph package gains no engine deps.

### RepoWorkspace (engine)
`app/runtime/workspace.py` — given a `project_id`: look up `projects.repository_id`
→ `repositories` row (`url`, `default_branch`, `token_secret_ref`) → resolve the
token via the secretstore → `git clone` (token-injected https, or `file://` in
tests) into `PDLC_WORKSPACE_DIR/<project>/<branch>`, checkout the feature branch,
hand back `.path`. Cached per (project, branch); cleaned on demand. Every real
backend acquires its workspace here, so repo/token/branch resolution lives once.

### Execution guard (engine)
`guard_execution()` — raises unless `PDLC_ENABLE_EXECUTION` and NOT
`auth_required`. Called at wire time (backends aren't even injected in
multi-user mode) and defensively per operation.

## Backends

1. **SubprocessTestRunner** (`app/runtime/test_backend.py`) — `run_layer(layer,
   target, …)` runs the configured command for `layer`
   (`PDLC_TEST_CMD_<LAYER>`, default `PDLC_TEST_CMD`) in the workspace, captures
   exit code + output tail, hard `PDLC_TEST_TIMEOUT_S`. Ignores the simulator's
   `fail_until`. Note: langgraph replays completed nodes on resume, so a real
   run may repeat — acceptable in the single-user gated context; documented.

2. **GitVCS** (`app/runtime/vcs_backend.py`) — `merge_to_main(feature, version,
   description, strategy)`: enforce merge-commit-only (as the sim does), then in
   the workspace `git checkout <default>`, `git merge --no-ff <feature-branch>`,
   `git tag <version>`, `git push origin <default> --tags`. Returns the REAL
   merge sha + tag. A merge conflict / push failure raises → the ship node fails
   visibly (a failed merge must never report success).

3. **CommandDeployer** (`app/runtime/deploy_backend.py`) + `deploy_port.set_deployer`
   — runs the org/project-configured deploy command (env-substituted target +
   ref) or POSTs a webhook; returns `{url, id}`. The returned URL replaces the
   `*.example.app` hardcode; `verify.smoke_tests` hits the real URL. Prod-ban
   layers run first.

4. **SubprocessScanner** (`app/runtime/security_backend.py`) + a graph
   `security_scan_port` — `dependency_audit` (`pip-audit`/`npm audit`),
   `secret_scan` (`gitleaks`) in the workspace; tools absent ⇒ honest
   `skipped`, never faked `clean`. `verify.security_checks` consumes real
   verdicts and can flag the gate blocking.

5. **Sentinel** — `_stalled` compares progress heartbeats carried in state
   (last task-state change / node count); the build/ship wrappers append real
   `ns_markers` (strike-panel convened, merge-conflict on a failed GitVCS merge,
   prod-deploy-attempted on a ban trip) so the abort conditions are reachable.

## Config (all default off / simulated)

`PDLC_ENABLE_EXECUTION` · `PDLC_WORKSPACE_DIR` · `PDLC_TEST_CMD` +
`PDLC_TEST_CMD_<LAYER>` · `PDLC_TEST_TIMEOUT_S` · `PDLC_DEPLOY_CMD` /
`PDLC_DEPLOY_WEBHOOK` · `PDLC_SECURITY_SCAN` (on/off) · `PDLC_GIT_AUTHOR_*`.

## Testing (hermetic — real code, no network)

Local `git` against `file://` bare repos and subprocesses running local
commands are **fully hermetic**, so the arc is tested with the REAL backends,
not fakes: a temp bare repo stands in for the remote (clone/merge/push all
work), `run_layer` runs `true`/`false`, the deployer runs `echo`, the scanner
runs against a temp dir. The guard matrix (flag × auth_required) mirrors the
stdio-MCP tests. The simulated defaults keep the existing graph suite
byte-identical.

## Milestones (one feature branch)

M0 foundation (context + workspace + guard + config) → M1 test runner →
M2 GitVCS → M3 deploy + scanners + sentinel → verify.py real verdicts + wiring.
