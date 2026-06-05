import { useState } from 'react';

import { admin, type RollupDimension } from '@/lib/api';
import { useThread } from '@/store/useThread';
import { PageHeader } from './_shared';

const DIMENSIONS: RollupDimension[] = [
  'initiative',
  'application',
  'squad',
  'domain',
  'roadmap',
  'user_story',
  'agent',
];

export function AdminExports() {
  const orgId = useThread((s) => s.orgId);
  const [dimension, setDimension] = useState<RollupDimension>('initiative');
  const url = admin.exportsCsvUrl(orgId, dimension);

  return (
    <div className="max-w-2xl">
      <PageHeader
        title="Exports"
        subtitle="Download a rollup as CSV (columns: key, events, tokens, usd) for BI tools."
      />
      <div className="rounded-xl border border-border p-4">
        <label className="mb-1 block text-xs uppercase tracking-wide text-muted-fg">
          Dimension
        </label>
        <div className="flex items-center gap-2">
          <select
            value={dimension}
            onChange={(e) => setDimension(e.target.value as RollupDimension)}
            className="rounded border border-border bg-bg px-2 py-1 text-sm"
          >
            {DIMENSIONS.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
          <a
            href={url}
            download={`rollup-${dimension}.csv`}
            className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-accent-fg hover:opacity-90"
          >
            Download CSV
          </a>
          <button
            type="button"
            onClick={() => window.open(url, '_blank')}
            className="rounded-lg border border-border px-3 py-1.5 text-sm text-muted-fg hover:bg-border/60"
          >
            Preview
          </button>
        </div>
        <p className="mt-3 break-all text-xs text-muted-fg">{url}</p>
      </div>
    </div>
  );
}
