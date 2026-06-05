import { Link } from 'react-router-dom';
import { FileText, FolderOpen } from 'lucide-react';

const MEMORY_KINDS = [
  'CONSTITUTION', 'STATE', 'INTENT', 'ROADMAP', 'DECISIONS',
  'METRICS', 'OVERVIEW', 'CHANGELOG', 'DEPLOYMENTS',
];

export function SideDrawer() {
  return (
    <aside className="w-56 shrink-0 overflow-auto border-r border-border px-3 py-3 text-sm">
      <div className="mb-2 flex items-center gap-2 text-xs uppercase tracking-wide text-muted-fg">
        <FolderOpen className="h-3.5 w-3.5" /> Projects
      </div>
      <div className="space-y-0.5">
        <Link to="/projects/demo-project-alpha" className="block rounded px-2 py-1 hover:bg-border/60">
          demo-project-alpha
        </Link>
        <Link to="/projects/demo-project-beta" className="block rounded px-2 py-1 hover:bg-border/60">
          demo-project-beta
        </Link>
      </div>

      <div className="mt-5 mb-2 flex items-center gap-2 text-xs uppercase tracking-wide text-muted-fg">
        <FileText className="h-3.5 w-3.5" /> Memory
      </div>
      <div className="space-y-0.5 text-muted-fg">
        {MEMORY_KINDS.map((k) => (
          <div key={k} className="rounded px-2 py-0.5 hover:bg-border/60 hover:text-fg">{k}</div>
        ))}
        <div className="rounded px-2 py-0.5 hover:bg-border/60 hover:text-fg">episodes/</div>
      </div>
    </aside>
  );
}
