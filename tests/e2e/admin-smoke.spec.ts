import { expect, test } from '@playwright/test';

import { recycleCiEmailsQuiet } from './recycle-ci-emails';

const adminEmail = process.env.E2E_ADMIN_EMAIL || '';
const adminPassword = process.env.E2E_ADMIN_PASSWORD || '';
/** Pevné testovací účty CC (před suite uvolníme slot v DB). */
const CC_TEST_EMAIL = (process.env.E2E_CC_TEST_EMAIL || 'e2e.cc.control-center@example.com').toLowerCase();
const CC_POSTUNBLOCK_EMAIL = (process.env.E2E_CC_POSTUNBLOCK_EMAIL || 'e2e.cc.post-unblock@example.com').toLowerCase();
const responsiveViewports = [
  { label: '390x844', width: 390, height: 844 },
  { label: '412x915', width: 412, height: 915 },
  { label: '768x1024', width: 768, height: 1024 },
  { label: '820x1180', width: 820, height: 1180 },
];
let cachedAdminToken = '';
let cachedAdminRole = 'developer_admin';

async function loginAdmin(page: any): Promise<void> {
  let token = cachedAdminToken;
  let role = cachedAdminRole || 'developer_admin';

  if (token) {
    const meResponse = await page.request.get('/user/me', {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!meResponse.ok()) {
      token = '';
      cachedAdminToken = '';
    }
  }

  if (!token) {
    for (let attempt = 0; attempt < 5; attempt += 1) {
      const response = await page.request.post('/user/login', {
        data: { email: adminEmail, password: adminPassword },
      });
      if (response.ok()) {
        const payload = await response.json();
        token = String(payload?.access_token || '');
        role = String(payload?.user?.role || 'developer_admin');
        if (!token) {
          throw new Error('Admin login API nevrátil access token.');
        }
        cachedAdminToken = token;
        cachedAdminRole = role;
        break;
      }

      const detailPayload = await response.json().catch(() => ({}));
      const detailText = typeof detailPayload?.detail === 'string'
        ? detailPayload.detail
        : JSON.stringify(detailPayload?.detail || '');
      const isRateLimit = response.status() === 429 || detailText.toLowerCase().includes('příliš mnoho');
      if (!isRateLimit) {
        throw new Error(`Admin login API failed: HTTP ${response.status()} ${detailText}`);
      }
      await page.waitForTimeout(15_000);
    }
  }

  expect(token.length).toBeGreaterThan(10);

  await page.goto('/web_admin/index.html');
  await expect(page.locator('#login-form')).toBeVisible({ timeout: 15_000 });
  await page.evaluate(({ nextToken, nextRole }) => {
    localStorage.setItem('adminAccessToken', nextToken);
    localStorage.setItem('adminRole', nextRole || 'developer_admin');
  }, { nextToken: token, nextRole: role });
  await page.reload();
  await expect(page.locator('#dashboard-screen')).toBeVisible({ timeout: 20_000 });
}

test.describe('Admin Smoke', () => {
  test.beforeAll(() => {
    recycleCiEmailsQuiet([CC_TEST_EMAIL, CC_POSTUNBLOCK_EMAIL]);
  });

  test('admin login screen stays usable on mobile/tablet viewports', async ({ page }) => {
    for (const viewport of responsiveViewports) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto('/web_admin/index.html');

      await expect(page.locator('#login-form')).toBeVisible({ timeout: 15_000 });
      await expect(page.locator('#admin-email')).toBeVisible();
      await expect(page.locator('#admin-password')).toBeVisible();

      const overflowX = await page.evaluate(() => {
        return Math.max(0, document.documentElement.scrollWidth - window.innerWidth);
      });
      expect(overflowX, `Horizontal overflow on ${viewport.label}`).toBeLessThanOrEqual(2);

      const loginButton = page.locator('#login-form .btn-login');
      await loginButton.scrollIntoViewIfNeeded();
      await expect(loginButton, `Login CTA visibility on ${viewport.label}`).toBeVisible();
    }
  });

  test('admin shell loads and CRUD modal opens/closes', async ({ page }) => {
    test.skip(!adminEmail || !adminPassword, 'E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD are required for admin smoke.');

    await loginAdmin(page);
    await expect(page.locator('button.nav-item[data-section="users"]')).toBeVisible();
    await page.click('button.nav-item[data-section="users"]');
    await expect(page.locator('#section-users')).toBeVisible({ timeout: 10_000 });

    await page.click('#section-users .btn-primary:has-text("+ Přidat uživatele")');
    await expect(page.locator('#user-modal')).toBeVisible({ timeout: 10_000 });
    await page.click('#user-modal .modal-close');
    await expect(page.locator('#user-modal')).toBeHidden({ timeout: 10_000 });
  });

  test('admin shell remains navigable on tablet viewport', async ({ page }) => {
    test.skip(!adminEmail || !adminPassword, 'E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD are required for admin smoke.');

    await page.setViewportSize({ width: 820, height: 1180 });
    await loginAdmin(page);

    const usersNavButton = page.locator('button.nav-item[data-section="users"]');
    await expect(usersNavButton).toBeVisible({ timeout: 10_000 });
    const usersNavWithinViewport = await usersNavButton.evaluate((el) => {
      const rect = el.getBoundingClientRect();
      return rect.top >= 0 && rect.left >= 0 && rect.bottom <= window.innerHeight && rect.right <= window.innerWidth;
    });
    if (usersNavWithinViewport) {
      await usersNavButton.click();
    } else {
      await page.click('#summary-users');
    }

    await expect(page.locator('#section-users')).toBeVisible({ timeout: 10_000 });

    await page.click('#section-users .btn-primary:has-text("+ Přidat uživatele")');
    const userModal = page.locator('#user-modal');
    await expect(userModal).toBeVisible({ timeout: 10_000 });

    const userForm = page.locator('#user-modal #user-form');
    await userForm.scrollIntoViewIfNeeded();
    await expect(userForm).toBeVisible();

    await page.click('#user-modal .modal-close');
    await expect(userModal).toBeHidden({ timeout: 10_000 });
  });

  test('record modal allows saving without service after vehicle selection', async ({ page }) => {
    test.skip(!adminEmail || !adminPassword, 'E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD are required for admin smoke.');

    const uniqueDescription = `E2E Admin no-service record ${Date.now()}`;

    await loginAdmin(page);

    await page.click('button.nav-item[data-section="records"]');
    await expect(page.locator('#section-records')).toBeVisible({ timeout: 10_000 });

    await page.click('#section-records .btn-primary:has-text("+ Přidat záznam")');
    await expect(page.locator('#record-modal')).toBeVisible({ timeout: 10_000 });

    const vehicleSelect = page.locator('#record-vehicle-id');
    const vehicleOptionsCount = await vehicleSelect.locator('option').count();
    test.skip(vehicleOptionsCount < 2, 'At least one vehicle is required to validate record creation flow.');

    const serviceSelect = page.locator('#record-service-id');
    await expect(serviceSelect).toBeDisabled();

    await vehicleSelect.selectOption({ index: 1 });
    await expect(serviceSelect).toBeEnabled();
    await serviceSelect.selectOption('');

    await page.fill('#record-description', uniqueDescription);
    await page.fill('#record-mileage', '777');
    await page.fill('#record-price', '77');
    await page.fill('#record-category', 'E2E');
    await page.fill('#record-note', 'Admin smoke: optional service');

    await page.click('#record-form .btn-primary:has-text("Uložit")');
    await expect(page.locator('#record-modal')).toBeHidden({ timeout: 10_000 });
    await expect(page.locator('#records-cards-container')).toContainText(uniqueDescription, { timeout: 15_000 });

    const createdCard = page.locator('#records-cards-container .card', { hasText: uniqueDescription }).first();
    await expect(createdCard).toBeVisible({ timeout: 10_000 });
    page.once('dialog', (dialog) => dialog.accept());
    await createdCard.locator('.btn-danger').click();
    await expect(createdCard).toBeHidden({ timeout: 15_000 });
  });

  test('user card action buttons do not open detail modal unexpectedly', async ({ page }) => {
    test.skip(!adminEmail || !adminPassword, 'E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD are required for admin smoke.');

    await loginAdmin(page);

    await page.click('button.nav-item[data-section="users"]');
    await expect(page.locator('#section-users')).toBeVisible({ timeout: 10_000 });

    const firstUserCard = page.locator('#users-cards-container .card.user-card, #users-cards-container .card.user-card-clickable').first();
    await expect(firstUserCard).toBeVisible({ timeout: 15_000 });

    const editButton = firstUserCard.locator('.btn-edit').first();
    await expect(editButton).toBeVisible({ timeout: 10_000 });
    await editButton.click();
    await expect(page.locator('#user-modal')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('#user-detail-modal')).toBeHidden({ timeout: 10_000 });
    await page.click('#user-modal .modal-close');
    await expect(page.locator('#user-modal')).toBeHidden({ timeout: 10_000 });

    page.once('dialog', (dialog) => dialog.dismiss());
    const deleteButton = firstUserCard.locator('.btn-danger').first();
    await expect(deleteButton).toBeVisible({ timeout: 10_000 });
    await deleteButton.click();
    await expect(page.locator('#user-detail-modal')).toBeHidden({ timeout: 10_000 });
  });

  test('editing user from detail modal opens user edit modal', async ({ page }) => {
    test.skip(!adminEmail || !adminPassword, 'E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD are required for admin smoke.');

    await loginAdmin(page);

    await page.click('button.nav-item[data-section="users"]');
    await expect(page.locator('#section-users')).toBeVisible({ timeout: 10_000 });

    const firstUserCard = page.locator('#users-cards-container .card.user-card, #users-cards-container .card.user-card-clickable').first();
    await expect(firstUserCard).toBeVisible({ timeout: 15_000 });
    await firstUserCard.click();
    await expect(page.locator('#user-detail-modal')).toBeVisible({ timeout: 10_000 });

    await page.click('#user-detail-modal .btn-primary:has-text("Upravit uživatele")');
    await expect(page.locator('#user-modal')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('#user-detail-modal')).toBeHidden({ timeout: 10_000 });
  });

  test('developer control center visibility and health panel wiring', async ({ page }) => {
    test.skip(!adminEmail || !adminPassword, 'E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD are required for admin smoke.');

    await loginAdmin(page);

    const controlCenterNav = page.locator('button.nav-item[data-section="control-center"]');
    const visibleCount = await controlCenterNav.count();
    if (visibleCount === 0) {
      await expect(controlCenterNav).toHaveCount(0);
      return;
    }
    if (!(await controlCenterNav.isVisible())) {
      await expect(controlCenterNav).toBeHidden();
      return;
    }

    await controlCenterNav.click();
    await expect(page.locator('#section-control-center')).toBeVisible({ timeout: 10_000 });

    await page.click('#section-control-center button:has-text("Načíst health")');
    const healthResult = page.locator('#cc-health-result');
    await expect(healthResult).toBeVisible({ timeout: 10_000 });
    await expect(healthResult).not.toHaveText('', { timeout: 15_000 });
  });

  test('developer control center critical actions are end-to-end functional', async ({ page, request }) => {
    test.skip(!adminEmail || !adminPassword, 'E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD are required for admin smoke.');

    const unique = Date.now();
    const testEmail = CC_TEST_EMAIL;
    const testPassword = 'TestPass123!';
    let activeUserPassword = testPassword;
    const testName = `CC User ${unique}`;
    const broadcastMessage = `CC broadcast ${unique}`;

    const registerResponse = await request.post('/user/register', {
      data: {
        email: testEmail,
        password: testPassword,
        name: testName,
      },
    });
    expect(registerResponse.ok()).toBeTruthy();
    const registerData = await registerResponse.json();
    const userId = registerData?.user?.id;
    const initialUserToken = registerData?.access_token;
    expect(typeof userId).toBe('number');
    expect(typeof initialUserToken).toBe('string');

    await loginAdmin(page);

    const adminToken = await page.evaluate(() => localStorage.getItem('adminAccessToken') || localStorage.getItem('accessToken'));
    expect(typeof adminToken).toBe('string');
    const adminHeaders = { Authorization: `Bearer ${adminToken}` };

    const controlCenterNav = page.locator('button.nav-item[data-section="control-center"]');
    await expect(controlCenterNav).toBeVisible({ timeout: 10_000 });
    await controlCenterNav.click();
    await expect(page.locator('#section-control-center')).toBeVisible({ timeout: 10_000 });

    await page.fill('#cc-insight-user-id', String(userId));
    await page.click('#section-control-center button:has-text("Načíst insight")');
    await expect(page.locator('#cc-insight-result')).toContainText(testEmail, { timeout: 15_000 });

    page.once('dialog', (dialog) => dialog.accept());
    await page.click('#section-control-center button:has-text("Force logout")');
    await expect(page.locator('#cc-insight-result')).not.toContainText('"loading": true', { timeout: 15_000 });

    const meAfterForceLogout = await request.get('/user/me', {
      headers: { Authorization: `Bearer ${initialUserToken}` },
    });
    expect(meAfterForceLogout.status()).toBe(401);

    page.once('dialog', (dialog) => dialog.accept());
    await page.click('#section-control-center button:has-text("Disable")');
    await expect(page.locator('#cc-insight-result')).not.toContainText('"loading": true', { timeout: 15_000 });

    const loginWhileDisabled = await request.post('/user/login', {
      data: { email: testEmail, password: testPassword },
    });
    expect(loginWhileDisabled.status()).toBe(403);

    page.once('dialog', (dialog) => dialog.accept());
    await page.click('#section-control-center button:has-text("Enable")');
    await expect(page.locator('#cc-insight-result')).not.toContainText('"loading": true', { timeout: 15_000 });

    const loginAfterEnable = await request.post('/user/login', {
      data: { email: testEmail, password: activeUserPassword },
    });
    expect(loginAfterEnable.ok()).toBeTruthy();
    const userTokenAfterEnable = (await loginAfterEnable.json())?.access_token;
    expect(typeof userTokenAfterEnable).toBe('string');
    let activeUserToken = String(userTokenAfterEnable);

    const resetPasswordValue = `Reset-${unique}!Aa1`;
    const resetPasswordResponse = await request.post(`/admin-api/control-center/users/${userId}/reset-password`, {
      headers: adminHeaders,
      data: {
        new_password: resetPasswordValue,
        generate_random: false,
        reason: 'e2e-password-reset',
      },
    });
    expect(resetPasswordResponse.ok()).toBeTruthy();

    const loginWithOldPassword = await request.post('/user/login', {
      data: { email: testEmail, password: activeUserPassword },
    });
    expect(loginWithOldPassword.ok()).toBeFalsy();

    const loginWithResetPassword = await request.post('/user/login', {
      data: { email: testEmail, password: resetPasswordValue },
    });
    expect(loginWithResetPassword.ok()).toBeTruthy();
    const loginWithResetPasswordPayload = await loginWithResetPassword.json();
    activeUserToken = String(loginWithResetPasswordPayload?.access_token || activeUserToken);
    activeUserPassword = resetPasswordValue;

    await page.selectOption('#cc-license-plan', 'premium');
    await page.selectOption('#cc-license-status', 'active');
    await page.click('#section-control-center button:has-text("Uložit licenci")');
    await expect(page.locator('#cc-insight-result')).not.toContainText('"loading": true', { timeout: 15_000 });

    const licenseStatus = await request.get('/api/v1/license/status', {
      headers: { Authorization: `Bearer ${activeUserToken}` },
    });
    expect(licenseStatus.ok()).toBeTruthy();
    const licensePayload = await licenseStatus.json();
    expect(String(licensePayload?.plan || '').toLowerCase()).toBe('premium');

    const userPage = await page.context().newPage();
    await userPage.goto('/');
    await expect(userPage.locator('[data-testid="input-email"]')).toBeVisible({ timeout: 15_000 });
    await userPage.fill('[data-testid="input-email"]', testEmail);
    await userPage.fill('[data-testid="input-password"]', activeUserPassword);
    await userPage.click('[data-testid="btn-login"]');
    await expect(userPage.locator('#dashboard')).toBeVisible({ timeout: 20_000 });
    await expect(userPage.locator('#licenseQuickLabel')).toContainText(/PREMIUM/i, { timeout: 20_000 });

    const paymentResync = await request.post('/admin-api/control-center/payments/resync', {
      headers: adminHeaders,
      data: {},
    });
    expect(paymentResync.ok()).toBeTruthy();

    const presenceResponse = await request.get('/admin-api/control-center/presence?limit=200', {
      headers: adminHeaders,
    });
    expect(presenceResponse.ok()).toBeTruthy();
    const presencePayload = await presenceResponse.json();
    const presenceItems = Array.isArray(presencePayload?.items) ? presencePayload.items : [];
    expect(presenceItems.some((item: any) => Number(item?.user_id) === Number(userId))).toBeTruthy();

    const jobsPauseResponse = await request.post('/admin-api/control-center/jobs/pause', {
      headers: adminHeaders,
      data: { job_name: 'license.subscription.cycle', reason: `e2e-${unique}` },
    });
    expect(jobsPauseResponse.ok()).toBeTruthy();

    const jobsRunWhilePaused = await request.post('/admin-api/control-center/jobs/run', {
      headers: adminHeaders,
      data: { job_name: 'license.subscription.cycle' },
    });
    expect(jobsRunWhilePaused.status()).toBe(409);

    const jobsResumeResponse = await request.post('/admin-api/control-center/jobs/resume', {
      headers: adminHeaders,
      data: { job_name: 'license.subscription.cycle', reason: `e2e-${unique}` },
    });
    expect(jobsResumeResponse.ok()).toBeTruthy();

    const jobsRunResponse = await request.post('/admin-api/control-center/jobs/run', {
      headers: adminHeaders,
      data: { job_name: 'license.subscription.cycle' },
    });
    expect(jobsRunResponse.ok()).toBeTruthy();

    const backupCreateResponse = await request.post('/admin-api/control-center/backups/create', {
      headers: adminHeaders,
      data: { include_data_dir: false },
    });
    expect(backupCreateResponse.ok()).toBeTruthy();
    const backupCreatePayload = await backupCreateResponse.json();
    const backupId = backupCreatePayload?.backup?.backup_id;
    expect(typeof backupId).toBe('string');

    const mutatedName = `Mutated ${unique}`;
    const mutateUserResponse = await request.patch(`/admin-api/users/${userId}`, {
      headers: adminHeaders,
      data: { name: mutatedName },
    });
    expect(mutateUserResponse.ok()).toBeTruthy();

    const detailAfterMutate = await request.get(`/admin-api/users/${userId}/detail`, {
      headers: adminHeaders,
    });
    expect(detailAfterMutate.ok()).toBeTruthy();
    const detailAfterMutatePayload = await detailAfterMutate.json();
    expect(String(detailAfterMutatePayload?.user?.name || '')).toBe(mutatedName);

    const restoreUserScopeResponse = await request.post('/admin-api/control-center/backups/restore', {
      headers: adminHeaders,
      data: {
        backup_id: backupId,
        scope: 'user',
        user_id: userId,
        confirm_text: 'PROCEED_RESTORE',
      },
    });
    expect(restoreUserScopeResponse.ok()).toBeTruthy();

    const detailAfterRestore = await request.get(`/admin-api/users/${userId}/detail`, {
      headers: adminHeaders,
    });
    expect(detailAfterRestore.ok()).toBeTruthy();
    const detailAfterRestorePayload = await detailAfterRestore.json();
    expect(String(detailAfterRestorePayload?.user?.name || '')).toBe(testName);

    const emailMonitorResponse = await request.get('/admin-api/control-center/email-monitor?limit=20', {
      headers: adminHeaders,
    });
    expect(emailMonitorResponse.ok()).toBeTruthy();
    const emailMonitorPayload = await emailMonitorResponse.json();
    expect(typeof emailMonitorPayload?.summary).toBe('object');

    const storageCleanupPreviewResponse = await request.get('/admin-api/control-center/storage/cleanup-preview?logs_days=30&backups_days=30', {
      headers: adminHeaders,
    });
    expect(storageCleanupPreviewResponse.ok()).toBeTruthy();
    const storagePreviewPayload = await storageCleanupPreviewResponse.json();
    expect(String(storagePreviewPayload?.confirm_text_required || '')).toBe('PROCEED_CLEANUP');

    await page.fill('#cc-broadcast-message', broadcastMessage);
    await page.fill('#cc-broadcast-title', 'E2E');
    await page.selectOption('#cc-broadcast-target-type', 'user');
    await page.fill('#cc-broadcast-target-value', String(userId));
    await page.click('#section-control-center button:has-text("Odeslat broadcast")');
    await expect(page.locator('#cc-notifications-result')).not.toContainText('"loading": true', { timeout: 15_000 });

    const notificationFeed = await request.get('/api/v1/system-notifications?limit=20', {
      headers: { Authorization: `Bearer ${activeUserToken}` },
    });
    expect(notificationFeed.ok()).toBeTruthy();
    const notificationPayload = await notificationFeed.json();
    const notificationItems = Array.isArray(notificationPayload?.items) ? notificationPayload.items : [];
    expect(notificationItems.some((item: any) => String(item?.message || '').includes(broadcastMessage))).toBeTruthy();
    await userPage.evaluate(async () => {
      const maybeLoader = (window as any).loadSystemNotifications;
      if (typeof maybeLoader === 'function') {
        await maybeLoader();
      }
    });
    await expect(userPage.locator('#alertContainer')).toContainText(broadcastMessage, { timeout: 15_000 });

    await page.fill('#cc-command', 'system.health');
    await page.click('#section-control-center button:has-text("Spustit příkaz")');
    await expect(page.locator('#cc-command-result')).toContainText('"ok": true', { timeout: 15_000 });

    const auditActionsResponse = await request.get('/admin-api/control-center/audit-actions?limit=200', {
      headers: adminHeaders,
    });
    expect(auditActionsResponse.ok()).toBeTruthy();
    const auditActionsPayload = await auditActionsResponse.json();
    const auditItems = Array.isArray(auditActionsPayload?.items) ? auditActionsPayload.items : [];
    expect(auditItems.some((item: any) => String(item?.action_type || '').includes('license'))).toBeTruthy();

    await page.fill('#cc-block-ip', '127.0.0.1');
    await page.fill('#cc-block-reason', `e2e-block-${unique}`);
    await page.click('#section-control-center button:has-text("Blokovat IP")');
    await expect(page.locator('#cc-security-result')).not.toContainText('"loading": true', { timeout: 15_000 });

    try {
      const blockedLogin = await request.post('/user/login', {
        data: { email: testEmail, password: activeUserPassword },
      });
      expect([403, 429]).toContain(blockedLogin.status());
    } finally {
      await page.click('#section-control-center button:has-text("Odblokovat IP")');
      await expect(page.locator('#cc-security-result')).not.toContainText('"loading": true', { timeout: 15_000 });
    }

    const postUnblockEmail = CC_POSTUNBLOCK_EMAIL;
    const postUnblockPassword = `PostUnblock-${unique}!Aa1`;
    const postUnblockRegister = await request.post('/user/register', {
      data: {
        email: postUnblockEmail,
        password: postUnblockPassword,
        name: `Post unblock ${unique}`,
      },
    });
    expect(postUnblockRegister.ok()).toBeTruthy();

    const loginAfterUnblock = await request.post('/user/login', {
      data: { email: postUnblockEmail, password: postUnblockPassword },
    });
    expect(loginAfterUnblock.ok()).toBeTruthy();

    await page.click('button.nav-item[data-section="users"]');
    await expect(page.locator('#section-users')).toBeVisible({ timeout: 10_000 });
    await page.fill('#user-search', testEmail);
    const userCard = page.locator('#users-cards-container .card', { hasText: testEmail }).first();
    await expect(userCard).toBeVisible({ timeout: 15_000 });
    page.once('dialog', (dialog) => dialog.accept());
    await userCard.locator('.btn-danger').first().click();
    await expect(userCard).toBeHidden({ timeout: 20_000 });

    const loginAfterDelete = await request.post('/user/login', {
      data: { email: testEmail, password: activeUserPassword },
    });
    expect(loginAfterDelete.ok()).toBeFalsy();

    await userPage.close();
  });
});
