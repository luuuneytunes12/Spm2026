/**
 * E2E SEARCH: CHANGE REQUEST, APPROVAL, REJECTION, CANCELLATION, RESOURCE RELEASE, NOTIFICATIONS
 *
 * Organiser change requests and coordinator cancellation (E26–E29).
 *
 * Each test starts with a submitted event assigned to its coordinator in the
 * disposable database. The change request, decision and cancellation are
 * performed through the real UI and checked from both people's perspectives.
 * These journeys complement the PostgreSQL integration tests for resource
 * release and concurrent writes; they do not replace those transaction tests.
 */
import { expect, test } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'
import { call, login } from './support/api'
import { openAs } from './support/coordinator-users'
import { assignEventTo, removeEquipment, removeUsers, removeVenue, resetUsers, seedEquipment, seedUsers, seedVenue } from './support/db'
import type { SeedUser } from './support/db'

const password = 'e2e-change-only-123'
const organiser: SeedUser = { email: 'e2e_change_org@cs.local', name: 'Change Organiser', role: 'organiser', password }
const coordinator: SeedUser = { email: 'e2e_change_coord@cs.local', name: 'Change Coordinator', role: 'coordinator', password }
const venueStaff: SeedUser = { email: 'e2e_change_staff@cs.local', name: 'Change Venue Staff', role: 'venue_staff', password }
const tech: SeedUser = { email: 'e2e_change_tech@cs.local', name: 'Change Tech', role: 'tech_support', password }
const users = [organiser, coordinator, venueStaff, tech]
const emails = users.map((user) => user.email)
const venue = { name: 'E2E Cancellation Hall', location: 'Test campus', capacity: 300 }
const item = { name: 'E2E Cancellation Projector', category: 'Projection', total_quantity: 3 }
let itemId = 0

// These cases create separate user sessions and can be slower on CI runners.
test.setTimeout(60_000)
test.beforeAll(() => { seedUsers(users); seedVenue(venue); itemId = seedEquipment(item) })
test.beforeEach(() => resetUsers(emails))
// BROWSER CONTEXT ISOLATION: openAs creates separate sessions for each role.
// Close them after every test, including failures, so sessions do not accumulate.
test.afterEach(async ({ browser }) => {
  await Promise.all(browser.contexts().map((context) => context.close()))
})
test.afterAll(() => { removeUsers(emails); removeVenue(venue.name); removeEquipment(item.name) })

/** Create the prerequisite submitted event and assign it to this test's coordinator. */
async function submittedEvent(request: APIRequestContext, name: string) {
  const headers = await login(request, organiser.email, password)
  const year = new Date().getFullYear() + 2
  const event = await call(request, 'post', '/events', headers, {
    name, purpose: 'Original purpose', event_type: 'conference',
    proposed_start: `${year}-11-02T09:00:00Z`, proposed_end: `${year}-11-02T17:00:00Z`,
    expected_attendance: 120, venue_requirements: 'Main hall',
    accessibility_needs: 'Step-free access', registration_enabled: false,
  }, 201)
  await call(request, 'post', `/events/${event.id}/submit`, headers)
  assignEventTo(event.id, coordinator.email)
  return event.id as number
}

/** Propose a changed purpose and verify it remains pending until reviewed. */
async function requestPurposeChange(page: Page, eventId: number, proposed: string) {
  await page.goto(`/organiser/events/${eventId}/edit`)
  await page.getByLabel('Purpose').fill(proposed)
  await page.getByRole('button', { name: 'Request changes' }).click()
  const dialog = page.getByRole('dialog', { name: 'Submit change request?' })
  await dialog.getByRole('button', { name: 'Submit change request' }).click()
  await expect(dialog.getByRole('alert')).toContainText('explain')
  await dialog.getByLabel('Reason for change').fill('The organiser revised the programme')
  await dialog.getByRole('button', { name: 'Submit change request' }).click()
  await expect(page.getByRole('list', { name: 'Change requests' })).toContainText('Pending')
  await expect(page.getByText('Original purpose', { exact: true })).toBeVisible()
  // A second proposal is not offered while the first one awaits review.
  await expect(page.getByRole('link', { name: 'Request changes' })).toHaveCount(0)
}

