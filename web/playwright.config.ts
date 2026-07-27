import { defineConfig, devices } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const port = Number(process.env.EVIDENCE_E2E_PORT || 8766)
const baseURL = `http://127.0.0.1:${port}`
const runsRoot = path.join(root, '.evidence-runs-e2e')

/**
 * Default CI: fake runners only (no LFS / sibling engines).
 * Optional @real-engines project is local/nightly — not merge-blocking (B5).
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [['list'], ['github']] : 'list',
  timeout: 60_000,
  expect: { timeout: 20_000 },
  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium-fake',
      use: { ...devices['Desktop Chrome'] },
      testIgnore: /real-engines/,
    },
    {
      name: 'chromium-real',
      use: { ...devices['Desktop Chrome'] },
      testMatch: /real-engines/,
      grep: /@real-engines/,
    },
  ],
  webServer: {
    command: `uv run evidence-workbench --host 127.0.0.1 --port ${port} --fake-runners`,
    cwd: root,
    url: `${baseURL}/api/health`,
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      ...process.env,
      EVIDENCE_FAKE_RUNNERS: '1',
      EVIDENCE_FAKE_RUNNER_DELAY: process.env.EVIDENCE_FAKE_RUNNER_DELAY || '2.5',
      EVIDENCE_RUNS_ROOT: process.env.EVIDENCE_RUNS_ROOT || runsRoot,
    },
  },
})
