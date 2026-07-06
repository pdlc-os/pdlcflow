# Nexus Dashboard (Streamlit)

Internal **ops** console over pdlcflow's OpenTelemetry signals — a bespoke view
of work moving through the PDLC workflow and across agents, complementing the
prebuilt Grafana dashboards.

- **Traces** from **Tempo** — per-thread span trees (turn → node → LLM call),
  the "across multiple agents" drilldown.
- **Metrics** from **Prometheus** — `pdlc.*` counters/histograms (turns, LLM
  calls/tokens/cost, gate activity).

It reads telemetry only and carries no per-org auth, so it is deliberately an
internal/admin surface. Per-tenant business analytics (tokens/USD behind RLS)
stay in the React **Nexus Console** served by the engine.

## Run

Part of the `observability` compose profile:

```bash
cd infra/compose      # or the standalone deploy/ directory
docker compose --profile observability up -d
```

Then open **http://localhost:8501** (Streamlit), with Grafana on
**http://localhost:3000**.

## Config (env)

| Var              | Default                     | Purpose                        |
|------------------|-----------------------------|--------------------------------|
| `PROMETHEUS_URL` | `http://prometheus:9090`    | metric queries                 |
| `TEMPO_URL`      | `http://tempo:3200`         | trace search / drilldown       |
| `GRAFANA_URL`    | `http://localhost:3000`     | "open in Grafana" links        |

Metrics/traces appear once the engine runs a turn with `PDLC_OTEL_ENABLED=true`
(the profile sets this automatically). See `docs/wiki/19-observability.md`.
