"""Shared egress helpers for provider builders (PRD-08).

The operator configures an outbound proxy / CA bundle once (instance-level
`PDLC_EGRESS_*` settings); orgs may add extra request headers (relay-gateway
routing hints). Builders call these helpers to apply whatever their SDK
supports — the honest per-provider matrix lives in the wiki and the boot-time
egress report; nothing here pretends uniformity.

httpx clients are memoized per (proxy, ca) pair — constructing one per build()
call would leak connection pools.
"""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse


def no_proxy_match(url: str | None, no_proxy: tuple[str, ...]) -> bool:
    """True when the target host matches a PDLC_EGRESS_NO_PROXY suffix."""
    if not url or not no_proxy:
        return False
    host = urlparse(url).hostname or ""
    return any(host == s or host.endswith("." + s.lstrip(".")) or host.endswith(s)
               for s in no_proxy if s)


def effective_proxy(net, target_url: str | None = None) -> str | None:
    """The proxy to use for this target (None when exempted via no_proxy)."""
    if net is None or not net.proxy_url:
        return None
    if no_proxy_match(target_url, net.no_proxy):
        return None
    return net.proxy_url


@lru_cache(maxsize=8)
def _clients(proxy: str | None, ca: str | None):
    import httpx

    verify = ca if ca else True
    return (httpx.Client(proxy=proxy, verify=verify),
            httpx.AsyncClient(proxy=proxy, verify=verify))


def httpx_clients(net, target_url: str | None = None):
    """(sync, async) httpx clients for an SDK's http_client passthrough, or
    (None, None) when no egress config applies (SDK builds its own default)."""
    if net is None:
        return None, None
    proxy = effective_proxy(net, target_url)
    ca = net.ca_bundle
    if not proxy and not ca:
        return None, None
    return _clients(proxy, ca)


def merged_headers(net) -> dict[str, str] | None:
    """Org extra_headers for SDKs with a default_headers passthrough."""
    if net is None or not net.extra_headers:
        return None
    return dict(net.extra_headers)
