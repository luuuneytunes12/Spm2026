import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { EquipmentLines } from '../../components/EquipmentLines'
import { EquipmentRequirementsSection } from '../../components/EquipmentRequirementsSection'
import { VenueBookingSection } from '../../components/VenueBookingSection'
import { BOOKABLE_EVENT_STATUSES } from '../../lib/venueBookings'
import { ApiError } from '../../lib/api'
import {
  ACTIVE_ASSIGNMENT_STATUSES,
  EVENT_STATUS_BRANCH_TONE,
  EVENT_STATUS_DESCRIPTIONS,
  EVENT_STATUS_LABELS,
  EVENT_STATUS_PIPELINE,
  EventStatus,
  approveEvent,
  approveEventChangeRequest,
  formatRange,
  formatTimestamp,
  getAssignedEvent,
  rejectEvent,
  rejectEventChangeRequest,
  releaseAssignedEvent,
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

/** Where on the pipeline the event has actually reached, or -1 if it has not
 *  entered the Coordinator-facing pipeline yet (a Draft, in the rare case
 *  one is visible here at all -- see EVENT_STATUS_PIPELINE).
 *
 *  If the current status IS a pipeline stage, that is the answer. If it is
 *  a branch (Changes requested / Rejected / Cancelled), the answer comes
 *  from the event's own activity log -- the `from_status` of its most
 *  recent transition is the stage it was AT when it branched off, and a
 *  branch can leave the path from more than one stage, so this is read
 *  from what actually happened rather than assumed. */
function reachedPipelineIndex(event: AssignedEventDetail): number {
  const own = EVENT_STATUS_PIPELINE.indexOf(event.status)
  if (own !== -1) return own
  const departedFrom = event.activity[0]?.from_status
  return departedFrom ? EVENT_STATUS_PIPELINE.indexOf(departedFrom as EventStatus) : -1
}

/** The full lifecycle a request moves through, with the event's actual
 *  progress marked on it -- not just the single word "Submitted", but where
 *  that sits between Draft and Completed.
 *
 *  A status that branches off the main path (Changes requested / Rejected /
 *  Cancelled) is drawn as an extra node after the stage it departed from,
 *  rather than forced into the fixed sequence -- it isn't the 8th step of
 *  a 7-step process, it's an exit from one of the earlier steps. */
function StatusTimeline({ event }: { event: AssignedEventDetail }) {
  const onPipeline = EVENT_STATUS_PIPELINE.includes(event.status)
  const reached = reachedPipelineIndex(event)
  const branchTone = !onPipeline ? EVENT_STATUS_BRANCH_TONE[event.status] : undefined

  return (
    <div>
      <ol className="status-timeline" aria-label="Status timeline">
        {EVENT_STATUS_PIPELINE.map((step, i) => {
          const state = i < reached ? 'done' : i === reached ? (onPipeline ? 'current' : 'done') : 'upcoming'
          return (
            <li
              key={step}
              className={`status-step status-step-${state}`}
              aria-current={state === 'current' ? 'step' : undefined}
            >
              <span className="status-step-dot" aria-hidden="true" />
              <span className="status-step-label">{EVENT_STATUS_LABELS[step]}</span>
            </li>
          )
        })}
        {branchTone && (
          <li
            className={`status-step status-step-branch status-step-branch-${branchTone}`}
            aria-current="step"
          >
            <span className="status-step-dot" aria-hidden="true" />
            <span className="status-step-label">{statusLabel(event.status)}</span>
          </li>
        )}
      </ol>
      <p className="page-subtitle status-description">{EVENT_STATUS_DESCRIPTIONS[event.status]}</p>
    </div>
  )
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
 *  editing what the Organiser wrote is each its own future story. The one
 *  control this page does offer -- "Decline this event" -- is not an edit
 *  of the event; it hands the whole thing to someone else.
 *  Booking a venue, requesting equipment, moving it through review are
 *  each still their own story, each free to add its own control here.
 *
 *  An event that is not assigned to this Coordinator comes back as a 404 from
 *  the API, indistinguishable from one that does not exist, and is rendered
 *  here as a plain "not found" rather than anything that would confirm the
 *  event is real. */
export function AssignedEventView() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [event, setEvent] = useState<AssignedEventDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [releasing, setReleasing] = useState(false)
  const [releaseError, setReleaseError] = useState<string | null>(null)
  const [rejectionReason, setRejectionReason] = useState('')
  const [reviewing, setReviewing] = useState(false)
  const [reviewError, setReviewError] = useState<string | null>(null)
  const [changeRequestNotes, setChangeRequestNotes] = useState<Record<number, string>>({})
  const [reviewingChangeRequest, setReviewingChangeRequest] = useState<number | null>(null)
  const [changeRequestError, setChangeRequestError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    getAssignedEvent(Number(id))
      .then((e) => {
        if (!cancelled) setEvent(e)
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

  async function release() {
    if (!event) return
    setReleasing(true)
    setReleaseError(null)
    try {
      await releaseAssignedEvent(event.id)
      // It is no longer assigned to me -- reopening this page would just
      // 404. Back to the list, where it will no longer appear.
      navigate('/coordinator/events', { replace: true })
    } catch (err) {
      setReleaseError(err instanceof ApiError ? err.message : 'Could not release this event.')
      setReleasing(false)
    }
  }

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
        <StatusTimeline event={event} />
        {(event.status === EventStatus.SUBMITTED ||
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
        {ACTIVE_ASSIGNMENT_STATUSES.includes(event.status) && (
          <div className="status-actions">
            <button
              type="button"
              className="btn-secondary"
              onClick={() => void release()}
              disabled={releasing}
            >
              {releasing ? 'Declining…' : 'Decline this event'}
            </button>
            <p className="page-subtitle">
              Hands this event to another available Coordinator. Everything else
              assigned to you, and your general availability, is unaffected.
            </p>
            {releaseError && (
              <p className="form-error" role="alert">
                {releaseError}
              </p>
            )}
          </div>
        )}
      </section>

      {BOOKABLE_EVENT_STATUSES.includes(event.status) && (
        <VenueBookingSection eventId={event.id} expectedAttendance={event.expected_attendance} />
      )}

      {/* Always present: while the event is under review it explains that
          equipment can be recorded once it is approved, rather than the
          Coordinator wondering where equipment goes. */}
      <EquipmentRequirementsSection
        eventId={event.id}
        eventStatus={event.status}
        organiserLines={event.equipment_items}
        organiserNotes={event.equipment_requirements}
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
