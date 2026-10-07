import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { API, login, submitEvent } from './support/api'
import { openAs } from './support/coordinator-users'
import type { SeedUser } from './support/db'
import { removeUsers, resetUsers, seedUsers } from './support/db'

/**
 * End-to-end coverage of "Notify the Event Coordinator Lead of a submitted
 * Event Request", plus its DoD accessibility checks.
 *
 *   TC-LN-1e -- AC1, a submitted request shows in the Lead's Notifications (name, Organiser, time)
 *   TC-LN-2e -- AC2, a saved draft sends the Lead nothing
 *   TC-LN-3e -- AC3, a submit blocked for empty fields sends the Lead nothing
 *   TC-LN-4e -- the Organiser and a Coordinator are not sent the Lead's notice
 *   TC-LN-A1 -- DoD 8, axe on the Notifications page (light, dark)
 *   TC-LN-A2 -- DoD 8, keyboard: the notice's "View event" link is reachable, visible focus
 */
const PASSWORD = 'e2e-lead-notice-123'
const LEAD: SeedUser = { email: 'e2e_ln_lead@cs.local', name: 'Lena Marie Lead', role: 'event_coordinator_lead', password: PASSWORD }
const ORG: SeedUser = { email: 'e2e_ln_org@cs.local', name: 'Olivia Organiser', role: 'organiser', password: PASSWORD }
const SAM: SeedUser = { email: 'e2e_ln_sam@cs.local', name: 'Sam Tan', role: 'coordinator', password: PASSWORD }
const EMAILS = [LEAD.email, ORG.email, SAM.email]

test.beforeAll(() => seedUsers([LEAD, ORG, SAM]))
test.beforeEach(() => resetUsers(EMAILS))
test.afterAll(() => removeUsers(EMAILS))

const orgHeaders = (request: Parameters<typeof login>[0]) => login(request, ORG.email, ORG.password)

async function expectNoSeriousViolations(page: Page, label: string) {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(blocking.map((v) => `${v.impact} ${v.id}: ${v.help}`).join('\n'), label).toBe('')
}

test('TC-LN-1e: a submitted request appears in the Lead\'s Notifications with name, Organiser and time', async ({ browser, request }) => {
  await submitEvent(request, await orgHeaders(request), 'Partner Summit', { assign: false })
  const lead = await openAs(browser, LEAD)
  await lead.goto('/notifications')
  const row = lead.locator('.notif-row').filter({ hasText: 'Partner Summit' })
  await expect(row).toBeVisible()
  await expect(row).toContainText('Olivia Organiser')
  await expect(row).toContainText(/submitted \d{2} \w{3} \d{4}, \d{2}:\d{2} UTC/)
  await expect(row.getByRole('link', { name: 'View event' })).toHaveAttribute('href', /\/coordinator-lead\/queue\/\d+/)
})

test('TC-LN-2e: saving a draft sends the Lead nothing', async ({ browser, request }) => {
  const headers = await orgHeaders(request)
  const created = await request.post(`${API}/events`, { data: { name: 'Only a draft' }, headers })
  expect(created.ok()).toBe(true)
  const lead = await openAs(browser, LEAD)
  await lead.goto('/notifications')
  await expect(lead.getByText('Only a draft')).toHaveCount(0)
})

test('TC-LN-3e: a submit blocked for empty mandatory fields sends the Lead nothing', async ({ browser, request }) => {
  const headers = await orgHeaders(request)
  const created = await request.post(`${API}/events`, { data: { name: 'Incomplete one' }, headers })
  const { id } = await created.json()
  const blocked = await request.post(`${API}/events/${id}/submit`, { headers })
  expect(blocked.status()).toBe(422)
  const lead = await openAs(browser, LEAD)
  await lead.goto('/notifications')
  await expect(lead.getByText('Incomplete one')).toHaveCount(0)
})

test('TC-LN-4e: the Organiser and a Coordinator are not sent the Lead\'s notice', async ({ browser, request }) => {
  await submitEvent(request, await orgHeaders(request), 'Private to the Lead', { assign: false })
  for (const who of [ORG, SAM]) {
    const page = await openAs(browser, who)
    await page.goto('/notifications')
    await expect(page.getByText('New Event Request')).toHaveCount(0)
  }
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`TC-LN-A1: the Lead's Notifications page passes axe (${colorScheme})`, async ({ browser, request }) => {
    await submitEvent(request, await orgHeaders(request), 'Axe notice', { assign: false })
    const lead = await openAs(browser, LEAD, { colorScheme })
    await lead.goto('/notifications')
    await expect(lead.getByText('Axe notice')).toBeVisible()
    await expectNoSeriousViolations(lead, `notifications ${colorScheme}`)
  })
}

test('TC-LN-A2: the notice\'s View event link is keyboard-reachable with visible focus', async ({ browser, request }) => {
  await submitEvent(request, await orgHeaders(request), 'Keyboard notice', { assign: false })
  const lead = await openAs(browser, LEAD)
  await lead.goto('/notifications')
  await expect(lead.getByText('Keyboard notice')).toBeVisible()
  const link = lead.locator('.notif-row').filter({ hasText: 'Keyboard notice' }).getByRole('link', { name: 'View event' })
  let reached = false
  for (let i = 0; i < 25 && !reached; i++) {
    await lead.keyboard.press('Tab')
    reached = await link.evaluate((el) => el === document.activeElement)
  }
  expect(reached, 'View event link not reachable by Tab').toBe(true)
  const visible = await link.evaluate((el) => {
    const s = getComputedStyle(el)
    return (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none'
  })
  expect(visible, 'no visible focus on View event').toBe(true)
  await lead.keyboard.press('Enter')
  await expect(lead).toHaveURL(/\/coordinator-lead\/queue\/\d+/)
})
