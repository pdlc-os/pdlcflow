import { useQuery } from '@tanstack/react-query';

import { admin } from '@/lib/api';
import { useThread } from '@/store/useThread';
import { ErrorNotice, Loading, PageHeader, RollupTable, StateNotice } from './_shared';

export function AdminDomains() {
  const orgId = useThread((s) => s.orgId);
  const q = useQuery({
    queryKey: ['admin', 'domains', orgId],
    queryFn: () => admin.domainsRollup(orgId),
  });

  const rows = q.data?.rows ?? [];

  return (
    <div>
      <PageHeader title="Domains" subtitle="Cross-cutting domain rollups." />
      {q.isLoading ? (
        <Loading />
      ) : q.isError ? (
        <ErrorNotice error={q.error} />
      ) : rows.length === 0 ? (
        <StateNotice>No domain activity recorded for this org yet.</StateNotice>
      ) : (
        <RollupTable rows={rows} keyLabel="Domain" />
      )}
    </div>
  );
}
