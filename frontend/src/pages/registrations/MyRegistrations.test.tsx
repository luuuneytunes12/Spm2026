/**
 * Component tests for the Attendee's My Registrations page (SCRUM-49).
 *
 * Each test is named for the acceptance criterion it covers. What counts as a
 * registration (one row per event, withdrawn ones kept) is decided server-side
 * and covered by backend/tests/test_registrations.py; here we check the page
 * shows what it is given, and asks the server fresh every time it opens.
 */
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MyRegistrations } from './MyRegistrations'

vi.mock('../../lib/registrations', () => ({
  listMyRegistrations: vi.fn(),
}))

import { listMyRegistrations } from '../../lib/registrations'
import type { RegistrableEvent } from '../../lib/registrations'

const mockList = vi.mocked(listMyRegistrations)

const SUMMIT: RegistrableEvent = {
  id: 3,
  name: 'Partner Summit',
  proposed_start: '2026-11-02T09:00:00Z',
  proposed_end: '2026-11-02T17:00:00Z',
  registration_open: true,
  my_status: 'registered',
}

const WORKSHOP: RegistrableEvent = {
  id: 4,
  name: 'Design Workshop',
  proposed_start: '2026-12-05T09:00:00Z',
  proposed_end: '2026-12-05T12:00:00Z',
  registration_open: true,
  my_status: 'withdrawn',
}

function renderPage() {
  return render(
    <MemoryRouter>
      <MyRegistrations />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('My Registrations', () => {
  it('AC1: shows each event name, date, time and registration status', async () => {
    mockList.mockResolvedValue([SUMMIT])
    renderPage()

    const row = (await screen.findByText('Partner Summit')).closest('li') as HTMLElement
    // Date and time come from the shared range formatter: "<date>, <start> – <end>".
    expect(within(row).getByText(/2026/)).toBeInTheDocument()
    expect(within(row).getByText(/–/)).toBeInTheDocument()
    expect(within(row).getByText('Registered')).toBeInTheDocument()
  })

  it('AC2: a withdrawn event still appears, with the status Withdrawn', async () => {
    mockList.mockResolvedValue([SUMMIT, WORKSHOP])
    renderPage()

    const row = (await screen.findByText('Design Workshop')).closest('li') as HTMLElement
    expect(within(row).getByText('Withdrawn')).toBeInTheDocument()
  })

  it('AC3: an event registered for since the last visit shows Registered on open', async () => {
    mockList.mockResolvedValueOnce([])
    const first = renderPage()
    expect(await screen.findByText('No registrations yet.')).toBeInTheDocument()
    first.unmount()

    mockList.mockResolvedValueOnce([SUMMIT])
    renderPage()

    expect(await screen.findByText('Registered')).toBeInTheDocument()
    expect(mockList).toHaveBeenCalledTimes(2)
  })

  it('AC4: an event withdrawn from since the last visit shows Withdrawn on open', async () => {
    mockList.mockResolvedValueOnce([SUMMIT])
    const first = renderPage()
    expect(await screen.findByText('Registered')).toBeInTheDocument()
    first.unmount()

    mockList.mockResolvedValueOnce([{ ...SUMMIT, my_status: 'withdrawn' }])
    renderPage()

    expect(await screen.findByText('Withdrawn')).toBeInTheDocument()
    expect(screen.queryByText('Registered')).not.toBeInTheDocument()
  })

  it('AC5: an event withdrawn from and registered for again appears once, as Registered', async () => {
    mockList.mockResolvedValue([{ ...SUMMIT, my_status: 'registered' }])
    renderPage()

    expect(await screen.findAllByText('Partner Summit')).toHaveLength(1)
    expect(screen.getByText('Registered')).toBeInTheDocument()
    expect(screen.queryByText('Withdrawn')).not.toBeInTheDocument()
  })

  it('AC6: with no registrations, shows "No registrations yet"', async () => {
    mockList.mockResolvedValue([])
    renderPage()

    expect(await screen.findByText('No registrations yet.')).toBeInTheDocument()
    expect(screen.queryByRole('listitem')).not.toBeInTheDocument()
  })

  it('is read-only: offers no register or withdraw controls', async () => {
    mockList.mockResolvedValue([SUMMIT, WORKSHOP])
    renderPage()

    await screen.findByText('Partner Summit')
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
