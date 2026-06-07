/* eslint-disable react-refresh/only-export-components -- shared module: components + helpers co-located by design */
import type { ReactNode } from 'react';
import type { RollupRow } from '@/lib/api';

export function PageHeader({ title, subtitle }: { title: string; subtitle?: ReactNode }) {
  return (
    <div className="mb-4">
      <h2 className="mb-1 text-lg font-semibold">{title}</h2>
      {subtitle ? <p className="text-sm text-muted-fg">{subtitle}</p> : null}
    </div>
  );
}

export function StateNotice({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted-fg">
      {children}
    </div>
  );
}

export function Loading() {
  return <StateNotice>Loading…</StateNotice>;
}

export function ErrorNotice({ error }: { error: unknown }) {
  return (
    <div className="rounded-xl border border-border bg-border/30 p-4 text-sm text-fg">
      Failed to load: {error instanceof Error ? error.message : String(error)}
    </div>
  );
}

const NUM = new Intl.NumberFormat('en-US');
const USD = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });

export const fmtInt = (n: number) => NUM.format(n);
export const fmtUsd = (n: number) => USD.format(n);

export function RollupTable({
  rows,
  keyLabel = 'Key',
}: {
  rows: RollupRow[];
  keyLabel?: string;
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-border">
      <table className="w-full text-sm">
        <thead className="bg-border/40 text-left text-xs uppercase tracking-wide text-muted-fg">
          <tr>
            <th className="px-3 py-2 font-medium">{keyLabel}</th>
            <th className="px-3 py-2 text-right font-medium">Events</th>
            <th className="px-3 py-2 text-right font-medium">Tokens</th>
            <th className="px-3 py-2 text-right font-medium">USD</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className="border-t border-border">
              <td className="px-3 py-2 font-medium">{r.key}</td>
              <td className="px-3 py-2 text-right tabular-nums">{fmtInt(r.events)}</td>
              <td className="px-3 py-2 text-right tabular-nums text-muted-fg">{fmtInt(r.tokens)}</td>
              <td className="px-3 py-2 text-right tabular-nums text-muted-fg">{fmtUsd(r.usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
