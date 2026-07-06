# PRD-06: Provider Config Versioning, Audit, Backup & Import/Export

> **Status:** Draft — for assessment · **Date:** 2026-07-05
> **Origin:** [cc-switch gap analysis](02-gap-analysis.md), row 7
> **Related PRDs:** builds on [PRD-01 BYOK](03-prd-01-byok-completion.md) (secret_ref
> handling rules) and [PRD-02 Console](04-prd-02-provider-settings-console.md) (history UI);
> versions the shapes introduced by [PRD-04](06-prd-04-provider-preset-catalog.md)
> (`openai_compatible`) and [PRD-05](07-prd-05-resilient-llm-routing.md) (`failover_chain`).

## 1. Problem & motivation

cc-switch treats config changes as dangerous and reversible: every rewrite is atomic, the 10
most recent backups auto-rotate in `~/.cc-switch/backups/`, the active provider can't be
deleted, and whole provider sets export/import as JSON (plus deep-link sharing). Users trust
one-click switching *because* they can get back to the last working state.

pdlcflow's provider config has none of that safety net:

- `PUT /admin/models/org-default` is a blind upsert (`routes/admin/models.py:64-81`): the
  previous provider/endpoint/tier_map is **destroyed in place**, with no record of what it
  was, who changed it, or when. Same for agent overrides (`:98-118`) and deletes (`:121-132`).
