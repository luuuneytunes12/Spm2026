import { useEffect, useState } from 'react'
import { useAuth } from '../../auth/useAuth'
import { RoleLanding } from '../../components/RoleLanding'
import { ApiError } from '../../lib/api'
import { getMyAvailabilityHistory, setMyAvailability } from '../../lib/coordinators'
import type { AvailabilityHistoryEntry } from '../../lib/coordinators'
import { formatTimestamp } from '../../lib/events'
import { Role } from '../../lib/roles'

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
    // Collapsed by default: the toggle above is what a Coordinator uses, the
    // log is there when they want to look something up. A native <details>
    // gives keyboard and screen-reader support for free.
    <details className="history-dropdown">
      <summary>
        Availability history
        {!loading && entries.length > 0 && (
          <span className="history-count">{entries.length}</span>
        )}
      </summary>
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
    </details>
  )
}

/** The Coordinator's landing page: the shared welcome and tiles, with their
 *  availability -- a live control they check constantly -- between the two. */
export function Coordinator() {
  const { user } = useAuth()

  return (
    <RoleLanding role={Role.COORDINATOR}>
      <section className="card landing-panel">
        <AvailabilityToggle />
        <AvailabilityHistory isAvailable={user?.is_available ?? true} />
      </section>
    </RoleLanding>
  )
}
