# Changelog

All notable changes to pdlcflow are documented here. This project adheres to
[Semantic Versioning](https://semver.org/).

## v1.13.0 — 2026-07-06

Wave 3 of the cc-switch gap roadmap — roadmap complete: cost analytics
(pricing overrides, versioned catalog, budgets, real spend events; PRD-07),
egress network controls (PRD-08), persona prompt overrides & packs (PRD-10),
and MCP tool servers for agents (PRD-09).

> **Upgrade notes:** (1) `alembic upgrade head` applies migrations
> `0011`–`0014` (the deploy stack does this automatically). (2) For
> `PDLC_WIRE_LLM=true` deployments, persona soul-specs now reach models as
> system prompts — real-model outputs shift and input tokens rise ~2–4 KiB per
> call (visible in the spend stream). Hermetic/stub deployments are unchanged.

### Changed
- **Persona soul-specs now actually reach models** (PRD-10 M0). The persona
  markdown files were documented as each agent's system prompt but had no
  consumer — nodes passed ad-hoc strings like "PDLC PRD author". `complete()`
  now always carries the persona's effective soul-spec as the system prompt,
  with any caller-provided `system` appended as a task role.
  **Behavior change for `wire_llm` deployments**: real-model outputs shift
  (personas finally get their intended identities) and per-call input tokens
  rise by the spec length (~2–4 KiB, visible in the spend stream). Hermetic
  CI/stub outputs are byte-identical (the stub hashes persona+prompt only).

### Added
- **Org persona prompt overrides** — edit any LLM persona's soul-spec per org
  (new Nexus → Prompts page + `/v1/admin/prompts/*` API). Versions are
  immutable (draft → active → archived, ≤1 active per persona via a partial
  unique index, migration `0013`); activation switches instantly (60 s TTL
  cache), deactivation returns to the packaged spec. Guardrails: 32 KiB cap,
  frontmatter-tier validation (tier itself stays in `agent_llm_config`), no
  templating (plain text — cross-tenant render-time leakage structurally
  impossible), sentinel excluded (deterministic evaluator). `prompt.activated`
  / `.deactivated` audit events.
- **Prompt packs** — export active overrides as a portable JSON pack (plain
  text, no secrets/org ids); import always lands as **drafts** (never
  auto-activated — backfill protection), with dry-run validation. The
  template-org → client-orgs rollout flow.
- **MCP tool servers** — agents can now call external tools. Org-scoped
  registry (migration `0014`, RLS-forced) with per-server tool **allowlists
  (empty = deny all)**, write-only bearer tokens via the secretstore, live
  test-connection probes, and persona/phase **bindings** (unbound servers are
  inert). New graph-side `tool_port` (null default — hermetic CI stays
  byte-identical; the `mcp` SDK is engine-only) + flagship flow: Muse's
  divergent ideation grounds itself in bound search tools, with results
  fenced + provenance-tagged as untrusted data. Execution is flag-gated
  (`PDLC_WIRE_MCP`, default off) with hard caps (timeout, 64 KiB result
  truncation, 20 calls/turn, 60 s dead-server cool-down); stdio transport is
  double-gated to single-user self-host (write **and** call time); server
  URLs pass the SSRF egress policy (`PDLC_MCP_ALLOW_PRIVATE_NETWORKS` for VPC
  servers). `tool.called` audit events + `pdlc.tool.<name>` spans. New
  **Nexus → Tools** page + wiki page 20.
- **Event-type registry fix** — the clickstream envelope validates
  `event_type` against a fixed registry, which was silently dropping every
  audit event added since Wave 1 (`admin.llm_key.*`, `llm_config.*`,
  `llm.failover`, `llm.rate_limited`, `budget.threshold`, `prompt.*`). All
  new families are now registered with correct human/system/agent actor
  classification — the audit trails these features promised actually record.
- **Egress network controls** — `PDLC_EGRESS_PROXY_URL` / `PDLC_EGRESS_NO_PROXY`
  / `PDLC_EGRESS_CA_BUNDLE` are threaded explicitly into every provider builder
  (httpx passthrough for the OpenAI/Anthropic family + gateways, client_kwargs
  for Ollama with in-cluster exemptions, botocore Config for Bedrock; gemini
  falls back to env only when unset; vertex honestly unsupported). A boot-time
  egress report states each provider's support level, and a misconfigured CA
  path fails loudly. Probes use the same egress path as real calls.
- **Org extra headers** — `extra_headers` on the org model config (migration
  `0012`) for relay-gateway routing hints, merged into requests where the SDK
  supports default headers. Guardrailed: max 8, name/value limits,
  `Authorization`/`Host`/`Cookie`/`Content-*`/`Proxy-*` rejected (never a
  second credential channel). Versioned, exported/imported with the provider
  set.
- **Per-org pricing overrides** — `org_llm_config.pricing_override` (the column
  `pricing.py` promised), editable via `PUT /v1/admin/pricing/overrides` and the
  console's new **Pricing & budget** panel (effective sheet with
  catalog/preset/override provenance badges). Resolution: override → catalog →
  preset hint → wildcard → unpriced. Overrides are versioned like any other
  config change and travel with export/import. Migration `0011`.
