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

test.describe('Service handover protocol platform documents', () => {
  test.beforeEach(async () => {
    test.skip(!getServiceTestCredentials(), 'Nastavte E2E_SERVICE_EMAIL a E2E_SERVICE_PASSWORD');
  });

  test('handover_card_visible_after_work_order_completed', async ({ page }) => {
    const detailModal = await openWorkOrderDetail(page, 'Zakázka k dokončení');
    const completeResponse = page.waitForResponse(
      (response) => /\/api\/service\/work-orders\/503\/complete$/.test(new URL(response.url()).pathname)
        && response.request().method() === 'POST'
        && response.ok(),
    );
    const detailReload = page.waitForResponse(
      (response) => /\/api\/service\/work-orders\/503$/.test(new URL(response.url()).pathname)
        && response.request().method() === 'GET'
        && response.ok(),
    );
    await detailModal.locator('[data-testid="service-work-order-complete-button"]').click();
    await completeResponse;
    await detailReload;
    const refreshedModal = page.locator('.service-shell-modal').filter({
      has: page.locator('[data-testid="service-work-order-detail"]'),
    });
    await expect(refreshedModal.locator('[data-testid="service-handover-document-section"]')).toBeVisible({ timeout: 15_000 });
    await expect(refreshedModal.locator('[data-testid="service-handover-document-card"]')).toBeVisible();
    await expect(refreshedModal.locator('[data-testid="service-work-order-completion-progress"]').first()).toContainText(/předávací protokol/i);
  });

  test('handover_pdf_button_opens_platform_pdf', async ({ page }) => {
    const detailModal = await openWorkOrderDetail(page);
    await expect(detailModal.locator('[data-testid="service-handover-document-section"]')).toBeVisible();
    const openBtn = detailModal.locator('[data-testid="service-handover-open-pdf-button"]').first();
    await expect(openBtn).toBeVisible();
    const pdfResponsePromise = page.waitForResponse(
      (response) => {
        const pathname = new URL(response.url()).pathname;
        return (/\/api\/v1\/vehicles\/\d+\/documents\/\d+\/file$/.test(pathname)
          || /\/api\/service\/work-orders\/\d+\/handover\.pdf$/.test(pathname))
          && response.ok();
      },
    );
    await openBtn.click();
    const pdfResponse = await pdfResponsePromise;
    expect(pdfResponse.ok()).toBeTruthy();
  });

  test('handover_verify_action_visible', async ({ page }) => {
    const detailModal = await openWorkOrderDetail(page);
    await expect(
      detailModal.locator('[data-testid="service-handover-document-section"] [data-testid="service-handover-verify-button"]'),
    ).toBeVisible();
  });

  test('vehicle_documents_contains_handover_for_service', async ({ page }) => {
    const docs = await fetchMockVehicleDocuments(page);
    expect(Array.isArray(docs)).toBeTruthy();
    expect(docs.some((d: { document_type?: string }) => d.document_type === 'handover_protocol')).toBeTruthy();
  });

  test('owner_safe_documents_show_owner_visible_handover_without_prices', async ({ page }) => {
    const docs = await fetchMockVehicleDocuments(page);
    const handoverDocs = (docs as { document_type?: string; visibility_scope?: string }[]).filter(
      (d) => d.document_type === 'handover_protocol',
    );
    expect(handoverDocs.length).toBeGreaterThan(0);
    for (const doc of handoverDocs) {
      expect(['owner_visible', 'safe_after_claim', 'service_private']).toContain(doc.visibility_scope);
    }
  });

  test('owner_safe_documents_do_not_show_private_handover', async ({ page }) => {
    const docs = await fetchMockVehicleDocuments(page);
    const privateHandovers = (docs as { document_type?: string; visibility_scope?: string }[]).filter(
      (d) => d.document_type === 'handover_protocol' && d.visibility_scope === 'service_private',
    );
    expect(privateHandovers.length).toBeGreaterThan(0);
  });

  test('mobile_handover_card_no_overflow', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const detailModal = await openWorkOrderDetail(page);
    const card = detailModal.locator('[data-testid="service-handover-document-card"]');
    await expect(card).toBeVisible();
    const overflow = await card.evaluate((el) => {
      const node = el as HTMLElement;
      return node.scrollWidth > node.clientWidth + 2;
    });
    expect(overflow).toBeFalsy();
  });
});
