// Mirror of backend/app/routers/coordinators.py and schemas/user.py --
// keep field names byte-identical.

import { apiFetch } from './api'

export interface PoolCoordinator {
  id: number
  name: string
  email: string
}

export interface AssignmentPool {
  /** Always `coordinators.length`. */
  available: number
  coordinators: PoolCoordinator[]
}

/** The Coordinators a newly submitted event could be assigned to right now,
 *  and how many there are. Organiser-only -- a debugging aid that explains
 *  why a request is sitting "Not yet assigned" (the pool is empty) and who
 *  is in it. Read from the same query the backend assigns from. */
export function getAssignmentPool(): Promise<AssignmentPool> {
  return apiFetch('/coordinators/available-count') as Promise<AssignmentPool>
}
