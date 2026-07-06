# Event registry — source of truth for the 57-event taxonomy

Every event the PDLC clickstream emits is listed here. Adding a new event type requires:

1. A new entry in `EVENT_TYPES` in `event_schema/envelope.py`.
2. Either a typed payload class in `event_schema/payloads.py`, or — for loose
   audit/telemetry families — a "generic dict" row here (like `admin.access.denied`).
3. A new row in this registry with semantics, payload shape, and the admin views that consume it.
4. The CI check (`event-schema/scripts/check_event_registry.py`, run by
   `tests/test_event_registry_sync.py` in the blocking event-schema job)
   confirming registry.md and `EVENT_TYPES` stay in sync.

Backwards-compatible additions (new optional payload fields) bump nothing. Breaking changes require `schema_version` bump + dual-write window + a ClickHouse view that unions versions.

PII rule: payloads carry **references** (S3 keys, UUIDs, route names), never raw prompts / messages / artifact contents.

---

## Session (3)

| Event | When | Payload | Consumed by |
|---|---|---|---|
| `session.opened` | New browser session authenticates | `SessionOpenedPayload` | Live mode, agent heatmap |
| `session.resumed` | Resume banner shown on session start | `SessionResumedPayload` | Initiative cycle-time analytics |
| `session.closed` | Session ends or times out | `SessionClosedPayload` | Squad scoreboard |

## Phase (3)

| Event | When | Payload | Consumed by |
|---|---|---|---|
| `phase.entered` | Worker enters Init/Inception/Construction/Operation subgraph | `PhaseEnteredPayload` | Live mode, status line |
| `phase.exited` | Worker exits a phase subgraph | `PhaseExitedPayload` | Cycle-time rollups |
| `phase.transition` | One phase ends and the next begins | `PhaseTransitionPayload` | Feature timeline |

## Sub-phase (2)

| Event | When | Payload | Consumed by |
|---|---|---|---|
| `subphase.entered` | Worker enters Discover/Define/Design/Plan/Build/Review/Test/Ship/Verify/Reflect | `SubphaseEnteredPayload` | Initiative breakdown |
| `subphase.exited` | Worker exits a sub-phase | `SubphaseExitedPayload` | Sub-phase duration heatmap |

## Step (1)

| Event | When | Payload | Consumed by |
|---|---|---|---|
| `step.completed` | A numbered step within a skill completes | `StepCompletedPayload` | Time-travel feature view |

## Skill (1)

| Event | When | Payload | Consumed by |
|---|---|---|---|
| `skill.invoked` | A slash-command-equivalent skill is invoked | `SkillInvokedPayload` | Command palette analytics |

## Agent (2)

| Event | When | Payload | Consumed by |
|---|---|---|---|
| `agent.invoked` | A persona's `create_react_agent` is called | `AgentInvokedPayload` | Agent heatmap |
| `agent.responded` | A persona's invocation returns | `AgentRespondedPayload` | Per-agent latency |

## Approval gate (2)

| Event | When | Payload | Consumed by |
|---|---|---|---|
| `gate.opened` | A graph hits `interrupt()` for one of the 8 gates | `GateOpenedPayload` | Approval queue, cycle-time |
| `gate.resolved` | User resolves the gate | `GateResolvedPayload` | Approval-rate per agent |

## Party meeting (3)

| Event | When | Payload | Consumed by |
|---|---|---|---|
| `party.opened` | A party meeting begins (fan-out) | `PartyOpenedPayload` | Party-meeting analytics |
| `party.pitch_received` | One persona's pitch lands at the consensus node | `PartyPitchReceivedPayload` | Per-persona contribution analytics |
| `party.consensus_reached` | Consensus node writes a MOM and a vote | `PartyConsensusReachedPayload` | Decision velocity |

## Tool (2)

| Event | When | Payload | Consumed by |
|---|---|---|---|
| `tool.invoked` | A `@tool` is invoked by an agent | `ToolInvokedPayload` | Tool-use heatmap, repo-level rollups |
| `tool.blocked` | A pre-tool guardrail blocks an invocation | `ToolBlockedPayload` | Guardrail audit |

## Test (3)

| Event | When | Payload | Consumed by |
|---|---|---|---|
| `test.run` | A test starts | `TestRunPayload` | TDD compliance |
| `test.passed` | A test passes | `TestPassedPayload` | Coverage rollup |
| `test.failed` | A test fails | `TestFailedPayload` | Strike escalation |

## Strike (2)

| Event | When | Payload | Consumed by |
|---|---|---|---|
| `strike.recorded` | A failed test marks attempt N of 3 | `StrikeRecordedPayload` | 3-Strike analytics |
| `strike.panel_convened` | The 3rd-strike panel meets | `StrikePanelConvenedPayload` | Build-loop quality metric |

## Deploy (3)

| Event | When | Payload | Consumed by |
|---|---|---|---|
| `deploy.requested` | A deploy command is about to run | `DeployRequestedPayload` | Deploy register |
| `deploy.succeeded` | Deploy returns success | `DeploySucceededPayload` | Lead time |
| `deploy.blocked` | A guardrail blocks the deploy | `DeployBlockedPayload` | Deploy-gating audit |

## Night-shift (4)

