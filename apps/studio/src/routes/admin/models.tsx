// Models settings — org default LLM provider + per-agent overrides, wired to
// /v1/admin/models/*. Key entry is write-only (the UI only ever learns
// `has_key`); Test probes the row's CURRENT draft via POST /admin/models/test
// before anything is saved.

import { useEffect, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import {
  admin,
  type AgentOverride,
  type ModelDefaults,
  type OrgDefault,
  type ProbeBody,
  type TestResult,
  type TierName,
} from '@/lib/api';
import { useThread } from '@/store/useThread';
import { ErrorNotice, Loading, PageHeader } from './_shared';

const TIERS: TierName[] = ['premium', 'balanced', 'economy'];
const REGION_PROVIDERS = new Set(['bedrock', 'vertex', 'azure']);
const ENDPOINT_PROVIDERS = new Set(['ollama', 'azure']);

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

      <section className="rounded-xl border border-border p-4">
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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [test, setTest] = useState<TestState>('idle');

  const dirty = useMemo(() => {
    if (keyInput) return true;
    if (!saved) return true; // nothing saved yet — saving creates the org row
    return (
      provider !== saved.provider ||
      TIERS.some((t) => tierMap[t] !== saved.tier_map[t]) ||
      (region || null) !== saved.region ||
      (endpoint || null) !== saved.endpoint
    );
  }, [saved, provider, tierMap, region, endpoint, keyInput]);
  useDirtyGuard(dirty);

  const onProviderChange = (p: string) => {
    setProvider(p);
    // Switching providers invalidates the old model ids — prefill the
    // provider's defaults (still editable afterwards).
    setTierMap(defaults.tier_maps[p] ?? { premium: '', balanced: '', economy: '' });
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
      await admin.putOrgDefault(orgId, {
        provider,
        tier_map: tierMap,
        region: region || null,
        endpoint: endpoint || null,
        ...(keyInput ? { api_key: keyInput } : {}),
      });
      setKeyInput('');
      await qc.invalidateQueries({ queryKey: ['admin', 'orgDefault', orgId] });
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

  const refresh = () => qc.invalidateQueries({ queryKey: ['admin', 'agentOverrides', orgId] });

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
