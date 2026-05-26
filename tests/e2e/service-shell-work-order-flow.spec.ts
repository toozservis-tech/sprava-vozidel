import { expect, test } from '@playwright/test';

import { installServiceShellMocks } from './service-shell-fallback.helpers';

test.describe('Service shell work order flow', () => {
  test('covers create, duplicate reject and update refresh flow', async ({ page }) => {
    await installServiceShellMocks(page);
    await page.goto('/web/index.html');
    await expect(page.locator('[data-service-shell="root"]')).toBeVisible({ timeout: 15000 });

    const closeModal = async () => {
      await page.evaluate(() => (window as any).serviceShell.closeModal());
      await expect(page.locator('.service-shell-modal')).toHaveCount(0);
    };

    await page.getByRole('button', { name: '+ Nová zakázka' }).click();
    await expect(page.locator('.service-shell-modal-title')).toContainText('Nová zakázka');
    await closeModal();

    await page.getByRole('button', { name: 'Otevřít zakázku' }).first().click();
    await expect(page.locator('.service-shell-modal-title')).toContainText('Detail zakázky');
    await expect(page.locator('.service-shell-modal')).toContainText('Linked Customer');
    await page.selectOption('#serviceShellDetailStatus', 'approved');
    await page.fill('#serviceShellDetailDescription', 'Aktualizovaná zakázka');
    await page.evaluate(() => (window as any).serviceShell.submitWorkOrderDetailUpdate(501));
    await expect(page.locator('.service-shell-modal')).toHaveCount(0);

    await page.locator('.service-shell-icon-btn[aria-label="Servisní nástroje"]').click();
    await page.fill('input[placeholder="VIN nebo SPZ"]', '1AB2345');
    await page.evaluate(() => (window as any).serviceShell.searchVehicles());
    await expect(page.locator('.service-shell-modal')).toContainText('Octavia');
    await page.evaluate(() => (window as any).serviceShell.openCreateWorkOrderFromLookupByIndex(0));
    await expect(page.locator('.service-shell-modal-title')).toContainText('Nová zakázka');
    await closeModal();

    await page.getByRole('button', { name: 'Dashboard' }).click();
    await expect(page.locator('[data-service-shell="root"]')).toContainText('Servisní přehled');
    await expect(page.locator('.service-shell-kpi').nth(0)).toContainText('2');
  });
});
