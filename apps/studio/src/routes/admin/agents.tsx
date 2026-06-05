import { useQuery } from '@tanstack/react-query';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { admin, type RollupRow } from '@/lib/api';
import { useThread } from '@/store/useThread';
import { ErrorNotice, fmtInt, fmtUsd, Loading, PageHeader } from './_shared';

export function AdminAgents() {
  const orgId = useThread((s) => s.orgId);
  const q = useQuery({
    queryKey: ['admin', 'agents', orgId],
    queryFn: () => admin.agentsHeatmap(orgId),
  });

  if (q.isLoading) return <Wrap>{<Loading />}</Wrap>;
  if (q.isError) return <Wrap>{<ErrorNotice error={q.error} />}</Wrap>;

  const personas = q.data?.personas ?? [];
  const cells = q.data?.cells ?? [];
  const byKey = new Map<string, RollupRow>(cells.map((c) => [c.key, c]));

  // Always show all 10 personas; zero-fill any without recorded activity.
  const chartData = personas.map((p) => ({
    key: p,
    events: byKey.get(p)?.events ?? 0,
    tokens: byKey.get(p)?.tokens ?? 0,
  }));
  const hasActivity = cells.length > 0;

  return (
    <Wrap>
      <div className="rounded-xl border border-border p-4">
        <div className="mb-3 text-xs uppercase tracking-wide text-muted-fg">
          Tokens per agent persona
        </div>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis dataKey="key" tick={{ fontSize: 12, fill: 'var(--muted-fg)' }} />
            <YAxis tick={{ fontSize: 12, fill: 'var(--muted-fg)' }} />
            <Tooltip
              contentStyle={{
                background: 'var(--bg)',
                border: '1px solid var(--border)',
                borderRadius: 8,
                fontSize: 12,
              }}
            />
            <Bar dataKey="tokens" fill="var(--accent)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {!hasActivity ? (
        <p className="mt-3 text-xs text-muted-fg">
          No agent activity recorded for this org yet — showing the persona roster.
        </p>
      ) : null}

      <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-5">
        {personas.map((p) => {
          const cell = byKey.get(p);
          return (
            <div key={p} className="rounded-xl border border-border p-3 text-sm">
              <div className="font-medium capitalize">{p}</div>
              <div className="mt-1 text-xs text-muted-fg">
                {cell
                  ? `${fmtInt(cell.events)} ev · ${fmtInt(cell.tokens)} tok · ${fmtUsd(cell.usd)}`
                  : 'no activity'}
              </div>
            </div>
          );
        })}
      </div>
    </Wrap>
  );
}

function Wrap({ children }: { children: React.ReactNode }) {
  return (
    <div>
      <PageHeader title="Agents" subtitle="Per-persona usage heatmap (events · tokens · spend)." />
      {children}
    </div>
  );
}
