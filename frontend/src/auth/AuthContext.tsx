import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import {
  apiFetch,
  hasSessionHint,
  setAccessToken,
  setOnSessionExpired,
  setSessionHint,
} from '../lib/api'
import type { Permission } from '../lib/roles'
import { AuthContext } from './auth-context'
import type { AuthUser } from './auth-context'

interface MeResponse {
  user: AuthUser
  permissions: Permission[]
}

interface TokenResponse {
  access_token: string
  token_type: string
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [permissions, setPermissions] = useState<Permission[]>([])
  const [loading, setLoading] = useState(true)

  const clearSession = useCallback(() => {
    setUser(null)
    setPermissions([])
  }, [])

  const hydrate = useCallback(async () => {
    try {
      const me = (await apiFetch('/auth/me')) as MeResponse
      setUser(me.user)
      setPermissions(me.permissions)
    } catch {
      clearSession()
    } finally {
      setLoading(false)
    }
  }, [clearSession])

  useEffect(() => {
    setOnSessionExpired(clearSession)
    // On mount there's no access token yet; try a refresh (relies on the
    // httpOnly cookie) before asking /auth/me, so a returning user with a
    // valid session doesn't get bounced to /login on a hard reload.
    void (async () => {
      if (!hasSessionHint()) {
        // Never signed in in this browser (or signed out): there is no
        // refresh cookie to exchange, so skip the request rather than
        // provoke a guaranteed 401.
        clearSession()
        setLoading(false)
        return
      }
      let refreshed = false
      try {
        const res = await fetch(
          `${import.meta.env.VITE_API_URL ?? 'http://localhost:8000'}/auth/refresh`,
          { method: 'POST', credentials: 'include' },
        )
        if (res.ok) {
          const body = (await res.json()) as TokenResponse
          setAccessToken(body.access_token)
          refreshed = true
        }
      } catch {
        // Backend unreachable. Treated the same as "no session": fail closed.
      }
      if (!refreshed) {
        // A 401 from /auth/refresh means there is no valid session cookie --
        // the visitor is simply logged out. Calling /auth/me anyway would
        // just fail a second time and log another console error, so stop
        // here and render the logged-out UI.
        clearSession()
        setLoading(false)
        return
      }
      await hydrate()
    })()
    return () => setOnSessionExpired(null)
  }, [clearSession, hydrate])

  const login = useCallback(async (email: string, password: string) => {
    const res = (await apiFetch('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })) as TokenResponse
    setAccessToken(res.access_token)
    setSessionHint(true)
    await hydrate()
  }, [hydrate])

  const register = useCallback(async (name: string, email: string, password: string) => {
    const res = (await apiFetch('/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, password }),
    })) as TokenResponse
    setAccessToken(res.access_token)
    setSessionHint(true)
    await hydrate()
  }, [hydrate])

  const logout = useCallback(async () => {
    try {
      await apiFetch('/auth/logout', { method: 'POST' })
    } finally {
      setAccessToken(null)
      setSessionHint(false)
      clearSession()
    }
  }, [clearSession])

  const value = useMemo(
    () => ({ user, permissions, loading, login, register, logout }),
    [user, permissions, loading, login, register, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
