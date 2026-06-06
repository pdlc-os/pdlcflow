// Session token + identity, persisted to localStorage. Kept dependency-free so
// `lib/api.ts` can read the token without importing the auth store (no cycle).

export interface Identity {
  user_id: string;
  email: string;
  org_id: string;
  role: string;
}

const TKEY = 'pdlc.token';
const IKEY = 'pdlc.identity';

let _token: string | null = localStorage.getItem(TKEY);
let _onUnauthorized: (() => void) | null = null;

export function getToken(): string | null {
  return _token;
}

export function setSession(token: string, identity: Identity): void {
  _token = token;
  localStorage.setItem(TKEY, token);
  localStorage.setItem(IKEY, JSON.stringify(identity));
}

export function clearSession(): void {
  _token = null;
  localStorage.removeItem(TKEY);
  localStorage.removeItem(IKEY);
}

export function loadIdentity(): Identity | null {
  try {
    return JSON.parse(localStorage.getItem(IKEY) ?? 'null') as Identity | null;
  } catch {
    return null;
  }
}

// The api layer calls this on a 401 so the app can surface the login overlay.
export function onUnauthorized(fn: () => void): void {
  _onUnauthorized = fn;
}

export function fireUnauthorized(): void {
  _onUnauthorized?.();
}
