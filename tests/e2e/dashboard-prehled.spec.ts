import { expect, test, type Page } from '@playwright/test';

function attachFatalErrorCollector(page: Page): string[] {
  const fatalMessages: string[] = [];
  const fatalConsolePatterns = [
    /TypeError/i,
    /ReferenceError/i,
    /SyntaxError/i,
    /Unhandled/i,
    /Cannot read/i,
  ];

  page.on('pageerror', (error) => {
    fatalMessages.push(`pageerror: ${error.message}`);
  });

  page.on('console', (message) => {
    if (message.type() !== 'error') return;
    const text = message.text();
    if (!fatalConsolePatterns.some((pattern) => pattern.test(text))) return;
    fatalMessages.push(`console: ${text}`);
  });

  return fatalMessages;
}

async function openUserDashboard(page: Page): Promise<void> {
  await page.goto('/web/index.html');
  await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 25_000 });
  await expect(page.locator('[data-testid="dashboard-overview-shell"]')).toBeVisible({ timeout: 25_000 });
}

test.describe('Dashboard Přehled (user-app-next)', () => {
  test.beforeEach(async ({ page }) => {
    await openUserDashboard(page);
  });

  test('overview shell, hero, quick grid, vehicles and aside are visible', async ({ page }) => {
    const fatalMessages = attachFatalErrorCollector(page);

    await expect(page.locator('[data-testid="dashboard-overview-shell"]')).toBeVisible();
    await expect(page.locator('[data-testid="dashboard-hero"]')).toBeVisible();
    await expect(page.locator('[data-testid="dashboard-quick-grid"]')).toBeVisible();
    await expect(page.locator('[data-testid="dashboard-vehicles-section"]')).toBeVisible();
    await expect(page.locator('[data-testid="dashboard-overview-aside"]')).toBeVisible();
    await expect(page.locator('[data-testid="dashboard-aside-deadlines"]')).toBeVisible();
    await expect(page.locator('[data-testid="dashboard-aside-activity"]')).toBeVisible();
    await expect(page.locator('[data-testid="dashboard-aside-access"]')).toBeVisible();

    expect(fatalMessages, `Fatal browser errors:\n${fatalMessages.join('\n')}`).toEqual([]);
  });

  test('sidebar navigation between Přehled and Moje vozidla', async ({ page }) => {
    await page.locator('[data-testid="dashboard-nav-vehicles"]').click();
    await expect(page.locator('.uapp-next-catalog[data-testid="user-app-next-vehicles"]')).toBeVisible({
      timeout: 15_000,
    });

    await page.locator('[data-testid="dashboard-nav-home"]').click();
    await expect(page.locator('[data-testid="dashboard-overview-shell"]')).toBeVisible({ timeout: 15_000 });
  });

  test('add vehicle opens modal from topbar', async ({ page }) => {
    await page.locator('[data-testid="dashboard-add-vehicle"]').click();
    await expect(page.locator('#addVehicleModal, [data-testid="add-vehicle-form"]').first()).toBeVisible({
      timeout: 15_000,
    });
  });

  test('Ctrl/Cmd+K focuses dashboard search', async ({ page }) => {
    const search = page.locator('[data-testid="dashboard-search-input"]');
    await search.click();
    await search.fill('');
    await page.keyboard.press('Control+K');
    await expect(search).toBeFocused();
  });

  test('quick STK card navigates to reminders', async ({ page }) => {
    await page.locator('[data-testid="dashboard-quick-stk"]').click();
    await expect(page.locator('.uapp-rem-page[data-testid="user-app-next-reminders"]')).toBeVisible({
      timeout: 15_000,
    });
  });

  test('service history deep link survives reload', async ({ page }) => {
    await page.locator('[data-testid="dashboard-nav-serviceHistory"]').click();
    await expect(page.locator('.uapp-sh-page[data-testid="user-app-next-service-history"]')).toBeVisible({
      timeout: 15_000,
    });

    const url = page.url();
    expect(url).toMatch(/service-history/i);

    await page.reload();
    await expect(page.locator('.uapp-sh-page[data-testid="user-app-next-service-history"]')).toBeVisible({
      timeout: 25_000,
    });
  });

  test('vehicle card detail opens user-app-next modal when present', async ({ page }) => {
    const card = page.locator('[data-testid^="dashboard-vehicle-card-"]').first();
    if (!(await card.isVisible({ timeout: 5_000 }).catch(() => false))) {
      test.skip(true, 'No vehicles on dashboard for this account');
    }

    await card.locator('.uapp-next-vehicle-open').click();
    await expect(
      page.locator('[data-testid="user-app-next-vehicle-detail"], #uappNextVehicleDetail').first(),
    ).toBeVisible({ timeout: 15_000 });
  });
});
