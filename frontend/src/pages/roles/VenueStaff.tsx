import { Role } from '../../lib/roles'
import { ROLE_WORKFLOWS } from '../../lib/roleWorkflows'
import { RoleHome } from './RoleHome'

export function VenueStaff() {
  return <RoleHome role={Role.VENUE_STAFF} planned={ROLE_WORKFLOWS[Role.VENUE_STAFF]} />
}
