import { expect, test } from '@playwright/test';

import {
  getServiceTestCredentials,
  getTestServiceCredentials,
  loginServiceUser,
  waitForServiceShellReady,
} from './helpers';

const SERVICE_SECTION_ROUTES = [
  { path: 'dashboard', navTestId: 'service-nav-dashboard', body: /Servisní přehled/i },
  { path: 'intake', navTestId: 'service-nav-intake', body: /Příjem vozidla/i },
  { path: 'work-orders', navTestId: 'service-nav-work-orders', body: /Zakázky/i },
  { path: 'vehicles', navTestId: 'service-nav-vehicles', body: /Vozidla zákazníků/i },
  { path: 'customers', navTestId: 'service-nav-clients', body: /Zákaznické centrum|Zákazníci/i },
  { path: 'photos', navTestId: 'service-nav-photos', body: /Fotodokumentace/i, limited: true },
  { path: 'history', navTestId: 'service-nav-history', body: /Servisní historie/i, limited: true },
  { path: 'billing', navTestId: 'service-nav-invoices', body: /Faktury|Nabídky/i },
  { path: 'parts-stock', navTestId: 'service-nav-parts', body: /Sklad dílů/i, limited: true },
  { path: 'reservations', navTestId: 'service-nav-reservations', body: /Rezervace/i },
  { path: 'team', navTestId: 'service-nav-team', body: /Tým/i },
  { path: 'audit-security', navTestId: 'service-nav-audit', body: /Audit a bezpečnost/i, limited: true },
  {
    path: 'settings',
    navTestId: 'service-nav-settings',
    body: /Nastavení servisu/i,
    limited: true,
    notTeamOnly: true,
  },
] as const;

test.describe('Service shell navigation (phase 2)', () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!getServiceTestCredentials(), 'Nastavte E2E_SERVICE_EMAIL a E2E_SERVICE_PASSWORD');
    await loginServiceUser(page);
    await waitForServiceShellReady(page);
  });

  test('service_navigation_all_sections_load', async ({ page }) => {
    const credentials = getTestServiceCredentials();
    expect(credentials).toBeTruthy();
    const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
    const slug = slugMatch?.[1] || 'e2e-fixed-service';

    for (const route of SERVICE_SECTION_ROUTES) {
      await page.goto(`/web/app/s/${slug}/${route.path}`, { waitUntil: 'domcontentloaded' });
      await waitForServiceShellReady(page);
      await expect(page).toHaveURL(new RegExp(`/app/s/[^/]+/${route.path.replace(/-/g, '\\-')}`));
      await expect(page.locator('[data-service-shell="root"]')).toBeVisible({ timeout: 25_000 });
      await expect(page.locator(`[data-testid="${route.navTestId}"]`)).toHaveAttribute('aria-current', 'page');
      await expect(page.locator('[data-service-shell="root"]')).toContainText(route.body);
      if (route.limited) {
        await expect(page.locator('[data-testid="service-limited-placeholder"]')).toBeVisible();
      }
      if (route.notTeamOnly) {
        await expect(page.locator('[data-service-shell="root"]')).not.toContainText('Seznam techniků');
      }
    }
  });

  test('service_f5_keeps_session_on_each_section', async ({ page }) => {
    const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
    const slug = slugMatch?.[1] || 'e2e-fixed-service';

    for (const route of SERVICE_SECTION_ROUTES) {
      const path = route.path;
      await page.goto(`/web/app/s/${slug}/${path}`, { waitUntil: 'domcontentloaded' });
      await waitForServiceShellReady(page);
      await expect(page.locator('[data-testid="login-form"]')).not.toBeVisible();
      const urlBefore = page.url();
      await page.reload({ waitUntil: 'domcontentloaded' });
      await waitForServiceShellReady(page);
      await expect(page.locator('[data-testid="login-form"]')).not.toBeVisible();
      await expect(page).toHaveURL(urlBefore);
      await expect(page.locator('[data-service-shell="root"]')).toBeVisible();
      await expect(page.locator(`[data-testid="${route.navTestId}"]`)).toHaveAttribute('aria-current', 'page');
    }
  });

  test('service_unknown_route_redirects_to_dashboard', async ({ page }) => {
    const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
    const slug = slugMatch?.[1] || 'e2e-fixed-service';
    await page.goto(`/web/app/s/${slug}/neznama-sekce-e2e`, { waitUntil: 'domcontentloaded' });
    await waitForServiceShellReady(page);
    await expect(page).toHaveURL(/\/app\/s\/[^/]+\/dashboard/);
    await expect(page.locator('[data-testid="service-nav-dashboard"]')).toHaveAttribute('aria-current', 'page');
  });

  test('service_billing_alias_opens_invoices_section', async ({ page }) => {
    const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
    const slug = slugMatch?.[1] || 'e2e-fixed-service';
    await page.goto(`/web/app/s/${slug}/billing`, { waitUntil: 'domcontentloaded' });
    await waitForServiceShellReady(page);
    await expect(page).toHaveURL(/\/billing/);
    await expect(page.locator('[data-service-active-section="invoices"]')).toBeVisible();
    await expect(page.locator('[data-service-shell="root"]')).toContainText(/Faktury/i);
  });

  test('service_parts_stock_alias_opens_parts_section', async ({ page }) => {
    const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
    const slug = slugMatch?.[1] || 'e2e-fixed-service';
    await page.goto(`/web/app/s/${slug}/parts-stock`, { waitUntil: 'domcontentloaded' });
    await waitForServiceShellReady(page);
    await expect(page).toHaveURL(/\/parts-stock/);
    await expect(page.locator('[data-service-active-section="parts"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-limited-placeholder"]')).toBeVisible();
  });

  test('service_audit_security_alias_opens_audit_section', async ({ page }) => {
    const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
    const slug = slugMatch?.[1] || 'e2e-fixed-service';
    await page.goto(`/web/app/s/${slug}/audit-security`, { waitUntil: 'domcontentloaded' });
    await waitForServiceShellReady(page);
    await expect(page).toHaveURL(/\/audit-security/);
    await expect(page.locator('[data-service-active-section="audit"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-limited-placeholder"]')).toBeVisible();
  });

  test('service_settings_route_shows_limited_settings_not_team_dashboard', async ({ page }) => {
    const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
    const slug = slugMatch?.[1] || 'e2e-fixed-service';
    await page.goto(`/web/app/s/${slug}/settings`, { waitUntil: 'domcontentloaded' });
    await waitForServiceShellReady(page);
    await expect(page).toHaveURL(/\/settings/);
    await expect(page.locator('[data-service-active-section="settings"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-limited-placeholder"]')).toBeVisible();
    await expect(page.locator('[data-service-shell="root"]')).toContainText(/Nastavení servisu/i);
    await expect(page.locator('[data-service-shell="root"]')).not.toContainText('Seznam techniků');
  });
});
