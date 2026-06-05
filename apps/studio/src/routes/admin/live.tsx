import { useQuery } from '@tanstack/react-query';

import { admin } from '@/lib/api';
import { useThread } from '@/store/useThread';
import { ErrorNotice, Loading, PageHeader, StateNotice } from './_shared';

export function AdminLive() {
  const orgId = useThread((s) => s.orgId);
  const q = useQuery({
    queryKey: ['admin', 'live', orgId],
    queryFn: () => admin.live(orgId, 50),
    refetchInterval: 5000,
  });

  return (
    <div>
      <PageHeader
        title="Live"
        subtitle="Most-recent events across every squad in the org. Auto-refreshes every 5s."
      />
      {q.isLoading ? (
        <Loading />
      ) : q.isError ? (
        <ErrorNotice error={q.error} />
      ) : !q.data || q.data.events.length === 0 ? (
        <StateNotice>No events yet for this org.</StateNotice>
      ) : (
        <ul className="space-y-1.5">
          {q.data.events.map((e, i) => (
            <li
              key={`${e.ts}-${i}`}
              className="flex items-center gap-3 rounded-lg border border-border px-3 py-2 text-sm"
            >
              <span className="rounded bg-accent/15 px-2 py-0.5 text-xs font-medium text-accent">
                {e.event_type}
              </span>
              {e.roadmap_id ? <span className="font-medium">{e.roadmap_id}</span> : null}
              {e.actor ? <span className="text-muted-fg">{e.actor}</span> : null}
              <span className="ml-auto text-xs text-muted-fg">{e.ts}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
