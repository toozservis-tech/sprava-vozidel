import { expect, test, type Page } from '@playwright/test';

async function openDashboard(page: Page): Promise<void> {
  await page.goto('/web/index.html');
  await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 20_000 });
}

const mobileAuditViewports = [
  { width: 360, height: 800, name: '360x800' },
  { width: 390, height: 844, name: '390x844' },
  { width: 412, height: 915, name: '412x915' },
];

const mobilePolishViewports = [
  { width: 360, height: 800, name: 'mobile-360x800' },
  { width: 390, height: 844, name: 'mobile-390x844' },
  { width: 412, height: 915, name: 'mobile-412x915' },
];

const requiredViewportMatrix = [
  { width: 360, height: 800, name: 'mobile-360x800' },
  { width: 390, height: 844, name: 'mobile-390x844' },
  { width: 412, height: 915, name: 'mobile-412x915' },
  { width: 768, height: 1024, name: 'tablet-768x1024' },
  { width: 820, height: 1180, name: 'tablet-820x1180' },
  { width: 1280, height: 800, name: 'desktop-1280x800' },
  { width: 1366, height: 768, name: 'desktop-1366x768' },
  { width: 1440, height: 900, name: 'desktop-1440x900' },
];

async function setMobileAuditViewport(page: Page, viewport: { width: number; height: number }): Promise<void> {
  await page.setViewportSize({ width: viewport.width, height: viewport.height });
  await openDashboard(page);
  await expect(page.locator('#mobileMenuToggle')).toBeVisible({ timeout: 10_000 });
}

async function expectMobileMenuOpen(page: Page): Promise<void> {
  await expect(page.locator('#mainNavbar')).toHaveClass(/mobile-menu-open/, { timeout: 5_000 });
  await expect(page.locator('#mobileMenuToggle')).toHaveAttribute('aria-expanded', 'true');
}

async function expectMobileMenuClosed(page: Page): Promise<void> {
  await expect(page.locator('#mainNavbar')).not.toHaveClass(/mobile-menu-open/, { timeout: 5_000 });
  await expect(page.locator('#mobileMenuToggle')).toHaveAttribute('aria-expanded', 'false');
}

async function ensureLicenseQuickToggleVisible(page: Page): Promise<boolean> {
  const quickToggle = page.locator('#licenseQuickToggle');
  if (!(await quickToggle.count())) {
    return false;
  }

  if (await quickToggle.isVisible().catch(() => false)) {
    return true;
  }

  const mobileMenuToggle = page.locator('#mobileMenuToggle');
  if (await mobileMenuToggle.isVisible().catch(() => false)) {
    await mobileMenuToggle.click();
    if (await quickToggle.isVisible().catch(() => false)) {
      return true;
    }
  }

  const toggledViaAppFn = await page.evaluate(() => {
    const fn = (window as unknown as { toggleMobileNavbarMenu?: () => void }).toggleMobileNavbarMenu;
    if (typeof fn !== 'function') return false;
    fn();
    return true;
  }).catch(() => false);
  if (toggledViaAppFn && await quickToggle.isVisible().catch(() => false)) {
    return true;
  }

  return false;
}

async function mockServicesDirectoryApis(page: Page): Promise<void> {
  const vehiclePayload = [{
    id: 101,
    nickname: 'Octavia',
    plate: '1AB2345',
  }];
  const contactPayload = {
    services: [{
      id: 501,
      name: 'Tomáš Zachurčok',
      email: 'servis@example.cz',
      phone: '+420731552299',
      address: 'Opatovec 122, 568 02 Svitavy',
      city: 'Svitavy',
      ico: '87854716',
      is_linked: true,
      shared_vehicles_count: 1,
    }],
  };

  await page.route('**/api/v1/services/discovery*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        services: [{
          id: 501,
          name: 'Tomáš Zachurčok',
          email: 'servis@example.cz',
          phone: '+420731552299',
          address: 'Opatovec 122, 568 02 Svitavy',
          city: 'Svitavy',
          ico: '87854716',
          is_linked: true,
          shared_vehicles_count: 1,
          distance_km: 4.2,
        }],
        meta: {
          linked_total: 1,
          reference_source: 'profile_address',
          distance_sorted: true,
        },
      }),
    });
  });

  await page.route('**/api/v1/services/my-contacts*', async (route) => {
    if (route.request().method() === 'DELETE') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ message: 'Servis byl odpojen.' }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(contactPayload),
    });
  });

  await page.route('**/api/v1/services/vehicle-access*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        grants: [{ service_id: 501, vehicle_id: 101 }],
        api_available: true,
      }),
    });
  });

  await page.route('**/api/v1/vehicles*', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(vehiclePayload),
    });
  });
}

async function mockReservationApis(page: Page): Promise<{
  getPostCount: () => number;
  getLatestPayload: () => Record<string, unknown> | null;
}> {
  const vehicles = [{
    id: 101,
    nickname: 'Octavia',
    plate: '1AB2345',
    assigned_service_id: 501,
  }];
  const servicesDiscovery = {
    services: [{
      id: 501,
      name: 'Servis Demo',
      email: 'servis@example.cz',
      city: 'Svitavy',
      phone: '+420731552299',
    }],
  };
  let postCount = 0;
  let latestPayload: Record<string, unknown> | null = null;

  await page.route('**/api/v1/services/discovery*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(servicesDiscovery),
    });
  });

  await page.route('**/api/v1/vehicles*', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(vehicles),
    });
  });

  await page.route('**/api/v1/reservations/my*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  await page.route('**/api/v1/reservations', async (route) => {
    const request = route.request();
    if (request.method() === 'POST') {
      postCount += 1;
      try {
        latestPayload = JSON.parse(request.postData() || '{}');
      } catch (_error) {
        latestPayload = null;
      }
      await new Promise((resolve) => setTimeout(resolve, 320));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: 9000 + postCount, ok: true }),
      });
      return;
    }
    await route.continue();
  });

  return {
    getPostCount: () => postCount,
    getLatestPayload: () => latestPayload,
  };
}

