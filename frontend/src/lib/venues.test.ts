/**
 * Unit tests for turning a venue search into a query string.
 *
 * Traceability (see docs/test-cases-venue-search.md): the wire format every
 * criterion in VS AC1-AC3 travels in. The page tests mock `listVenues`, so
 * without these nothing would check that the criteria actually reach the
 * API in the shape it reads.
 */
import { describe, expect, it } from 'vitest'
import { availabilityRangeError, describeBusyPeriod, describeRecheck, describeMinutes, minutesError, venueSearchQuery } from './venues'

describe('venueSearchQuery', () => {
  it('is empty for an empty search, so the plain list is requested', () => {
    expect(venueSearchQuery()).toBe('')
    expect(venueSearchQuery({})).toBe('')
  })

  it('VS AC1: sends the keyword trimmed, and drops one that is only spaces', () => {
    expect(venueSearchQuery({ q: '  marina ' })).toBe('?q=marina')
    expect(venueSearchQuery({ q: '   ' })).toBe('')
  })

  it('VS AC3: sends expected attendance as min_capacity', () => {
    expect(venueSearchQuery({ minCapacity: 120 })).toBe('?min_capacity=120')
  })

  it('VS AC2: repeats the parameter for each facility and accessibility feature', () => {
    const query = new URLSearchParams(
      venueSearchQuery({
        facilities: ['Projector', 'Video conferencing'],
        accessibility: ['Hearing loop'],
      }).slice(1),
    )

    // Repeated keys, not one comma-joined value -- a facility name could
    // itself contain a comma, and the API reads a list from repeats.
    expect(query.getAll('facilities')).toEqual(['Projector', 'Video conferencing'])
    expect(query.getAll('accessibility')).toEqual(['Hearing loop'])
  })

  it('VS AC2: sends a single layout', () => {
    expect(venueSearchQuery({ layout: 'Theatre' })).toBe('?layout=Theatre')
  })

  it('VS AC3: sends the time window as given', () => {
    const query = new URLSearchParams(
      venueSearchQuery({ start: '2026-11-02T01:00:00.000Z', end: '2026-11-02T09:00:00.000Z' }).slice(1),
    )

    expect(query.get('start')).toBe('2026-11-02T01:00:00.000Z')
    expect(query.get('end')).toBe('2026-11-02T09:00:00.000Z')
  })

  it('leaves out every criterion that was not given', () => {
    const query = new URLSearchParams(venueSearchQuery({ q: 'hall', facilities: [] }).slice(1))

    expect([...query.keys()]).toEqual(['q'])
  })
})

describe('SCRUM-78 AC2: minutesError', () => {
  it('accepts whole minutes, 0 or more', () => {
    for (const ok of ['0', '30', ' 45 ']) expect(minutesError('Setup time', ok)).toBeNull()
  })

  it('blocks an empty value', () => {
    expect(minutesError('Setup time', '')).toMatch(/required/)
    expect(minutesError('Setup time', '   ')).toMatch(/required/)
  })

  it('blocks a negative value', () => {
    expect(minutesError('Setup time', '-5')).toMatch(/cannot be negative/)
  })

  it('blocks a value that is not a whole number', () => {
    for (const bad of ['1.5', 'abc', '1e3', '10 min']) {
      expect(minutesError('Setup time', bad), bad).toMatch(/whole number/)
    }
  })
})

describe('SCRUM-78 AC3: describeMinutes', () => {
  it('says not set, and that 0 is used, when nothing is saved', () => {
    expect(describeMinutes(null)).toBe('Not set - 0 minutes is used')
  })

  it('shows saved minutes, including 0', () => {
    expect(describeMinutes(30)).toBe('30 minutes')
    expect(describeMinutes(0)).toBe('0 minutes')
  })
})

describe('SCRUM-41 availability helpers', () => {
  const at = (h: number, m = 0) => new Date(2026, 10, 2, h, m).toISOString()

  it('AC2: a booking is shown as its occupied window with the event name', () => {
    expect(describeBusyPeriod({ kind: 'booking', start: at(9, 30), end: at(12, 45), event_name: 'Alumni Gala' }))
      .toMatch(/^Booked for Alumni Gala: .*2026, 09:30-12:45$/)
  })

  it('AC2: the event name is left out when the server withholds it', () => {
    expect(describeBusyPeriod({ kind: 'booking', start: at(9), end: at(10), event_name: null }))
      .toMatch(/^Booked: .*09:00-10:00$/)
  })

  it('AC2: a closure is described as unavailable', () => {
    expect(describeBusyPeriod({ kind: 'closure', start: at(9), end: at(10) })).toMatch(/^Unavailable \(closed\): /)
  })

  it('AC2: the date range needs both ends, and the end after the start', () => {
    expect(availabilityRangeError('', '2026-11-02T10:00')).toMatch(/start/)
    expect(availabilityRangeError('2026-11-02T10:00', '')).toMatch(/end/)
    expect(availabilityRangeError('2026-11-02T10:00', '2026-11-02T10:00')).toMatch(/after the start/)
    expect(availabilityRangeError('2026-11-02T11:00', '2026-11-02T10:00')).toMatch(/after the start/)
    expect(availabilityRangeError('2026-11-02T10:00', '2026-11-02T11:00')).toBeNull()
  })
})

describe('SCRUM-92 AC1/AC3 - the re-check status line', () => {
  it('AC1: names how many bookings were flagged and how many flags cleared', () => {
    expect(describeRecheck({ flagged: 2, cleared: 1 })).toBe('2 existing bookings flagged for conflict; 1 flag cleared.')
    expect(describeRecheck({ flagged: 1, cleared: 3 })).toBe('1 existing booking flagged for conflict; 3 flags cleared.')
  })

  it('AC3: when nothing is flagged or cleared it says no booking conflicts', () => {
    expect(describeRecheck({ flagged: 0, cleared: 0 })).toBe('No existing bookings conflict.')
  })

  it('shows nothing when the server did no re-check', () => {
    expect(describeRecheck(null)).toBeNull()
    expect(describeRecheck(undefined)).toBeNull()
  })
})
