import { E2E_TEST_YEAR } from './support/dates'
import { expect, test } from '@playwright/test'
import type { Browser, Page } from '@playwright/test'
import { OLIVIA, SAM, openAs } from './support/coordinator-users'
import { removeUsers, removeVenueSchedule, seedUsers, seedVenueSchedule } from './support/db'
import type { ScheduledVenue } from './support/db'

/**
 * Venue search leaves out venues closed in the chosen time. The browser runs
 * in Singapore time, so the times typed read the same as the venues' hours.
 *
 *   TC-SH-1e -- AC1 + AC2 + AC3 + AC4, one search shows each rule
 *   TC-SH-2e -- AC1, a window running past closing leaves the venue out
 */
const USERS = [OLIVIA, SAM]
const EMAILS = USERS.map((u) => u.email)
const DAY = `${E2E_TEST_YEAR}-11-20`
const at = (time: string) => `${DAY}T${time}:00+08:00`
const HOURS = 'Daily 09:00-17:00'

const VENUES: ScheduledVenue[] = [
  { name: 'E2E SH Open Hall', capacity: 300, operatingHours: HOURS },
  { name: 'E2E SH Evening Hall', capacity: 300, operatingHours: 'Daily 18:00-22:00' },
  { name: 'E2E SH Unrecorded Hall', capacity: 300 },
  {
    name: 'E2E SH Booked Hall',
    capacity: 300,
    operatingHours: HOURS,
    bookings: [{ start: at('10:00'), end: at('12:00'), status: 'approved' }],
  },
  {
    name: 'E2E SH Held Hall',
    capacity: 300,
    operatingHours: HOURS,
    bookings: [{ start: at('10:00'), end: at('12:00'), status: 'tentative_hold', expiresAt: '2099-01-01T00:00:00+00:00' }],
  },
]

test.beforeAll(() => {
  seedUsers(USERS)
  seedVenueSchedule(OLIVIA.email, VENUES)
})
test.afterAll(() => {
  removeVenueSchedule(VENUES.map((v) => v.name))
  removeUsers(EMAILS)
})
test.afterEach(async ({ browser }) => {
  await Promise.all(browser.contexts().map((context) => context.close()))
})

async function search(browser: Browser, start: string, end: string): Promise<Page> {
  const sam = await openAs(browser, SAM, { timezoneId: 'Asia/Singapore', locale: 'en-GB' })
  await sam.goto('/venues')
  await sam.getByRole('textbox', { name: 'Search venues' }).fill('E2E SH')
  await expect(sam.getByText('5 venues')).toBeVisible()
  await sam.getByRole('button', { name: /^Date & time/ }).click()
  const panel = sam.getByRole('dialog', { name: 'Filter by date & time' })
  await panel.getByLabel('Date').fill(DAY)
  await panel.getByLabel('Start time').fill(start)
  await panel.getByLabel('End time').fill(end)
  return sam
}

test('TC-SH-1e: AC1 AC2 AC3 AC4 a window of exactly the opening hours', async ({ browser }) => {
  const sam = await search(browser, '09:00', '17:00')

  await expect(sam.getByText('2 venues')).toBeVisible()
  expect(await sam.locator('.request-list .request-title').allTextContents()).toEqual([
    'E2E SH Open Hall', // AC2
    'E2E SH Unrecorded Hall', // AC3
  ])
})

test('TC-SH-2e: AC1 a window running past closing leaves the venue out', async ({ browser }) => {
  const sam = await search(browser, '16:00', '17:30')

  await expect(sam.getByText('1 venue', { exact: true })).toBeVisible()
  expect(await sam.locator('.request-list .request-title').allTextContents()).toEqual([
    'E2E SH Unrecorded Hall',
  ])
})
