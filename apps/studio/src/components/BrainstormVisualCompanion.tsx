// BrainstormVisualCompanion — the in-browser visual companion (plan §14.13).
//
// Renders the `visual` spec that rides a brainstorm interrupt payload, in the
// SAME view as the chat (no separate localhost:7352 server). Option screens are
// clickable: choosing a card answers that question via `onSelect(key, title)`.

import { Check } from 'lucide-react';

import type { VisualScreen, VisualSpec } from '@/lib/api';
import { cn } from '@/lib/utils';

interface Props {
  visual: VisualSpec;
  selections?: Record<string, string>;
  onSelect?: (key: string, choiceTitle: string) => void;
}

export function BrainstormVisualCompanion({ visual, selections = {}, onSelect }: Props) {
  return (
    <aside className="flex flex-col gap-4 rounded-2xl border border-border bg-bg/60 p-4">
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-fg">
        <span className="grid h-5 w-5 place-items-center rounded bg-accent/10 text-accent">◧</span>
        Visual companion
      </div>
      {visual.screens.map((screen, i) => (
        <Screen key={i} screen={screen} selections={selections} onSelect={onSelect} />
      ))}
    </aside>
  );
}

function Screen({
  screen,
  selections,
  onSelect,
}: {
  screen: VisualScreen;
  selections: Record<string, string>;
  onSelect?: (key: string, choiceTitle: string) => void;
}) {
  return (
    <div className="rounded-xl border border-border bg-bg p-3">
      <div className="mb-0.5 text-sm font-semibold">{screen.title}</div>
      {screen.subtitle && <div className="mb-2 text-xs text-muted-fg">{screen.subtitle}</div>}

      {screen.type === 'options' && (
        <div className="flex flex-col gap-2">
          {screen.options?.map((opt) => {
            const selected = screen.key ? selections[screen.key] === opt.title : false;
            return (
              <button
                key={opt.choice}
                onClick={() => screen.key && onSelect?.(screen.key, opt.title)}
                className={cn(
                  'flex items-start gap-3 rounded-lg border px-3 py-2 text-left transition',
                  selected
                    ? 'border-accent bg-accent/10'
                    : 'border-border hover:border-accent/60 hover:bg-border/40'
                )}
              >
                <span
                  className={cn(
                    'mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full text-xs font-semibold uppercase',
                    selected ? 'bg-accent text-accent-fg' : 'bg-border/60 text-muted-fg'
                  )}
                >
                  {selected ? <Check className="h-3.5 w-3.5" /> : opt.choice}
                </span>
                <span>
                  <span className="block text-sm font-medium">{opt.title}</span>
                  {opt.description && (
                    <span className="block text-xs text-muted-fg">{opt.description}</span>
                  )}
                </span>
              </button>
            );
          })}
        </div>
      )}

      {screen.type === 'mermaid' && (
        <pre className="overflow-x-auto rounded-lg bg-border/40 p-3 text-xs leading-relaxed text-fg">
          {screen.mermaid}
        </pre>
      )}

      {screen.type === 'mockup' && (
        <div className="whitespace-pre-wrap rounded-lg bg-border/40 p-3 text-xs leading-relaxed">
          {screen.body}
        </div>
      )}
    </div>
  );
}
