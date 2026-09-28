// Mirror of backend/app/schemas/notification.py -- keep the string values
// byte-identical. The backend is the authority on what a notification
// contains; nothing here is a security boundary.

import { apiFetch } from './api'

export interface NotificationItem {
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

/** The caller's own notifications, newest first. */
export function listNotifications(): Promise<NotificationItem[]> {
  return apiFetch('/notifications') as Promise<NotificationItem[]>
}

export function markNotificationRead(id: number): Promise<NotificationItem> {
  return apiFetch(`/notifications/${id}/read`, { method: 'PATCH' }) as Promise<NotificationItem>
/** The signed-in user's own notifications, newest first. Scoped
 *  server-side to `user_id == me` -- there is no "whose?" parameter. */
export function listMyNotifications(): Promise<Notification[]> {
  return apiFetch('/notifications') as Promise<Notification[]>
}
