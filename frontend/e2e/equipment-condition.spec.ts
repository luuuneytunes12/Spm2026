import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { API, login } from './support/api'
import { openAs } from './support/coordinator-users'
import type { SeedUser } from './support/db'
import { removeEquipment, removeUsers, resetUsers, seedEquipment, seedUsers } from './support/db'

/**
 * End-to-end coverage of SCRUM-115, "Mark Equipment Damaged or Under
 * Maintenance", plus its DoD accessibility checks. The rules are in
 * backend/tests/test_equipment_condition.py and the Postgres integration test.
 *
 *   TC-EC-1e -- AC1 + AC2 + AC3, mark, availability excludes it, persists, return
 *   TC-EC-4e -- AC4, a bad quantity is refused and nothing changes
 *   TC-EC-5e -- other roles are denied by the API
 *   TC-EC-A1 -- axe: no serious/critical violations (light, dark)
 *   TC-EC-A2 -- keyboard: the form is reachable and usable, with visible focus
 */
const PASSWORD = 'e2e-condition-password-123'
const TECH: SeedUser = { email: 'e2e_ec_tech@cs.local', name: 'Tia Tech', role: 'tech_support', password: PASSWORD }
const ORG: SeedUser = { email: 'e2e_ec_org@cs.local', name: 'Olivia Organiser', role: 'organiser', password: PASSWORD }
const EMAILS = [TECH.email, ORG.email]
const ITEM = 'E2E Condition Projector'
let itemId = 0

test.beforeAll(() => seedUsers([TECH, ORG]))
test.beforeEach(() => {
  resetUsers(EMAILS)
  removeEquipment(ITEM)
  itemId = seedEquipment({ name: ITEM, category: 'E2E Condition', total_quantity: 10 })
})
test.afterAll(() => {
  removeEquipment(ITEM)
  removeUsers(EMAILS)
})

async function openForm(page: Page) {
  await page.goto('/equipment')
  await page.getByLabel('Search equipment').fill(ITEM)
  await page.getByRole('button', { name: `Update condition of ${ITEM}` }).click()
}

async function availableIn(request: Parameters<typeof login>[0]) {
  const query = new URLSearchParams({
    equipment_id: String(itemId),
    start: '2031-03-01T09:00:00Z',
    end: '2031-03-01T17:00:00Z',
  })
  const res = await request.get(`${API}/equipment-reservations/availability?${query}`, {
    headers: await login(request, TECH.email, TECH.password),
  })
  expect(res.ok(), await res.text()).toBe(true)
  return (await res.json()).available_quantity as number
}

test('TC-EC-1e: marked units leave availability, persist, and come back when returned', async ({ browser, request }) => {
  const tech = await openAs(browser, TECH)
  await openForm(tech)
  await tech.getByLabel('Condition', { exact: true }).selectOption({ label: 'Under maintenance' })
  await tech.getByLabel('Quantity').fill('3')
  await tech.getByRole('button', { name: 'Mark out of service' }).click()
  await expect(tech.getByText('7 of 10 available')).toBeVisible()
  await expect(tech.getByText('3 under maintenance')).toBeVisible()
  expect(await availableIn(request)).toBe(7)

  await tech.reload()
  await tech.getByLabel('Search equipment').fill(ITEM)
  await expect(tech.getByText('7 of 10 available')).toBeVisible()

  await tech.getByRole('button', { name: `Update condition of ${ITEM}` }).click()
  await tech.getByLabel('Condition', { exact: true }).selectOption({ label: 'Under maintenance' })
  await tech.getByLabel('Quantity').fill('2')
  await tech.getByRole('button', { name: 'Return to service' }).click()
  await expect(tech.getByText('9 of 10 available')).toBeVisible()
  expect(await availableIn(request)).toBe(9)
})

test('TC-EC-4e: a quantity above the total is refused and nothing changes', async ({ browser, request }) => {
  const tech = await openAs(browser, TECH)
  await openForm(tech)
  await tech.getByLabel('Quantity').fill('11')
  await tech.getByRole('button', { name: 'Mark out of service' }).click()
  await expect(tech.getByRole('alert')).toContainText('Only 10 of 10')
  await expect(tech.getByText('10 of 10 available')).toBeVisible()
  expect(await availableIn(request)).toBe(10)
})

test('TC-EC-5e: another role is denied by the API and nothing changes', async ({ request }) => {
  const res = await request.post(`${API}/equipment/${itemId}/out-of-service`, {
    headers: await login(request, ORG.email, ORG.password),
    data: { condition: 'damaged', quantity: 1 },
  })
  expect(res.status()).toBe(403)
  expect(await availableIn(request)).toBe(10)
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`TC-EC-A1: the open form passes axe (${colorScheme})`, async ({ browser }) => {
    const tech = await openAs(browser, TECH, { colorScheme })
    await openForm(tech)
    await tech.getByLabel('Quantity').fill('11')
    await tech.getByRole('button', { name: 'Mark out of service' }).click()
    await expect(tech.getByRole('alert')).toBeVisible()
    await tech.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
    const { violations } = await new AxeBuilder({ page: tech }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
    const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
    expect(blocking.map((v) => `${v.impact} ${v.id}: ${v.help}`).join('\n')).toBe('')
  })
}

test('TC-EC-A2: the form can be used by keyboard with visible focus', async ({ browser }) => {
  const tech = await openAs(browser, TECH)
  await tech.goto('/equipment')
  await tech.getByLabel('Search equipment').fill(ITEM)
  const open = tech.getByRole('button', { name: `Update condition of ${ITEM}` })
  await open.focus()
  await tech.keyboard.press('Enter')
  await expect(open).toHaveAttribute('aria-expanded', 'true')
  for (const name of ['Condition', 'Quantity']) {
    await tech.keyboard.press('Tab')
    await expect(tech.getByLabel(name, { exact: true })).toBeFocused()
  }
  await tech.keyboard.type('2')
  await tech.keyboard.press('Tab')
  const mark = tech.getByRole('button', { name: 'Mark out of service' })
  await expect(mark).toBeFocused()
  const visible = await mark.evaluate((el) => {
    const s = getComputedStyle(el)
    return (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none'
  })
  expect(visible, 'no visible focus').toBe(true)
  await tech.keyboard.press('Enter')
  await expect(tech.getByText('8 of 10 available')).toBeVisible()
})
