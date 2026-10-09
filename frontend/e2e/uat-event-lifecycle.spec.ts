import { expect, test } from '@playwright/test'
import type { APIRequestContext, Browser, Page } from '@playwright/test'
import { API, call as send, login, userId } from './support/api'
import { openAs } from './support/coordinator-users'
import type { SeedUser } from './support/db'
import {
  removeEquipment,
  removeUsers,
  removeVenue,
  resetUsers,
  seedEquipment,
  seedUsers,
  seedVenue,
} from './support/db'

/**
 * User acceptance test of the event lifecycle, across every role.
 *
 * It follows the Definition of Done's statuses (dod.md 11a) the way the
 * people involved would:
 *
 *   Organiser submits  ->  Lead assigns (manually)  ->  Coordinator approves
 *   ->  Venue Staff approves the booking, Tech Support reserves the equipment
 *   ->  Coordinator submits for the Safety Check  ->  Safety Officer decides
 *   ->  registration opens  ->  an Attendee registers
 *
 * The API drives the hand-offs between people; the screens are what each
 * person is then asked to see, so what is asserted is what they would read.
 *
 *   UAT-1 -- the whole path, to a registered Attendee
 *   UAT-2 -- nothing is assigned until the Lead assigns it
 *   UAT-3 -- an event cannot go to the Safety Officer until it is arranged
 *   UAT-4 -- the Safety Officer can send an event back, and the Coordinator is told
 *   UAT-5 -- people only see what is theirs
 */
const PASSWORD = 'e2e-uat-password-123'
const user = (key: string, name: string, role: SeedUser['role']): SeedUser => ({
  email: `e2e_uat_${key}@cs.local`,
  name,
  role,
  password: PASSWORD,
})
const ORG = user('org', 'Olivia Organiser', 'organiser')
const OTHER_ORG = user('org2', 'Otto Other', 'organiser')
const LEAD = user('lead', 'Lena Lead', 'event_coordinator_lead')
const COORD = user('coord', 'Sam Tan', 'coordinator')
const OTHER_COORD = user('coord2', 'Priya Nair', 'coordinator')
const STAFF = user('staff', 'Vera Venue', 'venue_staff')
const TECH = user('tech', 'Tess Tech', 'tech_support')
const SAFETY = user('safety', 'Sam Safety', 'safety_officer')
const EMAILS = [ORG, OTHER_ORG, LEAD, COORD, OTHER_COORD, STAFF, TECH, SAFETY].map((u) => u.email)
const ATTENDEE_EMAIL = 'e2e_uat_attendee@cs.local'
const VENUE = { name: 'UAT Auditorium', location: 'Block A', capacity: 300 }
const ITEM = { name: 'UAT Projector', category: 'Projection', total_quantity: 10 }

let equipmentId = 0

// Each scenario makes many calls across several roles; against a remote
// database that is well past Playwright's default 30 s.
test.setTimeout(120_000)

test.beforeAll(() => {
  seedUsers([ORG, OTHER_ORG, LEAD, COORD, OTHER_COORD, STAFF, TECH, SAFETY])
  seedVenue(VENUE)
  equipmentId = seedEquipment(ITEM)
})
test.beforeEach(() => resetUsers([...EMAILS, ATTENDEE_EMAIL]))
test.afterAll(() => {
  removeUsers([...EMAILS, ATTENDEE_EMAIL])
  removeVenue(VENUE.name)
  removeEquipment(ITEM.name)
})

type Headers = Record<string, string>

async function tokens(request: APIRequestContext) {
  const entries = await Promise.all(
    [ORG, OTHER_ORG, LEAD, COORD, OTHER_COORD, STAFF, TECH, SAFETY].map(
      async (u) => [u.email, await login(request, u.email, u.password)] as const,
    ),
  )
  return Object.fromEntries(entries) as Record<string, Headers>
}

