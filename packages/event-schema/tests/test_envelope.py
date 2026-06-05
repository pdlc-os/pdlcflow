from uuid import uuid4

import pytest

from event_schema import EventEnvelope, LLMTokensSpentPayload


def _base_kwargs() -> dict:
    return {
        "event_type": "llm.tokens_spent",
        "org_id": uuid4(),
        "project_id": uuid4(),
    }


def test_envelope_roundtrip():
    payload = LLMTokensSpentPayload(
        provider="bedrock",
        model_id="anthropic.claude-opus-4-7",
        tier="opus",
        agent_persona="neo",
        tokens_in=1200,
        tokens_out=380,
        usd_estimate=0.027,
    ).model_dump()
    e = EventEnvelope(**_base_kwargs(), payload=payload)
    js = e.model_dump_json()
    back = EventEnvelope.model_validate_json(js)
    assert back.event_type == "llm.tokens_spent"
    assert back.payload["provider"] == "bedrock"
    assert back.payload["tokens_in"] == 1200


def test_envelope_rejects_unknown_event_type():
    with pytest.raises(Exception):
        EventEnvelope(
            event_type="totally.made.up",
            org_id=uuid4(),
            project_id=uuid4(),
        )


def test_envelope_rejects_pii_keys():
    for key in ("prompt", "message", "content", "messages", "body"):
        with pytest.raises(Exception):
            EventEnvelope(**_base_kwargs(), payload={key: "secret"})


def test_envelope_taxonomy_dimensions_optional():
    e = EventEnvelope(**_base_kwargs(), payload={})
    assert e.squad_id is None
    assert e.initiative_id is None
    assert e.application_id is None
    assert e.domains == []
