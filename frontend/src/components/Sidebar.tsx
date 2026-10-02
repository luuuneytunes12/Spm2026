import { NavLink } from 'react-router'
import type { ReactNode } from 'react'
import { useAuth } from '../auth/useAuth'
import { ROLE_HOME_PATH, Role } from '../lib/roles'
import { Icon } from './Icon'
import type { IconName } from './Icon'

interface SidebarProps {
  id: string
  open: boolean
}

function Item({ to, icon, end, children }: { to: string; icon: IconName; end?: boolean; children: ReactNode }) {
  return (
    <li>
      <NavLink to={to} end={end}>
        <Icon name={icon} />
        <span>{children}</span>
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
  if (!user) return null

  return (
    <aside id={id} className="sidebar" hidden={!open}>
      <nav aria-label="Main">
        <ul className="sidebar-nav">
          <Item to={ROLE_HOME_PATH[user.role]} icon="home" end>
            Home
          </Item>
          {user.role === Role.ORGANISER && (
            <Item to="/organiser/events" icon="list">
              My Event Requests
            </Item>
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
            <Item to="/venue-staff/bookings" icon="inbox">
              Booking Requests
            </Item>
          )}
          {user.role === Role.TECH_SUPPORT && (
            <Item to="/equipment" icon="equipment">
              Equipment Catalogue
            </Item>
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
