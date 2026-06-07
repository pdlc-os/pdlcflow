// The slash commands the engine accepts (POST /v1/commands). Single source of
// truth for the composer's autocomplete + highlighting so they can't drift.

export interface PdlcCommand {
  name: string;
  summary: string;
  arg?: string; // hint for the free-text argument, if the command takes one
}

export const PDLC_COMMANDS: PdlcCommand[] = [
  { name: 'init', summary: 'Scaffold a new project + roadmap' },
  { name: 'brainstorm', summary: 'Start Inception — discovery, ideation, PRD, design', arg: 'feature' },
  { name: 'build', summary: 'Start Construction — implement the planned tasks' },
  { name: 'ship', summary: 'Start Operation — release & deploy' },
  { name: 'decide', summary: 'Record a decision (ADR)', arg: 'decision' },
  { name: 'whatif', summary: 'Explore a what-if scenario', arg: 'scenario' },
  { name: 'doctor', summary: 'Diagnose project health' },
  { name: 'rollback', summary: 'Roll back the last change' },
  { name: 'hotfix', summary: 'Emergency fix outside the normal flow', arg: 'issue' },
  { name: 'night-shift', summary: 'Autonomous overnight run within guardrails' },
  { name: 'pause', summary: 'Pause the active thread' },
  { name: 'resume', summary: 'Resume a paused thread' },
  { name: 'abandon', summary: 'Abandon the active thread' },
  { name: 'release', summary: 'Cut a release' },
  { name: 'override', summary: 'Bypass a guardrail (audited)' },
];

export const COMMAND_NAMES: ReadonlySet<string> = new Set(PDLC_COMMANDS.map((c) => c.name));

/** Parse the leading `/command` token from composer input. */
export function parseCommandToken(input: string): { token: string; name: string; rest: string } | null {
  const m = input.match(/^(\/[\w-]*)(.*)$/s);
  if (!m) return null;
  return { token: m[1], name: m[1].slice(1).toLowerCase(), rest: m[2] };
}

/** True while the user is still typing the command token (no space yet). */
export function inCommandContext(input: string): boolean {
  return /^\/[\w-]*$/.test(input);
}