- **Versioned pricing catalog** — the hardcoded `PRICES` dict became
  `pricing_catalog.json` (same values, byte-identical estimates), updated with
  each release.
- **Unpriced ≠ free** — unknown models now report `usd_estimate: null` instead
  of `$0.0`; spans carry `pdlc.unpriced=true`; rollup consumers already
  COALESCE nulls, so dashboards keep working while unpriced traffic becomes
  visible.
- **Org monthly budgets** — `PUT /v1/admin/budget` sets a soft limit; crossing
  50/80/100% (configurable) fires a `budget.threshold` clickstream event
  exactly once per org/month/threshold (ledger-deduped, evaluated on the
  clickstream drain path, memoized + fail-silent). Console shows month-to-date
  progress + fired chips. Estimates only — alerts never block turns.
- **Real `llm.tokens_spent` events** — the completion backend now emits the
  spend event the Nexus token/cost rollups pivot on (attributed via the turn's
  thread context); previously the emitting callback existed but was never
  wired, so production rollups had no producer.

### Fixed
- Cost labelling now honors the org's negotiated prices on the OTel metrics
  path as well (the factory caches `pricing_override` with a 60 s TTL — no
  extra hot-path query).

## v1.12.0 — 2026-07-06

Provider resilience & the open ecosystem (Wave 2 of the cc-switch gap roadmap):
preset catalog + OpenAI-compatible gateways (PRD-04), failover chains + circuit
breaker + real rate limiting (PRD-05), and config versioning, rollback &
export/import (PRD-06).

### Added
- **Config history & rollback** — every org/agent model-config mutation
  (console, API, preset apply, import) records the full prior state in an
  immutable RLS-forced `llm_config_versions` table (migration `0010`), written
  in the same transaction as the change. `GET /admin/models/versions` returns
  the timeline with field-level diffs (secrets render only as
  set/changed/cleared); one-click rollback restores any version — appending a
  `rollback` entry, never rewriting history — and drops stored keys that no
  longer resolve with a `secret_requires_reentry` flag instead of restoring
  them blind. Count-based retention (`PDLC_LLM_CONFIG_VERSION_KEEP`, default
  50/scope). Console gains a **History** panel.
- **Provider-set export/import** — `GET /admin/models/export` produces a
  self-describing JSON document with **zero key material** (`enc:` refs are
  Fernet ciphertext and are stripped; `vault:`/`env:` refs export as safe
  pointers); `POST /admin/models/import` supports dry-run plans
  (create/overwrite/error + secret reusability per item), merge/replace
  strategies, atomic apply, and reuses the write-path validators so an import
  can't smuggle in a config the API would reject. Console Export/Import panel
  with dry-run preview — the staging → production promotion flow.
