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
 * now lives at /organiser/events. "My events" followed it: the Coordinator
 * now reads their assigned events at /coordinator/events. The Attendee's
 * "Browse events" and "My registrations" became one page at
 * /attendee/events. Coordinators and Venue Staff view venues at /venues.
 * Venue Staff's "Decide on booking requests" went when approving and
 * rejecting shipped at /venue-staff/bookings. The Coordinator's "Request
 * equipment" went when recording equipment requirements shipped, as a card
 * on the assigned-event page. Technical Support's "Equipment requests"
 * stays: it describes reviewing and reserving, which has not shipped --
 * Technical Support can only READ requirements so far.)
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
    { title: 'Book venues', description: 'request a venue for an event (venue_bookings).' },
    {
      title: 'Registrations',
      description: 'view and manage attendee registrations (registrations).',
    },
  ],
  [Role.VENUE_STAFF]: [
    {
      // Renamed, NOT removed, when "View Venue Details" shipped at /venues.
      // That page is read-only; creating and editing venues still has no
      // screen.
      title: 'Manage venues',
      description: 'create and update venue records (venues).',
    },
    {
      title: 'Unavailability',
      description: 'block out dates a venue cannot be booked (venue_unavailability).',
    },
  ],
  [Role.TECH_SUPPORT]: [
    {
      // Renamed, NOT removed, when the catalogue shipped. "View Equipment
      // Catalogue" is read-only; adding, editing and retiring items is
      // EQUIPMENT_MANAGE and still has no screen, so this entry has to
      // keep saying so rather than disappear as if it were done.
      title: 'Manage equipment',
      description: 'add, update and retire inventory items (equipment).',
    },
    {
      title: 'Equipment requests',
      description: 'review, reserve or reject requests (equipment_requests).',
    },
    { title: 'Event schedule', description: 'see which events need technical support (events).' },
  ],
  [Role.ATTENDEE]: [
    { title: 'Notifications', description: 'updates about events you registered for (notifications).' },
  ],
}
