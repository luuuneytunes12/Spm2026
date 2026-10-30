import { expect, test } from '@playwright/test'
import { call } from './support/api'
import { approvedEvent, arrange, as, expectNoSeriousViolations, inDays, notice, tabToAndFollow } from './support/arranged'
import { openAs } from './support/coordinator-users'
import type { SeedUser } from './support/db'
import { removeUsers, removeVenue, resetUsers, seedUsers, seedVenue } from './support/db'

/**
 * End-to-end coverage of the Attendee's notifications about Events they
 * registered for, plus its DoD accessibility checks.
 *
 *   TC-AN-1e -- AC3, registering confirms the Event and "Registered"; it opens the Event
 *   TC-AN-2e -- AC3, withdrawing confirms "Withdrawn"
 *   TC-AN-3e -- AC1, a new date on the confirmed Event gives the new date/time
 *   TC-AN-4e -- AC2/AC4, an Attendee who withdrew is not told about the change
 *   TC-AN-A1 -- DoD 8, axe on the Attendee's Notifications page (light, dark)
 *   TC-AN-A2 -- DoD 8, keyboard: the notice's "View event" link is reachable, visible focus
 */
const PASSWORD = 'e2e-attendee-notice-123'
const user = (key: string, name: string, role: SeedUser['role']): SeedUser => ({
  email: `e2e_an_${key}@cs.local`, name, role, password: PASSWORD,
})
const ORG = user('org', 'Olivia Organiser', 'organiser')
const COORD = user('coord', 'Sam Tan', 'coordinator')
const STAFF = user('staff', 'Vera Venue', 'venue_staff')
const SAFETY = user('safety', 'Sofia Safety', 'safety_officer')
const AMY = user('amy', 'Amy Attendee', 'attendee')
const BEN = user('ben', 'Ben Attendee', 'attendee')
const USERS = [ORG, COORD, STAFF, SAFETY, AMY, BEN]
const EMAILS = USERS.map((u) => u.email)
const VENUE = { name: 'AN Auditorium', location: 'Block A', capacity: 400 }

test.beforeAll(() => {
  seedUsers(USERS)
  seedVenue(VENUE)
})
test.beforeEach(() => resetUsers(EMAILS))
test.afterAll(() => {
  removeUsers(EMAILS)
  removeVenue(VENUE.name)
})

/** A confirmed Event taking registrations now. */
async function open(request: Parameters<typeof as>[0], name: string) {
  const eventId = await approvedEvent(request, ORG, COORD, name)
  await arrange(request, eventId, { coord: COORD, staff: STAFF }, VENUE.name)
  const coordH = await as(request, COORD)
  await call(request, 'post', `/events/${eventId}/confirm`, coordH)
  await call(request, 'post', `/safety-checks/${eventId}/approve`, await as(request, SAFETY))
  await call(request, 'put', `/events/assigned/${eventId}/registration`, coordH, {
    registration_enabled: true,
    registration_opens_at: inDays(-1),
    registration_closes_at: inDays(29),
  })
  return eventId
}

const register = async (request: Parameters<typeof as>[0], eventId: number, who: SeedUser) =>
  call(request, 'post', `/registrations/events/${eventId}`, await as(request, who))

test('TC-AN-1e: registering confirms the Event and "Registered", and opens the Event', async ({ browser, request }) => {
  const eventId = await open(request, 'Registered Summit')
  await register(request, eventId, AMY)
  const amy = await openAs(browser, AMY)
  await amy.goto('/notifications')
  const row = notice(amy, "Your registration for 'Registered Summit' on")
  await expect(row).toContainText(/09:00 UTC is now Registered\./)
  await row.getByRole('link', { name: 'View event' }).click()
  await expect(amy).toHaveURL(new RegExp(`/attendee/events/${eventId}$`))
})

test('TC-AN-2e: withdrawing confirms "Withdrawn"', async ({ browser, request }) => {
  const eventId = await open(request, 'Withdrawn Summit')
  await register(request, eventId, AMY)
  await call(request, 'post', `/registrations/events/${eventId}/withdraw`, await as(request, AMY))
  const amy = await openAs(browser, AMY)
  await amy.goto('/notifications')
  await expect(notice(amy, /Your registration for 'Withdrawn Summit' on .* is now Withdrawn\./)).toBeVisible()
})

test('TC-AN-3e: a new date on the confirmed Event gives the new date/time', async ({ browser, request }) => {
  const eventId = await open(request, 'Moved Summit')
  await register(request, eventId, AMY)
  await call(request, 'patch', `/events/assigned/${eventId}/planning`, await as(request, COORD), {
    proposed_start: inDays(31), proposed_end: inDays(31, 17),
  })
  const amy = await openAs(browser, AMY)
  await amy.goto('/notifications')
  await expect(
    notice(amy, "'Moved Summit', which you are registered for, has changed: it now starts"),
  ).toContainText(/it now starts .* 09:00 UTC; it now ends .* 17:00 UTC\./)
})

test('TC-AN-4e: an Attendee who withdrew is not told about the change', async ({ browser, request }) => {
  const eventId = await open(request, 'Left Summit')
  await register(request, eventId, BEN)
  await call(request, 'post', `/registrations/events/${eventId}/withdraw`, await as(request, BEN))
  await call(request, 'patch', `/events/assigned/${eventId}/planning`, await as(request, COORD), {
    proposed_start: inDays(31), proposed_end: inDays(31, 17),
  })
  const ben = await openAs(browser, BEN)
  await ben.goto('/notifications')
  await expect(ben.getByText(/has changed: it now starts/)).toHaveCount(0)
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`TC-AN-A1: the Attendee's Notifications page passes axe (${colorScheme})`, async ({ browser, request }) => {
    const eventId = await open(request, `Axe Summit ${colorScheme}`)
    await register(request, eventId, AMY)
    const amy = await openAs(browser, AMY, { colorScheme })
    await amy.goto('/notifications')
    await expect(notice(amy, `Axe Summit ${colorScheme}`)).toBeVisible()
    await expectNoSeriousViolations(amy, `notifications ${colorScheme}`)
  })
}

test('TC-AN-A2: the notice\'s View event link is keyboard-reachable with visible focus', async ({ browser, request }) => {
  const eventId = await open(request, 'Keyboard Summit')
  await register(request, eventId, AMY)
  const amy = await openAs(browser, AMY)
  await amy.goto('/notifications')
  await tabToAndFollow(amy, notice(amy, 'Keyboard Summit').getByRole('link', { name: 'View event' }))
  await expect(amy).toHaveURL(new RegExp(`/attendee/events/${eventId}$`))
})