- **Failover-chain editor** in the console (deferred from PRD-05): ordered
  entries with per-entry provider/endpoint/region/tier-map/key, reorder and
  remove, saved with the org default.
- **Failover chains** — an org can declare up to 3 ordered fallback provider
  configs (`failover_chain` on the org model config), each with its own
  region/endpoint/tier_map and its **own write-only API key** (keyed providers
  require one — a fallback must never silently bill the operator's env key).
  On retriable errors (429/5xx/timeout/connection) the engine retries the same
  persona+tier on the next candidate; auth/validation errors surface
  immediately. Streaming fails over only before the first token (no mid-answer
  model splicing). Chainless orgs are byte-identical to before (the chain is
  only queried after a retriable primary failure). Migration `0009`.
- **Circuit breaker** per (org, provider[:gateway-host]) in Redis — open after
  N failures/window, cooldown skip, half-open single probe (`SET NX`), fail-open
  when Redis is down. `PDLC_LLM_BREAKER_*` knobs.
- **Real rate limiting** — `rate_limit.py`'s always-True stub replaced with the
  documented fixed-window Redis limiter, enforced per attempt in the completion
  path behind `PDLC_RATE_LIMIT_ENABLED` (default off); rejection raises a clear
  `RateLimited` error and never triggers failover.
- **Resilience telemetry** — OTel counters `pdlc.llm.fallbacks`,
  `pdlc.llm.breaker_transitions`, `pdlc.llm.rate_limited`; `llm.failover` /
  `llm.rate_limited` clickstream events; failed attempts get span
  `record_exception` + `pdlc.llm.fallback_rank`; a new **Resilience** row on the
  provisioned Grafana dashboard.
- **`openai_compatible` provider** — point any org (or single agent) at an
  OpenAI-protocol gateway or server with a custom base_url: OpenRouter,
  DeepSeek, Kimi/Moonshot, GLM, SiliconFlow, LiteLLM, vLLM, Ollama's `/v1` —
  zero per-vendor code. Endpoint + complete tier_map are enforced at
  config-write time (never a mid-turn `KeyError` — `resolve_model_id` now
  raises a typed `ModelResolutionError`), and tenant-supplied endpoints pass
  the SSRF egress guard before they can be stored. Migration `0008` widens the
  provider CHECK constraints (and names them for deterministic future
  widenings).
- **Provider preset catalog** — curated, versioned, vendored
  (`app/llm/presets/catalog.json`, 15 entries: the 7 first-party providers +
  8 gateways/local servers). `GET /v1/admin/models/presets?q=` to browse/search,
  `POST /v1/admin/models/presets/{id}/apply` for one-click org setup (never
  touches secrets; `needs_secret` tells the console to chain key entry). The
  console's Models page gains a **"Start from a preset…"** picker that
  pre-fills the form for review → key → Test → Save. Preset `pricing_hints`
  feed `estimate_usd` so gateway usage isn't silently $0 in dashboards.

## v1.11.0 — 2026-07-05

Provider Management (Wave 1 of the cc-switch gap roadmap: BYOK, connectivity
probes, and a working Settings Console) + full observability (OpenTelemetry →
Grafana, and a Streamlit ops dashboard).

### Added
- **Provider Settings Console**: Studio's Nexus → Models page (previously a
  static mockup) now fully works — load/edit/save the org default provider with
  a per-tier model map (prefilled from provider defaults on switch, with a
  confirm dialog naming the org-wide blast radius), per-persona overrides with
  inherit/override states and Clear, BYOK key entry/rotation/removal per scope
  (write-only; only a "key set" chip is ever shown), and a working **Test**
  button per row that probes the current draft (or the saved config with its
  stored key) and renders ✓ latency / classified error inline. Unsaved-change
  guard on navigation. New read-only `GET /v1/admin/models/defaults` supplies
  providers/personas/tier-map prefills/instance default.
