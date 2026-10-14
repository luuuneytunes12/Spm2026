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
 * and "Filter Venues by Date and Time" (docs/test-cases-venue-date-filter.md):
 *   DT AC1  date, start and end time exclude venues that are not free
 *   DT AC3  an end time earlier than the start blocks the search, fields flagged
 *   DT AC4  the date and time combine with every other filter
 *   (DT AC2 -- which booking statuses count -- is decided server-side, in
 *   backend/tests/test_venue_date_filter.py.)
 *
 * The filters live in a compact bar: one chip per filter, each opening a
 * small panel. Tests open the chip first, exactly as a person would.
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

/** Open a filter's panel by clicking its chip. Matched by the start of its
 *  name, because an active chip also shows its value ("Layout: Theatre"). */
async function openFilter(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(screen.getByRole('button', { name: new RegExp(`^${name}`) }))
  return screen.findByRole('dialog', { name: new RegExp(name, 'i') })
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

  it('keeps the filters out of the way until one is opened', async () => {
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    // The point of the filter bar: the venues, not the options, fill the
    // page. No checklist, date field or layout list is shown up front.
    for (const name of ['Attendance', 'Layout', 'Date & time', 'Facilities', 'Accessibility']) {
      expect(screen.getByRole('button', { name })).toHaveAttribute('aria-expanded', 'false')
    }
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('says how many venues are listed', async () => {
    renderPage()

    expect(await screen.findByText('2 venues')).toBeInTheDocument()
  })

  it('uses the singular for a single venue', async () => {
    mockList.mockResolvedValue([BALLROOM])
    renderPage()

    expect(await screen.findByText('1 venue')).toBeInTheDocument()
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
    await screen.findByText('Marina Grand Ballroom')

    const panel = await openFilter(user, 'Layout')
    // One choice only -- an event uses one layout -- so radios, not
    // checkboxes, with "Any layout" as the way back.
    await waitFor(() =>
      expect(within(panel).getAllByRole('radio').map((r) => r.closest('label')?.textContent)).toEqual([
        'Any layout',
        'Banquet',
        'Boardroom',
        'Theatre',
      ]),
    )

    await user.click(within(panel).getByRole('radio', { name: 'Theatre' }))

    await waitFor(() => expect(lastSearch()).toEqual({ layout: 'Theatre' }))
  })

  it('asks for every facility ticked, not just one', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    const panel = await openFilter(user, 'Facilities')
    const facilities = within(panel).getByRole('group', { name: 'Facilities' })
    await user.click(await within(facilities).findByRole('checkbox', { name: 'Projector' }))
    await user.click(within(facilities).getByRole('checkbox', { name: 'Video conferencing' }))

    await waitFor(() =>
      expect(lastSearch()).toEqual({ facilities: ['Projector', 'Video conferencing'] }),
    )
  })

  it('asks for every accessibility feature ticked', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    const panel = await openFilter(user, 'Accessibility')
    const accessibility = within(panel).getByRole('group', { name: 'Accessibility' })
    await user.click(await within(accessibility).findByRole('checkbox', { name: 'Hearing loop' }))

    await waitFor(() => expect(lastSearch()).toEqual({ accessibility: ['Hearing loop'] }))
  })

  it('unticking a facility takes it back out of the search', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    const panel = await openFilter(user, 'Facilities')
    const projector = await within(panel).findByRole('checkbox', { name: 'Projector' })
    await user.click(projector)
    await waitFor(() => expect(lastSearch()).toEqual({ facilities: ['Projector'] }))
    await user.click(projector)

    await waitFor(() => expect(lastSearch()).toEqual({}))
  })

  it('combines the keyword with every filter in one search', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    await user.type(screen.getByRole('textbox', { name: 'Search venues' }), 'marina')
    const attendance = await openFilter(user, 'Attendance')
    await user.type(within(attendance).getByRole('spinbutton', { name: 'Expected attendance' }), '120')
    const facilities = await openFilter(user, 'Facilities')
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

describe('the filter bar', () => {
  it('shows an applied filter on its chip, so what is filtered is visible at a glance', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    const layout = await openFilter(user, 'Layout')
    await user.click(await within(layout).findByRole('radio', { name: 'Theatre' }))
    const facilities = await openFilter(user, 'Facilities')
    await user.click(await within(facilities).findByRole('checkbox', { name: 'Projector' }))
    await user.click(within(facilities).getByRole('checkbox', { name: 'Stage' }))

    expect(screen.getByRole('button', { name: 'Layout: Theatre' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Facilities · 2' })).toBeInTheDocument()
  })

  it('removes one filter with its own ✕, leaving the others', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    const layout = await openFilter(user, 'Layout')
    await user.click(await within(layout).findByRole('radio', { name: 'Theatre' }))
    const facilities = await openFilter(user, 'Facilities')
    await user.click(await within(facilities).findByRole('checkbox', { name: 'Stage' }))
    await waitFor(() => expect(lastSearch()).toEqual({ layout: 'Theatre', facilities: ['Stage'] }))

    await user.click(screen.getByRole('button', { name: 'Remove Layout filter' }))

    await waitFor(() => expect(lastSearch()).toEqual({ facilities: ['Stage'] }))
    expect(screen.getByRole('button', { name: /^Layout$/ })).toBeInTheDocument()
  })

  it('clears the keyword and every filter with "Clear all"', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')
    expect(screen.queryByRole('button', { name: 'Clear all' })).not.toBeInTheDocument()

    await user.type(screen.getByRole('textbox', { name: 'Search venues' }), 'marina')
    const facilities = await openFilter(user, 'Facilities')
    await user.click(await within(facilities).findByRole('checkbox', { name: 'Stage' }))
    await waitFor(() => expect(lastSearch()).toEqual({ q: 'marina', facilities: ['Stage'] }))

    await user.click(screen.getByRole('button', { name: 'Clear all' }))

    await waitFor(() => expect(lastSearch()).toEqual({}))
    expect(screen.getByRole('textbox', { name: 'Search venues' })).toHaveValue('')
    expect(screen.queryByRole('button', { name: 'Clear all' })).not.toBeInTheDocument()
  })

  it('closes a panel with Escape and returns focus to its chip', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    await openFilter(user, 'Facilities')
    await user.keyboard('{Escape}')

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Facilities/ })).toHaveFocus()
  })

  it('closes a panel when you click elsewhere on the page', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    await openFilter(user, 'Facilities')
    await user.click(screen.getByRole('heading', { name: 'Venues' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('keeps focus where you are while you tick, rather than jumping to the first choice', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    const panel = await openFilter(user, 'Facilities')
    await user.click(await within(panel).findByRole('checkbox', { name: 'Projector' }))
    const second = within(panel).getByRole('checkbox', { name: 'Video conferencing' })
    await user.click(second)
    await waitFor(() =>
      expect(lastSearch()).toEqual({ facilities: ['Projector', 'Video conferencing'] }),
    )

    // Moving focus on open is right; moving it on every re-render would
    // drag a keyboard user back to the first ticked box after each tick.
    expect(second).toHaveFocus()
  })

  it('opens one panel at a time', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    await openFilter(user, 'Facilities')
    await openFilter(user, 'Layout')

    expect(screen.getAllByRole('dialog')).toHaveLength(1)
    expect(screen.getByRole('button', { name: /^Facilities/ })).toHaveAttribute('aria-expanded', 'false')
  })
})

