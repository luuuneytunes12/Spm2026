// Mirror of the clarification endpoints in backend/app/routers/events.py
// (SCRUM-27 request, SCRUM-103 reply) -- keep field names identical.

import { apiFetch } from './api'

export interface ClarificationOut {
  id: number
  event_id: number
  kind: 'request' | 'reply'
  message: string
  author_id: number
  author_name: string | null
  created_at: string
}

/** Event fields an Organiser may amend while replying to a clarification. */
export interface ClarificationUpdates {
  name?: string
  purpose?: string
  description?: string
  expected_attendance?: number
  venue_requirements?: string
  accessibility_needs?: string
  equipment_requirements?: string
  special_arrangements?: string
}

export function listClarifications(eventId: number): Promise<ClarificationOut[]> {
  return apiFetch(`/events/${eventId}/clarifications`) as Promise<ClarificationOut[]>
}

export function requestClarification(eventId: number, message: string): Promise<ClarificationOut> {
  return apiFetch(`/events/${eventId}/clarifications`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  }) as Promise<ClarificationOut>
}

export function replyToClarification(
  eventId: number,
  input: { message: string; updates?: ClarificationUpdates },
): Promise<ClarificationOut> {
  return apiFetch(`/events/${eventId}/clarifications/reply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  }) as Promise<ClarificationOut>
}
