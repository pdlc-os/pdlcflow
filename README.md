<p align="center">
  <img src="apps/studio/public/pdlcflow.png" alt="pdlcflow" width="440" />
</p>

# pdlcflow

**Run your product development lifecycle as a team of AI agents — from raw idea to shipped feature.**

pdlcflow is an open-source, multi-tenant platform that turns a structured Product Development
Lifecycle (PDLC) into a browser-based, multi-agent system. A cast of specialized AI agents
moves each feature through **brainstorm → build → ship**, with human approval gates, persistent
memory, automatic quality evaluation, and full audit telemetry. It runs on **your choice of
LLM provider** — with per-tenant keys (BYOK), a one-click provider console, automatic failover,
cost budgets, and optional external tools for agents (MCP) — self-hosted or as multi-tenant SaaS
on **AWS, GCP, or Azure**, with tenant isolation enforced at the database.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
[![Release](https://img.shields.io/github/v/release/pdlc-os/pdlcflow?sort=semver)](https://github.com/pdlc-os/pdlcflow/releases)
[![CI](https://github.com/pdlc-os/pdlcflow/actions/workflows/ci.yml/badge.svg)](https://github.com/pdlc-os/pdlcflow/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Built with LangGraph](https://img.shields.io/badge/built%20with-LangGraph-1c3c3c.svg)](https://github.com/langchain-ai/langgraph)

---

## Table of contents

- [Why pdlcflow](#why-pdlcflow)
- [Highlights](#highlights)
- [Bring your own LLM](#bring-your-own-llm)
- [Architecture](#architecture)
- [Quickstart](#quickstart)
- [Configuration](#configuration)
- [Documentation](#documentation)
- [Relationship to upstream `pdlc`](#relationship-to-upstream-pdlc)
- [Repository layout](#repository-layout)
- [Testing & CI](#testing--ci)
- [Contributing](#contributing)
- [Security](#security)
- [License](#license)

## Why pdlcflow

Most "AI coding" tools help with a single step. pdlcflow operationalizes the **whole
lifecycle**: it encodes a proven, phase-based methodology — discovery, definition, design,
build, review, and ship — and runs it as a coordinated team of role-specialized agents with
the guardrails a real organization needs.

- **For leaders:** a consistent, auditable path from idea to production. Every decision, gate,
  and agent action is captured as clickstream telemetry and surfaced in an admin dashboard, so
  you can see cost, throughput, and quality across teams — with cost controls and
  human-in-the-loop approvals built in.
- **For engineers:** a hackable, well-tested runtime. A Python [LangGraph](https://github.com/langchain-ai/langgraph)
  engine, a FastAPI service, and a React UI — all behind clean, swappable ports (LLM, storage,
  queue, telemetry) so you can run it on a laptop or scale it to a multi-tenant SaaS.

## Highlights

- **End-to-end lifecycle** — four phases, ~17 commands, and **10 specialized agent personas**
  collaborating through the work, including multi-agent **"party" meetings** for divergent
  ideation and adversarial review.
- **Human-in-the-loop governance** — **8 approval gates**, a Socratic interaction mode, and a
  **3-Strike escalation** protocol keep humans in control of consequential decisions.
- **Autonomy when you want it** — a `/night-shift` loop advances work unattended within
  guardrails, with episode reports for everything it did.
- **Bring your own LLM** — an 8-provider factory (Bedrock, Anthropic, OpenAI, Google Gemini,
  Vertex AI, Azure OpenAI, Ollama, plus a generic **OpenAI-compatible** provider for any
  gateway/relay or local server) selectable per deployment, with a deterministic offline stub
  for hermetic dev and CI.
- **Provider management, built for tenants** — a **Provider Settings console** to switch
  providers and models in a click; **BYOK** per-org/per-agent API keys (write-only, resolved
  server-side, fail-closed); a **preset catalog** (OpenRouter, DeepSeek, Kimi, GLM, SiliconFlow,
  LiteLLM, vLLM…) for one-minute onboarding; **pre-save connectivity probes** that catch a bad
  key or model before it breaks a turn; and immutable **config versioning** with one-click
  rollback and org-to-org export/import.
- **Resilient by default** — org-level **failover chains** with a Redis **circuit breaker**
  turn a provider incident into a logged fallback instead of a broken turn, plus per-org **rate
  limiting** — all fail-open so the resilience layer never becomes the outage.
- **Cost control** — per-org **pricing overrides** on a versioned price catalog, monthly
  **budgets** with soft threshold alerts, and real per-completion spend telemetry (estimates for
  dashboards, never billing).
- **Customizable agents** — org-level **persona prompt overrides** (immutable versions,
  one-click activate/rollback) and portable **prompt packs**; optional **MCP tool servers** give
  agents external tools (docs search, ticket lookup, …) with deny-all allowlists, persona/phase
  bindings, and a hard multi-tenant security boundary.
- **Enterprise egress** — explicit outbound **proxy / CA-bundle / custom-header** controls for
  air-gapped and TLS-inspecting environments.
- **Quality you can measure** — a built-in **evaluation harness** scores agent output at major
  steps: per-agent quality, groundedness / hallucination, citation & faithful-relay, spec
  adherence, production-safety, plus drift/regression tracking and nightly real-LLM evals.
- **Multi-tenant by design** — JWT authentication, role-based admin, and **PostgreSQL
  Row-Level Security (FORCE)** so tenant isolation is enforced by the database — not just the
  app. Artifacts (PRDs, design docs, reviews) are namespaced per tenant.
- **Observability built in** — a 50+-event clickstream taxonomy (every event tagged
  human / agent / system) feeds analytics and the **Nexus Console** admin dashboard:
  live runs, cost/usage rollups, per-agent metrics, and a **Work Narrative** that turns a
  date window into stats + an LLM story of what humans vs agents did. Opt-in **OpenTelemetry**
  traces + metrics export to Grafana/Tempo/Prometheus with a Streamlit ops dashboard.
- **Live experience** — a React **Studio** with real-time WebSocket updates and live token
  "drafting" previews.
- **Organized like a real org** — a first-class hierarchy: **Org → Domain → Squad → GitHub
  repos**, squads ↔ initiatives (many-to-many), cross-org **Programs**, and **projects** that
  group **conversations**, all tenant-isolated. ([data model](./docs/wiki/18-data-model.md))
- **Feels like a chat app** — a multi-line composer with slash-command autocomplete,
  **conversation history**, **drag-and-drop file attachments** (text/pdf/docx/xlsx/pptx have
  their content folded into the working agent's context), and a **repo-backed memory** browser
  that reads the connected repository's files.
- **Secrets done right** — per-repo VCS tokens via a pluggable backend: encrypted-in-DB
  (self-host default) or **HashiCorp Vault** (bundled, opt-in) / cloud secrets managers.
- **Deploy anywhere** — one-line install from published container images, a `pdlcflow` control
  CLI (`setup`/`start`/`stop`/`status`/`remove`/`wipe`), Docker Compose for self-host, or
  multi-tenant SaaS on **AWS, GCP, or Azure** (full-parity Terraform modules; plus an
  AWS-native CDK).
- **Migration tooling** — a CLI to scan, map, and back-fill from an existing PDLC setup.

## Bring your own LLM

pdlcflow is **provider-neutral**. Persona completions, the eval judge, and token streaming all
flow through one pluggable LLM factory; pick the instance default with a single setting
(`PDLC_DEFAULT_LLM_PROVIDER`), or let each org pick its own from the **Provider Settings
console** and bring its own key.

| Provider | Key | Notes |
| --- | --- | --- |
| **AWS Bedrock** | `bedrock` | Default; uses your AWS credentials/region |
| **Anthropic** | `anthropic` | Direct Claude API |
| **OpenAI** | `openai` | GPT models |
| **Google Gemini** | `gemini` | Gemini API |
| **Google Vertex AI** | `vertex` | Gemini/Claude on GCP |
| **Azure OpenAI** | `azure` | Azure-hosted OpenAI |
| **Ollama** | `ollama` | Local / air-gapped models |
| **OpenAI-compatible** | `openai_compatible` | Any OpenAI-protocol gateway/relay or local server (OpenRouter, DeepSeek, Kimi, GLM, SiliconFlow, LiteLLM, vLLM…) via a custom base URL — no per-vendor code |

Agents stay provider-neutral by declaring a **capability tier** (`premium` = highest
capability, `balanced` = general purpose, `economy` = low token / fast) rather than a model.
The factory maps the tier to the right model for the active provider — Anthropic-family
providers keep real Opus/Sonnet/Haiku, while OpenAI/Gemini auto-select their
highest/general/economy equivalent — so switching providers preserves each agent's intended
capability level. Defaults are overridable per tenant or per agent (see the
[configuration guide](./docs/wiki/03-configuration.md#per-agent-model-tiers-provider-neutral)).

**Per-tenant provider management** (all org-scoped, RLS-isolated, versioned): each org sets its
own provider + model tiers and **brings its own API key** (write-only, stored via the pluggable
secrets backend, resolved server-side and fail-closed — a broken key errors rather than silently
billing the operator). Start from the **preset catalog**, hit **Test** to validate connectivity
before saving, declare a **failover chain** so incidents degrade gracefully, and set a monthly
**budget**. Every change is an immutable version you can roll back or export to another org. See
the [configuration guide](./docs/wiki/03-configuration.md).

Leave the LLM unwired (`PDLC_WIRE_LLM=false`, the default) and pdlcflow runs against a
deterministic offline stub — so the full stack boots, tests, and demos with **no credentials**.

**Single-user self-host** can also bill against a **Claude Pro/Max, ChatGPT, or Google
subscription** instead of an API key, by shelling out to the locally-installed `claude` / `codex`
/ `gemini` CLI (`PDLC_DEFAULT_LLM_PROVIDER=claude_code|codex|gemini_cli`, opt-in via
`PDLC_ENABLE_CLI_PROVIDERS=true`). Refused when auth/multi-tenant is on — see the
[configuration guide](./docs/wiki/03-configuration.md#subscription-clis-single-user-self-host-only).

## Architecture

```mermaid
flowchart LR
  U["Browser · Studio<br/>(React + Vite)"] -->|REST + WebSocket| API["pdlc-engine<br/>FastAPI"]
  API --> G["pdlc-graph<br/>LangGraph meta-graph"]
  G --> P["Phase subgraphs · 10 personas<br/>party mode · Sentinel evaluator"]
  G --> MCP["Tool port<br/>MCP servers (opt-in)"]
  API --> LLM{"LLM factory<br/>8 providers · BYOK<br/>failover · circuit breaker"}
  LLM --> PROV["Bedrock · Anthropic · OpenAI · Gemini<br/>Vertex · Azure · Ollama · OpenAI-compatible"]
  API --> EV["Eval harness<br/>LLM-as-judge"]
  API --> PG[("PostgreSQL<br/>RLS + graph checkpoints")]
  API --> RD[("Redis<br/>event bus · queue · breaker")]
  API --> OBJ[("S3 / MinIO<br/>tenant-namespaced artifacts")]
  API --> CS["Clickstream<br/>50+-event taxonomy"] --> AD["Nexus Console<br/>admin dashboard"]
  API -.OTel.-> OT["Grafana · Tempo<br/>Prometheus (opt-in)"]
```

Every side effect sits behind an injectable port with an in-memory default, so the system is
fully testable without external services and each backend (Postgres, Redis, S3, the LLM) can
be swapped or stubbed independently.

## Quickstart

### Deploy — no clone, one line

Run from published container images with just Docker. The installer downloads the deploy
files, runs an interactive setup wizard (prompts + generates secrets), and brings the stack up:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/pdlc-os/pdlcflow/main/deploy/install.sh)"
```

Then open <http://localhost:8080> (Studio) and <http://localhost:8000/health> (API). Use the
`bash -c "$(curl …)"` form (**not** `curl | bash`) so the wizard can read your terminal.
The installer also adds a **`pdlcflow`** command to control the stack from anywhere —
`pdlcflow setup | start | stop | status | remove | wipe`. Update and uninstall use the same
one-line pattern — see the [deploy guide](./deploy/README.md).

### Self-host from source

```bash
cd infra/compose
cp .env.example .env          # set PDLC_JWT_SECRET; pick a provider + creds if wiring an LLM
docker compose up --build
```

### Develop

```bash
# Engine + graph (Python 3.12, uv workspace)
uv sync
uv run pytest
uv run uvicorn app.main:app --reload --app-dir services/pdlc-engine

# Studio (Node 20, pnpm)
pnpm install
pnpm --filter @pdlcflow/studio dev   # proxies /v1 and /ws to http://localhost:8000
```

### Deploy SaaS (AWS, GCP, or Azure)

Multi-cloud Terraform (full-parity modules per cloud) lives in
[`infra/terraform/`](./infra/terraform/README.md):

```bash
cd infra/terraform/modules/<aws|gcp|azure>
terraform init && terraform apply -var-file=../../example.tfvars
```

Or the AWS-native CDK ([`infra/cdk/`](./infra/cdk/README.md)):

```bash
cd infra/cdk && pnpm install && pnpm cdk bootstrap aws://<account>/<region> && pnpm cdk deploy --all
```

## Configuration

pdlcflow is configured entirely through environment variables (see
[`deploy/.env.example`](./deploy/.env.example) and the
[configuration guide](./docs/wiki/03-configuration.md)). Highlights:

| Setting | Purpose |
| --- | --- |
| `PDLC_DEFAULT_LLM_PROVIDER` / `PDLC_WIRE_LLM` | Choose the LLM provider; wire real models (else offline stub) |
| `PDLC_AUTH_REQUIRED` | Enforce JWT auth; derive tenant from the token |
| `PDLC_DB_URL` / `PDLC_MIGRATION_DB_URL` | App connects as a non-superuser role (RLS); migrations run as owner |
| `PDLC_SECRETS_BACKEND` / `PDLC_SECRET_KEY` | Where tenant API keys (BYOK) live: encrypted-in-DB, Vault, or env |
| `PDLC_RATE_LIMIT_ENABLED` / `PDLC_EGRESS_PROXY_URL` | Per-org RPM limiting; outbound proxy for LLM egress |
| `PDLC_RUN_EVALS` / `PDLC_EVAL_BLOCKING` | Score agent output; optionally block on failures |
| `PDLC_OTEL_ENABLED` / `PDLC_WIRE_MCP` | Export OpenTelemetry traces/metrics; enable MCP tool servers for agents |
| `PDLC_STREAM_TOKENS` | Live token streaming to the Studio |

Sensible defaults keep dev hermetic; every backend gracefully falls back to in-memory until
you opt in.

## Documentation

- **[Onboarding](./docs/onboarding/README.md)** — the fast on-ramp for teams adopting pdlcflow:
  greenfield vs brownfield setup, a step-by-step walkthrough, the day-two `/brainstorm → /build
  → /ship` loop, bug-fixing, shipping, and a one-page [visual journey](./docs/onboarding/journey.html).
- **[Wiki](./docs/wiki/README.md)** — install, launch, use & monitor pdlcflow; the core PDLC
  flow and the specialized flows (agents, party mode, night-shift, utilities, migration,
  evals), with diagrams.
- **[Provider management & resilience](./docs/wiki/03-configuration.md)** — BYOK, the preset
  catalog + OpenAI-compatible gateways, connectivity probes, failover/rate-limits, config
  versioning & promotion, pricing overrides & budgets, egress controls.
- **[Observability](./docs/wiki/19-observability.md)** · **[MCP Tool Servers](./docs/wiki/20-mcp-tools.md)** — OpenTelemetry/Grafana stack; external tools for agents.
- **[Deploy guide](./deploy/README.md)** — install / update / uninstall from published images.
- **[Configuration](./docs/wiki/03-configuration.md)** · **[Changelog](./CHANGELOG.md)** · **[Phase tracker](./STATUS.md)**
- **[Self-host README](./infra/compose/README.md)** · **[Multi-cloud Terraform (AWS/GCP/Azure)](./infra/terraform/README.md)** · **[SaaS / CDK README](./infra/cdk/README.md)**
- **[Architecture proposal](./docs/.research/.langgraph-bedrock-saas-migration-2026-06-05.md)** — the full design (15 sections, mermaid diagrams, event taxonomy, schema, provider factory, CDK topology).

## Relationship to upstream `pdlc`

[`pdlc-os/pdlc`](https://github.com/pdlc-os/pdlc) is the original Claude-Code-bound plugin
(`@pdlc-os/pdlc`). **pdlcflow is a parallel-track reimagination** that lifts the same
methodology off Claude Code into a standalone runtime — a Python LangGraph engine, a React UI,
multi-provider LLMs, and an admin dashboard. The two are maintained as **siblings, not a fork**:

- Upstream `pdlc` is the simplest path to PDLC on a single developer's machine.
- pdlcflow is the team-scale, multi-tenant, self-hostable path.

Both share the workflow (4 phases, ~17 commands, 10 personas, 8 gates, party meetings,
3-Strike escalation, the night-shift loop) and the agent soul-specs — the persona definitions
are carried over verbatim into `packages/pdlc-graph/pdlc_graph/personas/`.

## Repository layout

```
pdlcflow/
├── apps/
│   └── studio/          # React + Vite + Tailwind + shadcn/ui front end
├── packages/
│   ├── event-schema/    # Pydantic event envelope + 50+-event taxonomy
│   └── pdlc-graph/      # LangGraph engine: meta-graph, phase subgraphs, personas, party mode, evals
├── services/
│   └── pdlc-engine/     # FastAPI: REST + WebSocket, clickstream, DB models, 8-provider LLM factory (BYOK, failover, presets), MCP tool backend, Alembic
├── infra/
│   ├── compose/         # Docker Compose (self-host, single-tenant)
│   ├── terraform/       # Multi-cloud SaaS IaC — full-parity AWS / GCP / Azure modules
│   └── cdk/             # AWS CDK (SaaS, multi-tenant) — 8 stacks
├── tools/
│   └── pdlc-migrate/    # CLI: scan / push / taxonomy / backfill
├── deploy/              # No-clone deploy: published images + install/update/uninstall scripts
└── docs/                # Wiki + architecture research
```

## Testing & CI

- **~380 hermetic tests** (no external services) plus a live integration suite that exercises
  the real Postgres / Redis / MinIO adapters and Row-Level Security.
- GitHub Actions runs Python (×4 workspace members), Node (Studio + CDK), the eval suite, and
  a docker-compose integration job on every push.
- The full stack runs offline against in-memory backends and the deterministic LLM stub.

## Contributing

Issues and pull requests are welcome. Before opening a PR, run the checks CI enforces:
`uv run pytest` and `uv run ruff check` for the Python workspace, and
`pnpm --filter @pdlcflow/studio lint typecheck` for the Studio. CI must be green to merge.
See the [wiki](./docs/wiki/README.md) for architecture and development guidance.

## Security

pdlcflow ships multi-tenant controls (JWT auth, PostgreSQL Row-Level Security, tenant-namespaced
artifacts), all opt-in via configuration. If you discover a vulnerability, please open a
security advisory rather than a public issue. Rotate the sample credentials in
`deploy/.env.example` before any real deployment.

## License

MIT — see [`LICENSE`](./LICENSE).
