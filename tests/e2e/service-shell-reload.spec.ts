import { expect, test } from '@playwright/test';

import { installServiceShellMocks } from './service-shell-fallback.helpers';

test.describe('Service shell deep-link reload', () => {
  test('hydrates service workspace from /api/me before showing login', async ({ page }) => {
    await installServiceShellMocks(page, { seedCurrentUser: false, forceServiceWorkspaceRole: false });

    await page.goto('/web/app/s/toozservis/work-orders');
    await expect(page.locator('[data-service-shell="root"]')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[data-testid="login-form"]')).toBeHidden();
    await expect(page).toHaveURL(/\/web\/app\/s\/toozservis\/work-orders/);
    await expect(page.locator('[data-service-shell="root"]')).toContainText('Zakázky');

    await page.reload();
    await expect(page.locator('[data-service-shell="root"]')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[data-testid="login-form"]')).toBeHidden();
    await expect(page).toHaveURL(/\/web\/app\/s\/toozservis\/work-orders/);
    await expect(page.locator('[data-service-shell="root"]')).toContainText('Zakázky');

    await page.getByRole('button', { name: '+ Přijmout vozidlo' }).click();
    await expect(page).toHaveURL(/\/web\/app\/s\/toozservis\/intake/);
    await expect(page.locator('[data-service-shell="root"]')).toContainText('Rychlý příjem');

    await page.getByRole('button', { name: '+ Nová zakázka' }).click();
    await expect(page.locator('.service-shell-modal-title')).toContainText('Nová zakázka');
    await page.evaluate(() => (window as any).serviceShell.closeModal());

    await page.getByRole('button', { name: 'Přehled' }).click();
    await page.getByRole('button', { name: 'Zobrazit všechny zakázky' }).click();
    await expect(page).toHaveURL(/\/web\/app\/s\/toozservis\/work-orders/);

    await page.getByRole('button', { name: 'Přehled' }).click();
    await page.getByRole('button', { name: 'Zobrazit všechny rezervace' }).click();
    await expect(page).toHaveURL(/\/web\/app\/s\/toozservis\/reservations/);

    await page.getByRole('button', { name: 'Přehled' }).click();
    await page.getByRole('button', { name: 'Přístup povolen majitelem', exact: true }).click();
    await expect(page.locator('.service-shell-modal-title')).toContainText('Přístup povolen majitelem');
    await expect(page.locator('.service-shell-modal')).toContainText('/api/me');
  });
});
