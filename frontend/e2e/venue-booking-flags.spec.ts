import { E2E_TEST_YEAR } from './support/dates'
import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'
import { API, login } from './support/api'
import { OLIVIA, PASSWORD, SAM, openAs } from './support/coordinator-users'
import type { SeedUser } from './support/db'
import { autoAssign, removeUsers, removeVenue, resetUsers, seedUsers, seedVenue } from './support/db'

/**
 * End-to-end coverage of SCRUM-92, "Flag Conflicting Bookings given Venue
 * Setup & Turnaround", plus its DoD accessibility checks (section 8). Needs
 * the backend: the re-check on PUT /venues/{id}/setup-turnaround,
 * GET /venue-bookings/flagged and POST /venue-bookings/{id}/keep-conflict.
 *
 * Two approved bookings are seeded back to back (12:00 ends as 12:00 starts),
 * so they do not conflict until a turnaround is saved.
 *
 *   TC-BF-1e -- AC1 + AC4, saving a turnaround flags both and the list shows the overlap
 *   TC-BF-2e -- AC3, a turnaround too short to overlap flags nothing
 *   TC-BF-3e -- AC2 + AC5, the Coordinator sees the flag; the booking is still approved
 *   TC-BF-4e -- AC6, Keep anyway needs a reason (beside the field), then clears the flag
 *   TC-BF-A1 -- DoD 8, axe: no serious/critical violations (light, dark)
 *   TC-BF-A2 -- DoD 8, keyboard: the reason field and Keep anyway are reachable
 */
const STAFF: SeedUser = { email: 'e2e_bf_staff@cs.local', name: 'Vera Venue', role: 'venue_staff', password: PASSWORD }
const USERS = [OLIVIA, SAM, STAFF]
const EMAILS = USERS.map((u) => u.email)
const VENUE = 'E2E Flag Hall'
const FIRST = 'E2E Morning Event'
const SECOND = 'E2E Afternoon Event'

test.beforeAll(() => seedUsers(USERS))
// Fresh users, venue and bookings per test, so one test's decisions cannot leak.
test.beforeEach(() => {
  resetUsers(EMAILS)
  removeVenue(VENUE)
  seedVenue({ name: VENUE, location: 'E2E Road 3', capacity: 300 })
})
test.afterAll(() => {
  removeUsers(EMAILS)
  removeVenue(VENUE)
})

/** An approved booking for an event at the given hours (UTC) on 2 November in the shared future test year. */
async function approvedBooking(request: APIRequestContext, name: string, startHour: number, endHour: number) {
  const olivia = await login(request, OLIVIA.email, OLIVIA.password)
  const hour = (h: number) => `${E2E_TEST_YEAR}-11-02T${String(h).padStart(2, '0')}:00:00Z`
  const created = await request.post(`${API}/events`, {
    headers: olivia,
    data: {
      name,
      purpose: 'E2E',
      event_type: 'conference',
      description: 'E2E flag test',
      proposed_start: hour(startHour),
      proposed_end: hour(endHour),
      expected_attendance: 50,
      venue_requirements: 'Hall',
      accessibility_needs: 'None',
      equipment_requirements: 'None',
      registration_enabled: true,
    },
  })
  expect(created.ok(), await created.text()).toBe(true)
  const eventId = (await created.json()).id as number
  expect((await request.post(`${API}/events/${eventId}/submit`, { headers: olivia })).ok()).toBe(true)
  autoAssign(eventId)
  const sam = await login(request, SAM.email, SAM.password)
  expect((await request.post(`${API}/events/${eventId}/approve`, { headers: sam })).ok()).toBe(true)
  const venues: { id: number; name: string }[] = await (await request.get(`${API}/venues`, { headers: sam })).json()
  const venueId = venues.find((v) => v.name === VENUE)!.id
  const booked = await request.post(`${API}/venue-bookings/events/${eventId}`, {
    data: { venues: [{ venue_id: venueId }] },
    headers: sam,
  })
  expect(booked.ok(), await booked.text()).toBe(true)
  const bookingId = (await booked.json())[0].id as number
  const staff = await login(request, STAFF.email, STAFF.password)
  expect((await request.post(`${API}/venue-bookings/${bookingId}/approve`, { headers: staff })).ok()).toBe(true)
  return { venueId, bookingId, eventId }
}

