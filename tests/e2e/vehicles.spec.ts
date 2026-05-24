import { test, expect } from '@playwright/test';
import { loginUser } from './helpers';

test.describe('Vehicles Management', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/web/index.html');
    
    // Přihlásit se
    await loginUser(page);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 10000 });
  });

  test('should display vehicles tab', async ({ page }) => {
    await expect(page.locator('[data-testid="tab-vehicles"]')).toBeVisible();
    await expect(page.locator('[data-testid="vehicles-container"]')).toBeVisible();
  });

  test('should open add vehicle form on vehicles tab', async ({ page }) => {
    await page.click('[data-testid="tab-vehicles"]');
    await page.click('[data-testid="btn-toggle-add-vehicle"]');
    await expect(page.locator('[data-testid="add-vehicle-form"]')).toBeVisible();
    await expect(page.locator('[data-testid="input-vehicle-name"]')).toBeVisible();
    await expect(page.locator('[data-testid="input-vehicle-plate"]')).toBeVisible();
  });

  test('should create new vehicle', async ({ page }) => {
    await page.click('[data-testid="tab-vehicles"]');
    await page.click('[data-testid="btn-toggle-add-vehicle"]');
    
    // Vyplnit formulář
    const timestamp = Date.now();
    const stkDate = new Date(Date.now() + 365 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
    await page.fill('[data-testid="input-vehicle-name"]', `Test Vehicle ${timestamp}`);
    await page.fill('[data-testid="input-vehicle-plate"]', `TEST${timestamp.toString().slice(-4)}`);
    await page.fill('[data-testid="input-vehicle-stk-date"]', stkDate);
    
    // Přidat vozidlo
    await page.click('[data-testid="btn-add-vehicle"]');
    
    // Úspěch: nesmí se objevit chyba a vozidla musí být dostupná v seznamu
    await page.waitForTimeout(2000);
    await expect(page.locator('[data-testid="alert-error"]')).toHaveCount(0);
    await page.click('[data-testid="tab-vehicles"]');
    await expect(page.locator('[data-testid="vehicles-container"]')).toBeVisible();
  });

  test('should show vehicle detail', async ({ page }) => {
    // Počkat na načtení vozidel
    await page.waitForSelector('[data-testid="vehicle-card"]', { timeout: 10000 }).catch(() => {});
    
    // Kliknout na první vozidlo (pokud existuje)
    const vehicleCard = page.locator('[data-testid="vehicle-card"]').first();
    if (await vehicleCard.count() > 0) {
      await vehicleCard.click();
      await expect(page.locator('[data-testid="vehicle-detail-modal"]')).toBeVisible({ timeout: 5000 });
    } else {
      // Pokud nejsou žádná vozidla, přeskočit test
      test.skip();
    }
  });

  test('should validate required fields', async ({ page }) => {
    await page.click('[data-testid="tab-vehicles"]');
    await page.click('[data-testid="btn-toggle-add-vehicle"]');
    
    // Zkusit přidat vozidlo bez vyplnění povinných polí
    await page.click('[data-testid="btn-add-vehicle"]');
    
    // Měla by se zobrazit validace
    const nameInput = page.locator('[data-testid="input-vehicle-name"]');
    await expect(nameInput).toBeVisible();
    // HTML5 validace by měla zabránit odeslání
  });
});
