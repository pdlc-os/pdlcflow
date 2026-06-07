# Deploy pdlcflow (no clone required)

Run the whole stack from **prebuilt images** on GitHub Container Registry — you only
need Docker + these few files, not the source repo.

> **Image access.** The `ghcr.io/pdlc-os/pdlcflow-api` and `pdlcflow-studio` packages are
> **public**, so the pulls below work with no login. If you mirror pdlcflow into your own org
> and keep the packages **private**, deployers must authenticate first:
> `echo "$GHCR_PAT" | docker login ghcr.io -u <user> --password-stdin` (PAT with `read:packages`).

## Quick start (one line)

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/pdlc-os/pdlcflow/main/deploy/install.sh)"
```

That downloads the deploy files into `./pdlcflow`, runs the interactive wizard
(prompts + generates secrets → `.env`), brings the stack up, and applies the schema.
Use the `bash -c "$(curl …)"` form (**not** `curl | bash`) so the wizard can read your
terminal. Options: `--no-start` (download + configure only) and `--dir=<path>` /
`PDLCFLOW_DIR=<path>` (install location, default `./pdlcflow`). Then open
**http://localhost:8080** (Studio) and **http://localhost:8000/health** (API).

## Quick start (manual, step by step)

```bash
# 1. Grab the deploy files into an empty directory
base=https://raw.githubusercontent.com/pdlc-os/pdlcflow/main/deploy
mkdir pdlcflow && cd pdlcflow
curl -fsSLO $base/docker-compose.yml
curl -fsSL  $base/setup.sh -o setup.sh && chmod +x setup.sh
mkdir -p postgres-init && curl -fsSL $base/postgres-init/01-app-role.sh -o postgres-init/01-app-role.sh

# 2. Configure (interactive — prompts for the few choices, generates secrets)
./setup.sh

# 3. Launch + apply the database schema
docker compose up -d
docker compose run --rm api uv run alembic upgrade head
```

> Prefer not to use the wizard? `curl -fsSLO $base/.env.example`, copy it to `.env`,
> edit by hand, then `docker compose up -d`. Everything `setup.sh` asks is just a key in `.env`.

## What `setup.sh` asks (everything else is defaulted)
- **Image version** (pin a release, e.g. `1.5.0`, or `latest`).
- **Require login?** — turns on multi-tenant auth + RLS; if yes, it takes a bootstrap admin
  email/password (password auto-generated if blank).
- **Use real LLM models?** — else the deterministic offline stub. If yes: provider
  (Bedrock/Anthropic/OpenAI/Gemini) + that provider's credentials.
- **Run evals?**

It auto-generates the JWT secret + the Postgres/app-role passwords and writes `.env`
(git-ignored). Re-run any time.

## Update

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/pdlc-os/pdlcflow/main/deploy/update.sh)"
```

Refreshes the deploy files (compose + scripts; **never** your `.env`), pulls the latest
images, recreates the stack, and applies any new DB migrations. Run from your deploy dir
(or above `./pdlcflow`), or pass `--dir=<path>`. Bump the pinned version with
`update.sh --version=1.6.0` (append flags to the one-liner as
`bash -c "$(curl …)" -- --version=1.6.0`). `--no-migrate` skips the schema step.

## Uninstall

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/pdlc-os/pdlcflow/main/deploy/uninstall.sh)"
```

Stops + removes the stack. **By default it keeps your data and files**, then asks (default
*No*) before each irreversible step. Flags: `--data` (delete the Postgres/MinIO/artifacts
volumes — irreversible), `--images` (remove the pulled images), `--purge` (all of those +
remove the deploy directory), `--yes` (no prompts; only flagged actions run). `--dir=<path>`
selects the deployment.

## Notes
- Pin the version in `.env` (`PDLCFLOW_VERSION=1.5.0`) for reproducible deploys; `latest`
  tracks the newest release.
- **RLS:** the app connects as the non-superuser `pdlc_app` role (created on first DB init);
  migrations run as the owner. `setup.sh` keeps both passwords in sync.
- **Real evals one-shot:** `docker compose --profile evals run --rm evals` (needs LLM creds).
- **Upgrade:** use the [Update](#update) one-liner (or manually bump `PDLCFLOW_VERSION`,
  `docker compose pull && docker compose up -d`, then `… alembic upgrade head`).
- TLS / reverse proxy, backups, and scaling are deployment-specific — front the `studio`
  (`:8080`) + `api` (`:8000`) with your own proxy.
