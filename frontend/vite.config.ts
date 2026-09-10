/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    // Components are rendered into a simulated DOM -- no browser, no server.
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
    // Pinned to src/. Vitest's default pattern would also sweep up
    // e2e/*.spec.ts, which are Playwright specs -- those need a real browser
    // and would fail here.
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
