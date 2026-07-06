# PRD-01: BYOK Completion — per-tenant API key resolution

| | |
|---|---|
| **Status** | Draft — for assessment |
| **Date** | 2026-07-05 |
| **Origin** | [cc-switch gap analysis](02-gap-analysis.md), gap #2 |
| **Related PRDs** | [PRD-02 Provider Settings Console](04-prd-02-provider-settings-console.md) (UI for key entry) · [PRD-03 Health & Connectivity](05-prd-03-provider-health-connectivity.md) (validates a key before save) · [PRD-06 Config Versioning](08-prd-06-config-versioning-import-export.md) (audits key rotation events) |

## 1. Problem & motivation

pdlcflow's multi-tenant provider config is **half-wired for BYOK (bring-your-own-key)**:

- The schema is ready: `org_llm_config.secret_ref` and `agent_llm_config.secret_ref` exist
  (`services/pdlc-engine/app/db/models.py:265`, `:284`).
- The secrets backend is ready: `app/secretstore/__init__.py` has a full pluggable store
  (Fernet-encrypted `enc:` refs, Vault KV v2 `vault:` refs, `env:` refs) with
  `put(value, hint) → ref` and `resolve(ref) → plaintext`.
- The consumers are ready: every provider builder honors `cfg.secret_value` when present
  (e.g. `app/llm/providers/anthropic.py:16-17` — "per-tenant `secret_value` if set, otherwise
  the SDK's own `ANTHROPIC_API_KEY`").
- The factory even accepts a secrets handle: `LLMProviderFactory.__init__(self, db=None,
  secrets=None)` (`app/llm/factory.py:91-93`).

But **the middle link is missing**: `_agent_override()` selects only
`provider, model_id, region, endpoint` (`factory.py:150-156`) and `_org_default()` selects only
`provider, region, endpoint, tier_map` (`factory.py:173-179`). Neither reads `secret_ref`,
neither calls `secrets.resolve()`, and `self._secrets` is never used. So
`ProviderConfig.secret_value` is **always `None`** on the tenant path, and every provider builder
silently falls through to the instance-wide env key.

Consequences today:

1. **Every tenant's LLM traffic bills the instance operator's key** — SaaS-economics blocker.
2. **Silent misconfiguration**: an admin who stores a key believes their org is isolated; it
   isn't, and nothing tells them.
3. The admin API (`app/routes/admin/models.py`) offers **no way to submit a key at all** — the
   `OrgDefault`/`AgentOverride` Pydantic models (`models.py:32-44`) have no key field and the
   upserts never write `secret_ref`. So even the "storage-capable" half is unreachable via API.

**What cc-switch does here:** its entire premise is per-provider credentials — every provider
entry carries its own API key/auth token, switched atomically, with credential keys explicitly
stripped from shared config (`*_API_KEY`, `*_AUTH_TOKEN` scrubbing, v3.16.5). pdlcflow's
translation is per-*org* (and per-agent) keys resolved server-side at call time.

## 2. Goals / Non-goals

**Goals**

- G1: An org admin can attach an API key to the org default config and to any per-agent
  override; the factory resolves and injects it on every LLM call for that org.
- G2: Keys are write-only through the API — never echoed back in any response, log, or event.
- G3: Key rotation is a single PUT; the old secret is superseded atomically.
- G4: A dangling/broken `secret_ref` fails **loudly** (explicit error surfaced to the turn),
  not silently via env-key fallback — silent fallback is precisely today's bug.
- G5: Hot path stays fast: resolution adds no per-call Vault round-trip (TTL cache).

**Non-goals**

- Key entry UI (that's [PRD-02](04-prd-02-provider-settings-console.md); this PRD delivers the
  API + engine wiring it needs).
- Pre-save key validation probes ([PRD-03](05-prd-03-provider-health-connectivity.md)).
- Per-user (as opposed to per-org/per-agent) keys.
- New secretstore backends (AWS Secrets Manager etc. — the ref-prefix scheme already leaves
  room; out of scope here).
- Billing enforcement / quota (PRD-07 territory).

## 3. Users & user stories

- **Org admin (SaaS tenant)** — "As an org admin, I paste my Anthropic key into my org's model
  settings so my org's usage bills my account, not the platform's."
- **Org admin** — "As an org admin, I rotate a leaked key and am confident the old one is no
  longer used anywhere within seconds."
- **Platform operator** — "As the operator, I want tenant traffic to *fail* if a tenant's key is
  broken, rather than silently burning my instance key."
- **Security reviewer** — "As a reviewer, I can verify no API returns key material and the DB
  holds only ciphertext/refs."

## 4. Functional requirements

| ID | Requirement | MoSCoW |
|---|---|---|
| FR-1 | `PUT /admin/models/org-default` accepts an optional write-only `api_key` field; when present, it is stored via `secrets.put()` and the resulting ref persisted to `org_llm_config.secret_ref`. | Must |
| FR-2 | `PUT /admin/models/agent-overrides/{persona}` accepts the same optional `api_key`, persisted to `agent_llm_config.secret_ref`. | Must |
| FR-3 | GET responses expose only `has_key: bool` (derived from `secret_ref IS NOT NULL`); neither the plaintext key nor the ref is ever returned. | Must |
| FR-4 | `DELETE /admin/models/org-default/key` and `DELETE /admin/models/agent-overrides/{persona}/key` clear the stored key (set `secret_ref = NULL`). | Must |
| FR-5 | Factory `_org_default` / `_agent_override` read `secret_ref` and populate `ProviderConfig.secret_value` via `secrets.resolve()`. | Must |
| FR-6 | A non-null `secret_ref` that fails to resolve raises `SecretResolutionError` — the call errors; it does NOT fall back to the instance env key. | Must |
| FR-7 | Resolved plaintext is cached in-process with a short TTL (default 300 s) keyed by ref; a PUT/DELETE on the config invalidates the entry for that ref. | Should |
| FR-8 | PUT with `api_key` omitted (or `null`) leaves the existing `secret_ref` untouched — editing provider/model must not wipe the key. | Must |
| FR-9 | Key writes emit an audit event (`admin.llm_key.set` / `.cleared`) to the clickstream — org, scope (org-default vs persona), actor; never the key or ref. | Should |
| FR-10 | Agent-override resolution with no override-level key inherits the org-default key when the providers match; providers differing means no inheritance (an Anthropic key must not be sent to OpenAI). | Should |
| FR-11 | `vault`/`encrypted`/`env` backends all work via the existing prefix dispatch — no backend-specific code in the factory. | Must |
| FR-12 | CLI providers (`claude_code`, `codex`, `gemini_cli`) never accept keys — they're subscription CLIs; API rejects `api_key` for them (they are already excluded by the route's `Provider` Literal, `routes/admin/models.py:25`). | Could |

