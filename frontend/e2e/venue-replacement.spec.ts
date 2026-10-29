import { E2E_TEST_YEAR } from './support/dates'
import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'
import { API, login } from './support/api'
import { OLIVIA, PASSWORD, SAM, openAs } from './support/coordinator-users'
import type { SeedUser } from './support/db'
import { autoAssign, removeUsers, removeVenue, resetUsers, seedUsers, seedVenue } from './support/db'

/**
 * End-to-end coverage of SCRUM-95, "Request Replacement Venue for Affected
 * Booking", plus its DoD accessibility checks. The API rules are in
 * backend/tests/test_venue_replacement.py and the Postgres integration test.
 *
 *   TC-VR-1e -- AC1, Find replacement opens Venue Search with the booking's date, time, needs
 *   TC-VR-2e -- AC2 + AC3, the request shows Venue Staff what it replaces; approval marks the original Replaced
 *   TC-VR-A1 -- axe: no serious/critical violations on Venue Search in replacement mode (light, dark)
 *   TC-VR-A2 -- keyboard: Find replacement and Request as replacement are reachable, focus visible
 */
const STAFF: SeedUser = { email: 'e2e_vr_staff@cs.local', name: 'Vera Venue', role: 'venue_staff', password: PASSWORD }
const USERS = [OLIVIA, SAM, STAFF]
const EMAILS = USERS.map((u) => u.email)
const OLD = 'E2E Closed Hall'
const NEW = 'E2E Spare Hall'
const EVENT = 'E2E Replacement Event'

test.beforeAll(() => seedUsers(USERS))
test.beforeEach(() => {
  resetUsers(EMAILS)
  removeVenue(OLD)
  removeVenue(NEW)
  seedVenue({ name: OLD, location: 'E2E Road 5', capacity: 300 })
  seedVenue({ name: NEW, location: 'E2E Road 6', capacity: 300 })
})
test.afterAll(() => {
  // Events first (their bookings reference the venues), then venues (an
  // unavailability period references the staff user), then the users.
  resetUsers(EMAILS)
  removeVenue(OLD)
  removeVenue(NEW)
  removeUsers(EMAILS)
})

/** An approved booking at OLD that Venue Staff then close for the event's time: flagged. */
async function flaggedBooking(request: APIRequestContext) {
  const olivia = await login(request, OLIVIA.email, OLIVIA.password)
  const created = await request.post(`${API}/events`, {
    headers: olivia,
    data: {
      name: EVENT,
      purpose: 'E2E',
      event_type: 'conference',
      description: 'E2E replacement test',
      proposed_start: `${E2E_TEST_YEAR}-11-02T09:00:00Z`,
      proposed_end: `${E2E_TEST_YEAR}-11-02T12:00:00Z`,
      expected_attendance: 50,
      venue_requirements: 'Hall',
      accessibility_needs: 'None',
      equipment_requirements: 'None',
      registration_enabled: true,
    },
  })
  expect(created.ok(), await created.text()).toBe(true)
  const eventId = (await created.json()).id as number
  expect((await request.post(`${API}/events/${eventId}/submit`, { headers: olivia })).ok()).toBe(true)
  autoAssign(eventId)
  const sam = await login(request, SAM.email, SAM.password)
  expect((await request.post(`${API}/events/${eventId}/approve`, { headers: sam })).ok()).toBe(true)
  const venues: { id: number; name: string }[] = await (await request.get(`${API}/venues`, { headers: sam })).json()
  const oldId = venues.find((v) => v.name === OLD)!.id
  const booked = await request.post(`${API}/venue-bookings/events/${eventId}`, {
    data: { venues: [{ venue_id: oldId }] },
    headers: sam,
  })
  expect(booked.ok(), await booked.text()).toBe(true)
  const bookingId = (await booked.json())[0].id as number
  const staff = await login(request, STAFF.email, STAFF.password)
  expect((await request.post(`${API}/venue-bookings/${bookingId}/approve`, { headers: staff })).ok()).toBe(true)
  const closed = await request.post(`${API}/venues/${oldId}/unavailability`, {
    headers: staff,
    data: { start_time: `${E2E_TEST_YEAR}-11-02T00:00:00Z`, end_time: `${E2E_TEST_YEAR}-11-03T00:00:00Z`, reason_category: 'Renovation' },
  })
  expect(closed.ok(), await closed.text()).toBe(true)
  return { eventId, bookingId }
}