/** Fill the Date & time panel. Each value is set only when given, so a test
 *  can leave a field empty on purpose. */
function fillWindow(
  panel: HTMLElement,
  { date, start, end }: { date?: string; start?: string; end?: string },
) {
  if (date !== undefined)
    fireEvent.change(within(panel).getByLabelText('Date'), { target: { value: date } })
  if (start !== undefined)
    fireEvent.change(within(panel).getByLabelText('Start time'), { target: { value: start } })
  if (end !== undefined)
    fireEvent.change(within(panel).getByLabelText('End time'), { target: { value: end } })
}

/** Long enough for the search debounce to have fired, had it been going to. */
const pastTheDebounce = () => new Promise((resolve) => setTimeout(resolve, 400))

describe('DT AC1 - date, start time and end time', () => {
  it('searches for venues free on that date between the start and end time', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    const panel = await openFilter(user, 'Date & time')
    fillWindow(panel, { date: '2026-11-02', start: '09:00', end: '17:00' })

    // The inputs are in the Coordinator's local time; the API gets UTC.
    // Computed the same way here, so the test holds in any timezone.
    await waitFor(() =>
      expect(lastSearch()).toEqual({
        start: new Date('2026-11-02T09:00').toISOString(),
        end: new Date('2026-11-02T17:00').toISOString(),
      }),
    )
  })

  it('says that bookings, tentative holds, closures and setup and turnaround time count', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    const panel = await openFilter(user, 'Date & time')

    expect(
      within(panel).getByText(
        /booked, tentatively held or closed then, counting each venue's setup and turnaround time/,
      ),
    ).toBeInTheDocument()
  })

  it('shows the window on its chip once the panel is closed', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    const panel = await openFilter(user, 'Date & time')
    fillWindow(panel, { date: '2026-11-02', start: '09:00', end: '17:00' })
    await user.keyboard('{Escape}')

    // "2 Nov, 09:00 – 17:00" or "Nov 2, …" depending on the machine's locale.
    expect(screen.getByRole('button', { name: /^(2 Nov|Nov 2).*–/ })).toBeInTheDocument()
  })
})

