/**
 * E2E SEARCH: SAFETY APPROVAL, REGISTRATION, WITHDRAWAL, RE-REGISTRATION, TIME WINDOW, TEST ISOLATION
 *
 * Safety approval and attendee registration journey (E20–E24).
 *
 * The event, venue and users are isolated prerequisites. The coordinator,
 * safety officer and attendee perform the decisions through their browser
 * screens. This demonstrates the release gate and the registration lifecycle;
 * dedicated safety specs cover additional blocked arrangements and send-backs.
 */
import { expect, test } from '@playwright/test'
import type { APIRequestContext, Browser } from '@playwright/test'
import { call, login } from './support/api'
import { openAs } from './support/coordinator-users'
import { assignEventTo, removeUsers, removeVenue, resetUsers, seedUsers, seedVenue } from './support/db'
import type { SeedUser } from './support/db'

const password = 'e2e-safety-only-123'
const organiser: SeedUser = { email: 'e2e_journey_safety_org@cs.local', name: 'Safety Organiser', role: 'organiser', password }
const coordinator: SeedUser = { email: 'e2e_journey_safety_coord@cs.local', name: 'Safety Coordinator', role: 'coordinator', password }
const venueStaff: SeedUser = { email: 'e2e_journey_safety_staff@cs.local', name: 'Safety Venue Staff', role: 'venue_staff', password }
const safety: SeedUser = { email: 'e2e_journey_safety_officer@cs.local', name: 'Journey Safety Officer', role: 'safety_officer', password }
// Registration creates a real attendee role; the object supplies login details only.
const attendee: SeedUser = { email: 'e2e_journey_safety_attendee@cs.local', name: 'Journey Attendee', role: 'attendee', password }
const users = [organiser, coordinator, venueStaff, safety]
const emails = [...users.map((u) => u.email), attendee.email]
const venue = { name: 'E2E Safety Journey Hall', location: 'Test campus', capacity: 300 }

test.beforeAll(() => { seedUsers(users); seedVenue(venue) })
// TEST ISOLATION: clear prior events first (registrations reference them), then
// remove the attendee so each test can exercise real account registration again.
test.beforeEach(() => {
  resetUsers(emails)
  removeUsers([attendee.email])
})
// BROWSER CONTEXT ISOLATION: openAs creates separate sessions for each role.
// Close them after every test, including failures, so sessions do not accumulate.
test.afterEach(async ({ browser }) => {
  await Promise.all(browser.contexts().map((context) => context.close()))
})
test.afterAll(() => { removeUsers(emails); removeVenue(venue.name) })

/** Make a submitted, assigned, approved event and an approved venue booking. */
async function readyEvent(request: APIRequestContext) {
  const org = await login(request, organiser.email, password)
  const coord = await login(request, coordinator.email, password)
  const staff = await login(request, venueStaff.email, password)
  const year = new Date().getFullYear() + 2
  const event = await call(request, 'post', '/events', org, {
    name: 'E2E safety registration journey', purpose: 'Partner briefing', event_type: 'conference',
    proposed_start: `${year}-11-02T09:00:00Z`, proposed_end: `${year}-11-02T17:00:00Z`,
    expected_attendance: 120, venue_requirements: 'Stage', accessibility_needs: 'Step-free', registration_enabled: false,
  }, 201)
  await call(request, 'post', `/events/${event.id}/submit`, org)
  assignEventTo(event.id, coordinator.email)
  await call(request, 'post', `/events/${event.id}/approve`, coord)
  const venues = await call(request, 'get', '/venues', coord)
  const selected = venues.find((item: { name: string }) => item.name === venue.name)
  const bookings = await call(request, 'post', `/venue-bookings/events/${event.id}`, coord, { venues: [{ venue_id: selected.id }] }, 201)
  await call(request, 'post', `/venue-bookings/${bookings[0].id}/approve`, staff)
  await call(request, 'post', '/auth/register', {}, { name: attendee.name, email: attendee.email, password }, 201)
  return event.id as number
}

/** The safety officer lands directly on the safety queue instead of a welcome page. */
async function openSafety(browser: Browser) {
  const page = await (await browser.newContext()).newPage()
  await page.goto('/login')
  await page.getByLabel('Email').fill(safety.email)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/safety-checks/)
  return page
}

/** Produce a date input safely on either side of now, independent of the year. */
function daysFromNow(days: number) {
  const d = new Date(Date.now() + days * 24 * 60 * 60 * 1000)
  return d.toISOString().slice(0, 16)
}

