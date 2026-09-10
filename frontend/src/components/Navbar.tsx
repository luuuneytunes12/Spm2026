import { useAuth } from '../auth/useAuth'
import { ROLE_LABELS } from '../lib/roles'

/** First letter of the first two words, e.g. "Wei Lunn" -> "WL".
 *  Decorative only — the full name sits beside it. */
function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
}

interface NavbarProps {
  sidebarOpen: boolean
  onToggleSidebar: () => void
  /** id of the element the toggle controls, for aria-controls */
  sidebarId: string
}

/** Top bar: sidebar toggle and app name on the left, signed-in user on the
 *  right. Rendered inside RequireAuth, so `user` is present. */
export function Navbar({ sidebarOpen, onToggleSidebar, sidebarId }: NavbarProps) {
  const { user, logout } = useAuth()

  return (
    <header className="navbar">
      <div className="navbar-left">
        <button
          type="button"
          className="navbar-toggle"
          onClick={onToggleSidebar}
          aria-expanded={sidebarOpen}
          aria-controls={sidebarId}
          aria-label={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
        >
          {/* Decorative bars; the accessible name comes from aria-label. */}
          <span className="navbar-toggle-bars" aria-hidden="true" />
        </button>
        <span className="navbar-brand">ConnectSphere</span>
      </div>

      {user && (
        <div className="navbar-user">
          <span className="navbar-avatar" aria-hidden="true">
            {initials(user.name)}
          </span>
          <span className="navbar-user-text">
            <span className="navbar-user-name">{user.name}</span>
            <span className="navbar-user-role">{ROLE_LABELS[user.role] ?? user.role}</span>
          </span>
          <button type="button" className="navbar-logout" onClick={() => void logout()}>
            Log out
          </button>
        </div>
      )}
    </header>
  )
}
