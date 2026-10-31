import { Link, useInRouterContext } from 'react-router'
import { findReplacementPath } from '../lib/venueBookings'
import type { VenueBooking } from '../lib/venueBookings'

/** "Find replacement" for a booking marked Venue Unavailable - Action Required.
 *  A router link where there is a router, a plain link otherwise. */
export function FindReplacementLink({ booking }: { booking: VenueBooking }) {
  const inRouter = useInRouterContext()
  const to = findReplacementPath(booking)
  const label = `Find replacement for ${booking.venue.name} booking`
  return inRouter ? (
    <Link to={to} className="btn-link-accent" aria-label={label}>
      Find replacement
    </Link>
  ) : (
    <a href={to} className="btn-link-accent" aria-label={label}>
      Find replacement
    </a>
  )
}
