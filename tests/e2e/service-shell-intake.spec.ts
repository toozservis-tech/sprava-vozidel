import { expect, test } from '@playwright/test';

import {
  getServiceTestCredentials,
  loginServiceUser,
  waitForServiceShellReady,
} from './helpers';

const intakeLookupPath = '**/api/v1/services/workspace/vehicles/lookup';
const intakeAccessRequestPath = '**/api/v1/services/workspace/access-requests';
const intakeProvisionPath = '**/api/v1/services/workspace/vehicles/provision-unowned';

async function openIntake(page: Parameters<typeof test>[0]['page']) {
  const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
  const slug = slugMatch?.[1] || 'e2e-fixed-service';
  await page.goto(`/web/app/s/${slug}/intake`, { waitUntil: 'domcontentloaded' });
  await waitForServiceShellReady(page);
}

test.describe('Service shell intake route', () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!getServiceTestCredentials(), 'Nastavte E2E_SERVICE_EMAIL a E2E_SERVICE_PASSWORD');
    await loginServiceUser(page);
    await waitForServiceShellReady(page);
  });

  test('service_intake_route_loads', async ({ page }) => {
    await openIntake(page);
    await expect(page.locator('[data-testid="service-intake-section"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-intake-vin-input"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-intake-plate-input"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-intake-lookup-button"]')).toBeVisible();
  });

  test('service_intake_f5_keeps_session', async ({ page }) => {
    await openIntake(page);
    const before = page.url();
    await page.reload({ waitUntil: 'domcontentloaded' });
    await waitForServiceShellReady(page);
    await expect(page).toHaveURL(before);
    await expect(page.locator('[data-testid="login-form"]')).not.toBeVisible();
    await expect(page.locator('[data-testid="service-intake-section"]')).toBeVisible();
  });

  test('service_intake_lookup_empty_validation', async ({ page }) => {
    await openIntake(page);
    await page.locator('[data-testid="service-intake-vin-input"]').fill('');
    await page.locator('[data-testid="service-intake-plate-input"]').fill('');
    await page.locator('[data-testid="service-intake-lookup-button"]').click();
    await expect(page.locator('[data-testid="service-intake-error"]')).toContainText(/zadejte vin nebo spz/i);
  });

  test('service_intake_lookup_existing_vehicle_safe_preview', async ({ page }) => {
    await page.route(intakeLookupPath, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          found: true,
          status: 'found_access_required',
          vehicle_preview: {
            vehicle_id: 101,
            brand: 'Skoda',
            model: 'Octavia',
            year: 2021,
            vin_masked: 'TMB***1234',
            plate_masked: '1AB***45',
            in_system: true,
          },
          access: { status: 'not_requested', can_request_access: true },
          owner_data: null,
          service_history: null,
          documents: null,
          photos: null,
          prices: null,
          invoices: null,
        }),
      });
    });
    await openIntake(page);
    await page.locator('[data-testid="service-intake-vin-input"]').fill('TMBJH7NP9N7041234');
    await page.locator('[data-testid="service-intake-lookup-button"]').click();
    await expect(page.locator('[data-testid="service-intake-safe-preview"]')).toContainText(/Skoda Octavia/i);
    await expect(page.locator('[data-testid="service-intake-access-state"]')).toContainText(/autorizaci majitele/i);
  });

  test('service_intake_lookup_existing_vehicle_no_pii', async ({ page }) => {
    await page.route(intakeLookupPath, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          found: true,
          status: 'found_access_required',
          vehicle_preview: {
            vehicle_id: 202,
            brand: 'VW',
            model: 'Passat',
            year: 2020,
            vin_masked: 'WVW***9876',
            plate_masked: '2AB***66',
            in_system: true,
          },
          access: { status: 'pending', can_request_access: false },
          owner_data: null,
          service_history: null,
          documents: null,
          photos: null,
          prices: null,
          invoices: null,
        }),
      });
    });
    await openIntake(page);
    await page.locator('[data-testid="service-intake-plate-input"]').fill('2AB6666');
    await page.locator('[data-testid="service-intake-lookup-button"]').click();
    const root = page.locator('[data-testid="service-intake-section"]');
    const safePreview = page.locator('[data-testid="service-intake-safe-preview"]');
    await expect(root).toContainText(/čeká na autorizaci/i);
    await expect(safePreview).toBeVisible();
    await expect(safePreview).not.toContainText('@');
    await expect(safePreview).not.toContainText(/faktur|cena|kč|pdf|dokument/i);
  });

  test('service_intake_request_access_flow', async ({ page }) => {
    await page.route(intakeLookupPath, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          found: true,
          status: 'found_access_required',
          vehicle_preview: { vehicle_id: 303, brand: 'Audi', model: 'A4', vin_masked: 'WAU***4567', plate_masked: '3AB***77' },
          access: { status: 'not_requested', can_request_access: true },
          owner_data: null,
          service_history: null,
          documents: null,
          photos: null,
          prices: null,
          invoices: null,
        }),
      });
    });
    await page.route(intakeAccessRequestPath, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ created: true, request_id: 999, status: 'pending', email_sent: false }),
      });
    });
    await openIntake(page);
    await page.locator('[data-testid="service-intake-vin-input"]').fill('WAUZZZ8K9AA000001');
    await page.locator('[data-testid="service-intake-lookup-button"]').click();
    await page.locator('[data-testid="service-intake-request-access-button"]').click();
    await expect(page.locator('[data-testid="service-intake-access-state"]')).toContainText(/čeká na autorizaci/i);
  });

  test('service_intake_not_found_shows_create_unowned', async ({ page }) => {
    await page.route(intakeLookupPath, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ found: false, status: 'not_found', can_create_unowned_vehicle: true, message: 'Vozidlo není v systému.' }),
      });
    });
    await openIntake(page);
    await page.locator('[data-testid="service-intake-plate-input"]').fill('4AB0000');
    await page.locator('[data-testid="service-intake-lookup-button"]').click();
    await expect(page.locator('[data-testid="service-intake-create-unowned-button"]')).toBeVisible();
  });

  test('service_intake_create_unowned_vehicle', async ({ page }) => {
    test.skip(process.env.E2E_ALLOW_MUTATIONS !== '1', 'Mutační test vyžaduje E2E_ALLOW_MUTATIONS=1');
    await page.route(intakeLookupPath, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ found: false, status: 'not_found', can_create_unowned_vehicle: true, message: 'Vozidlo není v systému.' }),
      });
    });
    await page.route(intakeProvisionPath, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          created: true,
          vehicle_id: 404,
          status: 'service_provisioned_unowned',
          message: 'Nepřiřazené vozidlo bylo založeno.',
          vehicle_preview: { vehicle_id: 404, brand: 'Skoda', model: 'Fabia', vin_masked: 'TMB***2026', plate_masked: '5AB***00' },
        }),
      });
    });
    await openIntake(page);
    await page.locator('[data-testid="service-intake-vin-input"]').fill('TMBJH7NP9N7041026');
    await page.locator('[data-testid="service-intake-lookup-button"]').click();
    await page.locator('[data-testid="service-intake-section"]').getByLabel('Značka').fill('Skoda');
    await page.locator('[data-testid="service-intake-section"]').getByLabel('Model').fill('Fabia');
    await page.locator('[data-testid="service-intake-create-unowned-button"]').click();
    await expect(page.locator('[data-testid="service-intake-section"]')).toContainText(/bez vlastnické vazby/i);
  });

  test('service_intake_ocr_disabled_without_backend', async ({ page }) => {
    await openIntake(page);
    const ocr = page.locator('[data-testid="service-intake-ocr-button"]');
    await expect(ocr).toBeDisabled();
    await expect(ocr).toHaveAttribute('title', /OCR SPZ není aktuálně aktivní/i);
  });

  test('service_intake_crosslink_to_work_orders_or_disabled_notice', async ({ page }) => {
    await openIntake(page);
    await page.locator('[data-testid="service-intake-create-work-order-button"]').click();
    await expect(page.locator('[data-testid="service-intake-section"]')).toContainText(/Převod příjmu na zakázku bude doplněn/i);
  });
});
