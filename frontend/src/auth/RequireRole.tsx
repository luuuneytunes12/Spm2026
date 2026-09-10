import { Navigate, Outlet } from 'react-router'
import type { Role } from '../lib/roles'
import { useAuth } from './useAuth'

export function RequireRole({ roles }: { roles: Role[] }) {
  const { user, loading } = useAuth()

  if (loading) return null
  if (!user || !roles.includes(user.role)) {
    return <Navigate to="/forbidden" replace />
  }
  return <Outlet />
}
