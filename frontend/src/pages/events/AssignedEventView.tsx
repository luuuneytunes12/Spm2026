import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { EquipmentLines } from '../../components/EquipmentLines'
import { EquipmentRequirementsSection } from '../../components/EquipmentRequirementsSection'
import { StatusTimeline } from '../../components/StatusTimeline'
import { VenueBookingSection } from '../../components/VenueBookingSection'
import { BOOKABLE_EVENT_STATUSES } from '../../lib/venueBookings'
import { ApiError } from '../../lib/api'
import {
  EVENT_STATUS_LABELS,
  EventStatus,
  approveEvent,
  approveEventChangeRequest,
  submitForSafetyCheck,
  formatRange,
  formatTimestamp,
  fromDateTimeLocal,
  getAssignedEvent,
  rejectEvent,
  rejectEventChangeRequest,
  setEventRegistration,
  toDateTimeLocal,
} from '../../lib/events'
import type { ActivityEntry, AssignedEventDetail, EventChangeRequest } from '../../lib/events'

/** Turn a stored status slug into its label, falling back to the slug.
 *
 *  Activity log entries carry raw strings rather than an EventStatus, because
 *  they are a historical record: a status renamed tomorrow must not make
 *  yesterday's log unrenderable. Hence the lookup-then-fall-back. */
function statusLabel(value: string): string {
  return EVENT_STATUS_LABELS[value as EventStatus] ?? value
}

const CHANGE_FIELD_LABELS: Record<string, string> = {
  proposed_start: 'Proposed start',
  proposed_end: 'Proposed end',
  expected_attendance: 'Expected attendance',
  venue_requirements: 'Venue requirements',
  room_layout_preference: 'Room layout preference',
  accessibility_needs: 'Accessibility needs',
  equipment_requirements: 'Other equipment notes',
  equipment_items: 'Equipment requirements',
  registration_enabled: 'Registration required',
}

/** Render a detail field as prose, or as a bulleted list, based on how the
 *  Organiser actually wrote it -- not on which field it is.
 *
 *  These are free-text columns; nothing forces "equipment requirements" to
 *  be a list any more than "purpose" is. But when someone writes one item
 *  per line, that IS a list -- a programme, a set of accessibility needs, a
 *  handful of equipment items -- and a Coordinator scanning for "what do I
 *  need to arrange" is better served by bullets than by parsing a run-on
 *  sentence. A single line stays a single line: forcing a one-item bullet
 *  around a short sentence would just be visual clutter. */
function DetailValue({ value }: { value: string | null }) {
  if (value === null) return <span className="text-muted">Not provided</span>

  const lines = value.split('\n').map((line) => line.trim()).filter(Boolean)
  if (lines.length <= 1) return <>{value}</>

  return (
    <ul className="detail-value-list">
      {lines.map((line, i) => (
        // Lines aren't guaranteed unique (an Organiser could repeat one),
        // so the index is the only stable key here.
        <li key={i}>{line}</li>
      ))}
    </ul>
  )
}

/** One line of the activity log: what changed, who changed it, and when.
 *
 *  Assignments and Organiser corrections can both leave `from_status` and
 *  `to_status` identical. The note distinguishes an assignment from a
 *  correction; neither should be rendered as a status transition. */
function ActivityLine({ entry }: { entry: ActivityEntry }) {
  const when = formatTimestamp(entry.created_at)
  const isAssignment =
    entry.from_status !== null &&
    entry.from_status === entry.to_status &&
    (entry.note?.startsWith('Assigned to ') || entry.note?.startsWith('Reassigned from '))
  return (
    <li className="activity-item">
      <p className="activity-change">
        {isAssignment ? (
          <strong>Assignment</strong>
        ) : entry.from_status && entry.from_status !== entry.to_status ? (
          <>
            {statusLabel(entry.from_status)} <span aria-hidden="true">→</span>{' '}
            <strong>{statusLabel(entry.to_status)}</strong>
          </>
        ) : entry.from_status === entry.to_status ? (
          <strong>Request update</strong>
        ) : (
          <strong>{statusLabel(entry.to_status)}</strong>
        )}
      </p>
      <p className="activity-meta">
        {entry.changed_by_name ?? 'Unknown user'}
        {when && ` · ${when}`}
      </p>
      {entry.note && <p className="activity-note">{entry.note}</p>}
    </li>
  )
}

