import fs from 'node:fs';
import path from 'node:path';

import type { Page } from '@playwright/test';

import type { ClickableElementDescriptor, PageObservation } from './schemas';

const CLICKABLE_SELECTOR = [
  'button',
  'a[href]',
  '[role="button"]',
  '[data-uapp-action]',
  '[data-testid]',
  'summary',
  'select',
  'input[type="checkbox"]',
  'input[type="radio"]',
].join(',');

export const AUDIT_SCOPE_SELECTORS: Record<string, string[]> = {
  'dashboard-profile': [
    '.uapp-next-topbar',
    '#mobileProfileMenu',
    '[data-testid="app-notifications-panel"]',
    '[data-testid="app-profile-button-desktop"]',
    '[data-testid="dashboard-profile"]',
    '[data-testid="dashboard-notifications"]',
    '[data-testid="menu-how-to-tutorial"]',
  ],
  'profile-menu-only': ['#mobileProfileMenu'],
};

export function getAuditScope(): string {
  return process.env.UI_AUDIT_SCOPE || 'dashboard-profile';
}

export function getScopeRootSelectors(scope: string): string[] {
  return AUDIT_SCOPE_SELECTORS[scope] || AUDIT_SCOPE_SELECTORS['dashboard-profile'];
}

export async function ensureDashboardReady(page: Page): Promise<void> {
  await page.goto('/web/index.html', { waitUntil: 'domcontentloaded', timeout: 120_000 });
  await page.locator('[data-testid="dashboard"]').waitFor({ state: 'visible', timeout: 30_000 });
  await page.waitForFunction(
    () => {
      const candidates = [
        '[data-testid="user-app-next-dashboard"]',
        '[data-testid="home-tab"]',
        '[data-testid="dashboard-profile"]',
      ];
      return candidates.some((sel) => {
        const el = document.querySelector(sel);
        if (!el) return false;
        const rect = (el as HTMLElement).getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
      });
    },
    null,
    { timeout: 45_000 },
  );
  await page.waitForTimeout(800);
  const homeTab = page.locator('[data-testid="tab-home"]');
  if (await homeTab.isVisible().catch(() => false)) {
    await homeTab.click();
    await page.waitForTimeout(400);
  }
}

export async function discoverClickableElements(
  page: Page,
  scope: string,
): Promise<ClickableElementDescriptor[]> {
  const roots = getScopeRootSelectors(scope);
  return page.evaluate(
    ({ selector, roots: scopeRoots, scope: auditScope }) => {
      function isVisible(el: Element): boolean {
        const html = el as HTMLElement;
        if (!html || html.offsetParent === null && getComputedStyle(html).position !== 'fixed') {
          if (html.hasAttribute('hidden') || html.getAttribute('aria-hidden') === 'true') return false;
        }
        const rect = html.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) return false;
        const style = getComputedStyle(html);
        if (style.visibility === 'hidden' || style.display === 'none' || style.pointerEvents === 'none') return false;
        return true;
      }

      function sectionGuess(el: Element): string {
        if (el.closest('#mobileProfileMenu')) return 'Profilový panel';
        if (el.closest('#appNotificationsPanel')) return 'Přehled';
        if (el.closest('[data-testid="home-tab"]')) return 'Přehled';
        if (el.closest('.uapp-next-topbar')) return 'Přehled';
        if (el.closest('.uapp-next-sidebar')) return 'Navigace';
        if (el.closest('[data-testid="user-app-next-screen"]')) return 'Přehled';
        return 'Přehled';
      }

      function buildSelector(el: Element): string | null {
        const testId = el.getAttribute('data-testid');
        if (testId) return `[data-testid="${testId}"]`;
        const action = el.getAttribute('data-uapp-action');
        if (action) return `[data-uapp-action="${action}"]`;
        const id = el.id;
        if (id) return `#${CSS.escape(id)}`;
        return null;
      }

      function isInteractive(node: Element): boolean {
        const tag = node.tagName;
        if (['BUTTON', 'A', 'SUMMARY', 'SELECT', 'INPUT'].includes(tag)) return true;
        const role = node.getAttribute('role');
        if (role === 'button' || role === 'link' || role === 'tab') return true;
        if (node.hasAttribute('data-uapp-action')) return true;
        if (node.hasAttribute('onclick')) return true;
        const testId = node.getAttribute('data-testid') || '';
        if (testId.startsWith('dashboard-nav-')) return false;
        if (/^dashboard-(overview|hero|quick|vehicle|aside|overall|topbar|search)/.test(testId)) return false;
        if (testId.startsWith('tab-')) return true;
        if (/profile|notifications|menu-how-to|dashboard-help|dashboard-add-vehicle|dashboard-collapse/.test(testId)) return true;
        return false;
      }

      function inScope(el: Element, rootsList: string[]): boolean {
        if (auditScope === 'dashboard-profile' && el.closest('.uapp-next-sidebar')) return false;
        return rootsList.some((rootSel) => {
          try {
            const root = document.querySelector(rootSel);
            if (!root) return rootSel === '[data-testid="dashboard"]' && !!document.querySelector('[data-testid="dashboard"]');
            return root.contains(el) || el === root;
          } catch {
            return false;
          }
        });
      }

      const nodes = Array.from(document.querySelectorAll(selector));
      const seen = new Set<string>();
      const results: ClickableElementDescriptor[] = [];

      nodes.forEach((node, idx) => {
        if (!isVisible(node)) return;
        if (!isInteractive(node)) return;
        if (!inScope(node, scopeRoots)) return;

        const text = (node.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 120);
        const testId = node.getAttribute('data-testid');
        const action = node.getAttribute('data-uapp-action');
        const role = node.getAttribute('role') || (node.tagName === 'A' ? 'link' : node.tagName === 'BUTTON' ? 'button' : 'generic');
        const dedupeKey = `${testId || ''}|${action || ''}|${text}|${node.tagName}`;
        if (seen.has(dedupeKey)) return;
        seen.add(dedupeKey);

        results.push({
          index: idx,
          text,
          role,
          tagName: node.tagName,
          selector: buildSelector(node),
          dataTestId: testId,
          dataUappAction: action,
          href: node.tagName === 'A' ? (node as HTMLAnchorElement).href : null,
          type: node.getAttribute('type'),
          sectionGuess: sectionGuess(node),
        });
      });

      return results;
    },
    { selector: CLICKABLE_SELECTOR, roots, scope },
  );
}

