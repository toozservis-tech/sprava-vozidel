import { test, expect } from '@playwright/test';
import { getTestCredentials, loginUser } from './helpers';

test.describe('Authentication', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/web/index.html');
  });

  test('should display login form', async ({ page }) => {
    await expect(page.locator('[data-testid="login-form"]')).toBeVisible();
    await expect(page.locator('[data-testid="input-email"]')).toBeVisible();
    await expect(page.locator('[data-testid="input-password"]')).toBeVisible();
    await expect(page.locator('[data-testid="btn-login"]')).toBeVisible();
  });

  test('should login successfully with correct credentials', async ({ page }) => {
    await loginUser(page);
    
    // Mělo by se zobrazit dashboard
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="tab-vehicles"]')).toBeVisible();
  });

  test('should show error on wrong password', async ({ page }) => {
    const credentials = getTestCredentials();
    await page.fill('[data-testid="input-email"]', credentials.email);
    await page.fill('[data-testid="input-password"]', 'wrongpassword');
    await page.click('[data-testid="btn-login"]');
    
    // Měla by se zobrazit chybová hláška
    await expect(page.locator('[data-testid="alert-error"]')).toBeVisible({ timeout: 5000 });
  });

  test('should show error on nonexistent user', async ({ page }) => {
    await page.fill('[data-testid="input-email"]', 'nonexistent@example.com');
    await page.fill('[data-testid="input-password"]', 'password123');
    await page.click('[data-testid="btn-login"]');
    
    // Měla by se zobrazit chybová hláška
    await expect(page.locator('[data-testid="alert-error"]')).toBeVisible({ timeout: 5000 });
  });

  test('should switch to registration form', async ({ page }) => {
    await page.click('[data-testid="btn-show-register"]');
    await expect(page.locator('[data-testid="register-form"]')).toBeVisible();
    await expect(page.locator('[data-testid="input-reg-email"]')).toBeVisible();
  });

  test('should logout successfully', async ({ page }) => {
    // Přihlásit se
    await loginUser(page);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 10000 });
    
    // Odhlásit se
    await page.click('[data-testid="btn-logout"]');
    await expect(page.locator('[data-testid="login-form"]')).toBeVisible();
  });
});

