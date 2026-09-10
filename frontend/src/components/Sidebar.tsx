import { NavLink } from 'react-router'
import { useAuth } from '../auth/useAuth'
import { ROLE_HOME_PATH, ROLE_LABELS } from '../lib/roles'
import { ROLE_WORKFLOWS } from '../lib/roleWorkflows'

interface SidebarProps {
  id: string
  open: boolean
}

/**
 * Primary navigation for signed-in users.
 *
 * Only routes the current user can actually reach are listed: every role
 * page is guarded by RequireRole for exactly one role, so linking to the
 * other four would just send people to /forbidden.
 *
 * The workflow entries below the navigation are deliberately rendered as
 * disabled text rather than links — those screens do not exist yet, and a
 * link that goes nowhere is worse than an honest "planned" marker.
 *
 * When collapsed it is removed from the accessibility tree and taken out
 * of the tab order via `hidden`, rather than merely hidden visually — a
 * collapsed sidebar should not be reachable by keyboard or screen reader.
 */
export function Sidebar({ id, open }: SidebarProps) {
  const { user } = useAuth()
  if (!user) return null

  const roleLabel = ROLE_LABELS[user.role] ?? user.role
  const workflows = ROLE_WORKFLOWS[user.role] ?? []

  return (
    <aside id={id} className="sidebar" hidden={!open}>
      <nav aria-label="Main">
        <ul className="sidebar-nav">
          <li>
            <NavLink to="/" end>
              Dashboard
            </NavLink>
          </li>
          <li>
            <NavLink to={ROLE_HOME_PATH[user.role]}>{roleLabel}</NavLink>
          </li>
        </ul>
      </nav>

      {workflows.length > 0 && (
        <div className="sidebar-planned">
          <h2>Planned</h2>
          <ul>
            {workflows.map((workflow) => (
              <li key={workflow.title} title={`Not yet implemented — ${workflow.description}`}>
                {workflow.title}
              </li>
            ))}
          </ul>
        </div>
      )}
    </aside>
  )
}
