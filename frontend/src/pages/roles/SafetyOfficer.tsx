import { Role } from '../../lib/roles'
import { ROLE_WORKFLOWS } from '../../lib/roleWorkflows'
import { RoleHome } from './RoleHome'

export function SafetyOfficer() {
  return <RoleHome role={Role.SAFETY_OFFICER} planned={ROLE_WORKFLOWS[Role.SAFETY_OFFICER]} />
}
