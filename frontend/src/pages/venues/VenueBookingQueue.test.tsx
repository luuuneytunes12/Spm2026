/** SCRUM-39 AC2/AC3 - what Venue Staff see in the review queue. */
import { render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/api'
import { VenueBookingQueue } from './VenueBookingQueue'

vi.mock('../../lib/venueBookings', () => ({ listVenueBookingQueue: vi.fn() }))
import { listVenueBookingQueue } from '../../lib/venueBookings'
import type { VenueBooking } from '../../lib/venueBookings'

const mockQueue = vi.mocked(listVenueBookingQueue)

const BOOKING: VenueBooking = {
  id: 1,
  status: 'pending',
  created_at: '2026-10-01T02:00:00Z',
  event: { id: 7, name: 'Regional Partner Conference' },
  venue: { id: 3, name: 'Marina Hall', location: '10 Bayfront Ave', capacity: 250 },
  start_time: '2026-11-02T09:00:00Z',
  end_time: '2026-11-02T17:00:00Z',
  expected_attendance: 120,
  room_layout_preference: 'Theatre',
  accessibility_needs: 'Step-free access',
  venue_requirements: 'Main hall',
  requested_by: { name: 'Sam Tan', email: 'sam@connectsphere.test' },
}

beforeEach(() => vi.resetAllMocks())

describe('SCRUM-39 AC2 - the request appears in the queue', () => {
  it('lists each pending request under its event', async () => {
    mockQueue.mockResolvedValue([BOOKING])
    render(<VenueBookingQueue />)
    expect(await screen.findByRole('heading', { name: 'Regional Partner Conference' })).toBeInTheDocument()
  })

  it('says so plainly when the queue is empty', async () => {
    mockQueue.mockResolvedValue([])
    render(<VenueBookingQueue />)
    expect(await screen.findByText('No pending booking requests.')).toBeInTheDocument()
  })

  it('shows an error rather than an empty queue when it cannot load', async () => {
    mockQueue.mockRejectedValue(new ApiError(500, 'boom'))
    render(<VenueBookingQueue />)
    expect(await screen.findByRole('alert')).toHaveTextContent('boom')
  })
})

describe('SCRUM-39 AC3 - the request carries what Venue Staff need', () => {
  it('shows venue, date and time, attendance, layout, accessibility and facility needs', async () => {
    mockQueue.mockResolvedValue([BOOKING])
    render(<VenueBookingQueue />)
    const card = await screen.findByRole('region', { name: /Regional Partner Conference/ })
    const text = within(card)
    expect(text.getByText(/Marina Hall/)).toBeInTheDocument()
    expect(text.getByText('120')).toBeInTheDocument()
    expect(text.getByText('Theatre')).toBeInTheDocument()
    expect(text.getByText('Step-free access')).toBeInTheDocument()
    expect(text.getByText('Main hall')).toBeInTheDocument()
    expect(text.getByText(/Sam Tan/)).toBeInTheDocument()
    expect(text.getByText('Date and time')).toBeInTheDocument()
  })

  it('marks a need the event never stated instead of leaving a blank', async () => {
    mockQueue.mockResolvedValue([{ ...BOOKING, room_layout_preference: null, accessibility_needs: null }])
    render(<VenueBookingQueue />)
    expect((await screen.findAllByText('None given')).length).toBeGreaterThanOrEqual(2)
  })
})
