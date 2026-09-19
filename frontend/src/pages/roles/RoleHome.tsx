import type { ReactNode } from 'react'
import type { Role } from '../../lib/roles'
import { ROLE_LABELS, ROLE_PERMISSIONS } from '../../lib/roles'
import type { PlannedWorkflow } from '../../lib/roleWorkflows'

/** Shared presentational shell for every role landing page. Each role page
 * is a thin wrapper that supplies its own role + planned-workflow list —
 * see Organiser.tsx etc. Permissions are rendered straight from
 * ROLE_PERMISSIONS so this stays correct if that table changes; nothing
 * here is fetched from the backend, since no domain endpoints exist yet.
 *
 * `children`, when given, renders between the header and the Permissions
 * section — for a role page that has grown its own real (backend-backed)
 * controls, like the Coordinator's availability toggle, ahead of the
 * still-planned-workflow placeholders below it. */
export function RoleHome({
  role,
  planned,
  children,
}: {
  role: Role
  planned: PlannedWorkflow[]
  children?: ReactNode
}) {
  const permissions = ROLE_PERMISSIONS[role]

  return (
    <div className="stack">
      <header className="page-header">
        <h1>{ROLE_LABELS[role]}</h1>
        <p className="page-subtitle">
          What this role can do today, and what is planned for it.
        </p>
      </header>

      {children}

      <section className="card">
        <h2>Permissions</h2>
        <p className="page-subtitle" style={{ marginBottom: 14 }}>
          Granted by the role, enforced by the backend on every request.
        </p>
        <ul className="chip-list">
          {permissions.map((permission) => (
            <li key={permission} className="chip">
              {permission}
            </li>
          ))}
        </ul>
      </section>

      <section className="card">
        <h2>
          Planned <span className="badge badge-muted">not yet implemented</span>
        </h2>
        <p className="page-subtitle" style={{ marginBottom: 14 }}>
          The backend does not yet expose any event, venue, equipment or
          registration endpoints — only auth. Nothing below is real data.
        </p>
        <ul className="workflow-list">
          {planned.map((workflow) => (
            <li key={workflow.title} className="workflow">
              <span className="workflow-title">{workflow.title}</span>
              <span className="workflow-desc">{workflow.description}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
