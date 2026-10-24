/**
 * Component tests for the staff directory (SCRUM-19 AC2/AC3): colleagues'
 * department and responsibilities are visible to internal staff.
 */
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/api'

vi.mock('../lib/staff', () => ({ listStaff: vi.fn() }))

import { listStaff } from '../lib/staff'
import { StaffDirectory } from './StaffDirectory'

beforeEach(() => vi.clearAllMocks())

describe('StaffDirectory', () => {
  it('AC2/AC3: shows each colleague\'s department and responsibilities', async () => {
    vi.mocked(listStaff).mockResolvedValue([
      {
        id: 1,
        name: 'Sam Tan',
        email: 'sam@cs.local',
        role: 'venue_staff',
        department: 'venue_operations',
        responsibilities: 'Booking approvals',
      },
      {
        id: 2,
        name: 'Ria Lim',
        email: 'ria@cs.local',
        role: 'safety_officer',
        department: null,
        responsibilities: null,
      },
    ])
    render(<StaffDirectory />)

    expect(await screen.findByRole('rowheader', { name: 'Sam Tan' })).toBeInTheDocument()
    expect(screen.getByText('Venue Staff')).toBeInTheDocument()
    expect(screen.getByText('Venue Operations')).toBeInTheDocument()
    expect(screen.getByText('Booking approvals')).toBeInTheDocument()
    expect(screen.getByText('sam@cs.local')).toBeInTheDocument()
    // A colleague who has recorded nothing yet shows a dash, not a blank.
    expect(screen.getAllByText('—')).toHaveLength(2)
  })

  it('AC6: shows the refusal when the API denies the listing', async () => {
    vi.mocked(listStaff).mockRejectedValue(new ApiError(403, 'Forbidden', []))
    render(<StaffDirectory />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Forbidden')
  })
})
