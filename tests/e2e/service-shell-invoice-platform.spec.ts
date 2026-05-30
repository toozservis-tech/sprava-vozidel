import { expect, test } from '@playwright/test';

import { getServiceTestCredentials, loginServiceUser } from './helpers';
import {
  bootstrapAuthenticatedQuotePlatformShell,
  installQuotePlatformMocks,
} from './service-shell-fallback.helpers';

async function openInvoiceDetail(page: import('@playwright/test').Page) {
  await bootstrapAuthenticatedQuotePlatformShell(page);
  await expect(page.locator('[data-testid="service-billing-section"]')).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('[data-testid="login-form"]')).not.toBeVisible();

  const invoiceRow = page.locator('[data-testid="service-billing-invoice-row"]').first();
  await expect(invoiceRow).toBeVisible({ timeout: 15_000 });

  const invoiceDetailResponse = page.waitForResponse(
    (response) => /\/api\/service\/invoices\/\d+$/.test(new URL(response.url()).pathname)
      && response.request().method() === 'GET'
      && response.ok(),
  );
  await invoiceRow.click();
  await invoiceDetailResponse;

  const detailModal = page.locator('.service-shell-modal').filter({
    has: page.locator('[data-testid="service-billing-invoice-detail"]'),
  });
  await expect(detailModal).toBeVisible({ timeout: 20_000 });
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

test.describe('Service invoice platform documents', () => {
  test.beforeEach(async () => {
    test.skip(!getServiceTestCredentials(), 'Nastavte E2E_SERVICE_EMAIL a E2E_SERVICE_PASSWORD');
  });

  test('service_invoice_detail_shows_document_card', async ({ page }) => {
    const detailModal = await openInvoiceDetail(page);
    await expect(detailModal.locator('[data-testid="service-invoice-document-card"]')).toBeVisible();
    await expect(detailModal.locator('[data-testid="service-invoice-pdf-preview"]')).toBeVisible();
    await expect(detailModal.locator('[data-testid="service-invoice-status-badge"]').first()).toBeVisible();
  });

  test('service_invoice_pdf_button_opens_platform_pdf', async ({ page }) => {
    const detailModal = await openInvoiceDetail(page);
    const preview = detailModal.locator('[data-testid="service-invoice-pdf-preview"]');
    await expect(preview.locator('[data-testid="service-invoice-open-pdf-button"]')).toHaveCount(1);
    const pdfResponsePromise = page.waitForResponse(/\/api\/v1\/vehicles\/\d+\/documents\/\d+\/file$/);
    await preview.locator('[data-testid="service-invoice-open-pdf-button"]').click();
    const pdfResponse = await pdfResponsePromise;
    expect(pdfResponse.ok()).toBeTruthy();
  });

  test('service_invoice_verify_action_visible', async ({ page }) => {
    const detailModal = await openInvoiceDetail(page);
    await expect(
      detailModal.locator('[data-testid="service-invoice-pdf-preview"] [data-testid="service-invoice-verify-button"]'),
    ).toBeVisible();
  });

  test('vehicle_documents_contains_invoice_for_service @service', async ({ page }) => {
    const docs = await fetchMockVehicleDocuments(page);
    expect(Array.isArray(docs)).toBeTruthy();
    expect(docs.some((d: { document_type?: string }) => d.document_type === 'invoice')).toBeTruthy();
  });

  test('owner_safe_documents_do_not_show_private_invoice', async ({ page }) => {
    const docs = await fetchMockVehicleDocuments(page);
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
    const detailModal = await openInvoiceDetail(page);
    const card = detailModal.locator('[data-testid="service-invoice-document-card"]');
    await expect(card).toBeVisible();
    await expect(detailModal.locator('[data-testid="service-invoice-pdf-preview"]')).toBeVisible();
    const overflow = await card.evaluate((el) => {
      const node = el as HTMLElement;
      return node.scrollWidth > node.clientWidth + 2;
    });
    expect(overflow).toBeFalsy();
  });
});
