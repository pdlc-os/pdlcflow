// MCP tool servers (PRD-09): org-scoped registry of external tool servers,
// with allowlist-by-checkbox (Test lists the server's tools), persona/phase
// bindings, and write-only bearer tokens. Unbound servers are inert; nothing
// executes unless the operator sets PDLC_WIRE_MCP=true.

import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { admin, type MCPBinding, type MCPServer, type MCPServerBody, type MCPTemplate } from '@/lib/api';
import { useThread } from '@/store/useThread';
import { ErrorNotice, Loading, PageHeader } from './_shared';

const inputCls = 'rounded border border-border bg-bg px-2 py-1';
const btnCls =
  'rounded border border-border px-2 py-1 text-xs text-muted-fg hover:bg-border/60 disabled:opacity-40';

const PERSONAS = ['atlas', 'bolt', 'echo', 'friday', 'jarvis', 'muse', 'neo', 'phantom', 'pulse', 'sentinel'];
const PHASES = ['', 'Initialization', 'Inception', 'Construction', 'Operation'];

export function AdminMCP() {
  const orgId = useThread((s) => s.orgId);
  const servers = useQuery({
    queryKey: ['admin', 'mcpServers', orgId],
    queryFn: () => admin.listMCPServers(orgId),
    refetchOnWindowFocus: false,
  });
  const [adding, setAdding] = useState(false);

  if (servers.isLoading) return <Loading />;
  if (servers.isError) return <ErrorNotice error={servers.error} />;
  const rows = servers.data?.servers ?? [];

  return (
    <div className="max-w-4xl">
      <PageHeader
        title="Tools (MCP servers)"
        subtitle={
          <>
            Register external MCP tool servers, allow specific tools, and bind them to
            personas (optionally per phase). Empty allowlist = deny all. Unbound servers are
            inert; execution requires <code>PDLC_WIRE_MCP=true</code> on the engine.
          </>
        }
      />

      <div className="mb-3">
        <button onClick={() => setAdding(!adding)} className={btnCls}>
          {adding ? 'Close' : '+ Add server'}
        </button>
      </div>
      {adding ? (
        <ServerForm orgId={orgId} onDone={() => setAdding(false)} />
      ) : null}

      <div className="space-y-3">
        {rows.length === 0 && !adding ? (
          <div className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted-fg">
            No MCP servers registered — add one to give agents tools.
          </div>
        ) : null}
        {rows.map((s) => (
          <ServerCard key={s.id} orgId={orgId} server={s} />
        ))}
      </div>
    </div>
  );
}

