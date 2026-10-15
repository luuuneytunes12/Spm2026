/**
 * Unit tests for the client calls behind "Change or Cancel One Venue Booking"
 * (SCRUM-96). Whether the server accepts or refuses is
 * backend/tests/test_venue_booking_change_cancel.py; these pin what is sent.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  LIVE_BOOKING_STATUSES,
  cancelAllVenueBookings,
  cancelVenueBooking,
  changeVenueBooking,
  isLiveBooking,
  listCancellableVenueBookings,
} from './venueBookings'

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api')
  return { ...actual, apiFetch: vi.fn() }
})

import { apiFetch } from './api'

const mockFetch = vi.mocked(apiFetch)
const JSON_HEADERS = { 'Content-Type': 'application/json' }

beforeEach(() => {
  vi.clearAllMocks()
  mockFetch.mockResolvedValue({})
})

describe('which bookings are live', () => {
  it('is pending, held and approved: the ones that can still be changed or cancelled', () => {
    expect([...LIVE_BOOKING_STATUSES].sort()).toEqual(['approved', 'pending', 'tentative_hold'])
  })

  it.each(['pending', 'tentative_hold', 'approved'] as const)('treats %s as live', (status) => {
    expect(isLiveBooking(status)).toBe(true)
  })

  it.each(['rejected', 'cancelled'] as const)('treats %s as history', (status) => {
    expect(isLiveBooking(status)).toBe(false)
  })
})

describe('changing one booking', () => {
  it('sends a PATCH to that booking with only what changed', async () => {
    await changeVenueBooking(5, { venue_id: 9 })

    expect(mockFetch).toHaveBeenCalledWith('/venue-bookings/5', {
      method: 'PATCH',
      headers: JSON_HEADERS,
      body: JSON.stringify({ venue_id: 9 }),
    })
  })

  it('sends a cleared need as null, so it goes back to what the event says', async () => {
    await changeVenueBooking(5, { facilities_needs: null })

    const body = JSON.parse((mockFetch.mock.calls[0][1] as { body: string }).body)
    expect(body).toEqual({ facilities_needs: null })
  })

  it('sends no time: a booking has the event’s', async () => {
    await changeVenueBooking(5, { venue_id: 9, room_layout_preference: 'Classroom' })

    const body = JSON.parse((mockFetch.mock.calls[0][1] as { body: string }).body)
    expect(Object.keys(body).sort()).toEqual(['room_layout_preference', 'venue_id'])
  })
})

describe('cancelling one booking', () => {
  it('sends a POST to that booking’s cancel, with no reason when none is given', async () => {
    await cancelVenueBooking(5)

    expect(mockFetch).toHaveBeenCalledWith('/venue-bookings/5/cancel', {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify({}),
    })
  })

  it('sends the reason when there is one', async () => {
    await cancelVenueBooking(5, 'Roof leak')

    expect(mockFetch).toHaveBeenCalledWith('/venue-bookings/5/cancel', {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify({ reason: 'Roof leak' }),
    })
  })

  it('leaves out a reason that is only spaces', async () => {
    await cancelVenueBooking(5, '   ')

    const body = JSON.parse((mockFetch.mock.calls[0][1] as { body: string }).body)
    expect(body).toEqual({})
  })
})

describe('cancelling all of an event’s bookings', () => {
  it('asks the server for the list to be confirmed', async () => {
    await listCancellableVenueBookings(7)

    expect(mockFetch).toHaveBeenCalledWith('/venue-bookings/events/7/cancellable')
  })

  it('sends the ids that were listed, so only those can be cancelled', async () => {
    await cancelAllVenueBookings(7, [1, 2, 3])

    expect(mockFetch).toHaveBeenCalledWith('/venue-bookings/events/7/cancel-all', {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify({ booking_ids: [1, 2, 3] }),
    })
  })

  it('sends the reason too, when there is one', async () => {
    await cancelAllVenueBookings(7, [1], 'Moving venue')

    const body = JSON.parse((mockFetch.mock.calls[0][1] as { body: string }).body)
    expect(body).toEqual({ booking_ids: [1], reason: 'Moving venue' })
  })
})
