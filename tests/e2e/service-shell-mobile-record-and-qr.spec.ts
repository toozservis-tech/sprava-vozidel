import { expect, test } from '@playwright/test';

import { installServiceShellMocks } from './service-shell-fallback.helpers';

test.describe('Service shell mobile record and QR flows', () => {
  test('uses full-screen mobile flow for records and QR', async ({ page }) => {
    await installServiceShellMocks(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/web/index.html');

    await expect(page.locator('[data-service-shell="root"]')).toBeVisible({ timeout: 15000 });
    await page.locator('.service-shell-mobile-menu-btn').click();
    await page.getByRole('button', { name: 'Vozidla' }).click();
    await page.locator('tr', { hasText: 'Octavia' }).first().click();

    await expect(page.locator('.service-shell-modal--mobile-flow')).toBeVisible();
    await expect(page.locator('.service-shell-modal')).toContainText('Servisní záznamy');

    await page.locator('.service-shell-modal').getByRole('button', { name: 'Nový záznam' }).click();
    await expect(page.locator('.service-shell-modal--mobile-flow')).toContainText('Nový servisní záznam');
    await page.fill('#serviceShellRecordDescription', 'Mobilní servisní zápis');
    await page.fill('#serviceShellRecordMileage', '146500');
    await page.fill('#serviceShellRecordPrice', '4200');
    await page.getByRole('button', { name: 'Dokončit' }).click();

    await expect(page.locator('.service-shell-modal')).toHaveCount(0);
    await page.locator('tr', { hasText: 'Octavia' }).first().click();
    await expect(page.locator('.service-shell-modal')).toContainText('Mobilní servisní zápis');

    await page.locator('.service-shell-modal').getByText('Mobilní servisní zápis').click();
    const recordModal = page.locator('.service-shell-modal').last();
    await expect(recordModal).toContainText('Servisní záznam');
    await recordModal.getByRole('button', { name: 'Vytvořit nabídku' }).click();

    const quoteModal = page.locator('.service-shell-modal').last();
    await expect(quoteModal).toContainText('Cenová nabídka');
    await quoteModal.locator('[data-quote-item-price]').first().fill('4500');
    await quoteModal.locator('#serviceShellQuoteTotal').fill('4500');
    await quoteModal.getByRole('button', { name: 'Uložit nabídku' }).click();
    await expect(quoteModal).toContainText('Cenová nabídka');
    const popupPromise = page.waitForEvent('popup');
    const pdfResponsePromise = page.waitForResponse(/\/api\/service\/quotes\/\d+\/pdf$/);
    await quoteModal.getByRole('button', { name: 'Sdílet / stáhnout PDF' }).click();
    const pdfPopup = await popupPromise;
    const pdfResponse = await pdfResponsePromise;
    expect(pdfResponse.ok()).toBeTruthy();
    expect((pdfResponse.headers()['content-type'] || '').toLowerCase()).toContain('application/pdf');
    await pdfPopup.close();
    await quoteModal.getByRole('button', { name: 'Zpět' }).click();

    await page.getByRole('button', { name: 'QR' }).click();
    const qrModal = page.locator('.service-shell-modal').last();
    await expect(qrModal).toContainText('QR historie vozidla');
    await expect(qrModal.locator('.service-shell-qr-visual svg')).toBeVisible();
    await qrModal.getByRole('button', { name: 'Regenerovat QR' }).click();
    await expect(page.locator('.service-shell-modal').last()).toContainText('QR historie vozidla');
    await expect(page.locator('.service-shell-modal').last().locator('.service-shell-qr-link')).toContainText('public-vehicle-history.html?token=');
  });
});
