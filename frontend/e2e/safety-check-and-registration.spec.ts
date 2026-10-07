import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'
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
  setBookingStatus,
  seedUsers,
  seedVenue,
} from './support/db'

/**
 * SCRUM-65 (Submit Event for Safety Check) and SCRUM-66 (Schedule Registration
 * for a Confirmed Event), end to end on the Coordinator's event page.
 *
 *   TC-SC-AC1/2  -- 65 AC1, AC2: blocked with every outstanding item listed, then
 *                   submitted once the venue and equipment are ready
 *   TC-SC-AC5    -- 65 AC5: the Activity Log shows the change with the Coordinator's name
 *   TC-SC-A1     -- DoD 8, axe on the page in each state
 *   TC-RG-AC2    -- 66 AC2: told the Safety Officer must approve first
 *   TC-RG-AC1/5  -- 66 AC1, AC5: dates saved and shown; an Attendee then registers
 *   TC-RG-AC4    -- 66 AC4: a close date after the event starts is flagged
 *   TC-RG-AC3    -- 66 AC3: arrangements that fell through block it, every item listed
 *
 * The hand-offs between people (venue approval, reservation, the Safety Officer's
 * decision) go through the API; the Coordinator's screen is what is under test.
 */
const PASSWORD = 'e2e-sc-reg-123'
const user = (key: string, name: string, role: SeedUser['role']): SeedUser => ({
  email: `e2e_scr_${key}@cs.local`,
  name,
  role,
  password: PASSWORD,
})
const ORG = user('org', 'Olivia Organiser', 'organiser')
const COORD = user('coord', 'Sam Tan', 'coordinator')
const OTHER = user('other', 'Priya Nair', 'coordinator')
const STAFF = user('staff', 'Vera Venue', 'venue_staff')
const TECH = user('tech', 'Tess Tech', 'tech_support')
const SAFETY = user('safety', 'Sam Safety', 'safety_officer')
const USERS = [ORG, COORD, OTHER, STAFF, TECH, SAFETY]
const EMAILS = USERS.map((u) => u.email)
const ATTENDEE = user('attendee', 'Amy Attendee', 'organiser') // registered through the API, so a real Attendee
const VENUE = { name: 'SCR Auditorium', location: 'Block B', capacity: 400 }
const ITEM = { name: 'SCR Projector', category: 'Projection', total_quantity: 10 }

let equipmentId = 0

test.beforeAll(() => {
  seedUsers(USERS)
  seedVenue(VENUE)
  equipmentId = seedEquipment(ITEM)
})
test.beforeEach(() => resetUsers([...EMAILS, ATTENDEE.email]))
test.afterAll(() => {
  removeUsers([...EMAILS, ATTENDEE.email])
  removeVenue(VENUE.name)
  removeEquipment(ITEM.name)
})

type Headers = Record<string, string>

async function tokens(request: APIRequestContext) {
  const entries = await Promise.all(USERS.map(async (u) => [u.email, await login(request, u.email, u.password)] as const))
  return Object.fromEntries(entries) as Record<string, Headers>
}

/** An approved event of Sam's that asked for one projector. Nothing arranged. */
async function approvedEvent(request: APIRequestContext, h: Record<string, Headers>, name: string) {
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
  await call(request, 'post', `/events/${created.id}/approve`, h[COORD.email])
  return created.id as number
}

/** The venue approved by Venue Staff and the projector reserved by Tech Support. */
async function arrange(request: APIRequestContext, h: Record<string, Headers>, eventId: number) {
  const venues = await call(request, 'get', '/venues', h[COORD.email])
  const venue = venues.find((v: { name: string }) => v.name === VENUE.name)
  const [booking] = await call(request, 'post', `/venue-bookings/events/${eventId}`, h[COORD.email], { venues: [{ venue_id: venue.id }] }, 201)
  await call(request, 'post', `/venue-bookings/${booking.id}/approve`, h[STAFF.email])
  await call(request, 'post', '/equipment-reservations', h[TECH.email], {
    event_id: eventId,
    equipment_id: equipmentId,
    placement_notes: 'Back of hall',
  })
}

async function expectNoSeriousViolations(page: Page, label: string) {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(blocking.map((v) => `${v.impact} ${v.id}: ${v.help}`).join('\n'), label).toBe('')
}

const submitButton = (page: Page) => page.getByRole('button', { name: 'Submit for Safety Check' })

