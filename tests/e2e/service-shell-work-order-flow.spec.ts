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

    await page.locator('tr', { hasText: 'Výchozí zakázka' }).first().click();
    await expect(page.locator('.service-shell-modal-title')).toContainText('Detail zakázky');
    await expect(page.locator('.service-shell-modal')).toContainText('Linked Customer');
    await closeModal();

    await page.locator('.service-shell-icon-btn[aria-label="Servisní nástroje"]').click();
    await page.fill('input[placeholder="VIN nebo SPZ"]', '1AB2345');
    await page.evaluate(() => (window as any).serviceShell.searchVehicles());
    await expect(page.locator('.service-shell-modal')).toContainText('Octavia');
    await page.evaluate(() => (window as any).serviceShell.openCreateWorkOrderFromLookupByIndex(0));
    await expect(page.locator('.service-shell-modal-title')).toContainText('Nová zakázka');
    await closeModal();

    await page.getByRole('button', { name: '+ Nová zakázka' }).click();
    await page.fill('#serviceShellWorkOrderTitle', 'E2E Zakazka');
    await page.fill('#serviceShellWorkOrderDueDate', '2026-04-13');
    await page.fill('#serviceShellWorkOrderDescription', 'Zakázka vytvořená testem');
    await page.evaluate(() => (window as any).serviceShell.submitCreateWorkOrderModal());
    await expect(page.locator('.service-shell-modal')).toHaveCount(0);
    await expect(page.locator('[data-service-shell="root"]')).toContainText('E2E Zakazka');

    await page.locator('tr', { hasText: 'E2E Zakazka' }).first().click();
    await expect(page.locator('.service-shell-modal-title')).toContainText('Detail zakázky');
    await expect(page.locator('.service-shell-modal')).toContainText('Linked Customer');
    await page.selectOption('#serviceShellDetailStatus', 'approved');
    await page.fill('#serviceShellDetailDescription', 'Aktualizovaná zakázka');
    await page.evaluate(() => (window as any).serviceShell.submitWorkOrderDetailUpdate(777));
    await expect(page.locator('.service-shell-modal')).toHaveCount(0);

    await expect(page.locator('tr', { hasText: 'E2E Zakazka' }).first()).toContainText('Approved');
    await page.getByRole('button', { name: 'Dashboard' }).click();
    await expect(page.locator('.service-shell-kpi').nth(1)).toContainText('0');
    await expect(page.locator('.service-shell-kpi').nth(0)).toContainText('2');
    await expect(page.locator('.service-shell-queue-tile').nth(0)).toContainText('0');
    await expect(
      page.locator('.service-shell-side-card').filter({ hasText: 'Fronta práce' }).locator('.service-shell-list-row').nth(0),
    ).toContainText('2');

    await page.getByRole('button', { name: '+ Nová zakázka' }).click();
    await page.fill('#serviceShellWorkOrderTitle', 'Duplicitní pokus');
    await page.fill('#serviceShellWorkOrderDueDate', '2026-04-14');
    await page.fill('#serviceShellWorkOrderDescription', 'Nemá projít');
    await page.evaluate(() => (window as any).serviceShell.submitCreateWorkOrderModal());
    await expect(page.locator('.service-shell-modal')).toContainText('Na stejné vozidlo už existuje rozpracovaná zakázka');
    await expect(page.getByRole('button', { name: 'Otevřít existující zakázku' })).toBeVisible();
    await closeModal();
  });
});
