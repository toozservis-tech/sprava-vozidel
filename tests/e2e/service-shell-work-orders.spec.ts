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
    await expect(page.locator('[data-testid="service-work-order-labor-list"]')).toBeVisible();
    const addLabor = page.locator('[data-testid="service-work-order-add-labor-button"]');
    await expect(addLabor).toBeEnabled();
    await expect(page.locator('[data-testid="service-work-order-photo-list"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-work-order-photo-limited-notice"]')).toContainText(
      /Interní fotky a doklady nejsou viditelné pro majitele/i,
    );
  });

  test('service_work_order_item_edit_delete_or_limited', async ({ page }) => {
    await openWorkOrders(page);
    if ((await page.locator('[data-testid="service-work-order-row"]').count()) === 0) {
      test.skip(true, 'Žádná dostupná zakázka pro edit/delete test v tomto prostředí.');
    }
    await page.locator('[data-testid="service-work-order-row"]').first().click();
    await expect(page.locator('[data-testid="service-work-order-detail"]')).toBeVisible();
    const editButtons = page.locator('[data-testid="service-work-order-item-edit"]');
    const deleteButtons = page.locator('[data-testid="service-work-order-item-delete"]');
    const itemRows = page.locator('[data-testid="service-work-order-item-row"]');
    if ((await itemRows.count()) === 0) {
      const addLabor = page.locator('[data-testid="service-work-order-add-labor-button"]');
      await expect(addLabor).toBeVisible();
      return;
    }
    if ((await editButtons.count()) > 0) {
      await expect(editButtons.first()).toBeVisible();
      await editButtons.first().click();
      await expect(page.locator('[data-testid="service-work-order-item-edit-form"]')).toBeVisible();
      await page.locator('.service-shell-modal-title').filter({ hasText: /upravit položku/i }).first().waitFor({ state: 'visible' }).catch(() => {});
    }
    if ((await deleteButtons.count()) > 0) {
      await expect(deleteButtons.first()).toBeVisible();
    }
  });

  test('service_work_order_add_part_or_limited', async ({ page }) => {
    await openWorkOrders(page);
    if ((await page.locator('[data-testid="service-work-order-row"]').count()) === 0) {
      test.skip(true, 'Žádná dostupná zakázka pro detail test v tomto prostředí.');
    }
    await page.locator('[data-testid="service-work-order-row"]').first().click();
    await expect(page.locator('[data-testid="service-work-order-add-part-button"]')).toBeEnabled();
    await expect(page.locator('[data-testid="service-work-order-part-list"]')).toBeVisible();
  });

  test('service_work_order_add_time_or_limited', async ({ page }) => {
    await openWorkOrders(page);
    if ((await page.locator('[data-testid="service-work-order-row"]').count()) === 0) {
      test.skip(true, 'Žádná dostupná zakázka pro detail test v tomto prostředí.');
    }
    await page.locator('[data-testid="service-work-order-row"]').first().click();
    await expect(page.locator('[data-testid="service-work-order-add-time-button"]')).toBeEnabled();
  });

  test('service_work_order_photo_section_loads', async ({ page }) => {
    await openWorkOrders(page);
    if ((await page.locator('[data-testid="service-work-order-row"]').count()) === 0) {
      test.skip(true, 'Žádná dostupná zakázka pro detail test v tomto prostředí.');
    }
    await page.locator('[data-testid="service-work-order-row"]').first().click();
    await expect(page.locator('[data-testid="service-work-order-photo-list"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-work-order-add-photo-button"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-work-order-photo-type"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-work-order-photo-visibility-upload"]')).toBeVisible();
  });

  test('service_work_order_photo_visibility_notice', async ({ page }) => {
    await openWorkOrders(page);
    if ((await page.locator('[data-testid="service-work-order-row"]').count()) === 0) {
      test.skip(true, 'Žádná dostupná zakázka pro detail test v tomto prostředí.');
    }
    await page.locator('[data-testid="service-work-order-row"]').first().click();
    await expect(page.locator('[data-testid="service-work-order-photo-limited-notice"]')).toContainText(
      /Interní fotky/i,
    );
  });

  test('service_work_order_photo_upload_or_limited', async ({ page }) => {
    test.skip(process.env.E2E_ALLOW_MUTATIONS !== '1', 'Mutační upload vyžaduje E2E_ALLOW_MUTATIONS=1');
    await openWorkOrders(page);
    if ((await page.locator('[data-testid="service-work-order-row"]').count()) === 0) {
      test.skip(true, 'Žádná dostupná zakázka pro upload test v tomto prostředí.');
    }
    await page.locator('[data-testid="service-work-order-row"]').first().click();
    const addPhoto = page.locator('[data-testid="service-work-order-add-photo-button"]');
    if (!(await addPhoto.isEnabled())) {
      test.skip(true, 'Upload fotek není v tomto prostředí dostupný (limited).');
    }
    await page.locator('[data-testid="service-work-order-photo-type"]').selectOption('damage');
    await page.locator('[data-testid="service-work-order-photo-input"]').setInputFiles({
      name: 'e2e-damage.jpg',
      mimeType: 'image/jpeg',
      buffer: Buffer.from(
        '/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAn/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCwAA//2Q==',
        'base64',
      ),
    });
    await page.locator('[data-testid="service-work-order-photo-upload-submit"]').click();
    await expect(page.locator('[data-testid="service-work-order-photo-card"]').first()).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.locator('[data-testid="service-work-order-photo-error"]')).toBeHidden();
  });

  test('service_work_order_photo_type_selector', async ({ page }) => {
    await openWorkOrders(page);
    if ((await page.locator('[data-testid="service-work-order-row"]').count()) === 0) {
      test.skip(true, 'Žádná dostupná zakázka pro detail test v tomto prostředí.');
    }
    await page.locator('[data-testid="service-work-order-row"]').first().click();
    const typeSelect = page.locator('[data-testid="service-work-order-photo-type"]');
    await expect(typeSelect).toBeVisible();
    await expect(typeSelect.locator('option[value="damage"]')).toHaveCount(1);
    await expect(typeSelect.locator('option[value="completion"]')).toHaveCount(1);
  });

  test('service_work_order_complete_or_limited', async ({ page }) => {
    await openWorkOrders(page);
    if ((await page.locator('[data-testid="service-work-order-row"]').count()) === 0) {
      test.skip(true, 'Žádná dostupná zakázka pro detail test v tomto prostředí.');
    }
    await page.locator('[data-testid="service-work-order-row"]').first().click();
    const completeBtn = page.locator('[data-testid="service-work-order-complete-button"]');
    const status = page.locator('[data-testid="service-work-order-status"]');
    const statusValue = await status.inputValue();
    if (statusValue === 'completed') {
      await expect(completeBtn).toBeDisabled();
      await expect(page.locator('[data-testid="service-work-order-completion-panel"]')).toBeVisible();
    } else {
      await expect(completeBtn).toBeEnabled();
    }
  });

  test.describe('Work order completion panel', () => {
    const woId = 8801;

    function mockCompletedWorkOrder(page: Parameters<typeof test>[0]['page'], options: { recordId?: number; invoiceId?: number } = {}) {
      const recordId = Number(options.recordId || 0);
      const invoiceId = Number(options.invoiceId || 0);
      return page.route(new RegExp(`/api/service/work-orders/${woId}(?:/|$)`), async (route) => {
        const method = route.request().method();
        const url = route.request().url();
        if (method === 'GET') {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              id: woId,
              title: 'E2E completion WO',
              status: 'completed',
              customer_id: 101,
              owner_id: 101,
              vehicle_label: 'Skoda Octavia',
              capabilities: { create_service_record: recordId <= 0, invoices: true, complete: false },
              service_record_id: recordId || null,
              invoice_summary: invoiceId ? { invoice_id: invoiceId, status: 'issued', total: 1200 } : null,
              items: { labor: [], parts: [], time: [] },
              photos: [],
            }),
          });
          return;
        }
        if (method === 'POST' && url.includes('/service-record')) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ service_record_id: 9901 }),
          });
          return;
        }
        if (method === 'POST' && url.includes('/invoice')) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ id: 7701, invoice_number: 'FV-E2E-1', total: 1500 }),
          });
          return;
        }
        await route.continue();
      });
    }

    async function openCompletedWorkOrderDetail(page: Parameters<typeof test>[0]['page']) {
      await page.route('**/api/service/work-orders', async (route) => {
        if (route.request().method() === 'GET' && !route.request().url().includes(`/${woId}`)) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              items: [{ id: woId, title: 'E2E completion WO', status: 'completed' }],
              total: 1,
            }),
          });
          return;
        }
        await route.continue();
      });
      await openWorkOrders(page);
      await page.locator('[data-testid="service-work-order-row"]').first().click();
      await expect(page.locator('[data-testid="service-work-order-completion-panel"]')).toBeVisible({ timeout: 15_000 });
    }

    test('service_work_order_complete_shows_actions', async ({ page }) => {
      await mockCompletedWorkOrder(page);
      await openCompletedWorkOrderDetail(page);
      await expect(page.locator('[data-testid="service-work-order-complete-invoice"]')).toBeEnabled();
      await expect(page.locator('[data-testid="service-work-order-complete-record"]')).toBeEnabled();
      await expect(page.locator('[data-testid="service-work-order-complete-both"]')).toBeEnabled();
    });

    test('service_work_order_complete_create_record', async ({ page }) => {
      let recordCalled = false;
      await mockCompletedWorkOrder(page);
      await page.route(`**/api/service/work-orders/${woId}/service-record`, async (route) => {
        recordCalled = true;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ service_record_id: 9901 }),
        });
      });
      await openCompletedWorkOrderDetail(page);
      await page.locator('[data-testid="service-work-order-complete-record"]').click();
      await expect.poll(() => recordCalled).toBe(true);
    });

    test('service_work_order_complete_create_invoice', async ({ page }) => {
      let invoiceCalled = false;
      await mockCompletedWorkOrder(page);
      await page.route(`**/api/service/work-orders/${woId}/invoice`, async (route) => {
        invoiceCalled = true;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ id: 7701, invoice_number: 'FV-E2E-1', total: 1500 }),
        });
      });
      await openCompletedWorkOrderDetail(page);
      await page.locator('[data-testid="service-work-order-complete-invoice"]').click();
      await expect.poll(() => invoiceCalled).toBe(true);
    });

    test('service_work_order_complete_create_both_or_limited', async ({ page }) => {
      let invoiceCalled = false;
      let recordCalled = false;
      await mockCompletedWorkOrder(page);
      await page.route(`**/api/service/work-orders/${woId}/invoice`, async (route) => {
        invoiceCalled = true;
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 7701 }) });
      });
      await page.route(`**/api/service/work-orders/${woId}/service-record`, async (route) => {
        recordCalled = true;
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ service_record_id: 9901 }) });
      });
      await openCompletedWorkOrderDetail(page);
      await page.locator('[data-testid="service-work-order-complete-both"]').click();
      await expect.poll(() => invoiceCalled && recordCalled).toBe(true);
    });

    test('service_work_order_completion_f5_keeps_session', async ({ page }) => {
      await mockCompletedWorkOrder(page);
      await openCompletedWorkOrderDetail(page);
      const before = page.url();
      await page.reload({ waitUntil: 'domcontentloaded' });
      await waitForServiceShellReady(page);
      await expect(page).toHaveURL(before);
      await expect(page.locator('[data-testid="login-form"]')).not.toBeVisible();
    });

    test('service_work_order_completion_panel_mobile', async ({ page }) => {
      await page.setViewportSize({ width: 390, height: 844 });
      await mockCompletedWorkOrder(page);
      await openCompletedWorkOrderDetail(page);
      const invoiceBtn = page.locator('[data-testid="service-work-order-complete-invoice"]');
      await expect(invoiceBtn).toBeVisible();
      const box = await invoiceBtn.boundingBox();
      expect(box?.height || 0).toBeGreaterThanOrEqual(44);
    });
  });

  test('service_work_order_create_record_or_limited', async ({ page }) => {
    await openWorkOrders(page);
    if ((await page.locator('[data-testid="service-work-order-row"]').count()) === 0) {
      test.skip(true, 'Žádná dostupná zakázka pro detail test v tomto prostředí.');
    }
    await page.locator('[data-testid="service-work-order-row"]').first().click();
    const createRecord = page.locator('[data-testid="service-work-order-create-record-button"]');
    const statusValue = await page.locator('[data-testid="service-work-order-status"]').inputValue();
    if (statusValue === 'completed') {
      await expect(createRecord).toBeEnabled();
    } else {
      await expect(createRecord).toBeDisabled();
    }
  });

  test('service_work_order_photo_no_fake_success', async ({ page }) => {
    await openWorkOrders(page);
    if ((await page.locator('[data-testid="service-work-order-row"]').count()) === 0) {
      test.skip(true, 'Žádná dostupná zakázka pro detail test v tomto prostředí.');
    }
    await page.locator('[data-testid="service-work-order-row"]').first().click();
    const errorBox = page.locator('[data-testid="service-work-order-photo-error"]');
    await expect(errorBox).toBeHidden();
    const addPhoto = page.locator('[data-testid="service-work-order-add-photo-button"]');
    if (await addPhoto.isEnabled()) {
      await addPhoto.click();
      await page.locator('[data-testid="service-work-order-photo-upload-submit"]').click();
      await expect(errorBox).toBeVisible();
      await expect(page.locator('[data-testid="service-work-order-photo-card"]')).toHaveCount(0);
    }
  });

  test('service_work_order_photo_f5_keeps_session', async ({ page }) => {
    await openWorkOrders(page);
    if ((await page.locator('[data-testid="service-work-order-row"]').count()) === 0) {
      test.skip(true, 'Žádná dostupná zakázka pro detail test v tomto prostředí.');
    }
    await page.locator('[data-testid="service-work-order-row"]').first().click();
    await expect(page.locator('[data-testid="service-work-order-photo-list"]')).toBeVisible();
    const before = page.url();
    await page.reload({ waitUntil: 'domcontentloaded' });
    await waitForServiceShellReady(page);
    await expect(page).toHaveURL(before);
    await expect(page.locator('[data-testid="login-form"]')).not.toBeVisible();
    await expect(page.locator('[data-testid="service-work-order-photo-list"]')).toBeVisible();
  });

  test('service_work_order_photo_owner_visibility_safe', async ({ page }) => {
    await openWorkOrders(page);
    if ((await page.locator('[data-testid="service-work-order-row"]').count()) === 0) {
      test.skip(true, 'Žádná dostupná zakázka pro detail test v tomto prostředí.');
    }
    await page.locator('[data-testid="service-work-order-row"]').first().click();
    await expect(page.locator('[data-testid="service-work-order-photo-limited-notice"]')).toContainText(
      /majitel/i,
    );
    const visibilityUpload = page.locator('[data-testid="service-work-order-photo-visibility-upload"]');
    if (await visibilityUpload.isVisible()) {
      await expect(visibilityUpload.locator('option[value="internal_only"]')).toHaveCount(0);
    }
  });

  test('service_work_order_create_for_unowned_vehicle', async ({ page }) => {
    test.skip(process.env.E2E_ALLOW_MUTATIONS !== '1', 'Mutační test vyžaduje E2E_ALLOW_MUTATIONS=1');
    const uniqueVin = `TMBE2E${Date.now().toString().slice(-10)}UN`;
    await openWorkOrders(page);
    await page.locator('[data-testid="service-work-orders-new-button"]').click();
    await page.locator('#serviceShellWorkOrderOwner').selectOption('__unowned__');
    const vehicleSelect = page.locator('#serviceShellWorkOrderVehicle');
    if ((await vehicleSelect.locator('option').count()) <= 1) {
      await page.goto(page.url().replace('/work-orders', '/intake'), { waitUntil: 'domcontentloaded' });
      await waitForServiceShellReady(page);
      await page.locator('[data-testid="service-intake-vin-input"]').fill(uniqueVin);
      await page.locator('[data-testid="service-intake-lookup-button"]').click();
      await page.locator('[data-testid="service-intake-section"]').getByLabel('Značka').fill('Skoda');
      await page.locator('[data-testid="service-intake-section"]').getByLabel('Model').fill('Fabia');
      await page.locator('[data-testid="service-intake-save-vehicle-button"]').click();
      await expect(page.locator('[data-testid="service-intake-section"]')).toContainText(/bez vlastnické vazby/i, {
        timeout: 30_000,
      });
      await openWorkOrders(page);
      await page.locator('[data-testid="service-work-orders-new-button"]').click();
      await page.locator('#serviceShellWorkOrderOwner').selectOption('__unowned__');
    }
    await page.locator('#serviceShellWorkOrderTitle').fill(`E2E unowned ${Date.now()}`);
    const vehicleOptions = page.locator('#serviceShellWorkOrderVehicle option');
    await expect(vehicleOptions).not.toHaveCount(0);
    await page.locator('#serviceShellWorkOrderVehicle').selectOption({ index: 0 });
    await page.locator('.service-shell-modal-footer .btn-primary').click();
    await expect(page.locator('[data-testid="service-work-orders-section"]')).toContainText(/Zakázka byla vytvořena|Nepřiřazené/i, {
      timeout: 30_000,
    });
  });

  test('service_work_order_create_quote_or_limited', async ({ page }) => {
    await openWorkOrders(page);
    if ((await page.locator('[data-testid="service-work-order-row"]').count()) === 0) {
      test.skip(true, 'Žádná dostupná zakázka pro quote test v tomto prostředí.');
    }
    await page.locator('[data-testid="service-work-order-row"]').first().click();
    await expect(page.locator('[data-testid="service-work-order-quote-panel"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-work-order-create-quote-button"]')).toBeVisible();
  });

  test('service_work_order_billing_panel_loads', async ({ page }) => {
    await openWorkOrders(page);
    if ((await page.locator('[data-testid="service-work-order-row"]').count()) === 0) {
      test.skip(true, 'Žádná dostupná zakázka pro billing panel test.');
    }
    await page.locator('[data-testid="service-work-order-row"]').first().click();
    await expect(page.locator('[data-testid="service-work-order-quote-panel"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-work-order-invoice-panel"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-work-order-billing-limited-notice"]')).toContainText(/majitel/i);
  });

  test('service_work_order_create_invoice_or_limited', async ({ page }) => {
    await openWorkOrders(page);
    if ((await page.locator('[data-testid="service-work-order-row"]').count()) === 0) {
      test.skip(true, 'Žádná dostupná zakázka pro invoice test.');
    }
    await page.locator('[data-testid="service-work-order-row"]').first().click();
    const createInvoice = page.locator('[data-testid="service-work-order-create-invoice-button"]');
    await expect(createInvoice).toBeVisible();
  });

  test('service_billing_route_loads', async ({ page }) => {
    const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
    const slug = slugMatch?.[1] || 'e2e-fixed-service';
    await page.goto(`/web/app/s/${slug}/billing`, { waitUntil: 'domcontentloaded' });
    await waitForServiceShellReady(page);
    await expect(page.locator('[data-testid="service-billing-section"]')).toBeVisible({ timeout: 30_000 });
  });

  test('service_billing_f5_keeps_session', async ({ page }) => {
    const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
    const slug = slugMatch?.[1] || 'e2e-fixed-service';
    await page.goto(`/web/app/s/${slug}/billing`, { waitUntil: 'domcontentloaded' });
    await waitForServiceShellReady(page);
    const before = page.url();
    await page.reload({ waitUntil: 'domcontentloaded' });
    await waitForServiceShellReady(page);
    await expect(page).toHaveURL(before);
    await expect(page.locator('[data-testid="login-form"]')).not.toBeVisible();
  });

  test('service_invoice_pdf_button_or_limited', async ({ page }) => {
    await openWorkOrders(page);
    if ((await page.locator('[data-testid="service-work-order-row"]').count()) === 0) {
      test.skip(true, 'Žádná dostupná zakázka pro PDF tlačítko.');
    }
    await page.locator('[data-testid="service-work-order-row"]').first().click();
    const pdfBtn = page.locator('[data-testid="service-work-order-invoice-pdf-button"]');
    if ((await pdfBtn.count()) === 0) {
      return;
    }
    await expect(pdfBtn).toBeVisible();
  });

  test('service_billing_no_fake_success', async ({ page }) => {
    test.skip(process.env.E2E_ALLOW_MUTATIONS === '1', 'Kontrola bez mutace — tlačítko bez položek nesmí falešně uspět.');
    await openWorkOrders(page);
    if ((await page.locator('[data-testid="service-work-order-row"]').count()) === 0) {
      test.skip(true, 'Žádná zakázka pro billing no-fake test.');
    }
    await page.locator('[data-testid="service-work-order-row"]').first().click();
    const createQuote = page.locator('[data-testid="service-work-order-create-quote-button"]');
    if (!(await createQuote.isVisible())) {
      return;
    }
    await createQuote.click();
    await expect(page.locator('[data-testid="service-work-order-quote-status"]')).not.toBeVisible({ timeout: 5000 });
  });

  test('service_billing_quote_detail_or_limited', async ({ page }) => {
    const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
    const slug = slugMatch?.[1] || 'e2e-fixed-service';
    await page.goto(`/web/app/s/${slug}/billing`, { waitUntil: 'domcontentloaded' });
    await waitForServiceShellReady(page);
    await expect(page.locator('[data-testid="service-billing-section"]')).toBeVisible({ timeout: 30_000 });
    const quoteRow = page.locator('[data-testid="service-billing-quote-row"]').first();
    if ((await quoteRow.count()) === 0) {
      const limited = page.locator('[data-testid="service-billing-limited-notice"]');
      if ((await limited.count()) > 0) {
        await expect(limited).toBeVisible();
      }
      return;
    }
    await quoteRow.click();
    await expect(page.locator('[data-testid="service-billing-quote-detail"]')).toBeVisible({ timeout: 15_000 });
  });

  test('service_billing_invoice_detail_or_limited', async ({ page }) => {
    const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
    const slug = slugMatch?.[1] || 'e2e-fixed-service';
    await page.goto(`/web/app/s/${slug}/billing`, { waitUntil: 'domcontentloaded' });
    await waitForServiceShellReady(page);
    const invoiceRow = page.locator('[data-testid="service-billing-invoice-row"]').first();
    if ((await invoiceRow.count()) === 0) {
      const limited = page.locator('[data-testid="service-billing-limited-notice"]');
      if ((await limited.count()) > 0) {
        await expect(limited).toBeVisible();
      }
      return;
    }
    await invoiceRow.click();
    await expect(page.locator('[data-testid="service-billing-invoice-detail"]')).toBeVisible({ timeout: 15_000 });
  });

  test('service_billing_create_invoice_from_quote_or_limited', async ({ page }) => {
    const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
    const slug = slugMatch?.[1] || 'e2e-fixed-service';
    await page.goto(`/web/app/s/${slug}/billing`, { waitUntil: 'domcontentloaded' });
    await waitForServiceShellReady(page);
    const quoteRow = page.locator('[data-testid="service-billing-quote-row"]').first();
    if ((await quoteRow.count()) === 0) {
      test.skip(true, 'Žádná nabídka v billing seznamu.');
    }
    await quoteRow.click();
    const fromQuote = page.locator('[data-testid="service-billing-create-invoice-from-quote-button"]');
    if ((await fromQuote.count()) === 0) {
      const limited = page.locator('[data-testid="service-billing-limited-notice"]');
      if ((await limited.count()) > 0) {
        await expect(limited).toBeVisible();
      }
      return;
    }
    await expect(fromQuote).toBeVisible();
    if (process.env.E2E_ALLOW_MUTATIONS !== '1') {
      return;
    }
    await fromQuote.click();
    await expect(
      page.locator('[data-testid="service-billing-invoice-detail"], [data-testid="service-billing-error"]'),
    ).toBeVisible({ timeout: 20_000 });
  });

  test('service_billing_invoice_pdf_button_or_limited', async ({ page }) => {
    const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
    const slug = slugMatch?.[1] || 'e2e-fixed-service';
    await page.goto(`/web/app/s/${slug}/billing`, { waitUntil: 'domcontentloaded' });
    await waitForServiceShellReady(page);
    const invoiceRow = page.locator('[data-testid="service-billing-invoice-row"]').first();
    if ((await invoiceRow.count()) === 0) {
      test.skip(true, 'Žádná faktura v billing seznamu.');
    }
    await invoiceRow.click();
    const pdfBtn = page.locator('[data-testid="service-billing-invoice-pdf-button"]');
    if ((await pdfBtn.count()) === 0) {
      const limited = page.locator('[data-testid="service-billing-limited-notice"]');
      if ((await limited.count()) > 0) {
        await expect(limited).toBeVisible();
      }
      return;
    }
    await expect(pdfBtn).toBeVisible();
  });

  test('owner_safe_history_no_invoice_quote_prices', async ({ page }) => {
    await openWorkOrders(page);
    const historyNav = page.locator('[data-testid="service-nav-history"], a:has-text("Historie")').first();
    if ((await historyNav.count()) === 0) {
      test.skip(true, 'Historie vozidla není v navigaci dostupná.');
    }
    await historyNav.click();
    await waitForServiceShellReady(page);
    const body = await page.locator('body').innerText();
    const lower = body.toLowerCase();
    for (const token of ['invoice_id', 'quote_id', 'pdf_url', 'unit_price', 'faktura č.']) {
      expect(lower).not.toContain(token);
    }
  });

  test('service_billing_contact_section_loads', async ({ page }) => {
    await openWorkOrders(page);
    const rows = page.locator('[data-testid="service-work-order-row"]');
    if ((await rows.count()) === 0) {
      test.skip(true, 'Žádná zakázka pro billing contact test.');
    }
    await rows.first().click();
    const section = page.locator('[data-testid="service-billing-contact-section"]');
    if ((await section.count()) === 0) {
      test.skip(true, 'Sekce fakturačního kontaktu je jen u nepřiřazených vozidel.');
    }
    await expect(section).toBeVisible();
    await expect(page.locator('[data-testid="service-billing-contact-form"]')).toBeVisible();
  });

  test('service_create_billing_contact_or_limited', async ({ page }) => {
    test.skip(process.env.E2E_ALLOW_MUTATIONS !== '1', 'Mutace fakturačního kontaktu vyžaduje E2E_ALLOW_MUTATIONS=1.');
    await openWorkOrders(page);
    const rows = page.locator('[data-testid="service-work-order-row"]');
    if ((await rows.count()) === 0) {
      test.skip(true, 'Žádná unowned zakázka pro vytvoření kontaktu.');
    }
    await rows.first().click();
    const section = page.locator('[data-testid="service-billing-contact-section"]');
    if ((await section.count()) === 0) {
      test.skip(true, 'Sekce fakturačního kontaktu není dostupná.');
    }
    await page.locator('[data-testid="service-billing-contact-name"]').fill('E2E Fakturační kontakt');
    await page.locator('[data-testid="service-billing-contact-email"]').fill('e2e.billing.contact@example.test');
    await page.locator('[data-testid="service-billing-contact-save-button"]').click();
    await expect(page.locator('[data-testid="service-billing-contact-success"]')).toBeVisible({ timeout: 15_000 });
  });

  test('service_invoice_requires_billing_contact', async ({ page }) => {
    await openWorkOrders(page);
    const rows = page.locator('[data-testid="service-work-order-row"]');
    if ((await rows.count()) === 0) {
      test.skip(true, 'Žádná zakázka pro invoice billing contact test.');
    }
    await rows.first().click();
    const createBtn = page.locator('[data-testid="service-work-order-create-invoice-button"]');
    if (!(await createBtn.isVisible())) {
      return;
    }
    const section = page.locator('[data-testid="service-billing-contact-section"]');
    if ((await section.count()) === 0) {
      return;
    }
    await expect(createBtn).toBeDisabled();
  });

  test('service_invoice_with_billing_contact_or_limited', async ({ page }) => {
    test.skip(process.env.E2E_ALLOW_MUTATIONS !== '1', 'Mutace faktury vyžaduje E2E_ALLOW_MUTATIONS=1.');
    await openWorkOrders(page);
    const rows = page.locator('[data-testid="service-work-order-row"]');
    if ((await rows.count()) === 0) {
      test.skip(true, 'Žádná zakázka pro invoice s billing contact.');
    }
    await rows.first().click();
    if ((await page.locator('[data-testid="service-billing-contact-section"]').count()) === 0) {
      test.skip(true, 'Nepřiřazené vozidlo není v seznamu.');
    }
    const success = page.locator('[data-testid="service-billing-contact-success"]');
    if ((await success.count()) === 0 || !(await success.isVisible())) {
      await page.locator('[data-testid="service-billing-contact-name"]').fill('E2E Invoice Contact');
      await page.locator('[data-testid="service-billing-contact-save-button"]').click();
      await expect(success).toBeVisible({ timeout: 15_000 });
    }
    const createBtn = page.locator('[data-testid="service-work-order-create-invoice-button"]');
    if (await createBtn.isDisabled()) {
      test.skip(true, 'Faktura není povolena — chybí položky nebo kontakt.');
    }
    await createBtn.click();
    await expect(
      page.locator('[data-testid="service-work-order-invoice-status"], [data-testid="service-work-order-limited-notice"]'),
    ).toBeVisible({ timeout: 20_000 });
  });

  test('service_billing_contact_validation', async ({ page }) => {
    await openWorkOrders(page);
    const rows = page.locator('[data-testid="service-work-order-row"]');
    if ((await rows.count()) === 0) {
      test.skip(true, 'Žádná zakázka pro validaci kontaktu.');
    }
    await rows.first().click();
    if ((await page.locator('[data-testid="service-billing-contact-section"]').count()) === 0) {
      test.skip(true, 'Sekce fakturačního kontaktu není dostupná.');
    }
    await page.locator('[data-testid="service-billing-contact-name"]').fill('');
    await page.locator('[data-testid="service-billing-contact-save-button"]').click();
    await expect(page.locator('[data-testid="service-billing-contact-error"]')).toBeVisible({ timeout: 5000 });
  });

  test('service_billing_contact_f5_keeps_session', async ({ page }) => {
    await openWorkOrders(page);
    const rows = page.locator('[data-testid="service-work-order-row"]');
    if ((await rows.count()) === 0) {
      test.skip(true, 'Žádná zakázka pro F5 billing contact test.');
    }
    await rows.first().click();
    if ((await page.locator('[data-testid="service-billing-contact-section"]').count()) === 0) {
      test.skip(true, 'Sekce fakturačního kontaktu není dostupná.');
    }
    const before = page.url();
    await page.reload({ waitUntil: 'domcontentloaded' });
    await waitForServiceShellReady(page);
    await expect(page.locator('[data-testid="login-form"]')).not.toBeVisible();
    await openWorkOrders(page);
    await rows.first().click();
    await expect(page.locator('[data-testid="service-billing-contact-section"]')).toBeVisible();
  });

  test('owner_safe_history_no_invoice_data', async ({ page }) => {
    await openWorkOrders(page);
    const historyNav = page.locator('[data-testid="service-nav-history"], a:has-text("Historie")').first();
    if ((await historyNav.count()) === 0) {
      test.skip(true, 'Historie vozidla není v navigaci.');
    }
    await historyNav.click();
    await waitForServiceShellReady(page);
    const lower = (await page.locator('body').innerText()).toLowerCase();
    for (const token of ['billing_contact', 'ičo', 'dič', 'fakturační']) {
      expect(lower).not.toContain(token);
    }
  });

  test('vehicle_timeline_loads', async ({ page }) => {
    const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
    const slug = slugMatch?.[1] || 'e2e-fixed-service';
    await page.goto(`/web/app/s/${slug}/history`, { waitUntil: 'domcontentloaded' });
    await waitForServiceShellReady(page);
    await expect(page.locator('[data-testid="vehicle-timeline-section"]')).toBeVisible({ timeout: 30_000 });
  });

  test('vehicle_timeline_service_view', async ({ page }) => {
    const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
    const slug = slugMatch?.[1] || 'e2e-fixed-service';
    await page.goto(`/web/app/s/${slug}/history`, { waitUntil: 'domcontentloaded' });
    await waitForServiceShellReady(page);
    const select = page.locator('#vehicleTimelineSelect');
    if ((await select.count()) === 0) {
      test.skip(true, 'Timeline výběr vozidla není dostupný.');
    }
    const options = select.locator('option');
    if ((await options.count()) <= 1) {
      await expect(page.locator('[data-testid="vehicle-timeline-empty"]')).toBeVisible();
      return;
    }
    await select.selectOption({ index: 1 });
    await expect(
      page.locator('[data-testid="vehicle-timeline-event"], [data-testid="vehicle-timeline-empty"], [data-testid="vehicle-timeline-loading"]'),
    ).toBeVisible({ timeout: 20_000 });
  });

  test('vehicle_timeline_f5_keeps_session', async ({ page }) => {
    const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
    const slug = slugMatch?.[1] || 'e2e-fixed-service';
    await page.goto(`/web/app/s/${slug}/history`, { waitUntil: 'domcontentloaded' });
    await waitForServiceShellReady(page);
    const before = page.url();
    await page.reload({ waitUntil: 'domcontentloaded' });
    await waitForServiceShellReady(page);
    await expect(page).toHaveURL(before);
    await expect(page.locator('[data-testid="login-form"]')).not.toBeVisible();
  });

  test('vehicle_timeline_no_invoice_prices', async ({ page }) => {
    const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
    const slug = slugMatch?.[1] || 'e2e-fixed-service';
    await page.goto(`/web/app/s/${slug}/history`, { waitUntil: 'domcontentloaded' });
    await waitForServiceShellReady(page);
    const body = (await page.locator('body').innerText()).toLowerCase();
    expect(body).not.toContain('invoice_id');
    expect(body).not.toContain('pdf_url');
  });

  test('vehicle_timeline_no_fake_events', async ({ page }) => {
    await page.goto(page.url().replace(/\/[^/]+$/, '/history'), { waitUntil: 'domcontentloaded' }).catch(() => {});
    await waitForServiceShellReady(page);
    const section = page.locator('[data-testid="vehicle-timeline-section"]');
    if ((await section.count()) === 0) {
      test.skip(true, 'Timeline sekce není v UI.');
    }
    const fakeMarkers = page.locator('[data-testid="vehicle-timeline-event"][data-fake="1"]');
    await expect(fakeMarkers).toHaveCount(0);
  });
});
