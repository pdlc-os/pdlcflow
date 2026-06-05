"""FastAPI entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .clickstream import wire_emitter
from .config import settings
from .routes import admin as admin_routes
from .routes import approval_gates as approval_routes
from .routes import commands as command_routes
from .routes import health as health_routes
from .runtime import GraphRunner, build_checkpointer, set_runner, wire_llm_backend
from .websocket.handler import ws_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    wire_emitter(settings)
    # Graph runtime: one runner owns the checkpointer that makes interrupt()
    # sites resumable across REST turns. MemorySaver in dev; PostgresSaver when
    # use_postgres_checkpointer is set. LLM completions stay on the offline stub
    # unless wire_llm enables the provider factory.
    set_runner(GraphRunner(checkpointer=build_checkpointer(settings)))
    wire_llm_backend(settings)
    yield


app = FastAPI(
    title="pdlc-engine",
    version="0.0.1-phase-a",
    description="LangGraph-powered PDLC engine",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_routes.router)
app.include_router(command_routes.router, prefix="/v1")
app.include_router(approval_routes.router, prefix="/v1")
app.include_router(admin_routes.router, prefix="/v1/admin")
app.include_router(ws_router)
