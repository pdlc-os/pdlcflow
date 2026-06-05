// One-click mode toggle for Constitution §8 interaction_mode.

import { useState } from 'react';

export function SketchSocraticToggle() {
  const [mode, setMode] = useState<'sketch' | 'socratic'>('socratic');
  return (
    <div className="inline-flex rounded-md border border-border bg-bg p-0.5 text-xs">
      {(['sketch', 'socratic'] as const).map((m) => (
        <button
          key={m}
          onClick={() => setMode(m)}
          className={
            'rounded px-2 py-0.5 ' +
            (m === mode
              ? 'bg-accent text-accent-fg'
              : 'text-muted-fg hover:text-fg')
          }
        >
          {m}
        </button>
      ))}
    </div>
  );
}
