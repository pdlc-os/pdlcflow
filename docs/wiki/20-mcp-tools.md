# MCP Tool Servers

pdlcflow agents can call external tools via the **Model Context Protocol**: an
org-scoped registry of MCP servers, explicit tool allowlists, and
persona/phase bindings — so Muse can search your internal docs during
Inception, or Neo can look up tickets while planning. Unbound servers are
inert, and nothing executes at all until the operator enables the backend.

## Enabling

```bash
PDLC_WIRE_MCP=true          # engine flag — off by default; registry data is inert without it
```

Then in **Studio → Nexus Console → Tools**:

1. **Register** a server (or start from a template): name, transport, URL,
   optional bearer token (write-only — stored via the secrets backend, never
   shown again).
2. **Test** — connects, lists the server's tools and latency. The returned
   tool list renders as checkboxes.
3. **Allow** the tools the agents may call. An empty allowlist means
   **deny all** — allowing is always a conscious act.
4. **Bind** the server to personas, optionally scoped to a phase
   (`Inception`, `Construction`, …). A tool call is permitted only when the
   calling persona is bound and the phase matches (or the binding is
   phase-less).

## How agents use tools

Nodes author explicit calls through the graph package's `tool_port` (no
model-driven tool loop in v1). The flagship flow: **Muse's divergent ideation**
calls each bound search-shaped tool with the feature as the query and grounds
its ideation in the results. Tool output is treated as **untrusted data** —
fenced with delimiters and per-result `[source: server/tool]` provenance lines
before it enters any prompt, size-capped (`PDLC_MCP_MAX_RESULT_BYTES`), and a
tool failure never breaks a turn (the node just proceeds without the context).

Every call emits a `tool.called` clickstream event (org, persona, server,
tool, duration, ok, bytes) and a `pdlc.tool.<name>` span nested under the node
span in Tempo/Grafana.

## Security model

| Control | Detail |
| --- | --- |
| **stdio transport** | Executes commands on the engine host → **single-user self-host only**: requires `PDLC_ENABLE_STDIO_MCP=true` AND is refused whenever `PDLC_AUTH_REQUIRED=true` — enforced at registration *and* again at call time (config may predate a mode flip). Mirrors the CLI-provider guard. |
| **SSRF** | Server URLs pass the same egress policy as LLM endpoints; private/loopback/metadata targets are rejected unless `PDLC_MCP_ALLOW_PRIVATE_NETWORKS=true` (VPC-internal enterprise servers). HTTP calls ride the PDLC egress proxy config where set. |
| **Credentials** | Bearer tokens are write-only secretstore refs (`has_auth` is all reads ever expose). |
| **Allowlist** | Default deny; per-tool opt-in. Enforced server-side per call. |
| **Resource caps** | `PDLC_MCP_TIMEOUT_S` (30), `PDLC_MCP_MAX_RESULT_BYTES` (64 KiB, explicit `[truncated]` marker), `PDLC_MCP_CALLS_PER_TURN` (20). A failing server enters a 60 s cool-down so it can't tax every node. |
| **Tenancy** | Both tables are RLS-forced; binding resolution is keyed by the turn's org context. |
| **Prompt injection** | Tool output enters prompts as fenced, provenance-tagged, size-capped text; the eval layer (`PDLC_RUN_EVALS`) can score tool-augmented outputs. Residual risk is industry-open — the audit trail is the backstop. |

## Configuration reference

| Variable | Default | Meaning |
| --- | --- | --- |
| `PDLC_WIRE_MCP` | `false` | Master switch for tool execution. |
| `PDLC_ENABLE_STDIO_MCP` | `false` | Allow stdio servers (single-user self-host only). |
| `PDLC_MCP_TIMEOUT_S` | `30` | Per-call wall-clock budget. |
| `PDLC_MCP_MAX_RESULT_BYTES` | `65536` | Result size cap (truncated with a marker). |
| `PDLC_MCP_CALLS_PER_TURN` | `20` | Tool calls allowed within one graph turn. |
| `PDLC_MCP_ALLOW_PRIVATE_NETWORKS` | `false` | SSRF escape hatch for VPC-internal servers. |

Hermetic note: the graph package's `tool_port` defaults to a null backend —
CI/dev run toolless and byte-identical; the `mcp` SDK is an engine-only
dependency, imported lazily.

---
<!-- nav:bottom -->
⏮ [First: Overview](01-overview.md) · ◀ [Prev: Observability](19-observability.md) · [🏠 Home](README.md)
