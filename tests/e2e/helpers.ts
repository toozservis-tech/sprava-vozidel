/**
 * Helper funkce pro E2E testy
 */

import fs from 'node:fs';
import path from 'node:path';

import type { Page, TestInfo } from '@playwright/test';

/** `index.html` je velký; první načtení může trvat >20 s na slabším I/O. */
const AUTH_PAGE_GOTO_TIMEOUT_MS = Number(process.env.E2E_AUTH_GOTO_TIMEOUT_MS) || 120_000;
const AUTH_FORM_VISIBLE_TIMEOUT_MS = Number(process.env.E2E_AUTH_FORM_TIMEOUT_MS) || 60_000;

/** SPA odmaskuje #authSection až po běhu routeru – čeká víc než attached u prvku. */
export async function waitForAuthLoginFormVisible(page: Page): Promise<void> {
  await page.waitForFunction(
    () => {
      const form = document.querySelector('[data-testid="login-form"]');
      const auth = document.getElementById('authSection');
      if (!form || !auth) {
        return false;
      }
      if (auth.hasAttribute('hidden') || getComputedStyle(auth).display === 'none') {
        return false;
      }
      const r = (form as HTMLElement).getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    },
    null,
    { timeout: AUTH_FORM_VISIBLE_TIMEOUT_MS },
  );
}

/**
 * Získat base URL z environment proměnných nebo použít default
 */
export function getBaseUrl(): string {
  return process.env.BASE_URL || 'http://127.0.0.1:8000';
}

/**
 * Zkontrolovat, zda jsou testy v read-only režimu
 */
export function isReadOnly(): boolean {
  return process.env.E2E_READONLY === '1' || process.env.E2E_READONLY === 'true';
}

export function getTestUserCredentials(): { email: string; password: string } {
  return getTestCredentials();
}

export function getTestCredentials(): { email: string; password: string } {
  return {
    email: process.env.E2E_USER_EMAIL || process.env.E2E_EMAIL || 'e2e.user@toozservis.cz',
    password: process.env.E2E_USER_PASSWORD || process.env.E2E_PASSWORD || 'testpass123',
  };
}

export function getServiceTestCredentials(): { email: string; password: string } | null {
  const email = (process.env.E2E_SERVICE_EMAIL || 'e2e.service@toozservis.cz').trim();
  const password = (process.env.E2E_SERVICE_PASSWORD || 'testpass123').trim();
  if (!email || !password) {
    return null;
  }
  return { email, password };
}

export function getTestServiceCredentials(): { email: string; password: string } | null {
  return getServiceTestCredentials();
}

export function getE2eHttpHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    'x-forwarded-proto': 'https',
  };
  const secret = (process.env.E2E_RATE_LIMIT_BYPASS_SECRET || '').trim();
  if (secret && (process.env.E2E_RATE_LIMIT_BYPASS || '').trim() === '1') {
    headers['x-e2e-rate-limit-bypass'] = secret;
  }
  return headers;
}

type LoginApiResponse = {
  access_token?: string;
  user?: Record<string, unknown>;
};

async function postLogin(
  page: Page,
  email: string,
  password: string,
  expectedRole?: 'user' | 'service',
): Promise<LoginApiResponse> {
  const payload: Record<string, string> = { email, password };
  if (expectedRole) {
    payload.expected_role = expectedRole;
  }
  const response = await page.request.post('/user/login', {
    data: payload,
    headers: getE2eHttpHeaders(),
  });
  if (response.status() === 429) {
    throw new Error('login rate limited (HTTP 429) — enable E2E_RATE_LIMIT_BYPASS for localhost tests');
  }
  if (response.status() !== 200) {
    throw new Error(`Unable to use fixed test user. HTTP ${response.status()}: ${await response.text()}`);
  }
  return (await response.json()) as LoginApiResponse;
}

