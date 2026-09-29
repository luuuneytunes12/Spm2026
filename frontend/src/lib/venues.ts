// Mirror of backend/app/routers/venues.py and schemas/venue.py -- keep field
// names byte-identical. The backend decides who may see venues; nothing here
// is a security boundary.

import { apiFetch } from './api'

export interface VenueSummary {
  id: number
  name: string
  location: string
  capacity: number
  /** Inactive venues are still listed, flagged, rather than hidden. */
  is_active: boolean
}

export interface VenueDetail extends VenueSummary {
  supported_layouts: string[]
  facilities: string[]
  accessibility_features: string[]
  /** Free text as recorded by Venue Staff, possibly several lines. */
  operating_hours: string | null
}

export function listVenues(): Promise<VenueSummary[]> {
  return apiFetch('/venues') as Promise<VenueSummary[]>
}

/** Rejects with a 404 ApiError when the venue does not exist. */
export function getVenue(id: number): Promise<VenueDetail> {
  return apiFetch(`/venues/${id}`) as Promise<VenueDetail>
}
