import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'
import { API, login, submitEvent } from './support/api'
import { OLIVIA, PASSWORD, SAM, openAs } from './support/coordinator-users'
import { assignEventTo, registerAttendee, removeUsers, resetUsers, seedUsers } from './support/db'
import type { SeedUser } from './support/db'

/**
 * End-to-end coverage of "Notify everyone involved when an Event is
 * cancelled", plus its DoD accessibility checks. Venue Staff, Technical
 * Support and the Safety Officer are proven in the backend suites; here the
 * Organiser and Attendees read what reached them, in the browser.
 *
 *   TC-EC-1e -- AC1, a registered Attendee reads the Event and the reason, and opens the Event
 *   TC-EC-2e -- AC5, the Organiser reads the reason
 *   TC-EC-3e -- AC6, a withdrawn Attendee is told nothing
 *   TC-EC-A1 -- DoD 8, axe on the Attendee's Notifications page (light, dark)
 *   TC-EC-A2 -- DoD 8, keyboard: the notice's "View event" link is reachable, visible focus
 */
const AMY: SeedUser = { email: 'e2e_ec_amy@cs.local', name: 'Amy Attendee', role: 'attendee', password: PASSWORD }
const BEN: SeedUser = { email: 'e2e_ec_ben@cs.local', name: 'Ben Attendee', role: 'attendee', password: PASSWORD }
const USERS = [OLIVIA, SAM, AMY, BEN]
const EMAILS = USERS.map((u) => u.email)
const REASON = 'The client withdrew'

test.beforeAll(() => seedUsers(USERS))
test.beforeEach(() => resetUsers(EMAILS))
test.afterAll(() => removeUsers(EMAILS))

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
