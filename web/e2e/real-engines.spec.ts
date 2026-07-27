/**
 * Optional real-engine smoke (B5) — local/nightly only; not merge-blocking.
 * Requires sibling roots + LFS; start server without --fake-runners.
 *
 *   EVIDENCE_REAL_ENGINES=1 npm run test:e2e:real
 */
import { test } from '@playwright/test'

test.describe('real engines @real-engines', () => {
  test.skip(!process.env.EVIDENCE_REAL_ENGINES, 'Set EVIDENCE_REAL_ENGINES=1 for sibling+LFS runs')

  test('@real-engines placeholder — wire in B5', async () => {
    // B5 will drive bias_demo_1k / gc_full against real runners.
    test.skip(true, 'B5 optional job — not implemented in B1')
  })
})
