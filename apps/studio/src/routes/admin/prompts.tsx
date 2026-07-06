// Persona prompt overrides (PRD-10): edit any LLM persona's soul-spec for this
// org, with immutable versions, explicit activation (deactivate = back to the
// packaged default), and prompt-pack export/import (imports land as drafts).

import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { admin, type PromptSummary } from '@/lib/api';
import { useThread } from '@/store/useThread';
import { ErrorNotice, Loading, PageHeader } from './_shared';

const inputCls = 'rounded border border-border bg-bg px-2 py-1';
const btnCls =
  'rounded border border-border px-2 py-1 text-xs text-muted-fg hover:bg-border/60 disabled:opacity-40';

export function AdminPrompts() {
  const orgId = useThread((s) => s.orgId);
  const [selected, setSelected] = useState<string | null>(null);
  const list = useQuery({
    queryKey: ['admin', 'prompts', orgId],
    queryFn: () => admin.listPersonaPrompts(orgId),
    refetchOnWindowFocus: false,
  });

  if (list.isLoading) return <Loading />;
  if (list.isError) return <ErrorNotice error={list.error} />;
  const personas = list.data?.personas ?? [];

  return (
    <div className="max-w-4xl">
      <PageHeader
        title="Prompts"
        subtitle={
          <>
            Override any persona's soul-spec for this org. Versions are immutable — activate
            to switch, deactivate to return to the packaged default. Sentinel is a
            deterministic Python evaluator and has no prompt to override.
          </>
        }
      />

      <div className="mb-4 grid grid-cols-3 gap-2 text-sm">
        {personas.map((p) => (
          <PersonaCard
            key={p.persona}
            summary={p}
            selected={selected === p.persona}
            onSelect={() => setSelected(selected === p.persona ? null : p.persona)}
          />
        ))}
      </div>

      {selected ? (
        <PersonaEditor key={`${selected}:${orgId}`} orgId={orgId} persona={selected} />
      ) : (
        <div className="mb-4 rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted-fg">
          Select a persona to view or edit its prompt.
        </div>
      )}

      <section className="rounded-xl border border-border p-4">
        <h3 className="mb-2 text-sm font-medium">Prompt packs</h3>
        <PackPanel orgId={orgId} />
      </section>
    </div>
  );
}

function PersonaCard({
  summary,
  selected,
  onSelect,
}: {
  summary: PromptSummary;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      className={`rounded-xl border p-3 text-left ${
        selected ? 'border-accent' : 'border-border hover:bg-border/30'
      }`}
    >
      <div className="flex items-center justify-between">
        <span className="font-medium capitalize">{summary.persona}</span>
        {summary.overridden ? (
          <span className="rounded bg-green-500/20 px-1 text-[10px] text-green-500">
            override v{summary.active_version}
          </span>
        ) : (
          <span className="text-[10px] text-muted-fg">packaged</span>
        )}
      </div>
      <div className="mt-1 text-[10px] text-muted-fg">
        {summary.versions} version{summary.versions === 1 ? '' : 's'}
      </div>
    </button>
  );
}

