import { expect, test } from '@playwright/test';

import { installServiceShellMocks } from './service-shell-fallback.helpers';

async function openMockQuoteDetail(page: import('@playwright/test').Page) {
  await page.goto('/web/index.html');
  await expect(page.locator('[data-service-shell="root"]')).toBeVisible({ timeout: 15000 });
  await page.evaluate(() => window.serviceShell.openBillingQuoteDetail(800));
  await expect(page.locator('.service-shell-modal').last()).toBeVisible({ timeout: 15000 });
}

test.describe('Service quote platform documents', () => {
  test('service_quote_detail_shows_document_card', async ({ page }) => {
    await installServiceShellMocks(page);
    await openMockQuoteDetail(page);
    const detailModal = page.locator('.service-shell-modal').last();
    await expect(detailModal.locator('[data-testid="service-quote-document-card"]')).toBeVisible();
    await expect(detailModal.locator('[data-testid="service-quote-pdf-preview"]')).toBeVisible();
    await expect(detailModal.locator('[data-testid="service-quote-status-badge"]')).toBeVisible();
  });

  test('service_quote_pdf_button_opens_platform_pdf', async ({ page }) => {
    await installServiceShellMocks(page);
    await openMockQuoteDetail(page);
    const detailModal = page.locator('.service-shell-modal').last();
    const popupPromise = page.waitForEvent('popup');
    const pdfResponsePromise = page.waitForResponse(/\/api\/v1\/vehicles\/\d+\/documents\/\d+\/file$/);
    await detailModal.locator('[data-testid="service-quote-open-pdf-button"]').click();
    const pdfPopup = await popupPromise;
    const pdfResponse = await pdfResponsePromise;
    expect(pdfResponse.ok()).toBeTruthy();
    await pdfPopup.close();
  });

  test('service_quote_verify_action_visible', async ({ page }) => {
    await installServiceShellMocks(page);
    await openMockQuoteDetail(page);
    const detailModal = page.locator('.service-shell-modal').last();
    await expect(detailModal.locator('[data-testid="service-quote-verify-button"]')).toBeVisible();
  });

  test('service_quote_create_invoice_still_works', async ({ page }) => {
    await installServiceShellMocks(page);
    await openMockQuoteDetail(page);
    const detailModal = page.locator('.service-shell-modal').last();
    await detailModal.locator('[data-testid="service-quote-create-invoice-button"]').click();
    await expect(page.locator('.service-shell-modal').last()).toContainText('Servisní faktura');
  });

  test('vehicle_documents_contains_quote_for_service', async ({ page }) => {
    await installServiceShellMocks(page);
    await page.goto('/web/index.html');
    const docs = await page.evaluate(async () => {
      const res = await fetch('/api/v1/vehicles/301/documents', { credentials: 'include' });
      return res.json();
    });
    expect(Array.isArray(docs)).toBeTruthy();
    expect(docs.some((d: { document_type?: string }) => d.document_type === 'quote')).toBeTruthy();
  });

  test('owner_safe_documents_do_not_show_private_quote', async ({ page }) => {
    await installServiceShellMocks(page);
    await page.goto('/web/index.html');
    const docs = await page.evaluate(async () => {
      const res = await fetch('/api/v1/vehicles/301/documents', { credentials: 'include' });
      return res.json();
    });
    const quoteDocs = (docs as { document_type?: string; visibility_scope?: string }[]).filter(
      (d) => d.document_type === 'quote',
    );
    expect(quoteDocs.length).toBeGreaterThan(0);
    for (const doc of quoteDocs) {
      expect(doc.visibility_scope).not.toBe('owner_visible');
    }
  });

  test('mobile_quote_card_no_overflow', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await installServiceShellMocks(page);
    await openMockQuoteDetail(page);
    const card = page.locator('[data-testid="service-quote-document-card"]');
    await expect(card).toBeVisible();
    const overflow = await card.evaluate((el) => {
      const node = el as HTMLElement;
      return node.scrollWidth > node.clientWidth + 2;
    });
    expect(overflow).toBeFalsy();
  });
});
