import { expect, test } from '@playwright/test';

import {
  getE2eHttpHeaders,
  getServiceTestCredentials,
  getTestUserCredentials,
  loginUser,
  waitForUserShellReady,
} from './helpers';

const userServiceRequestsPath = '**/api/v1/user/service-requests**';
const accessDecisionPath = '**/api/v1/services/access-requests/*';
const serviceApprovedPath = '**/api/v1/services/approved-vehicles**';

type ServiceRequestRow = {
  request_id: number;
  vehicle_id: number;
  vehicle_name: string;
  vehicle_plate_masked: string;
  vehicle_vin_masked: string;
  service_name: string;
  reason: string;
  status: string;
  requested_at: string;
  scope: string;
  lookup_plate?: string;
};

async function createPendingRequestViaApi(page: Parameters<typeof test>[0]['page']): Promise<ServiceRequestRow> {
  const userCreds = getTestUserCredentials();
  const serviceCreds = getServiceTestCredentials();
  if (!serviceCreds) {
    throw new Error('Missing E2E service credentials');
  }

  const userLogin = await page.request.post('/user/login', {
    data: { email: userCreds.email, password: userCreds.password, expected_role: 'user' },
    headers: getE2eHttpHeaders(),
  });
  expect(userLogin.status()).toBe(200);
  const userBody = (await userLogin.json()) as { access_token?: string };
  const userToken = String(userBody.access_token || '');
  expect(userToken.length).toBeGreaterThan(10);

  const serviceLogin = await page.request.post('/user/login', {
    data: { email: serviceCreds.email, password: serviceCreds.password, expected_role: 'service' },
    headers: getE2eHttpHeaders(),
  });
  expect(serviceLogin.status()).toBe(200);
  const serviceBody = (await serviceLogin.json()) as { access_token?: string };
  const serviceToken = String(serviceBody.access_token || '');
  expect(serviceToken.length).toBeGreaterThan(10);

  const vehiclesResp = await page.request.get('/api/v1/vehicles', {
    headers: { ...getE2eHttpHeaders(), Authorization: `Bearer ${userToken}` },
  });
  expect(vehiclesResp.status()).toBe(200);
  const vehicles = (await vehiclesResp.json()) as Array<{ id?: number; plate?: string }>;
  const vehicle = vehicles.find((item) => Number(item?.id) > 0);
  if (!vehicle?.id || !vehicle.plate) {
    throw new Error('E2E user has no vehicle with plate for service request flow');
  }

  const serviceMeResp = await page.request.get('/api/me', {
    headers: { ...getE2eHttpHeaders(), Authorization: `Bearer ${serviceToken}` },
  });
  expect(serviceMeResp.status()).toBe(200);
  const serviceMe = (await serviceMeResp.json()) as { id?: number; account_id?: number };
  const serviceId = Number(serviceMe.account_id || serviceMe.id || 0);

  async function fetchPendingForVehicle() {
    const pendingResp = await page.request.get('/api/v1/user/service-requests?status=pending', {
      headers: { ...getE2eHttpHeaders(), Authorization: `Bearer ${userToken}` },
    });
    expect(pendingResp.status()).toBe(200);
    const pendingBody = (await pendingResp.json()) as { requests?: ServiceRequestRow[] };
    return (pendingBody.requests || []).find((row) => Number(row.vehicle_id) === Number(vehicle!.id));
  }

  const existingPending = await fetchPendingForVehicle();
  if (existingPending) {
    return { ...existingPending, lookup_plate: vehicle.plate };
  }

  async function createRequest() {
    return page.request.post('/api/v1/services/access-requests', {
      headers: { ...getE2eHttpHeaders(), Authorization: `Bearer ${serviceToken}` },
      data: { vehicle_id: Number(vehicle!.id), lookup_query: vehicle!.plate, note: 'E2E žádost o propojení' },
    });
  }

  if (serviceId > 0) {
    await page.request.delete(`/api/v1/services/vehicle-access/${serviceId}/${Number(vehicle.id)}`, {
      headers: { ...getE2eHttpHeaders(), Authorization: `Bearer ${userToken}` },
    });
  }

  let createResp = await createRequest();
  if (createResp.status() === 409) {
    const existing = await fetchPendingForVehicle();
    if (existing) return { ...existing, lookup_plate: vehicle.plate };
  }
  expect([200, 409]).toContain(createResp.status());
  if (createResp.status() === 409) {
    throw new Error(`Unable to create service access request: ${await createResp.text()}`);
  }
  const createBody = (await createResp.json()) as { request_id?: number; created?: boolean };
  const requestId = Number(createBody.request_id || 0);
  expect(requestId).toBeGreaterThan(0);
  if (createBody.created === false) {
    const existing = await fetchPendingForVehicle();
    if (existing) return { ...existing, lookup_plate: vehicle.plate };
  }

  const listResp = await page.request.get('/api/v1/user/service-requests?status=pending', {
    headers: { ...getE2eHttpHeaders(), Authorization: `Bearer ${userToken}` },
  });
  expect(listResp.status()).toBe(200);
  const listBody = (await listResp.json()) as { requests?: ServiceRequestRow[] };
  const row = (listBody.requests || []).find((item) => Number(item.request_id) === requestId);
  if (!row) {
    throw new Error(`Pending request ${requestId} not returned by user list endpoint`);
  }
  return { ...row, lookup_plate: vehicle.plate };
}

