import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { FolderOpen, MessageSquare, Plus } from 'lucide-react';

import { admin, entities, type ThreadSummary } from '@/lib/api';
import { useThread } from '@/store/useThread';
import { cn } from '@/lib/utils';

/** Left nav: projects (server-backed), each with its conversations nested beneath. */
export function SideDrawer() {
  const orgId = useThread((s) => s.orgId);
  const projectId = useThread((s) => s.projectId);
  const threadId = useThread((s) => s.threadId);
  const setProject = useThread((s) => s.setProject);
  const openThread = useThread((s) => s.openThread);
  const navigate = useNavigate();

  const projectsQ = useQuery({
    queryKey: ['projects', orgId],
    queryFn: () => entities.projects(orgId),
    enabled: !!orgId,
  });
  const projects = projectsQ.data?.projects ?? [];
  const nameFor = (id: string) => projects.find((p) => p.id === id)?.name ?? `proj-${id.slice(0, 6)}`;

  // One query for all threads; group by project so each project lists its convos.
  const { data } = useQuery({
    queryKey: ['allThreads', orgId, projectId, threadId],
    queryFn: () => admin.listThreads(orgId),
    enabled: !!orgId,
    refetchInterval: 15_000,
  });
  const threads = data?.threads ?? [];
  const byProject: Record<string, ThreadSummary[]> = {};
  for (const t of threads) {
    const k = t.project_id ?? 'unknown';
    (byProject[k] ||= []).push(t);
  }

  // Projects = the server list ∪ any project that already has conversations.
  const ids = Array.from(
    new Set([...projects.map((p) => p.id), ...threads.map((t) => t.project_id).filter(Boolean) as string[]])
  );

  const openProject = (id: string) => { setProject(id); navigate(`/projects/${id}`); };
  const openConv = (pid: string, tid: string) => {
    setProject(pid);
    navigate(`/projects/${pid}`);
    void openThread(tid);
  };

  return (
    <aside className="w-56 shrink-0 overflow-auto border-r border-border px-3 py-3 text-sm">
      <div className="mb-2 flex items-center justify-between text-xs uppercase tracking-wide text-muted-fg">
        <span className="flex items-center gap-2"><FolderOpen className="h-3.5 w-3.5" /> Projects</span>
        <button type="button" onClick={() => navigate('/')} title="New project" className="hover:text-fg">
          <Plus className="h-3.5 w-3.5" />
        </button>
      </div>

      {ids.length === 0 ? (
        <p className="px-2 py-1 text-xs text-muted-fg">No projects yet — create one on the home page.</p>
      ) : (
        <div className="space-y-1">
          {ids.map((pid) => (
            <div key={pid}>
              <button
                type="button"
                onClick={() => openProject(pid)}
                className={cn(
                  'block w-full truncate rounded px-2 py-1 text-left font-medium hover:bg-border/60',
                  pid === projectId && 'text-accent'
                )}
              >
                {nameFor(pid)}
              </button>
              <div className="ml-2 space-y-0.5 border-l border-border pl-2">
                {(byProject[pid] ?? []).map((t) => (
                  <button
                    key={t.thread_id}
                    type="button"
                    onClick={() => openConv(pid, t.thread_id)}
                    title={t.label}
                    className={cn(
                      'flex w-full items-center gap-1 rounded px-2 py-0.5 text-left text-xs hover:bg-border/60 hover:text-fg',
                      t.thread_id === threadId ? 'text-accent' : 'text-muted-fg'
                    )}
                  >
                    <MessageSquare className="h-3 w-3 shrink-0" />
                    <span className="truncate">{t.label}</span>
                  </button>
                ))}
                {(byProject[pid] ?? []).length === 0 && (
                  <div className="px-2 py-0.5 text-xs text-muted-fg/60">no conversations yet</div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </aside>
  );
}