export async function observePage(page: Page): Promise<PageObservation> {
  return page.evaluate(() => {
    function isActuallyVisible(el: HTMLElement): boolean {
      if (el.hasAttribute('hidden') || el.classList.contains('hidden') || el.getAttribute('aria-hidden') === 'true') {
        return false;
      }
      const style = getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
      const rect = el.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    }

    function visibleModalIds(): string[] {
      const ids: string[] = [];
      document.querySelectorAll('[role="dialog"], .modal, .vehicle-modal, .auth-modal, [data-testid*="modal"], #licenseModal').forEach((el) => {
        const html = el as HTMLElement;
        if (!isActuallyVisible(html)) return;
        ids.push(html.getAttribute('data-testid') || html.id || html.className.split(' ')[0] || 'dialog');
      });
      return ids;
    }

    function visiblePanelIds(): string[] {
      const panelIds: string[] = [];
      const profileMenu = document.getElementById('mobileProfileMenu');
      if (profileMenu) {
        const hidden = profileMenu.hasAttribute('hidden') || profileMenu.getAttribute('aria-hidden') === 'true';
        const style = getComputedStyle(profileMenu);
        const open = profileMenu.classList.contains('is-open');
        if (!hidden && style.display !== 'none' && (open || style.visibility !== 'hidden')) {
          panelIds.push('mobileProfileMenu');
        }
      }
      const notif = document.getElementById('appNotificationsPanel');
      if (notif) {
        const hidden = notif.hasAttribute('hidden') || notif.getAttribute('aria-hidden') === 'true';
        const style = getComputedStyle(notif);
        if (!hidden && style.display !== 'none') panelIds.push('appNotificationsPanel');
      }
      return [...new Set(panelIds)];
    }

    const activeTabBtn = document.querySelector('.tab.active[data-tab-key]') as HTMLElement | null;
    const activeNavBtn = document.querySelector('.uapp-next-sidebar button.is-active[data-uapp-action]') as HTMLElement | null;
    const body = document.body;
    const accountSettingsVisible = [
      '[data-testid="account-tab"]',
      '[data-testid="tab-account"].active',
      '[data-testid="profile-container"]',
      '.uapp-settings-page',
      '[data-testid="user-app-next-settings-root"]',
    ].some((sel) => {
      const el = document.querySelector(sel) as HTMLElement | null;
      return !!el && isActuallyVisible(el);
    }) || window.location.pathname.includes('/settings');

    return {
      url: window.location.href,
      activeTab: activeTabBtn?.getAttribute('data-tab-key') || null,
      activeView: activeNavBtn?.getAttribute('data-uapp-action') || null,
      openModals: visibleModalIds(),
      openPanels: visiblePanelIds(),
      accountSettingsVisible,
      bodyTextSample: (body.innerText || '').slice(0, 1500),
    };
  });
}