test('TC-SC-AC1/2: blocked with every outstanding item listed, then submitted once ready', async ({ browser, request }) => {
  const h = await tokens(request)
  const eventId = await approvedEvent(request, h, 'SCR blocked then ready')
  const sam = await openAs(browser, COORD)

  await sam.goto(`/coordinator/events/${eventId}`)
  const outstanding = sam.getByRole('status').filter({ hasText: 'Still outstanding' })
  await expect(outstanding).toContainText('The event has no venue') // AC2: no booking at all
  await expect(outstanding).toContainText('SCR Projector')
  await expect(outstanding).toContainText('requested') // ... with its status

  await submitButton(sam).click()
  await expect(sam.getByRole('alert')).toContainText('Cannot submit yet')
  await expect(sam.getByRole('alert')).toContainText('SCR Projector')
  expect((await call(request, 'get', `/events/${eventId}`, h[ORG.email])).status).toBe('event_approved') // unchanged

  await arrange(request, h, eventId)
  await sam.reload()
  await expect(sam.getByText('Still outstanding')).toHaveCount(0)
  await expect(sam.getByRole('region', { name: 'Venue bookings' })).toContainText('Approved')

  await submitButton(sam).click() // AC1
  await expect(submitButton(sam)).toHaveCount(0)
  expect((await call(request, 'get', `/events/${eventId}`, h[ORG.email])).status).toBe('awaiting_safety_check')
})

test('TC-SC-AC5: the Activity Log shows the submission with the Coordinator\'s name and time', async ({ browser, request }) => {
  const h = await tokens(request)
  const eventId = await approvedEvent(request, h, 'SCR logged')
  await arrange(request, h, eventId)
  const sam = await openAs(browser, COORD)
  await sam.goto(`/coordinator/events/${eventId}`)
  await submitButton(sam).click()
  await expect(submitButton(sam)).toHaveCount(0)

  await sam.reload()
  const log = sam.getByRole('region', { name: /activity/i }).or(sam.locator('section', { hasText: 'Activity' })).first()
  await expect(log).toContainText('Submitted for safety check by the Event Coordinator')
  await expect(log).toContainText('Sam Tan')
})

test('TC-SC-AC4: an event assigned to another Coordinator cannot be submitted by Priya', async ({ request }) => {
  const h = await tokens(request)
  const eventId = await approvedEvent(request, h, 'SCR not yours')
  await arrange(request, h, eventId)

  await call(request, 'post', `/events/${eventId}/confirm`, h[OTHER.email], undefined, 404)
  // Booking the venue moved it to Planning Event (SCRUM-39); the refused submit changed nothing more.
  expect((await call(request, 'get', `/events/${eventId}`, h[ORG.email])).status).toBe('planning_event')
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`TC-SC-A1: the Submit for Safety Check card passes axe, blocked and ready (${colorScheme})`, async ({ browser, request }) => {
    const h = await tokens(request)
    const eventId = await approvedEvent(request, h, `SCR axe ${colorScheme}`)
    const sam = await openAs(browser, COORD, { colorScheme })
    await sam.goto(`/coordinator/events/${eventId}`)
    await expect(sam.getByText('Still outstanding')).toBeVisible()
    await expectNoSeriousViolations(sam, `blocked ${colorScheme}`)
    await arrange(request, h, eventId)
    await sam.reload()
    await expect(sam.getByText('Still outstanding')).toHaveCount(0)
    await expectNoSeriousViolations(sam, `ready ${colorScheme}`)
  })
}

test('TC-RG-AC2: an event awaiting its safety check is told the Safety Officer must approve first', async ({ browser, request }) => {
  const h = await tokens(request)
  const eventId = await approvedEvent(request, h, 'SCR awaiting')
  await arrange(request, h, eventId)
  await call(request, 'post', `/events/${eventId}/confirm`, h[COORD.email])
  const sam = await openAs(browser, COORD)

  await sam.goto(`/coordinator/events/${eventId}`)
  await expect(sam.getByRole('note')).toContainText('once the Safety Officer has approved this event')
  await expect(sam.getByLabel('Enable registration')).toHaveCount(0)
  await call(request, 'put', `/events/assigned/${eventId}/registration`, h[COORD.email], { registration_enabled: true }, 409)
})

