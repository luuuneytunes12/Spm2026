import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { openAs } from './support/coordinator-users'
import type { SeedUser } from './support/db'
import { removeUsers, removeVenue, resetUsers, seedUsers, seedVenue } from './support/db'

/**
 * End-to-end coverage of SCRUM-108, "Manage Venue Catalogue Details", plus its
 * DoD accessibility checks (section 8).
 *
 *   TC-VC-1e -- AC1, Venue Staff add a venue; it appears in the catalogue
 *   TC-VC-2e -- AC2, an edit persists and shows on the venue page after reload
 *   TC-VC-3e -- AC3, missing detail / bad capacity / duplicate name refused with a reason
 *   TC-VC-5e -- AC5, the Activity Log shows the change, the name and the time
 *   TC-VC-A1 -- DoD 8, axe: no serious/critical violations (light, dark)
 *   TC-VC-A2 -- DoD 8, keyboard: every field and the button reachable, visible focus
 * AC4 (bookings kept and flagged) is covered by backend unit and Postgres tests.
 */
const PASSWORD = 'e2e-venue-catalogue-123'
const STAFF: SeedUser = { email: 'e2e_vc_staff@cs.local', name: 'Vera Venue', role: 'venue_staff', password: PASSWORD }
const NEW_VENUE = 'E2E Catalogue Hall'
const OTHER_VENUE = 'E2E Existing Hall'

test.beforeAll(() => seedUsers([STAFF]))
test.beforeEach(() => {
  resetUsers([STAFF.email])
  removeVenue(NEW_VENUE)
  removeVenue(OTHER_VENUE)
  seedVenue({ name: OTHER_VENUE, location: 'E2E Road 2', capacity: 80 })
})
test.afterAll(() => {
  removeVenue(NEW_VENUE)
  removeVenue(OTHER_VENUE)
  removeUsers([STAFF.email])
})

async function expectNoSeriousViolations(page: Page, label: string) {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(blocking.map((v) => `${v.impact} ${v.id}: ${v.help}`).join('\n'), label).toBe('')
}

async function fillNew(page: Page, name = NEW_VENUE) {
  await page.getByLabel('Name').fill(name)
  await page.getByLabel('Location').fill('1 Catalogue Way')
  await page.getByLabel('Capacity (people)').fill('150')
  await page.getByLabel('Facilities').fill('Projector, Stage')
  await page.getByLabel('Accessibility features').fill('Wheelchair access')
  await page.getByLabel('Supported room layouts').fill('Theatre, Classroom')
  await page.getByLabel('Operating hours').fill('Mon-Fri 08:00-22:00')
}

test('TC-VC-1e: Venue Staff add a venue and it appears in the catalogue', async ({ browser }) => {
  const staff = await openAs(browser, STAFF)
  await staff.goto('/venues')
  await staff.getByRole('link', { name: 'Add a venue' }).click()
  await fillNew(staff)
  await staff.getByRole('button', { name: 'Add venue' }).click()
  await expect(staff.getByRole('heading', { level: 1, name: NEW_VENUE })).toBeVisible()
  await expect(staff.getByText('150 people')).toBeVisible()
  await staff.goto('/venues')
  await expect(staff.getByRole('link', { name: `View details of ${NEW_VENUE}` })).toBeVisible()
})

test('TC-VC-2e: an edit persists and shows on the venue page', async ({ browser }) => {
  const staff = await openAs(browser, STAFF)
  await staff.goto('/venues')
  await staff.getByRole('link', { name: `View details of ${OTHER_VENUE}` }).click()
  await staff.getByRole('link', { name: 'Edit venue details' }).click()
  await staff.getByLabel('Capacity (people)').fill('120')
  await staff.getByLabel('Supported room layouts').fill('Banquet')
  await staff.getByLabel('Operating hours').fill('Daily 09:00-18:00')
  await staff.getByRole('button', { name: 'Save changes' }).click()
  await expect(staff.getByRole('status')).toContainText('saved')
  await staff.goto('/venues')
  await staff.getByRole('link', { name: `View details of ${OTHER_VENUE}` }).click()
  await expect(staff.getByText('120 people')).toBeVisible()
  await expect(staff.getByText('Banquet')).toBeVisible()
  await expect(staff.getByText('Daily 09:00-18:00')).toBeVisible()
})

