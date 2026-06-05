// Modal — Approve / Reject for an approval gate, with an optional visual
// companion (e.g. the Plan dependency tree) rendered alongside.

import { BrainstormVisualCompanion } from './BrainstormVisualCompanion';
import type { VisualSpec } from '@/lib/api';

interface Props {
  gateKind: string;
  summary?: string;
  visual?: VisualSpec | null;
  busy?: boolean;
  onResolve: (decision: { approved: boolean; comment?: string }) => void;
}

export function ApprovalGateModal({ gateKind, summary, visual, busy, onResolve }: Props) {
  const hasVisual = !!visual && visual.screens.length > 0;
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-fg/40 p-4 backdrop-blur-sm">
      <div className="grid max-h-[90vh] w-[min(900px,100%)] gap-4 overflow-auto rounded-2xl border border-border bg-bg p-5 shadow-lg"
           style={hasVisual ? { gridTemplateColumns: '1fr 340px' } : undefined}>
        <div>
          <div className="mb-2 text-xs uppercase tracking-wide text-muted-fg">Approval gate</div>
          <h3 className="mb-3 text-lg font-semibold">{gateKind}</h3>
          {summary && <p className="mb-4 text-sm text-muted-fg">{summary}</p>}
          <div className="mt-2 flex justify-end gap-2">
            <button
              onClick={() => onResolve({ approved: false })}
              disabled={busy}
              className="rounded-md px-3 py-1.5 text-sm text-muted-fg hover:bg-border/60 disabled:opacity-60"
            >
              Reject
            </button>
            <button
              onClick={() => onResolve({ approved: true })}
              disabled={busy}
              className="rounded-md bg-accent px-3 py-1.5 text-sm text-accent-fg hover:opacity-90 disabled:opacity-60"
            >
              Approve
            </button>
          </div>
        </div>
        {hasVisual && <BrainstormVisualCompanion visual={visual!} />}
      </div>
    </div>
  );
}
