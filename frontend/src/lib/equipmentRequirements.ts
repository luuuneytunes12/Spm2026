// Mirror of backend/app/routers/equipment_requirements.py and
// schemas/equipment_requirement.py -- keep field names byte-identical. The
// backend decides who may record or read requirements; nothing here is a
// security boundary.

import { apiFetch } from './api'
import { EventStatus } from './events'

/** The statuses in which equipment is recorded, and in which Technical
 *  Support looks. Mirrors EQUIPMENT_ACTIVE_STATUSES in
 *  backend/app/domain/equipment_requirements.py.
 *
 *  PROVISIONAL: neither PDF says when equipment may be recorded. Inferred
 *  from W4 p3 ("during the planning process") and W1 Step 8, which comes
 *  after Step 5 approval; pending the customer's answer in Q&A. One list
 *  for both sides, so a requirement never sits where Technical Support
 *  is not looking. */
export const EQUIPMENT_ACTIVE_STATUSES: readonly EventStatus[] = [
  EventStatus.EVENT_APPROVED,
  EventStatus.PLANNING_EVENT,
  EventStatus.SAFETY_CHECK_PASSED,
]

export function canRecordEquipment(status: EventStatus): boolean {
  return EQUIPMENT_ACTIVE_STATUSES.includes(status)
}

/** How a requirement's status reads to a person. A status this client does
 *  not know yet is shown as it arrives rather than hiding the row.
 *
 *  `rejected` is how an "unavailable" requirement is stored: the status enum
 *  is shared with the Organiser's equipment requests, and one feature does
 *  not get a value added to it. It is shown the way the customer says it
 *  (W1: equipment "found to be unavailable"). */
export const REQUIREMENT_STATUS_LABELS: Record<string, string> = {
  requested: 'Requested',
  reviewing: 'In review',
  reserved: 'Reserved',
  rejected: 'Unavailable',
  cancelled: 'Cancelled',
}

export function requirementStatusLabel(status: string): string {
  return REQUIREMENT_STATUS_LABELS[status] ?? status
}

/** The statuses Technical Support may set by hand. Reserved is not one: it is
 *  worked out from real reservations by the server, never chosen. Mirrors
 *  TECH_SUPPORT_STATUSES in backend/app/domain/requirement_progress.py. */
export const TECH_SUPPORT_STATUS_OPTIONS: readonly { value: string; label: string }[] = [
  { value: 'requested', label: REQUIREMENT_STATUS_LABELS.requested },
  { value: 'reviewing', label: REQUIREMENT_STATUS_LABELS.reviewing },
  { value: 'rejected', label: REQUIREMENT_STATUS_LABELS.rejected },
]

/** What a requirement's status reads as, on every screen that shows one.
 *
 *  With nothing reserved it is the status Technical Support set (Requested,
 *  In review, Unavailable). Once something is reserved it follows the
 *  reservations, and says how far: "In progress \u2014 3 of 5 reserved", then
 *  "Reserved \u2014 5 of 5". What is needed and what is reserved stay two
 *  numbers: 5 needed / 3 reserved is a normal state.
 *
 *  The figures decide, not the label sent with them. The server already works
 *  Reserved out from the reservations; this only gives it its wording. */
export function requirementStatusText(status: string, reserved: number, needed: number): string {
  if (reserved > 0 && reserved >= needed) return `Reserved \u2014 ${reserved} of ${needed}`
  if (reserved > 0) return `In progress \u2014 ${reserved} of ${needed} reserved`
  return requirementStatusLabel(status)
}

/** One item reserved towards a requirement. */
export interface ReservedItem {
  equipment_id: number
  equipment_name: string
  quantity: number
}

/** A requirement as the Coordinator who wrote it sees it. */
export interface EquipmentRequirement {
  id: number
  event_id: number
  /** The Organiser's pick this was based on, if any. Cleared (null) if that
   *  pick is later replaced -- the requirement itself is never deleted. */
  organiser_equipment_request_id: number | null
  /** An equipment type: one of the catalogue's categories. */
  category: string
  quantity_needed: number
  technical_notes: string | null
  /** The status everyone sees. Reserved is worked out from the reservations,
   *  not stored; rejected is shown as Unavailable. */
  status: string
  /** How much of `quantity_needed` is reserved. Never changes it. */
  reserved_quantity: number
  reservations: ReservedItem[]
  created_at: string
  updated_at: string
}

