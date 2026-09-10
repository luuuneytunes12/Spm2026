import { Role } from '../../lib/roles'
import { ROLE_WORKFLOWS } from '../../lib/roleWorkflows'
import { RoleHome } from './RoleHome'

export function Coordinator() {
  return <RoleHome role={Role.COORDINATOR} planned={ROLE_WORKFLOWS[Role.COORDINATOR]} />
}
