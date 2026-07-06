"""Repo workspace + execution guard (execution arc foundation).

`guard_execution()` enforces the single-user self-host gate shared by every
real execution backend (test runner / VCS / deploy / security scan): they run
commands and clone repos on the engine host, so — exactly like stdio MCP and
the subscription CLIs — they are refused in multi-user/SaaS mode.

`RepoWorkspace` resolves a turn's project → its connected repository (url,
default_branch, token via the secretstore), clones it into a managed dir, and
checks out the feature branch. All repo/token/branch resolution lives here so
the backends stay thin. Cloning from a `file://` bare repo is fully hermetic,
so this is exercised by real (network-free) tests.
"""

from __future__ import annotations

import logging
import subprocess
import uuid
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from ..config import settings

log = logging.getLogger("pdlc.runtime.workspace")


class ExecutionDisabled(RuntimeError):
    """Real execution attempted while disabled or in multi-user mode."""


def execution_enabled() -> bool:
    return bool(getattr(settings, "enable_execution", False)) and not getattr(
        settings, "auth_required", False)


def guard_execution() -> None:
    """Raise unless single-user self-host execution is explicitly enabled."""
    if not getattr(settings, "enable_execution", False):
        raise ExecutionDisabled(
            "real execution requires PDLC_ENABLE_EXECUTION=true "
            "(single-user self-host only)")
    if getattr(settings, "auth_required", False):
        raise ExecutionDisabled(
            "real execution is not allowed in multi-user/SaaS mode "
            "(PDLC_AUTH_REQUIRED is on) — it clones repos and runs commands on "
            "the engine host")


def run(cmd: list[str], *, cwd: Path | str | None = None, timeout: int = 120,
        check: bool = True) -> subprocess.CompletedProcess:
    """Thin subprocess wrapper — text mode, captured output, hard timeout."""
    return subprocess.run(
        cmd, cwd=str(cwd) if cwd else None, timeout=timeout,
        capture_output=True, text=True, check=check)


def _tokenized_url(url: str, token: str | None) -> str:
    """Inject a token into an https git URL for a non-interactive clone. Leaves
    file:// and ssh URLs untouched (tests use file://; ssh uses keys)."""
    if not token:
        return url
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        return url
    netloc = f"x-access-token:{token}@{p.hostname}" + (f":{p.port}" if p.port else "")
    return urlunparse((p.scheme, netloc, p.path, p.params, p.query, p.fragment))


class RepoWorkspace:
    """A checked-out clone of a project's repo on the feature branch."""

    def __init__(self, path: Path, default_branch: str, remote_url: str,
                 tokenized_url: str) -> None:
        self.path = path
        self.default_branch = default_branch
        self.remote_url = remote_url
        self._tokenized_url = tokenized_url

    def git(self, *args: str, check: bool = True, timeout: int = 120) -> subprocess.CompletedProcess:
        return run(["git", *args], cwd=self.path, check=check, timeout=timeout)

    @classmethod
    def acquire(cls, project_id: str, *, branch: str | None) -> RepoWorkspace:
        """Resolve the project's repo, clone it, checkout `branch`.

        Raises ExecutionDisabled (guard) or RuntimeError (no repo / clone fail).
        The caller already holds the execution guard, but we assert again.
        """
        guard_execution()
        repo = _resolve_repo(project_id)
        if repo is None:
            raise RuntimeError(
                f"project {project_id} has no connected repository — cannot run "
                "real execution against it")
        url, default_branch, token = repo
        tokenized = _tokenized_url(url, token)

        base = Path(settings.workspace_dir) / str(project_id)
        base.mkdir(parents=True, exist_ok=True)
        dest = base / (branch or default_branch or "work").replace("/", "__")

        if not (dest / ".git").exists():
            run(["git", "clone", tokenized, str(dest)], timeout=300)
        ws = cls(dest, default_branch or "main", url, tokenized)
        # Configure a non-interactive identity for merge commits.
        ws.git("config", "user.name", settings.git_author_name)
        ws.git("config", "user.email", settings.git_author_email)
        ws.git("fetch", "origin", check=False)
        if branch:
            _checkout(ws, branch)
        return ws


def _checkout(ws: RepoWorkspace, branch: str) -> None:
    # Prefer an existing remote branch; else create it off the default.
    remote = ws.git("ls-remote", "--heads", "origin", branch, check=False)
    if remote.stdout.strip():
        ws.git("checkout", "-B", branch, f"origin/{branch}")
    else:
        ws.git("checkout", "-B", branch)


def _resolve_repo(project_id: str) -> tuple[str, str, str | None] | None:
    """(url, default_branch, token) for a project's connected repo, or None."""
    try:
        uuid.UUID(str(project_id))
    except (ValueError, TypeError):
        return None
    from sqlalchemy import text

    from ..db.rls import set_org_context
    from ..db.session import get_sync_engine
    from ..secretstore import get_secrets

    engine = get_sync_engine(settings)
    # project → repository_id → repositories row. Org context for RLS; the
    # project row carries org_id.
    with engine.begin() as conn:
        proj = conn.execute(
            text("select org_id, repository_id from projects where id = :p"),
            {"p": project_id},
        ).mappings().first()
        if not proj or not proj["repository_id"]:
            return None
        set_org_context(conn, str(proj["org_id"]))
        repo = conn.execute(
            text("select url, default_branch, token_secret_ref from repositories "
                 "where id = :r"),
            {"r": str(proj["repository_id"])},
        ).mappings().first()
    if not repo:
        return None
    token = None
    if repo["token_secret_ref"]:
        try:
            token = get_secrets().resolve(repo["token_secret_ref"])
        except Exception:
            log.warning("repo token could not be resolved; trying tokenless clone")
    return repo["url"], repo["default_branch"] or "main", token


def feature_branch(feature: str | None, ctx_branch: str | None) -> str | None:
    """The branch to operate on: an explicit context branch wins; else derive
    `feature/<slug>` from the feature name."""
    if ctx_branch:
        return ctx_branch
    if feature:
        slug = feature.strip().lower().replace(" ", "-") or "feature"
        return f"feature/{slug}"
    return None
