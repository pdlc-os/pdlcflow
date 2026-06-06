"""Engine-side token streaming — wiring + frames reach the thread bus channel."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.runtime import get_event_bus, get_runner, set_runner, wire_token_streaming
from app.runtime.graph_runner import GraphRunner

ORG = str(uuid4())
PROJ = str(uuid4())


def test_wire_token_streaming_toggle():
    from pdlc_graph.llm_port import reset_token_publisher

    assert wire_token_streaming(SimpleNamespace(stream_tokens=False)) is False
    assert wire_token_streaming(SimpleNamespace(stream_tokens=True)) is True
    reset_token_publisher()


def test_turn_streams_token_frames_to_thread_channel():
    # Wire streaming onto the in-memory bus, then drive one brainstorm turn.
    wire_token_streaming(SimpleNamespace(stream_tokens=True))
    set_runner(GraphRunner())  # MemorySaver runner
    thread_id = f"{ORG}:{PROJ}:{uuid4()}"
    state = {
        "org_id": ORG, "project_id": PROJ, "phase": "Inception",
        "interaction_mode": "sketch", "feature": "dark mode", "brainstorm_log": [],
    }
    get_runner().start(thread_id, state)

    frames = get_event_bus().history(f"thread:{thread_id}")
    tokens = [f for f in frames if f.get("type") == "token"]
    assert tokens, "expected streamed token frames on the thread channel"
    assert any(f.get("start") for f in tokens)
    assert any(f.get("chunk") for f in tokens)
    assert any(f.get("done") for f in tokens)
