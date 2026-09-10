import { Role } from './roles'

export interface PlannedWorkflow {
  /** Short label — also used as the sidebar entry. */
  title: string
  /** One line on what the workflow does, naming the backing table(s). */
  description: string
}

/**
 * The workflows each role will own, once the backend serves them.
 *
 * Everything still listed here is PLANNED — remove an entry once its
 * screens ship, or the sidebar keeps rendering it as disabled text.
 * ("Create events" was the first to go: the Organiser draft/submit flow
 * now lives at /organiser/events.)
 *
 * The backend currently serves auth (`/auth/*`), `/health` and `/events`;
 * the venues, equipment and registration tables exist in the database but
 * no endpoint serves them. Both the role landing pages and the sidebar
 * render these as explicitly "planned", so this file is the single place
 * to edit when a workflow becomes real — update it here and both surfaces
 * follow.
 */
export const ROLE_WORKFLOWS: Record<Role, PlannedWorkflow[]> = {
  [Role.ORGANISER]: [
    {
      title: 'Review submissions',
      description: 'approve or reject submitted events (events, event_status_history).',
    },
    {
      title: 'Change requests',
      description: 'rule on requested changes to approved events (event_change_requests).',
    },
    { title: 'Oversight', description: 'full visibility across every venue, booking and request.' },
  ],
  [Role.COORDINATOR]: [
    { title: 'My events', description: 'plan and update the events assigned to you (events).' },
    { title: 'Book venues', description: 'request a venue for an event (venue_bookings).' },
    {
      title: 'Registrations',
      description: 'view and manage attendee registrations (registrations).',
    },
    {
      title: 'Request equipment',
      description: 'raise equipment requests for an event (equipment_requests).',
    },
  ],
  [Role.VENUE_STAFF]: [
    { title: 'Venues', description: 'create and update venue records (venues).' },
    {
      title: 'Booking requests',
      description: 'approve or reject requests against your venues (venue_bookings).',
    },
    {
      title: 'Unavailability',
      description: 'block out dates a venue cannot be booked (venue_unavailability).',
    },
  ],
  [Role.TECH_SUPPORT]: [
    { title: 'Equipment', description: 'maintain the equipment inventory (equipment).' },
    {
      title: 'Equipment requests',
      description: 'review, reserve or reject requests (equipment_requests).',
    },
    { title: 'Event schedule', description: 'see which events need technical support (events).' },
  ],
  [Role.ATTENDEE]: [
    { title: 'Browse events', description: 'see approved, upcoming events (events).' },
    {
      title: 'My registrations',
      description: 'register for an event or withdraw (registrations).',
    },
    { title: 'Notifications', description: 'updates about events you registered for (notifications).' },
  ],
}