/** Full detail of an event assigned to the signed-in Coordinator.
 *
 *  Read-only for the event's own fields, by design, not by omission: this
 *  story is about understanding an event well enough to plan it, and
 *  editing what the Organiser wrote is each its own future story.
 *  Booking a venue, requesting equipment, moving it through review are
 *  each still their own story, each free to add its own control here.
 *
 *  An event that is not assigned to this Coordinator comes back as a 404 from
 *  the API, indistinguishable from one that does not exist, and is rendered
 *  here as a plain "not found" rather than anything that would confirm the
 *  event is real. */
export function AssignedEventView() {
  const { id } = useParams()
  const [event, setEvent] = useState<AssignedEventDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [rejectionReason, setRejectionReason] = useState('')
  const [reviewing, setReviewing] = useState(false)
  const [reviewError, setReviewError] = useState<string | null>(null)
  const [changeRequestNotes, setChangeRequestNotes] = useState<Record<number, string>>({})
  const [reviewingChangeRequest, setReviewingChangeRequest] = useState<number | null>(null)
  const [changeRequestError, setChangeRequestError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [confirmError, setConfirmError] = useState<string | null>(null)
  const [registrationOn, setRegistrationOn] = useState(false)
  const [opensAt, setOpensAt] = useState('')
  const [closesAt, setClosesAt] = useState('')
  const [savingRegistration, setSavingRegistration] = useState(false)
  const [registrationError, setRegistrationError] = useState<string | null>(null)
  const [registrationFields, setRegistrationFields] = useState<string[]>([])
  const [registrationSaved, setRegistrationSaved] = useState(false)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    getAssignedEvent(Number(id))
      .then((e) => {
        if (cancelled) return
        setEvent(e)
        setRegistrationOn(e.registration_enabled)
        setOpensAt(toDateTimeLocal(e.registration_opens_at ?? null))
        setClosesAt(toDateTimeLocal(e.registration_closes_at ?? null))
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(
          err instanceof ApiError && err.status === 404
            ? 'That event is not assigned to you.'
            : err instanceof ApiError
              ? err.message
              : 'Could not load this event.',
        )
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [id])

  async function decide(decision: 'approve' | 'reject') {
    if (!event) return
    setReviewing(true)
    setReviewError(null)
    try {
      const updated =
        decision === 'approve'
          ? await approveEvent(event.id)
          : await rejectEvent(event.id, rejectionReason)
      setEvent((current) => (current ? { ...current, ...updated } : current))
      setRejectionReason('')
      const refreshed = await getAssignedEvent(event.id).catch(() => null)
      if (refreshed) setEvent(refreshed)
    } catch (err) {
      setReviewError(err instanceof ApiError ? err.message : 'Could not save the review decision.')
    } finally {
      setReviewing(false)
    }
  }

  /** Reload the event after something that can move its status (the first
   *  venue booking or equipment requirement moves an approved event into
   *  planning). A failed reload leaves what is on screen as it was. */
  async function refreshEvent() {
    if (!event) return
    const refreshed = await getAssignedEvent(event.id).catch(() => null)
    if (refreshed) setEvent(refreshed)
  }

  async function confirm() {
    if (!event) return
    setConfirming(true)
    setConfirmError(null)
    try {
      await submitForSafetyCheck(event.id)
      setEvent(await getAssignedEvent(event.id))
    } catch (err) {
      setConfirmError(err instanceof ApiError ? err.message : 'Could not submit this event for its safety check.')
      // The outstanding list may have changed since the page loaded.
      const refreshed = await getAssignedEvent(event.id).catch(() => null)
      if (refreshed) setEvent(refreshed)
    } finally {
      setConfirming(false)
    }
  }

  async function saveRegistration() {
    if (!event) return
    setSavingRegistration(true)
    setRegistrationError(null)
    setRegistrationFields([])
    setRegistrationSaved(false)
    try {
      await setEventRegistration(event.id, {
        registration_enabled: registrationOn,
        registration_opens_at: fromDateTimeLocal(opensAt),
        registration_closes_at: fromDateTimeLocal(closesAt),
      })
      setEvent(await getAssignedEvent(event.id))
      setRegistrationSaved(true)
    } catch (err) {
      if (err instanceof ApiError) {
        // The server's sentences as-is ("Registration cannot close before it
        // opens. Ensure ..."), not `message`, which prefixes column names.
        setRegistrationError(err.messages.length > 0 ? err.messages.join(' ') : err.message)
        setRegistrationFields(err.fields)
      } else {
        setRegistrationError('Could not save the registration settings.')
      }
    } finally {
      setSavingRegistration(false)
    }
  }

  async function decideChangeRequest(request: EventChangeRequest, decision: 'approve' | 'reject') {
    if (!event) return
    setReviewingChangeRequest(request.id)
    setChangeRequestError(null)
    try {
      const notes = changeRequestNotes[request.id]?.trim()
      if (decision === 'approve') {
        await approveEventChangeRequest(request.id, notes)
      } else {
        await rejectEventChangeRequest(request.id, notes)
      }
      setEvent(await getAssignedEvent(event.id))
      setChangeRequestNotes((current) => ({ ...current, [request.id]: '' }))
    } catch (err) {
      setChangeRequestError(
        err instanceof ApiError ? err.message : 'Could not save the change-request decision.',
      )
    } finally {
      setReviewingChangeRequest(null)
    }
  }

  if (loading) return null

  if (error || !event) {
    return (
      <div className="stack">
        <p className="form-error" role="alert">
          {error ?? 'Event not found.'}
        </p>
        <p>
          <Link to="/coordinator/events">← Back to my assigned events</Link>
        </p>
      </div>
    )
  }

  const details: [string, string | null][] = [
    ['Event type', event.event_type],
    ['Purpose', event.purpose],
    ['Description', event.description],
    ['Date and time', formatRange(event.proposed_start, event.proposed_end)],
    ['Expected attendance', event.expected_attendance?.toString() ?? null],
    ['General programme', event.programme],
    ['Venue requirements', event.venue_requirements],
    ['Room layout preference', event.room_layout_preference],
    ['Accessibility needs', event.accessibility_needs],
    ['Other equipment notes', event.equipment_requirements],
    [
      'Registration needs',
      event.registration_enabled ? 'Attendees must register' : 'Registration not required',
    ],
    ...(event.registration_opens_at && event.registration_closes_at
      ? ([
          [
            'Registration window',
            `${formatTimestamp(event.registration_opens_at)} – ${formatTimestamp(event.registration_closes_at)}`,
          ],
        ] as [string, string | null][])
      : []),
    ['Special arrangements', event.special_arrangements],
  ]

  const submitted = formatTimestamp(event.submitted_at)
  const pendingChangeRequest = event.change_requests.some((request) => request.status === 'pending')

  return (
    <div className="stack">
      <header className="page-header">
        <h1>{event.name ?? 'Untitled event'}</h1>
        <p className="page-subtitle">
          <span
            className={
              event.status === EventStatus.DRAFT ? 'badge badge-muted' : 'badge badge-accent'
            }
          >
            {statusLabel(event.status)}
          </span>
          {submitted && ` · submitted ${submitted}`}
        </p>
      </header>

      <section className="card">
        <h2>Status</h2>
        <StatusTimeline status={event.status} activity={event.activity} />
        {(event.status === EventStatus.SUBMITTED_AWAITING_COORDINATOR ||
          event.status === EventStatus.UNDER_REVIEW) && (
          <div className="status-actions">
            <h3>Coordinator decision</h3>
            <div className="form-actions">
              <button
                type="button"
                className="btn-primary"
                onClick={() => void decide('approve')}
                disabled={reviewing || pendingChangeRequest}
              >
                {reviewing ? 'Saving…' : 'Approve request'}
              </button>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => void decide('reject')}
                disabled={reviewing || pendingChangeRequest || !rejectionReason.trim()}
              >
                Reject request
              </button>
            </div>
            <label className="field">
              <span>Rejection reason</span>
              <textarea
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
                maxLength={2000}
                rows={3}
                disabled={reviewing}
              />
            </label>
            {reviewError && (
              <p className="form-error" role="alert">
                {reviewError}
              </p>
            )}
            {pendingChangeRequest && (
              <p className="page-subtitle">Review the pending change request before deciding this event.</p>
            )}
          </div>
        )}
        {(event.status === EventStatus.EVENT_APPROVED || event.status === EventStatus.PLANNING_EVENT) && (
          <div className="status-actions">
            <h3>Submit for Safety Check</h3>
            <p className="page-subtitle">
              Submit once the venue booking is approved and every equipment requirement is
              reserved. A Safety Officer then checks the arrangement; the event is confirmed
              when it passes.
            </p>
            {(event.confirmation_outstanding ?? []).length > 0 && (
              <div role="status" className="form-error form-error-stack">
                <p>Still outstanding:</p>
                <ul className="detail-value-list">
                  {(event.confirmation_outstanding ?? []).map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="form-actions">
              <button
                type="button"
                className="btn-primary"
                onClick={() => void confirm()}
                disabled={confirming}
              >
                {confirming ? 'Submitting…' : 'Submit for Safety Check'}
              </button>
            </div>
            {confirmError && (
              <p className="form-error" role="alert">
                {confirmError}
              </p>
            )}
          </div>
        )}
      </section>

      {BOOKABLE_EVENT_STATUSES.includes(event.status) && (
        <VenueBookingSection
          eventId={event.id}
          expectedAttendance={event.expected_attendance}
          onChanged={() => void refreshEvent()}
        />
      )}

      {(event.status === EventStatus.EVENT_APPROVED ||
        event.status === EventStatus.PLANNING_EVENT ||
        event.status === EventStatus.AWAITING_SAFETY_CHECK) && (
        <section className="card" aria-labelledby="registration-locked-heading">
          <h2 id="registration-locked-heading">Registration</h2>
          <p className="page-subtitle" role="note">
            Registration can be opened once the Safety Officer has approved this event. It is
            {event.status === EventStatus.AWAITING_SAFETY_CHECK
              ? ' waiting for that check now.'
              : ' not yet submitted for it.'}
          </p>
        </section>
      )}

      {event.status === EventStatus.SAFETY_CHECK_PASSED && (
        <section className="card">
          <h2>Registration</h2>
          <p className="page-subtitle">
            Let Attendees register for this event between the dates below.
          </p>
          <div className="stack-tight">
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={registrationOn}
                onChange={(e) => setRegistrationOn(e.target.checked)}
                disabled={savingRegistration}
              />
              <span>Enable registration</span>
            </label>
            <div className={`field${registrationFields.includes('registration_opens_at') ? ' field-invalid' : ''}`}>
              <label htmlFor="registration_opens_at">Registration opens</label>
              <input
                id="registration_opens_at"
                type="datetime-local"
                value={opensAt}
                onChange={(e) => setOpensAt(e.target.value)}
                disabled={savingRegistration}
                aria-invalid={registrationFields.includes('registration_opens_at') || undefined}
              />
            </div>
            <div className={`field${registrationFields.includes('registration_closes_at') ? ' field-invalid' : ''}`}>
              <label htmlFor="registration_closes_at">Registration closes</label>
              <input
                id="registration_closes_at"
                type="datetime-local"
                value={closesAt}
                onChange={(e) => setClosesAt(e.target.value)}
                disabled={savingRegistration}
                aria-invalid={registrationFields.includes('registration_closes_at') || undefined}
              />
            </div>
            {registrationError && (
              <p className="form-error" role="alert">
                {registrationError}
              </p>
            )}
            {registrationSaved && !registrationError && (
              <p className="page-subtitle" role="status">
                Registration settings saved.
              </p>
            )}
            <div className="form-actions">
              <button
                type="button"
                className="btn-primary"
                onClick={() => void saveRegistration()}
                disabled={savingRegistration}
              >
                {savingRegistration ? 'Saving…' : 'Save registration settings'}
              </button>
            </div>
          </div>
        </section>
      )}

      {/* Always present: while the event is under review it explains that
          equipment can be recorded once it is approved, rather than the
          Coordinator wondering where equipment goes. */}
      <EquipmentRequirementsSection
        eventId={event.id}
        eventStatus={event.status}
        organiserLines={event.equipment_items}
        organiserNotes={event.equipment_requirements}
        onChanged={() => void refreshEvent()}
      />

      <section className="card">
        <h2>Event Details</h2>
        <dl className="detail-list">
          {details.map(([label, value]) => (
            <div key={label} className="detail-row">
              <dt>{label}</dt>
              <dd>
                <DetailValue value={value} />
              </dd>
            </div>
          ))}
          {/* Outside the map: these are structured rows, not a string, and
              this is the list the Coordinator plans against. */}
          <div className="detail-row">
            <dt>Equipment requirements</dt>
            <dd>
              <EquipmentLines lines={event.equipment_items} />
            </dd>
          </div>
        </dl>
      </section>

      <section className="card">
        <h2>Event Organiser</h2>
        <dl className="detail-list">
          <div className="detail-row">
            <dt>Name</dt>
            <dd>{event.organiser.name}</dd>
          </div>
          <div className="detail-row">
            <dt>Email</dt>
            <dd>
              <a href={`mailto:${event.organiser.email}`}>{event.organiser.email}</a>
            </dd>
          </div>
        </dl>
      </section>

      {event.change_requests.length > 0 && (
        <section className="card">
          <h2>Change requests</h2>
          <div className="stack">
            {event.change_requests.map((request) => (
              <article key={request.id} className="activity-item">
                <h3>
                  {request.status[0].toUpperCase() + request.status.slice(1)} change request
                  {request.important_change && <span className="badge badge-accent">Important change</span>}
                </h3>
                <p>{request.description}</p>
                <dl className="detail-list">
                  {Object.entries(request.proposed_changes).map(([field, value]) => (
                    <div key={field} className="detail-row">
                      <dt>{CHANGE_FIELD_LABELS[field] ?? field.replaceAll('_', ' ')}</dt>
                      <dd>
                        {field === 'equipment_items' && Array.isArray(value) ? (
                          value.length ? (
                            <ul className="detail-value-list">
                              {value.map((line, index) => (
                                <li key={`${line.equipment_id}-${index}`}>
                                  {line.equipment_name ?? `Equipment #${line.equipment_id}`} ×{' '}
                                  {line.quantity_requested}
                                  {line.technical_requirements && ` · ${line.technical_requirements}`}
                                </li>
                              ))}
                            </ul>
                          ) : 'No equipment requested'
                        ) : field === 'proposed_start' || field === 'proposed_end' ? (
                          value ? new Date(String(value)).toLocaleString() : 'Not provided'
                        ) : field === 'registration_enabled' ? (
                          value ? 'Yes' : 'No'
                        ) : (
                          String(value ?? 'Not provided')
                        )}
                      </dd>
                    </div>
                  ))}
                </dl>
                {request.important_change && (
                  <div className="stack-tight">
                    <h4>Existing arrangements to reconsider</h4>
                    {request.venue_bookings_to_reconsider.length > 0 ? (
                      <ul>
                        {request.venue_bookings_to_reconsider.map((booking) => (
                          <li key={booking.id}>
                            {booking.venue_name}: {formatRange(booking.start_time, booking.end_time)} ({booking.status})
                          </li>
                        ))}
                      </ul>
                    ) : <p>No venue bookings are currently recorded.</p>}
                    {request.equipment_reservations_to_reconsider.length > 0 ? (
                      <ul>
                        {request.equipment_reservations_to_reconsider.map((reservation) => (
                          <li key={reservation.id}>
                            {reservation.quantity_requested} × {reservation.equipment_name} ({reservation.status})
                          </li>
                        ))}
                      </ul>
                    ) : <p>No equipment reservations are currently recorded.</p>}
                  </div>
                )}
                {request.review_notes && <p className="activity-note">{request.review_notes}</p>}
                {request.status === 'pending' && (
                  <div className="status-actions">
                    <label className="field">
                      <span>Review notes</span>
                      <textarea
                        value={changeRequestNotes[request.id] ?? ''}
                        onChange={(e) =>
                          setChangeRequestNotes((current) => ({ ...current, [request.id]: e.target.value }))
                        }
                        maxLength={2000}
                        rows={2}
                        disabled={reviewingChangeRequest === request.id}
                      />
                    </label>
                    <div className="form-actions">
                      <button
                        type="button"
                        className="btn-primary"
                        onClick={() => void decideChangeRequest(request, 'approve')}
                        disabled={reviewingChangeRequest !== null}
                      >
                        {reviewingChangeRequest === request.id ? 'Saving…' : 'Approve changes'}
                      </button>
                      <button
                        type="button"
                        className="btn-secondary"
                        onClick={() => void decideChangeRequest(request, 'reject')}
                        disabled={reviewingChangeRequest !== null}
                      >
                        Reject changes
                      </button>
                    </div>
                  </div>
                )}
              </article>
            ))}
          </div>
          {changeRequestError && <p className="form-error" role="alert">{changeRequestError}</p>}
        </section>
      )}

      <section className="card">
        <h2>Activity Log</h2>
        {event.activity.length === 0 ? (
          <p className="page-subtitle">No activity recorded yet.</p>
        ) : (
          <ol className="activity-list" aria-label="Activity log">
            {event.activity.map((entry) => (
              <ActivityLine key={`${entry.created_at}-${entry.to_status}`} entry={entry} />
            ))}
          </ol>
        )}
      </section>

      <p>
        <Link to="/coordinator/events">← Back to my assigned events</Link>
      </p>
    </div>
  )
}
