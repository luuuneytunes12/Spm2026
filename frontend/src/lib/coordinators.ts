// Mirror of backend/app/routers/coordinators.py and schemas/user.py --
// keep field names byte-identical.

import { apiFetch } from './api'

export interface CoordinatorSelf {
  id: number
  name: string
  email: string
  role: string
  is_available: boolean
  created_at: string
}

/** Toggle the signed-in Coordinator's own availability.
 *
 *  Availability only decides who is picked for NEW events: off takes the
 *  Coordinator out of the assignment pool, on puts them back. Events they
 *  already hold are never moved by this call -- see the "Declare
 *  Coordinator Global Unavailability" story. */
export function setMyAvailability(isAvailable: boolean): Promise<CoordinatorSelf> {
  return apiFetch('/coordinators/me/availability', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ is_available: isAvailable }),
  }) as Promise<CoordinatorSelf>
}

export interface AvailabilityHistoryEntry {
  id: number
  is_available: boolean
  created_at: string
}

/** The signed-in Coordinator's own availability-toggle history, newest
 *  first. Logged every time the toggle actually changes the value, even
 *  if there were no active events to reassign at the time. */
export function getMyAvailabilityHistory(): Promise<AvailabilityHistoryEntry[]> {
  return apiFetch('/coordinators/me/availability-history') as Promise<AvailabilityHistoryEntry[]>
}

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
