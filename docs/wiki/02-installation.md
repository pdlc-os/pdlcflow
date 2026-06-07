<!-- nav:top -->
[🏠 Wiki Home](README.md)

# Installation

Three ways to run pdlcflow:

1. **Deploy from published images** (recommended — no clone) — `docker` + a few files from `deploy/`.
2. **Self-host from source** — clone + `docker compose up --build` (for local changes).
3. **Dev** (no Docker) — `uv` + `pnpm` for working on the code.

## Deploy from published images (no clone)

Run the whole stack from prebuilt **GHCR** images — you only need Docker (not the source).
This is the easiest way to stand up or distribute pdlcflow.

**One line** — downloads the deploy files, runs the setup wizard, brings the stack up:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/pdlc-os/pdlcflow/main/deploy/install.sh)"
```

Use the `bash -c "$(curl …)"` form (**not** `curl | bash`) so the wizard can read your
terminal. Options: `--no-start` (download + configure only) · `--dir=<path>` (install
location). Or do it by hand:

```bash
base=https://raw.githubusercontent.com/pdlc-os/pdlcflow/main/deploy
mkdir pdlcflow && cd pdlcflow
curl -fsSLO $base/docker-compose.yml
curl -fsSL  $base/setup.sh -o setup.sh && chmod +x setup.sh
mkdir -p postgres-init && curl -fsSL $base/postgres-init/01-app-role.sh -o postgres-init/01-app-role.sh

./setup.sh                  # interactive: prompts for the few real choices, generates
                            # secrets (JWT + DB passwords), writes .env. No hand-editing.
docker compose up -d
docker compose run --rm api uv run alembic upgrade head
```

Then open **http://localhost:8080** (Studio) and **http://localhost:8000/health** (API).
`setup.sh` asks only: image version · require-login (+ bootstrap admin) · real LLM provider +
credentials · run evals — everything else is defaulted. Prefer manual config? `curl` the
`.env.example`, copy to `.env`, edit, and `docker compose up -d`. Pin a release with
`PDLCFLOW_VERSION=1.5.0` in `.env`. Full details: [`deploy/README.md`](https://github.com/pdlc-os/pdlcflow/blob/main/deploy/README.md).

**Update / uninstall** (same one-line pattern):

```bash
# update: refresh files + pull images + recreate + migrate (your .env is kept)
bash -c "$(curl -fsSL https://raw.githubusercontent.com/pdlc-os/pdlcflow/main/deploy/update.sh)"

