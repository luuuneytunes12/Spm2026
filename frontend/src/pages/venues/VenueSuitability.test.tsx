import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { VenueSuitability } from './VenueSuitability'

vi.mock('../../lib/events', () => ({
  listAssignedEvents: vi.fn(),
}))
vi.mock('../../lib/venues', () => ({
  checkVenueSuitability: vi.fn(),
}))

import { listAssignedEvents } from '../../lib/events'
import { checkVenueSuitability } from '../../lib/venues'
import type { EventSummary } from '../../lib/events'
import type { VenueSuitability as SuitabilityResult } from '../../lib/venues'

const mockListAssignedEvents = vi.mocked(listAssignedEvents)
const mockCheck = vi.mocked(checkVenueSuitability)

const EVENT: EventSummary = {
  id: 18,
  name: 'Access Workshop',
  event_type: 'Workshop',
  proposed_start: '2026-11-02T09:00:00Z',
  proposed_end: '2026-11-02T12:00:00Z',
  expected_attendance: 80,
  status: 'planning_event',
  submitted_at: null,
  updated_at: '2026-10-01T09:00:00Z',
}

const SUITABLE: SuitabilityResult = {
  venue_id: 4,
  event_id: 18,
  event_name: 'Access Workshop',
  suitable: true,
  checks: [
    {
      category: 'capacity',
      requirement: '80 people',
      available: '100 people',
      met: true,
      message: 'Capacity is sufficient.',
    },
  ],
}

function renderSuitability() {
  render(<VenueSuitability venueId={4} />)
}

beforeEach(() => {
  vi.clearAllMocks()
  mockListAssignedEvents.mockResolvedValue([EVENT])
})

describe('Check Venue Suitability for an Event', () => {
  it('AC1-AC3: checks the selected event and displays detailed mismatches', async () => {
    mockCheck.mockResolvedValue({
      ...SUITABLE,
      suitable: false,
      checks: [
        {
          category: 'capacity',
          requirement: '80 people',
          available: '40 people',
          met: false,
          message: 'Insufficient capacity: 40 available; 80 required.',
        },
        {
          category: 'layout',
          requirement: 'Theatre',
          available: 'Boardroom',
          met: false,
          message: "Unsupported layout: 'Theatre' is not offered by this venue.",
        },
      ],
    })
    renderSuitability()

    fireEvent.change(await screen.findByRole('combobox', { name: 'Event' }), {
      target: { value: '18' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Check suitability' }))

    expect(await screen.findByRole('heading', { name: 'Not suitable for Access Workshop' }))
      .toBeInTheDocument()
    expect(screen.getByText(/Insufficient capacity/)).toBeInTheDocument()
    expect(screen.getByText(/Unsupported layout/)).toBeInTheDocument()
    expect(mockCheck).toHaveBeenCalledWith(4, 18)
  })

  it('keeps the workflow active and offers retry after a check request fails', async () => {
    mockCheck.mockRejectedValueOnce(new Error('temporary network issue')).mockResolvedValueOnce(SUITABLE)
    renderSuitability()
    fireEvent.change(await screen.findByRole('combobox', { name: 'Event' }), {
      target: { value: '18' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Check suitability' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not check suitability')

    fireEvent.click(screen.getByRole('button', { name: 'Retry check' }))
    expect(await screen.findByRole('heading', { name: 'Suitable for Access Workshop' }))
      .toBeInTheDocument()
    expect(mockCheck).toHaveBeenCalledTimes(2)
  })

  it('allows retry when the assigned-event workflow cannot load its events', async () => {
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
