import { useEffect, useId, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { useAuth } from '../auth/useAuth'
import { formatTimestamp } from '../lib/events'
import { badgeLabel, notificationLink } from '../lib/notifications'
import type { Notification } from '../lib/notifications'
import { useNotifications } from '../notifications/useNotifications'

/** How many of the newest notifications the dropdown previews. */
const PREVIEW_COUNT = 5

/** Navbar bell: unread count at a glance, a short preview on click, and the
 *  way through to the full /notifications page. */
export function NotificationBell() {
  const { user } = useAuth()
  const { items, unreadCount, markRead, markAllRead } = useNotifications()
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const panelId = useId()
  const navigate = useNavigate()

  // Close on a click anywhere outside, or on Escape (focus back to the bell).
  useEffect(() => {
    if (!open) return
    function onPointerDown(e: PointerEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setOpen(false)
        buttonRef.current?.focus()
      }
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  if (!user) return null

  function openNotification(n: Notification) {
    void markRead([n.id])
    setOpen(false)
    const link = notificationLink(n, user!.role)
    if (link) void navigate(link)
  }

  const preview = items.slice(0, PREVIEW_COUNT)
  const label = unreadCount > 0 ? `Notifications, ${unreadCount} unread` : 'Notifications'

  return (
    <div className="notif-bell" ref={rootRef}>
      <button
        ref={buttonRef}
        type="button"
        className="theme-toggle notif-bell-button"
        onClick={() => setOpen((o) => !o)}
        aria-label={label}
        title={label}
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={panelId}
      >
        <svg viewBox="0 0 20 20" width="17" height="17" aria-hidden="true">
          <path
            fill="currentColor"
            d="M10 2a5 5 0 0 0-5 5v2.6c0 .7-.2 1.4-.6 2L3.2 13.4A1 1 0 0 0 4 15h12a1 1 0 0 0 .8-1.6l-1.2-1.8a3.6 3.6 0 0 1-.6-2V7a5 5 0 0 0-5-5Z"
          />
          <path fill="currentColor" d="M7.8 16.2a2.3 2.3 0 0 0 4.4 0Z" />
        </svg>
        {unreadCount > 0 && (
          <span className="notif-badge" aria-hidden="true">
            {badgeLabel(unreadCount)}
          </span>
        )}
      </button>

      {open && (
        <div id={panelId} className="notif-dropdown" role="region" aria-label="Recent notifications">
          <div className="notif-dropdown-header">
            <span className="notif-dropdown-title">Notifications</span>
            {unreadCount > 0 && (
              <button type="button" className="btn-link-muted" onClick={() => void markAllRead()}>
                Mark all as read
              </button>
            )}
          </div>

          {preview.length === 0 ? (
            <p className="notif-empty">You're all caught up.</p>
          ) : (
            <ul className="notif-dropdown-list">
              {preview.map((n) => (
                <li key={n.id}>
                  <button
                    type="button"
                    className={`notif-dropdown-item${n.is_read ? '' : ' is-unread'}`}
                    onClick={() => openNotification(n)}
                  >
                    <span className="notif-dot" aria-hidden="true" />
                    <span className="notif-text">
                      <span className="notif-message">{n.message}</span>
                      <span className="notif-time">{formatTimestamp(n.created_at)}</span>
                    </span>
                    {!n.is_read && <span className="visually-hidden"> (unread)</span>}
                  </button>
                </li>
              ))}
            </ul>
          )}

          <Link to="/notifications" className="notif-dropdown-footer" onClick={() => setOpen(false)}>
            View all notifications
          </Link>
        </div>
      )}
    </div>
  )
}