function PersonaEditor({ orgId, persona }: { orgId: string; persona: string }) {
  const qc = useQueryClient();
  const detail = useQuery({
    queryKey: ['admin', 'promptDetail', orgId, persona],
    queryFn: () => admin.getPersonaPrompt(orgId, persona),
    refetchOnWindowFocus: false,
  });
  const [draft, setDraft] = useState<string | null>(null); // null = not editing
  const [viewing, setViewing] = useState<{ version: number; body: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const refresh = async () => {
    await qc.invalidateQueries({ queryKey: ['admin', 'prompts', orgId] });
    await qc.invalidateQueries({ queryKey: ['admin', 'promptDetail', orgId, persona] });
  };

  const saveDraft = async () => {
    if (!draft?.trim()) return;
    setBusy(true);
    setMsg(null);
    try {
      const r = await admin.createPromptDraft(orgId, persona, draft);
      setMsg(`Draft v${r.version} created — activate it to take effect.`);
      setDraft(null);
      await refresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const activate = async (version: number) => {
    if (
      !window.confirm(
        `Activate ${persona} v${version}? Every new turn uses it as ${persona}'s identity.`,
      )
    )
      return;
    setBusy(true);
    try {
      await admin.activatePromptVersion(orgId, persona, version);
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const deactivate = async () => {
    if (!window.confirm(`Deactivate the override? ${persona} returns to the packaged spec.`))
      return;
    setBusy(true);
    try {
      await admin.deactivatePrompt(orgId, persona);
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const view = async (version: number) => {
    const v = await admin.getPromptVersion(orgId, persona, version);
    setViewing({ version: v.version, body: v.body });
  };

  if (detail.isLoading || !detail.data) return <Loading />;
  const d = detail.data;
  const active = d.versions.find((v) => v.status === 'active');

  return (
    <div className="mb-4 space-y-3 rounded-xl border border-border p-4 text-sm">
      <div className="flex items-center gap-2">
        <span className="font-medium capitalize">{persona}</span>
        {active ? (
          <>
            <span className="rounded bg-green-500/20 px-1 text-[10px] text-green-500">
              v{active.version} active
            </span>
            <button onClick={deactivate} disabled={busy} className={btnCls}>
              Deactivate (use packaged)
            </button>
          </>
        ) : (
          <span className="text-[10px] text-muted-fg">using packaged spec</span>
        )}
        <button
          onClick={() => {
            setDraft(viewing?.body ?? d.packaged_default);
            setMsg(null);
          }}
          disabled={busy}
          className={btnCls}
        >
          New draft{viewing ? ` (from v${viewing.version})` : ' (from packaged)'}
        </button>
      </div>

      {draft !== null ? (
        <div className="space-y-1.5">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={14}
            className={`${inputCls} w-full font-mono text-xs`}
          />
          <div className="flex items-center gap-2">
            <button onClick={saveDraft} disabled={busy || !draft.trim()} className={btnCls}>
              Save as new draft
            </button>
            <button onClick={() => setDraft(null)} className={btnCls}>
              Cancel
            </button>
            <span className="text-[10px] text-muted-fg">Max 32 KiB. Plain text — no templating.</span>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-fg">
              Packaged default
            </div>
            <pre className="max-h-64 overflow-auto rounded border border-border p-2 text-[11px]">
              {d.packaged_default}
            </pre>
          </div>
          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-fg">
              {viewing ? `Version v${viewing.version}` : 'Versions'}
            </div>
            {viewing ? (
              <pre className="max-h-64 overflow-auto rounded border border-border p-2 text-[11px]">
                {viewing.body}
              </pre>
            ) : (
              <div className="space-y-1">
                {d.versions.length === 0 ? (
                  <div className="text-xs text-muted-fg">No org versions yet.</div>
                ) : null}
                {d.versions.map((v) => (
                  <div key={v.version} className="flex items-center gap-2 text-xs">
                    <span>v{v.version}</span>
                    <span
                      className={
                        v.status === 'active' ? 'text-green-500' : 'text-muted-fg'
                      }
                    >
                      {v.status}
                    </span>
                    <span className="text-muted-fg">
                      {new Date(v.created_at).toLocaleString()}
                    </span>
                    <button onClick={() => view(v.version)} className={btnCls}>
                      View
                    </button>
                    {v.status !== 'active' ? (
                      <button
                        onClick={() => activate(v.version)}
                        disabled={busy}
                        className={btnCls}
                      >
                        Activate
                      </button>
                    ) : null}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
      {viewing && draft === null ? (
        <button onClick={() => setViewing(null)} className={btnCls}>
          Back to version list
        </button>
      ) : null}
      {msg ? <div className="text-xs text-muted-fg">{msg}</div> : null}
    </div>
  );
}

function PackPanel({ orgId }: { orgId: string }) {
  const qc = useQueryClient();
  const [packText, setPackText] = useState('');
  const [plan, setPlan] = useState<Record<string, string> | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const exportPack = async () => {
    const pack = await admin.exportPromptPack(orgId);
    const blob = new Blob([JSON.stringify(pack, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'pdlcflow-prompt-pack.json';
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const run = async (dryRun: boolean) => {
    setBusy(true);
    setMsg(null);
    try {
      const pack = JSON.parse(packText) as object;
      const r = await admin.importPromptPack(orgId, pack, dryRun);
      if (dryRun) {
        setPlan(r.plan ?? null);
      } else {
        setMsg(`Imported as drafts: ${Object.keys(r.created ?? {}).join(', ')} — activate per persona.`);
        setPlan(null);
        await qc.invalidateQueries({ queryKey: ['admin', 'prompts', orgId] });
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2 text-xs">
      <div className="flex items-center gap-2">
        <button onClick={exportPack} className={btnCls}>
          Export active overrides (JSON)
        </button>
        <span className="text-muted-fg">
          Packs contain plain prompt text — no secrets, no org identifiers. Imports always
          land as drafts.
        </span>
      </div>
      <textarea
        value={packText}
        onChange={(e) => {
          setPackText(e.target.value);
          setPlan(null);
        }}
        placeholder="Paste a prompt-pack JSON to import"
        rows={4}
        className={`${inputCls} w-full font-mono`}
      />
      <div className="flex items-center gap-2">
        <button onClick={() => run(true)} disabled={busy || !packText} className={btnCls}>
          Dry-run
        </button>
        <button
          onClick={() => run(false)}
          disabled={busy || !plan || Object.values(plan).some((v) => v.startsWith('error'))}
          className={btnCls}
          title={!plan ? 'Dry-run first' : undefined}
        >
          Import as drafts
        </button>
      </div>
      {plan ? (
        <div className="space-y-0.5">
          {Object.entries(plan).map(([p, v]) => (
            <div key={p}>
              <span className="capitalize">{p}</span>:{' '}
              <span className={v.startsWith('error') ? 'text-red-400' : 'text-muted-fg'}>{v}</span>
            </div>
          ))}
        </div>
      ) : null}
      {msg ? <div className="text-muted-fg">{msg}</div> : null}
    </div>
  );
}
