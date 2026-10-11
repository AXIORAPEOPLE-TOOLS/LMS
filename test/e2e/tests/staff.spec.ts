import { expect, test } from '@playwright/test'
import { expectNoHorizontalScroll, signIn } from './helpers'

test.describe('Manager', () => {
  test('team at a glance with heatmap and nudge', async ({ page }) => {
    await signIn(page, 'manager@example.com')
    await page.goto('/team')
    await expect(page.getByRole('heading', { name: 'My team at a glance' })).toBeVisible()
    await expect(page.getByText('On track', { exact: true })).toBeVisible()
    await expect(page.getByText('Skills heatmap: level by person')).toBeVisible()
    await expectNoHorizontalScroll(page)
    const nudge = page.getByRole('button', { name: 'Nudge' }).first()
    if (await nudge.isVisible()) {
      await nudge.click()
      // One kind reminder a day: a second nudge (e.g. from the phone run) is politely refused.
      await expect(page.getByText(/Nudge sent|already nudged this person today/)).toBeVisible()
    }
  })
})

test.describe('Admin', () => {
  test('assign training: check the list first, then send with undo', async ({ page }) => {
    await signIn(page, 'admin@example.com')
    await page.goto('/admin')
    await expect(page.getByRole('heading', { name: 'What do you want to do?' })).toBeVisible()
    await expect(page.getByText('Live today')).toBeVisible()
    // Core flow A4: its own page. Skill -> course -> who (everyone whose role needs the skill) -> check the list -> send.
    await page.getByRole('button', { name: /Assign training/ }).click()
    await expect(page.getByRole('heading', { name: 'Assign training' })).toBeVisible()
    await page.getByRole('combobox', { name: 'Skill', exact: true }).selectOption({ label: 'Verbal communication' })
    // The only published course for the skill is picked for you.
    await expect(page.getByRole('combobox', { name: 'Course', exact: true })).toContainText('Clear verbal communication')
    await page.getByRole('button', { name: 'See who gets it' }).click()
    await expect(page.getByText(/Message: /)).toBeVisible()
    await page.getByRole('button', { name: /Send to \d+ (person|people)/ }).click()
    await expect(page.getByText(/You can undo this/)).toBeVisible()
    await page.getByRole('button', { name: 'Undo' }).click()
    await expect(page.getByText(/Undone for \d+ people/)).toBeVisible()
  })

  test('workflows, reports and monitoring', async ({ page }) => {
    await signIn(page, 'admin@example.com')
    await page.goto('/admin/workflows')
    await expect(page.getByRole('heading', { name: 'New joiner' })).toBeVisible()
    await expect(page.getByText('WHEN')).toBeVisible()

    await page.goto('/admin/reports?report=mandatory_compliance')
    await expect(page.getByRole('heading', { name: 'Mandatory training compliance' })).toBeVisible()
    const download = page.waitForEvent('download')
    await page.getByRole('button', { name: 'CSV' }).click()
    expect((await download).suggestedFilename()).toMatch(/mandatory_compliance-\d+\.csv/)

    await page.goto('/admin/monitoring')
    await expect(page.getByRole('heading', { name: 'Everything, live' })).toBeVisible()
    await expect(page.getByText('Services')).toBeVisible()
    await expect(page.getByText('Redis & BullMQ queues')).toBeVisible()
    await expect(page.getByText(/All systems normal|Limited mode/)).toBeVisible()
  })

  test('learners cannot open admin pages', async ({ page }) => {
    await signIn(page, 'asha@example.com')
    await page.goto('/admin/monitoring')
    await expect(page).toHaveURL(/\/home$/)
  })

  test('learners do not see or open the Knowledge Hub', async ({ page }) => {
    await signIn(page, 'asha@example.com')
    await page.goto('/knowledge')
    await expect(page).toHaveURL(/\/home$/)
    await expect(page.getByRole('button', { name: /^Knowledge/ })).toHaveCount(0)
  })
})

test.describe('Knowledge Hub', () => {
  test('search, ask, open an item and confirm it is still correct', async ({ page }) => {
    await signIn(page, 'meera@example.com')
    await page.goto('/knowledge')
    await page.getByLabel('Search or ask').fill('refund')
    await page.getByRole('button', { name: 'Search', exact: true }).click()
    await expect(page.getByRole('link', { name: /Refund process/ })).toBeVisible()
    await page.getByLabel('Search or ask').fill('How many days are refunds allowed after delivery?')
    await page.getByRole('button', { name: 'Ask' }).click()
    await expect(page.getByText('Answer from the Knowledge Hub')).toBeVisible()

    await page.goto('/knowledge/library?q=refund')
    await page.getByRole('link', { name: 'Refund process' }).click()
    await expect(page.getByRole('heading', { name: 'Refund process' })).toBeVisible()
    await page.getByRole('button', { name: 'Still correct (verify)' }).click()
    await expect(page.getByText(/marked as still correct/)).toBeVisible()
    await page.getByRole('button', { name: /View history/ }).click()
    await expect(page.getByText('Compare: version')).toBeVisible()
  })

  test('my items worklist and leader dashboard', async ({ page }) => {
    await signIn(page, 'meera@example.com')
    await page.goto('/knowledge/my-items')
    await expect(page.getByRole('heading', { name: 'My items' })).toBeVisible()
    await expect(page.getByText('Coming up for me')).toBeVisible()
    await page.goto('/knowledge/dashboard')
    await expect(page.getByText('Knowledge health').first()).toBeVisible()
    await expect(page.getByText('Health score by function')).toBeVisible()
  })
})
