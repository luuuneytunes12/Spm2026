// Mirror of backend/app/routers/equipment_reservations.py and
// schemas/equipment_reservation.py -- keep field names byte-identical. The
// backend decides who may check or reserve; nothing here is a security
// boundary.

import { apiFetch } from './api'
import type { OperationalStatus } from './equipment'

/** One line of what an event asked for -- the quantity it requires. */
export interface RequiredEquipment {
  equipment_id: number
  equipment_name: string
  equipment_category: string | null
  quantity_requested: number
  status: string
}

/** An approved event equipment can be reserved for. */
export interface ReservableEvent {
  id: number
  name: string | null
  status: string
  proposed_start: string
  proposed_end: string
  equipment_items: RequiredEquipment[]
}

export interface EquipmentAvailability {
  equipment_id: number
  equipment_name: string
  equipment_category: string | null
  operational_status: OperationalStatus
  total_quantity: number
  reserved_quantity: number
  available_quantity: number
  start_time: string
  end_time: string
  /** What the event asked for; null when checked without an event, or for
   *  an item the event did not request. */
  required_quantity: number | null
  /** Whether what is free covers `required_quantity`; null alongside it. */
  sufficient: boolean | null
}

export interface EquipmentReservation {
  id: number
  event: { id: number; name: string | null }
  equipment_id: number
  equipment_name: string
  equipment_category: string | null
  quantity: number
  start_time: string
  end_time: string
  reserved_by: { name: string; email: string }
  reserved_at: string
}

export function listReservableEvents(): Promise<ReservableEvent[]> {
  return apiFetch('/equipment-reservations/events') as Promise<ReservableEvent[]>
}

/** Availability of one item for [start, end), ISO 8601. Pass `eventId` to
 *  compare against what that event requires. */
export function checkAvailability(
  equipmentId: number,
  start: string,
  end: string,
  eventId?: number,
): Promise<EquipmentAvailability> {
  const params = new URLSearchParams({ equipment_id: String(equipmentId), start, end })
  if (eventId !== undefined) params.set('event_id', String(eventId))
  return apiFetch(`/equipment-reservations/availability?${params}`) as Promise<EquipmentAvailability>
}

/** Reserve an item for an event, for the event's own date and time. Leave
 *  `quantity` out for an item the event requested -- its whole requested
 *  quantity is reserved. For one it did not, `quantity` says how many. */
export function reserveEquipment(
  eventId: number,
  equipmentId: number,
  quantity?: number,
): Promise<EquipmentReservation> {
  return apiFetch('/equipment-reservations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ event_id: eventId, equipment_id: equipmentId, quantity }),
  }) as Promise<EquipmentReservation>
}

export function listEventReservations(eventId: number): Promise<EquipmentReservation[]> {
  return apiFetch(`/equipment-reservations?event_id=${eventId}`) as Promise<EquipmentReservation[]>
}
