/**
 * E2E SEARCH: CAPACITY, SUITABILITY, MULTIPLE VENUES, CANCELLATION, EQUIPMENT, STOCK, OVERLAP
 *
 * Cross-role planning journeys for suitability and multiple venues (E10, E15)
 * and equipment request, availability and reservation decisions (E17–E19).
 *
 * Users, venues and stock are test-only fixtures in disposable PostgreSQL.
 * API setup brings an event to the approved starting state; the planning
 * decisions under test are made and checked through real browser pages.
 */
import { expect, test } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'
import { call, login } from './support/api'
import { openAs } from './support/coordinator-users'
import { assignEventTo, removeEquipment, removeUsers, removeVenue, resetUsers, seedEquipment, seedUsers, seedVenue } from './support/db'
import type { SeedUser } from './support/db'

const password = 'e2e-planning-only-123'
const organiser: SeedUser = { email: 'e2e_plan_org@cs.local', name: 'Planning Organiser', role: 'organiser', password }
const coordinator: SeedUser = { email: 'e2e_plan_coord@cs.local', name: 'Planning Coordinator', role: 'coordinator', password }
const staff: SeedUser = { email: 'e2e_plan_staff@cs.local', name: 'Planning Venue Staff', role: 'venue_staff', password }
const tech: SeedUser = { email: 'e2e_plan_tech@cs.local', name: 'Planning Tech', role: 'tech_support', password }
const users = [organiser, coordinator, staff, tech]
const emails = users.map((user) => user.email)
const halls = ['E2E Planning Hall A', 'E2E Planning Hall B']
const equipment = { name: 'E2E Planning Projector', category: 'Projection', total_quantity: 3 }

test.beforeAll(() => {
  seedUsers(users)
  for (const name of halls) seedVenue({ name, location: 'Test campus', capacity: 300 })
  seedEquipment(equipment)
})
test.beforeEach(() => resetUsers(emails))
// BROWSER CONTEXT ISOLATION: openAs creates separate sessions for each role.
// Close them after every test, including failures, so sessions do not accumulate.
test.afterEach(async ({ browser }) => {
  await Promise.all(browser.contexts().map((context) => context.close()))
})
test.afterAll(() => {
  removeUsers(emails)
  for (const name of halls) removeVenue(name)
  removeEquipment(equipment.name)
})

/** Create and approve an event with future dates so planning can begin. */
async function approvedEvent(request: APIRequestContext, name: string) {
  const org = await login(request, organiser.email, password)
  const coord = await login(request, coordinator.email, password)
  const year = new Date().getFullYear() + 2
  const event = await call(request, 'post', '/events', org, {
    name, purpose: 'Cross-role planning', event_type: 'conference',
    proposed_start: `${year}-11-02T09:00:00Z`, proposed_end: `${year}-11-02T17:00:00Z`,
    expected_attendance: 120, venue_requirements: 'Stage and seating',
    accessibility_needs: 'Step-free access', registration_enabled: false,
  }, 201)
  await call(request, 'post', `/events/${event.id}/submit`, org)
  assignEventTo(event.id, coordinator.email)
  await call(request, 'post', `/events/${event.id}/approve`, coord)
  return event.id as number
}

/** Add one coordinator requirement through the event page, not directly in the database. */
async function requestEquipment(page: Page, eventId: number, quantity: string) {
  await page.goto(`/coordinator/events/${eventId}`)
  await page.getByLabel('Equipment type').selectOption({ label: equipment.category })
  await page.getByLabel('Quantity needed').fill(quantity)
  await page.getByLabel('Technical notes').fill('Projector for the main session')
  await page.getByRole('button', { name: 'Add requirement' }).click()
  await expect(page.getByRole('list', { name: 'Recorded equipment requirements' })).toContainText(equipment.category)
}