- A bad tier_map or endpoint typo breaks every subsequent LLM call for the org (and with
  PRD-04's `openai_compatible`, an endpoint typo is easy). Recovery = remember what the old
  values were.
- There is no way to copy a proven provider setup between orgs — the natural dev→prod
  promotion flow of a multi-tenant deployment — or to snapshot config before an experiment.
- The only "export" in the codebase (`routes/admin/exports.py`) is BI analytics CSV/DDL,
  unrelated to config.

This PRD is also the **audit substrate** the other PRDs assume: PRD-01 (who set which key
ref), PRD-04 (endpoint changes logged — SSRF forensics), PRD-05 (what the chain was when an
incident happened).

## 2. Goals / Non-goals

**Goals**

- G1. **Immutable version history**: every write to `org_llm_config` / `agent_llm_config`
  (create/update/delete, via any route incl. preset-apply and import) records who, when, and
  the full before-state.
- G2. **One-click rollback** to any recorded version.
- G3. **Export** an org's full provider set (org default + agent overrides + failover chain)
  as a self-describing JSON document — **secrets excluded by construction**.
- G4. **Import** with dry-run validation and an explicit conflict strategy; supports the
  dev-org → prod-org promotion workflow.
- G5. Bounded storage: retention policy on version rows.

**Non-goals**

- NG1. Not a general audit-log framework for all tables (clickstream already covers workflow
  events); scope is the two LLM-config tables. If a general framework arrives later, this
  migrates into it.
- NG2. No secret values in exports, versions, or diffs — ever. Key *migration* between
  instances is out of scope (keys are re-entered on the target; PRD-01 owns key entry).
- NG3. No scheduled/automatic backups to external storage (Postgres backups + this export
  endpoint compose to cover it; cc-switch's WebDAV/S3 sync is N/A per the gap analysis).
- NG4. No cross-instance live sync.

## 3. Users & user stories

- **Org admin:** "As an org admin, I want to see who changed our provider from Anthropic to a
  gateway and when, so config surprises are attributable."
- **Org admin:** "As an org admin, I want to roll back to yesterday's working config in one
  click after a bad tier_map edit, so an outage lasts seconds, not a support cycle."
- **Platform team:** "As a platform admin, I want to export the staging org's provider set and
  import it into the production org (dry-run first), so promotion is reviewable and
  repeatable."
- **Security reviewer:** "As a security reviewer, I want endpoint changes (SSRF-relevant,
  PRD-04) in an immutable trail with actor identity."

## 4. Functional requirements

| ID | Requirement | MoSCoW |
|----|-------------|--------|
| FR-1 | New RLS-FORCEd table `llm_config_versions`: `id`, `org_id`, `scope` (`org` \| persona name), `change_kind` (`update`/`delete`/`rollback`/`import`/`preset_apply`), `snapshot` JSONB (full **prior** row state; null for prior-nonexistent), `actor_user_id`, `actor_label`, `created_at`. | Must |
| FR-2 | All mutating admin-models routes write a version row **in the same transaction** as the mutation (no drift possible). | Must |
| FR-3 | `GET /admin/models/versions?scope=&limit=` lists versions (newest first) with a computed field-level diff vs. the next-newer state. | Must |
| FR-4 | `POST /admin/models/versions/{id}/rollback` restores that version's snapshot for its scope; the rollback itself creates a new version row (`change_kind: rollback`) — history is append-only, never rewritten. | Must |
| FR-5 | Rollback restores `secret_ref` **only if** the referenced secret still resolves (secretstore lookup); otherwise the config is restored with `secret_ref = null` and the response flags `"secret_requires_reentry": true`. | Must |
| FR-6 | `GET /admin/models/export` returns a versioned JSON document: `{format_version, exported_at, source: {org_label}, org_default: {...}, agent_overrides: [...], catalog_version?}`. `secret_ref` fields are **transformed, never copied raw** (§5.3). | Must |
| FR-7 | `POST /admin/models/import?dry_run=true` validates and returns a per-item plan (`create`/`overwrite`/`skip`/`error` + reasons) without writing. Non-dry-run applies atomically (all-or-nothing transaction) with `strategy=replace` (drop rows absent from the document) or `strategy=merge` (only upsert present items; default). | Must |
| FR-8 | Import validation reuses the write-path validators (provider enum incl. `openai_compatible`, tier_map completeness, endpoint SSRF rules from PRD-04 §6, chain rules from PRD-05 §5.6) — an import can't smuggle in states the PUT routes would reject. | Must |
| FR-9 | Retention: keep the most recent `PDLC_LLM_CONFIG_VERSION_KEEP` (default 50) versions per (org, scope); prune opportunistically on write. Rollback targets never dangle (pruning is count-based per scope, oldest-first). | Should |
| FR-10 | Console: "History" panel on the Models page — timeline with actor/when/diff chips and per-entry Rollback button (confirm dialog shows the diff); Export/Import buttons with dry-run preview table. | Should |
| FR-11 | Clickstream events `llm_config.changed` / `.rolled_back` / `.imported` / `.exported` (metadata only — scope, change_kind, actor; no config payload) for org-level analytics. | Should |
| FR-12 | Deep-link/shareable config URLs (cc-switch `ccswitch://`) | Won't |

## 5. Detailed design

### 5.1 Data model

Alembic `0010_llm_config_versions.py`:

```python
class LLMConfigVersion(Base):
    __tablename__ = "llm_config_versions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)        # 'org' | '<persona>'
    change_kind: Mapped[str] = mapped_column(Text, nullable=False)  # CHECK: update|delete|rollback|import|preset_apply
    snapshot: Mapped[dict | None] = mapped_column(JSONB)            # prior row state; None = didn't exist
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    actor_label: Mapped[str | None] = mapped_column(Text)           # denormalized email/name at change time
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (Index("ix_llmcv_org_scope_created", "org_id", "scope", "created_at"),)
```

RLS policy + FORCE identical to the config tables (extend the `0002_rls.py`/`0003_rls_force.py`
pattern in the new migration). **Prior-state snapshots** (not post-state): rollback = "write
snapshot back", diff(vN) = snapshot(vN+1) ⊖ snapshot(vN) computed at read time — no dual
bookkeeping. Snapshot of the *current* live row is implicit (read the config table).

### 5.2 Write-path hook

A small helper used by every mutating route in `routes/admin/models.py` (and PRD-04's
preset-apply), inside the existing `with _engine().begin() as conn:` block — same transaction
(FR-2):

```python
def record_version(conn, org_id, scope, change_kind, actor):
    prior = _read_current(conn, org_id, scope)     # select from org/agent table
    conn.execute(text("insert into llm_config_versions (…) values (…)"),
                 {..., "snapshot": json.dumps(prior)})
    _prune(conn, org_id, scope)                    # FR-9, count-based delete
```

Actor comes from the same auth context that `admin_org(...)` (`routes/admin/_guard.py`)
already derives the org from; `actor_label` denormalizes the display identity so history
survives user deletion.

### 5.3 Export document & secret handling

```json
{
  "format_version": 1,
  "exported_at": "2026-07-05T18:00:00Z",
  "source": {"org_label": "acme-staging"},
  "catalog_version": "2026.07",
  "org_default": {
    "provider": "openai_compatible",
    "endpoint": "https://openrouter.ai/api/v1",
    "region": null,
    "tier_map": {"premium": "…", "balanced": "…", "economy": "…"},
    "failover_chain": [ {"provider": "bedrock", "region": "us-east-1", "secret": {"required": false}} ],
    "secret": {"required": true, "ref_kind": "vault", "ref_hint": "vault:pdlcflow/…/llm"}
  },
  "agent_overrides": [ {"agent_persona": "bolt", "provider": "…", "model_id": "…", "secret": {…}} ]
}
```

Secret transformation rules (FR-6/NG2), keyed by the secretstore ref prefixes
(`app/secretstore/__init__.py`, `app/config.py:38-50`):

| Stored `secret_ref` | Exported as |
|---|---|
| `enc:<ciphertext>` (Fernet; **the ref IS the ciphertext**) | `{"required": true, "ref_kind": "encrypted"}` — ciphertext **stripped**. Exporting it would leak encrypted key material, and it's useless cross-instance anyway (different Fernet `secret_key`). |
| `vault:<path>` | `{"required": true, "ref_kind": "vault", "ref_hint": "vault:<path>"}` — a *pointer* is safe and useful when source and target share a Vault; import re-links only after the target resolves it (FR-5-style check). |
| `env:NAME` | `{"required": true, "ref_kind": "env", "ref_hint": "env:NAME"}` — safe pointer. |
| null | `{"required": <provider needs key?>}` |

Import consequently never writes a `secret_ref` it cannot resolve on the target instance; the
dry-run plan lists every item as `secret: reusable | re-entry required`, and the console walks
the admin through re-entry (PRD-01 endpoints) after apply.

### 5.4 Import semantics

- **Dry-run (default-encouraged):** parse → validate each item through the shared write-path
  validators (FR-8) → resolve secret reusability → return plan; no writes, no version rows.
- **Apply:** single transaction; for each planned item, `record_version(change_kind='import')`
  then upsert (or delete under `strategy=replace`). Any item failing re-validation aborts the
  whole transaction (atomicity beats partial config).
- **Promotion flow:** export from staging org (admin A) → file/console paste → dry-run against
  prod org (admin B, their own RLS context) → review plan table → apply → re-enter/relink
  secrets. Cross-org is inherent: import runs entirely in the *caller's* org context; the
  document carries no org ids.

### 5.5 Rollback

`POST /admin/models/versions/{id}/rollback`: load version (RLS-scoped) → if
`snapshot is null`, the rollback is a delete of the current row (restoring "didn't exist") →
else validate snapshot through current validators (a snapshot may predate a rule — e.g. an
endpoint now failing SSRF checks is rejected with a clear error rather than restored) → FR-5
secret check → `record_version(change_kind='rollback')` → write. Console confirm-dialog
renders the field diff before executing.

### 5.6 API surface (added to `routes/admin/models.py` router)

```
GET    /admin/models/versions?scope=org&limit=20        → [{id, scope, change_kind, actor_label, created_at, diff: [{field, from, to}]}]
POST   /admin/models/versions/{id}/rollback             → {ok, restored_scope, secret_requires_reentry}
GET    /admin/models/export                             → document (§5.3)  [Content-Disposition: attachment]
POST   /admin/models/import?dry_run=true&strategy=merge → {plan: [{scope, action, reasons[], secret}] }
POST   /admin/models/import?strategy=merge              → {ok, applied: n, version_ids: […]}
```

All behind the existing `admin_org` dependency; export additionally emits the FR-11
clickstream event.

## 6. Security & tenancy

- `llm_config_versions` is RLS-FORCEd and org-scoped like its parents; versions never cross
  tenants; export/import operate solely in the caller's org context.
- **Secrets:** never in snapshots' plaintext (snapshots store `secret_ref` as-is — refs, not
  values — acceptable *inside* the DB since the config tables already store them; the
  export boundary is where refs are transformed/stripped, §5.3). Diffs render `secret_ref`
  changes as `set / changed / cleared`, never the ref string, in API responses.
