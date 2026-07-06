"""CommandDeployer (execution arc, T1-3) — the real deploy trigger.

Executes the operator-configured deploy: a shell command
(`PDLC_DEPLOY_CMD`, with `{env}`/`{ref}` substituted) run in the project's
workspace, or a webhook POST (`PDLC_DEPLOY_WEBHOOK`). Returns the real
environment URL — parsed from the command's stdout (a line `deploy_url=…` or
the last URL printed) or from the webhook response — which replaces ship.py's
hardcoded `*.example.app` and is what `verify.smoke_tests` then hits.

The 3-layer production-deploy ban runs BEFORE this (in the ship node), so a
deployer is only ever reached for a permitted tier.
"""

from __future__ import annotations

import logging
import re

from ..config import settings
from .workspace import RepoWorkspace, feature_branch, run

log = logging.getLogger("pdlc.runtime.deploy")

_URL_RE = re.compile(r"https?://[^\s\"']+")


class CommandDeployer:
    def deploy(self, *, env: str, ref: str, feature: str) -> dict:
        webhook = getattr(settings, "deploy_webhook", None)
        if webhook:
            return self._webhook(webhook, env=env, ref=ref, feature=feature)
        cmd = getattr(settings, "deploy_cmd", None)
        if not cmd:
            # Execution on but nothing configured — honest no-op, not a fake URL.
            return {"url": None, "id": None, "simulated": True,
                    "note": "PDLC_DEPLOY_CMD / PDLC_DEPLOY_WEBHOOK not set"}
        rendered = cmd.format(env=env, ref=ref, feature=feature)
        from pdlc_graph.execution_context import current_execution_context

        ctx = current_execution_context()
        cwd = None
        if ctx is not None:
            try:
                cwd = RepoWorkspace.acquire(
                    ctx.project_id,
                    branch=feature_branch(ctx.feature or feature, ctx.branch)).path
            except Exception:
                cwd = None
        proc = run(["bash", "-lc", rendered], cwd=cwd,
                   timeout=getattr(settings, "test_timeout_s", 600), check=False)
        if proc.returncode != 0:
            raise RuntimeError(
                f"deploy command failed (exit {proc.returncode}):\n"
                f"{proc.stdout}\n{proc.stderr}"[:2000])
        return {"url": _parse_url(proc.stdout), "id": ref, "simulated": False}

    @staticmethod
    def _webhook(url: str, *, env: str, ref: str, feature: str) -> dict:
        import httpx

        resp = httpx.post(url, json={"env": env, "ref": ref, "feature": feature},
                          timeout=30)
        resp.raise_for_status()
        body = {}
        try:
            body = resp.json()
        except Exception:
            pass
        return {"url": body.get("url"), "id": body.get("id") or ref, "simulated": False}


def _parse_url(stdout: str) -> str | None:
    """Prefer an explicit `deploy_url=…` line; else the last URL printed."""
    for line in reversed((stdout or "").splitlines()):
        if line.strip().lower().startswith("deploy_url="):
            return line.split("=", 1)[1].strip()
    urls = _URL_RE.findall(stdout or "")
    return urls[-1] if urls else None


def wire_deployer(settings) -> bool:
    from .workspace import execution_enabled

    if not execution_enabled():
        return False
    from pdlc_graph.deploy_port import set_deployer

    set_deployer(CommandDeployer())
    log.info("real deployer wired (command/webhook execution)")
    return True
