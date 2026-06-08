import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronLeft, FileText, Folder, GitBranch } from 'lucide-react';

import { entities } from '@/lib/api';
import { useScope } from '@/store/useScope';
import { useThread } from '@/store/useThread';
import { cn } from '@/lib/utils';

/**
 * Repo-backed memory (#3): only shown once a repository is connected/selected.
 * Browses the repo's files via the GitHub API; click a file to read it.
 */
export function RepoMemory() {
  const orgId = useThread((s) => s.orgId);
  const repoId = useScope((s) => s.repoId);
  const [path, setPath] = useState('');
  const [open, setOpen] = useState<{ path: string; content: string } | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ['repoFiles', orgId, repoId, path],
    queryFn: () => entities.repoFiles(orgId, repoId as string, path),
    enabled: !!orgId && !!repoId,
  });

  if (!repoId) return null; // memory appears only after a repo is opened

  const entries = (data?.entries ?? []).slice().sort((a, b) =>
    a.type === b.type ? a.name.localeCompare(b.name) : a.type === 'dir' ? -1 : 1);

  const openFile = async (p: string) => {
    const f = await entities.repoFile(orgId, repoId, p);
    setOpen({ path: p, content: f.content });
  };

  return (
    <div className="mt-5">
      <div className="mb-2 flex items-center gap-2 text-xs uppercase tracking-wide text-muted-fg">
        <GitBranch className="h-3.5 w-3.5" /> Repository memory
      </div>
      {path && (
        <button type="button" onClick={() => setPath(path.split('/').slice(0, -1).join('/'))}
          className="mb-1 flex items-center gap-1 px-1 text-xs text-muted-fg hover:text-fg">
          <ChevronLeft className="h-3 w-3" /> {path}
        </button>
      )}
      {isLoading && <div className="px-2 text-xs text-muted-fg">loading…</div>}
      {isError && <div className="px-2 text-xs text-red-500">couldn't read repo (check the token)</div>}
      <div className="space-y-0.5">
        {entries.map((x) => (
          <button
            key={x.path}
            type="button"
            onClick={() => (x.type === 'dir' ? setPath(x.path) : void openFile(x.path))}
            className="flex w-full items-center gap-1.5 truncate rounded px-2 py-0.5 text-left text-xs text-muted-fg hover:bg-border/60 hover:text-fg"
          >
            {x.type === 'dir' ? <Folder className="h-3 w-3 shrink-0" /> : <FileText className="h-3 w-3 shrink-0" />}
            <span className="truncate">{x.name}</span>
          </button>
        ))}
        {!isLoading && entries.length === 0 && <div className="px-2 text-xs text-muted-fg/60">empty</div>}
      </div>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-6" onClick={() => setOpen(null)}>
          <div className={cn('flex max-h-[80vh] w-[min(900px,90vw)] flex-col rounded-xl border border-border bg-bg')}
               onClick={(ev) => ev.stopPropagation()}>
            <div className="flex items-center justify-between border-b border-border px-4 py-2 text-sm">
              <span className="font-mono">{open.path}</span>
              <button type="button" onClick={() => setOpen(null)} className="text-muted-fg hover:text-fg">✕</button>
            </div>
            <pre className="overflow-auto whitespace-pre-wrap p-4 text-xs leading-relaxed">{open.content}</pre>
          </div>
        </div>
      )}
    </div>
  );
}
