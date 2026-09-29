import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { ApiError } from '../lib/api'
import {
  listMyNotifications,
  markAllNotificationsRead,
  markNotificationsRead,
  streamMyNotifications,
} from '../lib/notifications'
import type { Notification } from '../lib/notifications'
import { NotificationsContext } from './notifications-context'
import type { NotificationsContextValue } from './notifications-context'

function messageOf(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback
}

/** One shared copy of the user's notifications for the whole signed-in app,
 *  so the navbar bell and the /notifications page never disagree.
 *
 *  Loads the list once, then stays current from the live stream. Mounted in
 *  AppLayout, which only renders for a signed-in user. */
export function NotificationsProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Notification[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(
    () =>
      listMyNotifications()
        .then((rows) => {
          setItems(rows)
          setError(null)
        })
        .catch((err: unknown) => setError(messageOf(err, 'Could not load notifications.')))
        .finally(() => setLoading(false)),
    [],
  )

  useEffect(() => {
    const controller = new AbortController()
    load()
    void streamMyNotifications(
      (incoming) =>
        // Newest first; ignore a duplicate if the list load already has it.
        setItems((rows) => (rows.some((n) => n.id === incoming.id) ? rows : [incoming, ...rows])),
      controller.signal,
      // Anything sent while disconnected never came down the stream.
      () => void load(),
    )
    return () => controller.abort()
  }, [load])

  const setRead = useCallback((ids: Set<number> | null, isRead: boolean) => {
    setItems((rows) =>
      rows.map((n) => (ids === null || ids.has(n.id) ? { ...n, is_read: isRead } : n)),
    )
  }, [])

  const markRead = useCallback(
    async (ids: number[]) => {
      const unread = new Set(ids.filter((id) => items.some((n) => n.id === id && !n.is_read)))
      if (unread.size === 0) return
      setRead(unread, true)
      try {
        await markNotificationsRead([...unread])
        setError(null)
      } catch (err) {
        setRead(unread, false)
        setError(messageOf(err, 'Could not mark notifications as read.'))
      }
    },
    [items, setRead],
  )

  const markAllRead = useCallback(async () => {
    const unread = new Set(items.filter((n) => !n.is_read).map((n) => n.id))
    setRead(null, true)
    try {
      await markAllNotificationsRead()
      setError(null)
    } catch (err) {
      setRead(unread, false)
      setError(messageOf(err, 'Could not mark notifications as read.'))
    }
  }, [items, setRead])

  const value = useMemo<NotificationsContextValue>(
    () => ({
      items,
      unreadCount: items.filter((n) => !n.is_read).length,
      loading,
      error,
      markRead,
      markAllRead,
    }),
    [items, loading, error, markRead, markAllRead],
  )

  return <NotificationsContext.Provider value={value}>{children}</NotificationsContext.Provider>
}
