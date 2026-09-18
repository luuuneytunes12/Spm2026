import { useEffect, useState } from 'react'
import { useAuth } from '../../auth/useAuth'
import { ApiError } from '../../lib/api'
import { setMyAvailability } from '../../lib/coordinators'
import { formatTimestamp } from '../../lib/events'
import { listMyNotifications } from '../../lib/notifications'
import type { Notification } from '../../lib/notifications'
import { ROLE_LABELS, ROLE_PERMISSIONS, Role } from '../../lib/roles'
import { ROLE_WORKFLOWS } from '../../lib/roleWorkflows'

/** The "mark myself unavailable" control at the heart of this story.
 *
 *  Turning availability off is a single API call -- reassigning every event
 *  currently active under this Coordinator, to another available one, is a
 *  server-side side effect of that same call (see
 *  backend/app/services/assignment.py). There is nothing else to trigger
 *  here; the toggle IS the story. */
function AvailabilityToggle() {
  const { user, refreshUser } = useAuth()
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!user) return null
  const isAvailable = user.is_available

  async function toggle() {
    setPending(true)
    setError(null)
    try {
      await setMyAvailability(!isAvailable)
      await refreshUser()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not update your availability.')
    } finally {
      setPending(false)
    }
  }

  return (
    <>
      <h2>Availability</h2>
      <p className="page-subtitle" style={{ marginBottom: 14 }}>
        {isAvailable
          ? 'New submitted requests can be assigned to you, and anything reassigned from an unavailable Coordinator can come to you too.'
          : 'You will not receive new or reassigned events. Everything that was assigned to you has been handed to another available Coordinator.'}
      </p>
      <p className="availability-row">
        <span className={isAvailable ? 'badge badge-accent' : 'badge badge-muted'}>
          {isAvailable ? 'Available' : 'Unavailable'}
        </span>
        <button
          type="button"
          className={isAvailable ? 'btn-secondary' : 'btn-primary'}
          onClick={() => void toggle()}
          disabled={pending}
        >
          {pending ? 'Updating…' : isAvailable ? 'Mark myself unavailable' : 'Mark myself available'}
        </button>
      </p>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </>
  )
}

/** The Coordinator's own notifications -- including "you have been
 *  assigned to coordinate X" and, once someone else takes over one of
 *  their events, "Y has taken over coordinating X" -- both written
 *  server-side the moment an assignment or reassignment happens. */
function NotificationsList() {
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listMyNotifications()
      .then((rows) => {
        if (!cancelled) setNotifications(rows)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof ApiError ? err.message : 'Could not load notifications.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <>
      <h2>Notifications</h2>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {loading ? null : notifications.length === 0 ? (
        <p className="page-subtitle">No notifications yet.</p>
      ) : (
        <ul className="activity-list" aria-label="Notifications">
          {notifications.map((n) => (
            <li key={n.id} className="activity-item">
              <p className="activity-change">{n.message}</p>
              <p className="activity-meta">{formatTimestamp(n.created_at)}</p>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

/** The Coordinator's landing page.
 *
 *  A dedicated layout rather than the shared RoleHome shell every other
 *  role page uses: Availability and Notifications are real, backend-backed
 *  controls a Coordinator checks constantly, so they sit in a bento grid
 *  alongside Permissions and Planned instead of stacked full-width cards
 *  underneath them. */
export function Coordinator() {
  const permissions = ROLE_PERMISSIONS[Role.COORDINATOR]
  const planned = ROLE_WORKFLOWS[Role.COORDINATOR]

  return (
    <div className="stack">
      <header className="page-header">
        <h1>{ROLE_LABELS[Role.COORDINATOR]}</h1>
        <p className="page-subtitle">What this role can do today, and what is planned for it.</p>
      </header>

      <div className="bento-grid">
        <section className="card bento-availability">
          <AvailabilityToggle />
        </section>

        <section className="card bento-notifications">
          <NotificationsList />
        </section>

        <section className="card bento-permissions">
          <h2>Permissions</h2>
          <p className="page-subtitle" style={{ marginBottom: 14 }}>
            Granted by the role, enforced by the backend on every request.
          </p>
          <ul className="chip-list">
            {permissions.map((permission) => (
              <li key={permission} className="chip">
                {permission}
              </li>
            ))}
          </ul>
        </section>

        <section className="card bento-planned">
          <h2>
            Planned <span className="badge badge-muted">not yet implemented</span>
          </h2>
          <p className="page-subtitle" style={{ marginBottom: 14 }}>
            The backend does not yet expose venue, equipment or registration
            endpoints for this role. Nothing below is real data.
          </p>
          <ul className="workflow-list">
            {planned.map((workflow) => (
              <li key={workflow.title} className="workflow">
                <span className="workflow-title">{workflow.title}</span>
                <span className="workflow-desc">{workflow.description}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}
