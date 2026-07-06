"""$ per 1M tokens for cost rollups — dashboards only, NEVER billing decisions.

The price sheet is a versioned data file (`pricing_catalog.json`, updated with
each release) instead of a frozen dict, layered under per-org overrides:

  resolution: org override → catalog exact (provider/model) →
              preset pricing_hints (gateway models, PRD-04) →
              catalog wildcard (provider/*) → None (UNPRICED)

Unknown models estimate to **None**, not $0.0 — "unpriced" must be visible in
dashboards, not disguised as free (rollup consumers already COALESCE nulls).
Overrides live in `org_llm_config.pricing_override` (PRD-07), shaped
`{"<provider>/<model_id>": {"in": $/1M, "out": $/1M}}`.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _load() -> tuple[str, dict[str, dict[str, float]]]:
    raw = json.loads((Path(__file__).parent / "pricing_catalog.json").read_text())
    return raw["version"], raw["prices"]


def catalog_version() -> str:
    return _load()[0]


def catalog_prices() -> dict[str, dict[str, float]]:
    return _load()[1]


def estimate_usd(
    provider: str,
    model_id: str,
    usage: dict[str, int],
    overrides: dict | None = None,
) -> float | None:
    key = f"{provider}/{model_id}"
    price: dict | None = None
    if overrides and key in overrides:
        price = overrides[key]
    else:
        prices = catalog_prices()
        if key in prices:
            price = prices[key]
        else:
            hint = _catalog_hint(provider, model_id)
            if hint is not None:
                price = {"in": hint[0], "out": hint[1]}
            elif f"{provider}/*" in prices:
                price = prices[f"{provider}/*"]
    if price is None:
        return None  # unpriced — visible, not silently $0
    try:
        return (usage["input"] * float(price["in"])
                + usage["output"] * float(price["out"])) / 1_000_000
    except Exception:  # malformed override — never break a completion
        return None


def _catalog_hint(provider: str, model_id: str) -> tuple[float, float] | None:
    """Preset catalog pricing hints for gateway models (PRD-04)."""
    try:
        from .presets import load_catalog

        return load_catalog().pricing_hint(provider, model_id)
    except Exception:  # pricing must never break a completion callback
        return None
