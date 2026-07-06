"""Pydantic Settings — single source of env-var truth."""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PDLC_", env_file=".env", extra="ignore")

    # Service
    environment: Literal["dev", "staging", "prod"] = "dev"
    log_level: Literal["debug", "info", "warning", "error"] = "info"

    # Database
    db_url: str = "postgresql+asyncpg://postgres:pdlc@localhost:5432/pdlc"

    # Redis (pub/sub, rate limit, Arq queue)
    redis_url: str = "redis://localhost:6379/0"

    # Auth — local JWT (self-host) or cognito (SaaS)
    auth_mode: Literal["local", "cognito"] = "local"
    jwt_secret: str = "change-me-in-production"
    jwt_alg: str = "HS256"
    jwt_ttl_s: int = 60 * 60 * 12
    # Enforce auth: when True, protected routes require a valid JWT and derive
    # org_id from the token (not the request). Off => open API (today's default).
    auth_required: bool = False
    # Env-bootstrapped first admin: on boot, if set and no users exist, create an
    # org + admin user. Further users come from the admin-only /v1/auth/users.
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None

    # Secrets (e.g. per-repo VCS tokens). `secrets_backend` selects where NEW
    # secrets are written; resolve() dispatches by ref prefix, so mixed refs work.
    #   encrypted (default): Fernet-encrypt; the ref IS the ciphertext ("enc:…")
    #     stored in the DB. Needs `secret_key`. Best for single-user self-host.
    #   vault: HashiCorp Vault KV v2; ref is "vault:<path>". Bundle is opt-in
    #     (compose `--profile vault`) or point at any Vault / a custom address.
    #   env: ref is "env:NAME"; resolve reads that env var (cloud/custom managers
    #     that inject secrets as env).
    secrets_backend: Literal["encrypted", "vault", "env"] = "encrypted"
    secret_key: str | None = None  # Fernet key for the 'encrypted' backend
    vault_addr: str = "http://vault:8200"
    vault_token: str | None = None
    vault_mount: str = "secret"
    vault_path_prefix: str = "pdlcflow/repos"
    # TTL for the factory's resolved-secret cache (BYOK hot path). 0 disables.
    # After a key rotation, other replicas may serve the old key for up to this
    # long — acceptable because rotation replaces a working key with another.
    secret_cache_ttl_s: int = 300

    # Provider connectivity probes (POST /admin/models/test). The probe is a
    # minimal live completion; the timeout is the hard wall-clock budget.
    llm_probe_timeout_s: float = 10.0
    # Background probe of the INSTANCE default provider for /health/ready's llm
    # field. 0 (default) disables; also requires wire_llm.
    llm_health_interval_s: int = 0
    # SSRF escape hatch: allow probing endpoints that resolve to private /
    # loopback addresses (self-host with a local Ollama). Keep off for SaaS.
    allow_private_llm_endpoints: bool = False

    # LLM defaults
    default_llm_provider: Literal[
        "bedrock", "anthropic", "vertex", "azure", "openai", "gemini", "ollama",
        # Subscription-backed local CLIs — SINGLE-USER SELF-HOST ONLY (see below).
        "claude_code", "codex", "gemini_cli",
    ] = "bedrock"
    bedrock_region: str = "us-east-1"
    ollama_endpoint: str = "http://localhost:11434"

    # Subscription-CLI providers (claude_code / codex / gemini_cli) shell out to the
    # locally-installed, logged-in CLI so completions bill against your Claude Max /
    # ChatGPT / Gemini subscription. Single-user self-host ONLY: disabled by default,
    # and the factory refuses them when auth is enabled (multi-tenant/SaaS).
    enable_cli_providers: bool = False
    claude_code_bin: str = "claude"
    codex_bin: str = "codex"
    gemini_cli_bin: str = "gemini"

    # Runtime adapters — off by default so dev/test stay hermetic.
    # wire_llm: route persona completions through the provider factory (needs creds).
    # use_postgres_checkpointer: share graph state across processes (needs Postgres
    #   + langgraph-checkpoint-postgres); otherwise an in-process MemorySaver is used.
    wire_llm: bool = False
    use_postgres_checkpointer: bool = False
    pg_pool_max_size: int = 20
    # When RLS is enforced the app connects as a non-owner role (db_url); DDL /
    # migrations run as the owner. Defaults to db_url when unset (single-role dev).
    migration_db_url: str | None = None
    # use_arq_dispatch: enqueue graph turns to the Arq worker instead of running
    # them inline in the API (needs Redis + the Redis bus for pending delivery).
    use_arq_dispatch: bool = False
    # use_redis_bus: cross-process WebSocket fan-out via Redis pub/sub (also the
    # transport for live night-shift verdicts). Off => in-process in-memory bus.
    use_redis_bus: bool = False

    # Persistence backends (Phase H bundle 3). Off => in-memory (test/dev default).
    artifact_store: Literal["memory", "filesystem", "s3"] = "memory"
    artifact_dir: str = "/var/lib/pdlcflow/artifacts"  # filesystem store base
    s3_endpoint_url: str | None = None  # set for MinIO (e.g. http://minio:9000)
    task_store: Literal["memory", "postgres"] = "memory"
    analytics_backend: Literal["memory", "postgres"] = "memory"

    # Clickstream
    clickstream_sink: Literal["jsonl", "postgres", "firehose"] = "jsonl"
    firehose_stream_name: str | None = None

    # S3 / artifacts
    s3_artifacts_bucket: str = "pdlcflow-artifacts-dev"
    s3_events_bucket: str = "pdlcflow-events-dev"

    # Live token streaming — publish `token` frames to the thread channel as
    # agents generate, powering the Studio's live "drafting" preview. Off in
    # tests (so the no-stream path is byte-identical); on for dev/compose.
    stream_tokens: bool = False

    # Evals (Phase J). Off => the eval harness is a strict no-op. When on, evals
    # score agent output at major steps and emit eval.scored/eval.blocked events.
    run_evals: bool = False
    judge_tier: str = "premium"  # LLM tier for the LLM-as-judge (resolves via the factory)
    # Comma-separated eval ids forced to BLOCK their gate on failure (opt-in),
    # e.g. "groundedness,citation". Empty => measure-only.
    eval_blocking: str = ""

    # Observability — OpenTelemetry traces + metrics for the Nexus dashboard.
    # Off by default so dev/test/CI stay hermetic (no SDK provider installed → the
    # graph's tracer port is a no-op, byte-identical output). When enabled, the
    # engine exports OTLP to a collector (Tempo for traces, Prometheus for
    # metrics) which the Grafana + Streamlit Nexus dashboards read from. Enable
    # with the compose `observability` profile, which sets PDLC_OTEL_ENABLED=true.
    otel_enabled: bool = False
    otel_service_name: str = "pdlc-engine"
    # OTLP/gRPC endpoint of the collector. The standard OTEL_EXPORTER_OTLP_ENDPOINT
    # env var is honoured too; this is the pdlc-prefixed convenience knob.
    otel_endpoint: str = "http://otel-collector:4317"
    # Export spans/metrics to stdout as well (local debugging without a collector).
    otel_console_export: bool = False
    # Metric export cadence (seconds) to the collector.
    otel_metric_interval_s: int = 15
    # Instrument FastAPI request spans (server-side HTTP traces) in addition to
    # the graph turn/node/LLM spans.
    otel_instrument_fastapi: bool = True

    # CORS
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])


settings = Settings()
