import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { ApiError } from '../../lib/api'
import { listVenues } from '../../lib/venues'
import type { VenueSummary } from '../../lib/venues'

/** Every venue, for Event Coordinators and Venue Staff to pick one and open
 *  its details. Read-only: creating and editing venues is its own story. */
export function Venues() {
  const [venues, setVenues] = useState<VenueSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listVenues()
      .then((v) => {
        if (!cancelled) setVenues(v)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : 'Could not load venues.')
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="stack">
      <header className="page-header">
        <h1>Venues</h1>
        <p className="page-subtitle">
          Open a venue to check its layouts, facilities, accessibility and hours against an
          event's requirements.
        </p>
      </header>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      {venues?.length === 0 && (
        <div className="card notice-empty">
          <p className="page-subtitle">No venues have been recorded yet.</p>
        </div>
      )}

      {venues && venues.length > 0 && (
        <ul className="request-list">
          {venues.map((venue) => (
            <li key={venue.id} className="card request">
              <div className="request-main">
                <span className="request-title">{venue.name}</span>
                <span className="request-meta">
                  {venue.location} · Capacity {venue.capacity}
                </span>
              </div>
              <div className="request-side">
                {!venue.is_active && <span className="badge badge-muted">Inactive</span>}
                <Link to={`/venues/${venue.id}`} aria-label={`View details of ${venue.name}`}>
                  View details →
                </Link>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
