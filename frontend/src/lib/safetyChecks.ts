// Mirror of backend/app/routers/safety_checks.py and schemas/safety_check.py
// -- keep field names byte-identical. The backend decides who may decide;
// nothing here is a security boundary.

import { apiFetch } from './api'
import type { ActivityEntry, EventContact, EventDetail, EventStatus } from './events'

/** One row of the Safety Officer's queue. */
export interface SafetyCheckSummary {
  id: number
  name: string | null
  proposed_start: string | null
  proposed_end: string | null
  coordinator: EventContact | null
}

export interface SafetyVenueBooking {
  id: number
  event_id: number
  status: string
  start_time: string
  end_time: string
  safety_recheck_reason: string | null
  venue: {
    id: number
    name: string
    location: string
    capacity: number
    supported_layouts: string[]
    accessibility_features: string[]
    emergency_access: string | null
    known_restrictions: string | null
  }
}

export interface SafetyEquipmentLine {
  id: number
  equipment_name: string
  equipment_category: string | null
  quantity_requested: number
  status: string
  placement_notes: string | null
  safety_recheck_reason: string | null
}

/** Everything a Safety Officer needs to judge an event's arrangement. */
export interface SafetyCheckDetail {
  id: number
  name: string | null
  status: EventStatus
  proposed_start: string | null
  proposed_end: string | null
  expected_attendance: number | null
  room_layout_preference: string | null
  accessibility_needs: string | null
  special_arrangements: string | null
  organiser: EventContact
  coordinator: EventContact | null
  venue_bookings: SafetyVenueBooking[]
  equipment: SafetyEquipmentLine[]
  activity: ActivityEntry[]
}

export function listSafetyChecks(): Promise<SafetyCheckSummary[]> {
  return apiFetch('/safety-checks') as Promise<SafetyCheckSummary[]>
}

export function getSafetyCheck(eventId: number): Promise<SafetyCheckDetail> {
  return apiFetch(`/safety-checks/${eventId}`) as Promise<SafetyCheckDetail>
}

function post(eventId: number, action: string, body?: unknown): Promise<EventDetail> {
  return apiFetch(`/safety-checks/${eventId}/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  }) as Promise<EventDetail>
}

/** Pass the event: it becomes Safety Check Passed (Event Confirmed). */
export function approveSafetyCheck(eventId: number): Promise<EventDetail> {
  return post(eventId, 'approve')
}

/** Back to planning with only the marked booking / equipment to review. */
export function requestSafetyChanges(
  eventId: number,
  reason: string,
  venueBookingIds: number[],
  equipmentRequestIds: number[],
): Promise<EventDetail> {
  return post(eventId, 'request-changes', {
    reason,
    venue_booking_ids: venueBookingIds,
    equipment_request_ids: equipmentRequestIds,
  })
}

/** Back to planning with every arrangement to review; nothing is cancelled. */
export function rejectSafetyCheck(eventId: number, reason: string): Promise<EventDetail> {
  return post(eventId, 'reject', { reason })
}