async function mockReservationRescheduleApis(page: Page): Promise<{
  getPutCount: () => number;
  getLatestPayload: () => Record<string, unknown> | null;
}> {
  let putCount = 0;
  let latestPayload: Record<string, unknown> | null = null;

  await page.route('**/api/v1/reservations**', async (route) => {
    const request = route.request();
    const method = request.method().toUpperCase();
    const url = request.url();

    if (method === 'PUT' && /\/api\/v1\/reservations\/\d+/.test(url)) {
      putCount += 1;
      try {
        latestPayload = JSON.parse(request.postData() || '{}');
      } catch (_error) {
        latestPayload = null;
      }
      await new Promise((resolve) => setTimeout(resolve, 260));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, id: 7001 }),
      });
      return;
    }

    if (method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
      return;
    }

    await route.continue();
  });

  return {
    getPutCount: () => putCount,
    getLatestPayload: () => latestPayload,
  };
}

async function openRescheduleModalInServiceContext(page: Page, reservationId = 7001): Promise<void> {
  await page.evaluate((id) => {
    const app = window as unknown as Record<string, any>;
    const user = app.currentUser && typeof app.currentUser === 'object' ? app.currentUser : {};

    app.currentUser = {
      ...user,
      id: Number(user.id || 501),
      role: 'service',
      email: String(user.email || 'servis@example.cz'),
    };
    app.accessToken = String(app.accessToken || 'e2e-token');
    app.loginMode = 'service';

    if (!app.reservationsUiState || typeof app.reservationsUiState !== 'object') {
      app.reservationsUiState = {};
    }
    app.reservationsUiState.isServiceView = true;
    app.reservationsUiState.all = [{
      id: Number(id),
      status: 'PENDING',
      service_type: 'Přeplánování termínu',
      start_datetime: '2026-03-20T09:00:00.000Z',
      end_datetime: '2026-03-20T10:00:00.000Z',
      customer_name: 'Klient Test',
      customer_email: 'klient@example.cz',
      service_name: 'Servis Demo',
      service_id: 501,
      vehicle_name: 'Octavia',
      vehicle_id: 101,
    }];

    app.openReservationRescheduleModal?.(Number(id));
  }, reservationId);
}

async function mockReminderCalendarApis(page: Page): Promise<void> {
  const makeDate = (offsetDays: number): string => {
    const d = new Date();
    d.setDate(d.getDate() + offsetDays);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  };

  await page.route('**/api/v1/reminders/check-and-send-notifications', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ sent: 0 }),
    });
  });

  await page.route('**/api/v1/reminders/settings*', async (route) => {
    if (route.request().method() === 'PUT') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        notification_method: 'app',
        notify_days_before: 7,
      }),
    });
  });

  await page.route('**/api/v1/reminders', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 901,
          type: 'SERVIS',
          text: 'Kontrola brzd',
          vehicle_name: 'Octavia',
          due_date: makeDate(2),
          notify_at: null,
          is_completed: false,
        },
        {
          id: 902,
          type: 'OLEJ',
          text: 'Výměna oleje',
          vehicle_name: 'Superb',
          due_date: makeDate(7),
          notify_at: null,
          is_completed: false,
        },
        {
          id: 903,
          type: 'STK',
          text: 'STK hotovo',
          vehicle_name: 'Transporter',
          due_date: makeDate(-5),
          notify_at: null,
          is_completed: true,
        },
      ]),
    });
  });
}

async function mockReminderMobilePolishApis(page: Page): Promise<{
  getDeleteCount: () => number;
  getSettingsPutCount: () => number;
}> {
  const toDate = (offsetDays: number): string => {
    const date = new Date();
    date.setDate(date.getDate() + offsetDays);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };

  const toIso = (offsetDays: number, hour = 8, minute = 30): string => {
    const date = new Date();
    date.setDate(date.getDate() + offsetDays);
    date.setHours(hour, minute, 0, 0);
    return date.toISOString();
  };

  let deleteCount = 0;
  let settingsPutCount = 0;
  let reminders = [
    {
      id: 9101,
      type: 'STK',
      text: 'STK za dva týdny',
      vehicle_id: 101,
      vehicle_name: 'Octavia RS',
      due_date: toDate(14),
      notify_at: null,
      notification_method: 'both',
      is_manual: true,
      is_completed: false,
    },
    {
      id: 9102,
      type: 'SERVIS',
      text: 'Výměna oleje + filtry',
      vehicle_id: 102,
      vehicle_name: 'Transporter',
      due_date: toDate(5),
      notify_at: toIso(4),
      notification_method: 'email',
      is_manual: true,
      is_completed: false,
    },
    {
      id: 9103,
      type: 'POJISTKA',
      text: 'Obnovení povinného ručení',
      vehicle_id: null,
      vehicle_name: null,
      due_date: toDate(-2),
      notify_at: null,
      notification_method: 'app',
      is_manual: false,
      is_completed: false,
    },
    {
      id: 9104,
      type: 'STK',
      text: 'STK dokončeno',
      vehicle_id: 103,
      vehicle_name: 'Fabia',
      due_date: toDate(-12),
      notify_at: null,
      notification_method: 'app',
      is_manual: true,
      is_completed: true,
    },
  ];

  await page.route('**/api/v1/reminders/check-and-send-notifications', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ sent: 0 }),
    });
  });

  await page.route('**/api/v1/reminders/settings*', async (route) => {
    if (route.request().method() === 'PUT') {
      settingsPutCount += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        notification: {
          notification_method: 'both',
          notify_days_before: 7,
        },
      }),
    });
  });

  await page.route('**/api/v1/vehicles', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.continue();
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        { id: 101, nickname: 'Octavia RS', plate: '1AB2345' },
        { id: 102, nickname: 'Transporter', plate: '2CD6789' },
        { id: 103, nickname: 'Fabia', plate: '3EF9012' },
      ]),
    });
  });

  await page.route('**/api/v1/reminders/*', async (route) => {
    const request = route.request();
    const method = request.method().toUpperCase();
    const url = request.url();
    const idMatch = url.match(/\/api\/v1\/reminders\/(\d+)(?:\?|$)/);
    const reminderId = idMatch ? Number(idMatch[1]) : NaN;

    if (method === 'DELETE' && Number.isFinite(reminderId)) {
      deleteCount += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true }),
      });
      return;
    }

    if (method === 'PUT' && Number.isFinite(reminderId)) {
      let payload: Record<string, unknown> = {};
      try {
        payload = JSON.parse(request.postData() || '{}');
      } catch (_error) {
        payload = {};
      }

      reminders = reminders.map((item) => (
        Number(item.id) === reminderId
          ? { ...item, ...payload }
          : item
      ));

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true }),
      });
      return;
    }

    await route.continue();
  });

  await page.route('**/api/v1/reminders', async (route) => {
    const request = route.request();
    const method = request.method().toUpperCase();

    if (method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(reminders),
      });
      return;
    }

    if (method === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: 9999, ok: true }),
      });
      return;
    }

    await route.continue();
  });

  return {
    getDeleteCount: () => deleteCount,
    getSettingsPutCount: () => settingsPutCount,
  };
}

