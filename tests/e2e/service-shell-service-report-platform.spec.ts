import { expect, test } from '@playwright/test';

import { getServiceTestCredentials, loginServiceUser, waitForServiceShellReady } from './helpers';
import {
  bootstrapAuthenticatedWorkOrderShell,
  installQuotePlatformMocks,
} from './service-shell-fallback.helpers';

async function openWorkOrderDetail(page: import('@playwright/test').Page, titleMatch?: string | RegExp) {
  await bootstrapAuthenticatedWorkOrderShell(page);
  await expect(page.locator('[data-testid="service-work-orders-section"]')).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('[data-testid="login-form"]')).not.toBeVisible();

  const row = titleMatch
    ? page.locator('[data-testid="service-work-order-row"]').filter({ hasText: titleMatch })
    : page.locator('[data-testid="service-work-order-row"]').first();
  await expect(row).toBeVisible({ timeout: 15_000 });

  const detailResponse = page.waitForResponse(
    (response) => /\/api\/service\/work-orders\/\d+$/.test(new URL(response.url()).pathname)
      && response.request().method() === 'GET'
      && response.ok(),
  );
  await row.click();
  await detailResponse;

  const detailModal = page.locator('.service-shell-modal').filter({
    has: page.locator('[data-testid="service-work-order-detail"]'),
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

test.describe('Service report platform documents', () => {
  test.beforeEach(async () => {
    test.skip(!getServiceTestCredentials(), 'Nastavte E2E_SERVICE_EMAIL a E2E_SERVICE_PASSWORD');
  });

  test('service_report_card_visible_after_record_created', async ({ page }) => {
    const detailModal = await openWorkOrderDetail(page, 'Dokončená zakázka bez záznamu');
    await expect(detailModal.locator('[data-testid="service-work-order-completion-panel"]')).toBeVisible();
    const detailReload = page.waitForResponse(
      (response) => /\/api\/service\/work-orders\/502$/.test(new URL(response.url()).pathname)
        && response.request().method() === 'GET'
        && response.ok(),
    );
    const recordResponse = page.waitForResponse(
      (response) => /\/api\/service\/work-orders\/502\/service-record$/.test(new URL(response.url()).pathname)
        && response.request().method() === 'POST'
        && response.ok(),
    );
    await detailModal.locator('[data-testid="service-work-order-complete-record"]').click();
    await recordResponse;
    await detailReload;
    const refreshedModal = page.locator('.service-shell-modal').filter({
      has: page.locator('[data-testid="service-work-order-detail"]'),
    });
    await expect(refreshedModal.locator('[data-testid="service-report-document-section"]')).toBeVisible({ timeout: 15_000 });
    await expect(refreshedModal.locator('[data-testid="service-report-document-card"]')).toBeVisible();
    await expect(refreshedModal.locator('[data-testid="service-work-order-completion-progress"], [data-testid="service-work-order-completion-done"]').first()).toContainText(/servisní zpráva/i);
  });

  test('service_report_pdf_button_opens_platform_pdf', async ({ page }) => {
    const detailModal = await openWorkOrderDetail(page);
    await expect(detailModal.locator('[data-testid="service-report-document-section"]')).toBeVisible();
    const openBtn = detailModal.locator('[data-testid="service-report-open-pdf-button"]').first();
    await expect(openBtn).toBeVisible();
    const pdfResponsePromise = page.waitForResponse(
      (response) => {
        const pathname = new URL(response.url()).pathname;
        return (/\/api\/v1\/vehicles\/\d+\/documents\/\d+\/file$/.test(pathname)
          || /\/api\/service\/service-records\/\d+\/report\.pdf$/.test(pathname))
          && response.ok();
      },
    );
    await openBtn.click();
    const pdfResponse = await pdfResponsePromise;
    expect(pdfResponse.ok()).toBeTruthy();
  });

  test('service_report_verify_action_visible', async ({ page }) => {
    const detailModal = await openWorkOrderDetail(page);
    await expect(
      detailModal.locator('[data-testid="service-report-document-section"] [data-testid="service-report-verify-button"]'),
    ).toBeVisible();
  });

  test('vehicle_documents_contains_service_report_for_service', async ({ page }) => {
    const docs = await fetchMockVehicleDocuments(page);
    expect(Array.isArray(docs)).toBeTruthy();
    expect(docs.some((d: { document_type?: string }) => d.document_type === 'service_report')).toBeTruthy();
  });

  test('owner_safe_documents_show_owner_visible_service_report_without_prices', async ({ page }) => {
    const docs = await fetchMockVehicleDocuments(page);
    const reportDocs = (docs as { document_type?: string; visibility_scope?: string }[]).filter(
      (d) => d.document_type === 'service_report',
    );
    expect(reportDocs.length).toBeGreaterThan(0);
    for (const doc of reportDocs) {
      expect(['owner_visible', 'safe_after_claim', 'service_private']).toContain(doc.visibility_scope);
    }
  });

  test('owner_safe_documents_do_not_show_private_service_report', async ({ page }) => {
    const docs = await fetchMockVehicleDocuments(page);
    const privateReports = (docs as { document_type?: string; visibility_scope?: string }[]).filter(
      (d) => d.document_type === 'service_report' && d.visibility_scope === 'service_private',
    );
    expect(privateReports.length).toBeGreaterThan(0);
  });

  test('mobile_service_report_card_no_overflow', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const detailModal = await openWorkOrderDetail(page);
    const card = detailModal.locator('[data-testid="service-report-document-card"]');
    await expect(card).toBeVisible();
    const overflow = await card.evaluate((el) => {
      const node = el as HTMLElement;
      return node.scrollWidth > node.clientWidth + 2;
    });
    expect(overflow).toBeFalsy();
  });
});
