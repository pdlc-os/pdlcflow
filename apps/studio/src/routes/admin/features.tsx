import { useParams } from 'react-router-dom';

export function AdminFeatures() {
  const { f } = useParams<{ f: string }>();

  if (!f) {
    return (
      <div>
        <h2 className="mb-2 text-lg font-semibold">Feature time-travel</h2>
        <p className="text-sm text-muted-fg">
          Pick a feature to replay its full event history in chronological order. Open
          <code className="mx-1 rounded bg-border/60 px-1 py-0.5 text-xs">/admin/features/F-NNN</code>
          to view one. Timeline data (<code className="text-xs">GET /v1/admin/features/&#123;id&#125;/timeline</code>)
          wired in Phase G.
        </p>
      </div>
    );
  }

  return (
    <div>
      <h2 className="mb-2 text-lg font-semibold">Feature {f} — time-travel</h2>
      <p className="text-sm text-muted-fg">
        Every event for <span className="font-medium text-fg">{f}</span> in chronological order,
        replayable. Backed by <code className="text-xs">GET /v1/admin/features/{f}/timeline</code>;
        the <code className="text-xs">&lt;EventTimeline&gt;</code> render wires in Phase G.
      </p>
    </div>
  );
}
