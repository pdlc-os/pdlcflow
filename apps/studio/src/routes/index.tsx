import { Link } from 'react-router-dom';

export function ProjectSwitcher() {
  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="mb-2 text-2xl font-semibold tracking-tight">Welcome to pdlcflow</h1>
      <p className="mb-6 text-muted-fg">
        Phase A scaffold — pick a project to enter the LangGraph + Bedrock-powered workflow,
        or visit the <Link className="text-accent hover:underline" to="/admin/live">Nexus Console</Link>{' '}
        for rollups across initiatives, domains, squads, and agents.
      </p>
      <div className="grid grid-cols-2 gap-3">
        {['demo-project-alpha', 'demo-project-beta'].map((p) => (
          <Link
            key={p}
            to={`/projects/${p}`}
            className="rounded-xl border border-border p-4 hover:border-accent"
          >
            <div className="text-base font-medium">{p}</div>
            <div className="mt-1 text-sm text-muted-fg">No active claim</div>
          </Link>
        ))}
      </div>
    </div>
  );
}
