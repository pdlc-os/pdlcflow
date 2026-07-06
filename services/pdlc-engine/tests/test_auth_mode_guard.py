"""wire_auth validates the auth mode at boot (T2-4).

'local' = self-host JWT; 'oidc' = external issuer (requires issuer + audience).
An unknown mode, or 'oidc' with incomplete config, must fail loudly so a
deployment can't believe it enabled SSO when it hasn't.
"""

from __future__ import annotations

import pytest
from app.auth.wiring import wire_auth
from app.config import settings


def test_local_mode_boots(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "local")
    wire_auth(settings)  # no raise


def test_unknown_mode_refuses_to_boot(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "cognito")  # no longer a valid mode
    with pytest.raises(RuntimeError, match="not a valid auth mode"):
        wire_auth(settings)


def test_oidc_without_config_refuses_to_boot(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "oidc")
    monkeypatch.setattr(settings, "oidc_issuer", "")
    monkeypatch.setattr(settings, "oidc_audience", "")
    with pytest.raises(RuntimeError, match="requires oidc_issuer"):
        wire_auth(settings)


def test_oidc_with_config_boots(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "oidc")
    monkeypatch.setattr(settings, "oidc_issuer", "https://issuer.example.com")
    monkeypatch.setattr(settings, "oidc_audience", "pdlc-client")
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "task_store", "memory")
    wire_auth(settings)  # no raise
