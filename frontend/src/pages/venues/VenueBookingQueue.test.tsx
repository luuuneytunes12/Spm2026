/** SCRUM-39 AC2/AC3 - what Venue Staff see in the review queue -- and the
 *  "Approve or Reject Venue Booking Request" story: deciding from it.
 *  Whether the API accepts a decision is backend/tests/test_venue_booking_decision.py;
 *  these tests cover what the queue sends and does with the answer. */
import { fireEvent, render as rtlRender, screen, within } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/api'
import { VenueBookingQueue } from './VenueBookingQueue'

const render = (ui: ReactElement) => rtlRender(<MemoryRouter>{ui}</MemoryRouter>)

vi.mock('../../lib/venueBookings', async () => {
  const actual = await vi.importActual<typeof import('../../lib/venueBookings')>('../../lib/venueBookings')
  return {
    ...actual,
    listVenueBookingQueue: vi.fn(),
    listApprovedBookings: vi.fn(),
    listFlaggedBookings: vi.fn(),
    keepFlaggedBooking: vi.fn(),
    cancelFlaggedBooking: vi.fn(),
    approveVenueBooking: vi.fn(),
    rejectVenueBooking: vi.fn(),
    holdVenueBooking: vi.fn(),
  }
})
import {
  approveVenueBooking,
  cancelFlaggedBooking,
  holdVenueBooking,
  keepFlaggedBooking,
  listApprovedBookings,
  listFlaggedBookings,
  listVenueBookingQueue,
  rejectVenueBooking,
} from '../../lib/venueBookings'
import type { VenueBooking } from '../../lib/venueBookings'

const mockQueue = vi.mocked(listVenueBookingQueue)
const mockApprove = vi.mocked(approveVenueBooking)
const mockReject = vi.mocked(rejectVenueBooking)
const mockHold = vi.mocked(holdVenueBooking)
const mockKeep = vi.mocked(keepFlaggedBooking)
const mockCancel = vi.mocked(cancelFlaggedBooking)

const BOOKING: VenueBooking = {
  id: 1,
  status: 'pending',
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
  room_layout_preference: 'Theatre',
  accessibility_needs: 'Step-free access',
  facilities_needs: 'Main hall',
  venue_requirements: 'Main hall',
  requested_by: { name: 'Sam Tan', email: 'sam@connectsphere.test' },
  decision_notes: null,
  suggested_alternative: null,
  reviewed_by: null,
  reviewed_at: null,
}

const mockApproved = vi.mocked(listApprovedBookings)
const mockFlagged = vi.mocked(listFlaggedBookings)

beforeEach(() => {
  vi.resetAllMocks()
  mockApproved.mockResolvedValue([])
  mockFlagged.mockResolvedValue([])
})

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
    await userEvent.click(await screen.findByRole('button', { name: 'List' }))
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

describe('SCRUM-78 AC6 - the queue shows the event time, setup and turnaround', () => {
  it('shows the Event, Setup and Turnaround periods on each request', async () => {
    mockQueue.mockResolvedValue([BOOKING])
    render(<VenueBookingQueue />)
    await screen.findByRole('heading', { name: 'Regional Partner Conference' })
    expect(screen.getByText('Time breakdown')).toBeInTheDocument()
    expect(screen.getByText('Effective occupied time')).toBeInTheDocument()
    for (const label of ['Event', 'Setup', 'Turnaround']) {
      const li = screen.getByText(label, { selector: 'strong' }).closest('li')!
      expect(li).toHaveTextContent(new RegExp(`^${label} \\S+`))
    }
  })

  it('shows effective occupied time as occupied_start to occupied_end (setup 30, turnaround 45)', async () => {
    mockQueue.mockResolvedValue([
      { ...BOOKING, start_time: '2026-11-02T10:00:00', end_time: '2026-11-02T12:00:00', occupied_start: '2026-11-02T09:30:00', occupied_end: '2026-11-02T12:45:00' },
    ])
    render(<VenueBookingQueue />)
    await screen.findByRole('heading', { name: 'Regional Partner Conference' })
    const row = screen.getByText('Effective occupied time').closest('.detail-row')!
    expect(row).toHaveTextContent(/09:30.*12:45/)
  })
})

