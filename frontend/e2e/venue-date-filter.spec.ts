import { E2E_TEST_YEAR } from './support/dates'
import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Browser, Page } from '@playwright/test'
import { OLIVIA, SAM, openAs } from './support/coordinator-users'
import { removeUsers, removeVenueSchedule, seedUsers, seedVenueSchedule } from './support/db'
import type { ScheduledVenue } from './support/db'

/**
 * Filter Venues by Date and Time, end to end (real browser, real backend,
 * real Postgres). Each title names the acceptance criterion it proves; the
 * mapping is in docs/test-cases-venue-date-filter.md.
 *
 * Seven venues share the "E2E DT" prefix -- searched for by keyword so no
 * other venue in the database can change what is listed -- each with one
 * thing on 20 November in the shared future test year that should, or should not, take it out of a search
 * for 09:00-17:00. The browser runs in UTC so the times typed are the
 * times seeded, and in en-GB so the date chip reads "20 Nov, ..."
 */
const USERS = [OLIVIA, SAM]
const EMAILS = USERS.map((u) => u.email)

const DAY = `${E2E_TEST_YEAR}-11-20`
const at = (time: string) => `${DAY}T${time}:00+00:00`

const VENUES: ScheduledVenue[] = [
  { name: 'E2E DT Free Hall', capacity: 300 },
  { name: 'E2E DT Booked Hall', capacity: 300, bookings: [{ start: at('10:00'), end: at('12:00'), status: 'approved' }] },
  {
    name: 'E2E DT Held Hall',
    capacity: 300,
    bookings: [{ start: at('10:00'), end: at('12:00'), status: 'tentative_hold', expiresAt: '2099-01-01T00:00:00+00:00' }],
  },
  {
    // 07:00-08:00 does not touch 09:00-17:00 -- until the hour of reset and
    // the 30 minutes of setup are counted.
    name: 'E2E DT Padded Hall',
    capacity: 300,
    setupMinutes: 30,
    turnaroundMinutes: 60,
    bookings: [{ start: at('07:00'), end: at('08:00'), status: 'approved' }],
  },
  { name: 'E2E DT Closed Hall', capacity: 300, closures: [{ start: at('12:00'), end: at('13:00') }] },
  { name: 'E2E DT Rejected Hall', capacity: 50, bookings: [{ start: at('10:00'), end: at('12:00'), status: 'rejected' }] },
  {
    // A tentative hold whose expiry has passed: released, so it holds nothing.
    name: 'E2E DT Expired Hall',
    capacity: 200,
    bookings: [{ start: at('10:00'), end: at('12:00'), status: 'tentative_hold', expiresAt: '2020-01-01T00:00:00+00:00' }],
  },
]
const ALL = VENUES.map((v) => v.name)

test.beforeAll(() => {
  seedUsers(USERS)
  seedVenueSchedule(OLIVIA.email, VENUES)
})
test.afterAll(() => {
  removeVenueSchedule(ALL)
  removeUsers(EMAILS)
})

async function venuesPage(browser: Browser): Promise<Page> {
  const sam = await openAs(browser, SAM, { timezoneId: 'UTC', locale: 'en-GB' })
  await sam.goto('/venues')
  await sam.getByRole('textbox', { name: 'Search venues' }).fill('E2E DT')
  await expect(sam.getByText('7 venues')).toBeVisible()
  return sam
}

async function setWindow(page: Page, start: string, end: string, day = DAY) {
  const panel = page.getByRole('dialog', { name: 'Filter by date & time' })
  if (!(await panel.isVisible())) await page.getByRole('button', { name: /^(Date & time|\d+ Nov)/ }).click()
  await panel.getByLabel('Date').fill(day)
  await panel.getByLabel('Start time').fill(start)
  await panel.getByLabel('End time').fill(end)
  return panel
}

/** The venue names currently listed, in order. */
async function listed(page: Page): Promise<string[]> {
  return page.locator('.request-list .request-title').allTextContents()
}

