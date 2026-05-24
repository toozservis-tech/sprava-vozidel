import { test, expect } from '@playwright/test';
import { ensureTestUser, getBaseUrl } from './helpers';
import { recycleCiEmailsQuiet } from './recycle-ci-emails';

test.describe('License clickthrough', () => {
  test('should thoroughly click through license UI and collect API results', async ({ page }) => {
    const baseUrl = getBaseUrl();
    const email = (process.env.E2E_LICENSE_EMAIL || 'e2e.license.clickthrough@example.com').toLowerCase();
    recycleCiEmailsQuiet([email]);
    const password = 'E2eTest123!';
    const apiEvents: Array<{ method: string; status: number; url: string }> = [];
    const upgradeAlerts: string[] = [];

    page.on('response', (response) => {
      const url = response.url();
      if (url.includes('/api/v1/license/status') || url.includes('/api/v1/license/upgrade')) {
        apiEvents.push({
          method: response.request().method(),
          status: response.status(),
          url,
        });
      }
    });

    await page.goto(`${baseUrl}/web/index.html`);
    await ensureTestUser(page, email, password);

    await page.fill('[data-testid="input-email"]', email);
    await page.fill('[data-testid="input-password"]', password);
    await page.click('[data-testid="btn-login"]');

    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('#licenseQuickToggle')).toBeVisible();

    await expect(page.locator('#licenseQuickLabel')).toContainText('Licence:', { timeout: 15000 });

    const modal = page.locator('#licenseModal');
    await page.click('#licenseQuickToggle');
    await expect(modal).toBeVisible();
    await expect(modal.locator('text=Aktuální licence')).toBeVisible();
    await expect(modal.locator('text=Dostupné plány')).toBeVisible();
    await expect(modal.locator('.license-plan-card')).toHaveCount(3);

    const tryUpgrade = async (plan: 'basic' | 'premium') => {
      const btn = modal.locator(`.license-plan-card[data-plan="${plan}"] .plan-action-btn`);
      if (!(await btn.isVisible()) || !(await btn.isEnabled())) {
        return;
      }
      await btn.click();
      const alert = page.locator('#alertContainer .alert').first();
      await expect(alert).toBeVisible({ timeout: 8000 });
      const text = (await alert.innerText()).trim();
      if (text) {
        upgradeAlerts.push(`${plan.toUpperCase()}: ${text}`);
      }
    };

    await tryUpgrade('basic');
    await tryUpgrade('premium');

    await modal.locator('.license-modal-close').click();
    await expect(modal).toBeHidden();

    await page.click('#licenseQuickToggle');
    await expect(modal).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(modal).toBeHidden();

    await expect(page.locator('#licenseQuickLabel')).not.toContainText('načítám', { timeout: 10000 });
    await page.screenshot({ path: 'test-results/license-clickthrough-final.png', fullPage: true });

    expect(apiEvents.some((e) => e.url.includes('/api/v1/license/status'))).toBeTruthy();

    const summaryLines = [
      `Base URL: ${baseUrl}`,
      `User: ${email}`,
      '',
      'API events:',
      ...apiEvents.map((e) => `${e.method} ${e.status} ${e.url}`),
      '',
      'Upgrade alerts:',
      ...(upgradeAlerts.length ? upgradeAlerts : ['(none)']),
    ];

    await test.info().attach('license-clickthrough-summary', {
      body: summaryLines.join('\n'),
      contentType: 'text/plain',
    });
  });
});

