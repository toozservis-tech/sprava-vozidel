import { expect, test } from '@playwright/test';

import { installServiceShellMocks } from './service-shell-fallback.helpers';

test.describe('Service invoice platform documents', () => {
  test('service_invoice_detail_shows_document_card', async ({ page }) => {
    await installServiceShellMocks(page);
    await page.goto('/web/index.html');
    await expect(page.locator('[data-service-shell="root"]')).toBeVisible({ timeout: 15000 });

    await page.locator('.service-shell-nav-btn', { hasText: 'Faktury' }).click();
    await page.locator('tr', { hasText: '1000' }).first().click();
    const detailModal = page.locator('.service-shell-modal').last();
    await expect(detailModal.locator('[data-testid="service-invoice-document-card"]')).toBeVisible();
    await expect(detailModal.locator('[data-testid="service-invoice-pdf-preview"]')).toBeVisible();
    await expect(detailModal.locator('[data-testid="service-invoice-status-badge"]')).toBeVisible();
  });

  test('service_invoice_pdf_button_opens_platform_pdf', async ({ page }) => {
    await installServiceShellMocks(page);
    await page.goto('/web/index.html');
    await expect(page.locator('[data-service-shell="root"]')).toBeVisible({ timeout: 15000 });

    await page.locator('.service-shell-nav-btn', { hasText: 'Faktury' }).click();
    await page.locator('tr', { hasText: '1000' }).first().click();
    const detailModal = page.locator('.service-shell-modal').last();
    const popupPromise = page.waitForEvent('popup');
    const pdfResponsePromise = page.waitForResponse(/\/api\/v1\/vehicles\/\d+\/documents\/\d+\/file$/);
    await detailModal.locator('[data-testid="service-invoice-open-pdf-button"]').click();
    const pdfPopup = await popupPromise;
    const pdfResponse = await pdfResponsePromise;
    expect(pdfResponse.ok()).toBeTruthy();
    await pdfPopup.close();
  });

  test('service_invoice_verify_action_visible', async ({ page }) => {
    await installServiceShellMocks(page);
    await page.goto('/web/index.html');
    await expect(page.locator('[data-service-shell="root"]')).toBeVisible({ timeout: 15000 });

    await page.locator('.service-shell-nav-btn', { hasText: 'Faktury' }).click();
    await page.locator('tr', { hasText: '1000' }).first().click();
    const detailModal = page.locator('.service-shell-modal').last();
    await expect(detailModal.locator('[data-testid="service-invoice-verify-button"]')).toBeVisible();
  });

  test('vehicle_documents_contains_invoice_for_service @service', async ({ page }) => {
    await installServiceShellMocks(page);
    await page.goto('/web/index.html');
    await expect(page.locator('[data-service-shell="root"]')).toBeVisible({ timeout: 15000 });

    await page.evaluate(async () => {
      const res = await fetch('/api/v1/vehicles/301/documents', { credentials: 'include' });
      return res.json();
    }).then(async (docs) => {
      const items = await docs;
      expect(Array.isArray(items)).toBeTruthy();
      expect(items.some((d: { document_type?: string }) => d.document_type === 'invoice')).toBeTruthy();
    });
  });

  test('owner_safe_documents_do_not_show_private_invoice', async ({ page }) => {
    await installServiceShellMocks(page);
    await page.goto('/web/index.html');
    const docs = await page.evaluate(async () => {
      const res = await fetch('/api/v1/vehicles/301/documents', { credentials: 'include' });
      return res.json();
    });
    const invoiceDocs = (docs as { document_type?: string; visibility_scope?: string }[]).filter(
      (d) => d.document_type === 'invoice',
    );
    expect(invoiceDocs.length).toBeGreaterThan(0);
    for (const doc of invoiceDocs) {
      expect(doc.visibility_scope).not.toBe('owner_visible');
    }
  });

  test('mobile_invoice_card_no_overflow', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await installServiceShellMocks(page);
    await page.goto('/web/index.html');
    await expect(page.locator('[data-service-shell="root"]')).toBeVisible({ timeout: 15000 });

    await page.locator('.service-shell-nav-btn', { hasText: 'Faktury' }).click();
    await page.locator('tr', { hasText: '1000' }).first().click();
    const card = page.locator('[data-testid="service-invoice-document-card"]');
    await expect(card).toBeVisible();
    const overflow = await card.evaluate((el) => {
      const node = el as HTMLElement;
      return node.scrollWidth > node.clientWidth + 2;
    });
    expect(overflow).toBeFalsy();
  });
});
