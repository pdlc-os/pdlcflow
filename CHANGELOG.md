# Changelog

All notable changes to pdlcflow are documented here. This project adheres to
[Semantic Versioning](https://semver.org/).

## v1.6.0 — 2026-06-06

Distribution, multi-cloud, provider-neutral model selection, and observability on top of
v1.5.0. All new capability is flag-gated and off by default; dev/CI stay hermetic.

### Distribution — deploy without cloning
- **Published container images** to GHCR (`pdlcflow-api`, `pdlcflow-studio`, multi-arch) via a
  `release-images` workflow, plus a standalone `deploy/docker-compose.yml`.
- **One-line installer** — `bash -c "$(curl … deploy/install.sh)"` downloads the files, runs an
  interactive **`setup.sh`** wizard (prompts + generates secrets → `.env`), brings the stack up,
  and migrates. Matching **`update.sh`** + **`uninstall.sh`** one-liners.

### Multi-cloud SaaS (Terraform)
- **`infra/terraform/`** — full-parity modules for **AWS, GCP, and Azure** mirroring the 8 CDK
  stacks (managed Postgres/Redis/object-storage, serverless containers, CDN, identity, event
  streaming, LLM access, secrets, logs). Validated with `tofu validate` (not deploy-tested).

### Provider-neutral model selection
- **Per-persona capability tiers wired** — agents declare a tier and `complete()` honors it
  (previously everything defaulted to the top tier). Tiers renamed to generic
  **`premium` / `balanced` / `economy`**; the `tier_map` auto-selects each provider's
  highest/general/economy model (Claude family keeps Opus/Sonnet/Haiku). Defaults set to the
  highest current model per provider (2026-06).
- **Per-tenant / per-agent overrides wired** (`org_llm_config` / `agent_llm_config` + the
  `/v1/admin/models/*` API), verified against real Postgres.
- **Credentials as config for every provider** — direct-API providers fall back to their env key
  (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY` / `AZURE_OPENAI_*`), Bedrock/Vertex
  use the cloud SDK chains; the install wizard now covers all **7** providers.

### Observability — human vs agent work
- Every event tagged **`actor_type`** (human / agent / system). New **Work Narrative**
  (`GET /v1/admin/narrative` + a Nexus Console view): a date window → stats + an LLM-written
  story separating human (Studio) work from autonomous agent work.

### Security
- **Artifact tenant isolation** — artifacts namespaced `{org_id}/{project_id}/{path}` with the
  org bound from the turn context + path-traversal guards (the file-layer analogue of RLS).

### Naming / docs
- **Atlas Console → Nexus Console** (the admin dashboard) to avoid confusion with the Atlas
  agent. Professional, provider-neutral README; expanded wiki.

### Engineering
- ~234 hermetic tests + live integration (Postgres/Redis/MinIO + RLS + overrides + narrative);
  CI green (python ×4, node ×2, evals, integration). Multi-cloud Terraform `tofu validate`.

### Known limitations
- Multi-cloud Terraform is validated, not deploy-tested. Per-tenant `secret_ref` →
  secrets-manager resolution, OIDC auth on GCP/Azure, Azure Blob artifact adapter, and native
  Pub/Sub / Event Hubs clickstream sinks remain documented follow-ons.

## v1.5.0 — 2026-06-06

Adds an evaluation framework and completes the multi-tenant auth + RLS hardening on top of
v1.0.0. All new capability is **flag-gated and off by default**, so dev/CI stay hermetic.

### Evals (Phase J)
- **Eval framework** (`pdlc_graph/evals/`): a registry + runner + an injectable **LLM-as-judge**
  seam (deterministic stub for CI; factory-backed real judge at a configurable tier). Scores
  agent output at major steps and emits `eval.scored` / `eval.blocked` events (taxonomy → **40**),
  surfaced at `GET /v1/admin/evals/summary`. Measure-only by default; per-eval **opt-in blocking**.
- **Evals shipped**: per-agent output quality, groundedness/hallucination, citation,
  faithful-relay, drift/regression, **spec-adherence**, and **prod-safety**.
- **Golden suite + drift** + a **nightly real-LLM eval** workflow (provider-flexible:
  Bedrock/Anthropic/OpenAI/Gemini via a repo variable; credential-guarded). Hermetic `evals` CI job.

### Live token streaming
- `PDLC_STREAM_TOKENS` streams `token` frames (start/chunk/done) from the LLM port to the thread
  channel; the Studio renders a transient live **"drafting" preview**. Stub-chunked for dev; real
  via `model.stream()`.

### Auth + RLS (defense in depth)
- **Phase 1 — auth enforcement** (`PDLC_AUTH_REQUIRED`): Bearer-JWT on protected routes + the WS,
  **org derived from the token**, admin roles, login + env-bootstrapped first admin.
- **Phase 2 — Studio login**: login overlay, token on REST + WS, org bound to the principal.
- **Phase 3 — RLS FORCE**: app connects as a non-superuser role; `FORCE ROW LEVEL SECURITY` on
  tenant-content tables; org threaded through every query. **Phase 3.1** locks `org_members` too
  via a `SECURITY DEFINER` login function. Verified against real Postgres.

### Infra / build
- Compose wires the streaming + real-eval paths for local validation (incl. an `evals` one-shot
  profile + a MinIO/non-owner-role setup); **engine + studio Dockerfiles fixed** and now build
  reproducibly (engine COPY/`uv sync`; **studio on pnpm@9.12.0 via corepack + frozen lockfile**).
- Node CI fixed (pnpm version pin); a **docker-compose integration CI job** exercises the real
  Postgres/Redis/MinIO + RLS paths on every push.

### UI
- 3-way theme toggle (light → dark → **system**).

### Engineering
- ~217 hermetic tests + a live integration suite (Postgres/Redis/MinIO + RLS); CI green
  (python ×4, node ×2, evals, integration). 17-page operator [Wiki](./docs/wiki/README.md).

### Known limitations / deferred
- **Auth + RLS are opt-in** (default off) — turn on `PDLC_AUTH_REQUIRED` + the `pdlc_app`
  connection for a hardened multi-tenant deployment.
- The eval **stub judge** is a placeholder; real scores need `PDLC_RUN_EVALS` + `PDLC_WIRE_LLM`
  + provider credentials. `drift` uses word-overlap (swap in embeddings for semantic drift).
- Cognito/OIDC SSO is scaffolded; rotate the `pdlc_app` dev password before real use.

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
- **Studio** (React + Vite) — chat, gates, visual companion, mission control, Nexus Console.
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
