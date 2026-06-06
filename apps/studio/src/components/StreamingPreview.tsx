import type { Streaming } from '@/store/useThread';

/** Live "drafting" preview — shows an agent's current generation token-by-token
 *  while a turn runs, then clears when the next question/gate/result arrives. */
export function StreamingPreview({ streaming }: { streaming: Streaming | null }) {
  if (!streaming || !streaming.text) return null;
  return (
    <div className="rounded-xl border border-border bg-muted/30 p-3 text-sm">
      <div className="mb-1 flex items-center gap-2 text-xs uppercase tracking-wide text-muted-fg">
        <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-emerald-500" />
        {streaming.persona ? `${streaming.persona} is drafting…` : 'drafting…'}
      </div>
      <p className="whitespace-pre-wrap font-mono text-xs text-fg">
        {streaming.text}
        <span className="ml-0.5 inline-block h-3 w-1 animate-pulse bg-fg align-middle" />
      </p>
    </div>
  );
}
