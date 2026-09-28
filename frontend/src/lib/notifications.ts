// Mirror of backend/app/routers/notifications.py and schemas/notification.py.

import { apiFetch } from './api'

export interface Notification {
  id: number
  event_id: number | null
  type: string
  message: string
  is_read: boolean
  created_at: string
}

/** The signed-in user's own notifications, newest first. Scoped
 *  server-side to `user_id == me` -- there is no "whose?" parameter. */
export function listMyNotifications(): Promise<Notification[]> {
  return apiFetch('/notifications') as Promise<Notification[]>
}