async function openUserDashboard(page: Parameters<typeof test>[0]['page']) {
  const slugMatch = page.url().match(/\/app\/u\/([^/]+)/);
  const slug = slugMatch?.[1] || 'e2e-user';
  await page.goto(`/web/app/u/${slug}/dashboard`, { waitUntil: 'domcontentloaded' });
  await waitForUserShellReady(page);
}

test.describe('User service request full flow', () => {
  test.describe.configure({ mode: 'serial' });

  test.beforeEach(async ({ page }) => {
    test.skip(!getServiceTestCredentials(), 'Nastavte E2E_SERVICE_EMAIL a E2E_SERVICE_PASSWORD');
    await loginUser(page);
  });

  test('service creates request and user sees it on dashboard vehicle and settings', async ({ page }) => {
    const pending = await createPendingRequestViaApi(page);
    await openUserDashboard(page);
    await expect(page.locator('[data-testid="user-service-requests-dashboard-card"]')).toBeVisible({ timeout: 45_000 });
    const dashboardCard = page.locator('[data-testid="user-service-request-card"]').first();
    await expect(dashboardCard).toContainText(new RegExp(pending.service_name || 'Servis', 'i'));
    await expect(dashboardCard.locator('[data-testid="user-service-request-approve-button"]')).toBeVisible();

    await page.locator(`[data-uapp-action="detail:${pending.vehicle_id}"]`).first().click();
    await expect(page.locator('[data-testid="vehicle-detail-service-requests-section"]')).toBeVisible({ timeout: 30_000 });
    await page.locator('[data-uapp-action="detailClose"]').click({ timeout: 5000 }).catch(() => {});
    await expect(page.locator('[data-testid="user-service-requests-dashboard-card"]')).toBeVisible({ timeout: 15_000 });

    const slugMatch = page.url().match(/\/app\/u\/([^/]+)/);
    const slug = slugMatch?.[1] || 'e2e-user';
    await page.goto(`/web/app/u/${slug}/settings/services-sharing`, { waitUntil: 'domcontentloaded' });
    await waitForUserShellReady(page);
    await expect(page.locator('[data-testid="user-service-requests-section"]')).toBeVisible({ timeout: 45_000 });
    await expect(page.locator('[data-testid="user-service-request-card"]').first()).toBeVisible();
  });

  test('user rejects request service sees rejected and no owner pii', async ({ page }) => {
    const pending = await createPendingRequestViaApi(page);
    await openUserDashboard(page);
    await expect(page.locator('[data-testid="user-service-requests-dashboard-card"]')).toBeVisible({ timeout: 45_000 });
    await Promise.all([
      page.waitForResponse(
        (response) => response.url().includes('/api/v1/services/access-requests/')
          && response.request().method() === 'PUT'
          && response.status() === 200,
        { timeout: 30_000 },
      ),
      page.locator('[data-testid="user-service-request-reject-button"]').first().click(),
    ]);
    await expect(page.locator('[data-testid="user-service-request-rejected-state"]').first()).toBeVisible({ timeout: 30_000 });

    const serviceCreds = getServiceTestCredentials();
    expect(serviceCreds).toBeTruthy();
    const serviceLogin = await page.request.post('/user/login', {
      data: { email: serviceCreds!.email, password: serviceCreds!.password, expected_role: 'service' },
      headers: getE2eHttpHeaders(),
    });
    const serviceToken = String(((await serviceLogin.json()) as { access_token?: string }).access_token || '');
    const lookupResp = await page.request.post('/api/v1/services/vehicle-lookup', {
      headers: { ...getE2eHttpHeaders(), Authorization: `Bearer ${serviceToken}` },
      data: { query: pending.lookup_plate || pending.vehicle_plate_masked || 'UNKNOWN' },
    });
    expect(lookupResp.status()).toBe(200);
    const lookupBody = (await lookupResp.json()) as { owner_data?: unknown; owner_customer_id?: unknown };
    expect(lookupBody.owner_data).toBeFalsy();
    expect(lookupBody.owner_customer_id).toBeFalsy();
  });

  test('user approves request and service sees approved state', async ({ page }) => {
    const pending = await createPendingRequestViaApi(page);
    await openUserDashboard(page);
    await expect(page.locator('[data-testid="user-service-requests-dashboard-card"]')).toBeVisible({ timeout: 45_000 });
    await Promise.all([
      page.waitForResponse(
        (response) => response.url().includes('/api/v1/services/access-requests/')
          && response.request().method() === 'PUT'
          && response.status() === 200,
        { timeout: 30_000 },
      ),
      page.locator('[data-testid="user-service-request-approve-button"]').first().click(),
    ]);
    await expect(page.locator('[data-testid="user-service-request-approved-state"]').first()).toBeVisible({ timeout: 30_000 });

    const serviceCreds = getServiceTestCredentials();
    expect(serviceCreds).toBeTruthy();
    const serviceLogin = await page.request.post('/user/login', {
      data: { email: serviceCreds!.email, password: serviceCreds!.password, expected_role: 'service' },
      headers: getE2eHttpHeaders(),
    });
    expect(serviceLogin.status()).toBe(200);
    const serviceToken = String(((await serviceLogin.json()) as { access_token?: string }).access_token || '');
    const approvedResp = await page.request.get('/api/v1/services/approved-vehicles', {
      headers: { ...getE2eHttpHeaders(), Authorization: `Bearer ${serviceToken}` },
    });
    expect(approvedResp.status()).toBe(200);
    const approvedBody = (await approvedResp.json()) as { items?: Array<{ id?: number }> };
    expect((approvedBody.items || []).some((item) => Number(item.id) === Number(pending.vehicle_id))).toBeTruthy();
  });
});