## 5. Detailed design

### 5.1 Data model / migrations

**No new columns.** `secret_ref` already exists on both tables (`db/models.py:265`, `:284`).
One new alembic revision (`llm_key_audit`, next free number after `0006_hierarchy.py` in
`app/db/migrations/versions/`) is needed **only if** FR-9's audit lands as a table rather than a
clickstream event — recommendation: clickstream event, zero migration. Net: **no migration** in
the recommended shape.

### 5.2 API contract (`app/routes/admin/models.py`)

Extend the Pydantic models — request gains a write-only field, response gains a derived flag:

```python
class OrgDefault(BaseModel):
    provider: Provider
    tier_map: dict[str, str]
    region: str | None = None
    endpoint: str | None = None
    api_key: str | None = None      # WRITE-ONLY: accepted on PUT, never serialized on GET

class OrgDefaultOut(BaseModel):     # GET response model — no key fields at all
    provider: Provider
    tier_map: dict[str, str]
    region: str | None = None
    endpoint: str | None = None
    has_key: bool = False
```

`PUT /v1/admin/models/org-default` (behind `admin_org(...)` from `routes/admin/_guard.py`, as
today):

```jsonc
// request
{ "provider": "anthropic",
  "tier_map": {"premium": "claude-opus-4-8", "balanced": "claude-sonnet-4-6", "economy": "claude-haiku-4-5"},
  "api_key": "sk-ant-..." }        // optional; omitted → keep existing secret_ref
// response
{ "ok": true, "has_key": true }
```

Handler logic (mirrors the existing upsert at `routes/admin/models.py:64-81`):

```python
secret_ref_clause = ""
params = {...}
if cfg.api_key is not None:
    ref = get_secrets().put(cfg.api_key, hint=f"llm/org/{org_id}")
    secret_ref_clause = ", secret_ref = :sr"     # and in the INSERT column list
    params["sr"] = ref
    invalidate_secret_cache_for(org_id)          # see §5.4
```

The `hint` matters for the Vault backend (`secretstore/__init__.py:69-76` requires a stable id)
and yields stable paths `llm/org/<org_id>` and `llm/agent/<org_id>/<persona>` — rotation
overwrites the same Vault path (KV v2 keeps version history for free).

`GET /v1/admin/models/org-default` → `OrgDefaultOut`; the SQL adds
`secret_ref is not null as has_key` and **does not select `secret_ref` itself** (even the
ciphertext/ref never leaves the server).

