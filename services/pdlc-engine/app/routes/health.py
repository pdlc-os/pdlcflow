"""Liveness / readiness probes."""

from fastapi import APIRouter

from ..llm import probe

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "phase": "A"}


@router.get("/health/ready")
def ready() -> dict:
    # llm reflects the cached instance-default probe: "ok" | "degraded" |
    # "unprobed" (the default — background probing is opt-in via
    # PDLC_LLM_HEALTH_INTERVAL_S). Informational only: a degraded LLM never
    # flips readiness, so a provider incident can't get the pod killed.
    return {
        "status": "ready",
        "checks": {"db": "stub", "redis": "stub", "llm": probe.instance_llm_status()},
    }
