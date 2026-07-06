"""Auth wiring — select the user store + bootstrap the first admin at boot."""

from __future__ import annotations

import logging

from .passwords import hash_password
from .store import InMemoryUserStore, get_user_store, set_user_store

log = logging.getLogger("pdlc.auth")


def wire_auth(settings) -> None:
    """Pick the user store (Postgres when a DB is configured, else in-memory) and
    bootstrap the env-configured admin if no users exist. Always safe to call."""
    # Honesty guard: only local JWT auth is implemented. PDLC_AUTH_MODE=cognito
    # used to be silently ignored — a deployment that believed it enabled SSO
    # kept plain local auth. Refuse to boot rather than mislead (security
    # posture beats the never-block-boot rule here).
    mode = getattr(settings, "auth_mode", "local")
    if mode != "local":
        raise RuntimeError(
            f"PDLC_AUTH_MODE={mode!r} is not implemented — only 'local' auth "
            f"exists today (OIDC/Cognito is tracked in "
            f"docs/.research/stub-gaps-roadmap.md T2-4). Refusing to start "
            f"with a misleading auth configuration."
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
