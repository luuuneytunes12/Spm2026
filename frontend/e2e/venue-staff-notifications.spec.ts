import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'
import { API, login, submitEvent } from './support/api'
import { OLIVIA, PASSWORD, SAM, openAs } from './support/coordinator-users'
import { assignEventTo, removeUsers, removeVenue, resetUsers, seedUsers, seedVenue } from './support/db'
import type { SeedUser } from './support/db'

/**
 * End-to-end coverage of "Notify Venue Staff of booking requests and of
 * changes to Events approved at their venues", plus its DoD accessibility
 * checks. Every Venue Staff member manages every venue (confirmed with the
 * customer). Event changes and the Safety Check return are proven in the
 * backend suites; here Venue Staff read what reached them, in the browser.
 *
 *   TC-VN-1e -- AC1/AC2, a booking request names the Event, Venue and date/time; it opens the queue
 *   TC-VN-2e -- AC1, every Venue Staff member is told
 *   TC-VN-3e -- AC3, nobody outside Venue Staff is told
 *   TC-VN-A1 -- DoD 8, axe on the Venue Staff Notifications page (light, dark)
 *   TC-VN-A2 -- DoD 8, keyboard: the notice's "View event" link is reachable, visible focus
 */
const VERA: SeedUser = { email: 'e2e_vn_vera@cs.local', name: 'Vera Staff', role: 'venue_staff', password: PASSWORD }
const VIC: SeedUser = { email: 'e2e_vn_vic@cs.local', name: 'Vic Staff', role: 'venue_staff', password: PASSWORD }
const TESS: SeedUser = { email: 'e2e_vn_tess@cs.local', name: 'Tess Tech', role: 'tech_support', password: PASSWORD }
const USERS = [OLIVIA, SAM, VERA, VIC, TESS]
const EMAILS = USERS.map((u) => u.email)
const VENUE = 'E2E Notice Hall'

test.beforeAll(() => {
  seedUsers(USERS)
  seedVenue({ name: VENUE, location: '3 Test Road', capacity: 500 })
})
test.beforeEach(() => resetUsers(EMAILS))
test.afterAll(() => {
  removeUsers(EMAILS)
  removeVenue(VENUE)
})

/** An approved event of Sam's, with VENUE requested for it. */
async function requested(request: APIRequestContext, name: string) {
  const eventId = await submitEvent(request, await login(request, OLIVIA.email, OLIVIA.password), name, { assign: false })
  assignEventTo(eventId, SAM.email)
  const headers = await login(request, SAM.email, SAM.password)
  expect((await request.post(`${API}/events/${eventId}/approve`, { headers })).ok()).toBe(true)
  const venues: { id: number; name: string }[] = await (await request.get(`${API}/venues`, { headers })).json()
  const booked = await request.post(`${API}/venue-bookings/events/${eventId}`, {
    data: { venues: [{ venue_id: venues.find((v) => v.name === VENUE)!.id }] },
    headers,
  })
  expect(booked.ok(), await booked.text()).toBe(true)
}

const notice = (page: Page, event: string) =>
  page.locator('.notif-row').filter({ hasText: `New venue booking request for '${event}': ${VENUE}` })

async function expectNoSeriousViolations(page: Page, label: string) {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(blocking.map((v) => `${v.impact} ${v.id}: ${v.help}`).join('\n'), label).toBe('')
}

test('TC-VN-1e: a booking request names the Event, Venue and date/time, and opens the queue', async ({ browser, request }) => {
  await requested(request, 'Requested Summit')
  const vera = await openAs(browser, VERA)
  await vera.goto('/notifications')
  const row = notice(vera, 'Requested Summit')
  await expect(row).toBeVisible()
  await expect(row).toContainText(/\d{1,2} \w{3} \d{4}, \d{2}:\d{2}-\d{2}:\d{2} UTC/)
  await row.getByRole('link', { name: 'View event' }).click()
  await expect(vera).toHaveURL(/\/venue-staff\/bookings$/)
  await expect(vera.getByRole('region', { name: /Requested Summit/ })).toBeVisible()
})

test('TC-VN-2e: every Venue Staff member is told', async ({ browser, request }) => {
  await requested(request, 'Everyone Summit')
  const vic = await openAs(browser, VIC)
  await vic.goto('/notifications')
  await expect(notice(vic, 'Everyone Summit')).toBeVisible()
})

test('TC-VN-3e: nobody outside Venue Staff is told', async ({ browser, request }) => {
  await requested(request, 'Staff Only Summit')
  for (const who of [TESS, OLIVIA, SAM]) {
    const page = await openAs(browser, who)
    await page.goto('/notifications')
    await expect(page.getByText(/New venue booking request/)).toHaveCount(0)
  }
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`TC-VN-A1: the Venue Staff Notifications page passes axe (${colorScheme})`, async ({ browser, request }) => {
    await requested(request, `Axe Summit ${colorScheme}`)
    const vera = await openAs(browser, VERA, { colorScheme })
    await vera.goto('/notifications')
    await expect(notice(vera, `Axe Summit ${colorScheme}`)).toBeVisible()
    await expectNoSeriousViolations(vera, `notifications ${colorScheme}`)
  })
}

test('TC-VN-A2: the notice\'s View event link is keyboard-reachable with visible focus', async ({ browser, request }) => {
  await requested(request, 'Keyboard Summit')
  const vera = await openAs(browser, VERA)
  await vera.goto('/notifications')
  const link = notice(vera, 'Keyboard Summit').getByRole('link', { name: 'View event' })
  await expect(link).toBeVisible()
  let reached = false
  for (let i = 0; i < 25 && !reached; i++) {
    await vera.keyboard.press('Tab')
    reached = await link.evaluate((el) => el === document.activeElement)
  }
  expect(reached, 'View event link not reachable by Tab').toBe(true)
  const visible = await link.evaluate((el) => {
    const s = getComputedStyle(el)
    return (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none'
  })
  expect(visible, 'no visible focus on View event').toBe(true)
  await vera.keyboard.press('Enter')
  await expect(vera).toHaveURL(/\/venue-staff\/bookings$/)
})
