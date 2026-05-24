import { expect, type APIRequestContext, type Page } from '@playwright/test';

import { recycleCiEmailsQuiet } from './recycle-ci-emails';

export const betaAdminEmail = process.env.E2E_ADMIN_EMAIL || '';
export const betaAdminPassword = process.env.E2E_ADMIN_PASSWORD || '';

export type BetaE2eUser = {
  email: string;
  password: string;
  phone: string;
  userId: number;
  token: string;
};

type AdminSession = {
  token: string;
  role: string;
};

let cachedAdminSession: AdminSession | null = null;

function digitsOnly(value: number): string {
  return String(value).replace(/\D/g, '');
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
}

export function hasBetaAdminCredentials(): boolean {
  return Boolean(betaAdminEmail && betaAdminPassword);
}

export function buildUniqueEmail(prefix: string): string {
  const suffix = `${Date.now()}${Math.floor(Math.random() * 1000)}`;
  return `${prefix}.${suffix}@example.com`;
}

function betaStableEmail(prefix: string): string {
  const slug = prefix.replace(/[^a-z0-9._-]+/gi, '-').replace(/^-+|-+$/g, '').toLowerCase() || 'user';
  return `e2e.beta.${slug}@example.com`;
}

export function betaStablePhone(prefix: string): string {
  let h = 0;
  for (let i = 0; i < prefix.length; i += 1) {
    h = (h * 31 + prefix.charCodeAt(i)) >>> 0;
  }
  const tail = String(h % 100000000).padStart(8, '0');
  return `+4207${tail}`;
}

function useUniqueBetaUsers(): boolean {
  return process.env.E2E_BETA_UNIQUE_USERS === '1' || process.env.E2E_BETA_UNIQUE_USERS === 'true';
}

export function buildUniquePhone(seed = Date.now()): string {
  const tail = digitsOnly(seed).slice(-8).padStart(8, '0');
  return `+4207${tail}`;
}

async function responseJson(response: { json(): Promise<unknown> }): Promise<Record<string, unknown>> {
  const parsed = await response.json().catch(() => ({}));
  return parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : {};
}

export async function registerBetaE2eUser(
  request: APIRequestContext,
  prefix: string,
): Promise<BetaE2eUser> {
  const uniqueUsers = useUniqueBetaUsers();
  const email = uniqueUsers ? buildUniqueEmail(prefix) : betaStableEmail(prefix);
  const password = uniqueUsers
    ? `E2e!${Date.now()}`
    : (process.env.E2E_BETA_FIXED_PASSWORD || 'E2eBetaSmoke123!');
  const phone = uniqueUsers ? buildUniquePhone() : betaStablePhone(prefix);
  if (!uniqueUsers) {
    recycleCiEmailsQuiet([email]);
  }
  const response = await request.post('/user/register', {
    data: {
      email,
      password,
      name: `Beta ${prefix}`,
      phone,
    },
  });
  const payload = await responseJson(response);
  const user = asRecord(payload.user);

  expect(response.ok(), `Registrace E2E uživatele selhala: ${JSON.stringify(payload)}`).toBeTruthy();
  expect(typeof payload.access_token).toBe('string');
  expect(Number(user.id || 0)).toBeGreaterThan(0);

  return {
    email,
    password,
    phone,
    userId: Number(user.id || 0),
    token: String(payload.access_token || ''),
  };
}

export async function createVehicleForUser(
  request: APIRequestContext,
  token: string,
  label: string,
): Promise<number> {
  const stamp = Date.now();
  const response = await request.post('/api/v1/vehicles', {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      nickname: label,
      plate: `BTA${String(stamp).slice(-4)}`,
      brand: 'Skoda',
      model: 'Octavia',
      year: 2023,
      stk_valid_until: '2030-12-31',
    },
  });
  const payload = await responseJson(response);

  expect(response.ok(), `Vytvoření vozidla selhalo: ${JSON.stringify(payload)}`).toBeTruthy();
  expect(Number(payload.id || 0)).toBeGreaterThan(0);
  return Number(payload.id || 0);
}

