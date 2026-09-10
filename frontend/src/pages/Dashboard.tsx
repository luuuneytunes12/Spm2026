import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { useAuth } from '../auth/useAuth'
import { apiFetch } from '../lib/api'
import { ROLE_HOME_PATH, ROLE_LABELS, ROLE_PERMISSIONS } from '../lib/roles'
import { ROLE_WORKFLOWS } from '../lib/roleWorkflows'

export function Dashboard() {
  const { user } = useAuth()
  const [apiStatus, setApiStatus] = useState<'checking' | 'ok' | 'error'>('checking')

  useEffect(() => {
    apiFetch('/health')
      .then(() => setApiStatus('ok'))
      .catch(() => setApiStatus('error'))
  }, [])

  const permissionCount = user ? ROLE_PERMISSIONS[user.role]?.length ?? 0 : 0
  const plannedCount = user ? ROLE_WORKFLOWS[user.role]?.length ?? 0 : 0

  return (
    <div className="stack">
      <header className="page-header">
        <h1>Dashboard</h1>
        <p className="page-subtitle">
          {user ? `Signed in as ${user.name}.` : ''} Here's where things stand.
        </p>
      </header>

      <div className="card-grid">
        <div className="card">
          <h2>Your role</h2>
          <p className="page-subtitle">
            {user && <span className="badge badge-accent">{ROLE_LABELS[user.role]}</span>}
          </p>
          {user && (
            <p style={{ marginTop: 12 }}>
              <Link to={ROLE_HOME_PATH[user.role]}>Open your role page →</Link>
            </p>
          )}
        </div>

        <div className="card">
          <h2>Permissions</h2>
          <p className="page-subtitle">
            {permissionCount} granted to this role
          </p>
        </div>

        <div className="card">
          <h2>Backend API</h2>
          <p
            className={
              apiStatus === 'ok'
                ? 'status status-ok'
                : apiStatus === 'error'
                  ? 'status status-error'
                  : 'status'
            }
          >
            {apiStatus === 'checking' && 'Checking...'}
            {apiStatus === 'ok' && 'Connected'}
            {apiStatus === 'error' && 'Not reachable'}
          </p>
          {apiStatus === 'error' && (
            <p className="field-hint">Is the FastAPI server running on port 8000?</p>
          )}
        </div>
      </div>

      <div className="card">
        <h2>What's next</h2>
        <p className="page-subtitle" style={{ marginBottom: 14 }}>
          Authentication and role-based access are in place. The domain features
          below are not built yet — {plannedCount} planned for your role.
        </p>
        <p className="notice">
          The backend currently serves only <code>/auth/*</code> and{' '}
          <code>/health</code>. Event, venue, equipment and registration tables
          exist in the database but no endpoint serves them yet.
        </p>
      </div>
    </div>
  )
}