- **Provider connectivity testing**: `POST /v1/admin/models/test` probes a
  candidate or saved provider config with a minimal live completion (built
  through the same factory path real turns use), returning
  `{ok, latency_ms, error_class, tested_model, message}` with sanitized,
  classified errors (`auth_error`, `model_not_found`, `access_denied`,
  `endpoint_unreachable`, `rate_limited`, `timeout`, `bad_request`, …).
  Saved-scope tests resolve the stored BYOK key; last result per scope persists
  to a new RLS-forced `llm_provider_health` table served by
  `GET /v1/admin/models/health`. SSRF egress guard on candidate endpoints
  (`PDLC_ALLOW_PRIVATE_LLM_ENDPOINTS` escape hatch for local Ollama), 10/min
  per-org probe rate limit, injectable prober port (CI stays network-free), and
  an opt-in instance-default health loop (`PDLC_LLM_HEALTH_INTERVAL_S`) that
  makes `/health/ready`'s `llm` check real (`ok`/`degraded`/`unprobed`).
- **BYOK (bring-your-own-key) completion**: the LLM factory now reads
  `org_llm_config.secret_ref` / `agent_llm_config.secret_ref` and injects the
  tenant's key into every provider call for that org. The admin API gains a
  write-only `api_key` field on `PUT /v1/admin/models/org-default` and
  `…/agent-overrides/{persona}`, a derived `has_key` flag on reads (key material
  and refs are never returned), and `DELETE …/key` endpoints. Same-provider agent
  overrides inherit the org key; keys never cross provider boundaries. An
  unresolvable stored key **fails closed** instead of silently billing the
  operator's env key (that was the bug). Resolved keys are TTL-cached
  (`PDLC_SECRET_CACHE_TTL_S`, default 300 s); key set/clear emits
  `admin.llm_key.*` audit events carrying no key material.
- **OpenTelemetry instrumentation** (opt-in, `PDLC_OTEL_ENABLED`). One trace per
  graph turn → a span per LangGraph node → a leaf span per `complete()` call with
  GenAI semantic-convention attributes (model, provider, token usage, estimated
  cost). Metrics for turns, LLM calls/tokens/cost, latency histograms, and gate
  activity. FastAPI request spans. Exports OTLP to a collector.
- **Dep-free tracer port** in `pdlc-graph` (`pdlc_graph/tracing.py`) — an injectable
  seam mirroring `set_emitter`/`set_completion_backend`; the engine injects the
  OTel-backed tracer at boot, so the graph package keeps zero OpenTelemetry deps and
  CI/dev stay hermetic (byte-identical, no-op when disabled).
- **Observability compose profile** (`observability`) for both the self-host and
  standalone stacks: OTel Collector → **Tempo** (traces) + **Prometheus** (metrics),
  a provisioned **Grafana** dashboard, and the **Nexus Dashboard** — a Streamlit ops
  console (`services/nexus-dashboard`) with agent-activity, token/cost, gate, and a
  per-thread **trace explorer**.
- **`pdlcflow observability up|down|status`** control-CLI command; install/update
  scripts fetch the `observability/` configs; `pdlcflow-nexus-dashboard` added to the
  released image set.
- Docs: new [Observability](docs/wiki/19-observability.md) wiki page, plus config +
  monitoring cross-links.

## v1.10.0 — 2026-06-08

Studio conversation & entity-management improvements.

### Added
- **Landing greeting** — the logo (centered) replaces the "Welcome" text, with a
  time-of-day greeting (Good morning/afternoon/evening) that uses the signed-in
  user's handle when auth is on.
- **Rename + delete** for domains, squads, initiatives, and projects — from the top-nav
  dropdowns and the left Projects panel, each guarded by a confirmation. Org-scoped
  (RLS); deletes handle FKs (initiative un-links its projects/applications; project
  delete drops its conversations; squad cascades).
- **Continue a conversation** — clicking a thread loads its transcript, and a plain
  message continues it: `POST /v1/commands/continue` sends the **entire prior
  transcript to the LLM as context + the new prompt** (via Atlas) and appends both
  turns; tokens stream live.

