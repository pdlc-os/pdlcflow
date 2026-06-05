import { useEffect } from 'react';

import { ApprovalGateModal } from '@/components/ApprovalGateModal';
import { ChatPanel } from '@/components/ChatPanel';
import { MemoryFileViewer } from '@/components/MemoryFileViewer';
import { QuestionCard } from '@/components/QuestionCard';
import { connect } from '@/lib/ws';
import { useThread } from '@/store/useThread';

export function ProjectView() {
  const threadId = useThread((s) => s.threadId);
  const pending = useThread((s) => s.pending);
  const status = useThread((s) => s.status);
  const setPending = useThread((s) => s.setPending);
  const answer = useThread((s) => s.answer);
  const resolveApproval = useThread((s) => s.resolveApproval);

  // Live thread channel: interaction.opened / thread.completed frames keep the
  // view in sync even when the graph advances out-of-band.
  useEffect(() => {
    if (!threadId) return;
    return connect({
      threadId,
      onFrame: (f) => {
        if (f.type === 'interaction.opened') setPending(f.interaction);
        if (f.type === 'thread.completed') setPending(null);
      },
    });
  }, [threadId, setPending]);

  const busy = status === 'running';
  const question = pending?.kind === 'user_input_required' ? pending : null;
  const gate = pending?.kind === 'approval' ? pending : null;

  return (
    <div className="grid grid-cols-[1fr_280px] gap-4">
      <div className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold tracking-tight">Studio</h2>
        <ChatPanel />
        {question && (
          <QuestionCard pending={question} busy={busy} onSubmit={(a) => void answer(a)} />
        )}
      </div>
      <aside>
        <MemoryFileViewer />
      </aside>

      {gate && (
        <ApprovalGateModal
          gateKind={gate.gate_kind ?? 'approval'}
          summary={typeof gate.payload.summary === 'string' ? gate.payload.summary : undefined}
          visual={gate.payload.visual ?? null}
          busy={busy}
          onResolve={({ approved, comment }) => void resolveApproval(approved, comment)}
        />
      )}
    </div>
  );
}
