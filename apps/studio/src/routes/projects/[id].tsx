import { useEffect } from 'react';
import { useParams } from 'react-router-dom';

import { ApprovalGateModal } from '@/components/ApprovalGateModal';
import { ChatPanel } from '@/components/ChatPanel';
import { ContextMeter } from '@/components/ContextMeter';
import { MemoryFileViewer } from '@/components/MemoryFileViewer';
import { ThreadSidebar } from '@/components/ThreadSidebar';
import { NightShiftMissionControl } from '@/components/NightShiftMissionControl';
import { QuestionCard } from '@/components/QuestionCard';
import { StreamingPreview } from '@/components/StreamingPreview';
import { connect, type NightShiftFrame } from '@/lib/ws';
import { useThread } from '@/store/useThread';

export function ProjectView() {
  const { id: routeProjectId } = useParams();
  const projectId = useThread((s) => s.projectId);
  const setProject = useThread((s) => s.setProject);
  const threadId = useThread((s) => s.threadId);
  const pending = useThread((s) => s.pending);
  const status = useThread((s) => s.status);
  const result = useThread((s) => s.result);
  const verdicts = useThread((s) => s.verdicts);
  const streaming = useThread((s) => s.streaming);
  const setPending = useThread((s) => s.setPending);
  const setResult = useThread((s) => s.setResult);
  const appendVerdict = useThread((s) => s.appendVerdict);
  const streamToken = useThread((s) => s.streamToken);
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
        else if (f.type === 'thread.completed') {
          setPending(null);
          if (f.summary) setResult(f.summary);
        } else if (f.type === 'token') {
          streamToken(f);
        } else if (f.type.startsWith('night_shift.')) {
          appendVerdict(f as NightShiftFrame);
        }
      },
    });
  }, [threadId, setPending, setResult, appendVerdict, streamToken]);

  // Bind the active project to the route (deep links / nav), registering it so it
  // shows in the sidebar. Switching projects clears the thread view (setProject).
  useEffect(() => {
    if (routeProjectId && routeProjectId !== projectId) {
      setProject(routeProjectId);
    }
  }, [routeProjectId, projectId, setProject]);

  // On load, rehydrate the persisted thread — only if it belongs to this project.
  useEffect(() => {
    const s = useThread.getState();
    if (s.threadId && s.transcript.length === 0 && s.threadId.split(':')[1] === s.projectId) {
      void s.openThread(s.threadId);
    }
  }, []);

  const busy = status === 'running';
  const question = pending?.kind === 'user_input_required' ? pending : null;
  const gate = pending?.kind === 'approval' ? pending : null;

  // Night-shift mission control: shown while the contract gate is open or once
  // a run has produced an outcome.
  const isNightShift =
    pending?.gate_kind === 'night_shift_contract' ||
    result?.night_shift_outcome != null ||
    verdicts.length > 0;
  const nsPhase = pending?.gate_kind === 'night_shift_contract'
    ? 'awaiting-contract'
    : ((result?.night_shift_outcome as string) ?? 'running');

  return (
    <div className="grid grid-cols-[1fr_280px] gap-4">
      <div className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold tracking-tight">Studio</h2>
        <ChatPanel />
        <StreamingPreview streaming={streaming} />
        {isNightShift && (
          <NightShiftMissionControl
            phase={nsPhase as 'awaiting-contract' | 'running' | 'completed' | 'aborted' | 'declined'}
            result={result}
            verdicts={verdicts}
          />
        )}
        {question && (
          <QuestionCard pending={question} busy={busy} onSubmit={(a) => void answer(a)} />
        )}
      </div>
      <aside className="flex flex-col gap-4">
        <ThreadSidebar />
        <ContextMeter />
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
