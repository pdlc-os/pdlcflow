import { useMemo, useRef, useState } from 'react';
import { ChevronRight, Loader2 } from 'lucide-react';

import { useThread } from '@/store/useThread';
import { cn } from '@/lib/utils';
import {
  COMMAND_NAMES,
  PDLC_COMMANDS,
  inCommandContext,
  parseCommandToken,
  type PdlcCommand,
} from '@/lib/commands';

type Mode = 'socratic' | 'sketch';

export function ChatPanel() {
  const transcript = useThread((s) => s.transcript);
  const status = useThread((s) => s.status);
  const start = useThread((s) => s.start);
  const [input, setInput] = useState('');
  const [mode, setMode] = useState<Mode>('sketch');
  const [menuOpen, setMenuOpen] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const busy = status === 'running';

  // Autocomplete: while typing the first `/token`, suggest matching commands.
  const matches = useMemo<PdlcCommand[]>(() => {
    if (!inCommandContext(input)) return [];
    const prefix = input.slice(1).toLowerCase();
    return PDLC_COMMANDS.filter((c) => c.name.startsWith(prefix));
  }, [input]);
  const showMenu = menuOpen && matches.length > 0;

  const accept = (cmd: PdlcCommand) => {
    setInput(`/${cmd.name} `);
    setMenuOpen(false);
    inputRef.current?.focus();
  };

  const submit = () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput('');
    setMenuOpen(false);
    // "/brainstorm dark mode" -> command=brainstorm, feature="dark mode"
    const m = text.match(/^\/?(\w[\w-]*)\s*(.*)$/);
    const command = m ? m[1] : 'brainstorm';
    const feature = m && m[2] ? m[2] : undefined;
    void start(command, { feature, mode });
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (showMenu) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActive((i) => (i + 1) % matches.length);
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActive((i) => (i - 1 + matches.length) % matches.length);
        return;
      }
      if (e.key === 'Tab' || (e.key === 'Enter' && matches[active])) {
        e.preventDefault();
        accept(matches[active]);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setMenuOpen(false);
        return;
      }
    }
    if (e.key === 'Enter') submit();
  };

  // Inline color-coding: render a transparent input over a highlighted overlay.
  const parsed = parseCommandToken(input);
  const known = parsed ? COMMAND_NAMES.has(parsed.name) : false;

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

      <div className="relative mt-2">
        {/* Autocomplete menu (above the input) */}
        {showMenu && (
          <ul className="absolute bottom-full mb-1 max-h-64 w-full overflow-auto rounded-xl border border-border bg-bg py-1 shadow-lg">
            {matches.map((c, i) => (
              <li key={c.name}>
                <button
                  type="button"
                  onMouseDown={(e) => {
                    e.preventDefault();
                    accept(c);
                  }}
                  onMouseEnter={() => setActive(i)}
                  className={cn(
                    'flex w-full items-baseline gap-2 px-3 py-1.5 text-left text-sm',
                    i === active ? 'bg-border/50' : ''
                  )}
                >
                  <span className="font-mono font-medium text-accent">/{c.name}</span>
                  {c.arg && <span className="font-mono text-xs text-muted-fg">&lt;{c.arg}&gt;</span>}
                  <span className="ml-auto truncate text-xs text-muted-fg">{c.summary}</span>
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="flex items-center gap-2 rounded-xl border border-border px-3 py-2">
          {busy ? (
            <Loader2 className="h-4 w-4 shrink-0 animate-spin text-muted-fg" />
          ) : (
            <ChevronRight className={cn('h-4 w-4 shrink-0', known ? 'text-accent' : 'text-muted-fg')} />
          )}

          {/* overlay (highlight) + transparent input share identical typography */}
          <div className="relative flex-1">
            <div
              aria-hidden
              className="pointer-events-none absolute inset-0 flex items-center whitespace-pre overflow-hidden text-sm"
            >
              {parsed ? (
                <>
                  <span className={cn('font-mono font-medium', known ? 'text-accent' : 'text-muted-fg')}>
                    {parsed.token}
                  </span>
                  <span className="text-fg">{parsed.rest}</span>
                </>
              ) : (
                <span className="text-fg">{input}</span>
              )}
            </div>
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
                setMenuOpen(true);
                setActive(0);
              }}
              onKeyDown={onKeyDown}
              onBlur={() => setMenuOpen(false)}
              disabled={busy}
              placeholder="Type a slash command, e.g. /brainstorm dark mode"
              style={{ caretColor: 'var(--fg)' }}
              className="w-full bg-transparent text-sm text-transparent outline-none placeholder:text-muted-fg disabled:opacity-60"
            />
          </div>

          {/* sketch ⇄ socratic interaction mode */}
          <ModeToggle mode={mode} setMode={setMode} />
        </div>
      </div>
    </div>
  );
}

function ModeToggle({ mode, setMode }: { mode: Mode; setMode: (m: Mode) => void }) {
  return (
    <div
      className="flex shrink-0 overflow-hidden rounded-md border border-border text-xs"
      title="Interaction mode (init/brainstorm) — Sketch: the agent pre-fills recommended draft answers you edit. Socratic: blank questions you answer from scratch. Both ask the same questions; multi-option suggestions + gates work in both."
    >
      {(['sketch', 'socratic'] as Mode[]).map((m) => (
        <button
          key={m}
          type="button"
          onClick={() => setMode(m)}
          className={cn('px-2 py-0.5 capitalize', mode === m ? 'bg-accent text-accent-fg' : 'text-muted-fg')}
        >
          {m}
        </button>
      ))}
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
