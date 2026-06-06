<!-- nav:top -->
[🏠 Wiki Home](README.md)

# Configuration

All engine configuration is environment-driven through Pydantic settings with the `PDLC_` prefix (`services/pdlc-engine/app/config.py`). Values are read from the process environment and from a `.env` file; unknown keys are ignored (`extra="ignore"`). The compose stack passes `.env` to the `api` and `worker` containers via `env_file`.

## Environment variables

| Variable | Default | Effect |
|----------|---------|--------|
| `PDLC_ENVIRONMENT` | `dev` | Service environment: `dev` \| `staging` \| `prod`. |
| `PDLC_LOG_LEVEL` | `info` | `debug` \| `info` \| `warning` \| `error`. |
| `PDLC_DB_URL` | `postgresql+asyncpg://postgres:pdlc@localhost:5432/pdlc` | SQLAlchemy async DB URL. The Postgres checkpointer/task-store/analytics derive their sync `psycopg` connection from this. |
| `PDLC_REDIS_URL` | `redis://localhost:6379/0` | Redis DSN — used by the Redis event bus and the Arq queue. |
| `PDLC_AUTH_MODE` | `local` | `local` (self-host JWT) \| `cognito` (SaaS). Auth enforcement is currently deferred (open API). |
| `PDLC_JWT_SECRET` | `change-me-in-production` | HS256 signing secret — **set this in any real deployment**. |
| `PDLC_JWT_ALG` | `HS256` | JWT algorithm. |
| `PDLC_JWT_TTL_S` | `43200` | Token TTL in seconds (12 h). |
| `PDLC_DEFAULT_LLM_PROVIDER` | `bedrock` | One of `bedrock` \| `anthropic` \| `vertex` \| `azure` \| `openai` \| `gemini` \| `ollama`. Selects the provider in the LLM factory. |
| `PDLC_BEDROCK_REGION` | `us-east-1` | AWS region for Bedrock (and reused as the S3 region). |
| `PDLC_OLLAMA_ENDPOINT` | `http://localhost:11434` | Ollama base URL for air-gapped local models. |
| `PDLC_WIRE_LLM` | `false` | When **off**, persona completions run on the deterministic **offline stub**. When **on**, completions route through the provider factory (needs credentials). |
| `PDLC_USE_POSTGRES_CHECKPOINTER` | `false` | When on, graph state uses a pooled `PostgresSaver` (durable, multi-process). Off → in-process `MemorySaver`. |
| `PDLC_PG_POOL_MAX_SIZE` | `20` | Max connections in the PostgresSaver pool. |
| `PDLC_USE_ARQ_DISPATCH` | `false` | When on, graph turns are enqueued to the Arq worker instead of running inline in the API. Requires the Redis bus for pending delivery. |
| `PDLC_USE_REDIS_BUS` | `false` | When on, WebSocket fan-out (and live night-shift verdicts) go over Redis pub/sub. Off → in-process in-memory bus. Required if `USE_ARQ_DISPATCH=true`. |
| `PDLC_ARTIFACT_STORE` | `memory` | `memory` \| `filesystem` \| `s3`. Where PRD/design/review docs + memory bodies are written. |
| `PDLC_ARTIFACT_DIR` | `/var/lib/pdlcflow/artifacts` | Base path for the filesystem artifact store (mounted volume in compose). |
| `PDLC_S3_ENDPOINT_URL` | `null` | Custom S3 endpoint, e.g. `http://minio:9000` for MinIO. |
| `PDLC_S3_ARTIFACTS_BUCKET` | `pdlcflow-artifacts-dev` | Bucket name for the S3 artifact store. |
| `PDLC_S3_EVENTS_BUCKET` | `pdlcflow-events-dev` | Bucket name for event archives (SaaS pipeline). |
| `PDLC_TASK_STORE` | `memory` | `memory` \| `postgres`. The durable Beads-replacement task store. |
| `PDLC_ANALYTICS_BACKEND` | `memory` | `memory` \| `postgres`. Backs the admin rollups. In-memory is per-process. |
| `PDLC_CLICKSTREAM_SINK` | `jsonl` | `jsonl` \| `postgres` \| `firehose`. The durable event sink. |
| `PDLC_FIREHOSE_STREAM_NAME` | `null` | Kinesis Firehose stream (SaaS telemetry pipeline). |
| `PDLC_CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed CORS origins for the API. |

> AWS credentials (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`) are read by boto3 directly — only needed when using Bedrock, Firehose, or real S3.

## In-memory vs real backend matrix

Each seam is independently switchable. The left column is the dev/test default; the right is the self-host (Postgres/Redis/MinIO) production shape.

