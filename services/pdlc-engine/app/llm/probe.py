"""Provider connectivity probe — answers "will this config actually work?".

A probe is a minimal live chat completion (attempted with max_tokens=1) built
through the SAME `_BUILDERS` path the factory uses for real turns, so it
validates exactly what a turn would run: auth, invoke permission, the specific
model id, and region/endpoint routing. A models-list call can't do that
(list ≠ invoke permission on Bedrock/Vertex; Azure deployments aren't listed).

The prober is an injectable port (`set_prober`) mirroring the repo's
`set_emitter`/`set_tracer` seams — tests inject a fake and CI never touches the
network. Engine-side (not in pdlc-graph) because probing is an admin/ops
concern, not a graph concern.

Also here: the error taxonomy (SDK exception → stable `error_class` with a
sanitized human message — raw SDK errors can echo headers/URLs), the SSRF guard
for candidate endpoints, a small per-org probe rate limit, and the in-process
instance-default status consumed by /health/ready. Instance status deliberately
lives in memory, not in the RLS'd health table — it is operator state, not
tenant state.
"""

from __future__ import annotations

import concurrent.futures as _futures
import ipaddress
import logging
import socket
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from urllib.parse import urlparse

from ..config import settings

log = logging.getLogger(__name__)

ERROR_CLASSES = (
    "auth_error", "access_denied", "model_not_found", "endpoint_unreachable",
    "rate_limited", "timeout", "bad_request", "endpoint_forbidden",
    "secret_unresolvable", "unknown",
)

# Sanitized, human-written message per class — never the raw SDK exception.
MESSAGES = {
    "auth_error": "Provider rejected the credentials (key invalid or revoked).",
    "access_denied": "Authenticated, but this account lacks invoke access to the "
                     "model (check plan / IAM / model access).",
    "model_not_found": "Provider rejected the model id (check spelling / account access).",
    "endpoint_unreachable": "Could not reach the provider endpoint (DNS, network, or wrong URL).",
    "rate_limited": "Provider throttled the request — credentials work; try again shortly.",
    "timeout": "No response within the probe budget (PDLC_LLM_PROBE_TIMEOUT_S).",
    "bad_request": "Provider rejected the request shape (check region / endpoint / model pairing).",
    "endpoint_forbidden": "Endpoint blocked by egress policy (private / link-local addresses "
                          "require PDLC_ALLOW_PRIVATE_LLM_ENDPOINTS).",
    "secret_unresolvable": "The stored key could not be resolved — re-enter the key in "
                           "Settings → Models.",
    "unknown": "Probe failed for an unclassified reason (see server logs).",
}


@dataclass
class ProbeResult:
    ok: bool
    latency_ms: int | None = None
    error_class: str | None = None
    tested_model: str | None = None
    message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def failure(error_class: str, *, tested_model: str | None = None,
            latency_ms: int | None = None) -> ProbeResult:
    return ProbeResult(ok=False, latency_ms=latency_ms, error_class=error_class,
                       tested_model=tested_model,
                       message=MESSAGES.get(error_class, MESSAGES["unknown"]))


# ---------------------------------------------------------------------------
# Error taxonomy — table-ish classifier with an `unknown` fallback. Order
# matters: TimeoutError subclasses OSError (py≥3.10), gaierror subclasses
# OSError, so specific checks come first.
# ---------------------------------------------------------------------------

def classify_error(exc: BaseException) -> str:
    name = type(exc).__name__
    low = name.lower()
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(exc, (TimeoutError, _futures.TimeoutError)) or "timeout" in low:
        return "timeout"
    if (isinstance(exc, (ConnectionError, socket.gaierror))
            or "connect" in low or "apiconnection" in low):
        return "endpoint_unreachable"
    if (status == 401 or "authentication" in low or "unauthorized" in low
            or "unrecognizedclient" in low or "signature" in low):
        return "auth_error"
    if (name == "AccessDeniedException" or status == 403
            or "permission" in low or "forbidden" in low):
        return "access_denied"
    if status == 404 or "notfound" in low:
        return "model_not_found"
    if (status == 429 or "ratelimit" in low or "throttl" in low
            or "toomanyrequests" in low):
        return "rate_limited"
    # Bedrock reports a bad modelId as ValidationException.
    if "validation" in low and "model" in str(exc).lower():
        return "model_not_found"
    if status == 400 or "badrequest" in low or "validation" in low or "invalidrequest" in low:
        return "bad_request"
    if isinstance(exc, OSError):
        return "endpoint_unreachable"
    return "unknown"


# ---------------------------------------------------------------------------
# SSRF guard — a candidate `endpoint` is an arbitrary URL this server will
# connect to with admin-supplied credentials attached.
# ---------------------------------------------------------------------------

class EndpointNotAllowed(ValueError):
    """Endpoint rejected by the egress policy (message is safe to surface)."""