export interface EquipmentRequirementInput {
  category: string
  quantity_needed: number
  technical_notes: string | null
  /** Set once, when recording. Not editable afterwards. */
  organiser_equipment_request_id: number | null
}

/** An edit: only what is sent is changed; null notes clears them. */
export type EquipmentRequirementChanges = Partial<
  Pick<EquipmentRequirementInput, 'category' | 'quantity_needed' | 'technical_notes'>
>

/** A requirement as Technical Support sees it: no author, and no link to
 *  the Organiser's pick -- that is the Coordinator's own bookkeeping. */
export interface SupportRequirement {
  id: number
  category: string
  quantity_needed: number
  technical_notes: string | null
  status: string
  reserved_quantity: number
  reservations: ReservedItem[]
}

/** What Technical Support may change: only these two. */
export interface SupportRequirementChanges {
  status?: string
  quantity_needed?: number
}

export interface SupportEventSummary {
  id: number
  name: string | null
  event_type: string | null
  proposed_start: string | null
  proposed_end: string | null
  expected_attendance: number | null
  status: EventStatus
  requirement_count: number
}

export interface SupportEventRecord {
  id: number
  name: string | null
  event_type: string | null
  proposed_start: string | null
  proposed_end: string | null
  expected_attendance: number | null
  venue_requirements: string | null
  status: EventStatus
  coordinator: { id: number; name: string; email: string } | null
  requirements: SupportRequirement[]
}

const JSON_HEADERS = { 'Content-Type': 'application/json' }

// --- Event Coordinator -------------------------------------------------------

export function listRequirements(eventId: number): Promise<EquipmentRequirement[]> {
  return apiFetch(`/equipment-requirements/events/${eventId}`) as Promise<EquipmentRequirement[]>
}

export function addRequirement(
  eventId: number,
  input: EquipmentRequirementInput,
): Promise<EquipmentRequirement> {
  return apiFetch(`/equipment-requirements/events/${eventId}`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(input),
  }) as Promise<EquipmentRequirement>
}

export function updateRequirement(
  id: number,
  changes: EquipmentRequirementChanges,
): Promise<EquipmentRequirement> {
  return apiFetch(`/equipment-requirements/${id}`, {
    method: 'PATCH',
    headers: JSON_HEADERS,
    body: JSON.stringify(changes),
  }) as Promise<EquipmentRequirement>
}

export async function deleteRequirement(id: number): Promise<void> {
  await apiFetch(`/equipment-requirements/${id}`, { method: 'DELETE' })
}

// --- Technical Support -------------------------------------------------------

export function listSupportEvents(): Promise<SupportEventSummary[]> {
  return apiFetch('/equipment-requirements/support/events') as Promise<SupportEventSummary[]>
}

/** Rejects with a 404 ApiError for an event that does not exist or is not
 *  yet approved -- the two look the same on purpose. */
export function getSupportEvent(id: number): Promise<SupportEventRecord> {
  return apiFetch(`/equipment-requirements/support/events/${id}`) as Promise<SupportEventRecord>
}

/** Change the status and/or quantity needed. Only what is sent changes.
 *  Resolves to the requirement as the server now holds it. */
export function updateSupportRequirement(
  id: number,
  changes: SupportRequirementChanges,
): Promise<SupportRequirement> {
  return apiFetch(`/equipment-requirements/support/requirements/${id}`, {
    method: 'PATCH',
    headers: JSON_HEADERS,
    body: JSON.stringify(changes),
  }) as Promise<SupportRequirement>
}

/** Reserve an item for a requirement, through the existing Equipment
 *  Reservations. Leave `quantity` out for an item the Organiser asked for --
 *  their quantity is reserved whole -- or to take what is still needed. */
export function reserveForRequirement(
  id: number,
  equipmentId: number,
  quantity?: number,
): Promise<SupportRequirement> {
  return apiFetch(`/equipment-requirements/${id}/reservations`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ equipment_id: equipmentId, quantity }),
  }) as Promise<SupportRequirement>
}
