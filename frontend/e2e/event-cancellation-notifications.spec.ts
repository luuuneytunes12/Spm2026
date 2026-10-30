import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'
import { API, login, submitEvent } from './support/api'
import { OLIVIA, PASSWORD, SAM, openAs } from './support/coordinator-users'
import { approvedEvent, arrange, as, notice, signedIn } from './support/arranged'
import {
  assignEventTo,
  registerAttendee,
  removeEquipment,
  removeUsers,
  removeVenue,
  resetUsers,
  seedEquipment,
  seedUsers,
  seedVenue,
} from './support/db'
import type { SeedUser } from './support/db'

/**
 * End-to-end coverage of "Notify everyone involved when an Event is
 * cancelled", plus its DoD accessibility checks: each role reads what
 * reached them, in the browser.
 *
 *   TC-EC-1e -- AC1, a registered Attendee reads the Event and the reason, and opens the Event
 *   TC-EC-2e -- AC5, the Organiser reads the reason
 *   TC-EC-3e -- AC6, a withdrawn Attendee is told nothing
 *   TC-EC-4e -- AC2, Venue Staff read the Event, Venue and date/time, and open the booking queue
 *   TC-EC-5e -- AC3, the Technical Support Staff who reserved it read the Event and the equipment
 *   TC-EC-6e -- AC4, the Safety Officer reads that it left the queue and why, and opens the queue
 *   TC-EC-7e -- AC5, the Coordinator reads the reason and opens the Event
 *   TC-EC-A1 -- DoD 8, axe on the Attendee's Notifications page (light, dark)
 *   TC-EC-A2 -- DoD 8, keyboard: the notice's "View event" link is reachable, visible focus
 */
const AMY: SeedUser = { email: 'e2e_ec_amy@cs.local', name: 'Amy Attendee', role: 'attendee', password: PASSWORD }
const BEN: SeedUser = { email: 'e2e_ec_ben@cs.local', name: 'Ben Attendee', role: 'attendee', password: PASSWORD }
const VERA: SeedUser = { email: 'e2e_ec_vera@cs.local', name: 'Vera Venue', role: 'venue_staff', password: PASSWORD }
const VIC: SeedUser = { email: 'e2e_ec_vic@cs.local', name: 'Vic Venue', role: 'venue_staff', password: PASSWORD }
const TESS: SeedUser = { email: 'e2e_ec_tess@cs.local', name: 'Tess Tech', role: 'tech_support', password: PASSWORD }
const SOFIA: SeedUser = { email: 'e2e_ec_sofia@cs.local', name: 'Sofia Safety', role: 'safety_officer', password: PASSWORD }
const USERS = [OLIVIA, SAM, AMY, BEN, VERA, VIC, TESS, SOFIA]
const EMAILS = USERS.map((u) => u.email)
const REASON = 'The client withdrew'
const VENUE = { name: 'EC Auditorium', location: 'Block C', capacity: 400 }
const ITEM = { name: 'EC Projector', category: 'EC Projection', total_quantity: 10 }

let equipmentId = 0

test.beforeAll(() => {
  seedUsers(USERS)
  seedVenue(VENUE)
  equipmentId = seedEquipment(ITEM)
})
test.beforeEach(() => resetUsers(EMAILS))
test.afterAll(() => {
  removeUsers(EMAILS)
  removeVenue(VENUE.name)
  removeEquipment(ITEM.name)
})

/** Olivia's Event, arranged (venue approved by Vera, projector reserved by
 *  Tess) and awaiting its Safety Check -- then cancelled by Sam. */
async function cancelledWhileAwaitingCheck(request: APIRequestContext, name: string) {
  const eventId = await approvedEvent(request, OLIVIA, SAM, name, equipmentId)
  await arrange(request, eventId, { coord: SAM, staff: VERA, tech: TESS }, VENUE.name, equipmentId)
  const samH = await as(request, SAM)
  expect((await request.post(`${API}/events/${eventId}/confirm`, { headers: samH })).ok()).toBe(true)
  const res = await request.post(`${API}/events/${eventId}/cancel`, { data: { reason: REASON }, headers: samH })
  expect(res.ok(), await res.text()).toBe(true)
  return eventId
}

/** Olivia's Event, coordinated by Sam, with Amy registered and Ben withdrawn -- then cancelled. */
async function cancelled(request: APIRequestContext, name: string) {
  const eventId = await submitEvent(request, await login(request, OLIVIA.email, OLIVIA.password), name, { assign: false })
  assignEventTo(eventId, SAM.email)
  registerAttendee(eventId, AMY.email)
  registerAttendee(eventId, BEN.email, 'withdrawn')
  const res = await request.post(`${API}/events/${eventId}/cancel`, {
    data: { reason: REASON },
    headers: await login(request, SAM.email, SAM.password),
  })
  expect(res.ok(), await res.text()).toBe(true)
  return eventId
}

async function expectNoSeriousViolations(page: Page, label: string) {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(blocking.map((v) => `${v.impact} ${v.id}: ${v.help}`).join('\n'), label).toBe('')
}

