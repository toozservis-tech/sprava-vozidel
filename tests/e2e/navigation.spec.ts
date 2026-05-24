import { test, expect } from '@playwright/test';
import { loginUser } from './helpers';

test.describe('Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/web/index.html');
    
    // Přihlásit se
    await loginUser(page);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 10000 });
  });

  test('should navigate to vehicles tab', async ({ page }) => {
    await page.click('[data-testid="tab-vehicles"]');
    await expect(page.locator('[data-testid="vehicles-tab"]')).toBeVisible();
    await expect(page.locator('[data-testid="tab-vehicles"]')).toHaveClass(/active/);
  });

  test('should open add vehicle form inside vehicles tab', async ({ page }) => {
    await page.click('[data-testid="tab-vehicles"]');
    await expect(page.locator('[data-testid="vehicles-tab"]')).toBeVisible();
    await page.click('[data-testid="btn-toggle-add-vehicle"]');
    await expect(page.locator('[data-testid="add-vehicle-panel"]')).toBeVisible();
    await expect(page.locator('[data-testid="add-vehicle-form"]')).toBeVisible();
  });

  test('should navigate to reminders tab', async ({ page }) => {
    await page.click('[data-testid="tab-reminders"]');
    await expect(page.locator('[data-testid="reminders-tab"]')).toBeVisible();
    await expect(page.locator('[data-testid="tab-reminders"]')).toHaveClass(/active/);
  });

  test('should navigate to reservations tab', async ({ page }) => {
    await page.click('[data-testid="tab-reservations"]');
    await expect(page.locator('[data-testid="reservations-tab"]')).toBeVisible();
    await expect(page.locator('[data-testid="tab-reservations"]')).toHaveClass(/active/);
  });

  test('should navigate to documents and account tabs', async ({ page }) => {
    await page.click('[data-testid="tab-documents"]');
    await expect(page.locator('[data-testid="documents-tab"]')).toBeVisible();
    await expect(page.locator('[data-testid="tab-documents"]')).toHaveClass(/active/);

    await page.click('[data-testid="tab-account"]');
    await expect(page.locator('[data-testid="account-tab"]')).toBeVisible();
    await expect(page.locator('[data-testid="tab-account"]')).toHaveClass(/active/);
    await expect(page.locator('[data-testid="profile-container"]')).toBeVisible();
  });
});

