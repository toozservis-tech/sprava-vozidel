import type {
  ClickableElementDescriptor,
  SafetyClassification,
  UiAuditActionType,
} from './schemas';

export const DENY_TEXT = [
  'Smazat',
  'Odstranit',
  'Zaplatit',
  'Potvrdit platbu',
  'Odeslat',
  'Pozvat',
  'Předat vozidlo',
  'Zrušit účet',
  'Odhlásit se',
  'Vytvořit účet',
  'Zaregistrovat se',
  'Upravit',
  'Přidat vozidlo',
  'Nová připomínka',
  'Přidat servisní záznam',
];

export const DENY_SELECTORS = [
  "[data-danger='true']",
  "[data-uapp-action*='delete']",
  "[data-uapp-action*='remove']",
  "[data-uapp-action*='payment']",
  "[data-uapp-action*='logout']",
  "[data-uapp-action*='submit']",
  "[data-uapp-action*='newReminder']",
  "[data-uapp-action*='serviceHistoryAdd']",
  "[data-uapp-action*='shareVehicle']",
  "[data-uapp-action*='reminderComplete']",
  "[data-uapp-action*='reminderSnooze']",
  "[data-testid='btn-logout']",
  "[data-testid='btn-register']",
  "[data-testid='btn-add-vehicle']",
  "button[type='submit']",
  "input[type='submit']",
  '.mobile-profile-action--danger',
];

export const ALLOW_SAFE_ACTIONS = [
  'open',
  'detail',
  'navigate',
  'filter',
  'search-focus',
  'open-modal',
  'close-modal',
  'open-dropdown',
  'home',
  'vehicles',
  'serviceHistory',
  'reminders',
  'documents',
  'servicesDirectory',
  'settings',
  'collapse',
  'profile',
  'notifications',
  'attentionClose',
  'attentionAllVehicles',
  'remindersTipClose',
  'serviceHistoryResetFilters',
  'loadMoreServiceHistory',
];

const WARN_TEXT = [
  'Licence',
  'Stáhnout',
  'Download',
  'Faktury',
  'Objednat servis',
  'Předplatné',
];

const FORM_TAGS = new Set(['INPUT', 'SELECT', 'TEXTAREA']);

function matchesDenyText(text: string): string | null {
  const normalized = text.trim();
  if (!normalized) return null;
  for (const deny of DENY_TEXT) {
    if (normalized.includes(deny)) return deny;
  }
  return null;
}

function matchesWarnText(text: string): string | null {
  const normalized = text.trim();
  if (!normalized) return null;
  for (const warn of WARN_TEXT) {
    if (normalized.includes(warn)) return warn;
  }
  return null;
}

