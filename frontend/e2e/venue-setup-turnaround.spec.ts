import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { openAs } from './support/coordinator-users'
import type { SeedUser } from './support/db'
import { removeUsers, removeVenue, resetUsers, seedUsers, seedVenue } from './support/db'

/**
 * End-to-end coverage of SCRUM-78, "Configure Venue Setup & Turnaround Time",
 * plus its DoD accessibility checks (section 8). Needs the backend endpoint
 * PUT /venues/{id}/setup-turnaround.
 *
 *   TC-VT-1e -- AC1, Venue Staff save whole minutes; they persist on reload
 *   TC-VT-2e -- AC2, empty / negative / non-whole blocked, reason beside the field
 *   TC-VT-3e -- AC3, a venue with none saved says "Not set - 0 minutes is used"
 *   TC-VT-4e -- AC4, a Coordinator sees both values but has no edit form
 *   TC-VT-A1 -- DoD 8, axe: no serious/critical violations (light, dark)
 *   TC-VT-A2 -- DoD 8, keyboard: both fields and Save reachable, visible focus
 */
const PASSWORD = 'e2e-venue-setup-123'
const STAFF: SeedUser = { email: 'e2e_vt_staff@cs.local', name: 'Vera Venue', role: 'venue_staff', password: PASSWORD }
const COORD: SeedUser = { email: 'e2e_vt_coord@cs.local', name: 'Cora Coordinator', role: 'coordinator', password: PASSWORD }
const EMAILS = [STAFF.email, COORD.email]
const VENUE = 'E2E Setup Hall'

test.beforeAll(() => seedUsers([STAFF, COORD]))
// A fresh venue per test, so what one test saves cannot leak into the next.
test.beforeEach(() => {
  resetUsers(EMAILS)
  removeVenue(VENUE)
  seedVenue({ name: VENUE, location: 'E2E Road 1', capacity: 100 })
})
test.afterAll(() => {
  removeUsers(EMAILS)
  removeVenue(VENUE)
})

async function openVenue(page: Page) {
  await page.goto('/venues')
  await page.getByRole('link', { name: `View details of ${VENUE}` }).click()
  await expect(page.getByRole('heading', { level: 1, name: VENUE })).toBeVisible()
}

async function expectNoSeriousViolations(page: Page, label: string) {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(blocking.map((v) => `${v.impact} ${v.id}: ${v.help}`).join('\n'), label).toBe('')
}

test('TC-VT-3e: a venue with nothing saved says so', async ({ browser }) => {
  const staff = await openAs(browser, STAFF)
  await openVenue(staff)
  await expect(staff.getByText('Not set - 0 minutes is used')).toHaveCount(2)
})

test('TC-VT-1e: Venue Staff save setup and turnaround, and they persist', async ({ browser }) => {
  const staff = await openAs(browser, STAFF)
  await openVenue(staff)
  await staff.getByLabel('Setup time (minutes)').fill('30')
  await staff.getByLabel('Turnaround time (minutes)').fill('45')
  await staff.getByRole('button', { name: 'Save setup and turnaround' }).click()
  await expect(staff.getByRole('status')).toContainText('saved')
  await staff.reload()
  await expect(staff.getByText('30 minutes', { exact: true })).toBeVisible()
  await expect(staff.getByText('45 minutes', { exact: true })).toBeVisible()
  await expect(staff.getByText(/Event start minus 30 minutes to the Event end plus 45 minutes/)).toBeVisible()
})

test('TC-VT-2e: empty, negative and non-whole values are refused with the reason beside the field', async ({ browser }) => {
  const staff = await openAs(browser, STAFF)
  await openVenue(staff)
  const save = staff.getByRole('button', { name: 'Save setup and turnaround' })
  await save.click()
  await expect(staff.getByRole('alert').filter({ hasText: 'Setup time is required' })).toBeVisible()
  await expect(staff.getByLabel('Setup time (minutes)')).toHaveAttribute('aria-invalid', 'true')
  await staff.getByLabel('Setup time (minutes)').fill('-5')
  await staff.getByLabel('Turnaround time (minutes)').fill('1.5')
  await save.click()
  await expect(staff.getByRole('alert').filter({ hasText: 'cannot be negative' })).toBeVisible()
  await expect(staff.getByRole('alert').filter({ hasText: 'whole number' })).toBeVisible()
  // Nothing was saved.
  await staff.reload()
  await expect(staff.getByLabel('Setup time (minutes)')).toHaveValue('')
})

test('TC-VT-4e: a Coordinator sees both values read-only', async ({ browser }) => {
  const coord = await openAs(browser, COORD)
  await openVenue(coord)
  await expect(coord.getByRole('heading', { name: 'Setup and turnaround' })).toBeVisible()
  await expect(coord.getByText('Setup time', { exact: true })).toBeVisible()
  await expect(coord.getByText('Turnaround time', { exact: true })).toBeVisible()
  await expect(coord.getByLabel('Setup time (minutes)')).toHaveCount(0)
  await expect(coord.getByRole('button', { name: 'Save setup and turnaround' })).toHaveCount(0)
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`TC-VT-A1: the venue page and its form errors pass axe (${colorScheme})`, async ({ browser }) => {
    const staff = await openAs(browser, STAFF, { colorScheme })
    await openVenue(staff)
    await expectNoSeriousViolations(staff, `venue ${colorScheme}`)
    await staff.getByRole('button', { name: 'Save setup and turnaround' }).click()
    await expect(staff.getByRole('alert').first()).toBeVisible()
    await expectNoSeriousViolations(staff, `errors ${colorScheme}`)
  })
}

test('TC-VT-A2: both fields and Save are keyboard-reachable with visible focus', async ({ browser }) => {
  const staff = await openAs(browser, STAFF)
  await openVenue(staff)
  const focused = new Set<string>()
  for (let i = 0; i < 30; i++) {
    await staff.keyboard.press('Tab')
    const info = await staff.evaluate(() => {
      const el = document.activeElement as HTMLElement | null
      if (!el || el === document.body) return null
      const s = getComputedStyle(el)
      const visible = (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none'
      return { id: el.id, text: (el.textContent ?? '').trim().slice(0, 40), tag: el.tagName, visible }
    })
    if (info) {
      expect(info.visible, `no visible focus on "${info.text || info.id}"`).toBe(true)
      focused.add(info.id || `${info.tag}:${info.text}`)
    }
  }
  expect(focused.has('setup-minutes'), 'setup field not reachable by Tab').toBe(true)
  expect(focused.has('turnaround-minutes'), 'turnaround field not reachable by Tab').toBe(true)
  expect([...focused].some((t) => t.includes('Save setup')), 'Save not reachable by Tab').toBe(true)
})
