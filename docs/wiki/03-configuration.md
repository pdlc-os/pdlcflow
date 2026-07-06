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
| `PDLC_STREAM_TOKENS` | `false` | Stream live `token` frames to the Studio (the "drafting" preview). |
| `PDLC_RUN_EVALS` | `false` | Score agent output via the eval harness (`eval.scored`/`eval.blocked`). |
| `PDLC_EVAL_BLOCKING` | `` | Comma-separated evals that **block** on failure (else measure-only). |
| `PDLC_JUDGE_TIER` | `premium` | Capability tier for the LLM-as-judge (`premium`\|`balanced`\|`economy`). |
| `PDLC_AUTH_REQUIRED` | `false` | Enforce JWT auth; derive the tenant from the token. |
| `PDLC_ENABLE_CLI_PROVIDERS` | `false` | Allow subscription-CLI providers (single-user self-host only; see below). |
| `PDLC_OTEL_ENABLED` | `false` | Export OpenTelemetry traces + metrics (agent span tree, latency, token/cost) to the collector. Off ⇒ the graph tracer port is a no-op. See [Observability](19-observability.md). |
| `PDLC_OTEL_ENDPOINT` | `http://otel-collector:4317` | OTLP/gRPC endpoint of the OTel collector. |
| `PDLC_CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed CORS origins for the API. |

> AWS credentials (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`) are read by boto3 directly — only needed when using Bedrock, Firehose, or real S3.

### Provider credentials

Credentials are supplied as configuration and resolved per provider:

- **Cloud SDK chains** — Bedrock (boto3) and Vertex (Google ADC) use the standard chains: env
  vars (`AWS_*`, `GOOGLE_APPLICATION_CREDENTIALS`) **or** an attached IAM role / workload
  identity. No PDLC-specific key fields.
