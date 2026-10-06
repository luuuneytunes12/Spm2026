// Mirror of backend/app/routers/coordinator_lead.py and LeadEventOut in
// schemas/event.py -- keep field names byte-identical. Lead-only endpoints.

import { apiFetch } from './api'
import type { EventContact, EventDetail, EventSummary } from './events'

export interface LeadEvent extends EventSummary {
  organiser: EventContact
  /** null while the request has no Coordinator. */
  coordinator: EventContact | null
}

/** Active Event Requests with no Coordinator yet. Its length is the number
 *  on the landing-page shortcut. */
export function listUnassignedRequests(): Promise<LeadEvent[]> {
  return apiFetch('/lead/unassigned-requests') as Promise<LeadEvent[]>
}

/** A queued request in full, for the Lead to review. Read-only. */
export interface LeadEventDetail extends EventDetail {
  organiser: EventContact
}

/** The Unassigned Queue: submitted requests awaiting a Coordinator, oldest
 *  first. Its length is the number on the landing-page shortcut. */
export function listUnassignedQueue(): Promise<LeadEvent[]> {
  return apiFetch('/lead/unassigned-queue') as Promise<LeadEvent[]>
}

/** One queued request. Rejects with a 404 ApiError if it is not in the queue
 *  (a draft, an assigned request, or an unknown id). */
export function getQueuedRequest(id: number): Promise<LeadEventDetail> {
  return apiFetch(`/lead/unassigned-queue/${id}`) as Promise<LeadEventDetail>
}

/** Every active Event that has a Coordinator. With `coordinatorId`, only that
 *  Coordinator's; the number of Events is the length of the list. */
export function listCoordinatorAssignments(coordinatorId?: number): Promise<LeadEvent[]> {
  const query = coordinatorId === undefined ? '' : `?coordinator_id=${coordinatorId}`
  return apiFetch(`/lead/assignments${query}`) as Promise<LeadEvent[]>
}

/** One active Event in full, for review. Read-only. Rejects with a 404
 *  ApiError if it is not an active assignment. */
export function getAssignedEventForLead(id: number): Promise<LeadEventDetail> {
  return apiFetch(`/lead/assignments/${id}`) as Promise<LeadEventDetail>
}

/** A Coordinator and how many active Events they hold. */
export interface LeadCoordinator {
  id: number
  name: string
  email: string
  active_events: number
}

/** Every Coordinator with their active-Event count (the overview's filter). */
export function listLeadCoordinators(): Promise<LeadCoordinator[]> {
  return apiFetch('/lead/coordinators') as Promise<LeadCoordinator[]>
}

/** Assign a request from the Unassigned Queue to a Coordinator. Rejects with a
 *  409 ApiError if it is no longer in the queue; the assignment stands. */
export function assignEvent(eventId: number, coordinatorId: number): Promise<LeadEvent> {
  return apiFetch(`/lead/unassigned-queue/${eventId}/assign`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ coordinator_id: coordinatorId }),
  }) as Promise<LeadEvent>
}

/** Move an active Event to another Coordinator. Status, details and the
 *  earlier Activity Log are untouched. Rejects with a 409 ApiError for a
 *  finished Event, or if that Coordinator already has it. */
export function reassignEvent(eventId: number, coordinatorId: number): Promise<LeadEvent> {
  return apiFetch(`/lead/assignments/${eventId}/reassign`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ coordinator_id: coordinatorId }),
  }) as Promise<LeadEvent>
}
