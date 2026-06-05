// Beads-replacement kanban: backlog / in-progress / blocked / done. Stub.

const COLUMNS = ['backlog', 'in-progress', 'blocked', 'done'] as const;

export function RoadmapBoard() {
  return (
    <div className="grid grid-cols-4 gap-3">
      {COLUMNS.map((c) => (
        <div key={c} className="rounded-xl border border-border p-2">
          <div className="mb-2 text-xs uppercase tracking-wide text-muted-fg">{c}</div>
          <div className="space-y-2 text-sm text-muted-fg">No tasks yet.</div>
        </div>
      ))}
    </div>
  );
}