- **Direct-API keys** — Anthropic / OpenAI / Gemini / Azure OpenAI read the SDK's own env var
  when no per-tenant secret is set: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`,
  `AZURE_OPENAI_API_KEY` (+ `AZURE_OPENAI_ENDPOINT`). Put them in `.env` / the container env.
- **Per-tenant override** — a non-empty `secret_value` (from `org_llm_config` / `agent_llm_config`)
  takes precedence over the env var for that org/agent.

Precedence: **per-tenant `secret_value` → provider env var**. (`PDLC_WIRE_LLM=true` uses real
models; off uses the deterministic offline stub and needs no credentials.)

### Subscription CLIs (single-user self-host only)

You can bill completions against your **Claude Pro/Max**, **ChatGPT**, or **Google** subscription
instead of an API key by routing through the locally-installed coding-agent CLI:

| `PDLC_DEFAULT_LLM_PROVIDER` | CLI | Bin override | tier → `--model` |
| --- | --- | --- | --- |
| `claude_code` | `claude -p` | `PDLC_CLAUDE_CODE_BIN` | opus / sonnet / haiku |
| `codex` | `codex exec` | `PDLC_CODEX_BIN` | gpt-5.5 / gpt-5.4 / gpt-5.4-mini |
| `gemini_cli` | `gemini -m` | `PDLC_GEMINI_CLI_BIN` | gemini-3.1-pro / 3.5-flash / 3.1-flash-lite |

The engine shells out to the CLI (prompt on stdin, no shell), so the CLI must be **installed and
logged in** on the host. Enable with **`PDLC_ENABLE_CLI_PROVIDERS=true`** (default off) +
`PDLC_WIRE_LLM=true`.

> **Single-user self-host ONLY.** The factory **refuses** these providers when auth is enabled
> (`PDLC_AUTH_REQUIRED=true`) — a personal subscription can't power multi-user / SaaS (per the
> providers' terms), and it only bills one local seat. Intended for running the engine as a local
> process (`uvicorn`); they are not wired into the Docker/compose or cloud deploy paths.

Caveats: a subprocess per completion (CLI-startup latency) and **no live token streaming** (the
CLI returns the full text). Per-agent tiers still apply via each CLI's `--model`.

## Per-agent model tiers (provider-neutral)

Agents don't hard-code a model. Each persona declares a **provider-neutral capability
tier** in its soul-spec frontmatter (`tier: premium | balanced | economy`), and the engine's
`tier_map` resolves that tier to a concrete model **for whichever provider is active**:

| Tier | Meaning | Personas | Bedrock / Anthropic / Vertex | OpenAI / Azure | Gemini |
| --- | --- | --- | --- | --- | --- |
| `premium` | highest capability | atlas, bolt, friday, neo, pulse | Claude Opus | `gpt-5.5` | `gemini-3.1-pro` |
| `balanced` | general purpose | echo, jarvis, muse, phantom | Claude Sonnet | `gpt-5.4` | `gemini-3.5-flash` |
| `economy` | low token / fast | sentinel | Claude Haiku | `gpt-5.4-mini` | `gemini-3.1-flash-lite` |

So switching `PDLC_DEFAULT_LLM_PROVIDER` keeps the persona→tier association and
auto-selects each provider's equivalent — Anthropic-family providers keep the real
Opus/Sonnet/Haiku models; OpenAI/Gemini/etc. map to their highest/general/cheap models.

### Where to change models / tiers

- **Default tier → model table** — [`services/pdlc-engine/app/llm/tier_map.py`](https://github.com/pdlc-os/pdlcflow/blob/main/services/pdlc-engine/app/llm/tier_map.py) (`DEFAULT_TIER_MAP`). Edit this to change which model each tier resolves to per provider. Provider model IDs drift — verify against your account.
- **A persona's tier** — the `tier:` field in its soul-spec, `packages/pdlc-graph/pdlc_graph/personas/<persona>.md`.
- **Active provider** — `PDLC_DEFAULT_LLM_PROVIDER` (env).
- **Per-tenant / per-agent overrides** — see [Per-tenant & per-agent model overrides](#per-tenant--per-agent-model-overrides) below.

### Per-tenant & per-agent model overrides

Beyond the defaults, each **org** can override the provider + tier→model table, and each
**agent within an org** can be pinned to an exact model. Resolution is, in order:

1. **Per-agent** — `agent_llm_config(org_id, agent_persona)` → exact `model_id`.
2. **Per-org default** — `org_llm_config(org_id)` → provider + `tier_map`.
3. **Instance default** — `PDLC_DEFAULT_LLM_PROVIDER` (env) + `tier_map.py`.
4. **Fallback** — Bedrock + Claude.

These take effect when the engine runs with `PDLC_WIRE_LLM=true` and a Postgres
`PDLC_TASK_STORE` (so the factory has a DB). Both config tables are RLS-scoped to the org.

**Set them two ways:**

- **Admin API** (Nexus Console → Models settings), scoped to the caller's org:
  | Method & path | Effect |
  | --- | --- |
  | `PUT /v1/admin/models/org-default` | set the org's provider + `tier_map` |
  | `GET /v1/admin/models/org-default` | read it |
  | `PUT /v1/admin/models/agent-overrides/{persona}` | pin a persona to a provider + `model_id` |
  | `GET /v1/admin/models/agent-overrides` | list per-agent overrides |
  | `DELETE /v1/admin/models/agent-overrides/{persona}` | clear one |

  ```bash
  curl -X PUT "$API/v1/admin/models/org-default?org_id=$ORG" -H 'content-type: application/json' \
    -d '{"provider":"openai","tier_map":{"premium":"gpt-5.5","balanced":"gpt-5.4","economy":"gpt-5.4-mini"}}'
  curl -X PUT "$API/v1/admin/models/agent-overrides/neo?org_id=$ORG" -H 'content-type: application/json' \
    -d '{"agent_persona":"neo","provider":"anthropic","model_id":"claude-opus-4-8"}'
  ```

- **Directly in the DB** — tables `org_llm_config` / `agent_llm_config`.

**Source files:** factory resolution [`services/pdlc-engine/app/llm/factory.py`](https://github.com/pdlc-os/pdlcflow/blob/main/services/pdlc-engine/app/llm/factory.py) · admin API [`services/pdlc-engine/app/routes/admin/models.py`](https://github.com/pdlc-os/pdlcflow/blob/main/services/pdlc-engine/app/routes/admin/models.py) · table models [`services/pdlc-engine/app/db/models.py`](https://github.com/pdlc-os/pdlcflow/blob/main/services/pdlc-engine/app/db/models.py) (`OrgLLMConfig`, `AgentLLMConfig`).

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

> Auth asserts the principal at the app layer; **RLS FORCE** (Phase 3) makes Postgres enforce the same org boundary at the wire. They compose — auth is the trustworthy source of `org_id` that RLS keys on. See *Row-level security* below.

## Row-level security (Phase 3 — DB-enforced tenant isolation)

`0002` enables RLS + an `org_id = current_setting('app.org_id')` policy on the org-scoped tables; `0003` **FORCE**s it on the tenant-content tables. Because superusers bypass RLS, the **app connects as a non-superuser role** so the policy actually applies:

- **`PDLC_DB_URL`** → the app role (`pdlc_app`), created by the compose Postgres init script (`postgres-init/01-app-role.sh`) with `ALTER DEFAULT PRIVILEGES` so owner-created tables auto-grant it DML.
- **`PDLC_MIGRATION_DB_URL`** → the owner (`postgres`) — DDL + `FORCE` run here (`alembic upgrade head`). Defaults to `PDLC_DB_URL` when unset (single-role dev, no enforcement).
- Every adapter sets `app.org_id` per transaction (`db.rls.set_org_context`), so the app sees only its org's rows; an insert/read for another org returns nothing / is rejected **at the database**.
- **`org_members` is RLS-locked too** (`0004`). Login can't be org-scoped (it resolves a user's org by email *before* any context exists), so it goes through a narrow **`SECURITY DEFINER` `auth_lookup(email)`** function (owned by a superuser → bypasses RLS for that one lookup, `EXECUTE` granted only to the app role). The app role can therefore log a user in but **cannot** read another org's membership directly.

Verified against real Postgres (the `integration` CI job): as the non-owner role, cross-org reads return zero rows and cross-org inserts are rejected (`test_rls_force_blocks_cross_org_as_non_owner_role`); `org_members` is invisible cross-org yet login still works via the definer (`test_org_members_rls_locked_but_login_works_via_definer`).

### Artifact isolation

PRDs, design docs, reviews, episodes, etc. are namespaced **`{org_id}/{project_id}/{path}`** (filesystem dir / S3 key). The **org is the authoritative tenant** — the runner binds it per turn from the thread id (the JWT-bound org when auth is on), so a node only ever writes under its own tenant prefix even if a `project_id` is forged. `project_id`/`path` are sanitized (no traversal, no absolute paths), and the filesystem store pins every resolved path under its base dir. So one session's / repo's / tenant's files never mix with another's.

Wiring is defensive: `wire_persistence`, `build_checkpointer`, `wire_event_bus`, and `wire_dispatcher` each try to construct the configured real backend and **fall back to the in-memory default if its infrastructure is unreachable** — logging a warning rather than crashing. So:

- The engine **always boots**, even with a bad `PDLC_DB_URL` or no Redis.
- Misconfiguration degrades a feature (e.g. checkpoints become non-durable) instead of taking the service down.
- Watch the startup logs (`docker compose logs -f api`) for lines like `PostgresSaver unavailable (...); falling back to MemorySaver` to confirm a real backend actually engaged — a green boot does **not** by itself prove Postgres is wired.

## Real execution (test / merge / deploy / scan) — single-user self-host only

By default, Construction/Operation's outermost side-effects are **deterministic
simulations**: `SimulatedTestRunner` scripts pass/fail, `SimulatedVCS` returns a
fake merge SHA, deploy is a labeled no-op, and security checks report `skipped`.
This keeps CI hermetic and multi-tenant SaaS safe.

Enabling real execution makes them actually run — clone the connected repo, run
tests/scans/build/deploy as subprocesses, and merge with local git. Because that
is **host code execution**, it is gated exactly like stdio MCP and the
subscription CLIs: it requires `PDLC_ENABLE_EXECUTION=true` **and** is refused
whenever `PDLC_AUTH_REQUIRED=true` (single-user self-host only). The project must
have a connected repository (URL + token).

| Variable | Default | Meaning |
| --- | --- | --- |
| `PDLC_ENABLE_EXECUTION` | `false` | Master switch. Real backends wire only when set **and** auth is off. |
| `PDLC_WORKSPACE_DIR` | `/tmp/pdlcflow-workspaces` | Where repos are cloned per (project, branch). |
| `PDLC_TEST_CMD` | `true` | Default per-layer test command run in the workspace. |
| `PDLC_TEST_CMD_<LAYER>` | — | Override per layer (`UNIT`, `INTEGRATION`, `CONTRACT`, `E2E`, `SECURITY`, `PERF`, `UX`, `SMOKE`). |
| `PDLC_TEST_TIMEOUT_S` | `600` | Hard per-command budget. |
| `PDLC_DEPLOY_CMD` | — | Deploy command; `{env}`/`{ref}` substituted. Print `deploy_url=<url>` to record the environment URL. |
| `PDLC_DEPLOY_WEBHOOK` | — | Alternative: POST `{env, ref, project_id}`; response `{url, id}`. |
| `PDLC_SECURITY_SCAN` | `true` | Run `pip-audit` / `npm audit` / `gitleaks` when present (absent ⇒ `skipped`, never faked clean). |

What changes when enabled: Ship performs a **real merge** (real SHA + tag pushed
to the repo's default branch) and a **real deploy** (the returned URL is what
verify smoke-tests); the Construction TDD loop and the 7 test layers run the
**real suite**; a security **finding** blocks the smoke-signoff gate; and the
night-shift Sentinel's stagnation guard is live. The three-layer
production-deploy ban still runs in front of every deploy. A failed merge/deploy
**raises** — it is never reported as success.

## Secrets (per-repo VCS tokens, tenant LLM keys)

Sensitive values are stored via a pluggable backend. A value is written with `put()` which returns an opaque **ref** saved in the DB column (e.g. `repositories.token_secret_ref`); `resolve(ref)` returns the plaintext. **`resolve` dispatches on the ref prefix**, so a deployment can switch backends and still read old refs.

| `PDLC_SECRETS_BACKEND` | Ref shape | Where the secret lives | Use |
| --- | --- | --- | --- |
| `encrypted` (default) | `enc:<ciphertext>` | Fernet-encrypted **in the DB** | Single-user self-host. Needs **`PDLC_SECRET_KEY`** (a Fernet key; `setup.sh` generates one). |
| `vault` | `vault:<path>` | HashiCorp **Vault** KV v2 | SaaS / shared. Bundled **opt-in**: `docker compose --profile vault up -d` (dev-mode; for prod point `PDLC_VAULT_ADDR` at a persistent/external Vault). Set `PDLC_VAULT_TOKEN`/`PDLC_VAULT_MOUNT`/`PDLC_VAULT_PATH_PREFIX`. |
| `env` | `env:<NAME>` | the environment variable `NAME` | Cloud provider secrets managers (or a custom location) that inject secrets as env vars. |

The bundled Vault is **off by default** to keep the stack lean. `cryptography` (Fernet) ships in the image; `hvac` (Vault) is included so `vault` works without rebuilding.

### Tenant API keys (BYOK)

An org admin can attach an LLM API key to the org's model config (and to any per-agent override) from **Studio → Nexus Console → Models**, or via `PUT /v1/admin/models/org-default` / `…/agent-overrides/{persona}` with a **write-only** `api_key` field. The key is stored through the secrets backend above; only the opaque ref lands in the DB, and reads expose only a derived `has_key` flag — never the key or the ref. `DELETE …/org-default/key` (or `…/agent-overrides/{persona}/key`) removes it.

Semantics worth knowing:

- **Resolution is fail-closed.** A stored key that can no longer be resolved (deleted Vault path, changed `PDLC_SECRET_KEY`, missing env var) makes that org's LLM calls **error** instead of silently falling back to the instance-wide env key — re-enter the key to fix. No stored key at all ⇒ the instance env key is used, as before.
- **Same-provider inheritance.** An agent override without its own key inherits the org-default key only when both point at the same provider; keys never cross provider boundaries.
- **Rotation** is just another PUT with `api_key`; replicas pick the new key up within `PDLC_SECRET_CACHE_TTL_S` (default `300`s; `0` disables the cache).

| Variable | Default | Meaning |
| --- | --- | --- |
| `PDLC_SECRET_CACHE_TTL_S` | `300` | TTL for the engine's resolved-key cache on the LLM hot path. Bounds how long a rotated key may still be served on other replicas. `0` disables caching. |

### OpenAI-compatible gateways & provider presets

Beyond the 7 first-party providers, the **`openai_compatible`** provider points an org (or a single agent) at any OpenAI-protocol endpoint — relay gateways (OpenRouter, DeepSeek, Kimi/Moonshot, GLM, SiliconFlow) or self-hosted servers (LiteLLM, vLLM, Ollama's `/v1`). It requires an explicit `endpoint` (base_url) and a complete `tier_map` (there is no built-in default), both enforced when the config is written. Tenant-supplied endpoints pass the same SSRF egress policy as probes — private/loopback endpoints (local vLLM/LiteLLM/Ollama) need `PDLC_ALLOW_PRIVATE_LLM_ENDPOINTS=true` (self-host only).

The **preset catalog** (`GET /v1/admin/models/presets`, or "Start from a preset…" on the console's Models page) ships curated entries — provider, endpoint, recommended tier map, docs link, key format hint — for one-minute onboarding: pick a preset, review the pre-filled form, paste your key, **Test**, Save. Presets are suggestions updated with each pdlcflow release; your saved org config is the truth.

### Resilient routing — failover, circuit breaker, rate limits

An org can declare an ordered **failover chain** (≤3 entries) on its model config (`failover_chain` on `PUT /v1/admin/models/org-default`): when the primary provider fails with a **retriable** error (429 / 5xx / timeout / connection), the engine retries the same persona+tier on the next candidate — a provider incident degrades to a logged fallback instead of a failed turn. Auth (401/403) and validation (4xx) errors never fail over: they're config bugs, and a doomed request must not burn the chain. Each chain entry carries its own provider/region/endpoint/tier_map and its **own API key** (write-only `api_key`; keyed providers *require* one so a fallback can't silently bill the operator's env key). For streaming, failover applies only until the first token is yielded — models are never spliced mid-answer.

A Redis-backed **circuit breaker** per (org, provider[:gateway-host]) skips a repeatedly-failing fallback for a cooldown (open → half-open single probe → close), so a dead provider costs one timeout per cooldown, not one per call. The optional per-org **RPM limiter** (`PDLC_RATE_LIMIT_ENABLED`) enforces a fixed-window quota in Redis; rejection raises a clear rate-limit error and never triggers failover. Both **fail open** when Redis is unavailable. Every fallback/transition/rejection is an OTel metric (`pdlc.llm.fallbacks`, `pdlc.llm.breaker_transitions`, `pdlc.llm.rate_limited` — see the Grafana "Resilience" row) plus a clickstream event.

| Variable | Default | Meaning |
| --- | --- | --- |
| `PDLC_LLM_FAILOVER_ENABLED` | `true` | Kill switch — `false` reverts to single-candidate resolution instantly. (Inert until an org configures a chain.) |
| `PDLC_LLM_BREAKER_THRESHOLD` | `5` | Failures within the window that trip a breaker OPEN. |
| `PDLC_LLM_BREAKER_WINDOW_S` | `60` | Failure-counting window. |
| `PDLC_LLM_BREAKER_COOLDOWN_S` | `30` | How long an OPEN breaker skips the candidate before the half-open probe. |
| `PDLC_RATE_LIMIT_ENABLED` | `false` | Enforce the per-org RPM quota. |
| `PDLC_LLM_RPM_DEFAULT` | `60` | Calls/min per (org, provider, tier) bucket until per-org quotas ship. |

### Egress & proxies

Enterprise deployments route outbound HTTPS through a corporate proxy, often with a TLS-inspecting CA. pdlcflow's LLM egress is configured **explicitly** — never reliant on ambient `HTTPS_PROXY` env vars whose per-SDK behavior varies:

| Variable | Default | Meaning |
| --- | --- | --- |
| `PDLC_EGRESS_PROXY_URL` | — | Outbound proxy for LLM calls, e.g. `http://proxy.corp:3128`. |
| `PDLC_EGRESS_NO_PROXY` | — | Comma-separated host suffixes that bypass the proxy (in-cluster Ollama, local vLLM). |
| `PDLC_EGRESS_CA_BUNDLE` | — | PEM bundle path for TLS-inspection CAs. Validated loudly at boot. |