const CONFLICT = {
  booking_id: 9,
  event_id: 12,
  event_name: 'Alumni Gala',
  event_start: '2026-11-02T10:00:00Z',
  event_end: '2026-11-02T12:00:00Z',
  occupied_start: '2026-11-02T09:30:00Z',
  occupied_end: '2026-11-02T12:45:00Z',
  overlap_start: '2026-11-02T09:30:00Z',
  overlap_end: '2026-11-02T12:45:00Z',
}

describe('SCRUM-41 AC1 + AC5 - Venue Staff are warned of overlapping bookings', () => {
  it('AC1: flags the conflict in an alert on the request, with a text label', async () => {
    mockQueue.mockResolvedValue([{ ...BOOKING, conflicts: [CONFLICT] }])
    render(<VenueBookingQueue />)
    const card = within(await screen.findByRole('region', { name: /Regional Partner Conference/ }))
    expect(card.getByRole('alert')).toHaveTextContent(/^Conflict · Alumni Gala · overlap \d\d:\d\d–\d\d:\d\d$/)
  })

  it('AC5: names the conflicting event and shows its occupied period and the overlap', async () => {
    mockQueue.mockResolvedValue([{ ...BOOKING, conflicts: [CONFLICT] }])
    render(<VenueBookingQueue />)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/Conflict · Alumni Gala · overlap \d\d:\d\d–\d\d:\d\d/)
    expect(within(alert).queryByRole('listitem')).not.toBeInTheDocument()
    expect(screen.getByText('Effective occupied time')).toBeInTheDocument()
  })

  it('AC5: shows this request\'s occupied time, from start minus setup to end plus turnaround', async () => {
    const local = (h: number, m = 0) => new Date(2026, 10, 2, h, m).toISOString()
    const clock = (iso: string) =>
      new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
    // Event 09:00-17:00, 30 min setup, 45 min turnaround
    mockQueue.mockResolvedValue([
      {
        ...BOOKING,
        start_time: local(9),
        end_time: local(17),
        occupied_start: local(8, 30),
        occupied_end: local(17, 45),
        conflicts: [CONFLICT],
      },
    ])
    render(<VenueBookingQueue />)
    const card = within(await screen.findByRole('region', { name: /Regional Partner Conference/ }))
    const row = card.getByText('Effective occupied time').closest('.detail-row') as HTMLElement
    expect(row).toHaveTextContent(clock(local(8, 30)))
    expect(row).toHaveTextContent(clock(local(17, 45)))
    expect(row).not.toHaveTextContent(clock(local(9)))
    const breakdown = card.getByText('Time breakdown').closest('.detail-row') as HTMLElement
    expect(breakdown).toHaveTextContent('Setup 08:30-09:00')
    expect(breakdown).toHaveTextContent('Turnaround 17:00-17:45')
  })

  it('AC5: lists every conflict', async () => {
    mockQueue.mockResolvedValue([
      { ...BOOKING, conflicts: [CONFLICT, { ...CONFLICT, booking_id: 10, event_name: 'Careers Fair' }] },
    ])
    render(<VenueBookingQueue />)
    const alerts = await screen.findAllByRole('alert')
    expect(alerts).toHaveLength(2)
    expect(alerts[1]).toHaveTextContent('Conflict · Careers Fair · overlap')
  })

  it('AC3: no warning when the server lists no conflicts (touching bookings are not conflicts)', async () => {
    mockQueue.mockResolvedValue([{ ...BOOKING, conflicts: [] }])
    render(<VenueBookingQueue />)
    await screen.findByRole('heading', { name: 'Regional Partner Conference' })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByText(/^Conflict ·/)).not.toBeInTheDocument()
  })

  it('AC3/AC4: a booking with no conflicts field shows no warning', async () => {
    mockQueue.mockResolvedValue([BOOKING])
    render(<VenueBookingQueue />)
    await screen.findByRole('heading', { name: 'Regional Partner Conference' })
    expect(screen.queryByText(/^Conflict ·/)).not.toBeInTheDocument()
  })

  it('AC1: an approval refused for a conflict shows the message and keeps the request queued', async () => {
    mockQueue.mockResolvedValue([BOOKING])
    mockApprove.mockRejectedValue(new ApiError(409, 'Conflicts with Alumni Gala (2 Nov 2026).'))
    render(<VenueBookingQueue />)
    const card = within(await screen.findByRole('region', { name: /Regional Partner Conference/ }))
    await userEvent.click(card.getByRole('button', { name: 'Approve' }))
    expect(await card.findByText('Conflicts with Alumni Gala (2 Nov 2026).')).toBeInTheDocument()
    expect(card.getByRole('button', { name: 'Approve' })).toBeEnabled()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})

