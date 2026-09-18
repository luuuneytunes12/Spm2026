import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { ApiError } from '../../lib/api'
import {
  ACTIVE_ASSIGNMENT_STATUSES,
  EVENT_STATUS_BRANCH_TONE,
  EVENT_STATUS_DESCRIPTIONS,
  EVENT_STATUS_LABELS,
  EVENT_STATUS_PIPELINE,
  EventStatus,
  formatRange,
  formatTimestamp,
  getAssignedEvent,
  releaseAssignedEvent,
} from '../../lib/events'
import type { ActivityEntry, AssignedEventDetail } from '../../lib/events'

/** Turn a stored status slug into its label, falling back to the slug.
 *
 *  Activity log entries carry raw strings rather than an EventStatus, because
 *  they are a historical record: a status renamed tomorrow must not make
 *  yesterday's log unrenderable. Hence the lookup-then-fall-back. */
function statusLabel(value: string): string {
  return EVENT_STATUS_LABELS[value as EventStatus] ?? value
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
 *  Not every entry is a status change -- an assignment or reassignment (see
 *  the "Mark myself unavailable" story) writes a row whose `from_status`
 *  and `to_status` are identical, because the event's status did not move;
 *  only its Coordinator did. Rendering "Submitted → Submitted" for that
 *  would misreport it as a transition that never happened, so a same-status
 *  entry is headed by its own note instead of a status arrow. */
function ActivityLine({ entry }: { entry: ActivityEntry }) {
  const when = formatTimestamp(entry.created_at)
  const isAssignment = entry.from_status !== null && entry.from_status === entry.to_status
  return (
    <li className="activity-item">
      <p className="activity-change">
        {isAssignment ? (
          <strong>Assignment</strong>
        ) : entry.from_status ? (
          <>
            {statusLabel(entry.from_status)} <span aria-hidden="true">→</span>{' '}
            <strong>{statusLabel(entry.to_status)}</strong>
          </>
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
 *  control this page does offer -- "Mark unavailable for this event" --
 *  is not an edit of the event; it hands the whole thing to someone else.
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
    ['Equipment requirements', event.equipment_requirements],
    [
      'Registration needs',
      event.registration_enabled ? 'Attendees must register' : 'Registration not required',
    ],
    ['Special arrangements', event.special_arrangements],
  ]

  const submitted = formatTimestamp(event.submitted_at)

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
        {ACTIVE_ASSIGNMENT_STATUSES.includes(event.status) && (
          <div className="status-actions">
            <button
              type="button"
              className="btn-secondary"
              onClick={() => void release()}
              disabled={releasing}
            >
              {releasing ? 'Releasing…' : 'Mark unavailable for this event'}
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
