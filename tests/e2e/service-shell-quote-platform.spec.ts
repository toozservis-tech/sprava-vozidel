import { expect, test } from '@playwright/test';

import { bootstrapMockServiceShell } from './service-shell-fallback.helpers';

async function openMockQuoteDetail(page: import('@playwright/test').Page) {
  await bootstrapMockServiceShell(page);
  await page.evaluate(async () => {
    if (typeof window.serviceShell?.openBillingQuoteDetail !== 'function') {
      throw new Error('serviceShell.openBillingQuoteDetail unavailable');
    }
    window.serviceShell.openBillingQuoteDetail(800);
    for (let attempt = 0; attempt < 60; attempt += 1) {
      const detail = document.querySelector('[data-testid="service-billing-quote-detail"]');
      const preview = detail?.querySelector('[data-testid="service-quote-pdf-preview"]');
      const openBtn = detail?.querySelector('[data-testid="service-quote-open-pdf-button"]');
      if (detail && preview && openBtn) return;
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    throw new Error('quote billing detail modal did not render platform document card');
  });
  const detailModal = page.locator('.service-shell-modal').filter({
    has: page.locator('[data-testid="service-billing-quote-detail"]'),
  });
  await expect(detailModal).toBeVisible({ timeout: 15000 });
  return detailModal;
}

test.describe('Service quote platform documents', () => {
  test('service_quote_detail_shows_document_card', async ({ page }) => {
    const detailModal = await openMockQuoteDetail(page);
    await expect(detailModal.locator('[data-testid="service-quote-document-card"]')).toBeVisible();
    await expect(detailModal.locator('[data-testid="service-quote-pdf-preview"]')).toBeVisible();
    await expect(detailModal.locator('[data-testid="service-quote-status-badge"]').first()).toBeVisible();
  });

  test('service_quote_pdf_button_opens_platform_pdf', async ({ page }) => {
    const detailModal = await openMockQuoteDetail(page);
    const preview = detailModal.locator('[data-testid="service-quote-pdf-preview"]');
    await expect(preview.locator('[data-testid="service-quote-open-pdf-button"]')).toHaveCount(1);
    const popupPromise = page.waitForEvent('popup');
    const pdfResponsePromise = page.waitForResponse(/\/api\/v1\/vehicles\/\d+\/documents\/\d+\/file$/);
    await preview.locator('[data-testid="service-quote-open-pdf-button"]').click();
    const pdfPopup = await popupPromise;
    const pdfResponse = await pdfResponsePromise;
    expect(pdfResponse.ok()).toBeTruthy();
    await pdfPopup.close();
  });

  test('service_quote_verify_action_visible', async ({ page }) => {
    const detailModal = await openMockQuoteDetail(page);
    await expect(
      detailModal.locator('[data-testid="service-quote-pdf-preview"] [data-testid="service-quote-verify-button"]'),
    ).toBeVisible();
  });

  test('service_quote_create_invoice_still_works', async ({ page }) => {
    const detailModal = await openMockQuoteDetail(page);
    await detailModal.locator('[data-testid="service-quote-create-invoice-button"]').click();
    await expect(detailModal.locator('[data-testid="service-quote-create-invoice-loading"]').first()).toBeVisible();
    await expect(detailModal.locator('[data-testid="service-quote-created-invoice-card"]')).toBeVisible({
      timeout: 15000,
    });
    await expect(detailModal).toContainText('Servisní faktura');
    await expect(detailModal.locator('[data-testid="service-quote-create-invoice-button"]')).toHaveCount(0);
  });

  test('vehicle_documents_contains_quote_for_service', async ({ page }) => {
    await bootstrapMockServiceShell(page, { requireShell: false });
    const docs = await page.evaluate(async () => {
      const res = await fetch('/api/v1/vehicles/301/documents', { credentials: 'include' });
      return res.json();
    });
    expect(Array.isArray(docs)).toBeTruthy();
    expect(docs.some((d: { document_type?: string }) => d.document_type === 'quote')).toBeTruthy();
  });

  test('owner_safe_documents_do_not_show_private_quote', async ({ page }) => {
    await bootstrapMockServiceShell(page, { requireShell: false });
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
    const detailModal = await openMockQuoteDetail(page);
    const card = detailModal.locator('[data-testid="service-quote-document-card"]');
    await expect(card).toBeVisible();
    await expect(detailModal.locator('[data-testid="service-quote-pdf-preview"]')).toBeVisible();
    const overflow = await card.evaluate((el) => {
      const node = el as HTMLElement;
      return node.scrollWidth > node.clientWidth + 2;
    });
    expect(overflow).toBeFalsy();
  });
});
