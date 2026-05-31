import { expect, test } from '@playwright/test';

import { getServiceTestCredentials, loginServiceUser, waitForServiceShellReady } from './helpers';
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
  await expect(detailModal.locator('[data-testid="service-intake-protocol-section"]')).toBeVisible({ timeout: 15_000 });
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

async function bootstrapIntakeWizardDone(page: import('@playwright/test').Page) {
  await installQuotePlatformMocks(page);
  await loginServiceUser(page);
  const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
  const slug = slugMatch?.[1] || 'e2e-fixed-service';

  await page.route('**/api/v1/services/workspace/vehicles/lookup', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        found: true,
        status: 'found_service_unowned',
        vehicle_preview: { vehicle_id: 301, brand: 'Skoda', model: 'Octavia', vin_masked: 'VIN***6789', plate_masked: '1AB***45' },
        access: { status: 'work_access' },
        owner_data: null,
      }),
    });
  });

  let nextCaseId = 801;
  await page.route('**/api/v1/services/workspace/service-cases/', async (route) => {
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      const id = nextCaseId++;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id,
          vehicle_id: body.vehicle_id || 301,
          status: 'intake_started',
          customer_request: body.customer_request || null,
          mileage_in: body.initial_mileage_km || null,
        }),
      });
      return;
    }
    await route.continue();
  });

  await page.goto(`/web/app/s/${slug}/intake`, { waitUntil: 'domcontentloaded' });
  await waitForServiceShellReady(page);

  await page.locator('[data-testid="service-intake-plate-input"]').fill('1AB2345');
  await page.locator('[data-testid="service-intake-lookup-button"]').click();
  await expect(page.locator('[data-testid="service-intake-step-access-choice"]')).toBeVisible({ timeout: 15_000 });

  const clickNextStep = async () => {
    const next = page.getByRole('button', { name: /Další krok/i });
    await expect(next).toBeEnabled({ timeout: 10_000 });
    await next.click();
  };

  await clickNextStep();
  await clickNextStep();
  await expect(page.locator('[data-testid="service-intake-step-condition-report"]')).toBeVisible({ timeout: 15_000 });

  await page.locator('[data-testid="service-intake-arrival-condition"]').fill('Auto přijelo v pořádku');
  await page.locator('[data-testid="service-intake-customer-complaint"]').fill('Kontrola úniku kapaliny');
  await page.locator('[data-testid="service-intake-technician-note"]').fill('Vizuální kontrola');

  await clickNextStep();

  const createBtn = page.locator('[data-testid="service-intake-create-draft-work-order"]');
  await expect(createBtn).toBeVisible({ timeout: 10_000 });
  const woResponse = page.waitForResponse(
    (response) => /\/api\/service\/work-orders\/?$/.test(new URL(response.url()).pathname)
      && response.request().method() === 'POST'
      && response.ok(),
  );
  await createBtn.click();
  await woResponse;

  await expect(page.locator('[data-testid="service-intake-step-done"]')).toBeVisible({ timeout: 20_000 });
}

test.describe('Service intake protocol platform documents', () => {
  test.beforeEach(async () => {
    test.skip(!getServiceTestCredentials(), 'Nastavte E2E_SERVICE_EMAIL a E2E_SERVICE_PASSWORD');
  });

  test('service_work_order_detail_shows_intake_protocol_card', async ({ page }) => {
    const detailModal = await openWorkOrderDetail(page);
    await expect(detailModal.locator('[data-testid="service-intake-protocol-document-card"]')).toBeVisible();
    await expect(detailModal.locator('[data-testid="service-intake-protocol-open-pdf-button"]').first()).toBeVisible();
    await expect(detailModal.locator('[data-testid="service-intake-protocol-status-badge"]').first()).toBeVisible();
  });

  test('service_intake_protocol_pdf_button_opens_platform_pdf', async ({ page }) => {
    const detailModal = await openWorkOrderDetail(page);
    const section = detailModal.locator('[data-testid="service-intake-protocol-section"]');
    const openBtn = section.locator('[data-testid="service-intake-protocol-open-pdf-button"]').first();
    await expect(openBtn).toBeVisible();
    const pdfResponsePromise = page.waitForResponse(
      (response) => {
        const pathname = new URL(response.url()).pathname;
        return (/\/api\/v1\/vehicles\/\d+\/documents\/\d+\/file$/.test(pathname)
          || /\/api\/service\/intakes\/\d+\/protocol\.pdf$/.test(pathname))
          && response.ok();
      },
    );
    await openBtn.click();
    const pdfResponse = await pdfResponsePromise;
    expect(pdfResponse.ok()).toBeTruthy();
  });

  test('service_intake_protocol_verify_action_visible', async ({ page }) => {
    const detailModal = await openWorkOrderDetail(page);
    await expect(
      detailModal.locator('[data-testid="service-intake-protocol-section"] [data-testid="service-intake-protocol-verify-button"]'),
    ).toBeVisible();
  });

  test('vehicle_documents_contains_intake_protocol_for_service', async ({ page }) => {
    const docs = await fetchMockVehicleDocuments(page);
    expect(Array.isArray(docs)).toBeTruthy();
    expect(docs.some((d: { document_type?: string }) => d.document_type === 'intake_protocol')).toBeTruthy();
  });

  test('owner_safe_documents_do_not_show_private_intake_protocol', async ({ page }) => {
    const docs = await fetchMockVehicleDocuments(page);
    const protocolDocs = (docs as { document_type?: string; visibility_scope?: string }[]).filter(
      (d) => d.document_type === 'intake_protocol',
    );
    expect(protocolDocs.length).toBeGreaterThan(0);
    for (const doc of protocolDocs) {
      expect(doc.visibility_scope).not.toBe('owner_visible');
    }
  });

  test('mobile_intake_protocol_card_no_overflow', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const detailModal = await openWorkOrderDetail(page);
    const card = detailModal.locator('[data-testid="service-intake-protocol-document-card"]');
    await expect(card).toBeVisible();
    const overflow = await card.evaluate((el) => {
      const node = el as HTMLElement;
      return node.scrollWidth > node.clientWidth + 2;
    });
    expect(overflow).toBeFalsy();
  });

  test('service_intake_protocol_card_visible_after_intake', async ({ page }) => {
    await bootstrapIntakeWizardDone(page);
    await expect(page.locator('[data-testid="service-intake-open-protocol-button"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-intake-open-work-order-sheet-button"]')).toBeVisible();
  });
});
