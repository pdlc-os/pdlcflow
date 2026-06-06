# Self-host (Docker Compose)

Single-command bring-up for the pdlcflow stack: API + worker + Postgres + Redis + Studio.

## Quickstart

```bash
cp .env.example .env
# fill in PDLC_JWT_SECRET, AWS_* (if using Bedrock), etc.
docker compose up --build
```

Then open <http://localhost:8080> for Studio.

The engine listens on <http://localhost:8000> with `/health` available for smoke checks.

## Validate live token streaming + real evals (with credentials)

The streaming + eval paths default to the offline stub. To exercise them against a
real model locally, in `.env`:

```bash
PDLC_WIRE_LLM=true          # route completions + the eval judge through the provider factory
PDLC_STREAM_TOKENS=true     # live "drafting" preview (already on in .env.example)
PDLC_RUN_EVALS=true         # score agent output at major steps
PDLC_DEFAULT_LLM_PROVIDER=bedrock
AWS_ACCESS_KEY_ID=AKIA...   # the active provider's creds (reach api+worker via env_file)
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
# (or ANTHROPIC_API_KEY / OPENAI_API_KEY / GOOGLE_API_KEY + the matching provider)
```

Then:

```bash
docker compose up --build
```

- **Live streaming:** open Studio (<http://localhost:8080>), run `/brainstorm`, and watch the
  transient "…is drafting" preview fill token-by-token as agents generate (it clears on each
  question/gate/result). The browser's WebSocket is proxied to the API by nginx.
- **Real evals during a run:** drive a brainstorm; eval scores land at
  <http://localhost:8000/v1/admin/evals/summary?org_id=YOUR_ORG> (avg score + pass rate, by
  eval and by agent).
- **Real eval golden suite (one-shot):**

  ```bash
  docker compose --profile evals run --rm evals
  ```

  Scores the golden suite with the real judge and prints a JSON report. Without credentials it
  degrades gracefully (judge errors → neutral scores) — proof the path is wired; add creds for
  real numbers.

> Note: `PDLC_RUN_EVALS` adds judge LLM calls per major step (extra cost). Leave it off for
> normal use; turn it on to validate or to gather quality baselines.

## Row-level security (DB-enforced tenant isolation)

The app connects as the **non-superuser `pdlc_app`** role (`PDLC_DB_URL`) so Postgres RLS is
enforced; **migrations run as the owner** (`PDLC_MIGRATION_DB_URL=postgres`). The `pdlc_app`
role is created on first DB init by `postgres-init/01-app-role.sql` (change its dev password
for real use). Apply migrations (as the owner — the api container's env routes alembic to the
migration URL automatically):

```bash
docker compose run --rm api uv run alembic upgrade head
```

After that, every org-scoped query the app makes is filtered by `app.org_id` at the database —
a compromised request can't read or write another tenant's rows. For a single-role dev setup,
point `PDLC_DB_URL` + `PDLC_MIGRATION_DB_URL` both at `postgres` (RLS enabled but the superuser
bypasses it). Note: the role + grants are created only on a **fresh** `pgdata` volume.

## TLS (Caddy reverse proxy)

```bash
# edit caddy/Caddyfile to set your hostname
docker compose --profile tls up
```

## Air-gapped / local-models with Ollama

1. Install [Ollama](https://ollama.ai) on the host (or add it to compose).
2. Pull at least one model: `ollama pull llama3.3:70b`.
3. In `.env`, set:
   ```
   PDLC_DEFAULT_LLM_PROVIDER=ollama
   PDLC_OLLAMA_ENDPOINT=http://host.docker.internal:11434
   ```
4. `docker compose up --build`.

No outbound LLM traffic.

## Logs

```bash
docker compose logs -f api worker
```

## Tear down (keeping the DB volume)

```bash
docker compose down
```

## Tear down (wiping the DB volume)

```bash
docker compose down -v
```

## Phase A status

This compose stack boots the scaffold described in
[`../../docs/.research/.langgraph-bedrock-saas-migration-2026-06-05.md`](../../docs/.research/.langgraph-bedrock-saas-migration-2026-06-05.md).
The 17 slash commands, party meetings, and approval gates are stubbed —
endpoints return shape-correct responses and Studio renders Chainlit-style
chat with the right layout, but the real graph turns land in Phases B–F.