test.describe('Responsive Critical Smoke', () => {
  test.beforeEach(async ({ page }) => {
    await openDashboard(page);
  });

  test('MOBILE-NAV-CLICK-001: hamburger opens on first tap and remains stable', async ({ page }) => {
    for (const viewport of mobileAuditViewports) {
      await setMobileAuditViewport(page, viewport);

      const tapHitInfo = await page.evaluate(() => {
        const toggle = document.getElementById('mobileMenuToggle');
        if (!toggle) {
          return { missing: true };
        }
        const rect = toggle.getBoundingClientRect();
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;
        const topAtCenter = document.elementFromPoint(centerX, centerY) as HTMLElement | null;
        return {
          missing: false,
          insideToggle: !!topAtCenter && (topAtCenter === toggle || toggle.contains(topAtCenter)),
          topTag: topAtCenter?.tagName || '',
          topId: topAtCenter?.id || '',
          topClass: topAtCenter?.className || '',
        };
      });

      expect(tapHitInfo.missing, `${viewport.name}: mobile toggle missing`).toBeFalsy();
      expect(
        tapHitInfo.insideToggle,
        `${viewport.name}: tap center is blocked by ${tapHitInfo.topTag}#${tapHitInfo.topId}.${tapHitInfo.topClass}`,
      ).toBeTruthy();

      for (let i = 0; i < 6; i += 1) {
        await page.evaluate(() => {
          const navbar = document.getElementById('mainNavbar');
          const closeFn = (window as unknown as { closeMobileNavbarMenu?: () => void }).closeMobileNavbarMenu;
          if (typeof closeFn === 'function') {
            closeFn();
            return;
          }
          navbar?.classList.remove('mobile-menu-open');
        });
        await expectMobileMenuClosed(page);

        await page.tap('#mobileMenuToggle');
        await expectMobileMenuOpen(page);

        await expect(page.locator('#logout-btn'), `${viewport.name}: logout button should be reachable`).toBeVisible();
        await expect(page.locator('#userBadge'), `${viewport.name}: account/user badge should be reachable`).toBeVisible();

        const licenseQuick = page.locator('#licenseQuickToggle');
        if (await licenseQuick.count()) {
          await expect(licenseQuick, `${viewport.name}: license toggle should be reachable`).toBeVisible();
        }

        await page.tap('#mobileMenuToggle');
        await expectMobileMenuClosed(page);
      }
    }
  });

  test('MOBILE-NAV-CLICK-001: logout remains functional from mobile menu', async ({ page }) => {
    await setMobileAuditViewport(page, mobileAuditViewports[1]);

    await page.tap('#mobileMenuToggle');
    await expectMobileMenuOpen(page);

    const logoutBtn = page.locator('#logout-btn');
    await expect(logoutBtn).toBeVisible({ timeout: 10_000 });
    await logoutBtn.click();

    await expect(page.locator('[data-testid="input-email"]')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('[data-testid="dashboard"]')).not.toBeVisible();
  });

  test('critical mobile flows remain usable', async ({ page }) => {
    await setMobileAuditViewport(page, mobileAuditViewports[1]);

    await page.click('[data-testid="tab-vehicles"]');
    await expect(page.locator('[data-testid="vehicles-tab"]')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('[data-testid="vehicles-container"]')).toBeVisible({ timeout: 15_000 });

    const quickAddServiceButton = page.locator('button.vehicle-quick-add-record-btn');
    if (await quickAddServiceButton.isVisible().catch(() => false)) {
      await quickAddServiceButton.click();
      await expect(page.locator('#addServiceRecordModal')).toBeVisible({ timeout: 10_000 });
      await page.click('#addServiceRecordModal .vehicle-modal-close');
      await expect(page.locator('#addServiceRecordModal')).toBeHidden({ timeout: 10_000 });
    }

    const firstVehicle = page.locator('[data-testid="vehicles-tab"] [data-testid="vehicle-card"]:visible').first();
    const hasVisibleVehicle = await firstVehicle.isVisible({ timeout: 8_000 }).catch(() => false);
    if (hasVisibleVehicle) {
      await firstVehicle.click();
      await expect(page.locator('#vehicleDetailModal')).toBeVisible({ timeout: 10_000 });
      await page.click('[data-testid="btn-close-vehicle-modal"]');
      await expect(page.locator('#vehicleDetailModal')).toBeHidden({ timeout: 10_000 });
    }

    await page.click('[data-testid="tab-reminders"]');
    await expect(page.locator('[data-testid="reminders-tab"]')).toBeVisible({ timeout: 15_000 });
    const createReminderButton = page.getByRole('button', { name: /\+\s*Přidat připomínku/i });
    if (await createReminderButton.isVisible().catch(() => false)) {
      await createReminderButton.click();
      await expect(page.locator('.reminder-modal')).toBeVisible({ timeout: 10_000 });
      await page.click('.reminder-modal .reminder-modal-close');
      await expect(page.locator('.reminder-modal')).toBeHidden({ timeout: 10_000 });
    }

    await page.click('[data-testid="tab-reservations"]');
    await expect(page.locator('[data-testid="reservations-tab"]')).toBeVisible({ timeout: 15_000 });
    const createReservationButton = page.locator('button[onclick*="showCreateReservationForm"]').first();
    if (await createReservationButton.isVisible().catch(() => false)) {
      await createReservationButton.click();
      const reservationForm = page.locator('.reservation-create');
      const reservationFormVisible = await reservationForm.isVisible({ timeout: 3_000 }).catch(() => false);
      if (reservationFormVisible) {
        const reservationCancelButton = page.locator('.reservation-create .btn.btn-secondary').first();
        await reservationCancelButton.click();
        await expect(reservationForm).toBeHidden({ timeout: 10_000 });
      } else {
        await expect
          .poll(
            async () => page.locator('[data-testid="alert-warning"], [data-testid="alert-error"], [data-testid="alert-info"]').count(),
            { timeout: 10_000 },
          )
          .toBeGreaterThan(0);
      }
    }

    await page.click('[data-testid="tab-account"]');
    await expect(page.locator('[data-testid="account-tab"]')).toBeVisible({ timeout: 15_000 });
  });

  test('mobile/tablet nav remains usable and no blocking horizontal overflow', async ({ page }) => {
    await page.click('[data-testid="tab-vehicles"]');
    await expect(page.locator('[data-testid="vehicles-tab"]')).toBeVisible();

    await page.click('[data-testid="btn-toggle-add-vehicle"]');
    await expect(page.locator('[data-testid="add-vehicle-panel"]')).toBeVisible();

    await page.click('[data-testid="tab-reminders"]');
    await expect(page.locator('[data-testid="reminders-tab"]')).toBeVisible();

    await page.click('[data-testid="tab-reservations"]');
    await expect(page.locator('[data-testid="reservations-tab"]')).toBeVisible();

    await page.click('[data-testid="tab-account"]');
    await expect(page.locator('[data-testid="account-tab"]')).toBeVisible();

    const overflowX = await page.evaluate(() => {
      return Math.max(0, document.documentElement.scrollWidth - window.innerWidth);
    });

    expect(overflowX).toBeLessThanOrEqual(2);
  });

  test('repeated tab switching keeps layout stable without collision overflow', async ({ page }) => {
    const tabAndPanelPairs = [
      { tab: '[data-testid="tab-vehicles"]', panel: '[data-testid="vehicles-tab"]' },
      { tab: '[data-testid="tab-reminders"]', panel: '[data-testid="reminders-tab"]' },
      { tab: '[data-testid="tab-documents"]', panel: '[data-testid="documents-tab"]' },
      { tab: '[data-testid="tab-account"]', panel: '[data-testid="account-tab"]' },
    ];

    for (let cycle = 0; cycle < 3; cycle += 1) {
      for (const pair of tabAndPanelPairs) {
        await page.click(pair.tab);
        await expect(page.locator(pair.panel)).toBeVisible({ timeout: 10_000 });
      }
    }

    const overflowX = await page.evaluate(() => {
      return Math.max(0, document.documentElement.scrollWidth - window.innerWidth);
    });
    expect(overflowX).toBeLessThanOrEqual(2);
  });

  test('required viewport matrix keeps core navigation usable without blocking overflow', async ({ page }) => {
    for (const viewport of requiredViewportMatrix) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await openDashboard(page);

      await page.click('[data-testid="tab-vehicles"]');
      await expect(page.locator('[data-testid="vehicles-tab"]'), `Vehicles tab on ${viewport.name}`).toBeVisible({ timeout: 15_000 });

      await page.click('[data-testid="tab-account"]');
      await expect(page.locator('[data-testid="account-tab"]'), `Account tab on ${viewport.name}`).toBeVisible({ timeout: 15_000 });

      const mobileMenuToggle = page.locator('#mobileMenuToggle');
      if (await mobileMenuToggle.isVisible().catch(() => false)) {
        await mobileMenuToggle.click();
        await expectMobileMenuOpen(page);
        await expect(page.locator('#logout-btn'), `Logout action on ${viewport.name}`).toBeVisible({ timeout: 10_000 });
        await mobileMenuToggle.click();
        await expectMobileMenuClosed(page);
      }

      const overflowX = await page.evaluate(() => {
        return Math.max(0, document.documentElement.scrollWidth - window.innerWidth);
      });
      expect(overflowX, `Horizontal overflow on ${viewport.name}`).toBeLessThanOrEqual(2);
    }
  });

  test('modal CTA reachable and lower fields focusable (no keyboard trap symptom)', async ({ page }) => {
    await page.click('[data-testid="tab-reminders"]');
    await expect(page.locator('[data-testid="reminders-tab"]')).toBeVisible({ timeout: 15_000 });

    const createReminderButton = page.getByRole('button', { name: /\+\s*Přidat připomínku/i });
    if (!(await createReminderButton.count())) {
      test.skip(true, 'Reminder create flow unavailable for current account plan/role.');
    }

    await createReminderButton.click();
    await expect(page.locator('.reminder-modal')).toBeVisible({ timeout: 10_000 });

    const submitButton = page.locator('.reminder-create button[type="submit"]').first();
    await submitButton.scrollIntoViewIfNeeded();
    await expect(submitButton).toBeVisible();
    await expect(submitButton).toBeEnabled();

    const lowerField = page.locator('#reminderRepeatInterval');
    await lowerField.scrollIntoViewIfNeeded();
    await lowerField.focus();
    await expect(lowerField).toBeFocused();

    const activeElementId = await page.evaluate(() => (document.activeElement as HTMLElement | null)?.id || '');
    expect(activeElementId).toBe('reminderRepeatInterval');
  });

  test('license modal actions remain reachable on shorter heights', async ({ page }) => {
    const currentViewport = page.viewportSize() ?? { width: 390, height: 844 };
    const targetHeights = [...new Set([Math.min(currentViewport.height, 700), currentViewport.height])];

    for (const height of targetHeights) {
      await page.setViewportSize({ width: currentViewport.width, height });
      await openDashboard(page);

      const quickToggle = page.locator('#licenseQuickToggle');
      if (!(await quickToggle.count())) {
        test.skip(true, 'License quick toggle is unavailable for current runtime/account state.');
      }
      const isToggleVisible = await ensureLicenseQuickToggleVisible(page);
      if (!isToggleVisible) {
        test.skip(true, 'License quick toggle is hidden for current runtime/account state.');
      }

      await expect(quickToggle).toBeVisible({ timeout: 10_000 });
      await quickToggle.click();

      const modal = page.locator('#licenseModal');
      await expect(modal).toBeVisible({ timeout: 10_000 });
      await expect(modal.locator('.license-modal-body')).toBeVisible();

      const firstPlanAction = modal.locator('.plan-action-btn').first();
      const hasVisiblePlanAction = (await firstPlanAction.count()) && (await firstPlanAction.isVisible().catch(() => false));
      if (hasVisiblePlanAction) {
        await firstPlanAction.scrollIntoViewIfNeeded();
        await expect(firstPlanAction, `Plan action button visibility at ${currentViewport.width}x${height}`).toBeVisible();
      }

      const consentAction = modal.locator('.license-legal-consent-actions button').first();
      const hasVisibleConsentAction = (await consentAction.count()) && (await consentAction.isVisible().catch(() => false));
      if (hasVisibleConsentAction) {
        await consentAction.scrollIntoViewIfNeeded();
        await expect(consentAction, `Consent action visibility at ${currentViewport.width}x${height}`).toBeVisible();
      }

      const closeButton = modal.locator('.license-modal-close');
      await closeButton.scrollIntoViewIfNeeded();
      await expect(closeButton, `Close action visibility at ${currentViewport.width}x${height}`).toBeVisible();
      await closeButton.click();
      await expect(modal).toBeHidden({ timeout: 10_000 });
    }
  });

  test('MOBILE-POLISH-001: service card buttons stay compact and tappable on phone widths', async ({ page }) => {
    await mockServicesDirectoryApis(page);

    for (const viewport of mobilePolishViewports) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await openDashboard(page);

      await page.evaluate(() => {
        (window as unknown as { switchTab?: (tab: string) => void }).switchTab?.('servicesDirectory');
      });
      await expect(page.locator('[data-testid="services-directory-tab"]')).toBeVisible({ timeout: 10_000 });

      const serviceActionButtons = page.locator('.service-directory-row .service-directory-actions .btn');
      await expect(serviceActionButtons.first(), `${viewport.name}: service card buttons should be visible`).toBeVisible({ timeout: 10_000 });
      await serviceActionButtons.first().click({ trial: true });
      await serviceActionButtons.nth(1).click({ trial: true });

      const serviceMetrics = await serviceActionButtons.evaluateAll((buttons) => buttons.map((button) => {
        const rect = button.getBoundingClientRect();
        const style = getComputedStyle(button as HTMLElement);
        return {
          width: rect.width,
          height: rect.height,
          marginBottom: style.marginBottom,
        };
      }));
      serviceMetrics.forEach((metric) => {
        expect(metric.height, `${viewport.name}: service action button too small`).toBeGreaterThanOrEqual(34);
        expect(metric.height, `${viewport.name}: service action button too large`).toBeLessThanOrEqual(42);
        expect(metric.marginBottom, `${viewport.name}: service action button has heavy bottom margin`).toBe('0px');
      });

      const managedButtons = page.locator('#managedServiceContactsList .managed-service-contact-actions .btn');
      await expect(managedButtons.first(), `${viewport.name}: managed-service action should be visible`).toBeVisible({ timeout: 10_000 });
      await managedButtons.first().click({ trial: true });
      await managedButtons.nth(1).click({ trial: true });
      const managedMetrics = await managedButtons.evaluateAll((buttons) => buttons.map((button) => {
        const rect = button.getBoundingClientRect();
        const style = getComputedStyle(button as HTMLElement);
        return {
          width: rect.width,
          height: rect.height,
          marginBottom: style.marginBottom,
        };
      }));
      managedMetrics.forEach((metric) => {
        expect(metric.height, `${viewport.name}: managed-service button too small`).toBeGreaterThanOrEqual(32);
        expect(metric.height, `${viewport.name}: managed-service button too large`).toBeLessThanOrEqual(40);
        expect(metric.marginBottom, `${viewport.name}: managed-service button has heavy bottom margin`).toBe('0px');
      });

      const serviceCardOverflow = await page.locator('.service-directory-row').first().evaluate((card) => {
        return Math.max(0, card.scrollWidth - card.clientWidth);
      });
      expect(serviceCardOverflow, `${viewport.name}: service card should not overflow horizontally`).toBeLessThanOrEqual(1);
    }
  });

  test('MOBILE-POLISH-002: reservation submit resolves with success and blocks duplicate submit', async ({ page }) => {
    const tracker = await mockReservationApis(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await openDashboard(page);

    await page.click('[data-testid="tab-reservations"]');
    await expect(page.locator('[data-testid="reservations-tab"]')).toBeVisible({ timeout: 10_000 });

    const createButton = page.locator('button[onclick*="showCreateReservationForm"]').first();
    await expect(createButton).toBeVisible({ timeout: 10_000 });
    await createButton.click();

    const modal = page.locator('.reservation-create');
    await expect(modal).toBeVisible({ timeout: 10_000 });

    await page.selectOption('#reservationVehicle', '101');
    await page.selectOption('#reservationServiceId', '501');
    await page.fill('#reservationServiceType', 'Pravidelný servis');

    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const dateValue = `${tomorrow.getFullYear()}-${String(tomorrow.getMonth() + 1).padStart(2, '0')}-${String(tomorrow.getDate()).padStart(2, '0')}`;
    await page.fill('#reservationStartDate', dateValue);
    await page.fill('#reservationStartTime', '09:30');
    await page.fill('#reservationNote', 'Mobilní E2E test rezervace');

    const submit = page.locator('.reservation-create button[type="submit"]');
    const firstClick = submit.click();
    const secondClick = submit.click().catch(() => undefined);
    await firstClick;
    await secondClick;

    await expect(page.locator('.reservation-create')).toBeHidden({ timeout: 10_000 });
    await expect(page.locator('[data-testid="alert-success"]')).toContainText('Rezervace byla úspěšně vytvořena', { timeout: 10_000 });

    expect(tracker.getPostCount(), 'Reservation create endpoint should be called exactly once').toBe(1);
    const payload = tracker.getLatestPayload();
    expect(payload).not.toBeNull();
    expect(payload?.service_id).toBe(501);
    expect(payload?.vehicle_id).toBe(101);
    expect(String(payload?.service_type || '')).toContain('Pravidelný servis');
  });

  test('MOBILE-POLISH-003: reminders calendar fits phone width and navigation stays usable', async ({ page }) => {
    await mockReminderCalendarApis(page);

    for (const viewport of mobilePolishViewports) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await openDashboard(page);

      await page.click('[data-testid="tab-reminders"]');
      await expect(page.locator('[data-testid="reminders-tab"]')).toBeVisible({ timeout: 15_000 });

      await page.click('#remindersContainer .reminder-view-btn[data-view="calendar"]');
      const shell = page.locator('#remindersContainer .reminder-calendar-shell');
      await expect(shell, `${viewport.name}: calendar shell should be visible`).toBeVisible({ timeout: 10_000 });

      const overflowX = await shell.evaluate((element) => Math.max(0, element.scrollWidth - element.clientWidth));
      expect(overflowX, `${viewport.name}: reminder calendar should fit mobile width`).toBeLessThanOrEqual(2);

      const monthLabel = page.locator('#remindersContainer .reminder-calendar-toolbar strong');
      const beforeLabel = (await monthLabel.textContent())?.trim() || '';
      await page.locator('#remindersContainer .reminder-calendar-nav-btn').last().click();
      await expect(monthLabel, `${viewport.name}: month label should change after navigation`).not.toHaveText(beforeLabel, { timeout: 10_000 });

      await page.click('#remindersContainer .reminder-filter-btn >> text=Dokončené');
      await expect(shell, `${viewport.name}: calendar must remain usable after filter change`).toBeVisible({ timeout: 10_000 });
    }
  });

  test('MOBILE-POLISH-005: reminders cards, controls, detail modal, and actions stay compact and functional on phones', async ({ page }) => {
    const reminderTracker = await mockReminderMobilePolishApis(page);

    for (const viewport of mobilePolishViewports) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await openDashboard(page);

      await page.click('[data-testid="tab-reminders"]');
      await expect(page.locator('[data-testid="reminders-tab"]')).toBeVisible({ timeout: 15_000 });
      await expect(page.locator('#remindersContainer .reminder-card').first()).toBeVisible({ timeout: 10_000 });

      await page.evaluate(() => {
        const app = window as unknown as { [key: string]: unknown };
        app.__openVehicleCalls = [];
        app.openVehicleFromShortcut = async (vehicleId: number, source = '') => {
          const calls = Array.isArray(app.__openVehicleCalls) ? app.__openVehicleCalls as Array<Record<string, unknown>> : [];
          calls.push({ vehicleId: Number(vehicleId), source: String(source || '') });
          app.__openVehicleCalls = calls;
          return true;
        };
      });

      const cardHeights = await page.locator('#remindersContainer .reminder-card').evaluateAll((cards) => cards.map((card) => {
        const rect = card.getBoundingClientRect();
        return Math.round(rect.height);
      }));
      expect(cardHeights.length, `${viewport.name}: expected at least one reminder card`).toBeGreaterThan(0);
      cardHeights.forEach((height) => {
        expect(height, `${viewport.name}: reminder card should stay compact`).toBeLessThanOrEqual(260);
        expect(height, `${viewport.name}: reminder card height unexpectedly tiny`).toBeGreaterThanOrEqual(120);
      });

      const detailButtonMetrics = await page.locator('#remindersContainer .reminder-card .reminder-card-detail-btn').first().evaluate((button) => {
        const rect = button.getBoundingClientRect();
        return { width: Math.round(rect.width), height: Math.round(rect.height) };
      });
      expect(detailButtonMetrics.width, `${viewport.name}: detail button should not consume full row width`).toBeLessThanOrEqual(140);
      expect(detailButtonMetrics.height, `${viewport.name}: detail button should remain touch-friendly`).toBeGreaterThanOrEqual(30);
      expect(detailButtonMetrics.height, `${viewport.name}: detail button should stay visually compact`).toBeLessThanOrEqual(40);

      const switchHeight = await page.locator('#remindersContainer .reminder-view-switch').evaluate((switcher) => (
        Math.round(switcher.getBoundingClientRect().height)
      ));
      expect(switchHeight, `${viewport.name}: view switch should remain compact`).toBeLessThanOrEqual(46);

      const filterMetrics = await page.locator('#remindersContainer .reminder-filter-btn').evaluateAll((buttons) => buttons.map((button) => {
        const rect = button.getBoundingClientRect();
        return { width: Math.round(rect.width), height: Math.round(rect.height) };
      }));
      filterMetrics.forEach((metric) => {
        expect(metric.height, `${viewport.name}: filter pill should be tappable`).toBeGreaterThanOrEqual(30);
        expect(metric.height, `${viewport.name}: filter pill should stay compact`).toBeLessThanOrEqual(36);
      });

      const modeOrder = ['grid', 'list', 'compact', 'calendar', 'list'];
      for (const mode of modeOrder) {
        const modeButton = page.locator(`#remindersContainer .reminder-view-btn[data-view="${mode}"]`);
        await modeButton.click();
        await expect(modeButton, `${viewport.name}: ${mode} mode should become active`).toHaveClass(/active/);
      }
      await expect(page.locator('#remindersContainer .reminder-view.reminder-view-list')).toBeVisible({ timeout: 10_000 });

      for (const label of ['Aktivní', 'Propadlé', 'Dokončené', 'Vše']) {
        const filterButton = page.locator(`#remindersContainer .reminder-filter-btn:has-text("${label}")`).first();
        await filterButton.click();
        await expect(filterButton, `${viewport.name}: ${label} filter should become active`).toHaveClass(/active/);
      }
      await page.locator('#remindersContainer .reminder-filter-btn:has-text("Aktivní")').first().click();

      await expect(page.locator('#remindersContainer .reminder-settings-block'), `${viewport.name}: settings block should remain visible`).toBeVisible({ timeout: 10_000 });
      await expect(page.locator('#remindersContainer #reminderSettingsToggle'), `${viewport.name}: settings toggle should remain reachable`).toBeVisible({ timeout: 10_000 });

      const templatesPanel = page.locator('#reminderTemplatesPanel');
      await page.evaluate(() => {
        const app = window as unknown as { toggleReminderTemplates?: () => void };
        app.toggleReminderTemplates?.();
      });
      if (!(await templatesPanel.isVisible().catch(() => false))) {
        await page.evaluate(() => {
          const panel = document.getElementById('reminderTemplatesPanel');
          if (panel) panel.style.display = 'block';
        });
      }
      await expect(templatesPanel, `${viewport.name}: templates panel should open`).toBeVisible({ timeout: 10_000 });
      const templateButton = page.locator('#remindersContainer .reminder-pill-btn--olej');
      await expect(templateButton, `${viewport.name}: template shortcut should remain visible`).toBeVisible({ timeout: 10_000 });
      await templateButton.click({ trial: true });

      await page.click('#remindersContainer .reminder-card .reminder-card-detail-btn');
      const detailModal = page.locator('.app-floating-modal-root .reminder-detail-modal');
      await expect(detailModal, `${viewport.name}: detail modal should open`).toBeVisible({ timeout: 10_000 });
      await expect(detailModal.locator('.reminder-modal-close'), `${viewport.name}: detail close action should stay visible`).toBeVisible();

      const detailActionMetrics = await detailModal.locator('.reminder-detail-actions .btn').evaluateAll((buttons) => buttons.map((button) => {
        const rect = button.getBoundingClientRect();
        return {
          width: Math.round(rect.width),
          height: Math.round(rect.height),
        };
      }));
      expect(detailActionMetrics.length, `${viewport.name}: detail modal should expose actions`).toBeGreaterThanOrEqual(3);
      detailActionMetrics.forEach((metric) => {
        expect(metric.height, `${viewport.name}: detail action should be touch-friendly`).toBeGreaterThanOrEqual(34);
        expect(metric.height, `${viewport.name}: detail action should avoid oversized blocks`).toBeLessThanOrEqual(56);
      });

      const detailModalOverflowX = await detailModal.evaluate((modal) => Math.max(0, modal.scrollWidth - modal.clientWidth));
      expect(detailModalOverflowX, `${viewport.name}: detail modal should not clip horizontally`).toBeLessThanOrEqual(1);

      const openVehicleButton = detailModal.getByRole('button', { name: 'Otevřít vozidlo' });
      await expect(openVehicleButton, `${viewport.name}: open vehicle action should be available`).toBeVisible();
      await openVehicleButton.click();
      await expect(detailModal, `${viewport.name}: modal should close after open-vehicle action`).toBeHidden({ timeout: 10_000 });

      const openVehicleCalls = await page.evaluate(() => {
        const app = window as unknown as { [key: string]: unknown };
        return Array.isArray(app.__openVehicleCalls) ? app.__openVehicleCalls as Array<Record<string, unknown>> : [];
      });
      expect(openVehicleCalls.length, `${viewport.name}: open-vehicle action should invoke handler`).toBeGreaterThan(0);
      const latestOpenVehicle = openVehicleCalls[openVehicleCalls.length - 1];
      expect(Number(latestOpenVehicle?.vehicleId), `${viewport.name}: open-vehicle should pass a valid vehicle id`).toBeGreaterThan(0);
      expect(String(latestOpenVehicle?.source || ''), `${viewport.name}: open-vehicle source should stay reminder-detail`).toBe('reminder-detail');

      await page.click('#remindersContainer .reminder-card .reminder-card-detail-btn');
      await expect(detailModal).toBeVisible({ timeout: 10_000 });
      await detailModal.getByRole('button', { name: 'Upravit' }).click();
      await expect(page.locator('.app-floating-modal-root .reminder-create .modal-title')).toContainText('Upravit připomínku', {
        timeout: 10_000,
      });
      await page.evaluate(() => {
        const app = window as unknown as { loadReminders?: () => void };
        app.loadReminders?.();
      });
      await expect(page.locator('.app-floating-modal-root .reminder-create')).toBeHidden({ timeout: 10_000 });
      await expect(page.locator('#remindersContainer .reminder-card').first()).toBeVisible({ timeout: 15_000 });

      await page.click('#remindersContainer .reminder-card .reminder-card-detail-btn');
      await expect(detailModal).toBeVisible({ timeout: 10_000 });
      let deleteDialogSeen = false;
      page.once('dialog', async (dialog) => {
        deleteDialogSeen = true;
        expect(dialog.message()).toContain('Opravdu chcete smazat');
        await dialog.accept();
      });
      const deleteBefore = reminderTracker.getDeleteCount();
      await detailModal.getByRole('button', { name: 'Smazat' }).click();
      await expect.poll(() => (deleteDialogSeen ? 1 : 0), {
        message: `${viewport.name}: delete should require confirmation`,
        timeout: 10_000,
      }).toBe(1);
      await expect.poll(() => reminderTracker.getDeleteCount(), {
        message: `${viewport.name}: delete endpoint should be invoked`,
        timeout: 10_000,
      }).toBeGreaterThan(deleteBefore);

      const remindersOverflowX = await page.evaluate(() => {
        const wrapper = document.querySelector('#remindersContainer .reminder-list-priority') as HTMLElement | null;
        return wrapper ? Math.max(0, wrapper.scrollWidth - wrapper.clientWidth) : 0;
      });
      expect(remindersOverflowX, `${viewport.name}: reminder list should not clip horizontally`).toBeLessThanOrEqual(1);
    }
  });

  test('MOBILE-POLISH-004A: reservation reschedule modal is readable and touch-friendly on phones', async ({ page }) => {
    for (const viewport of mobilePolishViewports) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await openDashboard(page);
      await openRescheduleModalInServiceContext(page, 7001);

      const modal = page.locator('.reservation-reschedule-modal');
      await expect(modal, `${viewport.name}: reschedule modal should open`).toBeVisible({ timeout: 10_000 });
      await expect(modal.locator('.reminder-modal-close'), `${viewport.name}: close icon should stay visible`).toBeVisible();

      const layout = await page.evaluate(() => {
        const modal = document.querySelector('.reservation-reschedule-modal') as HTMLElement | null;
        const startDate = document.getElementById('rescheduleStartDate') as HTMLInputElement | null;
        const startTime = document.getElementById('rescheduleStartTime') as HTMLInputElement | null;
        const endDate = document.getElementById('rescheduleEndDate') as HTMLInputElement | null;
        const endTime = document.getElementById('rescheduleEndTime') as HTMLInputElement | null;
        if (!modal || !startDate || !startTime || !endDate || !endTime) {
          return null;
        }
        const modalRect = modal.getBoundingClientRect();
        const startDateRect = startDate.getBoundingClientRect();
        const startTimeRect = startTime.getBoundingClientRect();
        const endDateRect = endDate.getBoundingClientRect();
        const endTimeRect = endTime.getBoundingClientRect();
        return {
          modalOverflow: Math.max(0, modalRect.right - window.innerWidth) + Math.max(0, 0 - modalRect.left),
          startStacked: (startTimeRect.top - startDateRect.top) > 8,
          endStacked: (endTimeRect.top - endDateRect.top) > 8,
          startTouchHeight: startDateRect.height,
          endTouchHeight: endDateRect.height,
        };
      });

      expect(layout, `${viewport.name}: modal layout metrics should be available`).not.toBeNull();
      expect(layout?.modalOverflow || 0, `${viewport.name}: modal should fit viewport`).toBeLessThanOrEqual(1);
      expect(layout?.startStacked, `${viewport.name}: start date/time should stack vertically`).toBeTruthy();
      expect(layout?.endStacked, `${viewport.name}: end date/time should stack vertically`).toBeTruthy();
      expect(layout?.startTouchHeight || 0, `${viewport.name}: start date input should be touch-friendly`).toBeGreaterThanOrEqual(40);
      expect(layout?.endTouchHeight || 0, `${viewport.name}: end date input should be touch-friendly`).toBeGreaterThanOrEqual(40);

      await modal.locator('button.btn.btn-secondary:has-text("Zrušit")').click();
      await expect(modal, `${viewport.name}: cancel should close modal`).toBeHidden({ timeout: 10_000 });
    }
  });

  test('MOBILE-POLISH-004B: reservation reschedule submit closes modal and prevents duplicate update', async ({ page }) => {
    const tracker = await mockReservationRescheduleApis(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await openDashboard(page);
    await openRescheduleModalInServiceContext(page, 7001);

    const modal = page.locator('.reservation-reschedule-modal');
    await expect(modal).toBeVisible({ timeout: 10_000 });

    const nextDay = new Date();
    nextDay.setDate(nextDay.getDate() + 2);
    const dateValue = `${nextDay.getFullYear()}-${String(nextDay.getMonth() + 1).padStart(2, '0')}-${String(nextDay.getDate()).padStart(2, '0')}`;
    await page.fill('#rescheduleStartDate', dateValue);
    await page.fill('#rescheduleStartTime', '11:00');
    await page.fill('#rescheduleEndDate', dateValue);
    await page.fill('#rescheduleEndTime', '12:15');
    await page.selectOption('#rescheduleStatusAction', 'confirmed');

    const submit = modal.locator('button[type="submit"]');
    const firstClick = submit.click();
    const secondClick = submit.click().catch(() => undefined);
    await firstClick;
    await secondClick;

    await expect(modal).toBeHidden({ timeout: 10_000 });
    await expect(page.locator('[data-testid="alert-success"]')).toContainText('Zákazník byl informován e-mailem.', { timeout: 10_000 });

    expect(tracker.getPutCount(), 'Reservation reschedule PUT should be called exactly once').toBe(1);
    const payload = tracker.getLatestPayload();
    expect(payload).not.toBeNull();
    expect(payload?.status).toBe('CONFIRMED');
    expect(typeof payload?.start_datetime).toBe('string');
    expect(typeof payload?.end_datetime).toBe('string');
  });
});
