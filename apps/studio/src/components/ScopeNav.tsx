import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { ChevronDown, ChevronRight, Pencil, Trash2 } from 'lucide-react';

import { entities } from '@/lib/api';
import { useScope } from '@/store/useScope';
import { useThread } from '@/store/useThread';
import { cn } from '@/lib/utils';

interface Item { id: string; name: string }

/** A nav dropdown: pick an item, create one inline, or rename/delete it. */
function Dropdown({
  label, items, value, onSelect, onCreate, onRename, onDelete, createPlaceholder, disabled,
}: {
  label: string;
  items: Item[];
  value: string | null;
  onSelect: (id: string) => void;
  onCreate?: (name: string) => void;
  onRename?: (id: string, current: string) => void;
  onDelete?: (id: string, name: string) => void;
  createPlaceholder?: string;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const current = items.find((i) => i.id === value)?.name;

  return (
    <div className="relative">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 rounded-md px-2 py-0.5 text-muted-fg hover:bg-border/60 hover:text-fg disabled:opacity-40"
      >
        <span className={current ? 'max-w-[12ch] truncate text-fg' : ''}>{current ?? label}</span>
        <ChevronDown className="h-3.5 w-3.5" />
      </button>
      {open && !disabled && (
        <div
          className="absolute z-30 mt-1 w-60 rounded-lg border border-border bg-bg p-1 shadow-lg"
          onMouseLeave={() => setOpen(false)}
        >
          {items.length === 0 && <div className="px-2 py-1 text-xs text-muted-fg">none yet</div>}
          {items.map((i) => (
            <div key={i.id} className="group flex items-center rounded hover:bg-border/60">
              <button
                type="button"
                onClick={() => { onSelect(i.id); setOpen(false); }}
                className={cn('flex-1 truncate rounded px-2 py-1 text-left text-sm', i.id === value && 'text-accent')}
              >
                {i.name}
              </button>
              {onRename && (
                <button type="button" title="Rename" onClick={() => { onRename(i.id, i.name); setOpen(false); }}
                  className="px-1 text-muted-fg opacity-0 hover:text-fg group-hover:opacity-100">
                  <Pencil className="h-3 w-3" />
                </button>
              )}
              {onDelete && (
                <button type="button" title="Delete" onClick={() => { onDelete(i.id, i.name); setOpen(false); }}
                  className="px-1 text-muted-fg opacity-0 hover:text-red-500 group-hover:opacity-100">
                  <Trash2 className="h-3 w-3" />
                </button>
              )}
            </div>
          ))}
          {onCreate && (
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && name.trim()) { onCreate(name.trim()); setName(''); setOpen(false); }
              }}
              placeholder={createPlaceholder ?? '+ New…'}
              className="mt-1 w-full rounded border-t border-border bg-muted/30 px-2 py-1 text-xs outline-none"
            />
          )}
        </div>
      )}
    </div>
  );
}

/** Repo dropdown with a connect form (URL + token). Filtered to the selected squad. */
function RepoDropdown({ org, squadId }: { org: string; squadId: string | null }) {
  const repoId = useScope((s) => s.repoId);
  const setScope = useScope((s) => s.setScope);
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: '', url: '', token: '' });

  const { data } = useQuery({
    queryKey: ['repos', org, squadId],
    queryFn: () => entities.repositories(org, squadId ?? undefined),
    enabled: !!org && !!squadId,
  });
  const repos = data?.repositories ?? [];
  const current = repos.find((r) => r.id === repoId)?.name;

  const connect = async () => {
    if (!squadId || !form.name.trim() || !form.url.trim()) return;
    const r = await entities.createRepository(org, {
      squad_id: squadId, name: form.name.trim(), url: form.url.trim(),
      token: form.token.trim() || undefined,
    });
    setForm({ name: '', url: '', token: '' });
    await qc.invalidateQueries({ queryKey: ['repos', org, squadId] });
    setScope('repo', r.id);
    setOpen(false);
  };

  return (
    <div className="relative">
      <button
        type="button"
        disabled={!squadId}
        onClick={() => setOpen((o) => !o)}
        title={squadId ? 'GitHub repository' : 'Select a squad first'}
        className="flex items-center gap-1 rounded-md px-2 py-0.5 text-muted-fg hover:bg-border/60 hover:text-fg disabled:opacity-40"
      >
        <span className={current ? 'max-w-[12ch] truncate text-fg' : ''}>{current ?? 'Repo'}</span>
        <ChevronDown className="h-3.5 w-3.5" />
      </button>
      {open && squadId && (
        <div className="absolute z-30 mt-1 w-72 rounded-lg border border-border bg-bg p-1 shadow-lg"
             onMouseLeave={() => setOpen(false)}>
          {repos.length === 0 && <div className="px-2 py-1 text-xs text-muted-fg">no repos connected</div>}
          {repos.map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => { setScope('repo', r.id); setOpen(false); }}
              className={cn('block w-full truncate rounded px-2 py-1 text-left text-sm hover:bg-border/60',
                r.id === repoId && 'text-accent')}
              title={r.url}
            >
              {r.name}
            </button>
          ))}
          <div className="mt-1 space-y-1 border-t border-border pt-1">
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="repo name" className="w-full rounded bg-muted/30 px-2 py-1 text-xs outline-none" />
            <input value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })}
              placeholder="https://github.com/org/repo" className="w-full rounded bg-muted/30 px-2 py-1 text-xs outline-none" />
            <input value={form.token} onChange={(e) => setForm({ ...form, token: e.target.value })}
              type="password" placeholder="access token (stored encrypted)" className="w-full rounded bg-muted/30 px-2 py-1 text-xs outline-none" />
            <button type="button" onClick={() => void connect()}
              className="w-full rounded bg-accent px-2 py-1 text-xs font-medium text-accent-fg">Connect repository</button>
          </div>
        </div>
      )}
    </div>
  );
}

