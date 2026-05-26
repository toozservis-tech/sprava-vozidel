import { test, expect } from '@playwright/test';
import {
  blockAuthSessionReseed,
  clickUserLogout,
  getServiceTestCredentials,
  getTestCredentials,
  gotoUserTab,
  loginAsService,
  loginAsUser,
  loginServiceUser,
  loginUser,
  waitForAuthLoginFormVisible,
  waitForServiceShellReady,
  waitForUserShellReady,
} from './helpers';

test.describe('Public/Auth redesign smoke', () => {
  test('public landing is visible when logged out', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('#product-sections')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('#publicHeroTitle')).toContainText('Mějte všechna vozidla');
    await expect(page.locator('#authSection')).not.toBeVisible();
    await expect(page.locator('#app-shell')).not.toBeVisible();
  });

  test('login CTA opens existing login view', async ({ page }) => {
    await page.goto('/');
    await page.locator('.public-site-actions button', { hasText: 'Přihlásit se' }).click();
    await expect(page.locator('#loginForm')).toBeVisible({ timeout: 10_000 });
    await expect(page).toHaveURL(/\/(web\/)?login/);
  });

  test('register CTA opens existing register view and account type switch works', async ({ page }) => {
    await page.goto('/');
    await page.locator('.public-site-actions button', { hasText: 'Vyzkoušet zdarma' }).click();
    await expect(page.locator('#registerForm')).toBeVisible({ timeout: 10_000 });
    await expect(page).toHaveURL(/\/(web\/)?register/);
    await page.locator('#registerModeServiceBtn').click();
    await expect(page.locator('#serviceRegistrationExtraFields')).toBeVisible();
    await expect(page.locator('#registerModeServiceBtn')).toHaveClass(/active/);
  });

  test('mobile public landing has no horizontal overflow', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/');
    await expect(page.locator('#publicHeroTitle')).toBeVisible({ timeout: 15_000 });
    const overflow = await page.evaluate(() => ({
      html: document.documentElement.scrollWidth,
      body: document.body.scrollWidth,
      inner: window.innerWidth,
    }));
    expect(overflow.html).toBeLessThanOrEqual(overflow.inner + 2);
    expect(overflow.body).toBeLessThanOrEqual(overflow.inner + 2);
  });
});

