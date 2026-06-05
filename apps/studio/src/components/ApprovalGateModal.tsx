// Modal — Approve / Reject / Edit with artifact preview.

interface Props {
  gateKind: string;
  artifactUri?: string;
  summary?: string[];
  onResolve: (decision: { approved: boolean; comment?: string }) => void;
}

export function ApprovalGateModal({ gateKind, artifactUri, summary, onResolve }: Props) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-fg/40 backdrop-blur-sm">
      <div className="w-[min(640px,calc(100%-2rem))] rounded-2xl border border-border bg-bg p-5 shadow-lg">
        <div className="mb-2 text-xs uppercase tracking-wide text-muted-fg">
          Approval gate
        </div>
        <h3 className="mb-3 text-lg font-semibold">{gateKind}</h3>
        {summary?.length ? (
          <ul className="mb-3 list-inside list-disc space-y-1 text-sm">
            {summary.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        ) : null}
        {artifactUri && (
          <a className="text-sm text-accent hover:underline" href={artifactUri}>
            Open artifact ↗
          </a>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={() => onResolve({ approved: false })}
            className="rounded-md px-3 py-1.5 text-sm text-muted-fg hover:bg-border/60"
          >
            Reject
          </button>
          <button
            onClick={() => onResolve({ approved: true })}
            className="rounded-md bg-accent px-3 py-1.5 text-sm text-accent-fg hover:opacity-90"
          >
            Approve
          </button>
        </div>
      </div>
    </div>
  );
}
