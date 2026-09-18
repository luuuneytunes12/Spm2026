import { createContext } from 'react'
import type { Permission, Role } from '../lib/roles'

export interface AuthUser {
  id: number
  name: string
  email: string
  role: Role
  /** Meaningful for a Coordinator; every other role carries it too but
   *  never acts on it. See the "Mark myself unavailable" story. */
  is_available: boolean
  created_at: string
}

export interface AuthContextValue {
  user: AuthUser | null
  permissions: Permission[]
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (name: string, email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  /** Re-fetch /auth/me. Used after an action that changes something on the
   *  user's own row outside the login flow -- e.g. toggling availability --
   *  so the rest of the app sees the update without a full page reload. */
  refreshUser: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)
