import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';

const attachmentFixturePath = path.join(__dirname, 'fixtures', 'sample-service-note.txt');

/**
 * Otevře modal detailu záznamu přes window.showServiceRecordDetail (stejná data jako accordion řádek).
 */
async function openServiceRecordDetailModal(page: Page, descriptionSubstring?: string): Promise<void> {
  const scope = page.locator('#vehicleDetailModal');
  let item = descriptionSubstring
    ? scope.locator('.service-history-item').filter({ hasText: descriptionSubstring }).first()
    : scope.locator('.service-history-item').first();
  if (descriptionSubstring && (await item.count()) === 0) {
    item = scope.locator('.service-history-item').first();
  }
  await expect(item).toBeVisible({ timeout: 20_000 });
  const rid = await item.getAttribute('data-record-id');
  const vid = await item.getAttribute('data-vehicle-id');
  if (!rid || !vid) {
    throw new Error('openServiceRecordDetailModal: chybí data-record-id nebo data-vehicle-id');
  }
  await page.evaluate(
    async ({ recordId, vehicleId }) => {
      const w = window as unknown as {
        showServiceRecordDetail: (r: number, v: number) => Promise<void>;
      };
      await w.showServiceRecordDetail(Number(recordId), Number(vehicleId));
    },
    { recordId: rid, vehicleId: vid },
  );
  await expect(page.locator('#serviceRecordDetailModal')).toBeVisible({ timeout: 15_000 });
}

function attachFatalErrorCollector(page: Page): string[] {
  const fatalMessages: string[] = [];
  const ignoredConsolePatterns = [
    /favicon/i,
    /download the react devtools/i,
    /ERR_ABORTED/i,
  ];
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
    if (ignoredConsolePatterns.some((pattern) => pattern.test(text))) return;
    if (!fatalConsolePatterns.some((pattern) => pattern.test(text))) return;
    fatalMessages.push(`console: ${text}`);
  });

  return fatalMessages;
}

async function ensureLoggedDashboard(page: Page): Promise<void> {
  await page.goto('/web/index.html');
  await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 20_000 });
}

async function ensureAtLeastOneVehicle(page: Page): Promise<void> {
  await page.click('[data-testid="tab-vehicles"]');
  await expect(page.locator('[data-testid="vehicles-tab"]')).toBeVisible({ timeout: 15_000 });
  await expect(page.locator('[data-testid="vehicles-container"]')).toBeVisible({ timeout: 15_000 });

  const visibleVehicleCards = page.locator('[data-testid="vehicles-tab"] [data-testid="vehicle-card"]:visible');
  const waitForVisibleVehicleCard = async (timeoutMs: number): Promise<boolean> => {
    return visibleVehicleCards.first().isVisible({ timeout: timeoutMs }).catch(() => false);
  };

  if (await visibleVehicleCards.count()) return;

  const allVehicleCards = page.locator('[data-testid="vehicles-tab"] [data-testid="vehicle-card"]');
  if (await allVehicleCards.count()) {
    const becameVisible = await waitForVisibleVehicleCard(8_000);
    if (becameVisible) return;
  }

  await page.click('[data-testid="tab-vehicles"]');
  await expect(page.locator('[data-testid="vehicles-tab"]')).toBeVisible({ timeout: 10_000 });
  await page.click('[data-testid="btn-toggle-add-vehicle"]');
  await expect(page.locator('[data-testid="add-vehicle-form"]')).toBeVisible({ timeout: 10_000 });

  const stamp = Date.now();
  const stkDate = new Date(Date.now() + 330 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
  await page.fill('[data-testid="input-vehicle-name"]', `Smoke Vehicle ${stamp}`);
  await page.fill('[data-testid="input-vehicle-plate"]', `SMK${String(stamp).slice(-4)}`);
  await page.fill('[data-testid="input-vehicle-stk-date"]', stkDate);
  await page.click('[data-testid="btn-add-vehicle"]');

  await page.click('[data-testid="tab-vehicles"]');
  await expect(page.locator('[data-testid="vehicles-tab"]')).toBeVisible({ timeout: 15_000 });
  await expect(page.locator('[data-testid="vehicles-container"]')).toBeVisible({ timeout: 15_000 });
  if (!(await waitForVisibleVehicleCard(12_000))) {
    await page.reload();
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 20_000 });
    await page.click('[data-testid="tab-vehicles"]');
    await expect(page.locator('[data-testid="vehicles-tab"]')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('[data-testid="vehicles-container"]')).toBeVisible({ timeout: 15_000 });
  }
  await expect(visibleVehicleCards.first()).toBeVisible({ timeout: 20_000 });
}

