import { useEffect, useState } from 'react'
import { getAssignmentPool } from '../lib/coordinators'
import type { AssignmentPool } from '../lib/coordinators'

/** Who a new submission could be assigned to right now.
 *
 *  A debugging aid for Organisers: when a request reads "Not yet assigned",
 *  an empty pool says why, and otherwise the dropdown names who is in it.
 *  It comes from the same pool the backend assigns from, so it always
 *  matches who could actually be picked. Collapsed by default -- the count
 *  is the summary, the names are one click away. If the pool cannot be
 *  fetched this renders nothing: it is a hint, never worth an error banner. */
export function AvailableCoordinatorsCount() {
  const [pool, setPool] = useState<AssignmentPool | null>(null)

  useEffect(() => {
    let cancelled = false
    getAssignmentPool()
      .then((res) => {
        if (!cancelled) setPool(res)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  if (pool === null) return null

  const summary = (
    <>
      Coordinators currently available for assignment:{' '}
      <span className={pool.available > 0 ? 'badge badge-accent' : 'badge badge-muted'}>
        {pool.available}
      </span>
    </>
  )

  // Nothing to expand: say why plainly instead of offering an empty dropdown.
  if (pool.coordinators.length === 0) {
    return (
      <p className="page-subtitle" data-testid="available-coordinators">
        {summary} -- new submissions will stay unassigned until one is available.
      </p>
    )
  }

  return (
    <details className="pool-details" data-testid="available-coordinators">
      <summary>{summary}</summary>
      <ul className="pool-list" aria-label="Coordinators in the assignment pool">
        {pool.coordinators.map((c) => (
          <li key={c.id}>
            <strong>{c.name}</strong> <a href={`mailto:${c.email}`}>{c.email}</a>
          </li>
        ))}
      </ul>
    </details>
  )
}
