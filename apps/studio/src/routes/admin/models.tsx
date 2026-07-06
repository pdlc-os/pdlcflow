// Models settings — org default LLM provider + per-agent overrides, wired to
// /v1/admin/models/*. Key entry is write-only (the UI only ever learns
// `has_key`); Test probes the row's CURRENT draft via POST /admin/models/test
// before anything is saved.

import { useEffect, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import {
  admin,
  type AgentOverride,
  type ConfigVersion,
  type FallbackEntryBody,
  type ImportPlanItem,
  type ModelDefaults,
  type OrgDefault,
  type Preset,
  type ProbeBody,
  type TestResult,
  type TierName,
} from '@/lib/api';
import { useThread } from '@/store/useThread';
import { ErrorNotice, Loading, PageHeader } from './_shared';

const TIERS: TierName[] = ['premium', 'balanced', 'economy'];
const REGION_PROVIDERS = new Set(['bedrock', 'vertex', 'azure']);
const ENDPOINT_PROVIDERS = new Set(['ollama', 'azure', 'openai_compatible']);
// Providers whose builders would fall back to the operator's env key — chain
// entries for these require their own key (mirrors the backend rule).
const KEYED_PROVIDERS = new Set(['anthropic', 'openai', 'gemini', 'azure']);

interface ChainDraft {
  provider: string;
  endpoint: string;
  region: string;
  tierMap: Record<TierName, string> | null;
  keyInput: string;
  hasKey: boolean;
}

const inputCls = 'rounded border border-border bg-bg px-2 py-1';
const btnCls =
  'rounded border border-border px-2 py-1 text-xs text-muted-fg hover:bg-border/60 disabled:opacity-40';

type TestState = 'idle' | 'testing' | TestResult;

function useDirtyGuard(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);
}

function TestChip({ state }: { state: TestState }) {
  if (state === 'idle') return null;
  if (state === 'testing') return <span className="text-xs text-muted-fg">testing…</span>;
  return state.ok ? (
    <span className="text-xs text-green-500">
      ✓ {state.latency_ms != null ? `${state.latency_ms} ms` : 'ok'}
      {state.tested_model ? ` · ${state.tested_model}` : ''}
    </span>
  ) : (
    <span className="text-xs text-red-400" title={state.message}>
      ✗ {state.error_class ?? 'failed'}
    </span>
  );
}

function probeFailure(e: unknown): TestResult {
  return {
    ok: false,
    latency_ms: null,
    error_class: 'request_failed',
    tested_model: null,
    message: e instanceof Error ? e.message : String(e),
  };
}

export function AdminModels() {
  const orgId = useThread((s) => s.orgId);
  const defaults = useQuery({
    queryKey: ['admin', 'modelDefaults', orgId],
    queryFn: () => admin.modelDefaults(orgId),
    refetchOnWindowFocus: false,
  });
  const orgDefault = useQuery({
    queryKey: ['admin', 'orgDefault', orgId],
    queryFn: () => admin.getOrgDefault(orgId),
    refetchOnWindowFocus: false, // a focus refetch would clobber dirty drafts
  });
  const overrides = useQuery({
    queryKey: ['admin', 'agentOverrides', orgId],
    queryFn: () => admin.listAgentOverrides(orgId),
    refetchOnWindowFocus: false,
  });

  if (defaults.isLoading || orgDefault.isLoading || overrides.isLoading) return <Loading />;
  if (defaults.isError) return <ErrorNotice error={defaults.error} />;
  if (orgDefault.isError) return <ErrorNotice error={orgDefault.error} />;
  if (overrides.isError) return <ErrorNotice error={overrides.error} />;
  if (!defaults.data) return <Loading />;

  const byPersona = new Map((overrides.data ?? []).map((o) => [o.agent_persona, o]));

  return (
    <div className="max-w-3xl">
      <PageHeader
        title="Models"
        subtitle={
          <>
            Set the org default LLM provider, then override per-agent where it makes sense.
            Changes apply on each agent's next turn. Sentinel is a deterministic Python
            evaluator — it has no model.
          </>
        }
      />

      <section className="mb-6 rounded-xl border border-border p-4">
        <h3 className="mb-2 text-sm font-medium">Org default</h3>
        <OrgDefaultCard
          key={orgDefault.dataUpdatedAt} // remount → drafts reset after each save
          orgId={orgId}
          defaults={defaults.data}
          saved={orgDefault.data ?? null}
        />
      </section>

      <section className="mb-6 rounded-xl border border-border p-4">
        <h3 className="mb-2 text-sm font-medium">Per-agent overrides</h3>
        <div className="space-y-2">
          {defaults.data.personas.map((p) => (
            <PersonaRow
              key={`${p}:${overrides.dataUpdatedAt}`}
              orgId={orgId}
              persona={p}
              defaults={defaults.data}
              saved={byPersona.get(p)}
            />
          ))}
        </div>
      </section>

      <section className="mb-6 rounded-xl border border-border p-4">
        <h3 className="mb-2 text-sm font-medium">History</h3>
        <HistoryPanel orgId={orgId} />
      </section>

      <section className="rounded-xl border border-border p-4">
        <h3 className="mb-2 text-sm font-medium">Export / import</h3>
        <ExportImportPanel orgId={orgId} />
      </section>
    </div>
  );
}