**Honest support matrix** (also logged at boot when egress is configured):

| Providers | Proxy | CA bundle | Org extra headers |
| --- | --- | --- | --- |
| `anthropic`, `openai`, `azure`, `openai_compatible` | ✅ (httpx passthrough) | ✅ | ✅ |
| `ollama` | ✅ (client_kwargs; `NO_PROXY` exemptions apply) | ✅ | ✅ |
| `bedrock` | ✅ (botocore Config) | ⚠️ via `AWS_CA_BUNDLE` env | ❌ (signed requests) |
| `gemini` | ⚠️ env fallback (set only if unset — operator env never overwritten) | ⚠️ `SSL_CERT_FILE` | ❌ |
| `vertex` | ❌ (gRPC — use network-level egress) | ❌ | ❌ |
| CLI providers | inherit process env | n/a | n/a |

Connectivity probes (`POST /admin/models/test`) use the same egress path as real calls, so a probe fails exactly the way a turn would.

**Org extra headers** (relay gateways often need routing hints like `X-Gateway-Key`): set `extra_headers` on the org model config (console or PUT). Guardrails: max 8 headers, name/value limits, and `Authorization`/`Host`/`Cookie`/`Content-*`/`Proxy-*` are rejected — headers are routing hints, never a second credential channel (BYOK owns auth).

