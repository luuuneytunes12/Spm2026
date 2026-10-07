import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { VenueSuitability } from './VenueSuitability'

vi.mock('../../lib/events', () => ({
  listAssignedEvents: vi.fn(),
}))
vi.mock('../../lib/venues', () => ({
  checkEventVenueSuitability: vi.fn(),
}))

import { listAssignedEvents } from '../../lib/events'
import { checkEventVenueSuitability } from '../../lib/venues'
import type { EventSummary } from '../../lib/events'
import type { EventVenueSuitability } from '../../lib/venues'

const mockListAssignedEvents = vi.mocked(listAssignedEvents)
const mockCheck = vi.mocked(checkEventVenueSuitability)

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

const SUITABLE: EventVenueSuitability = {
  event_id: 18,
  event_name: 'Access Workshop',
  suitable: true,
  venues: [{
    booking_id: 23,
    venue_id: 4,
    venue_name: 'Harbour Room',
    suitable: true,
    checks: [{
      category: 'capacity',
      requirement: '80 people',
      available: '100 people',
      met: true,
      message: 'Capacity is sufficient.',
    }],
  }],
  combined_capacity: {
    required_capacity: 80,
    available_capacity: 100,
    met: true,
    message: 'Combined venue capacity is sufficient.',
  },
}

function renderSuitability() {
  render(<VenueSuitability venueId={4} />)
}

beforeEach(() => {
  vi.clearAllMocks()
  mockListAssignedEvents.mockResolvedValue([EVENT])
})

it('shows each venue result and the independent combined capacity result', async () => {
  mockCheck.mockResolvedValue({
    ...SUITABLE,
    suitable: false,
    venues: [
      SUITABLE.venues[0],
      {
        ...SUITABLE.venues[0],
        booking_id: 24,
        venue_id: 5,
        venue_name: 'Studio B',
        suitable: false,
        checks: [{
          category: 'layout',
          requirement: 'Theatre',
          available: 'Boardroom',
          met: false,
          message: 'Unsupported layout.',
        }],
      },
    ],
    combined_capacity: {
      required_capacity: 80,
      available_capacity: 150,
      met: true,
      message: 'Combined venue capacity is sufficient.',
    },
  })
  renderSuitability()
  fireEvent.change(await screen.findByRole('combobox', { name: 'Event' }), {
    target: { value: '18' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Check suitability' }))

  expect(await screen.findByRole('heading', { name: 'Harbour Room: Suitable' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Studio B: Not suitable' })).toBeInTheDocument()
  expect(screen.getByText(/Combined capacity: 150 \/ 80 required/)).toBeInTheDocument()
  expect(screen.getByText(/Meets requirement/)).toBeInTheDocument()
})

describe('Check Venue Suitability for an Event', () => {
  it('AC1-AC3: checks the selected event and displays detailed mismatches', async () => {
    mockCheck.mockResolvedValue({
      ...SUITABLE,
      suitable: false,
      venues: [{
        ...SUITABLE.venues[0],
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
      }],
      combined_capacity: {
        ...SUITABLE.combined_capacity,
        available_capacity: 40,
        met: false,
      },
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
    expect(mockCheck).toHaveBeenCalledWith(18)
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