export function classifyElement(element: ClickableElementDescriptor): {
  safety: SafetyClassification;
  reason: string;
  actionType: UiAuditActionType;
} {
  const text = element.text.trim();
  const action = element.dataUappAction || '';
  const testId = element.dataTestId || '';
  const inProfilePanel = element.parentPanel === 'mobileProfileMenu' || element.sectionGuess === 'Profilový panel';

  if (testId === 'dashboard-profile-menu-logout' || element.isDangerAction) {
    return { safety: 'BLOCKED', reason: 'Logout — zakázáno uprostřed běhu', actionType: 'blocked_destructive' };
  }
  if (
    testId === 'dashboard-profile-menu-help'
    || testId === 'menu-how-to-tutorial'
    || (inProfilePanel && text.includes('Jak na to'))
  ) {
    return { safety: 'SAFE', reason: 'Nápověda — otevře help modal', actionType: 'open_modal' };
  }
  if (
    testId === 'dashboard-profile-menu-settings'
    || (inProfilePanel && text.includes('Nastavení účtu'))
  ) {
    return { safety: 'SAFE', reason: 'Nastavení účtu — navigace do account/settings', actionType: 'navigate' };
  }
  if (
    testId === 'dashboard-profile-menu-license-plan'
    || (inProfilePanel && /licence|licence a plán/i.test(text))
  ) {
    return { safety: 'SAFE', reason: 'Licence — otevře license modal (bez checkout kliku)', actionType: 'open_modal' };
  }
  if (
    testId === 'dashboard-profile-menu-theme'
    || (inProfilePanel && /tmavý|světlý|motiv/i.test(text))
  ) {
    return { safety: 'SAFE', reason: 'Theme toggle — audit bez fatal JS error', actionType: 'unknown' };
  }

  if (element.tagName === 'A' && element.href) {
    const href = element.href.toLowerCase();
    if (href.startsWith('mailto:') || href.startsWith('tel:')) {
      return { safety: 'BLOCKED', reason: 'Externí komunikační odkaz', actionType: 'blocked_destructive' };
    }
  }

  if (FORM_TAGS.has(element.tagName)) {
    const inputType = (element.type || '').toLowerCase();
    if (inputType === 'submit' || inputType === 'file') {
      return { safety: 'BLOCKED', reason: 'Formulářový submit/upload', actionType: 'blocked_destructive' };
    }
    if (inputType === 'checkbox' || inputType === 'radio') {
      return { safety: 'WARN', reason: 'Formulářový přepínač — neklikáme', actionType: 'filter' };
    }
    return { safety: 'WARN', reason: 'Formulářové pole — neklikáme', actionType: 'filter' };
  }

  for (const pattern of DENY_SELECTORS) {
    if (pattern.includes('data-uapp-action') && action) {
      const needle = pattern.match(/\*='([^']+)'/)?.[1];
      if (needle && action.includes(needle)) {
        return { safety: 'BLOCKED', reason: `Zakázaná akce: ${action}`, actionType: 'blocked_destructive' };
      }
    }
    if (pattern.includes('data-testid') && testId) {
      const needle = pattern.match(/data-testid='([^']+)'/)?.[1];
      if (needle && testId === needle) {
        return { safety: 'BLOCKED', reason: `Zakázaný testid: ${testId}`, actionType: 'blocked_destructive' };
      }
    }
    if (pattern.startsWith('.') && element.selector?.includes(pattern.slice(1))) {
      return { safety: 'BLOCKED', reason: `Zakázaný selektor: ${pattern}`, actionType: 'blocked_destructive' };
    }
    if (pattern.includes("type='submit'") && element.type === 'submit') {
      return { safety: 'BLOCKED', reason: 'Submit tlačítko', actionType: 'blocked_destructive' };
    }
  }

  const denyMatch = matchesDenyText(text);
  if (denyMatch) {
    return { safety: 'BLOCKED', reason: `Destruktivní text: ${denyMatch}`, actionType: 'blocked_destructive' };
  }

  if (action) {
    const baseAction = action.split(':')[0];
    if (ALLOW_SAFE_ACTIONS.includes(baseAction) || ALLOW_SAFE_ACTIONS.includes(action)) {
      return { safety: 'SAFE', reason: `Povolená akce: ${action}`, actionType: inferActionType(action, text) };
    }
    if (action.startsWith('detail') || action.startsWith('docPreview') || action.startsWith('docDownload')) {
      if (action.startsWith('docDownload')) {
        return { safety: 'WARN', reason: 'Download — pouze zaznamenat', actionType: 'download' };
      }
      return { safety: 'SAFE', reason: `Detail akce: ${action}`, actionType: 'detail' };
    }
    if (action.includes('delete') || action.includes('remove') || action.includes('payment')) {
      return { safety: 'BLOCKED', reason: `Zakázaná akce: ${action}`, actionType: 'blocked_destructive' };
    }
  }

  if (testId.startsWith('tab-') || testId.startsWith('dashboard-nav-')) {
    return { safety: 'SAFE', reason: 'Navigační tab', actionType: 'navigate' };
  }
  if (testId.includes('profile') || testId.includes('notifications') || testId.includes('how-to')) {
    if (testId === 'dashboard-profile-menu-logout') {
      return { safety: 'BLOCKED', reason: 'Logout — zakázáno', actionType: 'blocked_destructive' };
    }
    return { safety: 'SAFE', reason: 'UI panel/dropdown', actionType: inferActionType(action, text) };
  }
  if (testId.startsWith('dashboard-profile-menu-')) {
    return { safety: 'SAFE', reason: 'Položka profilového menu', actionType: inferActionType(action, text) };
  }
  if (testId.includes('menu-')) {
    return { safety: 'SAFE', reason: 'Menu položka', actionType: 'open_modal' };
  }

  const warnMatch = matchesWarnText(text);
  if (warnMatch) {
    return { safety: 'WARN', reason: `Rizikový text: ${warnMatch}`, actionType: 'unknown' };
  }

  if (element.role === 'link' && element.href && !element.href.startsWith('#')) {
    return { safety: 'WARN', reason: 'Neznámý externí/ interní odkaz', actionType: 'navigate' };
  }

  if (text) {
    return { safety: 'WARN', reason: 'Neznámý prvek bez pravidla', actionType: 'unknown' };
  }

  return { safety: 'WARN', reason: 'Prvek bez textu/akce', actionType: 'unknown' };
}

function inferActionType(action: string, text: string): UiAuditActionType {
  if (action === 'profile' || text.includes('Profil')) return 'open_dropdown';
  if (action === 'notifications') return 'open_dropdown';
  if (action.includes('modal') || text.includes('Jak na to')) return 'open_modal';
  if (action === 'collapse') return 'unknown';
  if (['home', 'vehicles', 'serviceHistory', 'reminders', 'documents', 'servicesDirectory', 'settings', 'invoices', 'reservations'].includes(action)) {
    return 'navigate';
  }
  if (action.startsWith('detail')) return 'detail';
  if (action.includes('filter') || action.includes('Reset')) return 'filter';
  if (action.includes('Close') || text.includes('Zavřít')) return 'close_modal';
  return 'unknown';
}

export function isSafeToClick(safety: SafetyClassification): boolean {
  return safety === 'SAFE';
}
