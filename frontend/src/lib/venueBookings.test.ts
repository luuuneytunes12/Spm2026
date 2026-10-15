/**
 * SCRUM-78 AC5/AC6: the occupancy periods shown wherever bookings are listed.
 * Dates are built in local time because the helper formats local times.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { apiFetch } from './api'
import {
  cancelFlaggedBooking,
  keepFlaggedBooking,
  listFlaggedBookings, describeConflict, formatBookingPeriods, formatPeriod } from './venueBookings'

vi.mock('./api', () => ({ apiFetch: vi.fn() }))
const mockFetch = vi.mocked(apiFetch)
beforeEach(() => mockFetch.mockReset())

const at = (h: number, m = 0) => new Date(2026, 10, 2, h, m).toISOString()

describe('formatBookingPeriods', () => {
  it('adds short dates when the event spans days', () => {
    const d = (day: number, h: number, m = 0) => new Date(2026, 11, day, h, m).toISOString()
    expect(
      formatBookingPeriods({ start_time: d(12, 12, 12), end_time: d(13, 12, 12), setup_minutes: 20, turnaround_minutes: 40 }),
    ).toBe('Event Dec 12 12:12 – Dec 13 12:12 | Setup 11:52-12:12 | Turnaround 12:12-12:52')
  })

  it('AC6: Event 10:00-12:00 with 30 setup and 45 turnaround reads as the whole occupied window', () => {
    expect(
      formatBookingPeriods({
        start_time: at(10),
        end_time: at(12),
        setup_minutes: 30,
        turnaround_minutes: 45,
        occupied_start: at(9, 30),
        occupied_end: at(12, 45),
      }),
    ).toBe('Event 10:00-12:00 | Setup 09:30-10:00 | Turnaround 12:00-12:45')
  })

  it('AC5: works the occupied window out from the minutes when the server omits it', () => {
    expect(
      formatBookingPeriods({ start_time: at(10), end_time: at(12), setup_minutes: 30, turnaround_minutes: 45 }),
    ).toBe('Event 10:00-12:00 | Setup 09:30-10:00 | Turnaround 12:00-12:45')
  })

  it('AC3: with nothing saved (0 minutes) setup and turnaround take no time', () => {
    expect(
      formatBookingPeriods({ start_time: at(10), end_time: at(12), setup_minutes: 0, turnaround_minutes: 0 }),
    ).toBe('Event 10:00-12:00 | Setup 10:00-10:00 | Turnaround 12:00-12:00')
  })
})

describe('SCRUM-41 conflict formatting', () => {
  it('AC5: a same-day period reads as date plus times', () => {
    expect(formatPeriod(at(9, 30), at(12, 45))).toMatch(/2026, 09:30-12:45$/)
  })

  it('AC5: a period over midnight carries both dates', () => {
    const next = new Date(2026, 10, 3, 1, 0).toISOString()
    expect(formatPeriod(at(22), next)).toMatch(/22:00 to .*2026 01:00$/)
  })

  it('AC5: a conflict names the event, its occupied period and the overlap', () => {
    const d = describeConflict({
      booking_id: 1,
      event_id: 2,
      event_name: 'Alumni Gala',
      event_start: at(10),
      event_end: at(12),
      occupied_start: at(9, 30),
      occupied_end: at(12, 45),
      overlap_start: at(11),
      overlap_end: at(12, 45),
    })
    expect(d.name).toBe('Alumni Gala')
    expect(d.occupied).toMatch(/09:30-12:45$/)
    expect(d.overlap).toMatch(/11:00-12:45$/)
  })

  it('AC5: an unnamed event still reads sensibly', () => {
    const d = describeConflict({
      booking_id: 1, event_id: 2, event_name: null,
      event_start: at(10), event_end: at(12), occupied_start: at(10), occupied_end: at(12),
      overlap_start: at(10), overlap_end: at(12),
    })
    expect(d.name).toBe('Another event')
  })
})

describe('SCRUM-92 API helpers', () => {
  it('AC4: lists flagged bookings from /venue-bookings/flagged', async () => {
    mockFetch.mockResolvedValue([])
    await listFlaggedBookings()
    expect(mockFetch).toHaveBeenCalledWith('/venue-bookings/flagged')
  })

  it('AC6: cancelling a flagged booking posts the reason to cancel-flagged', async () => {
    mockFetch.mockResolvedValue({})
    await cancelFlaggedBooking(9, 'Double booked')
    expect(mockFetch).toHaveBeenCalledWith('/venue-bookings/9/cancel-flagged', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: 'Double booked' }),
    })
  })

  it('AC6: keeping a flagged booking posts the reason to keep-conflict', async () => {
    mockFetch.mockResolvedValue({})
    await keepFlaggedBooking(9, 'Agreed with both organisers')
    expect(mockFetch).toHaveBeenCalledWith('/venue-bookings/9/keep-conflict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: 'Agreed with both organisers' }),
    })
  })
})

describe('bookingPeriodParts', () => {
  it('returns labelled parts matching formatBookingPeriods, falling back to the minutes', async () => {
    const { bookingPeriodParts, formatBookingPeriods } = await import('./venueBookings')
    const b = { start_time: '2026-11-02T10:00:00', end_time: '2026-11-02T12:00:00', setup_minutes: 30, turnaround_minutes: 45 }
    const parts = bookingPeriodParts(b)
    expect(parts).toEqual([
      { label: 'Event', text: '10:00-12:00' },
      { label: 'Setup', text: '09:30-10:00' },
      { label: 'Turnaround', text: '12:00-12:45' },
    ])
    expect(formatBookingPeriods(b)).toBe('Event 10:00-12:00 | Setup 09:30-10:00 | Turnaround 12:00-12:45')
  })
})
