# Changelog

All notable changes to pdlcflow are documented here. This project adheres to
[Semantic Versioning](https://semver.org/).

## v1.0.0 — 2026-06-06

First stable release. pdlcflow is PDLC (the Product Development Lifecycle) reimagined as a
stand-alone **LangGraph + AWS Bedrock SaaS** — a browser-driven, multi-agent software
development lifecycle with pluggable LLM providers, clickstream telemetry, an admin
dashboard, autonomous runs, and an evaluation framework. Runs self-host via Docker Compose.

### Highlights

- **Full PDLC lifecycle** as a LangGraph meta-graph — Inception → Construction → Operation,
  with 8 human approval gates, Sketch/Socratic interaction, and a visual companion in the
  same browser view.
- **10-agent team** (personas with model tiers + always-on reviewers) and **party mode**
  — 7 party types (progressive-thinking, threat-model, design-laws, wave-kickoff,
  design-roundtable, party-review, strike-panel) with triage + minutes-of-meeting.
- **Night-Shift** autonomous runtime — one human Contract gate, a deterministic Sentinel
  evaluator, live verdict streaming to mission control, and a 3-layer production-deploy ban.
- **Utility commands** — `/decide /doctor /whatif /pause /resume /abandon /release /override
  /rollback /hotfix`.
- **Studio** (React + Vite) — chat, gates, visual companion, mission control, Atlas Console.
- **Telemetry & analytics** — a 40-event taxonomy with tenancy + feature-traceability
  dimensions (roadmap/PRD/user-story/plan-step), org-scoped rollups, cross-org ban.
- **Self-host production stack** — PostgresSaver checkpointer, Arq dispatch, Redis pub/sub
  bus, filesystem/S3·MinIO artifacts, Postgres task store + analytics, Alembic schema + RLS
  policies. Every backend flag-gated with an in-memory fallback.
- **Migration tooling** — scan / push / taxonomy / backfill an upstream `pdlc` project so
  the dashboards are non-empty on day one.
- **Eval framework** — per-agent output scoring, groundedness/faithfulness, citation +
  faithful-relay, spec-adherence, prod-safety, drift/regression, LLM-as-judge (factory
  judge + deterministic stub), measure-only by default with opt-in blocking, an eval CI
  job, and a nightly real-LLM run with drift tracking.

### Build phases (see [`STATUS.md`](./STATUS.md))

- **A** Foundations — monorepo, event schema, CI scaffold.
- **B** Inception loop — Discover/Define/Design/Plan graph.
- **C** Construction loop — TDD build loop, 3-Strike → Strike Panel, 7 test layers.
- **D** Operation loop — Ship/Verify/Reflect, semver, deploy, prod-deploy ban.
- **E** Utilities — the 10 utility commands.
- **F** Night-Shift — autonomous runtime + mission-control panel.
- **G** Admin dashboard + analytics pipeline.
- **H** SaaS hardening — durability, live streaming, persistence, migrations + RLS;
  docker-compose integration CI.
- **I** Migration tooling.
- **J** Eval framework (+ spec-adherence/prod-safety evals + nightly drift).

### Engineering

- ~203 hermetic tests across the workspace + 6 docker-compose integration tests; CI green
  (python × 4, node × 2, evals, integration).
- 17-page operator [Wiki](./docs/wiki/README.md) with mermaid diagrams.

### Known limitations / deferred

- **Auth is deferred** — the API is open (no JWT/Cognito enforcement yet).
- **RLS is enabled but not FORCEd** (the app connects as table owner); full enforcement
  needs a non-owner DB role + org threaded through the remaining reads.
- The **eval stub judge** is a deterministic placeholder; real scoring needs
  `PDLC_RUN_EVALS=true` + `PDLC_WIRE_LLM=true` + provider credentials. `drift` uses
  word-overlap (swap in embeddings for semantic drift).
- Live token streaming into the Studio transcript and the SaaS-only items (SSO, per-tenant
  KMS, ClickHouse, multi-AZ) are scaffolded/documented, not wired.