`DELETE /v1/admin/models/org-default/key` → `update org_llm_config set secret_ref = null where
org_id = :o` → `{"ok": true}`. Same pattern for
`DELETE /v1/admin/models/agent-overrides/{persona}/key`.

`AgentOverride` / `AgentOverrideOut` change identically (hint `llm/agent/{org_id}/{persona}`).
FR-8 is why `api_key: None` means "no change": the console will routinely re-PUT a row to change
the model id without re-entering the key.

### 5.3 Engine wiring (`app/llm/factory.py`)

1. **Queries read the ref.** `_agent_override` (`factory.py:150-156`) adds `secret_ref` to its
   SELECT; `_org_default` (`factory.py:173-179`) likewise. Both pass it through:

   ```python
   return ProviderConfig(
       provider=row["provider"], ...,
       secret_value=self._resolve_secret(row["secret_ref"]),
   )
   ```

2. **Resolution with explicit failure** (FR-6):

   ```python
   class SecretResolutionError(RuntimeError):
       """org config points at a secret that cannot be resolved — do NOT fall back."""

   def _resolve_secret(self, ref: str | None) -> str | None:
       if not ref:
           return None                    # legitimately no tenant key → env fallback OK
       value = _secret_cache.get(ref)     # §5.4
       if value is None:
           secrets = self._secrets or get_secrets()
           value = secrets.resolve(ref)
           if value is None:              # unknown prefix, bad ciphertext, missing env var…
               raise SecretResolutionError(f"unresolvable secret_ref for provider config")
           _secret_cache.set(ref, value)
       return value
   ```

   Rationale for raising: `Secrets.resolve()` returns `None` for unknown/legacy refs
   (`secretstore/__init__.py:100`) and for a missing env var (`:56`). If we mapped that `None`
   into "no key", we'd re-create today's bug — tenant traffic silently billed to the operator.
   The error surfaces through the existing node-error path (`instrumentation.py` emits `error`,
   the turn fails visibly) and, once PRD-03 lands, the console shows the provider as unhealthy.

3. **Construction site passes the store.** Wherever `LLMProviderFactory(db=...)` is built at
   engine boot, pass `secrets=get_secrets()` — the constructor already takes it
   (`factory.py:91-93`); `_resolve_secret` defaults to `get_secrets()` so tests can inject a
   fake.

4. **Key inheritance (FR-10).** Today `_agent_override` returning a row short-circuits
   `_org_default` entirely (`factory.py:102-107`). If the override row has `secret_ref IS NULL`
   **and** its provider equals the org default's provider, resolve the org row's ref instead
   (one extra indexed PK lookup, cached). Guarded by provider equality so a key never crosses
   provider boundaries.

### 5.4 Secret cache

Per-process dict `{ref: (value, expires_at)}`, TTL `PDLC_SECRET_CACHE_TTL_S` (default 300, `0`
disables). Justification: Vault resolve is a network round-trip on the hottest path in the
system (every completion); Fernet decrypt is cheap but caching is uniform and harmless.
Invalidation: the admin PUT/DELETE handlers call `invalidate(ref_prefix_for_org)`; cross-process
staleness is bounded by the TTL (≤ 5 min for rotation to fully propagate on a multi-replica
deployment — documented; acceptable because rotation replaces a *working* key with another
working key; revocation-critical rotation can bounce the pods or set TTL 0).

### 5.5 What does NOT change

Provider builders (`llm/providers/*.py`) — they already consume `cfg.secret_value`. Tier
resolution (`llm/tier_map.py`). RLS posture — both queries already run under
`set_org_context` (`factory.py:149`, `:172`).

## 6. Security & tenancy