export async function submitPublicBetaApplication(
  request: APIRequestContext,
  payload: {
    name: string;
    email: string;
    phone: string;
    applicantType: 'user' | 'service' | 'company';
    vehicleCount: number;
    note: string;
  },
): Promise<number> {
  const response = await request.post('/beta/applications', {
    data: {
      name: payload.name,
      email: payload.email,
      phone: payload.phone,
      applicant_type: payload.applicantType,
      vehicle_count: payload.vehicleCount,
      note: payload.note,
      gdpr_consent: true,
    },
  });
  const body = await responseJson(response);
  const application = asRecord(body.application);

  expect(response.ok(), `Beta přihláška selhala: ${JSON.stringify(body)}`).toBeTruthy();
  expect(Number(application.id || 0)).toBeGreaterThan(0);
  return Number(application.id || 0);
}

export async function loginDeveloperAdminApi(request: APIRequestContext): Promise<AdminSession> {
  if (!hasBetaAdminCredentials()) {
    throw new Error('Chybí E2E_ADMIN_EMAIL nebo E2E_ADMIN_PASSWORD.');
  }

  if (cachedAdminSession?.token) {
    const meResponse = await request.get('/admin-api/users', {
      headers: { Authorization: `Bearer ${cachedAdminSession.token}` },
    });
    if (meResponse.ok()) {
      return cachedAdminSession;
    }
    cachedAdminSession = null;
  }

  let lastError = 'unknown';
  for (let attempt = 0; attempt < 5; attempt += 1) {
    const response = await request.post('/user/login', {
      data: {
        email: betaAdminEmail,
        password: betaAdminPassword,
      },
    });
    const payload = await responseJson(response);
    const user = asRecord(payload.user);
    if (response.ok()) {
      const token = String(payload.access_token || '');
      const role = String(user.role || 'developer_admin');
      expect(token.length, `Admin login API nevrátil token: ${JSON.stringify(payload)}`).toBeGreaterThan(10);
      cachedAdminSession = { token, role };
      return cachedAdminSession;
    }

    lastError = typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload);
    if (response.status() !== 429) {
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 15_000));
  }

  throw new Error(`Admin login API selhal: ${lastError}`);
}

export async function adminApiRequest(
  request: APIRequestContext,
  method: 'GET' | 'POST',
  path: string,
  payload?: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const session = await loginDeveloperAdminApi(request);
  const response = method === 'GET'
    ? await request.get(path, {
        headers: { Authorization: `Bearer ${session.token}` },
      })
    : await request.post(path, {
        headers: { Authorization: `Bearer ${session.token}` },
        data: payload || {},
      });
  const body = await responseJson(response);
  expect(response.ok(), `Admin API ${method} ${path} selhalo: ${JSON.stringify(body)}`).toBeTruthy();
  return body;
}

export async function approveBetaApplicationAsAdmin(
  request: APIRequestContext,
  applicationId: number,
  payload?: Record<string, unknown>,
): Promise<number> {
  const body = await adminApiRequest(
    request,
    'POST',
    `/admin-api/beta/applications/${applicationId}/approve`,
    {
      approval_note: 'E2E schválení beta účastníka.',
      decision_reason: 'E2E ověření approved portal flow.',
      ...(payload || {}),
    },
  );
  expect(Number(body.participant_id || 0)).toBeGreaterThan(0);
  return Number(body.participant_id || 0);
}

export async function openDeveloperAdmin(page: Page, request: APIRequestContext): Promise<void> {
  const session = await loginDeveloperAdminApi(request);
  await page.goto('/web_admin/index.html');
  await expect(page.locator('#login-form')).toBeVisible({ timeout: 15_000 });
  await page.evaluate(({ token, role }) => {
    localStorage.setItem('adminAccessToken', token);
    localStorage.setItem('adminRole', role);
  }, { token: session.token, role: session.role });
  await page.reload();
  await expect(page.locator('#dashboard-screen')).toBeVisible({ timeout: 20_000 });
}

export async function loginRegularUserViaUi(page: Page, email: string, password: string): Promise<void> {
  await page.goto('/web/index.html');
  await expect(page.locator('[data-testid="input-email"]')).toBeVisible({ timeout: 20_000 });
  await page.fill('[data-testid="input-email"]', email);
  await page.fill('[data-testid="input-password"]', password);
  await page.click('[data-testid="btn-login"]');
  await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 20_000 });
}

export async function assertNoHorizontalOverflow(page: Page, label: string): Promise<void> {
  const overflowX = await page.evaluate(() => Math.max(0, document.documentElement.scrollWidth - window.innerWidth));
  expect(overflowX, `Horizontal overflow on ${label}`).toBeLessThanOrEqual(2);
}
