import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 60000,
  retries: 1,
  // All manual baselines live under e2e/__screenshots__/ ; the visual-baseline
  // spec passes 'baseline/<route>' so snapshots land at
  // e2e/__screenshots__/baseline/<route>.png (no external regression service).
  snapshotPathTemplate: '{testDir}/__screenshots__/baseline/{arg}{ext}',
  use: {
    baseURL: 'http://localhost:3000',
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    storageState: 'e2e/.auth/owner.json',
  },
  projects: [
    {
      name: 'setup',
      testMatch: /auth\.setup\.ts/,
      use: { ...devices['Desktop Chrome'], storageState: { cookies: [], origins: [] } },
    },
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['setup'],
    },
  ],
});
