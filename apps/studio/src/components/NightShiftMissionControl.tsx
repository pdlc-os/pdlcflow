// Live verdict stream + abort + auto-pick log. Stub.

interface Verdict {
  ts: string;
  verdict: 'continue' | 'complete' | 'abort';
  reason?: string;
}

interface Props {
  active: boolean;
  verdicts: Verdict[];
  onAbort: () => void;
}

export function NightShiftMissionControl({ active, verdicts, onAbort }: Props) {
  return (
    <div className="rounded-xl border border-border p-3 text-sm">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-xs uppercase tracking-wide text-muted-fg">Night-shift mission control</div>
        {active && (
          <button
            onClick={onAbort}
            className="rounded-md bg-red-500/10 px-2 py-0.5 text-xs text-red-500 hover:bg-red-500/20"
          >
            Abort
          </button>
        )}
      </div>
      {verdicts.length === 0 ? (
        <p className="text-muted-fg">No verdicts yet.</p>
      ) : (
        <ul className="space-y-1 font-mono text-xs">
          {verdicts.map((v, i) => (
            <li key={i}>
              {v.ts} · {v.verdict}
              {v.reason ? ` · ${v.reason}` : ''}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
