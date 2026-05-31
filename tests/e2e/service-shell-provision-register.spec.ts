import { expect, test } from '@playwright/test';

import {
  getServiceTestCredentials,
  loginServiceUser,
  waitForServiceShellReady,
} from './helpers';

const decodeVinPath = '**/api/vehicles/decode-vin';
const decodePlatePath = '**/api/vehicles/decode-plate';
const provisionPath = '**/api/v1/services/workspace/vehicles/provision-unowned';

const mockVinDecodeBody = {
  success: true,
  data: {
    vin: 'TMBJH7NP9N7041234',
    make: 'Skoda',
    model: 'Octavia',
    production_year: 2019,
    fuel_type: 'nm',
    stk_valid_until: '2027-05-01',
    engine_displacement_cc: 1968,
    engine_power_kw: 110,
    tyres: ['205/55 R16'],
  },
  errors: [],
};

const mockPlateDecodeBody = {
  success: true,
  data: {
    plate: '1AB2345',
    vin: 'WVWZZZ1KZAW123456',
    make: 'Volkswagen',
    model: 'Golf',
    production_year: 2020,
    fuel_type: 'bm',
    stk_valid_until: '2026-11-15',
    engine_type_label: '1.5 TSI 110 kW',
  },
  errors: [],
};

async function openProvisionModal(page: import('@playwright/test').Page, query = '') {
  await page.evaluate((prefill) => {
    const shell = (window as typeof window & {
      serviceShell?: { openProvisionUnownedVehicleModal?: () => void; setVehicleLookupQuery?: (q: string) => void };
    }).serviceShell;
    if (prefill && typeof shell?.setVehicleLookupQuery === 'function') {
      shell.setVehicleLookupQuery(prefill);
    }
    shell?.openProvisionUnownedVehicleModal?.();
  }, query);
  await expect(page.locator('[data-testid="service-intake-register-load-button"]')).toBeVisible({ timeout: 15_000 });
}

test.describe('Service provision register lookup', () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!getServiceTestCredentials(), 'Nastavte E2E_SERVICE_EMAIL a E2E_SERVICE_PASSWORD');
    await loginServiceUser(page);
    await waitForServiceShellReady(page);
  });

  test('service_intake_register_auto_load_once_on_open', async ({ page }) => {
    let decodeCalls = 0;
    await page.route(decodeVinPath, async (route) => {
      decodeCalls += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockVinDecodeBody),
      });
    });
    await openProvisionModal(page, 'TMBJH7NP9N7041234');
    await expect(page.locator('[data-testid="service-intake-register-success"]')).toContainText(/Skoda Octavia/i, {
      timeout: 15_000,
    });
    await page.waitForTimeout(1200);
    expect(decodeCalls).toBe(1);
  });

  test('service_intake_unowned_vehicle_loads_register_by_vin', async ({ page }) => {
    let decodeCalls = 0;
    await page.route(decodeVinPath, async (route) => {
      decodeCalls += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockVinDecodeBody),
      });
    });
    await openProvisionModal(page);
    await page.locator('#serviceShellProvisionQuery').fill('TMBJH7NP9N7041234');
    const decodeResponse = page.waitForResponse(
      (response) => response.url().includes('/api/vehicles/decode-vin') && response.ok(),
    );
    await page.locator('[data-testid="service-intake-register-load-button"]').click();
    await decodeResponse;
    await expect(page.locator('[data-testid="service-intake-register-success"]')).toContainText(/Skoda Octavia/i, {
      timeout: 15_000,
    });
    await expect(page.locator('[data-testid="service-intake-provision-brand"]')).toHaveValue('Skoda');
    await expect(page.locator('[data-testid="service-intake-provision-model"]')).toHaveValue('Octavia');
    await expect(page.locator('[data-testid="service-intake-provision-year"]')).toHaveValue('2019');
    await expect(page.locator('[data-testid="service-intake-provision-fuel"]')).toHaveValue('Nafta');
    expect(decodeCalls).toBeGreaterThan(0);
  });

  test('service_intake_unowned_vehicle_loads_register_by_plate', async ({ page }) => {
    let decodeCalls = 0;
    await page.route(decodePlatePath, async (route) => {
      decodeCalls += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockPlateDecodeBody),
      });
    });
    await openProvisionModal(page);
    await page.locator('#serviceShellProvisionQuery').fill('1AB2345');
    await page.locator('[data-testid="service-intake-register-load-button"]').click();
    await expect(page.locator('[data-testid="service-intake-register-success"]')).toContainText(/Volkswagen Golf/i, {
      timeout: 15_000,
    });
    await expect(page.locator('[data-testid="service-intake-provision-brand"]')).toHaveValue('Volkswagen');
    expect(decodeCalls).toBe(1);
  });

  test('service_intake_register_does_not_overwrite_manual_note', async ({ page }) => {
    await page.route(decodeVinPath, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockVinDecodeBody),
      });
    });
    await openProvisionModal(page);
    await page.locator('#serviceShellProvisionQuery').fill('TMBJH7NP9N7041234');
    await page.locator('[data-testid="service-intake-provision-note"]').fill('Vlastní poznámka technika');
    await page.locator('[data-testid="service-intake-register-load-button"]').click();
    await expect(page.locator('[data-testid="service-intake-register-success"]')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('[data-testid="service-intake-provision-note"]')).toHaveValue('Vlastní poznámka technika');
  });

  test('service_intake_register_sends_fuel_on_save', async ({ page }) => {
    let capturedPayload: Record<string, unknown> | null = null;
    await page.route(decodeVinPath, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockVinDecodeBody),
      });
    });
    await page.route(provisionPath, async (route) => {
      capturedPayload = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          created: true,
          vehicle_id: 9099,
          status: 'service_provisioned_unowned',
          message: 'Vozidlo evidováno bez majitele.',
        }),
      });
    });
    await openProvisionModal(page);
    await page.locator('#serviceShellProvisionQuery').fill('TMBJH7NP9N7041234');
    await page.locator('[data-testid="service-intake-register-load-button"]').click();
    await expect(page.locator('[data-testid="service-intake-register-success"]')).toBeVisible({ timeout: 15_000 });
    await page.locator('button:has-text("Založit nepřiřazené vozidlo")').click();
    await expect.poll(() => capturedPayload?.fuel).toBe('Nafta');
    expect(capturedPayload?.brand).toBe('Skoda');
    expect(capturedPayload?.model).toBe('Octavia');
  });

  test('mobile_register_button_no_overflow', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.route(decodeVinPath, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockVinDecodeBody),
      });
    });
    await openProvisionModal(page);
    const button = page.locator('[data-testid="service-intake-register-load-button"]');
    await expect(button).toBeVisible();
    const box = await button.boundingBox();
    expect(box?.height || 0).toBeGreaterThanOrEqual(44);
    const overflow = await page.locator('.service-provision-register-actions').evaluate((el) => {
      const node = el as HTMLElement;
      return node.scrollWidth > node.clientWidth + 2;
    });
    expect(overflow).toBeFalsy();
  });
});
