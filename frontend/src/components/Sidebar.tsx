import { NavLink, useLocation } from 'react-router'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useAuth } from '../auth/useAuth'
import { ROLE_HOME_PATH, Role } from '../lib/roles'
import { listFlaggedBookings, listVenueBookingQueue } from '../lib/venueBookings'
import { Icon } from './Icon'
import type { IconName } from './Icon'

interface SidebarProps {
  id: string
  open: boolean
}

/** Event the Booking Requests page fires when the queue changes, so the
 *  sidebar count follows decisions without a reload. */
export const VENUE_QUEUE_CHANGED = 'venue-queue-changed'

/** Number of requests waiting in the Venue Staff queue (null until known or
 *  when it cannot be loaded -- the badge is simply left out). */
function usePendingRequestCount(enabled: boolean) {
  const [count, setCount] = useState<number | null>(null)
  const { pathname } = useLocation()
  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    const load = () =>
      Promise.resolve()
        .then(() =>
          Promise.all([
            listVenueBookingQueue(),
            Promise.resolve()
              .then(listFlaggedBookings)
              .catch(() => []),
          ]),
        )
        .then(([q, f]) => !cancelled && setCount(q.length + f.length))
        .catch(() => !cancelled && setCount(null))
    load()
    window.addEventListener(VENUE_QUEUE_CHANGED, load)
    return () => {
      cancelled = true
      window.removeEventListener(VENUE_QUEUE_CHANGED, load)
    }
  }, [enabled, pathname])
  return count
}

function Item({
  to,
  icon,
  end,
  count,
  children,
}: {
  to: string
  icon: IconName
  end?: boolean
  count?: number | null
  children: ReactNode
}) {
  return (
    <li>
      <NavLink to={to} end={end}>
        <Icon name={icon} />
        <span>{children}</span>
        {count ? (
          <span className="nav-count" aria-label={`${count} pending`}>
            {count}
          </span>
        ) : null}
      </NavLink>
    </li>
  )
}

/**
 * Primary navigation for signed-in users.
 *
 * Only routes the current user can actually reach are listed: every role
 * page is guarded by RequireRole for exactly one role, so linking to the
 * other four would just send people to /forbidden. "Home" is the role's own
 * landing page, which is also where signing in lands.
 *
 * When collapsed it is removed from the accessibility tree and taken out
 * of the tab order via `hidden`, rather than merely hidden visually — a
 * collapsed sidebar should not be reachable by keyboard or screen reader.
 */
export function Sidebar({ id, open }: SidebarProps) {
  const { user } = useAuth()
  const pendingRequests = usePendingRequestCount(user?.role === Role.VENUE_STAFF)
  if (!user) return null

  return (
    <aside id={id} className="sidebar" hidden={!open}>
      <nav aria-label="Main">
        <ul className="sidebar-nav">
          {user.role !== Role.SAFETY_OFFICER && (
            <Item to={ROLE_HOME_PATH[user.role]} icon="home" end>
              Home
            </Item>
          )}

          {user.role === Role.ORGANISER && (
            <Item to="/organiser/events" icon="list">
              My Event Requests
            </Item>
          )}
          {user.role === Role.COORDINATOR_LEAD && (
            <>
              <Item to="/coordinator-lead/queue" icon="inbox">
                Unassigned Requests
              </Item>
              <Item to="/coordinator-lead/assignments" icon="list">
                Coordinator Assignments
              </Item>
            </>
          )}
          {user.role === Role.COORDINATOR && (
            <Item to="/coordinator/events" icon="list">
              My Assigned Events
            </Item>
          )}
          {(user.role === Role.COORDINATOR || user.role === Role.VENUE_STAFF) && (
            <Item to="/venues" icon="venue">
              Venues
            </Item>
          )}
          {user.role === Role.VENUE_STAFF && (
            <>
              <Item to="/venue-staff/bookings" icon="inbox" count={pendingRequests}>
                Booking Requests
              </Item>
            </>
          )}
          {user.role === Role.TECH_SUPPORT && (
            <>
              <Item to="/equipment" icon="equipment" end>
                Equipment Catalogue
              </Item>
              <Item to="/equipment-requirements" icon="list">
                Equipment Requirements
              </Item>
              <Item to="/equipment/reservations" icon="list">
                Equipment Reservations
              </Item>
            </>
          )}
          {user.role === Role.ATTENDEE && (
            <>
              <Item to="/attendee/events" icon="ticket">
                Events
              </Item>
              <Item to="/attendee/registrations" icon="check">
                My Registrations
              </Item>
            </>
          )}
          {user.role === Role.SAFETY_OFFICER && (
            <Item to="/safety-checks" icon="check">
              Safety Checks
            </Item>
          )}

          <Item to="/notifications" icon="bell">
            Notifications
          </Item>
          <Item to="/profile" icon="user">
            My Profile
          </Item>
        </ul>
      </nav>
    </aside>
  )
}
