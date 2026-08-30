/**
 * codeguru-auth — the only place the Code Guru platform talks to Code Coach's
 * authentication API.
 *
 * ========================= COPY - DO NOT EDIT =========================
 * The master copy of this file lives in the code-coach repo at
 * portal/src/lib/codeguru-auth.js.
 *
 * If you need to change how Study Guider talks to Code Coach's auth API,
 * change it THERE and copy the file here again. Editing this copy makes the
 * three services drift apart, and the field-name mismatches that follow
 * (identifier vs email, full_name vs fullName) are exactly what this file
 * exists to prevent.
 * =====================================================================
 *
 * The field names below come straight from the Code Coach API contract
 * (integration/API_CONTRACT.md). They are wire format, not style:
 *
 *   login    sends  { identifier, password, client_name }
 *   register sends  { full_name, email, password, client_name }
 *
 * Renaming any of them to camelCase makes the request fail validation.
 *
 * Nothing here reads its own configuration. The Code Coach base URL and the
 * dev-login flag are passed in by the caller, because every frontend in this
 * platform uses a different bundler (Vite's import.meta.env, Next's
 * process.env.NEXT_PUBLIC_*) and this file has to stay identical in all three
 * repos.
 */

// ── Storage keys ──
// One namespace, so a service can clear the platform session without touching
// its own local keys.
const ACCESS_TOKEN_KEY = 'codeguru.accessToken';
const REFRESH_TOKEN_KEY = 'codeguru.refreshToken';
const EXPIRES_AT_KEY = 'codeguru.expiresAt';
const USER_KEY = 'codeguru.user';

/** An auth call that failed. `status` is the HTTP status, 0 if the request never landed. */
export class AuthError extends Error {
  constructor(message, status = 0) {
    super(message);
    this.name = 'AuthError';
    this.status = status;
  }
}

function trimBase(baseUrl) {
  return String(baseUrl || '').replace(/\/+$/, '');
}

/**
 * Code Coach reports failures as {"detail": "human readable reason"}. Surface
 * that text: it is written to be shown to a student ("Invalid credentials.",
 * "An account with that email already exists."), so inventing our own wording
 * would be strictly worse.
 */
async function readError(response) {
  let detail = '';
  try {
    const body = await response.json();
    detail = body?.detail || '';
  } catch {
    // Non-JSON body (a proxy error page, an empty 502). Fall through.
  }
  if (detail) return detail;
  if (response.status === 429) return 'Too many attempts. Please wait a moment and try again.';
  return 'Request failed (' + response.status + ').';
}