### Pricing overrides & budgets

Spend numbers on the dashboards are **estimates for visibility — never used for billing**. The price sheet is a versioned catalog shipped with each release (`pricing_catalog.json`), layered under per-org **pricing overrides** (`PUT /v1/admin/pricing/overrides`, or Settings → Models → Pricing & budget): resolution is *override → catalog → preset hint → provider wildcard → **unpriced***. Unknown models now report `usd_estimate: null` — visible as *unpriced*, not disguised as $0. Overrides are versioned like any other config change and travel with export/import.

An org can set a **monthly soft budget** (`PUT /v1/admin/budget`): month-to-date estimated spend is evaluated on the clickstream path (memoized, fail-silent) and crossing 50/80/100% fires a `budget.threshold` event exactly once per org/month/threshold — surfaced as chips + a progress bar on the console. Alerts never block turns.

### Config history, rollback & promotion

Every change to the org/agent model config (console, API, preset apply, import) records the **full prior state** in an immutable, RLS-isolated history (`llm_config_versions`) — who, when, and a field-level diff (secrets render only as *set/changed/cleared*). The console's **History** panel shows the timeline; **Rollback** restores any version in one click (the rollback itself becomes a new history entry, and a stored key that no longer resolves is dropped with a re-enter prompt rather than restored blind). Retention: `PDLC_LLM_CONFIG_VERSION_KEEP` (default `50`) versions per scope.

