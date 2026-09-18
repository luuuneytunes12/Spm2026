import { useEffect, useState } from 'react'
import { applyTheme, getStoredTheme, systemTheme } from '../lib/theme'
import type { Theme } from '../lib/theme'

/** Sun/moon toggle between light and dark. Initial state reads whatever
 *  index.html's inline script already stamped onto <html> (a stored
 *  choice, or the OS preference) so this never fights that first paint. */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() => getStoredTheme() ?? systemTheme())

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  const next = theme === 'dark' ? 'light' : 'dark'

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={() => setTheme(next)}
      aria-label={`Switch to ${next} mode`}
      title={`Switch to ${next} mode`}
    >
      {theme === 'dark' ? (
        // Sun -- shown while dark is active, offering to switch to light.
        <svg viewBox="0 0 20 20" width="17" height="17" aria-hidden="true">
          <circle cx="10" cy="10" r="4" fill="currentColor" />
          <g stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <path d="M10 1.5v2M10 16.5v2M18.5 10h-2M3.5 10h-2" />
            <path d="M15.66 4.34l-1.42 1.42M5.76 14.24l-1.42 1.42M15.66 15.66l-1.42-1.42M5.76 5.76 4.34 4.34" />
          </g>
        </svg>
      ) : (
        // Moon -- shown while light is active, offering to switch to dark.
        <svg viewBox="0 0 20 20" width="17" height="17" aria-hidden="true">
          <path
            fill="currentColor"
            d="M17.3 12.6a7.3 7.3 0 0 1-9.9-9.9 7.8 7.8 0 1 0 9.9 9.9Z"
          />
        </svg>
      )}
    </button>
  )
}