def validate_endpoint(url: str | None, *, allow_private: bool | None = None) -> None:
    """Raise EndpointNotAllowed unless `url` passes the egress policy.

    Policy: http(s) only; the host must not resolve to loopback / RFC-1918 /
    link-local (cloud metadata) / reserved space — unless the caller's escape
    hatch applies (default: PDLC_ALLOW_PRIVATE_LLM_ENDPOINTS; MCP passes its
    own PDLC_MCP_ALLOW_PRIVATE_NETWORKS flag).
    """
    if not url:
        return
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise EndpointNotAllowed("endpoint must be http(s)")
    host = parsed.hostname
    if not host:
        raise EndpointNotAllowed("endpoint has no host")
    if allow_private is None:
        allow_private = getattr(settings, "allow_private_llm_endpoints", False)
    if allow_private:
        return
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise EndpointNotAllowed("endpoint hostname does not resolve") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise EndpointNotAllowed(
                "endpoint resolves to a private/loopback/link-local address"
            )


# ---------------------------------------------------------------------------
# Per-org probe rate limit — probes cost real (tiny) provider spend and could
# be abused as an oracle. In-process sliding window; PRD-05 may later swap in
# the shared Redis limiter.
# ---------------------------------------------------------------------------

PROBE_LIMIT_PER_MIN = 10
_PROBE_WINDOW: dict[str, list[float]] = {}


def probe_allowed(org_id: str, *, limit: int = PROBE_LIMIT_PER_MIN,
                  window_s: float = 60.0) -> bool:
    now = time.monotonic()
    recent = [t for t in _PROBE_WINDOW.get(org_id, []) if now - t < window_s]
    if len(recent) >= limit:
        _PROBE_WINDOW[org_id] = recent
        return False
    recent.append(now)
    _PROBE_WINDOW[org_id] = recent
    return True


def reset_probe_limiter() -> None:
    _PROBE_WINDOW.clear()


# ---------------------------------------------------------------------------
# The prober itself + injectable port.
# ---------------------------------------------------------------------------

def _real_probe(cfg, model_id: str, timeout_s: float) -> ProbeResult:
    from .factory import _BUILDERS

    def _call() -> None:
        model = _BUILDERS[cfg.provider](cfg, model_id)
        try:
            # Cap output where the provider accepts the kwarg; retry uncapped
            # where it doesn't (param naming varies across SDKs).
            model.bind(max_tokens=1).invoke("ping")
        except TypeError:
            model.invoke("ping")

    t0 = time.monotonic()
    ex = _futures.ThreadPoolExecutor(max_workers=1)
    try:
        ex.submit(_call).result(timeout=timeout_s)
    except _futures.TimeoutError:
        return failure("timeout", tested_model=model_id,
                       latency_ms=int((time.monotonic() - t0) * 1000))
    except Exception as exc:
        cls = classify_error(exc)
        log.debug("probe failed: %s → %s", type(exc).__name__, cls)
        return failure(cls, tested_model=model_id,
                       latency_ms=int((time.monotonic() - t0) * 1000))
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return ProbeResult(ok=True, latency_ms=int((time.monotonic() - t0) * 1000),
                       tested_model=model_id)


_prober: Callable[..., ProbeResult] = _real_probe


def set_prober(fn: Callable[..., ProbeResult]) -> None:
    """Tests inject a fake `(cfg, model_id, timeout_s) -> ProbeResult` here."""
    global _prober
    _prober = fn


def reset_prober() -> None:
    global _prober
    _prober = _real_probe


def run_probe(cfg, model_id: str, timeout_s: float | None = None) -> ProbeResult:
    budget = timeout_s if timeout_s is not None else getattr(settings, "llm_probe_timeout_s", 10)
    return _prober(cfg, model_id, budget)


# ---------------------------------------------------------------------------
# Instance-default status for /health/ready. Written by the optional
# background loop (PDLC_LLM_HEALTH_INTERVAL_S > 0, requires wire_llm) or by an
# operator-triggered probe; "unprobed" preserves today's behavior by default.
# ---------------------------------------------------------------------------

_instance_status: str = "unprobed"  # "ok" | "degraded" | "unprobed"


def record_instance_probe(result: ProbeResult) -> None:
    global _instance_status
    _instance_status = "ok" if result.ok else "degraded"


def instance_llm_status() -> str:
    return _instance_status


def reset_instance_status() -> None:
    global _instance_status
    _instance_status = "unprobed"


async def instance_health_loop() -> None:
    """Probe the instance-default provider on an interval (opt-in)."""
    import asyncio

    from .factory import LLMProviderFactory
    from .tier_map import resolve_model_id

    interval = getattr(settings, "llm_health_interval_s", 0)
    while True:
        try:
            cfg = LLMProviderFactory()._instance_default()
            model_id = resolve_model_id(cfg.provider, "balanced")
            result = await asyncio.to_thread(run_probe, cfg, model_id)
            record_instance_probe(result)
        except Exception as exc:  # the loop must never die
            log.warning("instance health probe failed to run: %s", exc)
        await asyncio.sleep(interval)
