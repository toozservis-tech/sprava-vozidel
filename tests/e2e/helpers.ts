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

/**
 * Získat testovací credentials z environment proměnných nebo použít default
 */
export function getTestCredentials(): { email: string; password: string } {
  return {
    email: process.env.E2E_USER_EMAIL || process.env.E2E_EMAIL || 'e2e.user@toozservis.cz',
    password: process.env.E2E_USER_PASSWORD || process.env.E2E_PASSWORD || 'testpass123',
  };
}

/** Servisní účet pro E2E — musí existovat v DB (schválený servisní login). */
export function getServiceTestCredentials(): { email: string; password: string } | null {
  const email = (process.env.E2E_SERVICE_EMAIL || 'e2e.service@toozservis.cz').trim();
  const password = (process.env.E2E_SERVICE_PASSWORD || 'testpass123').trim();
  if (!email || !password) {
    return null;
  }
  return { email, password };
}

/**
 * Zajistí existenci testovacího uživatele.
 * Registrace je idempotentní: pokud uživatel existuje, pokračujeme dál.
 */
export async function ensureTestUser(page: any, email?: string, password?: string): Promise<void> {
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

  const response = await page.request.post('/user/login', {
    data: { email: targetEmail, password: targetPassword },
  });
  if (response.status() === 200) {
    return;
  }

  throw new Error(`Unable to use fixed test user. HTTP ${response.status()}`);
}

/**
 * Přihlásit uživatele v testu
 */
export async function loginUser(page: any, email?: string, password?: string): Promise<void> {
  const credentials = getTestCredentials();
  const targetEmail = email || credentials.email;
  const targetPassword = password || credentials.password;

  await ensureTestUser(page, targetEmail, targetPassword);
  /* Kanonická veřejná cesta: PUBLIC_ROUTE_PATHS.login === '/login' (system.py + stejná SPA jako /web/login). */
  await page.goto('/login', { waitUntil: 'load', timeout: AUTH_PAGE_GOTO_TIMEOUT_MS });
  await waitForAuthLoginFormVisible(page);
  await page.locator('#loginModeUserBtn').click();
  await page.fill('[data-testid="input-email"]', targetEmail);
  await page.fill('[data-testid="input-password"]', targetPassword);
  await page.click('[data-testid="btn-login"]');
  const rateLimitAlert = page.locator('[data-testid="alert-error"]', {
    hasText: 'Příliš mnoho pokusů',
  });
  const serviceRoot = page.locator('[data-service-shell="root"]');
  const userDashboard = page.locator('[data-testid="dashboard"]');
  const deadline = Date.now() + 45_000;
  while (Date.now() < deadline) {
    if (await serviceRoot.isVisible().catch(() => false)) {
      return;
    }
    if (await userDashboard.isVisible().catch(() => false)) {
      return;
    }
    if (await rateLimitAlert.isVisible().catch(() => false)) {
      await page.waitForTimeout(61_000);
      await page.click('[data-testid="btn-login"]');
      await userDashboard.waitFor({ state: 'visible', timeout: 25_000 }).catch(async () => {
        await serviceRoot.waitFor({ state: 'visible', timeout: 25_000 });
      });
      return;
    }
    await page.waitForTimeout(250);
  }
  if (await rateLimitAlert.isVisible().catch(() => false)) {
    await page.waitForTimeout(61_000);
    await page.click('[data-testid="btn-login"]');
    await userDashboard.waitFor({ state: 'visible', timeout: 25_000 }).catch(async () => {
      await serviceRoot.waitFor({ state: 'visible', timeout: 25_000 });
    });
    return;
  }
  throw new Error('loginUser: po přihlášení se nezobrazil dashboard ani servisní shell');
}

/** Přihlášení režimu Servis (stejný login endpoint, předem zvolený typ účtu). */
export async function loginServiceUser(page: any, email?: string, password?: string): Promise<void> {
  const credentials = getServiceTestCredentials();
  if (!credentials) {
    throw new Error('E2E_SERVICE_EMAIL a E2E_SERVICE_PASSWORD nejsou nastavené');
  }
  const targetEmail = email || credentials.email;
  const targetPassword = password || credentials.password;

  await page.context().clearCookies();
  await page.goto('/login', { waitUntil: 'load', timeout: AUTH_PAGE_GOTO_TIMEOUT_MS });
  await waitForAuthLoginFormVisible(page);
  const serviceModeBtn = page.locator('#loginModeServiceBtn');
  await serviceModeBtn.waitFor({ state: 'visible', timeout: 30_000 });
  await serviceModeBtn.click();
  await page.fill('[data-testid="input-email"]', targetEmail);
  await page.fill('[data-testid="input-password"]', targetPassword);
  await page.click('[data-testid="btn-login"]');
  const serviceRoot = page.locator('[data-service-shell="root"]');
  await serviceRoot.waitFor({ state: 'visible', timeout: 30_000 });
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
