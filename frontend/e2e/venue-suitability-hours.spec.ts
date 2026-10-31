import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'
import { call, login } from './support/api'
import { openAs } from './support/coordinator-users'
import { assignEventTo, removeUsers, removeVenue, resetUsers, seedUsers, seedVenue } from './support/db'
import type { SeedUser } from './support/db'

/**
 * End-to-end coverage of operating hours in the suitability check, on Postgres.
 * The rules are in backend/tests/test_venue_suitability_operating_hours.py.
 *
 *   TC-OH-1e -- AC1, AC2, AC4, one event, three venues, each checked directly
 *   TC-OH-3e -- AC3, only the booking at the venue that is closed is Not suitable
 *   TC-OH-A1 -- axe: no serious/critical violations (light, dark)
 *   TC-OH-A2 -- keyboard: the check can be run and read with visible focus
 */
const PASSWORD = 'e2e-hours-only-123'
const ORG: SeedUser = { email: 'e2e_oh_org@cs.local', name: 'Hours Organiser', role: 'organiser', password: PASSWORD }
const COORD: SeedUser = { email: 'e2e_oh_coord@cs.local', name: 'Hours Coordinator', role: 'coordinator', password: PASSWORD }
const EMAILS = [ORG.email, COORD.email]
const OPEN = 'E2E Hours Open Hall'
const CLOSED = 'E2E Hours Closed Hall'
const UNRECORDED = 'E2E Hours Unrecorded Hall'
const EVENT_NAME = 'E2E hours event'
// Everything but the hours is met, so only the hours decide each result.
const HALL = { location: 'Test campus', capacity: 300, facilities: ['Projector'], accessibility_features: ['Step-free access'] }

test.beforeAll(() => {
  seedUsers([ORG, COORD])
  seedVenue({ ...HALL, name: OPEN, operating_hours: 'Daily 00:00-24:00' })
  seedVenue({ ...HALL, name: CLOSED, operating_hours: 'Daily 02:00-03:00' })
  seedVenue({ ...HALL, name: UNRECORDED })
})
test.beforeEach(() => resetUsers(EMAILS))
test.afterEach(async ({ browser }) => {
  await Promise.all(browser.contexts().map((context) => context.close()))
})
test.afterAll(() => {
  removeUsers(EMAILS)
  for (const name of [OPEN, CLOSED, UNRECORDED]) removeVenue(name)
})

async function approvedEvent(request: APIRequestContext) {
  const org = await login(request, ORG.email, PASSWORD)
  const coord = await login(request, COORD.email, PASSWORD)
  const year = new Date().getFullYear() + 2
  const event = await call(request, 'post', '/events', org, {
    name: EVENT_NAME, purpose: 'Hours check', event_type: 'conference',
    proposed_start: `${year}-11-02T09:00:00Z`, proposed_end: `${year}-11-02T17:00:00Z`,
    expected_attendance: 120, venue_requirements: 'Projector',
    accessibility_needs: 'Step-free access', registration_enabled: false,
  }, 201)
  await call(request, 'post', `/events/${event.id}/submit`, org)
  assignEventTo(event.id, COORD.email)
  await call(request, 'post', `/events/${event.id}/approve`, coord)
  return event.id as number
}

async function checkVenue(page: Page, venue: string) {
  await page.goto('/venues')
  await page.getByRole('link', { name: venue }).first().click()
  const section = page.getByRole('region', { name: `Check ${venue} suitability` })
  await section.getByRole('combobox', { name: 'Event' }).selectOption({ label: EVENT_NAME })
  await section.getByRole('button', { name: 'Check suitability' }).click()
  return section
}

test('TC-OH-1e: AC1, AC2, AC4 a venue is checked against its own hours', async ({ browser, request }) => {
  await approvedEvent(request)
  const page = await openAs(browser, COORD)

  const open = await checkVenue(page, OPEN)
  await expect(open.getByRole('heading', { name: `Suitable for ${EVENT_NAME}` })).toBeVisible()
  await expect(open).toContainText('operating hours: Pass')

  const closed = await checkVenue(page, CLOSED)
  await expect(closed.getByRole('heading', { name: `Not suitable for ${EVENT_NAME}` })).toBeVisible()
  await expect(closed).toContainText('Outside operating hours')

  const unrecorded = await checkVenue(page, UNRECORDED)
  await expect(unrecorded.getByRole('heading', { name: `Suitable for ${EVENT_NAME}` })).toBeVisible()
  await expect(unrecorded).not.toContainText('operating hours')
})

test('TC-OH-3e: AC3 only the booking at the closed venue is Not suitable', async ({ browser, request }) => {
  const id = await approvedEvent(request)
  const page = await openAs(browser, COORD)
  await page.goto(`/coordinator/events/${id}`)
  for (const name of [OPEN, CLOSED]) await page.getByRole('checkbox', { name: new RegExp(name) }).check()
  await page.getByLabel(`Expected attendance for ${OPEN}`).fill('100')
  await page.getByLabel(`Expected attendance for ${CLOSED}`).fill('100')
  await page.getByRole('button', { name: 'Submit booking request' }).click()
  await expect(page.getByRole('list', { name: 'Venue bookings for this event' })).toContainText(CLOSED)

  await page.reload()
  const suitability = page.getByRole('region', { name: 'Event venue suitability' })
  await expect(suitability.getByText(`${OPEN}: Suitable`)).toBeVisible()
  await expect(suitability.getByText(`${CLOSED}: Not suitable`)).toBeVisible()

  await suitability.getByRole('button', { name: `Recheck ${CLOSED}` }).click()
  await expect(suitability.getByText(`${CLOSED}: Not suitable`)).toBeVisible()
  await expect(suitability.getByText(`${OPEN}: Suitable`)).toBeVisible()
  await expect(suitability).toContainText('Outside operating hours')
})

for (const scheme of ['light', 'dark'] as const) {
  test(`TC-OH-A1: no serious or critical axe violations (${scheme})`, async ({ browser, request }) => {
    await approvedEvent(request)
    const page = await openAs(browser, COORD)
    await page.emulateMedia({ colorScheme: scheme })
    const section = await checkVenue(page, CLOSED)
    await expect(section).toContainText('Outside operating hours')

    const results = await new AxeBuilder({ page }).include('section[aria-label^="Check "]').analyze()
    const serious = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
    expect(serious).toEqual([])
  })
}

test('TC-OH-A2: the check runs from the keyboard with visible focus', async ({ browser, request }) => {
  await approvedEvent(request)
  const page = await openAs(browser, COORD)
  await page.goto('/venues')
  await page.getByRole('link', { name: CLOSED }).first().click()
  const section = page.getByRole('region', { name: `Check ${CLOSED} suitability` })
  const select = section.getByRole('combobox', { name: 'Event' })
  await select.selectOption({ label: EVENT_NAME })
  await select.focus()

  await page.keyboard.press('Tab')
  const button = section.getByRole('button', { name: 'Check suitability' })
  await expect(button).toBeFocused()
  const outline = await button.evaluate((el) => getComputedStyle(el).outlineStyle)
  expect(outline).not.toBe('none')

  await page.keyboard.press('Enter')
  await expect(section).toContainText('Outside operating hours')
})
