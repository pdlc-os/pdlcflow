"""Nexus Dashboard — Streamlit ops console over pdlcflow's OpenTelemetry signals.

This is the internal (single admin tenant) operational view. It reads the
OTel-sourced signals only:

  • Prometheus  — pdlc.* metrics (turns, LLM calls/tokens/cost, gate activity)
  • Tempo       — per-thread trace drilldown (the "across multiple agents" tree)

Tenant business analytics (per-org tokens/USD behind RLS) stay in the React
Nexus Console served by the engine; this surface is deliberately ops-facing and
does not carry per-org auth. See docs/wiki/19-observability.md.

Env:
  PROMETHEUS_URL   default http://prometheus:9090
  TEMPO_URL        default http://tempo:3200
  GRAFANA_URL      default http://localhost:3000  (for "open in Grafana" links)
"""

from __future__ import annotations

import os

import pandas as pd
import requests
import streamlit as st

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090").rstrip("/")
TEMPO_URL = os.environ.get("TEMPO_URL", "http://tempo:3200").rstrip("/")
GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://localhost:3000").rstrip("/")

st.set_page_config(page_title="pdlcflow · Nexus Dashboard", page_icon="🛰️", layout="wide")


# --------------------------------------------------------------------------- #
# Prometheus helpers
# --------------------------------------------------------------------------- #
def prom_query(expr: str) -> list[dict]:
    """Run an instant PromQL query; return the raw result list (or [])."""
    try:
        r = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": expr}, timeout=8)
        r.raise_for_status()
        return r.json().get("data", {}).get("result", [])
    except Exception as exc:  # surfaced to the user, never crashes the app
        st.session_state["_prom_error"] = str(exc)
        return []


def scalar(expr: str, default: float = 0.0) -> float:
    res = prom_query(expr)
    if not res:
        return default
    try:
        return float(res[0]["value"][1])
    except (KeyError, IndexError, ValueError):
        return default


def grouped(expr: str, label: str) -> pd.DataFrame:
    """Instant vector → DataFrame indexed by one label with a `value` column."""
    rows = []
    for series in prom_query(expr):
        metric = series.get("metric", {})
        try:
            val = float(series["value"][1])
        except (KeyError, IndexError, ValueError):
            continue
        rows.append({label: metric.get(label, "—"), "value": val})
    if not rows:
        return pd.DataFrame(columns=[label, "value"])
    return pd.DataFrame(rows).set_index(label).sort_values("value", ascending=False)


# --------------------------------------------------------------------------- #
# Tempo helpers
# --------------------------------------------------------------------------- #
def tempo_search(thread_id: str, limit: int = 20) -> list[dict]:
    """Search Tempo for traces of one pdlc thread via TraceQL."""
    q = '{ .pdlc.thread_id = "%s" }' % thread_id
    try:
        r = requests.get(f"{TEMPO_URL}/api/search", params={"q": q, "limit": limit}, timeout=8)
        r.raise_for_status()
        return r.json().get("traces", []) or []
    except Exception as exc:
        st.warning(f"Tempo search failed: {exc}")
        return []


