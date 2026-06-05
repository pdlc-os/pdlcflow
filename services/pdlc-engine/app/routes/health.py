"""Liveness / readiness probes."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "phase": "A"}


@router.get("/health/ready")
def ready() -> dict:
    # Phase B will check DB + Redis + Bedrock connectivity here.
    return {"status": "ready", "checks": {"db": "stub", "redis": "stub", "llm": "stub"}}