const Sep = () => <ChevronRight className="h-3.5 w-3.5 text-muted-fg" />;

/** The hierarchy nav: Org · Domain · Squad · Repo · Initiative · Project. */
export function ScopeNav() {
  const orgId = useThread((s) => s.orgId);
  const projectId = useThread((s) => s.projectId);
  const setProject = useThread((s) => s.setProject);
  const { domainId, squadId, initiativeId, setScope } = useScope();
  const qc = useQueryClient();
  const navigate = useNavigate();

  const domains = useQuery({ queryKey: ['domains', orgId], queryFn: () => entities.domains(orgId), enabled: !!orgId });
  const squads = useQuery({ queryKey: ['squads', orgId], queryFn: () => entities.squads(orgId), enabled: !!orgId });
  const inits = useQuery({ queryKey: ['initiatives', orgId], queryFn: () => entities.initiatives(orgId), enabled: !!orgId });
  const projects = useQuery({ queryKey: ['projects', orgId], queryFn: () => entities.projects(orgId), enabled: !!orgId });

  const refresh = (key: string) => qc.invalidateQueries({ queryKey: [key, orgId] });

  const ensureSquad = async (): Promise<string> => {
    if (squadId) return squadId;
    const sq = await entities.createSquad(orgId, 'General', domainId);
    await refresh('squads');
    setScope('squad', sq.id);
    return sq.id;
  };

  type Kind = 'domains' | 'squads' | 'initiatives' | 'projects';
  const renameEntity = async (kind: Kind, id: string, current: string) => {
    const next = window.prompt('Rename to:', current);
    if (next && next.trim() && next.trim() !== current) {
      await entities.rename(kind, orgId, id, next.trim());
      await refresh(kind);
    }
  };
  const deleteEntity = async (kind: Kind, id: string, name: string, warn: string, after?: () => void) => {
    if (!window.confirm(`Delete "${name}"?\n\n${warn}\n\nThis cannot be undone.`)) return;
    await entities.remove(kind, orgId, id);
    await refresh(kind);
    after?.();
  };

  return (
    <>
      <span className="text-muted-fg">Org</span>
      <Sep />
      <Dropdown
        label="Domain" value={domainId} items={domains.data?.domains ?? []}
        onSelect={(id) => setScope('domain', id)}
        onCreate={async (name) => { const d = await entities.createDomain(orgId, name); await refresh('domains'); setScope('domain', d.id); }}
        onRename={(id, cur) => void renameEntity('domains', id, cur)}
        onDelete={(id, name) => void deleteEntity('domains', id, name, 'Its squads are kept (just un-grouped).',
          () => { if (domainId === id) setScope('domain', null); })}
        createPlaceholder="+ New domain…"
      />
      <Sep />
      <Dropdown
        label="Squad" value={squadId} items={squads.data?.squads ?? []}
        onSelect={(id) => setScope('squad', id)}
        onCreate={async (name) => { const s = await entities.createSquad(orgId, name, domainId); await refresh('squads'); setScope('squad', s.id); }}
        onRename={(id, cur) => void renameEntity('squads', id, cur)}
        onDelete={(id, name) => void deleteEntity('squads', id, name,
          'This also deletes the squad’s projects (and their conversations), repos, and links.',
          () => { if (squadId === id) { setScope('squad', null); setScope('repo', null); } })}
        createPlaceholder="+ New squad…"
      />
      <Sep />
      <RepoDropdown org={orgId} squadId={squadId} />
      <Sep />
      <Dropdown
        label="Initiative" value={initiativeId} items={inits.data?.initiatives ?? []}
        onSelect={(id) => setScope('initiative', id)}
        onCreate={async (name) => { const i = await entities.createInitiative(orgId, name); await refresh('initiatives'); setScope('initiative', i.id); }}
        onRename={(id, cur) => void renameEntity('initiatives', id, cur)}
        onDelete={(id, name) => void deleteEntity('initiatives', id, name, 'Projects linked to it are kept (just un-linked).',
          () => { if (initiativeId === id) setScope('initiative', null); })}
        createPlaceholder="+ New initiative…"
      />
      <Sep />
      <Dropdown
        label="Project" value={projectId} items={projects.data?.projects ?? []}
        onSelect={(id) => { setProject(id); navigate(`/projects/${id}`); }}
        onCreate={async (name) => {
          const sq = await ensureSquad();
          const p = await entities.createProject(orgId, { name, squad_id: sq });
          await refresh('projects');
          setProject(p.id);
          navigate(`/projects/${p.id}`);
        }}
        onRename={(id, cur) => void renameEntity('projects', id, cur)}
        onDelete={(id, name) => void deleteEntity('projects', id, name, 'This also deletes its conversations.',
          () => { if (projectId === id) navigate('/'); })}
        createPlaceholder="+ New project…"
      />
    </>
  );
}
