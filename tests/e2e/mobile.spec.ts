import { test, expect } from '@playwright/test';
import { loginUser } from './helpers';

test.describe('Mobile View', () => {
  test.use({
    viewport: { width: 390, height: 844 }, // iPhone 12 Pro
  });

  test('should display login form on mobile', async ({ page }) => {
    await page.goto('/web/index.html');
    await expect(page.locator('[data-testid="login-form"]')).toBeVisible();
    
    // Ověřit, že formulář je použitelný
    await expect(page.locator('[data-testid="input-email"]')).toBeVisible();
    await expect(page.locator('[data-testid="input-password"]')).toBeVisible();
  });

  test('should login on mobile', async ({ page }) => {
    await page.goto('/web/index.html');
    await loginUser(page);
    
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 10000 });
  });

  test('should navigate tabs on mobile', async ({ page }) => {
    await page.goto('/web/index.html');
    
    // Přihlásit se
    await loginUser(page);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 10000 });
    
    // Ověřit, že navigace je viditelná a použitelná
    await expect(page.locator('[data-testid="tab-vehicles"]')).toBeVisible();
    await page.click('[data-testid="tab-vehicles"]');
    await page.click('[data-testid="btn-toggle-add-vehicle"]');
    await expect(page.locator('[data-testid="add-vehicle-panel"]')).toBeVisible();
  });
});

