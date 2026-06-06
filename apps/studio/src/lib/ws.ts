// WebSocket client with auto-reconnect — matches the engine's thread channel.

import type { Pending } from './api';

export interface NightShiftFrame {
  type: 'night_shift.started' | 'night_shift.verdict' | 'night_shift.completed' | 'night_shift.aborted';
  ts?: string;
  stage?: string;
  verdict?: string;
  reason?: string;
  ok?: boolean;
  [k: string]: unknown;
}

export type Frame =
  | { type: 'hello'; thread_id: string }
  | { type: 'interaction.opened'; interaction: Pending }
  | { type: 'thread.completed'; thread_id: string; summary?: Record<string, unknown> }
  | NightShiftFrame
  // live "drafting" preview — a generation streams start → chunk… → done
  | { type: 'token'; thread_id: string; chunk?: string; start?: boolean; done?: boolean; persona?: string }
  | { type: 'status'; phase: string; sub_phase: string | null };

export interface ConnectOpts {
  threadId: string;
  onFrame: (f: Frame) => void;
  onClose?: () => void;
}

export function connect(opts: ConnectOpts): () => void {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const url = `${proto}://${window.location.host}/ws/threads/${opts.threadId}`;
  let socket: WebSocket | null = null;
  let closed = false;
  let attempt = 0;

  const open = () => {
    socket = new WebSocket(url);
    socket.onmessage = (ev) => {
      try {
        opts.onFrame(JSON.parse(ev.data) as Frame);
      } catch {
        /* ignore malformed frames */
      }
    };
    socket.onclose = () => {
      opts.onClose?.();
      if (closed) return;
      const wait = Math.min(30000, 1000 * 2 ** attempt++);
      setTimeout(open, wait);
    };
  };
  open();

  return () => {
    closed = true;
    socket?.close();
  };
}
