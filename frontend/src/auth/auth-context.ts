import { createContext } from 'react'
import type { Permission, Role } from '../lib/roles'

export interface AuthUser {
  id: number
  name: string
  email: string
  role: Role
  created_at: string
}

export interface AuthContextValue {
  user: AuthUser | null
  permissions: Permission[]
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (name: string, email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)
