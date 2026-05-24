import fs from 'node:fs';
import path from 'node:path';

import { expect, test } from '@playwright/test';

import { createAiReviewer, maybeEnhanceStepWithAi } from './ai-reviewer';
import {
  closeAllDynamicPanels,
  detectLicenseCheckoutRisk,
  expandDynamicPanels,
  isDynamicPanelParent,
  openDynamicPanel,
  prepareIsolatedProfileChildRun,
  PROFILE_PANEL,
  type DynamicPanelDiscovery,
} from './dynamic-panels';
import { evaluateRouteOracle } from './route-oracle';
import { buildRunSummary, publishAuditArtifacts, writeScreenshotIndex } from './report-writer';
import { classifyElement, isSafeToClick } from './safety-policy';
import type { ClickableElementDescriptor, PageObservation, UiAuditStep } from './schemas';
import {
  captureScreenshot,
  createConsoleCollector,
  createNetworkCollector,
  detectGdprSignals,
  discoverClickableElements,
  ensureDashboardReady,
  getAuditScope,
  observePage,
  restoreUiState,
} from './ui-snapshot';

const OUTPUT_ROOT = path.join(__dirname, 'output', 'audit-runs');
const MAX_AUDIT_ELEMENTS = Number(process.env.UI_AUDIT_MAX_ELEMENTS || '40');

function stepMeta(
  element: ClickableElementDescriptor,
  isolated: { isolatedChildRun: boolean; parentPanelReopened: boolean },
) {
  return {
    section_guess: element.sectionGuess,
    element_text: element.text,
    element_role: element.role,
    selector: element.selector,
    data_testid: element.dataTestId,
    discovery_phase: element.discoveryPhase || 'top-level',
    parent_element: element.parentElement ?? null,
    parent_panel: element.parentPanel ?? null,
    isolated_child_run: isolated.isolatedChildRun,
    parent_panel_reopened: isolated.parentPanelReopened,
  };
}

