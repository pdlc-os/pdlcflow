<!-- nav:top -->
[🏠 Onboarding](README.md) · [📚 Full Wiki](../wiki/README.md) · [🗺️ Visual journey](journey.html)

# 2 · Getting started

Two things to decide before you start: **how to run it**, and **which road
you're on**.

## Prerequisites

For the recommended path you need only:

- **Docker** and **Docker Compose v2** (`docker compose version` works).
- That's it. GHCR images are public — no registry login, no clone.

The LLM layer defaults to an **offline deterministic stub**, so you can explore
the entire workflow with **no API keys**. Wire a real provider (Bedrock,
Anthropic, OpenAI, Gemini, Azure, Vertex, Ollama) whenever you want real model
output — the setup wizard will offer to do it, or you can do it later.

> **Contributing to pdlcflow itself?** That's a different setup (Python 3.12 +
> [uv](https://docs.astral.sh/uv/), Node 20 + pnpm 9, `uv sync && pnpm install`,
> build from `infra/compose/`). See the repo `README.md` → *Develop*. This page
> is for **adopting** pdlcflow, not hacking on it.

## Install & run (one command)

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/pdlc-os/pdlcflow/main/deploy/install.sh)"
```

> Use the `bash -c "$(curl …)"` form, **not** `curl … | bash` — the installer
> runs an interactive setup wizard that needs to read your terminal.

The installer downloads a small `./pdlcflow/` directory (compose file, env
template, helper scripts), runs the **setup wizard**, brings the stack up, and
applies the database migrations. When it finishes:

- **Studio (the UI):** <http://localhost:8080>
- **API / health:** <http://localhost:8000/health>

It also installs a `pdlcflow` control command: `pdlcflow start | stop | status
| remove | wipe` (and `pdlcflow observability up` for the Grafana/Nexus stack).

The wizard asks only a few questions — image version, whether to require login
(multi-tenant auth), whether to wire a real LLM now (and which provider's
credentials), and whether to run evals. Everything else is defaulted to a
working single-user self-host stack. For the exact keystroke-by-keystroke
sequence, see **[2a · Setup walkthrough](2a-setup-walkthrough.md)**.

## Pick your road

pdlcflow serves two very different starting points. Choose the one that matches
you — the rest of onboarding branches from here.

### 🌱 Greenfield — a brand-new product

You're starting something new; there's little or no existing code, and no prior
roadmap to import.

**Your path:**

1. Get the stack running (above).
2. Run **`/init`** in the Studio composer — an interactive genesis flow that
   authors your **Constitution** (your standing rules), **Intent** (mission,
   users, success metric), and a **seed Roadmap** (your first features). It ends
   at the `init_approve` gate and then hands you into Inception.
3. For each feature, run the day-two loop:
   **[`/brainstorm → /build → /ship`](6-implementing-a-requirement.md)**.
4. (Optional) Connect an empty git repo so artifacts and the real execution arc
   have somewhere to live.

→ Continue with **[6 · Implementing a requirement](6-implementing-a-requirement.md)**.
If you already have a written spec for your first feature, detour through
**[4 · Bringing your own spec](4-bringing-your-own-spec.md)** first.

### 🏛️ Brownfield — an existing app

You already have a codebase, and probably a roadmap, history, or an upstream
`pdlc` project. You want pdlcflow to pick up where you are — with dashboards
that aren't empty on day one.

**Your path depends on what you're bringing:**

| What you have | Do this |
|---|---|
| An existing **git repo** (any app) | Connect it in the Studio (**Repo** dropdown → *Connect repository*, or `POST /v1/repositories`). Then run `/init` to seed a Constitution/Intent/Roadmap informed by your existing plan, and work features normally. To run **real** tests/merge/deploy against the repo, enable the single-user self-host execution arc (see [8 · Shipping & release](8-shipping-and-release.md)). |
| An existing **upstream `pdlc` project** (file-based `docs/pdlc/memory/`) | Use the **`pdlc-migrate`** CLI (`scan → push → taxonomy → backfill`) to import its memory, tasks, decisions, deployments, and history. The Nexus dashboards light up immediately. |
| A **roadmap / backlog** in your head or a doc | Run `/init` and paste your features into the seed-roadmap round; each becomes an `F-NNN` item you can then `/brainstorm`. |

→ Continue with **[5 · Bringing your own roadmap](5-bringing-your-own-roadmap.md)**.

## Which backends am I running?

Out of the box the wizard configures a durable single-host stack: **Postgres**
(state + analytics), **Redis** (event bus), filesystem artifacts, and the
offline LLM stub. Optional profiles add **MinIO** (S3 artifacts), **Vault**
(secrets), and an **observability** stack (Grafana, Prometheus, the Streamlit
Nexus dashboard). The same engine code runs self-host or as multi-tenant SaaS —
only which flag-gated backends are wired changes. Details:
[wiki · Configuration & Backends](../wiki/03-configuration.md).

---
<!-- nav:bottom -->
◀ [Onboarding home](README.md) · **Next → [2a · Setup walkthrough](2a-setup-walkthrough.md)** · [🗺️ Visual journey](journey.html)
