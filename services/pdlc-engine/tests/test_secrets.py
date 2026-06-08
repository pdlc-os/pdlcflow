"""Pluggable secrets backend (encrypted / env / vault)."""

from __future__ import annotations

import pytest
from app import secretstore as S
from app.config import settings
from cryptography.fernet import Fernet


def test_encrypted_roundtrip(monkeypatch):
    monkeypatch.setattr(settings, "secret_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "secrets_backend", "encrypted")
    S.reset_secrets()
    ref = S.get_secrets().put("ghp_token123", hint="repo1")
    assert ref.startswith("enc:")
    assert ref != "ghp_token123"  # not plaintext
    assert S.get_secrets().resolve(ref) == "ghp_token123"
    S.reset_secrets()


def test_env_backend(monkeypatch):
    monkeypatch.setenv("MY_REPO_TOKEN", "abc123")
    monkeypatch.setattr(settings, "secrets_backend", "env")
    S.reset_secrets()
    ref = S.get_secrets().put("ignored", hint="MY_REPO_TOKEN")
    assert ref == "env:MY_REPO_TOKEN"
    assert S.get_secrets().resolve(ref) == "abc123"
    S.reset_secrets()


def test_encrypted_backend_requires_key(monkeypatch):
    monkeypatch.setattr(settings, "secret_key", None)
    monkeypatch.setattr(settings, "secrets_backend", "encrypted")
    S.reset_secrets()
    with pytest.raises(RuntimeError):
        S.get_secrets()
    S.reset_secrets()


def test_resolve_dispatch_handles_none_and_unknown(monkeypatch):
    monkeypatch.setattr(settings, "secrets_backend", "env")
    S.reset_secrets()
    sec = S.get_secrets()
    assert sec.resolve(None) is None
    assert sec.resolve("weird:xyz") is None
    S.reset_secrets()


def test_encrypted_ref_readable_even_when_backend_is_env(monkeypatch):
    # A deployment can switch the primary backend yet still read old enc: refs.
    monkeypatch.setattr(settings, "secret_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "secrets_backend", "encrypted")
    S.reset_secrets()
    ref = S.get_secrets().put("tok", hint="r")
    monkeypatch.setattr(settings, "secrets_backend", "env")
    S.reset_secrets()
    assert S.get_secrets().resolve(ref) == "tok"  # enc: ref still resolves
    S.reset_secrets()