async function openFirstVehicleDetail(page: Page): Promise<void> {
  await page.click('[data-testid="tab-vehicles"]');
  await expect(page.locator('[data-testid="vehicles-tab"]')).toBeVisible({ timeout: 15_000 });
  const firstVehicle = page.locator('[data-testid="vehicles-tab"] [data-testid="vehicle-card"]:visible').first();
  const hasVisibleVehicle = await firstVehicle.isVisible({ timeout: 10_000 }).catch(() => false);
  if (!hasVisibleVehicle) {
    await page.reload();
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 20_000 });
    await page.click('[data-testid="tab-vehicles"]');
    await expect(page.locator('[data-testid="vehicles-tab"]')).toBeVisible({ timeout: 15_000 });
  }
  await expect(firstVehicle).toBeVisible({ timeout: 15_000 });
  await firstVehicle.click();
  await expect(page.locator('#vehicleDetailModal')).toBeVisible({ timeout: 10_000 });
}

async function openVehicleServisSectionInDetailModal(page: Page): Promise<void> {
  const modal = page.locator('#vehicleDetailModal');
  await expect(modal).toBeVisible({ timeout: 10_000 });
  const servisDock = modal.locator('button.vehicle-detail-dock-btn[data-vehicle-detail-tab="service"]');
  await expect(servisDock).toBeVisible({ timeout: 10_000 });
  await servisDock.click();
  await expect(modal.locator('.service-history-list')).toBeVisible({ timeout: 20_000 });
}

async function ensureAtLeastOneServiceRecord(page: Page): Promise<void> {
  await openFirstVehicleDetail(page);
  await openVehicleServisSectionInDetailModal(page);
  const firstHistoryItem = page.locator('#vehicleDetailModal .service-history-item').first();
  const hasHistoryItem = (await firstHistoryItem.count()) > 0;
  if (hasHistoryItem) {
    await expect(firstHistoryItem).toBeVisible({ timeout: 15_000 });
    return;
  }

  await page.click('[data-testid="btn-close-vehicle-modal"]');
  await expect(page.locator('#vehicleDetailModal')).toBeHidden({ timeout: 10_000 });

  const quickAddServiceButton = page.locator('button.vehicle-quick-add-record-btn');
  await expect(quickAddServiceButton).toBeVisible({ timeout: 10_000 });
  await quickAddServiceButton.click();
  await expect(page.locator('#addServiceRecordModal')).toBeVisible({ timeout: 10_000 });

  await page.click('#category-selector-btn-add');
  await page.locator('#category-dropdown-add .category-option').first().click();
  await page.fill('#serviceDescription-add', `Viewport seed record ${Date.now()}`);
  await page.fill('#serviceMileage-add', '120000');
  await page.fill('#servicePrice-add', '1000');
  await page.setInputFiles('#serviceAttachmentFile-add', attachmentFixturePath);
  await page.click('#addServiceRecordSubmitBtn');
  await expect(page.locator('#addServiceRecordModal')).toBeHidden({ timeout: 20_000 });

  await openFirstVehicleDetail(page);
  await openVehicleServisSectionInDetailModal(page);
  await expect(page.locator('#vehicleDetailModal .service-history-item').first()).toBeVisible({ timeout: 20_000 });
}

