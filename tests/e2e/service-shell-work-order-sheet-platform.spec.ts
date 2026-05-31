import { expect, test } from '@playwright/test';

import { getServiceTestCredentials, loginServiceUser } from './helpers';
import {
  bootstrapAuthenticatedWorkOrderShell,
  installQuotePlatformMocks,
} from './service-shell-fallback.helpers';

async function openWorkOrderDetail(page: import('@playwright/test').Page) {
  await bootstrapAuthenticatedWorkOrderShell(page);
  await expect(page.locator('[data-testid="service-work-orders-section"]')).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('[data-testid="login-form"]')).not.toBeVisible();

  const row = page.locator('[data-testid="service-work-order-row"]').first();
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
  await expect(detailModal.locator('[data-testid="service-work-order-sheet-section"]')).toBeVisible({ timeout: 15_000 });
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

test.describe('Service work order sheet platform documents', () => {
  test.beforeEach(async () => {
    test.skip(!getServiceTestCredentials(), 'Nastavte E2E_SERVICE_EMAIL a E2E_SERVICE_PASSWORD');
  });

  test('service_work_order_detail_shows_sheet_card', async ({ page }) => {
    const detailModal = await openWorkOrderDetail(page);
    await expect(detailModal.locator('[data-testid="service-work-order-sheet-document-card"]')).toBeVisible();
    await expect(detailModal.locator('[data-testid="service-work-order-sheet-open-pdf-button"]').first()).toBeVisible();
    await expect(detailModal.locator('[data-testid="service-work-order-sheet-status-badge"]').first()).toBeVisible();
  });

  test('service_work_order_sheet_pdf_button_opens_platform_pdf', async ({ page }) => {
    const detailModal = await openWorkOrderDetail(page);
    const section = detailModal.locator('[data-testid="service-work-order-sheet-section"]');
    const openBtn = section.locator('[data-testid="service-work-order-sheet-open-pdf-button"]').first();
    await expect(openBtn).toBeVisible();
    const pdfResponsePromise = page.waitForResponse(
      (response) => {
        const pathname = new URL(response.url()).pathname;
        return (/\/api\/v1\/vehicles\/\d+\/documents\/\d+\/file$/.test(pathname)
          || /\/api\/service\/work-orders\/\d+\/sheet\.pdf$/.test(pathname))
          && response.ok();
      },
    );
    await openBtn.click();
    const pdfResponse = await pdfResponsePromise;
    expect(pdfResponse.ok()).toBeTruthy();
  });

  test('service_work_order_sheet_verify_action_visible', async ({ page }) => {
    const detailModal = await openWorkOrderDetail(page);
    await expect(
      detailModal.locator('[data-testid="service-work-order-sheet-section"] [data-testid="service-work-order-sheet-verify-button"]'),
    ).toBeVisible();
  });

  test('vehicle_documents_contains_work_order_sheet_for_service', async ({ page }) => {
    const docs = await fetchMockVehicleDocuments(page);
    expect(Array.isArray(docs)).toBeTruthy();
    expect(docs.some((d: { document_type?: string }) => d.document_type === 'work_order_sheet')).toBeTruthy();
  });

  test('owner_safe_documents_do_not_show_private_work_order_sheet', async ({ page }) => {
    const docs = await fetchMockVehicleDocuments(page);
    const sheetDocs = (docs as { document_type?: string; visibility_scope?: string }[]).filter(
      (d) => d.document_type === 'work_order_sheet',
    );
    expect(sheetDocs.length).toBeGreaterThan(0);
    for (const doc of sheetDocs) {
      expect(doc.visibility_scope).not.toBe('owner_visible');
    }
  });

  test('mobile_work_order_sheet_card_no_overflow', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const detailModal = await openWorkOrderDetail(page);
    const card = detailModal.locator('[data-testid="service-work-order-sheet-document-card"]');
    await expect(card).toBeVisible();
    const overflow = await card.evaluate((el) => {
      const node = el as HTMLElement;
      return node.scrollWidth > node.clientWidth + 2;
    });
    expect(overflow).toBeFalsy();
  });
});
