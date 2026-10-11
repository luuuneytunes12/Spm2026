import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'
import { API, login, submitEvent } from './support/api'
import { OLIVIA, PASSWORD, SAM, openAs } from './support/coordinator-users'
import type { SeedUser } from './support/db'
import { removeUsers, removeVenue, resetUsers, seedUsers, seedVenue } from './support/db'

/**
 * End-to-end coverage of SCRUM-41, "Identify Booking Conflicts", plus its DoD
 * accessibility checks (section 8). Needs the backend: the `conflicts` field
 * on queue bookings, GET /venues/{id}/availability, and the 409 on approve.
 *
 * Both events share the seeded time (see support/api.ts), so the second
 * request for the venue overlaps the first once the first is approved.
 *
 *   TC-BC-1e -- AC1 + AC5, the conflict is flagged with the event and times
 *   TC-BC-2e -- AC1, approving a conflicting request is refused and it stays queued
 *   TC-BC-3e -- AC2, the availability list does not show the venue free
 *   TC-BC-4e -- AC4, a rejected booking is out of the queue and warns nothing
 *   TC-BC-A1 -- DoD 8, axe: no serious/critical violations (light, dark)
 *   TC-BC-A2 -- DoD 8, keyboard: the availability fields and button are reachable
 */
const STAFF: SeedUser = { email: 'e2e_bc_staff@cs.local', name: 'Vera Venue', role: 'venue_staff', password: PASSWORD }
const USERS = [OLIVIA, SAM, STAFF]
const EMAILS = USERS.map((u) => u.email)
const VENUE = 'E2E Conflict Hall'
const FIRST = 'E2E First Event'
const SECOND = 'E2E Second Event'

test.beforeAll(() => seedUsers(USERS))
// Fresh users, venue and events per test, so one test's decisions cannot leak.
test.beforeEach(() => {
  resetUsers(EMAILS)
  removeVenue(VENUE)
  seedVenue({ name: VENUE, location: 'E2E Road 2', capacity: 300 })
})
test.afterAll(() => {
  removeUsers(EMAILS)
  removeVenue(VENUE)
})

async function requestVenue(request: APIRequestContext, name: string) {
  const eventId = await submitEvent(request, await login(request, OLIVIA.email, OLIVIA.password), name)
  const headers = await login(request, SAM.email, SAM.password)
  expect((await request.post(`${API}/events/${eventId}/approve`, { headers })).ok()).toBe(true)
  const venues: { id: number; name: string }[] = await (await request.get(`${API}/venues`, { headers })).json()
  const venueId = venues.find((v) => v.name === VENUE)!.id
  const booked = await request.post(`${API}/venue-bookings/events/${eventId}`, {
    data: { venues: [{ venue_id: venueId }] },
    headers,
  })
  expect(booked.ok()).toBe(true)
  return { venueId, bookingId: (await booked.json())[0].id as number }
}

/** FIRST approved, SECOND pending and overlapping it. */
async function overlappingPair(request: APIRequestContext) {
  const first = await requestVenue(request, FIRST)
  const staff = await login(request, STAFF.email, STAFF.password)
  expect((await request.post(`${API}/venue-bookings/${first.bookingId}/approve`, { headers: staff })).ok()).toBe(true)
  const second = await requestVenue(request, SECOND)
  return { venueId: first.venueId, secondId: second.bookingId, firstId: first.bookingId }
}

async function expectNoSeriousViolations(page: Page, label: string) {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(blocking.map((v) => `${v.impact} ${v.id}: ${v.help}`).join('\n'), label).toBe('')
}

async function checkAvailability(page: Page) {
  await page.getByLabel('Availability from').fill('2026-11-02T00:00')
  await page.getByLabel('Availability until').fill('2026-11-03T00:00')
  await page.getByRole('button', { name: 'Check availability' }).click()
}

test('TC-BC-1e: the queue flags the overlap with the other event and its times', async ({ browser, request }) => {
  await overlappingPair(request)
  const staff = await openAs(browser, STAFF)
  await staff.goto('/venue-staff/bookings')
  const card = staff.getByRole('region', { name: new RegExp(SECOND) })
  const warning = card.getByRole('alert')
  await expect(warning).toContainText('Warning: booking conflict')
  await expect(warning).toContainText(FIRST)
  await expect(warning).toContainText('Overlap:')
})

