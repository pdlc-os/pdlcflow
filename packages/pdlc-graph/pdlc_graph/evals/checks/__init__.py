"""Importing this package registers every concrete eval into the registry."""

from __future__ import annotations

from . import agent_output, citation, drift, groundedness  # noqa: F401  (import = register)
