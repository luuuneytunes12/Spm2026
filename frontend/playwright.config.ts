import { defineConfig, devices } from '@playwright/test'

/**
 * End-to-end config. Unlike the Vitest suite, these specs drive a real
 * browser against a real backend and a real database -- so they need both
 * servers running, which `webServer` below starts for us.
 *
 * See docs/test-cases-organiser-event-requests.md for what each spec covers.
 */

// The throwaway database these tests write to.
//
// Hardcoded to localhost on purpose: this must NEVER be the team's Supabase
// project. In CI a `postgres:16` service container answers on this exact
// address, so one value works identically on a laptop and on GitHub with no
// environment variable at all. The credentials are not a secret -- they
// belong to a container that is destroyed after every run -- which is why
// this file is safe to commit.
const E2E_DATABASE_URL =
  process.env.E2E_DATABASE_URL ??
  'postgresql+psycopg://postgres:postgres@localhost:5432/connectsphere_test'

// Belt and braces: if someone overrides the variable, refuse anything that
// is not local. Writing test events into the database used for demos is
// exactly the accident worth failing loudly to prevent.
if (!/@(localhost|127\.0\.0\.1)[:/]/.test(E2E_DATABASE_URL)) {
  throw new Error(
    `Refusing to run end-to-end tests against a non-local database.\n` +
      `  E2E_DATABASE_URL = ${E2E_DATABASE_URL}\n` +
      `These tests create and delete event requests. Point them at a ` +
      `disposable local postgres, never the shared Supabase project.`,
  )
}

/** Credentials for the organiser account the CI workflow seeds. */
export const E2E_ORGANISER = {
  email: 'e2e_organiser@cs.local',
  password: 'e2e-password-123',
}

export default defineConfig({
  testDir: './e2e',
  // Kept out of tsconfig.app.json (which includes only src/), so `npm run
  // build` is unaffected -- Playwright transpiles these specs itself.
  fullyParallel: false, // specs share one database; run them in order
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [['html', { open: 'never' }], ['list']],

  use: {
    baseURL: 'http://localhost:5173',
    // Kept on failure only -- a trace per passing test would bloat the
    // artifact for no benefit.
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },

  // Chromium alone. Three browsers would triple the runtime while testing
  // our own application logic three times over, which is not where the risk
  // in this project lies.
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],

  webServer: [
    {
      // DATABASE_URL is passed explicitly so the backend never falls back to
      // backend/.env -- environment variables outrank the .env file in
      // pydantic-settings, which is what makes this override reliable.
      command: 'uv run uvicorn app.main:app --port 8000',
      cwd: '../backend',
      url: 'http://localhost:8000/health',
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        DATABASE_URL: E2E_DATABASE_URL,
        JWT_SECRET: 'e2e-not-a-real-secret',
        CORS_ORIGINS: 'http://localhost:5173',
      },
    },
    {
      command: 'npm run dev -- --port 5173',
      url: 'http://localhost:5173',
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: { VITE_API_URL: 'http://localhost:8000' },
    },
  ],
})