describe('DT AC3 - an end time earlier than the start time', () => {
  it('blocks the search and flags both time fields', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')
    const callsBefore = mockList.mock.calls.length

    const panel = await openFilter(user, 'Date & time')
    fillWindow(panel, { date: '2026-11-02', start: '17:00', end: '09:00' })

    expect(
      await within(panel).findByText('The end time must be after the start time.'),
    ).toBeInTheDocument()
    expect(within(panel).getByLabelText('Start time')).toHaveAttribute('aria-invalid', 'true')
    expect(within(panel).getByLabelText('End time')).toHaveAttribute('aria-invalid', 'true')
    expect(within(panel).getByLabelText('Date')).toHaveAttribute('aria-invalid', 'false')
    // Blocked: no venues are shown as if they matched, and nothing is sent.
    expect(screen.getByText('Search paused.')).toBeInTheDocument()
    expect(screen.queryByText('Marina Grand Ballroom')).not.toBeInTheDocument()
    await pastTheDebounce()
    expect(mockList.mock.calls.length).toBe(callsBefore)
  })

  it('stays blocked while other filters change', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')
    const callsBefore = mockList.mock.calls.length

    const panel = await openFilter(user, 'Date & time')
    fillWindow(panel, { date: '2026-11-02', start: '17:00', end: '09:00' })
    await user.keyboard('{Escape}')
    await user.type(screen.getByRole('textbox', { name: 'Search venues' }), 'marina')
    await pastTheDebounce()

    expect(mockList.mock.calls.length).toBe(callsBefore)
    expect(screen.getByRole('button', { name: 'Date & time: invalid' })).toBeInTheDocument()
  })

  it('treats an end time equal to the start time the same way', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    const panel = await openFilter(user, 'Date & time')
    fillWindow(panel, { date: '2026-11-02', start: '09:00', end: '09:00' })

    expect(
      await within(panel).findByText('The end time must be after the start time.'),
    ).toBeInTheDocument()
    expect(screen.getByText('Search paused.')).toBeInTheDocument()
  })

  it('resumes the search, and clears the flags, once the end time is fixed', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    const panel = await openFilter(user, 'Date & time')
    fillWindow(panel, { date: '2026-11-02', start: '17:00', end: '09:00' })
    await within(panel).findByText('The end time must be after the start time.')
    fillWindow(panel, { end: '18:00' })

    await waitFor(() =>
      expect(lastSearch()).toEqual({
        start: new Date('2026-11-02T17:00').toISOString(),
        end: new Date('2026-11-02T18:00').toISOString(),
      }),
    )
    expect(await screen.findByText('Marina Grand Ballroom')).toBeInTheDocument()
    expect(within(panel).getByLabelText('End time')).toHaveAttribute('aria-invalid', 'false')
    expect(screen.queryByText('Search paused.')).not.toBeInTheDocument()
  })
})

