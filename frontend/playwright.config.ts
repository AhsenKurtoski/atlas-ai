import { defineConfig } from '@playwright/test';

/**
 * Smoke test E2E della build web: utilizza il backend già avviato su 8010 e
 * serve l'export statico di Expo su 19007. In CI il backend viene avviato dal
 * workflow prima di Playwright.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:19007',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'npx serve@14 dist -l 19007',
    url: 'http://127.0.0.1:19007/',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
