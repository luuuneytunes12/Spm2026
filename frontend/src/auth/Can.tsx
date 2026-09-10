import type { ReactNode } from 'react'
import type { Permission } from '../lib/roles'
import { useAuth } from './useAuth'

// Conditional-rendering helper for UI only (e.g. hiding an admin nav
// link). The backend permission check on the actual endpoint is the real
// access-control gate — this just avoids showing controls a user can't use.
export function Can({ permission, children }: { permission: Permission; children: ReactNode }) {
  const { permissions } = useAuth()
  if (!permissions.includes(permission)) return null
  return <>{children}</>
}
