const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

// Access token lives in memory (module-level) rather than localStorage so
// it never survives a full page reload on its own — AuthContext re-hydrates
// it via /auth/me (which itself relies on the httpOnly refresh cookie) on
// mount. This keeps it out of reach of anything that can read localStorage.
let accessToken: string | null = null

export function setAccessToken(token: string | null): void {
  accessToken = token
}

export function getAccessToken(): string | null {
  return accessToken
}

// The refresh token lives in an httpOnly cookie, which JS cannot read -- so
// on a cold load the app cannot tell "logged out" from "session waiting to be
// refreshed" without asking the server. Asking always means a guaranteed 401
// in the console for every logged-out visitor.
//
// This flag is a hint, not an authority: it records that a session was
// established at some point in this browser. Absent hint -> skip the refresh
// call entirely. It holds no token and grants nothing; the httpOnly cookie
// remains the only thing that can actually mint an access token, so a forged
// hint just produces the same 401 we were avoiding.
const SESSION_HINT_KEY = 'connectsphere.session'

export function setSessionHint(active: boolean): void {
  try {
    if (active) localStorage.setItem(SESSION_HINT_KEY, '1')
    else localStorage.removeItem(SESSION_HINT_KEY)
  } catch {
    // Storage unavailable (private mode, blocked cookies). Falling back to
    // "no hint" only costs one extra request on load.
  }
}

export function hasSessionHint(): boolean {
  try {
    return localStorage.getItem(SESSION_HINT_KEY) === '1'
  } catch {
    return false
  }
}

// Called when a refresh attempt fails, so AuthContext can clear user state
// and redirect to /login. Set by AuthContext on mount.
let onSessionExpired: (() => void) | null = null

export function setOnSessionExpired(handler: (() => void) | null): void {
  onSessionExpired = handler
}

async function parseBody(res: Response): Promise<unknown> {
  if (res.status === 204) return null
  const text = await res.text()
  if (!text) return null
  return JSON.parse(text)
}

/** Carries the HTTP status and the server's own explanation, so callers can
 *  show *why* a request failed rather than a generic "request failed". */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

interface ValidationItem {
  loc?: (string | number)[]
  msg?: string
}

/** FastAPI reports 422s as `detail: [{loc, msg}, ...]` and everything else as
 *  `detail: "some string"`. Flatten both into one human-readable line. */
function formatDetail(body: unknown): string | null {
  if (typeof body !== 'object' || body === null) return null
  const detail = (body as { detail?: unknown }).detail
  if (typeof detail === 'string') return detail
  if (!Array.isArray(detail)) return null
  const parts = (detail as ValidationItem[])
    .map((item) => {
      const field = item.loc?.filter((p) => p !== 'body').join('.')
      return field ? `${field}: ${item.msg ?? 'invalid'}` : (item.msg ?? 'invalid')
    })
    .filter(Boolean)
  return parts.length > 0 ? parts.join('; ') : null
}

async function toApiError(res: Response): Promise<ApiError> {
  let detail: string | null = null
  try {
    detail = formatDetail(await parseBody(res))
  } catch {
    // non-JSON error body; fall back to the status line
  }
  return new ApiError(res.status, detail ?? `${res.status} ${res.statusText}`)
}

async function refreshAccessToken(): Promise<boolean> {
  const res = await fetch(`${API_URL}/auth/refresh`, {
    method: 'POST',
    credentials: 'include',
  })
  if (!res.ok) {
    setSessionHint(false)
    return false
  }
  const body = (await parseBody(res)) as { access_token?: string } | null
  if (!body?.access_token) {
    setSessionHint(false)
    return false
  }
  setAccessToken(body.access_token)
  setSessionHint(true)
  return true
}

export async function apiFetch(path: string, init?: RequestInit, _retried = false): Promise<unknown> {
  const headers = new Headers(init?.headers)
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)

  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    credentials: 'include',
  })

  if (res.status === 401 && !_retried) {
    const refreshed = await refreshAccessToken()
    if (refreshed) {
      return apiFetch(path, init, true)
    }
    setAccessToken(null)
    onSessionExpired?.()
    throw new ApiError(401, 'Your session has expired. Please log in again.')
  }

  if (!res.ok) {
    throw await toApiError(res)
  }
  return parseBody(res)
}
