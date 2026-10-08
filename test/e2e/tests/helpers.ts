import { expect, type Page } from '@playwright/test'

export const PASSWORD = 'Demo@1234'

/** Sign in through the real form. Skips the once-per-session splash. */
export async function signIn(page: Page, email: string) {
  await page.addInitScript(() => sessionStorage.setItem('lms.splash-shown', '1'))
  await page.goto('/login')
  await page.getByLabel('Work email').fill(email)
  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).not.toHaveURL(/\/login/)
}

export const isPhone = (page: Page) => (page.viewportSize()?.width ?? 1200) < 1024

/** No horizontal page scroll at phone width (UI guide: 360 px first). */
export async function expectNoHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(1)
}