test.describe('Auth Smoke', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/web/login', { waitUntil: 'domcontentloaded', timeout: 60_000 });
  });

  test('deep link /web/app/... returns HTML shell (SPA fallback, no JSON 404)', async ({ page }) => {
    const res = await page.request.get('/web/app/u/workspace-slug-placeholder/dashboard');
    expect(res.status()).toBe(200);
    const ct = (res.headers()['content-type'] || '').toLowerCase();
    expect(ct).toContain('text/html');
    const text = await res.text();
    expect(text.toLowerCase()).toContain('<html');
  });

  test('[SEC-CRIT-001] file browser routes are blocked when unauthenticated', async ({ page }) => {
    const protectedRoutes = [
      '/files/',
      '/files/api/list',
      '/files/view?path=README.md',
      '/files/download?path=README.md',
    ];

    for (const route of protectedRoutes) {
      const response = await page.request.get(route);
      expect([401, 403, 404], `Unexpected status for ${route}`).toContain(response.status());
    }
  });

  test('login with valid user', async ({ page }) => {
    await loginUser(page);
    await waitForUserShellReady(page);
    await expect(page.locator('[data-testid="dashboard"], [data-testid="user-shell-root"]')).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByRole('navigation', { name: 'Sekce aplikace' }).getByRole('button', { name: 'Moje vozidla' }),
    ).toBeVisible({ timeout: 20_000 });
  });

  test('invalid login shows proper error', async ({ page }) => {
    const credentials = getTestCredentials();
    await page.fill('[data-testid="input-email"]', credentials.email);
    await page.fill('[data-testid="input-password"]', 'incorrect-password');
    await page.click('[data-testid="btn-login"]');
    await expect(page.locator('[data-testid="alert-error"]')).toBeVisible({ timeout: 10_000 });
  });

  test('logout path works', async ({ page }) => {
    await loginUser(page);
    await waitForUserShellReady(page);
    await clickUserLogout(page);
    await expect(page.locator('[data-testid="login-form"]')).toBeVisible({ timeout: 10_000 });
  });

  test('workspace URL after login and vehicles navigation', async ({ page }) => {
    await loginUser(page);
    await waitForUserShellReady(page);
    await expect(page).toHaveURL(/\/(web\/)?app\/u\/[^/]+\/dashboard/);
    await gotoUserTab(page, 'vehicles');
    await expect(page).toHaveURL(/\/(web\/)?app\/u\/[^/]+\/vehicles/);
  });

  test('workspace URL survives reload on vehicles', async ({ page }) => {
    await loginUser(page);
    await waitForUserShellReady(page);
    await gotoUserTab(page, 'vehicles');
    const url = page.url();
    await page.reload();
    await waitForUserShellReady(page);
    await expect(page).toHaveURL(url);
  });

  test('logout restores login URL', async ({ page }) => {
    await loginUser(page);
    await waitForUserShellReady(page);
    await clickUserLogout(page);
    await expect(page.locator('[data-testid="login-form"]')).toBeVisible({ timeout: 15_000 });
    await expect(page).toHaveURL(/\/(web\/)?login/);
  });

  test('guest hitting deep workspace URL is sent to login (no private shell)', async ({ page }) => {
    await page.goto('/web/app/u/cizi-neexistujici-slug-e2e/dashboard');
    await expect(page.locator('[data-testid="login-form"]')).toBeVisible({ timeout: 20_000 });
    await expect(page).toHaveURL(/\/(web\/)?login/);
    await expect(page.locator('[data-testid="dashboard"]')).not.toBeVisible();
  });

  test('guest hitting /web/app/s/... deep link is sent to login', async ({ page }) => {
    await page.goto('/web/app/s/cizi-servis-slug-e2e/dashboard');
    await expect(page.locator('[data-testid="login-form"]')).toBeVisible({ timeout: 20_000 });
    await expect(page).toHaveURL(/\/(web\/)?login/);
  });

  test('user multi-tab navigation updates URL (dashboard → … → settings)', async ({ page }) => {
    await loginUser(page);
    await waitForUserShellReady(page);
    await expect(page).toHaveURL(/\/(web\/)?app\/u\/[^/]+\/dashboard/);

    await gotoUserTab(page, 'vehicles');
    await expect(page).toHaveURL(/\/(web\/)?app\/u\/[^/]+\/vehicles/, { timeout: 15_000 });
    await gotoUserTab(page, 'reminders');
    await expect(page).toHaveURL(/\/(web\/)?app\/u\/[^/]+\/reminders/);
    await gotoUserTab(page, 'reservations');
    await expect(page).toHaveURL(/\/(web\/)?app\/u\/[^/]+\/reservations/);
    await gotoUserTab(page, 'documents');
    await expect(page).toHaveURL(/\/(web\/)?app\/u\/[^/]+\/documents/);
    await gotoUserTab(page, 'settings');
    await expect(page).toHaveURL(/\/(web\/)?app\/u\/[^/]+\/settings/);
  });

  test('user wrong slug in URL is corrected to own workspace', async ({ page }) => {
    await loginUser(page);
    await waitForUserShellReady(page);
    const href = page.url();
    const m = href.match(/\/app\/u\/([^/]+)(?:\/|$)/);
    expect(m, 'expected workspace slug in URL').toBeTruthy();
    const ownSlug = m![1];
    await page.goto(`/web/app/u/cizi-jiny-slug-neplatny/vehicles`);
    await expect(page).toHaveURL(new RegExp(`/app/u/${ownSlug}/(vehicles|dashboard)`), { timeout: 25_000 });
    await waitForUserShellReady(page);
  });

  test('user history back restores previous tab URL', async ({ page }) => {
    await loginUser(page);
    await waitForUserShellReady(page);
    await gotoUserTab(page, 'vehicles');
    await expect(page).toHaveURL(/\/(web\/)?app\/u\/[^/]+\/vehicles/);
    await gotoUserTab(page, 'reminders');
    await expect(page).toHaveURL(/\/(web\/)?app\/u\/[^/]+\/reminders/);
    await page.goBack();
    await expect(page).toHaveURL(/\/(web\/)?app\/u\/[^/]+\/vehicles/, { timeout: 15_000 });
  });

  test('invalid stored JWT after reload shows login (no fake private state)', async ({ page }) => {
    await loginUser(page);
    await waitForUserShellReady(page);
    await blockAuthSessionReseed(page);
    await page.evaluate(() => {
      try {
        localStorage.setItem('accessToken', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.invalid-signature');
        sessionStorage.removeItem('accessToken');
      } catch {
        /* ignore */
      }
    });
    await page.reload({ waitUntil: 'domcontentloaded' });
    await waitForAuthLoginFormVisible(page);
    await expect(page.locator('[data-testid="dashboard"], [data-testid="user-shell-root"]')).not.toBeVisible();
  });

  test('after logout, browser Back must not show authenticated dashboard', async ({ page }) => {
    await loginUser(page);
    await waitForUserShellReady(page);
    await clickUserLogout(page);
    await waitForAuthLoginFormVisible(page);
    await blockAuthSessionReseed(page);
    await page.goBack();
    await waitForAuthLoginFormVisible(page);
    await expect(page.locator('[data-testid="dashboard"], [data-testid="user-shell-root"]')).not.toBeVisible();
  });
});

