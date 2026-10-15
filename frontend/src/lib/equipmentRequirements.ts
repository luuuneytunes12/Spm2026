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

/** How a requirement's status reads to a person. These are the Definition of
 *  Done's four (11b) and no others; a status this client does not know yet is
 *  shown as it arrives rather than hiding the row.
 *
 *  What the server stores for Unavailable (`rejected`, in an enum shared with
 *  the Organiser's equipment requests) never reaches the client: the API
 *  speaks in these four words. */
export const REQUIREMENT_STATUS_LABELS: Record<string, string> = {
  requested: 'Requested',
  reserved: 'Reserved',
  unavailable: 'Unavailable',
  available: 'Available',
}

export function requirementStatusLabel(status: string): string {
  return REQUIREMENT_STATUS_LABELS[status] ?? status
}

/** The statuses Technical Support may set by hand. Reserved is not one: it is
 *  worked out from real reservations by the server, never chosen. Nor is
 *  Available: that is a reservation freed when the event ends. Mirrors
 *  TECH_SUPPORT_STATUSES in backend/app/domain/requirement_progress.py. */
export const TECH_SUPPORT_STATUS_OPTIONS: readonly { value: string; label: string }[] = [
  { value: 'requested', label: REQUIREMENT_STATUS_LABELS.requested },
  { value: 'unavailable', label: REQUIREMENT_STATUS_LABELS.unavailable },
]

/** What a requirement's status reads as, on every screen that shows one.
 *
 *  The status is the server's: Reserved and Available are worked out from the
 *  reservations and the event, never stored, so this only gives them their
 *  wording. Part reserved is still Requested -- the Definition of Done has no
 *  "in progress" -- with how far it has got beside it: "Requested \u2014 3 of 5
 *  reserved". What is needed and what is reserved stay two numbers: 5 needed /
 *  3 reserved is a normal state. A freed reservation says how much was freed. */
export function requirementStatusText(
  status: string,
  reserved: number,
  needed: number,
  released = 0,
): string {
  if (status === 'reserved') return `Reserved \u2014 ${reserved} of ${needed}`
  if (status === 'available' && released > 0) return `Available \u2014 ${released} freed`
  if (status === 'requested' && reserved > 0) {
    return `Requested \u2014 ${reserved} of ${needed} reserved`
  }
  return requirementStatusLabel(status)
}

/** One item reserved towards a requirement. */
export interface ReservedItem {
  equipment_id: number
  equipment_name: string
  quantity: number
  /** Where it will be set up at the venue: recorded by Technical Support when
   *  they reserve, and read by the Safety Officer. Null if not given. */
  placement_notes: string | null
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
  /** The status everyone sees: requested, reserved, unavailable or available.
   *  Reserved and Available are worked out, not stored. */
  status: string
  /** How much of `quantity_needed` is reserved now. Never changes it. */
  reserved_quantity: number
  /** How much was reserved and has since been freed (the event is over). */
  released_quantity: number
  /** Why Technical Support cannot provide it; only while Unavailable. */
  unavailable_reason: string | null
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
  released_quantity: number
  unavailable_reason: string | null
  reservations: ReservedItem[]
}

/** What Technical Support may change. `reason` goes with Unavailable and is
 *  required there; the server drops it with Requested. */
export interface SupportRequirementChanges {
  status?: string
  reason?: string
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
 *  their quantity is reserved whole -- or to take what is still needed.
 *  `placementNotes` is where the item will be set up at the venue; optional. */
export function reserveForRequirement(
  id: number,
  equipmentId: number,
  quantity?: number,
  placementNotes?: string,
): Promise<SupportRequirement> {
  return apiFetch(`/equipment-requirements/${id}/reservations`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({
      equipment_id: equipmentId,
      quantity,
      placement_notes: placementNotes,
    }),
  }) as Promise<SupportRequirement>
}
