import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'
import { call, login } from './support/api'
import { openAs } from './support/coordinator-users'
import type { SeedUser } from './support/db'
import { assignEventTo, removeUsers, removeVenue, resetUsers, seedUsers, seedVenue } from './support/db'

/**
 * SCRUM-50 View Attendee List for Event, end to end.
 *
 *   TC-AL-AC1  -- AC1: the Coordinator sees the registered count and attendees by name
 *   TC-AL-AC2  -- AC2: each attendee's registration status (Registered / Withdrawn)
 *   TC-AL-AC1b -- AC1: the Organiser sees the list on their own event page
 *   TC-AL-N1   -- another Coordinator is told the event is not theirs; an Attendee is refused
 *   TC-AL-N2   -- registration not enabled: no attendee list is shown
 *   TC-AL-A1   -- DoD 8, axe (light, dark) and keyboard
 */
const PASSWORD = 'e2e-attlist-123'
const user = (key: string, name: string, role: SeedUser['role']): SeedUser => ({
  email: `e2e_al_${key}@cs.local`,
  name,
  role,
  password: PASSWORD,
})
const ORG = user('org', 'Olivia Organiser', 'organiser')
const COORD = user('coord', 'Sam Tan', 'coordinator')
const OTHER = user('other', 'Priya Nair', 'coordinator')
const STAFF = user('staff', 'Vera Venue', 'venue_staff')
const SAFETY = user('safety', 'Sam Safety', 'safety_officer')
const USERS = [ORG, COORD, OTHER, STAFF, SAFETY]
const AMY = user('amy', 'Amy Attendee', 'attendee')
const BEN = user('ben', 'Ben Attendee', 'attendee')
const EMAILS = [...USERS, AMY, BEN].map((u) => u.email)
const VENUE = { name: 'AL Auditorium', location: 'Block C', capacity: 400 }
// Keep the attendee-registration setup valid regardless of the current year.
const FUTURE_YEAR = new Date().getFullYear() + 2

// Preparing a confirmed event and two attendees requires several role hand-offs.
test.setTimeout(90_000)
test.beforeAll(() => {
  seedUsers(USERS)
  seedVenue(VENUE)
})
test.beforeEach(() => resetUsers(EMAILS))
test.afterAll(() => {
  removeUsers(EMAILS)
  removeVenue(VENUE.name)
})

type Headers = Record<string, string>

async function tokens(request: APIRequestContext) {
  const entries = await Promise.all(USERS.map(async (u) => [u.email, await login(request, u.email, u.password)] as const))
  return Object.fromEntries(entries) as Record<string, Headers>
}

/** A confirmed event of Sam's. With `registration`, Sam has opened it. */
async function confirmedEvent(request: APIRequestContext, h: Record<string, Headers>, name: string, registration: boolean) {
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
      proposed_start: `${FUTURE_YEAR}-11-02T09:00:00Z`,
      proposed_end: `${FUTURE_YEAR}-11-02T17:00:00Z`,
      expected_attendance: 120,
      venue_requirements: 'Main hall',
      accessibility_needs: 'Step-free access',
      registration_enabled: false,
    },
    201,
  )
  const id = created.id as number
  await call(request, 'post', `/events/${id}/submit`, h[ORG.email])
  assignEventTo(id, COORD.email)
  await call(request, 'post', `/events/${id}/approve`, h[COORD.email])
  const venues = await call(request, 'get', '/venues', h[COORD.email])
  const venue = venues.find((v: { name: string }) => v.name === VENUE.name)
  const [booking] = await call(request, 'post', `/venue-bookings/events/${id}`, h[COORD.email], { venues: [{ venue_id: venue.id }] }, 201)
  await call(request, 'post', `/venue-bookings/${booking.id}/approve`, h[STAFF.email])
  await call(request, 'post', `/events/${id}/confirm`, h[COORD.email])
  await call(request, 'post', `/safety-checks/${id}/approve`, h[SAFETY.email])
  if (registration) {
    await call(request, 'put', `/events/assigned/${id}/registration`, h[COORD.email], {
      registration_enabled: true,
      registration_opens_at: new Date(Date.now() - 3 * 86_400_000).toISOString(),
      registration_closes_at: new Date(Date.now() + 3 * 86_400_000).toISOString(),
    })
  }
  return id
}

/** Amy registers and stays registered; Ben registers, then withdraws. */
async function twoAttendees(request: APIRequestContext, eventId: number) {
  removeUsers([AMY.email, BEN.email]) // left over from an earlier test; their registrations went with the events
  for (const a of [AMY, BEN]) {
    await call(request, 'post', '/auth/register', {}, { name: a.name, email: a.email, password: PASSWORD }, 201)
    const h = await login(request, a.email, PASSWORD)
    await call(request, 'post', `/registrations/events/${eventId}`, h)
    if (a === BEN) await call(request, 'post', `/registrations/events/${eventId}/withdraw`, h)
  }
}

