import { test, expect } from '@playwright/test';
import { loginUser } from './helpers';

test.describe('Reminders', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/web/index.html');
    
    // Přihlásit se
    await loginUser(page);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 10000 });
  });

  test('should display reminders tab', async ({ page }) => {
    await page.click('[data-testid="tab-reminders"]');
    await expect(page.locator('[data-testid="reminders-tab"]')).toBeVisible();
    await expect(page.locator('[data-testid="reminders-container"]')).toBeVisible();
  });

  test('should load reminders', async ({ page }) => {
    await page.click('[data-testid="tab-reminders"]');
    // Počkat na načtení (může být prázdné)
    await page.waitForTimeout(2000);
    await expect(page.locator('[data-testid="reminders-container"]')).toBeVisible();
  });
});

