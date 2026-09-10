import { Link } from 'react-router'

export function Forbidden() {
  return (
    <div className="auth-screen">
      <div className="auth-card">
        <p className="auth-brand">403</p>
        <h1>No access</h1>
        <p className="auth-intro">
          This page belongs to a different role. If you think that's wrong, ask
          an Event Organiser to check your account's role.
        </p>
        <p className="auth-footer" style={{ borderTop: 'none', paddingTop: 0 }}>
          <Link to="/">Back to dashboard</Link>
        </p>
      </div>
    </div>
  )
}
