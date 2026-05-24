import { expect, test } from '@playwright/test';

import {
  adminApiRequest,
  approveBetaApplicationAsAdmin,
  assertNoHorizontalOverflow,
  betaStablePhone,
  createVehicleForUser,
  hasBetaAdminCredentials,
  loginRegularUserViaUi,
  registerBetaE2eUser,
  submitPublicBetaApplication,
} from './beta-helpers';

test.describe('Beta Public Smoke', () => {
  test('landing page loads, audience switching works, and public form submits', async ({ page }) => {
    const landingEmail = 'e2e.beta.landing-form@example.com';
    const landingPhone = betaStablePhone('landing-form');

    await page.goto('/beta');
    await expect(page.locator('h1')).toContainText('Nechceme jen kontakty', { timeout: 15_000 });
    await assertNoHorizontalOverflow(page, 'beta landing');

    await page.locator('[data-beta-audience="service"]').click();
    await expect(page.locator('#betaApplicantType')).toHaveValue('service');
    await expect(page.locator('#betaVehicleHint')).toContainText('servisu');

    await page.locator('[data-beta-audience="company"]').click();
    await expect(page.locator('#betaApplicantType')).toHaveValue('company');
    await expect(page.locator('#betaVehicleHint')).toContainText('firmy');

    await page.fill('input[name="name"]', 'E2E Beta Landing');
    await page.fill('input[name="email"]', landingEmail);
    await page.fill('input[name="phone"]', landingPhone);
    await page.fill('input[name="vehicle_count"]', '14');
    await page.fill('textarea[name="note"]', 'E2E scénář pro veřejnou beta registraci a ověření CTA toku.');
    await page.check('input[name="gdpr_consent"]');
    await page.click('#betaApplicationForm button[type="submit"]');

    await expect(page.locator('#betaFormStatus')).toContainText('Beta přihláška', { timeout: 15_000 });
    await expect(page.locator('#betaFormStatus')).toHaveClass(/is-success/);
  });

  test('portal without token shows auth gate', async ({ page }) => {
    await page.goto('/beta/portal');
    await expect(page.locator('#portalAuthGate')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('#portalApp')).toBeHidden();
    await assertNoHorizontalOverflow(page, 'beta portal auth gate');
  });

  test('approved participant can log in through main app and send feedback in beta portal', async ({ page, request }) => {
    test.skip(!hasBetaAdminCredentials(), 'E2E_ADMIN_EMAIL a E2E_ADMIN_PASSWORD jsou potřeba pro schválený beta portal flow.');

    const user = await registerBetaE2eUser(request, 'beta.portal');
    const applicationId = await submitPublicBetaApplication(request, {
      name: 'E2E Beta Portal',
      email: user.email,
      phone: user.phone,
      applicantType: 'user',
      vehicleCount: 2,
      note: 'Chci testovat beta portál a feedback flow.',
    });
    await approveBetaApplicationAsAdmin(request, applicationId);
    await createVehicleForUser(request, user.token, `Beta Portal Vehicle ${Date.now()}`);

    await loginRegularUserViaUi(page, user.email, user.password);
    await page.goto('/beta/portal');

    await expect(page.locator('#portalApp')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('#portalFeedbackPanel')).toBeVisible();
    await expect(page.locator('#portalStatusBanner')).toContainText('Beta účet je aktivní');
    await expect(page.locator('#portalParticipantType')).toContainText('user');
    await assertNoHorizontalOverflow(page, 'beta portal approved participant');

    const feedbackTitle = `Portal feedback ${Date.now()}`;
    await page.selectOption('#portalFeedbackForm select[name="category"]', 'bug_report');
    await page.selectOption('#portalFeedbackForm select[name="severity"]', 'high');
    await page.fill('#portalFeedbackForm input[name="title"]', feedbackTitle);
    await page.fill('#portalFeedbackForm input[name="context_area"]', 'beta-portal');
    await page.fill('#portalFeedbackForm textarea[name="message"]', 'E2E beta portál ověřuje ukládání feedbacku a jeho propsání do historie.');
    await page.fill('#portalFeedbackForm input[name="route_path"]', '/beta/portal');
    await page.click('#portalFeedbackForm button[type="submit"]');

    await expect(page.locator('#portalFeedbackStatus')).toContainText('Feedback byl uložen', { timeout: 15_000 });
    await expect(page.locator('#portalFeedbackHistory')).toContainText(feedbackTitle, { timeout: 15_000 });
    await expect(page.locator('#metricFeedbackCount')).not.toHaveText('-', { timeout: 15_000 });

    const portalState = await adminApiRequest(request, 'GET', '/admin-api/beta/dashboard');
    const feedbackItems = Array.isArray(portalState.feedback) ? portalState.feedback : [];
    expect(feedbackItems.some((item) => item && typeof item === 'object' && item.title === feedbackTitle)).toBeTruthy();
  });
});
