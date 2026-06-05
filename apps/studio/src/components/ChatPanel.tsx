import { useState } from 'react';
import { ChevronRight, Loader2 } from 'lucide-react';

import { useThread } from '@/store/useThread';
import { cn } from '@/lib/utils';

export function ChatPanel() {
  const transcript = useThread((s) => s.transcript);
  const status = useThread((s) => s.status);
  const start = useThread((s) => s.start);
  const [input, setInput] = useState('');

  const busy = status === 'running';

  const submit = () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput('');
    // "/brainstorm dark mode" -> command=brainstorm, feature="dark mode"
    const m = text.match(/^\/?(\w[\w-]*)\s*(.*)$/);
    const command = m ? m[1] : 'brainstorm';
    const feature = m && m[2] ? m[2] : undefined;
    void start(command, { feature, mode: 'socratic' });
  };

  return (
    <div className="flex flex-col gap-3">
      {transcript.length === 0 ? (
        <div className="flex h-[40vh] items-center justify-center rounded-xl border border-dashed border-border text-sm text-muted-fg">
          Run <span className="mx-1 rounded bg-border/60 px-1.5 py-0.5 font-mono">/brainstorm dark mode</span> to start.
        </div>
      ) : (
        transcript.map((m) => (
          <div key={m.id} className={cn('flex gap-3', m.role === 'user' ? 'flex-row-reverse' : 'flex-row')}>
            <Avatar role={m.role} />
            <div
              className={cn(
                'max-w-[80ch] rounded-xl px-4 py-2 text-sm leading-relaxed',
                m.role === 'user'
                  ? 'bg-accent text-accent-fg'
                  : m.role === 'system'
                    ? 'border border-dashed border-border text-muted-fg'
                    : 'border border-border bg-bg'
              )}
            >
              {m.text}
            </div>
          </div>
        ))
      )}

      <div className="mt-2 flex items-center gap-2 rounded-xl border border-border px-3 py-2">
        {busy ? (
          <Loader2 className="h-4 w-4 animate-spin text-muted-fg" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-fg" />
        )}
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
          disabled={busy}
          placeholder="Type a slash command, e.g. /brainstorm dark mode"
          className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-fg disabled:opacity-60"
        />
      </div>
    </div>
  );
}

function Avatar({ role }: { role: string }) {
  return (
    <div className="grid h-7 w-7 shrink-0 place-items-center rounded-full border border-border text-xs font-medium text-muted-fg">
      {role.slice(0, 1).toUpperCase()}
    </div>
  );
}