async function postJson(baseUrl, path, body) {
  let response;
  try {
    response = await fetch(trimBase(baseUrl) + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch {
    // DNS failure, connection refused, CORS rejection. The service being down
    // must not read to the student as "wrong password".
    throw new AuthError(
      'Cannot reach Code Coach at ' + trimBase(baseUrl) + '. Is the backend running?',
      0,
    );
  }

  if (!response.ok) throw new AuthError(await readError(response), response.status);
  return response.json();
}

// ── The five auth calls ──

/** POST /api/v1/auth/login → the full AuthResponse (user, auth_session, tokens). */
export function login(baseUrl, { identifier, password, clientName }) {
  return postJson(baseUrl, '/api/v1/auth/login', {
    identifier,
    password,
    client_name: clientName,
  });
}

/** POST /api/v1/auth/register → the same shape as login. */
export function register(baseUrl, { fullName, email, password, clientName }) {
  return postJson(baseUrl, '/api/v1/auth/register', {
    full_name: fullName,
    email,
    password,
    client_name: clientName,
  });
}

/** POST /api/v1/auth/refresh. Refresh tokens rotate — always store the new one. */
export function refresh(baseUrl, refreshToken) {
  return postJson(baseUrl, '/api/v1/auth/refresh', { refresh_token: refreshToken });
}

/** GET /api/v1/auth/me — the token check every service uses to verify a caller. */
export async function me(baseUrl, accessToken) {
  let response;
  try {
    response = await fetch(trimBase(baseUrl) + '/api/v1/auth/me', {
      headers: { Authorization: 'Bearer ' + accessToken },
    });
  } catch {
    throw new AuthError('Cannot reach Code Coach at ' + trimBase(baseUrl) + '.', 0);
  }
  if (!response.ok) throw new AuthError(await readError(response), response.status);
  return response.json();
}

/** POST /api/v1/auth/logout — revokes the session server-side. Best effort. */
export async function logout(baseUrl, accessToken) {
  try {
    await fetch(trimBase(baseUrl) + '/api/v1/auth/logout', {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + accessToken },
    });
  } catch {
    // A failed logout must still clear the local session.
  }
}

/**
 * Mint a one-time code another client can redeem for its own session.
 *
 * Used by the VS Code extension sign-in: the extension opens the portal in a
 * browser and listens on a loopback port, and a loopback HTTP server never
 * receives a URL fragment - so the normal fragment handoff cannot reach it.
 * A code in the query string can, and unlike a token it is single-use, expires
 * in two minutes, and grants nothing on its own.
 *
 * Redeeming creates a NEW session under `clientName` rather than sharing this
 * one, so signing out of the browser does not sign the student out of their
 * editor.
 */
export async function createHandoffCode(baseUrl, accessToken, clientName) {
  let response;
  try {
    response = await fetch(trimBase(baseUrl) + '/api/v1/auth/handoff', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer ' + accessToken,
      },
      body: JSON.stringify({ client_name: clientName }),
    });
  } catch {
    throw new AuthError('Cannot reach Code Coach at ' + trimBase(baseUrl) + '.', 0);
  }

  // A 404 here means one specific thing and is worth saying out loud: the
  // backend is running code from before this endpoint existed. The generic
  // message for that is FastAPI's "Not Found", which sends you looking at the
  // login form rather than at the server you forgot to restart.
  if (response.status === 404) {
    throw new AuthError(
      'This Code Coach backend has no /api/v1/auth/handoff endpoint, so it cannot ' +
        'complete a VS Code sign-in. It is running an older build — restart it and ' +
        'try again.',
      404,
    );
  }

  if (!response.ok) throw new AuthError(await readError(response), response.status);
  const payload = await response.json();
  return payload.code;
}

// ── Token storage ──

/** Persist the `tokens` object from an AuthResponse, plus the user. */
export function saveTokens(authResponse) {
  const tokens = authResponse?.tokens || authResponse;
  if (!tokens?.access_token) throw new AuthError('No access token in the response.', 0);

  localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
  if (tokens.refresh_token) localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
  if (tokens.expires_in) {
    localStorage.setItem(EXPIRES_AT_KEY, String(Date.now() + Number(tokens.expires_in) * 1000));
  }
  if (authResponse?.user) localStorage.setItem(USER_KEY, JSON.stringify(authResponse.user));
}

/** → { accessToken, refreshToken, expiresAt }. accessToken is null when signed out. */
export function loadTokens() {
  return {
    accessToken: localStorage.getItem(ACCESS_TOKEN_KEY),
    refreshToken: localStorage.getItem(REFRESH_TOKEN_KEY),
    expiresAt: Number(localStorage.getItem(EXPIRES_AT_KEY) || 0),
  };
}