/** Two adjacent approved bookings (09-12 and 12-15) of one venue. */
async function adjacentPair(request: APIRequestContext) {
  const first = await approvedBooking(request, FIRST, 9, 12)
  const second = await approvedBooking(request, SECOND, 12, 15)
  return { venueId: first.venueId, firstId: first.bookingId, secondId: second.bookingId, secondEventId: second.eventId }
}

/** Save setup/turnaround through the venue page as Venue Staff. */
async function saveTurnaround(page: Page, venueId: number, setup: string, turnaround: string) {
  await page.goto(`/venues/${venueId}`)
  await page.getByLabel('Setup time (minutes)').fill(setup)
  await page.getByLabel('Turnaround time (minutes)').fill(turnaround)
  await page.getByRole('button', { name: 'Save setup and turnaround' }).click()
}

/** Open one flagged booking from the current calendar sidebar. */
async function selectFlagged(page: Page, eventName: string) {
  await page.locator('details.bq-section', { hasText: 'Flagged' }).getByRole('button', { name: new RegExp(eventName) }).click()
  return page.getByRole('region', { name: new RegExp(`Flagged booking for ${eventName}`) })
}

async function expectNoSeriousViolations(page: Page, label: string) {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(blocking.map((v) => `${v.impact} ${v.id}: ${v.help}`).join('\n'), label).toBe('')
}


test('TC-BF-1e: saving a turnaround that makes bookings overlap flags them and lists the overlap', async ({ browser, request }) => {
  const { venueId } = await adjacentPair(request)
  const staff = await openAs(browser, STAFF)
  await saveTurnaround(staff, venueId, '0', '30')
  await expect(staff.getByText(/2 existing bookings flagged for conflict/)).toBeVisible()
  await staff.getByRole('link', { name: 'View flagged bookings' }).click()
  await expect(staff.getByRole('heading', { level: 1, name: 'Booking requests' })).toBeVisible()
  const sidebar = staff.locator('details.bq-section', { hasText: 'Flagged' })
  await expect(sidebar.getByRole('button', { name: new RegExp(FIRST) })).toBeVisible()
  const card = await selectFlagged(staff, SECOND)
  await expect(card).toContainText('Conflict flagged - not counted as approved until resolved')
  await expect(card).toContainText(FIRST)
  await expect(card).toContainText(/overlap/i)
  await expect(await selectFlagged(staff, FIRST)).toBeVisible()
})

test('TC-BF-2e: a setup and turnaround that cause no overlap flag nothing', async ({ browser, request }) => {
  const { venueId } = await adjacentPair(request)
  const staff = await openAs(browser, STAFF)
  await saveTurnaround(staff, venueId, '0', '0')
  await expect(staff.getByText('No existing bookings conflict.')).toBeVisible()
  await expect(staff.getByRole('link', { name: 'View flagged bookings' })).toHaveCount(0)
  await staff.goto('/venue-staff/bookings?view=flagged')
  await expect(staff.locator('details.bq-section', { hasText: 'Flagged' }).locator('.bq-bubble')).toHaveText('0')
})

test('TC-BF-3e: the Coordinator sees the flag and the booking is not cancelled', async ({ browser, request }) => {
  const { venueId, secondId, secondEventId } = await adjacentPair(request)
  const staff = await openAs(browser, STAFF)
  await saveTurnaround(staff, venueId, '0', '30')
  await expect(staff.getByText(/flagged for conflict/)).toBeVisible()
  const sam = await openAs(browser, SAM)
  await sam.goto(`/coordinator/events/${secondEventId}`)
  const list = sam.getByRole('list', { name: 'Venue bookings for this event' })
  await expect(list).toContainText('Conflict flagged - not counted as approved until resolved')
  await expect(list).toContainText('Approved')
  const headers = await login(request, STAFF.email, STAFF.password)
  const flagged: { id: number; status: string }[] = await (await request.get(`${API}/venue-bookings/flagged`, { headers })).json()
  expect(flagged.find((b) => b.id === secondId)?.status).toBe('approved')
})

