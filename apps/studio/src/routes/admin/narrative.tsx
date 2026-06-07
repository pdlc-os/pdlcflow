import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { admin } from '@/lib/api';
import { useThread } from '@/store/useThread';
import { ErrorNotice, Loading, PageHeader, StateNotice } from './_shared';

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

export function AdminNarrative() {
  const orgId = useThread((s) => s.orgId);
  const [from, setFrom] = useState(isoDaysAgo(7));
  const [to, setTo] = useState(isoDaysAgo(0));
  const [range, setRange] = useState<{ from: string; to: string } | null>(null);

  const q = useQuery({
    queryKey: ['admin', 'narrative', orgId, range?.from, range?.to],
    queryFn: () => admin.narrative(orgId, { from: range!.from, to: `${range!.to}T23:59:59Z` }),
    enabled: !!orgId && !!range,
  });

  const s = q.data?.summary;
  const at = s?.by_actor_type;

  return (
    <div>
      <PageHeader
        title="Work Narrative"
        subtitle="A narrative + stats of work done by humans (Studio) and agents (pdlc-graph) over a date window."
      />

      <div className="mb-4 flex flex-wrap items-end gap-3 text-sm">
        <label className="flex flex-col gap-1">
          <span className="text-muted-fg">From</span>
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)}
            className="rounded-md border border-border bg-bg px-2 py-1" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-muted-fg">To</span>
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)}
            className="rounded-md border border-border bg-bg px-2 py-1" />
        </label>
        <button
          onClick={() => setRange({ from, to })}
          disabled={!orgId}
          className="rounded-md bg-accent px-3 py-1.5 font-medium text-accent-fg disabled:opacity-50"
        >
          Generate narrative
        </button>
      </div>

      {!orgId ? (
        <StateNotice>Select an org to generate a work narrative.</StateNotice>
      ) : !range ? (
        <StateNotice>Pick a date window and click “Generate narrative”.</StateNotice>
      ) : q.isLoading ? (
        <Loading />
      ) : q.isError ? (
        <ErrorNotice error={q.error} />
      ) : !s ? null : (
        <div className="space-y-5">
          {/* Stat cards */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Human actions" value={at?.human ?? 0} />
            <Stat label="Agent actions" value={at?.agent ?? 0} />
            <Stat label="System events" value={at?.system ?? 0} />
            <Stat label="Tokens" value={s.tokens.toLocaleString()} />
          </div>

          {/* Narrative */}
          <section className="rounded-lg border border-border p-4">
            <h3 className="mb-2 text-sm font-semibold text-muted-fg">Narrative</h3>
            <p className="whitespace-pre-wrap text-sm leading-relaxed">{q.data?.narrative}</p>
          </section>

          {/* Per-agent breakdown */}
          {Object.keys(s.by_agent).length > 0 && (
            <section className="rounded-lg border border-border p-4">
              <h3 className="mb-2 text-sm font-semibold text-muted-fg">By agent</h3>
              <table className="w-full text-sm">
                <thead className="text-left text-muted-fg">
                  <tr><th className="py-1">Agent</th><th>Actions</th><th>Tokens</th></tr>
                </thead>
                <tbody>
                  {Object.entries(s.by_agent).map(([name, g]) => (
                    <tr key={name} className="border-t border-border/60">
                      <td className="py-1 font-medium">{name}</td>
                      <td>{g.events}</td>
                      <td>{g.tokens.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg border border-border p-3">
      <div className="text-xs text-muted-fg">{label}</div>
      <div className="text-xl font-semibold">{value}</div>
    </div>
  );
}
