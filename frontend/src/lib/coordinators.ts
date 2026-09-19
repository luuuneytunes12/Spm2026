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
 *  Turning it off reassigns every event currently active under them to
 *  another available Coordinator server-side -- see the "Mark myself
 *  unavailable" story. There is nothing else to call here to make that
 *  happen; it is a side effect of this one request. */
export function setMyAvailability(isAvailable: boolean): Promise<CoordinatorSelf> {
  return apiFetch('/coordinators/me/availability', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ is_available: isAvailable }),
  }) as Promise<CoordinatorSelf>
}
