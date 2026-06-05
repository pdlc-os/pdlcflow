// QuestionCard — renders a user_input_required round (Socratic/Sketch + UX
// Discovery). Text inputs per question; when the interrupt carries a visual
// options spec, the companion sits beside it and clicking a card fills the
// matching answer (keys q0, q1, … map to question index).

import { useState } from 'react';

import { BrainstormVisualCompanion } from './BrainstormVisualCompanion';
import type { Pending } from '@/lib/api';

interface Props {
  pending: Pending;
  busy: boolean;
  onSubmit: (answers: string[]) => void;
}

export function QuestionCard({ pending, busy, onSubmit }: Props) {
  const questions = pending.payload.questions ?? [];
  const drafts = pending.payload.drafts ?? [];
  const visual = pending.payload.visual ?? null;

  const [answers, setAnswers] = useState<string[]>(() =>
    questions.map((_, i) => drafts?.[i] ?? '')
  );
  const [selections, setSelections] = useState<Record<string, string>>({});

  const setAnswer = (i: number, v: string) =>
    setAnswers((a) => a.map((x, idx) => (idx === i ? v : x)));

  // Companion click → fill the answer slot for that screen's key (q0 → index 0).
  const onSelect = (key: string, title: string) => {
    setSelections((s) => ({ ...s, [key]: title }));
    const idx = Number(key.replace(/^q/, ''));
    if (!Number.isNaN(idx)) setAnswer(idx, title);
  };

  const hasVisual = !!visual && visual.screens.length > 0;

  return (
    <div className={hasVisual ? 'grid grid-cols-[1fr_320px] gap-4' : ''}>
      <div className="rounded-2xl border border-border bg-bg p-4">
        <div className="mb-3 text-xs uppercase tracking-wide text-muted-fg">
          {pending.payload.context ?? 'Your input'}
        </div>
        <div className="flex flex-col gap-3">
          {questions.map((q, i) => (
            <label key={i} className="flex flex-col gap-1">
              <span className="text-sm font-medium">{q}</span>
              <input
                value={answers[i] ?? ''}
                onChange={(e) => setAnswer(i, e.target.value)}
                placeholder="Your answer…"
                className="rounded-lg border border-border bg-bg px-3 py-1.5 text-sm outline-none focus:border-accent"
              />
            </label>
          ))}
        </div>
        <div className="mt-4 flex justify-end">
          <button
            onClick={() => onSubmit(answers)}
            disabled={busy}
            className="rounded-md bg-accent px-3 py-1.5 text-sm text-accent-fg hover:opacity-90 disabled:opacity-60"
          >
            Submit answers
          </button>
        </div>
      </div>

      {hasVisual && (
        <BrainstormVisualCompanion visual={visual!} selections={selections} onSelect={onSelect} />
      )}
    </div>
  );
}
