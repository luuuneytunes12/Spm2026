import { useContext } from 'react'
import { NotificationsContext } from './notifications-context'
import type { NotificationsContextValue } from './notifications-context'

export function useNotifications(): NotificationsContextValue {
  const ctx = useContext(NotificationsContext)
  if (!ctx) throw new Error('useNotifications must be used within a NotificationsProvider')
  return ctx
}