describe('SCRUM-41 AC6 - approval of an overlapping request is refused', () => {
  it('shows the refusal naming the conflicting event, keeps the request pending and queued', async () => {
    mockQueue.mockResolvedValue([BOOKING])
    mockApprove.mockRejectedValue(
      new ApiError(409, 'Marina Hall is already booked for Alumni Gala from 2 Nov 2026 15:00 to 17:00.'),
    )
    render(<VenueBookingQueue />)
    const card = within(await screen.findByRole('region', { name: /Regional Partner Conference/ }))
    await userEvent.click(card.getByRole('button', { name: 'Approve' }))
    expect(await card.findByText(/already booked for Alumni Gala/)).toBeInTheDocument()
    expect(card.getByRole('button', { name: 'Approve' })).toBeEnabled()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Regional Partner Conference' })).toBeInTheDocument()
  })

  it('does not offer approval at all while the screen already knows of the conflict, and names the event', async () => {
    mockQueue.mockResolvedValue([{ ...BOOKING, conflicts: [CONFLICT] }])
    render(<VenueBookingQueue />)
    const card = within(await screen.findByRole('region', { name: /Regional Partner Conference/ }))
    await userEvent.click(card.getByRole('button', { name: 'Approve' }))
    expect(mockApprove).not.toHaveBeenCalled()
    expect(card.getByRole('alert')).toHaveTextContent('Alumni Gala')
  })
})

describe('Approve is disabled while a blocking conflict exists', () => {
  it('disables Approve with a hint naming the event; hold and reject stay enabled', async () => {
    mockQueue.mockResolvedValue([{ ...BOOKING, conflicts: [CONFLICT] }])
    render(<VenueBookingQueue />)
    const card = within(await screen.findByRole('region', { name: /Regional Partner Conference/ }))
    const approve = card.getByRole('button', { name: 'Approve' })
    expect(approve).toBeDisabled()
    expect(approve).toHaveAttribute('title', 'Conflicts with Alumni Gala')
    expect(approve).toHaveAccessibleDescription('Conflicts with Alumni Gala')
    expect(card.getByRole('button', { name: /hold/i })).toBeEnabled()
    expect(card.getByRole('button', { name: 'Reject' })).toBeEnabled()
  })

  it('also blocks on a venue-unavailability period', async () => {
    mockQueue.mockResolvedValue([
      { ...BOOKING, conflicts: [{ ...CONFLICT, kind: 'unavailability' as const, booking_id: null, event_name: null, reason: 'Repairs' }] },
    ])
    render(<VenueBookingQueue />)
    const card = within(await screen.findByRole('region', { name: /Regional Partner Conference/ }))
    expect(card.getByRole('button', { name: 'Approve' })).toBeDisabled()
  })
})

describe('SCRUM-93 AC3 - unavailability conflict in the queue', () => {
  const CLOSURE = { ...CONFLICT, kind: 'unavailability' as const, booking_id: null, event_name: null, reason: 'Maintenance: pipe repair' }

  it('shows the banner, disables Approve with the hint, and plots the closure in Calendar view', async () => {
    mockQueue.mockResolvedValue([{ ...BOOKING, conflicts: [CLOSURE] }])
    render(<VenueBookingQueue />)
    const card = within(await screen.findByRole('region', { name: /Regional Partner Conference/ }))
    expect(card.getByRole('alert')).toHaveTextContent(/^Venue unavailable · Maintenance: pipe repair · overlap \d\d:\d\d–\d\d:\d\d$/)
    const approve = card.getByRole('button', { name: 'Approve' })
    expect(approve).toBeDisabled()
    expect(approve).toHaveAttribute('title', 'Venue unavailable: Maintenance: pipe repair')
    const block = screen.getByRole('button', { name: /^Maintenance: pipe repair, occupied/ })
    expect(block).toHaveClass('k-unavailable')
    await userEvent.click(block)
    expect(screen.getByRole('region', { name: 'Venue unavailable · Maintenance: pipe repair' })).toBeInTheDocument()
  })
})