export function loadUser() {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function clearTokens() {
  [ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY, EXPIRES_AT_KEY, USER_KEY].forEach((key) =>
    localStorage.removeItem(key),
  );
}

export function isSignedIn() {
  return Boolean(loadTokens().accessToken);
}

// ── Authorized requests ──

/**
 * fetch() with the platform token attached, applying the contract's rule:
 * on 401, refresh once, then retry the original request once.
 *
 * `url` is the service you are calling (usually your own backend);
 * `codeCoachUrl` is where a refresh goes. They are different hosts, which is
 * why both are needed. Implemented once here so no service reimplements the
 * retry and gets the token rotation wrong.
 */
export async function authorizedFetch(url, options = {}, { codeCoachUrl } = {}) {
  const send = (token) =>
    fetch(url, {
      ...options,
      headers: { ...(options.headers || {}), Authorization: 'Bearer ' + token },
    });

  const { accessToken, refreshToken } = loadTokens();
  if (!accessToken) throw new AuthError('Not signed in.', 401);

  let response = await send(accessToken);
  if (response.status !== 401 || !refreshToken || !codeCoachUrl) return response;

  // Access tokens live one hour. Rotate and retry exactly once — retrying more
  // than once turns a genuinely revoked session into a loop.
  try {
    const refreshed = await refresh(codeCoachUrl, refreshToken);
    saveTokens(refreshed);
    response = await send(refreshed.tokens.access_token);
  } catch {
    clearTokens();
    throw new AuthError('Your session has expired. Please sign in again.', 401);
  }

  return response;
}

// ── Dev-login gate ──

/**
 * Is the localhost-only login page allowed to render?
 *
 * Two independent guards, deliberately: the page must be served from localhost
 * AND the build must have opted in. Either one alone is too easy to get wrong —
 * a flag left set in a deployed build would otherwise ship a second login
 * page, which is what the single-UI requirement forbids.
 *
 * Pass the env flag in; this file cannot read it itself (see the header).
 */
export function devLoginEnabled(flagValue) {
  if (typeof window === 'undefined') return false;

  const host = window.location.hostname;
  const isLocal = host === 'localhost' || host === '127.0.0.1' || host === '[::1]';
  const flagOn = flagValue === true || flagValue === 'true' || flagValue === '1';

  return isLocal && flagOn;
}

// ── Portal handoff (receiving side) ──

/**
 * Read the tokens the portal appended to the URL fragment after a successful
 * sign-in, and scrub them from the address bar.
 *
 * The portal uses the fragment rather than a query string because a fragment
 * is never sent to a server: it stays out of access logs and Referer headers.
 * It does still land in browser history, so the URL is replaced immediately.
 *
 * Returns true when a session was adopted.
 */
export function consumeHandoffFragment() {
  if (typeof window === 'undefined' || !window.location.hash) return false;

  const params = new URLSearchParams(window.location.hash.slice(1));
  const accessToken = params.get('access_token');
  if (!accessToken) return false;

  saveTokens({
    tokens: {
      access_token: accessToken,
      refresh_token: params.get('refresh_token'),
      expires_in: params.get('expires_in'),
    },
  });

  // Replace the stored profile whenever a DIFFERENT student arrives.
  //
  // This used to write only when nothing was stored, which meant signing in as
  // someone else left the previous student's name and email in localStorage
  // next to the new student's token — so the app displayed one identity while
  // acting as another. Invisible until the platform bar started showing the
  // signed-in name on every page; wrong the whole time.
  const userId = params.get('user_id');
  if (userId) {
    const stored = loadUser();
    if (!stored || stored.user_id !== userId) {
      localStorage.setItem(USER_KEY, JSON.stringify({ user_id: userId }));
    }
  }

  window.history.replaceState(null, '', window.location.pathname + window.location.search);
  return true;
}

/**
 * Send the browser to the shared portal to sign in, and come back here after.
 *
 * The JSDoc types are load-bearing: PairPath's frontend is TypeScript with
 * allowJs, so it type-checks this file directly. Without them TypeScript
 * infers the options bag from its `= {}` default and rejects `returnTo` at the
 * call site.
 *
 * @param {string} portalUrl - Base URL of the Code Guru portal.
 * @param {{ returnTo?: string, path?: string }} [options]
 *   returnTo: where the portal should send the student back to (defaults to
 *   the current page). path: '/login' or '/register'.
 */
export function redirectToPortal(portalUrl, { returnTo, path = '/login' } = {}) {
  const target = returnTo || window.location.href.split('#')[0];
  window.location.href =
    trimBase(portalUrl) + path + '?redirect_uri=' + encodeURIComponent(target);
}
