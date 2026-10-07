import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { API, login, submitEvent } from './support/api'
import { openAs } from './support/coordinator-users'
import type { SeedUser } from './support/db'
import { removeUsers, resetUsers, seedUsers } from './support/db'

/**
 * End-to-end coverage of "View Unassigned Event Request Queue as Coordinator
 * Lead", plus its Definition of Done accessibility checks (section 8).
 *
 * Traceability:
 *   TC-UQ-1e -- AC1, a submitted request waits in the queue, unassigned, even with a Coordinator available
 *   TC-UQ-2e -- AC2, a draft is not listed
 *   TC-UQ-3e -- AC3, each row shows the review fields, oldest first
 *   TC-UQ-4e -- AC4, opening one shows what the Organiser entered, read-only
 *   TC-UQ-5e -- AC5, other roles are denied (screen and direct request)
 *   TC-UQ-A1 -- DoD 8, axe: no serious/critical violations (light, dark)
 *   TC-UQ-A2 -- DoD 8, keyboard: the queue is reachable with visible focus
 */
const PASSWORD = 'e2e-queue-password-123'
const LEAD: SeedUser = { email: 'e2e_uq_lead@cs.local', name: 'Lena Marie Lead', role: 'event_coordinator_lead', password: PASSWORD }
const ORG: SeedUser = { email: 'e2e_uq_org@cs.local', name: 'Olivia Organiser', role: 'organiser', password: PASSWORD }
const COORD: SeedUser = { email: 'e2e_uq_coord@cs.local', name: 'Sam Tan', role: 'coordinator', password: PASSWORD }
const EMAILS = [LEAD.email, ORG.email, COORD.email]

// A Coordinator is in the pool on purpose: AC1 says submit must NOT assign them.
test.beforeAll(() => seedUsers([LEAD, ORG, COORD]))
test.beforeEach(() => resetUsers(EMAILS))
test.afterAll(() => removeUsers(EMAILS))

const QUEUE = '/coordinator-lead/queue'
const AWAITING = 'Submitted – Awaiting Coordinator'

const submit = async (request: Parameters<typeof login>[0], name: string) =>
  submitEvent(request, await login(request, ORG.email, ORG.password), name, { assign: false })

async function expectNoSeriousViolations(page: Page, label: string) {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(blocking.map((v) => `${v.impact} ${v.id}: ${v.help}`).join('\n'), label).toBe('')
}

test('TC-UQ-1e: a submitted request waits in the queue with no Coordinator, even with one available', async ({ browser, request }) => {
  await submit(request, 'Awaiting a coordinator')
  const lead = await openAs(browser, LEAD)
  await lead.goto(QUEUE)
  const row = lead.getByRole('listitem').filter({ hasText: 'Awaiting a coordinator' })
  await expect(row).toContainText(AWAITING)
  await expect(row).toContainText('not yet assigned')

  const sam = await openAs(browser, COORD)
  await sam.goto('/coordinator/events')
  await expect(sam.getByText('Nothing assigned to you yet.')).toBeVisible()
})

test('TC-UQ-2e: a draft is not listed', async ({ browser, request }) => {
  const headers = await login(request, ORG.email, ORG.password)
  await request.post(`${API}/events`, { data: { name: 'Only a draft' }, headers })
  await submit(request, 'Submitted one')
  const lead = await openAs(browser, LEAD)
  await lead.goto(QUEUE)
  await expect(lead.getByText('Submitted one')).toBeVisible()
  await expect(lead.getByText('Only a draft')).toHaveCount(0)
})

test('TC-UQ-3e: each row shows the review fields, oldest first', async ({ browser, request }) => {
  await submit(request, 'Submitted first')
  await submit(request, 'Submitted second')
  const lead = await openAs(browser, LEAD)
  await lead.goto(QUEUE)
  const rows = lead.locator('.request')
  await expect(rows).toHaveCount(2)
  await expect(rows.nth(0)).toContainText('Submitted first')
  await expect(rows.nth(1)).toContainText('Submitted second')
  await expect(rows.nth(0)).toContainText('conference')
  await expect(rows.nth(0)).toContainText('120 attendees')
  await expect(rows.nth(0)).toContainText('Organiser: Olivia Organiser')
  await expect(rows.nth(0)).toContainText(/Submitted [A-Z][a-z]{2} \d/)
  await expect(rows.nth(0)).toContainText(/(2 Nov|Nov 2),? 2026/)
})

