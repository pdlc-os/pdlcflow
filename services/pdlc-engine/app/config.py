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

    # LLM defaults
    default_llm_provider: Literal[
        "bedrock", "anthropic", "vertex", "azure", "openai", "gemini", "ollama"
    ] = "bedrock"
    bedrock_region: str = "us-east-1"
    ollama_endpoint: str = "http://localhost:11434"

    # Runtime adapters — off by default so dev/test stay hermetic.
    # wire_llm: route persona completions through the provider factory (needs creds).
    # use_postgres_checkpointer: share graph state across processes (needs Postgres
    #   + langgraph-checkpoint-postgres); otherwise an in-process MemorySaver is used.
    wire_llm: bool = False
    use_postgres_checkpointer: bool = False
    pg_pool_max_size: int = 20
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
    judge_tier: str = "opus"  # LLM tier for the LLM-as-judge (resolves via the factory)
    # Comma-separated eval ids forced to BLOCK their gate on failure (opt-in),
    # e.g. "groundedness,citation". Empty => measure-only.
    eval_blocking: str = ""

    # CORS
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])


settings = Settings()
