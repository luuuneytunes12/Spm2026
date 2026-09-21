import { createContext } from 'react'
import type { Permission, Role } from '../lib/roles'

export interface AuthUser {
  id: number
  name: string
  email: string
  role: Role
  organisation: string | null
  phone_country_code: string | null
  phone_number: string | null
  communication_preference: string | null
  created_at: string
}

export interface AuthContextValue {
  user: AuthUser | null
  permissions: Permission[]
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (name: string, email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  /** Re-fetch /auth/me, e.g. after the Profile page saves a change, so
   *  every consumer of `user` (navbar, sidebar, dashboard) picks it up. */
  refreshUser: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)
