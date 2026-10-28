import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'
import { API, call, login } from './support/api'
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
 * SCRUM-30 (Track My Event Status as Organiser), end to end on the
 * Organiser's My Requests list and Event page.
 *
 *   TC-TS-AC1   -- AC1: the list and the Event page show the same current status
 *   TC-TS-AC2   -- AC2: the status names are spelled exactly as the DoD
 *   TC-TS-AC3   -- AC3: a status the Coordinator sets shows on the next view
 *   TC-TS-AC4   -- AC4: the history lists each change with its time, newest first
 *   TC-TS-AC5   -- AC5: Planning Event shows venue, equipment and Safety Check progress,
 *                  and the send-back reason; no planning section before planning
 *   TC-TS-AC6   -- AC6: another Organiser cannot open the Event
 *   TC-TS-A1    -- DoD 8, axe on the Event page with planning progress (light, dark)
 *
 * The hand-offs between people (approval, venue booking, reservation, the
 * Safety Officer's decision) go through the API; the Organiser's screens are
 * what is under test.
 */
const PASSWORD = 'e2e-track-123'
const user = (key: string, name: string, role: SeedUser['role']): SeedUser => ({
  email: `e2e_ts_${key}@cs.local`,
  name,
  role,
  password: PASSWORD,
})
const ORG = user('org', 'Olivia Organiser', 'organiser')
const OTHER_ORG = user('org2', 'Oscar Organiser', 'organiser')
const COORD = user('coord', 'Sam Tan', 'coordinator')
const STAFF = user('staff', 'Vera Venue', 'venue_staff')
const TECH = user('tech', 'Tess Tech', 'tech_support')
const SAFETY = user('safety', 'Sam Safety', 'safety_officer')
const USERS = [ORG, OTHER_ORG, COORD, STAFF, TECH, SAFETY]
const EMAILS = USERS.map((u) => u.email)
const VENUE = { name: 'TS Auditorium', location: 'Block C', capacity: 400 }
const ITEM = { name: 'TS Projector', category: 'Projection', total_quantity: 10 }

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

/** A submitted event of Olivia's, assigned to Sam (so Under Review). */
async function underReview(request: APIRequestContext, h: Record<string, Headers>, name: string) {
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
      proposed_start: '2026-11-02T09:00:00Z',
      proposed_end: '2026-11-02T17:00:00Z',
      expected_attendance: 120,
      venue_requirements: 'Main hall',
      accessibility_needs: 'Step-free access',
      registration_enabled: false,
      equipment_items: [{ equipment_id: equipmentId, quantity_requested: 2 }],
    },
    201,
  )
  await call(request, 'post', `/events/${created.id}/submit`, h[ORG.email])
  assignEventTo(created.id, COORD.email)
  return created.id as number
}

/** Approved, with the venue approved and the projector reserved, then sent for Safety Check. */
async function awaitingSafetyCheck(request: APIRequestContext, h: Record<string, Headers>, name: string) {
  const eventId = await underReview(request, h, name)
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
  return { eventId, bookingId: booking.id as number }
}

async function expectNoSeriousViolations(page: Page, label: string) {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(blocking.map((v) => `${v.impact} ${v.id}: ${v.help}`).join('\n'), label).toBe('')
}

test('TC-TS-AC1: the list and the Event page show the same current status', async ({ browser, request }) => {
  const h = await tokens(request)
  const eventId = await underReview(request, h, 'TS list and page')
  const olivia = await openAs(browser, ORG)

  await olivia.goto('/organiser/events?tab=submitted')
  const row = olivia.locator('li.request').filter({ hasText: 'TS list and page' })
  await expect(row).toContainText('Under Review')

  await olivia.goto(`/organiser/events/${eventId}`)
  await expect(olivia.getByRole('heading', { name: 'Status' })).toBeVisible()
  await expect(olivia.getByText('Under Review').first()).toBeVisible()
})

test('TC-TS-AC2/3: a status the Coordinator sets shows on the next view, spelled exactly', async ({ browser, request }) => {
  const h = await tokens(request)
  const eventId = await underReview(request, h, 'TS new status')
  const olivia = await openAs(browser, ORG)
  await olivia.goto(`/organiser/events/${eventId}`)
  await expect(olivia.getByText('Under Review').first()).toBeVisible()

  await call(request, 'post', `/events/${eventId}/approve`, h[COORD.email])
  await olivia.reload()
  await expect(olivia.getByText('Event Approved').first()).toBeVisible()
  await olivia.goto('/organiser/events?tab=submitted')
  await expect(olivia.locator('li.request').filter({ hasText: 'TS new status' })).toContainText('Event Approved')
})

