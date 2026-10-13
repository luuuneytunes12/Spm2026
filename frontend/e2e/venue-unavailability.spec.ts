import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { openAs } from './support/coordinator-users'
import type { SeedUser } from './support/db'
import { removeUsers, removeVenue, resetUsers, seedUsers, seedVenue } from './support/db'

/**
 * End-to-end coverage of SCRUM-93, "Mark Venue Temporarily Unavailable",
 * plus its DoD accessibility checks (section 8).
 *
 *   TC-UN-1e -- AC1, a period with a reason is saved and survives a reload
 *   TC-UN-2e -- AC2, end before start is blocked and both date fields flagged
 *   TC-UN-3e -- AC3, the availability calendar shows the period with its reason
 *   TC-UN-6e -- AC6, end a period early / remove it: the venue is free again
 *   TC-UN-7e -- AC7, a Coordinator sees periods but has no form
 *   TC-UN-A1 -- DoD 8, axe: no serious/critical violations (light, dark)
 *   TC-UN-A2 -- DoD 8, keyboard: dates, reason and Save reachable, visible focus
 *
 * AC4 and AC5 (conflict flag in review, bookings identified, Events kept) are
 * covered against Postgres in backend/tests/integration/test_venue_unavailability_postgres.py.
 */
const PASSWORD = 'e2e-venue-unavail-123'
const STAFF: SeedUser = { email: 'e2e_un_staff@cs.local', name: 'Vera Venue', role: 'venue_staff', password: PASSWORD }
const COORD: SeedUser = { email: 'e2e_un_coord@cs.local', name: 'Cora Coordinator', role: 'coordinator', password: PASSWORD }
const EMAILS = [STAFF.email, COORD.email]
const VENUE = 'E2E Unavailable Hall'

test.beforeAll(() => seedUsers([STAFF, COORD]))
test.beforeEach(() => {
  resetUsers(EMAILS)
  removeVenue(VENUE)
  seedVenue({ name: VENUE, location: 'E2E Road 2', capacity: 100 })
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

/** A period tomorrow 08:00-18:00, in the browser's local time. */
async function fillPeriod(page: Page, reason = 'Renovation', start = '2031-03-04T08:00', end = '2031-03-04T18:00') {
  const form = page.getByRole('form', { name: 'Mark venue unavailable' })
  await form.getByLabel('Unavailable from').fill(start)
  await form.getByLabel('Unavailable until').fill(end)
  await form.getByLabel('Reason').selectOption(reason)
  await form.getByLabel('Details (optional)').fill('New floor')
  return form
}

test('TC-UN-1e: a period with a reason is saved and persists', async ({ browser }) => {
  const staff = await openAs(browser, STAFF)
  await openVenue(staff)
  const form = await fillPeriod(staff)
  await form.getByRole('button', { name: 'Save unavailable period' }).click()
  await expect(staff.getByRole('status')).toContainText('Unavailable period saved.')
  await staff.reload()
  const list = staff.getByRole('list', { name: 'Unavailable periods' })
  await expect(list).toContainText('Renovation')
  await expect(list).toContainText('New floor')
})

test('TC-UN-2e: end before start is blocked and both date fields are flagged', async ({ browser }) => {
  const staff = await openAs(browser, STAFF)
  await openVenue(staff)
  const form = await fillPeriod(staff, 'Other', '2031-03-04T18:00', '2031-03-04T08:00')
  await form.getByRole('button', { name: 'Save unavailable period' }).click()
  await expect(form.getByRole('alert')).toContainText('The end must be after the start.')
  await expect(form.getByLabel('Unavailable from')).toHaveAttribute('aria-invalid', 'true')
  await expect(form.getByLabel('Unavailable until')).toHaveAttribute('aria-invalid', 'true')
  await staff.reload()
  await expect(staff.getByText('No unavailable periods are recorded.')).toBeVisible()
})

test('TC-UN-3e: the availability calendar shows the period with its reason', async ({ browser }) => {
  const staff = await openAs(browser, STAFF)
  await openVenue(staff)
  const form = await fillPeriod(staff, 'Safety concern')
  await form.getByRole('button', { name: 'Save unavailable period' }).click()
  await expect(staff.getByRole('status')).toBeVisible()
  const check = staff.getByRole('form', { name: 'Check availability' })
  await check.getByLabel('Availability from').fill('2031-03-04T00:00')
  await check.getByLabel('Availability until').fill('2031-03-05T00:00')
  await check.getByRole('button', { name: 'Check availability' }).click()
  await expect(staff.getByRole('region', { name: 'Availability results' })).toContainText('Safety concern: New floor')
})

test('TC-UN-6e: removing a period makes the venue available again', async ({ browser }) => {
  const staff = await openAs(browser, STAFF)
  await openVenue(staff)
  const form = await fillPeriod(staff)
  await form.getByRole('button', { name: 'Save unavailable period' }).click()
  await expect(staff.getByRole('status')).toBeVisible()
  await staff.getByRole('button', { name: 'Remove' }).click()
  await expect(staff.getByText('No unavailable periods are recorded.')).toBeVisible()
  const check = staff.getByRole('form', { name: 'Check availability' })
  await check.getByLabel('Availability from').fill('2031-03-04T00:00')
  await check.getByLabel('Availability until').fill('2031-03-05T00:00')
  await check.getByRole('button', { name: 'Check availability' }).click()
  await expect(staff.getByRole('region', { name: 'Availability results' })).toContainText('Available for the whole period.')
})

test('TC-UN-7e: a Coordinator sees the period but has no form or buttons', async ({ browser }) => {
  const staff = await openAs(browser, STAFF)
  await openVenue(staff)
  const form = await fillPeriod(staff)
  await form.getByRole('button', { name: 'Save unavailable period' }).click()
  await expect(staff.getByRole('status')).toBeVisible()

  const coord = await openAs(browser, COORD)
  await openVenue(coord)
  await expect(coord.getByRole('list', { name: 'Unavailable periods' })).toContainText('Renovation')
  await expect(coord.getByRole('form', { name: 'Mark venue unavailable' })).toHaveCount(0)
  await expect(coord.getByRole('button', { name: 'Remove' })).toHaveCount(0)
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`TC-UN-A1: the venue page, a saved period and the form errors pass axe (${colorScheme})`, async ({ browser }) => {
    const staff = await openAs(browser, STAFF, { colorScheme })
    await openVenue(staff)
    await expectNoSeriousViolations(staff, `venue ${colorScheme}`)
    const form = await fillPeriod(staff)
    await form.getByRole('button', { name: 'Save unavailable period' }).click()
    await expect(staff.getByRole('status')).toBeVisible()
    await expectNoSeriousViolations(staff, `saved ${colorScheme}`)
    await staff.getByRole('button', { name: 'Save unavailable period' }).click()
    await expect(staff.getByRole('alert').first()).toBeVisible()
    await expectNoSeriousViolations(staff, `errors ${colorScheme}`)
  })
}

test('TC-UN-A2: dates, reason and Save are keyboard-reachable with visible focus', async ({ browser }) => {
  const staff = await openAs(browser, STAFF)
  await openVenue(staff)
  const focused = new Set<string>()
  for (let i = 0; i < 45; i++) {
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
  for (const id of ['unavailable-start', 'unavailable-end', 'unavailable-reason', 'unavailable-details']) {
    expect(focused.has(id), `${id} not reachable by Tab`).toBe(true)
  }
  expect([...focused].some((t) => t.includes('Save unavailable period')), 'Save not reachable by Tab').toBe(true)
})