### Fixed
- **Conversations now group under their project.** The Studio's `projectId` no longer
  defaults to a random orphan id, so conversations are filed under the real server
  project (and show in the Projects panel) instead of an unmatched id.

## v1.9.1 — 2026-06-07

Logo, attachment hardening, and a docs refresh on top of v1.9.0.

### Added / Changed
- **Studio logo** — the top-left moniker is now the pdlcflow logo image (still links home).
- **Chat attachments hardened** — files are stored under
  `uploads/{conversation}/{timestamp}-{nonce}-{filename}` (per project + conversation; a
  re-uploaded same name never overwrites), and **text is extracted from pdf/docx/xlsx/pptx**
  (in addition to utf-8 text) and folded into the prompt, so attachments reach whichever
  agent runs the turn. Commands accept a client `session_id` so pre-uploaded files share the
  conversation's folder.
- **Docs** — README gains the logo + a Release A/B review; new wiki page **Data Model &
  Hierarchy** (Org · Domain · Squad · Repository · Initiative · Program · Project ·
  Conversation, with the cross-org Program umbrella and RLS); API reference *Entities*
  section; Studio + deploy docs updated for the nav, repo connect, repo-backed memory,
  attachments, the `pdlcflow` CLI, and secrets/Vault.

## v1.9.0 — 2026-06-07

"Release B" — the hierarchy redesign, GitHub repos, repo-backed memory, and chat
attachments. (Pre-deployment schema change; no migration/backfill concerns.)

### Data model (the #10 redesign)
- **Org → Domain → Squad** (`squads.domain_id`), first-class **Repository** (owned
  by a Squad), **Squad ↔ Initiative** and **Initiative ↔ Repository** (many-to-many),
  and a cross-org **Program** umbrella — initiatives stay org-scoped (RLS-clean); a
  Program links them across orgs (owner + linked-org read). `Project.repository_id`.
- All new tables RLS-FORCEd; cross-org Program visibility verified on real Postgres.

### Secrets
- Pluggable **secrets backend** for per-repo tokens: `encrypted` (Fernet, in the DB —
  self-host default), `vault` (HashiCorp Vault KV v2), `env` (cloud/custom managers).
  **Vault bundled but opt-in** (`docker compose --profile vault up -d`); `setup.sh`
  generates a Fernet `PDLC_SECRET_KEY`.

### APIs
- Entity CRUD under `/v1`: domains, squads, initiatives, repositories (token via the
  secrets backend, never returned), and **server-backed projects**.
- Repo file browsing: `/v1/repositories/{id}/files` + `/file` (GitHub contents API).
- `POST /v1/uploads` — chat attachments (multipart, 15 MB cap).