// The same user journey has two possible coordinator decisions; run both.
for (const decision of ['approve', 'reject'] as const) {
  test(`E26: ${decision} a proposed change and show the organiser the result`, async ({ browser, request }) => {
    const id = await submittedEvent(request, `E2E change ${decision}`)
    const org = await openAs(browser, organiser)
    await requestPurposeChange(org, id, 'Updated purpose')
    const coord = await openAs(browser, coordinator)
    await coord.goto(`/coordinator/events/${id}`)
    const proposal = coord.getByRole('article').filter({ hasText: 'Pending change request' })
    await expect(proposal).toContainText('Updated purpose')
    await expect(coord.getByRole('button', { name: 'Approve request' })).toBeDisabled()
    await proposal.getByLabel('Review notes').fill('Coordinator reviewed the proposal')
    await proposal.getByRole('button', { name: decision === 'approve' ? 'Approve changes' : 'Reject changes' }).click()
    await expect(coord.getByRole('article').filter({ hasText: `${decision === 'approve' ? 'Approved' : 'Rejected'} change request` })).toBeVisible()

    // Approval changes the event; rejection leaves its original value intact.
    await org.reload()
    await expect(org.getByRole('list', { name: 'Change requests' })).toContainText(decision === 'approve' ? 'Approved' : 'Rejected')
    await expect(org.getByText(decision === 'approve' ? 'Updated purpose' : 'Original purpose', { exact: true }).first()).toBeVisible()
    await org.goto('/notifications')
    await expect(org.getByText(new RegExp(`requested changes.*${decision === 'approve' ? 'approved' : 'rejected'}`, 'i')).first()).toBeVisible()
  })
}

/** Verify cancellation from the screen and the release of both resource types. */
test('E29: cancellation needs a reason, releases arrangements, and is visible to the organiser', async ({ browser, request }) => {
  const id = await submittedEvent(request, 'E2E cancellation')
  const coordToken = await login(request, coordinator.email, password)
  const staffToken = await login(request, venueStaff.email, password)
  const techToken = await login(request, tech.email, password)
  await call(request, 'post', `/events/${id}/approve`, coordToken)
  const venues = await call(request, 'get', '/venues', coordToken)
  const selected = venues.find((entry: { name: string }) => entry.name === venue.name)
  const bookings = await call(request, 'post', `/venue-bookings/events/${id}`, coordToken, { venues: [{ venue_id: selected.id }] }, 201)
  await call(request, 'post', `/venue-bookings/${bookings[0].id}/approve`, staffToken)
  // Prepare a real reservation, then prove cancellation changes the visible state.
  await call(request, 'post', `/equipment-requirements/events/${id}`, coordToken, { category: item.category, quantity_needed: 2, technical_notes: null }, 201)
  const requirements = await call(request, 'get', `/equipment-requirements/events/${id}`, coordToken)
  const requirementId = requirements.find((entry: { category: string }) => entry.category === item.category).id
  await call(request, 'post', `/equipment-requirements/${requirementId}/reservations`, techToken, { equipment_id: itemId, quantity: 2 })
  const year = new Date().getFullYear() + 2
  const query = new URLSearchParams({ equipment_id: String(itemId), start: `${year}-11-02T09:00:00Z`, end: `${year}-11-02T17:00:00Z` })
  expect((await call(request, 'get', `/equipment-reservations/availability?${query}`, techToken)).available_quantity).toBe(1)
  const coord = await openAs(browser, coordinator)
  await coord.goto(`/coordinator/events/${id}`)
  const cancel = coord.getByRole('button', { name: 'Cancel event' })
  await expect(cancel).toBeDisabled()
  await coord.getByLabel('Cancellation reason').fill('The organiser can no longer proceed')
  await cancel.click()
  await expect(coord.getByText('Event Cancelled').first()).toBeVisible()
  // The cancelled event no longer occupies either resource in the backend.
  const updatedBookings = await call(request, 'get', `/venue-bookings/events/${id}`, coordToken)
  // Event cancellation releases a booking; cancelling one booking directly
  // uses a separate Cancelled status. Both leave the venue available.
  expect(updatedBookings.find((booking: { id: number }) => booking.id === bookings[0].id).status).toBe('released')
  expect((await call(request, 'get', `/equipment-reservations/availability?${query}`, techToken)).available_quantity).toBe(3)
  const org = await openAs(browser, organiser)
  await org.goto(`/organiser/events/${id}`)
  await expect(org.getByText('Event Cancelled').first()).toBeVisible()
  await expect(org.getByRole('list', { name: 'Activity log' })).toContainText('The organiser can no longer proceed')
})
