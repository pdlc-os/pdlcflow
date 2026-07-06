"""Config versioning, export & import (PRD-06) — hermetic half.

Pure helpers (diff computation, the secret-export transform table) and the
DB-free import validation paths. Full lifecycle (history, rollback, retention,
promotion) lives in the integration suite.
"""

from __future__ import annotations

import uuid

from app.main import app
from app.routes.admin.models_versions import config_diff, secret_export
from fastapi.testclient import TestClient

client = TestClient(app)
ORG = str(uuid.uuid4())


# ----- diff computation --------------------------------------------------------


def test_config_diff_basic_fields():
    before = {"provider": "anthropic", "region": None, "tier_map": {"premium": "a"}}
    after = {"provider": "bedrock", "region": "us-east-1", "tier_map": {"premium": "a"}}
    diff = {d["field"]: d for d in config_diff(before, after)}
    assert diff["provider"] == {"field": "provider", "from": "anthropic", "to": "bedrock"}
    assert diff["region"]["to"] == "us-east-1"
    assert "tier_map" not in diff  # unchanged


def test_config_diff_never_renders_secret_refs():
    before = {"secret_ref": "enc:SUPERSECRETCIPHERTEXT"}
    after = {"secret_ref": "enc:OTHERSECRET"}
    (d,) = config_diff(before, after)
    assert d == {"field": "secret", "from": "set", "to": "changed"}
    assert "SUPERSECRET" not in str(d)
    assert config_diff({"secret_ref": None}, {"secret_ref": "enc:x"})[0]["to"] == "set"
    assert config_diff({"secret_ref": "enc:x"}, {"secret_ref": None})[0]["to"] == "cleared"


def test_config_diff_redacts_chain_secret_refs():
    before = {"failover_chain": []}
    after = {"failover_chain": [
        {"provider": "bedrock", "secret_ref": None},
        {"provider": "openai_compatible", "secret_ref": "enc:CHAINSECRET"},
    ]}
    (d,) = config_diff(before, after)
    assert d["to"] == [{"provider": "bedrock", "has_key": False},
                       {"provider": "openai_compatible", "has_key": True}]
    assert "CHAINSECRET" not in str(d)


def test_config_diff_none_states():
    assert config_diff(None, None) == []
    (d,) = config_diff(None, {"provider": "openai"})
    assert d["from"] is None and d["to"] == "openai"


# ----- secret export transform (§5.3) -------------------------------------------


def test_secret_export_transform_table():
    # enc: the ref IS the ciphertext — must be stripped entirely
    out = secret_export("enc:FERNETCIPHERTEXT", "anthropic")
    assert out == {"required": True, "ref_kind": "encrypted"}
    assert "FERNET" not in str(out)
    # vault/env: pointers are safe and useful
    assert secret_export("vault:pdlcflow/llm/org/x", "openai") == {
        "required": True, "ref_kind": "vault", "ref_hint": "vault:pdlcflow/llm/org/x"}
    assert secret_export("env:MY_KEY", "gemini") == {
        "required": True, "ref_kind": "env", "ref_hint": "env:MY_KEY"}
    # no ref: required mirrors whether the provider takes a key at all
    assert secret_export(None, "anthropic") == {"required": True}
    assert secret_export(None, "bedrock") == {"required": False}
    assert secret_export(None, "ollama") == {"required": False}


# ----- import validation (DB-free paths) ----------------------------------------


def _doc(org_default=None, overrides=None, fmt=1):
    return {"format_version": fmt, "org_default": org_default,
            "agent_overrides": overrides or []}


TIERS = {"premium": "a", "balanced": "b", "economy": "c"}


def test_import_rejects_unknown_format_version():
    r = client.post(f"/v1/admin/models/import?org_id={ORG}&dry_run=true",
                    json=_doc(fmt=2))
    assert r.status_code == 422


def test_import_dry_run_flags_ssrf_endpoint():
    doc = _doc(org_default={
        "provider": "openai_compatible", "endpoint": "http://169.254.169.254/v1",
        "tier_map": TIERS, "secret": {"required": True}})
    r = client.post(f"/v1/admin/models/import?org_id={ORG}&dry_run=true", json=doc)
    assert r.status_code == 200
    (item,) = r.json()["plan"]
    assert item["action"] == "error" and item["reasons"]


def test_import_dry_run_flags_keyed_chain_entry_without_resolvable_ref():
    doc = _doc(org_default={
        "provider": "openai_compatible", "endpoint": "https://8.8.8.8/v1",
        "tier_map": TIERS,
        "failover_chain": [
            {"provider": "openai", "tier_map": TIERS,
             "secret": {"required": True, "ref_kind": "encrypted"}}],
        "secret": {"required": True}})
    r = client.post(f"/v1/admin/models/import?org_id={ORG}&dry_run=true", json=doc)
    (item,) = r.json()["plan"]
    assert item["action"] == "error"
    assert any("failover_chain[0]" in reason for reason in item["reasons"])


def test_import_apply_refuses_error_plans():
    doc = _doc(org_default={
        "provider": "openai_compatible", "endpoint": "http://10.0.0.1/v1",
        "tier_map": TIERS})
    r = client.post(f"/v1/admin/models/import?org_id={ORG}", json=doc)
    assert r.status_code == 422
    assert "plan" in r.json()["detail"]
