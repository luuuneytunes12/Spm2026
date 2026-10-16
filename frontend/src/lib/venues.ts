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
  /** Whole minutes of setup before an Event, or null when Venue Staff have
   *  not saved one (0 minutes is then used). */
  setup_minutes: number | null
  /** Whole minutes of turnaround after an Event; null as above. */
  turnaround_minutes: number | null
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

/** One calendar entry. `start_time`/`end_time` are the event itself;
 *  `occupied_*` add the venue's setup and turnaround (the period it really
 *  holds the venue). `event_id`/`event_name` are null unless the caller is
 *  Venue Staff or the event's own Coordinator. */
export interface VenueAvailabilityItem {
  id: number
  kind: 'confirmed_booking' | 'tentative_hold' | 'unavailability'
  start_time: string
  end_time: string
  occupied_start?: string | null
  occupied_end?: string | null
  event_id: number | null
  event_name: string | null
  reason_category?: string | null
  reason: string | null
  expires_at: string | null
  /** Tentative holds, Venue Staff only: what the Coordinator must do. */
  hold_action?: string | null
  conflicts_with_unavailability: boolean
}

/** `busy` and `items` describe the same periods; see the server docstring. */
export interface VenueAvailability {
  venue_id: number
  start: string
  end: string
  busy: BusyPeriod[]
  items: VenueAvailabilityItem[]
}

export interface VenueSuitabilityCheck {
  category: 'capacity' | 'layout' | 'accessibility' | 'facility'
  requirement: string
  available: string
  met: boolean
  message: string
}

export interface VenueSuitability {
  venue_id: number
  event_id: number
  event_name: string | null
  suitable: boolean
  checks: VenueSuitabilityCheck[]
}

export interface EventVenueSuitability {
  event_id: number
  event_name: string | null
  suitable: boolean
  venues: {
    booking_id: number
    venue_id: number
    venue_name: string
    expected_attendance: number | null
    suitable: boolean
    checks: VenueSuitabilityCheck[]
  }[]
  combined_capacity: {
    required_capacity: number | null
    available_capacity: number
    met: boolean
    message: string
  }
}

export type VenueBookingSuitability = EventVenueSuitability['venues'][number]

/** Recalculate one active booking using its current attendance and needs. */
export function checkVenueBookingSuitability(
  bookingId: number,
): Promise<VenueBookingSuitability> {
  return apiFetch(`/venues/bookings/${bookingId}/suitability`) as Promise<VenueBookingSuitability>
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

export interface SetupTurnaround {
  setup_minutes: number
  turnaround_minutes: number
}

/** Why a typed minutes value cannot be saved, or null when it can. Must be a
 *  non-empty, whole, non-negative number -- the server checks the same. */
export function minutesError(label: string, raw: string): string | null {
  const text = raw.trim()
  if (text === '') return `${label} is required. Enter a whole number of minutes, 0 or more.`
  if (!/^-?\d+$/.test(text)) return `${label} must be a whole number of minutes, such as 30.`
  if (Number(text) < 0) return `${label} cannot be negative. Enter 0 or more minutes.`
  return null
}

/** What is shown for a venue's saved minutes: the value, or the explicit
 *  not-set notice (0 minutes is what bookings use then). */
export function describeMinutes(minutes: number | null): string {
  return minutes === null ? 'Not set - 0 minutes is used' : `${minutes} minutes`
}

/** What re-checking the venue's future approved bookings found after a save:
 *  how many were newly flagged as conflicting and how many earlier flags no
 *  longer apply. Null (or absent) when the server did no re-check. */
export interface Recheck {
  flagged: number
  cleared: number
}

export type SavedSetupTurnaround = VenueDetail & { recheck?: Recheck | null }

/** The status line shown after a save, from the re-check result. */
export function describeRecheck(recheck: Recheck | null | undefined): string | null {
  if (!recheck) return null
  if (recheck.flagged === 0 && recheck.cleared === 0) return 'No existing bookings conflict.'
  const bookings = (n: number) => `${n} existing booking${n === 1 ? '' : 's'}`
  const flags = (n: number) => `${n} flag${n === 1 ? '' : 's'}`
  return `${bookings(recheck.flagged)} flagged for conflict; ${flags(recheck.cleared)} cleared.`
}

/** Venue Staff only (403 otherwise). A 422 ApiError carries the server's
 *  reasons in `fields` / `messages`. */
export function saveSetupTurnaround(id: number, values: SetupTurnaround): Promise<SavedSetupTurnaround> {
  return apiFetch(`/venues/${id}/setup-turnaround`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(values),
  }) as Promise<SavedSetupTurnaround>
}

/** One period in which a venue is not free. A 'booking' window is the
 *  OCCUPIED one (event plus setup and turnaround); `event_*` give the event
 *  itself. `event_name` is null unless the caller is Venue Staff. */
export interface BusyPeriod {
  kind: 'booking' | 'tentative_hold' | 'closure'
  start: string
  end: string
  event_start?: string | null
  event_end?: string | null
  event_name?: string | null
  /** Closures only (SCRUM-93): why the venue is unavailable. */
  reason_category?: string | null
  reason?: string | null
  /** Tentative holds only: when the hold lapses. */
  expires_at?: string | null
  /** Tentative holds, Venue Staff only: what the Coordinator must do. */
  hold_action?: string | null
}

/** Coordinator and Venue Staff. The window is [start, end), ISO 8601. */
export function getVenueAvailability(id: number, start: string, end: string): Promise<VenueAvailability> {
  const params = new URLSearchParams({ start, end })
  return apiFetch(`/venues/${id}/availability?${params.toString()}`) as Promise<VenueAvailability>
}

