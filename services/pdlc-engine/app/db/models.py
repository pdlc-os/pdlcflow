"""SQLAlchemy 2.0 models — full multi-tenant schema.

See docs/.research/.langgraph-bedrock-saas-migration-2026-06-05.md §6 for the
DDL rationale and §7 for the LLM-config tables. Alembic owns the actual DDL;
these models are the typed access layer.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# ---------------- Tenancy ----------------
class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)


class User(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str | None] = mapped_column(Text)  # local auth (null for SSO/Cognito)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class OrgMember(Base):
    __tablename__ = "org_members"
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (CheckConstraint("role in ('owner','admin','member','viewer')"),)


class Squad(Base):
    __tablename__ = "squads"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    # Domain → Squad (the hierarchy: Org → Domain → Squad). Nullable: a squad may be
    # ungrouped until assigned to a domain.
    domain_id: Mapped[UUID | None] = mapped_column(ForeignKey("domains.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(CITEXT, nullable=False)
    __table_args__ = (UniqueConstraint("org_id", "slug"),)


# ---------------- Taxonomy ----------------
class Initiative(Base):
    __tablename__ = "initiatives"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    budget_usd: Mapped[float | None] = mapped_column(Numeric(12, 2))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (
        CheckConstraint("status in ('proposed','active','paused','complete','abandoned')"),
    )


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    initiative_id: Mapped[UUID | None] = mapped_column(ForeignKey("initiatives.id"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    repository: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (CheckConstraint("kind in ('service','frontend','library','infra','docs')"),)


class Domain(Base):
    __tablename__ = "domains"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (UniqueConstraint("org_id", "name"),)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    squad_id: Mapped[UUID] = mapped_column(ForeignKey("squads.id", ondelete="CASCADE"))
    application_id: Mapped[UUID | None] = mapped_column(ForeignKey("applications.id"))
    initiative_id: Mapped[UUID | None] = mapped_column(ForeignKey("initiatives.id"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(CITEXT, nullable=False)
    repository: Mapped[str | None] = mapped_column(Text)  # legacy free-form; superseded by repository_id
    repository_id: Mapped[UUID | None] = mapped_column(ForeignKey("repositories.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("org_id", "slug"),)


# ---------------- Repositories + hierarchy links ----------------
class Repository(Base):
    """A GitHub (or other VCS) repo owned by a Squad. The token is referenced via
    `token_secret_ref` — resolved per deployment mode (encrypted DB value for
    self-host; a Vault/cloud secrets ref for SaaS)."""

    __tablename__ = "repositories"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    squad_id: Mapped[UUID] = mapped_column(ForeignKey("squads.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    default_branch: Mapped[str] = mapped_column(Text, nullable=False, server_default="main")
    provider: Mapped[str] = mapped_column(Text, nullable=False, server_default="github")
    token_secret_ref: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("squad_id", "url"),
        CheckConstraint("provider in ('github','gitlab','bitbucket','other')"),
    )


class SquadInitiative(Base):
    """Squads ↔ Initiatives (many-to-many): one or more squads work on one or more
    initiatives."""

    __tablename__ = "squad_initiatives"
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    squad_id: Mapped[UUID] = mapped_column(ForeignKey("squads.id", ondelete="CASCADE"), primary_key=True)
    initiative_id: Mapped[UUID] = mapped_column(ForeignKey("initiatives.id", ondelete="CASCADE"), primary_key=True)


class InitiativeRepository(Base):
    """Initiative ↔ Repository (many-to-many): an initiative can span repos."""

    __tablename__ = "initiative_repositories"
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    initiative_id: Mapped[UUID] = mapped_column(ForeignKey("initiatives.id", ondelete="CASCADE"), primary_key=True)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), primary_key=True)


class Program(Base):
    """Cross-org umbrella. Initiatives stay org-scoped (RLS-clean); a Program links
    them ACROSS orgs. Visible to its owning org and to any org with a linked
    initiative (see the RLS policies in migration 0006)."""

    __tablename__ = "programs"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ProgramInitiative(Base):
    """Program ↔ Initiative link, tagged with the initiative's org so each org only
    sees its own links (RLS) while sharing the Program."""

    __tablename__ = "program_initiatives"
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    program_id: Mapped[UUID] = mapped_column(ForeignKey("programs.id", ondelete="CASCADE"), primary_key=True)
    initiative_id: Mapped[UUID] = mapped_column(ForeignKey("initiatives.id", ondelete="CASCADE"), primary_key=True)


# ---------------- PDLC entities ----------------
class Task(Base):
    """Replaces Beads. external_id preserves bd-NN identifiers from migrations."""

    __tablename__ = "tasks"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(nullable=False)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    external_id: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    labels: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    depends_on: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)  # blocker external_ids
    claimed_by: Mapped[str | None] = mapped_column(Text)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    branch: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (
        CheckConstraint("status in ('open','claimed','in_progress','blocked','done','abandoned')"),
        # One active branch per task in a project — enforces atomic claim semantics.
        Index(
            "tasks_active_branch_unique",
            "project_id",
            "branch",
            unique=True,
            postgresql_where=text("branch is not null"),
        ),
        # Fast ready-queue scan.
        Index("tasks_open_priority", "org_id", "project_id", "status"),
    )


class MemoryFile(Base):
    __tablename__ = "memory_files"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(nullable=False)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    s3_key: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (
        CheckConstraint(
            "kind in ('CONSTITUTION','STATE','INTENT','ROADMAP','DECISIONS',"
            "'METRICS','OVERVIEW','CHANGELOG','DEPLOYMENTS','EPISODE')"
        ),
    )


class ApprovalGate(Base):
    __tablename__ = "approval_gates"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(nullable=False)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    thread_id: Mapped[str] = mapped_column(Text, nullable=False)
    gate_kind: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    comment: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint("status in ('open','approved','rejected','edited','expired')"),
    )


# ---------------- LLM config ----------------
class OrgLLMConfig(Base):
    __tablename__ = "org_llm_config"
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    region: Mapped[str | None] = mapped_column(Text)
    endpoint: Mapped[str | None] = mapped_column(Text)
    secret_ref: Mapped[str | None] = mapped_column(Text)
    tier_map: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Ordered fallback configs (≤3): [{provider, region, endpoint, tier_map,
    # secret_ref}] — tried in order on retriable primary failures (PRD-05).
    failover_chain: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    # Org price-sheet corrections for estimate_usd (PRD-07):
    # {"<provider>/<model_id>": {"in": $/1M, "out": $/1M}}. Dashboards only.
    pricing_override: Mapped[dict | None] = mapped_column(JSONB)
    __table_args__ = (
        CheckConstraint(
            "provider in ('bedrock','anthropic','vertex','azure','openai','gemini',"
            "'ollama','openai_compatible')",
            name="ck_org_llm_config_provider",
        ),
    )


class AgentLLMConfig(Base):
    """Per-agent override. Resolution: agent → org_default → instance → fallback."""

    __tablename__ = "agent_llm_config"
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    agent_persona: Mapped[str] = mapped_column(Text, primary_key=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[str] = mapped_column(Text, nullable=False)
    region: Mapped[str | None] = mapped_column(Text)
    endpoint: Mapped[str | None] = mapped_column(Text)
    secret_ref: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint(
            "agent_persona in "
            "('atlas','bolt','echo','friday','jarvis','muse','neo','phantom','pulse','sentinel')"
        ),
        CheckConstraint(
            "provider in ('bedrock','anthropic','vertex','azure','openai','gemini',"
            "'ollama','openai_compatible')",
            name="ck_agent_llm_config_provider",
        ),
    )


class OrgBudget(Base):
    """Monthly soft budget (estimate-only, never billing) + alert thresholds."""

    __tablename__ = "org_budgets"
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    monthly_limit_usd: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    alert_pcts: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[50, 80, 100]'::jsonb"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class OrgBudgetAlert(Base):
    """Dedupe ledger — the PK fires each (org, month, threshold) exactly once."""

    __tablename__ = "org_budget_alerts"
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    month: Mapped[date] = mapped_column(Date, primary_key=True)  # first of month
    pct: Mapped[int] = mapped_column(Integer, primary_key=True)
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class LLMConfigVersion(Base):
    """Append-only history of org/agent LLM config mutations (PRD-06). The
    snapshot is the PRIOR row state (null = didn't exist); rollback writes a
    snapshot back and records itself as a new version — history never rewrites."""

    __tablename__ = "llm_config_versions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)  # 'org' | '<persona>'
    change_kind: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot: Mapped[dict | None] = mapped_column(JSONB)
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_label: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    __table_args__ = (
        CheckConstraint(
            "change_kind in ('update','delete','rollback','import','preset_apply')"
        ),
        Index("ix_llmcv_org_scope_created", "org_id", "scope", "created_at"),
    )


class LLMProviderHealth(Base):
    """Last probe result per (org, scope) — console status chips. Scope is
    'org-default' or 'agent:<persona>'; instance status is in-process only."""

    __tablename__ = "llm_provider_health"
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    scope: Mapped[str] = mapped_column(Text, primary_key=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    ok: Mapped[bool] = mapped_column(nullable=False)
    latency_ms: Mapped[int | None] = mapped_column()
    error_class: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


# ---------------- Clickstream (self-host) ----------------
class Event(Base):
    __tablename__ = "events"
    event_id: Mapped[UUID] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    org_id: Mapped[UUID] = mapped_column(nullable=False)
    squad_id: Mapped[UUID | None]
    initiative_id: Mapped[UUID | None]
    application_id: Mapped[UUID | None]
    project_id: Mapped[UUID | None]
    repository: Mapped[str | None] = mapped_column(Text)
    domains: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    # Feature-level traceability dimensions (admin drill-down).
    roadmap_id: Mapped[str | None] = mapped_column(Text)
    prd_id: Mapped[str | None] = mapped_column(Text)
    user_story_id: Mapped[str | None] = mapped_column(Text)
    plan_step: Mapped[str | None] = mapped_column(Text)
    session_id: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[UUID | None]
    causation_id: Mapped[UUID | None]
    actor: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
