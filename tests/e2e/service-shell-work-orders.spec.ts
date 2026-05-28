import { expect, test } from '@playwright/test';

import {
  getServiceTestCredentials,
  loginServiceUser,
  waitForServiceShellReady,
} from './helpers';

async function openWorkOrders(page: Parameters<typeof test>[0]['page']) {
  const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
  const slug = slugMatch?.[1] || 'e2e-fixed-service';
  await page.goto(`/web/app/s/${slug}/work-orders`, { waitUntil: 'domcontentloaded' });
  await waitForServiceShellReady(page);
}

test.describe('Service shell work orders route', () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!getServiceTestCredentials(), 'Nastavte E2E_SERVICE_EMAIL a E2E_SERVICE_PASSWORD');
    await loginServiceUser(page);
    await waitForServiceShellReady(page);
  });

  test('service_work_orders_route_loads', async ({ page }) => {
    await openWorkOrders(page);
    await expect(page.locator('[data-testid="service-work-orders-section"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-work-orders-new-button"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-work-orders-search"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-work-orders-list"]')).toBeVisible();
  });

  test('service_work_orders_f5_keeps_session', async ({ page }) => {
    await openWorkOrders(page);
    const before = page.url();
    await page.reload({ waitUntil: 'domcontentloaded' });
    await waitForServiceShellReady(page);
    await expect(page).toHaveURL(before);
    await expect(page.locator('[data-testid="login-form"]')).not.toBeVisible();
    await expect(page.locator('[data-testid="service-work-orders-section"]')).toBeVisible();
  });

  test('service_work_order_new_button_opens_real_flow', async ({ page }) => {
    await openWorkOrders(page);
    await page.locator('[data-testid="service-work-orders-new-button"]').click();
    await expect(page.locator('.service-shell-modal-title')).toContainText(/nová zakázka/i);
    await expect(page.locator('#serviceShellWorkOrderOwner')).toBeVisible();
    await expect(page.locator('#serviceShellWorkOrderVehicle')).toBeVisible();
  });

  test('service_work_order_detail_loads', async ({ page }) => {
    await openWorkOrders(page);
    if ((await page.locator('[data-testid="service-work-order-row"]').count()) === 0) {
      test.skip(true, 'Žádná dostupná zakázka pro detail test v tomto prostředí.');
    }
    const row = page.locator('[data-testid="service-work-order-row"]').first();
    await expect(row).toBeVisible();
    await row.click();
    await expect(page.locator('[data-testid="service-work-order-detail"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-work-order-status"]')).toBeVisible();
  });

  test('service_work_order_add_labor_or_limited', async ({ page }) => {
    await openWorkOrders(page);
    if ((await page.locator('[data-testid="service-work-order-row"]').count()) === 0) {
      test.skip(true, 'Žádná dostupná zakázka pro limited-state test v tomto prostředí.');
    }
    await page.locator('[data-testid="service-work-order-row"]').first().click();
    const addLabor = page.locator('[data-testid="service-work-order-add-labor-button"]');
    await expect(addLabor).toBeDisabled();
    await expect(addLabor).toHaveAttribute('title', /doplněna v další fázi/i);
  });

  test('service_work_order_create_quote_or_limited', async ({ page }) => {
    await openWorkOrders(page);
    if ((await page.locator('[data-testid="service-work-order-row"]').count()) === 0) {
      test.skip(true, 'Žádná dostupná zakázka pro quote test v tomto prostředí.');
    }
    await page.locator('[data-testid="service-work-order-row"]').first().click();
    const createQuote = page.locator('[data-testid="service-work-order-create-quote-button"]');
    await expect(createQuote).toBeVisible();
  });
});
