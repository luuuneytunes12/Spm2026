import { E2E_TEST_YEAR } from './support/dates'
import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { APIRequestContext, Browser, BrowserContextOptions, Page } from '@playwright/test'
import { call, login } from './support/api'
import { openAs } from './support/coordinator-users'
import type { SeedUser } from './support/db'
import {
  assignEventTo,
  removeEquipment,
  removeUsers,
  removeVenue,
  resetUsers,
  seedEquipment,
  seedUsers,
  seedVenue,
} from './support/db'

/**
 * Past Safety Checks, end to end on the Safety Officer's screens.
 *
 *   TC-PSC-AC1   -- AC1: the decided event is listed with its decision, reason and time
 *   TC-PSC-AC2/3 -- AC2, AC3: opening it is read-only and lists every decision
 *   TC-PSC-AC4   -- AC4: another role is refused, on screen and by direct request
 *   TC-PSC-A1    -- DoD 8, axe on the list and the event (light, dark)
 *   TC-PSC-A2    -- DoD 8, keyboard: the View links are reachable with visible focus
 *
 * The hand-offs between people (arranging, submitting, the decisions) go through
 * the API; the Safety Officer's screens are what is under test.
 */
const PASSWORD = 'e2e-psc-password-123'
const user = (key: string, name: string, role: SeedUser['role']): SeedUser => ({
  email: `e2e_psc_${key}@cs.local`,
  name,
  role,
  password: PASSWORD,
})
const ORG = user('org', 'Olivia Organiser', 'organiser')
const COORD = user('coord', 'Sam Tan', 'coordinator')
const STAFF = user('staff', 'Vera Venue', 'venue_staff')
const TECH = user('tech', 'Tess Tech', 'tech_support')
const SAFETY = user('safety', 'Sam Safety', 'safety_officer')
const USERS = [ORG, COORD, STAFF, TECH, SAFETY]
const EMAILS = USERS.map((u) => u.email)
const VENUE = { name: 'PSC Auditorium', location: 'Block C', capacity: 400 }
const ITEM = { name: 'PSC Projector', category: 'Projection', total_quantity: 10 }

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

type Headers = Record<string, string>

async function tokens(request: APIRequestContext) {
  const entries = await Promise.all(USERS.map(async (u) => [u.email, await login(request, u.email, u.password)] as const))
  return Object.fromEntries(entries) as Record<string, Headers>
}

/** An event with its venue approved and projector reserved, submitted for its safety check. */
async function awaitingEvent(request: APIRequestContext, h: Record<string, Headers>, name: string) {
  const created = await call(
    request,
    'post',
    '/events',
    h[ORG.email],
    {
      name,
      purpose: 'Annual partner briefing',
      event_type: 'conference',
      description: 'A full-day briefing.',
      proposed_start: `${E2E_TEST_YEAR}-11-02T09:00:00Z`,
      proposed_end: `${E2E_TEST_YEAR}-11-02T17:00:00Z`,
      expected_attendance: 120,
      venue_requirements: 'Main hall',
      accessibility_needs: 'Step-free access',
      registration_enabled: false,
      equipment_items: [{ equipment_id: equipmentId, quantity_requested: 2 }],
    },
    201,
  )
  const eventId = created.id as number
  await call(request, 'post', `/events/${eventId}/submit`, h[ORG.email])
  assignEventTo(eventId, COORD.email)
  await call(request, 'post', `/events/${eventId}/approve`, h[COORD.email])
  const venues = await call(request, 'get', '/venues', h[COORD.email])
  const venue = venues.find((v: { name: string }) => v.name === VENUE.name)
  const [booking] = await call(request, 'post', `/venue-bookings/events/${eventId}`, h[COORD.email], { venues: [{ venue_id: venue.id }] }, 201)
  await call(request, 'post', `/venue-bookings/${booking.id}/approve`, h[STAFF.email])
  await call(request, 'post', '/equipment-reservations', h[TECH.email], {
    event_id: eventId,
    equipment_id: equipmentId,
    placement_notes: 'Back of hall',
  })
  await call(request, 'post', `/events/${eventId}/confirm`, h[COORD.email])
  return eventId
}

/** Decided by the Safety Officer: rejected with a reason. */
async function rejectedEvent(request: APIRequestContext, h: Record<string, Headers>, name: string) {
  const eventId = await awaitingEvent(request, h, name)
  await call(request, 'post', `/safety-checks/${eventId}/reject`, h[SAFETY.email], { reason: 'Exits blocked by staging' })
  return eventId
}

async function expectNoSeriousViolations(page: Page, label: string) {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(blocking.map((v) => `${v.impact} ${v.id}: ${v.help}`).join('\n'), label).toBe('')
}

const HISTORY = '/safety-checks/history'

/** The Safety Officer signed in. They land on their Safety Checks queue, not a
 *  "Welcome back" landing page, so support/openAs does not fit them. */
