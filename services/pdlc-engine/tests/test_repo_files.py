"""GitHub repo URL parsing for the repo-backed memory panel (pure, hermetic)."""

from __future__ import annotations

import pytest
from app.routes.entities import _gh_owner_repo
from fastapi import HTTPException


def test_parses_github_urls():
    assert _gh_owner_repo("https://github.com/octocat/Hello-World") == ("octocat", "Hello-World")
    assert _gh_owner_repo("https://github.com/octocat/Hello-World.git") == ("octocat", "Hello-World")
    assert _gh_owner_repo("https://github.com/octocat/Hello-World/") == ("octocat", "Hello-World")
    assert _gh_owner_repo("git@github.com:octocat/Hello-World.git") == ("octocat", "Hello-World")


def test_rejects_non_github():
    with pytest.raises(HTTPException):
        _gh_owner_repo("https://gitlab.com/x/y")
