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

    # Clickstream
    clickstream_sink: Literal["jsonl", "postgres", "firehose"] = "jsonl"
    firehose_stream_name: str | None = None

    # S3 / artifacts
    s3_artifacts_bucket: str = "pdlcflow-artifacts-dev"
    s3_events_bucket: str = "pdlcflow-events-dev"

    # CORS
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])


settings = Settings()
