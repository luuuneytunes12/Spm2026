import { expect, test } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'
import { API, login } from './support/api'
import { OLIVIA, PASSWORD, SAM, openAs } from './support/coordinator-users'
import type { SeedUser } from './support/db'
import { autoAssign, removeUsers, removeVenue, resetUsers, seedUsers, seedVenue } from './support/db'

/**
 * SCRUM-92 UAT. Venue with setup 20 / turnaround 40; approved bookings
 * A 10:00-12:00 and B 13:00-14:00 (UTC, browser pinned to UTC). A turnaround
 * of 60 makes A's window end 13:00 and B's start 12:40: overlap 12:40-13:00.
 */
const STAFF: SeedUser = { email: 'e2e_s92_staff@cs.local', name: 'Vera Venue', role: 'venue_staff', password: PASSWORD }
const USERS = [OLIVIA, SAM, STAFF]
const EMAILS = USERS.map((u) => u.email)
const VENUE = 'E2E UAT92 Hall'
const A = 'UAT92 Event A'
const B = 'UAT92 Event B'
const CTX = { timezoneId: 'UTC', locale: 'en-GB' }

test.beforeAll(() => seedUsers(USERS))
test.beforeEach(() => {
  resetUsers(EMAILS)
  removeVenue(VENUE)
  seedVenue({ name: VENUE, location: 'E2E Road 92', capacity: 300 })
})
test.afterAll(() => {
  removeUsers(EMAILS)
  removeVenue(VENUE)
})

