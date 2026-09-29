// Mirror of backend/app/routers/notifications.py and schemas/notification.py.

import { apiFetch, apiStream } from './api'
import { Role } from './roles'

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

/** Mark the given notifications as read. Ids that are not the caller's are
 *  ignored server-side; `updated` counts only rows that actually changed. */
export function markNotificationsRead(ids: number[]): Promise<{ updated: number }> {
  return apiFetch('/notifications/read', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  }) as Promise<{ updated: number }>
}

/** Mark every unread notification as read -- including ones never loaded. */
export function markAllNotificationsRead(): Promise<{ updated: number }> {
  return apiFetch('/notifications/read-all', { method: 'POST' }) as Promise<{ updated: number }>
}

/** Waits between reconnect attempts; the last one repeats. */
const RECONNECT_DELAYS_MS = [1_000, 2_000, 5_000, 10_000, 30_000]

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms)
    signal.addEventListener('abort', () => {
      clearTimeout(timer)
      resolve()
    })
  })
}

/** Pull every complete `data:` payload out of `buffer`, returning them and
 *  whatever partial event is left over for the next chunk. Comment lines
 *  (": ping" keep-alives) and other fields are skipped. */
export function parseSseChunk(buffer: string): { events: string[]; rest: string } {
  const blocks = buffer.split(/\r?\n\r?\n/)
  const rest = blocks.pop() ?? ''
  const events = blocks
    .map((block) =>
      block
        .split(/\r?\n/)
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).replace(/^ /, ''))
        .join('\n'),
    )
    .filter((data) => data !== '')
  return { events, rest }
}

/** Listen for the signed-in user's new notifications until `signal` aborts.
 *
 *  Reconnects with backoff when the connection drops (server restart,
 *  network blip). Only notifications created while connected arrive here --
 *  `onReconnect` fires after each reconnect so the caller can re-fetch the
 *  list and pick up anything sent while it was disconnected. */
export async function streamMyNotifications(
  onNotification: (n: Notification) => void,
  signal: AbortSignal,
  onReconnect?: () => void,
): Promise<void> {
  let attempt = 0
  while (!signal.aborted) {
    try {
      const res = await apiStream('/notifications/stream', signal)
      if (attempt > 0) onReconnect?.()
      attempt = 0
      if (!res.body) return
      const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
      let buffer = ''
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        const parsed = parseSseChunk(buffer + value)
        buffer = parsed.rest
        for (const data of parsed.events) {
          try {
            onNotification(JSON.parse(data) as Notification)
          } catch {
            // A malformed event is dropped rather than killing the stream.
          }
        }
      }
    } catch (err) {
      if (signal.aborted) return
      // A 401 here means the session is gone and AuthContext is already
      // sending the user to /login -- retrying would just fail again.
      if ((err as { status?: number }).status === 401) return
    }
    if (signal.aborted) return
    await wait(RECONNECT_DELAYS_MS[Math.min(attempt, RECONNECT_DELAYS_MS.length - 1)], signal)
    attempt += 1
  }
}

/** Where a notification should take the reader, or null if it has no
 *  page to open. Each role reaches an event through its own route, and
 *  the other side's route would only 404 or bounce to /forbidden. */
export function notificationLink(n: Notification, role: Role): string | null {
  if (n.event_id === null) return null
  if (role === Role.COORDINATOR) return `/coordinator/events/${n.event_id}`
  if (role === Role.ORGANISER) return `/organiser/events/${n.event_id}`
  return null
}

/** "99+" rather than a number that no longer fits the bell's badge. */
export function badgeLabel(count: number): string {
  return count > 99 ? '99+' : String(count)
}
