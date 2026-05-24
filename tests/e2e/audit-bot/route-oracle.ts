import type { ExpectedClickRule, ExpectedTarget, UiAuditStep, UiAuditVerdict } from './schemas';
import type { PageObservation } from './schemas';

export const ROUTE_ORACLE_RULES: ExpectedClickRule[] = [
  // Přehled / dashboard
  {
    source_section: 'Přehled',
    element_text: 'Přehled',
    data_testid: 'tab-home',
    allowed_actions: ['navigate'],
    expected_target: { type: 'route', route: '/web/index.html#home' },
    destructive: false,
    requires_confirmation: false,
    gdpr_scope: 'account',
  },
  {
    source_section: 'Přehled',
    element_text: 'Přehled',
    data_testid: 'dashboard-nav-home',
    allowed_actions: ['navigate'],
    expected_target: { type: 'route', route: 'view:home' },
    destructive: false,
    requires_confirmation: false,
    gdpr_scope: 'account',
  },

  // Profilový panel
  {
    source_section: 'Profilový panel',
    element_text: 'Profil',
    data_testid: 'app-profile-button-desktop',
    allowed_actions: ['open-dropdown'],
    expected_target: { type: 'panel', panel_testid: 'mobileProfileMenu' },
    destructive: false,
    requires_confirmation: false,
    gdpr_scope: 'account',
  },
  {
    source_section: 'Profilový panel',
    element_text: 'Profil',
    data_testid: 'dashboard-profile',
    allowed_actions: ['open-dropdown'],
    expected_target: { type: 'panel', panel_testid: 'mobileProfileMenu' },
    destructive: false,
    requires_confirmation: false,
    gdpr_scope: 'account',
  },
  {
    source_section: 'Profilový panel',
    element_text: 'Jak na to',
    data_testid: 'dashboard-profile-menu-help',
    allowed_actions: ['open-modal'],
    expected_target: { type: 'modal', modal_testid: 'how-to-hub-scroll' },
    destructive: false,
    requires_confirmation: false,
    gdpr_scope: 'public',
  },
  {
    source_section: 'Profilový panel',
    element_text: 'Jak na to',
    data_testid: 'menu-how-to-tutorial',
    allowed_actions: ['open-modal'],
    expected_target: { type: 'modal', modal_testid: 'how-to-hub-scroll' },
    destructive: false,
    requires_confirmation: false,
    gdpr_scope: 'public',
  },
  {
    source_section: 'Profilový panel',
    element_text: 'Nastavení účtu',
    data_testid: 'dashboard-profile-menu-settings',
    allowed_actions: ['navigate'],
    expected_target: { type: 'route', route: 'view:settings' },
    destructive: false,
    requires_confirmation: false,
    gdpr_scope: 'account',
  },
  {
    source_section: 'Profilový panel',
    element_text: 'Licence a plán',
    data_testid: 'dashboard-profile-menu-license-plan',
    allowed_actions: ['open-modal'],
    expected_target: { type: 'modal', modal_testid: 'licenseModal' },
    destructive: false,
    requires_confirmation: false,
    gdpr_scope: 'account',
  },
  {
    source_section: 'Profilový panel',
    element_text: 'Licence a plán',
    allowed_actions: ['open-modal'],
    expected_target: { type: 'modal', modal_testid: 'licenseModal' },
    destructive: false,
    requires_confirmation: false,
    gdpr_scope: 'account',
  },
  {
    source_section: 'Profilový panel',
    element_text: 'Odhlásit se',
    data_testid: 'dashboard-profile-menu-logout',
    allowed_actions: [],
    expected_target: { type: 'blocked', reason: 'Logout — zakázáno uprostřed běhu' },
    destructive: true,
    requires_confirmation: false,
    gdpr_scope: 'account',
  },
  {
    source_section: 'Profilový panel',
    element_text: 'Světlý / tmavý motiv',
    data_testid: 'dashboard-profile-menu-theme',
    allowed_actions: ['open'],
    expected_target: { type: 'route', route: 'theme:toggle' },
    destructive: false,
    requires_confirmation: false,
    gdpr_scope: 'account',
  },

  // Oznámení
  {
    source_section: 'Přehled',
    element_text: 'Oznámení',
    data_testid: 'app-notifications-button-desktop',
    allowed_actions: ['open-dropdown'],
    expected_target: { type: 'panel', panel_testid: 'app-notifications-panel' },
    destructive: false,
    requires_confirmation: false,
    gdpr_scope: 'account',
  },
  {
    source_section: 'Přehled',
    element_text: 'Oznámení',
    data_testid: 'dashboard-notifications',
    allowed_actions: ['open-dropdown'],
    expected_target: { type: 'panel', panel_testid: 'app-notifications-panel' },
    destructive: false,
    requires_confirmation: false,
    gdpr_scope: 'account',
  },
  {
    source_section: 'Přehled',
    element_text: 'Oznámení',
    data_testid: 'app-notifications-button-mobile',
    allowed_actions: ['open-dropdown'],
    expected_target: { type: 'panel', panel_testid: 'app-notifications-panel' },
    destructive: false,
    requires_confirmation: false,
    gdpr_scope: 'account',
  },

  {
    source_section: 'Přehled',
    element_text: 'Nápověda',
    data_testid: 'dashboard-help',
    allowed_actions: ['open-modal'],
    expected_target: { type: 'modal', modal_testid: 'how-to-hub-scroll' },
    destructive: false,
    requires_confirmation: false,
    gdpr_scope: 'public',
  },
  {
    source_section: 'Přehled',
    element_text: 'Oznámení',
    data_testid: 'dashboard-notifications',
    allowed_actions: ['open-dropdown'],
    expected_target: { type: 'panel', panel_testid: 'app-notifications-panel' },
    destructive: false,
    requires_confirmation: false,
    gdpr_scope: 'account',
  },
  {
    source_section: 'Přehled',
    element_text: 'Profil',
    data_testid: 'dashboard-profile',
    allowed_actions: ['open-dropdown'],
    expected_target: { type: 'panel', panel_testid: 'mobileProfileMenu' },
    destructive: false,
    requires_confirmation: false,
    gdpr_scope: 'account',
  },

  // Sidebar navigace (pro pozdější rozšíření)
  {
    source_section: 'Moje vozidla',
    element_text: 'Moje vozidla',
    data_testid: 'dashboard-nav-vehicles',
    allowed_actions: ['navigate'],
    expected_target: { type: 'route', route: 'view:vehicles' },
    destructive: false,
    requires_confirmation: false,
    gdpr_scope: 'vehicle',
  },
  {
    source_section: 'Servisní historie',
    element_text: 'Servisní historie',
    data_testid: 'dashboard-nav-serviceHistory',
    allowed_actions: ['navigate'],
    expected_target: { type: 'route', route: 'view:serviceHistory' },
    destructive: false,
    requires_confirmation: false,
    gdpr_scope: 'vehicle',
  },
  {
    source_section: 'Připomínky',
    element_text: 'Připomínky',
    data_testid: 'dashboard-nav-reminders',
    allowed_actions: ['navigate'],
    expected_target: { type: 'route', route: 'view:reminders' },
    destructive: false,
    requires_confirmation: false,
    gdpr_scope: 'vehicle',
  },
  {
    source_section: 'Dokumenty',
    element_text: 'Dokumenty',
    data_testid: 'dashboard-nav-documents',
    allowed_actions: ['navigate'],
    expected_target: { type: 'route', route: 'view:documents' },
    destructive: false,
    requires_confirmation: false,
    gdpr_scope: 'vehicle',
  },
  {
    source_section: 'Servisy',
    element_text: 'Servisy',
    data_testid: 'dashboard-nav-servicesDirectory',
    allowed_actions: ['navigate'],
    expected_target: { type: 'route', route: 'view:servicesDirectory' },
    destructive: false,
    requires_confirmation: false,
    gdpr_scope: 'service_access',
  },
  {
    source_section: 'Faktury',
    element_text: 'Faktury',
    data_testid: 'dashboard-nav-invoices',
    allowed_actions: ['navigate'],
    expected_target: { type: 'route', route: 'view:invoices' },
    destructive: false,
    requires_confirmation: false,
    gdpr_scope: 'account',
  },
  {
    source_section: 'Nastavení',
    element_text: 'Nastavení',
    data_testid: 'dashboard-nav-settings',
    allowed_actions: ['navigate'],
    expected_target: { type: 'route', route: 'view:settings' },
    destructive: false,
    requires_confirmation: false,
    gdpr_scope: 'account',
  },
  {
    source_section: 'Nastavení',
    element_text: 'Nastavení',
    data_testid: 'tab-account',
    allowed_actions: ['navigate'],
    expected_target: { type: 'route', route: 'view:settings' },
    destructive: false,
    requires_confirmation: false,
    gdpr_scope: 'account',
  },
];

