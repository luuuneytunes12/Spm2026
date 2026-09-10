import { Role } from '../../lib/roles'
import { ROLE_WORKFLOWS } from '../../lib/roleWorkflows'
import { RoleHome } from './RoleHome'

export function Attendee() {
  return <RoleHome role={Role.ATTENDEE} planned={ROLE_WORKFLOWS[Role.ATTENDEE]} />
}
