import { defineConfig, devices } from "@playwright/test";

/**
 * Smoke suite against the local dev server and the live seeded Mongo data.
 * Port 3100 keeps clear of the long-running dev server on 3000; with
 * reuseExistingServer you can also pre-start `npm run dev -- -p 3100` and
 * iterate without Playwright cycling the server.
 */
const PORT = Number(process.env.WEB_TEST_PORT ?? 3100);

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  reporter: [["list"]],
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  use: {
    baseURL: process.env.BASE_URL ?? `http://localhost:${PORT}`,
  },
  webServer: {
    command: `npm run dev -- -p ${PORT}`,
    url: `http://localhost:${PORT}/waivers`,
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
