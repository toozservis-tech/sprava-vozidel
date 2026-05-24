import { expect, test } from '@playwright/test';

import { installServiceShellMocks } from './service-shell-fallback.helpers';

test.describe('Service shell quote list polish', () => {
  test('filters, sorts, renders quote cards and opens quote from list', async ({ page }) => {
    await installServiceShellMocks(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/web/index.html');

    await page.waitForFunction(() => typeof (window as any).serviceShell !== 'undefined');
    await page.evaluate(() => (window as any).serviceShell.mount({ skipLoad: true }));
    await page.evaluate(() => (window as any).serviceShell.load(true));
    await page.evaluate(() => (window as any).serviceShell.openVehicleDetailModal(301));

    const vehicleModal = page.locator('.service-shell-modal').last();
    await expect(vehicleModal.getByText('Nabídky')).toBeVisible();
    await expect(vehicleModal.locator('.service-shell-quote-card')).toHaveCount(4);
    await expect(vehicleModal.getByText('Zobrazeno 4 z 4')).toBeVisible();

    await vehicleModal.locator('#serviceShellQuoteFilterStatus').selectOption('rejected');
    await expect(vehicleModal.locator('.service-shell-quote-card')).toHaveCount(1);
    await expect(vehicleModal.locator('[data-quote-id="804"]')).toBeVisible();
    await expect(vehicleModal.getByText('Zobrazeno 1 z 4')).toBeVisible();

    await vehicleModal.locator('#serviceShellQuoteFilterStatus').selectOption('all');
    await vehicleModal.locator('#serviceShellQuoteSortField').selectOption('total_price');
    await vehicleModal.locator('#serviceShellQuoteSortOrder').selectOption('desc');
    await expect(vehicleModal.locator('.service-shell-quote-card').first()).toHaveAttribute('data-quote-id', '803');

    await vehicleModal.locator('#serviceShellQuoteFilterStatus').selectOption('approved');
    await vehicleModal.locator('.service-shell-quote-card').first().getByRole('button', { name: 'Otevřít' }).click();
    const quoteModal = page.locator('.service-shell-modal').last();
    await expect(quoteModal).toContainText('Cenová nabídka');
    await expect(quoteModal.locator('#serviceShellQuoteTotal')).toHaveValue('9000');
    await page.evaluate(() => (window as any).serviceShell.closeModal());

    await page.evaluate(() => (window as any).serviceShell.openVehicleDetailModal(301));
    const vehicleModalAfter = page.locator('.service-shell-modal').last();
    await vehicleModalAfter.locator('#serviceShellQuoteFilterStatus').selectOption('rejected');
    await vehicleModalAfter.locator('.service-shell-quote-card').first().getByRole('button', { name: 'Otevřít' }).click();
    const quoteModalRejected = page.locator('.service-shell-modal').last();
    await expect(quoteModalRejected).toContainText('Cenová nabídka');
    await expect(quoteModalRejected.locator('#serviceShellQuoteTotal')).toHaveValue('1200');
  });
});
