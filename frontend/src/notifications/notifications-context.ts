import { createContext } from 'react'
import type { Notification } from '../lib/notifications'

export interface NotificationsContextValue {
  /** The signed-in user's notifications, newest first. */
  items: Notification[]
  unreadCount: number
  /** True until the first GET /notifications has answered. */
  loading: boolean
  /** Why the last load or mark-as-read failed; null when all is well. */
  error: string | null
  /** Mark these ids read. Updates the list immediately and puts it back if
   *  the server refuses. */
  markRead: (ids: number[]) => Promise<void>
  /** Mark every unread notification read, loaded or not. */
  markAllRead: () => Promise<void>
}

export const NotificationsContext = createContext<NotificationsContextValue | null>(null)
