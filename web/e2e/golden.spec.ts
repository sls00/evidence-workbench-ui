import { expect, test, type Page } from '@playwright/test'

async function waitTerminal(page: Page) {
  await expect(page.getByTestId('finding-card')).not.toHaveAttribute('data-status', 'running', {
    timeout: 30_000,
  })
  await expect(page.getByTestId('finding-title')).toBeVisible()
}

test.describe('Slice B golden paths (fake runners)', () => {
  test('Generator bias_demo_1k → finding + pillars', async ({ page }) => {
    await page.goto('/?home=generator')
    await expect(page.getByRole('tab', { name: /Generator Console/i })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    await expect(page.getByRole('button', { name: /bias_demo_1k/i })).toBeVisible()
    const run = page.locator('[data-action="run"]')
    await expect(run).toBeEnabled()
    await run.click()
    await waitTerminal(page)
    await expect(page.getByTestId('finding-title')).not.toHaveText(/No run yet|Running/)
    await expect(page.locator('.pillars .pillar')).toHaveCount(3)
    const status = await page.getByTestId('finding-card').getAttribute('data-status')
    expect(['ok', 'qualified']).toContain(status)
    await expect(page.getByTestId('timeline-pane').locator('.timeline-row').first()).toBeVisible()
    await expect(page.getByTestId('inspect-pane').locator('.inspect-well').first()).toBeVisible()
    await expect(page.getByTestId('inspect-pane')).toContainText(/Pillars|Bias metrics/i)
    await page.getByTestId('stage-output').click()
    await expect(page.locator('.proof-deck .row:has(.noun:text("run_id")) .val')).not.toHaveText('—')
  })

  test('Validation gc_full → finding + Verify control', async ({ page }) => {
    await page.goto('/?home=validation')
    await expect(page.getByRole('tab', { name: /Validation Review/i })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    const run = page.locator('[data-action="run"]')
    await expect(run).toBeEnabled()
    await run.click()
    await waitTerminal(page)
    await expect(page.getByTestId('finding-title')).not.toHaveText(/No run yet|Running/)
    await expect(page.locator('[data-action="reverify"]')).toBeVisible()
    await expect(page.locator('[data-action="reverify"]')).toBeEnabled()
    // B2: verify chip present from terminal poll (no Re-verify click)
    await expect(page.getByTestId('verify-chip')).toContainText(/verify=/i)
    await expect(page.getByTestId('timeline-pane')).toBeVisible()
    await expect(page.getByTestId('inspect-pane')).toBeVisible()
    await page.getByTestId('stage-output').click()
    await expect(page.locator('.occ-nav button').first()).toBeVisible()
    await expect(page.locator('iframe[title="Report"]')).toBeVisible()
  })

  test('Cancel → incomplete honesty', async ({ page }) => {
    await page.goto('/?home=generator')
    const run = page.locator('[data-action="run"]')
    await expect(run).toBeEnabled()
    await run.click()
    await expect(page.getByTestId('finding-card')).toHaveAttribute('data-status', 'running')
    await page.locator('[data-action="cancel"]').click()
    await expect(page.getByTestId('finding-card')).toHaveAttribute('data-status', 'incomplete', {
      timeout: 15_000,
    })
    await expect(page.getByTestId('finding-title')).toContainText(/incomplete/i)
  })

  test('Preflight blocker → Run disabled', async ({ page }) => {
    await page.route('**/api/preflight**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'blocked',
          home: 'generator',
          can_run: false,
          checks: [
            {
              id: 'forced_blocker',
              label: 'forced blocker (e2e)',
              severity: 'blocker',
              status: 'blocker',
              error: {
                code: 'e2e_forced',
                message: 'Synthetic preflight blocker for Playwright',
                hint: 'Clear E2E mock',
              },
            },
          ],
          error: {
            code: 'e2e_forced',
            message: 'Synthetic preflight blocker for Playwright',
            hint: 'Clear E2E mock',
          },
        }),
      })
    })
    await page.goto('/?home=generator')
    await expect(page.locator('.pf').filter({ hasText: /blocker/i })).toBeVisible()
    await expect(page.locator('[data-action="run"]')).toBeDisabled()
    await expect(page.getByText(/Run disabled until preflight blockers clear/i)).toBeVisible()
  })

  test('Library reopen prior run with report', async ({ page }) => {
    await page.goto('/?home=generator')
    await page.locator('[data-action="run"]').click()
    await waitTerminal(page)
    const title = await page.getByTestId('finding-title').innerText()
    await page.getByTestId('stage-output').click()
    const runId = await page.locator('.proof-deck .val').first().innerText()
    expect(runId).not.toBe('—')

    // Clear active view then reopen from library
    await page.getByRole('tab', { name: /Validation Review/i }).click()
    await page.getByRole('tab', { name: /Generator Console/i }).click()
    // Slice D: collapse Review path so idle finding chrome is visible again
    const reviewToggle = page.getByTestId('review-path-toggle')
    if ((await reviewToggle.getAttribute('aria-expanded')) === 'true') {
      await reviewToggle.click()
    }
    await expect(page.getByTestId('finding-card')).toHaveAttribute('data-status', 'idle')

    const row = page.locator(`[data-testid="library-run"][data-run-id="${runId}"]`)
    await expect(row).toBeVisible()
    await row.click()
    await expect(page.getByTestId('finding-title')).toHaveText(title)
    await page.getByTestId('stage-output').click()
    await expect(page.locator('iframe[title="Report"]')).toBeVisible()
  })

  test('Compare two generator runs (shift+select)', async ({ page }) => {
    await page.goto('/?home=generator')
    await page.locator('[data-action="run"]').click()
    await expect(page.getByTestId('finding-card')).toHaveAttribute('data-status', 'running')
    await waitTerminal(page)
    await page.getByTestId('stage-output').click()
    const firstRunId = await page.locator('.proof-deck .row:has(.noun:text("run_id")) .val').innerText()

    // Second run with different preset (scope to Controls rail — library also has preset labels)
    await page.getByTestId('stage-manifest').click()
    await page.locator('.rail button.field', { hasText: 'rate_shock_1k' }).click()
    await page.locator('[data-action="run"]').click()
    await expect(page.getByTestId('finding-card')).toHaveAttribute('data-status', 'running')
    await waitTerminal(page)
    await page.getByTestId('stage-output').click()
    await expect
      .poll(async () => page.locator('.proof-deck .row:has(.noun:text("run_id")) .val').innerText())
      .not.toBe(firstRunId)
    const secondRunId = await page.locator('.proof-deck .row:has(.noun:text("run_id")) .val').innerText()

    const firstRow = page.locator(`[data-testid="library-run"][data-run-id="${firstRunId}"]`)
    await expect(firstRow).toBeVisible()
    await firstRow.click({ modifiers: ['Shift'] })
    await expect(firstRow).toHaveAttribute('data-compare-selected', 'true')

    const secondRow = page.locator(`[data-testid="library-run"][data-run-id="${secondRunId}"]`)
    await expect(secondRow).toBeVisible()
    await secondRow.click({ modifiers: ['Shift'] })

    await page.getByTestId('stage-manifest').click()
    await expect(page.getByTestId('compare-pane')).toBeVisible({ timeout: 10_000 })
    await expect(page.getByTestId('compare-pane')).toContainText(/validation\.json/i)
    await expect(page.locator('.compare-diff')).toContainText(/subgroup_gap_pp/)
  })
})