describe('DT - an unfinished date and time', () => {
  it('asks for what is missing, flags only that, and does not search with half a window', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    const panel = await openFilter(user, 'Date & time')
    fillWindow(panel, { date: '2026-11-02', start: '09:00' })

    expect(
      await within(panel).findByText('Enter a date, a start time and an end time.'),
    ).toBeInTheDocument()
    expect(within(panel).getByLabelText('End time')).toHaveAttribute('aria-invalid', 'true')
    expect(within(panel).getByLabelText('Start time')).toHaveAttribute('aria-invalid', 'false')
    expect(within(panel).getByLabelText('Date')).toHaveAttribute('aria-invalid', 'false')
    await pastTheDebounce()
    expect(mockList.mock.calls.every(([search]) => !search?.start && !search?.end)).toBe(true)
  })

  it('flags an unfinished window on its chip, so it is not forgotten once closed', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    const panel = await openFilter(user, 'Date & time')
    fillWindow(panel, { start: '09:00', end: '17:00' })
    await user.keyboard('{Escape}')

    expect(screen.getByRole('button', { name: 'Date & time: incomplete' })).toBeInTheDocument()
  })

  it('removing the filter empties all three fields', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    const panel = await openFilter(user, 'Date & time')
    fillWindow(panel, { date: '2026-11-02', start: '17:00', end: '09:00' })
    await user.click(screen.getByRole('button', { name: 'Remove Date & time filter' }))

    expect(screen.queryByText('Search paused.')).not.toBeInTheDocument()
    const reopened = await openFilter(user, 'Date & time')
    expect(within(reopened).getByLabelText('Date')).toHaveValue('')
    expect(within(reopened).getByLabelText('Start time')).toHaveValue('')
    expect(within(reopened).getByLabelText('End time')).toHaveValue('')
  })
})

describe('DT AC4 - the date and time combine with the other filters', () => {
  it('sends the date and time together with every other filter in one search', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    await user.type(screen.getByRole('textbox', { name: 'Search venues' }), 'marina')
    const attendance = await openFilter(user, 'Attendance')
    await user.type(
      within(attendance).getByRole('spinbutton', { name: 'Expected attendance' }),
      '120',
    )
    const layout = await openFilter(user, 'Layout')
    await user.click(await within(layout).findByRole('radio', { name: 'Theatre' }))
    const facilities = await openFilter(user, 'Facilities')
    await user.click(await within(facilities).findByRole('checkbox', { name: 'Stage' }))
    const accessibility = await openFilter(user, 'Accessibility')
    await user.click(await within(accessibility).findByRole('checkbox', { name: 'Hearing loop' }))
    const dates = await openFilter(user, 'Date & time')
    fillWindow(dates, { date: '2026-11-02', start: '09:00', end: '17:00' })

    await waitFor(() =>
      expect(lastSearch()).toEqual({
        q: 'marina',
        minCapacity: 120,
        layout: 'Theatre',
        facilities: ['Stage'],
        accessibility: ['Hearing loop'],
        start: new Date('2026-11-02T09:00').toISOString(),
        end: new Date('2026-11-02T17:00').toISOString(),
      }),
    )
  })

  it('shows only the venues the server returns for the combined search', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Changi Business Suite')

    mockList.mockResolvedValue([BALLROOM])
    const attendance = await openFilter(user, 'Attendance')
    await user.type(
      within(attendance).getByRole('spinbutton', { name: 'Expected attendance' }),
      '100',
    )
    const dates = await openFilter(user, 'Date & time')
    fillWindow(dates, { date: '2026-11-02', start: '09:00', end: '17:00' })

    await waitFor(() =>
      expect(screen.queryByText('Changi Business Suite')).not.toBeInTheDocument(),
    )
    expect(screen.getByText('Marina Grand Ballroom')).toBeInTheDocument()
    expect(screen.getByText('1 venue')).toBeInTheDocument()
  })
})

describe('VS AC3 - expected attendance', () => {
  it('searches for venues that hold at least that many people', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    const panel = await openFilter(user, 'Attendance')
    await user.type(within(panel).getByRole('spinbutton', { name: 'Expected attendance' }), '120')

    await waitFor(() => expect(lastSearch()).toEqual({ minCapacity: 120 }))
    expect(screen.getByRole('button', { name: 'Attendance: 120+' })).toBeInTheDocument()
  })

  it('ignores an attendance that is not a positive number', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Marina Grand Ballroom')

    const panel = await openFilter(user, 'Attendance')
    await user.type(within(panel).getByRole('spinbutton', { name: 'Expected attendance' }), '0')

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
