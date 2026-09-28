import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router'
import { useAuth } from '../auth/useAuth'
import { formatTimestamp } from '../lib/events'
import { notificationLink } from '../lib/notifications'
import type { Notification } from '../lib/notifications'
import { useNotifications } from '../notifications/useNotifications'

type Filter = 'all' | 'unread'

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'unread', label: 'Unread' },
]

/** Today / Yesterday / Earlier, in the reader's own timezone. */
function dayGroup(iso: string, now: Date): string {
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const t = new Date(iso).getTime()
  if (t >= startOfToday) return 'Today'
  if (t >= startOfToday - 24 * 60 * 60 * 1000) return 'Yesterday'
  return 'Earlier'
}

function groupByDay(items: Notification[]): { label: string; items: Notification[] }[] {
  const now = new Date()
  const groups: { label: string; items: Notification[] }[] = []
  for (const n of items) {
    const label = dayGroup(n.created_at, now)
    const last = groups[groups.length - 1]
    if (last?.label === label) last.items.push(n)
    else groups.push({ label, items: [n] })
  }
  return groups
}

/** Every notification the signed-in user has, with select-to-mark-read.
 *
 *  Selection only ever covers what is on screen: "select all" picks the
 *  rows the current filter shows, never rows hidden by it. */
export function Notifications() {
  const { user } = useAuth()
  const { items, unreadCount, loading, error, markRead, markAllRead } = useNotifications()
  const [filter, setFilter] = useState<Filter>('all')
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const selectAllRef = useRef<HTMLInputElement>(null)

  const visible = useMemo(
    () => (filter === 'unread' ? items.filter((n) => !n.is_read) : items),
    [items, filter],
  )
  // Drop selections that are no longer on screen (filtered out, or marked
  // read while the Unread filter is on).
  const selectedVisible = visible.filter((n) => selected.has(n.id))
  const allSelected = visible.length > 0 && selectedVisible.length === visible.length
  const someSelected = selectedVisible.length > 0 && !allSelected

  // `indeterminate` has no HTML attribute; it can only be set from script.
  useEffect(() => {
    if (selectAllRef.current) selectAllRef.current.indeterminate = someSelected
  }, [someSelected])

  function changeFilter(next: Filter) {
    setFilter(next)
    setSelected(new Set())
  }

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(visible.map((n) => n.id)))
  }

  async function markSelectedRead() {
    await markRead(selectedVisible.map((n) => n.id))
    setSelected(new Set())
  }

  async function markEverythingRead() {
    await markAllRead()
    setSelected(new Set())
  }

  const selectedUnread = selectedVisible.filter((n) => !n.is_read).length

  return (
    <div className="stack">
      <header className="page-header page-header-row">
        <div>
          <h1>Notifications</h1>
          <p className="page-subtitle">
            {unreadCount === 0 ? "You're all caught up." : `${unreadCount} unread`}
          </p>
        </div>
      </header>

      <div className="tabs" role="tablist" aria-label="Show">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            role="tab"
            aria-selected={filter === f.key}
            className={filter === f.key ? 'tab tab-active' : 'tab'}
            onClick={() => changeFilter(f.key)}
          >
            {f.label}
            {f.key === 'unread' && unreadCount > 0 ? ` (${unreadCount})` : ''}
          </button>
        ))}
      </div>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      {loading ? null : visible.length === 0 ? (
        <div className="card notice-empty">
          <p className="page-subtitle">
            {filter === 'unread' ? 'No unread notifications.' : 'No notifications yet.'}
          </p>
        </div>
      ) : (
        <section className="card notif-page" aria-label="Notifications">
          <div className="notif-toolbar">
            <label className="notif-select-all">
              <input
                ref={selectAllRef}
                type="checkbox"
                checked={allSelected}
                onChange={toggleAll}
              />
              {selectedVisible.length > 0 ? `${selectedVisible.length} selected` : 'Select all'}
            </label>
            <div className="notif-toolbar-actions">
              <button
                type="button"
                className="btn-secondary"
                disabled={selectedUnread === 0}
                onClick={() => void markSelectedRead()}
              >
                Mark selected as read{selectedUnread > 0 ? ` (${selectedUnread})` : ''}
              </button>
              <button
                type="button"
                className="btn-secondary"
                disabled={unreadCount === 0}
                onClick={() => void markEverythingRead()}
              >
                Mark all as read
              </button>
            </div>
          </div>

          {groupByDay(visible).map((group) => (
            <div key={group.label} className="notif-group">
              <h2 className="notif-group-label">{group.label}</h2>
              <ul className="notif-list">
                {group.items.map((n) => {
                  const link = user ? notificationLink(n, user.role) : null
                  return (
                    <li key={n.id} className={`notif-row${n.is_read ? '' : ' is-unread'}`}>
                      <input
                        type="checkbox"
                        checked={selected.has(n.id)}
                        onChange={() => toggle(n.id)}
                        aria-label={`Select: ${n.message}`}
                      />
                      <span className="notif-dot" aria-hidden="true" />
                      <div className="notif-text">
                        <p className="notif-message">
                          {n.message}
                          {!n.is_read && <span className="visually-hidden"> (unread)</span>}
                        </p>
                        <p className="notif-time">
                          <time dateTime={n.created_at} title={new Date(n.created_at).toString()}>
                            {formatTimestamp(n.created_at)}
                          </time>
                        </p>
                      </div>
                      {link && (
                        <Link
                          to={link}
                          className="notif-link"
                          onClick={() => void markRead([n.id])}
                        >
                          View event
                        </Link>
                      )}
                    </li>
                  )
                })}
              </ul>
            </div>
          ))}
        </section>
      )}
    </div>
  )
}