describe('Venue links to its page', () => {
  it('links the venue on each request to /venues/:id', async () => {
    mockQueue.mockResolvedValue([BOOKING])
    render(<VenueBookingQueue />)
    const card = within(await screen.findByRole('region', { name: /Regional Partner Conference/ }))
    expect(card.getByRole('link', { name: new RegExp(BOOKING.venue.name) })).toHaveAttribute(
      'href',
      `/venues/${BOOKING.venue.id}`,
    )
  })
})

describe('SCRUM-41 - calendar-centred review', () => {
  it('opens in the calendar view with the first request selected', async () => {
    mockQueue.mockResolvedValue([BOOKING, OTHER])
    render(<VenueBookingQueue />)
    expect(await screen.findByRole('button', { name: 'Calendar' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('region', { name: /Regional Partner Conference/ })).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: /Staff Town Hall/ })).not.toBeInTheDocument()
  })

  it('selecting a sidebar row shows that request\'s details', async () => {
    mockQueue.mockResolvedValue([BOOKING, OTHER])
    render(<VenueBookingQueue />)
    const sidebar = within(await screen.findByRole('complementary', { name: 'Requests' }))
    await userEvent.click(sidebar.getByRole('button', { name: /Staff Town Hall/ }))
    expect(screen.getByRole('region', { name: /Staff Town Hall/ })).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: /Regional Partner Conference/ })).not.toBeInTheDocument()
  })

  it('badges requests that have conflicts with a text label', async () => {
    mockQueue.mockResolvedValue([{ ...BOOKING, conflicts: [CONFLICT] }, OTHER])
    render(<VenueBookingQueue />)
    const sidebar = within(await screen.findByRole('complementary', { name: 'Requests' }))
    expect(sidebar.getAllByText('Conflict')).toHaveLength(1)
    expect(within(sidebar.getByRole('button', { name: /Regional Partner/ })).getByText('Conflict')).toBeInTheDocument()
  })

  it('toggles to the list view and back', async () => {
    mockQueue.mockResolvedValue([BOOKING, OTHER])
    render(<VenueBookingQueue />)
    await userEvent.click(await screen.findByRole('button', { name: 'List' }))
    expect(screen.getByRole('region', { name: /Staff Town Hall/ })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Requests for Marina Hall' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Calendar' }))
    expect(screen.queryByRole('region', { name: /Staff Town Hall/ })).not.toBeInTheDocument()
  })

  it('clicking another booking shows a read-only summary, and its conflict button opens the request', async () => {
    mockQueue.mockResolvedValue([{ ...BOOKING, conflicts: [CONFLICT] }, OTHER])
    render(<VenueBookingQueue />)
    await userEvent.click(await screen.findByRole('button', { name: /^Alumni Gala · Approved/ }))
    const summary = screen.getByRole('region', { name: 'Alumni Gala · Approved' })
    expect(within(summary).getByText('Occupied')).toBeInTheDocument()
    expect(within(summary).getByText('Event time')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Alumni Gala · Approved/ })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(within(summary).getByRole('button', { name: 'Regional Partner Conference' }))
    expect(screen.getByRole('region', { name: /Booking request for Regional Partner/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument()
  })
})