test('TC-RG-AC1/5: dates are saved and shown, and an Attendee can then register', async ({ browser, request }) => {
  const h = await tokens(request)
  const eventId = await approvedEvent(request, h, 'SCR open registration')
  await arrange(request, h, eventId)
  await call(request, 'post', `/events/${eventId}/confirm`, h[COORD.email])
  await call(request, 'post', `/safety-checks/${eventId}/approve`, h[SAFETY.email])
  const sam = await openAs(browser, COORD)

  await sam.goto(`/coordinator/events/${eventId}`)
  await sam.getByLabel('Enable registration').check()
  await sam.getByLabel('Registration opens').fill('2026-10-01T09:00')
  await sam.getByLabel('Registration closes').fill('2026-11-01T09:00')
  await sam.getByRole('button', { name: 'Save registration settings' }).click()
  await expect(sam.getByText('Registration settings saved.')).toBeVisible()
  await sam.reload() // saved, not just on screen
  await expect(sam.getByLabel('Enable registration')).toBeChecked()
  await expect(sam.getByLabel('Registration opens')).toHaveValue('2026-10-01T09:00')
  await expect(sam.getByLabel('Registration closes')).toHaveValue('2026-11-01T09:00')

  await call(request, 'post', '/auth/register', {}, { name: ATTENDEE.name, email: ATTENDEE.email, password: PASSWORD }, 201)
  const amy = await openAs(browser, { ...ATTENDEE, role: 'organiser' })
  await amy.goto('/attendee/events')
  const card = amy.getByRole('listitem').filter({ hasText: 'SCR open registration' })
  await expect(card).toBeVisible()
  await card.getByRole('button', { name: /register/i }).click()
  await amy.goto('/attendee/registrations')
  await expect(amy.getByText('SCR open registration')).toBeVisible()
})

test('TC-RG-AC4: a close date after the event starts is flagged and nothing is saved', async ({ browser, request }) => {
  const h = await tokens(request)
  const eventId = await approvedEvent(request, h, 'SCR bad dates')
  await arrange(request, h, eventId)
  await call(request, 'post', `/events/${eventId}/confirm`, h[COORD.email])
  await call(request, 'post', `/safety-checks/${eventId}/approve`, h[SAFETY.email])
  const sam = await openAs(browser, COORD)

  await sam.goto(`/coordinator/events/${eventId}`)
  await sam.getByLabel('Enable registration').check()
  await sam.getByLabel('Registration opens').fill('2026-10-01T09:00')
  await sam.getByLabel('Registration closes').fill('2026-11-30T09:00') // the event starts on 2 Nov
  await sam.getByRole('button', { name: 'Save registration settings' }).click()

  await expect(sam.getByRole('alert')).toContainText('cannot close after the event starts')
  await expect(sam.getByLabel('Registration closes')).toHaveAttribute('aria-invalid', 'true')
  await expect(sam.getByLabel('Registration opens')).not.toHaveAttribute('aria-invalid', 'true')
  expect((await call(request, 'get', `/events/assigned/${eventId}`, h[COORD.email])).registration_enabled).toBe(false)
})

test('TC-RG-AC3: a venue that is no longer approved blocks registration, and the item is listed', async ({ browser, request }) => {
  const h = await tokens(request)
  const eventId = await approvedEvent(request, h, 'SCR venue lost')
  await arrange(request, h, eventId)
  await call(request, 'post', `/events/${eventId}/confirm`, h[COORD.email])
  await call(request, 'post', `/safety-checks/${eventId}/approve`, h[SAFETY.email])
  setBookingStatus(eventId, 'pending') // the venue became unavailable after confirmation
  const sam = await openAs(browser, COORD)

  await sam.goto(`/coordinator/events/${eventId}`)
  await sam.getByLabel('Enable registration').check()
  await sam.getByLabel('Registration opens').fill('2026-10-01T09:00')
  await sam.getByLabel('Registration closes').fill('2026-11-01T09:00')
  await sam.getByRole('button', { name: 'Save registration settings' }).click()

  const alert = sam.getByRole('alert')
  await expect(alert).toContainText('Registration cannot be opened')
  await expect(alert).toContainText(VENUE.name)
  await expect(alert).toContainText('pending') // the item and its status
  expect((await call(request, 'get', `/events/assigned/${eventId}`, h[COORD.email])).registration_enabled).toBe(false)
})

test('TC-PL: recording equipment moves an approved event to Planning Event, shown without a reload', async ({ browser, request }) => {
  const h = await tokens(request)
  const eventId = await approvedEvent(request, h, 'SCR equipment starts planning')
  const sam = await openAs(browser, COORD)

  await sam.goto(`/coordinator/events/${eventId}`)
  const badge = sam.getByRole('heading', { level: 1 }).locator('..').locator('.badge')
  await expect(badge).toHaveText('Event Approved')

  await sam.getByLabel('Equipment type').selectOption(ITEM.category)
  await sam.getByRole('button', { name: 'Add requirement' }).click()

  await expect(badge).toHaveText('Planning Event') // no reload
  expect((await call(request, 'get', `/events/${eventId}`, h[ORG.email])).status).toBe('planning_event')
  const log = await call(request, 'get', `/events/${eventId}/activity`, h[ORG.email])
  const move = log.find((e: { to_status: string }) => e.to_status === 'planning_event')
  expect(move.changed_by_name).toBe('Sam Tan')
})
