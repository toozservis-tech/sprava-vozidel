import { test, expect } from '@playwright/test';
import { loginUser } from './helpers';

test.describe('Reservations', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/web/index.html');
    
    // Přihlásit se
    await loginUser(page);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 10000 });
  });

  test('should display reservations tab', async ({ page }) => {
    await page.click('[data-testid="tab-reservations"]');
    await expect(page.locator('[data-testid="reservations-tab"]')).toBeVisible();
    await expect(page.locator('[data-testid="reservations-container"]')).toBeVisible();
  });

  test('should load reservations', async ({ page }) => {
    await page.click('[data-testid="tab-reservations"]');
    // Počkat na načtení (může být prázdné)
    await page.waitForTimeout(2000);
    await expect(page.locator('[data-testid="reservations-container"]')).toBeVisible();
  });
});