describe('Approved and Flagged sidebar sections', () => {
  const APPROVED: VenueBooking = { ...BOOKING, id: 20, status: 'approved', event: { id: 8, name: 'Gala Dinner' } }
  const FLAGGED: VenueBooking = {
    ...BOOKING,
    id: 30,
    status: 'approved',
    event: { id: 9, name: 'Board Retreat' },
    conflicts: [
      {
        booking_id: 99,
        kind: 'booking',
        event_name: 'Other Event',
        status: 'approved',
        occupied_start: '2026-11-02T08:00:00Z',
        occupied_end: '2026-11-02T12:00:00Z',
        event_start: '2026-11-02T08:00:00Z',
        event_end: '2026-11-02T12:00:00Z',
        overlap_start: '2026-11-02T08:30:00Z',
        overlap_end: '2026-11-02T12:00:00Z',
      } as never,
    ],
  }

  const row = (name: RegExp) => within(screen.getByLabelText('Requests')).getByRole('button', { name })

  async function open() {
    mockQueue.mockResolvedValue([BOOKING])
    mockApproved.mockResolvedValue([APPROVED])
    mockFlagged.mockResolvedValue([FLAGGED])
    render(<VenueBookingQueue />)
    await screen.findAllByText('Gala Dinner')
  }

  it('renders the three sections with counts, Approved collapsed', async () => {
    await open()
    const summaries = document.querySelectorAll('summary')
    expect([...summaries].map((x) => x.textContent)).toEqual(['Pending1', 'Approved1', 'Flagged1'])
    const [pending, approved, flagged] = [...document.querySelectorAll('details')]
    expect(pending.open).toBe(true)
    expect(approved.open).toBe(false)
    expect(flagged.open).toBe(false)
    expect(summaries[2].querySelector('.bq-bubble-danger')).toHaveTextContent('1')
  })

  it('opens Flagged by default for ?view=flagged', async () => {
    mockQueue.mockResolvedValue([BOOKING])
    mockFlagged.mockResolvedValue([FLAGGED])
    rtlRender(
      <MemoryRouter initialEntries={['/?view=flagged']}>
        <VenueBookingQueue />
      </MemoryRouter>,
    )
    await screen.findAllByText('Board Retreat')
    expect(document.querySelectorAll('details')[2].open).toBe(true)
  })

  it('selecting an approved row shows read-only details without decisions', async () => {
    await open()
    await userEvent.click(row(/Gala Dinner/))
    const panel = screen.getByRole('region', { name: 'Approved booking for Gala Dinner' })
    expect(within(panel).getByText('Time breakdown')).toBeInTheDocument()
    expect(within(panel).getByText('Sam Tan (sam@connectsphere.test)')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reject' })).not.toBeInTheDocument()
    expect(within(panel).queryByRole('button')).not.toBeInTheDocument()
  })

  it('keeps a flagged booking with a reason, removing it from the list', async () => {
    await open()
    mockKeep.mockResolvedValue({ ...FLAGGED, conflicts: [] })
    await userEvent.click(row(/Board Retreat/))
    const panel = screen.getByRole('region', { name: 'Flagged booking for Board Retreat' })
    expect(within(panel).getByText(/Conflict · Other Event · overlap/)).toBeInTheDocument()
    await userEvent.click(within(panel).getByRole('button', { name: 'Keep anyway' }))
    expect(within(panel).getByText(/Enter a reason for keeping/)).toBeInTheDocument()
    await userEvent.type(within(panel).getByRole('textbox'), 'Fine')
    await userEvent.click(within(panel).getByRole('button', { name: 'Keep anyway' }))
    expect(mockKeep).toHaveBeenCalledWith(30, 'Fine')
    expect(await screen.findByText(/Kept Marina Hall for Board Retreat/)).toBeInTheDocument()
    expect(document.querySelectorAll('summary')[2].textContent).toBe('Flagged0')
  })

  it('cancels a flagged booking with a reason', async () => {
    await open()
    mockCancel.mockResolvedValue(FLAGGED)
    await userEvent.click(row(/Board Retreat/))
    await userEvent.type(screen.getByRole('textbox'), 'Clash')
    await userEvent.click(screen.getByRole('button', { name: 'Cancel booking' }))
    expect(mockCancel).toHaveBeenCalledWith(30, 'Clash')
    expect(await screen.findByText(/Cancelled Marina Hall for Board Retreat/)).toBeInTheDocument()
  })

  it('shows an inline error in the Approved section only when it fails to load', async () => {
    mockQueue.mockResolvedValue([BOOKING])
    mockApproved.mockRejectedValue(new ApiError(500, 'approved boom'))
    render(<VenueBookingQueue />)
    expect(await screen.findByText('approved boom')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Regional Partner Conference' })).toBeInTheDocument()
  })
})

describe('Tentative hold with an expiry and a required action', () => {
  const ACTION = 'Confirm final headcount and pay the deposit'
  const HELD: VenueBooking = {
    ...BOOKING,
    status: 'tentative_hold',
    expires_at: '2030-01-02T02:00:00Z',
    hold_action: ACTION,
  }

  async function openHoldForm() {
    mockQueue.mockResolvedValue([BOOKING])
    render(<VenueBookingQueue />)
    await userEvent.click(await screen.findByRole('button', { name: 'Place tentative hold' }))
    return {
      expiry: screen.getByLabelText('Hold expires'),
      action: screen.getByLabelText('Required action'),
      confirm: screen.getByRole('button', { name: 'Confirm hold' }),
    }
  }

  it('AC1: asks for an expiry (prefilled) and the required action, and sends both', async () => {
    mockHold.mockResolvedValue(HELD)
    const { expiry, action, confirm } = await openHoldForm()
    expect((expiry as HTMLInputElement).value).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/)
    expect(expiry).toBeRequired()
    expect(action).toBeRequired()

    fireEvent.change(expiry, { target: { value: '2030-01-02T10:00' } })
    await userEvent.type(action, `  ${ACTION} `)
    await userEvent.click(confirm)

    expect(mockHold).toHaveBeenCalledWith(BOOKING.id, {
      expires_at: new Date('2030-01-02T10:00').toISOString(),
      required_action: ACTION,
    })
    const status = await screen.findByRole('status')
    expect(status).toHaveTextContent('Tentative hold placed for Marina Hall')
    expect(status).toHaveTextContent(`Required action: ${ACTION}`)
  })

  it('AC2: a missing expiry is not saved and the field is flagged and focused', async () => {
    const { expiry, action, confirm } = await openHoldForm()
    fireEvent.change(expiry, { target: { value: '' } })
    await userEvent.type(action, ACTION)
    await userEvent.click(confirm)

    expect(mockHold).not.toHaveBeenCalled()
    expect(expiry).toHaveAttribute('aria-invalid', 'true')
    expect(expiry).toHaveAccessibleDescription('Enter the date and time the hold expires.')
    expect(expiry).toHaveFocus()
    expect(action).toHaveAttribute('aria-invalid', 'false')
  })

  it('AC2: a past expiry is not saved and the field is flagged', async () => {
    const { expiry, action, confirm } = await openHoldForm()
    fireEvent.change(expiry, { target: { value: '2020-01-01T10:00' } })
    await userEvent.type(action, ACTION)
    await userEvent.click(confirm)

    expect(mockHold).not.toHaveBeenCalled()
    expect(expiry).toHaveAttribute('aria-invalid', 'true')
    expect(expiry).toHaveAccessibleDescription('The expiry must be in the future.')
  })

  it('AC1 negative: a blank required action is not saved and that field is flagged', async () => {
    const { expiry, action, confirm } = await openHoldForm()
    await userEvent.type(action, '   ')
    await userEvent.click(confirm)

    expect(mockHold).not.toHaveBeenCalled()
    expect(expiry).toHaveAttribute('aria-invalid', 'false')
    expect(action).toHaveAttribute('aria-invalid', 'true')
    expect(action).toHaveFocus()
  })

  it('AC2: a server 422 naming expires_at flags the expiry field', async () => {
    mockHold.mockRejectedValue(
      new ApiError(422, 'expires_at: A tentative hold expiry must be in the future.', ['expires_at']),
    )
    const { expiry, action, confirm } = await openHoldForm()
    await userEvent.type(action, ACTION)
    await userEvent.click(confirm)

    expect(await screen.findByText('The expiry must be in the future.')).toBeInTheDocument()
    expect(expiry).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByRole('heading', { name: 'Regional Partner Conference' })).toBeInTheDocument()
  })

  it('Cancel closes the form without placing a hold', async () => {
    await openHoldForm()
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(mockHold).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Place tentative hold' })).toBeEnabled()
  })

  it('AC4: a held request in the queue shows its expiry and required action', async () => {
    mockQueue.mockResolvedValue([HELD])
    render(<VenueBookingQueue />)
    const card = within(await screen.findByRole('region', { name: /Regional Partner Conference/ }))
    expect(card.getByText('Hold expires')).toBeInTheDocument()
    expect(card.getByText(ACTION)).toBeInTheDocument()
    expect(card.getByRole('button', { name: 'Place tentative hold' })).toBeDisabled()
    expect(card.getByRole('button', { name: 'Approve' })).toBeEnabled()
  })
})
