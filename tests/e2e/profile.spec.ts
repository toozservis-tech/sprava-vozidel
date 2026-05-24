import { test, expect } from '@playwright/test';
import { loginUser } from './helpers';

test.describe('Profile', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/web/index.html');
    
    // Přihlásit se
    await loginUser(page);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 10000 });
  });

  test('should display account tab with profile', async ({ page }) => {
    await page.click('[data-testid="tab-account"]');
    await expect(page.locator('[data-testid="account-tab"]')).toBeVisible();
    await expect(page.locator('[data-testid="profile-container"]')).toBeVisible();
  });

  test('should load profile data', async ({ page }) => {
    await page.click('[data-testid="tab-account"]');
    // Počkat na načtení
    await page.waitForTimeout(2000);
    await expect(page.locator('[data-testid="profile-container"]')).toBeVisible();
  });
});

