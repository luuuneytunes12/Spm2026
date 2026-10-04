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
  EventStatus.APPROVED,
  EventStatus.PLANNING,
  EventStatus.CONFIRMED,
]

export function canRecordEquipment(status: EventStatus): boolean {
  return EQUIPMENT_ACTIVE_STATUSES.includes(status)
}

/** How a requirement's status reads to a person. A status this client does
 *  not know yet is shown as it arrives rather than hiding the row. */
export const REQUIREMENT_STATUS_LABELS: Record<string, string> = {
  requested: 'Requested',
  reviewing: 'In review',
  reserved: 'Reserved',
  rejected: 'Rejected',
  cancelled: 'Cancelled',
}

export function requirementStatusLabel(status: string): string {
  return REQUIREMENT_STATUS_LABELS[status] ?? status
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
  status: string
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