- Import is a config-write amplifier → it must reuse, not reimplement, write-path validation
  (FR-8) so SSRF/enum/tier rules can't be bypassed; imports are rate-limit-worthy admin
  actions and land in the version trail + clickstream.
- Export documents are tenant data; the console should mark them "contains endpoint URLs and
  model routing — handle as internal".

## 7. Rollout & migration

1. Migration 0010 (new table + RLS) — additive, zero behavior change.
2. Engine release: version-recording hook (silent; history starts accruing), then
   versions/rollback endpoints, then export/import.
3. Console history panel + export/import UI with PRD-02's Models page (or as its fast-follow).
4. No backfill: history begins at deployment ("Initial state" pseudo-entry rendered by the
   console from the current live row).

## 8. Testing strategy

Hermetic, DB-backed via the existing migration/route test harness (no network):

- **Transactionality (FR-2):** force the upsert to fail after `record_version` → assert no
  orphan version row (same-transaction rollback).
- **History/diff:** sequence of PUTs → GET versions shows correct prior-state snapshots and
  field diffs; delete → snapshot; rollback → restores bytes-equal row and appends
  `change_kind=rollback`.
- **Secret rules:** export of `enc:`/`vault:`/`env:` refs matches the §5.3 table exactly
  (property test: no `secret_ref` value from the DB ever appears verbatim in an export with
  `ref_kind: encrypted`); FR-5 rollback with a since-deleted vault path → `secret_ref` null +
  flag.
