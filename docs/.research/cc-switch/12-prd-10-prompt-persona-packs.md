# PRD-10: Prompt & Persona Pack Management

- **Status:** Draft — for assessment
- **Date:** 2026-07-05
- **Origin:** [cc-switch gap analysis](02-gap-analysis.md) — gap #11 (GAP)
- **Related PRDs:** [PRD-02 Settings Console](04-prd-02-provider-settings-console.md) (console
  surface) · [PRD-06 Config versioning](08-prd-06-config-versioning-import-export.md) (bundle
  format shared for export/import)

## 1. Problem & motivation

Every pdlcflow org gets the same ten agents. Persona soul-specs — the markdown files that
define each agent's identity, beliefs, tone, and working style — are baked into the graph
package as package data (`packages/pdlc-graph/pdlc_graph/personas/*.md`, loaded by
`load_persona_spec`, `personas/loader.py:33-36`). An org that wants Muse to ideate with its
domain vocabulary, Neo to plan against its engineering standards, or Atlas to review with its
compliance checklist has exactly one option: fork the repo.

**What cc-switch does here:** a prompts manager with a Markdown editor, preset prompts with
activation switching, smart backfill protection for existing data, cross-app sync of
`CLAUDE.md`/`AGENTS.md`/`GEMINI.md`, and versioned skill backups (inventory §5). Translated to
pdlcflow's server-side persona model: **org-level persona prompt overrides with versioning,
activation switching, and pack import/export.**

### Grounding: how prompts actually flow today (important nuance)

Two prompt layers exist, and only one is currently reachable by `complete()`:

1. **Soul-specs** (`personas/atlas.md` … `sentinel.md`) — frontmatter (`tier:` consumed by
   `persona_tier`, `loader.py:39-58`) + the identity document. The loader docstring calls them
   "the system prompt for each persona's create_react_agent" (`loader.py:1-10`), but grep shows
   `load_persona_spec` has **no consumers outside the personas package** — the spec body is not
   currently passed to models.
2. **Ad-hoc node system strings** — graph nodes call `complete(persona, prompt, system="PDLC
   PRD author")`-style short strings (`graphs/brainstorm/define.py:47`,
   `graphs/brainstorm/plan.py:81`) or omit `system` entirely
   (`graphs/brainstorm/discover.py:140`).

So this PRD has a prerequisite milestone: **route soul-specs through a single resolution seam
into `complete()`'s system prompt** (M0 below). Without it, "org overrides of persona prompts"
would override text that never reaches a model. This also fixes a latent inconsistency for free
(the intended persona identities finally reach the LLM).

## 2. Goals / Non-goals

**Goals**
- G1 (M0): One resolution seam through which every persona's effective system prompt flows;
  packaged soul-specs become the default that models actually receive.
- G2: Org-level override of any persona's prompt body, with drafts, immutable versions, and
  explicit activation (activate/deactivate = switch back to the packaged default).
- G3: Pack export/import: a JSON bundle of persona prompt overrides, portable across orgs and
  deployments.
- G4: Hermetic CI preserved: without engine wiring, the graph package resolves prompts from
  packaged files exactly as today — byte-identical stub outputs.
- G5: Guardrails: size limits, valid-persona/tier constraints, no templating engine (plain
  text), full tenant isolation.

**Non-goals**
- NG1: Editing the *node-level task prompts* (the `prompt = f"..."` bodies inside graph nodes)
  — those encode workflow logic, not persona identity; overriding them per-org would fork the
  product's behavior contract.
