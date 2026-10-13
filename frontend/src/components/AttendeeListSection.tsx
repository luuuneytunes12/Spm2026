import { useEffect, useState } from 'react'
import { ApiError } from '../lib/api'
import { listEventAttendees } from '../lib/registrations'
import type { AttendeeList } from '../lib/registrations'

const STATUS_LABEL = { registered: 'Registered', withdrawn: 'Withdrawn' } as const

/** Who has registered for an event the viewer manages (SCRUM-50). Render it
 *  only when registration is enabled; the server enforces that and ownership. */
export function AttendeeListSection({ eventId }: { eventId: number }) {
  const [list, setList] = useState<AttendeeList | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listEventAttendees(eventId)
      .then((l) => {
        if (!cancelled) setList(l)
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setError(err instanceof ApiError ? err.message : 'Could not load the attendee list.')
      })
    return () => {
      cancelled = true
    }
  }, [eventId])

  return (
    <section className="card" aria-labelledby="attendee-list-heading">
      <h2 id="attendee-list-heading">Registered attendees</h2>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {list && (
        <>
          <p className="page-subtitle" data-testid="registered-count">
            {list.registered_count} registered
          </p>
          {list.attendees.length === 0 ? (
            <p className="text-muted">No one has registered yet.</p>
          ) : (
            <dl className="detail-list" aria-label="Attendees and their registration status">
              {list.attendees.map((a) => (
                <div key={a.registration_id} className="detail-row">
                  <dt>{a.name}</dt>
                  <dd>
                    <span className={a.status === 'registered' ? 'badge badge-accent' : 'badge badge-muted'}>
                      {STATUS_LABEL[a.status]}
                    </span>
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </>
      )}
    </section>
  )
}
