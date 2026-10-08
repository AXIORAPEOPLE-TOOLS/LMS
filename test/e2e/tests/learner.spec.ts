import { expect, test } from '@playwright/test'
import { signIn } from './helpers'

test.describe('Learner (Asha)', () => {
  test('home shows one clear next step and the pathway', async ({ page }) => {
    await signIn(page, 'asha@example.com')
    await expect(page.getByRole('heading', { name: /Asha/ })).toBeVisible()
    await expect(page.getByText('Your next step')).toBeVisible()
    await expect(page.getByText(/Learn: Data privacy/)).toBeVisible()
    await expect(page.getByText('My pathway')).toBeVisible()
    await page.goto('/path')
    await expect(page.getByRole('heading', { name: 'Wave 1 of 3' })).toBeVisible()
    await expect(page.getByText('Manager approved')).toBeVisible()
  })

  test('takes a lesson and the course progress moves', async ({ page }) => {
    await signIn(page, 'asha@example.com')
    await page.goto('/learn?tab=catalogue')
    await page.getByRole('link', { name: /Clear verbal communication/ }).click()
    const heading = page.getByRole('heading', { level: 1 })
    const before = await heading.textContent()
    await page.getByRole('button', { name: /Done, next|Next/ }).click()
    // Either the next lesson opens, or (after the last lesson) the quick check does.
    await expect(heading.filter({ hasNotText: before ?? '' }).or(page.getByText(/Question \d+ of \d+/))).toBeVisible()
    await expect(page.getByText(/\d+% done/).first()).toBeVisible()
  })

  test('skill check: one question per screen, then level and rank band', async ({ page }) => {
    await signIn(page, 'asha@example.com')
    await page.goto('/learn?tab=tests')
    await page.getByRole('button', { name: 'Start' }).or(page.getByRole('link', { name: 'Start' })).first().click()
    await expect(page.getByText('No pass or fail')).toBeVisible()
    await page.getByRole('button', { name: 'Start test' }).click()
    await expect(page.getByText(/Question 1 of/)).toBeVisible()
    for (;;) {
      await page.getByRole('radio').nth(1).click()
      const finish = page.getByRole('button', { name: 'Finish' })
      if (await finish.isVisible()) {
        await finish.click()
        break
      }
      await page.getByRole('button', { name: 'Next' }).click()
    }
    await expect(page.getByText('Your result')).toBeVisible()
    await expect(page.getByRole('heading', { name: /Level \d/ })).toBeVisible()
    await expect(page.getByText(/Top \d+% of \d+ people tested/)).toBeVisible()
  })

  test('leaderboard, career map and reminders', async ({ page }) => {
    await signIn(page, 'asha@example.com')
    await page.goto('/rank')
    await expect(page.getByRole('heading', { name: 'Leaderboards' })).toBeVisible()
    await expect(page.getByText(/You \(Asha V\.\)/)).toBeVisible()
    await expect(page.getByText('Mandatory training on time')).toBeVisible()

    await page.goto('/career')
    await expect(page.getByText('You are here')).toBeVisible()
    await page.getByRole('button', { name: /Senior Admissions Counsellor/ }).click()
    await expect(page.getByRole('button', { name: 'Add to my pathway' })).toBeVisible()

    await page.goto('/me/reminders')
    await page.getByRole('switch', { name: 'WhatsApp' }).click()
    await page.getByRole('button', { name: 'Save' }).click()
    await expect(page.getByText('Saved')).toBeVisible()
  })

  test('certificate can be verified publicly', async ({ page, request }) => {
    await signIn(page, 'asha@example.com')
    await page.goto('/learn/certificates')
    await expect(page.getByText('Ethics & code of conduct')).toBeVisible()
    const code = (await page.getByText(/^ID C-/).first().textContent())!.replace('ID ', '').trim()
    await page.goto(`/verify/${code}`)
    await expect(page.getByRole('heading', { name: 'Asha Verma' })).toBeVisible()
    await expect(page.getByText('✓ Valid')).toBeVisible()
    void request
  })
})