- NG2: A public prompt marketplace / registry search (cc-switch's skills.sh analog).
- NG3: Per-user or per-project prompt overrides — org-level only in v1.
- NG4: Overriding Sentinel's spec *behavior* — Sentinel is a deterministic evaluator, not an
  LLM (`personas/loader.py:7-11`); its md is display-only and excluded from overrides.
- NG5: Skills (executable tool bundles) — that space belongs to PRD-09 (MCP) in pdlcflow's
  architecture.

## 3. Users & user stories

- **Org admin:** "I edit Muse's prompt to include our product-domain glossary, preview the
  diff against the packaged default, activate v3, and every new brainstorm turn uses it."
- **Org admin:** "Neo's custom prompt made plans worse. I deactivate it — instantly back to
  the stock persona — and later reactivate v2 instead of v3."
- **Platform/consultancy operator:** "I export our tuned 'fintech pack' from the template org
  and import it into each client org."
- **Compliance reviewer:** "Every prompt version is immutable with author + timestamp; I can
  see exactly what system prompt was active during any period."

## 4. Functional requirements

| ID | Requirement | MoSCoW |
|---|---|---|
| FR-1 | M0 seam: `resolve_persona_prompt(persona) -> str` used by `llm_port.complete()` when the caller passes no explicit system; packaged soul-spec body is the default | Must |
| FR-2 | `persona_prompts` table: (org, persona, version) immutable rows; states draft → active → archived; ≤1 active per (org, persona) | Must |
| FR-3 | Admin API: list/read/create-draft/activate/deactivate/archive per persona; diff endpoint vs packaged default | Must |
| FR-4 | Engine resolver: active org override wins, else packaged default; per-org TTL cache with invalidation on activation | Must |
| FR-5 | Pack export (`GET /admin/prompts/export`) / import (`POST /admin/prompts/import`) — JSON bundle, imported as *drafts* (never auto-activated; cc-switch's "backfill protection" analog) | Must |
| FR-6 | Guardrails: body ≤ 32 KiB, valid persona (10-name list minus sentinel), frontmatter optional — if present, `tier:` must be in `TIERS` (`personas/loader.py:27`) | Must |
| FR-7 | Console editor: markdown editing, packaged-default preview/diff, version history, activate switch | Should |
| FR-8 | Tier override via frontmatter: an org prompt's `tier:` supersedes the packaged tier in `persona_tier` resolution | Should |
| FR-9 | `prompt.activated` / `prompt.deactivated` clickstream events (audit) | Should |
| FR-10 | Eval hook: run the eval harness (`PDLC_RUN_EVALS`) against a draft on a canned scenario before activation | Could |
| FR-11 | Per-project overrides | Won't (v1) |

## 5. Detailed design

### 5.1 M0 — the resolution seam (graph package)

Extend `personas/loader.py` with an injectable resolver, exactly the `llm_port`/`tracing` port
idiom (`llm_port.py:62-74`, `tracing.py:52-64`):

```python
# personas/loader.py (additions)
_prompt_resolver: Callable[[str], str | None] | None = None   # returns None → use packaged

def set_prompt_resolver(fn) -> None: ...      # engine boot injects the DB-backed lookup
def reset_prompt_resolver() -> None: ...      # tests

def resolve_persona_prompt(name: str) -> str:
    if _prompt_resolver is not None:
        body = _prompt_resolver(name)         # engine consults org context internally
        if body:
            return body
    return load_persona_spec(name)            # packaged default (loader.py:33-36)
```

`llm_port.complete()` (`llm_port.py:97-128`) gains one rule: when `system is None`, set
`system = resolve_persona_prompt(persona)` (alongside the existing tier defaulting at
`llm_port.py:109-112`). Call sites that pass explicit short strings
(`brainstorm/define.py:47`) are migrated in M0 to *prepend the persona prompt* rather than
replace it: `system = resolve_persona_prompt(p) + "\n\n## Task role\nPDLC PRD author"`, via a
small helper so nodes stay one-liners.

**Hermetic impact & mitigation:** the offline `_StubBackend` hashes `(persona, prompt)` only
(`llm_port.py:48`) — it ignores `system` — so stub outputs and the entire CI suite remain
byte-identical after M0. Real-model output changes (personas finally get identities); that is
the *intent* of M0 and is release-noted as behavior change for `wire_llm` deployments.

**Caching:** `persona_tier` is `functools.cache`d (`loader.py:39-40`) — safe today because
packaged files are immutable. With overrides + FR-8, tier resolution must consult the resolver
first; the packaged-tier path keeps its cache, the resolver path relies on the engine's TTL
cache (§5.3). `resolve_persona_prompt` itself is uncached in the graph package (the resolver
owns caching).

### 5.2 Data model / migrations

```sql
CREATE TABLE persona_prompts (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  persona     TEXT NOT NULL CHECK (persona IN
                ('atlas','bolt','echo','friday','jarvis','muse','neo','phantom','pulse')),
  version     INT  NOT NULL,
  body        TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','active','archived')),
  created_by  UUID REFERENCES users(id),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  activated_at TIMESTAMPTZ,
  UNIQUE (org_id, persona, version)
);
CREATE UNIQUE INDEX persona_prompts_one_active
  ON persona_prompts (org_id, persona) WHERE status = 'active';
-- RLS + FORCE, mirroring org_llm_config policies (0002_rls / 0003_rls_force).
```

The persona CHECK deliberately excludes `sentinel` (NG4) — note this diverges from
`agent_llm_config`'s 10-name list (`db/models.py:286-289`), which includes sentinel; that
existing constraint is arguably its own latent oddity (sentinel never calls an LLM) but is out
of scope here. Versions are immutable: activation flips `status` only; "editing" an active
prompt creates version N+1 as draft.

### 5.3 Engine resolver — `app/runtime/prompt_backend.py`

```python
class DBPromptResolver:
    def __call__(self, persona: str) -> str | None:
        org = self._current_org()            # pdlc_graph.ports.current_org, the
                                             # llm_backend._tenant idiom (llm_backend.py:33-42)
        if not self._is_org_uuid(org):       # self-host/no-DB → packaged default
            return None
        return self._cached_active_body(org, persona)   # TTL 60s
```

- Query: `SELECT body FROM persona_prompts WHERE org_id=:o AND persona=:p AND status='active'`
  under `set_org_context` (the factory's `_org_default` idiom, `app/llm/factory.py:166-187`).
- Cache: per-(org, persona) with 60 s TTL **plus** eager invalidation — the activation route
  bumps a per-org generation counter the resolver checks (cheap, same-process; multi-process
  deployments fall back to TTL staleness ≤ 60 s, acceptable for prompt changes).
- Wiring: `wire_prompt_resolver(settings)` beside `wire_llm_backend`
  (`app/runtime/llm_backend.py:141-164`), guarded by `task_store == "postgres"` presence like
  the factory's DB handle (`llm_backend.py:154-158`); no new flag — resolver with no DB or no
  rows is a transparent no-op.

### 5.4 API contract

Router `app/routes/admin/prompts.py`, mounted under `require_admin`
(`routes/admin/__init__.py:21`), org via `admin_org` + `set_org_context`
(`routes/admin/models.py:53-60`):

```
GET    /admin/prompts                          → [ { persona, active_version, versions: n,
                                                     overridden: bool } × 9 ]
GET    /admin/prompts/{persona}                → { persona, packaged_default: "...",
                                                   versions: [ {version, status, created_by,
                                                                created_at, activated_at} ] }
GET    /admin/prompts/{persona}/versions/{v}   → { version, status, body }
POST   /admin/prompts/{persona}                ← { body }            → { version }   (new draft)
POST   /admin/prompts/{persona}/versions/{v}/activate                → { ok }        (archives prior active)
POST   /admin/prompts/{persona}/deactivate                           → { ok }        (back to packaged)
GET    /admin/prompts/export                   → { format: "pdlcflow.prompt-pack/v1",
                                                   prompts: { "muse": {body, source_version}, ... } }
POST   /admin/prompts/import?mode=draft        ← (pack JSON)         → { created: {persona: version} }
```

Import always lands as drafts (FR-5); a `?dry_run=true` returns per-persona validation results
without writing.

### 5.5 Pack format

```json
{ "format": "pdlcflow.prompt-pack/v1",
  "exported_at": "2026-07-05T…Z",
  "prompts": { "muse": { "body": "---\ntier: premium\n---\n# Soul Spec — Muse …" }, … } }
```

Plain bodies, no secrets, no org identifiers — safe to share publicly. Aligns with PRD-06's
bundle envelope so a future combined "org config export" can embed it.

### 5.6 Console (FR-7)

Studio route `admin/prompts.tsx`: persona grid (avatar, overridden badge, active version),
detail view with side-by-side packaged-default vs draft markdown, version timeline, Activate
switch with confirm, Export/Import buttons. Read-only card for Sentinel explaining NG4.

## 6. Security & tenancy

- RLS + FORCE on `persona_prompts`; prompts are org-private (an org's tuned prompts are IP).
- **No templating engine** (FR guardrail): bodies are static text — no `{variable}`
  interpolation, no Jinja — so a prompt cannot exfiltrate state or another tenant's data at
  render time; cross-tenant leakage is structurally impossible (resolution is keyed by the
  turn's org context, `ports.current_org`).
- Prompt content is inherently a *self*-injection surface (an org admin can instruct their own
  agents badly) — accepted: admins already control their inputs. The eval hook (FR-10) and
  Sentinel's deterministic gates remain unaffected by prompt overrides.
- Size cap (32 KiB) bounds token-cost abuse and context blowout; activation events (FR-9)
  give an audit trail with actor identity.

## 7. Rollout & migration

1. **M0** ships alone first (graph + engine seam, no DB, no API): packaged soul-specs start
   flowing as system prompts. Flagged in release notes as model-output-affecting for
   `wire_llm` deployments; CI/stub path unchanged.
2. **M1**: table + admin API + resolver wiring. Dark until a row is activated.
3. **M2**: console editor + export/import + events.
4. Rollback at any stage: deactivate rows (or drop the resolver) → packaged defaults; M0
   rollback is a revert of the `system=None` defaulting rule.

## 8. Testing strategy (hermetic)

- **Graph:** resolver-port tests (set/reset fixtures; None → packaged fallback); M0 test that
  stub outputs are byte-identical (guards the `llm_port.py:48` invariant); `persona_tier`
  override precedence (FR-8) with an injected fake resolver.
- **Engine:** resolver unit tests with a seeded test DB (active/draft/none × cache
  invalidation on activate); route tests under RLS (two orgs; cross-org invisibility);
  immutability (PUT on a version 404s — versions are POST-only); one-active partial-index
  violation test.
- **Pack round-trip:** export → import(dry_run) → import → activate → resolve, all against
  the test DB; malformed-pack rejection cases.
- No network anywhere; the only LLM-adjacent test is prompt *resolution*, never completion.

## 9. Effort estimate

**M — ~3 eng-weeks.** M0 seam + call-site migration + hermetic proof (0.75w), table/RLS/API/
resolver (1w), console editor + diff + import/export (1w), docs + events (0.25w).

## 10. Risks & mitigations

- **R1: M0 changes live-model behavior for existing `wire_llm` users** (personas gain full
  identities; token cost per call rises by the spec length, ~2-4 KiB). Mitigate: release-note
  prominently; measure token delta in staging; specs are one-time-per-call system text, cost
  visible in the existing `llm.tokens_spent` stream.
- **R2: Bad org prompt degrades output quality silently.** Mitigate: one-click deactivate;
  version history; FR-10 eval preview; diff-vs-default view keeps edits anchored.
- **R3: Cache staleness across multiple engine processes** (≤ 60 s window). Accepted for v1;
  Redis pub/sub invalidation (the existing bus) is the M3 upgrade path if it bites.
- **R4: Scope creep into node task-prompt editing (NG1).** Mitigate: the API surface is
  persona-keyed only; document the boundary in the PRD and console copy.

## 11. Success metrics

- M0: 100% of `complete()` calls carry a persona system prompt (assert via span attribute
  sampling); zero CI diffs.
- ≥1 org activates an override and retains it > 30 days (i.e., it helped).
- Pack import used for at least one multi-org rollout (consultancy/template scenario).
- Zero cross-tenant prompt reads (security review + RLS tests).

## 12. Dependencies

- None hard on other PRDs. Console shell benefits from PRD-02's admin-UI plumbing; export
  envelope aligns with PRD-06. M0 is self-contained and valuable alone.

## 13. Open questions

1. Should M0 *prepend-migrate* the existing ad-hoc `system=` strings (recommended, §5.1) or
   leave explicit-system call sites untouched in v1? Prepending is more faithful to persona
   identity but touches ~a dozen nodes.
2. FR-8 tier override: is letting an org bump Echo from `economy` to `premium` via prompt
   frontmatter desirable, or should tier stay solely in `agent_llm_config`? (Two knobs for one
   concept is a smell — leaning: frontmatter tier in org prompts is *ignored*, document it.)
3. Multi-language packs (cc-switch is zh-first): packs are opaque text so nothing blocks a
   Chinese-language pack today — do we want language tagging in the pack format now (cheap) or
   never?
4. Should export include the *packaged* defaults for non-overridden personas (portable full
   snapshot) or only overrides (current design)?