function ServerForm({
  orgId,
  server,
  onDone,
}: {
  orgId: string;
  server?: MCPServer;
  onDone: () => void;
}) {
  const qc = useQueryClient();
  const templates = useQuery({
    queryKey: ['admin', 'mcpTemplates', orgId],
    queryFn: () => admin.listMCPTemplates(orgId),
    refetchOnWindowFocus: false,
    enabled: !server,
  });
  const [name, setName] = useState(server?.name ?? '');
  const [transport, setTransport] = useState<'http' | 'stdio'>(server?.transport ?? 'http');
  const [url, setUrl] = useState(server?.url ?? '');
  const [command, setCommand] = useState(server?.command ?? '');
  const [args, setArgs] = useState((server?.args ?? []).join(' '));
  const [token, setToken] = useState('');
  const [tools, setTools] = useState((server?.allowed_tools ?? []).join(', '));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const applyTemplate = (t: MCPTemplate) => {
    setName(t.name);
    setTransport(t.transport);
    setUrl(t.url ?? '');
    setCommand(t.command ?? '');
    setArgs((t.args ?? []).join(' '));
    setTools(t.allowed_tools.join(', '));
  };

  const save = async () => {
    setBusy(true);
    setErr(null);
    const body: MCPServerBody = {
      name,
      transport,
      url: transport === 'http' ? url : null,
      command: transport === 'stdio' ? command : null,
      args: args.split(/\s+/).filter(Boolean),
      allowed_tools: tools.split(',').map((t) => t.trim()).filter(Boolean),
      enabled: server?.enabled ?? true,
      ...(token ? { auth_token: token } : {}),
    };
    try {
      if (server) await admin.updateMCPServer(orgId, server.id, body);
      else await admin.createMCPServer(orgId, body);
      await qc.invalidateQueries({ queryKey: ['admin', 'mcpServers', orgId] });
      onDone();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mb-3 space-y-2 rounded-xl border border-border p-3 text-xs">
      {!server && (templates.data?.templates?.length ?? 0) > 0 ? (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-muted-fg">Templates:</span>
          {templates.data?.templates.map((t) => (
            <button key={t.id} onClick={() => applyTemplate(t)} title={t.note} className={btnCls}>
              {t.id}
            </button>
          ))}
        </div>
      ) : null}
      <div className="flex items-center gap-2">
        <input value={name} onChange={(e) => setName(e.target.value)}
               placeholder="name (kebab-case)" className={`${inputCls} w-44`} />
        <select value={transport}
                onChange={(e) => setTransport(e.target.value as 'http' | 'stdio')}
                className={inputCls}>
          <option value="http">http</option>
          <option value="stdio">stdio (self-host only)</option>
        </select>
        {transport === 'http' ? (
          <input value={url} onChange={(e) => setUrl(e.target.value)}
                 placeholder="https://…/mcp" className={`${inputCls} flex-1`} />
        ) : (
          <>
            <input value={command} onChange={(e) => setCommand(e.target.value)}
                   placeholder="command" className={`${inputCls} w-32`} />
            <input value={args} onChange={(e) => setArgs(e.target.value)}
                   placeholder="args (space-separated)" className={`${inputCls} flex-1`} />
          </>
        )}
      </div>
      <div className="flex items-center gap-2">
        <input type="password" autoComplete="off" value={token}
               onChange={(e) => setToken(e.target.value)}
               placeholder={server?.has_auth ? '●●● rotate bearer token' : 'bearer token (optional)'}
               className={`${inputCls} w-56`} />
        <input value={tools} onChange={(e) => setTools(e.target.value)}
               placeholder="allowed tools, comma-separated (empty = deny all)"
               className={`${inputCls} flex-1`} />
      </div>
      {transport === 'stdio' ? (
        <div className="text-red-400">
          ⚠ stdio servers execute commands on the engine host — single-user self-host only
          (requires PDLC_ENABLE_STDIO_MCP).
        </div>
      ) : null}
      <div className="flex items-center gap-2">
        <button onClick={save} disabled={busy || !name} className={btnCls}>
          {server ? 'Save changes' : 'Register server'}
        </button>
        <button onClick={onDone} className={btnCls}>Cancel</button>
        {err ? <span className="text-red-400">{err}</span> : null}
      </div>
    </div>
  );
}

function ServerCard({ orgId, server }: { orgId: string; server: MCPServer }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [testedTools, setTestedTools] = useState<{ name: string; description: string }[] | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = () => qc.invalidateQueries({ queryKey: ['admin', 'mcpServers', orgId] });

  const test = async () => {
    setBusy(true);
    setTestResult('testing…');
    setTestedTools(null);
    try {
      const r = await admin.testMCPServer(orgId, server.id);
      if (r.ok) {
        setTestResult(`✓ ${r.latency_ms} ms · ${r.tools?.length ?? 0} tools`);
        setTestedTools(r.tools ?? []);
      } else {
        setTestResult(`✗ ${r.error}`);
      }
    } catch (e) {
      setTestResult(`✗ ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const allowTool = async (tool: string, allowed: boolean) => {
    const next = allowed
      ? [...server.allowed_tools, tool]
      : server.allowed_tools.filter((t) => t !== tool);
    await admin.updateMCPServer(orgId, server.id, {
      name: server.name, transport: server.transport, url: server.url,
      command: server.command, args: server.args, allowed_tools: next,
      enabled: server.enabled,
    });
    await refresh();
  };

  const toggleEnabled = async () => {
    await admin.updateMCPServer(orgId, server.id, {
      name: server.name, transport: server.transport, url: server.url,
      command: server.command, args: server.args,
      allowed_tools: server.allowed_tools, enabled: !server.enabled,
    });
    await refresh();
  };

  const remove = async () => {
    if (!window.confirm(`Delete MCP server "${server.name}" and its bindings?`)) return;
    await admin.deleteMCPServer(orgId, server.id);
    await refresh();
  };

  return (
    <div className="space-y-2 rounded-xl border border-border p-3 text-xs">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">{server.name}</span>
        <span className="rounded bg-border/50 px-1">{server.transport}</span>
        {server.has_auth ? <span className="text-muted-fg">●●● token set</span> : null}
        <span className="flex-1 truncate text-muted-fg">
          {server.url ?? `${server.command} ${server.args.join(' ')}`}
        </span>
        <button onClick={toggleEnabled} className={btnCls}>
          {server.enabled ? 'Disable' : 'Enable'}
        </button>
        <button onClick={test} disabled={busy} className={btnCls}>Test</button>
        <button onClick={() => setEditing(!editing)} className={btnCls}>Edit</button>
        <button onClick={remove} className={btnCls}>Delete</button>
      </div>
      {testResult ? <div className="text-muted-fg">{testResult}</div> : null}

      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-muted-fg">Allowed tools:</span>
        {server.allowed_tools.length === 0 ? (
          <span className="text-red-400">none — deny all</span>
        ) : (
          server.allowed_tools.map((t) => (
            <span key={t} className="rounded bg-green-500/20 px-1 text-green-500">{t}</span>
          ))
        )}
      </div>
      {testedTools ? (
        <div className="flex flex-wrap items-center gap-2 rounded border border-border p-2">
          <span className="text-muted-fg">Server offers:</span>
          {testedTools.map((t) => (
            <label key={t.name} className="flex items-center gap-1" title={t.description}>
              <input
                type="checkbox"
                checked={server.allowed_tools.includes(t.name)}
                onChange={(e) => allowTool(t.name, e.target.checked)}
              />
              {t.name}
            </label>
          ))}
          {testedTools.length === 0 ? <span className="text-muted-fg">no tools reported</span> : null}
        </div>
      ) : null}

      {editing ? (
        <ServerForm orgId={orgId} server={server} onDone={() => { setEditing(false); void refresh(); }} />
      ) : (
        <BindingsEditor orgId={orgId} server={server} onSaved={refresh} />
      )}
    </div>
  );
}

function BindingsEditor({
  orgId,
  server,
  onSaved,
}: {
  orgId: string;
  server: MCPServer;
  onSaved: () => void;
}) {
  const [bindings, setBindings] = useState<MCPBinding[]>(server.bindings);
  const [persona, setPersona] = useState('muse');
  const [phase, setPhase] = useState('');
  const [busy, setBusy] = useState(false);

  const dirty = JSON.stringify(bindings) !== JSON.stringify(server.bindings);

  const save = async () => {
    setBusy(true);
    try {
      await admin.setMCPBindings(orgId, server.id, bindings);
      onSaved();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-muted-fg">Bindings:</span>
      {bindings.map((b, i) => (
        <span key={i} className="flex items-center gap-1 rounded bg-border/50 px-1">
          {b.persona}{b.phase ? ` @ ${b.phase}` : ''}
          <button onClick={() => setBindings(bindings.filter((_, j) => j !== i))}>✕</button>
        </span>
      ))}
      <select value={persona} onChange={(e) => setPersona(e.target.value)} className={inputCls}>
        {PERSONAS.map((p) => <option key={p} value={p}>{p}</option>)}
      </select>
      <select value={phase} onChange={(e) => setPhase(e.target.value)} className={inputCls}>
        {PHASES.map((p) => <option key={p} value={p}>{p || 'any phase'}</option>)}
      </select>
      <button
        onClick={() => setBindings([...bindings, { persona, phase: phase || null }])}
        className={btnCls}
      >
        + Bind
      </button>
      {dirty ? (
        <button onClick={save} disabled={busy} className={btnCls}>
          Save bindings
        </button>
      ) : null}
    </div>
  );
}
