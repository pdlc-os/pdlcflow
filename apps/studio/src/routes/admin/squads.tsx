import { useQuery } from '@tanstack/react-query';

import { admin } from '@/lib/api';
import { useThread } from '@/store/useThread';
import { ErrorNotice, Loading, PageHeader, RollupTable, StateNotice } from './_shared';

export function AdminSquads() {
  const orgId = useThread((s) => s.orgId);
  const q = useQuery({
    queryKey: ['admin', 'squads', orgId],
    queryFn: () => admin.squadsScoreboard(orgId),
  });

  const rows = q.data?.rows ?? [];

  return (
    <div>
      <PageHeader title="Squads" subtitle="Per-squad scoreboard." />
      {q.isLoading ? (
        <Loading />
      ) : q.isError ? (
        <ErrorNotice error={q.error} />
      ) : rows.length === 0 ? (
        <StateNotice>No squad activity recorded for this org yet.</StateNotice>
      ) : (
        <RollupTable rows={rows} keyLabel="Squad" />
      )}
    </div>
  );
}