// ── Org default ─────────────────────────────────────────────────────────────

function OrgDefaultCard({
  orgId,
  defaults,
  saved,
}: {
  orgId: string;
  defaults: ModelDefaults;
  saved: OrgDefault | null;
}) {
  const qc = useQueryClient();
  const [provider, setProvider] = useState(saved?.provider ?? defaults.instance_default.provider);
  const [tierMap, setTierMap] = useState<Record<TierName, string>>(
    saved?.tier_map ?? defaults.tier_maps[provider] ?? { premium: '', balanced: '', economy: '' },
  );
  const [region, setRegion] = useState(saved?.region ?? '');
  const [endpoint, setEndpoint] = useState(saved?.endpoint ?? '');
  const [keyInput, setKeyInput] = useState('');
  const [chain, setChain] = useState<ChainDraft[]>(() =>
    (saved?.failover_chain ?? []).map((e) => ({
      provider: e.provider,
      endpoint: e.endpoint ?? '',
      region: e.region ?? '',
      tierMap: e.tier_map,
      keyInput: '',
      hasKey: e.has_key,
    })),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [test, setTest] = useState<TestState>('idle');

  const savedChainNorm = useMemo(
    () =>
      JSON.stringify(
        (saved?.failover_chain ?? []).map((e) => ({
          p: e.provider, e: e.endpoint ?? '', r: e.region ?? '', t: e.tier_map,
        })),
      ),
    [saved],
  );
  const chainNorm = JSON.stringify(
    chain.map((e) => ({ p: e.provider, e: e.endpoint, r: e.region, t: e.tierMap })),
  );

  const dirty = useMemo(() => {
    if (keyInput || chain.some((e) => e.keyInput)) return true;
    if (!saved) return true; // nothing saved yet — saving creates the org row
    return (
      provider !== saved.provider ||
      TIERS.some((t) => tierMap[t] !== saved.tier_map[t]) ||
      (region || null) !== saved.region ||
      (endpoint || null) !== saved.endpoint ||
      chainNorm !== savedChainNorm
    );
  }, [saved, provider, tierMap, region, endpoint, keyInput, chain, chainNorm, savedChainNorm]);
  useDirtyGuard(dirty);

  const onProviderChange = (p: string) => {
    setProvider(p);
    // Switching providers invalidates the old model ids — prefill the
    // provider's defaults (still editable afterwards). openai_compatible has
    // no built-in map: start blank or pick a preset.
    setTierMap(defaults.tier_maps[p] ?? { premium: '', balanced: '', economy: '' });
    setTest('idle');
  };

  const applyPreset = (p: Preset) => {
    // Pre-fill only — the admin reviews, adds the key, Tests, then Saves.
    setProvider(p.provider);
    setTierMap(p.tier_map);
    setRegion(p.region ?? '');
    setEndpoint(p.endpoint ?? '');
    setTest('idle');
  };

  const save = async () => {
    if (
      saved &&
      provider !== saved.provider &&
      !window.confirm(
        'Switching the org default provider changes the model behind every agent ' +
          'in this org on their next turn. Continue?',
      )
    )
      return;
    setBusy(true);
    setError(null);
    try {
      const chainBody: FallbackEntryBody[] = chain.map((e) => ({
        provider: e.provider,
        endpoint: e.endpoint || null,
        region: e.region || null,
        tier_map: e.tierMap,
        ...(e.keyInput ? { api_key: e.keyInput } : {}),
      }));
      await admin.putOrgDefault(orgId, {
        provider,
        tier_map: tierMap,
        region: region || null,
        endpoint: endpoint || null,
        failover_chain: chainBody,
        ...(keyInput ? { api_key: keyInput } : {}),
      });
      setKeyInput('');
      await qc.invalidateQueries({ queryKey: ['admin', 'orgDefault', orgId] });
      await qc.invalidateQueries({ queryKey: ['admin', 'modelVersions', orgId] });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const removeKey = async () => {
    if (!window.confirm('Remove the stored API key? The org falls back to the instance key.'))
      return;
    setBusy(true);
    try {
      await admin.deleteOrgKey(orgId);
      await qc.invalidateQueries({ queryKey: ['admin', 'orgDefault', orgId] });
    } finally {
      setBusy(false);
    }
  };

  const runTest = async () => {
    setTest('testing');
    const body: ProbeBody =
      !keyInput && !dirty && saved?.has_key
        ? { scope: 'org-default', use_saved_key: true }
        : {
            provider,
            model_id: tierMap.balanced || undefined,
            region: region || null,
            endpoint: endpoint || null,
            ...(keyInput ? { api_key: keyInput } : {}),
          };
    try {
      setTest(await admin.testProvider(orgId, body));
    } catch (e) {
      setTest(probeFailure(e));
    }
  };

  return (
    <div className="space-y-3 text-sm">
      {!saved ? (
        <div className="rounded border border-dashed border-border px-3 py-2 text-xs text-muted-fg">
          No org config saved — currently inheriting the instance default (
          {defaults.instance_default.provider}
          {defaults.instance_default.region ? `, ${defaults.instance_default.region}` : ''}
          ). Saving creates an org-level config.
        </div>
      ) : null}

      <PresetPicker orgId={orgId} onPick={applyPreset} />

      <div className="grid grid-cols-[120px_1fr] items-center gap-2">
        <div className="text-muted-fg">Provider</div>
        <select
          value={provider}
          onChange={(e) => onProviderChange(e.target.value)}
          className={`${inputCls} max-w-56`}
        >
          {defaults.providers.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </div>

      {TIERS.map((t) => (
        <div key={t} className="grid grid-cols-[120px_1fr] items-center gap-2">
          <div className="capitalize text-muted-fg">{t}</div>
          <input
            value={tierMap[t]}
            onChange={(e) => setTierMap({ ...tierMap, [t]: e.target.value })}
            placeholder="model id"
            className={inputCls}
          />
        </div>
      ))}

      {REGION_PROVIDERS.has(provider) ? (
        <div className="grid grid-cols-[120px_1fr] items-center gap-2">
          <div className="text-muted-fg">Region</div>
          <input
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            placeholder="e.g. us-east-1"
            className={`${inputCls} max-w-56`}
          />
        </div>
      ) : null}
      {ENDPOINT_PROVIDERS.has(provider) ? (
        <div className="grid grid-cols-[120px_1fr] items-center gap-2">
          <div className="text-muted-fg">Endpoint</div>
          <input
            value={endpoint}
            onChange={(e) => setEndpoint(e.target.value)}
            placeholder="https://…"
            className={inputCls}
          />
        </div>
      ) : null}

      <div className="grid grid-cols-[120px_1fr] items-center gap-2">
        <div className="text-muted-fg">API key</div>
        <div className="flex items-center gap-2">
          <input
            type="password"
            autoComplete="off"
            value={keyInput}
            onChange={(e) => setKeyInput(e.target.value)}
            placeholder={saved?.has_key ? 'enter a new key to rotate' : 'org API key (BYOK)'}
            className={`${inputCls} flex-1`}
          />
          {saved?.has_key ? (
            <>
              <span className="whitespace-nowrap text-xs text-muted-fg">●●● key set</span>
              <button onClick={removeKey} disabled={busy} className={btnCls}>
                Remove key
              </button>
            </>
          ) : null}
        </div>
      </div>

      <div className="grid grid-cols-[120px_1fr] items-start gap-2">
        <div className="pt-1 text-muted-fg">
          Failover
          <div className="text-[10px]">tried in order on provider incidents</div>
        </div>
        <div className="space-y-1.5">
          {chain.map((e, i) => (
            <ChainEntryRow
              key={i}
              index={i}
              entry={e}
              providers={defaults.providers}
              onChange={(next) => setChain(chain.map((c, j) => (j === i ? next : c)))}
              onRemove={() => setChain(chain.filter((_, j) => j !== i))}
              onMove={(dir) => {
                const j = i + dir;
                if (j < 0 || j >= chain.length) return;
                const copy = [...chain];
                [copy[i], copy[j]] = [copy[j], copy[i]];
                setChain(copy);
              }}
            />
          ))}
          {chain.length < 3 ? (
            <button
              onClick={() =>
                setChain([...chain, {
                  provider: 'bedrock', endpoint: '', region: '',
                  tierMap: null, keyInput: '', hasKey: false,
                }])
              }
              className={btnCls}
            >
              + Add fallback
            </button>
          ) : null}
        </div>
      </div>

      <div className="flex items-center gap-2 pt-1">
        <button onClick={save} disabled={busy || !dirty} className={btnCls}>
          {busy ? 'Saving…' : 'Save'}
        </button>
        <button onClick={runTest} disabled={busy || test === 'testing'} className={btnCls}>
          Test
        </button>
        <TestChip state={test} />
        {dirty && !busy ? <span className="text-xs text-muted-fg">unsaved changes</span> : null}
        {error ? <span className="text-xs text-red-400">{error}</span> : null}
      </div>
    </div>
  );
}

function ChainEntryRow({
  index,
  entry,
  providers,
  onChange,
  onRemove,
  onMove,
}: {
  index: number;
  entry: ChainDraft;
  providers: string[];
  onChange: (e: ChainDraft) => void;
  onRemove: () => void;
  onMove: (dir: -1 | 1) => void;
}) {
  const isGateway = entry.provider === 'openai_compatible';
  const needsKey = KEYED_PROVIDERS.has(entry.provider) && !entry.hasKey;
  return (
    <div className="space-y-1 rounded border border-border p-2 text-xs">
      <div className="flex items-center gap-1.5">
        <span className="text-muted-fg">#{index + 1}</span>
        <select
          value={entry.provider}
          onChange={(e) =>
            onChange({
              ...entry,
              provider: e.target.value,
              hasKey: false,
              tierMap: e.target.value === 'openai_compatible'
                ? entry.tierMap ?? { premium: '', balanced: '', economy: '' }
                : entry.tierMap,
            })
          }
          className={inputCls}
        >
          {providers.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        {ENDPOINT_PROVIDERS.has(entry.provider) ? (
          <input
            value={entry.endpoint}
            onChange={(e) => onChange({ ...entry, endpoint: e.target.value })}
            placeholder="endpoint (base_url)"
            className={`${inputCls} flex-1`}
          />
        ) : null}
        {REGION_PROVIDERS.has(entry.provider) ? (
          <input
            value={entry.region}
            onChange={(e) => onChange({ ...entry, region: e.target.value })}
            placeholder="region"
            className={`${inputCls} w-24`}
          />
        ) : null}
        <input
          type="password"
          autoComplete="off"
          value={entry.keyInput}
          onChange={(e) => onChange({ ...entry, keyInput: e.target.value })}
          placeholder={entry.hasKey ? '●●● rotate' : needsKey ? 'key (required)' : 'key (optional)'}
          className={`${inputCls} w-28`}
        />
        <button onClick={() => onMove(-1)} className={btnCls} title="Move up">↑</button>
        <button onClick={() => onMove(1)} className={btnCls} title="Move down">↓</button>
        <button onClick={onRemove} className={btnCls} title="Remove">✕</button>
      </div>
      {isGateway && entry.tierMap ? (
        <div className="flex items-center gap-1.5 pl-6">
          {TIERS.map((t) => (
            <input
              key={t}
              value={entry.tierMap?.[t] ?? ''}
              onChange={(e) =>
                onChange({
                  ...entry,
                  tierMap: { ...(entry.tierMap ?? { premium: '', balanced: '', economy: '' }), [t]: e.target.value },
                })
              }
              placeholder={`${t} model`}
              className={`${inputCls} flex-1`}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

// ── Preset picker ───────────────────────────────────────────────────────────

function PresetPicker({ orgId, onPick }: { orgId: string; onPick: (p: Preset) => void }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const presets = useQuery({
    queryKey: ['admin', 'presets', orgId],
    queryFn: () => admin.listPresets(orgId),
    refetchOnWindowFocus: false,
    enabled: open,
  });

  const items = useMemo(() => {
    const all = presets.data?.presets ?? [];
    if (!q) return all;
    const n = q.toLowerCase();
    return all.filter(
      (p) =>
        p.id.toLowerCase().includes(n) ||
        p.label.toLowerCase().includes(n) ||
        p.tags.some((t) => t.toLowerCase().includes(n)),
    );
  }, [presets.data, q]);

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className={btnCls}>
        Start from a preset…
      </button>
    );
  }
  return (
    <div className="space-y-2 rounded border border-border p-3">
      <div className="flex items-center gap-2">
        <input
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search presets (openrouter, deepseek, vllm…)"
          className={`${inputCls} flex-1`}
        />
        <button onClick={() => setOpen(false)} className={btnCls}>
          Close
        </button>
      </div>
      {presets.isLoading ? (
        <div className="text-xs text-muted-fg">Loading catalog…</div>
      ) : (
        <div className="grid max-h-64 grid-cols-2 gap-2 overflow-y-auto">
          {items.map((p) => (
            <div key={p.id} className="rounded border border-border p-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium">{p.label}</span>
                <button
                  onClick={() => {
                    onPick(p);
                    setOpen(false);
                  }}
                  title={p.key_hint ? `Key: ${p.key_hint}` : undefined}
                  className={btnCls}
                >
                  Use
                </button>
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-1 text-[10px] text-muted-fg">
                <span>{p.provider}</span>
                {p.tags.map((t) => (
                  <span key={t} className="rounded bg-border/50 px-1">
                    {t}
                  </span>
                ))}
                {p.docs_url ? (
                  <a
                    href={p.docs_url}
                    target="_blank"
                    rel="noreferrer"
                    className="underline"
                  >
                    docs
                  </a>
                ) : null}
              </div>
            </div>
          ))}
          {items.length === 0 ? (
            <div className="col-span-2 text-xs text-muted-fg">No presets match.</div>
          ) : null}
        </div>
      )}
      {presets.data ? (
        <div className="text-[10px] text-muted-fg">
          Catalog {presets.data.catalog_version} — presets pre-fill the form; review, add your
          key, Test, then Save.
        </div>
      ) : null}
    </div>
  );
}

// ── History (versions + rollback) ───────────────────────────────────────────

function fmtDiff(d: { field: string; from: unknown; to: unknown }): string {
  if (typeof d.from === 'object' || typeof d.to === 'object') return `${d.field} changed`;
  return `${d.field}: ${d.from ?? '—'} → ${d.to ?? '—'}`;
}

function HistoryPanel({ orgId }: { orgId: string }) {
  const qc = useQueryClient();
  const versions = useQuery({
    queryKey: ['admin', 'modelVersions', orgId],
    queryFn: () => admin.listVersions(orgId, undefined, 20),
    refetchOnWindowFocus: false,
  });
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const rollback = async (v: ConfigVersion) => {
    const summary = v.diff.map(fmtDiff).join('\n') || '(no field changes)';
    if (!window.confirm(
      `Roll back "${v.scope}" to the state before this ${v.change_kind}?\n\nThis will undo:\n${summary}`))
      return;
    setBusy(v.id);
    setNotice(null);
    try {
      const r = await admin.rollbackVersion(orgId, v.id);
      setNotice(r.secret_requires_reentry
        ? 'Rolled back — the stored key could not be restored; re-enter it above.'
        : 'Rolled back.');
      await qc.invalidateQueries({ queryKey: ['admin'] });
    } catch (e) {
      setNotice(`Rollback failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const rows = versions.data?.versions ?? [];
  if (versions.isLoading) return <div className="text-xs text-muted-fg">Loading history…</div>;
  return (
    <div className="space-y-1.5 text-xs">
      {notice ? <div className="text-muted-fg">{notice}</div> : null}
      {rows.length === 0 ? (
        <div className="text-muted-fg">
          No changes recorded yet — history starts with the next edit.
        </div>
      ) : null}
      {rows.map((v) => (
        <div key={v.id} className="flex items-center gap-2 rounded border border-border px-2 py-1.5">
          <span className="whitespace-nowrap text-muted-fg">
            {new Date(v.created_at).toLocaleString()}
          </span>
          <span className="rounded bg-border/50 px-1 capitalize">{v.scope}</span>
          <span className="text-muted-fg">{v.change_kind}</span>
          {v.actor_label ? <span className="text-muted-fg">by {v.actor_label}</span> : null}
          <span className="flex-1 truncate" title={v.diff.map(fmtDiff).join(' · ')}>
            {v.diff.slice(0, 3).map(fmtDiff).join(' · ') || '—'}
            {v.diff.length > 3 ? ` · +${v.diff.length - 3} more` : ''}
          </span>
          <button onClick={() => rollback(v)} disabled={busy !== null} className={btnCls}>
            {busy === v.id ? 'Rolling back…' : 'Rollback'}
          </button>
        </div>
      ))}
    </div>
  );
}

// ── Export / import ─────────────────────────────────────────────────────────

function ExportImportPanel({ orgId }: { orgId: string }) {
  const qc = useQueryClient();
  const [importOpen, setImportOpen] = useState(false);
  const [docText, setDocText] = useState('');
  const [strategy, setStrategy] = useState<'merge' | 'replace'>('merge');
  const [plan, setPlan] = useState<ImportPlanItem[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const exportNow = async () => {
    setBusy(true);
    try {
      const doc = await admin.exportModels(orgId);
      const blob = new Blob([JSON.stringify(doc, null, 2)], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'pdlcflow-models-export.json';
      a.click();
      URL.revokeObjectURL(a.href);
    } finally {
      setBusy(false);
    }
  };

  const parseDoc = (): object | null => {
    try {
      return JSON.parse(docText) as object;
    } catch {
      setMsg('Not valid JSON.');
      return null;
    }
  };

  const dryRun = async () => {
    const doc = parseDoc();
    if (!doc) return;
    setBusy(true);
    setMsg(null);
    try {
      const r = await admin.importModels(orgId, doc, { dryRun: true, strategy });
      setPlan(r.plan);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const apply = async () => {
    const doc = parseDoc();
    if (!doc) return;
    if (!window.confirm(`Apply this import (strategy: ${strategy})? This overwrites current config.`)) return;
    setBusy(true);
    setMsg(null);
    try {
      const r = await admin.importModels(orgId, doc, { strategy });
      setMsg(`Imported — ${r.applied} item(s) applied. Re-enter any required keys above.`);
      setPlan(r.plan);
      await qc.invalidateQueries({ queryKey: ['admin'] });
    } catch (e) {
      setMsg(`Import failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2 text-xs">
      <div className="flex items-center gap-2">
        <button onClick={exportNow} disabled={busy} className={btnCls}>
          Export provider set (JSON)
        </button>
        <button onClick={() => setImportOpen(!importOpen)} className={btnCls}>
          {importOpen ? 'Hide import' : 'Import…'}
        </button>
        <span className="text-muted-fg">
          Exports never contain API keys — re-enter them on the target org.
        </span>
      </div>
      {importOpen ? (
        <div className="space-y-2">
          <textarea
            value={docText}
            onChange={(e) => {
              setDocText(e.target.value);
              setPlan(null);
            }}
            placeholder="Paste an exported provider-set JSON document"
            rows={6}
            className={`${inputCls} w-full font-mono`}
          />
          <div className="flex items-center gap-2">
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value as 'merge' | 'replace')}
              className={inputCls}
            >
              <option value="merge">merge (upsert items in the document)</option>
              <option value="replace">replace (also drop rows absent from it)</option>
            </select>
            <button onClick={dryRun} disabled={busy || !docText} className={btnCls}>
              Dry-run
            </button>
            <button
              onClick={apply}
              disabled={busy || !plan || plan.some((p) => p.action === 'error')}
              className={btnCls}
              title={!plan ? 'Dry-run first' : undefined}
            >
              Apply
            </button>
          </div>
          {plan ? (
            <div className="space-y-1">
              {plan.map((p) => (
                <div key={p.scope} className="flex items-center gap-2">
                  <span className="rounded bg-border/50 px-1 capitalize">{p.scope}</span>
                  <span className={p.action === 'error' ? 'text-red-400' : 'text-muted-fg'}>
                    {p.action}
                  </span>
                  <span className="text-muted-fg">secret: {p.secret}</span>
                  {p.reasons.length ? (
                    <span className="truncate text-red-400" title={p.reasons.join(' · ')}>
                      {p.reasons[0]}
                    </span>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
      {msg ? <div className="text-muted-fg">{msg}</div> : null}
    </div>
  );
}

// ── Per-agent overrides ─────────────────────────────────────────────────────

function PersonaRow({
  orgId,
  persona,
  defaults,
  saved,
}: {
  orgId: string;
  persona: string;
  defaults: ModelDefaults;
  saved: AgentOverride | undefined;
}) {
  const qc = useQueryClient();
  const disabled = persona === 'sentinel';
  const [provider, setProvider] = useState(saved?.provider ?? '');
  const [modelId, setModelId] = useState(saved?.model_id ?? '');
  const [keyInput, setKeyInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [test, setTest] = useState<TestState>('idle');

  const dirty = !disabled && (
    Boolean(keyInput) ||
    provider !== (saved?.provider ?? '') ||
    modelId !== (saved?.model_id ?? '')
  );
  useDirtyGuard(dirty);

  const refresh = async () => {
    await qc.invalidateQueries({ queryKey: ['admin', 'agentOverrides', orgId] });
    await qc.invalidateQueries({ queryKey: ['admin', 'modelVersions', orgId] });
  };

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await admin.putAgentOverride(orgId, persona, {
        agent_persona: persona,
        provider,
        model_id: modelId,
        ...(keyInput ? { api_key: keyInput } : {}),
      });
      setKeyInput('');
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const clear = async () => {
    if (!window.confirm(`Clear the ${persona} override? It returns to the org default.`)) return;
    setBusy(true);
    try {
      await admin.deleteAgentOverride(orgId, persona);
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const runTest = async () => {
    setTest('testing');
    const body: ProbeBody =
      !keyInput && !dirty && saved
        ? { scope: `agent:${persona}`, use_saved_key: true }
        : {
            provider,
            model_id: modelId || undefined,
            ...(keyInput ? { api_key: keyInput } : {}),
          };
    try {
      setTest(await admin.testProvider(orgId, body));
    } catch (e) {
      setTest(probeFailure(e));
    }
  };

  const inherit = provider === '';

  return (
    <div className="grid grid-cols-[110px_150px_1fr_190px] items-center gap-2 text-sm">
      <div className="capitalize text-muted-fg">
        {persona}
        {saved && !disabled ? <span className="ml-1 text-xs text-fg">•</span> : null}
      </div>
      <select
        disabled={disabled || busy}
        value={provider}
        onChange={(e) => {
          setProvider(e.target.value);
          setTest('idle');
        }}
        className={inputCls}
      >
        <option value="">— inherit —</option>
        {defaults.providers.map((p) => (
          <option key={p} value={p}>
            {p}
          </option>
        ))}
      </select>
      <div className="flex items-center gap-2">
        <input
          disabled={disabled || busy || inherit}
          value={modelId}
          onChange={(e) => setModelId(e.target.value)}
          placeholder={disabled ? 'N/A — deterministic Python' : inherit ? 'inherits org default' : 'model id'}
          className={`${inputCls} flex-1`}
        />
        {!disabled && !inherit ? (
          <input
            type="password"
            autoComplete="off"
            value={keyInput}
            onChange={(e) => setKeyInput(e.target.value)}
            placeholder={saved?.has_key ? '●●● rotate key' : 'key (optional)'}
            title={saved?.has_key ? 'A key is stored for this override' : 'Inherits the org key when providers match'}
            className={`${inputCls} w-36`}
          />
        ) : null}
      </div>
      <div className="flex items-center justify-end gap-1.5">
        <TestChip state={test} />
        {error ? (
          <span className="max-w-40 truncate text-xs text-red-400" title={error}>
            {error}
          </span>
        ) : null}
        <button
          disabled={disabled || busy || inherit || !modelId || !dirty}
          onClick={save}
          className={btnCls}
        >
          Save
        </button>
        <button
          disabled={disabled || busy || inherit || test === 'testing' || !modelId}
          onClick={runTest}
          className={btnCls}
        >
          Test
        </button>
        <button disabled={disabled || busy || !saved} onClick={clear} className={btnCls}>
          Clear
        </button>
      </div>
    </div>
  );
}