function normalizeText(value: string): string {
  return value.replace(/\s+/g, ' ').trim().toLowerCase();
}

export function findMatchingRule(
  sectionGuess: string,
  elementText: string,
  dataTestId: string | null,
): ExpectedClickRule | null {
  const textNorm = normalizeText(elementText);
  const sectionNorm = normalizeText(sectionGuess);

  if (dataTestId) {
    const byTestId = ROUTE_ORACLE_RULES.find((rule) => rule.data_testid === dataTestId);
    if (byTestId) return byTestId;
  }

  const byText = ROUTE_ORACLE_RULES.find((rule) => {
    const ruleText = normalizeText(rule.element_text);
  return ruleText === textNorm || textNorm.includes(ruleText) || ruleText.includes(textNorm);
  });
  if (byText) return byText;

  return ROUTE_ORACLE_RULES.find((rule) => normalizeText(rule.source_section) === sectionNorm) || null;
}

function targetToString(target: ExpectedTarget): string {
  switch (target.type) {
    case 'route':
      return target.route;
    case 'modal':
      return `modal:${target.modal_testid}`;
    case 'panel':
      return `panel:${target.panel_testid}`;
    case 'blocked':
      return `blocked:${target.reason}`;
    default:
      return 'unknown';
  }
}

function observationMatchesTarget(before: PageObservation, after: PageObservation, target: ExpectedTarget): boolean {
  switch (target.type) {
    case 'blocked':
      return false;
    case 'route': {
      const route = target.route;
      if (route.startsWith('view:')) {
        const view = route.slice('view:'.length);
        return after.activeView === view || after.url.includes(view);
      }
      if (route.startsWith('tab:')) {
        const tab = route.slice('tab:'.length);
        return after.activeTab === tab || after.activeView === 'settings' || after.url.includes('/settings');
      }
      if (route === 'view:settings') {
        return after.accountSettingsVisible || after.activeView === 'settings' || after.activeTab === 'account' || after.url.includes('/settings');
      }
      if (route.startsWith('theme:')) {
        return before.url === after.url;
      }
      if (route.includes('#home') || route.includes('home')) {
        return after.activeTab === 'home' || after.activeView === 'home';
      }
      return after.url.includes(route) || before.url !== after.url;
    }
    case 'modal':
      return (
        after.openModals.some((id) => id.includes(target.modal_testid) || target.modal_testid.includes(id))
        && !before.openModals.some((id) => id.includes(target.modal_testid) || target.modal_testid.includes(id))
      );
    case 'panel':
      return (
        after.openPanels.some((id) => id.includes(target.panel_testid) || target.panel_testid.includes(id))
        && !before.openPanels.some((id) => id.includes(target.panel_testid) || target.panel_testid.includes(id))
      );
    default:
      return false;
  }
}