**Export/Import** moves a proven provider set between orgs (the staging → production promotion flow): `GET /v1/admin/models/export` produces a JSON document that **never contains key material**; `POST /v1/admin/models/import?dry_run=true` returns a reviewable per-item plan (create/overwrite/error + whether each secret is reusable or needs re-entry), and the real import applies atomically, re-using the same validators as the PUT routes — an import cannot smuggle in a config the API would reject.

### Provider connectivity probes

`POST /v1/admin/models/test` runs a minimal live completion against a **candidate** config (provider/model/region/endpoint + optional one-shot `api_key`) or the **saved** config for a scope (`{"scope": "org-default", "use_saved_key": true}` or `"agent:<persona>"`) — so a bad key, model id, or endpoint is caught **before** it breaks a turn. Responses are `{ok, latency_ms, error_class, tested_model, message}` with a stable error taxonomy (`auth_error`, `model_not_found`, `access_denied`, `endpoint_unreachable`, `rate_limited`, `timeout`, `bad_request`, …). The last result per scope is kept in `llm_provider_health` and served by `GET /v1/admin/models/health` for status chips. Probes are limited to 10/min per org.

| Variable | Default | Meaning |
| --- | --- | --- |
| `PDLC_LLM_PROBE_TIMEOUT_S` | `10` | Hard wall-clock budget per probe; expiry reports `error_class: "timeout"`. |
| `PDLC_LLM_HEALTH_INTERVAL_S` | `0` | Opt-in background probe of the **instance default** provider feeding `/health/ready`'s `llm` field (`ok`/`degraded`/`unprobed`). `0` disables; also requires `PDLC_WIRE_LLM=true`. Tenant configs are never probed in the background (that would spend tenants' keys on synthetic traffic). |
| `PDLC_ALLOW_PRIVATE_LLM_ENDPOINTS` | `false` | SSRF guard escape hatch: allow probing endpoints that resolve to private/loopback/link-local addresses. Needed for self-host with a local Ollama; keep off for SaaS. |


---


---
<!-- nav:bottom -->
⏮ [First: Overview](01-overview.md) · ◀ [Prev: Installation](02-installation.md) · [🏠 Home](README.md) · [Next: Launching & Operating](04-launching.md) ▶ · [Last: Evals Framework](17-evals.md) ⏭
