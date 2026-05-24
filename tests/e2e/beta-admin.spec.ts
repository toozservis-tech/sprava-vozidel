import { expect, test, type Page } from '@playwright/test';

import {
  adminApiRequest,
  betaStablePhone,
  createVehicleForUser,
  hasBetaAdminCredentials,
  loginDeveloperAdminApi,
  openDeveloperAdmin,
  registerBetaE2eUser,
  submitPublicBetaApplication,
} from './beta-helpers';

async function openBetaAdminSection(page: Page): Promise<void> {
  const betaNav = page.locator('button.nav-item[data-section="beta-program"]');
  await expect(betaNav).toBeVisible({ timeout: 15_000 });
  await betaNav.click();
  await expect(page.locator('#section-beta-program')).toBeVisible({ timeout: 15_000 });
  await expect(page.locator('#beta-admin-status')).not.toHaveText('Čeká na načtení beta dashboardu.', { timeout: 15_000 });
}

test.describe('Beta Admin Smoke', () => {
  test('developer admin can link, approve, review feedback, refresh metrics and grant reward from UI', async ({ page, request }) => {
    test.skip(!hasBetaAdminCredentials(), 'E2E_ADMIN_EMAIL a E2E_ADMIN_PASSWORD jsou potřeba pro beta admin smoke.');

    const user = await registerBetaE2eUser(request, 'beta.admin.approve');
    const applicationId = await submitPublicBetaApplication(request, {
      name: 'E2E Fleet Applicant',
      email: 'e2e.beta.external-applicant@example.com',
      phone: betaStablePhone('external-applicant'),
      applicantType: 'company',
      vehicleCount: 9,
      note: 'E2E scénář pro ruční link a schválení v developer adminu.',
    });

    await openDeveloperAdmin(page, request);
    await openBetaAdminSection(page);
    await expect(page.locator('#beta-applications-table')).toContainText(String(applicationId), { timeout: 15_000 });

    await page.fill('#beta-application-id', String(applicationId));
    await page.fill('#beta-link-user-id', String(user.userId));
    await page.fill('#beta-link-reason', 'E2E ruční přiřazení na existující účet a schválení pro beta test.');
    await page.click('button:has-text("Uložit link")');

    await expect(page.locator('#beta-applications-table')).toContainText(`user:${user.email}`, { timeout: 15_000 });

    page.once('dialog', (dialog) => dialog.accept());
    await page.click('button:has-text("Schválit účastníka")');
    await expect(page.locator('#beta-participants-table')).toContainText(user.email, { timeout: 20_000 });

    const participantId = Number(await page.locator('#beta-participant-id').inputValue());
    expect(participantId).toBeGreaterThan(0);

    await createVehicleForUser(request, user.token, `Beta Admin Vehicle ${Date.now()}`);
    const feedbackResponse = await request.post('/beta/feedback', {
      headers: { Authorization: `Bearer ${user.token}` },
      data: {
        category: 'bug_report',
        title: `Admin beta bug ${Date.now()}`,
        message: 'E2E scénář ověřuje review feedbacku a reward flow v developer admin sekci.',
        severity: 'high',
        context_area: 'beta-admin',
        route_path: '/beta/portal',
      },
    });
    const feedbackPayload = await feedbackResponse.json().catch(() => ({}));
    expect(feedbackResponse.ok(), `Vytvoření beta feedbacku selhalo: ${JSON.stringify(feedbackPayload)}`).toBeTruthy();
    const feedbackId = Number(feedbackPayload.feedback?.id || 0);
    expect(feedbackId).toBeGreaterThan(0);

    await page.fill('#beta-participant-id', String(participantId));
    await page.click('button:has-text("Přepočítat scoring")');
    await expect(page.locator('#beta-admin-status')).toContainText('Načteno:', { timeout: 15_000 });

    await page.fill('#beta-feedback-id', String(feedbackId));
    await page.selectOption('#beta-feedback-status', 'planned');
    await page.fill('#beta-feedback-note', 'Zařazeno do E2E roadmapy beta admin validace.');
    await page.click('button:has-text("Uložit feedback review")');
    await expect(page.locator('#beta-feedback-table')).toContainText('planned', { timeout: 15_000 });

    await page.fill('#beta-participant-id', String(participantId));
    await page.selectOption('#beta-reward-decision', 'grant');
    await page.fill('#beta-reward-reason', 'E2E ověření ručního lifetime Premium přidělení přes admin UI.');
    page.once('dialog', (dialog) => dialog.accept());
    await page.click('button:has-text("Uložit reward rozhodnutí")');

    await expect(page.locator('#beta-rewards-table')).toContainText(String(participantId), { timeout: 20_000 });
    await expect(page.locator('#beta-rewards-table')).toContainText('granted');

    const dashboard = await adminApiRequest(request, 'GET', '/admin-api/beta/dashboard');
    const rewardItems = Array.isArray(dashboard.rewards) ? dashboard.rewards : [];
    expect(
      rewardItems.some(
        (item) => item && typeof item === 'object' && Number((item as { participant_id?: unknown }).participant_id || 0) === participantId,
      ),
    ).toBeTruthy();
  });

  test('developer admin can reject beta application from UI with explicit reason', async ({ page, request }) => {
    test.skip(!hasBetaAdminCredentials(), 'E2E_ADMIN_EMAIL a E2E_ADMIN_PASSWORD jsou potřeba pro beta admin smoke.');

    const applicantEmail = 'e2e.beta.reject-applicant@example.com';
    const applicationId = await submitPublicBetaApplication(request, {
      name: 'E2E Reject Applicant',
      email: applicantEmail,
      phone: betaStablePhone('reject-applicant'),
      applicantType: 'service',
      vehicleCount: 4,
      note: 'E2E scénář pro zamítnutí v admin sekci.',
    });

    await openDeveloperAdmin(page, request);
    await openBetaAdminSection(page);
    await expect(page.locator('#beta-applications-table')).toContainText(String(applicationId), { timeout: 15_000 });

    await page.fill('#beta-application-id', String(applicationId));
    await page.fill('#beta-link-reason', 'E2E reject důvod pro ověření auditního a review flow.');
    page.once('dialog', (dialog) => dialog.accept());
    await page.click('button:has-text("Zamítnout")');

    await expect(page.locator('#beta-admin-status')).toContainText('Načteno:', { timeout: 15_000 });
    await expect(page.locator('#beta-applications-table')).not.toContainText(applicantEmail);

    const session = await loginDeveloperAdminApi(request);
    const rejectedResponse = await request.get('/admin-api/beta/dashboard', {
      headers: { Authorization: `Bearer ${session.token}` },
    });
    const rejectedPayload = await rejectedResponse.json().catch(() => ({}));
    expect(rejectedResponse.ok()).toBeTruthy();
    const applications = Array.isArray(rejectedPayload.applications) ? rejectedPayload.applications : [];
    const rejected = applications.find(
      (item: unknown) => item && typeof item === 'object' && Number((item as { id?: unknown }).id || 0) === applicationId,
    ) as { status?: string; decision_reason?: string } | undefined;

    expect(rejected?.status).toBe('rejected');
    expect(rejected?.decision_reason || '').toContain('E2E reject důvod');
  });
});
