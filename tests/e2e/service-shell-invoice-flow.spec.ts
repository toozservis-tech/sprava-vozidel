import { expect, test } from '@playwright/test';

import { installServiceShellMocks } from './service-shell-fallback.helpers';

test.describe('Service shell invoice flow', () => {
  test('creates, updates, issues, exports and cancels an invoice end to end', async ({ page }) => {
    await installServiceShellMocks(page);
    await page.goto('/web/index.html');
    await expect(page.locator('[data-service-shell="root"]')).toBeVisible({ timeout: 15000 });

    await page.locator('.service-shell-nav-btn', { hasText: 'Faktury' }).click();
    await expect(page.locator('[data-service-shell="root"]')).toContainText('Servisní faktury');

    await page.getByRole('button', { name: 'Nová draft faktura' }).click();
    const createModal = page.locator('.service-shell-modal').last();
    await expect(createModal.locator('.service-shell-modal-title')).toContainText('Nová draft faktura');
    await createModal.locator('[data-invoice-line-description]').fill('Diagnostika faktura');
    await createModal.locator('[data-invoice-line-quantity]').fill('2');
    await createModal.locator('[data-invoice-line-unit-price]').fill('1500');
    await createModal.locator('#serviceShellCreateInvoiceNotes').fill('Faktura založená z E2E shellu');
    await createModal.getByRole('button', { name: 'Vytvořit draft' }).click();

    await expect(page.locator('.service-shell-modal')).toHaveCount(0);
    await expect(page.locator('[data-service-shell="root"]')).toContainText('3630');

    await page.locator('tr', { hasText: '3630' }).first().click();
    const detailModal = page.locator('.service-shell-modal').last();
    await expect(detailModal.locator('.service-shell-modal-title')).toContainText('Servisní faktura');
    await expect(detailModal.locator('[data-invoice-line-description]').first()).toHaveValue('Diagnostika faktura');

    await detailModal.locator('[data-invoice-line-description]').first().fill('Diagnostika a oprava');
    await detailModal.locator('[data-invoice-line-unit-price]').first().fill('2000');
    await detailModal.getByRole('button', { name: 'Uložit draft' }).click();
    await expect(detailModal.locator('[data-invoice-line-description]').first()).toHaveValue('Diagnostika a oprava');
    await expect(detailModal).toContainText('4840');

    const popupPromise = page.waitForEvent('popup');
    const pdfResponsePromise = page.waitForResponse(/\/api\/service\/invoices\/\d+\/pdf$/);
    await detailModal.getByRole('button', { name: 'PDF' }).click();
    const pdfPopup = await popupPromise;
    const pdfResponse = await pdfResponsePromise;
    expect(pdfResponse.ok()).toBeTruthy();
    expect((pdfResponse.headers()['content-type'] || '').toLowerCase()).toContain('application/pdf');
    await pdfPopup.close();

    await detailModal.getByRole('button', { name: 'Vystavit' }).click();
    await expect(page.locator('.service-shell-modal')).toHaveCount(0);
    await expect(page.locator('[data-service-shell="root"]')).toContainText('FV-2026-9002');
    await expect(page.locator('[data-service-shell="root"]')).toContainText('Vystaveno');

    await page.locator('tr', { hasText: 'FV-2026-9002' }).first().click();
    const issuedModal = page.locator('.service-shell-modal').last();
    await expect(issuedModal).toContainText('Vystaveno');
    await issuedModal.getByRole('button', { name: 'Zrušit' }).click();
    await expect(page.locator('.service-shell-modal')).toHaveCount(0);
    await expect(page.locator('[data-service-shell="root"]')).toContainText('Zrušeno');
  });
});
