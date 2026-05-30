import { expect, test } from '@playwright/test';

import { loginUser, waitForUserShellReady } from './helpers';

const settingsSnapshotPath = '**/api/v1/user/settings';
const sharingPath = '**/api/v1/user/settings/services-sharing';
const accessDecisionPath = '**/api/v1/services/access-requests/*';

const settingsSnapshot = {
  profile: { name: 'E2E User', email: 'e2e.user@toozservis.cz' },
  license: { trial_active: false },
};

const pendingSharingPayload = {
  favorites: [],
  sharing: [
    {
      request_id: 501,
      service_name: 'E2E Test Servis',
      vehicle_name: 'Skoda Octavia',
      vehicle_plate_masked: '1AB***45',
      vehicle_vin_masked: 'TMB***7890',
      reason: 'Propojení pro servisní historii',
      requested_scope: 'owner_approved',
      status: 'pending',
      created_at: '2026-05-28T10:00:00Z',
    },
  ],
  communication: { allow_vehicle_access: true, allow_communication: true },
};

async function openServicesSharingPanel(page: Parameters<typeof test>[0]['page']) {
  await page.route(settingsSnapshotPath, async (route) => {
    if (route.request().method() === 'GET' && !route.request().url().includes('/services-sharing')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(settingsSnapshot),
      });
      return;
    }
    await route.continue();
  });
  await page.route(sharingPath, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(pendingSharingPayload),
    });
  });
  const slugMatch = page.url().match(/\/app\/u\/([^/]+)/);
  const slug = slugMatch?.[1] || 'e2e-user';
  await page.goto(`/web/app/u/${slug}/settings/services-sharing`, { waitUntil: 'domcontentloaded' });
  await waitForUserShellReady(page);
  await expect(page.locator('.uapp-settings-topbar-title')).toBeVisible({ timeout: 45_000 });
  await expect(page.locator('[data-testid="user-service-requests-section"]')).toBeVisible({ timeout: 30_000 });
}

test.describe('Owner service access requests', () => {
  test.beforeEach(async ({ page }) => {
    await loginUser(page);
  });

  test('user_sees_service_request', async ({ page }) => {
    await openServicesSharingPanel(page);
    await expect(page.locator('[data-testid="user-service-request-card"]').first()).toContainText(/E2E Test Servis/i);
    await expect(page.locator('[data-testid="user-service-request-card"]').first()).toContainText(/Skoda Octavia/i);
    const card = page.locator('[data-testid="user-service-request-card"]').first();
    await expect(card.locator('[data-testid="user-service-request-approve-button"]')).toBeVisible();
    await expect(card.locator('[data-testid="user-service-request-reject-button"]')).toBeVisible();
  });

  test('user_approves_service_request', async ({ page }) => {
    let decisionBody: Record<string, unknown> | null = null;
    await openServicesSharingPanel(page);
    await page.route(accessDecisionPath, async (route) => {
      if (route.request().method() === 'PUT') {
        decisionBody = route.request().postDataJSON() as Record<string, unknown>;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ ok: true, status: 'approved' }),
        });
        return;
      }
      await route.continue();
    });
    await page.locator('[data-testid="user-service-request-card"]').first().locator('[data-testid="user-service-request-approve-button"]').click();
    await expect.poll(() => decisionBody?.decision).toBe('approved');
  });

  test('user_rejects_service_request', async ({ page }) => {
    let decisionBody: Record<string, unknown> | null = null;
    await openServicesSharingPanel(page);
    await page.route(accessDecisionPath, async (route) => {
      if (route.request().method() === 'PUT') {
        decisionBody = route.request().postDataJSON() as Record<string, unknown>;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ ok: true, status: 'rejected' }),
        });
        return;
      }
      await route.continue();
    });
    await page.locator('[data-testid="user-service-request-card"]').first().locator('[data-testid="user-service-request-reject-button"]').click();
    await expect.poll(() => decisionBody?.decision).toBe('rejected');
  });
});
