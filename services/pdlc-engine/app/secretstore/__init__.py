"""Pluggable secrets backend for sensitive values (per-repo VCS tokens, …).

`put(value, hint)` stores a secret and returns an opaque `ref` saved in the DB
column; `resolve(ref)` returns the plaintext. The configured backend
(`PDLC_SECRETS_BACKEND`) decides where NEW secrets go; `resolve` dispatches on the
ref prefix, so a deployment that switches backends still reads old refs.

Refs:
  enc:<ciphertext>   Fernet-encrypted in the DB (self-host default)
  vault:<path>       HashiCorp Vault KV v2 (bundled opt-in, or any Vault)
  env:<NAME>         read from environment variable NAME (cloud/custom managers)
"""

from __future__ import annotations

import os
from typing import Protocol

from ..config import settings

ENC, VAULT, ENV = "enc:", "vault:", "env:"


class _Backend(Protocol):
    prefix: str
    def put(self, value: str, *, hint: str = "") -> str: ...
    def resolve(self, ref: str) -> str | None: ...


class EncryptedBackend:
    prefix = ENC

    def __init__(self, key: str) -> None:
        from cryptography.fernet import Fernet

        self._f = Fernet(key.encode() if isinstance(key, str) else key)

    def put(self, value: str, *, hint: str = "") -> str:
        return ENC + self._f.encrypt(value.encode()).decode()

    def resolve(self, ref: str) -> str | None:
        return self._f.decrypt(ref[len(ENC):].encode()).decode()


class EnvBackend:
    prefix = ENV

    def put(self, value: str, *, hint: str = "") -> str:
        # Can't write to the environment; expect the value to already be present
        # under the variable named by `hint`.
        if not hint:
            raise ValueError("env secrets backend requires a variable name (hint)")
        return ENV + hint

    def resolve(self, ref: str) -> str | None:
        return os.environ.get(ref[len(ENV):]) or None


class VaultBackend:
    prefix = VAULT

    def __init__(self, addr: str, token: str | None, mount: str, path_prefix: str) -> None:
        import hvac  # lazy: only when vault is selected/used

        self._c = hvac.Client(url=addr, token=token)
        self._mount = mount
        self._prefix = path_prefix.strip("/")

    def put(self, value: str, *, hint: str = "") -> str:
        if not hint:
            raise ValueError("vault secrets backend requires a stable id (hint)")
        path = f"{self._prefix}/{hint}"
        self._c.secrets.kv.v2.create_or_update_secret(
            path=path, secret={"value": value}, mount_point=self._mount
        )
        return VAULT + path

    def resolve(self, ref: str) -> str | None:
        path = ref[len(VAULT):]
        r = self._c.secrets.kv.v2.read_secret_version(path=path, mount_point=self._mount)
        return r["data"]["data"].get("value")


class Secrets:
    """Facade: writes via the configured backend, reads via the matching backend."""

    def __init__(self, primary: _Backend, by_prefix: dict[str, _Backend]) -> None:
        self._primary = primary
        self._by_prefix = by_prefix

    def put(self, value: str, *, hint: str = "") -> str:
        return self._primary.put(value, hint=hint)

    def resolve(self, ref: str | None) -> str | None:
        if not ref:
            return None
        for prefix, backend in self._by_prefix.items():
            if ref.startswith(prefix):
                return backend.resolve(ref)
        return None  # unknown/legacy ref shape


def _build() -> Secrets:
    by_prefix: dict[str, _Backend] = {ENV: EnvBackend()}
    # Encrypted backend is available for reads whenever a key is present.
    if settings.secret_key:
        try:
            by_prefix[ENC] = EncryptedBackend(settings.secret_key)
        except Exception:  # pragma: no cover - bad key
            pass
    # Vault backend is built lazily; only when selected (or to read vault: refs).
    vault: _Backend | None = None
    if settings.secrets_backend == "vault":
        vault = VaultBackend(settings.vault_addr, settings.vault_token,
                             settings.vault_mount, settings.vault_path_prefix)
        by_prefix[VAULT] = vault

    backend = settings.secrets_backend
    if backend == "encrypted":
        if ENC not in by_prefix:
            raise RuntimeError("PDLC_SECRETS_BACKEND=encrypted requires PDLC_SECRET_KEY")
        primary = by_prefix[ENC]
    elif backend == "vault":
        primary = vault  # type: ignore[assignment]
    else:
        primary = by_prefix[ENV]
    return Secrets(primary, by_prefix)


_secrets: Secrets | None = None


def get_secrets() -> Secrets:
    global _secrets
    if _secrets is None:
        _secrets = _build()
    return _secrets


def reset_secrets() -> None:
    global _secrets
    _secrets = None
