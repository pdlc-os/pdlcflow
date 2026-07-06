"""LLM error classification for failover decisions.

`classify(exc)` → "retriable" | "auth" | "fatal":

  retriable → try the next candidate in the org's failover chain
              (429 / 5xx / timeouts / connection errors — provider incidents)
  auth      → never failover (the config is broken, not the provider;
              surfacing it is the fix — see BYOK's fail-closed rationale)
  fatal     → never failover (4xx validation: bad model id, oversized prompt…
              a doomed request would burn the whole chain for nothing)

Default is FATAL (fail closed). LangChain providers raise heterogeneous
exception types, so classification is by status-code attributes where present,
then by type-name matching — same approach as app/llm/probe.classify_error,
which answers the finer-grained "what should the admin fix" question; this one
answers only "is another provider worth trying".
"""

from __future__ import annotations

import socket
from typing import Literal

Classification = Literal["retriable", "auth", "fatal"]

_RETRIABLE_MARKERS = (
    "timeout", "ratelimit", "throttl", "toomanyrequests", "overloaded",
    "serviceunavailable", "internalserver", "connect", "apiconnection",
    "serverunavailable",
)
_AUTH_MARKERS = ("authentication", "unauthorized", "unrecognizedclient",
                 "signature", "permission", "forbidden", "accessdenied")


def classify(exc: BaseException) -> Classification:
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    if status is not None:
        if status in (401, 403):
            return "auth"
        if status == 429 or status >= 500:
            return "retriable"
        if 400 <= status < 500:
            return "fatal"

    low = type(exc).__name__.lower()
    if any(m in low for m in _AUTH_MARKERS):
        return "auth"
    if isinstance(exc, (TimeoutError, ConnectionError, socket.gaierror)):
        return "retriable"
    if any(m in low for m in _RETRIABLE_MARKERS):
        return "retriable"
    if isinstance(exc, OSError):
        return "retriable"
    return "fatal"
