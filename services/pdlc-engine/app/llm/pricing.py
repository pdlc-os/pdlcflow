"""Per-provider $ per 1M tokens for cost rollups.

Numbers are rough public-list ballparks at design time. Tenants can override
via `org_llm_config.pricing_override` (added in Phase B). Pricing is for the
admin dashboard's `usd_estimate` — never used for billing decisions.
"""

from __future__ import annotations

# (input_$_per_1M, output_$_per_1M)
PRICES: dict[tuple[str, str], tuple[float, float]] = {
    ("bedrock",   "anthropic.claude-opus-4-8"):    (15.0, 75.0),
    ("bedrock",   "anthropic.claude-sonnet-4-6"):  (3.0,  15.0),
    ("bedrock",   "anthropic.claude-haiku-4-5"):   (0.8,  4.0),
    ("anthropic", "claude-opus-4-8"):              (15.0, 75.0),
    ("anthropic", "claude-sonnet-4-6"):            (3.0,  15.0),
    ("anthropic", "claude-haiku-4-5"):             (0.8,  4.0),
    ("vertex",    "claude-opus-4-8"):              (15.0, 75.0),
    ("vertex",    "claude-sonnet-4-6"):            (3.0,  15.0),
    ("vertex",    "claude-haiku-4-5"):             (0.8,  4.0),
    ("openai",    "gpt-5.5"):                      (5.0,  30.0),
    ("openai",    "gpt-5.4"):                      (2.5,  15.0),
    ("openai",    "gpt-5.4-mini"):                 (0.75, 4.5),
    ("azure",     "gpt-5.5"):                      (5.0,  30.0),
    ("azure",     "gpt-5.4"):                      (2.5,  15.0),
    ("azure",     "gpt-5.4-mini"):                 (0.75, 4.5),
    ("gemini",    "gemini-3.1-pro"):               (2.0,  10.0),
    ("gemini",    "gemini-3.5-flash"):             (0.3,  2.5),
    ("gemini",    "gemini-3.1-flash-lite"):        (0.1,  0.4),
    ("ollama",    "*"):                            (0.0,  0.0),  # local; no $
}


def estimate_usd(provider: str, model_id: str, usage: dict[str, int]) -> float:
    key = (provider, model_id)
    if key not in PRICES:
        key = (provider, "*")
    if key not in PRICES:
        return 0.0
    inp, out = PRICES[key]
    return (usage["input"] * inp + usage["output"] * out) / 1_000_000
