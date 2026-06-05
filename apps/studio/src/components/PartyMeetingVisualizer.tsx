// N-up pitch panels + consensus banner. Stub.

interface Pitch {
  persona: string;
  ref: string;
}

interface Props {
  kind: 'wave_kickoff' | 'design_roundtable' | 'party_review' | 'strike_panel';
  pitches: Pitch[];
  decision?: string;
}

export function PartyMeetingVisualizer({ kind, pitches, decision }: Props) {
  return (
    <div className="rounded-xl border border-border p-3">
      <div className="mb-2 text-xs uppercase tracking-wide text-muted-fg">
        Party meeting: {kind.replace('_', ' ')}
      </div>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
        {pitches.map((p) => (
          <div key={p.persona} className="rounded-lg border border-border p-2 text-sm">
            <div className="mb-1 font-medium">{p.persona}</div>
            <a className="text-xs text-accent hover:underline" href={p.ref}>view pitch</a>
          </div>
        ))}
      </div>
      {decision && (
        <div className="mt-3 rounded-lg bg-accent/10 px-3 py-2 text-sm text-accent">
          Consensus: {decision}
        </div>
      )}
    </div>
  );
}
