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

import { admin } from '@/lib/api';
import { useThread } from '@/store/useThread';
import { ErrorNotice, Loading, PageHeader, RollupTable, StateNotice } from './_shared';

export function AdminInitiatives() {
  const orgId = useThread((s) => s.orgId);
  const q = useQuery({
    queryKey: ['admin', 'initiatives', orgId],
    queryFn: () => admin.initiativesRollup(orgId),
  });

  const rows = q.data?.rows ?? [];

  return (
    <div>
      <PageHeader
        title="Initiatives"
        subtitle="Spend, events, and per-initiative agent token usage."
      />
      {q.isLoading ? (
        <Loading />
      ) : q.isError ? (
        <ErrorNotice error={q.error} />
      ) : rows.length === 0 ? (
        <StateNotice>No initiative activity recorded for this org yet.</StateNotice>
      ) : (
        <div className="space-y-4">
          <div className="rounded-xl border border-border p-4">
            <div className="mb-3 text-xs uppercase tracking-wide text-muted-fg">
              Events per initiative
            </div>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={rows}>
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
                <Bar dataKey="events" fill="var(--accent)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <RollupTable rows={rows} keyLabel="Initiative" />
        </div>
      )}
    </div>
  );
}