export function evaluateRouteOracle(
  step: Pick<UiAuditStep, 'section_guess' | 'element_text' | 'data_testid' | 'action_type' | 'safety_class'>,
  before: PageObservation,
  after: PageObservation,
): { verdict: UiAuditVerdict; reason: string; recommended_fix: string | null; expected: Record<string, string | undefined> } {
  if (step.safety_class === 'WARN') {
    return {
      verdict: 'WARN',
      reason: 'Prvek klasifikován jako WARN — nebyl kliknut',
      recommended_fix: guessTargetFromText(step.element_text, step.data_testid) ? `Přidat oracle pravidlo pro "${step.element_text}"` : null,
      expected: {},
    };
  }

  if (step.safety_class === 'BLOCKED') {
    return {
      verdict: 'BLOCKED',
      reason: 'Prvek klasifikován jako BLOCKED — nebyl kliknut',
      recommended_fix: null,
      expected: {},
    };
  }

  const rule = findMatchingRule(step.section_guess, step.element_text, step.data_testid);
  if (!rule) {
    const guess = guessTargetFromText(step.element_text, step.data_testid);
    const matched = guess ? observationMatchesLoose(after, guess) : false;
    return {
      verdict: matched ? 'WARN' : 'WARN',
      reason: matched
        ? 'Chování vypadá rozumně, ale chybí route oracle pravidlo'
        : 'Chybí route oracle pravidlo pro tento prvek',
      recommended_fix: guess ? `Přidat pravidlo: ${step.element_text} → ${guess}` : `Definovat expected_target pro "${step.element_text}"`,
      expected: { expected_view: guess || undefined },
    };
  }

  if (rule.expected_target.type === 'blocked') {
    return {
      verdict: step.safety_class === 'SAFE' ? 'FAIL' : 'BLOCKED',
      reason: rule.expected_target.reason,
      recommended_fix: 'Ponechat mimo SAFE režim auditu',
      expected: { expected_view: targetToString(rule.expected_target) },
    };
  }

  const matched = observationMatchesTarget(before, after, rule.expected_target);
  const expectedStr = targetToString(rule.expected_target);

  if (matched) {
    return {
      verdict: 'PASS',
      reason: `Chování odpovídá oracle: ${expectedStr}`,
      recommended_fix: null,
      expected: {
        expected_view: expectedStr,
        expected_modal: rule.expected_target.type === 'modal' ? rule.expected_target.modal_testid : undefined,
      },
    };
  }

  // Panel/modal očekáván, ale bez UI reakce — spíš WARN než FAIL pro topbar dropdowny
  if (
    (rule.expected_target.type === 'panel' || rule.expected_target.type === 'modal')
    && step.safety_class === 'SAFE'
  ) {
    return {
      verdict: 'WARN',
      reason: `Očekáváno ${expectedStr}, panel/modal se neotevřel (zkontrolovat detekci nebo handler)`,
      recommended_fix: `Ověřit handler pro "${step.element_text}"`,
      expected: { expected_view: expectedStr },
    };
  }

  const actual = describeActualChange(before, after);
  return {
    verdict: 'FAIL',
    reason: `Očekáváno ${expectedStr}, skutečnost: ${actual}`,
    recommended_fix: `Upravit navigaci/prvek "${step.element_text}" aby vedl na ${expectedStr}`,
    expected: { expected_view: expectedStr },
  };
}

