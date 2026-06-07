# pdlcflow

PDLC reimagined as a **LangGraph + AWS Bedrock SaaS** with a browser UI, Chainlit-inspired design system, pluggable LLM providers (7), and clickstream telemetry feeding an admin dashboard.

> **Status: v1.5.0** — all phases A–J + eval framework + multi-tenant auth/RLS (FORCE) + live token streaming. See [`CHANGELOG.md`](./CHANGELOG.md) for the release notes, [`STATUS.md`](./STATUS.md) for the per-phase checklist, the [Wiki](./docs/wiki/README.md) to install/use it, and [`docs/.research/.langgraph-bedrock-saas-migration-2026-06-05.md`](./docs/.research/.langgraph-bedrock-saas-migration-2026-06-05.md) for the architecture proposal (15 sections, 5 mermaid diagrams, 40-event taxonomy, 25-table Postgres schema, 7-provider LLM factory, 8-stack CDK topology).

## Relationship to upstream `pdlc`

[`pdlc-os/pdlc`](https://github.com/pdlc-os/pdlc) is the existing Claude-Code-bound npm plugin (`@pdlc-os/pdlc`, v2.24.0). `pdlcflow` is a **parallel-track** reimagination that lifts PDLC off Claude Code into a stand-alone runtime — Python LangGraph engine + React UI + AWS Bedrock + admin dashboard. The two repos are maintained as **siblings, not a fork**:

- Upstream `pdlc` remains the simplest path to PDLC on a single dev box.
- `pdlcflow` is the SaaS / multi-tenant / team-scale path.

Both stacks share the workflow (4 phases, ~17 slash commands, 10 personas, 8 approval gates, party meetings, 3-Strike escalation, `/night-shift` autonomous loop) and the agent soul-specs (verbatim copies of the upstream `agents/*.md` files live in `packages/pdlc-graph/pdlc_graph/personas/`).

## Repo layout

```
pdlcflow/
├── apps/
│   └── studio/                # React + Vite + Tailwind + shadcn/ui + Chainlit-inspired tokens
├── packages/
│   ├── event-schema/          # Pydantic envelope + 40-event taxonomy + registry doc
│   └── pdlc-graph/            # LangGraph engine: meta-graph, phase subgraphs, party meetings, personas, Sentinel evaluator
├── services/
│   └── pdlc-engine/           # FastAPI: routes, WS, clickstream, DB models, 7-provider LLM factory, Alembic
├── infra/
│   ├── compose/               # Docker Compose for self-host (single-tenant)
│   └── cdk/                   # AWS CDK for SaaS (multi-tenant), 8 stacks
├── tools/
│   └── pdlc-migrate/          # Typer CLI: scan / push / taxonomy / backfill
└── docs/
    └── .research/             # Architecture proposals
```

## Quickstart — deploy (no clone, one line)

Run from published GHCR images — just Docker. One command downloads the deploy files,
runs the interactive setup wizard, and brings the stack up (see [`deploy/`](./deploy/README.md)):

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/pdlc-os/pdlcflow/main/deploy/install.sh)"
```

Then open <http://localhost:8080> (Studio) / <http://localhost:8000/health> (API). Use the
`bash -c "$(curl …)"` form (not `curl | bash`) so the wizard can read your terminal.

## Quickstart — self-host (from source)

```bash
cd infra/compose
cp .env.example .env
# fill in PDLC_JWT_SECRET, AWS_* (if using Bedrock), etc.
docker compose up --build
```

Open <http://localhost:8080> for Studio. The engine listens on <http://localhost:8000> with `/health` for smoke checks.

## Quickstart — dev (Python)

```bash
uv sync
uv run pytest                                            # round-trip tests
uv run uvicorn app.main:app --reload --app-dir services/pdlc-engine
```

## Quickstart — dev (Studio)

```bash
pnpm install
pnpm --filter @pdlcflow/studio dev
```

Vite proxies `/v1/*` and `/ws/*` to `http://localhost:8000` so the engine and Studio can run side by side.

## Quickstart — deploy SaaS

```bash
cd infra/cdk
pnpm install
pnpm cdk bootstrap aws://<account>/us-east-1
pnpm cdk deploy --all
```

## Documentation

- **[Wiki](./docs/wiki/README.md)** — install, launch, use & monitor pdlcflow; the core PDLC flow + specialized flows (agents, party mode, night-shift, utilities, migration, evals), with mermaid diagrams.
- **[Deploy guide](./deploy/README.md)** — run from published images with no clone (`setup.sh` wizard).
- [Changelog](./CHANGELOG.md) · [Phase tracker](./STATUS.md)
- [Self-host README](./infra/compose/README.md) · [SaaS / CDK README](./infra/cdk/README.md)
- [Architecture proposal](./docs/.research/.langgraph-bedrock-saas-migration-2026-06-05.md) — 15 sections, 5 mermaid diagrams.

## License

MIT — see [`LICENSE`](./LICENSE).
