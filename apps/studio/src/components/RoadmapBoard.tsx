// Task board for the active project — the bd-NN tasks grouped by status. Was a
// static "No tasks yet." placeholder (T3-6); now fed by GET /projects/{id}/tasks.
// Compact (sidebar-friendly): a grouped list rather than a wide kanban.

import { useQuery } from '@tanstack/react-query';

import { entities, type ProjectTask } from '@/lib/api';
import { useThread } from '@/store/useThread';

const GROUPS: { key: string; label: string; match: (s: string) => boolean }[] = [
  { key: 'done', label: 'Done', match: (s) => s === 'done' || s === 'complete' },
  { key: 'in-progress', label: 'In progress', match: (s) => s === 'claimed' || s === 'in-progress' },
  { key: 'blocked', label: 'Blocked', match: (s) => s === 'blocked' },
  {
    key: 'backlog',
    label: 'Backlog',
    match: (s) => !['done', 'complete', 'claimed', 'in-progress', 'blocked'].includes(s),
  },
];

export function RoadmapBoard() {
  const orgId = useThread((s) => s.orgId);
  const projectId = useThread((s) => s.projectId);
  const q = useQuery({
    queryKey: ['projectTasks', orgId, projectId],
    queryFn: () => entities.projectTasks(orgId, projectId),
    enabled: Boolean(projectId),
    refetchOnWindowFocus: false,
  });

  const tasks = q.data?.tasks ?? [];
  if (!projectId) return null;

  return (
    <div className="rounded-xl border border-border p-3 text-sm">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs uppercase tracking-wide text-muted-fg">Tasks</span>
        <span className="text-[10px] text-muted-fg">{tasks.length}</span>
      </div>
      {q.isLoading ? (
        <p className="text-xs text-muted-fg">Loading…</p>
      ) : tasks.length === 0 ? (
        <p className="text-xs text-muted-fg">
          No tasks yet — Plan decomposes the feature into bd-NN tasks.
        </p>
      ) : (
        <div className="space-y-2">
          {GROUPS.map((g) => {
            const rows = tasks.filter((t: ProjectTask) => g.match(t.status));
            if (rows.length === 0) return null;
            return (
              <div key={g.key}>
                <div className="mb-0.5 text-[10px] uppercase tracking-wide text-muted-fg">
                  {g.label} · {rows.length}
                </div>
                <ul className="space-y-0.5">
                  {rows.map((t) => (
                    <li key={t.external_id} className="flex items-center gap-1.5 text-[11px]">
                      <span className="font-mono text-muted-fg">{t.external_id}</span>
                      <span className="truncate" title={t.title}>
                        {t.title}
                      </span>
                      {t.claimed_by ? (
                        <span className="ml-auto shrink-0 text-[10px] text-muted-fg">
                          @{t.claimed_by}
                        </span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