test.describe('UI Audit Bot — dashboard + profile panel', () => {
  test('deterministic safe-click crawl', async ({ page }, testInfo) => {
    test.setTimeout(300_000);

    const runId = `audit-${new Date().toISOString().replace(/[:.]/g, '-')}`;
    const startedAt = new Date().toISOString();
    const scope = getAuditScope();
    const runDir = path.join(OUTPUT_ROOT, runId);
    const shotsDir = path.join(runDir, 'screenshots');
    fs.mkdirSync(shotsDir, { recursive: true });

    const tracePath = path.join(runDir, 'trace.zip');
    const network = createNetworkCollector(page);
    const consoleErrors = createConsoleCollector(page);
    const aiReviewer = createAiReviewer();
    const steps: UiAuditStep[] = [];
    let dynamicPanelDiscoveries: DynamicPanelDiscovery[] = [];

    await ensureDashboardReady(page);
    await closeAllDynamicPanels(page);
    await captureScreenshot(page, path.join(shotsDir, '00-baseline.png'));

    const topLevel = (await discoverClickableElements(page, scope)).map((el) => ({
      ...el,
      discoveryPhase: 'top-level' as const,
      parentElement: null,
      parentPanel: null,
    }));

    const expanded = await expandDynamicPanels(page, topLevel);
    dynamicPanelDiscoveries = expanded.discoveries;

    const seen = new Set<string>();
    const elements: ClickableElementDescriptor[] = [];
    [...topLevel, ...expanded.extraElements].forEach((el) => {
      const key = `${el.discoveryPhase}|${el.parentPanel || ''}|${el.dataTestId}|${el.dataUappAction}|${el.text}`;
      if (seen.has(key)) return;
      seen.add(key);
      elements.push(el);
    });

    const auditElements = elements.slice(0, MAX_AUDIT_ELEMENTS);
    let stepIndex = 0;

    async function pushStep(
      element: ClickableElementDescriptor,
      isolated: { isolatedChildRun: boolean; parentPanelReopened: boolean },
      partial: Partial<UiAuditStep> & Pick<UiAuditStep, 'verdict' | 'reason' | 'actual_result' | 'before_url' | 'after_url'>,
    ): Promise<void> {
      const classification = classifyElement(element);
      steps.push({
        run_id: runId,
        step_index: stepIndex,
        ...stepMeta(element, isolated),
        action_type: classification.actionType,
        safety_class: classification.safety,
        expected_result: partial.expected_result || {},
        recommended_fix: partial.recommended_fix ?? null,
        gdpr: partial.gdpr || detectGdprSignals('', element.sectionGuess),
        trace_path: tracePath,
        ...partial,
      } as UiAuditStep);
      stepIndex += 1;
    }

    for (const element of auditElements) {
      const classification = classifyElement(element);
      const stepPrefix = String(stepIndex).padStart(3, '0');
      const isProfileChild = element.discoveryPhase === 'dynamic-child' && element.parentPanel === PROFILE_PANEL.panelId;

      let isolated = { isolatedChildRun: false, parentPanelReopened: false };
      let locator = element.selector
        ? page.locator(element.selector).first()
        : page.getByRole('button', { name: element.text.replace(/^◐\s*/, '').split('›')[0].trim() }).first();

      if (isProfileChild) {
        isolated = { isolatedChildRun: true, parentPanelReopened: false };
        const prep = await prepareIsolatedProfileChildRun(page, PROFILE_PANEL, element);
        isolated.parentPanelReopened = prep.parentPanelReopened;

        if (!prep.ready) {
          const beforeObs = await observePage(page);
          const beforeShot = path.join(shotsDir, `${stepPrefix}-before.png`);
          await captureScreenshot(page, beforeShot);
          await pushStep(element, isolated, {
            before_url: beforeObs.url,
            after_url: beforeObs.url,
            expected_result: {},
            actual_result: {
              url_changed: false,
              modal_opened: false,
              view_changed: false,
              api_calls: [],
              http_errors: [],
              console_errors: [prep.reason || 'isolated child prep failed'],
              screenshot_before: beforeShot,
              screenshot_after: beforeShot,
              trace_path: tracePath,
            },
            verdict: 'WARN',
            reason: prep.reason || 'Izolovaný child krok — panel nebo prvek nedostupný',
            recommended_fix: 'Ověřit dashboard-overview-shell a selektor profilového panelu',
            gdpr: detectGdprSignals(beforeObs.bodyTextSample, element.sectionGuess),
          });
          continue;
        }
        locator = prep.locator!;
      } else if (element.parentPanel === PROFILE_PANEL.panelId) {
        await openDynamicPanel(page, PROFILE_PANEL);
      }

      const beforeObs = await observePage(page);
      const beforeShot = path.join(shotsDir, `${stepPrefix}-before.png`);
      await captureScreenshot(page, beforeShot);

      if (!isSafeToClick(classification.safety)) {
        const oracle = evaluateRouteOracle(
          {
            section_guess: element.sectionGuess,
            element_text: element.text,
            data_testid: element.dataTestId,
            action_type: classification.actionType,
            safety_class: classification.safety,
          },
          beforeObs,
          beforeObs,
        );
        await pushStep(element, isolated, {
          before_url: beforeObs.url,
          after_url: beforeObs.url,
          expected_result: {
            expected_view: oracle.expected.expected_view,
            expected_modal: oracle.expected.expected_modal,
          },
          actual_result: {
            url_changed: false,
            modal_opened: false,
            view_changed: false,
            api_calls: [...network.apiCalls].slice(-5),
            http_errors: [...network.httpErrors],
            console_errors: [...consoleErrors].slice(-5),
            screenshot_before: beforeShot,
            screenshot_after: beforeShot,
            trace_path: tracePath,
          },
          verdict: oracle.verdict,
          reason: classification.reason,
          recommended_fix: oracle.recommended_fix,
          gdpr: detectGdprSignals(beforeObs.bodyTextSample, element.sectionGuess),
        });
        continue;
      }

      if (!isProfileChild && !(await locator.isVisible().catch(() => false))) {
        await pushStep(element, isolated, {
          before_url: beforeObs.url,
          after_url: beforeObs.url,
          expected_result: {},
          actual_result: {
            url_changed: false,
            modal_opened: false,
            view_changed: false,
            api_calls: [],
            http_errors: [],
            console_errors: ['element not visible at audit time'],
            screenshot_before: beforeShot,
            screenshot_after: beforeShot,
            trace_path: tracePath,
          },
          verdict: 'WARN',
          reason: 'Prvek nebyl viditelný při auditu',
          recommended_fix: 'Zkontrolovat selektor nebo timing',
          gdpr: detectGdprSignals(beforeObs.bodyTextSample, element.sectionGuess),
        });
        continue;
      }

      const consoleBeforeLen = consoleErrors.length;
      const apiBeforeLen = network.apiCalls.length;
      const bodyClassBefore = await page.evaluate(() => document.body.className).catch(() => '');

      try {
        await locator.click({ timeout: 5000 });
      } catch (err) {
        await pushStep(element, isolated, {
          before_url: beforeObs.url,
          after_url: page.url(),
          expected_result: {},
          actual_result: {
            url_changed: false,
            modal_opened: false,
            view_changed: false,
            api_calls: [],
            http_errors: [],
            console_errors: [`click failed: ${String(err)}`],
            screenshot_before: beforeShot,
            screenshot_after: beforeShot,
            trace_path: tracePath,
          },
          verdict: 'FAIL',
          reason: `Klik selhal: ${String(err)}`,
          recommended_fix: 'Zkontrolovat selektor a viditelnost prvku',
          gdpr: detectGdprSignals(beforeObs.bodyTextSample, element.sectionGuess),
        });
        continue;
      }

      await page.waitForTimeout(600);
      const afterObs = await observePage(page);
      const afterShot = path.join(shotsDir, `${stepPrefix}-after.png`);
      await captureScreenshot(page, afterShot);

      let oracle = evaluateRouteOracle(
        {
          section_guess: element.sectionGuess,
          element_text: element.text,
          data_testid: element.dataTestId,
          action_type: classification.actionType,
          safety_class: classification.safety,
        },
        beforeObs,
        afterObs,
      );

      let reason = oracle.reason;
      let verdict = oracle.verdict;
      let recommendedFix = oracle.recommended_fix;

      if (element.text.includes('Jak na to') || element.dataTestId === 'dashboard-profile-menu-help') {
        if (afterObs.openModals.some((m) => /help|how|navod|návod/i.test(m))) {
          verdict = 'PASS';
          reason = 'Help modal/panel otevřen';
          recommendedFix = null;
        }
      }

      if (element.text.includes('Nastavení')) {
        if (afterObs.url.includes('/settings') || afterObs.activeView === 'settings' || afterObs.accountSettingsVisible) {
          verdict = 'PASS';
          reason = 'Navigace do nastavení účtu (settings/profile)';
          recommendedFix = null;
        }
      }

      if (
        element.dataTestId === 'dashboard-profile-menu-license-plan'
        || element.text.includes('Licence')
      ) {
        const checkoutRisk = await detectLicenseCheckoutRisk(page);
        if (checkoutRisk) {
          verdict = 'FAIL';
          reason = 'Licence modal otevřel checkout/platbu — audit nekliká na platbu';
          recommendedFix = 'Oddělit prohlížení licence od checkout flow v audit režimu';
        } else if (afterObs.openModals.some((m) => m.includes('license'))) {
          verdict = 'PASS';
          reason = 'Licence modal otevřen bez checkout redirectu';
          await page.keyboard.press('Escape').catch(() => {});
        }
      }

      if (element.dataTestId === 'dashboard-profile-menu-theme' || /motiv/i.test(element.text)) {
        const bodyClassAfter = await page.evaluate(() => document.body.className).catch(() => '');
        const fatalConsole = consoleErrors.slice(consoleBeforeLen).some((e) => /uncaught|fatal|syntaxerror/i.test(e));
        if (fatalConsole) {
          verdict = 'FAIL';
          reason = 'Theme toggle způsobil fatal JS error';
        } else if (bodyClassBefore === bodyClassAfter) {
          verdict = verdict === 'PASS' ? 'WARN' : verdict;
          reason = `${reason} | Theme toggle bez detekovatelné změny stavu`;
        } else {
          verdict = verdict === 'WARN' ? 'PASS' : verdict;
          reason = 'Theme toggle proběhl bez fatal JS erroru';
        }
      }

      let step: UiAuditStep = {
        run_id: runId,
        step_index: stepIndex,
        ...stepMeta(element, isolated),
        before_url: beforeObs.url,
        after_url: afterObs.url,
        action_type: classification.actionType,
        safety_class: classification.safety,
        expected_result: {
          expected_view: oracle.expected.expected_view,
          expected_modal: oracle.expected.expected_modal,
        },
        actual_result: {
          url_changed: beforeObs.url !== afterObs.url,
          modal_opened: afterObs.openModals.length > beforeObs.openModals.length,
          view_changed: beforeObs.activeTab !== afterObs.activeTab || beforeObs.activeView !== afterObs.activeView,
          api_calls: network.apiCalls.slice(apiBeforeLen, apiBeforeLen + 10),
          http_errors: network.httpErrors.slice(-5),
          console_errors: consoleErrors.slice(consoleBeforeLen, consoleBeforeLen + 5),
          screenshot_before: beforeShot,
          screenshot_after: afterShot,
          trace_path: tracePath,
        },
        verdict,
        reason,
        recommended_fix: recommendedFix,
        gdpr: detectGdprSignals(afterObs.bodyTextSample, element.sectionGuess),
      };

      step = await maybeEnhanceStepWithAi(step, aiReviewer, beforeShot, afterShot);
      steps.push(step);
      stepIndex += 1;

      if (isProfileChild) {
        // Další child krok si sám obnoví dashboard + panel — zde jen krátká pauza.
        await page.waitForTimeout(200);
      } else {
        await restoreUiState(page, beforeObs);
        await closeAllDynamicPanels(page);
        if (isDynamicPanelParent(element)) {
          await openDynamicPanel(page, PROFILE_PANEL);
        }
      }
    }

    const profilePanelChildCount = auditElements.filter((e) => e.discoveryPhase === 'dynamic-child').length;

    const summary = buildRunSummary(
      runId,
      scope,
      process.env.BASE_URL || 'http://127.0.0.1:8000',
      startedAt,
      steps,
      dynamicPanelDiscoveries,
      profilePanelChildCount,
      auditElements.length,
    );
    writeScreenshotIndex(summary, runDir);

    const pwTrace = path.join(testInfo.outputDir, 'trace.zip');
    const traceSource = fs.existsSync(pwTrace) ? pwTrace : undefined;
    const published = publishAuditArtifacts(summary, runDir, traceSource);

    await testInfo.attach('ui-audit-report-json', {
      path: published.reportJson,
      contentType: 'application/json',
    });
    await testInfo.attach('ui-audit-report-md', {
      path: published.reportMd,
      contentType: 'text/markdown',
    });

    // eslint-disable-next-line no-console
    console.log('[UI Audit Bot]', {
      runId,
      scope,
      total: summary.total_elements,
      profilePanelChildren: summary.profile_panel_child_count,
      safe: summary.safe_count,
      warn: summary.warn_count,
      blocked: summary.blocked_count,
      failRedirects: summary.fail_redirect_count,
      overall: summary.overall_verdict,
      dynamicPanels: summary.dynamic_panels,
      report: published.reportMd,
    });

    expect(summary.total_elements, 'audit should discover clickable elements').toBeGreaterThan(0);
    expect(summary.profile_panel_child_count, 'profile panel should expose menu items').toBeGreaterThanOrEqual(5);

    const logoutStep = steps.find((s) => s.data_testid === 'dashboard-profile-menu-logout' || s.element_text.includes('Odhlásit se'));
    expect(logoutStep?.safety_class).toBe('BLOCKED');
    expect(logoutStep?.isolated_child_run).toBe(true);
    expect(logoutStep?.parent_panel_reopened).toBe(true);

    const profileChildren = steps.filter((s) => s.discovery_phase === 'dynamic-child');
    expect(profileChildren.every((s) => s.isolated_child_run)).toBe(true);
    expect(profileChildren.every((s) => s.parent_panel_reopened)).toBe(true);

    if (summary.overall_verdict === 'FAIL') {
      test.info().annotations.push({
        type: 'ui-audit-verdict',
        description: `FAIL — viz ${published.reportMd}`,
      });
    }
    expect(summary.overall_verdict, `UI audit FAIL — report: ${published.reportMd}`).not.toBe('FAIL');
    expect(['PASS', 'WARN']).toContain(summary.overall_verdict);
  });
});