const REQUEST = {
  name: 'UAT Partner Conference',
  purpose: 'Annual partner briefing',
  event_type: 'conference',
  description: 'A full-day briefing.',
  proposed_start: '2026-11-02T09:00:00Z',
  proposed_end: '2026-11-02T17:00:00Z',
  expected_attendance: 120,
  venue_requirements: 'Main hall',
  accessibility_needs: 'Step-free access',
  registration_enabled: false,
}

/** The Organiser's request, submitted -- waiting in the Lead's queue. */
async function submitRequest(request: APIRequestContext, h: Record<string, Headers>, name = REQUEST.name) {
  const created = await send(
    request,
    'post',
    '/events',
    h[ORG.email],
    { ...REQUEST, name, equipment_items: [{ equipment_id: equipmentId, quantity_requested: 2 }] },
    201,
  )
  await send(request, 'post', `/events/${created.id}/submit`, h[ORG.email])
  return created.id as number
}

/** The Lead hands it to `coordinator`; the Coordinator approves it. */
async function assignAndApprove(
  request: APIRequestContext,
  h: Record<string, Headers>,
  eventId: number,
  coordinator: SeedUser = COORD,
) {
  const coordinatorId = await userId(request, h[coordinator.email])
  await send(request, 'post', `/lead/unassigned-queue/${eventId}/assign`, h[LEAD.email], { coordinator_id: coordinatorId })
  await send(request, 'post', `/events/${eventId}/approve`, h[coordinator.email])
}

/** Venue approved and equipment reserved, as Venue Staff and Tech Support would. */
async function arrange(request: APIRequestContext, h: Record<string, Headers>, eventId: number) {
  const venues = await send(request, 'get', '/venues', h[COORD.email])
  const venue = venues.find((v: { name: string }) => v.name === VENUE.name)
  const booking: { id: number }[] = await send(request, 'post', `/venue-bookings/events/${eventId}`, h[COORD.email], { venues: [{ venue_id: venue.id }] }, 201)
  await send(request, 'post', `/venue-bookings/${booking[0].id}/approve`, h[STAFF.email])
  await send(request, 'post', '/equipment-reservations', h[TECH.email], {
    event_id: eventId,
    equipment_id: equipmentId,
    placement_notes: 'Back of hall',
  })
  return booking[0].id as number
}

const statusOf = async (request: APIRequestContext, h: Record<string, Headers>, eventId: number) =>
  (await send(request, 'get', `/events/${eventId}`, h[ORG.email])).status

/** The Safety Officer's home is the Safety Checks list itself, with no welcome
 *  page, so `openAs` (which waits for one) does not fit. */
async function openAsSafetyOfficer(browser: Browser): Promise<Page> {
  const page = await (await browser.newContext()).newPage()
  await page.goto('/login')
  await page.getByLabel('Email').fill(SAFETY.email)
  await page.getByLabel('Password').fill(SAFETY.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/safety-checks$/)
  return page
}

const tile = (page: Page, name: RegExp) => page.locator('.tile-grid').getByRole('link', { name })