test('TC-EC-1e: a registered Attendee reads the Event and the reason, and opens the Event', async ({ browser, request }) => {
  const eventId = await cancelled(request, 'Cancelled Summit')
  const amy = await openAs(browser, AMY)
  await amy.goto('/notifications')
  const row = amy.locator('.notif-row').filter({
    hasText: `'Cancelled Summit', which you are registered for, has been cancelled. Reason: ${REASON}`,
  })
  await expect(row).toBeVisible()
  await row.getByRole('link', { name: 'View event' }).click()
  await expect(amy).toHaveURL(new RegExp(`/attendee/events/${eventId}$`))
})

test('TC-EC-2e: the Organiser reads the reason', async ({ browser, request }) => {
  await cancelled(request, 'Organiser Summit')
  const olivia = await openAs(browser, OLIVIA)
  await olivia.goto('/notifications')
  await expect(
    olivia.locator('.notif-row').filter({ hasText: `Your event 'Organiser Summit' has been cancelled. Reason: ${REASON}` }),
  ).toBeVisible()
})

test('TC-EC-3e: a withdrawn Attendee is told nothing', async ({ browser, request }) => {
  await cancelled(request, 'Withdrawn Summit')
  const ben = await openAs(browser, BEN)
  await ben.goto('/notifications')
  await expect(ben.getByText('Withdrawn Summit')).toHaveCount(0)
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`TC-EC-A1: the Attendee's Notifications page passes axe (${colorScheme})`, async ({ browser, request }) => {
    await cancelled(request, `Axe Summit ${colorScheme}`)
    const amy = await openAs(browser, AMY, { colorScheme })
    await amy.goto('/notifications')
    await expect(amy.getByText(new RegExp(`Axe Summit ${colorScheme}`))).toBeVisible()
    await expectNoSeriousViolations(amy, `notifications ${colorScheme}`)
  })
}

test('TC-EC-A2: the notice\'s View event link is keyboard-reachable with visible focus', async ({ browser, request }) => {
  const eventId = await cancelled(request, 'Keyboard Summit')
  const amy = await openAs(browser, AMY)
  await amy.goto('/notifications')
  const link = amy.locator('.notif-row').filter({ hasText: 'Keyboard Summit' }).getByRole('link', { name: 'View event' })
  await expect(link).toBeVisible()
  let reached = false
  for (let i = 0; i < 25 && !reached; i++) {
    await amy.keyboard.press('Tab')
    reached = await link.evaluate((el) => el === document.activeElement)
  }
  expect(reached, 'View event link not reachable by Tab').toBe(true)
  const visible = await link.evaluate((el) => {
    const s = getComputedStyle(el)
    return (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none'
  })
  expect(visible, 'no visible focus on View event').toBe(true)
  await amy.keyboard.press('Enter')
  await expect(amy).toHaveURL(new RegExp(`/attendee/events/${eventId}$`))
})

test('TC-EC-4e: Venue Staff read the Event, Venue and date/time, and open the booking queue', async ({ browser, request }) => {
  await cancelledWhileAwaitingCheck(request, 'Venue Summit')
  const vic = await openAs(browser, VIC)
  await vic.goto('/notifications')
  const row = notice(vic, "'Venue Summit' has been cancelled. Its booking of EC Auditorium")
  await expect(row).toContainText(/\(\d{1,2} \w{3} \d{4}, 09:00-17:00 UTC\) is no longer needed\./)
  await row.getByRole('link', { name: 'View event' }).click()
  await expect(vic).toHaveURL(/\/venue-staff\/bookings$/)
})

test('TC-EC-5e: the Technical Support Staff who reserved it read the Event and the equipment', async ({ browser, request }) => {
  await cancelledWhileAwaitingCheck(request, 'Equipment Summit')
  const tess = await openAs(browser, TESS)
  await tess.goto('/notifications')
  const row = notice(tess, "'Equipment Summit' has been cancelled.")
  await expect(row).toContainText(`Its reserved equipment is no longer needed: 2 x ${ITEM.name}.`)
  // A cancelled Event has no equipment record to open.
  await expect(row.getByRole('link', { name: 'View event' })).toHaveCount(0)
})

test('TC-EC-6e: the Safety Officer reads that it left the queue and why, and opens the queue', async ({ browser, request }) => {
  await cancelledWhileAwaitingCheck(request, 'Queue Summit')
  const sofia = await signedIn(browser, SOFIA)
  await sofia.goto('/notifications')
  const row = notice(sofia, 'has left your Safety Check queue because it was cancelled').filter({ hasText: 'Queue Summit' })
  await expect(row).toContainText(`Reason: ${REASON}`)
  await row.getByRole('link', { name: 'View event' }).click()
  await expect(sofia).toHaveURL(/\/safety-checks$/)
})

test('TC-EC-7e: the Coordinator reads the reason and opens the Event', async ({ browser, request }) => {
  const eventId = await cancelledWhileAwaitingCheck(request, 'Coordinated Summit')
  const sam = await openAs(browser, SAM)
  await sam.goto('/notifications')
  const row = notice(sam, `'Coordinated Summit', which you coordinate, has been cancelled. Reason: ${REASON}`)
  await row.getByRole('link', { name: 'View event' }).click()
  await expect(sam).toHaveURL(new RegExp(`/coordinator/events/${eventId}$`))
})
