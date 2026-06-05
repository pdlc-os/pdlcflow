import { Loader2 } from 'lucide-react';

export function StatusLine() {
  return (
    <footer className="flex h-7 items-center gap-3 border-t border-border px-4 text-xs text-muted-fg">
      <Loader2 className="h-3 w-3 animate-spin" />
      <span>Idle</span>
      <span className="ml-auto font-mono">phase: Inception · sub: Discover</span>
    </footer>
  );
}
