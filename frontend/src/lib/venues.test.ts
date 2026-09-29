/**
 * Unit tests for turning a venue search into a query string.
 *
 * Traceability (see docs/test-cases-venue-search.md): the wire format every
 * criterion in VS AC1-AC3 travels in. The page tests mock `listVenues`, so
 * without these nothing would check that the criteria actually reach the
 * API in the shape it reads.
 */
import { describe, expect, it } from 'vitest'
import { venueSearchQuery } from './venues'

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
