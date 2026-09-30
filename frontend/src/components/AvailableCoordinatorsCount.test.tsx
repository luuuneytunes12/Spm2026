/**
 * The Organiser's "coordinators available" dropdown -- a debugging aid that
 * explains a request sitting "Not yet assigned" and names who is in the
 * assignment pool. The pool itself comes from the backend
 * (backend/tests/test_available_coordinator_count.py); these tests cover
 * what the screen does with it.
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/api'
import { AvailableCoordinatorsCount } from './AvailableCoordinatorsCount'

vi.mock('../lib/coordinators', () => ({ getAssignmentPool: vi.fn() }))

import { getAssignmentPool } from '../lib/coordinators'

const mockPool = vi.mocked(getAssignmentPool)

const SAM = { id: 2, name: 'Sam Tan', email: 'sam@connectsphere.test' }
const PRIYA = { id: 3, name: 'Priya Nair', email: 'priya@connectsphere.test' }

beforeEach(() => {
  vi.clearAllMocks()
})

describe('the summary', () => {
  it('shows how many coordinators a new submission could go to', async () => {
    mockPool.mockResolvedValue({ available: 2, coordinators: [SAM, PRIYA] })

    render(<AvailableCoordinatorsCount />)

    expect(await screen.findByText(/Coordinators currently available for assignment/)).toBeVisible()
    expect(screen.getByText('2')).toBeVisible()
  })
})

describe('the dropdown', () => {
  it('starts collapsed, hiding the names', async () => {
    mockPool.mockResolvedValue({ available: 2, coordinators: [SAM, PRIYA] })

    render(<AvailableCoordinatorsCount />)

    const details = await screen.findByTestId('available-coordinators')
    expect(details).not.toHaveAttribute('open')
    expect(screen.getByText('Sam Tan')).not.toBeVisible()
    expect(screen.getByText('Priya Nair')).not.toBeVisible()
  })

  it('lists every coordinator in the pool, with a mailto link, once opened', async () => {
    mockPool.mockResolvedValue({ available: 2, coordinators: [SAM, PRIYA] })
    render(<AvailableCoordinatorsCount />)

    await userEvent.click(await screen.findByText(/Coordinators currently available/))

    const list = screen.getByRole('list', { name: 'Coordinators in the assignment pool' })
    const items = within(list).getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('Sam Tan')
    expect(within(items[0]).getByRole('link', { name: 'sam@connectsphere.test' })).toHaveAttribute(
      'href',
      'mailto:sam@connectsphere.test',
    )
    expect(items[1]).toHaveTextContent('Priya Nair')
    expect(list).toBeVisible()
  })

  it('collapses again when the summary is clicked a second time', async () => {
    mockPool.mockResolvedValue({ available: 1, coordinators: [SAM] })
    render(<AvailableCoordinatorsCount />)
    const summary = await screen.findByText(/Coordinators currently available/)

    await userEvent.click(summary)
    expect(screen.getByText('Sam Tan')).toBeVisible()
    await userEvent.click(summary)

    expect(screen.getByText('Sam Tan')).not.toBeVisible()
  })
})

describe('an empty pool', () => {
  it('says why requests stay unassigned, with nothing to expand', async () => {
    mockPool.mockResolvedValue({ available: 0, coordinators: [] })

    render(<AvailableCoordinatorsCount />)

    const line = await screen.findByTestId('available-coordinators')
    expect(line).toHaveTextContent('available for assignment: 0')
    expect(line).toHaveTextContent('new submissions will stay unassigned')
    expect(line.tagName).not.toBe('DETAILS')
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })
})

describe('when the pool is not shown', () => {
  it('shows nothing while it is loading', () => {
    mockPool.mockReturnValue(new Promise(() => {}))

    render(<AvailableCoordinatorsCount />)

    expect(screen.queryByTestId('available-coordinators')).not.toBeInTheDocument()
  })

  it('shows nothing rather than an error when it cannot be fetched', async () => {
    mockPool.mockRejectedValue(new ApiError(403, 'Forbidden'))

    render(<AvailableCoordinatorsCount />)

    await vi.waitFor(() => expect(mockPool).toHaveBeenCalled())
    expect(screen.queryByTestId('available-coordinators')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
