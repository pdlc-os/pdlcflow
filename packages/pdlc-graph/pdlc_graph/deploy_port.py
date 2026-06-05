"""Deploy port — environment-tier inference, the prod-deploy ban, and the
deployments register.

Three-layer production-deploy ban (plan §10.3), independent by design:

  layer 1 — `select_deploy_targets` filters production out of the candidate set
            (partition at selection).
  layer 2 — `assert_deploy_allowed` refuses a production tier under autonomous
            (night-shift) flow (validate at activate).
  layer 3 — the Sentinel evaluator's `prod-deploy-attempted` abort condition
            (runtime check; pdlc_graph/sentinel/evaluator.py).

Tier inference uses token-boundary matching with a priority order so `pre-prod`
and `non-prod` resolve to pre-production before the bare `prod` rule fires.
The register defaults to in-memory; the engine injects a Postgres-backed one.
"""

from __future__ import annotations

import re
from typing import Protocol

VALID_TIERS = ("dev", "test", "staging", "pre-production", "production")

# (tier, tokens) in priority order — first match wins.
_TIER_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("pre-production", ("pre-prod", "preprod", "pre-production", "non-prod", "nonprod", "non-production")),
    ("staging", ("staging", "stage", "stg")),
    ("test", ("test", "qa", "uat")),
    ("dev", ("dev", "development", "sandbox", "sbx", "local")),
    ("production", ("prod", "production", "live")),
]


class DeployBanError(Exception):
    """Raised when a production deploy is attempted under autonomous flow."""


def _tokens(env: str) -> set[str]:
    return {t for t in re.split(r"[-_/.]", env.lower()) if t}


def infer_tier(env: str) -> str:
    """Infer a tier from an environment name (token-boundary, priority-ordered)."""
    toks = _tokens(env)
    joined = env.lower()
    for tier, needles in _TIER_RULES:
        for n in needles:
            # token match, or substring for multi-token needles like "pre-prod"
            if n in toks or (("-" in n or len(n) > 4) and n in joined):
                return tier
    return "dev"


def select_deploy_targets(envs: list[str]) -> list[str]:
    """Layer 1 — drop production-tier environments from the candidate set."""
    return [e for e in envs if infer_tier(e) != "production"]


def assert_deploy_allowed(tier: str, *, night_shift: bool) -> None:
    """Layer 2 — refuse a production deploy under autonomous flow."""
    if tier == "production" and night_shift:
        raise DeployBanError(
            "production deploy refused under night-shift (ns-abort:prod-deploy-attempted); "
            "production requires a human at the keyboard"
        )


class DeployRegister(Protocol):
    def record(self, project_id: str, *, env: str, tier: str, version: str, url: str, sha: str) -> dict: ...
    def list(self, project_id: str) -> list[dict]: ...


class InMemoryDeployRegister:
    def __init__(self) -> None:
        self._rows: list[dict] = []

    def record(self, project_id: str, *, env: str, tier: str, version: str, url: str, sha: str) -> dict:
        row = {
            "project_id": project_id,
            "env": env,
            "tier": tier,
            "version": version,
            "url": url,
            "sha": sha,
        }
        self._rows.append(row)
        return row

    def list(self, project_id: str) -> list[dict]:
        return [r for r in self._rows if r["project_id"] == project_id]


_register: DeployRegister = InMemoryDeployRegister()


def set_deploy_register(register: DeployRegister) -> None:
    global _register
    _register = register


def reset_deploy_register() -> None:
    global _register
    _register = InMemoryDeployRegister()


def get_deploy_register() -> DeployRegister:
    return _register
