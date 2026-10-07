import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { SeedUser } from './support/db'
import { removeUsers, resetUsers, seedUsers } from './support/db'
import { openAs } from './support/coordinator-users'

/**
 * End-to-end coverage of the "Create Event Coordinator Lead Role" story,
 * plus its Definition of Done accessibility checks (section 8).
 *
 * Traceability (see docs/test-cases-coordinator-lead.md):
 *   TC-CL-2e -- AC2, a Lead logs in, edits their profile and logs out
 *   TC-CL-3e -- AC3, an existing role (Coordinator) still lands on its own page
 *   TC-CL-A1 -- DoD 8, axe finds no serious/critical violations (light, dark)
 *   TC-CL-A2 -- DoD 8, the Lead page is keyboard-navigable with visible focus
 */
const PASSWORD = 'e2e-lead-password-123'
const LEAD: SeedUser = { email: 'e2e_lead@cs.local', name: 'Lena Lead', role: 'event_coordinator_lead', password: PASSWORD }
const COORD: SeedUser = { email: 'e2e_lead_coord@cs.local', name: 'Colin Coordinator', role: 'coordinator', password: PASSWORD }
const EMAILS = [LEAD.email, COORD.email]

test.beforeAll(() => seedUsers([LEAD, COORD]))
test.beforeEach(() => resetUsers(EMAILS))
test.afterAll(() => removeUsers(EMAILS))

test('TC-CL-2e: a Lead lands on the Lead page, edits their profile and logs out', async ({ browser }) => {
  const page = await openAs(browser, LEAD)
  await expect(page).toHaveURL(/\/coordinator-lead$/)
  await expect(page.getByText('Event Coordinator Lead').first()).toBeVisible()

  const organisation = `E2E-${Date.now()} Lead Org`
  await page.goto('/profile')
  await page.getByLabel('Organisation').fill(organisation)
  await page.getByRole('button', { name: 'Save changes' }).click()
  await expect(page.getByText('Your profile has been updated.')).toBeVisible()
  await page.reload()
  await expect(page.getByLabel('Organisation')).toHaveValue(organisation)

  await page.getByRole('button', { name: /log ?out|sign ?out/i }).click()
  await expect(page).toHaveURL(/\/login/)
  await page.goto('/coordinator-lead')
  await expect(page).toHaveURL(/\/login/)
})

test('TC-CL-3e: a Coordinator still lands on the Coordinator page and cannot open the Lead page', async ({ browser }) => {
  const page = await openAs(browser, COORD)
  await expect(page).toHaveURL(/\/coordinator$/)
  await page.goto('/coordinator-lead')
  await expect(page).toHaveURL(/\/forbidden/)
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`TC-CL-A1: Lead landing page has no serious/critical axe violations (${colorScheme})`, async ({ browser }) => {
    const page = await openAs(browser, LEAD, { colorScheme })
    await page.goto('/coordinator-lead')
    await expect(page.getByRole('heading', { name: /Welcome back/ })).toBeVisible()
    await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
    const { violations } = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze()
    const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
    expect(blocking.map((v) => `${v.impact} ${v.id}: ${v.help}`).join('\n')).toBe('')
  })
}

test('TC-CL-A2: the Lead landing page is keyboard-navigable with visible focus', async ({ browser }) => {
  const page = await openAs(browser, LEAD)
  await page.goto('/coordinator-lead')
  await expect(page.getByRole('heading', { name: /Welcome back/ })).toBeVisible()
  await page.keyboard.press('Tab')
  const seen = new Set<string>()
  for (let i = 0; i < 12; i++) {
    const info = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null
      if (!el || el === document.body) return null
      const s = getComputedStyle(el)
      const visible = (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none'
      return { key: `${el.tagName}:${el.textContent?.trim().slice(0, 30)}`, visible }
    })
    if (info) {
      expect(info.visible, `no visible focus on ${info.key}`).toBe(true)
      seen.add(info.key)
    }
    await page.keyboard.press('Tab')
  }
  expect(seen.size).toBeGreaterThan(3)
})
