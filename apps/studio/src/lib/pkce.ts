// PKCE (RFC 7636) helpers for the OIDC auth-code flow. Uses the Web Crypto API
// (S256 challenge) — no dependencies. The verifier is stashed in sessionStorage
// across the IdP redirect and consumed once on callback.

const VERIFIER_KEY = 'pdlc.pkce.verifier';

function base64UrlEncode(bytes: Uint8Array): string {
  let s = '';
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function randomVerifier(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return base64UrlEncode(bytes);
}

export async function challengeFor(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
  return base64UrlEncode(new Uint8Array(digest));
}

/** Create a verifier (persisted for the callback) + its S256 challenge + state. */
export async function beginPkce(): Promise<{ challenge: string; state: string }> {
  const verifier = randomVerifier();
  sessionStorage.setItem(VERIFIER_KEY, verifier);
  const state = randomVerifier();
  sessionStorage.setItem('pdlc.pkce.state', state);
  return { challenge: await challengeFor(verifier), state };
}

export function takeVerifier(): string | null {
  const v = sessionStorage.getItem(VERIFIER_KEY);
  sessionStorage.removeItem(VERIFIER_KEY);
  return v;
}

export function expectedState(): string | null {
  const s = sessionStorage.getItem('pdlc.pkce.state');
  sessionStorage.removeItem('pdlc.pkce.state');
  return s;
}
