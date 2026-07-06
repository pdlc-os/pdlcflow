"""wire_auth refuses to boot under an unimplemented auth mode.

PDLC_AUTH_MODE=cognito used to be silently ignored (kept local JWT). It must
now fail loudly so a deployment can't believe it enabled SSO when it hasn't.
"""

from __future__ import annotations

import pytest
from app.auth.wiring import wire_auth
from app.config import settings


def test_local_mode_boots(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "local")
    wire_auth(settings)  # no raise


def test_cognito_mode_refuses_to_boot(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "cognito")
    with pytest.raises(RuntimeError, match="not implemented"):
        wire_auth(settings)