### Studio
- **Real hierarchy nav** — Org · Domain · Squad · **Repo** · Initiative · Project
  dropdowns (list + inline create), with a **GitHub repo selector** (#2) and a
  connect form (url + token). Projects moved off the client registry onto the server.
- **Repo-backed memory** (#3) — a left-panel browser of the connected repo's files,
  shown only once a repo is open.
- **Chat attachments** (#7) — drag-and-drop / paperclip; text files' content is folded
  into the prompt, binaries are stored + referenced.

## v1.8.0 — 2026-06-07

"Release A" — operational CLI + Studio UX quick wins. (The larger GitHub-repo and
schema-hierarchy work is tracked for a following release.)

### Added
- **`pdlcflow` control CLI + `PDLCFLOW_HOME`.** The installer symlinks a `pdlcflow`
  command onto PATH and exports `PDLCFLOW_HOME`; subcommands wrap docker compose in
  that dir: `setup` (up -d) · `start` · `stop` · `status` (ps) · `remove` (down) ·
  `wipe` (down -v). The updater recreates the symlink/env if missing; the
  uninstaller removes them.
- **Create projects from the Studio landing page** → straight into the project's
  chat (replacing the hardcoded demo tiles).
- **Conversations nested under each project** in the left nav — click to open/replay.

### Changed / Fixed
- **Composer is multi-line.** It's now a `<textarea>`: **Enter sends**,
  **Shift/Ctrl/Cmd/Alt+Enter** inserts a newline; it auto-grows then scrolls.
- **Slash-command caret fix.** The highlight overlay now shares the textarea's exact
  typography (color-only highlight), so the caret no longer trails when typing a
  `/command`.
- **Sign-in overlay is dismissable** (Cancel always shown + Esc + backdrop click) —
  previously self-hosted simulation-mode users with no identity were trapped on it.

### Notes
- Studio projects are backed by a client-side registry for now; the next release
  promotes them to a server-side, org-scoped entity as part of the data-model
  redesign (Org→Domain→Squad→repos, Squad↔Initiative many-to-many, cross-org
  initiatives), alongside GitHub-repo selection, repo-backed memory, and chat
  file attachments.

## v1.7.1 — 2026-06-07

Patch: fixes a one-line-installer failure on a fresh deploy.

### Fixed
- **Installer: Postgres (and therefore the whole stack) failed to start.** `install.sh`
  / `update.sh` fetch `postgres-init/01-app-role.sh` with `curl -o`, which drops the
  execute bit. Postgres's entrypoint then either can't exec it (`bad interpreter:
  Permission denied`, container exits 126) or sources it and leaks the script's
  `set -e` into the entrypoint — so Postgres never becomes healthy and every
  dependent service reports *"dependency … failed to start"*. Both scripts now
  `chmod +x` the init script after download. (No image change — the deploy scripts
  are served from `main`, so the fix reaches new installs immediately.)

  Already hit this? The half-initialized data volume must be wiped before retrying:
  `docker compose down -v` in your `pdlcflow/` dir, then re-run the installer.

## v1.7.0 — 2026-06-07

Conversation history, subscription-CLI LLMs, deeper defense-in-depth, and Studio
UX on top of v1.6.0. All new capability is flag-gated and off by default.

### Conversation history (ChatGPT/Claude-style)
- **Durable, verbatim transcript** of every thread — an RLS-FORCEd `thread_transcript`
  table (migration 0005, org-isolated), recorded at each turn boundary.
- **`GET /v1/admin/threads`** + **`/threads/{id}`** to list past threads and open one.
- A Studio **Conversations sidebar**: list, reopen (verbatim replay), continue, or start
  new — with org/project/thread persisted across reloads.

### Subscription-CLI LLM providers (single-user self-host)
- `claude_code` / `codex` / `gemini_cli` — bill against a Claude Max / ChatGPT / Google
  subscription via the local CLI (`PDLC_ENABLE_CLI_PROVIDERS`), refused under
  auth/multi-tenant.

### Defense-in-depth
- **RLS-FORCE on the LangGraph checkpoint tables** (`checkpoints`/`checkpoint_writes`/
  `checkpoint_blobs`) so thread state is DB-isolated per org, not just by `thread_id`.
  (Also fixed a latent issue: the durable checkpointer needed `CREATE` to run as `pdlc_app`.)

### Observability
- **Context-window meter** (`GET /v1/admin/context` + a Studio gauge): peak prompt tokens
  vs the model's window, with a near-limit flag.
- **`/compact`** command + a meter button: distills the working log to free up context.

### Studio UX
- Slash-command **autocomplete + color-coding** in the composer, and a **Sketch ⇄ Socratic**
  interaction-mode toggle (default Sketch — pre-filled recommended answers).

### Build / CI / providers
- **Credentials as config for all 7 providers** (env keys + cloud SDK chains); the install
  wizard covers every provider; fixed the Bedrock-region var.
- **Node CI now gates** (no more `|| true`) with a proper ESLint v9 flat config — which
  immediately caught + fixed CDK stack sources that were gitignored and never committed.
- Docs/scripts audit; README intro reflects multi-cloud (AWS/GCP/Azure).

### Known limitations
- Subscription CLIs are single-user self-host only. Multi-cloud Terraform is validated, not
  deploy-tested. The context meter measures per-call prompt size (not a single growing
  conversation — pdlcflow uses discrete, state-reconstructed prompts).

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