test('TC-TS-AC4: the history lists each change with its time, newest first', async ({ browser, request }) => {
  const h = await tokens(request)
  const eventId = await underReview(request, h, 'TS history')
  await call(request, 'post', `/events/${eventId}/approve`, h[COORD.email])
  const olivia = await openAs(browser, ORG)
  await olivia.goto(`/organiser/events/${eventId}`)

  const log = olivia.getByRole('list', { name: 'Activity log' })
  const items = log.locator('.activity-item')
  await expect(items.first()).toContainText('Event Approved')
  await expect(items.first()).toContainText('Sam Tan')
  await expect(items.first().locator('.activity-meta')).toContainText(/ · \S+/)
  await expect(items.last()).toContainText('Submitted – Awaiting Coordinator')
})

test('TC-TS-AC5: Planning Event shows venue, equipment and Safety Check progress; none before planning', async ({ browser, request }) => {
  const h = await tokens(request)
  const reviewId = await underReview(request, h, 'TS before planning')
  const olivia = await openAs(browser, ORG)
  await olivia.goto(`/organiser/events/${reviewId}`)
  await expect(olivia.getByText('Under Review').first()).toBeVisible()
  await expect(olivia.getByRole('heading', { name: 'Planning progress', exact: true })).toHaveCount(0)

  const { eventId } = await awaitingSafetyCheck(request, h, 'TS planning progress')
  await olivia.goto(`/organiser/events/${eventId}`)
  await expect(olivia.getByRole('heading', { name: 'Planning progress', exact: true })).toBeVisible()
  await expect(olivia.getByRole('list', { name: 'Venue bookings' })).toContainText('TS Auditorium')
  await expect(olivia.getByRole('list', { name: 'Venue bookings' })).toContainText('Approved')
  await expect(olivia.getByRole('list', { name: 'Equipment progress' })).toContainText('TS Projector')
  await expect(olivia.getByText('Safety Check:')).toContainText('Awaiting Safety Officer')
})

test('TC-TS-AC5b: a Safety Check that sends the Event back shows its reason', async ({ browser, request }) => {
  const h = await tokens(request)
  const { eventId, bookingId } = await awaitingSafetyCheck(request, h, 'TS sent back')
  const REASON = 'Fire exits on the stage side are blocked.'
  await call(request, 'post', `/safety-checks/${eventId}/request-changes`, h[SAFETY.email], {
    reason: REASON,
    venue_booking_ids: [bookingId],
    equipment_request_ids: [],
  })
  const olivia = await openAs(browser, ORG)
  await olivia.goto(`/organiser/events/${eventId}`)
  await expect(olivia.getByText('Planning Event').first()).toBeVisible()
  await expect(olivia.getByText('Safety Check:')).toContainText('Sent back')
  await expect(olivia.getByRole('note').filter({ hasText: REASON })).toContainText('Changes Requested')
})

test("TC-TS-AC6: another Organiser cannot open the Event or read its progress", async ({ browser, request }) => {
  const h = await tokens(request)
  const eventId = await underReview(request, h, 'TS private event')
  const oscar = await openAs(browser, OTHER_ORG)
  await oscar.goto(`/organiser/events/${eventId}`)
  await expect(oscar.getByText('TS private event')).toHaveCount(0)
  await expect(oscar.getByRole('alert')).toBeVisible()

  const res = await request.get(`${API}/events/${eventId}/progress`, { headers: h[OTHER_ORG.email] })
  expect([403, 404]).toContain(res.status())
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`TC-TS-A1: the Event page with planning progress passes axe (${colorScheme})`, async ({ browser, request }) => {
    const h = await tokens(request)
    const { eventId } = await awaitingSafetyCheck(request, h, `TS axe ${colorScheme}`)
    const olivia = await openAs(browser, ORG, { colorScheme })
    await olivia.goto(`/organiser/events/${eventId}`)
    await expect(olivia.getByRole('heading', { name: 'Planning progress', exact: true })).toBeVisible()
    await expectNoSeriousViolations(olivia, `event page ${colorScheme}`)
  })
}
