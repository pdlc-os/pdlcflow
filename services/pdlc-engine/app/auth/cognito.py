"""Cognito JWT verification for SaaS deployments.

Phase A stub. Verifies access tokens against the user pool's JWKS endpoint
and maps Cognito groups to PDLC roles. Real implementation lands in Phase H
(SaaS hardening) along with SSO via Cognito identity providers.
"""

from __future__ import annotations

from .local import Identity


def current_identity_cognito(token: str) -> Identity:
    # TODO: validate against COGNITO_JWKS_URL; map groups → role
    raise NotImplementedError("cognito auth lands in Phase H")
