import { expect, test } from '@playwright/test';

const hasAuth = !!process.env.E2E_USER_EMAIL && !!process.env.E2E_USER_PASSWORD;
const hasServiceAuth = !!process.env.E2E_SERVICE_EMAIL && !!process.env.E2E_SERVICE_PASSWORD;

test.describe('Vehicle document platform cards (C1.0)', () => {
  test.skip(!hasServiceAuth, 'Requires E2E_SERVICE_EMAIL and E2E_SERVICE_PASSWORD');

  test('service_vehicle_documents_cards_load @service', async ({ page, request }) => {
    const serviceEmail = process.env.E2E_SERVICE_EMAIL!;
    const servicePassword = process.env.E2E_SERVICE_PASSWORD!;

    await page.goto('/user/login');
    await page.fill('input[type="email"]', serviceEmail);
    await page.fill('input[type="password"]', servicePassword);
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/web\/app\//, { timeout: 30000 });

    const vehiclesResp = await request.get('/api/v1/services/workspace/approved-vehicles');
    expect(vehiclesResp.ok()).toBeTruthy();
    const vehiclesPayload = await vehiclesResp.json();
    const items = Array.isArray(vehiclesPayload?.items) ? vehiclesPayload.items : [];
    test.skip(items.length === 0, 'No approved vehicles for service fixture');

    const vehicleId = Number(items[0].id || items[0].vehicle_id);
    const createResp = await request.post(`/api/v1/vehicles/${vehicleId}/documents/platform`, {
      data: {
        document_type: 'invoice',
        document_status: 'draft',
        visibility_scope: 'owner_visible',
        title: 'E2E platform document',
      },
    });
    expect(createResp.ok()).toBeTruthy();

    await page.evaluate(() => {
      if (window.serviceShell && typeof window.serviceShell.navigate === 'function') {
        window.serviceShell.navigate('documents');
      }
    });
    await page.waitForTimeout(1500);

    const card = page.locator('[data-testid="vehicle-document-card"]').first();
    await expect(card).toBeVisible({ timeout: 15000 });
    await expect(card.locator('[data-testid="vehicle-document-thumbnail"]')).toBeVisible();
    await expect(card.locator('[data-testid="vehicle-document-type"]')).toBeVisible();
    await expect(card.locator('[data-testid="vehicle-document-status"]')).toBeVisible();
    await expect(card.locator('[data-testid="vehicle-document-open-button"]')).toBeVisible();
    await expect(card.locator('[data-testid="vehicle-document-download-button"]')).toBeVisible();
  });
});

test.describe('User vehicle document cards (C1.0)', () => {
  test.skip(!hasAuth, 'Requires E2E_USER_EMAIL and E2E_USER_PASSWORD');

  test('user_vehicle_documents_cards_load @user', async ({ page }) => {
    await page.goto('/user/login');
    await page.fill('input[type="email"]', process.env.E2E_USER_EMAIL!);
    await page.fill('input[type="password"]', process.env.E2E_USER_PASSWORD!);
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/web\/app\//, { timeout: 30000 });

    await page.evaluate(() => {
      if (window.userAppNext && typeof window.userAppNext.setView === 'function') {
        window.userAppNext.setView('documents');
      }
    });
    await page.waitForTimeout(1500);

    const section = page.locator('[data-testid="user-app-next-documents"]');
    await expect(section).toBeVisible({ timeout: 15000 });
  });
});

test('document_card_actions_visible @mobile', async ({ page }) => {
  test.skip(!hasServiceAuth, 'Requires service auth for platform fixture');
  await page.setViewportSize({ width: 390, height: 844 });

  await page.goto('/user/login');
  await page.fill('input[type="email"]', process.env.E2E_SERVICE_EMAIL!);
  await page.fill('input[type="password"]', process.env.E2E_SERVICE_PASSWORD!);
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/web\/app\//, { timeout: 30000 });

  await page.evaluate(() => {
    if (window.serviceShell && typeof window.serviceShell.navigate === 'function') {
      window.serviceShell.navigate('documents');
    }
  });
  await page.waitForTimeout(1500);

  const card = page.locator('[data-testid="vehicle-document-card"]').first();
  if (await card.count()) {
    const box = await card.boundingBox();
    expect(box).toBeTruthy();
    if (box) {
      expect(box.width).toBeLessThanOrEqual(390);
    }
    await expect(card.locator('[data-testid="vehicle-document-download-button"]')).toBeVisible();
  }
});

test('document_verify_link_opens_safe_page_or_endpoint @api', async ({ request }) => {
  const response = await request.get('/api/public/documents/verify/not-a-real-token');
  expect(response.ok()).toBeTruthy();
  const payload = await response.json();
  expect(payload.valid === false || payload.status === 'not_found').toBeTruthy();
  expect(JSON.stringify(payload)).not.toContain('@');
});