def tempo_trace_spans(trace_id: str) -> pd.DataFrame:
    """Fetch one trace and flatten it to a span table (name, duration, attrs)."""
    try:
        r = requests.get(f"{TEMPO_URL}/api/traces/{trace_id}", timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        st.warning(f"Could not fetch trace {trace_id}: {exc}")
        return pd.DataFrame()

    rows = []
    for batch in data.get("batches", []):
        for scope in batch.get("scopeSpans", batch.get("instrumentationLibrarySpans", [])):
            for s in scope.get("spans", []):
                attrs = {a["key"]: list(a.get("value", {}).values())[0] for a in s.get("attributes", [])}
                start = int(s.get("startTimeUnixNano", 0))
                end = int(s.get("endTimeUnixNano", 0))
                rows.append(
                    {
                        "span": s.get("name", ""),
                        "duration_ms": round((end - start) / 1e6, 1) if end > start else 0.0,
                        "persona": attrs.get("pdlc.persona") or attrs.get("pdlc.agent_persona") or "",
                        "model": attrs.get("gen_ai.request.model", ""),
                        "tokens_in": attrs.get("gen_ai.usage.input_tokens", ""),
                        "tokens_out": attrs.get("gen_ai.usage.output_tokens", ""),
                        "phase": attrs.get("pdlc.phase", ""),
                    }
                )
    df = pd.DataFrame(rows)
    return df.sort_values("duration_ms", ascending=False) if not df.empty else df


# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #
st.title("🛰️ Nexus Dashboard")
st.caption(
    "Operational view over pdlcflow's OpenTelemetry signals — traces from Tempo, "
    "metrics from Prometheus. Tenant business analytics live in the Studio's Nexus Console."
)

window = st.sidebar.selectbox("Rate window", ["1m", "5m", "15m", "1h"], index=1)
st.sidebar.markdown(f"**Prometheus**: `{PROMETHEUS_URL}`")
st.sidebar.markdown(f"**Tempo**: `{TEMPO_URL}`")
st.sidebar.markdown(f"[Open Grafana]({GRAFANA_URL})")
if st.sidebar.button("Refresh"):
    st.rerun()

# ── KPI row ────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("Turns", f"{scalar('sum(pdlc_turns_total)'):,.0f}")
c2.metric("LLM calls", f"{scalar('sum(pdlc_llm_calls_total)'):,.0f}")
c3.metric("Tokens", f"{scalar('sum(pdlc_llm_tokens_total)'):,.0f}")
c4.metric("Est. spend", f"${scalar('sum(pdlc_llm_cost_usd_total)'):,.4f}")

if err := st.session_state.pop("_prom_error", None):
    st.info(
        f"No metrics yet (or Prometheus unreachable): {err}. "
        "Metrics appear once the engine runs a turn with `PDLC_OTEL_ENABLED=true`."
    )

st.divider()

# ── Agent + token activity ──────────────────────────────────────────────────
left, right = st.columns(2)
with left:
    st.subheader("Agent activity — LLM calls by persona")
    df = grouped("sum by (persona) (pdlc_llm_calls_total)", "persona")
    st.bar_chart(df, horizontal=True) if not df.empty else st.caption("No agent activity yet.")
with right:
    st.subheader("Tokens by direction")
    df = grouped("sum by (direction) (pdlc_llm_tokens_total)", "direction")
    st.bar_chart(df) if not df.empty else st.caption("No token usage yet.")

# ── Cost + turn outcomes ────────────────────────────────────────────────────
left, right = st.columns(2)
with left:
    st.subheader("Spend by provider / model")
    df = grouped("sum by (provider, model) (pdlc_llm_cost_usd_total)", "model")
    st.dataframe(df, use_container_width=True) if not df.empty else st.caption("No spend recorded yet.")
with right:
    st.subheader(f"Turn outcomes (rate/s over {window})")
    df = grouped(f"sum by (outcome) (rate(pdlc_turns_total[{window}]))", "outcome")
    st.bar_chart(df) if not df.empty else st.caption("No turns in this window.")

# ── Gate activity ───────────────────────────────────────────────────────────
st.subheader("Approval gates / question rounds opened, by kind")
df = grouped('sum by (kind) (pdlc_gates_total{action="opened"})', "kind")
st.bar_chart(df, horizontal=True) if not df.empty else st.caption("No gates opened yet.")

st.divider()

# ── Trace explorer ──────────────────────────────────────────────────────────
st.subheader("🔎 Thread trace explorer")
st.caption(
    "Enter a thread id (`org:project:session`) to pull its per-turn traces from Tempo "
    "and drill into the agent span tree."
)
thread_id = st.text_input("Thread id", placeholder="org-uuid:project-uuid:session-id")
if thread_id:
    traces = tempo_search(thread_id.strip())
    if not traces:
        st.caption("No traces found for that thread (yet).")
    else:
        tdf = pd.DataFrame(
            [
                {
                    "traceID": t.get("traceID", ""),
                    "root": t.get("rootTraceName", ""),
                    "durationMs": t.get("durationMs", 0),
                    "start": t.get("startTimeUnixNano", ""),
                }
                for t in traces
            ]
        )
        st.dataframe(tdf, use_container_width=True)
        pick = st.selectbox("Inspect a trace", tdf["traceID"].tolist())
        if pick:
            spans = tempo_trace_spans(pick)
            if spans.empty:
                st.caption("No spans in that trace.")
            else:
                st.dataframe(spans, use_container_width=True)
            st.markdown(f"[Open this trace in Grafana Explore]({GRAFANA_URL}/explore)")
