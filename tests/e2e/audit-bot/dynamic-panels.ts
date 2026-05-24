import type { Page } from '@playwright/test';

import type { ClickableElementDescriptor } from './schemas';

export type DynamicPanelDefinition = {
  panelId: string;
  panelLabel: string;
  parentTestId: string;
  parentAction: string | null;
  panelSelector: string;
  childSelector: string;
};

export type DynamicPanelDiscovery = {
  panel_id: string;
  panel_label: string;
  parent_element: string;
  parent_panel: string | null;
  child_count: number;
  child_testids: string[];
};

export const PROFILE_PANEL: DynamicPanelDefinition = {
  panelId: 'mobileProfileMenu',
  panelLabel: 'user-app-next profile dropdown (#mobileProfileMenu)',
  parentTestId: 'dashboard-profile',
  parentAction: 'profile',
  panelSelector: '#mobileProfileMenu.is-open, #mobileProfileMenu:not([hidden])',
  childSelector: '.mobile-profile-actions button.mobile-profile-action',
};

export const DYNAMIC_PANELS: DynamicPanelDefinition[] = [PROFILE_PANEL];

function labelText(raw: string): string {
  return raw.replace(/\s+/g, ' ').trim();
}

export function isDynamicPanelParent(element: ClickableElementDescriptor): DynamicPanelDefinition | null {
  for (const panel of DYNAMIC_PANELS) {
    if (element.dataTestId === panel.parentTestId) return panel;
    if (panel.parentAction && element.dataUappAction === panel.parentAction) return panel;
  }
  return null;
}

export async function isPanelOpen(page: Page, panel: DynamicPanelDefinition): Promise<boolean> {
  return page.locator(panel.panelSelector).first().isVisible().catch(() => false);
}

