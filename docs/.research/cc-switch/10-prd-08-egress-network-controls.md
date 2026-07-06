# PRD-08: Egress Network Controls — outbound proxy, CA bundles, custom headers

- **Status:** Draft — for assessment
- **Date:** 2026-07-05
- **Origin:** [cc-switch gap analysis](02-gap-analysis.md) — gap #9 (GAP)
- **Related PRDs:** [PRD-04 Preset catalog](06-prd-04-provider-preset-catalog.md) (relay gateways
  often need custom headers) · [PRD-03 Health](05-prd-03-provider-health-connectivity.md)
  (probes must use the same egress path as real calls)

## 1. Problem & motivation

pdlcflow has **zero explicit proxy awareness** — no `proxy` reference anywhere in `services/` or
`packages/` Python ([current state §8](01-pdlcflow-current-state.md)). Enterprise self-host
deployments routinely require all outbound HTTPS to pass through a corporate proxy with a
TLS-inspecting CA. Today that only works *by accident*, where a langchain SDK happens to honor
ambient `HTTPS_PROXY` env vars — behavior that varies per SDK, is undocumented for pdlcflow
operators, and can't be scoped or verified. Similarly, relay gateways (the ecosystem PRD-04
opens up) frequently require extra request headers (gateway keys, routing hints), which no
provider builder can currently send — builders pass only `model` + `api_key`
(`app/llm/providers/anthropic.py:12-18`, `openai.py:12-18`).

**What cc-switch does here:** its local proxy layer offers custom request header/body override,
custom User-Agent, pooled HTTPS connection reuse (inventory §3). pdlcflow doesn't need a proxy
*server* — it needs the equivalent *egress controls* threaded into its existing provider
builders.

This is deliberately the smallest, most surgical PRD of the set.

## 2. Goals / Non-goals

**Goals**
- G1: Instance-level outbound HTTP(S) proxy for LLM egress, explicitly configured
  (`PDLC_` env), explicitly passed to each SDK — not reliant on ambient env.
- G2: Custom CA bundle path for TLS-inspection environments.
- G3: Optional per-org extra request headers (relay-gateway support).
- G4: Honest, documented per-SDK support matrix — where a knob cannot be honored, the docs and
  boot log say so rather than silently ignoring it.

