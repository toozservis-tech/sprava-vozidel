import { test, expect } from '@playwright/test';
import { getServiceTestCredentials, getTestCredentials, loginServiceUser, loginUser } from './helpers';

test.use({
  extraHTTPHeaders: {
    'x-forwarded-proto': 'https',
  },
});

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
    await page.goto('/web/login');
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
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('[data-testid="tab-vehicles"]')).toBeVisible();
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
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 15_000 });
    const logoutBtn = page.locator('[data-testid="btn-logout"]');
    if (!(await logoutBtn.isVisible().catch(() => false))) {
      const mobileMenuToggle = page.locator('#mobileMenuToggle');
      if (await mobileMenuToggle.isVisible().catch(() => false)) {
        await mobileMenuToggle.click();
      }
    }
    await expect(logoutBtn).toBeVisible({ timeout: 15_000 });
    await logoutBtn.click();
    await expect(page.locator('[data-testid="login-form"]')).toBeVisible({ timeout: 10_000 });
  });

  test('workspace URL after login and vehicles navigation', async ({ page }) => {
    await loginUser(page);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 20_000 });
    await expect(page).toHaveURL(/\/(web\/)?app\/u\/[^/]+\/dashboard/);
    await expect(page.locator('[data-testid="workspace-context-badge"]')).toBeVisible();
    await page.click('[data-testid="tab-vehicles"]');
    await expect(page).toHaveURL(/\/(web\/)?app\/u\/[^/]+\/vehicles/);
  });

  test('workspace URL survives reload on vehicles', async ({ page }) => {
    await loginUser(page);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 20_000 });
    await page.click('[data-testid="tab-vehicles"]');
    const url = page.url();
    await page.reload();
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 25_000 });
    await expect(page).toHaveURL(url);
  });

  test('logout restores login URL', async ({ page }) => {
    await loginUser(page);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 20_000 });
    const logoutBtn = page.locator('[data-testid="btn-logout"]');
    if (!(await logoutBtn.isVisible().catch(() => false))) {
      const mobileMenuToggle = page.locator('#mobileMenuToggle');
      if (await mobileMenuToggle.isVisible().catch(() => false)) {
        await mobileMenuToggle.click();
      }
    }
    await logoutBtn.click();
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
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 20_000 });
    await expect(page).toHaveURL(/\/(web\/)?app\/u\/[^/]+\/dashboard/);

    await page.click('[data-testid="tab-vehicles"]');
    await expect(page).toHaveURL(/\/(web\/)?app\/u\/[^/]+\/vehicles/, { timeout: 15_000 });
    await page.click('[data-testid="tab-reminders"]');
    await expect(page).toHaveURL(/\/(web\/)?app\/u\/[^/]+\/reminders/);
    await page.click('[data-testid="tab-reservations"]');
    await expect(page).toHaveURL(/\/(web\/)?app\/u\/[^/]+\/reservations/);
    await page.click('[data-testid="tab-documents"]');
    await expect(page).toHaveURL(/\/(web\/)?app\/u\/[^/]+\/documents/);
    await page.click('[data-testid="tab-account"]');
    await expect(page).toHaveURL(/\/(web\/)?app\/u\/[^/]+\/settings/);
  });

  test('user wrong slug in URL is corrected to own workspace', async ({ page }) => {
    await loginUser(page);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 20_000 });
    const href = page.url();
    const m = href.match(/\/app\/u\/([^/]+)\//);
    expect(m, 'expected workspace slug in URL').toBeTruthy();
    const ownSlug = m![1];
    await page.goto(`/web/app/u/cizi-jiny-slug-neplatny/vehicles`);
    await expect(page).toHaveURL(new RegExp(`/app/u/${ownSlug}/(vehicles|dashboard)`), { timeout: 25_000 });
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 25_000 });
  });

  test('user history back restores previous tab URL', async ({ page }) => {
    await loginUser(page);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 20_000 });
    await page.click('[data-testid="tab-vehicles"]');
    await expect(page).toHaveURL(/\/(web\/)?app\/u\/[^/]+\/vehicles/);
    await page.click('[data-testid="tab-reminders"]');
    await expect(page).toHaveURL(/\/(web\/)?app\/u\/[^/]+\/reminders/);
    await page.goBack();
    await expect(page).toHaveURL(/\/(web\/)?app\/u\/[^/]+\/vehicles/, { timeout: 15_000 });
  });

  test('invalid stored JWT after reload shows login (no fake private state)', async ({ page }) => {
    await loginUser(page);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 20_000 });
    await page.evaluate(() => {
      try {
        localStorage.setItem('accessToken', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.invalid-signature');
        sessionStorage.removeItem('accessToken');
      } catch {
        /* ignore */
      }
    });
    await page.reload();
    await expect(page.locator('[data-testid="login-form"]')).toBeVisible({ timeout: 25_000 });
    await expect(page.locator('[data-testid="dashboard"]')).not.toBeVisible();
  });

  test('after logout, browser Back must not show authenticated dashboard', async ({ page }) => {
    await loginUser(page);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 20_000 });
    const logoutBtn = page.locator('[data-testid="btn-logout"]');
    if (!(await logoutBtn.isVisible().catch(() => false))) {
      const mobileMenuToggle = page.locator('#mobileMenuToggle');
      if (await mobileMenuToggle.isVisible().catch(() => false)) {
        await mobileMenuToggle.click();
      }
    }
    await logoutBtn.click();
    await expect(page.locator('[data-testid="login-form"]')).toBeVisible({ timeout: 15_000 });
    await page.goBack();
    if (page.url() !== 'about:blank') {
      await expect(page.locator('[data-testid="login-form"]')).toBeVisible({ timeout: 15_000 });
    }
    await expect(page.locator('[data-testid="dashboard"]')).not.toBeVisible();
  });
});

test.describe('Service workspace E2E', () => {
  const serviceRoot = '[data-service-shell="root"]';

  test.beforeEach(async ({ page }) => {
    test.skip(!getServiceTestCredentials(), 'Nastavte E2E_SERVICE_EMAIL a E2E_SERVICE_PASSWORD pro servisní E2E');
    await page.goto('/web/login');
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
    const m = href.match(/\/app\/s\/([^/]+)\//);
    expect(m).toBeTruthy();
    const slug = m![1];
    await page.goto(`/web/app/u/${slug}/dashboard`);
    await expect(page).toHaveURL(/\/(web\/)?app\/s\/[^/]+\/dashboard/, { timeout: 25_000 });
  });

  test('service wrong foreign slug is corrected', async ({ page }) => {
    await loginServiceUser(page);
    await expect(page.locator(serviceRoot)).toBeVisible({ timeout: 25_000 });
    const href = page.url();
    const m = href.match(/\/app\/s\/([^/]+)\//);
    expect(m).toBeTruthy();
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
