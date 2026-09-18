// Explicit light/dark toggle. Two states only -- not a third "system"
// option -- because the request was for a toggle, and index.css already
// falls back to the OS preference on a first visit via the plain
// `prefers-color-scheme` media query. Once a visitor touches the toggle,
// their choice is remembered and wins over the OS setting from then on.

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'connectsphere.theme'

export function getStoredTheme(): Theme | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value === 'light' || value === 'dark' ? value : null
  } catch {
    return null
  }
}

export function systemTheme(): Theme {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

/** Stamp `data-theme` on <html> and remember the choice. The same logic
 *  runs inline in index.html before React mounts, so the page never
 *  flashes the wrong theme on load -- this is what keeps it in sync on
 *  every later toggle. */
export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute('data-theme', theme)
  try {
    localStorage.setItem(STORAGE_KEY, theme)
  } catch {
    // Storage unavailable (private mode, blocked cookies) -- the theme
    // still applies for this page view, it just won't be remembered.
  }
}