/** Why a typed date-time range cannot be checked, or null when it can.
 *  `start` and `end` are the raw `datetime-local` values (`YYYY-MM-DDTHH:mm`). */
export function availabilityRangeError(start: string, end: string): string | null {
  if (!start) return 'Choose a start date and time.'
  if (!end) return 'Choose an end date and time.'
  const s = new Date(start).getTime()
  const e = new Date(end).getTime()
  if (Number.isNaN(s) || Number.isNaN(e)) return 'Enter valid dates and times.'
  if (e <= s) return 'The end must be after the start.'
  return null
}

const time = (d: Date) =>
  `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
const day = (d: Date) => d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })

function span(startIso: string, endIso: string): string {
  const s = new Date(startIso)
  const e = new Date(endIso)
  return s.toDateString() === e.toDateString()
    ? `${day(s)}, ${time(s)}-${time(e)}`
    : `${day(s)} ${time(s)} to ${day(e)} ${time(e)}`
}

/** One busy period as a line of text. Bookings read as occupied (setup and
 *  turnaround included), with the event name when the caller may see it. */
export function describeBusyPeriod(p: BusyPeriod): string {
  const when = span(p.start, p.end)
  if (p.kind === 'closure') {
    const why = p.reason_category ? ` - ${p.reason_category}${p.reason ? `: ${p.reason}` : ''}` : ''
    return `Unavailable (closed): ${when}${why}`
  }
  if (p.kind === 'tentative_hold') {
    const until = p.expires_at ? ` (expires ${new Date(p.expires_at).toLocaleString()})` : ''
    const action = p.hold_action ? `. Required action: ${p.hold_action}` : ''
    return `${p.event_name ? `Tentative hold for ${p.event_name}` : 'Tentative hold'}: ${when}${until}${action}`
  }
  return p.event_name ? `Booked for ${p.event_name}: ${when}` : `Booked: ${when}`
}

/** The reasons Venue Staff choose from (SCRUM-93); the server holds the same list. */
export const UNAVAILABILITY_REASONS = [
  'Maintenance',
  'Equipment failure',
  'Renovation',
  'Safety concern',
  'Other',
] as const

export type UnavailabilityReason = (typeof UNAVAILABILITY_REASONS)[number]

/** A future booking inside a period. Identified only: it is not cancelled. */
export interface AffectedBooking {
  booking_id: number
  event_id: number
  event_name: string
  status: string
  start_time: string
  end_time: string
  flagged: boolean
}

export interface Unavailability {
  id: number
  venue_id: number
  start_time: string
  end_time: string
  reason_category: UnavailabilityReason
  reason: string | null
  updated_at: string | null
  /** Venue Staff only. */
  affected_bookings: AffectedBooking[]
  /** Only in the response to a save or end. */
  recheck?: Recheck | null
}

export interface UnavailabilityInput {
  start_time: string
  end_time: string
  reason_category: UnavailabilityReason
  reason: string | null
}

/** Why a typed period cannot be saved. `dates` covers both date fields (they
 *  are flagged together, e.g. when the end is not after the start). `start`
 *  and `end` are raw `datetime-local` values. Null for what is fine. */
export function unavailabilityErrors(
  start: string,
  end: string,
  category: string,
): { dates: string | null; category: string | null } {
  let dates: string | null = null
  if (!start) dates = 'Choose a start date and time.'
  else if (!end) dates = 'Choose an end date and time.'
  else {
    const s = new Date(start).getTime()
    const e = new Date(end).getTime()
    if (Number.isNaN(s) || Number.isNaN(e)) dates = 'Enter valid dates and times.'
    else if (e <= s) dates = 'The end must be after the start.'
  }
  return { dates, category: category ? null : 'Choose a reason.' }
}

/** The status line after saving: how many bookings lie inside the period. */
export function describeAffected(count: number): string | null {
  if (count === 0) return null
  return `${count} future booking${count === 1 ? ' is' : 's are'} inside this period. They are listed below and have not been cancelled.`
}

export function listUnavailability(venueId: number): Promise<Unavailability[]> {
  return apiFetch(`/venues/${venueId}/unavailability`) as Promise<Unavailability[]>
}

const json = { 'Content-Type': 'application/json' }

/** Venue Staff only (403 otherwise). A 422 ApiError names `end_time` when the
 *  end is not after the start. */
export function createUnavailability(venueId: number, input: UnavailabilityInput): Promise<Unavailability> {
  return apiFetch(`/venues/${venueId}/unavailability`, {
    method: 'POST',
    headers: json,
    body: JSON.stringify(input),
  }) as Promise<Unavailability>
}

export function updateUnavailability(
  venueId: number,
  id: number,
  input: UnavailabilityInput,
): Promise<Unavailability> {
  return apiFetch(`/venues/${venueId}/unavailability/${id}`, {
    method: 'PUT',
    headers: json,
    body: JSON.stringify(input),
  }) as Promise<Unavailability>
}

/** Sets the end of a period that is under way to now. */
export function endUnavailabilityEarly(venueId: number, id: number): Promise<Unavailability> {
  return apiFetch(`/venues/${venueId}/unavailability/${id}/end`, { method: 'POST' }) as Promise<Unavailability>
}

export function deleteUnavailability(venueId: number, id: number): Promise<void> {
  return apiFetch(`/venues/${venueId}/unavailability/${id}`, { method: 'DELETE' }) as Promise<void>
}

export function checkVenueSuitability(id: number, eventId: number): Promise<VenueSuitability> {
  return apiFetch(`/venues/${id}/suitability/${eventId}`) as Promise<VenueSuitability>
}

export function checkEventVenueSuitability(eventId: number): Promise<EventVenueSuitability> {
  return apiFetch(`/venues/events/${eventId}/suitability`) as Promise<EventVenueSuitability>
}