test.describe('Service workspace E2E', () => {
  const serviceRoot = '[data-service-shell="root"]';

  test.beforeEach(async ({ page }) => {
    test.skip(!getServiceTestCredentials(), 'Nastavte E2E_SERVICE_EMAIL a E2E_SERVICE_PASSWORD pro servisní E2E');
    await page.goto('/web/login', { waitUntil: 'domcontentloaded', timeout: 60_000 });
  });

  test('service login lands on /app/s/{slug}/dashboard', async ({ page }) => {
    await loginServiceUser(page);
    await expect(page.locator(serviceRoot)).toBeVisible({ timeout: 25_000 });
    await expect(page).toHaveURL(/\/(web\/)?app\/s\/[^/]+\/[^/]+/);
  });

  test('service navigation clients → work-orders and URL', async ({ page }) => {
    await loginServiceUser(page);
    await expect(page.locator(serviceRoot)).toBeVisible({ timeout: 25_000 });
    await page.waitForTimeout(500);
    await page.evaluate(() => {
      const w = window as unknown as { serviceShell?: { navigate?: (s: string) => void } };
      w.serviceShell?.navigate?.('dashboard');
    });
    await expect(page).toHaveURL(/\/(web\/)?app\/s\/[^/]+\/dashboard/, { timeout: 20_000 });
    await page.evaluate(() => {
      const w = window as unknown as { serviceShell?: { navigate?: (s: string) => void } };
      w.serviceShell?.navigate?.('clients');
    });
    await expect(page).toHaveURL(/\/(web\/)?app\/s\/[^/]+\/clients/, { timeout: 20_000 });
    await page.evaluate(() => {
      const w = window as unknown as { serviceShell?: { navigate?: (s: string) => void } };
      w.serviceShell?.navigate?.('work-orders');
    });
    await expect(page).toHaveURL(/\/(web\/)?app\/s\/[^/]+\/work-orders/);
  });

  test('service reload preserves work-orders section', async ({ page }) => {
    await loginServiceUser(page);
    await expect(page.locator(serviceRoot)).toBeVisible({ timeout: 25_000 });
    await page.evaluate(() => {
      (window as unknown as { serviceShell?: { navigate?: (s: string) => void } }).serviceShell?.navigate?.('work-orders');
    });
    await expect(page).toHaveURL(/\/(web\/)?app\/s\/[^/]+\/work-orders/);
    const url = page.url();
    await page.reload();
    await expect(page.locator(serviceRoot)).toBeVisible({ timeout: 30_000 });
    await expect(page).toHaveURL(url, { timeout: 20_000 });
  });

  test('service account on /app/u/... is redirected to /app/s/...', async ({ page }) => {
    await loginServiceUser(page);
    await expect(page.locator(serviceRoot)).toBeVisible({ timeout: 25_000 });
    const href = page.url();
    const m = href.match(/\/app\/s\/([^/]+)(?:\/|$)/);
    expect(m).toBeTruthy();
    const slug = m![1];
    await page.goto(`/web/app/u/${slug}/dashboard`);
    await expect(page).toHaveURL(/\/(web\/)?app\/s\/[^/]+\/dashboard/, { timeout: 25_000 });
  });

  test('service wrong foreign slug is corrected', async ({ page }) => {
    await loginServiceUser(page);
    await waitForServiceShellReady(page);
    const href = page.url();
    const m = href.match(/\/app\/s\/([^/]+)(?:\/|$)/);
    expect(m, 'expected workspace slug in URL').toBeTruthy();
    const ownSlug = m![1];
    await page.goto(`/web/app/s/cizi-cizi-servis/documents`);
    await expect(page).toHaveURL(new RegExp(`/app/s/${ownSlug}/(documents|dashboard)`), { timeout: 25_000 });
  });

  test('service logout returns to login', async ({ page }) => {
    await loginServiceUser(page);
    await expect(page.locator(serviceRoot)).toBeVisible({ timeout: 25_000 });
    await page.evaluate(() => {
      const w = window as unknown as { serviceShell?: { logout?: () => void } };
      w.serviceShell?.logout?.();
    });
    await expect(page.locator('[data-testid="login-form"]')).toBeVisible({ timeout: 15_000 });
    await expect(page).toHaveURL(/\/(web\/)?login/);
  });
});