test('UAT-1: an event goes from request to a registered Attendee, and each person sees it', async ({ browser, request }) => {
  const h = await tokens(request)
  const eventId = await submitRequest(request, h)

  await test.step('Organiser: the request is submitted and waiting for a Coordinator', async () => {
    expect(await statusOf(request, h, eventId)).toBe('submitted_awaiting_coordinator')
    const page = await openAs(browser, ORG)
    await expect(tile(page, /Submitted Requests/).locator('.tile-count')).toHaveText('1')
    await page.goto('/organiser/events?tab=submitted')
    await expect(page.getByText(REQUEST.name)).toBeVisible()
    await expect(page.getByText('Submitted – Awaiting Coordinator')).toBeVisible()
  })

  await test.step('Lead: sees it in the queue, then assigns it by hand', async () => {
    const page = await openAs(browser, LEAD)
    await expect(tile(page, /Unassigned Requests/).locator('.tile-count')).toHaveText('1')
    const coordinatorId = await userId(request, h[COORD.email])
    await send(request, 'post', `/lead/unassigned-queue/${eventId}/assign`, h[LEAD.email], { coordinator_id: coordinatorId })
    expect(await statusOf(request, h, eventId)).toBe('under_review')
    await page.goto('/coordinator-lead')
    await expect(tile(page, /Unassigned Requests/).locator('.tile-count')).toHaveCount(0)
  })

  await test.step('Coordinator: sees one assigned event and approves it', async () => {
    const page = await openAs(browser, COORD)
    await expect(tile(page, /My Assigned Events/).locator('.tile-count')).toHaveText('1')
    await send(request, 'post', `/events/${eventId}/approve`, h[COORD.email])
    expect(await statusOf(request, h, eventId)).toBe('event_approved')
  })

  await test.step('Venue Staff and Tech Support arrange the venue and equipment', async () => {
    await arrange(request, h, eventId)
  })

  await test.step('Coordinator: sends it to the Safety Officer', async () => {
    await send(request, 'post', `/events/${eventId}/confirm`, h[COORD.email])
    expect(await statusOf(request, h, eventId)).toBe('awaiting_safety_check')
  })

  await test.step('Safety Officer: finds it waiting and passes it', async () => {
    const page = await openAsSafetyOfficer(browser)
    await expect(page.getByText(REQUEST.name)).toBeVisible()
    await send(request, 'post', `/safety-checks/${eventId}/approve`, h[SAFETY.email])
    expect(await statusOf(request, h, eventId)).toBe('safety_check_passed')
  })

  await test.step('Organiser: the event now reads "Safety Check Passed (Event Confirmed)"', async () => {
    const page = await openAs(browser, ORG)
    await page.goto('/organiser/events?tab=submitted')
    await expect(page.getByText('Safety Check Passed (Event Confirmed)')).toBeVisible()
  })

  await test.step('Coordinator: opens registration, an Attendee registers', async () => {
    await send(request, 'put', `/events/assigned/${eventId}/registration`, h[COORD.email], {
      registration_enabled: true,
      registration_opens_at: '2026-10-01T00:00:00Z',
      registration_closes_at: '2026-11-01T00:00:00Z',
    })
    await send(request, 'post', '/auth/register', {}, { name: 'Amy Attendee', email: ATTENDEE_EMAIL, password: PASSWORD }, 201)
    const attendee = await login(request, ATTENDEE_EMAIL, PASSWORD)
    await send(request, 'post', `/registrations/events/${eventId}`, attendee)
    const page = await openAs(browser, { ...ORG, email: ATTENDEE_EMAIL, name: 'Amy Attendee' })
    await expect(tile(page, /My Registrations/).locator('.tile-count')).toHaveText('1')
    await page.goto('/attendee/registrations')
    await expect(page.getByText(REQUEST.name)).toBeVisible()
  })

  await test.step('The activity log recorded every milestone, with who and when', async () => {
    const log: { to_status: string; changed_by_name: string | null; created_at: string }[] = await send(
      request, 'get', `/events/${eventId}/activity`, h[ORG.email])
    const statuses = log.map((e) => e.to_status)
    for (const s of ['submitted_awaiting_coordinator', 'under_review', 'event_approved', 'awaiting_safety_check', 'safety_check_passed']) {
      expect(statuses, `activity log is missing ${s}`).toContain(s)
    }
    for (const entry of log) {
      expect(entry.changed_by_name, `no actor on ${entry.to_status}`).toBeTruthy()
      expect(entry.created_at).toBeTruthy()
    }
  })
})