/** Check that two venue decisions are independent within the same event. */
test('E15: two venue bookings remain independent when one is cancelled', async ({ browser, request }) => {
  test.setTimeout(60_000)
  const id = await approvedEvent(request, 'E2E multiple venues')
  const coord = await openAs(browser, coordinator)
  await coord.goto(`/coordinator/events/${id}`)
  for (const name of halls) await coord.getByRole('checkbox', { name: new RegExp(name) }).check()
  // One room fits its own attendance; the other is deliberately too small.
  await coord.getByLabel(`Expected attendance for ${halls[0]}`).fill('100')
  await coord.getByLabel(`Expected attendance for ${halls[1]}`).fill('400')
  await coord.getByRole('button', { name: 'Submit booking request' }).click()
  const bookings = coord.getByRole('list', { name: 'Venue bookings for this event' })
  for (const name of halls) await expect(bookings.getByRole('listitem').filter({ hasText: name })).toContainText('Pending')
  await coord.reload()
  const suitability = coord.getByRole('region', { name: 'Event venue suitability' })
  await expect(suitability.getByRole('listitem').filter({ hasText: halls[0] }).first()).toContainText('Capacity is sufficient.')
  await expect(suitability.getByRole('listitem').filter({ hasText: halls[1] }).first()).toContainText('Insufficient capacity')

  // Venue Staff decide each booking separately, even though both belong to one event.
  const venueStaff = await openAs(browser, staff)
  await venueStaff.goto('/venue-staff/bookings')
  for (const name of halls) {
    const card = venueStaff.getByRole('region').filter({ hasText: name }).filter({ hasText: 'E2E multiple venues' })
    await card.getByRole('button', { name: 'Approve', exact: true }).click()
    await expect(card).toHaveCount(0)
  }
  await coord.reload()
  for (const name of halls) await expect(bookings.getByRole('listitem').filter({ hasText: name })).toContainText('Approved')

  // Cancelling one booking must leave the other venue and the event in place.
  await coord.getByRole('button', { name: `Cancel ${halls[0]} booking` }).click()
  const dialog = coord.getByRole('dialog')
  await dialog.getByLabel('Reason (optional)').fill('Only one room is needed')
  await dialog.getByRole('button', { name: 'Yes, cancel booking' }).click()
  await expect(bookings.getByRole('listitem').filter({ hasText: halls[0] })).toContainText('Cancelled')
  await expect(bookings.getByRole('listitem').filter({ hasText: halls[1] })).toContainText('Approved')
  await expect(coord.getByRole('heading', { level: 1, name: 'E2E multiple venues' })).toBeVisible()
  await coord.reload()
  await expect(bookings.getByRole('listitem').filter({ hasText: halls[1] })).toContainText('Approved')
})

/** Check stock consumption, changed demand and an unavailable outcome across two events. */
test('E17–E19: reserved equipment reduces stock for an overlapping event', async ({ browser, request }) => {
  test.setTimeout(60_000)
  const first = await approvedEvent(request, 'E2E equipment first event')
  const second = await approvedEvent(request, 'E2E equipment overlapping event')
  const coord = await openAs(browser, coordinator)
  await requestEquipment(coord, first, '3')
  await requestEquipment(coord, second, '1')
  const techPage = await openAs(browser, tech)

  // Technical Support checks availability and reserves all three units.
  await techPage.goto(`/equipment-requirements/${first}`)
  await techPage.getByRole('button', { name: `Manage ${equipment.category} requirement` }).click()
  await techPage.getByLabel('Equipment', { exact: true }).selectOption({ label: equipment.name })
  await expect(techPage.getByRole('status', { name: 'Availability' })).toContainText('3 of 3')
  await techPage.getByRole('button', { name: 'Reserve', exact: true }).click()
  await expect(techPage.getByRole('list', { name: 'Equipment requirements' })).toContainText('Reserved')
  await coord.goto(`/coordinator/events/${first}`)
  await expect(coord.getByRole('list', { name: 'Recorded equipment requirements' })).toContainText('Reserved')

  // Increasing the requirement above what is already reserved reopens it.
  await techPage.getByLabel('Quantity needed').fill('4')
  await techPage.getByRole('button', { name: 'Save changes' }).click()
  await expect(techPage.getByRole('list', { name: 'Equipment requirements' })).toContainText('Requested')
  await coord.reload()
  await expect(coord.getByRole('list', { name: 'Recorded equipment requirements' })).toContainText('Requested')

  // A second event at the same time must not be offered the same stock.
  await techPage.goto(`/equipment-requirements/${second}`)
  await techPage.getByRole('button', { name: `Manage ${equipment.category} requirement` }).click()
  await techPage.getByLabel('Equipment', { exact: true }).selectOption({ label: equipment.name })
  await expect(techPage.getByRole('status', { name: 'Availability' })).toContainText('0 of 3')
  await expect(techPage.getByRole('button', { name: 'Reserve', exact: true })).toBeDisabled()
  await techPage.getByLabel('Status', { exact: true }).selectOption({ label: 'Unavailable' })
  await techPage.getByLabel('Reason', { exact: true }).fill('All projectors are reserved for the overlapping event')
  await techPage.getByRole('button', { name: 'Save changes' }).click()
  await coord.goto(`/coordinator/events/${second}`)
  await expect(coord.getByRole('list', { name: 'Recorded equipment requirements' })).toContainText('Unavailable')
  await expect(coord.getByRole('list', { name: 'Recorded equipment requirements' })).toContainText('All projectors are reserved')
})
