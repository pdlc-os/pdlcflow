<!-- nav:top -->
[🏠 Onboarding](README.md) · [📚 Full Wiki](../wiki/README.md) · [🗺️ Visual journey](journey.html)

# 2a · Setup walkthrough

A concrete "do this, then this" list. Follow it top to bottom the first time.
Each step says what you'll see so you know it worked.

## Step 1 — Install

Run the one-liner:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/pdlc-os/pdlcflow/main/deploy/install.sh)"
```

**You'll see:** the installer verify Docker is present, download a `./pdlcflow/`
folder, and launch the **setup wizard**.

## Step 2 — Answer the wizard

The wizard generates all secrets for you (Postgres password, app-role password,
JWT secret, encryption key). You only answer a handful of prompts — defaults in
brackets are fine to accept:

1. **Image version** `[latest]` — press Enter.
2. **Require login (multi-tenant auth + RLS)?** `[n]` — press Enter for
   single-user self-host. (Choose `y` only if you want per-user accounts; it
   then asks for a bootstrap admin email/password.)
3. **Use real LLM models now?** `[n]` — press Enter to start on the offline
   stub. (Choose `y` to wire a provider now; it asks which — `bedrock`,
   `anthropic`, `openai`, `gemini`, `azure`, `vertex`, `ollama` — and that
   provider's credentials.)
4. **Run evals?** `[n]` — press Enter.

**You'll see:** the wizard write a `.env` file and print the next steps.

## Step 3 — Let it come up

The installer then brings the stack up and applies the database migrations for
you. (If you ever need to do these by hand from the `./pdlcflow/` folder:
`docker compose up -d`, then `docker compose run --rm api uv run alembic upgrade
head`.)

**You'll see:** containers start — `postgres`, `redis`, `api`, `worker`,
`studio`.

## Step 4 — Confirm it's healthy

Open the API health check:

- <http://localhost:8000/health> → `{"status":"ok", ...}`
- <http://localhost:8000/health/ready> → `{"status":"ready", ...}` with `db`
  and `redis` healthy.

If readiness is `degraded`/503, the database or Redis isn't up yet — give it a
few seconds and retry, or check `pdlcflow status`.

## Step 5 — Open the Studio

Go to **<http://localhost:8080>**. This is your control surface — a chat
composer on the left, gates and artifacts on the right.

**You'll see:** the pdlcflow Studio. If you enabled login in step 2, sign in
with the bootstrap admin (or via SSO if you configured OIDC).

## Step 6 — (Brownfield only) Connect your repo

If you're onboarding an existing app, connect its git repository so artifacts
and real execution have a home:

- In the Studio, use the **Repo** dropdown → **Connect repository**. Provide a
  name, the `https://github.com/org/repo` URL, and an access token (stored
  encrypted, never in plaintext).
- Equivalent API: `POST /v1/repositories` with `{squad_id, name, url, token,
  default_branch, provider}`.

Greenfield users can skip this (or connect an empty repo later).

## Step 7 — Run your first command

In the Studio composer, type one of:

- **Greenfield:** `/init My Product` — starts the genesis flow (Constitution,
  Intent, seed Roadmap).
- **Just exploring:** `/brainstorm dark mode` — jumps straight into an Inception
  run for a sample feature.

**You'll see:** the engine run for a moment, then **pause** — either at a
question round (it asks you something) or at an **approval gate** (it shows you
a drafted artifact to approve). Approving resumes the run. That pause-and-resume
rhythm is the whole product.

## Step 8 — (Optional) Turn on the dashboards

For the Grafana + Nexus analytics stack:

```bash
pdlcflow observability up
```

**You'll see:** Grafana at <http://localhost:3000>, the Streamlit Nexus
dashboard at <http://localhost:8501>, Prometheus at <http://localhost:9090>.

## Everyday controls

| Do this | Command |
|---|---|
| Check what's running | `pdlcflow status` |
| Stop / start (keep data) | `pdlcflow stop` / `pdlcflow start` |
| Remove containers (keep data) | `pdlcflow remove` |
| **Wipe everything (delete data)** | `pdlcflow wipe` |

---

You're up. Next: **[3 · Going deeper](3-going-deeper.md)** to learn the system,
or jump straight to **[6 · Implementing a requirement](6-implementing-a-requirement.md)**
to build something.

<!-- nav:bottom -->
◀ [2 · Getting started](2-getting-started.md) · **Next → [3 · Going deeper](3-going-deeper.md)** · [🗺️ Visual journey](journey.html)