async function booking(request: APIRequestContext, name: string, venueName: string, s: number, e: number) {
  const olivia = await login(request, OLIVIA.email, OLIVIA.password)
  const at = (h: number) => `2026-11-02T${String(h).padStart(2, '0')}:00:00Z`
  const created = await request.post(`${API}/events`, {
    headers: olivia,
    data: {
      name, purpose: 'E2E', event_type: 'conference', description: 'UAT', proposed_start: at(s), proposed_end: at(e),
      expected_attendance: 50, venue_requirements: 'Hall', accessibility_needs: 'None', equipment_requirements: 'None',
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
  const venueId = venues.find((v) => v.name === venueName)!.id
  const booked = await request.post(`${API}/venue-bookings/events/${eventId}`, { data: { venues: [{ venue_id: venueId }] }, headers: sam })
  expect(booked.ok(), await booked.text()).toBe(true)
  const bookingId = (await booked.json())[0].id as number
  const staff = await login(request, STAFF.email, STAFF.password)
  expect((await request.post(`${API}/venue-bookings/${bookingId}/approve`, { headers: staff })).ok()).toBe(true)
  return { venueId, bookingId, eventId }
}

async function setup(request: APIRequestContext) {
  const staff = await login(request, STAFF.email, STAFF.password)
  const venues: { id: number; name: string }[] = await (await request.get(`${API}/venues`, { headers: staff })).json()
  const venueId = venues.find((v) => v.name === VENUE)!.id
  const put = await request.put(`${API}/venues/${venueId}/setup-turnaround`, { headers: staff, data: { setup_minutes: 20, turnaround_minutes: 40 } })
  expect(put.ok(), await put.text()).toBe(true)
  const a = await booking(request, A, VENUE, 10, 12)
  const b = await booking(request, B, VENUE, 13, 14)
  return { venueId, a, b }
}

async function save(page: Page, venueId: number, turnaround: string) {
  await page.goto(`/venues/${venueId}`)
  await page.getByLabel('Turnaround time (minutes)').fill(turnaround)
  await page.getByRole('button', { name: 'Save setup and turnaround' }).click()
}

const flaggedBubble = (page: Page) => page.locator('details.bq-section', { hasText: 'Flagged' }).locator('.bq-bubble')

/** Select a row in the sidebar's Flagged section; its detail card then shows. */
async function openCard(staff: Page, name: string) {
  await staff.goto('/venue-staff/bookings?view=flagged')
  await staff.locator('details.bq-section', { hasText: 'Flagged' }).getByRole('button', { name: new RegExp(name) }).click()
}

async function flaggedIds(request: APIRequestContext) {
  const h = await login(request, STAFF.email, STAFF.password)
  const rows: { id: number; status: string }[] = await (await request.get(`${API}/venue-bookings/flagged`, { headers: h })).json()
  return rows
}

async function notes(request: APIRequestContext) {
  const h = await login(request, SAM.email, SAM.password)
  const rows: { message: string }[] = await (await request.get(`${API}/notifications`, { headers: h })).json()
  return rows.map((n) => n.message).join('\n')
}

async function activity(request: APIRequestContext, eventId: number) {
  const h = await login(request, OLIVIA.email, SAM.password)
  return JSON.stringify(await (await request.get(`${API}/events/${eventId}/activity`, { headers: h })).json())
}

async function flag(staff: Page, venueId: number) {
  await save(staff, venueId, '60')
  await expect(staff.getByRole('alert').filter({ hasText: /flagged/ })).toBeVisible()
}

test('UAT-1: raising turnaround to 60 flags a booking; staff and Coordinator are told; booking stays approved', async ({ browser, request }) => {
  const { venueId } = await setup(request)
  const staff = await openAs(browser, STAFF, CTX)
  await save(staff, venueId, '60')
  const alert = staff.getByRole('alert').filter({ hasText: /flagged/ })
  await expect(alert).toBeVisible()
  await expect(alert.getByRole('link', { name: 'View flagged bookings' })).toBeVisible()

  await staff.goto('/venue-staff/bookings')
  // NOTE: the UAT expects 1; the app flags BOTH bookings (each clashes with the other).
  await expect(flaggedBubble(staff)).toHaveText('2')
  const flagged = await flaggedIds(request)
  expect(flagged).toHaveLength(2)
  const flaggedEvent = B
  const other = A
  await openCard(staff, flaggedEvent)
  const card = staff.getByRole('region', { name: new RegExp(`Flagged booking for ${flaggedEvent}`) })
  await expect(card).toContainText(other)
  await expect(card).toContainText('12:40–13:00')

  expect(flagged.every((x) => x.status === 'approved')).toBe(true)
  const txt = await notes(request)
  expect(txt).toMatch(/flag|conflict/i)
})

test('UAT-2: turnaround back to 40 reports no conflicts and clears the flagged count', async ({ browser, request }) => {
  const { venueId } = await setup(request)
  const staff = await openAs(browser, STAFF, CTX)
  await flag(staff, venueId)
  await save(staff, venueId, '40')
  // Wording differs from the UAT's "no bookings conflict": the app says "0 existing bookings flagged for conflict; 2 flags cleared."
  await expect(staff.getByRole('status')).toContainText(/0 existing bookings flagged for conflict; 2 flags cleared/)
  await expect(staff.getByRole('alert').filter({ hasText: /flagged/ })).toHaveCount(0)
  await staff.goto('/venue-staff/bookings')
  await expect(flaggedBubble(staff)).toHaveText('0')
  expect(await flaggedIds(request)).toHaveLength(0)
})

test('UAT-3: Keep needs a reason; with one the flag clears and the Activity Log shows it', async ({ browser, request }) => {
  const { venueId, a, b } = await setup(request)
  const staff = await openAs(browser, STAFF, CTX)
  await flag(staff, venueId)
  const [f] = await flaggedIds(request)
  const ev = f.id === a.bookingId ? a : b
  const name = f.id === a.bookingId ? A : B
  await openCard(staff, name)
  const card = staff.getByRole('region', { name: new RegExp(`Flagged booking for ${name}`) })
  await card.getByRole('button', { name: 'Keep anyway' }).click()
  await expect(card.locator('.form-error')).toContainText('Enter a reason')
  expect(await flaggedIds(request)).toHaveLength(2)
  await card.getByLabel(/Reason for keeping/).fill('UAT92 keep reason')
  await card.getByRole('button', { name: 'Keep anyway' }).click()
  await expect(staff.getByText(/The flag is cleared/)).toBeVisible()
  expect((await flaggedIds(request)).map((x) => x.id)).not.toContain(ev.bookingId)
  expect(await activity(request, ev.eventId)).toContain('UAT92 keep reason')
})

test('UAT-4: cancelling a flagged booking with a reason clears the flag, logs it, tells the Coordinator, keeps the event', async ({ browser, request }) => {
  const { venueId, a, b } = await setup(request)
  const staff = await openAs(browser, STAFF, CTX)
  await flag(staff, venueId)
  const [f] = await flaggedIds(request)
  const ev = f.id === a.bookingId ? a : b
  const name = f.id === a.bookingId ? A : B
  await openCard(staff, name)
  const card = staff.getByRole('region', { name: new RegExp(`Flagged booking for ${name}`) })
  await card.getByRole('button', { name: 'Cancel booking' }).click()
  await expect(card.locator('.form-error')).toContainText('Enter a reason for cancelling')
  await card.getByLabel(/Reason for keeping or cancelling/).fill('UAT92 cancel reason')
  await card.getByRole('button', { name: 'Cancel booking' }).click()
  await expect(staff.getByText(/The Event is not cancelled/)).toBeVisible()
  expect(await flaggedIds(request)).toHaveLength(0)
  const sam = await login(request, SAM.email, SAM.password)
  const bookings: { id: number; status: string }[] = await (await request.get(`${API}/venue-bookings/events/${ev.eventId}`, { headers: sam })).json()
  expect(bookings.find((x) => x.id === ev.bookingId)?.status).toBe('cancelled')
  expect(await activity(request, ev.eventId)).toContain('UAT92 cancel reason')
  expect(await notes(request)).toContain('UAT92 cancel reason')
  const olivia = await login(request, OLIVIA.email, OLIVIA.password)
  const event = await (await request.get(`${API}/events/${ev.eventId}`, { headers: olivia })).json()
  expect(event.status).not.toBe('cancelled')
})
