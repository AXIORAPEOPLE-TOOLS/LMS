import { defineConfig, devices } from '@playwright/test'

/**
 * End-to-end tests. Run before every push:  cd test/e2e && pnpm test
 * Starts its own backend (fresh SQLite + demo company, offline services) and the frontend dev server.
 */
const API_PORT = 8001
const WEB_PORT = 5174

export default defineConfig({
  testDir: './tests',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false, // tests share one seeded database
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: 'retain-on-failure',
    screenshot: 'off',
  },
  projects: [
    { name: 'phone', use: { ...devices['Pixel 7'], viewport: { width: 360, height: 780 } } },
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: [
    {
      command: `python start_backend.py ${API_PORT}`,
      url: `http://localhost:${API_PORT}/api/health/live`,
      timeout: 180_000,
      reuseExistingServer: false,
      stdout: 'pipe',
    },
    {
      command: `pnpm --dir ../../frontend exec vite --port ${WEB_PORT} --strictPort`,
      url: `http://localhost:${WEB_PORT}`,
      timeout: 120_000,
      reuseExistingServer: false,
      env: { VITE_API_PROXY: `http://localhost:${API_PORT}` },
    },
  ],
})