async function expectNoSeriousViolations(page: Page, label: string) {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(blocking.map((v) => `${v.impact} ${v.id}: ${v.help}`).join('\n'), label).toBe('')
}

async function openReplacement(browser: Parameters<typeof openAs>[0], eventId: number) {
  const coord = await openAs(browser, SAM, { timezoneId: 'UTC' })
  await coord.goto(`/coordinator/events/${eventId}`)
  await coord.getByRole('link', { name: `Find replacement for ${OLD} booking` }).click()
  await expect(coord.getByText(/Finding a replacement for your booking at/)).toBeVisible()
  return coord
}

test('TC-VR-1e: Find replacement opens Venue Search with the booking date, time and needs filled in', async ({ browser, request }) => {
  const { eventId } = await flaggedBooking(request)
  const coord = await openReplacement(browser, eventId)
  // An applied chip shows its value; its "Remove ... filter" button proves it is applied.
  const chip = (label: string) =>
    coord
      .locator('.filter-chip-wrap')
      .filter({ has: coord.getByRole('button', { name: `Remove ${label} filter` }) })
      .locator('.filter-chip')
  await chip('Date & time').click()
  await expect(coord.getByLabel('Date', { exact: true })).toHaveValue(`${E2E_TEST_YEAR}-11-02`)
  await expect(coord.getByLabel('Start time')).toHaveValue('09:00')
  await expect(coord.getByLabel('End time')).toHaveValue('12:00')
  await chip('Attendance').click()
  await expect(coord.getByLabel('Expected attendance')).toHaveValue('50')
})

test('TC-VR-2e: the request shows Venue Staff what it replaces; approval marks the original Replaced', async ({ browser, request }) => {
  const { eventId } = await flaggedBooking(request)
  const coord = await openReplacement(browser, eventId)
  await coord.getByRole('button', { name: `Request as replacement: ${NEW}` }).click()
  await expect(coord.getByRole('status')).toContainText(`Replacement requested at ${NEW}`)

  const staff = await openAs(browser, STAFF)
  await staff.goto('/venue-staff/bookings')
  const card = staff.getByRole('region', { name: `Booking request for ${EVENT}` })
  await expect(card).toContainText('Replacement request')
  await expect(card).toContainText(OLD)
  await card.getByRole('button', { name: 'Approve' }).click()

  await coord.goto(`/coordinator/events/${eventId}`)
  await expect(coord.getByText('Replaced by another venue booking')).toBeVisible()
  await expect(coord.getByText('Replaced', { exact: true })).toBeVisible()
})

for (const scheme of ['light', 'dark'] as const) {
  test(`TC-VR-A1: no serious axe violations on replacement search (${scheme})`, async ({ browser, request }) => {
    const { eventId } = await flaggedBooking(request)
    const coord = await openReplacement(browser, eventId)
    await coord.emulateMedia({ colorScheme: scheme })
    await expect(coord.getByRole('button', { name: `Request as replacement: ${NEW}` })).toBeVisible()
    await expectNoSeriousViolations(coord, `replacement search ${scheme}`)
    await coord.goto(`/coordinator/events/${eventId}`)
    await expect(coord.getByRole('link', { name: `Find replacement for ${OLD} booking` })).toBeVisible()
    await expectNoSeriousViolations(coord, `event booking section ${scheme}`)
  })
}

test('TC-VR-A2: Find replacement and Request as replacement are reachable by keyboard with visible focus', async ({ browser, request }) => {
  const { eventId } = await flaggedBooking(request)
  const coord = await openAs(browser, SAM, { timezoneId: 'UTC' })
  await coord.goto(`/coordinator/events/${eventId}`)
  const link = coord.getByRole('link', { name: `Find replacement for ${OLD} booking` })
  await link.focus()
  const outline = await link.evaluate((el) => {
    const s = getComputedStyle(el)
    return `${s.outlineStyle} ${s.outlineWidth} ${s.boxShadow}`
  })
  expect(outline).not.toMatch(/^none 0px none$/)
  await coord.keyboard.press('Enter')
  const button = coord.getByRole('button', { name: `Request as replacement: ${NEW}` })
  await expect(button).toBeVisible()
  let reached = false
  for (let i = 0; i < 60 && !reached; i++) {
    await coord.keyboard.press('Tab')
    reached = await button.evaluate((el) => el === document.activeElement)
  }
  expect(reached, 'Request as replacement not reachable by Tab').toBe(true)
  await coord.keyboard.press('Enter')
  await expect(coord.getByRole('status')).toContainText(`Replacement requested at ${NEW}`)
})