test('UAT-2: nothing is assigned until the Lead assigns it', async ({ browser, request }) => {
  const h = await tokens(request)
  const eventId = await submitRequest(request, h)

  const sam = await openAs(browser, COORD)
  await expect(tile(sam, /My Assigned Events/).locator('.tile-count')).toHaveCount(0)
  expect(await send(request, 'get', '/events/assigned', h[COORD.email])).toEqual([])
  expect(await statusOf(request, h, eventId)).toBe('submitted_awaiting_coordinator')

  // Only the Lead can assign: a Coordinator cannot pick up the request themselves.
  const coordinatorId = await userId(request, h[COORD.email])
  const res = await request.post(`${API}/lead/unassigned-queue/${eventId}/assign`, {
    headers: h[COORD.email],
    data: { coordinator_id: coordinatorId },
  })
  expect(res.status()).toBe(403)
  expect(await statusOf(request, h, eventId)).toBe('submitted_awaiting_coordinator')

  await send(request, 'post', `/lead/unassigned-queue/${eventId}/assign`, h[LEAD.email], { coordinator_id: coordinatorId })
  await sam.goto('/coordinator')
  await expect(tile(sam, /My Assigned Events/).locator('.tile-count')).toHaveText('1')
})

test('UAT-3: an event cannot go to the Safety Officer until it is arranged', async ({ request }) => {
  const h = await tokens(request)
  const eventId = await submitRequest(request, h)
  await assignAndApprove(request, h, eventId)

  const res = await request.post(`${API}/events/${eventId}/confirm`, { headers: h[COORD.email] })
  expect(res.status()).toBe(409)
  expect(JSON.stringify(await res.json())).toContain('The event has no venue')
  expect(await statusOf(request, h, eventId)).toBe('event_approved')

  // The Safety Officer cannot pass an event that was never sent to them.
  const early = await request.post(`${API}/safety-checks/${eventId}/approve`, { headers: h[SAFETY.email] })
  expect(early.status()).toBe(409)
  expect(await statusOf(request, h, eventId)).toBe('event_approved')
})

test('UAT-4: the Safety Officer sends an event back and the Coordinator is told', async ({ browser, request }) => {
  const h = await tokens(request)
  const eventId = await submitRequest(request, h)
  await assignAndApprove(request, h, eventId)
  const bookingId = await arrange(request, h, eventId)
  await send(request, 'post', `/events/${eventId}/confirm`, h[COORD.email])

  const blank = await request.post(`${API}/safety-checks/${eventId}/request-changes`, {
    headers: h[SAFETY.email],
    data: { reason: '   ', venue_booking_ids: [bookingId] },
  })
  expect(blank.status()).toBe(422)
  expect(await statusOf(request, h, eventId)).toBe('awaiting_safety_check')

  await send(request, 'post', `/safety-checks/${eventId}/request-changes`, h[SAFETY.email], {
    reason: 'Second fire exit is blocked',
    venue_booking_ids: [bookingId],
  })
  expect(await statusOf(request, h, eventId)).toBe('planning_event')

  const page = await openAs(browser, COORD)
  await page.goto('/notifications')
  await expect(page.getByText(/Second fire exit is blocked/).first()).toBeVisible()
})

test('UAT-5: people only see what is theirs', async ({ request }) => {
  const h = await tokens(request)
  const eventId = await submitRequest(request, h)
  await assignAndApprove(request, h, eventId)

  // Another Organiser cannot open it; another Coordinator is not responsible for it.
  expect((await request.get(`${API}/events/${eventId}`, { headers: h[OTHER_ORG.email] })).status()).toBe(404)
  expect(await send(request, 'get', '/events', h[OTHER_ORG.email])).toEqual([])
  expect(await send(request, 'get', '/events/assigned', h[OTHER_COORD.email])).toEqual([])
  expect((await request.get(`${API}/events/assigned/${eventId}`, { headers: h[OTHER_COORD.email] })).status()).toBe(404)

  // Role boundaries: Safety checks are for the Safety Officer, the queue is the Lead's.
  expect((await request.get(`${API}/safety-checks`, { headers: h[ORG.email] })).status()).toBe(403)
  expect((await request.get(`${API}/lead/unassigned-queue`, { headers: h[COORD.email] })).status()).toBe(403)
})
