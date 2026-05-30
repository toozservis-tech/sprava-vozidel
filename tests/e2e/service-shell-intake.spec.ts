import { expect, test } from '@playwright/test';

import {
  getServiceTestCredentials,
  loginServiceUser,
  waitForServiceShellReady,
} from './helpers';

const intakeLookupPath = '**/api/v1/services/workspace/vehicles/lookup';
const intakeAccessRequestPath = '**/api/v1/services/workspace/access-requests';
const intakeProvisionPath = '**/api/v1/services/workspace/vehicles/provision-unowned';
const intakeWorkAccessPath = '**/api/v1/services/workspace/vehicles/*/work-access';

async function openIntake(page: Parameters<typeof test>[0]['page']) {
  const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
  const slug = slugMatch?.[1] || 'e2e-fixed-service';
  await page.goto(`/web/app/s/${slug}/intake`, { waitUntil: 'domcontentloaded' });
  await waitForServiceShellReady(page);
}

async function waitForIntakeStable(page: Parameters<typeof test>[0]['page']) {
  await expect(page.locator('[data-testid="service-intake-section"]')).toBeVisible();
  const lookupBtn = page.locator('[data-testid="service-intake-lookup-button"]');
  await expect(lookupBtn).toHaveText(/načíst vozidlo/i, { timeout: 45_000 });
  await page.waitForFunction(() => {
    const input = document.querySelector('[data-testid="service-intake-plate-input"]');
    const btn = document.querySelector('[data-testid="service-intake-lookup-button"]');
    return input instanceof HTMLElement
      && input.isConnected
      && btn instanceof HTMLElement
      && !/načítám/i.test(btn.textContent || '');
  }, { timeout: 45_000 });
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
    await expect(page.locator('[data-testid="service-intake-access-not-requested"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-intake-access-state"]')).toContainText(/přístup vyžaduje rozhodnutí/i);
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
    await expect(root).toContainText(/čeká na schválení majitele/i);
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
    await expect(page.locator('[data-testid="service-intake-request-owner-link-button"]')).toBeVisible();
    await Promise.all([
      page.waitForResponse((response) => response.url().includes('/access-requests') && response.status() === 200),
      page.locator('[data-testid="service-intake-request-owner-link-button"]').click(),
    ]);
    await expect(page.locator('[data-testid="service-intake-access-state"]')).toContainText(/čeká na schválení majitele/i, { timeout: 20_000 });
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
    await expect(page.locator('[data-testid="service-intake-not-found-message"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-intake-add-vehicle-button"]')).toBeVisible();
  });

  test('service_lookup_keeps_focus_while_typing', async ({ page }) => {
    await page.route(intakeLookupPath, async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 8000));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ found: false, status: 'not_found', can_create_unowned_vehicle: true }),
      });
    });
    await openIntake(page);
    await waitForIntakeStable(page);
    const plateInput = page.locator('[data-testid="service-intake-plate-input"]');
    await plateInput.click();
    for (const ch of '1AB2345'.split('')) {
      await plateInput.press(ch);
      const focused = await page.evaluate(() => {
        const el = document.querySelector('[data-testid="service-intake-plate-input"]');
        return el instanceof HTMLElement && document.activeElement === el;
      });
      expect(focused).toBe(true);
    }
  });

  test('service_lookup_not_found_opens_create_vehicle', async ({ page }) => {
    await page.route(intakeLookupPath, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ found: false, status: 'not_found', can_create_unowned_vehicle: true }),
      });
    });
    await openIntake(page);
    await page.locator('[data-testid="service-intake-plate-input"]').fill('9ZZ9999');
    await page.locator('[data-testid="service-intake-lookup-button"]').click();
    await expect(page.locator('[data-testid="service-intake-not-found-message"]')).toBeVisible();
    await page.locator('[data-testid="service-intake-add-vehicle-button"]').click();
    await expect(page.locator('[data-testid="service-intake-create-vehicle-panel"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-intake-create-plate"]')).toHaveValue(/9ZZ/i);
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
    await page.locator('[data-testid="service-intake-add-vehicle-button"]').click();
    await page.locator('[data-testid="service-intake-create-brand"]').fill('Skoda');
    await page.locator('[data-testid="service-intake-create-model"]').fill('Fabia');
    await page.locator('[data-testid="service-intake-save-vehicle-button"]').click();
    await expect(page.locator('[data-testid="service-intake-section"]')).toContainText(/bez vlastnické vazby/i);
  });

  test('service_intake_work_access_enables_work_order', async ({ page }) => {
    await page.route(intakeLookupPath, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          found: true,
          status: 'found_access_required',
          vehicle_preview: {
            vehicle_id: 501,
            brand: 'Skoda',
            model: 'Octavia',
            vin_masked: 'TMB***5010',
            plate_masked: '5AB***01',
          },
          access: { status: 'not_requested', can_request_access: true },
          can_create_work_order: false,
          owner_data: null,
        }),
      });
    });
    await page.route(intakeWorkAccessPath, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'work_access',
          vehicle_preview: {
            vehicle_id: 501,
            brand: 'Skoda',
            model: 'Octavia',
            vin_masked: 'TMB***5010',
            plate_masked: '5AB***01',
          },
        }),
      });
    });
    await openIntake(page);
    await page.locator('[data-testid="service-intake-vin-input"]').fill('TMBJH7NP9N7050101');
    await page.locator('[data-testid="service-intake-lookup-button"]').click();
    await expect(page.locator('[data-testid="service-intake-access-not-requested"]')).toBeVisible();
    await page.locator('[data-testid="service-intake-one-time-work-button"]').click();
    await expect(page.locator('[data-testid="service-intake-access-work-access"]')).toContainText(/Jednorázový servisní zásah/i);
    await expect(page.locator('[data-testid="service-intake-create-work-order-button"]')).toBeEnabled();
  });

  test('service_intake_rejected_shows_both_ctas', async ({ page }) => {
    await page.route(intakeLookupPath, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          found: true,
          status: 'found_access_required',
          vehicle_preview: {
            vehicle_id: 502,
            brand: 'VW',
            model: 'Golf',
            vin_masked: 'WVW***5020',
            plate_masked: '5AB***02',
          },
          access: { status: 'rejected', can_request_access: true },
          can_create_work_order: false,
          owner_data: null,
        }),
      });
    });
    await openIntake(page);
    await page.locator('[data-testid="service-intake-plate-input"]').fill('5AB5002');
    await page.locator('[data-testid="service-intake-lookup-button"]').click();
    await expect(page.locator('[data-testid="service-intake-access-rejected"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-intake-one-time-work-button"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-intake-request-owner-link-button"]')).toBeEnabled();
    await expect(page.locator('[data-testid="service-intake-create-work-order-button"]')).toBeDisabled();
  });

  test('service_intake_unowned_vehicle_work_order_enabled', async ({ page }) => {
    await page.route(intakeLookupPath, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          found: true,
          status: 'found_service_unowned',
          vehicle_preview: {
            vehicle_id: 503,
            brand: 'Skoda',
            model: 'Fabia',
            vin_masked: 'TMB***5030',
            plate_masked: '5AB***03',
          },
          access: { status: 'work_access', can_request_access: false },
          can_create_work_order: true,
          owner_data: null,
        }),
      });
    });
    await openIntake(page);
    await page.locator('[data-testid="service-intake-vin-input"]').fill('TMBJH7NP9N7050303');
    await page.locator('[data-testid="service-intake-lookup-button"]').click();
    await expect(page.locator('[data-testid="service-intake-access-work-access"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-intake-one-time-work-button"]')).not.toBeVisible();
    await expect(page.locator('[data-testid="service-intake-create-work-order-button"]')).toBeEnabled();
  });

  test('service_intake_ocr_disabled_without_backend', async ({ page }) => {
    await openIntake(page);
    const ocr = page.locator('[data-testid="service-intake-ocr-button"]');
    await expect(ocr).toBeDisabled();
    await expect(ocr).toHaveAttribute('title', /OCR SPZ není aktuálně aktivní/i);
  });

  test('service_intake_crosslink_to_work_orders_or_disabled_notice', async ({ page }) => {
    await openIntake(page);
    const woBtn = page.locator('[data-testid="service-intake-create-work-order-button"]');
    await expect(woBtn).toBeDisabled();
    await expect(woBtn).toHaveAttribute('title', /jednorázový servisní zásah/i);
  });

  test('service_intake_create_work_order_for_unowned_vehicle', async ({ page }) => {
    test.skip(process.env.E2E_ALLOW_MUTATIONS !== '1', 'Mutační test vyžaduje E2E_ALLOW_MUTATIONS=1');
    const uniqueVin = `TMBINT${Date.now().toString().slice(-10)}WO`;
    await openIntake(page);
    await page.locator('[data-testid="service-intake-vin-input"]').fill(uniqueVin);
    await page.locator('[data-testid="service-intake-lookup-button"]').click();
    await page.locator('[data-testid="service-intake-add-vehicle-button"]').click();
    await page.locator('[data-testid="service-intake-create-brand"]').fill('Skoda');
    await page.locator('[data-testid="service-intake-create-model"]').fill('Fabia');
    await page.locator('[data-testid="service-intake-save-vehicle-button"]').click();
    await expect(page.locator('[data-testid="service-intake-section"]')).toContainText(/bez vlastnické vazby/i, {
      timeout: 30_000,
    });
    await page.locator('[data-testid="service-intake-create-work-order-button"]').click();
    await expect(page).toHaveURL(/\/work-orders/, { timeout: 30_000 });
    await waitForServiceShellReady(page);
    await expect(page.locator('[data-testid="service-work-orders-section"]')).toBeVisible();
    const detail = page.locator('[data-testid="service-work-order-detail"]');
    if (await detail.isVisible().catch(() => false)) {
      await expect(detail).toContainText(/Nepřiřazené/i);
    }
  });
});
