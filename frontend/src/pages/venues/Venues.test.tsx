/**
 * Component tests for searching and filtering venues.
 *
 * Traceability (see docs/test-cases-venue-search.md):
 *   VS AC1  keyword
 *   VS AC2  filters -- every one selected must hold
 *   VS AC3  expected attendance and date/time exclude venues
 *   VS AC4  what each result shows
 *   VS AC5  opening a result
 *
 * These assert what a Coordinator experiences -- labels, visible text, what
 * is asked of the API -- never CSS class names. Which venues actually match
 * is decided server-side and covered by backend/tests/test_venue_search.py;
 * here `lib/venues` is mocked.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Venues } from './Venues'

vi.mock('../../lib/venues', () => ({
  listVenues: vi.fn(),
  listVenueFilterOptions: vi.fn(),
  getVenue: vi.fn(),
}))

import { listVenueFilterOptions, listVenues } from '../../lib/venues'
import type { VenueFilterOptions, VenueSearch, VenueSummary } from '../../lib/venues'

const mockList = vi.mocked(listVenues)
const mockOptions = vi.mocked(listVenueFilterOptions)

const BALLROOM: VenueSummary = {
  id: 1,
  name: 'Marina Grand Ballroom',
  location: '10 Bayfront Ave, Level 3',
  capacity: 600,
  facilities: ['Stage', 'Built-in PA system'],
  is_active: true,
}

const SUITE: VenueSummary = {
  id: 2,
  name: 'Changi Business Suite',
  location: '2 Changi Business Park Ave 1',
  capacity: 40,
  facilities: ['Display screen'],
  is_active: false,
}

const OPTIONS: VenueFilterOptions = {
  layouts: ['Banquet', 'Boardroom', 'Theatre'],
  facilities: ['Projector', 'Stage', 'Video conferencing'],
  accessibility_features: ['Hearing loop', 'Wheelchair access'],
}

function renderPage() {
  return render(
    <MemoryRouter>
      <Venues />
    </MemoryRouter>,
  )
}

/** The criteria of the most recent search. */
function lastSearch(): VenueSearch {
  const calls = mockList.mock.calls
  return (calls[calls.length - 1]?.[0] ?? {}) as VenueSearch
}

beforeEach(() => {
  vi.clearAllMocks()
  mockList.mockResolvedValue([BALLROOM, SUITE])
  mockOptions.mockResolvedValue(OPTIONS)
})

describe('before anything is entered', () => {
  it('lists every venue, exactly as the page did before searching existed', async () => {
    renderPage()

    expect(await screen.findByText('Marina Grand Ballroom')).toBeInTheDocument()
    expect(screen.getByText('Changi Business Suite')).toBeInTheDocument()
    expect(lastSearch()).toEqual({})
  })
})

describe('VS AC1 - keyword', () => {
  it('searches by what is typed', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    await user.type(screen.getByRole('textbox', { name: 'Search venues' }), 'marina')

    await waitFor(() => expect(lastSearch()).toEqual({ q: 'marina' }))
  })

  it('waits for a pause in typing rather than searching on every keystroke', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')
    const before = mockList.mock.calls.length

    await user.type(screen.getByRole('textbox', { name: 'Search venues' }), 'ballroom')
    await waitFor(() => expect(lastSearch()).toEqual({ q: 'ballroom' }))

    // Eight characters typed, but nothing like eight requests.
    expect(mockList.mock.calls.length - before).toBeLessThan(4)
  })
})

describe('VS AC2 - filters', () => {
  it('offers the layouts recorded for venues, and filters by the one chosen', async () => {
    const user = userEvent.setup()
    renderPage()
    const layout = await screen.findByRole('combobox', { name: 'Layout' })

    await waitFor(() =>
      expect(within(layout).getAllByRole('option').map((o) => o.textContent)).toEqual([
        'Any layout',
        'Banquet',
        'Boardroom',
        'Theatre',
      ]),
    )

    await user.selectOptions(layout, 'Theatre')

    await waitFor(() => expect(lastSearch()).toEqual({ layout: 'Theatre' }))
  })

  it('asks for every facility ticked, not just one', async () => {
    const user = userEvent.setup()
    renderPage()
    const facilities = await screen.findByRole('group', { name: 'Facilities' })

    await user.click(await within(facilities).findByRole('checkbox', { name: 'Projector' }))
    await user.click(within(facilities).getByRole('checkbox', { name: 'Video conferencing' }))

    await waitFor(() =>
      expect(lastSearch()).toEqual({ facilities: ['Projector', 'Video conferencing'] }),
    )
  })

  it('asks for every accessibility feature ticked', async () => {
    const user = userEvent.setup()
    renderPage()
    const accessibility = await screen.findByRole('group', { name: 'Accessibility' })

    await user.click(await within(accessibility).findByRole('checkbox', { name: 'Hearing loop' }))

    await waitFor(() => expect(lastSearch()).toEqual({ accessibility: ['Hearing loop'] }))
  })

  it('unticking a facility takes it back out of the search', async () => {
    const user = userEvent.setup()
    renderPage()
    const facilities = await screen.findByRole('group', { name: 'Facilities' })
    const projector = await within(facilities).findByRole('checkbox', { name: 'Projector' })

    await user.click(projector)
    await waitFor(() => expect(lastSearch()).toEqual({ facilities: ['Projector'] }))
    await user.click(projector)

    await waitFor(() => expect(lastSearch()).toEqual({}))
  })

  it('combines the keyword with every filter in one search', async () => {
    const user = userEvent.setup()
    renderPage()
    const facilities = await screen.findByRole('group', { name: 'Facilities' })

    await user.type(screen.getByRole('textbox', { name: 'Search venues' }), 'marina')
    await user.type(screen.getByRole('spinbutton', { name: 'Expected attendance' }), '120')
    await user.click(await within(facilities).findByRole('checkbox', { name: 'Stage' }))

    await waitFor(() =>
      expect(lastSearch()).toEqual({ q: 'marina', minCapacity: 120, facilities: ['Stage'] }),
    )
  })

  it('still lets you search by keyword if the filter choices fail to load', async () => {
    const user = userEvent.setup()
    mockOptions.mockRejectedValue(new Error('offline'))
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    await user.type(screen.getByRole('textbox', { name: 'Search venues' }), 'marina')

    await waitFor(() => expect(lastSearch()).toEqual({ q: 'marina' }))
  })
})

