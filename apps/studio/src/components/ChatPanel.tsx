import { ChevronRight } from 'lucide-react';

import { useThread } from '@/store/useThread';
import { StepCard } from './StepCard';
import { cn } from '@/lib/utils';

export function ChatPanel() {
  const messages = useThread((s) => s.messages);

  if (messages.length === 0) {
    return (
      <div className="flex h-[60vh] items-center justify-center rounded-xl border border-dashed border-border text-sm text-muted-fg">
        Run <span className="mx-1 rounded bg-border/60 px-1.5 py-0.5 font-mono">/brainstorm</span> to start.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {messages.map((m) => (
        <div
          key={m.id}
          className={cn(
            'flex gap-3',
            m.role === 'user' ? 'flex-row-reverse' : 'flex-row'
          )}
        >
          <Avatar role={m.role} persona={m.persona} />
          <div
            className={cn(
              'max-w-[80ch] rounded-xl px-4 py-2 leading-relaxed',
              m.role === 'user'
                ? 'bg-accent text-accent-fg'
                : 'border border-border bg-bg'
            )}
          >
            <div className="whitespace-pre-wrap text-sm">{m.text}</div>
            {m.steps?.map((s, i) => (
              <StepCard key={i} kind={s.kind} summary={s.summary} />
            ))}
          </div>
        </div>
      ))}
      <div className="mt-2 flex items-center gap-2 rounded-xl border border-border px-3 py-2">
        <ChevronRight className="h-4 w-4 text-muted-fg" />
        <input
          placeholder="Type a slash command or a message…"
          className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-fg"
        />
      </div>
    </div>
  );
}

function Avatar({ role, persona }: { role: string; persona?: string }) {
  const initial = (persona ?? role).slice(0, 1).toUpperCase();
  return (
    <div className="grid h-7 w-7 shrink-0 place-items-center rounded-full border border-border text-xs font-medium text-muted-fg">
      {initial}
    </div>
  );
}