test('TC-BF-4e: Keep anyway needs a reason, then the booking leaves the flagged list', async ({ browser, request }) => {
  const { venueId } = await adjacentPair(request)
  const staff = await openAs(browser, STAFF)
  await saveTurnaround(staff, venueId, '0', '30')
  await expect(staff.getByText(/flagged for conflict/)).toBeVisible()
  await staff.goto('/venue-staff/bookings?view=flagged')
  const card = await selectFlagged(staff, SECOND)
  await card.getByRole('button', { name: 'Keep anyway' }).click()
  await expect(card.getByRole('alert').filter({ hasText: 'Enter a reason' })).toBeVisible()
  await expect(card.getByLabel(/Reason for keeping/)).toHaveAttribute('aria-invalid', 'true')
  await card.getByLabel(/Reason for keeping/).fill('Both organisers agreed to a shared changeover')
  await card.getByRole('button', { name: 'Keep anyway' }).click()
  await expect(staff.getByText(/The flag is cleared/)).toBeVisible()
  await staff.reload()
  await expect(staff.locator('details.bq-section', { hasText: 'Flagged' }).getByRole('button', { name: new RegExp(SECOND) })).toHaveCount(0)
})

test('TC-BF-6e: cancelling a flagged booking needs a reason, clears the flag and leaves the Event alone', async ({ browser, request }) => {
  const { venueId, secondId } = await adjacentPair(request)
  const staff = await openAs(browser, STAFF)
  await saveTurnaround(staff, venueId, '0', '30')
  await expect(staff.getByText(/flagged for conflict/)).toBeVisible()
  await staff.goto('/venue-staff/bookings?view=flagged')
  const card = await selectFlagged(staff, SECOND)
  await card.getByRole('button', { name: 'Cancel booking' }).click()
  await expect(card.getByRole('alert').filter({ hasText: 'Enter a reason for cancelling' })).toBeVisible()
  await card.getByLabel(/Reason for keeping or cancelling/).fill('The venue is needed for the earlier event')
  await card.getByRole('button', { name: 'Cancel booking' }).click()
  await expect(staff.getByText(/The Event is not cancelled/)).toBeVisible()
  await staff.reload()
  await expect(staff.locator('details.bq-section', { hasText: 'Flagged' }).locator('.bq-bubble')).toHaveText('0')
  const headers = await login(request, STAFF.email, STAFF.password)
  const flagged: { id: number }[] = await (await request.get(`${API}/venue-bookings/flagged`, { headers })).json()
  expect(flagged.find((b) => b.id === secondId)).toBeUndefined()
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`TC-BF-A1: flagged bookings page and save message pass axe (${colorScheme})`, async ({ browser, request }) => {
    const { venueId } = await adjacentPair(request)
    const staff = await openAs(browser, STAFF, { colorScheme })
    await saveTurnaround(staff, venueId, '0', '30')
    await expect(staff.getByText(/flagged for conflict/)).toBeVisible()
    await expectNoSeriousViolations(staff, `venue ${colorScheme}`)
    await staff.goto('/venue-staff/bookings?view=flagged')
    const card = await selectFlagged(staff, SECOND)
    await expect(card).toBeVisible()
    await expectNoSeriousViolations(staff, `flagged list ${colorScheme}`)
    await card.getByRole('button', { name: 'Keep anyway' }).click()
    await expect(card.getByRole('alert').filter({ hasText: 'Enter a reason' })).toBeVisible()
    await expectNoSeriousViolations(staff, `flagged list error ${colorScheme}`)
  })
}

test('TC-BF-A2: the reason field and Keep anyway are keyboard-reachable with visible focus', async ({ browser, request }) => {
  const { venueId } = await adjacentPair(request)
  const staff = await openAs(browser, STAFF)
  await saveTurnaround(staff, venueId, '0', '30')
  await expect(staff.getByText(/flagged for conflict/)).toBeVisible()
  await staff.goto('/venue-staff/bookings?view=flagged')
  await expect(await selectFlagged(staff, SECOND)).toBeVisible()
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
  expect([...focused].some((t) => t.startsWith('keep-reason-')), 'reason field not reachable by Tab').toBe(true)
  expect([...focused].some((t) => t.includes('Keep anyway')), 'Keep anyway not reachable by Tab').toBe(true)
})
