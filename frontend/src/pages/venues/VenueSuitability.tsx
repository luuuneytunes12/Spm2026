import { useEffect, useState } from 'react'
import { ApiError } from '../../lib/api'
import { listAssignedEvents } from '../../lib/events'
import type { EventSummary } from '../../lib/events'
import { checkVenueSuitability } from '../../lib/venues'
import type { VenueSuitability as VenueSuitabilityResult } from '../../lib/venues'

function nextStep(
  category: VenueSuitabilityResult['checks'][number]['category'],
  requirement: string,
): string {
  if (category === 'capacity') {
    if (requirement.includes('not recorded')) {
      return 'Edit the event and enter its expected attendance, then check again.'
    }
    return 'Choose a venue with enough capacity, or correct the event attendance if it is inaccurate.'
  }
  if (category === 'layout') {
    return 'Choose a layout this venue supports, or ask Venue Staff to update the venue layout list if it is incomplete.'
  }
  if (category === 'accessibility') {
    return 'Choose a venue that provides this feature, or ask Venue Staff to update its accessibility features if they are incomplete.'
  }
  return 'Choose a venue with this facility, or ask Venue Staff to update its facilities if the listing is incomplete.'
}

export function VenueSuitability({ venueId, venueName }: { venueId: number; venueName: string }) {
  const [events, setEvents] = useState<EventSummary[]>([])
  const [loadingEvents, setLoadingEvents] = useState(true)
  const [eventsError, setEventsError] = useState<string | null>(null)
  const [selectedEventId, setSelectedEventId] = useState('')
  const [result, setResult] = useState<VenueSuitabilityResult | null>(null)
  const [checkError, setCheckError] = useState<string | null>(null)
  const [checking, setChecking] = useState(false)

  useEffect(() => {
    let cancelled = false
    listAssignedEvents()
      .then((rows) => {
        if (!cancelled) {
          setEvents(rows)
          setEventsError(null)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setEventsError(
            err instanceof ApiError ? err.message : 'Could not load your assigned events.',
          )
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingEvents(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function loadEvents() {
    setLoadingEvents(true)
    setEventsError(null)
    try {
      setEvents(await listAssignedEvents())
    } catch (err: unknown) {
      setEventsError(
        err instanceof ApiError ? err.message : 'Could not load your assigned events.',
      )
    } finally {
      setLoadingEvents(false)
    }
  }

  async function runCheck() {
    if (!selectedEventId) return
    setChecking(true)
    setCheckError(null)
    setResult(null)
    try {
      setResult(await checkVenueSuitability(venueId, Number(selectedEventId)))
    } catch (err: unknown) {
      setCheckError(
        err instanceof ApiError ? err.message : 'Could not check suitability. Please try again.',
      )
    } finally {
      setChecking(false)
    }
  }

  const failedChecks = result?.checks.filter((check) => !check.met) ?? []

  return (
    <section className="card stack" aria-label={`Check ${venueName} suitability`}>
      <h2>Check this venue for an event</h2>
      <p className="page-subtitle">
        Compare {venueName} with one of your assigned events. This check does not require a
        booking to exist. Requirement text may contain comma-, semicolon-, or line-separated items.
      </p>
      {eventsError ? (
        <div>
          <p className="form-error" role="alert">
            {eventsError}
          </p>
          <button
            type="button"
            className="btn-secondary"
            onClick={loadEvents}
            disabled={loadingEvents}
          >
            {loadingEvents ? 'Loading events…' : 'Retry loading events'}
          </button>
        </div>
      ) : (
        <>
          {loadingEvents ? (
            <p role="status">Loading assigned events…</p>
          ) : (
            <>
              <div className="field">
                <label htmlFor={`suitability-event-${venueId}`}>Event</label>
                <select
                  id={`suitability-event-${venueId}`}
                  value={selectedEventId}
                  onChange={(event) => {
                    setSelectedEventId(event.target.value)
                    setResult(null)
                    setCheckError(null)
                  }}
                >
                  <option value="">Select an assigned event</option>
                  {events.map((event) => (
                    <option key={event.id} value={event.id}>
                      {event.name || `Event ${event.id}`}
                    </option>
                  ))}
                </select>
              </div>
              {events.length === 0 && (
                <p className="text-muted">You have no assigned events to check.</p>
              )}
              <button
                type="button"
                className="btn-primary"
                onClick={runCheck}
                disabled={!selectedEventId || checking}
              >
                {checking ? 'Checking suitability…' : 'Check suitability'}
              </button>
            </>
          )}
        </>
      )}

      {checkError && (
        <div>
          <p className="form-error" role="alert">
            {checkError}
          </p>
          <button
            type="button"
            className="btn-secondary"
            onClick={runCheck}
            disabled={checking || !selectedEventId}
          >
            Retry check
          </button>
        </div>
      )}
      {result && (
        <div className="stack" aria-live="polite">
          <h3>
            {result.suitable ? 'Suitable' : 'Not suitable'}
            {result.event_name ? ` for ${result.event_name}` : ''}
          </h3>
          {result.checks.length === 0 ? (
            <p className="text-muted">
              No layout, accessibility, or facility requirements were recorded for this event.
            </p>
          ) : (
            <ul className="detail-value-list" aria-label={`Suitability results for ${venueName}`}>
              {result.checks.map((check, index) => (
                <li key={`${check.category}-${check.requirement}-${index}`}>
                  <strong>{check.category}: {check.met ? 'Pass' : 'Needs attention'}</strong>
                  <p>{check.message}</p>
                  <p className="text-muted">
                    Required: {check.requirement}; available: {check.available}
                  </p>
                  {!check.met && (
                    <p className="suitability-next-step">
                      <strong>How to resolve:</strong> {nextStep(check.category, check.requirement)}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
          {failedChecks.length === 0 ? (
            <p className="notice-success" role="status">
              All recorded requirements pass for {venueName}. You can proceed to check availability
              and request this venue.
            </p>
          ) : (
            <p className="text-muted">
              {failedChecks.length} of {result.checks.length} recorded checks need attention.
              Update the event details or venue information as appropriate, then run the check again.
            </p>
          )}
        </div>
      )}
    </section>
  )
}
