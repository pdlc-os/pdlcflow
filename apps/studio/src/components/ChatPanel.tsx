import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronRight, Loader2, Paperclip, X } from 'lucide-react';

import { uploadFile, type Upload } from '@/lib/api';
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

// Shared typography for the textarea AND its highlight overlay. They MUST match
// exactly (font, size, line-height, padding, wrapping) or the caret drifts — the
// highlight differs only by COLOR, never font/weight.
const FIELD_TYPO = 'm-0 border-0 p-0 font-sans text-sm leading-6 whitespace-pre-wrap break-words';
const MAX_H = 168; // ~7 lines, then scroll

export function ChatPanel() {
  const transcript = useThread((s) => s.transcript);
  const status = useThread((s) => s.status);
  const start = useThread((s) => s.start);
  const continueThread = useThread((s) => s.continueThread);
  const threadId = useThread((s) => s.threadId);
  const pending = useThread((s) => s.pending);
  const orgId = useThread((s) => s.orgId);
  const projectId = useThread((s) => s.projectId);
  const [input, setInput] = useState('');
  const [mode, setMode] = useState<Mode>('sketch');
  const [menuOpen, setMenuOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [attachments, setAttachments] = useState<Upload[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  // The conversation id this composer's uploads + the next send share, so files
  // land under the same conversation folder. Reset after each send.
  const sessionRef = useRef<string>(crypto.randomUUID());

  const busy = status === 'running';

  const addFiles = async (files: FileList | File[]) => {
    const list = Array.from(files);
    if (list.length === 0) return;
    setUploading(true);
    try {
      for (const f of list) {
        try {
          const up = await uploadFile(orgId, projectId, sessionRef.current, f);
          setAttachments((a) => [...a, up]);
        } catch {
          /* skip a failed file; others still upload */
        }
      }
    } finally {
      setUploading(false);
    }
  };

  // Autocomplete: while typing the first `/token`, suggest matching commands.
  const matches = useMemo<PdlcCommand[]>(() => {
    if (!inCommandContext(input)) return [];
    const prefix = input.slice(1).toLowerCase();
    return PDLC_COMMANDS.filter((c) => c.name.startsWith(prefix));
  }, [input]);
  const showMenu = menuOpen && matches.length > 0;

  // Auto-grow the textarea to fit its content (capped at MAX_H, then scrolls).
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, MAX_H)}px`;
    if (overlayRef.current) overlayRef.current.scrollTop = ta.scrollTop;
  }, [input]);

  const accept = (cmd: PdlcCommand) => {
    setInput(`/${cmd.name} `);
    setMenuOpen(false);
    taRef.current?.focus();
  };

  const submit = () => {
    const text = input.trim();
    if ((!text && attachments.length === 0) || busy) return;

    // Continue an open conversation: plain text (no slash-command, no attachments)
    // while a thread is loaded and not awaiting a gate/question.
    if (threadId && !pending && !text.startsWith('/') && attachments.length === 0) {
      setInput('');
      setMenuOpen(false);
      void continueThread(text);
      return;
    }

    // "/brainstorm dark mode" -> command=brainstorm, feature="dark mode" (across newlines)
    const m = text.match(/^\/?(\w[\w-]*)\s*([\s\S]*)$/);
    const command = m ? m[1] : 'brainstorm';
    let feature = m && m[2] ? m[2].trim() : '';
    // Fold attachments into the prompt: any extracted text (utf-8 OR doc) is inlined
    // so the working agent gets it as context; non-text files are noted by name.
    for (const a of attachments) {
      feature += a.text
        ? `\n\n--- attached: ${a.filename} ---\n${a.text}`
        : `\n\n[attached file: ${a.filename}]`;
    }
    const names = attachments.map((a) => a.filename);
    const display = (text || '(attachment)') + (names.length ? `  📎 ${names.join(', ')}` : '');
    const session_id = sessionRef.current;
    setInput('');
    setMenuOpen(false);
    setAttachments([]);
    sessionRef.current = crypto.randomUUID(); // next conversation gets a fresh id
    void start(command, { feature: feature.trim() || undefined, mode, display, session_id });
  };

  const insertNewline = () => {
    const ta = taRef.current;
    if (!ta) return;
    const s = ta.selectionStart;
    const e = ta.selectionEnd;
    const next = `${input.slice(0, s)}\n${input.slice(e)}`;
    setInput(next);
    requestAnimationFrame(() => {
      ta.selectionStart = ta.selectionEnd = s + 1;
    });
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    const mod = e.shiftKey || e.ctrlKey || e.metaKey || e.altKey;
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
      if (e.key === 'Tab') {
        e.preventDefault();
        accept(matches[active]);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setMenuOpen(false);
        return;
      }
      if (e.key === 'Enter' && !mod && matches[active]) {
        e.preventDefault();
        accept(matches[active]);
        return;
      }
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      if (mod) insertNewline(); // any modifier + Enter = newline
      else submit(); // plain Enter = send
    }
  };

  // Inline color-coding (color only — same font as the textarea so the caret stays aligned).
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
                'max-w-[80ch] whitespace-pre-wrap rounded-xl px-4 py-2 text-sm leading-relaxed',
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

      <div
        className="relative mt-2"
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={(e) => { e.preventDefault(); setDragging(false); }}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (e.dataTransfer.files?.length) void addFiles(e.dataTransfer.files);
        }}
      >
        {/* Attachment chips */}
        {(attachments.length > 0 || uploading) && (
          <div className="mb-1 flex flex-wrap gap-1">
            {attachments.map((a) => (
              <span key={a.id} className="flex items-center gap-1 rounded-md border border-border bg-muted/30 px-2 py-0.5 text-xs">
                <Paperclip className="h-3 w-3 text-muted-fg" />
                <span className="max-w-[20ch] truncate">{a.filename}</span>
                <button type="button" onClick={() => setAttachments((x) => x.filter((y) => y.id !== a.id))}
                  className="text-muted-fg hover:text-fg"><X className="h-3 w-3" /></button>
              </span>
            ))}
            {uploading && <span className="px-1 text-xs text-muted-fg">uploading…</span>}
          </div>
        )}

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

        <div className={cn('flex items-start gap-2 rounded-xl border px-3 py-2',
          dragging ? 'border-accent ring-1 ring-accent' : 'border-border')}>
          {busy ? (
            <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-muted-fg" />
          ) : (
            <ChevronRight className={cn('mt-0.5 h-4 w-4 shrink-0', known ? 'text-accent' : 'text-muted-fg')} />
          )}

          {/* highlight overlay + transparent textarea share identical typography */}
          <div className="relative flex-1">
            <div
              ref={overlayRef}
              aria-hidden
              className={cn('pointer-events-none absolute inset-0 overflow-hidden text-fg', FIELD_TYPO)}
            >
              {parsed ? (
                <>
                  <span className={known ? 'text-accent' : 'text-muted-fg'}>{parsed.token}</span>
                  <span>{parsed.rest}</span>
                </>
              ) : (
                input
              )}
              {'​'}
            </div>
            <textarea
              ref={taRef}
              value={input}
              rows={1}
              onChange={(e) => {
                setInput(e.target.value);
                setMenuOpen(true);
                setActive(0);
              }}
              onKeyDown={onKeyDown}
              onScroll={() => {
                if (overlayRef.current && taRef.current) overlayRef.current.scrollTop = taRef.current.scrollTop;
              }}
              onBlur={() => setMenuOpen(false)}
              disabled={busy}
              placeholder="Message, or /command — Enter to send, Shift/Ctrl/Cmd/Alt+Enter for a new line"
              style={{ caretColor: 'var(--fg)', maxHeight: MAX_H }}
              className={cn(
                'block w-full resize-none overflow-y-auto bg-transparent text-transparent outline-none placeholder:text-muted-fg disabled:opacity-60',
                FIELD_TYPO
              )}
            />
          </div>

          {/* attach files */}
          <input
            ref={fileRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => { if (e.target.files) void addFiles(e.target.files); e.target.value = ''; }}
          />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            title="Attach files (or drag & drop)"
            className="mt-0.5 shrink-0 rounded-md p-1 text-muted-fg hover:bg-border/60 hover:text-fg"
          >
            <Paperclip className="h-4 w-4" />
          </button>

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
      className="mt-0.5 flex shrink-0 overflow-hidden rounded-md border border-border text-xs"
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
