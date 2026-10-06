import type { IconName } from '../components/Icon'
import { listMyEvents, listAssignedEvents } from './events'
import { listUnassignedQueue } from './coordinatorLead'
import { listMyRegistrations } from './registrations'
import { listVenueBookingQueue } from './venueBookings'
import { Role } from './roles'

export interface LandingTile {
  title: string
  description: string
  to: string
  icon: IconName
  /** Optional live number shown on the tile. A failure just hides it. */
  count?: () => Promise<number>
  /** Counts the signed-in user's unread notifications instead of calling an
   *  API -- they are already loaded for the navbar bell. */
  unreadNotifications?: boolean
}

export interface RoleLandingConfig {
  tagline: string
  tiles: LandingTile[]
}

const NOTIFICATIONS: LandingTile = {
  title: 'Notifications',
  description: 'Updates about your events and requests.',
  to: '/notifications',
  icon: 'bell',
  unreadNotifications: true,
}

const PROFILE: LandingTile = {
  title: 'My Profile',
  description: 'Your details and contact preferences.',
  to: '/profile',
  icon: 'user',
}

/** What each role sees when they sign in: where they can go, nothing more.
 *  Every `to` sits behind a RequireRole that admits that role, so no tile
 *  leads to /forbidden. */
export const ROLE_LANDING: Record<Role, RoleLandingConfig> = {
  [Role.ORGANISER]: {
    tagline: 'Create event requests and follow them through review.',
    tiles: [
      {
        title: 'New Event Request',
        description: 'Start a request. Save it as a draft and finish later.',
        to: '/organiser/events/new',
        icon: 'plus',
      },
      {
        title: 'Draft Requests',
        description: 'Requests you have not submitted yet.',
        to: '/organiser/events',
        icon: 'draft',
        count: async () => (await listMyEvents('draft')).length,
      },
      {
        title: 'Submitted Requests',
        description: 'Requests under review, approved or confirmed.',
        to: '/organiser/events?tab=submitted',
        icon: 'send',
        count: async () => (await listMyEvents()).filter((e) => e.status !== 'draft').length,
      },
      NOTIFICATIONS,
      PROFILE,
    ],
  },
  [Role.COORDINATOR]: {
    tagline: 'Review the events assigned to you and arrange their venue and equipment.',
    tiles: [
      {
        title: 'My Assigned Events',
        description: 'Review requests, book venues, confirm events and open registration.',
        to: '/coordinator/events',
        icon: 'list',
        count: async () => (await listAssignedEvents()).length,
      },
      {
        title: 'Venues',
        description: 'Search venues and check their availability.',
        to: '/venues',
        icon: 'venue',
      },
      NOTIFICATIONS,
      PROFILE,
    ],
  },
  [Role.VENUE_STAFF]: {
    tagline: 'Decide on venue booking requests from Event Coordinators.',
    tiles: [
      {
        title: 'Booking Requests',
        description: 'Approve or reject pending venue bookings.',
        to: '/venue-staff/bookings',
        icon: 'inbox',
        count: async () => (await listVenueBookingQueue()).length,
      },
      {
        title: 'Venues',
        description: 'Browse venue details and capacity.',
        to: '/venues',
        icon: 'venue',
      },
      NOTIFICATIONS,
      PROFILE,
    ],
  },
  [Role.TECH_SUPPORT]: {
    tagline: 'See the equipment available for events.',
    tiles: [
      {
        title: 'Equipment Catalogue',
        description: 'Browse equipment, stock levels and condition.',
        to: '/equipment',
        icon: 'equipment',
      },
      {
        title: 'Equipment Reservations',
        description: 'See which equipment is reserved for events.',
        to: '/equipment/reservations',
        icon: 'list',
      },
      NOTIFICATIONS,
      PROFILE,
    ],
  },
  [Role.ATTENDEE]: {
    tagline: 'Find events to attend and keep track of your place.',
    tiles: [
      {
        title: 'Events',
        description: 'Confirmed events open for registration.',
        to: '/attendee/events',
        icon: 'ticket',
      },
      {
        title: 'My Registrations',
        description: 'The events you registered for, and your status for each.',
        to: '/attendee/registrations',
        icon: 'check',
        count: async () =>
          (await listMyRegistrations()).filter((e) => e.my_status === 'registered').length,
      },
      NOTIFICATIONS,
      PROFILE,
    ],
  },
  [Role.COORDINATOR_LEAD]: {
    tagline: 'Assign Event Requests to Coordinators and oversee their assignments.',
    tiles: [
      {
        title: 'Unassigned Requests',
        description: 'Submitted Event Requests waiting for a Coordinator.',
        to: '/coordinator-lead/queue',
        icon: 'list',
        count: async () => (await listUnassignedQueue()).length,
      },
      {
        title: 'Coordinator Assignments',
        description: 'Every Coordinator and the active Events they hold.',
        to: '/coordinator-lead/assignments',
        icon: 'venue',
      },
      NOTIFICATIONS,
      PROFILE,
    ],
  },
  [Role.SAFETY_OFFICER]: {
    tagline: 'Review events for safety compliance.',
    tiles: [NOTIFICATIONS, PROFILE],
  },
}