- **Import:** dry-run plan correctness for create/overwrite/skip/error; merge vs replace;
  mid-apply validation failure aborts atomically; imported items all carry version rows;
  FR-8 parity test (any payload rejected by PUT is rejected by import — run both validators
  over a shared fixture corpus).
- **Retention:** 60 writes → 50 rows, oldest pruned, newest intact.
- **RLS:** org B cannot list/rollback org A's versions (existing RLS test pattern).

## 9. Effort estimate

**M — ~2–2.5 eng-weeks.** Table + hook + versions/rollback API (1 w), export/import with
secret rules + dry-run planner (1 w), console history/import UI (0.5 w on PRD-02
scaffolding). Low technical risk; the care is in secret-handling rules and validator reuse.

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Secret leakage through the export boundary | §5.3 transform table + property test; review checklist item; refs-only even inside snapshots |
| Import bypasses newer validation rules | FR-8 shared-validator design + parity test corpus |
| Snapshot schema drift (columns added by PRD-04/05 later) | Snapshots are JSONB of the row as-of write; rollback validates through *current* rules and surfaces incompatibilities instead of blind-writing |
| Version table growth | FR-9 count-based retention; rows are small (config-sized) |
| Rollback restores a config whose secret no longer exists → silent auth failures | FR-5 resolve-check + `secret_requires_reentry` flag + console prompt |
| Cross-org import used to exfiltrate another org's setup | Export requires admin of the source org; document carries no secrets; endpoints/model routing are the only sensitive payload (flagged in console, §6) |

## 11. Success metrics

- 100% of config mutations have a version row (invariant check in CI + a periodic count
  assertion between mutation events and versions).
- Config-mistake recovery time: rollback in < 30 s from the console vs. "reconstruct from
  memory" today.
- ≥ 1 real promotion (staging→prod import) executed via dry-run flow in the first month of
  availability (design-partner validation).
- Zero secret values in any export document (property test, standing).

## 12. Dependencies

- **PRD-01 (BYOK):** defines secretstore resolution used by FR-5 and §5.3 reusability checks,
  and the re-entry endpoints the import flow chains into. Hard dependency for the secret
  rules; the versioning core (FR-1–FR-4) only needs today's `secret_ref` column.
- **PRD-02 (Console):** history panel / import-export UI. API-first value exists without it.
- **PRD-04 / PRD-05:** their new fields (`openai_compatible`, endpoints, `failover_chain`)
  are versioned/exported transparently via JSONB snapshots; their validators are the ones
  FR-8 reuses. This PRD should land **after** PRD-01/02 but can land before or after 04/05
  (snapshots don't care about the schema's width).

## 13. Open questions

1. Should preset-apply (PRD-04) and future automated writers (e.g. a failover "sticky
   fallback" persisting state) be distinguishable actors (`actor_label: "system:preset"`)?
   Proposed: yes — `change_kind` + actor_label conventions cover it.
2. Import auth for promotion: is same-human-different-org sufficient (current design), or do
   we want an explicit org-to-org share grant object?
3. Retain deleted-org history? (`ondelete=CASCADE` currently wipes it with the org — fine for
   tenant deletion/GDPR, but confirm with compliance posture.)
4. Should `GET /admin/models/export` include the preset id it was derived from (provenance),
   when PRD-04's apply recorded one?
