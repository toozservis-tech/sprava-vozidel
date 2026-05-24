import { expect, test } from '@playwright/test';

import { installServiceShellMocks } from './service-shell-fallback.helpers';

test.describe('Service shell account and navigation', () => {
  test('covers account actions and dashboard navigation', async ({ page }) => {
    await installServiceShellMocks(page);
    await page.goto('/web/index.html');
    await expect(page.locator('[data-service-shell="root"]')).toBeVisible({ timeout: 15000 });

    const closeModal = async () => {
      await page.evaluate(() => (window as any).serviceShell.closeModal());
      await expect(page.locator('.service-shell-modal')).toHaveCount(0);
    };

    await page.locator('.service-shell-icon-btn[aria-label="Přepnout motiv"]').click();
    await expect(page.locator('body')).toHaveClass(/service-shell-theme-light/);

    await page.locator('.service-shell-userbox').click();
    await expect(page.locator('.service-shell-account-menu')).toContainText('Otevřít nastavení účtu');
    await page.getByRole('button', { name: 'Otevřít nastavení účtu' }).click();
    await expect(page.locator('.service-shell-modal-title')).toContainText('Nastavení účtu');
    await closeModal();

    await page.locator('.service-shell-userbox').click();
    await page.getByRole('button', { name: 'Otevřít profil' }).click();
    await expect(page.locator('[data-service-shell="root"]')).toContainText('Aktivní technici');

    await page.getByRole('button', { name: 'Faktury' }).click();
    await expect(page.locator('[data-service-shell="root"]')).toContainText('Servisní faktury');

    await page.getByRole('button', { name: 'Dashboard' }).click();
    await page.locator('.service-shell-kpi').nth(0).click();
    await expect(page.locator('[data-service-shell="root"]')).toContainText('Aktivní zakázky');
    await page.locator('.service-shell-kpi').nth(1).click();
    await page.locator('.service-shell-side-card').filter({ hasText: 'Fronta práce' }).locator('.service-shell-list-row').nth(0).click();
    await page.locator('.service-shell-side-card').filter({ hasText: 'Fronta práce' }).locator('.service-shell-list-row').nth(1).click();

    await page.locator('.service-shell-userbox').click();
    await page.getByRole('button', { name: 'Odhlásit se' }).click();
    await expect(page.locator('[data-testid="login-form"]')).toBeVisible({ timeout: 10000 });
  });
});
