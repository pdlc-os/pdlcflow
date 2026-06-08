"""Entity CRUD — domains, squads, initiatives, repositories, projects.

Org-scoped (the org comes from the JWT when auth is on, else an `org_id` query
param). Writes go through `set_org_context`, so RLS lets a tenant only ever touch
its own rows. Repo tokens are stored via the secrets backend (never returned).
"""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from ..auth.local import Identity, get_principal, resolve_org
from ..config import settings
from ..db.rls import set_org_context
from ..db.session import get_sync_engine
from ..secretstore import get_secrets

router = APIRouter(tags=["entities"])


def current_org(label: str):
    def _dep(
        org_id: str | None = Query(None),
        principal: Identity | None = Depends(get_principal),
    ) -> str:
        return resolve_org(principal, org_id, label)

    return _dep


def _slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "item"
    return f"{base[:40]}-{uuid.uuid4().hex[:4]}"


def _rows(org: str, sql: str, params: dict | None = None) -> list[dict]:
    with get_sync_engine(settings).begin() as c:
        set_org_context(c, org)
        return [dict(r) for r in c.execute(text(sql), params or {}).mappings().all()]


def _one(org: str, sql: str, params: dict, *, ensure_org: bool = False) -> dict:
    with get_sync_engine(settings).begin() as c:
        set_org_context(c, org)
        if ensure_org:
            # Self-host: make sure the tenant row exists (organizations has no RLS).
            c.execute(
                text("insert into organizations (id, name, slug, created_at, settings) "
                     "values (cast(:o as uuid), 'Default', 'org-' || left(cast(:o as text), 8), now(), '{}'::jsonb) "
                     "on conflict (id) do nothing"),
                {"o": org},
            )
        return dict(c.execute(text(sql), params).mappings().one())


# ---------------- Domains ----------------
class DomainCreate(BaseModel):
    name: str


@router.get("/domains")
def list_domains(org: str = Depends(current_org("/domains"))) -> dict:
    return {"domains": _rows(org, "select id, name from domains where org_id = :o order by name", {"o": org})}


@router.post("/domains")
def create_domain(body: DomainCreate, org: str = Depends(current_org("/domains"))) -> dict:
    return _one(org, "insert into domains (id, org_id, name) values (gen_random_uuid(), :o, :n) returning id, name",
                {"o": org, "n": body.name}, ensure_org=True)


# ---------------- Squads ----------------
class SquadCreate(BaseModel):
    name: str
    domain_id: str | None = None


@router.get("/squads")
def list_squads(org: str = Depends(current_org("/squads"))) -> dict:
    return {"squads": _rows(org, "select id, name, slug, domain_id from squads where org_id = :o order by name", {"o": org})}


@router.post("/squads")
def create_squad(body: SquadCreate, org: str = Depends(current_org("/squads"))) -> dict:
    return _one(org,
                "insert into squads (id, org_id, name, slug, domain_id) "
                "values (gen_random_uuid(), :o, :n, :s, :d) returning id, name, slug, domain_id",
                {"o": org, "n": body.name, "s": _slug(body.name), "d": body.domain_id}, ensure_org=True)


# ---------------- Initiatives ----------------
class InitiativeCreate(BaseModel):
    name: str
    status: str = "active"


@router.get("/initiatives")
def list_initiatives(org: str = Depends(current_org("/initiatives"))) -> dict:
    return {"initiatives": _rows(org, "select id, name, status from initiatives where org_id = :o order by name", {"o": org})}


@router.post("/initiatives")
def create_initiative(body: InitiativeCreate, org: str = Depends(current_org("/initiatives"))) -> dict:
    return _one(org,
                "insert into initiatives (id, org_id, name, status, created_at) "
                "values (gen_random_uuid(), :o, :n, :st, now()) returning id, name, status",
                {"o": org, "n": body.name, "st": body.status}, ensure_org=True)


# ---------------- Repositories ----------------
class RepoCreate(BaseModel):
    squad_id: str
    name: str
    url: str
    token: str | None = None
    default_branch: str = "main"
    provider: str = "github"


@router.get("/repositories")
def list_repositories(
    org: str = Depends(current_org("/repositories")),
    squad_id: str | None = Query(None),
) -> dict:
    sql = ("select id, name, url, squad_id, default_branch, provider, "
           "(token_secret_ref is not null) as has_token from repositories where org_id = :o")
    params: dict = {"o": org}
    if squad_id:
        sql += " and squad_id = :sq"
        params["sq"] = squad_id
    return {"repositories": _rows(org, sql + " order by name", params)}


@router.post("/repositories")
def create_repository(body: RepoCreate, org: str = Depends(current_org("/repositories"))) -> dict:
    rid = str(uuid.uuid4())
    ref = get_secrets().put(body.token, hint=rid) if body.token else None
    return _one(org,
                "insert into repositories (id, org_id, squad_id, name, url, default_branch, provider, token_secret_ref, created_at) "
                "values (:id, :o, :sq, :n, :u, :br, :p, :ref, now()) "
                "returning id, name, url, squad_id, default_branch, provider, (token_secret_ref is not null) as has_token",
                {"id": rid, "o": org, "sq": body.squad_id, "n": body.name, "u": body.url,
                 "br": body.default_branch, "p": body.provider, "ref": ref})


@router.delete("/repositories/{repo_id}")
def delete_repository(repo_id: str, org: str = Depends(current_org("/repositories"))) -> dict:
    rows = _rows(org, "delete from repositories where id = :id returning id", {"id": repo_id})
    if not rows:
        raise HTTPException(status_code=404, detail="repository not found")
    return {"deleted": repo_id}


# ---------------- Projects (server-backed; supersedes the Studio client registry) ----------------
class ProjectCreate(BaseModel):
    name: str
    squad_id: str
    repository_id: str | None = None


@router.get("/projects")
def list_projects(org: str = Depends(current_org("/projects"))) -> dict:
    return {"projects": _rows(org,
            "select id, name, slug, squad_id, repository_id from projects where org_id = :o order by created_at desc",
            {"o": org})}


@router.post("/projects")
def create_project(body: ProjectCreate, org: str = Depends(current_org("/projects"))) -> dict:
    return _one(org,
                "insert into projects (id, org_id, squad_id, repository_id, name, slug, created_at) "
                "values (gen_random_uuid(), :o, :sq, :r, :n, :s, now()) returning id, name, slug, squad_id, repository_id",
                {"o": org, "sq": body.squad_id, "r": body.repository_id, "n": body.name, "s": _slug(body.name)},
                ensure_org=True)
