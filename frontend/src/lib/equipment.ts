// Mirror of backend/app/routers/equipment.py and schemas/equipment.py --
// keep field names and enum values byte-identical. The backend is the
// authority on what the catalogue contains; nothing here is a security
// boundary.

import { apiFetch } from './api'

/** The condition of a physical item.
 *
 *  Deliberately NOT the same thing as an equipment *request's* status
 *  (requested/reviewing/reserved/...). "This request is reserved" and "this
 *  projector works" are different facts about different things, and the
 *  database keeps them as two separate enums for that reason. */
export const OperationalStatus = {
  AVAILABLE: 'available',
  MAINTENANCE: 'maintenance',
  DAMAGED: 'damaged',
  RETIRED: 'retired',
} as const
export type OperationalStatus = (typeof OperationalStatus)[keyof typeof OperationalStatus]

export const OPERATIONAL_STATUS_LABELS: Record<OperationalStatus, string> = {
  [OperationalStatus.AVAILABLE]: 'Available',
  [OperationalStatus.MAINTENANCE]: 'Under maintenance',
  [OperationalStatus.DAMAGED]: 'Damaged',
  [OperationalStatus.RETIRED]: 'Retired',
}

export interface EquipmentItem {
  id: number
  name: string
  /** The equipment "type" the catalogue is filtered by. */
  category: string | null
  description: string | null
  total_quantity: number
  location: string | null
  operational_status: OperationalStatus
  /** Units free to reserve right now. Computed server-side: total minus
   *  reserved, and always 0 for an item that is not operational. */
  available_quantity: number
  technical_specs: string | null
}

export interface EquipmentCatalogue {
  items: EquipmentItem[]
  /** Every type in the WHOLE catalogue, not just in `items`. The filter
   *  dropdown is built from this, so it stays complete while a filter is
   *  applied -- a dropdown derived from a filtered list would collapse to
   *  the one type already chosen, with no way back. */
  types: string[]
}

/** Fetch the catalogue, optionally narrowed by type and/or free text.
 *
 *  The two filters combine with AND server-side. Empty values are left out
 *  of the query string entirely rather than sent as `?type=`, so a cleared
 *  filter reads as "no filter" rather than "match the empty string". */
export function listEquipment(
  options: { type?: string; q?: string } = {},
): Promise<EquipmentCatalogue> {
  const params = new URLSearchParams()
  if (options.type) params.set('type', options.type)
  if (options.q?.trim()) params.set('q', options.q.trim())

  const query = params.toString()
  return apiFetch(`/equipment${query ? `?${query}` : ''}`) as Promise<EquipmentCatalogue>
}

/** How an item's stock reads on screen.
 *
 *  Phrased as "x of y" rather than a bare number because total quantity and
 *  availability are both acceptance-criterion fields, and showing one
 *  without the other invites the wrong read -- "0 available" alone looks
 *  like the item does not exist. */
export function formatAvailability(item: EquipmentItem): string {
  if (item.operational_status !== OperationalStatus.AVAILABLE) {
    return `None of ${item.total_quantity} available`
  }
  return `${item.available_quantity} of ${item.total_quantity} available`
}
