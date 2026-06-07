import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { useProjects } from '@/store/useProjects';
import { useThread } from '@/store/useThread';

export function ProjectSwitcher() {
  const projects = useProjects((s) => s.projects);
  const create = useProjects((s) => s.create);
  const setProject = useThread((s) => s.setProject);
  const navigate = useNavigate();
  const [name, setName] = useState('');

  const make = () => {
    const n = name.trim();
    if (!n) return;
    const p = create(n);
    setProject(p.id);
    navigate(`/projects/${p.id}`); // straight into the chat
  };

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="mb-2 text-2xl font-semibold tracking-tight">Welcome to pdlcflow</h1>
      <p className="mb-6 text-muted-fg">
        Create a project to start a LangGraph-powered workflow, or open an existing one.
        Visit the{' '}
        <Link className="text-accent hover:underline" to="/admin/live">Nexus Console</Link>{' '}
        for rollups across initiatives, domains, squads, and agents.
      </p>

      {/* Create a project → jump into its chat */}
      <div className="mb-6 flex gap-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && make()}
          placeholder="New project name, e.g. Billing revamp"
          className="flex-1 rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm outline-none focus:border-accent"
        />
        <button
          type="button"
          onClick={make}
          disabled={!name.trim()}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-fg disabled:opacity-50"
        >
          Create project
        </button>
      </div>

      {projects.length === 0 ? (
        <p className="text-sm text-muted-fg">No projects yet — create one above to begin.</p>
      ) : (
        <div className="grid grid-cols-2 gap-3">
          {projects.map((p) => (
            <Link
              key={p.id}
              to={`/projects/${p.id}`}
              onClick={() => setProject(p.id)}
              className="rounded-xl border border-border p-4 hover:border-accent"
            >
              <div className="truncate text-base font-medium">{p.name}</div>
              <div className="mt-1 text-sm text-muted-fg">Open chat →</div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
