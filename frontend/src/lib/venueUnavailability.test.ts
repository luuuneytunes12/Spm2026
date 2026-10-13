/** SCRUM-93 helpers: AC1 reasons, AC2 date validation, AC3 calendar text, AC5 notice. */
import { describe, expect, it } from 'vitest'
import { describeConflict } from './venueBookings'
import { UNAVAILABILITY_REASONS, describeAffected, describeBusyPeriod, unavailabilityErrors } from './venues'

describe('SCRUM-93 helpers', () => {
  it('ac1 offers exactly the five reasons', () => {
    expect([...UNAVAILABILITY_REASONS]).toEqual([
      'Maintenance',
      'Equipment failure',
      'Renovation',
      'Safety concern',
      'Other',
    ])
  })

  it('ac2 flags the dates when the end is not after the start', () => {
    expect(unavailabilityErrors('2030-11-02T10:00', '2030-11-02T09:00', 'Other').dates).toBe(
      'The end must be after the start.',
    )
    expect(unavailabilityErrors('2030-11-02T10:00', '2030-11-02T10:00', 'Other').dates).not.toBeNull()
  })

  it('ac1 requires both dates and a reason, and passes a valid period', () => {
    expect(unavailabilityErrors('', '2030-11-02T09:00', 'Other').dates).toMatch(/start/)
    expect(unavailabilityErrors('2030-11-02T09:00', '', 'Other').dates).toMatch(/end/)
    expect(unavailabilityErrors('2030-11-02T09:00', '2030-11-02T10:00', '').category).toBe('Choose a reason.')
    expect(unavailabilityErrors('2030-11-02T09:00', '2030-11-02T10:00', 'Other')).toEqual({
      dates: null,
      category: null,
    })
  })

  it('ac3 shows the reason on a closure in the calendar', () => {
    const text = describeBusyPeriod({
      kind: 'closure',
      start: '2030-11-02T01:00:00Z',
      end: '2030-11-02T05:00:00Z',
      reason_category: 'Renovation',
      reason: 'New floor',
    })
    expect(text).toMatch(/^Unavailable \(closed\): /)
    expect(text).toMatch(/- Renovation: New floor$/)
  })

  it('ac4 describes an unavailability conflict with its reason', () => {
    const d = describeConflict({
      kind: 'unavailability',
      booking_id: null,
      event_id: null,
      event_name: null,
      event_start: '2030-11-02T01:00:00Z',
      event_end: '2030-11-02T05:00:00Z',
      occupied_start: '2030-11-02T01:00:00Z',
      occupied_end: '2030-11-02T05:00:00Z',
      overlap_start: '2030-11-02T01:00:00Z',
      overlap_end: '2030-11-02T05:00:00Z',
      reason: 'Maintenance: Aircon',
    })
    expect(d.unavailable).toBe(true)
    expect(d.reason).toBe('Maintenance: Aircon')
  })

  it('ac5 says affected bookings were not cancelled', () => {
    expect(describeAffected(0)).toBeNull()
    expect(describeAffected(1)).toMatch(/1 future booking is inside.*not been cancelled/)
    expect(describeAffected(3)).toMatch(/3 future bookings are inside/)
  })
})
