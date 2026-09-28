// Adds the DOM matchers (toBeInTheDocument, toHaveAttribute, toBeVisible...)
// to Vitest's expect. Loaded once for every test file via
// `setupFiles` in vite.config.ts.
import '@testing-library/jest-dom/vitest'

// jsdom implements no layout, so Element.prototype.scrollIntoView does not
// exist and calling it throws. Any component that moves the user to an
// error needs it stubbed rather than guarded in production code.
Element.prototype.scrollIntoView = vi.fn()
