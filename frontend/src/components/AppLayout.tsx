import { useCallback, useEffect, useState } from 'react'
import { Outlet } from 'react-router'
import { Navbar } from './Navbar'
import { Sidebar } from './Sidebar'

const SIDEBAR_KEY = 'connectsphere.sidebar'
const SIDEBAR_ID = 'app-sidebar'

/** Remembered per browser so the sidebar doesn't spring back open on every
 *  navigation or reload. Wrapped because storage throws in some contexts
 *  (private mode, blocked site data) — defaulting to open is fine there. */
function readStoredOpen(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_KEY) !== 'collapsed'
  } catch {
    return true
  }
}

/** Shell for every signed-in route: top navbar, collapsible sidebar, and
 *  the routed page. Sits inside RequireAuth, so `user` is always present. */
export function AppLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(readStoredOpen)

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_KEY, sidebarOpen ? 'open' : 'collapsed')
    } catch {
      // Non-fatal: the preference just won't persist.
    }
  }, [sidebarOpen])

  const toggleSidebar = useCallback(() => setSidebarOpen((open) => !open), [])

  return (
    <div className="app-layout">
      <Navbar
        sidebarOpen={sidebarOpen}
        onToggleSidebar={toggleSidebar}
        sidebarId={SIDEBAR_ID}
      />
      <div className="app-shell">
        <Sidebar id={SIDEBAR_ID} open={sidebarOpen} />
        <main className="app-main">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
