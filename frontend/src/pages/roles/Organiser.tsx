import { Role } from '../../lib/roles'
import { ROLE_WORKFLOWS } from '../../lib/roleWorkflows'
import { RoleHome } from './RoleHome'

export function Organiser() {
  return <RoleHome role={Role.ORGANISER} planned={ROLE_WORKFLOWS[Role.ORGANISER]} />
}
