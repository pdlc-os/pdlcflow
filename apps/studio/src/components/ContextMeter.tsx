import { useQuery } from '@tanstack/react-query';

import { admin } from '@/lib/api';
import { useThread } from '@/store/useThread';

/**
 * Shows how close this project's agent prompts came to the active model's context
 * window (peak single-prompt tokens), and offers a one-click `/compact` when near
 * the limit. Each agent call is a discrete prompt, so the gauge tracks the peak.
 */
export function ContextMeter() {
  const orgId = useThread((s) => s.orgId);
  const projectId = useThread((s) => s.projectId);
  const status = useThread((s) => s.status);
  const start = useThread((s) => s.start);

  const q = useQuery({
    queryKey: ['context', orgId, projectId, status],
    queryFn: () => admin.contextUsage(orgId, projectId),
    enabled: !!orgId,
    refetchInterval: 15_000,
  });

  const u = q.data;
  if (!u || u.calls === 0) return null;

  const pct = Math.min(100, Math.round(u.pct_used * 100));
  const danger = u.near_limit;

  return (
    <div className="rounded-lg border border-border p-3 text-xs">
      <div className="mb-1 flex items-center justify-between text-muted-fg">
        <span>Context window</span>
        <span>{pct}% used</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded bg-border/50">
        <div className="h-full rounded" style={{ width: `${pct}%`, backgroundColor: danger ? '#ef4444' : 'var(--accent)' }} />
      </div>
      <div className="mt-1 text-muted-fg">
        peak {u.peak_prompt_tokens.toLocaleString()} / {u.context_window.toLocaleString()} tok
        {u.model_id ? ` · ${u.model_id}` : ''}
      </div>
      {danger && (
        <button
          type="button"
          onClick={() => void start('compact')}
          disabled={status === 'running'}
          className="mt-2 w-full rounded-md bg-accent px-2 py-1 font-medium text-accent-fg disabled:opacity-50"
          title="Distill the working log into a concise summary to free up context"
        >
          Compact context
        </button>
      )}
    </div>
  );
}