export async function captureScreenshot(page: Page, filePath: string): Promise<string> {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  await page.screenshot({ path: filePath, fullPage: false });
  return filePath;
}

export async function restoreUiState(page: Page, before: PageObservation): Promise<void> {
  await page.keyboard.press('Escape').catch(() => {});
  await page.waitForTimeout(200);

  const profileOpen = await page.locator('#mobileProfileMenu:not([hidden])').isVisible().catch(() => false);
  if (profileOpen) {
    await page.locator('.mobile-profile-backdrop').click({ timeout: 2000 }).catch(async () => {
      await page.keyboard.press('Escape');
    });
  }

  const notifOpen = await page.locator('[data-testid="app-notifications-panel"]:not([hidden])').isVisible().catch(() => false);
  if (notifOpen) {
    await page.keyboard.press('Escape');
  }

  const howToOpen = await page.locator('[data-testid="how-to-hub-scroll"]').isVisible().catch(() => false);
  if (howToOpen) {
    await page.keyboard.press('Escape');
    await page.locator('.vehicle-modal-close, [aria-label="Zavřít"]').first().click({ timeout: 1500 }).catch(() => {});
  }

  await page.evaluate(() => {
    if (typeof window.closeLicenseModal === 'function') window.closeLicenseModal();
    if (typeof window.closeMobileProfileMenu === 'function') window.closeMobileProfileMenu();
  }).catch(() => {});

  if (before.activeTab && before.activeTab !== 'home') {
    const tab = page.locator(`[data-testid="tab-${before.activeTab}"]`);
    if (await tab.isVisible().catch(() => false)) {
      await tab.click().catch(() => {});
    }
  } else {
    const homeTab = page.locator('[data-testid="tab-home"]');
    if (await homeTab.isVisible().catch(() => false)) {
      await homeTab.click().catch(() => {});
    }
  }

  if (before.url && page.url() !== before.url) {
    await page.goto('/web/index.html', { waitUntil: 'domcontentloaded' }).catch(() => {});
    await page.locator('[data-testid="dashboard"], [data-testid="user-app-next-screen"]').first().waitFor({ state: 'visible', timeout: 15_000 }).catch(() => {});
  }

  await page.waitForTimeout(300);
}

export function detectGdprSignals(bodyText: string, sectionGuess: string): {
  owner_data_visible: boolean;
  vehicle_data_visible: boolean;
  vin_visible: boolean;
  spz_visible: boolean;
  public_context: boolean;
  violation: boolean;
  note: string;
} {
  const emailRe = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i;
  const vinRe = /\b[A-HJ-NPR-Z0-9]{17}\b/i;
  const spzRe = /\b[0-9][A-Z0-9]{1,7}\b/i;

  const owner_data_visible = emailRe.test(bodyText) || /licence|předplatné|session/i.test(bodyText);
  const vin_visible = vinRe.test(bodyText);
  const spz_visible = spzRe.test(bodyText) && !/^\d+$/.test(bodyText.trim());
  const vehicle_data_visible = vin_visible || spz_visible || /nájezd|STK|servisní historie/i.test(bodyText);
  const public_context = /veřejn|QR|ověřovací token/i.test(sectionGuess + bodyText);

  const violation = public_context && (owner_data_visible || vehicle_data_visible);

  let note = 'OK';
  if (violation) note = 'Veřejný kontext obsahuje citlivá data';
  else if (vehicle_data_visible && sectionGuess.includes('Profil')) note = 'Profil může zobrazovat metadata vozidla — report maskuje';

  return {
    owner_data_visible,
    vehicle_data_visible,
    vin_visible,
    spz_visible,
    public_context,
    violation,
    note,
  };
}

export function createNetworkCollector(page: Page): {
  apiCalls: string[];
  httpErrors: Array<{ url: string; status: number }>;
} {
  const apiCalls: string[] = [];
  const httpErrors: Array<{ url: string; status: number }> = [];

  page.on('response', (response) => {
    const url = response.url();
    if (/\/api\/|\/user\/|\/vehicles\/|\/license\//.test(url)) {
      apiCalls.push(`${response.request().method()} ${url} → ${response.status()}`);
      if (response.status() >= 400) {
        httpErrors.push({ url, status: response.status() });
      }
    }
  });

  return { apiCalls, httpErrors };
}

export function createConsoleCollector(page: Page): string[] {
  const errors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('pageerror', (err) => errors.push(err.message));
  return errors;
}
