import { expect, test } from '@playwright/test';

import { installServiceShellMocks } from './service-shell-fallback.helpers';

test.describe('Service shell search and link flows', () => {
  test('covers search, link, lookup and detail modals', async ({ page }) => {
    await installServiceShellMocks(page);
    await page.goto('/web/index.html');
    await expect(page.locator('[data-service-shell="root"]')).toBeVisible({ timeout: 15000 });

    const closeModal = async () => {
      await page.evaluate(() => (window as any).serviceShell.closeModal());
      await expect(page.locator('.service-shell-modal')).toHaveCount(0);
    };

    await page.locator('.service-shell-icon-btn[aria-label="Servisní nástroje"]').click();
    await expect(page.locator('.service-shell-modal-title')).toContainText('Najít nebo vytvořit');

    await page.fill('input[placeholder="email, telefon nebo jméno"]', 'Vyhledany');
    await page.evaluate(() => (window as any).serviceShell.searchCustomers());
    await expect(page.locator('.service-shell-modal')).toContainText('Klient Vyhledany');
    await page.evaluate(() => (window as any).serviceShell.linkCustomerById(201));
    await expect(page.locator('.service-shell-modal')).toContainText('Otevřít');

    await page.fill('input[placeholder="VIN nebo SPZ"]', '1AB2345');
    await page.evaluate(() => (window as any).serviceShell.searchVehicles());
    await expect(page.locator('.service-shell-modal')).toContainText('Octavia');
    await page.evaluate(() => {
      const shell = (window as any).serviceShell;
      shell.openAddVehicleModal(101, {
        vin: '1AB2345',
        plate: '1AB2345',
      });
    });
    await expect(page.locator('.service-shell-modal-title')).toContainText('Založit nové vozidlo');
    await expect(page.locator('#serviceShellAddVehicleCustomer')).toHaveValue('101');
    await expect(page.locator('#serviceShellAddVehiclePlate')).toHaveValue('1AB2345');
    await closeModal();

    await page.getByRole('button', { name: 'Klienti' }).click();
    await page.locator('tr', { hasText: 'Linked Customer' }).first().click();
    await expect(page.locator('.service-shell-modal-title')).toContainText('Detail klienta');
    await closeModal();

    await page.getByRole('button', { name: 'Vozidla' }).click();
    await page.locator('tr', { hasText: 'Octavia' }).first().click();
    await expect(page.locator('.service-shell-modal-title')).toContainText('Detail vozidla');
    await closeModal();

    await page.getByRole('button', { name: 'Dokumenty' }).click();
    await page.locator('tr', { hasText: 'FV-001' }).first().click();
    await expect(page.locator('.service-shell-modal-title')).toContainText('Detail dokumentu');
    await closeModal();

    await page.getByRole('button', { name: 'Rezervace' }).click();
    await page.locator('tr', { hasText: 'Linked Customer' }).first().click();
    await expect(page.locator('.service-shell-modal-title')).toContainText('Detail rezervace');
    await closeModal();

    await page.getByRole('button', { name: 'Připomínky' }).click();
    await page.locator('tr', { hasText: 'Kontrola STK' }).first().click();
    await expect(page.locator('.service-shell-modal-title')).toContainText('Detail připomínky');
    await closeModal();
  });
});
