"""Live token streaming seam — llm_port publishes token frames when wired."""

from __future__ import annotations

from pdlc_graph import llm_port


def test_no_streaming_without_publisher():
    # default: no publisher -> complete() returns full text, emits nothing
    out = llm_port.complete("atlas", "draft the overview")
    assert out.startswith("[stub:atlas:")


def test_streaming_publishes_start_chunks_done_and_returns_full_text():
    frames: list[dict] = []
    llm_port.set_token_publisher(lambda thread, frame: frames.append((thread, frame)))
    tok = llm_port.set_thread_context("org:proj:t1")
    try:
        out = llm_port.complete("atlas", "draft the overview")
    finally:
        llm_port.reset_thread_context(tok)
        llm_port.reset_token_publisher()

    types = [f["type"] for _t, f in frames]
    assert types[0] == "token" and frames[0][1].get("start") is True
    assert frames[0][1]["persona"] == "atlas"
    assert frames[-1][1].get("done") is True
    # the streamed chunks reconstruct exactly the full completion
    streamed = "".join(f.get("chunk", "") for _t, f in frames)
    assert streamed == out
    assert all(t == "org:proj:t1" for t, _f in frames)


def test_streaming_requires_thread_context():
    frames: list = []
    llm_port.set_token_publisher(lambda thread, frame: frames.append(frame))
    try:
        # publisher set but NO thread context -> no streaming
        llm_port.complete("neo", "design it")
    finally:
        llm_port.reset_token_publisher()
    assert frames == []
