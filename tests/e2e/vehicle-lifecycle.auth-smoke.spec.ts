import fs from 'node:fs';
import { expect, test } from '@playwright/test';
import { loginUser } from './helpers';

test.use({
  extraHTTPHeaders: {
    'x-forwarded-proto': 'https',
  },
  screenshot: 'off',
  video: 'off',
  launchOptions: {
    args: ['--disable-dev-shm-usage', '--disable-gpu', '--disable-extensions', '--no-zygote', '--single-process'],
  },
});

test.describe('Vehicle lifecycle browser click-through', () => {
  test('removal sale PDF transfer claim preserves history', async ({ page }) => {
    const runId = `${Date.now()}${test.info().workerIndex}`;
    const suffix = runId.slice(-8);
    const ownerEmail = 'e2e.lifecycle.owner@example.com';
    const buyerEmail = 'e2e.lifecycle.buyer@example.com';
    const password = 'E2eTest123!';
    const vin = `TMB${suffix.padStart(10, '0')}ABCD`.slice(0, 17);
    const plate = `LC${suffix.slice(-6)}`.toUpperCase();
    const stkDate = new Date(Date.now() + 365 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);

    await page.goto('/web/login');
    await loginUser(page, ownerEmail, password);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 20_000 });

    const createdVehicle = await page.evaluate(async ({ vin, plate, suffix, stkDate }) => {
      const api = (window as unknown as { apiCall: (endpoint: string, method?: string, data?: unknown) => Promise<unknown> }).apiCall;
      return api('/api/v1/vehicles', 'POST', {
        vin,
        plate,
        nickname: `Lifecycle ${suffix}`,
        brand: 'Skoda',
        model: 'BrowserFlow',
        year: 2020,
        engine: '2.0 TDI',
        stk_valid_until: stkDate,
      });
    }, { vin, plate, suffix, stkDate }) as { id?: number };
    const vehicleId = Number(createdVehicle.id);
    expect(vehicleId).toBeGreaterThan(0);

    const record = await page.evaluate(async ({ vehicleId }) => {
      const api = (window as unknown as { apiCall: (endpoint: string, method?: string, data?: unknown) => Promise<unknown> }).apiCall;
      return api(`/api/v1/vehicles/${vehicleId}/records`, 'POST', {
        performed_at: new Date().toISOString(),
        mileage: 123456,
        description: 'Lifecycle browser preserved history record',
        price: 0,
        category: 'JINE',
        record_status: 'approved',
      });
    }, { vehicleId });
    expect(Number((record as { id?: number }).id || 0)).toBeGreaterThan(0);

    await page.click('[data-testid="tab-vehicles"]');
    await page.evaluate(async () => {
      const w = window as unknown as { loadVehicles?: () => Promise<void> };
      await w.loadVehicles?.();
    });
    await expect(page.locator(`[data-vehicle-id="${vehicleId}"]`)).toBeVisible({ timeout: 20_000 });
    await page.locator(`[data-vehicle-id="${vehicleId}"]`).getByRole('button', { name: 'Detail' }).click();
    await expect(page.locator('[data-testid="vehicle-detail-modal"]')).toBeVisible({ timeout: 10_000 });
    await page.locator('[data-testid="vehicle-detail-modal"]').getByRole('button', { name: 'Servis' }).click();
    await expect(page.locator('.vehicle-service-actions')).toBeVisible({ timeout: 10_000 });

    const removeResponsePromise = page.waitForResponse((response) => (
      response.request().method() === 'POST'
      && response.url().includes(`/api/v1/vehicles/${vehicleId}/remove/confirm`)
    ));
    await page.locator('.vehicle-service-actions').getByRole('button', { name: /Odebrat/ }).click();
    await expect(page.getByTestId('vehicle-removal-modal')).toBeVisible({ timeout: 10_000 });
    await page.getByTestId('vehicle-removal-reason-sale').check();
    await page.getByTestId('vehicle-removal-buyer-email').fill(buyerEmail);
    await page.getByTestId('vehicle-removal-buyer-phone').fill('+420601' + suffix.slice(-6));
    await page.getByTestId('vehicle-removal-submit').click();
    const removeResponse = await removeResponsePromise;
    const removalText = await removeResponse.text();
    expect(removeResponse.ok(), `remove/confirm HTTP ${removeResponse.status()}: ${removalText}`).toBeTruthy();
    const removal = JSON.parse(removalText);
    expect(removal.removed).toBeTruthy();
    expect(removal.history_preserved).toBeTruthy();
    expect(removal.transfer?.token).toBeTruthy();
    expect(removal.transfer?.qr_payload).toContain('/web/vehicle-transfer.html?token=');
    expect(removal.digital_report_url).toContain('/digital-report?document_id=');
    expect(removal.archive_bundle_path).toContain('vehicle_archives');

    const pdfCheck = await page.evaluate(async (digitalReportUrl) => {
      const token = localStorage.getItem('accessToken') || sessionStorage.getItem('accessToken') || '';
      const response = await fetch(digitalReportUrl, {
        headers: {
          Authorization: `Bearer ${token}`,
          'x-forwarded-proto': 'https',
        },
      });
      const contentType = response.headers.get('content-type') || '';
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const frame = document.createElement('iframe');
      frame.dataset.testid = 'generated-digital-report-frame';
      frame.src = objectUrl;
      frame.style.width = '320px';
      frame.style.height = '240px';
      document.body.appendChild(frame);
      return { ok: response.ok, status: response.status, contentType, size: blob.size };
    }, removal.digital_report_url);
    expect(pdfCheck.ok, `PDF HTTP ${pdfCheck.status}`).toBeTruthy();
    expect(pdfCheck.contentType.toLowerCase()).toContain('application/pdf');
    expect(pdfCheck.size).toBeGreaterThan(1000);
    await expect(page.locator('iframe[data-testid="generated-digital-report-frame"]')).toBeAttached();

    await page.evaluate(() => {
      localStorage.removeItem('accessToken');
      localStorage.removeItem('token');
      sessionStorage.removeItem('accessToken');
      sessionStorage.removeItem('token');
    });
    await page.goto('/web/login');
    await expect(page.locator('[data-testid="login-form"]')).toBeVisible({ timeout: 15_000 });
    await loginUser(page, buyerEmail, password);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 20_000 });

    const transferUrl = new URL(removal.transfer.qr_payload);
    await page.goto(`/web/vehicle-transfer.html${transferUrl.search}`);
    await expect(page.locator('[data-testid="transfer-claim-form"]')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('[data-testid="transfer-summary"]')).toContainText('active');
    await page.fill('[data-testid="transfer-input-spz"]', plate);
    await page.fill('[data-testid="transfer-input-vin"]', vin);
    const claimResponsePromise = page.waitForResponse((response) => (
      response.request().method() === 'POST'
      && response.url().includes('/api/public/vehicle-transfer/')
      && response.url().endsWith('/claim')
    ));
    await page.click('[data-testid="transfer-claim-button"]');
    const claimResponse = await claimResponsePromise;
    expect(claimResponse.ok()).toBeTruthy();
    const claim = await claimResponse.json();
    expect(claim.claimed).toBeTruthy();
    await expect(page.locator('[data-testid="transfer-message"]')).toContainText('Historie zůstala zachovaná');

    await page.goto('/web/app/u/lifecycle-check/vehicles');
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 25_000 });
    await page.click('[data-testid="tab-vehicles"]');
    await expect(page.locator(`[data-vehicle-id="${vehicleId}"]`)).toBeVisible({ timeout: 20_000 });
    const records = await page.evaluate(async ({ vehicleId }) => {
      const api = (window as unknown as { apiCall: (endpoint: string, method?: string, data?: unknown) => Promise<unknown> }).apiCall;
      return api(`/api/v1/vehicles/${vehicleId}/records`, 'GET');
    }, { vehicleId });
    const recordList = Array.isArray(records) ? records : (records as { records?: unknown[] }).records || [];
    expect(JSON.stringify(recordList)).toContain('Lifecycle browser preserved history record');

    fs.writeFileSync('/tmp/toozhub-vehicle-lifecycle-browser-result.json', JSON.stringify({
      vehicleId,
      vin,
      plate,
      archiveBundlePath: removal.archive_bundle_path,
      digitalReportUrl: removal.digital_report_url,
      transferQrPayload: removal.transfer.qr_payload,
      transferTokenLength: String(removal.transfer.token || '').length,
      claimed: claim.claimed,
      historyRecordId: (record as { id?: number }).id,
    }, null, 2));
  });
});
