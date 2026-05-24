/**
 * Skeleton: servisní shell — sekce Zákazníci (vyhledání, vytvoření, F5, izolace vozidla, historie).
 *
 * Nenavázáno na stabilní servisní auth storage v CI — spouštět až po:
 *   - dostupný BASE_URL s testovacím servisním účtem
 *   - Playwright storageState pro service workspace
 * Výchozí stav: testy přeskočeny (viz test.skip).
 */
import { test, expect } from '@playwright/test';

test.describe.skip('Service shell — customer bindings (needs SERVICE_SHELL_E2E=1 + auth)', () => {
  test('servis otevře Zákazníky, vyhledá e-mailem, zobrazí maskovaný výsledek', async ({ page }) => {
    await page.goto('/web/service-shell.html');
    await expect(page.getByRole('heading', { name: /zákazníci/i })).toBeVisible();
  });

  test('po F5 zůstane workspace route', async ({ page }) => {
    await page.goto('/web/service-shell.html');
    await page.reload();
    await expect(page).toHaveURL(/service-shell/);
  });
});
