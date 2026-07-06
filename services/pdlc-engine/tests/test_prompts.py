"""Persona prompt overrides (PRD-10) — hermetic half.

Guardrail validation and DB-free pack paths. The full lifecycle
(draft → activate → resolve → deactivate, packs, RLS) is in the integration
suite; the M0 seam itself is tested in packages/pdlc-graph.
"""

from __future__ import annotations

import uuid

import pytest
from app.main import app
from app.routes.admin.prompts import PROMPT_PERSONAS, validate_prompt_body
from fastapi import HTTPException
from fastapi.testclient import TestClient

client = TestClient(app)
ORG = str(uuid.uuid4())


def test_prompt_personas_exclude_sentinel():
    assert "sentinel" not in PROMPT_PERSONAS and len(PROMPT_PERSONAS) == 9


def test_validate_prompt_body_guardrails():
    validate_prompt_body("# Soul Spec — Muse\nYou ideate.")               # plain ok
    validate_prompt_body("---\ntier: balanced\n---\n# Muse")              # valid tier ok
    with pytest.raises(HTTPException):
        validate_prompt_body("")                                          # empty
    with pytest.raises(HTTPException):
        validate_prompt_body("   \n  ")                                   # whitespace
    with pytest.raises(HTTPException):
        validate_prompt_body("x" * (32 * 1024 + 1))                       # size cap
    with pytest.raises(HTTPException):
        validate_prompt_body("---\ntier: ultra\n---\n# Muse")             # bad tier


def test_create_draft_validation_is_db_free():
    r = client.post(f"/v1/admin/prompts/muse?org_id={ORG}", json={"body": ""})
    assert r.status_code == 422
    r = client.post(f"/v1/admin/prompts/muse?org_id={ORG}",
                    json={"body": "x" * (32 * 1024 + 1)})
    assert r.status_code == 422
    # sentinel is not a valid path param at all
    r = client.post(f"/v1/admin/prompts/sentinel?org_id={ORG}", json={"body": "x"})
    assert r.status_code == 422


def test_pack_import_validation():
    r = client.post(f"/v1/admin/prompts/import?org_id={ORG}",
                    json={"format": "something-else/v9", "prompts": {}})
    assert r.status_code == 422

    pack = {"format": "pdlcflow.prompt-pack/v1", "prompts": {
        "muse": {"body": "tuned muse"},
        "sentinel": {"body": "nope"},
        "neo": {"body": ""},
    }}
    plan = client.post(
        f"/v1/admin/prompts/import?org_id={ORG}&dry_run=true", json=pack).json()["plan"]
    assert plan["muse"] == "draft"
    assert plan["sentinel"].startswith("error")
    assert plan["neo"].startswith("error")
    # apply refuses a plan containing errors
    r = client.post(f"/v1/admin/prompts/import?org_id={ORG}", json=pack)
    assert r.status_code == 422