/** Follow the hand-off from a safety decision to a persistent attendee registration. */
test('E20–E24: safety approval enables an attendee to register, withdraw and return', async ({ browser, request }) => {
  test.setTimeout(90_000)
  const id = await readyEvent(request)
  const coord = await openAs(browser, coordinator)
  const person = await openAs(browser, attendee)
  await person.goto('/attendee/events')
  await expect(person.getByText('E2E safety registration journey')).toHaveCount(0)

  // The coordinator submits the arrangement; registration remains locked pending safety.
  await coord.goto(`/coordinator/events/${id}`)
  await coord.getByRole('button', { name: 'Submit for Safety Check' }).click()
  await expect(coord.getByText('Awaiting Safety Check').first()).toBeVisible()
  await expect(coord.getByLabel('Enable registration')).toHaveCount(0)
  const officer = await openSafety(browser)
  await officer.goto(`/safety-checks/${id}`)
  await officer.getByRole('button', { name: 'Approve', exact: true }).click()
  await expect(officer.getByText('Safety Check passed. The event is confirmed.')).toBeVisible()

  // Once approved, the coordinator opens a window spanning the current time.
  await coord.reload()
  await coord.getByLabel('Enable registration').check()
  await coord.getByLabel('Registration opens').fill(daysFromNow(-3))
  await coord.getByLabel('Registration closes').fill(daysFromNow(3))
  await coord.getByRole('button', { name: 'Save registration settings' }).click()
  await expect(coord.getByText('Registration settings saved.')).toBeVisible()

  // A registered attendee can withdraw and re-register without duplicate rows.
  await person.reload()
  const card = person.getByRole('listitem').filter({ hasText: 'E2E safety registration journey' })
  await card.getByRole('button', { name: 'Register', exact: true }).click()
  await expect(card).toContainText('Registered')
  await expect(card.getByRole('button', { name: 'Register', exact: true })).toHaveCount(0)
  await card.getByRole('button', { name: 'Withdraw' }).click()
  await expect(card).toContainText('Withdrawn')
  await person.goto('/attendee/registrations')
  await expect(person.getByRole('listitem').filter({ hasText: 'E2E safety registration journey' })).toContainText('Withdrawn')
  await person.goto('/attendee/events')
  await card.getByRole('button', { name: 'Register again' }).click()
  await person.goto('/attendee/registrations')
  const registrations = person.getByRole('listitem').filter({ hasText: 'E2E safety registration journey' })
  await expect(registrations).toHaveCount(1)
  await expect(registrations).toContainText('Registered')
})

/** Check both time-window decisions from the attendee's events page. */
test('E24: registration is unavailable before opening and after closing', async ({ browser, request }) => {
  test.setTimeout(60_000)
  const id = await readyEvent(request)
  const coordToken = await login(request, coordinator.email, password)
  const safetyToken = await login(request, safety.email, password)
  // Safety approval is a prerequisite here; the window is the decision tested.
  await call(request, 'post', `/events/${id}/confirm`, coordToken)
  await call(request, 'post', `/safety-checks/${id}/approve`, safetyToken)
  const coord = await openAs(browser, coordinator)
  await coord.goto(`/coordinator/events/${id}`)
  await coord.getByLabel('Enable registration').check()
  await coord.getByLabel('Registration opens').fill(daysFromNow(3))
  await coord.getByLabel('Registration closes').fill(daysFromNow(4))
  await coord.getByRole('button', { name: 'Save registration settings' }).click()
  await expect(coord.getByText('Registration settings saved.')).toBeVisible()
  const person = await openAs(browser, attendee)
  await person.goto('/attendee/events')
  const card = person.getByRole('listitem').filter({ hasText: 'E2E safety registration journey' })
  await expect(card).toContainText('Registration not open yet')
  await expect(card.getByRole('button', { name: 'Register', exact: true })).toHaveCount(0)

  // Move the window wholly into the past and check the closed outcome.
  await coord.getByLabel('Registration opens').fill(daysFromNow(-4))
  await coord.getByLabel('Registration closes').fill(daysFromNow(-3))
  await coord.getByRole('button', { name: 'Save registration settings' }).click()
  await expect(coord.getByText('Registration settings saved.')).toBeVisible()
  await person.reload()
  await expect(card).toContainText('Registration closed')
  await expect(card.getByRole('button', { name: 'Register', exact: true })).toHaveCount(0)
})