async function resolveDefaultAppPath(page: Page, accessToken: string): Promise<string> {
  const meResponse = await page.request.get('/api/me', {
    headers: {
      ...getE2eHttpHeaders(),
      Authorization: `Bearer ${accessToken}`,
    },
  });
  if (meResponse.status() !== 200) {
    throw new Error(`/api/me failed with HTTP ${meResponse.status()}`);
  }
  const me = (await meResponse.json()) as {
    default_app_path?: string;
    account_slug?: string;
    workspace_route_kind?: string;
  };
  let path = '';
  if (me.default_app_path) {
    path = me.default_app_path.startsWith('/') ? me.default_app_path : `/${me.default_app_path}`;
  } else {
    const slug = me.account_slug;
    const kind = me.workspace_route_kind === 'service' ? 's' : 'u';
    if (!slug) {
      throw new Error('/api/me did not return default_app_path or account_slug');
    }
    path = `/web/app/${kind}/${slug}/dashboard`;
  }
  if (path.startsWith('/app/')) {
    path = `/web${path}`;
  }
  return path;
}

const E2E_BLOCK_AUTH_SEED_KEY = '__e2e_block_auth_seed';

async function seedBrowserAuthSession(page: Page, loginBody: LoginApiResponse): Promise<void> {
  await page.context().addInitScript((payload) => {
    try {
      if (sessionStorage.getItem('__e2e_block_auth_seed') === '1') {
        return;
      }
    } catch {
      /* ignore */
    }
    const token = String(payload.access_token || '');
    const user = payload.user && typeof payload.user === 'object' ? payload.user : {};
    const w = window as unknown as {
      saveAuthSession?: (t: string, u: Record<string, unknown>, persistent?: boolean) => void;
    };
    if (typeof w.saveAuthSession === 'function') {
      w.saveAuthSession(token, user, true);
      return;
    }
    localStorage.setItem('accessToken', token);
    localStorage.setItem('currentUser', JSON.stringify(user));
    localStorage.setItem('wasLoggedIn', 'true');
  }, loginBody);
}

export async function blockAuthSessionReseed(page: Page): Promise<void> {
  await page.evaluate((key) => {
    sessionStorage.setItem(key, '1');
  }, E2E_BLOCK_AUTH_SEED_KEY);
}

export async function waitForUserShellReady(page: Page, timeoutMs = 45_000): Promise<void> {
  const userShell = page.locator('[data-testid="user-shell-root"], [data-testid="user-app-next-screen"]');
  const legacyDashboard = page.locator('[data-testid="dashboard"]');
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await userShell.first().isVisible().catch(() => false)) {
      return;
    }
    if (await legacyDashboard.isVisible().catch(() => false)) {
      const loading = page.locator('text=Načítám…').first();
      if (!(await loading.isVisible().catch(() => false))) {
        return;
      }
    }
    await page.waitForTimeout(250);
  }
  throw new Error('waitForUserShellReady: user shell se nezobrazil');
}

export async function waitForServiceShellReady(page: Page, timeoutMs = 45_000): Promise<void> {
  const serviceRoot = page.locator('[data-service-shell="root"], [data-testid="service-shell-root"]');
  await serviceRoot.first().waitFor({ state: 'visible', timeout: timeoutMs });
}

export async function clickUserLogout(page: Page): Promise<void> {
  const visibleLegacyLogout = page.locator('[data-testid="btn-logout"]:visible');
  if (await visibleLegacyLogout.count()) {
    await visibleLegacyLogout.first().click();
    return;
  }
  const profileBtn = page
    .locator('[data-testid="dashboard-profile"]:visible')
    .or(page.getByRole('button', { name: 'Profil uživatele' }));
  await profileBtn.first().click();
  const profilePanel = page.getByRole('region', { name: 'Profil a licence' });
  await profilePanel.getByRole('button', { name: 'Odhlásit se' }).click({ timeout: 10_000 });
}

const USER_TAB_LABELS: Record<string, string> = {
  home: 'Přehled',
  vehicles: 'Moje vozidla',
  reminders: 'Připomínky',
  reservations: 'Objednat servis',
  documents: 'Dokumenty',
  settings: 'Nastavení',
};

