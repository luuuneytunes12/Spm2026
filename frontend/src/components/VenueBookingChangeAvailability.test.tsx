/**
 * SCRUM-96 AC2 -- warning the Coordinator, in the change form, about venues
 * that are not free at the event's time.
 *
 * Saving a change does not refuse an unavailable venue: Venue Staff are the
 * authority and decide when they review the booking, as they do for a new
 * request. But the Coordinator should not have to find out afterwards, so the
 * venue list says which venues are booked or closed at the event's time. A
 * tagged venue can still be chosen.
 *
 * The tag comes from the existing venue search with the event's window: it
 * returns only the venues that are free for it. The server's own rules --
 * who is booked, closed, held -- are not repeated here. The libs are mocked.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/api'
import { VenueBookingSection } from './VenueBookingSection'

vi.mock('../lib/venueBookings', async () => {
  const actual = await vi.importActual<typeof import('../lib/venueBookings')>('../lib/venueBookings')
  return {
    ...actual,
    submitVenueBookings: vi.fn(),
    listEventVenueBookings: vi.fn(),
    changeVenueBooking: vi.fn(),
  }
})
vi.mock('../lib/venues', () => ({ listVenues: vi.fn() }))

import { changeVenueBooking, listEventVenueBookings } from '../lib/venueBookings'
import type { VenueBooking } from '../lib/venueBookings'
import { listVenues } from '../lib/venues'
import type { VenueSearch, VenueSummary } from '../lib/venues'

const mockList = vi.mocked(listEventVenueBookings)
const mockChange = vi.mocked(changeVenueBooking)
const mockVenues = vi.mocked(listVenues)

const START = '2026-11-02T09:00:00Z'
const END = '2026-11-02T17:00:00Z'

const BOOKING: VenueBooking = {
  id: 1,
  status: 'approved',
  created_at: '2026-10-01T02:00:00Z',
  event: { id: 7, name: 'Conference' },
  venue: { id: 3, name: 'Marina Hall', location: '10 Bayfront Ave', capacity: 250 },
  start_time: START,
  end_time: END,
  setup_minutes: 0,
  turnaround_minutes: 0,
  occupied_start: START,
  occupied_end: END,
  expires_at: null,
  expected_attendance: 120,
  room_layout_preference: null,
  accessibility_needs: null,
  facilities_needs: null,
  venue_requirements: null,
  requested_by: { name: 'Sam Tan', email: 'sam@connectsphere.test' },
  decision_notes: null,
  suggested_alternative: null,
  reviewed_by: { name: 'Vera Staff', email: 'vera@connectsphere.test' },
  reviewed_at: '2026-10-02T02:00:00Z',
}

const venue = (id: number, name: string, location: string, capacity: number): VenueSummary => ({
  id, name, location, capacity, facilities: [], is_active: true,
})
const MARINA = venue(3, 'Marina Hall', '10 Bayfront Ave', 250)
const GARDEN = venue(5, 'Garden Hall', 'Level 2', 100)
const SPARE = venue(7, 'Spare Hall', 'Wing C', 300)
const ALL = [MARINA, GARDEN, SPARE]

// What the search says is free for the event's time: Garden Hall is booked or
// closed then, and Marina Hall (this booking's own venue) holds itself.
const FREE = [SPARE]

const TAG = 'not free at this time'
const GARDEN_OPTION = 'Garden Hall — Level 2 (capacity 100)'
const SPARE_OPTION = 'Spare Hall — Wing C (capacity 300)'

function searchAnswers(free: VenueSummary[]) {
  mockVenues.mockImplementation((search?: VenueSearch) =>
    Promise.resolve(search?.start ? free : ALL),
  )
}

async function openChange() {
  const user = userEvent.setup()
  await screen.findByText('Marina Hall', { selector: 'strong' })
  await user.click(screen.getByRole('button', { name: 'Change Marina Hall booking' }))
  return { user, panel: within(await screen.findByRole('region', { name: 'Change Marina Hall booking' })) }
}

const optionTexts = (panel: { getByLabelText: (text: string) => HTMLElement }) =>
  Array.from(panel.getByLabelText('Venue').querySelectorAll('option')).map((o) => o.textContent ?? '')

beforeEach(() => {
  vi.resetAllMocks()
  mockList.mockResolvedValue([BOOKING])
  searchAnswers(FREE)
})

describe('asking which venues are free', () => {
  it('asks the existing search about the event’s own window', async () => {
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    await openChange()

    await waitFor(() => expect(mockVenues).toHaveBeenCalledWith({ start: START, end: END }))
  })

  it('asks when the form is opened, not before', async () => {
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    await screen.findByText('Marina Hall', { selector: 'strong' })

    expect(mockVenues).not.toHaveBeenCalledWith({ start: START, end: END })
  })
})

describe('tagging the venues that are not free', () => {
  it('tags a venue the search says is not free at the event’s time', async () => {
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    const { panel } = await openChange()

    await waitFor(() => expect(optionTexts(panel)).toContain(`${GARDEN_OPTION} — ${TAG}`))
  })

  it('does not tag a venue that is free', async () => {
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    const { panel } = await openChange()

    await waitFor(() => expect(optionTexts(panel).some((o) => o.includes(TAG))).toBe(true))
    expect(optionTexts(panel)).toContain(SPARE_OPTION)
  })

  it('does not tag the booking’s own venue', async () => {
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    const { panel } = await openChange()

    await waitFor(() => expect(optionTexts(panel).some((o) => o.includes(TAG))).toBe(true))
    expect(optionTexts(panel).find((o) => o.startsWith('Marina Hall'))).not.toContain(TAG)
  })

  it('still lists the tagged venue: it is a warning, not a filter', async () => {
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    const { panel } = await openChange()

    await waitFor(() => expect(optionTexts(panel).some((o) => o.includes(TAG))).toBe(true))
    expect(optionTexts(panel).some((o) => o.startsWith('Garden Hall'))).toBe(true)
  })
})

describe('choosing a venue that is not free', () => {
  async function chooseGarden() {
    const { user, panel } = await openChange()
    await waitFor(() => expect(optionTexts(panel).some((o) => o.includes(TAG))).toBe(true))
    await user.selectOptions(panel.getByLabelText('Venue'), `${GARDEN_OPTION} — ${TAG}`)
    return { user, panel }
  }

  it('says so, and that Venue Staff will decide', async () => {
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    const { panel } = await chooseGarden()

    const warning = panel.getByRole('note')
    expect(warning).toHaveTextContent(/looks unavailable at the event.s time/i)
    expect(warning).toHaveTextContent(/venue staff will decide/i)
  })

  it('can still be saved: the Coordinator may ask for it', async () => {
    mockChange.mockResolvedValue({ ...BOOKING, status: 'pending', venue: { ...GARDEN } })
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    const { user, panel } = await chooseGarden()

    await user.click(panel.getByRole('button', { name: 'Save change' }))

    await waitFor(() => expect(mockChange).toHaveBeenCalledWith(1, { venue_id: 5 }))
  })

  it('shows no warning for a venue that is free', async () => {
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    const { user, panel } = await openChange()
    await waitFor(() => expect(optionTexts(panel).some((o) => o.includes(TAG))).toBe(true))

    await user.selectOptions(panel.getByLabelText('Venue'), SPARE_OPTION)

    expect(panel.queryByRole('note')).not.toBeInTheDocument()
  })

  it('shows no warning before anything is chosen', async () => {
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    const { panel } = await openChange()
    await waitFor(() => expect(optionTexts(panel).some((o) => o.includes(TAG))).toBe(true))

    expect(panel.queryByRole('note')).not.toBeInTheDocument()
  })

  it('drops the warning when the Coordinator goes back to a free venue', async () => {
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    const { user, panel } = await chooseGarden()

    await user.selectOptions(panel.getByLabelText('Venue'), SPARE_OPTION)

    expect(panel.queryByRole('note')).not.toBeInTheDocument()
  })
})

describe('when availability cannot be checked', () => {
  it('tags nothing, still offers every venue, and says it could not check', async () => {
    mockVenues.mockImplementation((search?: VenueSearch) =>
      search?.start ? Promise.reject(new ApiError(500, 'down')) : Promise.resolve(ALL),
    )
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    const { panel } = await openChange()

    expect(await panel.findByText(/availability could not be checked/i)).toBeInTheDocument()
    expect(optionTexts(panel).some((o) => o.includes(TAG))).toBe(false)
    expect(optionTexts(panel)).toContain(SPARE_OPTION)
  })

  it('does not stop the change being saved', async () => {
    mockChange.mockResolvedValue({ ...BOOKING, status: 'pending', venue: { ...SPARE } })
    mockVenues.mockImplementation((search?: VenueSearch) =>
      search?.start ? Promise.reject(new Error('network down')) : Promise.resolve(ALL),
    )
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    const { user, panel } = await openChange()
    await panel.findByText(/availability could not be checked/i)

    await user.selectOptions(panel.getByLabelText('Venue'), SPARE_OPTION)
    await user.click(panel.getByRole('button', { name: 'Save change' }))

    await waitFor(() => expect(mockChange).toHaveBeenCalledWith(1, { venue_id: 7 }))
  })
})
