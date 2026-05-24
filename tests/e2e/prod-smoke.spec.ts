import { test, expect } from '@playwright/test';
import { loginUser, isReadOnly, assertNoGlobalErrorBanner, gotoTab, getBaseUrl } from './helpers';

test.describe('Production Smoke Tests (Read-Only)', () => {
  test.beforeEach(async ({ page }) => {
    // Ověřit, že jsme v read-only režimu
    if (!isReadOnly()) {
      test.skip();
    }
    
    const baseUrl = getBaseUrl();
    await page.goto(`${baseUrl}/web/index.html`);
  });

  test('should load login page', async ({ page }) => {
    await expect(page.locator('[data-testid="login-form"]')).toBeVisible();
    await expect(page.locator('[data-testid="input-email"]')).toBeVisible();
    await expect(page.locator('[data-testid="input-password"]')).toBeVisible();
    await expect(page.locator('[data-testid="btn-login"]')).toBeVisible();
    
    // Ověřit, že nejsou chybové hlášky
    await assertNoGlobalErrorBanner(page);
  });

  test('should login successfully', async ({ page }) => {
    await loginUser(page);
    
    // Mělo by se zobrazit dashboard
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="tab-vehicles"]')).toBeVisible();
    
    // Ověřit, že nejsou chybové hlášky
    await assertNoGlobalErrorBanner(page);
  });

  test('should navigate to vehicles tab', async ({ page }) => {
    await loginUser(page);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 10000 });
    
    await gotoTab(page, 'tab-vehicles');
    await expect(page.locator('[data-testid="vehicles-tab"]')).toBeVisible();
    await expect(page.locator('[data-testid="vehicles-container"]')).toBeVisible();
    
    // Ověřit, že nejsou chybové hlášky
    await assertNoGlobalErrorBanner(page);
  });

  test('should navigate to reminders tab', async ({ page }) => {
    await loginUser(page);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 10000 });
    
    await gotoTab(page, 'tab-reminders');
    await expect(page.locator('[data-testid="reminders-tab"]')).toBeVisible();
    await expect(page.locator('[data-testid="reminders-container"]')).toBeVisible();
    
    // Ověřit, že nejsou chybové hlášky
    await assertNoGlobalErrorBanner(page);
  });

  test('should navigate to reservations tab', async ({ page }) => {
    await loginUser(page);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 10000 });
    
    await gotoTab(page, 'tab-reservations');
    await expect(page.locator('[data-testid="reservations-tab"]')).toBeVisible();
    await expect(page.locator('[data-testid="reservations-container"]')).toBeVisible();
    
    // Ověřit, že nejsou chybové hlášky
    await assertNoGlobalErrorBanner(page);
  });

  test('should navigate to profile tab', async ({ page }) => {
    await loginUser(page);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 10000 });
    
    await gotoTab(page, 'tab-account');
    await expect(page.locator('[data-testid="account-tab"]')).toBeVisible();
    await expect(page.locator('[data-testid="profile-container"]')).toBeVisible();
    
    // Ověřit, že nejsou chybové hlášky
    await assertNoGlobalErrorBanner(page);
  });

  test('should display vehicles list (read-only)', async ({ page }) => {
    await loginUser(page);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 10000 });
    
    await gotoTab(page, 'tab-vehicles');
    
    // Počkat na načtení vozidel (může být prázdné, to je OK)
    await page.waitForTimeout(2000);
    
    // Ověřit, že kontejner existuje (i když je prázdný)
    await expect(page.locator('[data-testid="vehicles-container"]')).toBeVisible();
    
    // Ověřit, že nejsou chybové hlášky
    await assertNoGlobalErrorBanner(page);
  });

  test('should logout successfully', async ({ page }) => {
    await loginUser(page);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 10000 });
    
    // Odhlásit se
    await page.click('[data-testid="btn-logout"]');
    await expect(page.locator('[data-testid="login-form"]')).toBeVisible();
    
    // Ověřit, že nejsou chybové hlášky
    await assertNoGlobalErrorBanner(page);
  });
});

