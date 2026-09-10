import { Navigate, Outlet } from 'react-router'
import type { Permission } from '../lib/roles'
import { useAuth } from './useAuth'

export function RequirePermission({ permission }: { permission: Permission }) {
  const { permissions, loading } = useAuth()

  if (loading) return null
  if (!permissions.includes(permission)) {
    return <Navigate to="/forbidden" replace />
  }
  return <Outlet />
}
