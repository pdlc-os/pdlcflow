"""Execution arc (T1-1/2/3, T1-4) — REAL backends, hermetically.

Local `git` against `file://` bare repos and subprocesses running local
commands need no network, so these exercise the actual SubprocessTestRunner,
GitVCS (a real merge!), CommandDeployer, and SubprocessScanner — not fakes.
The guard matrix mirrors the stdio-MCP tests.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from app.config import settings
from app.runtime import workspace as W
from app.runtime.deploy_backend import CommandDeployer
from app.runtime.security_backend import SubprocessScanner
from app.runtime.test_backend import SubprocessTestRunner
from app.runtime.vcs_backend import GitMergeError, GitVCS
from pdlc_graph.execution_context import (
    ExecutionContext,
    reset_execution_context,
    set_execution_context,
)


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def _enabled(monkeypatch):
    monkeypatch.setattr(settings, "enable_execution", True)
    monkeypatch.setattr(settings, "auth_required", False)
    yield


@pytest.fixture
def _ctx():
    tok = set_execution_context(ExecutionContext(
        project_id="11111111-1111-1111-1111-111111111111",
        feature="dark mode", branch="feature/dark-mode"))
    yield
    reset_execution_context(tok)


# ----- guard matrix (single-user self-host only) -------------------------------


def test_execution_guard_matrix(monkeypatch):
    monkeypatch.setattr(settings, "enable_execution", False)
    monkeypatch.setattr(settings, "auth_required", False)
    with pytest.raises(W.ExecutionDisabled, match="ENABLE_EXECUTION"):
        W.guard_execution()
    assert W.execution_enabled() is False

    monkeypatch.setattr(settings, "enable_execution", True)
    W.guard_execution()  # single-user self-host: allowed
    assert W.execution_enabled() is True

    monkeypatch.setattr(settings, "auth_required", True)  # multi-user → refused
    with pytest.raises(W.ExecutionDisabled, match="multi-user"):
        W.guard_execution()
    assert W.execution_enabled() is False


def test_backends_not_wired_in_multi_user(monkeypatch):
    from app.runtime.test_backend import wire_test_runner
    from app.runtime.vcs_backend import wire_vcs

    monkeypatch.setattr(settings, "enable_execution", True)
    monkeypatch.setattr(settings, "auth_required", True)
    assert wire_test_runner(settings) is False
    assert wire_vcs(settings) is False


# ----- workspace + GitVCS against a REAL local bare repo -----------------------


def _make_remote_with_feature_branch(tmp_path: Path) -> Path:
    """A bare 'remote' with main + a feature/dark-mode branch ahead of it."""
    origin = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    seed.mkdir()
    _git("init", "-b", "main", cwd=seed)
    _git("config", "user.email", "t@t", cwd=seed)
    _git("config", "user.name", "t", cwd=seed)
    (seed / "README.md").write_text("base\n")
    _git("add", ".", cwd=seed)
    _git("commit", "-m", "base", cwd=seed)
    _git("checkout", "-b", "feature/dark-mode", cwd=seed)
    (seed / "feature.txt").write_text("the feature\n")
    _git("add", ".", cwd=seed)
    _git("commit", "-m", "add feature", cwd=seed)
    _git("checkout", "main", cwd=seed)
    _git("clone", "--bare", str(seed), str(origin), cwd=tmp_path)
    return origin


def test_git_vcs_performs_a_real_merge(monkeypatch, tmp_path, _enabled, _ctx):
    origin = _make_remote_with_feature_branch(tmp_path)
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path / "ws"))
    monkeypatch.setattr(W, "_resolve_repo",
                        lambda pid: (f"file://{origin}", "main", None))

    result = GitVCS().merge_to_main(
        feature="dark mode", version="v1.2.0", description="Ship dark mode")

    assert result["strategy"] == "merge" and result["tag"] == "v1.2.0"
    assert len(result["sha"]) >= 10 and "sim" not in result["sha"]
    # The merge actually landed on the remote's main (feature.txt now present).
    verify = tmp_path / "verify"
    _git("clone", str(origin), str(verify), cwd=tmp_path)
    assert (verify / "feature.txt").exists()
    log = subprocess.run(["git", "log", "--oneline", "--merges"], cwd=verify,
                         capture_output=True, text=True).stdout
    assert "Merge feature/dark-mode" in log


def test_git_vcs_merge_conflict_raises(monkeypatch, tmp_path, _enabled, _ctx):
    # Create a conflict: main and feature both edit README differently.
    origin = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    seed.mkdir()
    _git("init", "-b", "main", cwd=seed)
    _git("config", "user.email", "t@t", cwd=seed)
    _git("config", "user.name", "t", cwd=seed)
    (seed / "f.txt").write_text("base\n")
    _git("add", ".", cwd=seed)
    _git("commit", "-m", "base", cwd=seed)
    _git("checkout", "-b", "feature/dark-mode", cwd=seed)
    (seed / "f.txt").write_text("feature version\n")
    _git("add", ".", cwd=seed)
    _git("commit", "-m", "feat", cwd=seed)
    _git("checkout", "main", cwd=seed)
    (seed / "f.txt").write_text("main version\n")
    _git("add", ".", cwd=seed)
    _git("commit", "-m", "main edit", cwd=seed)
    _git("clone", "--bare", str(seed), str(origin), cwd=tmp_path)

    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path / "ws"))
    monkeypatch.setattr(W, "_resolve_repo", lambda pid: (f"file://{origin}", "main", None))
    with pytest.raises(GitMergeError, match=r"conflict|failed"):
        GitVCS().merge_to_main(feature="dark mode", version="v1", description="x")


# ----- SubprocessTestRunner (real subprocess) ----------------------------------


def test_test_runner_pass_fail(monkeypatch, tmp_path, _enabled, _ctx):
    ws = W.RepoWorkspace(tmp_path, "main", "file://x", "file://x")
    monkeypatch.setattr(W.RepoWorkspace, "acquire", classmethod(lambda cls, pid, *, branch: ws))

    monkeypatch.setattr(settings, "test_cmd", "true")
    out = SubprocessTestRunner().run_layer("unit", "t1")
    assert out["passed"] is True and out["layer"] == "unit"

    monkeypatch.setattr(settings, "test_cmd_unit", "false")  # per-layer override wins
    out = SubprocessTestRunner().run_layer("unit", "t1")
    assert out["passed"] is False and "FAIL" in out["report"]


def test_test_runner_no_context_fails_safe(monkeypatch, _enabled):
    # No execution context bound → error, never a fabricated pass.
    out = SubprocessTestRunner().run_layer("unit", "t1")
    assert out["passed"] is False and "runner error" in out["report"]


# ----- CommandDeployer ---------------------------------------------------------


def test_deployer_parses_url_from_command(monkeypatch, _enabled):
    monkeypatch.setattr(settings, "deploy_webhook", None)
    monkeypatch.setattr(settings, "deploy_cmd",
                        "echo deploying; echo deploy_url=https://staging.acme.app")
    # no ctx → cwd None is fine for echo
    out = CommandDeployer().deploy(env="staging", ref="abc123", feature="f")
    assert out["url"] == "https://staging.acme.app" and out["simulated"] is False


def test_deployer_nothing_configured_is_honest_noop(monkeypatch, _enabled):
    monkeypatch.setattr(settings, "deploy_webhook", None)
    monkeypatch.setattr(settings, "deploy_cmd", None)
    out = CommandDeployer().deploy(env="staging", ref="abc", feature="f")
    assert out["url"] is None and out["simulated"] is True


def test_deployer_command_failure_raises(monkeypatch, _enabled):
    monkeypatch.setattr(settings, "deploy_webhook", None)
    monkeypatch.setattr(settings, "deploy_cmd", "exit 3")
    with pytest.raises(RuntimeError, match="deploy command failed"):
        CommandDeployer().deploy(env="staging", ref="abc", feature="f")


# ----- SubprocessScanner -------------------------------------------------------


def test_scanner_skips_when_tools_absent(monkeypatch, tmp_path, _enabled, _ctx):
    ws = W.RepoWorkspace(tmp_path, "main", "file://x", "file://x")
    monkeypatch.setattr(W.RepoWorkspace, "acquire", classmethod(lambda cls, pid, *, branch: ws))
    monkeypatch.setattr("app.runtime.security_backend.shutil.which", lambda _t: None)
    dep = SubprocessScanner().scan("dependency_audit")
    sec = SubprocessScanner().scan("secret_scan")
    assert dep["skipped"] is True and dep["passed"] is True  # skipped, never faked clean
    assert sec["skipped"] is True
