import { expect, test } from '@playwright/test';

import {
  getServiceTestCredentials,
  loginServiceUser,
  waitForServiceShellReady,
} from './helpers';

const inventoryItemsPath = '**/api/service/inventory/items**';

async function openPartsStock(page: Parameters<typeof test>[0]['page']) {
  const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
  const slug = slugMatch?.[1] || 'e2e-fixed-service';
  await page.goto(`/web/app/s/${slug}/parts-stock`, { waitUntil: 'domcontentloaded' });
  await waitForServiceShellReady(page);
}

test.describe('Service shell inventory', () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!getServiceTestCredentials(), 'Nastavte E2E_SERVICE_EMAIL a E2E_SERVICE_PASSWORD');
    await loginServiceUser(page);
    await waitForServiceShellReady(page);
  });

  test('service_inventory_route_loads', async ({ page }) => {
    await page.route(inventoryItemsPath, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], count: 0 }),
      });
    });
    await openPartsStock(page);
    await expect(page.locator('[data-testid="service-inventory-section"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-inventory-add-button"]')).toBeVisible();
  });

  test('service_inventory_empty_state', async ({ page }) => {
    await page.route(inventoryItemsPath, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], count: 0 }),
      });
    });
    await openPartsStock(page);
    await expect(page.locator('[data-testid="service-inventory-empty"]')).toBeVisible();
  });

  test('service_inventory_add_item_or_limited', async ({ page }) => {
    test.skip(process.env.E2E_ALLOW_MUTATIONS !== '1', 'Mutační test vyžaduje E2E_ALLOW_MUTATIONS=1');
    await page.route(inventoryItemsPath, async (route) => {
      if (route.request().method() === 'POST') {
        const body = route.request().postDataJSON();
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 901,
            name: body?.name || 'E2E díl',
            quantity_on_hand: 3,
            min_quantity: 1,
            unit: 'ks',
            is_low_stock: false,
            is_active: true,
          }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [{ id: 901, name: 'E2E díl', quantity_on_hand: 3, min_quantity: 1, unit: 'ks', is_low_stock: false }],
          count: 1,
        }),
      });
    });
    await openPartsStock(page);
    await page.locator('[data-testid="service-inventory-add-button"]').click();
    await expect(page.locator('[data-testid="service-inventory-form"]')).toBeVisible();
    await page.locator('[data-testid="service-inventory-form"] input').nth(1).fill('E2E díl');
    await page.locator('[data-testid="service-inventory-save-button"]').click();
    await expect(page.locator('[data-testid="service-inventory-item-row"]')).toContainText(/E2E díl/i);
  });

  test('service_inventory_low_stock_badge', async ({ page }) => {
    await page.route(inventoryItemsPath, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [{
            id: 902,
            name: 'Kritický díl',
            quantity_on_hand: 1,
            min_quantity: 5,
            unit: 'ks',
            is_low_stock: true,
          }],
          count: 1,
        }),
      });
    });
    await openPartsStock(page);
    await expect(page.locator('[data-testid="service-inventory-low-stock-badge"]')).toBeVisible();
  });

  test('service_inventory_f5_keeps_session', async ({ page }) => {
    await page.route(inventoryItemsPath, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], count: 0 }),
      });
    });
    await openPartsStock(page);
    const before = page.url();
    await page.reload({ waitUntil: 'domcontentloaded' });
    await waitForServiceShellReady(page);
    await expect(page).toHaveURL(before);
    await expect(page.locator('[data-testid="service-inventory-section"]')).toBeVisible();
  });

  test('service_inventory_no_fake_success', async ({ page }) => {
    await page.route(inventoryItemsPath, async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({ status: 422, contentType: 'application/json', body: JSON.stringify({ detail: 'Chyba validace' }) });
        return;
      }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], count: 0 }) });
    });
    await openPartsStock(page);
    await page.locator('[data-testid="service-inventory-add-button"]').click();
    await page.locator('[data-testid="service-inventory-form"] input').nth(1).fill('Fail díl');
    await page.locator('[data-testid="service-inventory-save-button"]').click();
    await expect(page.locator('[data-testid="service-inventory-error"]')).toBeVisible();
  });
});
