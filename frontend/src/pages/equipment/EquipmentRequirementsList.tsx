import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { EquipmentRequirementItem } from '../../components/EquipmentRequirementItem'
import { RequirementManagePanel } from '../../components/RequirementManagePanel'
import { ApiError } from '../../lib/api'
import { formatRange } from '../../lib/events'
import { listRequestedRequirements } from '../../lib/equipmentRequirements'
import type { RequestedRequirement, SupportRequirement } from '../../lib/equipmentRequirements'

/** Technical Support's list of equipment requirements waiting for them, across
 *  every event, so nothing has to be looked for event by event.
 *
 *  Which requirements are listed -- Requested, in an event Technical Support
 *  can act on -- and their order, oldest event date first, are the server's.
 *  Each row says which event it is for, and has one action, Manage
 *  requirement: it opens the same panel as the event record, in place, with
 *  the technical notes, where the equipment will be placed, its availability
 *  and the reservation.
 *
 *  A requirement stays in its place after it is reserved or marked
 *  Unavailable, showing its new status, so the confirmation in the panel is
 *  not lost from under the person using it; it leaves the list the next time
 *  the list is loaded. */
export function EquipmentRequirementsList() {
  const [rows, setRows] = useState<RequestedRequirement[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  // The requirement whose panel is open. Only one is open at a time.
  const [openId, setOpenId] = useState<number | null>(null)

  /** A requirement as the server now holds it, in place of the one shown. The
   *  server's answer has no event, so the row keeps its own. */
  function replace(updated: SupportRequirement) {
    setRows((current) =>
      current ? current.map((r) => (r.id === updated.id ? { ...r, ...updated } : r)) : current,
    )
  }

  useEffect(() => {
    let cancelled = false
    listRequestedRequirements()
      .then((loaded) => {
        if (!cancelled) setRows(loaded)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setRows([])
        setError(err instanceof ApiError ? err.message : 'Could not load the equipment requirements.')
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="stack">
      <header className="page-header">
        <h1>Equipment Requirements</h1>
        <p className="page-subtitle">
          Requirements waiting for you to review and reserve, oldest event first.
        </p>
      </header>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      {rows !== null && rows.length === 0 && !error && (
        <div className="card notice-empty">
          <p>No equipment requirements</p>
        </div>
      )}

      {rows !== null && rows.length > 0 && (
        <ul className="requirement-list" aria-label="Equipment requirements waiting">
          {rows.map((requirement) => (
            <EquipmentRequirementItem
              key={requirement.id}
              category={requirement.category}
              quantity={requirement.quantity_needed}
              notes={requirement.technical_notes}
              status={requirement.status}
              reserved={requirement.reserved_quantity}
              reservations={requirement.reservations}
              released={requirement.released_quantity}
              unavailableReason={requirement.unavailable_reason}
              context={
                <>
                  <Link to={`/equipment-requirements/${requirement.event.id}`}>
                    {requirement.event.name ?? <em>Untitled event</em>}
                  </Link>
                  {' · '}
                  {formatRange(requirement.event.proposed_start, requirement.event.proposed_end)}
                </>
              }
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
                    event={requirement.event}
                    onChanged={replace}
                    onClose={() => setOpenId(null)}
                  />
                )
              }
            />
          ))}
        </ul>
      )}
    </div>
  )
}
