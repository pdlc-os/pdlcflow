"""Provider preset catalog — curated, versioned, vendored data (not code).

`catalog.json` ships in the package and is validated at first load (a malformed
catalog fails loudly in CI/boot, never silently at request time). Presets are
SUGGESTIONS the console prefills from; the org's saved config remains the only
truth. Adding a vendor is a data PR — no factory changes.

First-party presets mirror `tier_map.DEFAULT_TIER_MAP` (a test asserts they
don't drift). `openai_compatible` presets open the relay/gateway ecosystem
(OpenRouter, DeepSeek, Kimi, GLM, SiliconFlow, LiteLLM, vLLM, …) and MUST carry
an endpoint. `pricing_hints` seed `estimate_usd` for gateway models so their
usage isn't silently $0 in dashboards (PRD-07 adds real overrides).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

_TIERS = ("premium", "balanced", "economy")
# Providers whose auth comes from the platform/host (no per-org API key).
_NO_KEY_PROVIDERS = {"bedrock", "vertex", "ollama"}


class Preset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    provider: str
    endpoint: str | None = None
    region: str | None = None
    tier_map: dict[str, str]
    docs_url: str | None = None
    key_hint: str | None = None
    # model_id -> {"in": $/1M input, "out": $/1M output}
    pricing_hints: dict[str, dict[str, float]] = {}
    tags: list[str] = []

    @field_validator("tier_map")
    @classmethod
    def _complete_tier_map(cls, v: dict[str, str]) -> dict[str, str]:
        if set(v) != set(_TIERS) or not all(v.values()):
            raise ValueError(f"tier_map must define non-empty {_TIERS}")
        return v

    @field_validator("pricing_hints")
    @classmethod
    def _sane_hints(cls, v: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
        for model, hint in v.items():
            if set(hint) != {"in", "out"} or hint["in"] < 0 or hint["out"] < 0:
                raise ValueError(f"pricing hint for {model!r} must be non-negative in/out")
        return v

    @model_validator(mode="after")
    def _gateway_needs_endpoint(self) -> Preset:
        if self.provider == "openai_compatible" and not self.endpoint:
            raise ValueError(f"preset {self.id!r}: openai_compatible requires an endpoint")
        return self

    @property
    def needs_secret(self) -> bool:
        return self.provider not in _NO_KEY_PROVIDERS


class Catalog(BaseModel):
    catalog_version: str
    presets: list[Preset]

    @model_validator(mode="after")
    def _unique_ids(self) -> Catalog:
        ids = [p.id for p in self.presets]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate preset ids in catalog")
        return self

    def get(self, preset_id: str) -> Preset | None:
        return next((p for p in self.presets if p.id == preset_id), None)

    def search(self, q: str | None) -> list[Preset]:
        if not q:
            return list(self.presets)
        needle = q.lower()
        return [
            p for p in self.presets
            if needle in p.id.lower() or needle in p.label.lower()
            or any(needle in t.lower() for t in p.tags)
        ]

    def pricing_hint(self, provider: str, model_id: str) -> tuple[float, float] | None:
        """$/1M (input, output) for a (provider, model) any preset knows about."""
        for p in self.presets:
            if p.provider == provider and model_id in p.pricing_hints:
                h = p.pricing_hints[model_id]
                return (h["in"], h["out"])
        return None


@lru_cache(maxsize=1)
def load_catalog() -> Catalog:
    raw = json.loads((Path(__file__).parent / "catalog.json").read_text())
    return Catalog.model_validate(raw)