| Event | When | Payload | Consumed by |
|---|---|---|---|
| `night_shift.started` | Night-shift run begins | `NightShiftStartedPayload` | Mission control |
| `night_shift.verdict` | Sentinel evaluator emits a verdict | `NightShiftVerdictPayload` | Verdict timeline |
| `night_shift.completed` | Run finishes successfully | `NightShiftCompletedPayload` | Autonomous-run analytics |
| `night_shift.aborted` | Run aborts | `NightShiftAbortedPayload` | Abort-rate analysis |

## Decision / override (2)

| Event | When | Payload | Consumed by |
|---|---|---|---|
| `decision.recorded` | `/decide` writes a row to DECISIONS.md | `DecisionRecordedPayload` | Decision registry |
| `override.invoked` | `/override` bypasses a guardrail | `OverrideInvokedPayload` | Override audit |

## LLM (3)

| Event | When | Payload | Consumed by |
|---|---|---|---|
| `llm.tokens_spent` | An LLM call completes | `LLMTokensSpentPayload` | Cost rollups by provider × agent × initiative × domain |
| `llm.failover` | A retriable provider error rolls to the next failover-chain candidate (PRD-05) | `LLMFailoverPayload` | Resilience dashboard, provider health |
| `llm.rate_limited` | A completion is rejected by the per-org RPM limit (PRD-05) | `LLMRateLimitedPayload` | Resilience dashboard, quota analytics |

## Context / UI / error (3)

| Event | When | Payload | Consumed by |
|---|---|---|---|
| `context.warning` | Token watchdog crosses 75/90/95% | `ContextWarningPayload` | Context-rot analytics |
| `ui.viewed` | User opens a route or component | `UIViewedPayload` | Adoption analytics |
| `error` | An exception is caught in a node | `ErrorPayload` | Error budget |

## Admin / audit (5)

Provider-console audit events — loose reference dicts (no rigid payload class),
validated by `event_type` only, references never content.

| Event | When | Payload | Consumed by |
|---|---|---|---|
| `admin.access.denied` | An admin query is attempted without an org filter (cross-org ban) | generic dict (`path`, `reason`) | Security audit |
| `admin.llm_key.set` | A tenant BYOK key is stored for an org/agent scope (PRD-01) | generic dict (`scope`, `persona?`, `provider`) | Provider-config audit |
| `admin.llm_key.cleared` | A stored tenant key is removed (PRD-01) | generic dict (`scope`, `persona?`) | Provider-config audit |
| `admin.provider.probed` | A provider connectivity/health probe runs (PRD-03) | generic dict (`provider`, `scope?`, `ok`, `error_class?`, `latency_ms?`) | Provider health |
| `admin.preset.applied` | A catalog preset is applied to an org (PRD-04) | generic dict (`preset`, `provider`) | Provider-config audit |

## Provider config lifecycle (4)

Immutable-history audit events (PRD-06) — loose reference dicts.

| Event | When | Payload | Consumed by |
|---|---|---|---|
| `llm_config.changed` | Org/agent model config (or pricing/headers) mutated | generic dict (`scope`, `change_kind`, …) | Config history, audit |
| `llm_config.rolled_back` | A config version is restored | generic dict (`scope`, `version_id`, `secret_requires_reentry`) | Config history, audit |
| `llm_config.imported` | A provider set is imported into the org | generic dict (`strategy`, `applied`) | Config history, audit |
| `llm_config.exported` | A provider set is exported | generic dict (`agent_overrides`, `has_org_default`) | Config history, audit |

## Budget (2)

| Event | When | Payload | Consumed by |
|---|---|---|---|
| `budget.configured` | An org sets/updates its monthly budget (PRD-07) | generic dict (`monthly_limit_usd`, `alert_pcts`) | Cost dashboard |
| `budget.threshold` | Month-to-date spend crosses a 50/80/100% threshold (fires once per org/month/pct) | `BudgetThresholdPayload` | Cost dashboard, budget banner |

## Persona prompts (4)

Prompt-override audit events (PRD-10) — loose reference dicts.

| Event | When | Payload | Consumed by |
|---|---|---|---|
| `prompt.activated` | An org activates a persona prompt override version | generic dict (`persona`, `version`) | Prompt history, audit |
| `prompt.deactivated` | An org reverts a persona to the packaged spec | generic dict (`persona`) | Prompt history, audit |
| `prompt_pack.exported` | Active prompt overrides are exported as a pack | generic dict (`personas`) | Prompt history, audit |
| `prompt_pack.imported` | A prompt pack is imported (as drafts) | generic dict (`personas`) | Prompt history, audit |

## MCP tools (1)

| Event | When | Payload | Consumed by |
|---|---|---|---|
| `tool.called` | An agent invokes a bound MCP tool (PRD-09) | `ToolCalledPayload` | Tool-use analytics, `pdlc.tool.*` spans |

## Evaluation (2)

| Event | When | Payload | Consumed by |
|---|---|---|---|
| `eval.scored` | An eval runs against an agent output / major step (Phase J) | `EvalScoredPayload` | Eval analytics, drift/regression |
| `eval.blocked` | A blocking eval failed its threshold and blocked an approval gate | `EvalBlockedPayload` | Eval analytics, quality audit |

---

**Total: 40 event types in 17 categories.**

Coverage map (every numbered step in every upstream skill emits at least one of: `step.completed`, `subphase.entered/exited`, `agent.invoked/responded`, `tool.invoked`, plus phase events at boundaries). See §15 verification in `docs/.research/.langgraph-bedrock-saas-migration-2026-06-05.md`.
