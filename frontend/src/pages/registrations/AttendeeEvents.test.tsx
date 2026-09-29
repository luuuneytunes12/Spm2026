/**
 * Component tests for the Attendee's events list.
 *
 * Traceability (see docs/test-cases-attendee-registration.md): each row
 * state shows the right control. The rules themselves (what "open" means,
 * no double registration) are enforced server-side and covered by
 * backend/tests/test_registrations.py.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AttendeeEvents } from './AttendeeEvents'

vi.mock('../../lib/registrations', () => ({
  listRegistrableEvents: vi.fn(),
  registerForEvent: vi.fn(),
  withdrawFromEvent: vi.fn(),
}))

import { listRegistrableEvents, registerForEvent, withdrawFromEvent } from '../../lib/registrations'
import type { RegistrableEvent } from '../../lib/registrations'

const mockList = vi.mocked(listRegistrableEvents)
const mockRegister = vi.mocked(registerForEvent)
const mockWithdraw = vi.mocked(withdrawFromEvent)

const OPEN: RegistrableEvent = {
  id: 3,
  name: 'Partner Summit',
  proposed_start: '2026-11-02T09:00:00Z',
  proposed_end: '2026-11-02T17:00:00Z',
  registration_open: true,
  my_status: null,
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('registering', () => {
  it('offers Register on an open event and shows Registered afterwards', async () => {
    mockList.mockResolvedValue([OPEN])
    mockRegister.mockResolvedValue({ ...OPEN, my_status: 'registered' })
    render(<AttendeeEvents />)

    await userEvent.click(await screen.findByRole('button', { name: 'Register' }))

    expect(mockRegister).toHaveBeenCalledWith(3)
    expect(await screen.findByText('Registered')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Register/ })).not.toBeInTheDocument()
  })

  it('offers no way to register once registration has closed', async () => {
    mockList.mockResolvedValue([{ ...OPEN, registration_open: false }])
    render(<AttendeeEvents />)

    expect(await screen.findByText('Registration closed')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('does not offer Register to someone already registered', async () => {
    mockList.mockResolvedValue([{ ...OPEN, my_status: 'registered' }])
    render(<AttendeeEvents />)

    expect(await screen.findByRole('button', { name: 'Withdraw' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Register/ })).not.toBeInTheDocument()
  })
})

describe('withdrawing', () => {
  it('changes the status to Withdrawn', async () => {
    mockList.mockResolvedValue([{ ...OPEN, my_status: 'registered' }])
    mockWithdraw.mockResolvedValue({ ...OPEN, my_status: 'withdrawn' })
    render(<AttendeeEvents />)

    await userEvent.click(await screen.findByRole('button', { name: 'Withdraw' }))

    expect(mockWithdraw).toHaveBeenCalledWith(3)
    expect(await screen.findByText('Withdrawn')).toBeInTheDocument()
  })

  it('offers Register again after withdrawing while still open', async () => {
    mockList.mockResolvedValue([{ ...OPEN, my_status: 'withdrawn' }])
    render(<AttendeeEvents />)

    expect(await screen.findByRole('button', { name: 'Register again' })).toBeInTheDocument()
  })
})