describe('VS AC3 - date and time', () => {
  it('searches for venues free across the window entered', async () => {
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    fireEvent.change(screen.getByLabelText('Available from'), {
      target: { value: '2026-11-02T09:00' },
    })
    fireEvent.change(screen.getByLabelText('Available until'), {
      target: { value: '2026-11-02T17:00' },
    })

    // The inputs are in the Coordinator's local time; the API gets UTC.
    // Computed the same way here, so the test holds in any timezone.
    await waitFor(() =>
      expect(lastSearch()).toEqual({
        start: new Date('2026-11-02T09:00').toISOString(),
        end: new Date('2026-11-02T17:00').toISOString(),
      }),
    )
  })

  it('refuses a window that ends before it starts, and does not search with it', async () => {
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    fireEvent.change(screen.getByLabelText('Available from'), {
      target: { value: '2026-11-02T17:00' },
    })
    fireEvent.change(screen.getByLabelText('Available until'), {
      target: { value: '2026-11-02T09:00' },
    })

    expect(await screen.findByText('The end must be after the start.')).toBeInTheDocument()
    expect(mockList.mock.calls.every(([search]) => !search?.start && !search?.end)).toBe(true)
  })

  it('asks for the other half of the window rather than searching with one end', async () => {
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    fireEvent.change(screen.getByLabelText('Available from'), {
      target: { value: '2026-11-02T09:00' },
    })

    expect(await screen.findByText('Enter both a start and an end.')).toBeInTheDocument()
    expect(mockList.mock.calls.every(([search]) => !search?.start)).toBe(true)
  })
})

describe('VS AC3 - expected attendance', () => {
  it('searches for venues that hold at least that many people', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    await user.type(screen.getByRole('spinbutton', { name: 'Expected attendance' }), '120')

    await waitFor(() => expect(lastSearch()).toEqual({ minCapacity: 120 }))
  })

  it('ignores an attendance that is not a positive number', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    await user.type(screen.getByRole('spinbutton', { name: 'Expected attendance' }), '0')

    // Zero would be a 422 from the API; it is simply not a filter yet.
    await waitFor(() => expect(lastSearch()).toEqual({}))
  })
})

describe('VS AC4 - what each result shows', () => {
  it('shows the name, location, capacity and facilities of every result', async () => {
    renderPage()

    const card = (await screen.findByText('Marina Grand Ballroom')).closest('li')!
    expect(within(card).getByText(/10 Bayfront Ave, Level 3/)).toBeInTheDocument()
    expect(within(card).getByText(/600/)).toBeInTheDocument()
    expect(within(card).getByText('Stage')).toBeInTheDocument()
    expect(within(card).getByText('Built-in PA system')).toBeInTheDocument()
  })

  it('marks an inactive venue as inactive rather than hiding it', async () => {
    renderPage()

    const card = (await screen.findByText('Changi Business Suite')).closest('li')!
    expect(within(card).getByText('Inactive')).toBeInTheDocument()
  })

  it('says so when nothing matches, and can clear back to every venue', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    mockList.mockResolvedValue([])
    await user.type(screen.getByRole('textbox', { name: 'Search venues' }), 'nowhere')
    expect(await screen.findByText('No venues match your search.')).toBeInTheDocument()

    mockList.mockResolvedValue([BALLROOM, SUITE])
    await user.click(screen.getByRole('button', { name: 'Clear filters' }))

    expect(await screen.findByText('Marina Grand Ballroom')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Search venues' })).toHaveValue('')
    await waitFor(() => expect(lastSearch()).toEqual({}))
  })
})

describe('VS AC5 - opening a result', () => {
  it('links each result to that venue’s full details', async () => {
    renderPage()

    const link = await screen.findByRole('link', { name: 'View details of Marina Grand Ballroom' })
    expect(link).toHaveAttribute('href', '/venues/1')
  })
})
