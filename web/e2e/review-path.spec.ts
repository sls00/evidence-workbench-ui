import { expect, test, type Page } from '@playwright/test'

async function waitTerminal(page: Page) {
  await expect(page.getByTestId('finding-card')).not.toHaveAttribute('data-status', 'running', {
    timeout: 30_000,
  })
  await expect(page.getByTestId('finding-title')).toBeVisible()
}

async function clearReviewDismiss(page: Page) {
  // Clear once via evaluate after first navigation — do NOT use addInitScript
  // (it would wipe dismiss again on reload).
  await page.goto('/?home=generator')
  await page.evaluate(() => {
    try {
      localStorage.removeItem('ew.reviewPath.dismissed.generator')
      localStorage.removeItem('ew.reviewPath.dismissed.validation')
    } catch {
      /* ignore */
    }
  })
}

test.describe('Slice D Review path', () => {
  test('Generator: first visit open → Hide persists → ? reopens → run advances past Run', async ({
    page,
  }) => {
    await clearReviewDismiss(page)
    await page.goto('/?home=generator')
    await expect(page.getByTestId('review-path-toggle')).toHaveAttribute('aria-expanded', 'true')
    await expect(page.getByTestId('review-path-body')).toBeVisible()
    await expect(page.getByTestId('review-path-lead')).toContainText(/Generator —/)
    await expect(page.getByTestId('finding-card')).toHaveCount(0)

    const runStep = page.locator('[data-testid="review-path-steps"] [data-step-id="run"]')
    await expect(runStep).toHaveAttribute('data-state', 'current')

    await page.getByTestId('review-path-toggle').click()
    await expect(page.getByTestId('review-path-toggle')).toHaveAttribute('aria-expanded', 'false')
    await expect(page.getByTestId('review-path-body')).toHaveCount(0)
    await expect(page.getByTestId('finding-card')).toHaveAttribute('data-status', 'idle')

    await page.reload()
    await expect(page.getByTestId('review-path-toggle')).toHaveAttribute('aria-expanded', 'false')

    await page.keyboard.press('?')
    await expect(page.getByTestId('review-path-toggle')).toHaveAttribute('aria-expanded', 'true')
    await expect(page.getByTestId('review-path-body')).toBeVisible()

    const run = page.locator('[data-action="run"]')
    await expect(run).toBeEnabled()
    await run.click()
    await waitTerminal(page)
    await expect(runStep).toHaveAttribute('data-state', 'done')
    await expect(page.locator('[data-testid="review-path-steps"] [data-step-id="finding"]')).toHaveAttribute(
      'data-state',
      'done',
    )
    await expect(page.getByTestId('review-path-lead')).toContainText(/Path complete/)
  })

  test('Validation: open / Hide / ? / gc_full advances toward verify', async ({ page }) => {
    await clearReviewDismiss(page)
    await page.goto('/?home=validation')
    await expect(page.getByTestId('review-path-toggle')).toHaveAttribute('aria-expanded', 'true')
    await expect(page.getByTestId('review-path-lead')).toContainText(/Validation —/)

    await page.getByTestId('review-path-toggle').click()
    await expect(page.getByTestId('review-path-body')).toHaveCount(0)
    await page.keyboard.press('?')
    await expect(page.getByTestId('review-path-body')).toBeVisible()

    const run = page.locator('[data-action="run"]')
    await expect(run).toBeEnabled()
    await run.click()
    await waitTerminal(page)
    await expect(page.locator('[data-testid="review-path-steps"] [data-step-id="run"]')).toHaveAttribute(
      'data-state',
      'done',
    )
    const verify = page.locator('[data-testid="review-path-steps"] [data-step-id="verify"]')
    await expect(verify).toHaveAttribute('data-state', /done|current/)
  })
})