**Non-goals**
- NG1: An interposing proxy service (cc-switch's architecture) — rejected in the gap analysis.
- NG2: Request/response *body* rewriting (cc-switch's "rectifier") — langchain adapters already
  normalize payloads.
- NG3: Proxying non-LLM egress (VCS/GitHub calls, Vault, S3) — those SDKs have their own
  conventions; out of scope here (open question §13.2).
- NG4: Per-org proxy URLs — proxy is an instance/infrastructure concern; orgs get headers only.

## 3. Users & user stories

- **Enterprise operator (self-host):** "All egress must go through `proxy.corp:3128` with our
  corporate CA. I set two env vars and every provider call complies — and `pdlcflow` tells me at
  boot which providers can't honor it."
- **Org admin using a relay gateway:** "SiliconFlow requires an `X-Gateway-Key` header alongside
  the API key. I add it to my org's LLM config and completions work."
- **Operator debugging egress:** "The health probe (PRD-03) fails the same way a real call
  would, because both use the same network config."

## 4. Functional requirements

| ID | Requirement | MoSCoW |
|---|---|---|
| FR-1 | `PDLC_EGRESS_PROXY_URL` (http/https/socks5 URL) applied to all HTTP-based provider SDKs | Must |
| FR-2 | `PDLC_EGRESS_CA_BUNDLE` (file path) used for TLS verification by the same SDKs | Must |
| FR-3 | `PDLC_EGRESS_NO_PROXY` (comma list) exemptions (e.g. in-cluster Ollama) | Must |
| FR-4 | Per-org `extra_headers` (JSONB on `org_llm_config`), merged into provider requests where the SDK supports default headers | Should |
| FR-5 | Boot-time egress report: log one line per configured provider stating proxy/CA support status (full / partial / unsupported) | Must |
| FR-6 | Health probes (PRD-03) and catalog refresh (PRD-07 FR-8) route through the same egress config | Should |
| FR-7 | Custom User-Agent suffix (`pdlcflow/<version>`) on httpx-based SDK calls | Could |
| FR-8 | Per-org proxy URL | Won't |

## 5. Detailed design

### 5.1 Config (instance level)

Additions to `Settings` (`app/config.py:11`, env prefix `PDLC_`):

```python
# Egress network controls — explicit outbound networking for LLM calls.
egress_proxy_url: str | None = None      # e.g. "http://proxy.corp:3128"
egress_no_proxy: str = ""                # comma-separated host suffixes
egress_ca_bundle: str | None = None      # path to a PEM bundle
```

### 5.2 `NetworkConfig` threaded through `ProviderConfig`

`ProviderConfig` (`app/llm/factory.py:75-82`) gains one field:

```python
@dataclass
class NetworkConfig:
    proxy_url: str | None = None
    no_proxy: tuple[str, ...] = ()
    ca_bundle: str | None = None
    extra_headers: dict[str, str] | None = None   # org-level, FR-4

@dataclass
class ProviderConfig:
    ...
    network: NetworkConfig | None = None
```

The factory constructs a module-level `NetworkConfig` from settings once, attaches it in every
resolution branch (`_agent_override` / `_org_default` / `_instance_default` / `_fallback`,
`factory.py:143-201`), and merges the org row's `extra_headers` in the tenant branches. A
`no_proxy` match against the target host clears `proxy_url` for that builder call (relevant for
`ollama` with an in-cluster endpoint, `providers/ollama.py`).

### 5.3 Per-builder application — the honest support matrix

Each builder in `app/llm/providers/*.py` applies what its SDK supports. This variance is the
core design reality; document it rather than pretend uniformity:

| Provider (builder) | Underlying client | Proxy | CA bundle | Extra headers | How |
|---|---|---|---|---|---|
| `anthropic` | httpx via `langchain-anthropic` | ✅ | ✅ | ✅ | pass `http_client=httpx.Client(proxy=..., verify=ca)` (or the SDK's `anthropic.Anthropic(http_client=…)` passthrough) + `default_headers` |
| `openai` | httpx via `langchain-openai` | ✅ | ✅ | ✅ | same: `http_client` + `default_headers` |
| `azure` | httpx via `langchain-openai` (AzureChatOpenAI) | ✅ | ✅ | ✅ | same as openai |
| `ollama` | httpx via `langchain-ollama` | ✅ | ✅ | ⚠️ client-level only | `client_kwargs={"proxy":…, "verify":…}` |
| `bedrock` | boto3/botocore | ✅ | ✅ | ⚠️ via botocore events, v2 only | `botocore.config.Config(proxies={"https": url}, proxies_config=…)`; CA via `verify=ca_path` on the client |
| `gemini` | `google-genai` / `langchain-google-genai` | ⚠️ env-var only in several versions | ⚠️ | ❌ | best-effort: set `HTTPS_PROXY`/`SSL_CERT_FILE` process-scoped iff unset; log "partial" |
| `vertex` | google-cloud-aiplatform (gRPC) | ❌ (gRPC proxy support is env-dependent) | ⚠️ | ❌ | log "unsupported — use network-level egress"; do not fake it |
| `claude_code` / `codex` / `gemini_cli` | subprocess CLIs | inherit child env | n/a | n/a | export proxy env vars into the child process env (`providers/cli.py`) |

Implementation shape — a tiny shared helper `app/llm/providers/_net.py`:

```python
def httpx_client(net: NetworkConfig | None):        # returns None when net is empty
    if not net or not (net.proxy_url or net.ca_bundle):
        return None
    import httpx
    return httpx.Client(proxy=net.proxy_url, verify=net.ca_bundle or True)

def merged_headers(net, base=None): ...
```

Builders stay thin: `anthropic.build` becomes ~6 lines longer (conditionally add
`http_client=`, `default_headers=`). Note both sync and async clients where the langchain
integration uses them (`http_client` + `http_async_client` kwargs on ChatOpenAI/ChatAnthropic).

**Verification note (pre-implementation):** exact kwarg names (`http_client` vs `client`,
`client_kwargs`) must be pinned against the locked versions of `langchain-anthropic`,
`langchain-openai`, `langchain-ollama` in `services/pdlc-engine/pyproject.toml` during
implementation — the matrix above is the design contract, per-version spelling may differ.

### 5.4 Per-org extra headers (FR-4)

- Migration: `ALTER TABLE org_llm_config ADD COLUMN extra_headers JSONB;`
- Surfaced in the existing models admin API: `OrgDefault` model
  (`app/routes/admin/models.py:32-36`) gains `extra_headers: dict[str, str] | None`; the
  upsert (`models.py:64-81`) writes it; `_org_default` (`factory.py:166-187`) selects it into
  `NetworkConfig.extra_headers`.
- Guardrails: max 8 headers, header-name allowlist pattern `^[A-Za-z0-9-]{1,64}$`, values ≤ 512
  chars; reject `Authorization`, `Host`, `Content-*` (the API key path owns auth — headers must
  not become a second, unencrypted credential channel; see §6).

### 5.5 Boot-time egress report (FR-5)

`wire_llm_backend` (`app/runtime/llm_backend.py:141-164`) logs once when
`egress_proxy_url or egress_ca_bundle` is set:

```
pdlc.runtime.llm: egress proxy=http://proxy.corp:3128 ca=/etc/ssl/corp.pem
  full: anthropic, openai, azure, ollama, bedrock · partial(env): gemini · unsupported: vertex
```

## 6. Security & tenancy

- Proxy + CA are instance-level env config — operator domain, never org-editable (a tenant
  must not redirect another tenant's traffic; hence FR-8 = Won't).
- `extra_headers` values are stored **plaintext** in `org_llm_config` (RLS-FORCEd). They are
  routing hints, not credentials — the reject-list in §5.4 blocks `Authorization` so tenants
  aren't nudged into storing secrets there. If a gateway demands a secret header, that's the
  open question §13.3 (secretstore-ref header values).
- CA bundle path is read server-side; validate existence at boot, fail loudly (misconfigured CA
  ⇒ every call fails confusingly otherwise).
- Setting process-scoped env vars for the gemini fallback only happens when the operator
  configured a proxy AND the var is unset — never overwrite operator-provided env.

## 7. Rollout & migration

1. All knobs default to `None`/empty ⇒ zero behavior change for existing deployments.
2. One additive migration (`extra_headers` column) — nullable, no backfill.
3. Docs: new "Egress & proxies" section in `docs/wiki/03-configuration.md` including the
   support matrix verbatim; troubleshooting entry for TLS-inspection CAs.
4. No feature flag needed — absence of config is the off state.

## 8. Testing strategy (hermetic)

- `_net.httpx_client` unit tests: None passthrough, proxy-only, CA-only, both; `no_proxy`
  host matching.
- Builder tests (existing `test_llm_factory.py` style): build each provider with a
  `NetworkConfig` and assert the constructed langchain object's client/kwargs — **no network**;
  we assert configuration, not connectivity.
- Header guardrail tests: reject `Authorization`, oversize values, bad names (route-level,
  test DB).
- Boot report test: capture log output for a settings fixture with proxy set.
- Explicitly no integration test against a real proxy in CI; a compose-profile smoke recipe
  (tinyproxy) documented for manual verification.

## 9. Effort estimate

**S — ~1 eng-week.** Settings + NetworkConfig threading (0.25w), 10 builder touches + `_net`
helper (0.25w), extra_headers column + API + guardrails (0.25w), boot report + docs + tests
(0.25w).

## 10. Risks & mitigations

- **R1: SDK kwarg drift across versions** (httpx client passthrough names change). Mitigate:
  builder tests assert the kwargs actually land; pinned versions in pyproject; matrix
  re-verified on dependency bumps.
- **R2: gemini/vertex partial support surprises operators.** Mitigate: FR-5 boot report + docs
  say exactly which providers are partial/unsupported; recommend network-level egress
  (transparent proxy) for gRPC.
- **R3: sync `httpx.Client` reuse/lifecycle** — constructing a client per `build()` call leaks
  connections. Mitigate: memoize one client per (proxy, ca) pair at module level in `_net.py`.
- **R4: headers used to smuggle credentials.** Mitigate: reject-list + docs; secretstore-ref
  variant deferred (§13.3).

## 11. Success metrics

- A TLS-inspecting-proxy deployment (staging sim with tinyproxy + custom CA) completes a full
  PDLC turn on anthropic/openai/bedrock with **zero ambient env vars** set.
- Boot report correctly classifies all 10 providers.
- ≥1 relay gateway (PRD-04 preset) works end-to-end using org `extra_headers`.

## 12. Dependencies

- None hard. Synergy: PRD-03 probes and PRD-04 gateway presets should consume `NetworkConfig`
  from day one; land this before or with PRD-04.

## 13. Open questions

1. Should VCS egress (repo clone/push via per-repo tokens) honor the same proxy in this PRD or
   a follow-up? (Leaning follow-up — different code path, `vcs_port` side.)
2. SOCKS5 support requires `httpx[socks]` extra — add the dependency unconditionally or
   document as optional?
3. Secret header values: support `{"X-Gateway-Key": "secretref:enc:…"}` resolved via
   `app/secretstore` (`__init__.py:94-100`)? Adds complexity; defer until a preset actually
   needs a secret header.
4. Should `extra_headers` be per-agent too (`agent_llm_config`)? Org-level only for now.
