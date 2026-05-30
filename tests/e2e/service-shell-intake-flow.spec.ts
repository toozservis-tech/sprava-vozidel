import { expect, test } from '@playwright/test';

import {
  getServiceTestCredentials,
  loginServiceUser,
  waitForServiceShellReady,
} from './helpers';

const intakeLookupPath = '**/api/v1/services/workspace/vehicles/lookup';
const intakeWorkAccessPath = '**/api/v1/services/workspace/vehicles/*/work-access';
const intakeCasePath = '**/api/v1/services/workspace/service-cases/';
const workOrdersPath = '**/api/service/work-orders';

async function openIntake(page: Parameters<typeof test>[0]['page']) {
  const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
  const slug = slugMatch?.[1] || 'e2e-fixed-service';
  await page.goto(`/web/app/s/${slug}/intake`, { waitUntil: 'domcontentloaded' });
  await waitForServiceShellReady(page);
}

async function clickNextStep(page: Parameters<typeof test>[0]['page']) {
  const next = page.getByRole('button', { name: /Další krok/i });
  await expect(next).toBeEnabled({ timeout: 15_000 });
  await next.click();
}

async function mockVehicleLookup(
  page: Parameters<typeof test>[0]['page'],
  body: Record<string, unknown>,
) {
  await page.route(intakeLookupPath, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });
  });
}

