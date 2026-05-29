import { expect, test } from '@playwright/test';

import {
  getServiceTestCredentials,
  loginServiceUser,
  waitForServiceShellReady,
} from './helpers';

const intakeLookupPath = '**/api/v1/services/workspace/vehicles/lookup';
const intakeLegacyLookupPath = '**/api/v1/services/workspace/vehicle-lookup';

const MOBILE_VIEWPORTS = [
  { name: 'iphone', width: 390, height: 844 },
  { name: 'android', width: 412, height: 915 },
  { name: 'tablet', width: 768, height: 1024 },
] as const;

async function openIntake(page: Parameters<typeof test>[0]['page']) {
  const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
  const slug = slugMatch?.[1] || 'e2e-fixed-service';
  await page.goto(`/web/app/s/${slug}/intake`, { waitUntil: 'domcontentloaded' });
  await waitForServiceShellReady(page);
}

async function clickIntakeCta(page: Parameters<typeof test>[0]['page'], testId: string) {
  const btn = page.locator(`[data-testid="${testId}"]`);
  await btn.scrollIntoViewIfNeeded();
  await btn.click({ force: true, timeout: 15_000 });
}

async function waitForIntakeStable(page: Parameters<typeof test>[0]['page']) {
  await expect(page.locator('[data-testid="service-intake-section"]')).toBeVisible();
  const lookupBtn = page.locator('[data-testid="service-intake-lookup-button"]');
  await expect(lookupBtn).toBeVisible();
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

async function assertNoHorizontalOverflow(page: Parameters<typeof test>[0]['page']) {
  const ok = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2);
  expect(ok).toBe(true);
}

async function assertPlateInputIsActiveElement(page: Parameters<typeof test>[0]['page']) {
  const focused = await page.evaluate(() => {
    const el = document.querySelector('[data-testid="service-intake-plate-input"]');
    return el instanceof HTMLElement && document.activeElement === el;
  });
  expect(focused).toBe(true);
}

async function fillPlateStable(page: Parameters<typeof test>[0]['page'], value: string) {
  await page.evaluate((val) => {
    const el = document.querySelector('[data-testid="service-intake-plate-input"]');
    if (!(el instanceof HTMLInputElement)) throw new Error('SPZ input not found');
    el.focus();
    el.value = val;
    el.dispatchEvent(new Event('input', { bubbles: true }));
  }, value);
}

function mockIntakeLookupRoutes(page: Parameters<typeof test>[0]['page']) {
  return Promise.all([
    page.route(intakeLookupPath, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ found: false, status: 'not_found', can_create_unowned_vehicle: true }),
      });
    }),
    page.route(intakeLegacyLookupPath, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ candidates: [] }),
      });
    }),
  ]);
}

async function lookupPlateAfterFill(page: Parameters<typeof test>[0]['page'], plate: string) {
  const plateInput = page.locator('[data-testid="service-intake-plate-input"]');
  await plateInput.scrollIntoViewIfNeeded();
  await plateInput.fill(plate);
  const lookupDone = page.waitForResponse(
    (response) => response.url().includes('/vehicles/lookup') && response.ok(),
    { timeout: 20_000 },
  );
  await page.locator('[data-testid="service-intake-lookup-button"]').click({ force: true });
  await lookupDone;
  const status = await page.evaluate(() => window.serviceShell?.state?.intakeLookupResponse?.status || '');
  expect(status, 'lookup should return not_found from mock').toBe('not_found');
  await expect(page.locator('[data-testid="service-intake-not-found-message"]')).toBeVisible({ timeout: 5_000 });
}

for (const viewport of MOBILE_VIEWPORTS) {
  test.describe(`Mobile intake (${viewport.name} ${viewport.width}x${viewport.height})`, () => {
    test.use({
      viewport: { width: viewport.width, height: viewport.height },
      hasTouch: true,
    });

    test.beforeEach(async ({ page }) => {
      test.skip(!getServiceTestCredentials(), 'Nastavte E2E_SERVICE_EMAIL a E2E_SERVICE_PASSWORD');
      await loginServiceUser(page);
      await waitForServiceShellReady(page);
    });

    test('mobile_intake_route_loads', async ({ page }) => {
      await openIntake(page);
      await waitForIntakeStable(page);
      await expect(page.locator('[data-testid="service-intake-section"]')).toBeVisible();
      await assertNoHorizontalOverflow(page);
    });

    test('mobile_spz_input_keeps_focus_while_typing', async ({ page }) => {
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
      await page.evaluate(() => {
        const el = document.querySelector('[data-testid="service-intake-plate-input"]');
        if (el instanceof HTMLElement) {
          el.scrollIntoView({ block: 'center', inline: 'nearest' });
          el.focus();
        }
      });
      for (const ch of '1AB2345'.split('')) {
        await page.keyboard.press(ch);
        await assertPlateInputIsActiveElement(page);
      }
    });

    test('mobile_lookup_not_found_shows_add_vehicle_cta', async ({ page }) => {
      await mockIntakeLookupRoutes(page);
      await openIntake(page);
      await lookupPlateAfterFill(page, '4AB0000');
      const message = page.locator('[data-testid="service-intake-not-found-message"]');
      const cta = page.locator('[data-testid="service-intake-add-vehicle-button"]');
      await cta.scrollIntoViewIfNeeded();
      await expect(cta).toBeVisible();
      await assertNoHorizontalOverflow(page);
    });

    test('mobile_create_vehicle_panel_is_visible', async ({ page }) => {
      await mockIntakeLookupRoutes(page);
      await openIntake(page);
      await lookupPlateAfterFill(page, '7MO0002');
      await page.evaluate(() => window.serviceShell.openIntakeCreateVehicleForm());
      const panel = page.locator('[data-testid="service-intake-create-vehicle-panel"]');
      await panel.scrollIntoViewIfNeeded();
      await expect(panel).toBeVisible();
      await expect(page.locator('[data-testid="service-intake-create-plate"]')).toHaveValue(/7MO/i);
    });

    test('mobile_create_vehicle_form_has_no_horizontal_overflow', async ({ page }) => {
      await mockIntakeLookupRoutes(page);
      await openIntake(page);
      await lookupPlateAfterFill(page, '7MO0003');
      await page.evaluate(() => window.serviceShell.openIntakeCreateVehicleForm());
      await expect(page.locator('[data-testid="service-intake-create-vehicle-panel"]')).toBeVisible();
      await assertNoHorizontalOverflow(page);
    });

    test('mobile_fuel_field_is_usable', async ({ page }) => {
      await mockIntakeLookupRoutes(page);
      await openIntake(page);
      await lookupPlateAfterFill(page, '7MO0004');
      await page.evaluate(() => window.serviceShell.openIntakeCreateVehicleForm());
      const fuel = page.locator('[data-testid="service-intake-create-fuel"]');
      await fuel.scrollIntoViewIfNeeded();
      await expect(fuel).toBeVisible();
      await expect(fuel).toBeEnabled();
      await expect(fuel.locator('option')).not.toHaveCount(0);
      await fuel.selectOption({ label: 'Nafta' });
      await expect(fuel).toHaveValue('Nafta');
    });

    test('mobile_f5_keeps_session_on_intake', async ({ page }) => {
      await openIntake(page);
      await waitForIntakeStable(page);
      await expect(page.locator('[data-testid="service-intake-section"]')).toBeVisible();
      await page.reload({ waitUntil: 'domcontentloaded' });
      await waitForServiceShellReady(page);
      await expect(page.locator('[data-testid="service-intake-section"]')).toBeVisible();
      await expect(page).not.toHaveURL(/\/login/i);
    });
  });
}
