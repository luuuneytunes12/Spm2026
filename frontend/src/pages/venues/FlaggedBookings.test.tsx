/** SCRUM-92 AC4/AC6 - Venue Staff's flagged-bookings page: each flagged
 *  booking with its overlap, and keeping one anyway with a reason. Whether
 *  the API flags or clears is backend/tests/test_booking_conflicts.py. */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/api'
import { FlaggedBookings } from './FlaggedBookings'

vi.mock('../../lib/venueBookings', async () => {
  const actual = await vi.importActual<typeof import('../../lib/venueBookings')>('../../lib/venueBookings')
  return { ...actual, listFlaggedBookings: vi.fn(), keepFlaggedBooking: vi.fn(), cancelFlaggedBooking: vi.fn() }
})
import { cancelFlaggedBooking, keepFlaggedBooking, listFlaggedBookings } from '../../lib/venueBookings'
import type { VenueBooking } from '../../lib/venueBookings'

const mockList = vi.mocked(listFlaggedBookings)
const mockKeep = vi.mocked(keepFlaggedBooking)
const mockCancel = vi.mocked(cancelFlaggedBooking)

const FLAGGED: VenueBooking = {
  id: 5,
  status: 'approved',
  created_at: '2026-10-01T02:00:00Z',
  event: { id: 7, name: 'Regional Partner Conference' },
  venue: { id: 3, name: 'Marina Hall', location: '10 Bayfront Ave', capacity: 250 },
  start_time: '2026-11-02T09:00:00Z',
  end_time: '2026-11-02T17:00:00Z',
  setup_minutes: 30,
  turnaround_minutes: 45,
  occupied_start: '2026-11-02T08:30:00Z',
  occupied_end: '2026-11-02T17:45:00Z',
  expires_at: null,
  expected_attendance: 120,
  room_layout_preference: null,
  accessibility_needs: null,
  facilities_needs: null,
  venue_requirements: null,
  requested_by: { name: 'Sam Tan', email: 'sam@connectsphere.test' },
  decision_notes: null,
  suggested_alternative: null,
  reviewed_by: null,
  reviewed_at: null,
  conflict_flagged: true,
  conflicts: [
    {
      booking_id: 6,
      event_id: 8,
      event_name: 'Alumni Dinner',
      event_start: '2026-11-02T17:30:00Z',
      event_end: '2026-11-02T20:00:00Z',
      occupied_start: '2026-11-02T17:30:00Z',
      occupied_end: '2026-11-02T20:00:00Z',
      overlap_start: '2026-11-02T17:30:00Z',
      overlap_end: '2026-11-02T17:45:00Z',
    },
  ],
}

beforeEach(() => vi.resetAllMocks())

describe('SCRUM-92 AC4 - flagged bookings are listed with their overlap', () => {
  it('AC4: shows the event, venue, conflicting event and overlap period', async () => {
    mockList.mockResolvedValue([FLAGGED])
    render(<FlaggedBookings />)
    const card = within(await screen.findByRole('region', { name: /Regional Partner Conference/ }))
    expect(card.getByText(/Conflict flagged - not counted as approved until resolved/)).toBeInTheDocument()
    expect(card.getByText(/Marina Hall/)).toBeInTheDocument()
    expect(card.getByText('Alumni Dinner')).toBeInTheDocument()
    expect(card.getByText(/Overlap:/)).toBeInTheDocument()
  })

  it('AC4: with nothing flagged it says so', async () => {
    mockList.mockResolvedValue([])
    render(<FlaggedBookings />)
    expect(await screen.findByText('No flagged bookings.')).toBeInTheDocument()
  })

  it('shows a load failure as an alert', async () => {
    mockList.mockRejectedValue(new ApiError(403, 'Not allowed.'))
    render(<FlaggedBookings />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Not allowed.')
  })
})

describe('SCRUM-92 AC6 - keep a flagged booking with a reason', () => {
  it('AC6: a blank reason is blocked beside the field and nothing is sent', async () => {
    mockList.mockResolvedValue([FLAGGED])
    render(<FlaggedBookings />)
    await userEvent.click(await screen.findByRole('button', { name: 'Keep anyway' }))
    const field = screen.getByLabelText(/Reason for keeping/)
    expect(await screen.findByRole('alert')).toHaveTextContent('Enter a reason')
    expect(field).toHaveAttribute('aria-invalid', 'true')
    expect(mockKeep).not.toHaveBeenCalled()
  })

  it('AC6: keeping sends the reason, then the booking leaves the list', async () => {
    mockList.mockResolvedValue([FLAGGED])
    mockKeep.mockResolvedValue({ ...FLAGGED, conflict_flagged: false })
    render(<FlaggedBookings />)
    await userEvent.type(await screen.findByLabelText(/Reason for keeping/), 'Both organisers agreed')
    await userEvent.click(screen.getByRole('button', { name: 'Keep anyway' }))
    expect(mockKeep).toHaveBeenCalledWith(5, 'Both organisers agreed')
    expect(await screen.findByText(/The flag is cleared/)).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: /Regional Partner Conference/ })).not.toBeInTheDocument()
  })

  it('AC6: a server refusal is shown beside the field and the booking stays', async () => {
    mockList.mockResolvedValue([FLAGGED])
    mockKeep.mockRejectedValue(new ApiError(409, 'This booking is not flagged.'))
    render(<FlaggedBookings />)
    await userEvent.type(await screen.findByLabelText(/Reason for keeping/), 'Because')
    await userEvent.click(screen.getByRole('button', { name: 'Keep anyway' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('This booking is not flagged.')
    expect(screen.getByRole('region', { name: /Regional Partner Conference/ })).toBeInTheDocument()
  })
})

describe('SCRUM-92 AC6 - cancel a flagged booking with a reason', () => {
  it('AC6: a blank reason blocks cancelling and nothing is sent', async () => {
    mockList.mockResolvedValue([FLAGGED])
    render(<FlaggedBookings />)
    await userEvent.click(await screen.findByRole('button', { name: 'Cancel booking' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Enter a reason for cancelling')
    expect(mockCancel).not.toHaveBeenCalled()
  })

  it('AC6: cancelling sends the reason, the booking leaves the list and the Event is said to stay', async () => {
    mockList.mockResolvedValue([FLAGGED])
    mockCancel.mockResolvedValue({ ...FLAGGED, status: 'cancelled', conflict_flagged: false })
    render(<FlaggedBookings />)
    await userEvent.type(await screen.findByLabelText(/Reason for keeping or cancelling/), 'Double booked')
    await userEvent.click(screen.getByRole('button', { name: 'Cancel booking' }))
    expect(mockCancel).toHaveBeenCalledWith(5, 'Double booked')
    expect(mockKeep).not.toHaveBeenCalled()
    expect(await screen.findByText(/The Event is not cancelled/)).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: /Regional Partner Conference/ })).not.toBeInTheDocument()
  })

  it('AC6: a server refusal is shown beside the field and the booking stays', async () => {
    mockList.mockResolvedValue([FLAGGED])
    mockCancel.mockRejectedValue(new ApiError(409, 'This booking is not flagged as conflicting.'))
    render(<FlaggedBookings />)
    await userEvent.type(await screen.findByLabelText(/Reason for keeping or cancelling/), 'Because')
    await userEvent.click(screen.getByRole('button', { name: 'Cancel booking' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('not flagged')
    expect(screen.getByRole('region', { name: /Regional Partner Conference/ })).toBeInTheDocument()
  })
})
