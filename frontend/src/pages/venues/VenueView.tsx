import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { ApiError } from '../../lib/api'
import { getVenue } from '../../lib/venues'
import type { VenueDetail } from '../../lib/venues'

/** A list field as chips, or an explicit "None recorded" -- an empty list
 *  must read as "nothing recorded", not as a missing row. */
function ChipList({ items, label }: { items: string[]; label: string }) {
  if (items.length === 0) return <span className="text-muted">None recorded</span>
  return (
    <ul className="chip-list" aria-label={label}>
      {items.map((item) => (
        <li key={item} className="chip">
          {item}
        </li>
      ))}
    </ul>
  )
}

/** Operating hours are free text; one entry per line is shown as a list. */
function OperatingHours({ value }: { value: string | null }) {
  const lines = (value ?? '').split('\n').map((line) => line.trim()).filter(Boolean)
  if (lines.length === 0) return <span className="text-muted">Not recorded</span>
  if (lines.length === 1) return <>{lines[0]}</>
  return (
    <ul className="detail-value-list">
      {lines.map((line, i) => (
        <li key={i}>{line}</li>
      ))}
    </ul>
  )
}

/** Everything an internal user needs to judge whether a venue suits an
 *  event. Read-only by design. */
export function VenueView() {
  const { id } = useParams()
  const [venue, setVenue] = useState<VenueDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    getVenue(Number(id))
      .then((v) => {
        if (!cancelled) setVenue(v)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(
          err instanceof ApiError && err.status === 404
            ? 'Venue not found.'
            : err instanceof ApiError
              ? err.message
              : 'Could not load this venue.',
        )
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [id])

  const back = (
    <p>
      <Link to="/venues">← Back to venues</Link>
    </p>
  )

  if (loading) return null

  if (error || !venue) {
    return (
      <div className="stack">
        <p className="form-error" role="alert">
          {error ?? 'Venue not found.'}
        </p>
        {back}
      </div>
    )
  }

  return (
    <div className="stack">
      <header className="page-header">
        <h1>{venue.name}</h1>
        {!venue.is_active && (
          <p className="page-subtitle">
            <span className="badge badge-muted">Inactive</span>
          </p>
        )}
      </header>

      <section className="card">
        <h2>Overview</h2>
        <dl className="detail-list">
          <div className="detail-row">
            <dt>Location</dt>
            <dd>{venue.location}</dd>
          </div>
          <div className="detail-row">
            <dt>Capacity</dt>
            <dd>{venue.capacity} people</dd>
          </div>
          <div className="detail-row">
            <dt>Operating hours</dt>
            <dd>
              <OperatingHours value={venue.operating_hours} />
            </dd>
          </div>
        </dl>
      </section>

      <section className="card">
        <h2>Suitability</h2>
        <dl className="detail-list">
          <div className="detail-row">
            <dt>Supported room layouts</dt>
            <dd>
              <ChipList items={venue.supported_layouts} label="Supported room layouts" />
            </dd>
          </div>
          <div className="detail-row">
            <dt>Facilities</dt>
            <dd>
              <ChipList items={venue.facilities} label="Facilities" />
            </dd>
          </div>
          <div className="detail-row">
            <dt>Accessibility features</dt>
            <dd>
              <ChipList items={venue.accessibility_features} label="Accessibility features" />
            </dd>
          </div>
        </dl>
      </section>

      {back}
    </div>
  )
}