test.describe('Central identity E2E (auth gate)', () => {
  test('auth_user_login_and_f5_keeps_session', async ({ page }) => {
    await loginAsUser(page);
    await waitForUserShellReady(page);
    await page.reload();
    await waitForUserShellReady(page);
    await expect(page.locator('[data-testid="dashboard"], [data-testid="user-shell-root"]')).toBeVisible({ timeout: 25_000 });
    await expect(page.locator('[data-testid="login-form"]')).not.toBeVisible();
  });

  test('auth_service_login_and_f5_keeps_session', async ({ page }) => {
    test.skip(!getServiceTestCredentials(), 'Nastavte E2E_SERVICE_EMAIL a E2E_SERVICE_PASSWORD');
    await loginAsService(page);
    await waitForServiceShellReady(page);
    await page.reload();
    await waitForServiceShellReady(page);
    await expect(page.locator('[data-service-shell="root"]')).toBeVisible({ timeout: 25_000 });
    await expect(page.locator('[data-testid="login-form"]')).not.toBeVisible();
  });

  test('user_existing_vehicles_visible_after_central_identity', async ({ page }) => {
    await loginUser(page);
    await waitForUserShellReady(page);
    await expect(page.getByRole('heading', { name: 'Moje vozidla', level: 2 })).toBeVisible({
      timeout: 25_000,
    });
    const vehicleCards = page.locator(
      '.uapp-next-vehicle-card[data-uapp-vehicle-card], .uapp-next-garage-card[data-uapp-vehicle-card]',
    );
    await expect(vehicleCards.first()).toBeVisible({ timeout: 25_000 });
  });

  test('service_lookup_existing_vehicle_safe_preview_e2e', async ({ page }) => {
    test.skip(!getServiceTestCredentials(), 'Nastavte E2E_SERVICE_EMAIL a E2E_SERVICE_PASSWORD');
    await loginServiceUser(page);
    await waitForServiceShellReady(page);
    await page.evaluate(() => {
      (window as unknown as { serviceShell?: { openServiceToolsModal?: () => void } }).serviceShell?.openServiceToolsModal?.();
    });
    const intakeSection = page.locator('[data-testid="service-intake-section"]');
    const lookupInput = intakeSection.locator('[data-testid="service-vehicle-lookup-input"]');
    await lookupInput.waitFor({ state: 'visible', timeout: 20_000 });
    await lookupInput.fill('TEST209E');
    await lookupInput.dispatchEvent('input');
    await intakeSection.getByRole('button', { name: 'Hledat vozidlo' }).click();
    const resultRow = intakeSection.locator('.service-shell-list-row').first();
    await expect(resultRow).toBeVisible({ timeout: 25_000 });
    const rowText = await resultRow.innerText();
    expect(rowText.toLowerCase()).not.toMatch(/faktur|invoice|@|telefon|tel\.|cena|kč|eur/);
    expect(rowText).toMatch(/•/);
  });

  test('service_create_unowned_vehicle_e2e', async ({ page }) => {
    test.skip(!getServiceTestCredentials(), 'Nastavte E2E_SERVICE_EMAIL a E2E_SERVICE_PASSWORD');
    test.skip(process.env.E2E_ALLOW_MUTATIONS !== '1', 'Založení nepřiřazeného vozidla vyžaduje E2E_ALLOW_MUTATIONS=1');
    const uniqueVin = `TMBE2E${Date.now().toString(36).toUpperCase().slice(-9).padStart(9, '0')}`.slice(0, 17);
    await loginServiceUser(page);
    await waitForServiceShellReady(page);
    await page.evaluate(() => {
      (window as unknown as { serviceShell?: { openServiceToolsModal?: () => void } }).serviceShell?.openServiceToolsModal?.();
    });
    const lookupInput = page.locator('[data-testid="service-vehicle-lookup-input"]');
    await lookupInput.waitFor({ state: 'visible', timeout: 20_000 });
    await lookupInput.fill(uniqueVin);
    await page.locator('button:has-text("Hledat vozidlo")').click();
    const createBtn = page.locator('button:has-text("Založit nepřiřazené vozidlo")');
    await expect(createBtn).toBeVisible({ timeout: 25_000 });
    await createBtn.click();
    await expect(page.locator('.service-shell-modal, .service-shell-empty, .service-shell-list-row').first()).toBeVisible({
      timeout: 25_000,
    });
  });
});
