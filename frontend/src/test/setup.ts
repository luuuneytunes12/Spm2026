// Adds the DOM matchers (toBeInTheDocument, toHaveAttribute, toBeVisible...)
// to Vitest's expect. Loaded once for every test file via
// `setupFiles` in vite.config.ts.
import '@testing-library/jest-dom/vitest'
