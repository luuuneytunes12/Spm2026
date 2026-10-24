// Mirror of backend/app/schemas/event.py EventProgress -- keep field names
// byte-identical. What the Organiser sees of an Event's planning (SCRUM-30).

import { apiFetch } from './api'
import { EventStatus } from './events'
import type { BookingStatus } from './venueBookings'

export interface VenueBookingProgress {
  id: number
  venue_name: string
  status: BookingStatus
  start_time: string
  end_time: string
  needs_replacement: boolean
  replaces_venue_name: string | null
}

export interface EquipmentProgress {
  id: number
  equipment_name: string
  quantity_requested: number
  status: 'requested' | 'reviewing' | 'reserved' | 'rejected' | 'cancelled'
}

export interface SafetyCheckProgress {
  stage: 'Not requested' | 'Awaiting Safety Officer' | 'Passed' | 'Sent back'
  sent_back: {
    result: 'Rejected' | 'Changes Requested'
    reason: string
    decided_by_name: string | null
    decided_at: string
    items_to_review: string[]
  } | null
}

export interface EventProgress {
  status: EventStatus
  venue_bookings: VenueBookingProgress[]
  equipment: EquipmentProgress[]
  safety_check: SafetyCheckProgress
}

export const EQUIPMENT_PROGRESS_LABELS: Record<EquipmentProgress['status'], string> = {
  requested: 'Requested',
  reviewing: 'Under review',
  reserved: 'Reserved',
  rejected: 'Rejected',
  cancelled: 'Cancelled',
}

/** The statuses in which the planning progress is worth showing. */
export const PROGRESS_STATUSES: readonly EventStatus[] = [
  EventStatus.PLANNING_EVENT,
  EventStatus.AWAITING_SAFETY_CHECK,
  EventStatus.SAFETY_CHECK_PASSED,
]

export function getOwnEventProgress(id: number): Promise<EventProgress> {
  return apiFetch(`/events/${id}/progress`) as Promise<EventProgress>
}
