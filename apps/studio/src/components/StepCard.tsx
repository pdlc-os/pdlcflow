import { useState } from 'react';
import { ChevronDown, ChevronRight, Sparkles, ShieldCheck, Wrench, Vote } from 'lucide-react';

interface Props {
  kind: 'tool' | 'llm' | 'verdict' | 'pitch';
  summary: string;
}

const KIND_META: Record<Props['kind'], { Icon: typeof Wrench; label: string }> = {
  tool: { Icon: Wrench, label: 'Tool' },
  llm: { Icon: Sparkles, label: 'LLM' },
  verdict: { Icon: ShieldCheck, label: 'Sentinel verdict' },
  pitch: { Icon: Vote, label: 'Party pitch' },
};

export function StepCard({ kind, summary }: Props) {
  const [open, setOpen] = useState(false);
  const { Icon, label } = KIND_META[kind];
  return (
    <div className="mt-2 rounded-lg border border-border bg-bg/60">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-muted-fg hover:text-fg"
      >
        {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        <Icon className="h-3.5 w-3.5" />
        <span className="font-medium">{label}</span>
        <span className="truncate">{summary}</span>
      </button>
      {open && (
        <div className="border-t border-border px-3 py-2 text-xs font-mono text-muted-fg">
          {summary}
        </div>
      )}
    </div>
  );
}
