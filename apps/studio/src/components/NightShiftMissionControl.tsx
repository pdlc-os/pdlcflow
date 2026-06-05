// Night-shift mission control — run status for an autonomous /night-shift run.
// The Contract Party is the one human gate (rendered via ApprovalGateModal);
// this panel tracks the run lifecycle and the final outcome. (Live per-verdict
// streaming arrives with the Arq/Redis pipeline in Phase H.)

import { cn } from '@/lib/utils';

type Phase = 'awaiting-contract' | 'running' | 'completed' | 'aborted' | 'declined';

interface Props {
  phase: Phase;
  result?: Record<string, unknown> | null;
}

const LABEL: Record<Phase, string> = {
  'awaiting-contract': 'Awaiting Contract Party',
  running: 'Running autonomously…',
  completed: 'Completed',
  aborted: 'Aborted',
  declined: 'Declined',
};

const TONE: Record<Phase, string> = {
  'awaiting-contract': 'bg-accent/10 text-accent',
  running: 'bg-accent/10 text-accent',
  completed: 'bg-emerald-500/10 text-emerald-600',
  aborted: 'bg-red-500/10 text-red-500',
  declined: 'bg-border/60 text-muted-fg',
};

export function NightShiftMissionControl({ phase, result }: Props) {
  const outcome = (result?.night_shift_outcome as string) ?? null;
  const reason = (result?.night_shift_abort_reason as string) ?? null;

  return (
    <div className="rounded-xl border border-border p-3 text-sm">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-xs uppercase tracking-wide text-muted-fg">Night-shift mission control</div>
        <span className={cn('rounded-full px-2 py-0.5 text-xs font-medium', TONE[phase])}>
          {LABEL[phase]}
        </span>
      </div>

      <ul className="space-y-1 font-mono text-xs text-muted-fg">
        <li>● preflight → contract party → activate → build → ship → reflect</li>
        {phase === 'awaiting-contract' && <li>▸ paused at the single human gate</li>}
        {outcome && <li>▸ outcome: <span className="text-fg">{outcome}</span></li>}
        {reason && <li>▸ reason: {reason}</li>}
        {result?.version != null && <li>▸ shipped {String(result.version)} → {String(result.deploy_tier)}</li>}
      </ul>
    </div>
  );
}
