import { test, expect } from '@playwright/test';
import { loginUser } from './helpers';

type ShellState = {
  exists: boolean;
  hiddenAttr: boolean;
  ariaHidden: string | null;
  inert: boolean;
  display: string;
  visibility: string;
  opacity: string;
  rect: { width: number; height: number };
  takesSpace: boolean;
  visible: boolean;
};

type PageSnapshot = {
  url: string;
  bodyClass: string;
  isAuthenticated: boolean;
  shellState: Record<string, ShellState>;
  shellVisibilityState: unknown;
  debugLogCount: number;
  debugLogs: unknown[];
};

const shellSelectors = {
  productSections: '#product-sections',
  authSection: '#authSection',
  appShell: '#app-shell',
  paymentFooter: '.payment-legal-footer',
  devControlRail: '#devControlRail',
  devApiPanel: '#dev-api-url-panel',
  debugPanel: '#debugPanel',
} as const;

async function captureSnapshot(page: any): Promise<PageSnapshot> {
  return page.evaluate((selectors) => {
    const readState = (selector: string) => {
      const el = document.querySelector(selector) as HTMLElement | null;
      if (!el) {
        return {
          exists: false,
          hiddenAttr: false,
          ariaHidden: null,
          inert: false,
          display: 'missing',
          visibility: 'missing',
          opacity: 'missing',
          rect: { width: 0, height: 0 },
          takesSpace: false,
          visible: false,
        };
      }

      const style = window.getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      const visible = (
        style.display !== 'none'
        && style.visibility !== 'hidden'
        && style.opacity !== '0'
        && rect.width > 0
        && rect.height > 0
      );

      return {
        exists: true,
        hiddenAttr: el.hasAttribute('hidden'),
        ariaHidden: el.getAttribute('aria-hidden'),
        inert: Boolean((el as any).inert),
        display: style.display,
        visibility: style.visibility,
        opacity: style.opacity,
        rect: { width: rect.width, height: rect.height },
        takesSpace: rect.width > 0 || rect.height > 0,
        visible,
      };
    };

    return {
      url: window.location.href,
      bodyClass: document.body.className,
      isAuthenticated: typeof (window as any).isAuthenticated === 'function'
        ? Boolean((window as any).isAuthenticated())
        : false,
      shellState: Object.fromEntries(
        Object.entries(selectors).map(([key, selector]) => [key, readState(selector)])
      ),
      shellVisibilityState: (window as any).shellVisibilityState || null,
      debugLogCount: Array.isArray((window as any).__shellGatingLogs)
        ? (window as any).__shellGatingLogs.length
        : 0,
      debugLogs: Array.isArray((window as any).__shellGatingLogs)
        ? (window as any).__shellGatingLogs.slice(-5)
        : [],
    };
  }, shellSelectors);
}

test.describe('Authenticated shell visibility', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/web/index.html');
    await loginUser(page);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 20_000 });
  });

  for (const route of ['dashboard', 'vehicles'] as const) {
    test(`only app shell is visible on ${route}`, async ({ page }) => {
      if (route === 'vehicles') {
        await page.click('[data-testid="tab-vehicles"]');
        await expect(page).toHaveURL(/\/(web\/)?app\/u\/[^/]+\/vehicles/, { timeout: 15_000 });
      } else {
        await expect(page).toHaveURL(/\/(web\/)?app\/u\/[^/]+\/dashboard/, { timeout: 15_000 });
      }

      await page.waitForTimeout(1200);
      const snapshot = await captureSnapshot(page);
      console.log(`[shell-snapshot:${route}]`, JSON.stringify(snapshot, null, 2));

      expect(snapshot.isAuthenticated).toBeTruthy();
      expect(snapshot.bodyClass).toContain('route-app-view');
      expect(snapshot.shellState.appShell.visible).toBeTruthy();
      expect(snapshot.shellState.productSections.visible).toBeFalsy();
      expect(snapshot.shellState.authSection.visible).toBeFalsy();
      expect(snapshot.shellState.paymentFooter.visible).toBeFalsy();
      expect(snapshot.shellState.devControlRail.visible).toBeFalsy();
      expect(snapshot.shellState.devApiPanel.visible).toBeFalsy();
      expect(snapshot.shellState.debugPanel.visible).toBeFalsy();
    });
  }
});
