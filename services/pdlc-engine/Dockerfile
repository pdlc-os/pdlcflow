FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

# Build context is the repo root (docker-compose `context: ../../`), so COPY
# paths are repo-root-relative. uv resolves the whole workspace, so every member
# declared in the root pyproject must be present. `scripts/` carries the eval
# suite runner used by the `evals` one-shot service.
COPY pyproject.toml /workspace/pyproject.toml
COPY packages/event-schema /workspace/packages/event-schema
COPY packages/pdlc-graph /workspace/packages/pdlc-graph
COPY tools/pdlc-migrate /workspace/tools/pdlc-migrate
COPY services/pdlc-engine /workspace/services/pdlc-engine
COPY scripts /workspace/scripts

WORKDIR /workspace/services/pdlc-engine
RUN uv sync

EXPOSE 8000
ENV PYTHONUNBUFFERED=1

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
