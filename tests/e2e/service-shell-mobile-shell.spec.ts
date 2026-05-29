import { expect, test } from '@playwright/test';

import {
  getServiceTestCredentials,
  loginServiceUser,
  waitForServiceShellReady,
} from './helpers';

const MOBILE_VIEWPORTS = [
  { name: 'iphone', width: 390, height: 844 },
  { name: 'iphone14pro', width: 430, height: 932 },
] as const;

async function openServiceSection(
  page: Parameters<typeof test>[0]['page'],
  section: string,
) {
  const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
  const slug = slugMatch?.[1] || 'e2e-fixed-service';
  await page.goto(`/web/app/s/${slug}/${section}`, { waitUntil: 'domcontentloaded' });
  await waitForServiceShellReady(page);
}

async function assertNoHorizontalOverflow(page: Parameters<typeof test>[0]['page']) {
  const ok = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2);
  expect(ok).toBe(true);
}

for (const viewport of MOBILE_VIEWPORTS) {
  test.describe(`Mobile shell (${viewport.name} ${viewport.width}x${viewport.height})`, () => {
    test.use({
      viewport: { width: viewport.width, height: viewport.height },
      hasTouch: true,
    });

    test.beforeEach(async ({ page }) => {
      test.skip(!getServiceTestCredentials(), 'Nastavte E2E_SERVICE_EMAIL a E2E_SERVICE_PASSWORD');
      await loginServiceUser(page);
      await waitForServiceShellReady(page);
    });

    test('bottom_nav_has_five_tabs_without_overflow', async ({ page }) => {
      await openServiceSection(page, 'dashboard');
      const nav = page.locator('#service-shell-left-nav .service-nav-menu .service-nav-slot');
      await expect(nav).toHaveCount(5);
      const navOverflow = await page.evaluate(() => {
        const menu = document.querySelector('.service-nav--mobile-tabs .service-nav-menu');
        if (!(menu instanceof HTMLElement)) return false;
        return menu.scrollWidth <= menu.clientWidth + 2;
      });
      expect(navOverflow).toBe(true);
      await expect(page.locator('[data-testid="service-nav-more"]')).toBeVisible();
    });

    test('more_sheet_opens_and_navigates_to_settings', async ({ page }) => {
      await openServiceSection(page, 'dashboard');
      await page.locator('[data-testid="service-nav-more"]').click();
      await expect(page.locator('[data-testid="service-mobile-nav-sheet"]')).toBeVisible();
      await expect(page.locator('[data-testid="service-mobile-nav-settings"]')).toBeVisible();
      await page.locator('[data-testid="service-mobile-nav-settings"]').click();
      await expect(page.locator('[data-service-active-section="settings"]')).toBeVisible();
      await expect(page.locator('[data-testid="service-mobile-nav-sheet"]')).toHaveCount(0);
    });

    test('topbar_search_and_ctas_are_full_width', async ({ page }) => {
      await openServiceSection(page, 'dashboard');
      const topbar = page.locator('.service-topbar--mobile');
      await expect(topbar).toBeVisible();
      const searchRow = page.locator('.service-topbar-row--search');
      const searchRowWidth = await searchRow.evaluate((el) => (el as HTMLElement).getBoundingClientRect().width);
      const searchWidth = await page.locator('[data-testid="service-topbar-search"]').evaluate((el) => {
        return (el as HTMLElement).getBoundingClientRect().width;
      });
      expect(searchWidth).toBeGreaterThanOrEqual(searchRowWidth * 0.95);
      const intakeBtn = page.locator('[data-testid="service-topbar-intake-cta"]');
      await expect(intakeBtn).toBeVisible();
      const ctaRowWidth = await page.locator('.service-topbar-row--cta').evaluate((el) => (el as HTMLElement).getBoundingClientRect().width);
      const intakeWidth = await intakeBtn.evaluate((el) => (el as HTMLElement).getBoundingClientRect().width);
      expect(intakeWidth).toBeGreaterThanOrEqual(ctaRowWidth * 0.95);
    });

    test('sections_have_no_horizontal_overflow', async ({ page }) => {
      for (const section of ['dashboard', 'intake', 'work-orders', 'clients']) {
        await openServiceSection(page, section);
        await assertNoHorizontalOverflow(page);
      }
    });

    test('create_work_order_modal_footer_stacks_on_mobile', async ({ page }) => {
      await openServiceSection(page, 'work-orders');
      await page.locator('[data-testid="service-topbar-workorder-cta"]').click();
      const footer = page.locator('.app-floating-modal-root .service-shell-modal-footer');
      await expect(footer).toBeVisible({ timeout: 20_000 });
      const primaryBtn = footer.locator('.btn-primary').first();
      const footerWidth = await footer.evaluate((el) => (el as HTMLElement).getBoundingClientRect().width);
      const primaryWidth = await primaryBtn.evaluate((el) => (el as HTMLElement).getBoundingClientRect().width);
      expect(primaryWidth).toBeGreaterThanOrEqual(footerWidth * 0.92);
      await page.evaluate(() => window.serviceShell.closeModal());
    });
  });
}
