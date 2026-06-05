"""Runtime ports — the seams the GraphRunner drives through.

Mirrors the pdlc-graph ports philosophy: every side effect is an injectable
port with an in-memory default so the whole command → gate → resume loop runs
in-process in tests. The engine injects production adapters at boot:

- GateStore   in-memory  →  Postgres `approval_gates` rows
- EventBus    in-memory  →  Redis Pub/Sub (WebSocket fan-out)

A "pending interaction" is the unified record for both interrupt kinds the
graph raises: `approval` (the 8 gates) and `user_input_required` (Socratic /
Sketch question rounds). The plan (§1.3) models both as approval_gates rows.
"""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from typing import Protocol
from uuid import UUID, uuid4


@dataclass
class PendingInteraction:
    thread_id: str
    org_id: str
    project_id: str
    kind: str  # "approval" | "user_input_required"
    payload: dict
    gate_kind: str | None = None  # set for approval interrupts
    status: str = "open"  # open | resolved
    id: UUID = field(default_factory=uuid4)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["id"] = str(self.id)
        return d


# --------------------------------------------------------------------------- #
# Gate store
# --------------------------------------------------------------------------- #
class GateStore(Protocol):
    def open(self, rec: PendingInteraction) -> PendingInteraction: ...
    def get(self, gate_id: UUID) -> PendingInteraction | None: ...
    def list_open(self, *, org_id: str | None = None, project_id: str | None = None) -> list[PendingInteraction]: ...
    def resolve(self, gate_id: UUID, status: str = "resolved") -> None: ...
    def close_open_for_thread(self, thread_id: str) -> None: ...


class InMemoryGateStore:
    def __init__(self) -> None:
        self._by_id: dict[UUID, PendingInteraction] = {}
        self._lock = threading.Lock()

    def open(self, rec: PendingInteraction) -> PendingInteraction:
        with self._lock:
            self._by_id[rec.id] = rec
        return rec

    def get(self, gate_id: UUID) -> PendingInteraction | None:
        return self._by_id.get(gate_id)

    def list_open(
        self, *, org_id: str | None = None, project_id: str | None = None
    ) -> list[PendingInteraction]:
        out = []
        for rec in self._by_id.values():
            if rec.status != "open":
                continue
            if org_id is not None and rec.org_id != org_id:
                continue
            if project_id is not None and rec.project_id != project_id:
                continue
            out.append(rec)
        return out

    def resolve(self, gate_id: UUID, status: str = "resolved") -> None:
        with self._lock:
            rec = self._by_id.get(gate_id)
            if rec is not None:
                rec.status = status

    def close_open_for_thread(self, thread_id: str) -> None:
        with self._lock:
            for rec in self._by_id.values():
                if rec.thread_id == thread_id and rec.status == "open":
                    rec.status = "superseded"


# --------------------------------------------------------------------------- #
# Event bus (WebSocket fan-out)
# --------------------------------------------------------------------------- #
class EventBus(Protocol):
    def publish(self, channel: str, frame: dict) -> None: ...
    def history(self, channel: str) -> list[dict]: ...
    # async iterator: replay recent history, then stream live frames.
    def listen(self, channel: str): ...


class InMemoryEventBus:
    """Records frames per channel; the WebSocket handler streams them via
    `listen()`. Production swaps this for the Redis-backed bus (same interface).
    """

    _POLL_S = 0.1

    def __init__(self) -> None:
        self._history: dict[str, list[dict]] = {}
        self._lock = threading.Lock()

    def publish(self, channel: str, frame: dict) -> None:
        with self._lock:
            self._history.setdefault(channel, []).append(frame)

    def history(self, channel: str) -> list[dict]:
        with self._lock:
            return list(self._history.get(channel, []))

    async def listen(self, channel: str):
        """Replay existing frames, then yield new ones as they're published.

        Runs until the consumer (the WS task) is cancelled on disconnect.
        """
        import asyncio

        cursor = 0
        while True:
            frames = self.history(channel)
            while cursor < len(frames):
                yield frames[cursor]
                cursor += 1
            await asyncio.sleep(self._POLL_S)


# --------------------------------------------------------------------------- #
# Module-level singletons (set at boot; reset in tests)
# --------------------------------------------------------------------------- #
_gate_store: GateStore = InMemoryGateStore()
_event_bus: EventBus = InMemoryEventBus()


def set_gate_store(store: GateStore) -> None:
    global _gate_store
    _gate_store = store


def set_event_bus(bus: EventBus) -> None:
    global _event_bus
    _event_bus = bus


def get_gate_store() -> GateStore:
    return _gate_store


def get_event_bus() -> EventBus:
    return _event_bus


def reset_runtime_ports() -> None:
    global _gate_store, _event_bus
    _gate_store = InMemoryGateStore()
    _event_bus = InMemoryEventBus()
