import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { VenueSuitability } from './VenueSuitability'

vi.mock('../../lib/events', () => ({
  listAssignedEvents: vi.fn(),
}))
vi.mock('../../lib/venues', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../lib/venues')>()),
  checkVenueSuitability: vi.fn(),
}))

import { listAssignedEvents } from '../../lib/events'
import { checkVenueSuitability } from '../../lib/venues'
import type { EventSummary } from '../../lib/events'
import type { VenueSuitability as VenueSuitabilityResult } from '../../lib/venues'

const mockListAssignedEvents = vi.mocked(listAssignedEvents)
const mockCheck = vi.mocked(checkVenueSuitability)

const EVENT: EventSummary = {
  id: 18,
  name: 'Hottie Stuff testing 2',
  event_type: 'Workshop',
  proposed_start: '2026-11-02T09:00:00Z',
  proposed_end: '2026-11-02T12:00:00Z',
  expected_attendance: 120,
  status: 'planning_event',
  submitted_at: null,
  updated_at: '2026-10-01T09:00:00Z',
}

const SUITABLE: VenueSuitabilityResult = {
  venue_id: 4,
  event_id: 18,
  event_name: 'Hottie Stuff testing 2',
  suitable: true,
  checks: [
    {
      category: 'capacity',
      requirement: '120 people',
      available: '250 people',
      met: true,
      message: 'Capacity is sufficient.',
    },
  ],
}

function renderSuitability() {
  render(<VenueSuitability venueId={4} venueName="Harbour Room" />)
}

beforeEach(() => {
  vi.clearAllMocks()
  mockListAssignedEvents.mockResolvedValue([EVENT])
})

