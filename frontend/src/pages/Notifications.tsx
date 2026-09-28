import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { ApiError } from '../lib/api'
import { listNotifications, markNotificationRead } from '../lib/notifications'
import type { NotificationItem } from '../lib/notifications'
import { useAuth } from '../auth/useAuth'
import { Role } from '../lib/roles'

/** Shared across every role -- notifications are per-user, not per-role.
 *  A Coordinator lands here after an auto-assignment; other roles will
 *  get their own notification types as those stories ship. */
export function Notifications() {
  const { user } = useAuth()
  const [notifications, setNotifications] = useState<NotificationItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    listNotifications()
      .then((rows) => {
        if (!cancelled) setNotifications(rows)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(
            err instanceof ApiError
              ? err.message
              : 'Could not reach the server. Is the backend running?',
          )
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  function handleMarkRead(id: number) {
    // Optimistic: flip is_read locally first so the click feels instant,
    // then reconcile with the server's copy.
    setNotifications((rows) => rows.map((n) => (n.id === id ? { ...n, is_read: true } : n)))
    markNotificationRead(id).catch(() => {
      setNotifications((rows) => rows.map((n) => (n.id === id ? { ...n, is_read: false } : n)))
    })
  }

  return (
    <div className="stack">
      <header className="page-header">
        <h1>Notifications</h1>
        <p className="page-subtitle">Updates about events you're involved in.</p>
      </header>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      {loading ? null : notifications.length === 0 ? (
        <div className="card notice-empty">
          <p>No notifications yet.</p>
        </div>
      ) : (
        <ul className="request-list">
          {notifications.map((n) => (
            <li key={n.id} className="card request">
              <div className="request-main">
                <span className="request-title">{n.message}</span>
                <span className="request-meta">
                  {new Date(n.created_at).toLocaleString(undefined, {
                    dateStyle: 'medium',
                    timeStyle: 'short',
                  })}
                </span>
              </div>
              <div className="request-side">
                {!n.is_read && <span className="badge badge-accent">New</span>}
                {n.event_id && (
                  <Link
                    to={
                      user?.role === Role.COORDINATOR
                        ? `/coordinator/events/${n.event_id}`
                        : `/organiser/events/${n.event_id}`
                    }
                  >
                    View event →
                  </Link>
                )}
                {!n.is_read && (
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => handleMarkRead(n.id)}
                  >
                    Mark as read
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
