import { useQuery } from '@tanstack/react-query';

import { admin } from '@/lib/api';
import { useThread } from '@/store/useThread';
import { cn } from '@/lib/utils';

/** ChatGPT-style conversation history: list past threads for this project and
 *  reopen one to replay/continue it. */
export function ThreadSidebar() {
  const orgId = useThread((s) => s.orgId);
  const projectId = useThread((s) => s.projectId);
  const threadId = useThread((s) => s.threadId);
  const status = useThread((s) => s.status);
  const openThread = useThread((s) => s.openThread);
  const newThread = useThread((s) => s.newThread);

  const q = useQuery({
    queryKey: ['threads', orgId, projectId, threadId, status],
    queryFn: () => admin.listThreads(orgId, projectId),
    enabled: !!orgId,
    refetchInterval: 15_000,
  });
  const threads = q.data?.threads ?? [];

  return (
    <div className="rounded-lg border border-border p-2 text-sm">
      <div className="mb-2 flex items-center justify-between px-1">
        <span className="font-medium">Conversations</span>
        <button
          type="button"
          onClick={() => newThread()}
          className="rounded-md border border-border px-2 py-0.5 text-xs hover:bg-border/50"
        >
          + New
        </button>
      </div>
      {threads.length === 0 ? (
        <p className="px-1 py-2 text-xs text-muted-fg">No conversations yet.</p>
      ) : (
        <ul className="max-h-[50vh] space-y-0.5 overflow-auto">
          {threads.map((t) => (
            <li key={t.thread_id}>
              <button
                type="button"
                onClick={() => void openThread(t.thread_id)}
                title={t.label}
                className={cn(
                  'flex w-full items-center justify-between gap-2 rounded-md px-2 py-1 text-left text-xs',
                  t.thread_id === threadId ? 'bg-accent text-accent-fg' : 'hover:bg-border/50'
                )}
              >
                <span className="truncate">{t.label}</span>
                <span className="shrink-0 opacity-60">{t.turns}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