describe('Check Venue Suitability for an Event', () => {
  async function checkWith(check: VenueSuitabilityResult['checks'][number]) {
    mockCheck.mockResolvedValue({ ...SUITABLE, suitable: check.met, checks: [check] })
    renderSuitability()
    fireEvent.change(await screen.findByRole('combobox', { name: 'Event' }), {
      target: { value: '18' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Check suitability' }))
  }

  it('AC1: shows operating hours as met when the event is inside them', async () => {
    await checkWith({
      category: 'operating_hours',
      requirement: 'Mon 02 Nov 2026 10:00 to Mon 02 Nov 2026 12:00',
      available: 'Mon-Fri 09:00-17:00',
      met: true,
      message: 'Within operating hours.',
    })

    expect(await screen.findByRole('heading', { name: 'Suitable for Hottie Stuff testing 2' }))
      .toBeInTheDocument()
    expect(screen.getByText('operating hours: Pass')).toBeInTheDocument()
  })

  it('AC2: shows Not suitable and "Outside operating hours" with what to do next', async () => {
    await checkWith({
      category: 'operating_hours',
      requirement: 'Mon 02 Nov 2026 18:00 to Mon 02 Nov 2026 20:00',
      available: 'Mon-Fri 09:00-17:00',
      met: false,
      message: 'Outside operating hours',
    })

    expect(await screen.findByRole('heading', { name: 'Not suitable for Hottie Stuff testing 2' }))
      .toBeInTheDocument()
    expect(screen.getByText('Outside operating hours')).toBeInTheDocument()
    expect(screen.getByText(/Choose a venue that is open for the whole event/)).toBeInTheDocument()
  })

  it('tells the Coordinator who can fix operating hours that cannot be read', async () => {
    await checkWith({
      category: 'operating_hours',
      requirement: 'Mon 02 Nov 2026 10:00 to Mon 02 Nov 2026 12:00',
      available: 'By appointment',
      met: false,
      message: "Cannot read this venue's operating hours, so they cannot be confirmed.",
    })

    expect(await screen.findByText(/Ask Venue Staff to record the hours/)).toBeInTheDocument()
  })

  it('checks this venue directly even when the event has no venue booking', async () => {
    mockCheck.mockResolvedValue(SUITABLE)
    renderSuitability()

    fireEvent.change(await screen.findByRole('combobox', { name: 'Event' }), {
      target: { value: '18' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Check suitability' }))

    expect(await screen.findByRole('heading', { name: 'Suitable for Hottie Stuff testing 2' }))
      .toBeInTheDocument()
    expect(screen.getByText('Capacity is sufficient.')).toBeInTheDocument()
    expect(screen.getByText(/Required: 120 people; available: 250 people/)).toBeInTheDocument()
    expect(screen.getByText(/You can proceed to check availability/)).toBeInTheDocument()
    expect(screen.queryByText(/No active venue bookings are attached/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Combined capacity:/)).not.toBeInTheDocument()
    expect(mockCheck).toHaveBeenCalledWith(4, 18)
  })

  it('explains each failed check and gives an action to resolve it', async () => {
    mockCheck.mockResolvedValue({
      ...SUITABLE,
      suitable: false,
      checks: [
        SUITABLE.checks[0],
        {
          category: 'layout',
          requirement: 'Theatre',
          available: 'Boardroom',
          met: false,
          message: "Unsupported layout: 'Theatre' is not offered by this venue.",
        },
        {
          category: 'accessibility',
          requirement: 'Hearing loop',
          available: 'None recorded',
          met: false,
          message: "Missing accessibility feature: 'Hearing loop'.",
        },
        {
          category: 'facility',
          requirement: 'Stage',
          available: 'Projector',
          met: false,
          message: "Missing facility: 'Stage'.",
        },
      ],
    })
    renderSuitability()

    fireEvent.change(await screen.findByRole('combobox', { name: 'Event' }), {
      target: { value: '18' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Check suitability' }))

    expect(await screen.findByRole('heading', { name: 'Not suitable for Hottie Stuff testing 2' }))
      .toBeInTheDocument()
    expect(screen.getByText(/Required: Theatre; available: Boardroom/)).toBeInTheDocument()
    expect(screen.getByText(/Choose a layout this venue supports/)).toBeInTheDocument()
    expect(screen.getByText(/Choose a venue that provides this feature/)).toBeInTheDocument()
    expect(screen.getByText(/Choose a venue with this facility/)).toBeInTheDocument()
    expect(screen.getByText(/3 of 4 recorded checks need attention/)).toBeInTheDocument()
  })

  it('explains how to fix missing attendance', async () => {
    mockCheck.mockResolvedValue({
      ...SUITABLE,
      suitable: false,
      checks: [{
        category: 'capacity',
        requirement: 'Expected attendance is not recorded',
        available: '250 people',
        met: false,
        message: 'Cannot confirm capacity until the event attendance is recorded.',
      }],
    })
    renderSuitability()

    fireEvent.change(await screen.findByRole('combobox', { name: 'Event' }), {
      target: { value: '18' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Check suitability' }))

    expect(await screen.findByText(/Edit the event and enter its expected attendance/))
      .toBeInTheDocument()
  })

  it('offers retry after a suitability request fails', async () => {
    mockCheck.mockRejectedValueOnce(new Error('temporary network issue')).mockResolvedValueOnce(SUITABLE)
    renderSuitability()
    fireEvent.change(await screen.findByRole('combobox', { name: 'Event' }), {
      target: { value: '18' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Check suitability' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not check suitability')

    fireEvent.click(screen.getByRole('button', { name: 'Retry check' }))
    expect(await screen.findByRole('heading', { name: 'Suitable for Hottie Stuff testing 2' }))
      .toBeInTheDocument()
    expect(mockCheck).toHaveBeenCalledTimes(2)
  })

  it('explains a backend connection failure and logs venue and event context', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    mockCheck.mockRejectedValue(new TypeError('Failed to fetch'))
    renderSuitability()
    fireEvent.change(await screen.findByRole('combobox', { name: 'Event' }), {
      target: { value: '18' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Check suitability' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not reach the backend to check venue suitability.',
    )
    expect(consoleError).toHaveBeenCalledWith(
      'Failed to check venue suitability.',
      expect.objectContaining({ venueId: 4, eventId: 18 }),
    )
    consoleError.mockRestore()
  })

  it('allows retry when assigned events cannot be loaded', async () => {
    mockListAssignedEvents
      .mockRejectedValueOnce(new Error('temporary network issue'))
      .mockResolvedValueOnce([EVENT])
    renderSuitability()
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load your assigned events')

    fireEvent.click(screen.getByRole('button', { name: 'Retry loading events' }))
    expect(await screen.findByRole('combobox', { name: 'Event' })).toBeInTheDocument()
    expect(mockListAssignedEvents).toHaveBeenCalledTimes(2)
  })
})
