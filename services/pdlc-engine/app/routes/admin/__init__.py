"""Nexus Console admin routes — live, initiatives, domains, squads, agents,
features (time-travel), exports, models, narrative."""

from fastapi import APIRouter, Depends

from ...auth.local import require_admin
from .agents import router as agents_router
from .context import router as context_router
from .domains import router as domains_router
from .evals import router as evals_router
from .exports import router as exports_router
from .features import router as features_router
from .initiatives import router as initiatives_router
from .live import router as live_router
from .models import router as models_router
from .narrative import router as narrative_router
from .squads import router as squads_router
from .threads import router as threads_router

# Every admin route requires the admin/owner role when auth is enforced (no-op when off).
router = APIRouter(dependencies=[Depends(require_admin)])
router.include_router(live_router)
router.include_router(initiatives_router)
router.include_router(domains_router)
router.include_router(squads_router)
router.include_router(agents_router)
router.include_router(features_router)
router.include_router(exports_router)
router.include_router(models_router)
router.include_router(evals_router)
router.include_router(narrative_router)
router.include_router(context_router)
router.include_router(threads_router)
