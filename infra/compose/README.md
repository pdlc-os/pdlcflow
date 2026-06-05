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