| Seam | Flag | In-memory default | Real backend |
|------|------|-------------------|--------------|
| Graph checkpointer | `PDLC_USE_POSTGRES_CHECKPOINTER` | `MemorySaver` (in-process) | `PostgresSaver` (durable, shared across API + worker) |
| Command dispatch | `PDLC_USE_ARQ_DISPATCH` | inline (synchronous, in-API) | `ArqDispatcher` → Redis queue → worker |
| Event bus | `PDLC_USE_REDIS_BUS` | `InMemoryEventBus` (in-process) | `RedisEventBus` (pub/sub, cross-process WS) |
| Artifact store | `PDLC_ARTIFACT_STORE` | `memory` | `filesystem` (volume) or `s3`/MinIO |
| Task store | `PDLC_TASK_STORE` | `memory` | `postgres` (`tasks` table, atomic claim) |
| Analytics store | `PDLC_ANALYTICS_BACKEND` | `memory` (per-process) | `postgres` (SQL rollups over `events`) |
| Clickstream sink | `PDLC_CLICKSTREAM_SINK` | `jsonl` | `postgres` (durable rows) or `firehose` (SaaS) |
| LLM completions | `PDLC_WIRE_LLM` | offline stub (deterministic) | provider factory (`PDLC_DEFAULT_LLM_PROVIDER`) |

## Self-host vs SaaS profiles

- **Self-host** — the `.env.example` profile: Postgres checkpointer + task store + analytics + clickstream, Redis bus, filesystem (or MinIO) artifacts, `auth_mode=local`. Everything runs in the compose stack on one host.
- **Dev / hermetic** — leave the flags off: every seam is in-memory, no external infra, `PDLC_WIRE_LLM=false`. This is what the test suite and `uvicorn --reload` use.
- **SaaS** — `auth_mode=cognito`, `clickstream_sink=firehose`, S3 artifacts/events buckets, Bedrock provider, and the CDK-provisioned multi-tenant infrastructure (`infra/cdk/`). The same flags select the cloud-backed adapters.

## Authentication (Phase 1 — flag-gated)

Auth is **enforced only when `PDLC_AUTH_REQUIRED=true`** (default off = open API). When on:

- Protected routes (`/v1/commands`, `/v1/approval-gates`, `/v1/admin/*`, `/v1/migrate/import`) and the thread WebSocket require a **Bearer JWT** (`?token=` for the WS); missing/invalid → **401**.
- **`org_id` is derived from the token**, not the request — a mismatched `org_id` is rejected (**403**), and admin/analytics routes require the **admin**/**owner** role.
- **First user**: set `PDLC_BOOTSTRAP_ADMIN_EMAIL` + `PDLC_BOOTSTRAP_ADMIN_PASSWORD` — on boot, if no users exist, an org + admin user are created. Then:

  ```bash
  curl -X POST localhost:8000/v1/auth/login -d '{"email":"...","password":"..."}' -H 'content-type: application/json'
  # → {"access_token":"…","identity":{…}}   then send  Authorization: Bearer <token>
  ```

  Create more users via the admin-only `POST /v1/auth/users`. Accounts live in the user store (in-memory in dev/test; Postgres `users`/`org_members` when `PDLC_TASK_STORE=postgres`). `PDLC_AUTH_MODE=cognito` (SSO) is scaffolded for a later phase.

> Auth asserts the principal at the app layer; **RLS FORCE** (a future phase) makes Postgres enforce the same org boundary at the wire. They compose — auth is the trustworthy source of `org_id` that RLS keys on.

## The "always falls back to in-memory" safety note

Wiring is defensive: `wire_persistence`, `build_checkpointer`, `wire_event_bus`, and `wire_dispatcher` each try to construct the configured real backend and **fall back to the in-memory default if its infrastructure is unreachable** — logging a warning rather than crashing. So:

- The engine **always boots**, even with a bad `PDLC_DB_URL` or no Redis.
- Misconfiguration degrades a feature (e.g. checkpoints become non-durable) instead of taking the service down.
- Watch the startup logs (`docker compose logs -f api`) for lines like `PostgresSaver unavailable (...); falling back to MemorySaver` to confirm a real backend actually engaged — a green boot does **not** by itself prove Postgres is wired.


---


---
<!-- nav:bottom -->
⏮ [First: Overview](01-overview.md) · ◀ [Prev: Installation](02-installation.md) · [🏠 Home](README.md) · [Next: Launching & Operating](04-launching.md) ▶ · [Last: Evals Framework](17-evals.md) ⏭