async function expectNoSeriousViolations(page: Page, label: string) {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(blocking.map((v) => `${v.impact} ${v.id}: ${v.help}`).join('\n'), label).toBe('')
}

const section = (page: Page) => page.getByRole('region', { name: 'Registered attendees' })

test('TC-AL-AC1/AC2: the Coordinator sees the count, the names and each status', async ({ browser, request }) => {
  const h = await tokens(request)
  const id = await confirmedEvent(request, h, 'AL coordinator view', true)
  await twoAttendees(request, id)
  const sam = await openAs(browser, COORD)

  await sam.goto(`/coordinator/events/${id}`)
  await expect(section(sam)).toContainText('1 registered') // Ben withdrew
  await expect(section(sam).getByText('Amy Attendee')).toBeVisible()
  await expect(section(sam).getByText('Ben Attendee')).toBeVisible()
  await expect(section(sam).locator('.detail-row').filter({ hasText: 'Amy Attendee' })).toContainText('Registered')
  await expect(section(sam).locator('.detail-row').filter({ hasText: 'Ben Attendee' })).toContainText('Withdrawn')
})

test('TC-AL-AC1b: the Organiser sees the list on their own event page', async ({ browser, request }) => {
  const h = await tokens(request)
  const id = await confirmedEvent(request, h, 'AL organiser view', true)
  await twoAttendees(request, id)
  const olivia = await openAs(browser, ORG)

  await olivia.goto(`/organiser/events/${id}`)
  await expect(section(olivia)).toContainText('1 registered')
  await expect(section(olivia).getByText('Amy Attendee')).toBeVisible()
})

test('TC-AL-N1: another Coordinator and an Attendee are refused, and no names leak', async ({ browser, request }) => {
  const h = await tokens(request)
  const id = await confirmedEvent(request, h, 'AL denied', true)
  await twoAttendees(request, id)

  const priya = await openAs(browser, OTHER)
  await priya.goto(`/coordinator/events/${id}`)
  await expect(priya.getByText('That event is not assigned to you.')).toBeVisible()
  await expect(priya.getByText('Amy Attendee')).toHaveCount(0)

  const res = await request.get(`http://localhost:8001/registrations/events/${id}/attendees`, {
    headers: h[OTHER.email],
  })
  expect(res.status()).toBe(404)
  const amy = await login(request, AMY.email, PASSWORD)
  const denied = await request.get(`http://localhost:8001/registrations/events/${id}/attendees`, { headers: amy })
  expect(denied.status()).toBe(403)
})

test('TC-AL-N2: registration not enabled shows no attendee list', async ({ browser, request }) => {
  const h = await tokens(request)
  const id = await confirmedEvent(request, h, 'AL not enabled', false)
  const sam = await openAs(browser, COORD)

  await sam.goto(`/coordinator/events/${id}`)
  await expect(sam.getByRole('heading', { level: 1, name: 'AL not enabled' })).toBeVisible()
  await expect(section(sam)).toHaveCount(0)
  const res = await request.get(`http://localhost:8001/registrations/events/${id}/attendees`, { headers: h[COORD.email] })
  expect(res.status()).toBe(409)
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`TC-AL-A1: the attendee list passes axe (${colorScheme})`, async ({ browser, request }) => {
    const h = await tokens(request)
    const id = await confirmedEvent(request, h, `AL axe ${colorScheme}`, true)
    await twoAttendees(request, id)
    const sam = await openAs(browser, COORD, { colorScheme })
    await sam.goto(`/coordinator/events/${id}`)
    await expect(section(sam).getByText('Amy Attendee')).toBeVisible()
    await expectNoSeriousViolations(sam, `attendee list ${colorScheme}`)
  })
}

test('TC-AL-A1b: the page is keyboard-navigable past the attendee list with visible focus', async ({ browser, request }) => {
  const h = await tokens(request)
  const id = await confirmedEvent(request, h, 'AL keyboard', true)
  await twoAttendees(request, id)
  const sam = await openAs(browser, COORD)
  await sam.goto(`/coordinator/events/${id}`)
  await expect(section(sam).getByText('Amy Attendee')).toBeVisible()
  let visible = false
  for (let i = 0; i < 12; i++) {
    await sam.keyboard.press('Tab')
    visible ||= await sam.evaluate(() => {
      const el = document.activeElement as HTMLElement | null
      if (!el || el === document.body) return false
      const s = getComputedStyle(el)
      return (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none'
    })
  }
  expect(visible).toBe(true)
})
