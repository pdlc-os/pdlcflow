// Read-only memory-file inspector. Stub.

export function MemoryFileViewer() {
  return (
    <div className="rounded-xl border border-border p-3 text-sm">
      <div className="mb-2 text-xs uppercase tracking-wide text-muted-fg">Memory</div>
      <div className="space-y-2 text-muted-fg">
        <div>Constitution · Intent · State · Roadmap · Decisions · Metrics</div>
        <div>Overview · Changelog · Deployments</div>
        <div>episodes/</div>
      </div>
      <p className="mt-3 text-xs text-muted-fg">
        Inline Monaco viewer lands in Phase B.
      </p>
    </div>
  );
}
