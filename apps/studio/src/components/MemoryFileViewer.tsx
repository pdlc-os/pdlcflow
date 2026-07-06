// Read-only memory-file inspector — lists the active project's stored artifacts
// (PRD, design docs, decisions, deployments, uploads, migrated memory…) and
// shows their content on click. Was a static "lands in Phase B" mockup (T3-4).

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { entities } from '@/lib/api';
import { useThread } from '@/store/useThread';

export function MemoryFileViewer() {
  const orgId = useThread((s) => s.orgId);
  const projectId = useThread((s) => s.projectId);
  const [selected, setSelected] = useState<string | null>(null);

  const list = useQuery({
    queryKey: ['projectArtifacts', orgId, projectId],
    queryFn: () => entities.projectArtifacts(orgId, projectId),
    enabled: Boolean(projectId),
    refetchOnWindowFocus: false,
  });

  const content = useQuery({
    queryKey: ['projectArtifact', orgId, projectId, selected],
    queryFn: () => entities.projectArtifact(orgId, projectId, selected as string),
    enabled: Boolean(projectId && selected),
    refetchOnWindowFocus: false,
  });

  const files = list.data?.artifacts ?? [];

  return (
    <div className="rounded-xl border border-border p-3 text-sm">
      <div className="mb-2 text-xs uppercase tracking-wide text-muted-fg">Memory</div>
      {!projectId ? (
        <p className="text-xs text-muted-fg">Select a project to view its artifacts.</p>
      ) : list.isLoading ? (
        <p className="text-xs text-muted-fg">Loading…</p>
      ) : files.length === 0 ? (
        <p className="text-xs text-muted-fg">No artifacts yet — they appear as the workflow runs.</p>
      ) : selected ? (
        <div className="space-y-2">
          <button
            onClick={() => setSelected(null)}
            className="text-xs text-muted-fg underline hover:text-fg"
          >
            ← {files.length} files
          </button>
          <div className="font-mono text-[11px] text-muted-fg">{selected}</div>
          <pre className="max-h-80 overflow-auto rounded border border-border p-2 text-[11px]">
            {content.isLoading ? 'Loading…' : content.data?.content ?? '(empty)'}
          </pre>
        </div>
      ) : (
        <ul className="space-y-0.5">
          {files.map((f) => (
            <li key={f}>
              <button
                onClick={() => setSelected(f)}
                className="w-full truncate text-left font-mono text-[11px] text-muted-fg hover:text-fg"
                title={f}
              >
                {f}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
