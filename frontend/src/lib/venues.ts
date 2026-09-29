// Mirror of backend/app/routers/venues.py and schemas/venue.py -- keep field
// names byte-identical. The backend decides who may see venues; nothing here
// is a security boundary.

import { apiFetch } from './api'

export interface VenueSummary {
  id: number
  name: string
  location: string
  capacity: number
  /** Shown on each search result, so a Coordinator can rule a venue in or
   *  out without opening it. */
  facilities: string[]
  /** Inactive venues are still listed, flagged, rather than hidden. */
  is_active: boolean
}

export interface VenueDetail extends VenueSummary {
  supported_layouts: string[]
  accessibility_features: string[]
  /** Free text as recorded by Venue Staff, possibly several lines. */
  operating_hours: string | null
}

/** What a Coordinator can search and filter venues by.
 *
 *  Every field is optional, and an empty search returns every venue -- the
 *  same list as before searching existed. The criteria combine with AND. */
export interface VenueSearch {
  /** Matched against name and location, partially, in any case. */
  q?: string
  /** Expected attendance: venues that hold fewer people are excluded. */
  minCapacity?: number
  /** One layout -- an event uses one. */
  layout?: string
  /** A venue must have EVERY facility listed, not just one of them. */
  facilities?: string[]
  /** Likewise: every accessibility feature listed. */
  accessibility?: string[]
  /** ISO 8601. Venues booked or blocked in [start, end) are excluded. Both
   *  or neither -- the server rejects half a window. */
  start?: string
  end?: string
}

/** The values the filters can offer.
 *
 *  Layouts, facilities and accessibility features are free text typed by
 *  Venue Staff, so the choices come from what has actually been recorded
 *  rather than a hard-coded list that could drift from the data. */
export interface VenueFilterOptions {
  layouts: string[]
  facilities: string[]
  accessibility_features: string[]
}

/** The query string for a search. Empty criteria are left out entirely, so
 *  a cleared filter means "no filter" rather than "match the empty string".
 *  Lists become repeated parameters (`facilities=a&facilities=b`), which is
 *  how the API reads them. */
export function venueSearchQuery(search: VenueSearch = {}): string {
  const params = new URLSearchParams()
  if (search.q?.trim()) params.set('q', search.q.trim())
  if (search.minCapacity !== undefined) params.set('min_capacity', String(search.minCapacity))
  if (search.layout) params.set('layout', search.layout)
  for (const facility of search.facilities ?? []) params.append('facilities', facility)
  for (const feature of search.accessibility ?? []) params.append('accessibility', feature)
  if (search.start) params.set('start', search.start)
  if (search.end) params.set('end', search.end)
  const query = params.toString()
  return query ? `?${query}` : ''
}

export function listVenues(search: VenueSearch = {}): Promise<VenueSummary[]> {
  return apiFetch(`/venues${venueSearchQuery(search)}`) as Promise<VenueSummary[]>
}

export function listVenueFilterOptions(): Promise<VenueFilterOptions> {
  return apiFetch('/venues/filter-options') as Promise<VenueFilterOptions>
}

/** Rejects with a 404 ApiError when the venue does not exist. */
export function getVenue(id: number): Promise<VenueDetail> {
  return apiFetch(`/venues/${id}`) as Promise<VenueDetail>
}
