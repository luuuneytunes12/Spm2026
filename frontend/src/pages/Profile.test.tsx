/**
 * Component tests for the Edit User Profile screen.
 *
 * Traceability (see docs/test-cases-edit-profile.md):
 *   TC-EP-1a, TC-EP-1b -- AC1, any field can be changed and is saved
 *   TC-EP-2a           -- AC2, an invalid email is flagged, nothing saved
 *   TC-EP-3a, TC-EP-3b -- AC3, an invalid phone number is flagged
 *
 * `lib/profile` and `useAuth` are mocked: this layer is about rendering
 * and wiring. The real request/response behaviour (format rules, digit
 * counts, persistence) is covered by backend/tests/test_users.py.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
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

const USER: AuthUser = {
  id: 5,
  name: 'Jane Organiser',
  email: 'jane@example.com',
  role: 'organiser',
  is_available: true,
  organisation: 'Acme Events',
  phone_country_code: '+65',
  phone_number: '91234567',
  communication_preference: 'email',
  created_at: '2026-09-10T00:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
  mockUseAuth.mockReturnValue({ user: USER, refreshUser })
  mockUpdate.mockResolvedValue({ ...USER })
})

describe('AC1 - any profile field can be updated and is reflected', () => {
  it('TC-EP-1a: pre-fills the form with the current profile', () => {
    render(<Profile />)
    expect(screen.getByLabelText('Name')).toHaveValue('Jane Organiser')
    expect(screen.getByLabelText('Organisation')).toHaveValue('Acme Events')
    expect(screen.getByLabelText('Email')).toHaveValue('jane@example.com')
    expect(screen.getByLabelText('Phone number')).toHaveValue('91234567')
  })

  it('TC-EP-1b: saves the edited fields and shows a confirmation', async () => {
    const user = userEvent.setup()
    render(<Profile />)

    await user.clear(screen.getByLabelText('Organisation'))
    await user.type(screen.getByLabelText('Organisation'), 'New Org')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1))
    expect(mockUpdate).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Jane Organiser', organisation: 'New Org' }),
    )
    expect(refreshUser).toHaveBeenCalledTimes(1)
    expect(await screen.findByText('Your profile has been updated.')).toBeInTheDocument()
  })
})

describe('AC2 - an invalid email format is rejected and nothing is saved', () => {
  it('TC-EP-2a: flags the email field and shows the server error', async () => {
    const user = userEvent.setup()
    mockUpdate.mockRejectedValueOnce(
      new ApiError(422, 'email: value is not a valid email address', ['email']),
    )
    render(<Profile />)

    await user.clear(screen.getByLabelText('Email'))
    await user.type(screen.getByLabelText('Email'), 'not-an-email')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() =>
      expect(screen.getByLabelText('Email')).toHaveAttribute('aria-invalid', 'true'),
    )
    expect(screen.getByRole('alert')).toHaveTextContent('not a valid email')
    expect(screen.queryByText('Your profile has been updated.')).not.toBeInTheDocument()
  })
})

describe('AC3 - an invalid phone number is rejected and nothing is saved', () => {
  it('TC-EP-3a: flags the phone field when it contains letters', async () => {
    const user = userEvent.setup()
    mockUpdate.mockRejectedValueOnce(
      new ApiError(422, 'phone_number: must contain digits only', ['phone_number']),
    )
    render(<Profile />)

    await user.clear(screen.getByLabelText('Phone number'))
    await user.type(screen.getByLabelText('Phone number'), '9123abcd')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() =>
      expect(screen.getByLabelText('Phone number')).toHaveAttribute('aria-invalid', 'true'),
    )
    expect(
      screen.getByText('Enter a valid phone number for the selected country code.'),
    ).toBeInTheDocument()
  })

  it('TC-EP-3b: flags the phone field when the digit count is wrong for the country', async () => {
    const user = userEvent.setup()
    mockUpdate.mockRejectedValueOnce(
      new ApiError(422, 'phone_number: must have 8 digits for this country code', [
        'phone_number',
      ]),
    )
    render(<Profile />)

    await user.clear(screen.getByLabelText('Phone number'))
    await user.type(screen.getByLabelText('Phone number'), '123')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1))
    expect(screen.getByLabelText('Phone number')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.queryByText('Your profile has been updated.')).not.toBeInTheDocument()
  })
})

describe('network failure', () => {
  it('shows a fallback message when the server cannot be reached', async () => {
    const user = userEvent.setup()
    mockUpdate.mockRejectedValueOnce(new Error('network down'))
    render(<Profile />)

    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(
      await screen.findByText('Could not reach the server. Is the backend running?'),
    ).toBeInTheDocument()
  })
})

describe("SCRUM-24 AC1 - a Coordinator's profile shows their availability", () => {
  const COORDINATOR: AuthUser = { ...USER, role: 'coordinator', name: 'Sam Tan' }

  function renderAs(user: AuthUser) {
    mockUseAuth.mockReturnValue({ user, refreshUser })
    return render(
      <MemoryRouter>
        <Profile />
      </MemoryRouter>,
    )
  }

  it('shows "Available" when the Coordinator is in the assignment pool', () => {
    renderAs({ ...COORDINATOR, is_available: true })

    const card = screen.getByRole('region', { name: 'Availability' })
    expect(within(card).getByText('Available')).toBeInTheDocument()
    expect(within(card).queryByText('Unavailable')).not.toBeInTheDocument()
  })

  it('shows "Unavailable" once they have marked themselves unavailable', () => {
    renderAs({ ...COORDINATOR, is_available: false })

    const card = screen.getByRole('region', { name: 'Availability' })
    expect(within(card).getByText('Unavailable')).toBeInTheDocument()
    expect(within(card).getByText(/will not be assigned new events/)).toBeInTheDocument()
    expect(within(card).getByText(/Events already assigned to you stay with you/)).toBeInTheDocument()
  })

  it('reflects a change: Unavailable becomes Available when the status flips back', () => {
    const view = renderAs({ ...COORDINATOR, is_available: false })
    expect(screen.getByText('Unavailable')).toBeInTheDocument()

    mockUseAuth.mockReturnValue({ user: { ...COORDINATOR, is_available: true }, refreshUser })
    view.rerender(
      <MemoryRouter>
        <Profile />
      </MemoryRouter>,
    )

    expect(screen.getByText('Available')).toBeInTheDocument()
    expect(screen.queryByText('Unavailable')).not.toBeInTheDocument()
  })

  it('is read-only here and points to the Coordinator page to change it', () => {
    renderAs({ ...COORDINATOR, is_available: true })

    const card = screen.getByRole('region', { name: 'Availability' })
    expect(within(card).queryByRole('button')).not.toBeInTheDocument()
    expect(
      within(card).getByRole('link', { name: 'Change on your Event Coordinator page' }),
    ).toHaveAttribute('href', '/coordinator')
  })

  it.each(['organiser', 'attendee', 'venue_staff', 'tech_support'])(
    'is not shown to a %s, who has no availability to report',
    (role) => {
      renderAs({ ...USER, role: role as AuthUser['role'], is_available: false })

      expect(screen.queryByRole('region', { name: 'Availability' })).not.toBeInTheDocument()
      expect(screen.queryByText('Unavailable')).not.toBeInTheDocument()
    },
  )

  it('still shows the editable profile form beneath the status', () => {
    renderAs({ ...COORDINATOR, is_available: false })

    expect(screen.getByLabelText('Name')).toHaveValue('Sam Tan')
  })
})
