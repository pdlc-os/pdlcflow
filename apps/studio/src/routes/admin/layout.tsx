import { NavLink, Outlet } from 'react-router-dom';
import { cn } from '@/lib/utils';

const ROUTES = [
  { to: 'live',        label: 'Live' },
  { to: 'initiatives', label: 'Initiatives' },
  { to: 'domains',     label: 'Domains' },
  { to: 'squads',      label: 'Squads' },
  { to: 'agents',      label: 'Agents' },
  { to: 'features',    label: 'Features' },
  { to: 'narrative',   label: 'Narrative' },
  { to: 'exports',     label: 'Exports' },
  { to: 'models',      label: 'Models' },
  { to: 'prompts',     label: 'Prompts' },
];

export function AdminLayout() {
  return (
    <div>
      <nav className="mb-4 flex gap-1 border-b border-border text-sm">
        {ROUTES.map((r) => (
          <NavLink
            key={r.to}
            to={r.to}
            className={({ isActive }) =>
              cn(
                'border-b-2 px-3 py-2',
                isActive
                  ? 'border-accent text-fg'
                  : 'border-transparent text-muted-fg hover:text-fg'
              )
            }
          >
            {r.label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  );
}
