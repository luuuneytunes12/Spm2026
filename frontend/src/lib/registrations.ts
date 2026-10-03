import { apiFetch } from './api'

export type RegistrationStatus = 'registered' | 'withdrawn'

/** One event as an Attendee sees it. Both flags are computed server-side --
 *  the UI only decides which control to show, never whether registration is
 *  open (see `registration_open` in backend/app/routers/registrations.py). */
export interface RegistrableEvent {
  id: number
  name: string | null
  proposed_start: string | null
  proposed_end: string | null
  registration_open: boolean
  registration_opens_at?: string | null
  registration_closes_at?: string | null
  /** null when the caller has never registered for this event. */
  my_status: RegistrationStatus | null
}

export function listRegistrableEvents(): Promise<RegistrableEvent[]> {
  return apiFetch('/registrations/events') as Promise<RegistrableEvent[]>
}

/** Every event the caller has registered for, withdrawn ones included, one
 *  row per event. Empty when they have never registered. */
export function listMyRegistrations(): Promise<RegistrableEvent[]> {
  return apiFetch('/registrations/mine') as Promise<RegistrableEvent[]>
}

/** Register, or register again after withdrawing. Rejects with a 409
 *  ApiError if already registered or registration has closed. */
export function registerForEvent(id: number): Promise<RegistrableEvent> {
  return apiFetch(`/registrations/events/${id}`, { method: 'POST' }) as Promise<RegistrableEvent>
}

export function withdrawFromEvent(id: number): Promise<RegistrableEvent> {
  return apiFetch(`/registrations/events/${id}/withdraw`, {
    method: 'POST',
  }) as Promise<RegistrableEvent>
}