test('TC-UQ-4e: opening a request shows what the Organiser entered, read-only', async ({ browser, request }) => {
  await submit(request, 'Review me')
  const lead = await openAs(browser, LEAD)
  await lead.goto(QUEUE)
  await lead.getByRole('link', { name: /Review/ }).click()
  await expect(lead).toHaveURL(/\/coordinator-lead\/queue\/\d+$/)
  await expect(lead.getByRole('heading', { level: 1, name: 'Review me' })).toBeVisible()
  for (const text of ['Annual partner briefing', 'A full-day briefing for our regional partners.', 'Main hall, stage, podium', 'Step-free access, hearing loop', '2 projectors, 4 radio mics', 'Olivia Organiser']) {
    await expect(lead.getByText(text)).toBeVisible()
  }
  for (const label of ['Purpose', 'Description', 'Type', 'Proposed date and time', 'Expected attendance', 'Venue requirements', 'Accessibility needs', 'Equipment requirements', 'Registration needed']) {
    await expect(lead.getByText(label, { exact: true })).toBeVisible()
  }
  // The Event's own fields are not editable: no text inputs. The only controls are
  // the assign panel's one select and one button (SCRUM-80).
  await expect(lead.locator('main input, main textarea')).toHaveCount(0)
  await expect(lead.locator('main select')).toHaveCount(1)
  await expect(lead.locator('main button')).toHaveText(['Assign'])
})

test('TC-UQ-5e: other roles are denied on screen and by direct request', async ({ browser, request }) => {
  const id = await submit(request, 'Secret request')
  for (const user of [COORD, ORG]) {
    const page = await openAs(browser, user)
    await page.goto(QUEUE)
    await expect(page).toHaveURL(/\/forbidden/)
    await expect(page.getByText('Secret request')).toHaveCount(0)
    await page.goto(`${QUEUE}/${id}`)
    await expect(page).toHaveURL(/\/forbidden/)
  }
  const coord = await login(request, COORD.email, COORD.password)
  for (const path of ['/lead/unassigned-queue', `/lead/unassigned-queue/${id}`]) {
    const res = await request.get(`${API}${path}`, { headers: coord })
    expect(res.status()).toBe(403)
    expect(await res.text()).not.toContain('Secret request')
  }
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`TC-UQ-A1: the queue and a request pass axe (${colorScheme})`, async ({ browser, request }) => {
    const id = await submit(request, 'Axe request')
    const lead = await openAs(browser, LEAD, { colorScheme })
    await lead.goto(QUEUE)
    await expect(lead.getByText('Axe request')).toBeVisible()
    await expectNoSeriousViolations(lead, `queue ${colorScheme}`)
    await lead.goto(`${QUEUE}/${id}`)
    await expect(lead.getByRole('heading', { level: 1, name: 'Axe request' })).toBeVisible()
    await expectNoSeriousViolations(lead, `request ${colorScheme}`)
  })
}

test('TC-UQ-A2: the queue is keyboard-navigable with visible focus', async ({ browser, request }) => {
  await submit(request, 'Keyboard request')
  const lead = await openAs(browser, LEAD)
  await lead.goto(QUEUE)
  await expect(lead.getByText('Keyboard request')).toBeVisible()
  const focused = new Set<string>()
  for (let i = 0; i < 14; i++) {
    await lead.keyboard.press('Tab')
    const info = await lead.evaluate(() => {
      const el = document.activeElement as HTMLElement | null
      if (!el || el === document.body) return null
      const s = getComputedStyle(el)
      const visible = (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none'
      return { text: el.textContent?.trim() ?? '', visible }
    })
    if (info) {
      expect(info.visible, `no visible focus on "${info.text}"`).toBe(true)
      focused.add(info.text)
    }
  }
  expect([...focused].some((t) => t.includes('Review')), 'Review link not reachable by Tab').toBe(true)
})
