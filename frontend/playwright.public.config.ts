import { defineConfig, devices } from '@playwright/test';

// Temporary public-only config (no auth-setup dependency) so public routes can be
// validated and baselines regenerated without a running backend. Add spec files with
// `-g` or run the whole dir: this config only matches public specs by default.
export default defineConfig({
  testDir: './e2e',
  timeout: 60000,
  retries: 0,
  snapshotPathTemplate: '{testDir}/__screenshots__/baseline/{arg}{ext}',
  use: {
    baseURL: 'http://localhost:3000',
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'public',
      testMatch: /landing\.spec\.ts|navigation\.spec\.ts|visual-baseline\.spec\.ts/,
      use: {
        ...devices['Desktop Chrome'],
        storageState: { cookies: [], origins: [] },
      },
    },
  ],
});