export async function gotoUserTab(
  page: Page,
  tab: 'home' | 'vehicles' | 'reminders' | 'reservations' | 'documents' | 'settings',
): Promise<void> {
  const stableIds: Record<string, string> = {
    home: 'user-dashboard',
    vehicles: 'user-vehicles-tab',
    reminders: 'user-reminders-tab',
    reservations: 'user-reservations-tab',
    documents: 'user-documents-tab',
    settings: 'user-settings-tab',
  };
  const legacyIds: Record<string, string> = {
    home: 'tab-home',
    vehicles: 'tab-vehicles',
    reminders: 'tab-reminders',
    reservations: 'tab-reservations',
    documents: 'tab-documents',
    settings: 'tab-account',
  };
  const label = USER_TAB_LABELS[tab];
  const uappAction = tab === 'settings' ? 'settings' : tab;
  const uappNav = page.locator(`[data-uapp-action="${uappAction}"]`);
  if ((await uappNav.count()) > 0) {
    await uappNav.first().click({ force: true });
    await page.waitForTimeout(400);
    return;
  }
  const byRole = page
    .getByRole('navigation', { name: 'Sekce aplikace' })
    .getByRole('button', { name: new RegExp(`^${label}`) });
  if (await byRole.first().isVisible().catch(() => false)) {
    await byRole.first().click();
    await page.waitForTimeout(400);
    return;
  }
  const stable = page.locator(`[data-testid="${stableIds[tab]}"]`);
  if (await stable.isVisible().catch(() => false)) {
    await stable.click();
    await page.waitForTimeout(400);
    return;
  }
  await page.evaluate((tabKey) => {
    const w = window as unknown as { switchTab?: (k: string) => void };
    if (typeof w.switchTab === 'function') {
      w.switchTab(tabKey);
    }
  }, tab === 'settings' ? 'account' : tab);
  await page.waitForTimeout(400);
}

export async function ensureTestUser(page: Page, email?: string, password?: string): Promise<void> {
  const credentials = getTestCredentials();
  const targetEmail = email || credentials.email;
  const targetPassword = password || credentials.password;
  const allowed = new Set([
    (process.env.E2E_USER_EMAIL || 'e2e.user@toozservis.cz').toLowerCase(),
    (process.env.E2E_SERVICE_EMAIL || 'e2e.service@toozservis.cz').toLowerCase(),
  ]);
  if (!allowed.has(targetEmail.trim().toLowerCase())) {
    throw new Error('Refusing to create non-allowlisted test account. Use fixed E2E_USER_EMAIL or E2E_SERVICE_EMAIL.');
  }
  await postLogin(page, targetEmail, targetPassword);
}

export async function loginAsUser(page: Page, email?: string, password?: string): Promise<void> {
  return loginUser(page, email, password);
}

export async function loginUser(page: Page, email?: string, password?: string): Promise<void> {
  const credentials = getTestCredentials();
  const targetEmail = email || credentials.email;
  const targetPassword = password || credentials.password;
  const loginBody = await postLogin(page, targetEmail, targetPassword, 'user');
  if (!loginBody.access_token) {
    throw new Error('loginUser: /user/login nevrátil access_token');
  }
  await seedBrowserAuthSession(page, loginBody);
  const appPath = await resolveDefaultAppPath(page, loginBody.access_token);
  await page.goto(appPath, { waitUntil: 'domcontentloaded', timeout: AUTH_PAGE_GOTO_TIMEOUT_MS });
  await waitForUserShellReady(page);
}

export async function loginAsService(page: Page, email?: string, password?: string): Promise<void> {
  return loginServiceUser(page, email, password);
}

export async function loginServiceUser(page: Page, email?: string, password?: string): Promise<void> {
  const credentials = getServiceTestCredentials();
  if (!credentials) {
    throw new Error('E2E_SERVICE_EMAIL a E2E_SERVICE_PASSWORD nejsou nastavené');
  }
  const targetEmail = email || credentials.email;
  const targetPassword = password || credentials.password;
  await page.context().clearCookies();
  const loginBody = await postLogin(page, targetEmail, targetPassword, 'service');
  if (!loginBody.access_token) {
    throw new Error('loginServiceUser: /user/login nevrátil access_token');
  }
  await seedBrowserAuthSession(page, loginBody);
  const appPath = await resolveDefaultAppPath(page, loginBody.access_token);
  await page.goto(appPath, { waitUntil: 'domcontentloaded', timeout: AUTH_PAGE_GOTO_TIMEOUT_MS });
  await waitForServiceShellReady(page);
}

