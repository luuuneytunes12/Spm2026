// Mirror of backend/app/routers/venue_catalogue.py and schemas/venue_catalogue.py
// (SCRUM-108). Field names are byte-identical. The server decides who may add
// or edit; the checks here only save a round trip.

import { apiFetch } from './api'
import type { VenueDetail } from './venues'

export interface VenueInput {
  name: string
  location: string
  capacity: number
  facilities: string[]
  accessibility_features: string[]
  supported_layouts: string[]
  operating_hours: string
}

export interface FlaggedBooking {
  booking_id: number
  event_id: number
  event_name: string | null
  reason: string
}

export interface VenueSaved extends VenueDetail {
  flagged_bookings: FlaggedBooking[]
}

export interface VenueActivityEntry {
  id: number
  venue_id: number
  venue_name: string
  note: string
  changed_by: string | null
  created_at: string
}

/** A comma- or line-separated field as a clean list (no blanks, no repeats). */
export function parseList(text: string): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const part of text.split(/[,\n]/)) {
    const item = part.trim()
    if (item && !seen.has(item.toLowerCase())) {
      seen.add(item.toLowerCase())
      out.push(item)
    }
  }
  return out
}

export interface VenueFormValues {
  name: string
  location: string
  capacity: string
  facilities: string
  accessibility_features: string
  supported_layouts: string
  operating_hours: string
}

export type VenueFormErrors = Partial<Record<keyof VenueFormValues, string>>

/** The reasons a form cannot be saved yet; empty when it can. */
export function venueFormErrors(v: VenueFormValues): VenueFormErrors {
  const errors: VenueFormErrors = {}
  if (!v.name.trim()) errors.name = 'Name is required.'
  if (!v.location.trim()) errors.location = 'Location is required.'
  if (!/^\d+$/.test(v.capacity.trim()) || Number(v.capacity) <= 0) {
    errors.capacity = 'Capacity must be a whole number above zero.'
  }
  if (parseList(v.supported_layouts).length === 0) {
    errors.supported_layouts = 'Add at least one supported room layout.'
  }
  if (!v.operating_hours.trim()) errors.operating_hours = 'Operating hours are required.'
  return errors
}

export function toVenueInput(v: VenueFormValues): VenueInput {
  return {
    name: v.name.trim(),
    location: v.location.trim(),
    capacity: Number(v.capacity),
    facilities: parseList(v.facilities),
    accessibility_features: parseList(v.accessibility_features),
    supported_layouts: parseList(v.supported_layouts),
    operating_hours: v.operating_hours.trim(),
  }
}

const json = (method: string, body: VenueInput): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export function addVenue(body: VenueInput): Promise<VenueSaved> {
  return apiFetch('/venues', json('POST', body)) as Promise<VenueSaved>
}

export function editVenue(id: number, body: VenueInput): Promise<VenueSaved> {
  return apiFetch(`/venues/${id}`, json('PUT', body)) as Promise<VenueSaved>
}

export function listVenueActivity(): Promise<VenueActivityEntry[]> {
  return apiFetch('/venues/activity') as Promise<VenueActivityEntry[]>
}