async function openAsOfficer(browser: Browser, options: BrowserContextOptions = {}): Promise<Page> {
  const page = await (await browser.newContext(options)).newPage()
  await page.goto('/login')
  await page.getByLabel('Email').fill(SAFETY.email)
  await page.getByLabel('Password').fill(SAFETY.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Safety Checks' })).toBeVisible()
  return page
}

test('TC-PSC-AC1: the decided event is listed with its decision, reason and time', async ({ browser, request }) => {
  const h = await tokens(request)
  await rejectedEvent(request, h, 'PSC listed')
  const officer = await openAsOfficer(browser)

  await officer.goto('/safety-checks')
  await officer.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Past Safety Checks' }).click()
  await expect(officer).toHaveURL(HISTORY)
  const row = officer.locator('.request-list li', { hasText: 'PSC listed' })
  await expect(row).toContainText('Rejected')
  await expect(row).toContainText('Reason: Exits blocked by staging')
  await expect(row).toContainText(new RegExp(`Decided .*${new Date().getFullYear()}`))
  await expect(row).toContainText('Now: Planning Event')
})

test('TC-PSC-AC2/3: opening it is read-only and lists every decision with who made it', async ({ browser, request }) => {
  const h = await tokens(request)
  const eventId = await rejectedEvent(request, h, 'PSC read only')
  const officer = await openAsOfficer(browser)

  await officer.goto(HISTORY)
  await officer.getByRole('link', { name: 'View PSC read only' }).click()
  await expect(officer).toHaveURL(`/safety-checks/${eventId}`)
  await expect(officer.getByRole('heading', { level: 1, name: 'PSC read only' })).toBeVisible()
  await expect(officer.getByText('Step-free access')).toBeVisible()
  for (const name of ['Approve', 'Request changes', 'Reject']) {
    await expect(officer.getByRole('button', { name })).toHaveCount(0)
  }
  const decisions = officer.getByRole('list', { name: 'Safety Check decisions' })
  await expect(decisions.getByRole('listitem')).toHaveCount(1)
  await expect(decisions).toContainText('Rejected')
  await expect(decisions).toContainText('Sam Safety')
  await expect(decisions).toContainText('Reason: Exits blocked by staging')
})

test('TC-PSC-AC4: another role is refused the past safety checks, on screen and by direct request', async ({ browser, request }) => {
  const h = await tokens(request)
  const eventId = await rejectedEvent(request, h, 'PSC private')
  const organiser = await openAs(browser, ORG)

  await organiser.goto(HISTORY)
  await expect(organiser.getByRole('heading', { name: 'No Access' })).toBeVisible()
  await expect(organiser.getByText('Exits blocked by staging')).toHaveCount(0)
  await call(request, 'get', HISTORY, h[ORG.email], undefined, 403)
  await call(request, 'get', `/safety-checks/${eventId}`, h[COORD.email], undefined, 403)
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`TC-PSC-A1: the list and the event pass axe (${colorScheme})`, async ({ browser, request }) => {
    const h = await tokens(request)
    const eventId = await rejectedEvent(request, h, `PSC axe ${colorScheme}`)
    const officer = await openAsOfficer(browser, { colorScheme })
    await officer.goto(HISTORY)
    await expect(officer.getByText(`PSC axe ${colorScheme}`)).toBeVisible()
    await expectNoSeriousViolations(officer, `list ${colorScheme}`)
    await officer.goto(`/safety-checks/${eventId}`)
    await expect(officer.getByRole('list', { name: 'Safety Check decisions' })).toBeVisible()
    await expectNoSeriousViolations(officer, `event ${colorScheme}`)
  })
}

test('TC-PSC-A2: the View links are keyboard-reachable with visible focus', async ({ browser, request }) => {
  const h = await tokens(request)
  await rejectedEvent(request, h, 'PSC keyboard')
  const officer = await openAsOfficer(browser)
  await officer.goto(HISTORY)
  await expect(officer.getByText('PSC keyboard')).toBeVisible()
  const focused = new Set<string>()
  for (let i = 0; i < 16; i++) {
    await officer.keyboard.press('Tab')
    const info = await officer.evaluate(() => {
      const el = document.activeElement as HTMLElement | null
      if (!el || el === document.body) return null
      const s = getComputedStyle(el)
      const visible = (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none'
      return { label: el.getAttribute('aria-label') ?? (el.textContent ?? '').trim().slice(0, 40), visible }
    })
    if (info) {
      expect(info.visible, `no visible focus on "${info.label}"`).toBe(true)
      focused.add(info.label)
    }
  }
  expect(focused).toContain('View PSC keyboard')
  await officer.keyboard.press('Shift+Tab')
  for (let i = 0; i < 16; i++) {
    if ((await officer.evaluate(() => document.activeElement?.getAttribute('aria-label'))) === 'View PSC keyboard') break
    await officer.keyboard.press('Tab')
  }
  await officer.keyboard.press('Enter')
  await expect(officer.getByRole('heading', { level: 1, name: 'PSC keyboard' })).toBeVisible()
})
