"""Auth wiring — select the user store + bootstrap the first admin at boot."""

from __future__ import annotations

import logging

from .passwords import hash_password
from .store import InMemoryUserStore, get_user_store, set_user_store

log = logging.getLogger("pdlc.auth")


def wire_auth(settings) -> None:
    """Pick the user store (Postgres when a DB is configured, else in-memory) and
    bootstrap the env-configured admin if no users exist. Always safe to call."""
    # Fail fast on a misconfigured auth mode rather than silently degrading.
    # 'local' = self-host HS256 JWT; 'oidc' = validate against an external
    # issuer's JWKS (requires issuer + audience). An unknown mode, or 'oidc'
    # with missing config, refuses to boot — a deployment that believes it
    # enabled SSO must not fall back to open/local auth unnoticed.
    mode = getattr(settings, "auth_mode", "local")
    if mode == "oidc":
        missing = [k for k in ("oidc_issuer", "oidc_audience")
                   if not getattr(settings, k, "")]
        if missing:
            raise RuntimeError(
                f"PDLC_AUTH_MODE=oidc requires {', '.join(missing)} to be set. "
                f"Refusing to start with an incomplete OIDC configuration."
            )
        if not getattr(settings, "auth_required", False):
            log.warning("auth_mode=oidc but PDLC_AUTH_REQUIRED is off — the API "
                        "is open; tokens are validated only where presented")
        log.info("auth mode: oidc (issuer=%s)", settings.oidc_issuer)
    elif mode != "local":
        raise RuntimeError(
            f"PDLC_AUTH_MODE={mode!r} is not a valid auth mode (expected "
            f"'local' or 'oidc'). Refusing to start."
        )
    # Use Postgres accounts when the durable backends are on; else in-memory.
    if getattr(settings, "task_store", "memory") == "postgres":
        try:
            from .store import PostgresUserStore

            set_user_store(PostgresUserStore(settings))
            log.info("user store: postgres")
        except Exception as exc:  # pragma: no cover - prod-only
            log.warning("postgres user store unavailable (%s); using in-memory", exc)
            set_user_store(InMemoryUserStore())

    _bootstrap_admin(settings)


def _bootstrap_admin(settings) -> None:
    email = getattr(settings, "bootstrap_admin_email", None)
    password = getattr(settings, "bootstrap_admin_password", None)
    if not email or not password:
        return
    store = get_user_store()
    try:
        if store.count_users() > 0:
            return
        org_id = store.create_org("default")
        store.create_user(org_id=org_id, email=email, pw_hash=hash_password(password), role="admin")
        log.info("bootstrapped admin user %s (org %s)", email, org_id)
    except Exception as exc:  # pragma: no cover - prod-only
        log.warning("admin bootstrap failed: %s", exc)