test('DT AC1 + AC2: only venues free for the whole window, setup and turnaround included, are listed', async ({ browser }) => {
  const sam = await venuesPage(browser)

  await setWindow(sam, '09:00', '17:00')

  await expect(sam.getByText('3 venues')).toBeVisible()
  // AC2: a rejected booking or an expired hold leaves the venue listed.
  expect(await listed(sam)).toEqual(['E2E DT Expired Hall', 'E2E DT Free Hall', 'E2E DT Rejected Hall'])
  // AC1: approved, tentatively held, closed -- and padded by setup/turnaround.
  for (const gone of ['Booked', 'Held', 'Padded', 'Closed']) {
    await expect(sam.getByText(`E2E DT ${gone} Hall`, { exact: true })).toHaveCount(0)
  }

  // The next day nothing is booked, so every venue is back.
  await setWindow(sam, '09:00', '17:00', `${E2E_TEST_YEAR}-11-21`)
  await expect(sam.getByText('7 venues')).toBeVisible()
})

test('DT AC1: a window that clears the padding shows the padded venue again', async ({ browser }) => {
  const sam = await venuesPage(browser)

  // 08:00 + 60 min reset + 30 min setup = free from 09:30.
  await setWindow(sam, '09:30', '09:45')
  await expect(sam.getByText('E2E DT Padded Hall', { exact: true })).toBeVisible()
  await setWindow(sam, '09:29', '09:45')
  await expect(sam.getByText('E2E DT Padded Hall', { exact: true })).toHaveCount(0)
})

test('DT AC3: an end time earlier than the start time blocks the search and flags both fields', async ({ browser }) => {
  const sam = await venuesPage(browser)

  const panel = await setWindow(sam, '17:00', '09:00')

  await expect(panel.getByText('The end time must be after the start time.')).toBeVisible()
  await expect(panel.getByLabel('Start time')).toHaveAttribute('aria-invalid', 'true')
  await expect(panel.getByLabel('End time')).toHaveAttribute('aria-invalid', 'true')
  await expect(sam.getByText('Search paused.')).toBeVisible()
  await expect(sam.locator('.request-list')).toHaveCount(0)

  // Fixing it resumes the search.
  await panel.getByLabel('End time').fill('18:00')
  await expect(sam.getByText('Search paused.')).toHaveCount(0)
  await expect(panel.getByLabel('End time')).toHaveAttribute('aria-invalid', 'false')
  await expect(sam.locator('.request-list')).toBeVisible()
})

test('DT AC4: with expected attendance as well, only venues meeting both are listed', async ({ browser }) => {
  const sam = await venuesPage(browser)

  await setWindow(sam, '09:00', '17:00')
  await expect(sam.getByText('3 venues')).toBeVisible()
  await sam.keyboard.press('Escape')
  await sam.getByRole('button', { name: /^Attendance/ }).click()
  await sam.getByRole('spinbutton', { name: 'Expected attendance' }).fill('250')

  // Free Hall is free and big enough; Expired Hall (200) and Rejected Hall
  // (50) are free but too small; the big ones are all taken.
  await expect(sam.getByText('1 venue', { exact: true })).toBeVisible()
  expect(await listed(sam)).toEqual(['E2E DT Free Hall'])
})

test('DT negative: an Organiser cannot search venues by date', async ({ browser }) => {
  const olivia = await openAs(browser, OLIVIA)
  await olivia.goto('/venues')
  await expect(olivia).toHaveURL(/forbidden/)
})

test('DT accessibility: the date and time fields have no serious axe violations and work from the keyboard', async ({ browser }) => {
  const sam = await venuesPage(browser)
  const panel = await setWindow(sam, '17:00', '09:00') // the flagged state, the busiest one

  await sam.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page: sam })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze()
  // Include affected elements and axe's explanation so a CI failure can be fixed, not hidden.
  expect(violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => ({
    id: v.id,
    nodes: v.nodes.map((node) => ({ target: node.target, failureSummary: node.failureSummary })),
  }))).toEqual([])

  // Labelled, and reachable in order with Tab. A date input holds several
  // focus stops (day, month, year), so tab until the next field is reached.
  await panel.getByLabel('Date').focus()
  for (const next of ['Start time', 'End time']) {
    const field = panel.getByLabel(next)
    for (let i = 0; i < 6 && !(await field.evaluate((el) => el === document.activeElement)); i++) {
      await sam.keyboard.press('Tab')
    }
    await expect(field).toBeFocused()
  }
})
