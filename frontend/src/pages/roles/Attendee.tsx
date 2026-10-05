import { RoleLanding } from '../../components/RoleLanding'
import { Role } from '../../lib/roles'

export function Attendee() {
  return <RoleLanding role={Role.ATTENDEE} />
}