test('TC-VC-3e: missing detail, bad capacity and a duplicate name are refused with a reason', async ({ browser }) => {
  const staff = await openAs(browser, STAFF)
  await staff.goto('/venue-staff/venues/new')
  await staff.getByLabel('Capacity (people)').fill('0')
  await staff.getByRole('button', { name: 'Add venue' }).click()
  await expect(staff.getByRole('alert').filter({ hasText: 'Name is required.' })).toBeVisible()
  await expect(staff.getByRole('alert').filter({ hasText: 'Capacity must be a whole number above zero.' })).toBeVisible()
  await expect(staff.getByLabel('Name')).toHaveAttribute('aria-invalid', 'true')
  await fillNew(staff, OTHER_VENUE.toLowerCase())
  await staff.getByRole('button', { name: 'Add venue' }).click()
  await expect(staff.getByRole('alert').filter({ hasText: 'already exists' })).toBeVisible()
  await staff.goto('/venues')
  await expect(staff.getByRole('link', { name: /View details of E2E Existing Hall/i })).toHaveCount(1)
})

test('TC-VC-5e: the Activity Log records the change, the name and the time', async ({ browser }) => {
  const staff = await openAs(browser, STAFF)
  await staff.goto('/venue-staff/venues/new')
  await fillNew(staff)
  await staff.getByRole('button', { name: 'Add venue' }).click()
  await expect(staff.getByRole('heading', { level: 1, name: NEW_VENUE })).toBeVisible()
  await staff.goto('/venue-staff/venues/new')
  const log = staff.getByRole('region', { name: 'Venue Activity Log' })
  await expect(log).toContainText(`Venue '${NEW_VENUE}' added.`)
  await expect(log).toContainText('By Vera Venue on')
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`TC-VC-A1: the add form passes axe (${colorScheme})`, async ({ browser }) => {
    const staff = await openAs(browser, STAFF, { colorScheme })
    await staff.goto('/venue-staff/venues/new')
    await expect(staff.getByRole('heading', { level: 1, name: 'Add a venue' })).toBeVisible()
    await expectNoSeriousViolations(staff, `add form ${colorScheme}`)
    await staff.getByRole('button', { name: 'Add venue' }).click()
    await expect(staff.getByText('Name is required.')).toBeVisible()
    await expectNoSeriousViolations(staff, `add form with errors ${colorScheme}`)
  })
}

test('TC-VC-A2: every field and the button are keyboard-reachable with visible focus', async ({ browser }) => {
  const staff = await openAs(browser, STAFF)
  await staff.goto('/venue-staff/venues/new')
  await expect(staff.getByRole('heading', { level: 1, name: 'Add a venue' })).toBeVisible()
  const focused = new Set<string>()
  for (let i = 0; i < 30; i++) {
    await staff.keyboard.press('Tab')
    const info = await staff.evaluate(() => {
      const el = document.activeElement as HTMLElement | null
      if (!el || el === document.body) return null
      const s = getComputedStyle(el)
      const visible = (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none'
      return { id: el.id || el.textContent?.trim() || el.tagName, visible }
    })
    if (info) {
      expect(info.visible, `focus indicator on ${info.id}`).toBe(true)
      focused.add(info.id)
    }
  }
  for (const id of ['name', 'location', 'capacity', 'facilities', 'accessibility_features', 'supported_layouts', 'operating_hours', 'Add venue']) {
    expect(focused, id).toContain(id)
  }
})