test('TC-BC-2e: approving a conflicting request is refused and it stays in the queue', async ({ browser, request }) => {
  const { secondId } = await overlappingPair(request)
  const staff = await openAs(browser, STAFF)
  await staff.goto('/venue-staff/bookings')
  const card = staff.getByRole('region', { name: new RegExp(SECOND) })
  await card.getByRole('button', { name: 'Approve' }).click()
  await expect(card.getByRole('alert').filter({ hasText: FIRST }).last()).toBeVisible()
  await staff.reload()
  await expect(staff.getByRole('region', { name: new RegExp(SECOND) })).toBeVisible()
  const headers = await login(request, STAFF.email, STAFF.password)
  const queue: { id: number }[] = await (await request.get(`${API}/venue-bookings/queue`, { headers })).json()
  expect(queue.map((b) => b.id)).toContain(secondId)
})

test('TC-BC-3e: the availability list does not show the venue free during an approved booking', async ({ browser, request }) => {
  const { venueId } = await overlappingPair(request)
  const staff = await openAs(browser, STAFF)
  await staff.goto(`/venues/${venueId}`)
  await checkAvailability(staff)
  const results = staff.getByRole('region', { name: 'Availability results' })
  await expect(results).toContainText(`Booked for ${FIRST}`)
  await expect(results).not.toContainText('Available for the whole period')
  // A far-off window is free.
  await staff.getByLabel('Availability from').fill('2030-01-01T00:00')
  await staff.getByLabel('Availability until').fill('2030-01-02T00:00')
  await staff.getByRole('button', { name: 'Check availability' }).click()
  await expect(results).toContainText('Available for the whole period')
})

test('TC-BC-3e: an end before the start is refused beside the fields', async ({ browser, request }) => {
  const { venueId } = await overlappingPair(request)
  const staff = await openAs(browser, STAFF)
  await staff.goto(`/venues/${venueId}`)
  await staff.getByLabel('Availability from').fill('2026-11-03T00:00')
  await staff.getByLabel('Availability until').fill('2026-11-02T00:00')
  await staff.getByRole('button', { name: 'Check availability' }).click()
  await expect(staff.getByRole('alert').filter({ hasText: 'The end must be after the start.' })).toBeVisible()
  await expect(staff.getByLabel('Availability from')).toHaveAttribute('aria-invalid', 'true')
})

test('TC-BC-4e: a rejected booking leaves the queue and raises no warning', async ({ browser, request }) => {
  const { firstId, secondId } = await overlappingPair(request)
  const headers = await login(request, STAFF.email, STAFF.password)
  // A rejected booking never counts, so it no longer holds the venue.
  expect(secondId).not.toBe(firstId)
  const rejected = await request.post(`${API}/venue-bookings/${secondId}/reject`, {
    headers,
    data: { reason: 'E2E', suggested_alternative: '' },
  })
  expect(rejected.ok()).toBe(true)
  const staff = await openAs(browser, STAFF)
  await staff.goto('/venue-staff/bookings')
  await expect(staff.getByText('No pending booking requests.')).toBeVisible()
  await expect(staff.getByText('Warning: booking conflict')).toHaveCount(0)
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`TC-BC-A1: queue conflict warning and availability pass axe (${colorScheme})`, async ({ browser, request }) => {
    const { venueId } = await overlappingPair(request)
    const staff = await openAs(browser, STAFF, { colorScheme })
    await staff.goto('/venue-staff/bookings')
    await expect(staff.getByText('Warning: booking conflict')).toBeVisible()
    await expectNoSeriousViolations(staff, `queue ${colorScheme}`)
    await staff.goto(`/venues/${venueId}`)
    await checkAvailability(staff)
    await expect(staff.getByRole('region', { name: 'Availability results' })).toContainText(FIRST)
    await expectNoSeriousViolations(staff, `availability ${colorScheme}`)
  })
}

test('TC-BC-A2: the availability fields and button are keyboard-reachable with visible focus', async ({ browser, request }) => {
  const { venueId } = await overlappingPair(request)
  const staff = await openAs(browser, STAFF)
  await staff.goto(`/venues/${venueId}`)
  const focused = new Set<string>()
  for (let i = 0; i < 40; i++) {
    await staff.keyboard.press('Tab')
    // The focus ring fades in (box-shadow transition); read it once settled.
    await staff.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
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
  expect(focused.has('availability-start'), 'start field not reachable by Tab').toBe(true)
  expect(focused.has('availability-end'), 'end field not reachable by Tab').toBe(true)
  expect([...focused].some((t) => t.includes('Check availability')), 'button not reachable by Tab').toBe(true)
})
