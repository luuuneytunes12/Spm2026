import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { EquipmentRequirementItem } from '../../components/EquipmentRequirementItem'
import { RequirementManagePanel } from '../../components/RequirementManagePanel'
import { ApiError } from '../../lib/api'
import { EVENT_STATUS_LABELS, formatRange } from '../../lib/events'
import { getSupportEvent } from '../../lib/equipmentRequirements'
import type { SupportEventRecord, SupportRequirement } from '../../lib/equipmentRequirements'

const NOT_PROVIDED = <span className="text-muted">Not provided</span>

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="detail-row">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

// Plain link, worded like the other "back" links in the app.
const BACK = <Link to="/equipment-requirements">← Back to equipment requirements</Link>

/** An event as Technical Support sees it: enough to judge what the equipment
 *  is for, and every requirement its Coordinator has recorded -- each with
 *  how far it has got, and one action: Manage requirement. That opens a single
 *  panel for the whole task -- its status and quantity, the exact equipment,
 *  its availability and the reservation.
 *
 *  This is the work queue. Reserving from here uses the existing Equipment
 *  Reservations, with the event, the type and the date and time already
 *  filled in; the Equipment Reservations page itself is untouched and still
 *  there for the global view. An event that does not exist and one that is
 *  not yet approved look the same here, because the server answers both with
 *  "not found". */
export function EquipmentRequirementsRecord() {
  const { eventId } = useParams()
  const id = Number(eventId)
  const [record, setRecord] = useState<SupportEventRecord | null>(null)
  const [error, setError] = useState<string | null>(null)
  // The requirement whose panel is open. Only one is open at a time.
  const [openId, setOpenId] = useState<number | null>(null)

  /** A requirement as the server now holds it, in place of the one shown. */
  function replace(updated: SupportRequirement) {
    setRecord((current) =>
      current
        ? { ...current, requirements: current.requirements.map((r) => (r.id === updated.id ? updated : r)) }
        : current,
    )
  }

  useEffect(() => {
    let cancelled = false
    getSupportEvent(id)
      .then((loaded) => {
        if (!cancelled) setRecord(loaded)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : 'Could not load this event.')
      })
    return () => {
      cancelled = true
    }
  }, [id])

  if (error) {
    return (
      <div className="stack">
        {BACK}
        <p className="form-error" role="alert">
          {error}
        </p>
      </div>
    )
  }
  if (!record) return null

  return (
    <div className="stack">
      {BACK}

      <header className="page-header page-header-row">
        <div>
          <h1>{record.name ?? 'Untitled event'}</h1>
        </div>
        <span className="badge badge-accent">
          {EVENT_STATUS_LABELS[record.status] ?? record.status}
        </span>
      </header>

      <section className="card">
        <h2>Event</h2>
        <dl className="detail-list">
          <DetailRow label="Date and time">
            {formatRange(record.proposed_start, record.proposed_end)}
          </DetailRow>
          <DetailRow label="Event type">{record.event_type ?? NOT_PROVIDED}</DetailRow>
          <DetailRow label="Expected attendance">{record.expected_attendance ?? NOT_PROVIDED}</DetailRow>
          <DetailRow label="Venue requirements">{record.venue_requirements ?? NOT_PROVIDED}</DetailRow>
          <DetailRow label="Event Coordinator">
            {record.coordinator ? (
              <>
                {record.coordinator.name}{' '}
                <span className="text-muted">({record.coordinator.email})</span>
              </>
            ) : (
              <span className="text-muted">Not assigned</span>
            )}
          </DetailRow>
        </dl>
      </section>

      <section className="card stack-tight">
        <h2>Equipment requirements</h2>
        {record.requirements.length === 0 ? (
          <p className="text-muted">No equipment recorded yet.</p>
        ) : (
          <ul className="requirement-list" aria-label="Equipment requirements">
            {record.requirements.map((requirement) => (
              <EquipmentRequirementItem
                key={requirement.id}
                category={requirement.category}
                quantity={requirement.quantity_needed}
                notes={requirement.technical_notes}
                status={requirement.status}
                reserved={requirement.reserved_quantity}
                reservations={requirement.reservations}
                actions={
                  <button
                    type="button"
                    className="btn-secondary"
                    aria-label={`Manage ${requirement.category} requirement`}
                    aria-expanded={openId === requirement.id}
                    onClick={() => setOpenId(openId === requirement.id ? null : requirement.id)}
                  >
                    Manage requirement
                  </button>
                }
                panel={
                  openId === requirement.id && (
                    <RequirementManagePanel
                      requirement={requirement}
                      event={record}
                      onChanged={replace}
                      onClose={() => setOpenId(null)}
                    />
                  )
                }
              />
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