# uninstall: stop + remove the stack (keeps data + files by default; asks before deleting)
bash -c "$(curl -fsSL https://raw.githubusercontent.com/pdlc-os/pdlcflow/main/deploy/uninstall.sh)"
```

## Prerequisites

For the Docker Compose path:

- **Docker** with the Compose plugin (`docker compose`, v2).
- Roughly 2 GB free disk for the images + volumes (`pgdata`, `miniodata`, `artifacts`).
- Optional: AWS credentials if you point the LLM provider at Bedrock; an Ollama host if you run air-gapped local models.

For the dev path:

- **uv** (Python 3.12 toolchain manager) for the engine + graph packages.
- **pnpm** (Node 20) for Studio — pinned to **pnpm@9.12.0** via the root `package.json`
  `packageManager` field; run `corepack enable` so the right version is used automatically.

## Clone

```bash
git clone https://github.com/pdlc-os/pdlcflow.git
cd pdlcflow
```

## Docker Compose path (self-host)

The compose stack lives in `infra/compose/`. It defines six services — `postgres` (5432), `redis` (6379), `minio` (9000 API / 9001 console), `api` (8000), `worker` (Arq), `studio` (8080 → nginx:80) — plus an optional `caddy` TLS profile (80/443).

### 1. Configure the environment

```bash
cd infra/compose
cp .env.example .env
```

Edit `.env`. At minimum set a real `PDLC_JWT_SECRET`, and fill in `AWS_*` if you use Bedrock. The shipped `.env.example` already enables the self-host backends:

```ini
PDLC_DB_URL=postgresql+asyncpg://postgres:pdlc@postgres:5432/pdlc
PDLC_REDIS_URL=redis://redis:6379/0
PDLC_USE_POSTGRES_CHECKPOINTER=true
PDLC_USE_REDIS_BUS=true
PDLC_ARTIFACT_STORE=filesystem
PDLC_ARTIFACT_DIR=/var/lib/pdlcflow/artifacts
PDLC_TASK_STORE=postgres
PDLC_ANALYTICS_BACKEND=postgres
PDLC_CLICKSTREAM_SINK=postgres
PDLC_DEFAULT_LLM_PROVIDER=bedrock
```

> Note: `PDLC_WIRE_LLM` is **off** by default — persona completions run on the deterministic offline stub until you set it (and provide provider credentials). See the configuration page.

### 2. Bring up the stack

```bash
docker compose up --build
```

The `api` and `worker` containers are built from `services/pdlc-engine/Dockerfile` (a `python:3.12-slim` image that `uv sync`s the workspace and runs `uvicorn app.main:app --host 0.0.0.0 --port 8000`). Studio is built from `apps/studio/Dockerfile` (a Node 20 build served by nginx, which proxies `/v1/*` and `/ws/*` to `api:8000`). `postgres` and `redis` come up first behind healthchecks; the `api` and `worker` wait for them.

### 3. Run database migrations

The schema is **not** auto-created. Apply the Alembic migrations once the DB is healthy:

```bash
cd services/pdlc-engine && uv run alembic upgrade head
```

- `0001_init` builds the full 25-table schema (`Base.metadata.create_all` + the `pgcrypto`/`citext` extensions).
- `0002_rls` enables row-level-security with an `org_id = current_setting('app.org_id')` isolation policy on every org-scoped table.

(You can also run this inside the running `api` container, e.g. `docker compose exec api uv run alembic upgrade head`.)

### 4. Create the MinIO bucket (only if using S3 artifacts)

The self-host default is `PDLC_ARTIFACT_STORE=filesystem`, which needs **no** bucket — it writes to the mounted `artifacts` volume at `PDLC_ARTIFACT_DIR`. If instead you set `PDLC_ARTIFACT_STORE=s3` with `PDLC_S3_ENDPOINT_URL=http://minio:9000`, create the artifacts bucket first. Open the MinIO console at <http://localhost:9001> (login `minioadmin` / `minioadmin`) and create a bucket matching `PDLC_S3_ARTIFACTS_BUCKET` (default `pdlcflow-artifacts-dev`), or use the MinIO client:

```bash
docker compose exec minio mc alias set local http://localhost:9000 minioadmin minioadmin
docker compose exec minio mc mb local/pdlcflow-artifacts-dev
```

### 5. Verify

```bash
curl http://localhost:8000/health        # {"status":"ok","phase":"A"}
curl http://localhost:8000/health/ready   # {"status":"ready","checks":{...}}
```

Then open **Studio** at <http://localhost:8080>. The engine API is at <http://localhost:8000>. Tail logs with:

```bash
docker compose logs -f api worker
```

### Tear down

```bash
docker compose down        # keep the DB + artifact volumes
docker compose down -v     # also wipe pgdata / miniodata / artifacts
```

## Dev path (no Docker)

Run the engine and Studio side by side on the host. By default every backend is in-memory, so you need **no** Postgres/Redis/MinIO to start.

### Engine

```bash
uv sync
uv run uvicorn app.main:app --reload --app-dir services/pdlc-engine --port 8000
```

### Studio

```bash
pnpm install
pnpm --filter @pdlcflow/studio dev     # Vite on :5173
```

Vite proxies `/v1/*` and `/ws/*` to `http://localhost:8000`, so the two run together. Verify with `curl http://localhost:8000/health` and open <http://localhost:5173>.

### Tests

```bash
uv run pytest        # hermetic suite — no network/DB/AWS required
```


---


---
<!-- nav:bottom -->
⏮ [First: Overview](01-overview.md) · ◀ [Prev: Overview](01-overview.md) · [🏠 Home](README.md) · [Next: Configuration](03-configuration.md) ▶ · [Last: Evals Framework](17-evals.md) ⏭
