FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy workspace manifest + the two upstream packages this service depends on
COPY ../../pyproject.toml /workspace/pyproject.toml
COPY ../../packages/event-schema /workspace/packages/event-schema
COPY ../../packages/pdlc-graph /workspace/packages/pdlc-graph
COPY . /workspace/services/pdlc-engine

WORKDIR /workspace/services/pdlc-engine
RUN uv sync --frozen=false

EXPOSE 8000
ENV PYTHONUNBUFFERED=1

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