test.describe('Critical Authenticated Smoke', () => {
  test.beforeEach(async ({ page }) => {
    await ensureLoggedDashboard(page);
  });

  test('dashboard loads, tab navigation works, no fatal boot errors', async ({ page }) => {
    const fatalMessages = attachFatalErrorCollector(page);

    await page.click('[data-testid="tab-vehicles"]');
    await expect(page.locator('[data-testid="vehicles-tab"]')).toBeVisible();

    await page.click('[data-testid="tab-reminders"]');
    await expect(page.locator('[data-testid="reminders-tab"]')).toBeVisible();

    await page.click('[data-testid="tab-reservations"]');
    await expect(page.locator('[data-testid="reservations-tab"]')).toBeVisible();

    await page.click('[data-testid="tab-account"]');
    await expect(page.locator('[data-testid="account-tab"]')).toBeVisible();

    expect(fatalMessages, `Fatal browser errors:\n${fatalMessages.join('\n')}`).toEqual([]);
  });

  test('vehicles list loads, details open, and add vehicle path works', async ({ page }) => {
    await ensureAtLeastOneVehicle(page);

    await page.click('[data-testid="tab-vehicles"]');
    await expect(page.locator('[data-testid="vehicles-container"]')).toBeVisible();

    await openFirstVehicleDetail(page);
    await expect(page.locator('#vehicleDetailModal .vehicle-modal-header')).toBeVisible();

    await page.click('[data-testid="btn-close-vehicle-modal"]');
    await expect(page.locator('#vehicleDetailModal')).toBeHidden({ timeout: 10_000 });
  });

  test('service records: modal, validation, create, edit, detail, attachment preview, pdf export', async ({ page }) => {
    await ensureAtLeastOneVehicle(page);

    const quickAddServiceButton = page.locator('button.vehicle-quick-add-record-btn');
    await expect(quickAddServiceButton).toBeVisible({ timeout: 10_000 });
    await quickAddServiceButton.click();

    await expect(page.locator('#addServiceRecordModal')).toBeVisible({ timeout: 10_000 });
    await page.click('#addServiceRecordSubmitBtn');
    await expect(page.locator('#addServiceRecordFormError')).not.toHaveText('', { timeout: 10_000 });

    await page.click('#category-selector-btn-add');
    await page.locator('#category-dropdown-add .category-option').first().click();
    const createdDescription = `Smoke service record ${Date.now()}`;
    await page.fill('#serviceDescription-add', createdDescription);
    await page.fill('#serviceMileage-add', '125000');
    await page.fill('#servicePrice-add', '2450');

    const autofillCheckbox = page.locator('#serviceAttachmentAutofill-add');
    if (await autofillCheckbox.isChecked()) {
      await autofillCheckbox.uncheck();
    }
    await page.setInputFiles('#serviceAttachmentFile-add', attachmentFixturePath);

    await page.click('#addServiceRecordSubmitBtn');
    await expect(page.locator('#addServiceRecordModal')).toBeHidden({ timeout: 20_000 });

    await openFirstVehicleDetail(page);
    await openVehicleServisSectionInDetailModal(page);

    const pdfExportButton = page.locator('button.vehicle-service-btn.pdf').first();
    await expect(pdfExportButton).toBeVisible({ timeout: 10_000 });

    const historyRow = page.locator('#vehicleDetailModal .service-history-item').filter({ hasText: createdDescription }).first();
    await expect(historyRow).toBeVisible({ timeout: 20_000 });
    await openServiceRecordDetailModal(page, createdDescription);

    const attachmentButton = page.locator('.record-attachments-item').first();
    await expect(attachmentButton).toBeVisible({ timeout: 10_000 });
    const attachmentPopup = page.waitForEvent('popup', { timeout: 5_000 }).catch(() => null);
    await attachmentButton.click();
    const popupPage = await attachmentPopup;
    const attachmentModal = page.locator('#attachmentPreviewModal');
    const modalVisible = await attachmentModal.isVisible({ timeout: 3_000 }).catch(() => false);
    if (popupPage) {
      await popupPage.close();
    } else if (modalVisible) {
      await page.click('#attachmentPreviewModal .vehicle-modal-close');
      await expect(attachmentModal).toBeHidden({ timeout: 10_000 });
    }
    await expect(page.locator('#serviceRecordDetailModal')).toBeVisible({ timeout: 10_000 });

    await page.click('#serviceRecordDetailModal button:has-text("✏️ Upravit")');
    await expect(page.locator('#addServiceRecordModal')).toBeVisible({ timeout: 10_000 });

    const editDescription = page.locator('textarea[id^="serviceDescription-edit-"]').first();
    await expect(editDescription).toBeVisible({ timeout: 10_000 });
    await editDescription.fill(`Edited smoke service ${Date.now()}`);
    await page.click('#addServiceRecordModal button:has-text("Uložit změny")');

    await expect(page.locator('#addServiceRecordModal')).toBeHidden({ timeout: 20_000 });

    const downloadPromise = page.waitForEvent('download', { timeout: 15_000 }).catch(() => null);
    await pdfExportButton.click();
    const download = await downloadPromise;
    if (download) {
      const filename = download.suggestedFilename().toLowerCase();
      expect(filename).toContain('.pdf');
    } else {
      await expect(page.locator('#vehicleDetailModal')).toBeVisible({ timeout: 10_000 });
    }

    await page.click('[data-testid="btn-close-vehicle-modal"]');
    await expect(page.locator('#vehicleDetailModal')).toBeHidden({ timeout: 10_000 });
  });

  test('mobile: focus in service record edit modal keeps vehicle context and does not jump to vehicles list', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await ensureLoggedDashboard(page);
    await ensureAtLeastOneServiceRecord(page);

    await expect(page.locator('#vehicleDetailModal .service-history-item').first()).toBeVisible({ timeout: 15_000 });
    await openServiceRecordDetailModal(page);

    await page.locator('#serviceRecordDetailModal button:has-text("✏️ Upravit")').click();
    await expect(page.locator('#addServiceRecordModal')).toBeVisible({ timeout: 10_000 });

    const editDescription = page.locator('textarea[id^="serviceDescription-edit-"]').first();
    await editDescription.scrollIntoViewIfNeeded();
    await editDescription.click();
    await expect(editDescription).toBeFocused({ timeout: 10_000 });

    await page.waitForTimeout(450);
    await expect(page.locator('#addServiceRecordModal')).toBeVisible();
    await expect(page.locator('#vehicleDetailModal')).toBeVisible();
    await expect(page.locator('.tab[data-tab-key="vehicles"].active')).toHaveCount(1);

    await page.click('#addServiceRecordModal .vehicle-modal-close');
    await expect(page.locator('#addServiceRecordModal')).toBeHidden({ timeout: 10_000 });
    await page.click('[data-testid="btn-close-vehicle-modal"]');
    await expect(page.locator('#vehicleDetailModal')).toBeHidden({ timeout: 10_000 });
  });

  test('service record modals stay readable and actionable on tablet/smaller laptop viewports', async ({ page }) => {
    const targetViewports = [
      { label: 'tablet-768x1024', width: 768, height: 1024 },
      { label: 'small-laptop-1280x720', width: 1280, height: 720 },
    ];

    for (const viewport of targetViewports) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await ensureLoggedDashboard(page);
      await ensureAtLeastOneVehicle(page);

      const quickAddServiceButton = page.locator('button.vehicle-quick-add-record-btn');
      await expect(quickAddServiceButton).toBeVisible({ timeout: 10_000 });
      await quickAddServiceButton.click();
      await expect(page.locator('#addServiceRecordModal')).toBeVisible({ timeout: 10_000 });

      const addModalContent = page.locator('#addServiceRecordModal .vehicle-modal-content');
      await expect(addModalContent).toBeVisible({ timeout: 10_000 });
      const addSubmitButton = page.locator('#addServiceRecordSubmitBtn');
      await addSubmitButton.scrollIntoViewIfNeeded();
      await expect(addSubmitButton, `Add submit button on ${viewport.label}`).toBeVisible();

      const addModalBox = await addModalContent.boundingBox();
      expect(addModalBox, `Missing add modal box on ${viewport.label}`).not.toBeNull();
      if (addModalBox) {
        expect(addModalBox.width, `Add modal width overflow on ${viewport.label}`).toBeLessThanOrEqual(viewport.width + 1);
        expect(addModalBox.height, `Add modal height overflow on ${viewport.label}`).toBeLessThanOrEqual(viewport.height + 1);
      }

      await page.click('#addServiceRecordModal .vehicle-modal-close');
      await expect(page.locator('#addServiceRecordModal')).toBeHidden({ timeout: 10_000 });

      await ensureAtLeastOneServiceRecord(page);
      await openServiceRecordDetailModal(page);

      const detailModalContent = page.locator('#serviceRecordDetailModal .vehicle-modal-content');
      await expect(detailModalContent).toBeVisible({ timeout: 10_000 });
      const editButton = page.locator('#serviceRecordDetailModal button:has-text("✏️ Upravit")');
      await editButton.scrollIntoViewIfNeeded();
      await expect(editButton, `Detail edit button on ${viewport.label}`).toBeVisible();
      await editButton.click();

      await expect(page.locator('#addServiceRecordModal')).toBeVisible({ timeout: 10_000 });
      const editSaveButton = page.locator('#addServiceRecordModal button:has-text("Uložit změny")');
      await editSaveButton.scrollIntoViewIfNeeded();
      await expect(editSaveButton, `Edit save button on ${viewport.label}`).toBeVisible();

      await page.click('#addServiceRecordModal .vehicle-modal-close');
      await expect(page.locator('#addServiceRecordModal')).toBeHidden({ timeout: 10_000 });

      const detailModalCloseButton = page.locator('#serviceRecordDetailModal .vehicle-modal-close');
      const isDetailModalCloseVisible = await detailModalCloseButton.isVisible().catch(() => false);
      if (isDetailModalCloseVisible) {
        await detailModalCloseButton.click();
        await expect(page.locator('#serviceRecordDetailModal')).toBeHidden({ timeout: 10_000 });
      }

      await page.click('[data-testid="btn-close-vehicle-modal"]');
      await expect(page.locator('#vehicleDetailModal')).toBeHidden({ timeout: 10_000 });
    }
  });

  test('reminders and reservations modal paths are usable', async ({ page }) => {
    await ensureAtLeastOneVehicle(page);

    await page.click('[data-testid="tab-reminders"]');
    await expect(page.locator('[data-testid="reminders-tab"]')).toBeVisible({ timeout: 10_000 });

    const reminderCreateButton = page.getByRole('button', { name: /\+\s*Přidat připomínku/i });
    if (!(await reminderCreateButton.count())) {
      test.skip(true, 'Reminder create button not available for current plan/role.');
    }
    await reminderCreateButton.click();
    await expect(page.locator('.reminder-modal .modal-title:has-text("Nová připomínka")')).toBeVisible({ timeout: 10_000 });

    await page.click('.reminder-create button[type="submit"]');
    await expect(page.locator('#reminderText')).toBeFocused({ timeout: 10_000 });
    await page.fill('#reminderText', `Smoke reminder ${Date.now()}`);
    await page.click('.reminder-create button[type="submit"]');
    await expect(page.locator('[data-testid="reminders-tab"]')).toBeVisible({ timeout: 15_000 });

    await page.click('[data-testid="tab-reservations"]');
    await expect(page.locator('[data-testid="reservations-tab"]')).toBeVisible({ timeout: 10_000 });
    const reservationCreateButton = page.getByRole('button', { name: /Vytvořit novou rezervaci/i }).first();
    if (!(await reservationCreateButton.count())) {
      test.skip(true, 'Reservation create button not available in current mode.');
    }

    await reservationCreateButton.click();
    const reservationModalTitle = page.locator('.reminder-modal .modal-title:has-text("Nová rezervace")');
    const modalVisible = await reservationModalTitle.isVisible({ timeout: 5_000 }).catch(() => false);

    if (!modalVisible) {
      test.skip(true, 'Reservation modal is not available in current runtime state.');
    }

    await page.click('.reservation-create button[type="submit"]');
    await expect(page.locator('[data-testid="alert-error"]')).toBeVisible({ timeout: 10_000 });
    await page.click('.reservation-create button:has-text("Zrušit")');
  });

  test('profile and support forms open and basic submit path is operational', async ({ page }) => {
    await page.click('[data-testid="tab-account"]');
    await expect(page.locator('[data-testid="account-tab"]')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('#settingsSaveButton')).toBeVisible({ timeout: 15_000 });
    await page.click('#settingsSaveButton');
    await expect(page.locator('#settingsSaveButton')).toBeEnabled({ timeout: 15_000 });

    await expect(page.locator('#supportForm')).toBeVisible({ timeout: 10_000 });
    await page.fill('#supportSubject', `Smoke support ${Date.now()}`);
    await page.fill('#supportMessage', 'Smoke support request body with enough characters.');
    await page.click('#supportSubmitBtn');
    await expect(page.locator('#supportResult .alert')).toBeVisible({ timeout: 15_000 });
  });

  test('unsaved add-vehicle draft prompts only when leaving dirty form', async ({ page }) => {
    await page.click('[data-testid="tab-vehicles"]');
    await expect(page.locator('[data-testid="vehicles-tab"]')).toBeVisible({ timeout: 10_000 });
    await page.click('[data-testid="btn-toggle-add-vehicle"]');
    await expect(page.locator('[data-testid="add-vehicle-form"]')).toBeVisible({ timeout: 10_000 });

    await page.fill('[data-testid="input-vehicle-name"]', `Unsaved draft ${Date.now()}`);

    let dismissedDialogMessage = '';
    page.once('dialog', async (dialog) => {
      dismissedDialogMessage = dialog.message();
      await dialog.dismiss();
    });

    await page.click('[data-testid="tab-home"]');
    await expect(page.locator('[data-testid="vehicles-tab"]')).toBeVisible({ timeout: 10_000 });
    expect(dismissedDialogMessage).not.toEqual('');

    page.once('dialog', async (dialog) => {
      await dialog.accept();
    });

    await page.click('[data-testid="tab-home"]');
    await expect(page.locator('[data-testid="home-tab"]')).toBeVisible({ timeout: 10_000 });

    await page.click('[data-testid="tab-vehicles"]');
    await expect(page.locator('[data-testid="vehicles-tab"]')).toBeVisible({ timeout: 10_000 });
    await page.click('[data-testid="btn-toggle-add-vehicle"]');
    await expect(page.locator('[data-testid="add-vehicle-form"]')).toBeVisible({ timeout: 10_000 });
    await page.fill('[data-testid="input-vehicle-name"]', '');
    await page.fill('[data-testid="input-vehicle-plate"]', '');
    await page.fill('[data-testid="input-vehicle-stk-date"]', '');

    let unexpectedDialog = false;
    const dialogListener = async (dialog: { dismiss: () => Promise<void> }) => {
      unexpectedDialog = true;
      await dialog.dismiss();
    };

    page.on('dialog', dialogListener);
    await page.click('[data-testid="tab-home"]');
    await expect(page.locator('[data-testid="home-tab"]')).toBeVisible({ timeout: 10_000 });
    await page.waitForTimeout(250);
    page.off('dialog', dialogListener);
    expect(unexpectedDialog).toBeFalsy();
  });
});
