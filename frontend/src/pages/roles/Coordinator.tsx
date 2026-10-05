import { useEffect, useState } from 'react'
import { useAuth } from '../../auth/useAuth'
import { ApiError } from '../../lib/api'
import { getMyAvailabilityHistory, setMyAvailability } from '../../lib/coordinators'
import type { AvailabilityHistoryEntry } from '../../lib/coordinators'
import { formatTimestamp } from '../../lib/events'
import { ROLE_LABELS, Role } from '../../lib/roles'
import { ROLE_WORKFLOWS } from '../../lib/roleWorkflows'

/** The "mark myself unavailable" control at the heart of this story.
 *
 *  Turning availability off is a single API call that only takes this
 *  Coordinator out of the pool for NEW events (see
 *  backend/app/services/assignment.py). Events already assigned to them are
 *  untouched, so there is nothing else to trigger here; the toggle IS the
 *  story. */
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
          ? 'New submitted requests can be assigned to you.'
          : 'You will not be assigned new events until you mark yourself available again. Events already assigned to you stay with you.'}
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

/** History of the Coordinator's own availability toggles.
 *
 *  Logged server-side every time PATCH /coordinators/me/availability
 *  actually changes the value -- unlike the per-event activity log, this
 *  still records the change even when the Coordinator had zero active
 *  events at the time (nothing there for an event's own log to attach
 *  to). */
function AvailabilityHistory({ isAvailable }: { isAvailable: boolean }) {
  const [entries, setEntries] = useState<AvailabilityHistoryEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Reloaded whenever the availability itself changes: toggling refreshes the
  // signed-in user, and the entry that toggle just wrote should appear
  // straight away -- not only after the page is reloaded.
  useEffect(() => {
    let cancelled = false
    getMyAvailabilityHistory()
      .then((rows) => {
        if (cancelled) return
        setEntries(rows)
        setError(null)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof ApiError ? err.message : 'Could not load availability history.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [isAvailable])

  return (
    <>
      <h3>History</h3>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {loading ? null : entries.length === 0 ? (
        <p className="page-subtitle">No changes yet.</p>
      ) : (
        <ul className="activity-list" aria-label="Availability history">
          {entries.map((entry) => (
            <li key={entry.id} className="activity-item">
              <p className="activity-change">
                {entry.is_available ? 'Marked available' : 'Marked unavailable'}
              </p>
              <p className="activity-meta">{formatTimestamp(entry.created_at)}</p>
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
 *  role page uses: Availability is a real, backend-backed control a
 *  Coordinator checks constantly, so it sits in a bento grid alongside
 *  Permissions and Planned instead of a stacked full-width card underneath
 *  them. Notifications live in the navbar bell and /notifications. */
export function Coordinator() {
  const { user } = useAuth()
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
          <AvailabilityHistory isAvailable={user?.is_available ?? true} />
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
