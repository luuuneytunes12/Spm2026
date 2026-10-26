/**
 * Component tests for "Record Department & Responsibilities" (SCRUM-19) on
 * the Profile page. AC numbers follow the story: AC1 predefined list,
 * AC2 department saved, AC3 responsibilities saved, AC4 change replaces,
 * AC5 missing department blocks save, AC6 not-mine / non-staff.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/api'

const refreshUser = vi.fn()
const mockUseAuth = vi.fn()
vi.mock('../auth/useAuth', () => ({ useAuth: () => mockUseAuth() }))
vi.mock('../lib/profile', () => ({ updateMyProfile: vi.fn() }))

import { updateMyProfile } from '../lib/profile'
import type { AuthUser } from '../auth/auth-context'
import { Profile } from './Profile'

const mockUpdate = vi.mocked(updateMyProfile)

const STAFF: AuthUser = {
  id: 7,
  name: 'Sam Tan',
  email: 'sam@example.com',
  role: 'venue_staff',
  is_available: true,
  organisation: null,
  phone_country_code: null,
  phone_number: null,
  communication_preference: null,
  department: null,
  responsibilities: null,
  created_at: '2026-09-10T00:00:00Z',
}

function signIn(user: AuthUser) {
  mockUseAuth.mockReturnValue({ user, refreshUser })
}

beforeEach(() => {
  vi.clearAllMocks()
  signIn(STAFF)
  mockUpdate.mockResolvedValue({ ...STAFF, department: 'venue_operations' })
})

describe('AC1 - only a department from the predefined list can be chosen', () => {
  it('offers exactly the four departments plus a placeholder', () => {
    render(<Profile />)
    const options = within(screen.getByLabelText('Department')).getAllByRole('option')
    expect(options.map((o) => o.textContent)).toEqual([
      'Select a department',
      'Events Coordination',
      'Venue Operations',
      'Technical Support',
      'Safety & Compliance',
    ])
  })
})

describe('AC2 - the chosen department is saved', () => {
  it('sends the department slug on save and confirms', async () => {
    const user = userEvent.setup()
    render(<Profile />)
    await user.selectOptions(screen.getByLabelText('Department'), 'Venue Operations')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1))
    expect(mockUpdate).toHaveBeenCalledWith(
      expect.objectContaining({ department: 'venue_operations', responsibilities: null }),
    )
    expect(await screen.findByText('Your profile has been updated.')).toBeInTheDocument()
  })
})

describe('AC3 - responsibilities are saved and shown', () => {
  it('sends the typed responsibilities and shows the saved ones', async () => {
    const user = userEvent.setup()
    signIn({ ...STAFF, department: 'venue_operations' })
    mockUpdate.mockResolvedValue({
      ...STAFF,
      department: 'venue_operations',
      responsibilities: 'Booking approvals',
    })
    render(<Profile />)
    await user.type(screen.getByLabelText('Responsibilities'), 'Booking approvals')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() =>
      expect(mockUpdate).toHaveBeenCalledWith(
        expect.objectContaining({ responsibilities: 'Booking approvals' }),
      ),
    )
    expect(screen.getByLabelText('Responsibilities')).toHaveValue('Booking approvals')
  })

  it('limits responsibilities to 1000 characters', () => {
    render(<Profile />)
    expect(screen.getByLabelText('Responsibilities')).toHaveAttribute('maxlength', '1000')
  })
})

describe('AC4 - a different department replaces the old one', () => {
  it('pre-fills the current department and saves the new one', async () => {
    const user = userEvent.setup()
    signIn({ ...STAFF, department: 'venue_operations' })
    mockUpdate.mockResolvedValue({ ...STAFF, department: 'safety_compliance' })
    render(<Profile />)
    expect(screen.getByLabelText('Department')).toHaveValue('venue_operations')

    await user.selectOptions(screen.getByLabelText('Department'), 'safety_compliance')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() =>
      expect(mockUpdate).toHaveBeenCalledWith(
        expect.objectContaining({ department: 'safety_compliance' }),
      ),
    )
    expect(screen.getByLabelText('Department')).toHaveValue('safety_compliance')
  })
})

describe('AC5 - no department blocks the save and flags the field', () => {
  it('sends nothing and marks Department invalid', async () => {
    const user = userEvent.setup()
    render(<Profile />)
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(mockUpdate).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Department')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getAllByText('Select your department.').length).toBeGreaterThan(0)
    expect(screen.queryByText('Your profile has been updated.')).not.toBeInTheDocument()
  })

  it('flags Department when the server rejects it', async () => {
    const user = userEvent.setup()
    mockUpdate.mockRejectedValueOnce(new ApiError(422, 'department: required', ['department']))
    render(<Profile />)
    await user.selectOptions(screen.getByLabelText('Department'), 'Venue Operations')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() =>
      expect(screen.getByLabelText('Department')).toHaveAttribute('aria-invalid', 'true'),
    )
  })
})

describe('AC6 - people who are not internal staff have no department', () => {
  it.each(['organiser', 'attendee'] as const)('%s sees no Work section and sends no such fields', async (role) => {
    const user = userEvent.setup()
    signIn({ ...STAFF, role })
    mockUpdate.mockResolvedValue({ ...STAFF, role })
    render(<Profile />)

    expect(screen.queryByLabelText('Department')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Responsibilities')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1))
    expect(mockUpdate.mock.calls[0][0]).not.toHaveProperty('department')
    expect(mockUpdate.mock.calls[0][0]).not.toHaveProperty('responsibilities')
  })
})
