import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { useAuth } from '../auth/useAuth'
import { formatTimestamp } from '../lib/events'
import { listMyNotifications } from '../lib/notifications'
import type { Notification } from '../lib/notifications'
import { eventDetailPath } from '../lib/roles'

/** How many of the signed-in user's most recent notifications the dropdown
 *  shows -- the full history lives at /notifications, this is a preview. */
const PREVIEW_COUNT = 5

/** Bell icon in the navbar, opening a dropdown preview of the signed-in
 *  user's own notifications (GET /notifications, same role-agnostic list
 *  the full /notifications page shows). Fetches once on mount, same as
 *  every other list on this page -- there is no push/poll infrastructure
 *  to watch for new ones arriving while the dropdown is closed. */
export function NotificationsBell() {
  const { user } = useAuth()
  const [open, setOpen] = useState(false)
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false
    listMyNotifications()
      .then((rows) => {
        if (!cancelled) setNotifications(rows)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'Could not load notifications.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!open) return
    function onOutsideClick(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    function onEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onOutsideClick)
    document.addEventListener('keydown', onEscape)
    return () => {
      document.removeEventListener('mousedown', onOutsideClick)
      document.removeEventListener('keydown', onEscape)
    }
  }, [open])

  const preview = notifications.slice(0, PREVIEW_COUNT)

  return (
    <div className="notifications-bell" ref={containerRef}>
      <button
        type="button"
        className="navbar-bell"
        onClick={() => setOpen((prev) => !prev)}
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={
          notifications.length > 0 ? `Notifications (${notifications.length})` : 'Notifications'
        }
      >
        <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
          <path
            fill="currentColor"
            d="M10 2a5 5 0 0 0-5 5v2.2c0 .6-.18 1.19-.5 1.7l-.99 1.5A1 1 0 0 0 4.35 14h11.3a1 1 0 0 0 .84-1.6l-.99-1.5a3 3 0 0 1-.5-1.7V7a5 5 0 0 0-5-5Z"
          />
          <path fill="currentColor" d="M8 16a2 2 0 0 0 4 0Z" />
        </svg>
        {notifications.length > 0 && (
          <span className="navbar-bell-badge" aria-hidden="true">
            {notifications.length > 9 ? '9+' : notifications.length}
          </span>
        )}
      </button>

      {open && (
        <div className="notifications-dropdown" role="menu" aria-label="Notifications">
          <div className="notifications-dropdown-header">Notifications</div>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          {loading ? null : preview.length === 0 ? (
            <p className="page-subtitle notifications-dropdown-empty">No notifications yet.</p>
          ) : (
            <ul className="notifications-dropdown-list">
              {preview.map((n) => {
                const href =
                  n.event_id != null && user ? eventDetailPath(user.role, n.event_id) : null
                const body = (
                  <>
                    <p className="activity-change">{n.message}</p>
                    <p className="activity-meta">{formatTimestamp(n.created_at)}</p>
                  </>
                )
                return (
                  <li key={n.id} className="notifications-dropdown-item">
                    {href ? (
                      <Link to={href} className="notification-link" onClick={() => setOpen(false)}>
                        {body}
                      </Link>
                    ) : (
                      body
                    )}
                  </li>
                )
              })}
            </ul>
          )}
          <Link to="/notifications" className="notifications-dropdown-viewall" onClick={() => setOpen(false)}>
            View all notifications
          </Link>
        </div>
      )}
    </div>
  )
}
