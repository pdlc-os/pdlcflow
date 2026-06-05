"""Runtime adapter layer — drives the pdlc-graph engine through the API.

Wires the Phase B graph (Inception loop) to the live service: the GraphRunner
executes interrupt/resume turns, the GateStore records pending approvals +
question rounds, and the EventBus fans out frames to WebSocket clients.
"""

from .dispatch import (
    ArqDispatcher,
    InlineDispatcher,
    get_dispatcher,
    reset_dispatcher,
    set_dispatcher,
    wire_dispatcher,
)
from .graph_runner import GraphRunner, build_checkpointer, get_runner, reset_runner, set_runner
from .llm_backend import wire_llm_backend
from .ports import (
    InMemoryEventBus,
    InMemoryGateStore,
    PendingInteraction,
    get_event_bus,
    get_gate_store,
    reset_runtime_ports,
    set_event_bus,
    set_gate_store,
)

__all__ = [
    "ArqDispatcher",
    "GraphRunner",
    "InMemoryEventBus",
    "InMemoryGateStore",
    "InlineDispatcher",
    "PendingInteraction",
    "build_checkpointer",
    "get_dispatcher",
    "get_event_bus",
    "get_gate_store",
    "get_runner",
    "reset_dispatcher",
    "reset_runner",
    "reset_runtime_ports",
    "set_dispatcher",
    "set_event_bus",
    "set_gate_store",
    "set_runner",
    "wire_dispatcher",
    "wire_llm_backend",
]
