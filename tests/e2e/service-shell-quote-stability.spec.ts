import { expect, test } from '@playwright/test';

import { installServiceShellMocks } from './service-shell-fallback.helpers';

test.describe('Service shell quote stability flow', () => {
  test('creates quote, opens public link, approves and reflects status', async ({ page }) => {
    await installServiceShellMocks(page);
    await page.goto('/web/index.html');

    await page.waitForFunction(() => typeof (window as any).serviceShell !== 'undefined');
    await page.evaluate(() => (window as any).serviceShell.openVehicleDetailModal(301));

    const vehicleModal = page.locator('.service-shell-modal').last();
    await expect(vehicleModal).toContainText('Nabídky');
    await vehicleModal.locator('button', { hasText: 'Vytvořit nabídku' }).click();

    const quoteModal = page.locator('.service-shell-modal').last();
    await expect(quoteModal).toContainText('Cenová nabídka');
    await quoteModal.locator('#serviceShellQuoteTotal').fill('4500');
    await quoteModal.getByRole('button', { name: 'Uložit nabídku' }).click();

    const popupPromise = page.waitForEvent('popup');
    await quoteModal.getByRole('button', { name: 'Otevřít veřejný odkaz' }).click();
    const publicPopup = await popupPromise;
    await expect(publicPopup).toHaveURL(/public-quote\.html\?token=/);
    publicPopup.on('dialog', async (dialog) => {
      await dialog.accept();
    });
    await publicPopup.getByRole('button', { name: 'Schválit' }).click();
    await expect(publicPopup.getByText('Nabídka byla schválena.')).toBeVisible();
    await publicPopup.close();

    await quoteModal.getByRole('button', { name: 'Zpět' }).click();
    await page.evaluate(() => (window as any).serviceShell.closeModal());

    await page.evaluate(() => (window as any).serviceShell.openVehicleDetailModal(301));
    const refreshedVehicleModal = page.locator('.service-shell-modal').last();
    await expect(refreshedVehicleModal).toContainText('Schváleno');
    await page.evaluate(() => (window as any).serviceShell.closeModal());

    await page.evaluate(() => (window as any).serviceShell.openWorkOrderDetailModal(501));
    const workOrderModal = page.locator('.service-shell-modal').last();
    await expect(workOrderModal).toContainText('Nabídka');
    await expect(workOrderModal).toContainText('Schváleno');
    await expect(workOrderModal).toContainText('public-quote.html?token=');
  });
});
