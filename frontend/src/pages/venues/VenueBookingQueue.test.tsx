/** SCRUM-39 AC2/AC3 - what Venue Staff see in the review queue -- and the
 *  "Approve or Reject Venue Booking Request" story: deciding from it.
 *  Whether the API accepts a decision is backend/tests/test_venue_booking_decision.py;
 *  these tests cover what the queue sends and does with the answer. */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/api'
import { VenueBookingQueue } from './VenueBookingQueue'

vi.mock('../../lib/venueBookings', async () => {
  const actual = await vi.importActual<typeof import('../../lib/venueBookings')>('../../lib/venueBookings')
  return { ...actual, listVenueBookingQueue: vi.fn(), approveVenueBooking: vi.fn(), rejectVenueBooking: vi.fn() }
})
import { approveVenueBooking, listVenueBookingQueue, rejectVenueBooking } from '../../lib/venueBookings'
import type { VenueBooking } from '../../lib/venueBookings'

const mockQueue = vi.mocked(listVenueBookingQueue)
const mockApprove = vi.mocked(approveVenueBooking)
const mockReject = vi.mocked(rejectVenueBooking)

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
  decision_notes: null,
  suggested_alternative: null,
  reviewed_by: null,
  reviewed_at: null,
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

const DECIDED = { reviewed_by: { name: 'Vera Staff', email: 'vera@connectsphere.test' }, reviewed_at: '2026-10-02T03:00:00Z' }
const APPROVED: VenueBooking = { ...BOOKING, ...DECIDED, status: 'approved' }
const REJECTED: VenueBooking = { ...BOOKING, ...DECIDED, status: 'rejected', decision_notes: 'Closed for repairs.' }
const OTHER: VenueBooking = { ...BOOKING, id: 2, event: { id: 8, name: 'Staff Town Hall' } }

async function openRejection() {
  const card = await screen.findByRole('region', { name: /Regional Partner Conference/ })
  await userEvent.click(within(card).getByRole('button', { name: 'Reject' }))
  return within(card)
}

describe('AC2 - Venue Staff can approve or reject a request', () => {
  it('offers both decisions on every pending request', async () => {
    mockQueue.mockResolvedValue([BOOKING, OTHER])
    render(<VenueBookingQueue />)
    for (const name of [/Regional Partner Conference/, /Staff Town Hall/]) {
      const card = within(await screen.findByRole('region', { name }))
      expect(card.getByRole('button', { name: 'Approve' })).toBeEnabled()
      expect(card.getByRole('button', { name: 'Reject' })).toBeEnabled()
    }
  })

  it('approves the request, takes it out of the queue and confirms the decision', async () => {
    mockQueue.mockResolvedValue([BOOKING, OTHER])
    mockApprove.mockResolvedValue(APPROVED)
    render(<VenueBookingQueue />)
    const card = await screen.findByRole('region', { name: /Regional Partner Conference/ })
    await userEvent.click(within(card).getByRole('button', { name: 'Approve' }))

    expect(mockApprove).toHaveBeenCalledWith(1)
    expect(await screen.findByRole('status')).toHaveTextContent('Approved: Marina Hall for Regional Partner Conference')
    expect(screen.getByRole('status')).toHaveFocus()
    expect(screen.queryByRole('region', { name: /Regional Partner Conference/ })).not.toBeInTheDocument()
    expect(screen.getByRole('region', { name: /Staff Town Hall/ })).toBeInTheDocument()
  })

  it('rejects the request, takes it out of the queue and confirms the decision', async () => {
    mockQueue.mockResolvedValue([BOOKING])
    mockReject.mockResolvedValue(REJECTED)
    render(<VenueBookingQueue />)
    const card = await openRejection()
    await userEvent.type(card.getByLabelText('Reason'), 'Closed for repairs.')
    await userEvent.click(card.getByRole('button', { name: 'Confirm rejection' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Rejected: Marina Hall')
    expect(screen.getByText('No pending booking requests.')).toBeInTheDocument()
  })

  it('shows why a decision was refused and keeps the request in the queue', async () => {
    mockQueue.mockResolvedValue([BOOKING])
    mockApprove.mockRejectedValue(new ApiError(409, 'The venue is already booked for another event at that time.'))
    render(<VenueBookingQueue />)
    const card = within(await screen.findByRole('region', { name: /Regional Partner Conference/ }))
    await userEvent.click(card.getByRole('button', { name: 'Approve' }))

    expect(await card.findByRole('alert')).toHaveTextContent('already booked')
    expect(card.getByRole('button', { name: 'Reject' })).toBeEnabled() // can still be rejected
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})

describe('AC3 - a rejection records a reason, an alternative, or both', () => {
  it.each([
    ['a reason only', 'Closed for repairs.', ''],
    ['an alternative only', '', 'Try Hall B.'],
    ['both', 'Closed for repairs.', 'Try Hall B.'],
  ])('sends %s', async (_case, reason, alternative) => {
    mockQueue.mockResolvedValue([BOOKING])
    mockReject.mockResolvedValue(REJECTED)
    render(<VenueBookingQueue />)
    const card = await openRejection()
    if (reason) await userEvent.type(card.getByLabelText('Reason'), reason)
    if (alternative) await userEvent.type(card.getByLabelText('Suggested alternative'), alternative)
    await userEvent.click(card.getByRole('button', { name: 'Confirm rejection' }))

    expect(mockReject).toHaveBeenCalledWith(1, { reason, suggested_alternative: alternative })
  })

  it('cannot be confirmed with neither, or with only spaces', async () => {
    mockQueue.mockResolvedValue([BOOKING])
    render(<VenueBookingQueue />)
    const card = await openRejection()
    expect(card.getByRole('button', { name: 'Confirm rejection' })).toBeDisabled()
    await userEvent.type(card.getByLabelText('Reason'), '   ')
    expect(card.getByRole('button', { name: 'Confirm rejection' })).toBeDisabled()
    expect(mockReject).not.toHaveBeenCalled()
  })

  it('can be cancelled, leaving the request undecided', async () => {
    mockQueue.mockResolvedValue([BOOKING])
    render(<VenueBookingQueue />)
    const card = await openRejection()
    await userEvent.click(card.getByRole('button', { name: 'Cancel' }))
    expect(card.getByRole('button', { name: 'Approve' })).toBeInTheDocument()
    expect(mockReject).not.toHaveBeenCalled()
  })
})