export async function openDynamicPanel(page: Page, panel: DynamicPanelDefinition): Promise<boolean> {
  if (await isPanelOpen(page, panel)) return true;

  const triggerSelectors = [
    `[data-testid="${panel.parentTestId}"]`,
    '[data-testid="app-profile-button-desktop"]',
  ];
  let clicked = false;
  for (const selector of triggerSelectors) {
    const trigger = page.locator(selector).first();
    if (await trigger.isVisible().catch(() => false)) {
      await trigger.click({ timeout: 5000 });
      clicked = true;
      break;
    }
  }
  if (!clicked) return false;

  await page.locator(panel.panelSelector).first().waitFor({ state: 'visible', timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(350);
  return isPanelOpen(page, panel);
}

export async function closeDynamicPanel(page: Page, panel: DynamicPanelDefinition): Promise<void> {
  if (!(await isPanelOpen(page, panel))) return;
  await page.locator('#mobileProfileMenu .mobile-profile-backdrop').click({ timeout: 2000 }).catch(async () => {
    await page.keyboard.press('Escape');
  });
  await page.waitForTimeout(250);
}

export async function closeAllDynamicPanels(page: Page): Promise<void> {
  for (const panel of DYNAMIC_PANELS) {
    await closeDynamicPanel(page, panel);
  }
}

export async function discoverDynamicPanelChildren(
  page: Page,
  panel: DynamicPanelDefinition,
  parent: ClickableElementDescriptor,
): Promise<ClickableElementDescriptor[]> {
  if (!(await isPanelOpen(page, panel))) return [];

  const parentLabel = labelText(parent.text) || parent.dataTestId || panel.parentTestId;
  const handles = await page.locator(`${panel.panelSelector} ${panel.childSelector}`).elementHandles();
  const results: ClickableElementDescriptor[] = [];
  const seen = new Set<string>();

  for (let index = 0; index < handles.length; index += 1) {
    const handle = handles[index];
    const meta = await handle.evaluate((node, idx) => {
      const labelEl = node.querySelector('.mobile-profile-action-label');
      const label = labelEl ? (labelEl.textContent || '') : (node.textContent || '');
      const testId = node.getAttribute('data-testid');
      const onclick = node.getAttribute('onclick') || '';
      const isBackdrop = node.classList.contains('mobile-profile-backdrop');
      return {
        text: label.replace(/\s+/g, ' ').trim().slice(0, 120),
        role: node.getAttribute('role') || 'button',
        tagName: node.tagName,
        dataTestId: testId,
        dataUappAction: node.getAttribute('data-uapp-action'),
        onclick,
        type: node.getAttribute('type'),
        isDanger: node.classList.contains('mobile-profile-action--danger'),
        isBackdrop,
        menuIndex: idx,
      };
    }, index);

    if (meta.isBackdrop) continue;
    if (!meta.text && !meta.dataTestId) continue;
    if (!meta.text || meta.text.length > 80) continue;

    const dedupe = `${meta.dataTestId || ''}|${meta.text}`;
    if (seen.has(dedupe)) continue;
    seen.add(dedupe);

    let selector: string | null = null;
    if (meta.dataTestId) {
      selector = `[data-testid="${meta.dataTestId}"]`;
    } else if (meta.text) {
      selector = `#mobileProfileMenu button.mobile-profile-action >> nth=${meta.menuIndex}`;
    }

    results.push({
      index,
      text: meta.text,
      role: meta.role,
      tagName: meta.tagName,
      selector,
      dataTestId: meta.dataTestId,
      dataUappAction: meta.dataUappAction,
      href: null,
      type: meta.type,
      sectionGuess: 'Profilový panel',
      discoveryPhase: 'dynamic-child',
      parentElement: parentLabel,
      parentPanel: panel.panelId,
      onclickSnippet: meta.onclick.slice(0, 160),
      isDangerAction: meta.isDanger,
    });
  }

  return results;
}

export async function expandDynamicPanels(
  page: Page,
  topLevel: ClickableElementDescriptor[],
): Promise<{ extraElements: ClickableElementDescriptor[]; discoveries: DynamicPanelDiscovery[] }> {
  const extraElements: ClickableElementDescriptor[] = [];
  const discoveries: DynamicPanelDiscovery[] = [];

  for (const panel of DYNAMIC_PANELS) {
    const parent = topLevel.find(
      (el) => el.dataTestId === panel.parentTestId || el.dataUappAction === panel.parentAction,
    );
    if (!parent) continue;

    await closeAllDynamicPanels(page);
    const opened = await openDynamicPanel(page, panel);
    if (!opened) {
      discoveries.push({
        panel_id: panel.panelId,
        panel_label: panel.panelLabel,
        parent_element: parent.dataTestId || parent.text || panel.parentTestId,
        parent_panel: null,
        child_count: 0,
        child_testids: [],
      });
      continue;
    }

    const children = await discoverDynamicPanelChildren(page, panel, parent);
    extraElements.push(...children);
    discoveries.push({
      panel_id: panel.panelId,
      panel_label: panel.panelLabel,
      parent_element: parent.dataTestId || labelText(parent.text) || panel.parentTestId,
      parent_panel: panel.panelId,
      child_count: children.length,
      child_testids: children.map((c) => c.dataTestId).filter(Boolean) as string[],
    });
    await closeDynamicPanel(page, panel);
  }

  return { extraElements, discoveries };
}

export async function detectLicenseCheckoutRisk(page: Page): Promise<boolean> {
  const url = page.url().toLowerCase();
  if (/comgate\.cz|\/payment\/|checkout=/.test(url)) return true;

  return page.evaluate(() => {
    const iframe = document.querySelector('iframe[src*="comgate"], iframe[src*="payment"]');
    if (iframe) {
      const style = getComputedStyle(iframe as HTMLElement);
      if (style.display !== 'none' && style.visibility !== 'hidden') return true;
    }

    const modal = document.getElementById('licenseModal');
    if (!modal || modal.classList.contains('hidden') || getComputedStyle(modal).display === 'none') {
      return false;
    }

    const consentBlock = document.getElementById('licenseLegalConsentBlock');
    if (consentBlock && !consentBlock.classList.contains('hidden')) return true;

    const confirmBtn = document.getElementById('licenseConfirmPaidPlanBtn') as HTMLButtonElement | null;
    if (confirmBtn && !confirmBtn.disabled) {
      const rect = confirmBtn.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) return true;
    }

    return false;
  });
}

export async function detectThemeToggle(page: Page, beforeClass: string, afterClass: string): Promise<boolean> {
  if (beforeClass !== afterClass) return true;
  return page.evaluate(() => {
    const theme = document.documentElement.getAttribute('data-theme') || document.body.getAttribute('data-theme');
    return !!theme;
  });
}

export function profileChildLabel(element: ClickableElementDescriptor): string {
  return element.text.replace(/^◐\s*/, '').trim();
}

export async function restoreDashboardBaseline(page: Page): Promise<void> {
  await page.evaluate(() => {
    if (typeof (window as unknown as { closeLicenseModal?: () => void }).closeLicenseModal === 'function') {
      (window as unknown as { closeLicenseModal: () => void }).closeLicenseModal();
    }
    if (typeof (window as unknown as { closeMobileProfileMenu?: () => void }).closeMobileProfileMenu === 'function') {
      (window as unknown as { closeMobileProfileMenu: () => void }).closeMobileProfileMenu();
    }
  }).catch(() => {});
  await page.keyboard.press('Escape').catch(() => {});
  await page.waitForTimeout(200);

  const onDashboard = await page
    .locator('[data-testid="dashboard-overview-shell"], [data-testid="user-app-next-dashboard"]')
    .first()
    .isVisible()
    .catch(() => false);

  if (!onDashboard || page.url().includes('/settings')) {
    await page.goto('/web/index.html', { waitUntil: 'domcontentloaded', timeout: 60_000 });
  }

  await page
    .locator('[data-testid="dashboard-overview-shell"], [data-testid="user-app-next-dashboard"]')
    .first()
    .waitFor({ state: 'visible', timeout: 30_000 });

  const homeTab = page.locator('[data-testid="tab-home"]');
  if (await homeTab.isVisible().catch(() => false)) {
    await homeTab.click().catch(() => {});
    await page.waitForTimeout(300);
  }

  await closeAllDynamicPanels(page);
  await page.waitForTimeout(250);
}

export async function locateProfileChild(page: Page, element: ClickableElementDescriptor) {
  if (element.dataTestId) {
    const byTestId = page.locator(`#mobileProfileMenu [data-testid="${element.dataTestId}"]`).first();
    if (await byTestId.count()) return byTestId;
  }
  const label = profileChildLabel(element);
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return page.locator('#mobileProfileMenu').getByRole('button', { name: new RegExp(escaped, 'i') }).first();
}

export type IsolatedChildPrep = {
  ready: boolean;
  parentPanelReopened: boolean;
  locator: ReturnType<Page['locator']> | null;
  reason?: string;
};

export async function prepareIsolatedProfileChildRun(
  page: Page,
  panel: DynamicPanelDefinition,
  element: ClickableElementDescriptor,
): Promise<IsolatedChildPrep> {
  await restoreDashboardBaseline(page);
  const parentPanelReopened = await openDynamicPanel(page, panel);
  if (!parentPanelReopened) {
    return {
      ready: false,
      parentPanelReopened: false,
      locator: null,
      reason: 'Parent panel se nepodařilo znovu otevřít po návratu na dashboard',
    };
  }

  const locator = await locateProfileChild(page, element);
  const visible = await locator.isVisible().catch(() => false);
  if (!visible) {
    return {
      ready: false,
      parentPanelReopened: true,
      locator: null,
      reason: 'Child prvek není viditelný po reopen parent panelu',
    };
  }

  return { ready: true, parentPanelReopened: true, locator };
}
