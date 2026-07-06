"""The Wave 1-3 + MCP event families validate (previously they would have been
silently dropped by the emitter's fail-safe — the envelope rejects unknown
event_types by design)."""

from uuid import uuid4

from event_schema import EventEnvelope
from event_schema.envelope import actor_type_for


def test_new_event_families_validate():
    for et in (
        "admin.llm_key.set", "admin.llm_key.cleared", "admin.provider.probed",
        "admin.preset.applied", "llm_config.changed", "llm_config.rolled_back",
        "llm_config.imported", "llm_config.exported", "llm.failover",
        "llm.rate_limited", "budget.configured", "budget.threshold",
        "prompt.activated", "prompt.deactivated", "prompt_pack.exported",
        "prompt_pack.imported", "tool.called",
    ):
        EventEnvelope(event_type=et, org_id=uuid4(), project_id=uuid4(), payload={})


def test_actor_classification():
    assert actor_type_for("llm_config.changed") == "human"
    assert actor_type_for("prompt.activated") == "human"
    assert actor_type_for("llm.failover") == "system"
    assert actor_type_for("budget.threshold") == "system"
    assert actor_type_for("tool.called") == "agent"
