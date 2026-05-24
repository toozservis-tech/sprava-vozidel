import { expect, test } from '@playwright/test';
import { getServiceTestCredentials, loginServiceUser } from './helpers';

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

test.describe('Real service auth browser smoke', () => {
  test.beforeEach(() => {
    test.skip(!getServiceTestCredentials(), 'Nastavte E2E_SERVICE_EMAIL a E2E_SERVICE_PASSWORD pro servisní E2E');
  });

  test('service login, intake, approval, work and logout are backed by real API', async ({ page }) => {
    const runId = `${Date.now()}${test.info().workerIndex}`;
    const suffix = runId.slice(-8);
    const ownerEmail = 'e2e.lifecycle.buyer@example.com';
    const ownerPassword = 'E2eTest123!';
    const vin = `TMS${suffix.padStart(10, '0')}REAL`.slice(0, 17);
    const plate = `RS${suffix.slice(-6)}`.toUpperCase();
    const stkDate = new Date(Date.now() + 365 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);

    const ownerLogin = await page.request.post('/user/login', {
      headers: { 'x-forwarded-proto': 'https' },
      data: { email: ownerEmail, password: ownerPassword },
    });
    expect(ownerLogin.ok(), await ownerLogin.text()).toBeTruthy();
    const ownerToken = (await ownerLogin.json()).access_token;
    const ownerHeaders = {
      Authorization: `Bearer ${ownerToken}`,
      'x-forwarded-proto': 'https',
    };
    const createdVehicleResponse = await page.request.post('/api/v1/vehicles', {
      headers: ownerHeaders,
      data: {
        vin,
        plate,
        nickname: `Real service ${suffix}`,
        brand: 'Skoda',
        model: 'ServiceFlow',
        year: 2021,
        engine: '2.0 TDI',
        stk_valid_until: stkDate,
      },
    });
    expect(createdVehicleResponse.ok(), await createdVehicleResponse.text()).toBeTruthy();
    const vehicleId = Number((await createdVehicleResponse.json()).id);
    expect(vehicleId).toBeGreaterThan(0);

    const serviceCredentials = getServiceTestCredentials();
    expect(serviceCredentials).toBeTruthy();
    await loginServiceUser(page, serviceCredentials!.email, serviceCredentials!.password);
    await expect(page.locator('[data-service-shell="root"]')).toBeVisible({ timeout: 25_000 });
    await expect(page).toHaveURL(/\/(web\/)?app\/s\/[^/]+\/dashboard/);

    const serviceRequest = async (endpoint: string, method = 'GET', body?: unknown) => page.evaluate(async ({ endpoint, method, body }) => {
      const token = localStorage.getItem('accessToken') || sessionStorage.getItem('accessToken') || '';
      const response = await fetch(endpoint, {
        method,
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
          'x-forwarded-proto': 'https',
        },
        body: body == null ? undefined : JSON.stringify(body),
      });
      const text = await response.text();
      let data: unknown = null;
      try {
        data = text ? JSON.parse(text) : null;
      } catch {
        data = { raw: text };
      }
      return { ok: response.ok, status: response.status, data };
    }, { endpoint, method, body }) as Promise<{ ok: boolean; status: number; data: any }>;

    const assignedBefore = await serviceRequest('/api/service/vehicles/assigned');
    expect(assignedBefore.ok).toBeTruthy();
    expect(Array.isArray(assignedBefore.data.items)).toBeTruthy();

    const search = await serviceRequest(`/api/service/vehicles/search?q=${encodeURIComponent(plate)}`);
    expect(search.ok).toBeTruthy();
    expect(search.data.items?.[0]?.vehicle_id).toBe(vehicleId);
    expect(search.data.items?.[0]?.can_request_access).toBeTruthy();

    const intake = await serviceRequest('/api/service/vehicle-intake/from-spz-photo', 'POST', {
      manual_spz: plate,
      file_name: 'real-service-intake.jpg',
      file_mime_type: 'image/jpeg',
    });
    expect(intake.ok).toBeTruthy();
    const caseId = Number(intake.data.case.id);
    expect(caseId).toBeGreaterThan(0);
    expect(intake.data.requires_owner_approval).toBeTruthy();

    const blockedRecord = await serviceRequest(`/api/service/vehicle-intake/${caseId}/create-service-record`, 'POST', {
      template_type: 'oil_change',
      description: 'Blocked before approved access',
    });
    expect(blockedRecord.status).toBe(403);

    const accessRequest = await serviceRequest(`/api/service/vehicle-intake/${caseId}/owner-access-request`, 'POST', {
      message: 'E2E real service access request',
    });
    expect(accessRequest.ok).toBeTruthy();
    const requestId = Number(accessRequest.data.request_id);
    expect(requestId).toBeGreaterThan(0);

    const approve = await page.request.post(`/api/v1/vehicles/${vehicleId}/service-access/${requestId}/approve`, {
      headers: ownerHeaders,
      data: { note: 'E2E approved' },
    });
    expect(approve.ok(), await approve.text()).toBeTruthy();

    const assignedAfter = await serviceRequest('/api/service/vehicles/assigned');
    expect(assignedAfter.ok).toBeTruthy();
    expect(JSON.stringify(assignedAfter.data.items)).toContain(String(vehicleId));

    const start = await serviceRequest(`/api/service/vehicle-intake/${caseId}/start-work`, 'POST');
    expect(start.ok).toBeTruthy();
    const stop = await serviceRequest(`/api/service/vehicle-intake/${caseId}/stop-work`, 'POST');
    expect(stop.ok).toBeTruthy();

    const finalRecord = await serviceRequest(`/api/service/vehicle-intake/${caseId}/create-service-record`, 'POST', {
      template_type: 'oil_change',
      description: 'Real service browser final record',
      mileage: 123450,
      recommended_next_service_km: 138450,
    });
    expect(finalRecord.ok).toBeTruthy();
    expect(finalRecord.data.created).toBeTruthy();

    await page.evaluate(() => {
      const shell = (window as unknown as { serviceShell?: { logout?: () => void } }).serviceShell;
      shell?.logout?.();
    });
    await expect(page.locator('[data-testid="login-form"]')).toBeVisible({ timeout: 15_000 });
    await page.goBack();
    await expect(page.locator('[data-testid="dashboard"]')).not.toBeVisible();
  });
});
