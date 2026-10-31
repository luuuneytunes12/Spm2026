/**
 * Component tests for the Attendee's event catalogue. Which events are listed
 * is the server's decision: backend/tests/test_scrum68_event_catalogue.py.
 *
 * Traceability (SCRUM-68):
 *   AC1  each listed event shows its name, date and time
 *   AC3  selecting an event opens its attendee-facing details
 *   AC4  no internal planning information appears
 *   AC5  with nothing open, a clear message is shown
 *   AC6  the current confirmed values are shown
 *
 * The it.todo lines are acceptance criteria the page does not meet yet.
 */
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/api'
import { formatRange } from '../../lib/events'
import type { RegistrableEvent } from '../../lib/registrations'

vi.mock('../../lib/registrations', () => ({
  listRegistrableEvents: vi.fn(),
  registerForEvent: vi.fn(),
  withdrawFromEvent: vi.fn(),
}))

import { listRegistrableEvents } from '../../lib/registrations'
import { AttendeeEvents } from './AttendeeEvents'

const SUMMIT: RegistrableEvent = {
  id: 3,
  name: 'Partner Summit',
  proposed_start: '2026-11-02T09:00:00Z',
  proposed_end: '2026-11-02T17:00:00Z',
  registration_open: true,
  my_status: null,
}

const open = () =>
  render(
    <MemoryRouter>
      <AttendeeEvents />
    </MemoryRouter>,
  )

beforeEach(() => vi.clearAllMocks())

describe('SCRUM-68: event catalogue', () => {
  it('AC1: shows each event with its name, date and time', async () => {
    vi.mocked(listRegistrableEvents).mockResolvedValue([SUMMIT, { ...SUMMIT, id: 4, name: 'Trade Fair' }])
    open()
    expect(await screen.findByRole('link', { name: 'Partner Summit' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Trade Fair' })).toBeInTheDocument()
    const [first] = screen.getAllByRole('listitem')
    expect(within(first).getByText(formatRange(SUMMIT.proposed_start, SUMMIT.proposed_end))).toBeInTheDocument()
  })

  it('AC1: labels an event that was never named rather than rendering a blank', async () => {
    vi.mocked(listRegistrableEvents).mockResolvedValue([{ ...SUMMIT, name: null }])
    open()
    expect(await screen.findByText('Untitled event')).toBeInTheDocument()
  })

  it('AC3: selecting an event links to its attendee-facing details', async () => {
    vi.mocked(listRegistrableEvents).mockResolvedValue([SUMMIT])
    open()
    expect(await screen.findByRole('link', { name: 'Partner Summit' })).toHaveAttribute('href', '/attendee/events/3')
  })

  it('AC4: shows only summary information', async () => {
    vi.mocked(listRegistrableEvents).mockResolvedValue([SUMMIT])
    open()
    await screen.findByRole('link', { name: 'Partner Summit' })
    expect(screen.queryByText(/coordinator|equipment|venue booking|reservation|technical/i)).not.toBeInTheDocument()
  })

  it('AC5: says so when no events are open for registration', async () => {
    vi.mocked(listRegistrableEvents).mockResolvedValue([])
    open()
    expect(await screen.findByText('No events are open for registration right now.')).toBeInTheDocument()
    expect(screen.queryByRole('listitem')).not.toBeInTheDocument()
  })

  it('AC5: a failure to load is an error, not "no events"', async () => {
    vi.mocked(listRegistrableEvents).mockRejectedValue(new ApiError(500, 'The catalogue is unavailable.'))
    open()
    expect(await screen.findByRole('alert')).toHaveTextContent('The catalogue is unavailable.')
  })

  it('AC6: shows the values the server has now', async () => {
    vi.mocked(listRegistrableEvents).mockResolvedValue([{ ...SUMMIT, name: 'Partner Summit 2027' }])
    open()
    expect(await screen.findByRole('link', { name: 'Partner Summit 2027' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Partner Summit' })).not.toBeInTheDocument()
  })

  it.todo('AC1: shows each event\'s category (the API does not return it yet)')
  it.todo('AC1: shows each event\'s venue name (the API does not return it yet)')
})
