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

async function openProfilePanel(page: Page) {
  await page.locator('[data-testid="dashboard-profile"]').click();
  const menu = page.locator('[data-testid="dashboard-profile-menu"]');
  await expect(menu).toBeVisible({ timeout: 10_000 });
  return menu;
}

test.describe('Dashboard profile dropdown panel', () => {
  test.beforeEach(async ({ page }) => {
    await openUserDashboard(page);
  });

  test('profile click opens panel with account, license and menu items', async ({ page }) => {
    const fatalMessages = attachFatalErrorCollector(page);
    const menu = await openProfilePanel(page);

    await expect(menu).toHaveAttribute('aria-hidden', 'false');
    await expect(page.locator('[data-testid="dashboard-profile-menu-account"]')).toBeVisible();
    await expect(page.locator('[data-testid="dashboard-profile-menu-license"]')).toBeVisible();
    await expect(page.locator('[data-testid="dashboard-profile-menu-help"]')).toBeVisible();
    await expect(page.locator('[data-testid="dashboard-profile-menu-settings"]')).toBeVisible();
    await expect(page.locator('[data-testid="dashboard-profile-menu-license-plan"]')).toBeVisible();
    await expect(page.locator('[data-testid="dashboard-profile-menu-theme"]')).toBeVisible();
    await expect(page.locator('[data-testid="dashboard-profile-menu-logout"]')).toBeVisible();

    expect(fatalMessages, `Fatal browser errors:\n${fatalMessages.join('\n')}`).toEqual([]);
  });

  test('re-click profile and click outside close the panel', async ({ page }) => {
    await openProfilePanel(page);

    await page.locator('[data-testid="dashboard-profile"]').click();
    await expect(page.locator('[data-testid="dashboard-profile-menu"]')).toBeHidden();

    await openProfilePanel(page);
    await page.locator('[data-testid="dashboard-hero"]').click();
    await expect(page.locator('[data-testid="dashboard-profile-menu"]')).toBeHidden();
  });

  test('Escape closes the profile panel', async ({ page }) => {
    await openProfilePanel(page);
    await page.keyboard.press('Escape');
    await expect(page.locator('[data-testid="dashboard-profile-menu"]')).toBeHidden();
  });

  test('Jak na to opens help hub modal', async ({ page }) => {
    const fatalMessages = attachFatalErrorCollector(page);
    await openProfilePanel(page);
    await page.locator('[data-testid="dashboard-profile-menu-help"]').click();

    const helpModal = page.locator('#howToHubModal');
    await expect(helpModal).toHaveAttribute('aria-hidden', 'false', { timeout: 10_000 });
    expect(fatalMessages, `Fatal browser errors:\n${fatalMessages.join('\n')}`).toEqual([]);
  });

  test('Nastavení účtu closes panel and wires account settings action', async ({ page }) => {
    await openProfilePanel(page);
    const settings = page.locator('[data-testid="dashboard-profile-menu-settings"]');
    await expect(settings).toHaveAttribute('onclick', /switchTab\('account'\)/);
    await settings.click();
    await expect(page.locator('[data-testid="dashboard-profile-menu"]')).toBeHidden();
  });

  test('Licence a plán opens license modal', async ({ page }) => {
    const fatalMessages = attachFatalErrorCollector(page);
    await openProfilePanel(page);
    await page.locator('[data-testid="dashboard-profile-menu-license-plan"]').click();

    const licenseModal = page.locator('#licenseModal');
    await expect(licenseModal).toBeVisible({ timeout: 10_000 });
    expect(fatalMessages, `Fatal browser errors:\n${fatalMessages.join('\n')}`).toEqual([]);
  });

  test('theme toggle action works without JS errors', async ({ page }) => {
    const fatalMessages = attachFatalErrorCollector(page);
    await openProfilePanel(page);
    await page.locator('[data-testid="dashboard-profile-menu-theme"]').click();
    expect(fatalMessages, `Fatal browser errors:\n${fatalMessages.join('\n')}`).toEqual([]);
  });

  test('logout action is present but not executed', async ({ page }) => {
    const logout = page.locator('[data-testid="dashboard-profile-menu-logout"]');
    await openProfilePanel(page);
    await expect(logout).toBeVisible();
    await expect(logout).toContainText('Odhlásit se');
    await expect(logout).toHaveAttribute('onclick', /handleLogout/);
  });
});
