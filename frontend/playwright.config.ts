import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright E2E configuration for JobHunter Agent.
 *
 * - Runs against the full stack (backend + frontend) via the root start script.
 * - Uses Chromium only for speed.
 * - Screenshots captured on test failure.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: "html",

  /* Shared settings for all tests */
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  /* Per-test timeout: 30 seconds */
  timeout: 30_000,

  /* Expect assertion timeout: 60 seconds */
  expect: {
    timeout: 60_000,
  },

  /* Only run in Chromium for speed */
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  /* Tests expect the dev server to already be running (npm start from project root).
     No webServer config — start it separately to avoid test dependency. */
});
