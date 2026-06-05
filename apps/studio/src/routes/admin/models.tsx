const PROVIDERS = [
  'bedrock', 'anthropic', 'vertex', 'azure', 'openai', 'gemini', 'ollama',
] as const;

const PERSONAS = [
  'atlas', 'bolt', 'echo', 'friday', 'jarvis',
  'muse', 'neo', 'phantom', 'pulse', 'sentinel',
] as const;

export function AdminModels() {
  return (
    <div className="max-w-3xl">
      <h2 className="mb-2 text-lg font-semibold">Models</h2>
      <p className="mb-5 text-sm text-muted-fg">
        Set the org default LLM provider, then override per-agent where it makes sense.
        Sentinel is a deterministic Python evaluator — it has no model.
      </p>

      <section className="mb-6 rounded-xl border border-border p-4">
        <h3 className="mb-2 text-sm font-medium">Org default</h3>
        <ProviderRow persona={null} />
      </section>

      <section className="rounded-xl border border-border p-4">
        <h3 className="mb-2 text-sm font-medium">Per-agent overrides</h3>
        <div className="space-y-2">
          {PERSONAS.map((p) => <ProviderRow key={p} persona={p} />)}
        </div>
      </section>
    </div>
  );
}

function ProviderRow({ persona }: { persona: string | null }) {
  const disabled = persona === 'sentinel';
  return (
    <div className="grid grid-cols-[120px_1fr_1fr_80px] items-center gap-2 text-sm">
      <div className="capitalize text-muted-fg">{persona ?? 'default'}</div>
      <select disabled={disabled} className="rounded border border-border bg-bg px-2 py-1">
        {persona ? <option value="">— inherit —</option> : null}
        {PROVIDERS.map((p) => <option key={p} value={p}>{p}</option>)}
      </select>
      <input
        disabled={disabled}
        placeholder={disabled ? 'N/A — deterministic Python' : 'model id'}
        className="rounded border border-border bg-bg px-2 py-1"
      />
      <button
        disabled={disabled}
        className="rounded border border-border px-2 py-1 text-xs text-muted-fg hover:bg-border/60 disabled:opacity-40"
      >
        Test
      </button>
    </div>
  );
}