- **Write-only keys**: plaintext appears only in the PUT request body and the in-process cache;
  GET models physically lack the field (separate `*Out` response models — not just omission by
  serializer config). `secret_ref` is also never returned (an `enc:` ref *is* the ciphertext;
  don't hand it out).
- **RLS**: both tables are RLS-FORCEd (`0002_rls.py`/`0003_rls_force.py`); all reads/writes go
  through `set_org_context`. No change.
- **Admin gating**: routes stay behind `admin_org()` (`routes/admin/_guard.py`) — admin/owner
  role when auth is on.
- **Logging discipline**: the audit event (FR-9) carries `{scope, persona?, actor}` only. Add a
  test asserting the word `api_key` never appears in emitted event payloads.
- **At rest**: `encrypted` backend → Fernet ciphertext in the DB column (needs
  `PDLC_SECRET_KEY`, `config.py:46`); `vault` → only a path in the DB. The `env` backend is
  effectively operator-managed BYOK (ref names an env var) — fine for self-host, pointless for
  SaaS; docs should say so.
- **Failure mode**: FR-6's hard-fail is itself a security property — no silent
  cross-tenant billing.

## 7. Rollout & migration

1. Ship behind no flag — the behavior only activates when a tenant stores a key
   (`secret_ref IS NULL` everywhere today, so day-one behavior is identical).
2. Existing rows: none have `secret_ref` set (there was never an API to set it), so no backfill.
3. Docs: wiki `03-configuration.md` gains a "Tenant API keys (BYOK)" section; `deploy/.env.example`
   already documents `PDLC_SECRET_KEY`/`PDLC_SECRETS_BACKEND`.
4. Order within Wave 1: land this before PRD-02 (console needs `has_key` + the key field) and
   before PRD-03 (probe wants to test the *saved* key path).

## 8. Testing strategy (hermetic — no network in CI)

- **Fake secrets store**: tiny in-memory `_Backend` (`fake:` prefix) injected via
  `LLMProviderFactory(secrets=FakeSecrets())` — constructor param exists; no monkeypatching.
  The `encrypted` backend is also CI-safe (pure `cryptography`, no network) for
  round-trip tests.
- **Factory unit tests** (extend the suite that covers `_SpyFactory`/resolution):
  - org row with `secret_ref` → builder receives `secret_value` (assert via a spy builder).
  - `secret_ref` present, resolve → `None` ⇒ `SecretResolutionError` (NOT env fallback).
  - `secret_ref` NULL ⇒ `secret_value is None` (env fallback preserved).
  - override row without ref + same provider ⇒ inherits org key; different provider ⇒ no key.
  - cache: second resolve within TTL doesn't hit the store (spy call-count).
- **Route tests** (existing admin-route test style, sqlite/pg test engine): PUT with `api_key`
  persists a ref & response has no key material; GET returns `has_key` true/false; PUT without
  `api_key` preserves ref (FR-8); DELETE …/key nulls it.
- **Leak test**: serialize every response model + emitted events from a full PUT/GET cycle;
  assert the plaintext test key appears nowhere.

## 9. Effort estimate

**S — ~1 engineer-week.** Factory: ~40 LOC + tests. Routes: ~60 LOC + tests. Cache: ~30 LOC.
No migration, no UI (PRD-02), no new deps.

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Hard-fail (FR-6) breaks a tenant mid-turn after a bad rotation | PRD-03's pre-save probe validates keys before persist; error message names the fix ("re-enter the key in Settings → Models") |
| Multi-replica cache staleness after rotation (≤ TTL) | Documented bound; TTL configurable to 0; rotation keeps old key valid until admin revokes upstream |
| Vault down ⇒ all tenant LLM calls fail | Correct behavior (fail closed), but noisy — cache absorbs blips ≤ TTL; health check (PRD-03) surfaces it |
| Operator key still used when tenant has none | Intentional default (freemium/managed tiers); PRD-07 budgets can gate it |
| Key material in tracebacks | `SecretResolutionError` message contains no ref/value; builders receive the key as kwargs (already the pattern, `anthropic.py:17`) |

## 11. Success metrics

- 100% of LLM calls for an org with a stored key authenticate with that key (verifiable in a
  staging env by revoking the instance env key and observing the org still works).
- 0 occurrences of key/ref material in API responses, logs, clickstream events (leak test in CI).
- Key rotation propagates within `PDLC_SECRET_CACHE_TTL_S` on all replicas.
- p50 added latency on `resolve()` hot path < 1 ms with warm cache.

## 12. Dependencies

- Existing: secretstore (`app/secretstore/__init__.py`), RLS context (`app/db/rls.py`),
  admin guard (`routes/admin/_guard.py`). All shipped.
- Downstream dependents: PRD-02 (console key entry), PRD-03 (probe `use_saved` mode),
  PRD-06 (export must exclude/flag keys).

## 13. Open questions

1. Should `has_key` also disclose the backend kind (`encrypted` vs `vault`)? Lean no —
   operator detail, not tenant detail.
2. FR-10 inheritance: is org-key inheritance for same-provider overrides wanted, or should an
   override always require its own key when the org key shouldn't apply? Proposed: inherit
   (matches "override the *model*, keep the account"), revisit if a tenant asks for
   per-persona accounts.
3. Per-tier keys (different key for premium vs economy on the same provider)? No known demand;
   the schema wouldn't need to change (tier_map stays model-only) — defer.
4. Should the audit event (FR-9) be a first-class table for compliance exports instead of a
   clickstream event? Defer to PRD-06 (config versioning) which subsumes it.
