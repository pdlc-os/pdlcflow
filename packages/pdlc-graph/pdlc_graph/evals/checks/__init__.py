"""Importing this package registers every concrete eval into the registry."""

from __future__ import annotations

from . import (  # noqa: F401  (import = register)
    agent_output,
    citation,
    drift,
    groundedness,
    prod_safety,
    spec_adherence,
)
