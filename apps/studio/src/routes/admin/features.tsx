import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';

import { admin } from '@/lib/api';
import { useThread } from '@/store/useThread';
import { ErrorNotice, Loading, PageHeader, StateNotice } from './_shared';

export function AdminFeatures() {
  const { f } = useParams<{ f: string }>();
  const orgId = useThread((s) => s.orgId);

  const q = useQuery({
    queryKey: ['admin', 'feature-timeline', orgId, f],
    queryFn: () => admin.featureTimeline(orgId, f!),
    enabled: Boolean(f),
  });

  if (!f) {
    return (
      <div>
        <PageHeader title="Feature time-travel" />
        <StateNotice>
          Pick a feature to replay its full event history. Open
          <code className="mx-1 rounded bg-border/60 px-1 py-0.5 text-xs">/admin/features/F-NNN</code>
          to view one.
        </StateNotice>
      </div>
    );
  }

  const events = q.data?.events ?? [];

  return (
    <div>
      <PageHeader
        title={`Feature ${f} — time-travel`}
        subtitle="Every event for this roadmap in chronological order."
      />
      {q.isLoading ? (
        <Loading />
      ) : q.isError ? (
        <ErrorNotice error={q.error} />
      ) : events.length === 0 ? (
        <StateNotice>No events recorded for {f}.</StateNotice>
      ) : (
        <ol className="relative space-y-0 border-l border-border pl-5">
          {events.map((e, i) => (
            <li key={`${e.ts}-${i}`} className="relative pb-4">
              <span className="absolute -left-[1.4rem] top-1.5 h-2 w-2 rounded-full bg-accent" />
              <div className="flex items-center gap-2 text-sm">
                <span className="font-medium">{e.event_type}</span>
                {e.actor ? <span className="text-muted-fg">· {e.actor}</span> : null}
              </div>
              <div className="text-xs text-muted-fg">{e.ts}</div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
