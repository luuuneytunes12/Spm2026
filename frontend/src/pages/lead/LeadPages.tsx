import { useCallback, useEffect, useState } from 'react'
import type { LeadCoordinator } from '../../lib/coordinatorLead'
import {
  listCoordinatorAssignments,
  listLeadCoordinators,
  listUnassignedQueue,
  listUnassignedRequests,
} from '../../lib/coordinatorLead'
import { LeadEventList } from './LeadEventList'

export function UnassignedRequests() {
  return (
    <LeadEventList
      title="Unassigned Requests"
      subtitle="Event Requests that are still waiting for a Coordinator."
      emptyText="No unassigned requests. Every active request has a Coordinator."
      load={listUnassignedRequests}
    />
  )
}

/** Coordinator Assignments: every active Event that has a Coordinator, with a
 *  filter by Coordinator and the number of Events shown. */
export function CoordinatorAssignments() {
  const [coordinators, setCoordinators] = useState<LeadCoordinator[]>([])
  const [selected, setSelected] = useState<number | undefined>(undefined)

  useEffect(() => {
    let cancelled = false
    listLeadCoordinators()
      .then((rows) => {
        if (!cancelled) setCoordinators(rows)
      })
      .catch(() => {
        // The filter is a convenience: without it the full list still works.
      })
    return () => {
      cancelled = true
    }
  }, [])

  const load = useCallback(() => listCoordinatorAssignments(selected), [selected])

  return (
    <LeadEventList
      title="Coordinator Assignments"
      subtitle="Every active Event that has a Coordinator, and who holds it."
      emptyText="No active Events match."
      load={load}
      detailTo={(event) => `/coordinator-lead/assignments/${event.id}`}
      countText={(n) => `${n} active ${n === 1 ? 'Event' : 'Events'}`}
      filter={
        <div className="field">
          <label htmlFor="coordinator-filter">Filter by Coordinator</label>
          <select
            id="coordinator-filter"
            value={selected ?? ''}
            onChange={(e) => setSelected(e.target.value === '' ? undefined : Number(e.target.value))}
          >
            <option value="">All Coordinators</option>
            {coordinators.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.active_events})
              </option>
            ))}
          </select>
        </div>
      }
    />
  )
}

/** The Unassigned Queue. Oldest submission first, as the server orders it. */
export function UnassignedQueue() {
  return (
    <LeadEventList
      title="Unassigned Queue"
      subtitle="Submitted Event Requests waiting for a Coordinator, oldest first."
      emptyText="The queue is empty. No submitted requests are waiting for a Coordinator."
      load={listUnassignedQueue}
      detailTo={(event) => `/coordinator-lead/queue/${event.id}`}
      showSubmitted
    />
  )
}
