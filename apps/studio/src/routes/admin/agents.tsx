const PERSONAS = [
  'atlas', 'bolt', 'echo', 'friday', 'jarvis',
  'muse', 'neo', 'phantom', 'pulse', 'sentinel',
] as const;

export function AdminAgents() {
  return (
    <div>
      <h2 className="mb-2 text-lg font-semibold">Agents</h2>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
        {PERSONAS.map((p) => (
          <div key={p} className="rounded-xl border border-border p-3 text-sm">
            <div className="font-medium capitalize">{p}</div>
            <div className="mt-1 text-xs text-muted-fg">usage · tokens · approval rate</div>
          </div>
        ))}
      </div>
    </div>
  );
}
