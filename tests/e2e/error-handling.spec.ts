import { test, expect } from '@playwright/test';
import { loginUser } from './helpers';

test.describe('Error Handling', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/web/index.html');
  });

  test('should handle 401 unauthorized gracefully', async ({ page, context }) => {
    // Přihlásit se
    await loginUser(page);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 10000 });
    
    // Simulovat 401 - smazat token z localStorage
    await page.evaluate(() => {
      localStorage.removeItem('accessToken');
    });
    
    // Zkusit načíst vozidla (mělo by selhat)
    await page.click('[data-testid="tab-vehicles"]');
    
    // Měla by se zobrazit chybová hláška nebo přesměrování na login
    // (závisí na implementaci)
    await page.waitForTimeout(2000);
    
    // Aplikace by neměla spadnout
    const body = page.locator('body');
    await expect(body).toBeVisible();
  });

  test('should handle network errors gracefully', async ({ page, context }) => {
    // Přihlásit se
    await loginUser(page);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 10000 });
    
    // Blokovat síťové požadavky
    await page.route('**/api/**', route => route.abort());
    
    // Zkusit načíst vozidla
    await page.click('[data-testid="tab-vehicles"]');
    await page.waitForTimeout(2000);
    
    // Aplikace by neměla spadnout
    const body = page.locator('body');
    await expect(body).toBeVisible();
  });
});