test.describe('Service intake wizard flow', () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!getServiceTestCredentials(), 'Nastavte E2E_SERVICE_EMAIL a E2E_SERVICE_PASSWORD');
    await loginServiceUser(page);
    await waitForServiceShellReady(page);
  });

  test('service_intake_wizard_search_vehicle', async ({ page }) => {
    await openIntake(page);
    await expect(page.locator('[data-testid="service-intake-step-search"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-intake-vin-input"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-intake-lookup-button"]')).toBeVisible();
  });

  test('service_intake_choose_request_owner_link', async ({ page }) => {
    await mockVehicleLookup(page, {
      found: true,
      status: 'found_access_required',
      vehicle_preview: { vehicle_id: 303, brand: 'Audi', model: 'A4', vin_masked: 'WAU***4567', plate_masked: '3AB***77' },
      access: { status: 'not_requested', can_request_access: true },
      owner_data: null,
    });
    await openIntake(page);
    await page.locator('[data-testid="service-intake-vin-input"]').fill('WAUZZZ8K9AA000001');
    await page.locator('[data-testid="service-intake-lookup-button"]').click();
    await expect(page.locator('[data-testid="service-intake-step-access-choice"]')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('[data-testid="service-intake-request-owner-link-button"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-intake-one-time-work-button"]')).toBeVisible();
  });

  test('service_intake_condition_report_step_or_limited', async ({ page }) => {
    await mockVehicleLookup(page, {
      found: true,
      status: 'found_service_unowned',
      vehicle_preview: { vehicle_id: 707, brand: 'VW', model: 'Polo', vin_masked: 'WVW***7070', plate_masked: '7FL***70' },
      access: { status: 'work_access' },
      owner_data: null,
    });
    await openIntake(page);
    await page.locator('[data-testid="service-intake-plate-input"]').fill('7FL7070');
    await page.locator('[data-testid="service-intake-lookup-button"]').click();
    await expect(page.locator('[data-testid="service-intake-step-access-choice"]')).toBeVisible({ timeout: 15_000 });
    for (let i = 0; i < 2; i += 1) {
      await clickNextStep(page);
    }
    await expect(page.locator('[data-testid="service-intake-step-condition-report"]')).toBeVisible();
  });

  test('service_intake_choose_one_time_work', async ({ page }) => {
    await mockVehicleLookup(page, {
      found: true,
      status: 'found_access_required',
      vehicle_preview: { vehicle_id: 808, brand: 'Skoda', model: 'Fabia', vin_masked: 'TMB***8080', plate_masked: '8FL***80' },
      access: { status: 'not_requested', can_request_access: true },
      owner_data: null,
    });
    await page.route(intakeWorkAccessPath, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ created: true, status: 'work_access' }),
      });
    });
    await openIntake(page);
    await page.locator('[data-testid="service-intake-vin-input"]').fill('TMBE2E80808080808');
    await page.locator('[data-testid="service-intake-lookup-button"]').click();
    await expect(page.locator('[data-testid="service-intake-step-access-choice"]')).toBeVisible({ timeout: 15_000 });
    await Promise.all([
      page.waitForResponse((r) => r.url().includes('/work-access') && r.status() === 200),
      page.locator('[data-testid="service-intake-one-time-work-button"]').click(),
    ]);
    await expect(page.locator('[data-testid="service-intake-step-access-choice"]')).toContainText(/jednorázov/i, { timeout: 15_000 });
  });

  test('service_intake_condition_report_creates_draft_order', async ({ page }) => {
    let workOrderPayload: Record<string, unknown> | null = null;
    await mockVehicleLookup(page, {
      found: true,
      status: 'found_service_unowned',
      vehicle_preview: { vehicle_id: 909, brand: 'VW', model: 'Golf', vin_masked: 'WVW***9090', plate_masked: '9FL***90', in_system: true },
      access: { status: 'work_access' },
      owner_data: null,
    });
    await page.route(intakeCasePath, async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ id: 42, vehicle_id: 909 }),
        });
        return;
      }
      await route.continue();
    });
    await page.route(workOrdersPath, async (route) => {
      if (route.request().method() === 'POST') {
        workOrderPayload = route.request().postDataJSON() as Record<string, unknown>;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ id: 1001, status: 'intake_pending', title: 'Nový příjem vozidla' }),
        });
        return;
      }
      await route.continue();
    });
    await openIntake(page);
    await page.locator('[data-testid="service-intake-plate-input"]').fill('9FL9090');
    await page.locator('[data-testid="service-intake-lookup-button"]').click();
    await expect(page.locator('[data-testid="service-intake-step-access-choice"]')).toBeVisible({ timeout: 15_000 });
    await clickNextStep(page);
    await clickNextStep(page);
    await page.locator('[data-testid="service-intake-customer-complaint"]').fill('Klimatizace nefunguje');
    await page.locator('[data-testid="service-intake-technician-note"]').fill('Kontrola chladiva');
    await clickNextStep(page);
    await page.locator('[data-testid="service-intake-create-draft-work-order"]').click();
    await expect.poll(() => workOrderPayload?.status).toBe('intake_pending');
    await expect(page.locator('[data-testid="service-intake-step-done"]')).toBeVisible({ timeout: 20_000 });
  });

  test('service_intake_upload_or_limited_photos', async ({ page }) => {
    await mockVehicleLookup(page, {
      found: true,
      status: 'found_service_unowned',
      vehicle_preview: { vehicle_id: 606, brand: 'Skoda', model: 'Scala', vin_masked: 'TMB***6060', plate_masked: '6FL***60' },
      access: { status: 'work_access' },
      owner_data: null,
    });
    await openIntake(page);
    await page.locator('[data-testid="service-intake-plate-input"]').fill('6FL6060');
    await page.locator('[data-testid="service-intake-lookup-button"]').click();
    await expect(page.locator('[data-testid="service-intake-step-access-choice"]')).toBeVisible({ timeout: 15_000 });
    await clickNextStep(page);
    await expect(page.locator('[data-testid="service-intake-step-photos"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-intake-photo-upload"]').first()).toBeVisible();
  });

  test('service_order_appears_after_intake', async ({ page }) => {
    await page.route(workOrdersPath, async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            items: [
              { id: 2002, title: 'Nový příjem vozidla', status: 'intake_pending', vehicle_label: 'VW Golf', source_type: 'intake' },
            ],
            total: 1,
          }),
        });
        return;
      }
      await route.continue();
    });
    const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
    const slug = slugMatch?.[1] || 'e2e-fixed-service';
    await page.goto(`/web/app/s/${slug}/work-orders`, { waitUntil: 'domcontentloaded' });
    await waitForServiceShellReady(page);
    await expect(page.locator('[data-testid="service-work-order-row"]')).toContainText(/Nový příjem|intake/i);
  });

  test('technician_accepts_order_and_completes_it', async ({ page }) => {
    const woId = 3003;
    let woStatus = 'intake_pending';
    await page.route(new RegExp(`/api/service/work-orders/${woId}(?:/|$)`), async (route) => {
      const method = route.request().method();
      if (method === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: woId,
            title: 'Nový příjem vozidla',
            status: woStatus,
            vehicle_label: 'Skoda Octavia',
            customer_id: 101,
            owner_id: 101,
            capabilities: {
              accept: woStatus === 'intake_pending',
              complete: woStatus !== 'completed',
              create_service_record: woStatus === 'completed',
              invoices: true,
            },
            items: { labor: [], parts: [], time: [] },
            photos: [],
          }),
        });
        return;
      }
      if (method === 'POST' && route.request().url().includes('/accept')) {
        woStatus = 'in_progress';
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ id: woId, status: 'in_progress' }),
        });
        return;
      }
      if (method === 'POST' && route.request().url().includes('/complete')) {
        woStatus = 'completed';
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ id: woId, status: 'completed' }),
        });
        return;
      }
      await route.continue();
    });
    await page.route(workOrdersPath, async (route) => {
      if (route.request().method() === 'GET' && !route.request().url().includes(`/${woId}`)) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            items: [{ id: woId, title: 'Nový příjem vozidla', status: 'intake_pending' }],
            total: 1,
          }),
        });
        return;
      }
      await route.continue();
    });
    const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
    const slug = slugMatch?.[1] || 'e2e-fixed-service';
    await page.goto(`/web/app/s/${slug}/work-orders`, { waitUntil: 'domcontentloaded' });
    await waitForServiceShellReady(page);
    await page.locator('[data-testid="service-work-order-row"]').first().click();
    await expect(page.locator('[data-testid="service-work-order-accept-button"]')).toBeVisible();
    await page.locator('[data-testid="service-work-order-accept-button"]').click();
    await expect(page.locator('[data-testid="service-work-order-complete-button"]')).toBeVisible({ timeout: 15_000 });
    await Promise.all([
      page.waitForResponse((r) => r.url().includes(`/work-orders/${woId}/complete`) && r.status() === 200),
      page.locator('[data-testid="service-work-order-complete-button"]').click(),
    ]);
    await expect(page.locator('[data-testid="service-work-order-completion-panel"]')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('[data-testid="service-work-order-complete-invoice"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-work-order-complete-record"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-work-order-complete-both"]')).toBeVisible();
  });
});
