import { expect, test } from '@playwright/test';

import { getServiceTestCredentials, loginServiceUser } from './helpers';
import {
  bootstrapAuthenticatedQuotePlatformShell,
  installQuotePlatformMocks,
} from './service-shell-fallback.helpers';

async function openQuoteDetail(page: import('@playwright/test').Page) {
  await bootstrapAuthenticatedQuotePlatformShell(page);
  await expect(page.locator('[data-testid="service-billing-section"]')).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('[data-testid="login-form"]')).not.toBeVisible();

  const quoteRow = page.locator('[data-testid="service-billing-quote-row"]').first();
  await expect(quoteRow).toBeVisible({ timeout: 15_000 });

  const quoteDetailResponse = page.waitForResponse(
    (response) => {
      const pathname = new URL(response.url()).pathname;
      return /\/api\/service\/quotes\/\d+$/.test(pathname)
        && response.request().method() === 'GET'
        && response.ok();
    },
  );
  await quoteRow.click();
  await quoteDetailResponse;

  const detailModal = page.locator('.service-shell-modal').filter({
    has: page.locator('[data-testid="service-billing-quote-detail"]'),
  });
  await expect(detailModal).toBeVisible({ timeout: 20_000 });
  await expect(detailModal.locator('[data-testid="service-quote-pdf-preview"]')).toBeVisible({ timeout: 15_000 });
  await expect(detailModal.locator('[data-testid="service-quote-open-pdf-button"]')).toHaveCount(1);
  return detailModal;
}

async function fetchMockVehicleDocuments(page: import('@playwright/test').Page) {
  await installQuotePlatformMocks(page);
  await loginServiceUser(page);
  return page.evaluate(async () => {
    const token = localStorage.getItem('accessToken') || '';
    const res = await fetch('/api/v1/vehicles/301/documents', {
      credentials: 'include',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      throw new Error(`documents fetch failed: ${res.status}`);
    }
    return res.json();
  });
}

test.describe('Service quote platform documents', () => {
  test.beforeEach(async () => {
    test.skip(!getServiceTestCredentials(), 'Nastavte E2E_SERVICE_EMAIL a E2E_SERVICE_PASSWORD');
  });

  test('service_quote_detail_shows_document_card', async ({ page }) => {
    const detailModal = await openQuoteDetail(page);
    await expect(detailModal.locator('[data-testid="service-quote-document-card"]')).toBeVisible();
    await expect(detailModal.locator('[data-testid="service-quote-pdf-preview"]')).toBeVisible();
    await expect(detailModal.locator('[data-testid="service-quote-status-badge"]').first()).toBeVisible();
  });

  test('service_quote_pdf_button_opens_platform_pdf', async ({ page }) => {
    const detailModal = await openQuoteDetail(page);
    const preview = detailModal.locator('[data-testid="service-quote-pdf-preview"]');
    await expect(preview.locator('[data-testid="service-quote-open-pdf-button"]')).toHaveCount(1);
    const pdfResponsePromise = page.waitForResponse(/\/api\/v1\/vehicles\/\d+\/documents\/\d+\/file$/);
    await preview.locator('[data-testid="service-quote-open-pdf-button"]').click();
    const pdfResponse = await pdfResponsePromise;
    expect(pdfResponse.ok()).toBeTruthy();
  });

  test('service_quote_verify_action_visible', async ({ page }) => {
    const detailModal = await openQuoteDetail(page);
    await expect(
      detailModal.locator('[data-testid="service-quote-pdf-preview"] [data-testid="service-quote-verify-button"]'),
    ).toBeVisible();
  });

  test('service_quote_create_invoice_still_works', async ({ page }) => {
    const detailModal = await openQuoteDetail(page);
    const createBtn = detailModal.locator('[data-testid="service-quote-create-invoice-button"]');
    await expect(createBtn).toBeVisible();
    const invoiceCreatePromise = page.waitForResponse(
      (response) => /\/api\/service\/invoices\/from-quote\/\d+$/.test(new URL(response.url()).pathname)
        && response.request().method() === 'POST'
        && response.ok(),
    );
    await createBtn.click();
    await invoiceCreatePromise;
    await expect(
      detailModal.locator('[data-testid="service-quote-create-invoice-loading"], [data-testid="service-quote-created-invoice-card"]').first(),
    ).toBeVisible({ timeout: 5000 });
    await expect(detailModal.locator('[data-testid="service-quote-created-invoice-card"]')).toBeVisible({
      timeout: 15_000,
    });
    await expect(detailModal).toContainText('Servisní faktura');
    await expect(detailModal.locator('[data-testid="service-quote-create-invoice-button"]')).toHaveCount(0);
  });

  test('vehicle_documents_contains_quote_for_service', async ({ page }) => {
    const docs = await fetchMockVehicleDocuments(page);
    expect(Array.isArray(docs)).toBeTruthy();
    expect(docs.some((d: { document_type?: string }) => d.document_type === 'quote')).toBeTruthy();
  });

  test('owner_safe_documents_do_not_show_private_quote', async ({ page }) => {
    const docs = await fetchMockVehicleDocuments(page);
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
    const detailModal = await openQuoteDetail(page);
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