/**
 * Ověřit, že nejsou zobrazeny globální chybové hlášky
 */
export async function assertNoGlobalErrorBanner(page: any): Promise<void> {
  const errorAlerts = page.locator('[data-testid="alert-error"]');
  const count = await errorAlerts.count();
  if (count > 0) {
    const messages = await errorAlerts.allTextContents();
    throw new Error(`Found ${count} error alert(s): ${messages.join(', ')}`);
  }
}

/**
 * Přejít na konkrétní tab
 */
export async function gotoTab(page: any, tabTestId: string): Promise<void> {
  await page.click(`[data-testid="${tabTestId}"]`);
  // Počkat na aktivaci tabu
  await page.waitForTimeout(500);
}

/**
 * Při selhání E2E pro React seznam: připojí stav stránky (URL, flag, DOM, tagy pro assety).
 * Poslední requesty: předávejte pole z createRelevantRequestRing.
 */
export async function attachReactVehicleListFailureDiagnostics(
  page: Page,
  testInfo: TestInfo,
  options: { lastRelevantRequestUrls?: string[]; consoleErrorSamples?: string[] } = {},
): Promise<void> {
  const [title, state] = await Promise.all([
    page.title().catch(() => ''),
    page.evaluate(() => {
      const w = window as unknown as { __ENABLE_REACT_VEHICLE_LIST?: boolean };
      return {
        __ENABLE_REACT_VEHICLE_LIST: w.__ENABLE_REACT_VEHICLE_LIST,
        hasVehiclesContainer: !!document.getElementById('vehiclesContainer'),
        hasReactVehiclesRoot: !!document.getElementById('react-vehicles-root'),
        hasReactListCss: !!document.getElementById('react-vehicle-list-css'),
        hasReactListJs: !!document.getElementById('react-vehicle-list-js'),
      };
    }),
  ]).catch(() => ['', null as unknown as Record<string, unknown>]);

  const body = {
    currentUrl: page.url(),
    title,
    ...((state as object) || {}),
    lastRelevantRequestUrls: options.lastRelevantRequestUrls?.slice(-10) ?? [],
    consoleErrorSamples: options.consoleErrorSamples?.slice(-10) ?? [],
  };

  await testInfo.attach('react-vehicle-list-diagnostics', {
    body: JSON.stringify(body, null, 2),
    contentType: 'application/json',
  });
  // eslint-disable-next-line no-console
  console.error('[E2E react-vehicle-list diagnostics]', body);
}

export type ReactVehicleListAssetNames = {
  buildJs: string;
  buildCss: string;
};

/**
 * Runtime source of truth: `app/web/index.html` (synchronizováno `postbuild` z app/frontend).
 * Nepoužívejte natvrdo index-*.js / index-*.css v E2E.
 */
export function readReactVehicleListAssetNames(): ReactVehicleListAssetNames {
  const indexPath = path.join(__dirname, '../../web/index.html');
  if (!fs.existsSync(indexPath)) {
    throw new Error(`readReactVehicleListAssetNames: soubor neexistuje: ${indexPath}`);
  }
  const raw = fs.readFileSync(indexPath, 'utf8');
  const mJs = raw.match(/var REACT_VEHICLE_LIST_BUILD_JS = '([^']*)';/);
  const mCss = raw.match(/var REACT_VEHICLE_LIST_BUILD_CSS = '([^']*)';/);
  if (!mJs) {
    throw new Error(
      "readReactVehicleListAssetNames: v index.html chybí řádek var REACT_VEHICLE_LIST_BUILD_JS = '…';",
    );
  }
  if (!mCss) {
    throw new Error(
      "readReactVehicleListAssetNames: v index.html chybí řádek var REACT_VEHICLE_LIST_BUILD_CSS = '…';",
    );
  }
  const buildJs = mJs[1].trim();
  const buildCss = mCss[1].trim();
  if (!buildJs || !buildCss) {
    throw new Error(
      `readReactVehicleListAssetNames: prázdné názvy (JS: "${buildJs}", CSS: "${buildCss}")`,
    );
  }
  return { buildJs, buildCss };
}