function guessTargetFromText(text: string, testId: string | null): string | null {
  const norm = normalizeText(text);
  if (norm.includes('přehled') || norm.includes('domů')) return 'view:home';
  if (norm.includes('vozidla')) return 'view:vehicles';
  if (norm.includes('připomín')) return 'view:reminders';
  if (norm.includes('dokument')) return 'view:documents';
  if (norm.includes('nastaven') || norm.includes('účet')) return 'tab:account';
  if (norm.includes('profil')) return 'panel:mobileProfileMenu';
  if (norm.includes('oznámen') || norm.includes('notifik')) return 'panel:app-notifications-panel';
  if (testId?.includes('how-to')) return 'modal:how-to-hub-scroll';
  return null;
}

function observationMatchesLoose(after: PageObservation, guess: string): boolean {
  if (guess.startsWith('view:')) return after.activeView === guess.slice(5);
  if (guess.startsWith('tab:')) return after.activeTab === guess.slice(4);
  if (guess.startsWith('panel:')) {
    const panel = guess.slice(6);
    return after.openPanels.some((p) => p.includes(panel));
  }
  if (guess.startsWith('modal:')) {
    const modal = guess.slice(6);
    return after.openModals.some((m) => m.includes(modal));
  }
  return false;
}

function describeActualChange(before: PageObservation, after: PageObservation): string {
  const parts: string[] = [];
  if (before.url !== after.url) parts.push(`url=${after.url}`);
  if (before.activeTab !== after.activeTab && after.activeTab) parts.push(`tab=${after.activeTab}`);
  if (before.activeView !== after.activeView && after.activeView) parts.push(`view=${after.activeView}`);
  if (after.openModals.length) parts.push(`modals=${after.openModals.join(',')}`);
  if (after.openPanels.length) parts.push(`panels=${after.openPanels.join(',')}`);
  return parts.length ? parts.join('; ') : 'beze změny';
}

export function countFailRedirects(steps: UiAuditStep[]): number {
  return steps.filter((s) => s.verdict === 'FAIL' && s.action_type === 'navigate').length;
}
