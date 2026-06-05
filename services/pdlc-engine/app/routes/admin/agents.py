"""Per-persona heatmap — usage, token spend, approval rate, P0 finding rate."""

from fastapi import APIRouter

router = APIRouter(prefix="/agents", tags=["admin", "agents"])


@router.get("/heatmap")
def heatmap() -> dict:
    personas = ["atlas", "bolt", "echo", "friday", "jarvis",
                "muse", "neo", "phantom", "pulse", "sentinel"]
    return {"personas": personas, "cells": [], "phase": "A stub"}
