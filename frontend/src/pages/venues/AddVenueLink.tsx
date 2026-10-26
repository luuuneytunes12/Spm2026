import { useContext } from 'react'
import { Link } from 'react-router'
import { AuthContext } from '../../auth/auth-context'
import { Role } from '../../lib/roles'

/** "Add a venue" for Venue Staff only (SCRUM-108). Reads the auth context
 *  directly so a page without a provider simply shows nothing. */
export function AddVenueLink() {
  const auth = useContext(AuthContext)
  if (auth?.user?.role !== Role.VENUE_STAFF) return null
  return (
    <p>
      <Link to="/venue-staff/venues/new">Add a venue</Link>
    </p>
  )
}
