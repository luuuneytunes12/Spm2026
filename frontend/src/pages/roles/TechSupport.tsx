import { Role } from '../../lib/roles'
import { ROLE_WORKFLOWS } from '../../lib/roleWorkflows'
import { RoleHome } from './RoleHome'

export function TechSupport() {
  return <RoleHome role={Role.TECH_SUPPORT} planned={ROLE_WORKFLOWS[Role.TECH_SUPPORT]} />
}
