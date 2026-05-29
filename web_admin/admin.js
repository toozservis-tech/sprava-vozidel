// ============================================
// Správa vozidel – administrační přehled
// Kompletní refaktoring s plně funkčním CRUD
// ============================================

const API_BASE = "";
const ADMIN_TOKEN_KEY = 'adminAccessToken';
const LEGACY_TOKEN_KEY = 'accessToken';
const ADMIN_ROLE_KEY = 'adminRole';

// Globální proměnné
let authToken = null;
let currentSection = "overview";
let currentAdminRole = null;
const LIST_FETCH_PAGE_SIZE = 200;
const USERS_RENDER_PAGE_SIZE = 24;
let usersAllCache = [];
let usersFilteredCache = [];
let usersCurrentPage = 1;
let userDetailData = null;
let userDetailActivePanel = 'vehicles';
let userDetailReturnContext = null;
let usersSearchDebounceTimer = null;
let usersListFetchGeneration = 0;
const ADMIN_VIEW_SECTIONS = ['users', 'vehicles', 'services', 'records'];
const ADMIN_VIEW_MODES = ['grid', 'list', 'compact'];
const ADMIN_API_TIMEOUT_MS = 30000;
const adminViewState = {};
const ARCHIVED_USERS_PURGE_CONFIRM_PHRASE = 'VYMAZAT ARCHIV';
function normalizeArchivedUsersPurgeConfirmPhrase(value) {
  return String(value || '')
    .trim()
    .replace(/[.,;:!?'"`´]+/g, '')
    .replace(/\s+/g, ' ')
    .toUpperCase();
}
const ADMIN_NAVBAR_CLOCK_TZ = 'Europe/Prague';
let adminNavbarClockTimer = null;
let trafficReportObjectUrl = null;

function tickAdminNavbarClock() {
  const el = document.getElementById('adminNavbarClock');
  if (!el) return;
  const now = new Date();
  el.textContent = now.toLocaleTimeString('cs-CZ', {
    timeZone: ADMIN_NAVBAR_CLOCK_TZ,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
  const dateStr = now.toLocaleDateString('cs-CZ', {
    timeZone: ADMIN_NAVBAR_CLOCK_TZ,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
  el.setAttribute('datetime', now.toISOString());
  el.title = `Čas v Česku (Europe/Prague): ${dateStr}`;
}

function startAdminNavbarClock() {
  if (adminNavbarClockTimer) clearInterval(adminNavbarClockTimer);
  tickAdminNavbarClock();
  adminNavbarClockTimer = setInterval(tickAdminNavbarClock, 1000);
}

function stopAdminNavbarClock() {
  if (adminNavbarClockTimer) {
    clearInterval(adminNavbarClockTimer);
    adminNavbarClockTimer = null;
  }
}
const recordFormOptionsState = {
  users: [],
  vehicles: [],
};
let controlCenterCurrentInsight = null;
const controlCenterDataState = {
  users: [],
  health: null,
  payments: null,
  presence: null,
  security: null,
  backups: null,
  apiMonitor: null,
  webhookMonitor: null,
  storage: null,
  storageCleanupPreview: null,
  email: null,
  jobs: null,
  notifications: null,
  audit: null,
  systemLogs: null,
  insight: null,
  command: null,
};
const controlCenterPaymentsFilters = {
  env: 'all',
  state: 'all',
  query: '',
};
let systemCapabilities = {};

/** Pořadí v dropdownu — musí odpovědět `get_allowed_license_plans_for_role` na backendu. */
const USER_LICENSE_PLAN_ORDER = ['free', 'basic', 'premium', 'lifetime'];
const SERVICE_LICENSE_PLAN_ORDER = ['service_free', 'service_full', 'service_lifetime'];

const ADMIN_LICENSE_PLAN_LABELS = {
  free: 'FREE (uživatel · 1 vozidlo)',
  basic: 'BASIC (uživatel · plná osobní správa)',
  premium: 'PREMIUM (uživatel · rozšířený přehled a servisní propojení)',
  lifetime: 'LIFETIME (uživatel · doživotní Premium, pouze admin)',
  service_free: 'SERVIS FREE · zdarma (limity)',
  service_full: 'SERVIS FULL · placená licence (všechny funkce)',
  service_lifetime: 'SERVIS LIFETIME · doživotní FULL (jen přes admin)',
};

function collapseLegacyStoredPlan(planId) {
  const x = String(planId || '').trim().toLowerCase();
  if (x === 'service_basic' || x === 'service_premium') {
    return 'service_full';
  }
  return x;
}

/**
 * Nabídka plánů v admin formuláři: u servisu nikdy neseparuje „BASIC/PREMIUM“ —
 * tyto hodnoty v DB jsou legacy a při výběru se mapují na service_full (viz backend).
 */
function resolveLicensePlanChoicesForPopulate(workspaceKind, allowedFromApi = null) {
  const ws = workspaceKind === 'service' ? 'service' : 'user';
  const order = ws === 'service' ? SERVICE_LICENSE_PLAN_ORDER : USER_LICENSE_PLAN_ORDER;
  const allowedSet = new Set(order);

  let picked = [];
  if (Array.isArray(allowedFromApi) && allowedFromApi.length > 0) {
    const want = new Set();
    allowedFromApi.forEach((raw) => {
      const key = collapseLegacyStoredPlan(raw);
      if (allowedSet.has(key)) {
        want.add(key);
      }
    });
    picked = order.filter((k) => want.has(k));
  } else {
    picked = order.slice();
  }
  if (!picked.length) {
    picked = order.slice();
  }
  return picked.map((value) => ({
    value,
    label: ADMIN_LICENSE_PLAN_LABELS[value] || String(value).toUpperCase(),
  }));
}

function getLicenseWorkspaceKindForRole(role) {
  return String(role || '').trim().toLowerCase() === 'service' ? 'service' : 'user';
}

function getLicensePlanBase(plan) {
  const normalized = String(plan || '').trim().toLowerCase();
  const base = normalized.startsWith('service_') ? normalized.slice(8) : normalized;
  return ['free', 'basic', 'premium', 'lifetime', 'full'].includes(base) ? base : 'free';
}

function normalizeLicensePlanForRole(plan, role, workspaceKind = null) {
  const ws = workspaceKind || getLicenseWorkspaceKindForRole(role);
  const n = String(plan || '').trim().toLowerCase();
  if (!n) return '';
  const fromServiceFamily = n.startsWith('service_');

  /** Zarovnání s backendem _map_service_license_storage_to_user_plan + normalize_license_plan_key. */
  const userPlanFromServiceStorage = () => {
    let eff = n;
    if (eff === 'service_basic' || eff === 'service_premium') {
      eff = 'service_full';
    }
    const map = { service_free: 'free', service_full: 'premium', service_lifetime: 'lifetime' };
    return map[eff] || 'free';
  };

  const servicePlanFromUserStorage = () => {
    const b = getLicensePlanBase(n);
    if (b === 'free') return 'service_free';
    if (b === 'lifetime') return 'service_lifetime';
    return 'service_full';
  };

  let canon = n;
  if (ws === 'service') {
    if (!fromServiceFamily) {
      canon = servicePlanFromUserStorage();
    } else if (n === 'service_basic' || n === 'service_premium') {
      canon = 'service_full';
    }
  } else if (fromServiceFamily) {
    canon = userPlanFromServiceStorage();
  }

  const order = ws === 'service' ? SERVICE_LICENSE_PLAN_ORDER : USER_LICENSE_PLAN_ORDER;
  if (order.includes(canon)) {
    return canon;
  }
  return order[0] || 'free';
}

function getLicensePlanOptionsForRole(role, workspaceKind = null) {
  const ws = workspaceKind || getLicenseWorkspaceKindForRole(role);
  return resolveLicensePlanChoicesForPopulate(ws, null);
}

function formatAdminLicensePlanLabel(plan, role = null, workspaceKind = null) {
  const normalized = String(plan || '').trim().toLowerCase();
  const inferredWs =
    workspaceKind ||
    (normalized.startsWith('service_') ? 'service' : getLicenseWorkspaceKindForRole(role || 'user'));
  const inferredRole = role || (inferredWs === 'service' ? 'service' : 'user');
  const normalizedForRole = normalizeLicensePlanForRole(normalized, inferredRole, inferredWs);
  const options = getLicensePlanOptionsForRole(inferredRole, inferredWs);
  const match = options.find((option) => option.value === normalizedForRole);
  return match ? match.label : normalizedForRole.toUpperCase();
}

/** Stejná logika jako backend _format_bytes — pro fallback když API pošle jen disk_usage_bytes. */
function formatAdminBytes(value) {
  let size = Math.max(0, Number(value) || 0);
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  for (let i = 0; i < units.length; i += 1) {
    if (size < 1024 || i === units.length - 1) {
      return `${size.toFixed(1)} ${units[i]}`;
    }
    size /= 1024;
  }
  return '0.0 B';
}

function formatUserDiskHuman(row) {
  const h = row?.disk_usage_human;
  if (h != null && String(h).trim() !== '') {
    return String(h);
  }
  const b = row?.disk_usage_bytes;
  if (b != null && Number.isFinite(Number(b))) {
    return formatAdminBytes(Number(b));
  }
  return null;
}

function populateLicensePlanSelect(selectId, role, currentPlan = '', options = {}) {
  const select = document.getElementById(selectId);
  if (!select) return;
  const includeBlank = options.includeBlank !== false;
  const blankLabel = options.blankLabel || 'beze změny';
  const workspaceKind = options.workspaceKind || null;
  const wsResolved = workspaceKind || getLicenseWorkspaceKindForRole(role);
  const normalizedCurrent = currentPlan
    ? normalizeLicensePlanForRole(currentPlan, role, workspaceKind)
    : '';
  const previousValue = String(select.value || '').trim().toLowerCase();
  const desiredValue =
    normalizedCurrent || normalizeLicensePlanForRole(previousValue, role, workspaceKind);
  const planOptions = resolveLicensePlanChoicesForPopulate(wsResolved, options.allowedPlansFromApi ?? null);
  const html = [];
  if (includeBlank) {
    html.push(`<option value="">${escapeHtml(blankLabel)}</option>`);
  }
  planOptions.forEach((option) => {
    html.push(`<option value="${escapeHtml(option.value)}">${escapeHtml(option.label)}</option>`);
  });
  select.innerHTML = html.join('');
  const canUseDesiredValue = planOptions.some((option) => option.value === desiredValue);
  select.value = canUseDesiredValue ? desiredValue : (includeBlank ? '' : planOptions[0]?.value || '');
}

// ============================================
// AUTH & TOKEN MANAGEMENT
// ============================================

function getAuthToken() {
  if (authToken) return authToken;
  authToken = localStorage.getItem(ADMIN_TOKEN_KEY) || localStorage.getItem(LEGACY_TOKEN_KEY);
  if (authToken) return authToken;
  const urlParams = new URLSearchParams(window.location.search);
  authToken = urlParams.get('token');
  if (authToken) {
    localStorage.setItem(ADMIN_TOKEN_KEY, authToken);
    return authToken;
  }
  return null;
}

function setAuthToken(token) {
  authToken = token;
  localStorage.setItem(ADMIN_TOKEN_KEY, token);
}

function setAdminRole(role) {
  currentAdminRole = role || null;
  if (currentAdminRole) {
    localStorage.setItem(ADMIN_ROLE_KEY, currentAdminRole);
  } else {
    localStorage.removeItem(ADMIN_ROLE_KEY);
  }
  updateControlCenterVisibility();
}

function getStoredAdminRole() {
  if (currentAdminRole) return currentAdminRole;
  currentAdminRole = localStorage.getItem(ADMIN_ROLE_KEY) || null;
  return currentAdminRole;
}

function clearAuthToken() {
  const currentToken = authToken;
  const legacyToken = localStorage.getItem(LEGACY_TOKEN_KEY);
  authToken = null;
  localStorage.removeItem(ADMIN_TOKEN_KEY);
  if (legacyToken && currentToken && legacyToken === currentToken) {
    localStorage.removeItem(LEGACY_TOKEN_KEY);
  }
  setAdminRole(null);
}

// ============================================
// CENTRÁLNÍ API HELPER
// ============================================

function showGlobalError(message) {
  const errorEl = document.getElementById('global-error');
  if (errorEl) {
    errorEl.textContent = message;
    errorEl.classList.remove('hidden');
    setTimeout(() => {
      errorEl.classList.add('hidden');
    }, 5000);
  }
}

function hideGlobalError() {
  const errorEl = document.getElementById('global-error');
  if (errorEl) {
    errorEl.classList.add('hidden');
  }
}

function showSuccess(message) {
  const errorEl = document.getElementById('global-error');
  if (errorEl) {
    errorEl.textContent = message;
    errorEl.classList.add('success');
    errorEl.classList.remove('hidden');
    setTimeout(() => {
      errorEl.classList.add('hidden');
      errorEl.classList.remove('success');
    }, 3000);
  }
}

function formatApiDetailMessage(detail) {
  if (detail == null || detail === '') return null;
  if (typeof detail === 'string') return detail;
  try {
    return JSON.stringify(detail);
  } catch {
    return String(detail);
  }
}

/** Klik na text uvnitř <button> má target = Text — closest() tam není. */
function eventClickTargetElement(ev) {
  const t = ev && ev.target;
  if (t instanceof Element) return t;
  if (t && typeof t === 'object' && t.parentElement instanceof Element) return t.parentElement;
  return null;
}

let _sysNotifDeactivateInFlight = false;

function initSysNotificationDeactivateDelegation() {
  const root = document.getElementById('dashboard-screen');
  if (!root || root.dataset.sysNotifDeactivateBound === '1') return;
  root.dataset.sysNotifDeactivateBound = '1';
  root.addEventListener(
    'click',
    async (ev) => {
      const origin = eventClickTargetElement(ev);
      const btn = origin && origin.closest('.js-sys-notif-off');
      if (!btn || !root.contains(btn)) return;
      ev.preventDefault();
      ev.stopPropagation();
      if (_sysNotifDeactivateInFlight || btn.disabled) return;
      const nid = Number(btn.getAttribute('data-sys-notif-id'));
      if (!Number.isFinite(nid) || nid <= 0) return;
      if (!confirm(`Vypnout oznámení #${nid} pro všechny uživatele?`)) return;
      _sysNotifDeactivateInFlight = true;
      btn.disabled = true;
      const prev = btn.textContent;
      btn.textContent = '…';
      try {
        await apiRequest('POST', `/admin-api/settings/system-notifications/${nid}/deactivate`, {});
        showSuccess('Oznámení bylo vypnuto');
        await refreshSettingsNotificationsOverview();
      } catch (err) {
        showGlobalError(err?.message || String(err));
        btn.disabled = false;
        btn.textContent = prev;
      } finally {
        _sysNotifDeactivateInFlight = false;
      }
    },
    true,
  );
}

async function apiRequest(method, path, body = null, requestConfig = null) {
  const silentBanner =
    requestConfig && typeof requestConfig === 'object' && requestConfig.silentGlobalError === true;
  const token = getAuthToken();
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), ADMIN_API_TIMEOUT_MS);
  const headers = {
    "Accept": "application/json",
  };
  
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  
  if (body && (method === "POST" || method === "PATCH" || method === "PUT")) {
    headers["Content-Type"] = "application/json";
  }
  
  try {
    const options = {
      method,
      headers,
      credentials: 'include', // Pro CORS cookies
      signal: controller.signal
    };
    
    if (body) {
      options.body = JSON.stringify(body);
    }
    
    const url = API_BASE + path;
    const res = await fetch(url, options);
    
    // Pokud je 401 Unauthorized, zkusit přesměrovat na login
    if (res.status === 401) {
      clearAuthToken();
      showGlobalError('Session vypršela. Prosím přihlaste se znovu.');
      setTimeout(() => {
        showLoginScreen();
      }, 2000);
      throw new Error('Unauthorized');
    }
    
    if (!res.ok) {
      let errorData;
      try {
        errorData = await res.json();
      } catch {
        errorData = { detail: res.statusText || `HTTP ${res.status}` };
      }
      const detailMsg = formatApiDetailMessage(errorData.detail);
      throw new Error(detailMsg || `Request failed: ${res.status} ${res.statusText}`);
    }
    
    // Pokud response je prázdný (204 No Content), vrátit null
    if (res.status === 204) {
      return null;
    }
    
    return await res.json();
  } catch (error) {
    if (error.name === 'AbortError') {
      const timeoutError = `Server neodpověděl do ${Math.round(ADMIN_API_TIMEOUT_MS / 1000)} s. Zkuste obnovit stránku; pokud se to opakuje, databáze je pravděpodobně zamčená dlouhou operací.`;
      console.error(`API Timeout [${method} ${path}]:`, error);
      if (!silentBanner) showGlobalError(timeoutError);
      throw new Error(timeoutError);
    }
    // Pokud je to network error (Failed to fetch), zobrazit uživatelsky přívětivou zprávu
    if (error.message === 'Failed to fetch' || error.name === 'TypeError') {
      const friendlyError = 'Nelze se připojit k serveru. Zkontrolujte, zda server běží na ' + (API_BASE || window.location.origin);
      console.error(`API Error [${method} ${path}]:`, error);
      if (!silentBanner) showGlobalError(friendlyError);
      throw new Error(friendlyError);
    }

    console.error(`API Error [${method} ${path}]:`, error);
    if (!silentBanner) showGlobalError(error.message || `Chyba při ${method} ${path}`);
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

async function loadSystemCapabilitiesAdmin() {
  try {
    const data = await apiRequest('GET', '/api/v1/system/capabilities');
    systemCapabilities = (data && data.modules) || {};
  } catch (error) {
    console.warn('Capabilities unavailable:', error?.message || error);
    systemCapabilities = {};
  }
}

function withQueryParams(path, params = {}) {
  const [base, query = ""] = path.split("?");
  const search = new URLSearchParams(query);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      search.set(key, String(value));
    }
  });
  const serialized = search.toString();
  return serialized ? `${base}?${serialized}` : base;
}

async function fetchAllList(
  path,
  pageSize = LIST_FETCH_PAGE_SIZE,
  maxPages = 200,
  extraParams = null,
) {
  const allItems = [];
  let offset = 0;
  const extra = extraParams && typeof extraParams === 'object' ? extraParams : null;

  for (let page = 0; page < maxPages; page += 1) {
    const params = { limit: pageSize, offset };
    if (extra) {
      Object.assign(params, extra);
    }
    const response = await apiRequest('GET', withQueryParams(path, params));
    const items = Array.isArray(response) ? response : (Array.isArray(response?.records) ? response.records : []);

    allItems.push(...items);

    if (items.length < pageSize) {
      break;
    }

    offset += items.length;
  }

  return allItems;
}

function escapeHtml(value) {
  if (value === null || value === undefined) return '';
  const div = document.createElement('div');
  div.textContent = String(value);
  return div.innerHTML;
}

/** Přehledové číslo v adminu (1,2,3…); fallback na DB id před migrací. */
function userAdminBadgeLabel(user) {
  if (user && user.admin_ordinal !== undefined && user.admin_ordinal !== null && user.admin_ordinal !== '') {
    return `#${user.admin_ordinal}`;
  }
  return `#${user?.id ?? '?'}`;
}

/** Časová pásma klienta ignorujeme — admin má konzistentně čas podle Prahy. */
const ADMIN_DISPLAY_TIMEZONE = { timeZone: 'Europe/Prague' };

function formatDateTime(value, fallback = '-') {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return date.toLocaleString('cs-CZ', ADMIN_DISPLAY_TIMEZONE);
}

function formatDate(value, fallback = '-') {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return date.toLocaleDateString('cs-CZ', ADMIN_DISPLAY_TIMEZONE);
}

function formatMoney(value, fallback = '-') {
  const num = Number(value);
  if (!Number.isFinite(num)) return fallback;
  return `${num.toLocaleString('cs-CZ')} Kč`;
}

function phoneStatusAdminLabel(user) {
  const s = user && user.phone_status_label;
  if (s === 'verified') return 'Ověřený';
  if (s === 'unverified') return 'Formálně validní, neověřený';
  if (s === 'invalid') return 'Nevalidní / chybí E.164';
  return '—';
}

function formatRiskFlags(raw) {
  if (raw == null || raw === '') return '—';
  if (Array.isArray(raw)) return raw.length ? raw.join(', ') : '—';
  if (typeof raw === 'string') return raw || '—';
  try {
    return JSON.stringify(raw);
  } catch (e) {
    return String(raw);
  }
}

function truncUa(ua) {
  if (!ua) return '—';
  const t = String(ua);
  return t.length > 80 ? `${t.slice(0, 77)}…` : t;
}

function getAdminSectionContainer(section) {
  return document.getElementById(`${section}-cards-container`);
}

function getStoredViewMode(section) {
  const saved = localStorage.getItem(`admin:view:${section}`);
  return ADMIN_VIEW_MODES.includes(saved) ? saved : 'grid';
}

function applySectionViewMode(section) {
  const container = getAdminSectionContainer(section);
  const mode = adminViewState[section] || 'grid';
  const switchEl = document.querySelector(`.view-switch[data-section="${section}"]`);

  if (container) {
    container.classList.remove('view-grid', 'view-list', 'view-compact');
    container.classList.add(`view-${mode}`);
  }

  if (switchEl) {
    switchEl.querySelectorAll('.view-btn').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.view === mode);
    });
  }
}

function setSectionViewMode(section, mode) {
  if (!ADMIN_VIEW_SECTIONS.includes(section)) return;
  if (!ADMIN_VIEW_MODES.includes(mode)) return;
  adminViewState[section] = mode;
  localStorage.setItem(`admin:view:${section}`, mode);
  if (section === 'users') {
    renderUsersList();
    return;
  }
  applySectionViewMode(section);
}

function initSectionViewModes() {
  ADMIN_VIEW_SECTIONS.forEach((section) => {
    adminViewState[section] = getStoredViewMode(section);
    applySectionViewMode(section);
  });
}

function getOnlineState(user) {
  if (typeof user?.is_online === 'boolean') {
    return user.is_online;
  }
  if (!user?.last_seen_at) {
    return false;
  }
  const lastSeen = new Date(user.last_seen_at);
  if (Number.isNaN(lastSeen.getTime())) {
    return false;
  }
  const ageSec = (Date.now() - lastSeen.getTime()) / 1000;
  return ageSec <= 300;
}

function canAccessControlCenter() {
  const role = (getStoredAdminRole() || '').toLowerCase();
  return role === 'developer_admin';
}

function updateControlCenterVisibility() {
  const navItem = document.querySelector('.nav-item[data-section="control-center"]');
  const section = document.getElementById('section-control-center');
  const allowed = canAccessControlCenter();

  if (navItem) {
    navItem.classList.toggle('hidden', !allowed);
  }
  if (section && !allowed) {
    section.classList.remove('active');
  }
  if (!allowed && currentSection === 'control-center') {
    switchSection('overview');
  }
}

async function resolveCurrentAdminRole() {
  if (getStoredAdminRole()) {
    updateControlCenterVisibility();
    return;
  }
  try {
    const me = await apiRequest('GET', '/user/me');
    setAdminRole(me?.role || null);
  } catch (error) {
    // Role není k dispozici - neblokovat dashboard.
    updateControlCenterVisibility();
  }
}

// ============================================
// SECTION NAVIGATION
// ============================================

function initNavigation() {
  const navItems = document.querySelectorAll('.nav-item[data-section]');
  
  navItems.forEach((item) => {
    item.addEventListener('click', () => {
      const section = item.getAttribute('data-section');
      switchSection(section);
    });
  });

  initSummaryNavigation();
  initOverviewStatsDelegation();

  // Načíst data pro aktivní sekci
  const activeItem = document.querySelector('.nav-item.active');
  if (activeItem) {
    const section = activeItem.getAttribute('data-section');
    if (section) {
      currentSection = section;
      loadSectionData(section);
    }
  }
}

function isAdminMobileViewport() {
  return window.matchMedia('(max-width: 1024px)').matches;
}

function openAdminMobileNav() {
  if (!isAdminMobileViewport()) return;
  const sidebar = document.getElementById('adminSidebar');
  const overlay = document.getElementById('admin-mobile-nav-overlay');
  const toggle = document.getElementById('admin-mobile-menu-toggle');

  sidebar?.classList.add('mobile-open');
  if (overlay) {
    overlay.classList.remove('hidden');
    overlay.classList.add('active');
  }
  document.body.classList.add('admin-mobile-nav-open');
  if (toggle) {
    toggle.setAttribute('aria-expanded', 'true');
  }
}

function closeAdminMobileNav() {
  const sidebar = document.getElementById('adminSidebar');
  const overlay = document.getElementById('admin-mobile-nav-overlay');
  const toggle = document.getElementById('admin-mobile-menu-toggle');

  sidebar?.classList.remove('mobile-open');
  if (overlay) {
    overlay.classList.remove('active');
    overlay.classList.add('hidden');
  }
  document.body.classList.remove('admin-mobile-nav-open');
  if (toggle) {
    toggle.setAttribute('aria-expanded', 'false');
  }
}

function toggleAdminMobileNav() {
  if (!isAdminMobileViewport()) return;
  const sidebar = document.getElementById('adminSidebar');
  const isOpen = Boolean(sidebar?.classList.contains('mobile-open'));
  if (isOpen) {
    closeAdminMobileNav();
  } else {
    openAdminMobileNav();
  }
}

function initSummaryNavigation() {
  const sectionMap = {
    'summary-users': 'users',
    'summary-vehicles': 'vehicles',
    'summary-services': 'services',
    'summary-records': 'records',
  };

  Object.entries(sectionMap).forEach(([id, section]) => {
    const el = document.getElementById(id);
    if (!el || el.dataset.bound === '1') return;

    const navigate = () => switchSection(section);
    el.setAttribute('role', 'button');
    el.setAttribute('tabindex', '0');
    el.addEventListener('click', navigate);
    el.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        navigate();
      }
    });
    el.dataset.bound = '1';
  });
}

function initOverviewStatsDelegation() {
  const grid = document.getElementById('overview-stats');
  if (!grid || grid.dataset.overviewNavBound === '1') {
    return;
  }
  grid.dataset.overviewNavBound = '1';
  grid.addEventListener('click', (ev) => {
    const btn = ev.target?.closest?.('button[data-admin-section]');
    if (!btn || !grid.contains(btn)) {
      return;
    }
    const section = btn.getAttribute('data-admin-section');
    if (section) {
      switchSection(section);
    }
  });
}

function switchSection(section) {
  if (section !== 'control-center') {
    closeAllControlCenterDetails();
  } else {
    syncControlCenterDetailsOverlayState();
  }

  currentSection = section;
  
  // Aktualizovat aktivní stav v navigaci
  document.querySelectorAll('.nav-item').forEach(item => {
    item.classList.remove('active');
  });
  const activeNavBtn = document.querySelector(`.nav-item[data-section="${section}"]`);
  if (activeNavBtn) {
    activeNavBtn.classList.add('active');
  }
  
  // Skrýt všechny sekce
  document.querySelectorAll('.content-section').forEach(sec => {
    sec.classList.remove('active');
  });
  
  // Zobrazit aktivní sekci
  const activeSection = document.getElementById(`section-${section}`);
  if (activeSection) {
    activeSection.classList.add('active');
  }
  
  // Načíst data pro sekci
  loadSectionData(section);

  // Na mobilu po kliknutí na sekci zavřít sidebar
  if (isAdminMobileViewport()) {
    closeAdminMobileNav();
  }
}

function loadSectionData(section) {
  hideGlobalError();
  
  switch(section) {
    case 'overview':
      loadOverview();
      break;
    case 'app-center':
      loadAppCenter();
      break;
    case 'global-admin':
      loadGlobalAdmin();
      break;
    case 'demo-access':
      loadDemoAccessLeads();
      break;
    case 'users':
      loadUsers();
      break;
    case 'vehicles':
      loadVehicles();
      break;
    case 'mdcr-open-data':
      loadMdcrOpenData();
      break;
    case 'vehicle-lifecycle':
      loadVehicleLifecycleSection();
      break;
    case 'services':
      loadServices();
      break;
    case 'records':
      loadRecords();
      loadDeletedServiceRecords();
      break;
    case 'audit':
      loadAuditLog();
      break;
    case 'traffic':
      loadTrafficReportSection();
      break;
    case 'support':
      loadSupportInbox();
      break;
    case 'support-chat':
      refreshSupportChatPanel();
      break;
    case 'security':
      loadSecurityPanel();
      break;
    case 'system':
      // Systémové nástroje se načítají při kliknutí
      break;
    case 'settings':
      loadSettings();
      break;
    case 'control-center':
      refreshControlCenterOverview();
      break;
  }
}

function releaseTrafficReportObjectUrl() {
  if (trafficReportObjectUrl) {
    URL.revokeObjectURL(trafficReportObjectUrl);
    trafficReportObjectUrl = null;
  }
}

async function fetchAdminHtmlGet(path) {
  const token = getAuthToken();
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), ADMIN_API_TIMEOUT_MS);
  try {
    const res = await fetch(API_BASE + path, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'text/html',
      },
      credentials: 'include',
      signal: controller.signal,
    });
    const text = await res.text();
    return { ok: res.ok, status: res.status, text };
  } finally {
    clearTimeout(timeoutId);
  }
}

async function loadTrafficReportSection() {
  const statusEl = document.getElementById('traffic-report-status');
  const errEl = document.getElementById('traffic-report-error');
  const iframe = document.getElementById('traffic-report-iframe');
  if (!statusEl || !iframe) return;

  if (errEl) {
    errEl.style.display = 'none';
    errEl.textContent = '';
  }

  statusEl.innerHTML = '<div class="loading">Načítám stav přehledu…</div>';

  try {
    const st = await apiRequest('GET', '/admin-api/traffic/report/status', null, {
      silentGlobalError: true,
    });
    const meta = (st && st.meta) || {};
    const exists = Boolean(st && st.report_exists);
    const lines = [];
    lines.push(
      `<strong>Stav souboru:</strong> ${exists ? 'přehled je k dispozici' : 'přehled zatím nebyl vygenerován'}`,
    );
    if (meta.generated_at) {
      lines.push(`<strong>Naposledy vygenerováno:</strong> ${escapeHtml(String(meta.generated_at))}`);
    }
    if (meta.source_log) {
      lines.push(`<strong>Zdrojový log:</strong> <code>${escapeHtml(String(meta.source_log))}</code>`);
    }
    if (meta.ok === false && meta.error) {
      lines.push(
        `<span class="error-inline"><strong>Poslední generování:</strong> ${escapeHtml(String(meta.error))}</span>`,
      );
    }
    statusEl.innerHTML = `<div class="global-admin-summary-card">${lines.join('<br/>')}</div>`;
  } catch (e) {
    statusEl.innerHTML = `<div class="error">Stav se nepodařilo načíst: ${escapeHtml(e.message || String(e))}</div>`;
  }

  releaseTrafficReportObjectUrl();
  iframe.removeAttribute('srcdoc');
  iframe.setAttribute('src', 'about:blank');

  try {
    const { ok, status, text } = await fetchAdminHtmlGet('/admin-api/traffic/report');
    if (!ok) {
      if (errEl) {
        errEl.style.display = 'block';
        errEl.innerHTML =
          status === 404 ? text : `Nepodařilo se načíst přehled (HTTP ${status}).`;
      }
      iframe.srcdoc = text && text.length ? text : '<!DOCTYPE html><html><body><p>Chyba načtení.</p></body></html>';
      return;
    }
    const blob = new Blob([text], { type: 'text/html;charset=utf-8' });
    trafficReportObjectUrl = URL.createObjectURL(blob);
    iframe.src = trafficReportObjectUrl;
  } catch (e) {
    if (errEl) {
      errEl.style.display = 'block';
      errEl.textContent = e.message || String(e);
    }
  }
}

async function regenerateTrafficReport() {
  const btn = document.getElementById('traffic-report-regenerate-btn');
  if (btn) {
    btn.disabled = true;
  }
  try {
    await apiRequest('POST', '/admin-api/traffic/report/regenerate', {});
    await loadTrafficReportSection();
  } catch (e) {
    showGlobalError(e.message || String(e));
  } finally {
    if (btn) {
      btn.disabled = false;
    }
  }
}

async function loadVehicleLifecycleSection() {
  try {
    const data = await apiRequest('GET', '/admin-api/vehicle-lifecycle?limit=100');
    const wrap = document.getElementById('vehicle-lifecycle-table');
    if (!wrap) return;
    const rows = (data.items || []).map((row) => `
      <tr>
        <td>${escapeHtml(String(row.vehicle_id ?? ''))}</td>
        <td>${escapeHtml(row.vin || '')}</td>
        <td>${escapeHtml(row.plate || '')}</td>
        <td>${escapeHtml(row.lifecycle_phase || '')}</td>
        <td>${escapeHtml(row.reason_code || '')}</td>
        <td>${escapeHtml(row.recipient_email || '')}</td>
      </tr>
    `).join('');
    wrap.innerHTML = `
      <table class="tool-table">
        <thead><tr><th>ID</th><th>VIN</th><th>SPZ</th><th>Fáze</th><th>Důvod</th><th>Příjemce</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="6">Žádné záznamy</td></tr>'}</tbody>
      </table>`;
  } catch (err) {
    showGlobalError(err?.message || String(err));
  }
}

// ============================================
// OVERVIEW SECTION
// ============================================

function adminPriorityClass(severity) {
  const normalized = String(severity || '').toLowerCase();
  if (normalized === 'critical') return 'is-critical';
  if (normalized === 'warning') return 'is-warning';
  if (normalized === 'ok') return 'is-ok';
  return '';
}

function formatMoneyHalers(amount, currency = 'CZK') {
  if (amount === null || amount === undefined || amount === '') return '-';
  const value = Number(amount) / 100;
  if (!Number.isFinite(value)) return '-';
  return `${value.toLocaleString('cs-CZ', { maximumFractionDigits: 2 })} ${currency || 'CZK'}`;
}

async function loadAdminToday() {
  const el = document.getElementById('admin-today-panel');
  if (!el) return;
  el.innerHTML = '<div class="loading">Načítám pracovní přehled...</div>';
  try {
    const data = await apiRequest('GET', '/admin-api/admin-home');
    const priorities = Array.isArray(data.priorities) ? data.priorities : [];
    const requests = Array.isArray(data.pending_service_requests) ? data.pending_service_requests : [];
    const payments = Array.isArray(data.payment_attention) ? data.payment_attention : [];
    const licenses = Array.isArray(data.expired_licenses) ? data.expired_licenses : [];
    const errors = Array.isArray(data.recent_errors) ? data.recent_errors : [];
    const security = data.security || {};
    const backup = data.backup || {};

    el.innerHTML = `
      <div class="admin-today-hero">
        <div>
          <span class="eyebrow">Pracovní přehled</span>
          <h2>Admin nemusí lovit v systému. Tady jsou věci, které chtějí pozornost.</h2>
          <p>Aktualizováno: ${escapeHtml(formatDateTime(data.timestamp))}</p>
        </div>
        <div class="admin-today-security">
          <span>Vaše IP</span>
          <strong>${escapeHtml(security.current_ip || '-')}</strong>
          <small>Allowlist: ${security.admin_allowlist_configured ? 'nastaven' : 'není nastaven'}</small>
        </div>
      </div>
      <div class="admin-priority-grid">
        ${priorities.map((item) => `
          <button type="button" class="admin-priority-card ${adminPriorityClass(item.severity)}" onclick="switchSection('${escapeHtml(item.section || 'overview')}')">
            <span>${escapeHtml(item.label || '-')}</span>
            <strong>${Number(item.count || 0).toLocaleString('cs-CZ')}</strong>
            <small>${escapeHtml(item.hint || '')}</small>
          </button>
        `).join('')}
      </div>
      <div class="admin-today-grid">
        <article class="admin-work-card">
          <h3>Čekající servisy</h3>
          ${requests.length ? requests.map((row) => `
            <div class="admin-work-row">
              <div><strong>${escapeHtml(row.service_name || row.email || '-')}</strong><span>${escapeHtml(row.email || '')} · ${escapeHtml(row.city || '')}</span></div>
              <button class="btn-secondary btn-sm" type="button" onclick="switchSection('services')">Vyřešit</button>
            </div>
          `).join('') : '<div class="empty">Žádná čekající servisní registrace.</div>'}
        </article>
        <article class="admin-work-card">
          <h3>Platby a licence</h3>
          ${payments.length ? payments.slice(0, 5).map((row) => `
            <div class="admin-work-row">
              <div><strong>${escapeHtml(row.email || row.trans_id || '-')}</strong><span>${escapeHtml(row.provider_status || row.event_type || '-')} · ${formatMoneyHalers(row.amount_halers, row.currency)}</span></div>
              ${row.user_id ? `<button class="btn-secondary btn-sm" type="button" onclick="openUserDetail(${Number(row.user_id)}, 'timeline')">Detail</button>` : ''}
            </div>
          `).join('') : '<div class="empty">Žádné problémové platby v posledních 14 dnech.</div>'}
          ${licenses.length ? `<div class="admin-work-note">${licenses.length} expirovaných licencí čeká na kontrolu.</div>` : ''}
        </article>
        <article class="admin-work-card">
          <h3>Bezpečnost a backup</h3>
          <div class="admin-work-row"><div><strong>Neúspěšné login pokusy 24h</strong><span>${Number(security.failed_logins_24h || 0).toLocaleString('cs-CZ')}</span></div><button class="btn-secondary btn-sm" type="button" onclick="switchSection('security')">Otevřít</button></div>
          <div class="admin-work-row"><div><strong>Aktivní blokace IP</strong><span>${Number(security.blocked_ips_active || 0).toLocaleString('cs-CZ')}</span></div><button class="btn-secondary btn-sm" type="button" onclick="switchSection('security')">Detail</button></div>
          <div class="admin-work-row"><div><strong>Backup</strong><span>${backup.warning ? 'Chybí nebo je starší než 72 h' : 'OK'} · ${Number(backup.count || 0).toLocaleString('cs-CZ')} snapshotů</span></div><button class="btn-secondary btn-sm" type="button" onclick="switchSection('system')">Systém</button></div>
        </article>
        <article class="admin-work-card">
          <h3>Poslední chyby</h3>
          ${errors.length ? errors.slice(0, 6).map((row) => `
            <div class="admin-work-row">
              <div><strong>${escapeHtml(row.action || row.source || '-')}</strong><span>${escapeHtml(row.actor || '-')} · ${escapeHtml(row.result || '')} · ${escapeHtml(formatDateTime(row.created_at))}</span></div>
            </div>
          `).join('') : '<div class="empty">Žádné nové kritické chyby.</div>'}
        </article>
      </div>
    `;
  } catch (error) {
    el.innerHTML = `<div class="error">Nepodařilo se načíst pracovní přehled: ${escapeHtml(error.message || String(error))}</div>`;
  }
}

async function loadOverview() {
  try {
    loadAdminToday();
    const stats = await apiRequest('GET', '/admin-api/overview');
    const activeUsersCount = stats.total_users ?? 0;
    
    // Aktualizovat statistiky v navbaru
    document.getElementById('summary-users').innerHTML = `👥 Uživatelé: <strong>${activeUsersCount}</strong>`;
    document.getElementById('summary-vehicles').innerHTML = `🚗 Vozidla: <strong>${stats.total_vehicles ?? 0}</strong>`;
    document.getElementById('summary-services').innerHTML = `🛠 Servisy: <strong>${stats.total_services ?? 0}</strong>`;
    document.getElementById('summary-records').innerHTML = `📋 Záznamy: <strong>${stats.total_records ?? 0}</strong>`;
    
    // Zobrazit statistiky
    const statsEl = document.getElementById('overview-stats');
    if (statsEl) {
      statsEl.innerHTML = `
        <button type="button" class="overview-stat overview-stat--action" data-admin-section="users" title="Otevřít sekci Uživatelé">
          <span class="overview-stat-ico" aria-hidden="true">👥</span>
          <span class="overview-stat-val">${activeUsersCount}</span>
          <span class="overview-stat-lbl">Uživatelé</span>
        </button>
        <button type="button" class="overview-stat overview-stat--action" data-admin-section="vehicles" title="Otevřít sekci Vozidla">
          <span class="overview-stat-ico" aria-hidden="true">🚗</span>
          <span class="overview-stat-val">${stats.total_vehicles ?? 0}</span>
          <span class="overview-stat-lbl">Vozidla</span>
        </button>
        <button type="button" class="overview-stat overview-stat--action" data-admin-section="services" title="Otevřít sekci Servisy">
          <span class="overview-stat-ico" aria-hidden="true">🛠</span>
          <span class="overview-stat-val">${stats.total_services ?? 0}</span>
          <span class="overview-stat-lbl">Servisy</span>
        </button>
        <button type="button" class="overview-stat overview-stat--action" data-admin-section="records" title="Otevřít sekci Záznamy">
          <span class="overview-stat-ico" aria-hidden="true">📋</span>
          <span class="overview-stat-val">${stats.total_records ?? 0}</span>
          <span class="overview-stat-lbl">Servisní záznamy</span>
        </button>
        <div class="overview-stat overview-stat--passive" title="Souhrnný údaj (bez přímé sekce v menu)">
          <span class="overview-stat-ico" aria-hidden="true">🔗</span>
          <span class="overview-stat-val">${stats.total_assignments ?? 0}</span>
          <span class="overview-stat-lbl">Přiřazení</span>
        </div>
      `;
    }
    
    // Načíst poslední aktivitu
    loadRecentActivity();
    
  } catch (error) {
    console.error('Error loading overview:', error);
  }
}

function appCenterStatusLabel(status) {
  const normalized = String(status || '').toLowerCase();
  if (normalized === 'ok') return 'OK';
  if (normalized === 'warning') return 'Pozornost';
  if (normalized === 'error') return 'Chyba';
  return 'Neznámé';
}

function appCenterStatusClass(status) {
  const normalized = String(status || '').toLowerCase();
  if (normalized === 'ok') return 'is-ok';
  if (normalized === 'warning') return 'is-warning';
  if (normalized === 'error') return 'is-critical';
  return '';
}

function formatAppMetricValue(value) {
  if (value === null || value === undefined || value === '') return '-';
  if (typeof value === 'boolean') return value ? 'ANO' : 'NE';
  if (typeof value === 'number') return value.toLocaleString('cs-CZ');
  return String(value);
}

function runAppCenterAction(actionType, target) {
  const type = String(actionType || '');
  const destination = String(target || '');
  if (!destination) return;
  if (type === 'section') {
    switchSection(destination);
    return;
  }
  if (type === 'url') {
    window.open(destination, '_blank', 'noopener');
    return;
  }
  if (type === 'global_filter') {
    switchSection('global-admin');
    setTimeout(() => {
      const select = document.getElementById('global-admin-type');
      if (select) select.value = destination;
      loadGlobalAdmin();
    }, 0);
    return;
  }
  if (type === 'control_center') {
    switchSection('control-center');
    setTimeout(() => {
      const detailsMap = {
        payments: 'cc-payments-details',
        notifications: 'cc-notifications-details',
        security: 'cc-security-details',
      };
      const detailId = detailsMap[destination];
      if (detailId) openControlCenterModuleDetails(detailId);
      if (destination === 'payments') loadControlCenterPayments();
      if (destination === 'notifications') loadControlCenterNotifications();
      if (destination === 'security') loadControlCenterSecurityMonitor();
    }, 0);
    return;
  }
  if (type === 'command') {
    executeAppCenterCommand(destination);
  }
}

async function executeAppCenterCommand(commandKey) {
  if (!commandKey) return;
  const needsConfirm = ['payments.resync', 'backup.create'].includes(commandKey);
  if (needsConfirm && !confirm(`Spustit rychlou akci ${commandKey}?`)) return;
  try {
    const data = await apiRequest('POST', `/admin-api/app-center/actions/${encodeURIComponent(commandKey)}`, {});
    showSuccess(`Akce ${commandKey} dokončena`);
    console.info('App center action result:', data);
    await loadAppCenter();
    if (currentSection === 'overview') {
      await loadAdminToday();
    }
  } catch (error) {
    showGlobalError(error.message || String(error));
  }
}

async function loadAppCenter() {
  const grid = document.getElementById('app-center-grid');
  const summary = document.getElementById('app-center-summary');
  if (!grid) return;
  grid.innerHTML = '<div class="loading">Načítám centrum aplikace...</div>';
  try {
    const data = await apiRequest('GET', '/admin-api/app-center/modules');
    const modules = Array.isArray(data.modules) ? data.modules : [];
    const counts = data.status_counts || {};
    if (summary) {
      summary.innerHTML = `
        <span class="global-admin-chip"><span>Moduly</span><strong>${modules.length.toLocaleString('cs-CZ')}</strong></span>
        <span class="global-admin-chip"><span>OK</span><strong>${Number(counts.ok || 0).toLocaleString('cs-CZ')}</strong></span>
        <span class="global-admin-chip"><span>Pozornost</span><strong>${Number(counts.warning || 0).toLocaleString('cs-CZ')}</strong></span>
        <span class="global-admin-chip"><span>Chyby</span><strong>${Number(counts.error || 0).toLocaleString('cs-CZ')}</strong></span>
      `;
    }
    if (!modules.length) {
      grid.innerHTML = '<div class="empty">Žádné moduly nebyly nalezeny.</div>';
      return;
    }
    const groups = [...new Set(modules.map((item) => item.group || 'Ostatní'))];
    grid.innerHTML = groups.map((group) => {
      const groupModules = modules.filter((item) => (item.group || 'Ostatní') === group);
      return `
        <section class="app-center-group">
          <h2>${escapeHtml(group)}</h2>
          <div class="app-center-cards">
            ${groupModules.map((module) => {
              const metrics = module.metrics || {};
              const actions = Array.isArray(module.actions) ? module.actions : [];
              const notes = Array.isArray(module.notes) ? module.notes : [];
              return `
                <article class="app-center-card ${appCenterStatusClass(module.status)}">
                  <div class="app-center-card-head">
                    <div>
                      <h3>${escapeHtml(module.label || module.key || '-')}</h3>
                      <p>${escapeHtml(module.description || '')}</p>
                    </div>
                    <span class="app-center-status">${escapeHtml(appCenterStatusLabel(module.status))}</span>
                  </div>
                  <div class="app-center-metrics">
                    ${Object.entries(metrics).map(([key, value]) => `
                      <div><span>${escapeHtml(key)}</span><strong>${escapeHtml(formatAppMetricValue(value))}</strong></div>
                    `).join('') || '<div><span>Stav</span><strong>Bez metrik</strong></div>'}
                  </div>
                  ${notes.length ? `<div class="app-center-notes">${notes.map((note) => `<span>${escapeHtml(note)}</span>`).join('')}</div>` : ''}
                  <div class="app-center-actions">
                    ${actions.map((action) => `
                      <button class="btn-secondary btn-sm" type="button" onclick="runAppCenterAction(decodeURIComponent('${encodeURIComponent(action.type || '')}'), decodeURIComponent('${encodeURIComponent(action.target || '')}'))">${escapeHtml(action.label || action.target || 'Akce')}</button>
                    `).join('')}
                  </div>
                </article>
              `;
            }).join('')}
          </div>
        </section>
      `;
    }).join('');
  } catch (error) {
    grid.innerHTML = `<div class="error">Centrum aplikace se nepodařilo načíst: ${escapeHtml(error.message || String(error))}</div>`;
  }
}

async function loadMdcrOpenData() {
  const statusEl = document.getElementById('mdcr-open-data-status');
  const fieldsEl = document.getElementById('mdcr-open-data-fields');
  const importsEl = document.getElementById('mdcr-open-data-imports');
  const legalEl = document.getElementById('mdcr-legal-panel');
  const urlEl = document.getElementById('mdcr-source-url');
  if (statusEl) statusEl.innerHTML = '<span class="global-admin-chip"><span>Stav</span><strong>Načítám...</strong></span>';
  try {
    const data = await apiRequest('GET', '/admin-api/mdcr-open-data/status');
    if (urlEl) urlEl.value = data.latest_source?.source_url || data.default_source_url || '';
    const tables = data.tables || {};
    const tableOk = Object.values(tables).every(Boolean);
    if (statusEl) {
      statusEl.innerHTML = `
        <span class="global-admin-chip"><span>Vozidla s VIN</span><strong>${Number(data.vehicles_with_vin || 0).toLocaleString('cs-CZ')}</strong></span>
        <span class="global-admin-chip"><span>DB tabulky</span><strong>${tableOk ? 'OK' : 'Chybí'}</strong></span>
        <span class="global-admin-chip"><span>Nejnovější MDČR data</span><strong>${escapeHtml(data.latest_source?.dataset_date || 'nezjištěno')}</strong></span>
        <span class="global-admin-chip"><span>Zdroj</span><strong>${escapeHtml(data.source_label || 'MDČR')}</strong></span>
        <span class="global-admin-chip"><span>Poslední import</span><strong>${escapeHtml(data.latest_import?.created_at || 'zatím žádný')}</strong></span>
      `;
    }
    if (fieldsEl) {
      const fields = Array.isArray(data.what_is_imported) ? data.what_is_imported : [];
      fieldsEl.innerHTML = fields.map((item) => `<span>${escapeHtml(item)}</span>`).join('');
    }
    if (legalEl) {
      legalEl.innerHTML = renderMdcrLegalNotice(data.legal_notice || {});
    }
    await loadMdcrOpenDataImports();
  } catch (error) {
    if (statusEl) statusEl.innerHTML = `<div class="error">MDČR stav se nepodařilo načíst: ${escapeHtml(error.message || String(error))}</div>`;
    if (importsEl) importsEl.innerHTML = '';
  }
}

function renderMdcrLegalNotice(notice) {
  const links = Array.isArray(notice.links) ? notice.links : [];
  const rules = Array.isArray(notice.usage_rules) ? notice.usage_rules : [];
  const datasets = Array.isArray(notice.supported_datasets) ? notice.supported_datasets : [];
  return `
    <section class="mdcr-compliance-card">
      <div class="mdcr-compliance-head">
        <div>
          <h2>Právní a zdrojový režim použití dat</h2>
          <p>${escapeHtml(notice.freshness_notice || '')}</p>
        </div>
        <span>${escapeHtml(notice.status || 'open_data')}</span>
      </div>
      <div class="mdcr-compliance-grid">
        <div><span>Poskytovatel</span><strong>${escapeHtml(notice.provider || 'Ministerstvo dopravy ČR')}</strong></div>
        <div><span>Katalog</span><strong>${escapeHtml(notice.catalog || 'data.gov.cz')}</strong></div>
        <div><span>Atribuce</span><strong>${escapeHtml(notice.attribution || '')}</strong></div>
        <div><span>Upozornění</span><strong>${escapeHtml(notice.not_official_app_notice || '')}</strong></div>
      </div>
      <details class="mdcr-compliance-details">
        <summary>Zobrazit pravidla správného použití a rozšiřování dat</summary>
        <div class="mdcr-compliance-lists">
          <div>
            <h3>Pravidla použití</h3>
            <ul>${rules.map((rule) => `<li>${escapeHtml(rule)}</li>`).join('')}</ul>
          </div>
          <div>
            <h3>Oficiální odkazy</h3>
            <ul>${links.map((link) => `<li><a href="${escapeHtml(link.url || '#')}" target="_blank" rel="noopener">${escapeHtml(link.label || link.url || '')}</a></li>`).join('')}</ul>
          </div>
        </div>
        <h3>Datové sady</h3>
        <div class="mdcr-dataset-list">
          ${datasets.map((dataset) => `
            <article>
              <strong>${escapeHtml(dataset.label || dataset.key || '')}</strong>
              <span>${escapeHtml(dataset.status || '')}</span>
              <p>${escapeHtml(dataset.purpose || '')}</p>
            </article>
          `).join('')}
        </div>
      </details>
    </section>
  `;
}

async function loadMdcrOpenDataImports() {
  const importsEl = document.getElementById('mdcr-open-data-imports');
  if (!importsEl) return;
  try {
    const data = await apiRequest('GET', '/admin-api/mdcr-open-data/imports?limit=30');
    const rows = Array.isArray(data.items) ? data.items : [];
    if (!rows.length) {
      importsEl.innerHTML = '<div class="empty">Zatím tu není žádný lokální import.</div>';
      return;
    }
    importsEl.innerHTML = `
      <table class="data-table">
        <thead><tr><th>Čas</th><th>Vozidlo</th><th>VIN</th><th>Stav</th><th>Zpráva</th></tr></thead>
        <tbody>
          ${rows.map((row) => `
            <tr>
              <td>${escapeHtml(formatDateTime(row.created_at))}</td>
              <td>#${escapeHtml(String(row.vehicle_id || ''))}</td>
              <td>${escapeHtml(row.vin || '')}</td>
              <td>${escapeHtml(row.status || '')}</td>
              <td>${escapeHtml(row.message || '')}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  } catch (error) {
    importsEl.innerHTML = `<div class="error">Importy se nepodařilo načíst: ${escapeHtml(error.message || String(error))}</div>`;
  }
}

function renderMdcrRecordTable(records, title, emptyText, includeRaw = false) {
  const rows = Array.isArray(records) ? records : [];
  if (!rows.length) {
    return `<div class="empty">${escapeHtml(emptyText || 'Žádné záznamy.')}</div>`;
  }
  return `
    <h3>${escapeHtml(title)}</h3>
    <div class="tool-table-wrap">
      <table class="data-table mdcr-record-table">
        <thead><tr><th>VIN</th><th>Datum</th><th>Typ</th><th>Výsledek</th><th>Km</th><th>STK do</th><th>Vozidlo</th><th>Stanice</th><th>Protokol</th>${includeRaw ? '<th>Raw</th>' : ''}</tr></thead>
        <tbody>
          ${rows.map((row) => `
            <tr>
              <td>${escapeHtml(row.vin || '')}</td>
              <td>${escapeHtml(formatDateTime(row.inspection_date || row.inspection_date_raw))}</td>
              <td>${escapeHtml(row.inspection_type || '')}</td>
              <td>${escapeHtml(row.result_label || '')}</td>
              <td>${escapeHtml(row.odometer_km == null ? '' : Number(row.odometer_km).toLocaleString('cs-CZ'))}</td>
              <td>${escapeHtml(row.next_inspection_date || row.next_inspection_date_raw || '')}</td>
              <td>${escapeHtml([row.brand, row.model].filter(Boolean).join(' '))}</td>
              <td>${escapeHtml(row.station_name || row.station_code || '')}</td>
              <td>${escapeHtml(row.protocol_number || '')}</td>
              ${includeRaw ? `
                <td>
                  <details class="mdcr-raw-details">
                    <summary>JSON</summary>
                    <pre>${escapeHtml(JSON.stringify(row, null, 2))}</pre>
                  </details>
                </td>
              ` : ''}
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;
}

function renderMdcrRecordCards(records, title, emptyText) {
  const rows = Array.isArray(records) ? records : [];
  if (!rows.length) {
    return `<div class="empty">${escapeHtml(emptyText || 'Žádné záznamy.')}</div>`;
  }
  return `
    <section class="mdcr-visible-data-panel">
      <div class="mdcr-visible-data-head">
        <div>
          <h3>${escapeHtml(title)}</h3>
          <p>Tyto řádky jsou už rozbalené z MDČR GZIP/XML souboru a zobrazené přímo v aplikaci.</p>
        </div>
        <span>${rows.length.toLocaleString('cs-CZ')} řádků</span>
      </div>
      <div class="mdcr-record-cards">
        ${rows.map((row, index) => `
          <article class="mdcr-record-card">
            <div class="mdcr-record-card-head">
              <strong>${escapeHtml(row.vin || 'VIN neuveden')}</strong>
              <span>Řádek ${Number(index + 1).toLocaleString('cs-CZ')}</span>
            </div>
            <dl>
              <div><dt>Datum prohlídky</dt><dd>${escapeHtml(formatDateTime(row.inspection_date || row.inspection_date_raw) || '-')}</dd></div>
              <div><dt>Druh prohlídky</dt><dd>${escapeHtml(row.inspection_type || '-')}</dd></div>
              <div><dt>Výsledek</dt><dd>${escapeHtml(row.result_label || '-')}</dd></div>
              <div><dt>Tachometr</dt><dd>${escapeHtml(row.odometer_km == null ? '-' : `${Number(row.odometer_km).toLocaleString('cs-CZ')} km`)}</dd></div>
              <div><dt>Příští STK</dt><dd>${escapeHtml(row.next_inspection_date || row.next_inspection_date_raw || '-')}</dd></div>
              <div><dt>Vozidlo</dt><dd>${escapeHtml([row.brand, row.model].filter(Boolean).join(' ') || '-')}</dd></div>
              <div><dt>Stanice</dt><dd>${escapeHtml(row.station_name || row.station_code || '-')}</dd></div>
              <div><dt>Protokol</dt><dd>${escapeHtml(row.protocol_number || '-')}</dd></div>
            </dl>
            <details class="mdcr-raw-details">
              <summary>Zobrazit raw JSON tohoto řádku</summary>
              <pre>${escapeHtml(JSON.stringify(row, null, 2))}</pre>
            </details>
          </article>
        `).join('')}
      </div>
    </section>
  `;
}

function renderMdcrSearchedVehiclePanel(data, localVehicles) {
  const vehicles = Array.isArray(localVehicles) ? localVehicles : [];
  const normalizedVin = data.normalized_vin || data.vin || '';
  return `
    <section class="mdcr-visible-data-panel mdcr-searched-vehicle-panel">
      <div class="mdcr-visible-data-head">
        <div>
          <h3>Hledané vozidlo podle zadaného VIN</h3>
          <p>Zobrazuji jen vozidlo, které bylo zadané do pole VIN. Náhodné ukázkové řádky z jiných vozidel jsou schované pryč, aby to nemátlo.</p>
        </div>
        <span>${escapeHtml(normalizedVin)}</span>
      </div>
      ${vehicles.length ? `
        <div class="mdcr-record-cards">
          ${vehicles.map((vehicle) => `
            <article class="mdcr-record-card">
              <div class="mdcr-record-card-head">
                <strong>${escapeHtml(vehicle.plate || normalizedVin)}</strong>
                <span>Naše vozidlo #${escapeHtml(String(vehicle.id || ''))}</span>
              </div>
              <dl>
                <div><dt>VIN</dt><dd>${escapeHtml(normalizedVin)}</dd></div>
                <div><dt>Značka</dt><dd>${escapeHtml(vehicle.brand || '-')}</dd></div>
                <div><dt>Model</dt><dd>${escapeHtml(vehicle.model || '-')}</dd></div>
                <div><dt>Uživatel</dt><dd>${escapeHtml(vehicle.user_email || '-')}</dd></div>
                <div><dt>STK v aplikaci</dt><dd>${escapeHtml(vehicle.stk_valid_until || '-')}</dd></div>
                <div><dt>Poslední km v aplikaci</dt><dd>${escapeHtml(vehicle.latest_stk_odometer_km == null ? '-' : `${Number(vehicle.latest_stk_odometer_km).toLocaleString('cs-CZ')} km`)}</dd></div>
              </dl>
              <div class="mdcr-no-vin-match">
                MDČR data pro tento VIN v aktuálně čteném souboru/limitu nebyla nalezena.
              </div>
            </article>
          `).join('')}
        </div>
      ` : `
        <article class="mdcr-record-card">
          <div class="mdcr-record-card-head">
            <strong>${escapeHtml(normalizedVin)}</strong>
            <span>Zadaný VIN</span>
          </div>
          <div class="mdcr-no-vin-match">
            Tento VIN není v lokální databázi aplikace a v aktuálně čteném MDČR souboru/limitu pro něj nebyl nalezen záznam.
          </div>
        </article>
      `}
    </section>
  `;
}

function renderMdcrLocalVehicles(localVehicles, normalizedVin) {
  const vehicles = Array.isArray(localVehicles) ? localVehicles : [];
  if (!vehicles.length) {
    return '<p class="panel-subtle">Tento VIN zatím není v lokálních vozidlech aplikace.</p>';
  }
  return `
    <section class="mdcr-app-data-panel">
      <h3>Data uložená v naší aplikaci</h3>
      <p>Tyto hodnoty jsou naše lokální data pod aktuální kontrolou MDČR.</p>
      <div class="tool-table-wrap">
        <table class="data-table">
          <thead><tr><th>ID</th><th>VIN</th><th>SPZ</th><th>Značka</th><th>Model</th><th>Uživatel</th><th>STK v aplikaci</th><th>Poslední km v aplikaci</th></tr></thead>
          <tbody>
            ${vehicles.map((vehicle) => `
              <tr>
                <td>#${escapeHtml(String(vehicle.id || ''))}</td>
                <td>${escapeHtml(normalizedVin || '')}</td>
                <td>${escapeHtml(vehicle.plate || '')}</td>
                <td>${escapeHtml(vehicle.brand || '')}</td>
                <td>${escapeHtml(vehicle.model || '')}</td>
                <td>${escapeHtml(vehicle.user_email || '')}</td>
                <td>${escapeHtml(vehicle.stk_valid_until || '')}</td>
                <td>${escapeHtml(vehicle.latest_stk_odometer_km == null ? '' : Number(vehicle.latest_stk_odometer_km).toLocaleString('cs-CZ'))}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </section>
  `;
}

async function lookupMdcrVin(forceNoLimit = false) {
  const resultEl = document.getElementById('mdcr-vin-lookup-result');
  const vin = document.getElementById('mdcr-vin-lookup')?.value?.trim() || '';
  const sourceUrl = document.getElementById('mdcr-source-url')?.value?.trim() || '';
  const limitRaw = document.getElementById('mdcr-limit')?.value?.trim() || '';
  if (!vin) {
    if (resultEl) resultEl.innerHTML = '<div class="error">Zadej VIN, který chceš ověřit v MDČR datech.</div>';
    return;
  }
  const payload = {
    vin,
    source_url: sourceUrl || null,
    use_latest_source: true,
    limit: forceNoLimit ? null : (limitRaw ? Number(limitRaw) : null),
    max_matches: 50,
  };
  if (resultEl) resultEl.innerHTML = '<div class="loading">Hledám VIN v MDČR datasetu...</div>';
  try {
    const data = await apiRequest('POST', '/admin-api/mdcr-open-data/lookup-vin', payload);
    const matches = Array.isArray(data.matches) ? data.matches : [];
    const localVehicles = Array.isArray(data.local_vehicles) ? data.local_vehicles : [];
    const sourceMetadata = data.source_metadata || {};
    const sourceInfo = data.source_info || {};
    const legalNotice = data.legal_notice || {};
    if (!resultEl) return;
    resultEl.innerHTML = `
      <div class="section-header section-header-secondary">
        <div>
          <h2>Kontrolní protokol MDČR pro VIN ${escapeHtml(data.normalized_vin || vin)}</h2>
          <p class="section-subtitle">${escapeHtml(data.verification_note || '')}</p>
        </div>
      </div>
      <div class="mdcr-proof-card ${matches.length ? 'is-match' : 'is-miss'}">
        <strong>${matches.length ? 'VIN byl v tomto MDČR souboru nalezen.' : 'VIN v tomto rozsahu nebyl nalezen.'}</strong>
        <span>${matches.length ? 'Níže jsou přesné řádky, které by se importovaly.' : 'Níže je přesto vidět, že MDČR soubor se skutečně načetl a jaká data z něj chodí.'}</span>
      </div>
      <div class="mdcr-opened-card">
        <strong>${data.source_opened ? 'Soubor MDČR se podařilo otevřít a rozbalit.' : 'Soubor MDČR se nepodařilo otevřít.'}</strong>
        <span>${escapeHtml(data.source_opened_note || 'Níže se zobrazí dostupný obsah po zpracování aplikací.')}</span>
      </div>
      <div class="mdcr-compliance-mini">
        <strong>Oficiální zdroj a omezení tvrzení</strong>
        <span>${escapeHtml(legalNotice.attribution || 'Zdroj dat: Ministerstvo dopravy ČR / data.gov.cz.')} ${escapeHtml(legalNotice.not_official_app_notice || '')}</span>
      </div>
      <div class="global-admin-summary">
        <span class="global-admin-chip"><span>VIN</span><strong>${escapeHtml(data.normalized_vin || '')}</strong></span>
        <span class="global-admin-chip"><span>Aktuální dataset</span><strong>${escapeHtml(sourceInfo.dataset_date || 'nezjištěno')}</strong></span>
        <span class="global-admin-chip"><span>Lokální vozidla</span><strong>${Number(localVehicles.length || 0).toLocaleString('cs-CZ')}</strong></span>
        <span class="global-admin-chip"><span>Záznamy s VIN</span><strong>${Number(data.records_with_vin || 0).toLocaleString('cs-CZ')}</strong></span>
        <span class="global-admin-chip"><span>Prošlo záznamů</span><strong>${Number(data.scanned_records || 0).toLocaleString('cs-CZ')}</strong></span>
        <span class="global-admin-chip"><span>Nalezené shody</span><strong>${Number(data.matches_count || 0).toLocaleString('cs-CZ')}</strong></span>
        <span class="global-admin-chip"><span>Limit</span><strong>${escapeHtml(data.limit == null ? 'bez limitu' : String(data.limit))}</strong></span>
      </div>
      <div class="mdcr-source-card">
        <h3>Aktuální zdroj k okamžiku kliknutí</h3>
        <p class="panel-subtle">${escapeHtml(sourceInfo.title || 'Nejnovější dostupný distribuční soubor z data.gov.cz')} ${sourceInfo.warning ? `· ${escapeHtml(sourceInfo.warning)}` : ''}</p>
        <div class="mdcr-source-grid">
          <div><span>URL</span><a href="${escapeHtml(data.source_url || '#')}" target="_blank" rel="noopener">${escapeHtml(data.source_url || '')}</a></div>
          <div><span>Dataset na data.gov.cz</span>${sourceInfo.catalog_url ? `<a href="${escapeHtml(sourceInfo.catalog_url)}" target="_blank" rel="noopener">Otevřít katalog</a>` : '<strong>-</strong>'}</div>
          <div><span>Datum datasetu</span><strong>${escapeHtml(sourceInfo.dataset_date || '-')}</strong></div>
          <div><span>Zjištěno přes</span><strong>${escapeHtml(sourceInfo.resolved_by || '-')}</strong></div>
          <div><span>Finální URL</span><strong>${escapeHtml(sourceMetadata.final_url || data.source_url || '')}</strong></div>
          <div><span>HTTP status</span><strong>${escapeHtml(String(sourceMetadata.status_code || ''))}</strong></div>
          <div><span>Content-Type</span><strong>${escapeHtml(sourceMetadata.content_type || '')}</strong></div>
          <div><span>Formát</span><strong>${escapeHtml(sourceMetadata.detected_format || '')}</strong></div>
          <div><span>Content-Length</span><strong>${escapeHtml(sourceMetadata.content_length || 'neuvedeno')}</strong></div>
        </div>
      </div>
      ${matches.length
        ? renderMdcrRecordCards(matches, 'Aktuální hodnoty z MDČR pro zadaný VIN', 'Pro zadaný VIN není v aktuálním souboru žádný řádek.')
        : renderMdcrSearchedVehiclePanel(data, localVehicles)
      }
      ${renderMdcrLocalVehicles(localVehicles, data.normalized_vin || vin)}
      ${matches.length ? renderMdcrRecordTable(matches, 'Tabulkový pohled na shody pro zadaný VIN', 'V tomto datasetu a limitu nebyl pro zadaný VIN nalezen žádný záznam.', true) : ''}
    `;
  } catch (error) {
    if (resultEl) resultEl.innerHTML = `<div class="error">VIN lookup selhal: ${escapeHtml(error.message || String(error))}</div>`;
  }
}

function lookupMdcrVinWithoutLimit() {
  const limitEl = document.getElementById('mdcr-limit');
  if (limitEl) limitEl.value = '';
  lookupMdcrVin(true);
}

async function runMdcrOpenDataImport(forceDryRun = true) {
  const resultEl = document.getElementById('mdcr-open-data-result');
  const sourceUrl = document.getElementById('mdcr-source-url')?.value?.trim() || '';
  const limitRaw = document.getElementById('mdcr-limit')?.value?.trim() || '';
  const updateProfileEl = document.getElementById('mdcr-update-profile');
  const dryRun = forceDryRun ? true : false;
  if (!dryRun && !confirm('Spustit lokální zápis MDČR dat do historie vozidel a karet vozidel? Doporučený první krok je test bez zápisu.')) return;
  const payload = {
    source_url: sourceUrl || null,
    use_latest_source: true,
    dry_run: dryRun,
    limit: limitRaw ? Number(limitRaw) : null,
    update_vehicle_profile: Boolean(updateProfileEl?.checked ?? true),
  };
  if (resultEl) resultEl.innerHTML = '<div class="loading">Import běží, čtu stream z MDČR a páruji VIN...</div>';
  try {
    const data = await apiRequest('POST', '/admin-api/mdcr-open-data/import', payload);
    const samples = Array.isArray(data.sample_matches) ? data.sample_matches : [];
    if (resultEl) {
      resultEl.innerHTML = `
        <div class="success">${data.dry_run ? 'Test dokončen bez zápisu.' : 'Lokální import dokončen.'}</div>
        <div class="security-status-grid mdcr-result-grid">
          <article class="security-status-card"><span>Prošlo záznamů</span><strong>${Number(data.scanned_records || 0).toLocaleString('cs-CZ')}</strong></article>
          <article class="security-status-card"><span>Záznamy s VIN</span><strong>${Number(data.records_with_vin || 0).toLocaleString('cs-CZ')}</strong></article>
          <article class="security-status-card"><span>Nalezené záznamy</span><strong>${Number(data.matched_records || 0).toLocaleString('cs-CZ')}</strong></article>
          <article class="security-status-card"><span>Nalezená vozidla</span><strong>${Number(data.matched_vehicles || 0).toLocaleString('cs-CZ')}</strong></article>
          <article class="security-status-card"><span>STK historie</span><strong>+${Number(data.inspection_inserted || 0).toLocaleString('cs-CZ')} / ${Number(data.inspection_updated || 0).toLocaleString('cs-CZ')}</strong></article>
          <article class="security-status-card"><span>Karty vozidel</span><strong>${Number(data.vehicle_profile_updated || 0).toLocaleString('cs-CZ')}</strong></article>
        </div>
        ${samples.length ? `
          <h3>Ukázka nalezených shod</h3>
          <div class="tool-table-wrap">
            <table class="data-table">
              <thead><tr><th>Vozidlo</th><th>VIN</th><th>SPZ</th><th>Datum</th><th>Km</th><th>Výsledek</th></tr></thead>
              <tbody>
                ${samples.map((row) => `
                  <tr>
                    <td>#${escapeHtml(String(row.vehicle_id || ''))}</td>
                    <td>${escapeHtml(row.vin || '')}</td>
                    <td>${escapeHtml(row.plate || '')}</td>
                    <td>${escapeHtml(formatDateTime(row.inspection_date))}</td>
                    <td>${escapeHtml(row.odometer_km == null ? '' : Number(row.odometer_km).toLocaleString('cs-CZ'))}</td>
                    <td>${escapeHtml(row.result || '')}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        ` : '<p class="panel-subtle">V tomto rozsahu nebyla nalezena shoda na VIN v aplikaci. Zkus vyšší limit nebo plný import bez limitu.</p>'}
      `;
    }
    if (!data.dry_run) await loadMdcrOpenData();
  } catch (error) {
    if (resultEl) resultEl.innerHTML = `<div class="error">Import selhal: ${escapeHtml(error.message || String(error))}</div>`;
  }
}

async function loadRecentActivity() {
  try {
    const auditData = await apiRequest('GET', '/admin-api/audit?limit=5');
    const activityEl = document.getElementById('recent-activity');
    
    if (!activityEl) return;
    
    const logs = auditData.logs || [];
    const source = String(auditData.source || 'unknown');
    
    if (logs.length === 0) {
      activityEl.innerHTML = `<div class="empty">Žádná nedávná aktivita${source === 'audit_log' ? ' v append-only audit logu' : ''}</div>`;
      return;
    }
    
    activityEl.innerHTML = `
      <div class="activity-item" style="justify-content:flex-start; gap:8px; color:#64748b;">
        <strong>Zdroj:</strong> ${source === 'audit_log' ? 'append-only audit_log' : source}
      </div>
      ${logs.map(log => {
      const timestamp = log.timestamp ? formatDateTime(log.timestamp) : '-';
      const actor = log.actor_email || `Uživatel #${log.actor_user_id || '?'}`;
      const actionText = getActionText(log.action || '');
      const entityType = log.entity_type || '?';
      const entityId = log.entity_id || '?';
      
      return `
        <div class="activity-item">
          <span class="activity-time">${timestamp}</span>
          <span class="activity-actor">${actor}</span>
          <span class="activity-action">${actionText}</span>
          <span class="activity-entity">${entityType} #${entityId}</span>
        </div>
      `;
    }).join('')}`;
    
  } catch (error) {
    console.error('Error loading recent activity:', error);
  }
}

// ============================================
// GLOBAL ADMIN OVERSIGHT
// ============================================

function initGlobalAdminBindings() {
  const searchInput = document.getElementById('global-admin-search');
  const typeSelect = document.getElementById('global-admin-type');
  if (searchInput && searchInput.dataset.bound !== '1') {
    let searchTimer = null;
    searchInput.addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(loadGlobalAdmin, 250);
    });
    searchInput.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        loadGlobalAdmin();
      }
    });
    searchInput.dataset.bound = '1';
  }
  if (typeSelect && typeSelect.dataset.bound !== '1') {
    typeSelect.addEventListener('change', loadGlobalAdmin);
    typeSelect.dataset.bound = '1';
  }
}

function getGlobalAdminTypeLabel(type) {
  const labels = {
    user: 'Uživatel',
    service: 'Servis',
    vehicle: 'Vozidlo',
    record: 'Záznam',
    reservation: 'Rezervace',
    reminder: 'Připomínka',
    payment: 'Platba',
    audit: 'Audit',
  };
  return labels[type] || type || '-';
}

function getGlobalAdminTone(status) {
  const normalized = String(status || '').toLowerCase();
  if (['active', 'ok', 'paid', 'confirmed', 'completed'].includes(normalized)) return 'ok';
  if (['disabled', 'pending', 'created', 'warning'].includes(normalized)) return 'warn';
  if (['deleted', 'failed', 'cancelled', 'expired', 'suspended'].includes(normalized)) return 'bad';
  return '';
}

function renderGlobalAdminSummary(summary = {}) {
  const el = document.getElementById('global-admin-summary');
  if (!el) return;
  const order = ['user', 'service', 'vehicle', 'record', 'reservation', 'reminder', 'payment', 'audit'];
  el.innerHTML = order.map((type) => `
    <button class="global-admin-chip" type="button" onclick="filterGlobalAdminType('${type}')">
      <span>${escapeHtml(getGlobalAdminTypeLabel(type))}</span>
      <strong>${Number(summary[type] || 0).toLocaleString('cs-CZ')}</strong>
    </button>
  `).join('');
}

function renderGlobalAdminResults(items = []) {
  const el = document.getElementById('global-admin-results');
  if (!el) return;
  if (!items.length) {
    el.innerHTML = '<div class="empty">Nic nenalezeno. Zkuste email, SPZ, VIN, ID nebo část textu záznamu.</div>';
    return;
  }
  el.innerHTML = items.map((item) => {
    const type = String(item.type || '');
    const tone = getGlobalAdminTone(item.status);
    const statusClass = tone ? ` status-${tone}` : '';
    const timestamp = item.timestamp ? formatDateTime(item.timestamp) : '-';
    const tenant = item.tenant_id !== null && item.tenant_id !== undefined ? `Tenant ${item.tenant_id}` : 'Tenant -';
    return `
      <article class="global-admin-result">
        <div class="global-admin-result-main">
          <div class="global-admin-result-head">
            <span class="global-admin-type">${escapeHtml(getGlobalAdminTypeLabel(type))}</span>
            <h3>${escapeHtml(item.title || '-')}</h3>
            <span class="card-id">#${escapeHtml(String(item.id ?? '-'))}</span>
          </div>
          <div class="global-admin-result-subtitle">${escapeHtml(item.subtitle || '-')}</div>
          <div class="global-admin-result-meta">${escapeHtml(item.meta || '-')}</div>
        </div>
        <div class="global-admin-result-state">
          <span class="status-pill${statusClass}">${escapeHtml(item.status || '-')}</span>
          <span>${escapeHtml(tenant)}</span>
          <span>${escapeHtml(timestamp)}</span>
        </div>
        <div class="global-admin-result-actions">
          ${renderGlobalAdminActions(item)}
        </div>
      </article>
    `;
  }).join('');
}

function renderGlobalAdminActions(item) {
  const type = String(item.type || '');
  const id = Number(item.id || 0);
  const userId = Number(item.user_id || 0);
  const vehicleId = Number(item.vehicle_id || 0);
  const buttons = [];

  if (userId) {
    buttons.push(`<button class="btn-secondary btn-sm" type="button" onclick="openUserDetail(${userId})">Detail účtu</button>`);
    buttons.push(`<button class="btn-secondary btn-sm" type="button" onclick="openGlobalAdminUserInControlCenter(${userId})">Insight</button>`);
  }
  if (type === 'service' && id) {
    buttons.push(`<button class="btn-edit btn-sm" type="button" onclick="editService(${id})">Upravit servis</button>`);
  } else if (type === 'vehicle' && id) {
    buttons.push(`<button class="btn-edit btn-sm" type="button" onclick="editVehicle(${id})">Upravit vozidlo</button>`);
    buttons.push(`<button class="btn-danger btn-sm" type="button" onclick="deleteVehicle(${id}, 'vozidlo #${id}')">Smazat</button>`);
  } else if (type === 'record' && id) {
    buttons.push(`<button class="btn-edit btn-sm" type="button" onclick="editRecord(${id})">Upravit záznam</button>`);
    buttons.push(`<button class="btn-danger btn-sm" type="button" onclick="deleteRecord(${id})">Smazat</button>`);
  } else if (type === 'audit') {
    buttons.push(`<button class="btn-secondary btn-sm" type="button" onclick="switchSection('audit')">Audit log</button>`);
  }
  if (vehicleId && type !== 'vehicle') {
    buttons.push(`<button class="btn-secondary btn-sm" type="button" onclick="openGlobalAdminVehicle(${vehicleId})">Vozidlo</button>`);
  }
  return buttons.join('') || '<span class="list-meta">Bez rychlé akce</span>';
}

function filterGlobalAdminType(type) {
  const select = document.getElementById('global-admin-type');
  if (select) {
    select.value = type;
  }
  loadGlobalAdmin();
}

async function openGlobalAdminVehicle(vehicleId) {
  switchSection('vehicles');
  const search = document.getElementById('vehicle-search');
  if (search) {
    search.value = `#${vehicleId}`;
    search.dispatchEvent(new Event('input'));
  }
}

async function openGlobalAdminUserInControlCenter(userId) {
  switchSection('control-center');
  const input = document.getElementById('cc-insight-user-id');
  if (input) input.value = String(userId);
  await loadControlCenterUserInsight();
}

async function loadGlobalAdmin() {
  const resultsEl = document.getElementById('global-admin-results');
  if (!resultsEl) return;
  initGlobalAdminBindings();
  resultsEl.innerHTML = '<div class="loading">Načítám globální dohled...</div>';
  try {
    const query = (document.getElementById('global-admin-search')?.value || '').trim();
    const entityType = (document.getElementById('global-admin-type')?.value || '').trim();
    const url = withQueryParams('/admin-api/global-admin/search', {
      q: query || null,
      entity_type: entityType || null,
      limit: 120,
    });
    const data = await apiRequest('GET', url);
    renderGlobalAdminSummary(data.summary || {});
    renderGlobalAdminResults(data.items || []);
  } catch (error) {
    resultsEl.innerHTML = `<div class="error">Chyba při načítání globálního dohledu: ${escapeHtml(error.message || 'Neznámá chyba')}</div>`;
  }
}

function truncateDemoAccessUa(value, maxLen = 96) {
  const s = String(value || '').trim();
  if (!s) return '-';
  const shortened = s.length > maxLen ? `${s.slice(0, maxLen)}…` : s;
  return escapeHtml(shortened);
}

async function loadDemoAccessLeads() {
  const tableEl = document.getElementById('demo-access-table');
  const summaryEl = document.getElementById('demo-access-summary');
  const noteEl = document.getElementById('demo-access-note');
  if (!tableEl) return;
  setControlCenterTableLoading('demo-access-table', 'Načítám přehled žádostí o ukázku…');
  if (noteEl) {
    noteEl.classList.add('hidden');
    noteEl.textContent = '';
  }
  try {
    const search = (document.getElementById('demo-access-search')?.value || '').trim();
    const params = new URLSearchParams({ limit: '500', offset: '0' });
    if (search) params.set('search', search);
    const data = await apiRequest('GET', `/admin-api/demo-access-leads?${params.toString()}`);
    const summary = data.summary || {};
    if (summaryEl) {
      summaryEl.innerHTML = `
        <div class="cc-metric-grid" style="margin-bottom: 8px;">
          <div class="cc-metric-item"><span>Odeslaných odkazů (celkem)</span><strong>${Number(summary.total_requests ?? 0).toLocaleString('cs-CZ')}</strong></div>
          <div class="cc-metric-item"><span>Unikátních e-mailů</span><strong>${Number(summary.unique_visitor_emails ?? 0).toLocaleString('cs-CZ')}</strong></div>
          <div class="cc-metric-item"><span>Uplatněných odkazů</span><strong>${Number(summary.consumed_total ?? 0).toLocaleString('cs-CZ')}</strong></div>
          <div class="cc-metric-item"><span>Za posledních 24 h</span><strong>${Number(summary.last_24h_requests ?? 0).toLocaleString('cs-CZ')}</strong></div>
        </div>
      `;
    }
    const items = Array.isArray(data.items) ? data.items : [];
    const filteredTotal = summary.filtered_total != null ? Number(summary.filtered_total) : items.length;
    if (noteEl) {
      const parts = [];
      if (data.note) parts.push(String(data.note));
      if (Number.isFinite(filteredTotal) && items.length < filteredTotal) {
        parts.push(`Zobrazeno ${items.length} z ${filteredTotal} záznamů (maximum 500 na jedno načtení).`);
      }
      noteEl.textContent = parts.join(' ');
      noteEl.classList.toggle('hidden', parts.length === 0);
    }
    renderControlCenterTable('demo-access-table', [
      { key: 'visitor_email', label: 'E-mail (odeslán odkaz)', render: (row) => escapeHtml(row.visitor_email || '-') },
      { key: 'created_at', label: 'Požadavek', render: (row) => escapeHtml(formatDateTime(row.created_at)) },
      { key: 'expires_at', label: 'Platnost do', render: (row) => escapeHtml(formatDateTime(row.expires_at)) },
      {
        key: 'consumed_at',
        label: 'Odkaz použit',
        render: (row) => (row.consumed_at ? escapeHtml(formatDateTime(row.consumed_at)) : 'ne'),
      },
      { key: 'client_ip', label: 'IP (žádost)', render: (row) => escapeHtml(row.client_ip || '-') },
      { key: 'user_agent', label: 'User-Agent', render: (row) => truncateDemoAccessUa(row.user_agent) },
    ], items);
  } catch (error) {
    tableEl.innerHTML = `<div class="error">Nepodařilo se načíst přehled demo: ${escapeHtml(error.message || 'Chyba')}</div>`;
  }
}

function getActionText(action) {
  const actionMap = {
    'CREATE_USER': 'vytvořil uživatele',
    'UPDATE_USER': 'aktualizoval uživatele',
    'DELETE_USER': 'smazal uživatele',
    'CREATE_VEHICLE': 'vytvořil vozidlo',
    'UPDATE_VEHICLE': 'aktualizoval vozidlo',
    'DELETE_VEHICLE': 'smazal vozidlo',
    'CREATE_SERVICE': 'vytvořil servis',
    'UPDATE_SERVICE': 'aktualizoval servis',
    'DELETE_SERVICE': 'smazal servis',
    'CREATE_SERVICE_RECORD': 'vytvořil servisní záznam',
    'UPDATE_SERVICE_RECORD': 'aktualizoval servisní záznam',
    'DELETE_SERVICE_RECORD': 'smazal servisní záznam',
  };
  return actionMap[action] || action;
}

// ============================================
// USERS CRUD
// ============================================

function scheduleUsersSearchRefetch() {
  clearTimeout(usersSearchDebounceTimer);
  usersSearchDebounceTimer = setTimeout(() => {
    void refetchUsersListForSearch(false);
  }, 320);
}

async function refetchUsersListForSearch(refreshArchive) {
  const container = document.getElementById('users-cards-container');
  const searchInput = document.getElementById('user-search');
  const q = (searchInput?.value || '').trim();
  const gen = ++usersListFetchGeneration;
  if (container) {
    container.innerHTML = '<div class="loading">Načítám…</div>';
  }
  const paginationEl = document.getElementById('users-pagination');
  if (paginationEl) {
    paginationEl.classList.add('hidden');
    paginationEl.innerHTML = '';
  }
  try {
    const rows = await fetchAllList(
      '/admin-api/users',
      LIST_FETCH_PAGE_SIZE,
      200,
      q ? { search: q } : null,
    );
    if (gen !== usersListFetchGeneration) {
      return;
    }
    usersAllCache = rows;
    usersCurrentPage = 1;
    renderUsersList();
    if (refreshArchive) {
      loadDeletedUsersArchive();
    }
  } catch (error) {
    if (gen !== usersListFetchGeneration) {
      return;
    }
    if (container) {
      container.innerHTML = `<div class="error">Chyba při načítání: ${escapeHtml(error.message || String(error))}</div>`;
    }
  }
}

async function loadUsers() {
  const container = document.getElementById('users-cards-container');
  if (!container) return;

  container.innerHTML = '<div class="loading">Načítám uživatele...</div>';
  const paginationEl = document.getElementById('users-pagination');
  if (paginationEl) {
    paginationEl.classList.add('hidden');
    paginationEl.innerHTML = '';
  }

  try {
    const searchInput = document.getElementById('user-search');
    if (searchInput && searchInput.dataset.bound !== '1') {
      searchInput.addEventListener('input', () => {
        usersCurrentPage = 1;
        scheduleUsersSearchRefetch();
      });
      searchInput.addEventListener('keydown', (evt) => {
        if (evt.key === 'Enter') {
          evt.preventDefault();
          clearTimeout(usersSearchDebounceTimer);
          void refetchUsersListForSearch(false);
        }
      });
      searchInput.dataset.bound = '1';
    }

    await refetchUsersListForSearch(true);
  } catch (error) {
    container.innerHTML = `<div class="error">Chyba při načítání: ${error.message}</div>`;
  }
}

async function loadDeletedUsersArchive() {
  const body = document.getElementById('deleted-users-archive-body');
  if (!body) return;
  body.innerHTML = '<div class="loading">Načítám archiv…</div>';
  try {
    const rows = await apiRequest('GET', '/admin-api/user-deletion-archive');
    if (!Array.isArray(rows) || rows.length === 0) {
      body.innerHTML = '<p class="muted">Zatím žádný záznam v archivu (čísla # / ## vznikají až po smazání účtu).</p>';
      return;
    }
    const esc = escapeHtml;
    body.innerHTML = `
      <p class="muted archive-purge-hint" style="margin-bottom:0.75rem">
        <strong>Trvalé smazání z databáze</strong> odstraní řádek z <code>customers</code> (uvolní IČO u smazaných servisů).
        Vyžaduje opsání přesné fráze <code>${esc(ARCHIVED_USERS_PURGE_CONFIRM_PHRASE)}</code>.
      </p>
      <div class="section-toolbar" style="margin-bottom:0.75rem; flex-wrap:wrap; gap:8px;">
        <label class="archive-purge-confirm-wrap" style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
          <span class="muted">Potvrzení</span>
          <input
            type="text"
            id="archive-purge-confirm-input"
            class="archive-purge-confirm-input"
            placeholder="${esc(ARCHIVED_USERS_PURGE_CONFIRM_PHRASE)}"
            autocomplete="off"
            spellcheck="false"
            style="min-width:210px;padding:9px 11px;border:1px solid #cbd5e1;border-radius:8px;"
          />
        </label>
        <button type="button" class="btn-secondary" onclick="purgeDeletedArchiveSelected()">Odstranit vybrané z DB…</button>
        <button type="button" class="btn-secondary" onclick="purgeDeletedArchiveAll()">Odstranit všechny soft-smazané z DB…</button>
      </div>
      <table class="data-table deleted-archive-table">
        <thead><tr>
          <th style="width:2rem"><input type="checkbox" title="Vybrat vše" aria-label="Vybrat vše archivu" id="archive-purge-select-all" onchange="toggleArchivePurgeSelectAll(this)" /></th>
          <th>Označení</th><th>Původní e-mail</th><th>Smazáno</th><th>Aktuální e-mail v DB</th><th></th>
        </tr></thead>
        <tbody>
          ${rows.map((row) => `
            <tr>
              <td><input type="checkbox" class="archive-purge-cb" value="${Number(row.customer_id)}" aria-label="Vybrat ${esc(row.deletion_mark || '')}" /></td>
              <td><strong>${esc(row.deletion_mark || '')}</strong></td>
              <td>${esc(row.email_before || '')}</td>
              <td>${esc(formatDateTime(row.deleted_at))}</td>
              <td><code>${esc(row.current_email || '')}</code></td>
              <td><button type="button" class="btn-secondary btn-small" onclick="openUserDetail(${Number(row.customer_id)}, 'vehicles')">Detail</button></td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  } catch (error) {
    body.innerHTML = `<p class="error">Archiv nelze načíst: ${escapeHtml(error.message || String(error))}</p>`;
  }
}

function toggleArchivePurgeSelectAll(master) {
  const on = Boolean(master && master.checked);
  document.querySelectorAll('.archive-purge-cb').forEach((cb) => {
    cb.checked = on;
  });
}

function getArchivePurgeSelectedIds() {
  return Array.from(document.querySelectorAll('.archive-purge-cb:checked'))
    .map((el) => Number(el.value))
    .filter((n) => Number.isFinite(n) && n > 0);
}

function getArchivePurgeConfirmPhrase() {
  return document.getElementById('archive-purge-confirm-input')?.value || '';
}

function resetArchivePurgeConfirmPhrase() {
  const input = document.getElementById('archive-purge-confirm-input');
  if (input) input.value = '';
}

function validateArchivePurgeConfirmPhrase() {
  const phrase = getArchivePurgeConfirmPhrase();
  if (normalizeArchivedUsersPurgeConfirmPhrase(phrase) !== ARCHIVED_USERS_PURGE_CONFIRM_PHRASE) {
    showGlobalError(`Do pole Potvrzení napište ${ARCHIVED_USERS_PURGE_CONFIRM_PHRASE}.`);
    document.getElementById('archive-purge-confirm-input')?.focus();
    return null;
  }
  return normalizeArchivedUsersPurgeConfirmPhrase(phrase);
}

async function purgeDeletedArchiveSelected() {
  const ids = getArchivePurgeSelectedIds();
  if (!ids.length) {
    showGlobalError('Vyberte v archivu alespoň jeden účet (zaškrtnutí).');
    return;
  }
  const phrase = validateArchivePurgeConfirmPhrase();
  if (!phrase) return;
  try {
    const res = await apiRequest('POST', '/admin-api/user-archive-purge', {
      customer_ids: ids,
      purge_all: false,
      confirm_phrase: phrase,
    });
    showSuccess(res?.message || `Trvale odstraněno: ${res?.purged ?? ids.length}.`);
    await loadDeletedUsersArchive();
    resetArchivePurgeConfirmPhrase();
    if (typeof refetchUsersListForSearch === 'function') {
      await refetchUsersListForSearch(false);
    }
  } catch (error) {
    console.error(error);
  }
}

async function purgeDeletedArchiveAll() {
  const phrase = validateArchivePurgeConfirmPhrase();
  if (!phrase) return;
  try {
    const res = await apiRequest('POST', '/admin-api/user-archive-purge', {
      customer_ids: [],
      purge_all: true,
      confirm_phrase: phrase,
    });
    showSuccess(res?.message || `Trvale odstraněno: ${res?.purged ?? 0}.`);
    await loadDeletedUsersArchive();
    resetArchivePurgeConfirmPhrase();
    if (typeof refetchUsersListForSearch === 'function') {
      await refetchUsersListForSearch(false);
    }
  } catch (error) {
    console.error(error);
  }
}

function renderUsersList() {
  const container = document.getElementById('users-cards-container');
  const paginationEl = document.getElementById('users-pagination');
  if (!container) return;

  usersFilteredCache = [...usersAllCache];

  if (usersFilteredCache.length === 0) {
    container.innerHTML = '<div class="empty">Žádní uživatelé</div>';
    if (paginationEl) {
      paginationEl.classList.add('hidden');
      paginationEl.innerHTML = '';
    }
    return;
  }

  const totalPages = Math.max(1, Math.ceil(usersFilteredCache.length / USERS_RENDER_PAGE_SIZE));
  usersCurrentPage = Math.min(Math.max(usersCurrentPage, 1), totalPages);

  const start = (usersCurrentPage - 1) * USERS_RENDER_PAGE_SIZE;
  const end = start + USERS_RENDER_PAGE_SIZE;
  const pageItems = usersFilteredCache.slice(start, end);

  const roleLabelMap = {
    user: 'Uživatel',
    service: 'Servis',
    admin: 'Admin',
    developer_admin: 'Developer',
  };
  const usersViewMode = adminViewState.users || getStoredViewMode('users');

  container.innerHTML = pageItems.map(user => {
    const pendingN = Number(user.pending_admin_notify_count || 0);
    const notifyBadge = pendingN > 0 ? `<span class="notify-badge">${pendingN}</span>` : '';
    const createdDate = formatDate(user.created_at, '-');
    const lastSeen = formatDateTime(user.last_seen_at);
    const lastPaidAt = formatDateTime(user.last_paid_at);
    const hasPaid = Boolean(user.has_paid);
    const paymentSummary = hasPaid
      ? `ANO${lastPaidAt !== '-' ? ` • ${lastPaidAt}` : ''}`
      : 'NE';
    const isOnline = getOnlineState(user);
    const presenceClass = isOnline ? 'presence-online' : 'presence-offline';
    const presenceLabel = isOnline ? 'Online' : 'Offline';
    const roleRaw = String(user.role || 'user').toLowerCase();
    const role = ['user', 'service', 'admin', 'developer_admin'].includes(roleRaw) ? roleRaw : 'user';
    const roleLabel = roleLabelMap[role] || 'Uživatel';
    const displayName = escapeHtml(user.name || user.email || 'Bez jména');
    const email = escapeHtml(user.email || '-');
    const city = escapeHtml(user.city || '-');
    const phone = escapeHtml(user.phone || '-');
    const ipAddress = escapeHtml(user.last_ip_address || '-');
    const location = escapeHtml(user.last_location || '-');
    const licensePlan = escapeHtml(formatAdminLicensePlanLabel(user.license_plan || 'free', user.role));
    const licenseStatus = escapeHtml(user.license_status || 'active');
    const vehiclesCount = Number(user.vehicles_count || 0).toLocaleString('cs-CZ');
    const tenantId = user.tenant_id ?? '-';
    const tenantIdValue = escapeHtml(String(tenantId));
    const diskTitle =
      'Odhad obsazení disku ve složce data/ pro tenant tohoto účtu (fotky, přílohy, ORV, reporty). Stejná hodnota u účtů se stejným tenant_id.';
    const diskHuman = escapeHtml(formatUserDiskHuman(user) ?? '—');
    const contactValue = [phone !== '-' ? phone : null, city !== '-' ? city : null].filter(Boolean).join(' • ') || '-';
    const networkValue = [ipAddress !== '-' ? ipAddress : null, location !== '-' ? location : null].filter(Boolean).join(' • ') || '-';
    const encodedEmail = encodeURIComponent(String(user.email || ''));

    if (usersViewMode === 'compact') {
      return `
        <div class="card user-card-clickable" data-user-id="${user.id}" onclick="handleUserCardClick(event, ${user.id})" title="Otevřít detail uživatele">
          <div class="card-header">
            <h3 class="card-title">${user.name || user.email || 'Bez jména'}</h3>
            <span class="card-id">${userAdminBadgeLabel(user)}</span>
          </div>
          <div class="card-body">
            <div class="card-field">
              <span class="card-label">Email</span>
              <span class="card-value">${user.email || '-'}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Jméno</span>
              <span class="card-value">${user.name || '-'}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Role</span>
              <span class="card-value"><span class="role-badge role-${user.role || 'user'}">${user.role || 'user'}</span></span>
            </div>
            <div class="card-field">
              <span class="card-label">Licence</span>
              <span class="card-value">${licensePlan} (${licenseStatus})</span>
            </div>
            <div class="card-field">
              <span class="card-label">Platby</span>
              <span class="card-value">${escapeHtml(paymentSummary)}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Stav</span>
              <span class="card-value"><span class="presence-pill ${presenceClass}">${presenceLabel}</span></span>
            </div>
            <div class="card-field">
              <span class="card-label">Tenant</span>
              <span class="card-value">${user.tenant_id ?? '-'}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Úložiště (data)</span>
              <span class="card-value" title="${diskTitle}">${diskHuman}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Vozidla</span>
              <span class="card-value">${user.vehicles_count || 0}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Registrován</span>
              <span class="card-value">${createdDate}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Poslední IP</span>
              <span class="card-value">${escapeHtml(user.last_ip_address || '-')}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Lokalita</span>
              <span class="card-value">${escapeHtml(user.last_location || '-')}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Naposledy aktivní</span>
              <span class="card-value">${lastSeen}</span>
            </div>
          </div>
          <div class="card-actions">
            <button type="button" class="btn-secondary btn-small user-card-notify-btn" title="E-mail uživateli (historie změn z adminu)" onclick="openAdminUserNotifyModal(event, ${user.id})">✉️${notifyBadge}</button>
            <button class="btn-edit" onclick="editUser(event, ${user.id})">✏️ Upravit</button>
            <button class="btn-danger" onclick="deleteUser(event, ${user.id}, decodeURIComponent('${encodedEmail}'))">🗑️ Smazat</button>
          </div>
        </div>
      `;
    }

    return `
      <div class="card user-card user-card-clickable" data-user-id="${user.id}" onclick="handleUserCardClick(event, ${user.id})" title="Otevřít detail uživatele">
        <div class="card-header user-card-header">
          <div class="user-card-head-main">
            <h3 class="card-title">${displayName}</h3>
            <div class="user-card-email">${email}</div>
          </div>
          <div class="user-card-head-meta">
            <span class="role-badge role-${role}">${roleLabel}</span>
            <span class="presence-pill ${presenceClass}">${presenceLabel}</span>
            <span class="card-id">${userAdminBadgeLabel(user)}</span>
          </div>
        </div>
        <div class="card-body user-card-body">
          <div class="user-card-kpis">
            <span class="user-chip">Vozidla <strong>${vehiclesCount}</strong></span>
            <span class="user-chip">Tenant <strong>${tenantIdValue}</strong></span>
            <span class="user-chip" title="${diskTitle}">Data <strong>${diskHuman}</strong></span>
            <span class="user-chip">${licensePlan} • ${licenseStatus}</span>
            <span class="user-chip">Platby <strong>${hasPaid ? 'ANO' : 'NE'}</strong></span>
          </div>
          <div class="user-card-details">
            <div class="card-field">
              <span class="card-label">Kontakt</span>
              <span class="card-value">${contactValue}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Registrován</span>
              <span class="card-value">${createdDate}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Naposledy aktivní</span>
              <span class="card-value">${lastSeen}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Poslední platba</span>
              <span class="card-value">${lastPaidAt}</span>
            </div>
            <div class="card-field user-card-field-wide">
              <span class="card-label">IP a lokalita</span>
              <span class="card-value user-card-tech">${networkValue}</span>
            </div>
          </div>
          <div class="card-field user-card-mobile-summary">
            <span class="card-label">Naposledy aktivní</span>
            <span class="card-value">${lastSeen}</span>
          </div>
        </div>
        <div class="card-actions user-card-actions">
          <button type="button" class="btn-secondary user-card-notify-btn" title="E-mail uživateli (historie změn z adminu)" onclick="openAdminUserNotifyModal(event, ${user.id})">✉️${notifyBadge}</button>
          <button class="btn-edit" onclick="editUser(event, ${user.id})">Upravit</button>
          <button class="btn-danger" onclick="deleteUser(event, ${user.id}, decodeURIComponent('${encodedEmail}'))">Smazat</button>
        </div>
      </div>
    `;
  }).join('');

  applySectionViewMode('users');

  if (!paginationEl) {
    return;
  }

  const from = start + 1;
  const to = start + pageItems.length;
  paginationEl.classList.remove('hidden');
  paginationEl.innerHTML = `
    <div class="list-meta">Zobrazeno ${from}-${to} z ${usersFilteredCache.length} uživatelů</div>
    <div class="pagination-controls">
      <button class="pagination-btn" onclick="changeUsersPage(-1)" ${usersCurrentPage <= 1 ? 'disabled' : ''}>Předchozí</button>
      <span class="list-meta">Strana ${usersCurrentPage}/${totalPages}</span>
      <button class="pagination-btn" onclick="changeUsersPage(1)" ${usersCurrentPage >= totalPages ? 'disabled' : ''}>Další</button>
    </div>
  `;
}

function changeUsersPage(delta) {
  usersCurrentPage += delta;
  renderUsersList();
}

function handleUserCardClick(event, userId) {
  // Ochrana proti nechtěnému otevření detailu při kliku na akční tlačítka uvnitř karty.
  const target = event?.target;
  if (target && typeof target.closest === 'function') {
    if (target.closest('.card-actions, .user-card-actions, .user-card-notify-btn, button, a, input, select, textarea, label')) {
      return;
    }
  }
  openUserDetail(userId);
}

function closeAdminUserNotifyModal() {
  const modal = document.getElementById('admin-user-notify-modal');
  if (!modal) return;
  modal.classList.add('hidden');
  modal.dataset.userId = '';
  const err = document.getElementById('admin-notify-error');
  if (err) {
    err.classList.add('hidden');
    err.textContent = '';
  }
}

async function openAdminUserNotifyModal(event, userId) {
  if (event && typeof event.stopPropagation === 'function') {
    event.stopPropagation();
  }
  const modal = document.getElementById('admin-user-notify-modal');
  if (!modal || !userId) return;
  modal.dataset.userId = String(userId);
  modal.classList.remove('hidden');
  await refreshAdminUserNotifyModal();
}

function adminNotifySelectAllPending() {
  const modal = document.getElementById('admin-user-notify-modal');
  if (!modal) return;
  modal.querySelectorAll('.admin-notify-row input[type="checkbox"][data-change-id]').forEach((box) => {
    if (!box.disabled) {
      box.checked = true;
    }
  });
}

async function refreshAdminUserNotifyModal() {
  const modal = document.getElementById('admin-user-notify-modal');
  const listEl = document.getElementById('admin-notify-list');
  const loadingEl = document.getElementById('admin-notify-loading');
  const titleEl = document.getElementById('admin-notify-modal-title');
  const errEl = document.getElementById('admin-notify-error');
  if (!modal || !listEl) return;
  const userId = modal.dataset.userId;
  if (!userId) return;
  if (loadingEl) loadingEl.classList.remove('hidden');
  if (errEl) {
    errEl.classList.add('hidden');
    errEl.textContent = '';
  }
  listEl.innerHTML = '';
  try {
    const data = await apiRequest('GET', `/admin-api/users/${userId}/admin-notify-history`);
    const items = Array.isArray(data.items) ? data.items : [];
    const email = escapeHtml(data.user_email || '');
    if (titleEl) {
      titleEl.textContent = email ? `E-mail uživateli (${email})` : 'E-mail uživateli';
    }
    if (items.length === 0) {
      listEl.innerHTML = '<div class="empty">Zatím žádné zaznamenané změny z adminu pro tento účet.</div>';
    } else {
      listEl.innerHTML = items
        .map((item) => {
          const sent = Boolean(item.notified_at);
          const esc = escapeHtml;
          const sum = esc(item.summary_line || '');
          const meta = [
            item.created_at ? formatDateTime(item.created_at) : '',
            item.admin_email ? `admin: ${esc(item.admin_email)}` : '',
            sent ? `odesláno: ${esc(formatDateTime(item.notified_at))}` : 'čeká na odeslání',
          ]
            .filter(Boolean)
            .join(' · ');
          const det = item.detail_text ? `<div class="admin-notify-detail muted">${esc(item.detail_text)}</div>` : '';
          const disabled = sent ? 'disabled' : '';
          const checked = !sent ? 'checked' : '';
          return `
            <label class="admin-notify-row ${sent ? 'is-sent' : ''}">
              <input type="checkbox" data-change-id="${item.id}" ${disabled} ${checked} />
              <div>
                <div><strong>${sum}</strong></div>
                <div class="admin-notify-meta">${meta}</div>
                ${det}
              </div>
            </label>
          `;
        })
        .join('');
    }
  } catch (e) {
    if (errEl) {
      errEl.textContent = e.message || String(e);
      errEl.classList.remove('hidden');
    }
  } finally {
    if (loadingEl) loadingEl.classList.add('hidden');
  }
}

async function submitAdminUserNotifySend() {
  const modal = document.getElementById('admin-user-notify-modal');
  const errEl = document.getElementById('admin-notify-error');
  if (!modal) return;
  const userId = modal.dataset.userId;
  if (!userId) return;
  const boxes = modal.querySelectorAll('.admin-notify-row input[type="checkbox"][data-change-id]:checked:not(:disabled)');
  const ids = [...boxes].map((b) => parseInt(b.getAttribute('data-change-id'), 10)).filter((n) => Number.isFinite(n));
  if (!ids.length) {
    if (errEl) {
      errEl.textContent = 'Vyberte alespoň jednu změnu k odeslání.';
      errEl.classList.remove('hidden');
    }
    return;
  }
  if (errEl) {
    errEl.classList.add('hidden');
    errEl.textContent = '';
  }
  try {
    const res = await apiRequest('POST', `/admin-api/users/${userId}/admin-notify-send`, { change_ids: ids });
    showSuccess(res?.message || 'E-mail byl odeslán');
    closeAdminUserNotifyModal();
    await loadUsers();
    if (getCurrentUserDetailId() === parseInt(userId, 10)) {
      await refreshUserDetail(userDetailActivePanel);
    }
  } catch (e) {
    if (errEl) {
      errEl.textContent = e.message || String(e);
      errEl.classList.remove('hidden');
    }
  }
}

function getCurrentUserDetailId() {
  if (userDetailData?.user?.id) return userDetailData.user.id;
  const modal = document.getElementById('user-detail-modal');
  if (!modal) return null;
  const rawId = modal.dataset.userId;
  const parsedId = Number.parseInt(rawId || '', 10);
  return Number.isFinite(parsedId) ? parsedId : null;
}

function setUserDetailLoadingState(isLoading) {
  const loadingEl = document.getElementById('user-detail-loading');
  const contentEl = document.getElementById('user-detail-content');
  const errorEl = document.getElementById('user-detail-error');
  if (loadingEl) {
    loadingEl.classList.toggle('hidden', !isLoading);
  }
  if (contentEl && isLoading) {
    contentEl.classList.add('hidden');
  }
  if (errorEl && isLoading) {
    errorEl.classList.add('hidden');
    errorEl.textContent = '';
  }
}

async function openUserDetail(userId, panel = 'vehicles') {
  const modal = document.getElementById('user-detail-modal');
  if (!modal) return;
  modal.dataset.userId = String(userId);
  userDetailActivePanel = panel;
  modal.classList.remove('hidden');
  await refreshUserDetail(panel);
}

function closeUserDetailModal() {
  const modal = document.getElementById('user-detail-modal');
  if (!modal) return;
  modal.classList.add('hidden');
  modal.dataset.userId = '';
  userDetailData = null;
}

function setUserDetailReturnContext(userId, panel) {
  userDetailReturnContext = { userId, panel };
}

async function reopenUserDetailIfNeeded() {
  if (!userDetailReturnContext) return;
  const context = userDetailReturnContext;
  userDetailReturnContext = null;
  await openUserDetail(context.userId, context.panel || 'vehicles');
}

/** Skryje akce jen pro aktivní účty a zobrazí „Obnovit účet“ u soft-smazaného zákazníka. */
function syncUserDetailModalFooter(user) {
  const modal = document.getElementById('user-detail-modal');
  if (!modal) return;
  const isDeleted = !!(user && user.is_deleted);
  modal.querySelectorAll('[data-user-detail-active-only]').forEach((btn) => {
    btn.classList.toggle('hidden', isDeleted);
  });
  const restoreBtn = document.getElementById('user-detail-btn-restore-account');
  if (restoreBtn) {
    restoreBtn.classList.toggle('hidden', !isDeleted);
  }
}

async function refreshUserDetail(panelOverride = null) {
  const userId = getCurrentUserDetailId();
  const modal = document.getElementById('user-detail-modal');
  if (!userId || !modal) return;

  if (panelOverride) {
    userDetailActivePanel = panelOverride;
  }

  setUserDetailLoadingState(true);

  try {
    const detail = await apiRequest('GET', `/admin-api/users/${userId}/detail`);
    userDetailData = detail;
    renderUserDetailModal();
  } catch (error) {
    const errorEl = document.getElementById('user-detail-error');
    if (errorEl) {
      errorEl.textContent = `Chyba při načítání detailu uživatele: ${error.message}`;
      errorEl.classList.remove('hidden');
    }
  } finally {
    setUserDetailLoadingState(false);
  }
}

function setUserDetailPanel(panelKey) {
  userDetailActivePanel = panelKey;
  renderUserDetailModal();
}

function renderUserDetailModal() {
  const contentEl = document.getElementById('user-detail-content');
  const profileEl = document.getElementById('user-detail-profile');
  const panelsEl = document.getElementById('user-detail-panels');
  const listTitleEl = document.getElementById('user-detail-list-title');
  const listEl = document.getElementById('user-detail-list');
  const titleEl = document.getElementById('user-detail-title');
  const errorEl = document.getElementById('user-detail-error');
  if (!contentEl || !profileEl || !panelsEl || !listEl || !listTitleEl || !titleEl) return;

  const detail = userDetailData || {};
  const user = detail.user || {};
  const stats = detail.stats || {};
  const meta = detail.meta || {};
  const panels = detail.panels || {};
  const insight = detail.insight || {};
  const insightLicense = insight.license || {};
  const insightPaymentsSummary = insight.payments_summary || {};
  const insightPresence = insight.presence || {};
  const insightPayments = Array.isArray(insight.payments) ? insight.payments : [];

  titleEl.textContent = `Detail uživatele: ${user.name || user.email || userAdminBadgeLabel(user)}`;
  const notifyWrap = document.getElementById('user-detail-notify-wrap');
  if (notifyWrap && user.id) {
    const pending = Number(detail.admin_notify_pending_count || 0);
    notifyWrap.innerHTML = `
      <button type="button" class="btn-secondary btn-small user-detail-notify-btn" title="Historie změn z adminu a e-mail uživateli" onclick="openAdminUserNotifyModal(event, ${user.id})">
        ✉️ Informovat${pending > 0 ? `<span class="notify-badge">${pending}</span>` : ''}
      </button>
    `;
  }
  if (errorEl) {
    errorEl.classList.add('hidden');
    errorEl.textContent = '';
  }

  const roleClass = `role-${user.role || 'user'}`;
  const addressLine = [user.address_line, user.city_line].filter(Boolean).join(', ') || '-';
  const ipHistory = Array.isArray(meta.ip_history) ? meta.ip_history : [];
  const latestIpEntry = ipHistory.length > 0 ? ipHistory[0] : null;
  const latestIp = latestIpEntry?.ip_address || meta.last_ip_address || '-';
  const latestLocation = latestIpEntry?.location_label || meta.last_location || '-';
  const latestGeoSource = latestIpEntry?.geo_source || latestIpEntry?.source || '-';
  const latestGeoAccuracy = latestIpEntry?.geo_accuracy_m;
  const latestLatitude = latestIpEntry?.latitude;
  const latestLongitude = latestIpEntry?.longitude;
  const latestCoordinates = (
    latestLatitude !== null && latestLatitude !== undefined &&
    latestLongitude !== null && latestLongitude !== undefined
  ) ? `${Number(latestLatitude).toFixed(5)}, ${Number(latestLongitude).toFixed(5)}` : '-';
  const latestMapsUrl = latestIpEntry?.maps_url || null;
  const olderIpEntries = ipHistory.slice(1);
  const latestSeen = formatDateTime(meta.last_activity_at);
  const detailOnline = getOnlineState({ last_seen_at: insightPresence.last_seen_at || meta.last_activity_at });
  const detailOnlineClass = detailOnline ? 'presence-online' : 'presence-offline';
  const detailOnlineLabel = detailOnline ? 'Online' : 'Offline';
  const paymentPreview = insightPayments
    .slice(0, 3)
    .map((payment) => {
      const amount = Number(payment.amount_halers || 0).toLocaleString('cs-CZ');
      const stamp = formatDateTime(payment.payment_timestamp);
      const status = escapeHtml(payment.provider_status || payment.event_type || '-');
      const environment = escapeHtml(normalizePaymentEnvironment(payment));
      return `${environment} • ${amount} ${escapeHtml(payment.currency || 'CZK')} • ${status} • ${stamp}`;
    })
    .join('<br/>');

  const diskUsageTitle =
    user.disk_usage_note ||
    'Odhad obsazení disku ve složce data/ pro tenant tohoto účtu (fotky, přílohy, ORV, reporty). Stejná hodnota u účtů se stejným tenant_id.';

  profileEl.innerHTML = `
    <div class="user-detail-info-grid">
      <div class="user-detail-info-card">
        <h4>Základní údaje</h4>
        <div class="user-detail-row"><span>Číslo v přehledu</span><strong>${user.admin_ordinal != null && user.admin_ordinal !== '' ? '#' + user.admin_ordinal : '—'}</strong></div>
        <div class="user-detail-row"><span>Archiv po smazání</span><strong>${user.deletion_archive_mark ? escapeHtml(user.deletion_archive_mark) : '—'}</strong></div>
        ${user.is_deleted && user.deletion_email_before ? `<div class="user-detail-row"><span>E-mail po obnově (z archivu)</span><strong>${escapeHtml(user.deletion_email_before)}</strong></div>` : ''}
        <div class="user-detail-row"><span>Interní ID (DB)</span><strong>${user.id ?? '-'}</strong></div>
        <div class="user-detail-row"><span>Email</span><strong>${escapeHtml(user.email || '-')}</strong></div>
        <div class="user-detail-row"><span>Jméno / Název</span><strong>${escapeHtml(user.name || '-')}</strong></div>
        <div class="user-detail-row"><span>Role</span><strong><span class="role-badge ${roleClass}">${escapeHtml(user.role || 'user')}</span></strong></div>
        <div class="user-detail-row"><span>Tenant</span><strong>${user.tenant_id ?? '-'}</strong></div>
        <div class="user-detail-row"><span>Úložiště (data)</span><strong title="${escapeHtml(diskUsageTitle)}">${escapeHtml(formatUserDiskHuman(user) ?? '—')}</strong></div>
        <div class="user-detail-row"><span>Licence</span><strong>${escapeHtml(formatAdminLicensePlanLabel(user.license_plan || 'free', user.role))} (${escapeHtml(user.license_status || 'active')})</strong></div>
        <div class="user-detail-row"><span>Stav účtu</span><strong>${user.is_deleted ? 'Smazaný' : (user.is_disabled ? 'Pozastavený' : 'Aktivní')}</strong></div>
        <div class="user-detail-row"><span>Session verze</span><strong>${user.session_version ?? 0}</strong></div>
        <div class="user-detail-row"><span>Registrován</span><strong>${formatDateTime(user.created_at)}</strong></div>
        <div class="user-detail-row"><span>E-mail</span><strong>${user.email_verification_label === 'verified' ? 'Ověřen' : 'Neověřen'}</strong></div>
        <div class="user-detail-row"><span>Telefon</span><strong>${escapeHtml(phoneStatusAdminLabel(user))}</strong></div>
        <div class="user-detail-row"><span>Účet (stav)</span><strong>${escapeHtml(user.account_status || 'active')}</strong></div>
        <div class="user-detail-row"><span>Rizikové příznaky</span><strong>${escapeHtml(formatRiskFlags(user.registration_risk_flags))}</strong></div>
        <div class="user-detail-row"><span>Registr. IP</span><strong>${escapeHtml(user.registration_ip || '—')}</strong></div>
        <div class="user-detail-row"><span>Registr. user-agent</span><strong title="${escapeHtml(user.registration_user_agent || '')}">${escapeHtml(truncUa(user.registration_user_agent))}</strong></div>
      </div>
      <div class="user-detail-info-card">
        <h4>Kontakt a firma</h4>
        <div class="user-detail-row"><span>Telefon</span><strong>${escapeHtml(user.phone || '-')}</strong></div>
        <div class="user-detail-row"><span>IČO</span><strong>${escapeHtml(user.ico || '-')}</strong></div>
        <div class="user-detail-row"><span>DIČ</span><strong>${escapeHtml(user.dic || '-')}</strong></div>
        <div class="user-detail-row"><span>Adresa</span><strong>${escapeHtml(addressLine)}</strong></div>
      </div>
      <div class="user-detail-info-card">
        <h4>Aktivita a IP</h4>
        <div class="user-detail-row"><span>Stav</span><strong><span class="presence-pill ${detailOnlineClass}">${detailOnlineLabel}</span></strong></div>
        <div class="user-detail-row"><span>Poslední IP</span><strong>${escapeHtml(latestIp)}</strong></div>
        <div class="user-detail-row"><span>Lokalita</span><strong>${escapeHtml(latestLocation)}</strong></div>
        <div class="user-detail-row"><span>Zdroj polohy</span><strong>${escapeHtml(latestGeoSource)}</strong></div>
        <div class="user-detail-row"><span>GPS</span><strong>${escapeHtml(latestCoordinates)}</strong></div>
        <div class="user-detail-row"><span>Přesnost</span><strong>${latestGeoAccuracy ? `±${escapeHtml(Math.round(Number(latestGeoAccuracy)).toString())} m` : '-'}</strong></div>
        <div class="user-detail-row"><span>Last login</span><strong>${escapeHtml(formatDateTime(insightPresence.last_login_at || user.last_login_at))}</strong></div>
        <div class="user-detail-row"><span>Last seen</span><strong>${escapeHtml(formatDateTime(insightPresence.last_seen_at || user.last_seen_at))}</strong></div>
        <div class="user-detail-row"><span>Aktivní relace</span><strong>${escapeHtml(String(insightPresence.active_session_count ?? 0))}</strong></div>
        <div class="user-detail-row"><span>Poslední aktivita</span><strong>${escapeHtml(latestSeen)}</strong></div>
        ${latestMapsUrl ? `<div class="user-detail-ip-map-link"><a href="${escapeHtml(latestMapsUrl)}" target="_blank" rel="noopener noreferrer">Otevřít poslední polohu na mapě</a></div>` : ''}
        <div class="user-detail-ip-list user-detail-ip-last">
          ${(latestIpEntry
            ? `
                <div class="user-detail-ip-item">
                  <strong>${escapeHtml(latestIpEntry.ip_address || '-')}</strong>
                  <span>${escapeHtml(latestIpEntry.location_label || '-')}</span>
                  <span>${escapeHtml(formatDateTime(latestIpEntry.timestamp))}</span>
                </div>
              `
            : '<div class="empty">Žádná uložená IP historie</div>')}
        </div>
        ${olderIpEntries.length > 0
          ? `
            <details class="user-detail-ip-history-details">
              <summary>Historie připojení (${olderIpEntries.length})</summary>
              <div class="user-detail-ip-list user-detail-ip-list-scroll">
                ${olderIpEntries.map((ip) => {
                  const hasCoords = ip.latitude !== null && ip.latitude !== undefined && ip.longitude !== null && ip.longitude !== undefined;
                  const coords = hasCoords ? `${Number(ip.latitude).toFixed(5)}, ${Number(ip.longitude).toFixed(5)}` : null;
                  const sourceLabel = ip.geo_source || ip.source || '-';
                  const accuracyLabel = ip.geo_accuracy_m ? ` ±${Math.round(Number(ip.geo_accuracy_m))} m` : '';
                  const mapLink = ip.maps_url
                    ? `<a href="${escapeHtml(ip.maps_url)}" target="_blank" rel="noopener noreferrer">mapa</a>`
                    : '';
                  return `
                    <div class="user-detail-ip-item">
                      <strong>${escapeHtml(ip.ip_address || '-')}</strong>
                      <span>${escapeHtml(ip.location_label || '-')}</span>
                      <span>${escapeHtml(formatDateTime(ip.timestamp))}</span>
                      <span>Zdroj: ${escapeHtml(sourceLabel)}${escapeHtml(accuracyLabel)}</span>
                      ${coords ? `<span>GPS: ${escapeHtml(coords)} ${mapLink}</span>` : ''}
                    </div>
                  `;
                }).join('')}
              </div>
            </details>
          `
          : ''}
      </div>
      <div class="user-detail-info-card">
        <h4>Licence a platby</h4>
        <div class="user-detail-row"><span>Plan</span><strong>${escapeHtml(formatAdminLicensePlanLabel(insightLicense.current_plan || user.license_plan || 'free', user.role))}</strong></div>
        <div class="user-detail-row"><span>Status</span><strong>${escapeHtml(insightLicense.status || user.license_status || 'active')}</strong></div>
        <div class="user-detail-row"><span>Zdroj aktivace</span><strong>${escapeHtml(insightLicense.source_of_activation || '-')}</strong></div>
        <div class="user-detail-row"><span>Nákup</span><strong>${escapeHtml(formatDateTime(insightLicense.purchase_date))}</strong></div>
        <div class="user-detail-row"><span>Aktivace</span><strong>${escapeHtml(formatDateTime(insightLicense.activation_date))}</strong></div>
        <div class="user-detail-row"><span>Expirace</span><strong>${escapeHtml(formatDateTime(insightLicense.expiration_date))}</strong></div>
        <div class="user-detail-row"><span>Další obnova</span><strong>${escapeHtml(formatDateTime(insightLicense.next_renewal_date))}</strong></div>
        <div class="user-detail-row"><span>LIVE paid</span><strong>${insightPaymentsSummary.has_live_paid || insightPaymentsSummary.has_paid ? 'Ano' : 'Ne'}</strong></div>
        <div class="user-detail-row"><span>LIVE/TEST tx</span><strong>${escapeHtml(String(insightPaymentsSummary.count_live ?? 0))} / ${escapeHtml(String(insightPaymentsSummary.count_test ?? 0))}</strong></div>
        <div class="user-detail-row"><span>LIVE/TEST paid</span><strong>${escapeHtml(String(insightPaymentsSummary.live_paid_count ?? 0))} / ${escapeHtml(String(insightPaymentsSummary.test_paid_count ?? 0))}</strong></div>
        <div class="user-detail-row"><span>Počet transakcí</span><strong>${escapeHtml(String(insightPaymentsSummary.count ?? insightPayments.length ?? 0))}</strong></div>
        <div class="user-detail-row"><span>Poslední platba</span><strong>${escapeHtml(formatDateTime(insightPaymentsSummary.last_paid_at))}</strong></div>
        <div class="user-detail-row"><span>Nedávné transakce</span><strong>${paymentPreview || '-'}</strong></div>
      </div>
      <div class="user-detail-info-card">
        <h4>Notifikace</h4>
        <div class="user-detail-row"><span>Email notifikace</span><strong>${user.notify_email ? 'Ano' : 'Ne'}</strong></div>
        <div class="user-detail-row"><span>SMS notifikace</span><strong>${user.notify_sms ? 'Ano' : 'Ne'}</strong></div>
        <div class="user-detail-row"><span>STK připomínky</span><strong>${user.notify_stk ? 'Ano' : 'Ne'}</strong></div>
        <div class="user-detail-row"><span>Olej připomínky</span><strong>${user.notify_oil ? 'Ano' : 'Ne'}</strong></div>
        <div class="user-detail-row"><span>Obecné připomínky</span><strong>${user.notify_general ? 'Ano' : 'Ne'}</strong></div>
      </div>
    </div>
  `;

  const panelDefs = [
    { key: 'vehicles', label: 'Vozidla', icon: '🚗', count: stats.vehicles_count ?? 0 },
    { key: 'reminders', label: 'Připomínky', icon: '⏰', count: stats.reminders_count ?? 0 },
    { key: 'reservations', label: 'Rezervace', icon: '📅', count: stats.reservations_count ?? 0 },
    { key: 'records', label: 'Záznamy', icon: '📋', count: stats.records_count ?? 0 },
    { key: 'timeline', label: 'Historie', icon: '🧾', count: '∞' },
  ];

  panelsEl.innerHTML = panelDefs.map((panel) => `
    <button
      class="user-detail-panel-card ${userDetailActivePanel === panel.key ? 'active' : ''}"
      onclick="setUserDetailPanel('${panel.key}')"
      type="button"
    >
      <span class="user-detail-panel-icon">${panel.icon}</span>
      <span class="user-detail-panel-label">${panel.label}</span>
      <span class="user-detail-panel-count">${panel.count}</span>
    </button>
  `).join('');

  syncUserDetailModalFooter(user);

  const titleMap = {
    vehicles: 'Vozidla uživatele',
    reminders: 'Připomínky uživatele',
    reservations: 'Rezervace uživatele',
    records: 'Servisní záznamy uživatele',
    timeline: 'Jednotná historie účtu',
  };
  listTitleEl.textContent = titleMap[userDetailActivePanel] || 'Detail položek';

  if (userDetailActivePanel === 'timeline') {
    listEl.innerHTML = '<div class="loading">Načítám jednotnou historii účtu...</div>';
    contentEl.classList.remove('hidden');
    loadUserDetailTimeline(user.id);
    return;
  }

  const selected = Array.isArray(panels[userDetailActivePanel]) ? panels[userDetailActivePanel] : [];
  if (selected.length === 0) {
    listEl.innerHTML = '<div class="empty">Žádné položky</div>';
    contentEl.classList.remove('hidden');
    return;
  }

  if (userDetailActivePanel === 'vehicles') {
    listEl.innerHTML = selected.map((vehicle) => {
      const label = vehicle.label || vehicle.nickname || `Vozidlo #${vehicle.id}`;
      const encodedLabel = encodeURIComponent(label || '');
      const metaText = [
        `SPZ: ${vehicle.plate || '-'}`,
        `Rok: ${vehicle.year || '-'}`,
        `Záznamů: ${vehicle.service_count || 0}`,
        `Vytvořeno: ${formatDate(vehicle.created_at)}`,
      ].join(' • ');
      return `
        <div class="user-detail-list-item">
          <div class="user-detail-list-text">
            <div class="user-detail-list-title">🚗 ${escapeHtml(label)}</div>
            <div class="user-detail-list-meta">${escapeHtml(metaText)}</div>
          </div>
          <div class="user-detail-list-actions">
            <button class="btn-edit btn-sm" onclick="stopEventSafely(event); editVehicleFromUserDetail(${vehicle.id})">Upravit</button>
            <button class="btn-danger btn-sm" onclick="stopEventSafely(event); deleteVehicleFromUserDetail(${vehicle.id}, '${encodedLabel}')">Smazat</button>
          </div>
        </div>
      `;
    }).join('');
  } else if (userDetailActivePanel === 'reminders') {
    listEl.innerHTML = selected.map((reminder) => {
      const encodedText = encodeURIComponent(reminder.text || '');
      const status = reminder.is_completed ? 'Dokončeno' : 'Aktivní';
      const statusClass = reminder.is_completed ? 'status-ok' : 'status-warn';
      const due = formatDate(reminder.due_date);
      return `
        <div class="user-detail-list-item">
          <div class="user-detail-list-text">
            <div class="user-detail-list-title">⏰ ${escapeHtml(reminder.text || '-')}</div>
            <div class="user-detail-list-meta">
              ${escapeHtml(`Typ: ${reminder.type || '-'} • Vozidlo: ${reminder.vehicle_label || '-'} • Termín: ${due}`)}
            </div>
          </div>
          <div class="user-detail-list-actions">
            <span class="status-pill ${statusClass}">${status}</span>
            <button class="btn-secondary btn-sm" onclick="stopEventSafely(event); toggleReminderCompletionFromUserDetail(${reminder.id}, ${!reminder.is_completed})">${reminder.is_completed ? 'Obnovit' : 'Dokončit'}</button>
            <button class="btn-edit btn-sm" onclick="stopEventSafely(event); quickEditReminderFromUserDetail(${reminder.id}, '${encodedText}')">Upravit</button>
            <button class="btn-danger btn-sm" onclick="stopEventSafely(event); deleteReminderFromUserDetail(${reminder.id})">Smazat</button>
          </div>
        </div>
      `;
    }).join('');
  } else if (userDetailActivePanel === 'reservations') {
    listEl.innerHTML = selected.map((reservation) => {
      const statusClass = reservation.status === 'CONFIRMED' ? 'status-ok' : (reservation.status === 'CANCELLED' ? 'status-bad' : 'status-warn');
      const status = reservation.status || '-';
      return `
        <div class="user-detail-list-item">
          <div class="user-detail-list-text">
            <div class="user-detail-list-title">📅 ${escapeHtml(reservation.service_type || 'Rezervace')}</div>
            <div class="user-detail-list-meta">
              ${escapeHtml(`Vozidlo: ${reservation.vehicle_label || '-'} • Servis: ${reservation.service_name || reservation.service_email || '-'} • Od: ${formatDateTime(reservation.start_datetime)}`)}
            </div>
            ${reservation.note ? `<div class="user-detail-list-note">${escapeHtml(reservation.note)}</div>` : ''}
          </div>
          <div class="user-detail-list-actions">
            <span class="status-pill ${statusClass}">${escapeHtml(status)}</span>
            <button class="btn-secondary btn-sm" onclick="stopEventSafely(event); updateReservationStatusFromUserDetail(${reservation.id}, 'CONFIRMED')">Potvrdit</button>
            <button class="btn-secondary btn-sm" onclick="stopEventSafely(event); updateReservationStatusFromUserDetail(${reservation.id}, 'CANCELLED')">Zrušit</button>
            <button class="btn-danger btn-sm" onclick="stopEventSafely(event); deleteReservationFromUserDetail(${reservation.id})">Smazat</button>
          </div>
        </div>
      `;
    }).join('');
  } else {
    listEl.innerHTML = selected.map((record) => {
      const metaText = [
        `Vozidlo: ${record.vehicle_label || '-'}`,
        `Datum: ${formatDateTime(record.performed_at)}`,
        `Nájezd: ${record.mileage ? `${Number(record.mileage).toLocaleString('cs-CZ')} km` : '-'}`,
        `Cena: ${formatMoney(record.price)}`,
      ].join(' • ');
      return `
        <div class="user-detail-list-item">
          <div class="user-detail-list-text">
            <div class="user-detail-list-title">📋 ${escapeHtml(record.description || '-')}</div>
            <div class="user-detail-list-meta">${escapeHtml(metaText)}</div>
            ${record.note ? `<div class="user-detail-list-note">${escapeHtml(record.note)}</div>` : ''}
          </div>
          <div class="user-detail-list-actions">
            <button class="btn-edit btn-sm" onclick="stopEventSafely(event); editRecordFromUserDetail(${record.id})">Upravit</button>
            <button class="btn-danger btn-sm" onclick="stopEventSafely(event); deleteRecordFromUserDetail(${record.id})">Smazat</button>
          </div>
        </div>
      `;
    }).join('');
  }

  contentEl.classList.remove('hidden');
}

async function loadUserDetailTimeline(userId) {
  const listEl = document.getElementById('user-detail-list');
  if (!listEl || !userId) return;
  try {
    const role = String(userDetailData?.user?.role || 'user').toLowerCase();
    const entityType = role === 'service' ? 'service' : 'user';
    const data = await apiRequest('GET', `/admin-api/entity-history/${entityType}/${userId}?limit=150`);
    const items = Array.isArray(data.items) ? data.items : [];
    if (!items.length) {
      listEl.innerHTML = '<div class="empty">Zatím žádná timeline historie pro tento účet.</div>';
      return;
    }
    listEl.innerHTML = items.map((item) => `
      <div class="user-detail-list-item timeline-item timeline-${escapeHtml(item.severity || 'info')}">
        <div class="user-detail-list-text">
          <div class="user-detail-list-title">${escapeHtml(item.title || '-')}</div>
          <div class="user-detail-list-meta">
            ${escapeHtml(item.source || '-')} · ${escapeHtml(item.actor || '-')} · ${escapeHtml(formatDateTime(item.created_at))}
            ${item.ip_address ? ` · IP ${escapeHtml(item.ip_address)}` : ''}
          </div>
          ${item.details ? `<div class="user-detail-list-note">${escapeHtml(String(item.details))}</div>` : ''}
        </div>
        <span class="status-pill">${escapeHtml(item.severity || 'info')}</span>
      </div>
    `).join('');
  } catch (error) {
    listEl.innerHTML = `<div class="error">Chyba při načítání historie: ${escapeHtml(error.message || String(error))}</div>`;
  }
}

async function editUserFromDetail() {
  if (!userDetailData?.user?.id) return;
  const userId = userDetailData.user.id;
  const panel = userDetailActivePanel;
  const opened = await showUserModal(userId);
  if (!opened) return;
  setUserDetailReturnContext(userId, panel);
  closeUserDetailModal();
}

async function deleteCurrentUserFromDetail() {
  const userId = getCurrentUserDetailId();
  if (!userId) return;
  const userEmail = userDetailData?.user?.email || `#${userId}`;
  await deleteUser(userId, userEmail);
}

/** Obnova po soft-delete: e-mail z archivu, aktivace účtu, sync `user_email` u vozidel, obnova archivovaných servisních záznamů na vozidlech vlastníka. */
async function restoreSoftDeletedUserFromDetail() {
  const userId = getCurrentUserDetailId();
  const user = userDetailData?.user;
  if (!userId || !user?.is_deleted) {
    showGlobalError('Obnova je dostupná jen pro účty ve stavu soft-delete.');
    return;
  }
  const planned = user.deletion_email_before ? String(user.deletion_email_before).trim() : '';
  const reason = await promptAdminReason(
    planned
      ? `Obnova účtu #${userId}: přihlašovací e-mail bude ${planned}. U vozidel vlastníka se obnoví zobrazený e-mail a archivované servisní záznamy na těchto vozidlech.`
      : `Obnova účtu #${userId} z archivu smazání.`,
  );
  if (!reason) return;
  const confirmMsg = planned
    ? `Obnovit účet #${userId} na e-mail ${planned}?\n\nDůvod (audit): ${reason}`
    : `Obnovit účet #${userId}?\n\nDůvod (audit): ${reason}`;
  if (!confirm(confirmMsg)) return;
  try {
    const data = await apiRequest('POST', '/admin-api/user-soft-restore', {
      customer_id: userId,
      reason,
    });
    showSuccess(data?.message || 'Účet byl obnoven');
    if (typeof loadDeletedUsersArchive === 'function') {
      await loadDeletedUsersArchive();
    }
    await Promise.all([
      typeof loadUsers === 'function' ? loadUsers() : Promise.resolve(),
      typeof loadOverview === 'function' ? loadOverview() : Promise.resolve(),
    ]);
    await refreshUserDetail(userDetailActivePanel);
  } catch (error) {
    console.error('Error restoring soft-deleted user:', error);
    showGlobalError(error?.message || String(error));
  }
}

async function disableCurrentUserFromDetail() {
  const userId = getCurrentUserDetailId();
  if (!userId) return;
  if (!confirm(`Pozastavit účet uživatele #${userId}?`)) return;
  try {
    const data = await apiRequest('POST', `/admin-api/control-center/users/${userId}/disable`, { reason: 'detail_modal' });
    showSuccess(data?.message || 'Účet byl pozastaven');
    await Promise.all([loadUsers(), refreshUserDetail()]);
  } catch (error) {
    console.error('Error disabling user from detail:', error);
  }
}

async function enableCurrentUserFromDetail() {
  const userId = getCurrentUserDetailId();
  if (!userId) return;
  if (!confirm(`Aktivovat účet uživatele #${userId}?`)) return;
  try {
    const data = await apiRequest('POST', `/admin-api/control-center/users/${userId}/enable`, { reason: 'detail_modal' });
    showSuccess(data?.message || 'Účet byl aktivován');
    await Promise.all([loadUsers(), refreshUserDetail()]);
  } catch (error) {
    console.error('Error enabling user from detail:', error);
  }
}

async function forceLogoutCurrentUserFromDetail() {
  const userId = getCurrentUserDetailId();
  if (!userId) return;
  if (!confirm(`Ukončit všechny relace uživatele #${userId}?`)) return;
  try {
    const data = await apiRequest('POST', `/admin-api/control-center/users/${userId}/force-logout`, { reason: 'detail_modal' });
    showSuccess(data?.message || 'Relace byly ukončeny');
    await refreshUserDetail();
  } catch (error) {
    console.error('Error forcing logout from detail:', error);
  }
}

async function resetPasswordCurrentUserFromDetail() {
  const userId = getCurrentUserDetailId();
  if (!userId) return;
  const password = prompt('Nové heslo (prázdné = vygenerovat dočasné):', '');
  try {
    const data = await apiRequest('POST', `/admin-api/control-center/users/${userId}/reset-password`, {
      new_password: password || null,
      generate_random: !password,
      reason: 'detail_modal',
    });
    if (data?.temporary_password) {
      showSuccess(`Dočasné heslo: ${data.temporary_password}`);
    } else {
      showSuccess(data?.message || 'Heslo bylo resetováno');
    }
    await refreshUserDetail();
  } catch (error) {
    console.error('Error resetting password from detail:', error);
  }
}

function editVehicleFromUserDetail(vehicleId) {
  if (!userDetailData?.user?.id) return;
  setUserDetailReturnContext(userDetailData.user.id, 'vehicles');
  closeUserDetailModal();
  showVehicleModal(vehicleId);
}

function editRecordFromUserDetail(recordId) {
  if (!userDetailData?.user?.id) return;
  setUserDetailReturnContext(userDetailData.user.id, 'records');
  closeUserDetailModal();
  showRecordModal(recordId);
}

async function deleteVehicleFromUserDetail(vehicleId, encodedVehicleLabel) {
  const vehicleLabel = decodeURIComponent(encodedVehicleLabel || '');
  if (!confirm(`Opravdu chcete smazat vozidlo ${vehicleLabel || '#'+vehicleId}?`)) return;
  try {
    await apiRequest('DELETE', `/admin-api/vehicles/${vehicleId}`);
    showSuccess('Údaj byl upraven adminem: vozidlo smazáno');
    await Promise.all([loadVehicles(), loadUsers(), loadOverview()]);
    await refreshUserDetail('vehicles');
  } catch (error) {
    console.error('Error deleting vehicle from detail:', error);
  }
}

async function deleteRecordFromUserDetail(recordId) {
  if (!confirm('Archivovat tento servisní záznam? Lze jej později obnovit v sekci Záznamy → archivované záznamy.')) return;
  try {
    await apiRequest('DELETE', `/admin-api/records/${recordId}`);
    showSuccess('Servisní záznam archivován (obnovitelný v adminu)');
    await Promise.all([loadRecords(), loadDeletedServiceRecords(), loadOverview()]);
    await refreshUserDetail('records');
  } catch (error) {
    console.error('Error deleting record from detail:', error);
  }
}

async function quickEditReminderFromUserDetail(reminderId, encodedCurrentText) {
  const currentText = decodeURIComponent(encodedCurrentText || '');
  const nextText = prompt('Upravte text připomínky:', currentText || '');
  if (nextText === null) return;
  try {
    await apiRequest('PATCH', `/admin-api/reminders/${reminderId}`, { text: nextText });
    showSuccess('Údaj byl upraven adminem: připomínka aktualizována');
    await Promise.all([loadOverview()]);
    await refreshUserDetail('reminders');
  } catch (error) {
    console.error('Error updating reminder from detail:', error);
  }
}

async function toggleReminderCompletionFromUserDetail(reminderId, nextCompletedState) {
  try {
    await apiRequest('PATCH', `/admin-api/reminders/${reminderId}`, { is_completed: nextCompletedState });
    showSuccess('Údaj byl upraven adminem: stav připomínky změněn');
    await Promise.all([loadOverview()]);
    await refreshUserDetail('reminders');
  } catch (error) {
    console.error('Error toggling reminder state from detail:', error);
  }
}

async function deleteReminderFromUserDetail(reminderId) {
  if (!confirm('Opravdu chcete smazat tuto připomínku?')) return;
  try {
    await apiRequest('DELETE', `/admin-api/reminders/${reminderId}`);
    showSuccess('Údaj byl upraven adminem: připomínka smazána');
    await Promise.all([loadOverview()]);
    await refreshUserDetail('reminders');
  } catch (error) {
    console.error('Error deleting reminder from detail:', error);
  }
}

async function updateReservationStatusFromUserDetail(reservationId, status) {
  try {
    await apiRequest('PATCH', `/admin-api/reservations/${reservationId}`, { status });
    showSuccess(`Údaj byl upraven adminem: rezervace nastavena na ${status}`);
    await Promise.all([loadOverview()]);
    await refreshUserDetail('reservations');
  } catch (error) {
    console.error('Error updating reservation status from detail:', error);
  }
}

async function deleteReservationFromUserDetail(reservationId) {
  if (!confirm('Opravdu chcete smazat tuto rezervaci?')) return;
  try {
    await apiRequest('DELETE', `/admin-api/reservations/${reservationId}`);
    showSuccess('Údaj byl upraven adminem: rezervace smazána');
    await Promise.all([loadOverview()]);
    await refreshUserDetail('reservations');
  } catch (error) {
    console.error('Error deleting reservation from detail:', error);
  }
}

function applyDefaultUserWorkspaceCheckboxesFromRole() {
  const role = (document.getElementById('user-role')?.value || 'user').toLowerCase();
  populateLicensePlanSelect('user-license-plan', role, document.getElementById('user-license-plan')?.value || '', {
    includeBlank: false,
  });
  const uEl = document.getElementById('user-ws-user');
  const sEl = document.getElementById('user-ws-service');
  const dEl = document.getElementById('user-ws-default');
  if (!uEl || !sEl) return;
  if (role === 'service') {
    uEl.checked = false;
    sEl.checked = true;
  } else {
    uEl.checked = true;
    sEl.checked = false;
  }
  if (dEl) dEl.value = '';
}

function roleDerivedWorkspaceEntitlements(role) {
  const r = String(role || '').toLowerCase();
  if (r === 'service') return ['service'];
  return ['user'];
}

/** Sjednocení s backendem effective_workspace_kinds + PATCH přes model_fields_set. */
function collectUserWorkspaceSavePayload(role) {
  const ws = [];
  if (document.getElementById('user-ws-user')?.checked) ws.push('user');
  if (document.getElementById('user-ws-service')?.checked) ws.push('service');
  ws.sort((a, b) => a.localeCompare(b));
  if (ws.length === 0) {
    return { error: 'Vyberte alespoň jeden pracovní režim (uživatel a/nebo servis).' };
  }
  const derived = roleDerivedWorkspaceEntitlements(role).slice().sort((a, b) => a.localeCompare(b));
  const sameDer = ws.length === derived.length && ws.every((k) => derived.includes(k));
  const defRaw = (document.getElementById('user-ws-default')?.value || '').trim();
  if (sameDer) {
    return { workspace_entitlements: null, workspace_ui_default: null, sameAsRoleDefault: true };
  }
  return {
    workspace_entitlements: ws,
    workspace_ui_default: ws.length > 1 && defRaw ? defRaw : null,
    sameAsRoleDefault: false,
  };
}

async function showUserModal(userId = null) {
  const modal = document.getElementById('user-modal');
  const form = document.getElementById('user-form');
  const title = document.getElementById('user-modal-title');
  const passwordHint = document.getElementById('user-password-hint');
  const passwordInput = document.getElementById('user-password');
  
  if (userId) {
    title.textContent = 'Upravit uživatele';
    passwordHint.textContent = '(nechte prázdné, pokud neměníte)';
    passwordInput.required = false;
    
    try {
      let user = null;
      try {
        const detail = await apiRequest('GET', `/admin-api/users/${userId}/detail`);
        user = detail?.user || null;
      } catch (detailError) {
        console.warn('Detail uživatele se nepodařilo načíst, použije se fallback seznam.', detailError);
      }

      if (!user) {
        const users = usersAllCache.length > 0 ? usersAllCache : await fetchAllList('/admin-api/users');
        user = users.find(u => u.id === userId) || null;
      }

      if (!user) {
        showGlobalError(
          'Uživatele se nepodařilo načíst (detail ani seznam). Obnovte sekci Uživatelé nebo se přihlaste znovu.',
        );
        return false;
      }

      document.getElementById('user-id').value = user.id;
      document.getElementById('user-email').value = user.email || '';
      document.getElementById('user-name').value = user.name || '';
      document.getElementById('user-role').value = user.role || 'user';
      document.getElementById('user-phone').value = user.phone || '';
      document.getElementById('user-ico').value = user.ico || '';
      document.getElementById('user-dic').value = user.dic || '';
      document.getElementById('user-street').value = user.street || '';
      document.getElementById('user-street-number').value = user.street_number || '';
      document.getElementById('user-city').value = user.city || '';
      document.getElementById('user-zip').value = user.zip || '';
      populateLicensePlanSelect('user-license-plan', user.role || 'user', user.license_plan || 'free', {
        includeBlank: false,
        workspaceKind: user.license_workspace_kind || null,
        allowedPlansFromApi: user.license_allowed_plans ?? null,
      });
      const ent = Array.isArray(user.workspace_entitlements)
        ? user.workspace_entitlements.map((x) => String(x || '').toLowerCase())
        : null;
      const uWs = document.getElementById('user-ws-user');
      const sWs = document.getElementById('user-ws-service');
      const dWs = document.getElementById('user-ws-default');
      if (uWs && sWs) {
        if (ent && ent.length) {
          uWs.checked = ent.includes('user');
          sWs.checked = ent.includes('service');
        } else {
          applyDefaultUserWorkspaceCheckboxesFromRole();
        }
      }
      if (dWs) {
        const ud = String(user.workspace_ui_default || '').toLowerCase();
        dWs.value = ud === 'service' || ud === 'user' ? ud : '';
      }
      passwordInput.value = '';
    } catch (error) {
      showGlobalError('Chyba při načítání uživatele: ' + error.message);
      return false;
    }
  } else {
    title.textContent = 'Přidat uživatele';
    passwordHint.textContent = '(povinné při vytvoření)';
    form.reset();
    document.getElementById('user-id').value = '';
    passwordInput.required = true;
    populateLicensePlanSelect('user-license-plan', document.getElementById('user-role')?.value || 'user', 'free', {
      includeBlank: false,
    });
    applyDefaultUserWorkspaceCheckboxesFromRole();
  }
  
  modal.classList.remove('hidden');
  return true;
}

function closeUserModal(preserveReturnContext = false) {
  document.getElementById('user-modal').classList.add('hidden');
  document.getElementById('user-form').reset();
  if (!preserveReturnContext) {
    userDetailReturnContext = null;
  }
}

async function saveUser(event) {
  event.preventDefault();
  
  const userId = document.getElementById('user-id').value;
  const userData = {
    email: document.getElementById('user-email').value,
    name: document.getElementById('user-name').value || null,
    role: document.getElementById('user-role').value,
    phone: document.getElementById('user-phone').value || null,
    ico: document.getElementById('user-ico').value || null,
    dic: document.getElementById('user-dic').value || null,
    street: document.getElementById('user-street').value || null,
    street_number: document.getElementById('user-street-number').value || null,
    city: document.getElementById('user-city').value || null,
    zip: document.getElementById('user-zip').value || null,
    license_plan: document.getElementById('user-license-plan').value || 'free',
  };
  
  const password = document.getElementById('user-password').value;
  if (password) {
    userData.password = password;
  }

  const wsp = collectUserWorkspaceSavePayload(userData.role);
  if (wsp.error) {
    showGlobalError(wsp.error);
    return;
  }
  
  try {
    let responseData = null;
    if (userId) {
      if (!wsp.sameAsRoleDefault) {
        userData.workspace_entitlements = wsp.workspace_entitlements;
        userData.workspace_ui_default = wsp.workspace_ui_default;
      }
      responseData = await apiRequest('PATCH', `/admin-api/users/${userId}`, userData);
      const planLabel = formatAdminLicensePlanLabel(
        responseData?.license_plan || userData.license_plan || 'free',
        userData.role,
        userDetailData?.user?.license_workspace_kind || null,
      );
      const wEnt = Array.isArray(responseData?.workspace_entitlements) ? responseData.workspace_entitlements.join(' + ') : '';
      const wMsg = wEnt ? ` Režimy v aplikaci: ${wEnt}.` : '';
      showSuccess(`Údaj byl upraven (licence: ${planLabel}).${wMsg} Uživatel uvidí změnu po obnovení stránky v aplikaci nebo při příštím načtení účtu.`);
    } else {
      if (!password) {
        showGlobalError('Heslo je povinné při vytváření uživatele');
        return;
      }
      if (!wsp.sameAsRoleDefault) {
        userData.workspace_entitlements = wsp.workspace_entitlements;
        userData.workspace_ui_default = wsp.workspace_ui_default;
      }
      responseData = await apiRequest('POST', '/admin-api/users', userData);
      const planLabel = formatAdminLicensePlanLabel(responseData?.license_plan || userData.license_plan || 'free', userData.role);
      const wEnt = Array.isArray(responseData?.workspace_entitlements) ? responseData.workspace_entitlements.join(' + ') : '';
      const wMsg = wEnt ? ` Režimy: ${wEnt}.` : '';
      showSuccess(`Uživatel byl vytvořen (licence: ${planLabel}).${wMsg}`);
    }
    
    closeUserModal(true);
    await Promise.all([loadUsers(), loadOverview()]);
    await reopenUserDetailIfNeeded();
  } catch (error) {
    console.error('Error saving user:', error);
  }
}

function stopEventSafely(evt) {
  if (!evt || typeof evt !== 'object') return;
  if (typeof evt.preventDefault === 'function') evt.preventDefault();
  if (typeof evt.stopPropagation === 'function') evt.stopPropagation();
}

let _adminReasonModalResolve = null;
let _adminReasonEscapeHandler = null;

function _teardownAdminInterventionReasonModal() {
  if (_adminReasonEscapeHandler) {
    document.removeEventListener('keydown', _adminReasonEscapeHandler, true);
    _adminReasonEscapeHandler = null;
  }
  const modal = document.getElementById('admin-intervention-reason-modal');
  if (modal) {
    modal.classList.add('hidden');
  }
}

function cancelAdminInterventionReasonModal() {
  const resolve = _adminReasonModalResolve;
  _adminReasonModalResolve = null;
  _teardownAdminInterventionReasonModal();
  if (resolve) {
    resolve(null);
  }
}

function submitAdminInterventionReasonModal() {
  const textarea = document.getElementById('admin-reason-modal-input');
  const errEl = document.getElementById('admin-reason-modal-error');
  const trimmed = String(textarea?.value || '').trim();
  if (trimmed.length < 3) {
    if (errEl) {
      errEl.textContent =
        'Důvod je příliš krátký: po odebrání mezer na začátku a konci musí text mít alespoň 3 znaky (stačí jedna krátká věta, ne „tři důvody“).';
      errEl.classList.remove('hidden');
    }
    return;
  }
  if (errEl) {
    errEl.textContent = '';
    errEl.classList.add('hidden');
  }
  const resolve = _adminReasonModalResolve;
  _adminReasonModalResolve = null;
  _teardownAdminInterventionReasonModal();
  if (resolve) {
    resolve(trimmed);
  }
}

/** Vlastní modal místo window.prompt — prompt u otevřeného fullscreen modalu často nefunguje. */
function promptAdminReason(message) {
  if (_adminReasonModalResolve) {
    showGlobalError('Dialog důvodu je již otevřený; nejdřív ho dokončete nebo zrušte.');
    return Promise.resolve(null);
  }
  return new Promise((resolve) => {
    const modal = document.getElementById('admin-intervention-reason-modal');
    const ctx = document.getElementById('admin-reason-modal-context');
    const textarea = document.getElementById('admin-reason-modal-input');
    const errEl = document.getElementById('admin-reason-modal-error');
    if (!modal || !textarea) {
      resolve(null);
      return;
    }
    _adminReasonModalResolve = resolve;
    if (ctx) {
      ctx.textContent = message || '';
    }
    textarea.value = '';
    if (errEl) {
      errEl.textContent = '';
      errEl.classList.add('hidden');
    }
    modal.classList.remove('hidden');
    _adminReasonEscapeHandler = (ev) => {
      if (ev.key === 'Escape') {
        ev.preventDefault();
        ev.stopPropagation();
        cancelAdminInterventionReasonModal();
      }
    };
    document.addEventListener('keydown', _adminReasonEscapeHandler, true);
    requestAnimationFrame(() => {
      textarea.focus();
    });
  });
}

async function editUser(eventOrUserId, maybeUserId = null) {
  const hasEvent = eventOrUserId && typeof eventOrUserId === 'object' && typeof eventOrUserId.stopPropagation === 'function';
  const userId = hasEvent ? maybeUserId : eventOrUserId;
  if (hasEvent) {
    stopEventSafely(eventOrUserId);
  }
  showUserModal(userId);
}

async function deleteUser(eventOrUserId, maybeUserId = null, maybeUserEmail = null) {
  const hasEvent = eventOrUserId && typeof eventOrUserId === 'object' && typeof eventOrUserId.stopPropagation === 'function';
  const userId = hasEvent ? maybeUserId : eventOrUserId;
  const userEmail = hasEvent ? maybeUserEmail : maybeUserId;
  if (hasEvent) {
    stopEventSafely(eventOrUserId);
  }
  const reason = await promptAdminReason(`Mazání uživatele ${userEmail} je destruktivní akce.`);
  if (!reason) {
    return;
  }
  if (!confirm(`Potvrdit smazání uživatele ${userEmail}?\n\nDůvod: ${reason}`)) return;
  
  try {
    await apiRequest('DELETE', `/admin-api/users/${userId}`);
    showSuccess('Uživatel byl smazán');
    const currentDetailId = getCurrentUserDetailId();
    if (Number(currentDetailId) === Number(userId)) {
      closeUserDetailModal();
    }
    await Promise.all([loadUsers(), loadOverview()]);
  } catch (error) {
    console.error('Error deleting user:', error);
  }
}

// ============================================
// VEHICLES CRUD
// ============================================

async function loadVehicles() {
  const container = document.getElementById('vehicles-cards-container');
  if (!container) return;
  
  container.innerHTML = '<div class="loading">Načítám vozidla...</div>';
  
  try {
    const vehicles = await fetchAllList('/admin-api/vehicles');
    
    if (vehicles.length === 0) {
      container.innerHTML = '<div class="empty">Žádná vozidla</div>';
      applySectionViewMode('vehicles');
      return;
    }
    
    container.innerHTML = vehicles.map(vehicle => {
      const createdDate = formatDate(vehicle.created_at, '-');
      const vehicleName = vehicle.nickname || `${vehicle.brand || ''} ${vehicle.model || ''}`.trim() || 'Bez názvu';
      return `
        <div class="card" data-vehicle-id="${vehicle.id}" onclick="maybeOpenVehicleSupportView(event, ${vehicle.id})" style="cursor: pointer;">
          <div class="card-header">
            <h3 class="card-title">🚗 ${vehicleName}</h3>
            <span class="card-id">#${vehicle.id}</span>
          </div>
          <div class="card-body">
            <div class="card-field">
              <span class="card-label">Vlastník</span>
              <span class="card-value">${vehicle.owner_name || vehicle.user_email || '-'}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Značka / Model</span>
              <span class="card-value">${vehicle.brand || '-'} ${vehicle.model || ''}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Rok</span>
              <span class="card-value">${vehicle.year || '-'}</span>
            </div>
            <div class="card-field">
              <span class="card-label">SPZ</span>
              <span class="card-value">${vehicle.plate || '-'}</span>
            </div>
            ${vehicle.vin ? `
            <div class="card-field">
              <span class="card-label">VIN</span>
              <span class="card-value" style="font-family: monospace; font-size: 13px;">${vehicle.vin}</span>
            </div>
            ` : ''}
            <div class="card-field">
              <span class="card-label">Přidáno</span>
              <span class="card-value">${createdDate}</span>
            </div>
          </div>
          <div class="card-actions" onclick="event.stopPropagation();">
            <button type="button" class="btn-secondary btn-small" onclick="openVehicleSupportViewModal(${vehicle.id})">🔍 Podpora</button>
            <button type="button" class="btn-edit" onclick="editVehicle(${vehicle.id})">✏️ Upravit</button>
            <button type="button" class="btn-danger" onclick="deleteVehicle(${vehicle.id}, '${vehicleName.replace(/'/g, "\\'")}')">🗑️ Smazat</button>
          </div>
        </div>
      `;
    }).join('');
    applySectionViewMode('vehicles');
    
    // Vyhledávání
    const searchInput = document.getElementById('vehicle-search');
    if (searchInput) {
      searchInput.oninput = (e) => {
        const query = e.target.value.toLowerCase();
        const cards = container.querySelectorAll('.card');
        cards.forEach(card => {
          const text = card.textContent.toLowerCase();
          card.style.display = text.includes(query) ? '' : 'none';
        });
      };
    }
    
  } catch (error) {
    container.innerHTML = `<div class="error">Chyba při načítání: ${error.message}</div>`;
  }
}

async function showVehicleModal(vehicleId = null) {
  const modal = document.getElementById('vehicle-modal');
  const title = document.getElementById('vehicle-modal-title');
  
  if (vehicleId) {
    title.textContent = 'Upravit vozidlo';
    try {
      const vehicles = await fetchAllList('/admin-api/vehicles');
      const vehicle = vehicles.find(v => v.id === vehicleId);
      if (vehicle) {
        document.getElementById('vehicle-id').value = vehicle.id;
        document.getElementById('vehicle-user-email').value = vehicle.user_email || '';
        document.getElementById('vehicle-nickname').value = vehicle.nickname || '';
        document.getElementById('vehicle-brand').value = vehicle.brand || '';
        document.getElementById('vehicle-model').value = vehicle.model || '';
        document.getElementById('vehicle-year').value = vehicle.year || '';
        document.getElementById('vehicle-plate').value = vehicle.plate || '';
        document.getElementById('vehicle-vin').value = vehicle.vin || '';
      }
    } catch (error) {
      showGlobalError('Chyba při načítání vozidla: ' + error.message);
      return;
    }
  } else {
    title.textContent = 'Přidat vozidlo';
    document.getElementById('vehicle-form').reset();
    document.getElementById('vehicle-id').value = '';
  }
  
  modal.classList.remove('hidden');
}

function closeVehicleModal(preserveReturnContext = false) {
  document.getElementById('vehicle-modal').classList.add('hidden');
  document.getElementById('vehicle-form').reset();
  if (!preserveReturnContext) {
    userDetailReturnContext = null;
  }
}

async function saveVehicle(event) {
  event.preventDefault();
  
  const vehicleId = document.getElementById('vehicle-id').value;
  const vehicleData = {
    user_email: document.getElementById('vehicle-user-email').value,
    nickname: document.getElementById('vehicle-nickname').value || null,
    brand: document.getElementById('vehicle-brand').value || null,
    model: document.getElementById('vehicle-model').value || null,
    year: parseInt(document.getElementById('vehicle-year').value) || null,
    plate: document.getElementById('vehicle-plate').value || null,
    vin: document.getElementById('vehicle-vin').value || null,
  };
  
  try {
    if (vehicleId) {
      await apiRequest('PATCH', `/admin-api/vehicles/${vehicleId}`, vehicleData);
      showSuccess('Údaj byl upraven adminem: vozidlo');
    } else {
      await apiRequest('POST', '/admin-api/vehicles', vehicleData);
      showSuccess('Vozidlo bylo vytvořeno');
    }
    
    closeVehicleModal(true);
    await Promise.all([loadVehicles(), loadOverview(), loadUsers()]);
    await reopenUserDetailIfNeeded();
  } catch (error) {
    console.error('Error saving vehicle:', error);
  }
}

async function editVehicle(vehicleId) {
  showVehicleModal(vehicleId);
}

async function deleteVehicle(vehicleId, vehicleName) {
  if (!confirm(`Opravdu chcete smazat vozidlo ${vehicleName}?`)) {
    return;
  }
  
  try {
    await apiRequest('DELETE', `/admin-api/vehicles/${vehicleId}`);
    showSuccess('Vozidlo bylo smazáno');
    await Promise.all([loadVehicles(), loadOverview()]);
    if (currentSection === 'global-admin') {
      await loadGlobalAdmin();
    }
  } catch (error) {
    console.error('Error deleting vehicle:', error);
  }
}

// ============================================
// SERVICES CRUD
// ============================================

async function loadServices() {
  const container = document.getElementById('services-cards-container');
  if (!container) return;
  
  container.innerHTML = '<div class="loading">Načítám servisy...</div>';
  loadServiceRegistrationRequests();
  
  try {
    const services = await fetchAllList('/admin-api/services');
    
    if (services.length === 0) {
      container.innerHTML = '<div class="empty">Žádné servisy</div>';
      applySectionViewMode('services');
      return;
    }
    
    container.innerHTML = services.map(service => {
      const createdDate = formatDate(service.created_at, '-');
      return `
        <div class="card" data-service-id="${service.id}">
          <div class="card-header">
            <h3 class="card-title">🛠️ ${service.name || service.email || 'Bez názvu'}</h3>
            <span class="card-id">#${service.id}</span>
          </div>
          <div class="card-body">
            <div class="card-field">
              <span class="card-label">Email</span>
              <span class="card-value">${service.email || '-'}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Město</span>
              <span class="card-value">${service.city || '-'}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Telefon</span>
              <span class="card-value">${service.phone || '-'}</span>
            </div>
            ${service.ico ? `
            <div class="card-field">
              <span class="card-label">IČO</span>
              <span class="card-value">${service.ico}</span>
            </div>
            ` : ''}
            <div class="card-field">
              <span class="card-label">Registrován</span>
              <span class="card-value">${createdDate}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Úložiště (data)</span>
              <span class="card-value" title="Odhad podle tenant_id — stejné u účtů se stejným tenantem.">${escapeHtml(formatUserDiskHuman(service) ?? '—')}</span>
            </div>
          </div>
          <div class="card-actions">
            <button class="btn-edit" onclick="editService(${service.id})">✏️ Upravit</button>
            <button class="btn-danger" onclick="deleteService(${service.id}, '${(service.name || service.email || '').replace(/'/g, "\\'")}')">🗑️ Smazat</button>
          </div>
        </div>
      `;
    }).join('');
    applySectionViewMode('services');
    
    // Vyhledávání
    const searchInput = document.getElementById('service-search');
    if (searchInput) {
      searchInput.oninput = (e) => {
        const query = e.target.value.toLowerCase();
        const cards = container.querySelectorAll('.card');
        cards.forEach(card => {
          const text = card.textContent.toLowerCase();
          card.style.display = text.includes(query) ? '' : 'none';
        });
      };
    }
    
  } catch (error) {
    container.innerHTML = `<div class="error">Chyba při načítání: ${error.message}</div>`;
  }
}

async function loadServiceRegistrationRequests() {
  const container = document.getElementById('service-requests-container');
  if (!container) return;

  container.innerHTML = '<div class="loading">Načítám čekající žádosti...</div>';

  try {
    const requests = await fetchAllList('/admin-api/service-registration-requests?status=pending');
    if (!requests.length) {
      container.innerHTML = '<div class="empty">Žádné čekající žádosti o servisní registraci.</div>';
      return;
    }

    container.innerHTML = requests.map((item) => {
      const createdAt = formatDateTime(item.created_at, '-');
      const address = [item.street, item.street_number, item.city, item.zip]
        .filter(Boolean)
        .join(', ');
      const emailVerificationLabel = (() => {
        if (item.email_verification_state === 'verified' && item.email_verified_at) {
          return `Ano (${formatDateTime(item.email_verified_at, '-')})`;
        }
        if (item.email_verification_state === 'pending') {
          return 'Ne — žadatel musí kliknout na odkaz v e-mailu';
        }
        return 'Starší žádost (bez e-mailového ověřovacího odkazu)';
      })();
      return `
        <article class="service-request-item">
          <div class="service-request-main">
            <div>
              <p class="service-request-title">🛠️ ${escapeHtml(item.service_name || '-')}</p>
              <p class="service-request-meta">
                Email: <strong>${escapeHtml(item.email || '-')}</strong><br>
                Ověření e-mailu žadatele: <strong>${escapeHtml(emailVerificationLabel)}</strong><br>
                IČO: <strong>${escapeHtml(item.ico || '-')}</strong> ${item.dic ? `• DIČ: <strong>${escapeHtml(item.dic)}</strong>` : ''}<br>
                Zodpovědná osoba: <strong>${escapeHtml(item.responsible_person || '-')}</strong><br>
                Telefon: <strong>${escapeHtml(item.phone || '-')}</strong><br>
                Adresa: <strong>${escapeHtml(address || '-')}</strong><br>
                Podáno: <strong>${escapeHtml(createdAt)}</strong>
              </p>
            </div>
            <span class="status-pill status-warn">Čeká na schválení</span>
          </div>
          <div class="service-request-purpose"><strong>Účel registrace:</strong><br>${escapeHtml(item.registration_purpose || '-')}</div>
          <div class="service-request-actions">
            <button class="btn-primary btn-sm" onclick="approveServiceRegistrationRequest(${item.id})">✅ Schválit</button>
            <button class="btn-danger btn-sm" onclick="rejectServiceRegistrationRequest(${item.id})">❌ Zamítnout</button>
          </div>
        </article>
      `;
    }).join('');
  } catch (error) {
    container.innerHTML = `<div class="error">Chyba při načítání žádostí: ${escapeHtml(error.message || 'Neznámá chyba')}</div>`;
  }
}

async function approveServiceRegistrationRequest(requestId) {
  if (!confirm('Opravdu chcete schválit tuto servisní registraci a vytvořit aktivní servisní účet?')) {
    return;
  }

  const reviewNoteRaw = prompt('Poznámka ke schválení (volitelné):', 'Schváleno po kontrole údajů.');
  if (reviewNoteRaw === null) {
    return;
  }

  try {
    await apiRequest('POST', `/admin-api/service-registration-requests/${requestId}/approve`, {
      review_note: reviewNoteRaw || null
    });
    showSuccess('Žádost byla schválena a servisní účet vytvořen.');
    // Servis je nový záznam v customers — bez loadUsers() by sekce „Uživatelé“ a cache zůstaly zastaralé až do F5.
    await Promise.all([loadServices(), loadUsers(), loadOverview()]);
  } catch (error) {
    console.error('Error approving service registration request:', error);
  }
}

async function rejectServiceRegistrationRequest(requestId) {
  if (!confirm('Opravdu chcete zamítnout tuto servisní registraci?')) {
    return;
  }

  const reviewNoteRaw = prompt('Důvod zamítnutí (doporučeno):', 'Žádost byla zamítnuta po kontrole údajů.');
  if (reviewNoteRaw === null) {
    return;
  }

  try {
    await apiRequest('POST', `/admin-api/service-registration-requests/${requestId}/reject`, {
      review_note: reviewNoteRaw || null
    });
    showSuccess('Žádost byla zamítnuta.');
    await Promise.all([loadServiceRegistrationRequests(), loadOverview()]);
  } catch (error) {
    console.error('Error rejecting service registration request:', error);
  }
}

async function showServiceModal(serviceId = null) {
  const modal = document.getElementById('service-modal');
  const title = document.getElementById('service-modal-title');
  const passwordHint = document.getElementById('service-password-hint');
  const passwordInput = document.getElementById('service-password');
  
  if (serviceId) {
    title.textContent = 'Upravit servis';
    passwordHint.textContent = '(nechte prázdné, pokud neměníte)';
    passwordInput.required = false;
    
    try {
      const services = await fetchAllList('/admin-api/services');
      const service = services.find(s => s.id === serviceId);
      if (service) {
        document.getElementById('service-id').value = service.id;
        document.getElementById('service-email').value = service.email || '';
        document.getElementById('service-name').value = service.name || '';
        document.getElementById('service-city').value = service.city || '';
        document.getElementById('service-phone').value = service.phone || '';
        document.getElementById('service-ico').value = service.ico || '';
        passwordInput.value = '';
      }
    } catch (error) {
      showGlobalError('Chyba při načítání servisu: ' + error.message);
      return;
    }
  } else {
    title.textContent = 'Přidat servis';
    passwordHint.textContent = '(povinné při vytvoření)';
    document.getElementById('service-form').reset();
    document.getElementById('service-id').value = '';
    passwordInput.required = true;
  }
  
  modal.classList.remove('hidden');
}

function closeServiceModal() {
  document.getElementById('service-modal').classList.add('hidden');
  document.getElementById('service-form').reset();
}

async function saveService(event) {
  event.preventDefault();
  
  const serviceId = document.getElementById('service-id').value;
  const serviceData = {
    email: document.getElementById('service-email').value,
    name: document.getElementById('service-name').value,
    city: document.getElementById('service-city').value || null,
    phone: document.getElementById('service-phone').value || null,
    ico: document.getElementById('service-ico').value || null,
  };
  
  const password = document.getElementById('service-password').value;
  if (password) {
    serviceData.password = password;
  }
  
  try {
    if (serviceId) {
      await apiRequest('PATCH', `/admin-api/services/${serviceId}`, serviceData);
      showSuccess('Servis byl upraven');
    } else {
      if (!password) {
        showGlobalError('Heslo je povinné při vytváření servisu');
        return;
      }
      await apiRequest('POST', '/admin-api/services', serviceData);
      showSuccess('Servis byl vytvořen');
    }
    
    closeServiceModal();
    await Promise.all([loadServices(), loadUsers(), loadOverview()]);
  } catch (error) {
    console.error('Error saving service:', error);
  }
}

async function editService(serviceId) {
  showServiceModal(serviceId);
}

async function deleteService(serviceId, serviceName) {
  if (!confirm(`Opravdu chcete smazat servis ${serviceName}?`)) {
    return;
  }
  
  try {
    const data = await apiRequest('DELETE', `/admin-api/services/${serviceId}`);
    showSuccess(data?.message || 'Servis byl odstraněn ze seznamu');
    await Promise.all([loadServices(), loadUsers(), loadOverview()]);
  } catch (error) {
    console.error('Error deleting service:', error);
  }
}

// ============================================
// RECORDS CRUD
// ============================================

async function loadDeletedServiceRecords() {
  const container = document.getElementById('records-deleted-container');
  if (!container) return;
  container.innerHTML = '<div class="loading">Načítám archivované záznamy…</div>';
  try {
    const baseParams = { limit: 200, offset: 0 };
    const attempts = [
      { label: 'archived-service-records', path: '/admin-api/archived-service-records', params: { ...baseParams } },
      { label: 'records-deleted-only', path: '/admin-api/records', params: { ...baseParams, deleted_only: true } },
      { label: 'records-deleted', path: '/admin-api/records/deleted', params: { ...baseParams } },
    ];
    let data = null;
    const attemptErrors = [];
    for (const { label, path, params } of attempts) {
      try {
        const payload = await apiRequest('GET', withQueryParams(path, params));
        if (payload && Array.isArray(payload.items)) {
          data = payload;
          break;
        }
        if (payload && Array.isArray(payload.records) && payload.items === undefined) {
          attemptErrors.push(`${label}: API vrátilo běžný seznam (chybí podpora archivu na serveru)`);
        }
      } catch (err) {
        attemptErrors.push(`${label}: ${err?.message || String(err)}`);
      }
    }

    if (!data || !Array.isArray(data.items)) {
      const hint = attemptErrors.length
        ? `<ul style="margin:0.5rem 0 0 1rem;">${attemptErrors.map((e) => `<li>${escapeHtml(e)}</li>`).join('')}</ul>`
        : '';
      container.innerHTML = `<div class="error">Archiv se nepodařilo načíst. Nasaďte backend s endpointem <code>/admin-api/archived-service-records</code> a restartujte službu.${hint}</div>`;
      return;
    }

    const items = Array.isArray(data?.items) ? data.items : [];
    if (data?.error && !items.length) {
      container.innerHTML = `<div class="error">${escapeHtml(data.error)}</div>`;
      return;
    }
    if (!items.length) {
      container.innerHTML = '<div class="empty">Žádné archivované servisní záznamy</div>';
      return;
    }
    const rows = items
      .map((row) => {
        const del = row.deleted_at ? formatDate(row.deleted_at, '-') : '-';
        const perf = row.performed_at ? formatDate(row.performed_at, '-') : '-';
        const reason = escapeHtml(String(row.deletion_reason || '—'));
        const desc = escapeHtml(String(row.description_preview || ''));
        const vehicle = escapeHtml(String(row.vehicle_label || ''));
        const rid = Number(row.record_id);
        return `
          <tr>
            <td><strong>#${rid}</strong></td>
            <td>${vehicle}</td>
            <td>${perf}</td>
            <td>${del}</td>
            <td>${reason}</td>
            <td style="max-width: 320px; white-space: normal; font-size: 0.9rem;">${desc}</td>
            <td><button type="button" class="btn-primary btn-sm" onclick="restoreAdminServiceRecord(${rid})">Obnovit</button></td>
          </tr>`;
      })
      .join('');
    container.innerHTML = `
      <table class="tool-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Vozidlo</th>
            <th>Provedeno</th>
            <th>Archivováno</th>
            <th>Důvod</th>
            <th>Popis</th>
            <th>Akce</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>`;
  } catch (error) {
    container.innerHTML = `<div class="error">Chyba: ${escapeHtml(error.message || String(error))}</div>`;
    console.error('loadDeletedServiceRecords', error);
  }
}

async function restoreAdminServiceRecord(recordId) {
  if (!recordId || !confirm(`Obnovit archivovaný servisní záznam #${recordId}?`)) return;
  try {
    const data = await apiRequest('POST', `/admin-api/records/${recordId}/restore`);
    showSuccess(data?.message || 'Záznam byl obnoven');
    await Promise.all([loadRecords(), loadDeletedServiceRecords(), loadOverview()]);
    if (currentSection === 'global-admin') {
      await loadGlobalAdmin();
    }
    await reopenUserDetailIfNeeded();
  } catch (error) {
    console.error('restoreAdminServiceRecord', error);
  }
}

async function loadRecords() {
  const container = document.getElementById('records-cards-container');
  if (!container) return;
  
  container.innerHTML = '<div class="loading">Načítám záznamy...</div>';
  
  try {
    const response = await apiRequest('GET', withQueryParams('/admin-api/records', { limit: 500, offset: 0 }));
    const records = Array.isArray(response) ? response : (response.records || []);
    
    if (records.length === 0) {
      container.innerHTML = '<div class="empty">Žádné záznamy</div>';
      applySectionViewMode('records');
      return;
    }
    
    container.innerHTML = records.map(record => {
      const performedDate = formatDate(record.performed_at, '-');
      const serviceLabel = record.user_name || record.user_email || (record.user_id ? `#${record.user_id}` : '-');
      const vehicleLabel = record.vehicle_nickname
        || `${record.vehicle_brand || ''} ${record.vehicle_model || ''}`.trim()
        || record.vehicle_plate
        || (record.vehicle_id ? `#${record.vehicle_id}` : '-');
      return `
        <div class="card" data-record-id="${record.id}">
          <div class="card-header">
            <h3 class="card-title">📋 ${record.description || 'Bez popisu'}</h3>
            <span class="card-id">#${record.id}</span>
          </div>
          <div class="card-body">
            <div class="card-field">
              <span class="card-label">Servis</span>
              <span class="card-value">${serviceLabel}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Vozidlo</span>
              <span class="card-value">${vehicleLabel}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Datum provedení</span>
              <span class="card-value">${performedDate}</span>
            </div>
            ${record.mileage ? `
            <div class="card-field">
              <span class="card-label">Nájezd</span>
              <span class="card-value">${record.mileage.toLocaleString('cs-CZ')} km</span>
            </div>
            ` : ''}
            ${record.price ? `
            <div class="card-field">
              <span class="card-label">Cena</span>
              <span class="card-value" style="color: #059669; font-weight: 700;">${record.price.toLocaleString('cs-CZ')} Kč</span>
            </div>
            ` : ''}
            ${record.category ? `
            <div class="card-field">
              <span class="card-label">Kategorie</span>
              <span class="card-value">${record.category}</span>
            </div>
            ` : ''}
          </div>
          <div class="card-actions">
            <button class="btn-edit" onclick="editRecord(${record.id})">✏️ Upravit</button>
            <button class="btn-danger" onclick="deleteRecord(${record.id})" title="Soft archivace — lze obnovit">Archivovat</button>
          </div>
        </div>
      `;
    }).join('');
    applySectionViewMode('records');
    
    // Vyhledávání
    const searchInput = document.getElementById('record-search');
    if (searchInput) {
      searchInput.oninput = (e) => {
        const query = e.target.value.toLowerCase();
        const cards = container.querySelectorAll('.card');
        cards.forEach(card => {
          const text = card.textContent.toLowerCase();
          card.style.display = text.includes(query) ? '' : 'none';
        });
      };
    }
    
  } catch (error) {
    container.innerHTML = `<div class="error">Chyba při načítání: ${error.message}</div>`;
  }
}

function buildRecordActorLabel(user) {
  if (!user) return '-';
  const roleLabel = ({
    service: 'servis',
    user: 'uživatel',
    admin: 'admin',
    developer_admin: 'developer admin',
  })[user.role] || user.role || 'uživatel';
  return `${user.name || user.email || `ID ${user.id}`} (${roleLabel})`;
}

function renderRecordServiceSelect(selectedVehicleId = null, selectedUserId = null) {
  const serviceSelect = document.getElementById('record-service-id');
  if (!serviceSelect) return;

  const selectedVehicle = recordFormOptionsState.vehicles.find(
    (vehicle) => Number(vehicle.id) === Number(selectedVehicleId),
  );
  const selectedVehicleTenantId = selectedVehicle?.tenant_id ?? null;

  let users = recordFormOptionsState.users;
  if (selectedVehicleTenantId !== null && selectedVehicleTenantId !== undefined) {
    users = users.filter((user) => Number(user.tenant_id) === Number(selectedVehicleTenantId));
  }

  users = [...users].sort((a, b) => {
    const aRole = String(a.role || '');
    const bRole = String(b.role || '');
    if (aRole === bRole) {
      return String(a.name || a.email || '').localeCompare(String(b.name || b.email || ''));
    }
    if (aRole === 'service') return -1;
    if (bRole === 'service') return 1;
    return aRole.localeCompare(bRole);
  });

  let html = '<option value="">Bez přiřazení</option>';
  if (!selectedVehicleId) {
    html += '<option value="" disabled>Nejprve vyberte vozidlo</option>';
    serviceSelect.innerHTML = html;
    serviceSelect.disabled = true;
    return;
  }

  html += users.map((user) => {
    const label = buildRecordActorLabel(user);
    return `<option value="${user.id}">${escapeHtml(label)}</option>`;
  }).join('');

  // Pokud je u editace historicky přiřazen uživatel mimo tenant, zobrazíme ho explicitně.
  if (
    selectedUserId
    && !users.some((user) => Number(user.id) === Number(selectedUserId))
  ) {
    const foreignUser = recordFormOptionsState.users.find((user) => Number(user.id) === Number(selectedUserId));
    if (foreignUser) {
      html += `<option value="${foreignUser.id}">${escapeHtml(`${buildRecordActorLabel(foreignUser)} (mimo tenant)`)}`
        + '</option>';
    }
  }

  serviceSelect.innerHTML = html;
  serviceSelect.disabled = false;
  if (selectedUserId !== null && selectedUserId !== undefined && String(selectedUserId) !== '') {
    serviceSelect.value = String(selectedUserId);
  } else {
    serviceSelect.value = '';
  }
}

async function loadRecordFormData(selectedVehicleId = null, selectedUserId = null) {
  try {
    const [users, vehicles] = await Promise.all([
      fetchAllList('/admin-api/users'),
      fetchAllList('/admin-api/vehicles'),
    ]);

    recordFormOptionsState.users = Array.isArray(users) ? users : [];
    recordFormOptionsState.vehicles = Array.isArray(vehicles) ? vehicles : [];

    const vehicleSelect = document.getElementById('record-vehicle-id');
    if (vehicleSelect) {
      vehicleSelect.innerHTML = '<option value="">Vyberte vozidlo</option>' +
        recordFormOptionsState.vehicles.map((vehicle) => {
          const label = vehicle.nickname
            || `${vehicle.brand || ''} ${vehicle.model || ''}`.trim()
            || `ID ${vehicle.id}`;
          return `<option value="${vehicle.id}">${escapeHtml(`${label} (${vehicle.user_email || '-'})`)}</option>`;
        }).join('');

      if (selectedVehicleId !== null && selectedVehicleId !== undefined && String(selectedVehicleId) !== '') {
        vehicleSelect.value = String(selectedVehicleId);
      }

      vehicleSelect.onchange = (event) => {
        const vehicleId = parseInt(event.target.value, 10);
        renderRecordServiceSelect(Number.isFinite(vehicleId) ? vehicleId : null, null);
      };
    }

    renderRecordServiceSelect(selectedVehicleId, selectedUserId);
  } catch (error) {
    console.error('Error loading form data:', error);
  }
}

async function showRecordModal(recordId = null) {
  const modal = document.getElementById('record-modal');
  const title = document.getElementById('record-modal-title');

  if (recordId) {
    title.textContent = 'Upravit záznam';
    try {
      const response = await apiRequest('GET', withQueryParams('/admin-api/records', { limit: 500, offset: 0 }));
      const records = Array.isArray(response) ? response : (response.records || []);
      const record = records.find(r => r.id === recordId);
      if (record) {
        await loadRecordFormData(record.vehicle_id, record.user_id);
        document.getElementById('record-id').value = record.id;
        document.getElementById('record-vehicle-id').value = record.vehicle_id || '';
        renderRecordServiceSelect(record.vehicle_id || null, record.user_id || null);
        document.getElementById('record-service-id').value = record.user_id || '';
        document.getElementById('record-description').value = record.description || '';
        
        if (record.performed_at) {
          const date = new Date(record.performed_at);
          const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
          document.getElementById('record-performed-at').value = localDate.toISOString().slice(0, 16);
        }
        
        document.getElementById('record-mileage').value = record.mileage || '';
        document.getElementById('record-price').value = record.price || '';
        document.getElementById('record-category').value = record.category || '';
        document.getElementById('record-note').value = record.note || '';
      }
    } catch (error) {
      showGlobalError('Chyba při načítání záznamu: ' + error.message);
      return;
    }
  } else {
    title.textContent = 'Přidat záznam';
    document.getElementById('record-form').reset();
    document.getElementById('record-id').value = '';
    await loadRecordFormData(null, null);
    
    // Nastavit výchozí datum na teď
    const now = new Date();
    const localNow = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
    document.getElementById('record-performed-at').value = localNow.toISOString().slice(0, 16);
  }
  
  modal.classList.remove('hidden');
}

function closeRecordModal(preserveReturnContext = false) {
  document.getElementById('record-modal').classList.add('hidden');
  document.getElementById('record-form').reset();
  if (!preserveReturnContext) {
    userDetailReturnContext = null;
  }
}

async function saveRecord(event) {
  event.preventDefault();
  
  const recordId = document.getElementById('record-id').value;
  const performedAtStr = document.getElementById('record-performed-at').value;
  const performedAt = performedAtStr ? new Date(performedAtStr) : new Date();
  
  const selectedUserId = parseInt(document.getElementById('record-service-id').value, 10);
  const selectedVehicleId = parseInt(document.getElementById('record-vehicle-id').value, 10);
  if (!Number.isFinite(selectedVehicleId)) {
    showGlobalError('Vyberte prosím vozidlo.');
    return;
  }

  const recordData = {
    user_id: Number.isFinite(selectedUserId) ? selectedUserId : null,
    vehicle_id: selectedVehicleId,
    performed_at: performedAt.toISOString(),
    description: document.getElementById('record-description').value,
    mileage: parseInt(document.getElementById('record-mileage').value) || null,
    price: parseFloat(document.getElementById('record-price').value) || null,
    category: document.getElementById('record-category').value || null,
    note: document.getElementById('record-note').value || null,
  };
  
  try {
    if (recordId) {
      await apiRequest('PATCH', `/admin-api/records/${recordId}`, recordData);
      showSuccess('Údaj byl upraven adminem: servisní záznam');
    } else {
      await apiRequest('POST', '/admin-api/records', recordData);
      showSuccess('Záznam byl vytvořen');
    }
    
    closeRecordModal(true);
    await Promise.all([loadRecords(), loadOverview()]);
    await reopenUserDetailIfNeeded();
  } catch (error) {
    console.error('Error saving record:', error);
  }
}

async function editRecord(recordId) {
  showRecordModal(recordId);
}

async function deleteRecord(recordId) {
  if (!confirm(
    'Archivovat tento servisní záznam? Záznam zmizí z běžného přehledu, ale půjde obnovit v sekci „Archivované servisní záznamy“.',
  )) {
    return;
  }

  try {
    await apiRequest('DELETE', `/admin-api/records/${recordId}`);
    showSuccess('Záznam byl archivován (lze obnovit v sekci Archivované servisní záznamy)');
    await Promise.all([loadRecords(), loadDeletedServiceRecords(), loadOverview()]);
    if (currentSection === 'global-admin') {
      await loadGlobalAdmin();
    }
  } catch (error) {
    console.error('Error deleting record:', error);
  }
}

// ============================================
// AUDIT LOG
// ============================================

async function loadAuditLog() {
  const listEl = document.getElementById('audit-log-list');
  if (!listEl) return;
  
  listEl.innerHTML = '<div class="loading">Načítám audit log...</div>';
  
  try {
    const entityType = document.getElementById('audit-entity-type')?.value || '';
    const action = document.getElementById('audit-action')?.value || '';
    const actor = document.getElementById('audit-actor')?.value || '';
    const entityId = document.getElementById('audit-entity-id')?.value || '';
    const severity = document.getElementById('audit-severity')?.value || '';
    const dateFrom = document.getElementById('audit-date-from')?.value || '';
    const dateTo = document.getElementById('audit-date-to')?.value || '';
    
    const url = withQueryParams('/admin-api/audit', {
      limit: 150,
      entity_type: entityType || null,
      action: action || null,
      actor: actor || null,
      entity_id: entityId || null,
      severity: severity || null,
      date_from: dateFrom ? new Date(dateFrom).toISOString() : null,
      date_to: dateTo ? new Date(dateTo).toISOString() : null,
    });
    
    const auditData = await apiRequest('GET', url);
    const logs = auditData.logs || [];
    const source = String(auditData.source || 'unknown');
    
    if (logs.length === 0) {
      listEl.innerHTML = `<div class="empty">Žádné záznamy v audit logu${source === 'audit_log' ? ' (append-only zdroj)' : ''}</div>`;
      return;
    }
    
    listEl.innerHTML = `
      <div class="audit-log-item" style="background:#f8fafc;">
        <div class="audit-log-content">
          <strong>Zdroj auditu:</strong> ${source === 'audit_log' ? 'append-only audit_log' : source}
        </div>
      </div>
      ${logs.map(log => {
      const timestamp = log.timestamp ? formatDateTime(log.timestamp) : '-';
      const actor = log.actor_email || `Uživatel #${log.actor_user_id || '?'}`;
      const actionText = getActionText(log.action || '');
      const entityType = log.entity_type || '?';
      const entityId = log.entity_id || '';
      const severity = log.severity || 'info';
      
      return `
        <div class="audit-log-item audit-severity-${escapeHtml(severity)}">
          <div class="audit-log-header">
            <span class="audit-log-time">${timestamp}</span>
            <span class="status-pill">${escapeHtml(severity)}</span>
            <span class="audit-log-project">${log.source_project || '?'}</span>
          </div>
          <div class="audit-log-content">
            <strong>${escapeHtml(actor)}</strong> ${escapeHtml(actionText)} <strong>${escapeHtml(entityType)}</strong>
            ${entityId ? `#${escapeHtml(entityId)}` : ''}
          </div>
          ${log.ip ? `<div class="audit-log-details">IP: ${escapeHtml(log.ip)}</div>` : ''}
          ${log.details ? `<div class="audit-log-details">${escapeHtml(log.details)}</div>` : ''}
        </div>
      `;
    }).join('')}`;
    
  } catch (error) {
    listEl.innerHTML = `<div class="error">Chyba při načítání: ${error.message}</div>`;
  }
}

async function exportAuditLogCsv() {
  const entityType = document.getElementById('audit-entity-type')?.value || '';
  const action = document.getElementById('audit-action')?.value || '';
  const actor = document.getElementById('audit-actor')?.value || '';
  const entityId = document.getElementById('audit-entity-id')?.value || '';
  const severity = document.getElementById('audit-severity')?.value || '';
  const dateFrom = document.getElementById('audit-date-from')?.value || '';
  const dateTo = document.getElementById('audit-date-to')?.value || '';
  const url = withQueryParams('/admin-api/audit', {
    limit: 500,
    entity_type: entityType || null,
    action: action || null,
    actor: actor || null,
    entity_id: entityId || null,
    severity: severity || null,
    date_from: dateFrom ? new Date(dateFrom).toISOString() : null,
    date_to: dateTo ? new Date(dateTo).toISOString() : null,
    export: 'csv',
  });
  try {
    const token = getAuthToken();
    const response = await fetch(`${API_BASE}${url}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!response.ok) {
      throw new Error(`Export selhal (${response.status})`);
    }
    const blob = await response.blob();
    const downloadUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = downloadUrl;
    a.download = `admin-audit-log-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(downloadUrl);
  } catch (error) {
    showGlobalError(error.message || String(error));
  }
}

async function loadSupportInbox() {
  const listEl = document.getElementById('support-inbox-list');
  const summaryEl = document.getElementById('support-inbox-summary');
  if (!listEl) return;
  listEl.innerHTML = '<div class="loading">Načítám podporu...</div>';
  try {
    const data = await apiRequest('GET', '/admin-api/support-inbox?limit=150');
    const items = Array.isArray(data.items) ? data.items : [];
    if (summaryEl) {
      const unique = new Set(items.map((item) => item.email).filter(Boolean)).size;
      summaryEl.innerHTML = `
        <span class="global-admin-chip"><span>Požadavky</span><strong>${items.length.toLocaleString('cs-CZ')}</strong></span>
        <span class="global-admin-chip"><span>Unikátní účty</span><strong>${unique.toLocaleString('cs-CZ')}</strong></span>
      `;
    }
    if (!items.length) {
      listEl.innerHTML = '<div class="empty">Zatím žádné požadavky podpory.</div>';
      return;
    }
    listEl.innerHTML = `
      <table class="tool-table">
        <thead><tr><th>Čas</th><th>Uživatel</th><th>Kategorie</th><th>Předmět</th><th>IP</th><th>Akce</th></tr></thead>
        <tbody>
          ${items.map((row) => `
            <tr>
              <td>${escapeHtml(formatDateTime(row.created_at))}</td>
              <td>${escapeHtml(row.email || '-')}</td>
              <td>${escapeHtml(row.category || '-')}</td>
              <td>${escapeHtml(row.subject || '-')}</td>
              <td>${escapeHtml(row.ip_address || '-')}</td>
              <td>${row.customer_id ? `<button class="btn-secondary btn-sm" type="button" onclick="openUserDetail(${Number(row.customer_id)}, 'timeline')">Detail účtu</button>` : '-'}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  } catch (error) {
    listEl.innerHTML = `<div class="error">Chyba při načítání podpory: ${escapeHtml(error.message || String(error))}</div>`;
  }
}

async function loadSecurityPanel() {
  const el = document.getElementById('security-admin-panel');
  if (!el) return;
  el.innerHTML = '<div class="loading">Načítám bezpečnostní stav...</div>';
  try {
    const data = await apiRequest('GET', '/admin-api/security-status');
    const counters = data.counters || {};
    const allowlist = data.allowlist || {};
    const blocks = Array.isArray(data.active_blocks) ? data.active_blocks : [];
    const events = Array.isArray(data.latest_security_events) ? data.latest_security_events : [];
    el.innerHTML = `
      <div class="security-status-grid">
        <article class="security-status-card">
          <span>Aktuální IP admina</span>
          <strong>${escapeHtml(data.current_ip || '-')}</strong>
          <small>Porovnejte s allowlistem před ostrým nasazením.</small>
        </article>
        <article class="security-status-card ${allowlist.configured ? 'is-ok' : 'is-warning'}">
          <span>ADMIN_NETWORK_ALLOWLIST</span>
          <strong>${allowlist.configured ? 'Nastaven' : 'Nenastaven'}</strong>
          <small>${allowlist.configured ? escapeHtml((allowlist.entries || []).join(', ')) : 'Admin není omezený IP allowlistem.'}</small>
        </article>
        <article class="security-status-card">
          <span>Failed login / 24 h</span>
          <strong>${Number(counters.failed_logins_24h || 0).toLocaleString('cs-CZ')}</strong>
          <small>Rate limited: ${Number(counters.rate_limited_24h || 0).toLocaleString('cs-CZ')}</small>
        </article>
        <article class="security-status-card">
          <span>Aktivní blokace IP</span>
          <strong>${Number(counters.blocked_ips_active || 0).toLocaleString('cs-CZ')}</strong>
          <small>Source probes: ${Number(counters.source_probes_24h || 0).toLocaleString('cs-CZ')}</small>
        </article>
      </div>
      <div class="admin-today-grid">
        <article class="admin-work-card">
          <h3>Aktivní blokované IP</h3>
          ${blocks.length ? blocks.map((row) => `
            <div class="admin-work-row"><div><strong>${escapeHtml(row.ip_address || '-')}</strong><span>${escapeHtml(row.reason || '-')} · ${escapeHtml(formatDateTime(row.blocked_at))}</span></div></div>
          `).join('') : '<div class="empty">Žádná aktivní ruční blokace IP.</div>'}
        </article>
        <article class="admin-work-card">
          <h3>Poslední bezpečnostní události</h3>
          ${events.length ? events.slice(0, 20).map((row) => `
            <div class="admin-work-row"><div><strong>${escapeHtml(row.event_type || '-')}</strong><span>${escapeHtml(row.user_email || '-')} · ${escapeHtml(row.ip_address || '-')} · ${escapeHtml(formatDateTime(row.created_at))}</span></div></div>
          `).join('') : '<div class="empty">Žádné bezpečnostní události.</div>'}
        </article>
      </div>
    `;
  } catch (error) {
    el.innerHTML = `<div class="error">Chyba při načítání bezpečnosti: ${escapeHtml(error.message || String(error))}</div>`;
  }
}

// ============================================
// SYSTEM TOOLS
// ============================================

async function runReindex() {
  const resultEl = document.getElementById('reindex-result');
  if (!resultEl) return;
  
  resultEl.innerHTML = '<div class="loading">Probíhá reindexace...</div>';
  
  try {
    const result = await apiRequest('POST', '/admin-api/reindex');
    const results = Array.isArray(result?.results) ? result.results : [];
    resultEl.innerHTML = `
      <div style="color: #28a745;">
        <strong>✓ ${result?.message || 'Reindexace dokončena'}</strong>
        ${results.length > 0 ? `
        <ul style="margin-top: 8px; padding-left: 20px;">
          ${results.map(r => `<li>${r}</li>`).join('')}
        </ul>
        ` : ''}
      </div>
    `;
    loadOverview(); // Aktualizovat statistiky
  } catch (error) {
    resultEl.innerHTML = `<div style="color: #dc3545;">Chyba: ${error.message}</div>`;
  }
}

async function runRepair() {
  const resultEl = document.getElementById('repair-result');
  if (!resultEl) return;
  
  resultEl.innerHTML = '<div class="loading">Probíhá oprava...</div>';
  
  try {
    const result = await apiRequest('POST', '/admin-api/repair');
    const results = Array.isArray(result?.results) ? result.results : [];
    resultEl.innerHTML = `
      <div style="color: #28a745;">
        <strong>✓ ${result?.message || 'Oprava dokončena'}</strong>
        ${results.length > 0 ? `
        <ul style="margin-top: 8px; padding-left: 20px;">
          ${results.map(r => `<li>${r}</li>`).join('')}
        </ul>
        ` : ''}
      </div>
    `;
  } catch (error) {
    resultEl.innerHTML = `<div style="color: #dc3545;">Chyba: ${error.message}</div>`;
  }
}

async function loadDbInfo() {
  const resultEl = document.getElementById('db-info-result');
  if (!resultEl) return;
  
  resultEl.innerHTML = '<div class="loading">Načítám informace...</div>';
  
  try {
    const info = await apiRequest('GET', '/admin-api/db-info');
    resultEl.innerHTML = `
      <div>
        <p><strong>Cesta k databázi:</strong><br>${info.db_path}</p>
        <p><strong>Počet tabulek:</strong> ${info.table_count}</p>
        ${info.total_size_kb ? `<p><strong>Velikost:</strong> ${info.total_size_kb.toFixed(2)} KB</p>` : ''}
        <p><strong>Tabulky:</strong><br>${info.tables.join(', ')}</p>
      </div>
    `;
  } catch (error) {
    resultEl.innerHTML = `<div style="color: #dc3545;">Chyba: ${error.message}</div>`;
  }
}

// ============================================
// SETTINGS
// ============================================

let allSettings = {};
let currentSettingsCategory = 'general';

async function loadSettings() {
  const loadingEl = document.getElementById('settings-loading');
  const errorEl = document.getElementById('settings-error');
  const contentEl = document.getElementById('settings-content');
  
  loadingEl.classList.remove('hidden');
  errorEl.classList.add('hidden');
  contentEl.classList.add('hidden');
  
  try {
    const response = await apiRequest('GET', '/admin-api/settings');
    allSettings = response.settings || {};
    loadSettingsSourcePanel();
    
    // Zobrazit první kategorii
    showSettingsCategory('general');
    
    loadingEl.classList.add('hidden');
    contentEl.classList.remove('hidden');
  } catch (error) {
    loadingEl.classList.add('hidden');
    errorEl.textContent = `Chyba při načítání nastavení: ${error.message}`;
    errorEl.classList.remove('hidden');
    console.error('Error loading settings:', error);
  }
}

async function loadSettingsSourcePanel() {
  const el = document.getElementById('settings-source-panel');
  if (!el) return;
  el.innerHTML = '<div class="loading">Načítám zdroje nastavení...</div>';
  try {
    const data = await apiRequest('GET', '/admin-api/settings/effective');
    const envRows = Array.isArray(data.env) ? data.env : [];
    const restartCount = envRows.filter((row) => row.requires_restart).length;
    el.innerHTML = `
      <div class="settings-source-head">
        <div>
          <strong>Zdroje nastavení</strong>
          <span>Runtime změny se ukládají do ${escapeHtml(data.settings_file || '-')}</span>
        </div>
        <div class="settings-source-badges">
          <span>${envRows.length} env položek</span>
          <span>${restartCount} vyžaduje restart</span>
        </div>
      </div>
      <details>
        <summary>Zobrazit .env / process nastavení</summary>
        <div class="tool-table-wrap">
          <table class="tool-table">
            <thead><tr><th>Klíč</th><th>Hodnota</th><th>Zdroj</th><th>Restart</th><th>Editace</th></tr></thead>
            <tbody>
              ${envRows.map((row) => `
                <tr>
                  <td>${escapeHtml(row.key || '-')}</td>
                  <td>${escapeHtml(String(row.value ?? ''))}</td>
                  <td>${escapeHtml(row.source || '-')}</td>
                  <td>${row.requires_restart ? 'ANO' : 'NE'}</td>
                  <td>${row.editable_in_admin ? 'Admin' : '.env'}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </details>
    `;
  } catch (error) {
    el.innerHTML = `<div class="error">Nepodařilo se načíst zdroje nastavení: ${escapeHtml(error.message || String(error))}</div>`;
  }
}

function showSettingsCategory(category) {
  currentSettingsCategory = category;
  
  // Aktualizovat aktivní tab
  document.querySelectorAll('.settings-tab').forEach(tab => {
    if (tab.dataset.category === category) {
      tab.classList.add('active');
    } else {
      tab.classList.remove('active');
    }
  });
  
  // Zobrazit obsah kategorie
  renderSettingsCategory(category);
}

async function refreshSettingsNotificationsOverview() {
  const body = document.getElementById('settings-notifications-overview-body');
  if (!body) return;
  body.innerHTML = '<div class="setting-description">Načítám přehled…</div>';
  try {
    const data = await apiRequest(
      'GET',
      '/admin-api/settings/system-notifications-overview?limit=40',
      null,
      { silentGlobalError: true },
    );
    const dbItems = Array.isArray(data.database_items) ? data.database_items : [];
    let html = '';

    html += '<div class="settings-notification-section"><strong>Z konfigurace údržby (virtuální řádek)</strong>';
    if (data.runtime_maintenance_active && data.runtime_maintenance_preview) {
      const r = data.runtime_maintenance_preview;
      html += `<div class="settings-notification-runtime-preview">${escapeHtml(String(r.title || ''))} — ${escapeHtml(String(r.message || ''))}</div>`;
    } else {
      html +=
        '<div class="setting-description">Nepublikováno nebo mimo zadané období / prázdný text / vypnuté oznámení.</div>';
    }
    html += '</div>';

    html +=
      '<div class="settings-notification-section" style="margin-top:16px"><strong>Z databáze (broadcast)</strong>';
    html += '<div id="settings-notifications-db-table" class="tool-table-wrap"></div>';
    html += '</div>';

    body.innerHTML = html;

    renderControlCenterTable(
      'settings-notifications-db-table',
      [
        { key: 'id', label: 'ID', render: (row) => escapeHtml(String(row.id)) },
        {
          key: 'is_active',
          label: 'Aktivní',
          render: (row) =>
            row.is_active ? '<span style="color:#15803d">ano</span>' : '<span style="color:#b45309">ne</span>',
        },
        {
          key: 'target',
          label: 'Cílení',
          render: (row) =>
            escapeHtml(`${row.target_type || '-'}${row.target_value ? ':' + row.target_value : ''}`),
        },
        { key: 'title', label: 'Titulek', render: (row) => escapeHtml(row.title || '-') },
        {
          key: 'message',
          label: 'Zpráva',
          render: (row) => escapeHtml(String(row.message || '').slice(0, 140)),
        },
        { key: 'created_at', label: 'Vytvořeno', render: (row) => escapeHtml(formatDateTime(row.created_at)) },
        {
          key: 'created_by_email',
          label: 'Odeslal / zdroj',
          render: (row) => escapeHtml(row.created_by_email || '-'),
        },
        {
          key: '_actions',
          label: 'Akce',
          render: (row) => {
            const id = Number(row.id);
            if (!Number.isFinite(id) || id <= 0) return '-';
            if (!row.is_active) return '<span style="color:#64748b">—</span>';
            return `<button type="button" class="btn-secondary js-sys-notif-off" style="padding:4px 10px;font-size:12px;cursor:pointer" data-sys-notif-id="${id}">Vypnout</button>`;
          },
        },
      ],
      dbItems,
    );
  } catch (error) {
    const msg = error?.message || String(error);
    const hint404 =
      String(msg).includes('Not Found') || String(msg).includes('404')
        ? `<p class="setting-description" style="margin-top:10px">Endpoint přehledu oznámení na serveru chybí – nasaďte aktuální kód aplikace a <strong>restartujte backend</strong>. Ostatní nastavení fungují i bez něj.</p>`
        : '';
    body.innerHTML = `<div class="error">${escapeHtml(msg)}</div>${hint404}`;
  }
}

function renderSettingsCategory(category) {
  const container = document.getElementById('settings-categories');
  const categorySettings = allSettings[category] || {};
  
  const categoryConfigs = {
    general: {
      title: 'Obecná nastavení',
      groups: [
        {
          title: 'Aplikace',
          settings: [
            { key: 'app_name', label: 'Název aplikace', type: 'text', desc: 'Název aplikace' },
            { key: 'app_version', label: 'Verze', type: 'text', desc: 'Verze aplikace' },
            { key: 'app_description', label: 'Popis', type: 'textarea', desc: 'Popis aplikace' }
          ]
        },
        {
          title: 'Údržba a oznámení',
          settings: [
            {
              key: 'maintenance_notice_enabled',
              label: 'Oznámení o údržbě',
              type: 'checkbox',
              desc:
                'Text z admin_settings (stejné ID u všech uživatelů). Jednorázové zprávy s vlastním ID v databázi (např. id 15) se zveřejňují v Developer Control Center → karta Notifications → Odeslat broadcast; v auditu akcí je záznam notifications.broadcast.'
            },
            { key: 'maintenance_notice_title', label: 'Nadpis', type: 'text', desc: 'Nadpis v seznamu (např. Oznámení)' },
            {
              key: 'maintenance_notice_message',
              label: 'Text pro uživatele',
              type: 'textarea',
              desc: 'Např. plánovaná odstávka, žádost o zálohu dat'
            },
            {
              key: 'maintenance_notice_period_start',
              label: 'Zobrazovat od (datum)',
              type: 'date',
              desc: 'Volitelné; prázdné = hned. Formát RRRR-MM-DD'
            },
            {
              key: 'maintenance_notice_period_end',
              label: 'Zobrazovat do (datum)',
              type: 'date',
              desc: 'Volitelné; prázdné = bez konce. Formát RRRR-MM-DD'
            },
            {
              key: 'maintenance_mode',
              label: 'Kompletní blokace aplikace',
              type: 'checkbox',
              desc: 'Všichni uživatelé uvidí chybu 503 (odstávka). Admin panel (admin-api) zůstane dostupný.'
            }
          ]
        }
      ]
    },
    security: {
      title: 'Bezpečnost',
      groups: [
        {
          title: 'Autentizace',
          settings: [
            { key: 'jwt_expiration_hours', label: 'Platnost JWT tokenu (hodiny)', type: 'number', desc: 'Jak dlouho je token platný' },
            { key: 'session_timeout_minutes', label: 'Timeout session (minuty)', type: 'number', desc: 'Automatické odhlášení po nečinnosti' },
            { key: 'max_login_attempts', label: 'Max. pokusů o přihlášení', type: 'number', desc: 'Počet pokusů před zablokováním' }
          ]
        },
        {
          title: 'Hesla',
          settings: [
            { key: 'password_min_length', label: 'Minimální délka hesla', type: 'number', desc: 'Minimální počet znaků' },
            { key: 'password_require_uppercase', label: 'Vyžadovat velká písmena', type: 'checkbox', desc: 'Heslo musí obsahovat velká písmena' },
            { key: 'password_require_numbers', label: 'Vyžadovat čísla', type: 'checkbox', desc: 'Heslo musí obsahovat čísla' }
          ]
        }
      ]
    },
    database: {
      title: 'Databáze',
      groups: [
        {
          title: 'Zálohování',
          settings: [
            { key: 'backup_enabled', label: 'Automatické zálohování', type: 'checkbox', desc: 'Povolit automatické zálohování' },
            { key: 'backup_frequency_hours', label: 'Frekvence zálohování (hodiny)', type: 'number', desc: 'Jak často se má zálohovat' },
            { key: 'backup_retention_days', label: 'Uchování záloh (dny)', type: 'number', desc: 'Kolik dní uchovávat zálohy' },
            { key: 'backup_path', label: 'Cesta k zálohám', type: 'text', desc: 'Složka pro ukládání záloh' }
          ]
        }
      ]
    },
    server: {
      title: 'Server',
      groups: [
        {
          title: 'Síť',
          settings: [
            { key: 'host', label: 'Host', type: 'text', desc: 'IP adresa nebo hostname' },
            { key: 'port', label: 'Port', type: 'number', desc: 'Port serveru' }
          ]
        },
        {
          title: 'CORS',
          settings: [
            { key: 'cors_enabled', label: 'Povolit CORS', type: 'checkbox', desc: 'Povolit Cross-Origin Resource Sharing' },
            { key: 'cors_origins', label: 'Povolené origins', type: 'textarea', desc: 'JSON pole povolených originů' }
          ]
        },
        {
          title: 'Rate Limiting',
          settings: [
            { key: 'rate_limit_enabled', label: 'Povolit rate limiting', type: 'checkbox', desc: 'Omezit počet požadavků' },
            { key: 'rate_limit_per_minute', label: 'Požadavků za minutu', type: 'number', desc: 'Maximální počet požadavků za minutu' }
          ]
        }
      ]
    },
    email: {
      title: 'E-maily',
      groups: [
        {
          title: 'SMTP',
          settings: [
            { key: 'smtp_enabled', label: 'Povolit SMTP', type: 'checkbox', desc: 'Zapnout odesílání e-mailů' },
            { key: 'smtp_host', label: 'SMTP host', type: 'text', desc: 'Adresa SMTP serveru' },
            { key: 'smtp_port', label: 'SMTP port', type: 'number', desc: 'Port SMTP serveru' },
            { key: 'smtp_user', label: 'SMTP uživatel', type: 'text', desc: 'Uživatelské jméno' },
            { key: 'smtp_from', label: 'Odesílatel', type: 'email', desc: 'E-mailová adresa odesílatele' }
          ]
        }
      ]
    },
    logging: {
      title: 'Logování',
      groups: [
        {
          title: 'Konfigurace',
          settings: [
            { key: 'log_level', label: 'Úroveň logování', type: 'select', desc: 'Minimální úroveň logů', options: ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] },
            { key: 'log_file_enabled', label: 'Ukládat do souboru', type: 'checkbox', desc: 'Ukládat logy do souboru' },
            { key: 'log_file_path', label: 'Cesta k logům', type: 'text', desc: 'Složka pro ukládání logů' },
            { key: 'log_rotation_days', label: 'Rotace logů (dny)', type: 'number', desc: 'Po kolika dnech rotovat logy' }
          ]
        }
      ]
    },
    ui: {
      title: 'Vzhled',
      groups: [
        {
          title: 'Téma',
          settings: [
            { key: 'theme', label: 'Téma', type: 'select', desc: 'Vzhled aplikace', options: ['light', 'dark', 'auto'] },
            { key: 'primary_color', label: 'Primární barva', type: 'text', desc: 'Hex kód primární barvy' },
            { key: 'items_per_page', label: 'Položek na stránku', type: 'number', desc: 'Výchozí počet položek v seznamech' }
          ]
        }
      ]
    },
    api: {
      title: 'API',
      groups: [
        {
          title: 'Konfigurace',
          settings: [
            { key: 'api_docs_enabled', label: 'Povolit API dokumentaci', type: 'checkbox', desc: 'Zobrazit Swagger dokumentaci' },
            { key: 'api_rate_limit', label: 'API rate limit', type: 'number', desc: 'Maximální počet API požadavků za minutu' }
          ]
        }
      ]
    },
    comgate: {
      title: 'Comgate',
      groups: [
        {
          title: 'Základní nastavení',
          settings: [
            { key: 'enabled', label: 'Aktivovat Comgate', type: 'checkbox', desc: 'Globálně zapnout platební bránu v aplikaci' },
            { key: 'merchant', label: 'Merchant ID', type: 'text', desc: 'Merchant identifikátor z Comgate portálu' },
            { key: 'secret', label: 'Secret', type: 'text', desc: 'Heslo/secret pro serverovou komunikaci' },
            { key: 'test_mode', label: 'Testovací režim', type: 'checkbox', desc: 'Používat test mód Comgate' },
            { key: 'currency', label: 'Měna', type: 'select', desc: 'Měna plateb', options: ['CZK', 'EUR', 'USD'] },
            { key: 'lang', label: 'Jazyk brány', type: 'select', desc: 'Jazyk platební stránky', options: ['cs', 'en', 'sk', 'de'] },
            { key: 'country', label: 'Země', type: 'text', desc: 'Kód země (např. CZ)' }
          ]
        },
        {
          title: 'Platební režim',
          settings: [
            { key: 'method', label: 'Výchozí metoda', type: 'select', desc: 'ALL/CARD/BANK', options: ['ALL', 'CARD', 'BANK'] },
            { key: 'subscription_method', label: 'Metoda předplatného', type: 'select', desc: 'Pro recurring doporučeno CARD', options: ['CARD', 'ALL'] },
            { key: 'test_one_time_fallback', label: 'Test fallback bez recurring', type: 'checkbox', desc: 'Použít jednorázový fallback při testu' }
          ]
        },
        {
          title: 'Comgate endpointy',
          settings: [
            { key: 'create_url', label: 'Create URL', type: 'text', desc: 'Endpoint pro založení platby' },
            { key: 'status_url', label: 'Status URL', type: 'text', desc: 'Endpoint pro kontrolu statusu' },
            { key: 'recurring_url', label: 'Recurring URL', type: 'text', desc: 'Endpoint pro opakované stržení' }
          ]
        },
        {
          title: 'Ceník (haléře)',
          settings: [
            { key: 'price_basic_monthly_halers', label: 'BASIC měsíčně', type: 'number', desc: 'Např. 9900 = 99 Kč' },
            { key: 'price_basic_yearly_halers', label: 'BASIC ročně', type: 'number', desc: 'Roční cena v haléřích' },
            { key: 'price_premium_monthly_halers', label: 'PREMIUM měsíčně', type: 'number', desc: 'Např. 29900 = 299 Kč' },
            { key: 'price_premium_yearly_halers', label: 'PREMIUM ročně', type: 'number', desc: 'Roční cena v haléřích' }
          ]
        },
        {
          title: 'Předplatné lifecycle',
          settings: [
            { key: 'subscription_grace_days', label: 'Grace period (dny)', type: 'number', desc: 'Počet dní po neúspěšné obnově' },
            { key: 'subscription_notify_days', label: 'Dny upozornění (CSV)', type: 'text', desc: 'Např. 14,7,1' }
          ]
        }
      ]
    },
    system: {
      title: 'Systémové',
      groups: [
        {
          title: 'Desktop aplikace',
          settings: [
            { key: 'autostart_enabled', label: 'Automatický start při bootu', type: 'checkbox', desc: 'Spustit aplikaci při startu PC' },
          ]
        }
      ]
    }
  };
  
  const config = categoryConfigs[category] || { title: category, groups: [] };
  
  let html = `<div class="settings-category active" data-category="${category}">`;
  html += `<h2 style="margin-bottom: 24px; font-size: 24px; color: #1e293b;">${config.title}</h2>`;
  html += `<div class="settings-category-grid">`;
  
  config.groups.forEach(group => {
    html += `<div class="settings-group">`;
    html += `<h4>${group.title}</h4>`;
    
    // Escape HTML pro bezpečnost
    const escapeHtml = (text) => {
      if (text === null || text === undefined) return '';
      const div = document.createElement('div');
      div.textContent = String(text);
      return div.innerHTML;
    };
    
    group.settings.forEach(setting => {
      const settingData = categorySettings[setting.key] || {};
      const value = settingData.value !== undefined ? settingData.value : '';
      const desc = settingData.description || setting.desc;
      
      html += `<div class="setting-item">`;
      html += `<label for="setting-${escapeHtml(category)}-${escapeHtml(setting.key)}">${escapeHtml(setting.label)}</label>`;
      if (desc) {
        html += `<div class="setting-description">${escapeHtml(desc)}</div>`;
      }
      
      if (setting.type === 'checkbox') {
        const checked = value === true || value === 'true' || value === 1 || value === '1';
        const idAttr = `setting-${escapeHtml(category)}-${escapeHtml(setting.key)}`;
        html += `<div class="checkbox-wrapper">`;
        html += `<input type="checkbox" id="${idAttr}" data-category="${escapeHtml(category)}" data-key="${escapeHtml(setting.key)}" ${checked ? 'checked' : ''}>`;
        html += `<label for="${idAttr}" style="margin: 0;">${checked ? 'Zapnuto' : 'Vypnuto'}</label>`;
        html += `</div>`;
      } else if (setting.type === 'select') {
        const idAttr = `setting-${escapeHtml(category)}-${escapeHtml(setting.key)}`;
        html += `<select id="${idAttr}" data-category="${escapeHtml(category)}" data-key="${escapeHtml(setting.key)}">`;
        setting.options.forEach(opt => {
          const selected = value === opt ? 'selected' : '';
          html += `<option value="${escapeHtml(opt)}" ${selected}>${escapeHtml(opt)}</option>`;
        });
        html += `</select>`;
      } else if (setting.type === 'date') {
        const idAttr = `setting-${escapeHtml(category)}-${escapeHtml(setting.key)}`;
        const dateVal = String(value || '').slice(0, 10);
        html += `<input type="date" id="${idAttr}" data-category="${escapeHtml(category)}" data-key="${escapeHtml(setting.key)}" value="${escapeHtml(dateVal)}">`;
      } else if (setting.type === 'textarea') {
        const idAttr = `setting-${escapeHtml(category)}-${escapeHtml(setting.key)}`;
        html += `<textarea id="${idAttr}" data-category="${escapeHtml(category)}" data-key="${escapeHtml(setting.key)}" rows="3">${escapeHtml(String(value))}</textarea>`;
      } else {
        const inputType = setting.type === 'email' ? 'email' : setting.type === 'number' ? 'number' : 'text';
        const idAttr = `setting-${escapeHtml(category)}-${escapeHtml(setting.key)}`;
        html += `<input type="${inputType}" id="${idAttr}" data-category="${escapeHtml(category)}" data-key="${escapeHtml(setting.key)}" value="${escapeHtml(String(value))}">`;
      }
      
      html += `</div>`;
    });
    
    html += `</div>`;
  });

  if (category === 'general') {
    html += `<div class="settings-group settings-notifications-overview">`;
    html += `<h4>Přehled oznámení v aplikaci</h4>`;
    html +=
      `<div class="setting-description">Záznamy v databázi: ruční broadcast (Developer Control Center; v sloupci „Odeslal“ je e-mail vývojáře), automatické z aplikace (<strong>SPRÁVA VOZIDEL</strong>) nebo virtuální řádek údržby z konfigurace výše. U řádků s kladným ID použijte <strong>Vypnout</strong>. Nový broadcast jen <strong>developer_admin</strong> → Control Center → Notifications.</div>`;
    html += `<div id="settings-notifications-overview-body" class="settings-notifications-overview-body"></div>`;
    html +=
      `<button type="button" class="btn-secondary settings-notifications-refresh-btn" style="margin-top:12px">Obnovit přehled</button>`;
    html += `</div>`;
  }

  html += `</div></div>`;

  container.innerHTML = html;

  container.querySelector('.settings-notifications-refresh-btn')?.addEventListener('click', () => {
    void refreshSettingsNotificationsOverview();
  });

  // Přidat event listenery pro checkboxy
  container.querySelectorAll('input[type="checkbox"]').forEach(cb => {
    cb.addEventListener('change', function () {
      const label = this.nextElementSibling;
      label.textContent = this.checked ? 'Zapnuto' : 'Vypnuto';
    });
  });

  if (category === 'general') {
    void refreshSettingsNotificationsOverview();
  }
}

async function saveAllSettings() {
  try {
    const settingsToSave = [];
    
    // Projít všechny inputy, selecty a textarey
    document.querySelectorAll('[data-category][data-key]').forEach(el => {
      const category = el.dataset.category;
      const key = el.dataset.key;
      let value = el.value;
      
      if (el.type === 'checkbox') {
        value = el.checked;
      } else if (el.type === 'number') {
        value = parseFloat(value) || 0;
      }
      
      // Zjistit typ hodnoty
      const settingData = allSettings[category]?.[key] || {};
      let valueType = settingData.value_type || 'string';
      
      if (typeof value === 'boolean') {
        valueType = 'boolean';
      } else if (typeof value === 'number') {
        valueType = 'number';
      } else if (el.tagName === 'TEXTAREA' && (key.includes('origins') || key.includes('json'))) {
        valueType = 'json';
      }
      
      settingsToSave.push({
        category,
        key,
        value,
        value_type: valueType,
        description: settingData.description || null
      });
    });
    
    await apiRequest('PUT', '/admin-api/settings', { settings: settingsToSave });
    showSuccess('Nastavení byla úspěšně uložena');
    
    // Znovu načíst nastavení
    await loadSettings();
  } catch (error) {
    showGlobalError(`Chyba při ukládání nastavení: ${error.message}`);
  }
}

function resetSettingsCategory() {
  if (confirm('Opravdu chcete obnovit všechna nastavení v této kategorii na výchozí hodnoty?')) {
    showSettingsCategory(currentSettingsCategory);
  }
}

async function initDefaultSettings() {
  if (!confirm('Tato akce vytvoří výchozí nastavení aplikace. Pokračovat?')) {
    return;
  }
  
  try {
    await apiRequest('POST', '/admin-api/settings/init-defaults');
    showSuccess('Výchozí nastavení byla úspěšně vytvořena');
    await loadSettings();
  } catch (error) {
    showGlobalError(`Chyba při inicializaci nastavení: ${error.message}`);
  }
}

// ============================================
// DEVELOPER CONTROL CENTER
// ============================================

const CONTROL_CENTER_TECHNICAL_RESULT_IDS = {
  'cc-health-result': 'cc-health-technical',
  'cc-payments-result': 'cc-payments-technical',
  'cc-presence-result': 'cc-presence-technical',
  'cc-security-result': 'cc-security-technical',
  'cc-backup-result': 'cc-backup-technical',
  'cc-infra-result': 'cc-infra-technical',
  'cc-ops-result': 'cc-ops-technical',
  'cc-logs-result': 'cc-logs-technical',
  'cc-notifications-result': 'cc-notifications-technical',
};

const CONTROL_CENTER_RAW_RESULT_IDS = new Set(['cc-insight-result', 'cc-command-result']);

function setControlCenterState(key, value) {
  controlCenterDataState[key] = value;
  controlCenterDataState.lastUpdatedAt = new Date().toISOString();
  renderControlCenterDashboard();
}

function setControlCenterText(id, value) {
  const el = document.getElementById(id);
  if (el) {
    el.textContent = String(value ?? '-');
  }
}

function setControlCenterKpi(id, value, tone = '') {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = String(value ?? '-');
  el.classList.remove('is-ok', 'is-warn', 'is-alert');
  if (tone) {
    el.classList.add(`is-${tone}`);
  }
}

function setControlCenterStatusChip(id, tone, text) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.remove('is-ok', 'is-warn', 'is-alert');
  if (tone) {
    el.classList.add(`is-${tone}`);
  }
  el.textContent = text;
}

function setControlCenterHealthChip(id, label, status) {
  const el = document.getElementById(id);
  if (!el) return;
  const normalized = String(status || 'unknown').toLowerCase();
  el.classList.remove('is-ok', 'is-warn', 'is-alert');
  if (normalized === 'ok') {
    el.classList.add('is-ok');
  } else if (normalized === 'warning') {
    el.classList.add('is-warn');
  } else if (normalized === 'error') {
    el.classList.add('is-alert');
  }
  el.textContent = `${label}: ${String(status || '-').toUpperCase()}`;
}

function parseIsoDate(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function isDateOlderThan(value, hours) {
  const date = parseIsoDate(value);
  if (!date) return true;
  return (Date.now() - date.getTime()) > (hours * 3600 * 1000);
}

function formatNumber(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return '0';
  return num.toLocaleString('cs-CZ');
}

function formatHalersToCzk(value) {
  const halers = Number(value);
  if (!Number.isFinite(halers)) return '-';
  const czk = halers / 100;
  return `${czk.toLocaleString('cs-CZ', { minimumFractionDigits: 0, maximumFractionDigits: 2 })} Kč`;
}

function formatShortDateTime(value) {
  return formatDateTime(value, '-');
}

function normalizeLicenseStatus(value) {
  return String(value || 'active').trim().toLowerCase();
}

function isPaidLicenseUser(user) {
  const plan = getLicensePlanBase(user?.license_plan || 'free');
  const status = normalizeLicenseStatus(user?.license_status);
  const hasPaid = Boolean(user?.has_paid);
  if (['expired', 'inactive', 'suspended'].includes(status)) {
    return false;
  }
  return hasPaid || plan !== 'free';
}

function isUnpaidProblemUser(user) {
  const plan = getLicensePlanBase(user?.license_plan || 'free');
  const status = normalizeLicenseStatus(user?.license_status);
  if (['expired', 'inactive', 'suspended'].includes(status)) {
    return true;
  }
  return plan !== 'free' && !Boolean(user?.has_paid);
}

function normalizePaymentEnvironment(item) {
  const explicit = String(item?.payment_environment || '').trim().toUpperCase();
  if (explicit === 'LIVE' || explicit === 'TEST') {
    return explicit;
  }
  const status = String(item?.provider_status || '').trim().toLowerCase();
  const eventType = String(item?.event_type || '').trim().toLowerCase();
  if (status.includes('test') || status.includes('sandbox') || eventType.includes('test') || eventType.includes('sandbox')) {
    return 'TEST';
  }
  return 'LIVE';
}

function isPaymentSuccessful(item) {
  const status = String(item?.provider_status || '').trim().toUpperCase();
  const eventType = String(item?.event_type || '').trim().toLowerCase();
  return status === 'PAID' || status === 'CONFIRMED'
    || eventType === 'payment_paid'
    || eventType === 'payment_confirmed'
    || eventType === 'subscription_renewal_paid'
    || eventType === 'paid_confirmed'
    || eventType === 'renewal_paid';
}

function isPaymentFailed(item) {
  const status = String(item?.provider_status || '').trim().toLowerCase();
  const eventType = String(item?.event_type || '').trim().toLowerCase();
  return status.includes('fail')
    || status.includes('error')
    || status.includes('declin')
    || status.includes('cancel')
    || status.includes('denied')
    || status.includes('timeout')
    || eventType.includes('fail')
    || eventType.includes('error')
    || eventType.includes('cancel')
    || eventType.includes('declin');
}

function isPaymentNeedsAttention(item) {
  const status = String(item?.provider_status || '').trim().toLowerCase();
  const refunded = String(item?.refund_status || '').trim().toLowerCase() === 'refunded';
  return refunded || isPaymentFailed(item) || status.includes('pending') || status.includes('created');
}

function isRecentlyActive(value, minutes = 15) {
  const date = parseIsoDate(value);
  if (!date) return false;
  return (Date.now() - date.getTime()) <= (minutes * 60 * 1000);
}

function buildControlCenterHealthDetail(component = {}) {
  if (component.error) return String(component.error);
  if (Array.isArray(component.hardening_hints)) {
    if (component.hardening_hints.length > 0) {
      return component.hardening_hints.map((h) => escapeHtml(h)).join(' · ');
    }
    return 'Doporučený bezpečnostní obvod: v pořádku.';
  }
  if (Object.prototype.hasOwnProperty.call(component, 'merchant_configured')) {
    return component.merchant_configured ? 'Merchant configured' : 'Merchant missing';
  }
  if (Object.prototype.hasOwnProperty.call(component, 'smtp_host_configured')) {
    return component.smtp_host_configured ? 'SMTP configured' : 'SMTP missing';
  }
  if (Object.prototype.hasOwnProperty.call(component, 'recent_api_activity_15m')) {
    return `Events 15m: ${formatNumber(component.recent_api_activity_15m)}`;
  }
  if (Object.prototype.hasOwnProperty.call(component, 'recent_events_tail_count')) {
    if (component.log_file_exists === false) {
      return 'Licenční webhook: soubor logu ještě není (žádný webhook od hubu neproběhl).';
    }
    const n = formatNumber(component.recent_events_tail_count);
    return n === '0'
      ? 'Licenční webhook: log existuje, v záběru posledních řádků nic (nebo prázdný soubor).'
      : `Licenční webhook log (náhled řádků): ${n}`;
  }
  if (Object.prototype.hasOwnProperty.call(component, 'license_worker_paused')) {
    const paused = component.license_worker_paused || component.reminders_worker_paused;
    return paused ? 'Některé workers jsou pozastavené' : 'Workers aktivní';
  }
  return 'OK';
}

function renderControlCenterStatusLabel(status) {
  const normalized = String(status || 'unknown').toLowerCase();
  let klass = 'status-pill';
  if (normalized === 'ok') klass += ' status-ok';
  else if (normalized === 'warning') klass += ' status-warn';
  else if (normalized === 'error') klass += ' status-bad';
  return `<span class="${klass}">${escapeHtml(String(status || '-').toUpperCase())}</span>`;
}

/** Postup + cílová čára po kliknutí „Otevřít“ u priorit Control Center. */
const CONTROL_CENTER_PLAYBOOKS = {
  'health-alert': {
    tone: 'alert',
    title: 'Vyřešte chybu v System Health',
    steps: [
      'V modulu System Health dole klikněte „Načíst health“, pokud tabulka v detailu chybí.',
      'V tabulce najděte komponentu se stavem ERROR a přečtěte sloupec Poznámka.',
      'Typicky jde o databázi (připojení, disk) nebo nedostupnou službu — ověřte log aplikace na serveru.',
      'Po opravě nahoře klikněte „Obnovit panel“ a zkontrolujte, že červená priorita zmizela.',
    ],
    done: 'Hotovo: v health detailu jsou všechny komponenty OK a v „Co řešit teď“ už není kritická položka System Health.',
    afterOpen: () => loadControlCenterHealth(),
  },
  'health-warn': {
    tone: 'warn',
    title: 'Dokončete kontrolu varování (System Health)',
    steps: [
      'Modul System Health je otevřený — v detailu ověřte řádky se stavem WARNING.',
      'Řádek „security_hardening“ shrnuje doporučený produkční obvod (HTTPS, CORS, admin allowlist) — postupujte podle nápovědy ve sloupci Poznámka.',
      'Podle poznámky zkontrolujte SMTP, platby (Comgate) nebo workers; část položek může být jen informativní.',
      'V případě workerů otevřete také sekci Jobs a ověřte, že nejsou zbytečně pozastavené joby.',
      'Po úpravách konfigurace dejte „Obnovit panel“.',
    ],
    done: 'Hotovo: po obnovení přehledu zmizí žlutá priorita System Health, nebo jsou všechny komponenty OK.',
    afterOpen: () => loadControlCenterHealth(),
  },
  'payments-failed': {
    tone: 'warn',
    title: 'Vyřešte neúspěšné platby',
    steps: [
      'V sekci Licenses & Payments klikněte „Načíst platby“.',
      'V detailu plateb najděte LIVE transakce ve stavu failed nebo vyžadující pozornost.',
      'Ověřte u zákazníka platbu, limity, případně po opravě na bráně použijte „Spustit resync“.',
    ],
    done: 'Hotovo: neúspěšné LIVE platby jsou vyřešeny (0 v metrikách) nebo evidovaně refundovány.',
    afterOpen: () => loadControlCenterPayments(),
  },
  'security-alerts': {
    tone: 'alert',
    title: 'Projděte security alerty',
    steps: [
      'Otevřel se Security monitor — data se doplní automaticky; případně klikněte „Načíst monitor“.',
      'Zkontrolujte tabulku zdrojových pokusů podle IP a řádkové bezpečnostní události.',
      'U opakovaných neúspěšných přihlášení z jedné IP ji opište do pole „IP adresa“ a klikněte „Blokovat IP“.',
      'Automatické skeny (.env, config) aplikace už blokuje — u reverse proxy ověřte předávání skutečné IP (X-Forwarded-For).',
      'Produkční tvrdší obvod: v .env nastavte ENFORCE_HTTPS=1, explicitní ALLOWED_ORIGINS a volitelně ADMIN_NETWORK_ALLOWLIST (VPN/office IP) — popis v .env.example a ukázkový Nginx v deploy/.',
    ],
    done: 'Hotovo zásahu: rizika posouzena, případně IP zablokovány. Číslo v banneru klesne na 0 až po uběhnutí 24 h od zdrojových pokusů nebo po odeznění ostatních složek součtu.',
    afterOpen: () => loadControlCenterSecurityMonitor(),
    focusSelector: '#cc-block-ip',
  },
  'licenses-expired': {
    tone: 'warn',
    title: 'Expirované licence',
    steps: [
      'V modulu Users zadejte User ID a klikněte „Načíst insight“ (nebo postupně projděte uživatele).',
      'Ověřte stav licence a domluvte obnovu / platbu.',
      'Po změně v licenčním hubu nebo ruční úpravě stiskněte „Obnovit panel“.',
    ],
    done: 'Hotovo: počet expirovaných licencí v metrikách je 0, nebo máte uživatele ošetřené mimo panel.',
    afterOpen: () => loadControlCenterUsersSnapshot(),
    focusSelector: '#cc-insight-user-id',
  },
  'backup-alert': {
    tone: 'alert',
    title: 'Záloha není dostupná nebo je neplatná',
    steps: [
      'V sekci Backup & Restore klikněte „Vytvořit backup“ a počkejte na dokončení.',
      'Poté „Načíst seznam“ a ověřte první řádek (čas, velikost, že DB existuje).',
      'Na serveru zkontrolujte místo na disku a oprávnění zápisu do složky záloh.',
    ],
    done: 'Hotovo: nejnovější snapshot má vehicles.db (db_exists), KPI nahoře ukáže OK a červená priorita zmizí po obnovení přehledu.',
    afterOpen: () => loadControlCenterBackups(),
  },
  'backup-stale': {
    tone: 'warn',
    title: 'Záloha je starší než doporučené okno',
    steps: [
      'V sekci Backup klikněte „Vytvořit backup“ nebo spusťte plánovanou zálohu na serveru.',
      'Po dokončení „Načíst seznam“ a ověřte datum posledního snapshotu.',
    ],
    done: 'Hotovo: nový backup je mladší než 72 h, v něm existuje vehicles.db a horní KPI ukáže OK — priorita zálohy zmizí po „Obnovit panel“ nebo automaticky po načtení seznamu.',
    afterOpen: () => loadControlCenterBackups(),
  },
  'jobs-paused': {
    tone: 'warn',
    title: 'Pozastavené joby',
    steps: [
      'V sekci Jobs / Operations načtěte stav jobů.',
      'Najděte joby ve stavu paused — pokud je chyba vyřešena, použijte Resume.',
      'Proč byl job pozastaven ověřte v logách nebo v předchozích chybách integrace.',
    ],
    done: 'Hotovo: kritické joby běží a priorita o pozastavených po obnovení zmizí.',
    afterOpen: () => loadControlCenterJobs(),
  },
};

function renderControlCenterActivePlaybook(spec) {
  const el = document.getElementById('cc-active-playbook');
  if (!el) return;
  if (!spec || !spec.title) {
    el.hidden = true;
    el.innerHTML = '';
    return;
  }
  const tone = spec.tone === 'alert' ? 'alert' : (spec.tone === 'ok' ? 'ok' : 'warn');
  const steps = Array.isArray(spec.steps) ? spec.steps : [];
  el.hidden = false;
  el.innerHTML = `
    <div class="cc-playbook-inner is-${tone}">
      <div class="cc-playbook-head">
        <h3 class="cc-playbook-title">${escapeHtml(spec.title)}</h3>
        <button type="button" class="btn-secondary cc-playbook-dismiss" onclick="dismissControlCenterPlaybook()">Skrýt postup</button>
      </div>
      <ol class="cc-playbook-steps">
        ${steps.map((s) => `<li>${escapeHtml(s)}</li>`).join('')}
      </ol>
      <p class="cc-playbook-done"><strong>Cílová čára:</strong> ${escapeHtml(spec.done || '')}</p>
    </div>
  `;
  el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function dismissControlCenterPlaybook() {
  const el = document.getElementById('cc-active-playbook');
  if (!el) return;
  el.hidden = true;
  el.innerHTML = '';
}

function focusControlCenterPriorityWithPlaybook(moduleId, detailsId, playbookKey) {
  const spec = CONTROL_CENTER_PLAYBOOKS[playbookKey];
  renderControlCenterActivePlaybook(spec || null);
  focusControlCenterModule(moduleId, detailsId || '');
  if (!spec) return;
  const finishFocus = () => {
    if (spec.focusSelector) {
      const input = document.querySelector(spec.focusSelector);
      if (input && typeof input.focus === 'function') {
        input.focus({ preventScroll: false });
      }
    }
  };
  if (typeof spec.afterOpen === 'function') {
    Promise.resolve(spec.afterOpen()).finally(() => {
      requestAnimationFrame(finishFocus);
    });
  } else {
    requestAnimationFrame(finishFocus);
  }
}

function renderControlCenterPriorities(metrics) {
  const listEl = document.getElementById('cc-priority-list');
  if (!listEl) return;

  const priorities = [];
  if (metrics.healthTone === 'alert') {
    priorities.push({
      tone: 'alert',
      text: 'System health hlásí chybu. Zkontrolujte komponenty.',
      moduleId: 'cc-module-health',
      detailsId: 'cc-health-details',
      playbookKey: 'health-alert',
    });
  } else if (metrics.healthTone === 'warn') {
    priorities.push({
      tone: 'warn',
      text: 'System health má varování. Ověřte konfiguraci a workers.',
      moduleId: 'cc-module-health',
      detailsId: 'cc-health-details',
      playbookKey: 'health-warn',
    });
  }

  if (metrics.failedPayments > 0) {
    priorities.push({
      tone: metrics.failedPayments >= 5 ? 'alert' : 'warn',
      text: `Neúspěšné platby: ${formatNumber(metrics.failedPayments)}.`,
      moduleId: 'cc-module-payments',
      detailsId: 'cc-payments-details',
      playbookKey: 'payments-failed',
    });
  }

  if (metrics.securityAlerts > 0) {
    const p = metrics.securityAlertParts || {};
    const sub = [];
    if (Number(p.bruteForceAlertIps || 0) > 0) {
      sub.push(`IP s ≥5 neúspěšnými loginy (24h): ${formatNumber(p.bruteForceAlertIps)}`);
    }
    if (Number(p.blockedActive || 0) > 0) {
      sub.push(`aktivních blokací IP: ${formatNumber(p.blockedActive)}`);
    }
    if (Number(p.sourceProbes24h || 0) > 0) {
      sub.push(`blokovaných zdrojových pokusů (24h): ${formatNumber(p.sourceProbes24h)}`);
    }
    const suffix = sub.length ? ` — ${sub.join('; ')}` : '';
    priorities.push({
      tone: 'alert',
      text: `Security alerty: ${formatNumber(metrics.securityAlerts)} (součet výše)${suffix}. Otevřete detail pro konkrétní IP, účty a lokality.`,
      moduleId: 'cc-module-security',
      detailsId: 'cc-security-details',
      playbookKey: 'security-alerts',
    });
  }

  if (metrics.expiredLicenses > 0) {
    priorities.push({
      tone: 'warn',
      text: `Expirované licence: ${formatNumber(metrics.expiredLicenses)}.`,
      moduleId: 'cc-module-users',
      detailsId: 'cc-users-details',
      playbookKey: 'licenses-expired',
    });
  }

  if (metrics.backupTone !== 'ok') {
    priorities.push({
      tone: metrics.backupTone === 'alert' ? 'alert' : 'warn',
      text: metrics.backupTone === 'alert'
        ? 'Backup není dostupný nebo je nevalidní.'
        : 'Backup je starší než doporučené okno.',
      moduleId: 'cc-module-backups',
      detailsId: 'cc-backups-details',
      playbookKey: metrics.backupTone === 'alert' ? 'backup-alert' : 'backup-stale',
    });
  }

  if (metrics.pausedJobs > 0) {
    priorities.push({
      tone: 'warn',
      text: `Pozastavené joby: ${formatNumber(metrics.pausedJobs)}.`,
      moduleId: 'cc-module-jobs',
      detailsId: 'cc-jobs-details',
      playbookKey: 'jobs-paused',
    });
  }

  if (priorities.length === 0) {
    priorities.push({
      tone: 'ok',
      text: 'Žádné kritické problémy. Sledujte moduly pro průběžný dohled.',
    });
  }

  listEl.innerHTML = priorities.map((item) => {
    const openHandler = item.moduleId && item.playbookKey
      ? `focusControlCenterPriorityWithPlaybook('${item.moduleId}', '${item.detailsId || ''}', '${item.playbookKey}')`
      : (item.moduleId ? `focusControlCenterModule('${item.moduleId}', '${item.detailsId || ''}')` : '');
    return `
    <li class="cc-priority-item is-${item.tone}">
      <span class="cc-priority-text">${escapeHtml(item.text)}</span>
      ${openHandler ? `<button class="cc-priority-action" type="button" onclick="${openHandler}">Otevřít postup</button>` : ''}
    </li>
  `;
  }).join('');
}

function renderControlCenterDashboard() {
  const users = Array.isArray(controlCenterDataState.users) ? controlCenterDataState.users : [];
  const presenceItems = Array.isArray(controlCenterDataState?.presence?.items) ? controlCenterDataState.presence.items : [];
  const paymentItems = Array.isArray(controlCenterDataState?.payments?.items) ? controlCenterDataState.payments.items : [];
  const security = controlCenterDataState.security || {};
  const securitySummary = security.summary || {};
  const topFailedIps = Array.isArray(security.top_failed_ips) ? security.top_failed_ips : [];
  const latestSecurityEvents = Array.isArray(security.latest_events) ? security.latest_events : [];
  const backupItems = Array.isArray(controlCenterDataState?.backups?.items) ? controlCenterDataState.backups.items : [];
  const jobs = Array.isArray(controlCenterDataState?.jobs?.jobs) ? controlCenterDataState.jobs.jobs : [];
  const emailSummary = controlCenterDataState?.email?.summary || {};
  const notifications = Array.isArray(controlCenterDataState?.notifications?.items) ? controlCenterDataState.notifications.items : [];
  const subscriptionsCapability = systemCapabilities.subscriptions || null;
  const notificationsCapability = systemCapabilities.system_notifications || null;
  const adminAuditCapability = systemCapabilities.admin_audit || null;
  const auditItems = Array.isArray(controlCenterDataState?.audit?.items) ? controlCenterDataState.audit.items : [];
  const apiItems = Array.isArray(controlCenterDataState?.apiMonitor?.items) ? controlCenterDataState.apiMonitor.items : [];
  const storagePayload = controlCenterDataState.storage || {};
  const webhookPayload = controlCenterDataState.webhookMonitor || {};
  const health = controlCenterDataState.health || {};
  const healthComponents = health.components || {};

  const onlineUsers = presenceItems.filter((item) => String(item.online_status || '').toUpperCase() === 'ONLINE').length;
  const offlineUsers = Math.max(0, presenceItems.length - onlineUsers);
  const recentlyActive = presenceItems.filter((item) => isRecentlyActive(item.last_seen_at, 30)).length;
  const suspiciousPresence = presenceItems.filter((item) => {
    const sessions = Number(item.active_session_count || 0);
    const online = String(item.online_status || '').toUpperCase() === 'ONLINE';
    return sessions >= 4 || (!online && sessions > 0 && isRecentlyActive(item.last_seen_at, 5));
  }).length;

  const paidLicenses = users.filter((user) => isPaidLicenseUser(user)).length;
  const expiredLicenses = users.filter((user) => normalizeLicenseStatus(user?.license_status) === 'expired').length;
  const disabledUsers = users.filter((user) => Boolean(user?.is_disabled)).length;
  const unpaidUsers = users.filter((user) => isUnpaidProblemUser(user)).length;

  const livePaymentItems = paymentItems.filter((item) => normalizePaymentEnvironment(item) === 'LIVE');
  const testPaymentItems = paymentItems.filter((item) => normalizePaymentEnvironment(item) === 'TEST');
  const livePaidCount = livePaymentItems.filter((item) => isPaymentSuccessful(item)).length;
  const testPaidCount = testPaymentItems.filter((item) => isPaymentSuccessful(item)).length;
  const paidTodayHalers = livePaymentItems
    .filter((item) => isPaymentSuccessful(item))
    .filter((item) => {
      const created = parseIsoDate(item.created_at);
      if (!created) return false;
      const now = new Date();
      return created.getFullYear() === now.getFullYear()
        && created.getMonth() === now.getMonth()
        && created.getDate() === now.getDate();
    })
    .reduce((acc, item) => acc + Number(item.amount_halers || 0), 0);
  const latestLivePaymentAt = livePaymentItems
    .filter((item) => isPaymentSuccessful(item))
    .map((item) => parseIsoDate(item.created_at))
    .filter(Boolean)
    .sort((a, b) => b.getTime() - a.getTime())[0] || null;
  const failedPayments = livePaymentItems.filter((item) => isPaymentFailed(item)).length;
  const refundedPayments = livePaymentItems.filter((item) => String(item.refund_status || '').toLowerCase() === 'refunded').length;
  const paymentsAttention = livePaymentItems.filter((item) => isPaymentNeedsAttention(item)).length;

  const blockedActive = Number(securitySummary.blocked_ips_active || 0);
  const bruteForceAlertsFromTop = topFailedIps.filter((item) => Number(item.failed_count || 0) >= 5).length;
  const bruteForceAlerts = Number.isFinite(Number(securitySummary.brute_force_alert_ips))
    ? Number(securitySummary.brute_force_alert_ips)
    : bruteForceAlertsFromTop;
  const rateLimited24h = Number(securitySummary.rate_limited_24h || 0);
  const sourceProbes24h = Number(securitySummary.source_probes_24h || 0);
  const suspiciousAuthEvents = latestSecurityEvents
    .filter((item) => {
      const type = String(item.event_type || '').toLowerCase();
      return type.includes('login_failed') || type.includes('rate_limited') || type.includes('source_probe');
    })
    .length;
  const securityAlertsFallback = bruteForceAlerts + blockedActive + sourceProbes24h;
  const rawAlertTotal = securitySummary.control_center_alert_total;
  const securityAlerts = (rawAlertTotal != null && Number.isFinite(Number(rawAlertTotal)))
    ? Number(rawAlertTotal)
    : securityAlertsFallback;

  const backupsByRecency = [...backupItems].sort((a, b) => {
    const ta = parseIsoDate(a?.created_at)?.getTime() ?? 0;
    const tb = parseIsoDate(b?.created_at)?.getTime() ?? 0;
    return tb - ta;
  });
  const latestBackup = backupsByRecency.find((row) => row && row.db_exists) || backupsByRecency[0] || null;
  const latestBackupTime = latestBackup?.created_at || null;
  const backupCount = backupItems.length;
  const backupHealthy = Boolean(latestBackup && latestBackup.db_exists);
  const backupStale = latestBackup ? isDateOlderThan(latestBackup.created_at, 72) : true;

  const runningJobs = jobs.filter((job) => String(job.state || '').toLowerCase() === 'running').length;
  const pausedJobs = jobs.filter((job) => String(job.state || '').toLowerCase() === 'paused').length;
  const emailSent24h = Number(emailSummary.sent_24h || 0);
  const emailFailed24h = Number(emailSummary.failed_24h || 0);

  const activeNotifications = notifications.filter((item) => Boolean(item.is_active)).length;
  const lastCriticalAudit = auditItems.find((item) => {
    const result = String(item.result || '').toLowerCase();
    const code = Number(item.status_code || 0);
    return result === 'failed' || result === 'partial' || code >= 400;
  });

  const apiTop = apiItems[0] || null;
  const webhookFailed = Number(webhookPayload.failed_count || 0);
  const dbBytes = Number(storagePayload?.database?.size_bytes || 0);
  const dirs = storagePayload?.directories || {};
  const storageTotalBytes = dbBytes
    + Number(dirs?.data?.total_bytes || 0)
    + Number(dirs?.logs?.total_bytes || 0)
    + Number(dirs?.backups?.total_bytes || 0);

  let healthTone = 'ok';
  const healthStatuses = Object.values(healthComponents)
    .map((item) => String(item?.status || '').toLowerCase())
    .filter(Boolean);
  if (healthStatuses.some((status) => status === 'error')) {
    healthTone = 'alert';
  } else if (healthStatuses.some((status) => status === 'warning')) {
    healthTone = 'warn';
  }

  const paymentsTone = subscriptionsCapability && subscriptionsCapability.available === false
    ? 'warn'
    : (failedPayments > 0 ? (failedPayments >= 5 ? 'alert' : 'warn') : 'ok');
  const usersTone = expiredLicenses > 0 ? 'warn' : 'ok';
  const presenceTone = suspiciousPresence > 0 ? 'warn' : (onlineUsers > 0 ? 'ok' : 'warn');
  const securityTone = securityAlerts > 0 ? 'alert' : (rateLimited24h > 0 ? 'warn' : 'ok');
  const backupTone = !backupHealthy ? 'alert' : (backupStale ? 'warn' : 'ok');
  const jobsTone = (pausedJobs > 0 || emailFailed24h > 0) ? 'warn' : 'ok';
  const notificationsTone = notificationsCapability && notificationsCapability.available === false
    ? 'warn'
    : (notifications.length === 0 ? 'warn' : 'ok');
  const auditTone = lastCriticalAudit ? 'warn' : 'ok';
  const infraTone = webhookFailed > 0 ? 'warn' : 'ok';

  setControlCenterKpi('cc-kpi-active-users', formatNumber(onlineUsers), onlineUsers > 0 ? 'ok' : 'warn');
  setControlCenterKpi('cc-kpi-paid-licenses', formatNumber(paidLicenses), paidLicenses > 0 ? 'ok' : 'warn');
  setControlCenterKpi('cc-kpi-expired-licenses', formatNumber(expiredLicenses), expiredLicenses > 0 ? 'warn' : 'ok');
  setControlCenterKpi('cc-kpi-failed-payments', formatNumber(failedPayments), failedPayments > 0 ? 'alert' : 'ok');
  setControlCenterKpi('cc-kpi-security-alerts', formatNumber(securityAlerts), securityAlerts > 0 ? 'alert' : 'ok');
  setControlCenterKpi('cc-kpi-backup-status', backupHealthy ? 'OK' : 'NONE', backupTone);
  setControlCenterText('cc-kpi-backup-time', latestBackupTime ? formatShortDateTime(latestBackupTime) : 'Bez backupu');
  setControlCenterText('cc-kpi-last-updated', `Naposledy: ${formatShortDateTime(controlCenterDataState.lastUpdatedAt)}`);

  setControlCenterText('cc-users-total', formatNumber(users.length));
  setControlCenterText('cc-users-disabled', formatNumber(disabledUsers));
  setControlCenterText('cc-users-expired', formatNumber(expiredLicenses));
  setControlCenterText('cc-users-unpaid', formatNumber(unpaidUsers));

  setControlCenterText('cc-payments-paid-today', formatHalersToCzk(paidTodayHalers));
  setControlCenterText('cc-payments-live-paid-count', formatNumber(livePaidCount));
  setControlCenterText('cc-payments-failed', formatNumber(failedPayments));
  setControlCenterText('cc-payments-refunds', formatNumber(refundedPayments));
  setControlCenterText('cc-payments-attention', formatNumber(paymentsAttention));
  setControlCenterText('cc-payments-live-test-ratio', `${formatNumber(livePaymentItems.length)} / ${formatNumber(testPaymentItems.length)}`);
  setControlCenterText('cc-payments-live-last', latestLivePaymentAt ? formatShortDateTime(latestLivePaymentAt.toISOString()) : 'Žádná');

  setControlCenterText('cc-presence-online', formatNumber(onlineUsers));
  setControlCenterText('cc-presence-offline', formatNumber(offlineUsers));
  setControlCenterText('cc-presence-recent', formatNumber(recentlyActive));
  setControlCenterText('cc-presence-suspicious', formatNumber(suspiciousPresence));

  setControlCenterText('cc-security-blocked-active', formatNumber(blockedActive));
  setControlCenterText('cc-security-bruteforce', formatNumber(bruteForceAlerts));
  setControlCenterText('cc-security-rate-limited', formatNumber(rateLimited24h));
  setControlCenterText('cc-security-suspicious', formatNumber(suspiciousAuthEvents));

  setControlCenterText('cc-backup-latest-status', backupHealthy ? 'OK' : 'Nedostupný');
  setControlCenterText('cc-backup-latest-time', latestBackupTime ? formatShortDateTime(latestBackupTime) : '-');
  setControlCenterText('cc-backup-count', formatNumber(backupCount));
  setControlCenterText('cc-backup-restore-warning', 'Dangerous');

  setControlCenterText('cc-jobs-running', formatNumber(runningJobs));
  setControlCenterText('cc-jobs-paused', formatNumber(pausedJobs));
  setControlCenterText('cc-email-sent', formatNumber(emailSent24h));
  setControlCenterText('cc-email-failed', formatNumber(emailFailed24h));

  setControlCenterText('cc-notifications-active', formatNumber(activeNotifications));
  setControlCenterText('cc-notifications-total', formatNumber(notifications.length));
  setControlCenterText('cc-notifications-severity-preview', 'info');
  setControlCenterText('cc-notifications-target-preview', (document.getElementById('cc-broadcast-target-type')?.value || 'all'));

  setControlCenterText('cc-audit-count', formatNumber(auditItems.length));
  setControlCenterText('cc-audit-last-critical', lastCriticalAudit
    ? `${lastCriticalAudit.action_type || '-'} (${formatShortDateTime(lastCriticalAudit.created_at)})`
    : 'Žádná');

  setControlCenterText('cc-infra-api-hits', apiTop ? `${apiTop.endpoint || '-'}: ${formatNumber(apiTop.hits || 0)}` : '-');
  setControlCenterText('cc-infra-webhooks-failed', formatNumber(webhookFailed));
  setControlCenterText('cc-infra-storage', storageTotalBytes > 0 ? `${(storageTotalBytes / (1024 * 1024)).toFixed(1)} MB` : '-');
  setControlCenterText('cc-infra-cleanup-preview', controlCenterDataState?.storageCleanupPreview?.reclaimed_human || '-');

  setControlCenterStatusChip('cc-module-health-status', healthTone, healthTone === 'ok' ? 'Healthy' : (healthTone === 'warn' ? 'Warning' : 'Error'));
  setControlCenterStatusChip(
    'cc-module-payments-status',
    paymentsTone,
    subscriptionsCapability && subscriptionsCapability.available === false
      ? 'Disabled until migration'
      : (paymentsTone === 'ok' ? 'Stable' : (paymentsTone === 'warn' ? 'Attention' : 'Critical'))
  );
  setControlCenterStatusChip('cc-module-users-status', usersTone, usersTone === 'ok' ? 'Stable' : 'Attention');
  setControlCenterStatusChip('cc-module-presence-status', presenceTone, presenceTone === 'ok' ? 'Normal' : 'Attention');
  setControlCenterStatusChip('cc-module-security-status', securityTone, securityTone === 'ok' ? 'Normal' : (securityTone === 'warn' ? 'Warning' : 'Alert'));
  setControlCenterStatusChip('cc-module-backups-status', backupTone, backupTone === 'ok' ? 'Safe' : (backupTone === 'warn' ? 'Stale' : 'No backup'));
  setControlCenterStatusChip('cc-module-jobs-status', jobsTone, jobsTone === 'ok' ? 'Running' : 'Attention');
  setControlCenterStatusChip(
    'cc-module-notifications-status',
    notificationsTone,
    notificationsCapability && notificationsCapability.available === false
      ? 'Disabled until migration'
      : (notificationsTone === 'ok' ? 'Active' : 'Empty')
  );
  if (adminAuditCapability && adminAuditCapability.available === false) {
    setControlCenterText('cc-audit-preview', 'Audit actions disabled until migration');
  }
  setControlCenterStatusChip('cc-module-audit-status', auditTone, auditTone === 'ok' ? 'Clean' : 'Review');
  setControlCenterStatusChip('cc-module-infra-status', infraTone, infraTone === 'ok' ? 'Stable' : 'Warning');

  setControlCenterHealthChip('cc-health-chip-api', 'API', healthComponents?.api?.status);
  setControlCenterHealthChip('cc-health-chip-database', 'DB', healthComponents?.database?.status);
  setControlCenterHealthChip('cc-health-chip-email', 'Email', healthComponents?.email_service?.status);
  setControlCenterHealthChip('cc-health-chip-payments', 'Payments', healthComponents?.payment_gateway?.status);
  setControlCenterHealthChip('cc-health-chip-workers', 'Workers', healthComponents?.background_jobs?.status);
  setControlCenterHealthChip('cc-health-chip-storage', 'Storage', backupHealthy ? 'ok' : 'warning');

  renderControlCenterPriorities({
    healthTone,
    failedPayments,
    securityAlerts,
    securityAlertParts: {
      bruteForceAlertIps: bruteForceAlerts,
      blockedActive,
      sourceProbes24h,
    },
    expiredLicenses,
    backupTone,
    pausedJobs,
  });
}

function summarizeControlCenterPayload(elementId, payload) {
  if (typeof payload === 'string') return payload;
  if (!payload || typeof payload !== 'object') return String(payload ?? '-');
  if (payload.error) return `Chyba: ${payload.error}`;

  switch (elementId) {
    case 'cc-health-result': {
      const components = payload.components || {};
      const statuses = Object.values(components).map((item) => String(item?.status || 'unknown').toLowerCase());
      if (statuses.length === 0) return 'Health data načtena.';
      if (statuses.some((status) => status === 'error')) return 'Health obsahuje chybu. Otevřete detail.';
      if (statuses.some((status) => status === 'warning')) return 'Health obsahuje varování. Ověřte detail.';
      return 'System health je v pořádku.';
    }
    case 'cc-payments-result': {
      const summary = payload.summary || {};
      const liveCount = Number(summary?.live?.count || 0);
      const testCount = Number(summary?.test?.count || 0);
      const livePaid = Number(summary?.live?.paid_count || 0);
      return `Načteno plateb: ${formatNumber(payload.count ?? payload.items?.length ?? 0)}. LIVE ${formatNumber(liveCount)} (paid ${formatNumber(livePaid)}), TEST ${formatNumber(testCount)}.`;
    }
    case 'cc-presence-result':
      return `Načteno presence záznamů: ${formatNumber(payload.count ?? payload.items?.length ?? 0)}.`;
    case 'cc-security-result': {
      const s = payload?.summary || {};
      const total = controlCenterSecurityAlertTotal(s);
      const rollupN = Array.isArray(payload?.source_probe_by_ip_24h) ? payload.source_probe_by_ip_24h.length : 0;
      const parts = [
        `součet (banner): ${formatNumber(total)}`,
        `zdrojové IP řádky (agregace): ${formatNumber(rollupN)}`,
        `aktivní blokace: ${formatNumber(s.blocked_ips_active || 0)}`,
        `IP ≥5 fail/24h: ${formatNumber(s.brute_force_alert_ips ?? 0)}`,
        `zdrojové pokusy 24h: ${formatNumber(s.source_probes_24h || 0)}`,
      ];
      const secCount = Array.isArray(payload?.security_events) ? payload.security_events.length : 0;
      return `${parts.join('; ')}. Detailních bezpečnostních událostí v odpovědi: ${formatNumber(secCount)}.`;
    }
    case 'cc-backup-result':
      return payload.message || `Načteno backupů: ${formatNumber(payload.items?.length ?? 0)}.`;
    case 'cc-infra-result':
      return payload.message || 'Infrastrukturní data načtena.';
    case 'cc-ops-result':
      return payload.message || 'Jobs/email data načtena.';
    case 'cc-logs-result':
      return payload.message || 'Audit/log data načtena.';
    case 'cc-notifications-result':
      return payload.message || `Načteno notifikací: ${formatNumber(payload.count ?? payload.items?.length ?? 0)}.`;
    default:
      return payload.message || 'Operace dokončena.';
  }
}

function setControlCenterResult(elementId, payload) {
  const el = document.getElementById(elementId);
  if (!el) return;

  const serialized = typeof payload === 'string' ? payload : JSON.stringify(payload, null, 2);
  const technicalId = CONTROL_CENTER_TECHNICAL_RESULT_IDS[elementId];
  if (technicalId) {
    const technicalEl = document.getElementById(technicalId);
    if (technicalEl) {
      technicalEl.textContent = serialized;
    }
  }

  if (CONTROL_CENTER_RAW_RESULT_IDS.has(elementId)) {
    el.textContent = serialized;
    return;
  }
  el.textContent = summarizeControlCenterPayload(elementId, payload);
}

function getNumberValue(id) {
  const raw = document.getElementById(id)?.value;
  if (!raw) return null;
  const num = Number(raw);
  if (!Number.isFinite(num) || num <= 0) return null;
  return Math.floor(num);
}

function renderControlCenterTable(containerId, columns, rows) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const safeRows = Array.isArray(rows) ? rows : [];
  if (safeRows.length === 0) {
    el.innerHTML = '<div class="empty">Žádná data</div>';
    return;
  }
  const head = columns.map((col) => `<th>${escapeHtml(col.label)}</th>`).join('');
  const body = safeRows.map((row) => {
    const cells = columns.map((col) => {
      const rawValue = typeof col.render === 'function' ? col.render(row) : row[col.key];
      return `<td>${rawValue === undefined || rawValue === null || rawValue === '' ? '-' : rawValue}</td>`;
    }).join('');
    return `<tr>${cells}</tr>`;
  }).join('');
  el.innerHTML = `
    <table class="cc-mini-table">
      <thead><tr>${head}</tr></thead>
      <tbody>${body}</tbody>
    </table>
  `;
}

function clearControlCenterTable(containerId) {
  const el = document.getElementById(containerId);
  if (el) {
    el.innerHTML = '';
  }
}

function setControlCenterTableLoading(containerId, message = 'Načítám...') {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = `<div class="loading">${escapeHtml(message)}</div>`;
}

function setControlCenterLoading(resultId, tableIds = []) {
  const loadingPayload = { loading: true, timestamp: new Date().toISOString() };
  if (resultId) {
    if (CONTROL_CENTER_RAW_RESULT_IDS.has(resultId)) {
      setControlCenterResult(resultId, loadingPayload);
    } else {
      const target = document.getElementById(resultId);
      if (target) {
        target.textContent = 'Načítám...';
      }
      const technicalId = CONTROL_CENTER_TECHNICAL_RESULT_IDS[resultId];
      const technicalEl = technicalId ? document.getElementById(technicalId) : null;
      if (technicalEl) {
        technicalEl.textContent = JSON.stringify(loadingPayload, null, 2);
      }
    }
  }
  for (const tableId of tableIds) {
    setControlCenterTableLoading(tableId);
  }
}

function syncControlCenterDetailsOverlayState() {
  const anyOpen = Boolean(document.querySelector('#section-control-center .cc-module-details[open]'));
  document.body.classList.toggle('cc-details-open', anyOpen);
  if (anyOpen) {
    const scrollbarWidth = Math.max(0, window.innerWidth - document.documentElement.clientWidth);
    document.body.style.setProperty('--cc-overlay-scrollbar', `${scrollbarWidth}px`);
  } else {
    document.body.style.removeProperty('--cc-overlay-scrollbar');
  }
}

function closeAllControlCenterDetails(exceptId = '') {
  const detailsNodes = Array.from(document.querySelectorAll('#section-control-center .cc-module-details'));
  detailsNodes.forEach((node) => {
    if (!exceptId || node.id !== exceptId) {
      node.open = false;
    }
  });
  syncControlCenterDetailsOverlayState();
}

function initControlCenterDetailsBehavior() {
  const detailsNodes = Array.from(document.querySelectorAll('#section-control-center .cc-module-details'));
  detailsNodes.forEach((node) => {
    const summary = node.querySelector(':scope > summary');
    if (summary && summary.dataset.closeBound !== '1') {
      const closeBtn = document.createElement('button');
      closeBtn.type = 'button';
      closeBtn.className = 'cc-details-close-btn';
      closeBtn.textContent = 'Zavřít';
      closeBtn.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        node.open = false;
        syncControlCenterDetailsOverlayState();
      });
      summary.appendChild(closeBtn);
      summary.dataset.closeBound = '1';
    }

    if (node.dataset.bound === '1') return;
    node.addEventListener('toggle', () => {
      if (node.open) {
        closeAllControlCenterDetails(node.id);
      }
      syncControlCenterDetailsOverlayState();
    });
    node.dataset.bound = '1';
  });
}

function focusControlCenterDetailPrimaryField(detailsEl) {
  if (!detailsEl) return;
  const target = detailsEl.querySelector(
    '[data-cc-primary-focus], input:not([type="hidden"]):not([disabled]), select:not([disabled]), textarea:not([disabled])',
  );
  if (target && typeof target.focus === 'function') {
    target.focus({ preventScroll: true });
  }
}

function openControlCenterModuleDetails(detailsId) {
  const detailsEl = document.getElementById(detailsId);
  if (!detailsEl || detailsEl.tagName.toLowerCase() !== 'details') return;
  if (detailsEl.open) {
    detailsEl.open = false;
    syncControlCenterDetailsOverlayState();
    return;
  }
  closeAllControlCenterDetails(detailsId);
  detailsEl.open = true;
  syncControlCenterDetailsOverlayState();
  const ccDetailLoaders = {
    'cc-health-details': loadControlCenterHealth,
    'cc-security-details': loadControlCenterSecurityMonitor,
    'cc-backups-details': loadControlCenterBackups,
    'cc-payments-details': loadControlCenterPayments,
    'cc-jobs-details': loadControlCenterJobs,
    'cc-users-details': loadControlCenterUsersSnapshot,
  };
  const loader = ccDetailLoaders[detailsId];
  if (typeof loader === 'function') {
    loader();
  }
  requestAnimationFrame(() => {
    detailsEl.scrollTop = 0;
    focusControlCenterDetailPrimaryField(detailsEl);
  });
}

function focusControlCenterModule(moduleId, detailsId = '') {
  const moduleEl = document.getElementById(moduleId);
  if (moduleEl) {
    moduleEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  if (detailsId) {
    openControlCenterModuleDetails(detailsId);
  }
}

async function loadControlCenterUsersSnapshot() {
  try {
    const users = await fetchAllList('/admin-api/users');
    setControlCenterState('users', users);
  } catch (error) {
    console.error('Error loading control center users snapshot:', error);
    setControlCenterState('users', []);
  }
}

function initControlCenterDraftPreviewBindings() {
  const targetType = document.getElementById('cc-broadcast-target-type');
  const targetValue = document.getElementById('cc-broadcast-target-value');
  if (targetType && targetType.dataset.bound !== '1') {
    targetType.addEventListener('change', renderControlCenterDashboard);
    targetType.dataset.bound = '1';
  }
  if (targetValue && targetValue.dataset.bound !== '1') {
    targetValue.addEventListener('input', () => {
      const value = (targetValue.value || '').trim();
      setControlCenterText('cc-notifications-target-preview', value || (targetType?.value || 'all'));
    });
    targetValue.dataset.bound = '1';
  }
}

function initControlCenterModuleColumns() {
  const grid = document.querySelector('#section-control-center .cc-module-grid');
  if (!grid) return;
  if (grid.dataset.columnsReady === '1') return;
  if (Array.from(grid.children).some((el) => el.classList && el.classList.contains('cc-module-column'))) {
    grid.dataset.columnsReady = '1';
    return;
  }

  const cards = Array.from(grid.children).filter(
    (el) => el.classList && el.classList.contains('cc-module-card'),
  );
  if (cards.length === 0) return;

  const leftColumn = document.createElement('div');
  leftColumn.className = 'cc-module-column cc-module-column-left';
  const rightColumn = document.createElement('div');
  rightColumn.className = 'cc-module-column cc-module-column-right';

  cards.forEach((card, index) => {
    if (index % 2 === 0) {
      leftColumn.appendChild(card);
    } else {
      rightColumn.appendChild(card);
    }
  });

  grid.appendChild(leftColumn);
  grid.appendChild(rightColumn);
  grid.dataset.columnsReady = '1';
}

async function refreshControlCenterOverview() {
  if (!canAccessControlCenter()) {
    setControlCenterResult('cc-health-result', { detail: 'Sekce je dostupná pouze pro roli developer_admin.' });
    return;
  }

  dismissControlCenterPlaybook();

  initControlCenterModuleColumns();
  initControlCenterDetailsBehavior();
  initControlCenterDraftPreviewBindings();
  initControlCenterBroadcastComposer();

  await Promise.all([
    loadControlCenterUsersSnapshot(),
    loadControlCenterHealth(),
    loadControlCenterPayments(),
    loadControlCenterPresence(),
    loadControlCenterSecurityMonitor(),
    loadControlCenterBackups(),
    loadControlCenterApiMonitor(),
    loadControlCenterWebhookMonitor(),
    loadControlCenterStorage(),
    loadControlCenterEmailMonitor(),
    loadControlCenterJobs(),
    loadControlCenterNotifications(),
    loadControlCenterAuditActions(),
  ]);
}

async function loadControlCenterHealth() {
  setControlCenterLoading('cc-health-result', ['cc-health-table']);
  try {
    const data = await apiRequest('GET', '/admin-api/control-center/health');
    setControlCenterState('health', data);
    const components = data?.components || {};
    const rows = Object.entries(components).map(([name, component]) => ({
      component: name,
      status: component?.status || 'unknown',
      detail: buildControlCenterHealthDetail(component),
    }));
    renderControlCenterTable(
      'cc-health-table',
      [
        { key: 'component', label: 'Komponenta', render: (row) => escapeHtml(row.component) },
        { key: 'status', label: 'Stav', render: (row) => renderControlCenterStatusLabel(row.status) },
        { key: 'detail', label: 'Poznámka', render: (row) => escapeHtml(row.detail) },
      ],
      rows,
    );
    setControlCenterResult('cc-health-result', data);
  } catch (error) {
    clearControlCenterTable('cc-health-table');
    setControlCenterResult('cc-health-result', { error: error.message });
  }
}

function getSortedControlCenterPaymentItems(items) {
  return items
    .slice()
    .sort((a, b) => {
      const envA = normalizePaymentEnvironment(a);
      const envB = normalizePaymentEnvironment(b);
      if (envA !== envB) return envA === 'LIVE' ? -1 : 1;
      return new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime();
    });
}

function getControlCenterPaymentsFilterState() {
  const env = (document.getElementById('cc-payments-filter-env')?.value || 'all').toLowerCase();
  const state = (document.getElementById('cc-payments-filter-state')?.value || 'all').toLowerCase();
  const query = (document.getElementById('cc-payments-filter-query')?.value || '').trim().toLowerCase();
  controlCenterPaymentsFilters.env = env;
  controlCenterPaymentsFilters.state = state;
  controlCenterPaymentsFilters.query = query;
  return { ...controlCenterPaymentsFilters };
}

function paymentMatchesControlCenterFilters(item, filters) {
  const env = normalizePaymentEnvironment(item).toLowerCase();
  if (filters.env !== 'all' && filters.env !== env) return false;

  if (filters.state === 'success' && !isPaymentSuccessful(item)) return false;
  if (filters.state === 'failed' && !isPaymentFailed(item)) return false;
  if (filters.state === 'attention' && !isPaymentNeedsAttention(item)) return false;
  if (filters.state === 'refunded' && String(item?.refund_status || '').trim().toLowerCase() !== 'refunded') return false;

  if (filters.query) {
    const haystack = [
      String(item?.account_email || ''),
      String(item?.trans_id || ''),
      String(item?.ref_id || ''),
      String(item?.plan || ''),
      String(item?.provider_status || ''),
    ].join(' ').toLowerCase();
    if (!haystack.includes(filters.query)) return false;
  }

  return true;
}

function renderControlCenterPaymentsLiveFeed(items) {
  const liveFeedEl = document.getElementById('cc-payments-live-feed');
  const liveLastEl = document.getElementById('cc-payments-live-last');
  if (!liveFeedEl || !liveLastEl) return;

  const livePaid = items
    .filter((item) => normalizePaymentEnvironment(item) === 'LIVE' && isPaymentSuccessful(item))
    .sort((a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime());

  const latestLive = livePaid[0] || null;
  liveLastEl.textContent = latestLive ? formatDateTime(latestLive.created_at) : 'Žádná';

  if (livePaid.length === 0) {
    liveFeedEl.innerHTML = '<div class="empty">Žádné LIVE platby v aktuálním feedu.</div>';
    return;
  }

  liveFeedEl.innerHTML = livePaid.slice(0, 4).map((item) => {
    const amount = Number(item.amount_halers || 0).toLocaleString('cs-CZ');
    const email = escapeHtml(item.account_email || '-');
    const transId = escapeHtml(item.trans_id || '-');
    return `
      <div class="cc-live-feed-item">
        <div class="cc-live-feed-main">${email}</div>
        <div class="cc-live-feed-meta">${amount} hal. • ${escapeHtml(item.currency || 'CZK')} • ${formatDateTime(item.created_at)}</div>
        <div class="cc-live-feed-meta">transId: ${transId}</div>
      </div>
    `;
  }).join('');
}

function renderControlCenterPaymentsModule(data) {
  const items = Array.isArray(data?.items) ? data.items : [];
  const summary = data?.summary || {};
  const liveSummary = summary?.live || {};
  const testSummary = summary?.test || {};
  const allSummary = summary?.all || {};
  const sortedItems = getSortedControlCenterPaymentItems(items);
  const liveItems = sortedItems.filter((item) => normalizePaymentEnvironment(item) === 'LIVE');
  const filters = getControlCenterPaymentsFilterState();
  const filteredItems = sortedItems.filter((item) => paymentMatchesControlCenterFilters(item, filters));

  renderControlCenterTable(
    'cc-payments-summary',
    [
      { key: 'metric', label: 'Metrika', render: (row) => escapeHtml(row.metric) },
      { key: 'value', label: 'Hodnota', render: (row) => escapeHtml(row.value) },
    ],
    [
      { metric: 'Transakce celkem', value: formatNumber(allSummary.count ?? items.length) },
      { metric: 'LIVE transakce', value: formatNumber(liveSummary.count ?? liveItems.length) },
      { metric: 'TEST transakce', value: formatNumber(testSummary.count ?? (items.length - liveItems.length)) },
      { metric: 'LIVE paid', value: formatNumber(liveSummary.paid_count ?? liveItems.filter((item) => isPaymentSuccessful(item)).length) },
      { metric: 'LIVE paid today', value: formatHalersToCzk(liveSummary.paid_today_halers ?? 0) },
      { metric: 'LIVE failed', value: formatNumber(liveSummary.failed_count ?? liveItems.filter((item) => isPaymentFailed(item)).length) },
      { metric: 'LIVE refundy', value: formatNumber(liveSummary.refund_count ?? liveItems.filter((item) => String(item.refund_status || '').toLowerCase() === 'refunded').length) },
      { metric: 'LIVE vyžaduje akci', value: formatNumber(liveSummary.attention_count ?? liveItems.filter((item) => isPaymentNeedsAttention(item)).length) },
      { metric: 'Filtrované položky', value: formatNumber(filteredItems.length) },
    ],
  );

  renderControlCenterTable(
    'cc-payments-table',
    [
      { key: 'id', label: '#' },
      { key: 'payment_environment', label: 'Env', render: (row) => escapeHtml(normalizePaymentEnvironment(row)) },
      { key: 'account_email', label: 'Účet', render: (row) => escapeHtml(row.account_email || '-') },
      { key: 'trans_id', label: 'Trans ID', render: (row) => escapeHtml(row.trans_id || '-') },
      { key: 'plan', label: 'Plan', render: (row) => escapeHtml((row.plan || '-').toUpperCase()) },
      { key: 'amount_halers', label: 'Částka', render: (row) => Number(row.amount_halers || 0).toLocaleString('cs-CZ') + ' hal.' },
      { key: 'provider_status', label: 'Stav', render: (row) => escapeHtml(row.provider_status || '-') },
      { key: 'refund_status', label: 'Refund', render: (row) => escapeHtml(row.refund_status || 'none') },
      { key: 'created_at', label: 'Čas', render: (row) => formatDateTime(row.created_at) },
    ],
    filteredItems.slice(0, 40),
  );

  renderControlCenterPaymentsLiveFeed(sortedItems);
}

function bindControlCenterPaymentsFilters() {
  const envEl = document.getElementById('cc-payments-filter-env');
  const stateEl = document.getElementById('cc-payments-filter-state');
  const queryEl = document.getElementById('cc-payments-filter-query');
  if (!envEl || !stateEl || !queryEl) return;

  if (envEl.dataset.bound !== '1') {
    envEl.addEventListener('change', () => {
      renderControlCenterPaymentsModule(controlCenterDataState.payments || {});
    });
    envEl.dataset.bound = '1';
  }
  if (stateEl.dataset.bound !== '1') {
    stateEl.addEventListener('change', () => {
      renderControlCenterPaymentsModule(controlCenterDataState.payments || {});
    });
    stateEl.dataset.bound = '1';
  }
  if (queryEl.dataset.bound !== '1') {
    queryEl.addEventListener('input', () => {
      renderControlCenterPaymentsModule(controlCenterDataState.payments || {});
    });
    queryEl.dataset.bound = '1';
  }
}

async function loadControlCenterPayments() {
  setControlCenterLoading('cc-payments-result', ['cc-payments-summary', 'cc-payments-table']);
  try {
    bindControlCenterPaymentsFilters();
    const data = await apiRequest('GET', '/admin-api/control-center/payments?limit=60');
    setControlCenterState('payments', data);
    renderControlCenterPaymentsModule(data);
    setControlCenterResult('cc-payments-result', data);
  } catch (error) {
    clearControlCenterTable('cc-payments-table');
    clearControlCenterTable('cc-payments-summary');
    const liveFeedEl = document.getElementById('cc-payments-live-feed');
    if (liveFeedEl) {
      liveFeedEl.innerHTML = '<div class="empty">Nepodařilo se načíst LIVE feed plateb.</div>';
    }
    setControlCenterResult('cc-payments-result', { error: error.message });
  }
}

async function runControlCenterPaymentResync() {
  if (!confirm('Spustit resync plateb a subscription stavu?')) return;
  setControlCenterLoading('cc-payments-result');
  try {
    const data = await apiRequest('POST', '/admin-api/control-center/payments/resync', {});
    setControlCenterResult('cc-payments-result', data);
    showSuccess('Payment resync dokončen');
    await Promise.all([loadControlCenterPayments(), loadControlCenterUsersSnapshot()]);
  } catch (error) {
    setControlCenterResult('cc-payments-result', { error: error.message });
  }
}

async function loadControlCenterPresence() {
  setControlCenterLoading('cc-presence-result', ['cc-presence-table']);
  try {
    const data = await apiRequest('GET', '/admin-api/control-center/presence?limit=120');
    const items = Array.isArray(data?.items) ? data.items : [];
    setControlCenterState('presence', data);
    renderControlCenterTable(
      'cc-presence-table',
      [
        { key: 'user_id', label: 'User ID' },
        { key: 'email', label: 'Email', render: (row) => escapeHtml(row.email || '-') },
        {
          key: 'online_status',
          label: 'Stav',
          render: (row) => {
            const isOnline = String(row.online_status || '').toUpperCase() === 'ONLINE';
            const klass = isOnline ? 'cc-status-online' : 'cc-status-offline';
            return `<span class="${klass}">${escapeHtml(row.online_status || '-')}</span>`;
          },
        },
        { key: 'last_seen_at', label: 'Last seen', render: (row) => formatDateTime(row.last_seen_at) },
        { key: 'last_login_at', label: 'Last login', render: (row) => formatDateTime(row.last_login_at) },
        { key: 'active_session_count', label: 'Relace' },
      ],
      items.slice(0, 30),
    );
    setControlCenterResult('cc-presence-result', data);
  } catch (error) {
    clearControlCenterTable('cc-presence-table');
    setControlCenterResult('cc-presence-result', { error: error.message });
  }
}

function formatSecurityLocationRow(row) {
  const label = (row && row.location_label) ? String(row.location_label).trim() : '';
  if (label) return escapeHtml(label);
  const parts = [row?.city, row?.region, row?.country].filter(Boolean);
  if (parts.length) return escapeHtml(parts.join(', '));
  return '-';
}

/** Stejná logika jako banner: API total jen když je skutečně vrácené číslo (ne null). */
function controlCenterSecurityAlertTotal(summary) {
  const s = summary || {};
  const raw = s.control_center_alert_total;
  if (raw != null && Number.isFinite(Number(raw))) {
    return Number(raw);
  }
  const brute = Number(s.brute_force_alert_ips) || 0;
  const blocked = Number(s.blocked_ips_active) || 0;
  const probes = Number(s.source_probes_24h) || 0;
  return brute + blocked + probes;
}

function renderSecurityMonitorExplain(data) {
  const el = document.getElementById('cc-security-breakdown-explain');
  if (!el) return;
  const s = data?.summary || {};
  const total = controlCenterSecurityAlertTotal(s);
  const brute = Number(s.brute_force_alert_ips) || 0;
  const blocked = Number(s.blocked_ips_active) || 0;
  const probes = Number(s.source_probes_24h) || 0;
  el.innerHTML = `
    <div class="cc-security-hero-stats" role="group" aria-label="Přehled security alertů">
      <div class="cc-security-stat"><span>Součet (jako v „Co řešit teď“)</span><strong>${formatNumber(total)}</strong></div>
      <div class="cc-security-stat"><span>Brute IP ≥5 fail / 24 h</span><strong>${formatNumber(brute)}</strong></div>
      <div class="cc-security-stat"><span>Aktivní blokace</span><strong>${formatNumber(blocked)}</strong></div>
      <div class="cc-security-stat"><span>Zdrojové pokusy / 24 h</span><strong>${formatNumber(probes)}</strong></div>
    </div>
    <p class="cc-security-hero-hint">Součet = první tři složky výše. U zdrojových pokusů jde o <strong>počet událostí</strong> (stejná IP může přispět vícekrát). Nejdřív zkontrolujte tabulku zdrojových pokusů podle IP — je nejčitelnější.</p>
  `;
}

function isSecurityEventRow(item) {
  const t = String(item?.event_type || '').toLowerCase();
  if (t === 'login_success') return false;
  return t === 'login_failed'
    || t === 'login_rate_limited'
    || t === 'source_probe_blocked'
    || t.includes('rate_limited')
    || t.includes('source_probe')
    || t.includes('login_failed');
}

async function loadControlCenterSecurityMonitor() {
  setControlCenterLoading('cc-security-result', [
    'cc-security-source-probes-table',
    'cc-security-events-table',
    'cc-security-failed-ips-table',
    'cc-security-table',
    'cc-security-activity-table',
  ]);
  try {
    const data = await apiRequest('GET', '/admin-api/control-center/security-monitor');
    setControlCenterState('security', data);
    renderSecurityMonitorExplain(data);
    const rollup = Array.isArray(data?.source_probe_by_ip_24h) ? data.source_probe_by_ip_24h : [];
    renderControlCenterTable(
      'cc-security-source-probes-table',
      [
        { key: 'ip_address', label: 'IP', render: (row) => escapeHtml(row.ip_address || '-') },
        { key: 'probe_count', label: 'Pokusů (24 h)', render: (row) => formatNumber(row.probe_count || 0) },
        { key: 'last_probe_at', label: 'Poslední', render: (row) => formatDateTime(row.last_probe_at) },
      ],
      rollup.slice(0, 50),
    );
    const topFailedIps = Array.isArray(data?.top_failed_ips) ? data.top_failed_ips : [];
    renderControlCenterTable(
      'cc-security-failed-ips-table',
      [
        { key: 'ip_address', label: 'IP (neúspěšné loginy 24h)', render: (row) => escapeHtml(row.ip_address || '-') },
        {
          key: 'failed_count',
          label: 'Počet',
          render: (row) => formatNumber(row.failed_count || 0),
        },
        {
          key: 'alert',
          label: 'Práh',
          render: (row) => (Number(row.failed_count || 0) >= 5 ? '<span class="cc-status-alert">≥5 = alert</span>' : 'pod prahem'),
        },
      ],
      topFailedIps.slice(0, 20),
    );
    const blocked = Array.isArray(data?.blocked_ips) ? [...data.blocked_ips] : [];
    blocked.sort((a, b) => {
      if (Boolean(a.is_active) === Boolean(b.is_active)) return 0;
      return a.is_active ? -1 : 1;
    });
    renderControlCenterTable(
      'cc-security-table',
      [
        { key: 'ip_address', label: 'IP' },
        { key: 'is_active', label: 'Aktivní', render: (row) => row.is_active ? 'ANO' : 'NE' },
        { key: 'reason', label: 'Důvod', render: (row) => escapeHtml(row.reason || '-') },
        {
          key: 'blocked_by_email',
          label: 'Blokoval',
          render: (row) => escapeHtml(row.blocked_by_email || '-'),
        },
        { key: 'blocked_at', label: 'Blocked at', render: (row) => formatDateTime(row.blocked_at) },
        { key: 'expires_at', label: 'Expires', render: (row) => formatDateTime(row.expires_at) },
      ],
      blocked.slice(0, 40),
    );
    let securityEvents = Array.isArray(data?.security_events) ? data.security_events : [];
    const latestRaw = Array.isArray(data?.latest_events) ? data.latest_events : [];
    if (securityEvents.length === 0 && latestRaw.length > 0) {
      securityEvents = latestRaw.filter(isSecurityEventRow);
    }
    renderControlCenterTable(
      'cc-security-events-table',
      [
        { key: 'created_at', label: 'Čas', render: (row) => formatDateTime(row.created_at) },
        { key: 'event_type', label: 'Událost', render: (row) => escapeHtml(row.event_type || '-') },
        { key: 'user_email', label: 'Uživatel', render: (row) => escapeHtml(row.user_email || '(neznámý)') },
        { key: 'ip_address', label: 'IP', render: (row) => escapeHtml(row.ip_address || '-') },
        { key: 'location_label', label: 'Lokalita', render: (row) => formatSecurityLocationRow(row) },
        { key: 'endpoint', label: 'Endpoint', render: (row) => escapeHtml(row.endpoint || '-') },
        {
          key: 'details_preview',
          label: 'Detail',
          render: (row) => {
            const full = row.details || row.details_preview || '';
            const short = row.details_preview || (full.length > 120 ? `${full.slice(0, 117)}...` : full);
            if (!short) return '-';
            return `<span title="${escapeHtml(full)}">${escapeHtml(short)}</span>`;
          },
        },
      ],
      securityEvents.slice(0, 150),
    );
    const latestEvents = Array.isArray(data?.latest_events) ? data.latest_events : [];
    renderControlCenterTable(
      'cc-security-activity-table',
      [
        { key: 'created_at', label: 'Čas', render: (row) => formatDateTime(row.created_at) },
        { key: 'event_type', label: 'Událost', render: (row) => escapeHtml(row.event_type || '-') },
        { key: 'user_email', label: 'Uživatel', render: (row) => escapeHtml(row.user_email || '-') },
        { key: 'ip_address', label: 'IP', render: (row) => escapeHtml(row.ip_address || '-') },
        { key: 'location_label', label: 'Lokalita', render: (row) => formatSecurityLocationRow(row) },
        { key: 'endpoint', label: 'Endpoint', render: (row) => escapeHtml(row.endpoint || '-') },
      ],
      latestEvents.slice(0, 150),
    );
    const sp = Number(data?.summary?.source_probes_24h || 0);
    if (sp > 0 && rollup.length === 0) {
      const wrap = document.getElementById('cc-security-source-probes-table');
      if (wrap && wrap.querySelector('.empty')) {
        wrap.innerHTML = `<div class="cc-security-warn">API hlásí ${formatNumber(sp)} zdrojových pokusů, ale agregace podle IP je prázdná — zkontrolujte nasazení backendu nebo schéma DB.</div>`;
      }
    }
    setControlCenterResult('cc-security-result', data);
  } catch (error) {
    clearControlCenterTable('cc-security-source-probes-table');
    clearControlCenterTable('cc-security-failed-ips-table');
    clearControlCenterTable('cc-security-table');
    clearControlCenterTable('cc-security-events-table');
    clearControlCenterTable('cc-security-activity-table');
    const explain = document.getElementById('cc-security-breakdown-explain');
    if (explain) explain.innerHTML = '';
    setControlCenterResult('cc-security-result', { error: error.message });
  }
}

async function blockIpFromControlCenter() {
  const ipAddress = (document.getElementById('cc-block-ip')?.value || '').trim();
  const reason = (document.getElementById('cc-block-reason')?.value || '').trim();
  if (!ipAddress) {
    showGlobalError('Vyplňte IP adresu pro blokaci.');
    return;
  }
  try {
    const data = await apiRequest('POST', '/admin-api/control-center/security/block-ip', {
      ip_address: ipAddress,
      reason: reason || null,
    });
    setControlCenterResult('cc-security-result', data);
    await loadControlCenterSecurityMonitor();
    showSuccess('IP adresa byla zablokována');
  } catch (error) {
    setControlCenterResult('cc-security-result', { error: error.message });
  }
}

async function unblockIpFromControlCenter() {
  const ipAddress = (document.getElementById('cc-block-ip')?.value || '').trim();
  const reason = (document.getElementById('cc-block-reason')?.value || '').trim();
  if (!ipAddress) {
    showGlobalError('Vyplňte IP adresu pro odblokování.');
    return;
  }
  try {
    const data = await apiRequest('POST', '/admin-api/control-center/security/unblock-ip', {
      ip_address: ipAddress,
      reason: reason || null,
    });
    setControlCenterResult('cc-security-result', data);
    await loadControlCenterSecurityMonitor();
    showSuccess('IP adresa byla odblokována');
  } catch (error) {
    setControlCenterResult('cc-security-result', { error: error.message });
  }
}

async function loadControlCenterBackups() {
  setControlCenterLoading('cc-backup-result', ['cc-backups-table']);
  try {
    const data = await apiRequest('GET', '/admin-api/control-center/backups');
    setControlCenterState('backups', data);
    const items = Array.isArray(data?.items) ? data.items : [];
    renderControlCenterTable(
      'cc-backups-table',
      [
        { key: 'backup_id', label: 'Backup ID', render: (row) => escapeHtml(row.backup_id || '-') },
        { key: 'created_at', label: 'Vytvořeno', render: (row) => formatDateTime(row.created_at) },
        { key: 'created_by', label: 'Vytvořil', render: (row) => escapeHtml(row.created_by || '-') },
        { key: 'db_size_bytes', label: 'DB size', render: (row) => Number(row.db_size_bytes || 0).toLocaleString('cs-CZ') + ' B' },
        { key: 'include_data_dir', label: 'Data', render: (row) => row.include_data_dir ? 'ANO' : 'NE' },
      ],
      items.slice(0, 20),
    );
    setControlCenterResult('cc-backup-result', data);
  } catch (error) {
    clearControlCenterTable('cc-backups-table');
    setControlCenterResult('cc-backup-result', { error: error.message });
  }
}

async function createControlCenterBackup() {
  setControlCenterLoading('cc-backup-result');
  try {
    const data = await apiRequest('POST', '/admin-api/control-center/backups/create', { include_data_dir: true });
    setControlCenterResult('cc-backup-result', data);
    await Promise.all([loadControlCenterBackups(), loadControlCenterStorage()]);
    renderControlCenterDashboard();
    showSuccess('Backup byl vytvořen. Stav zálohy a priorita „Co řešit teď“ jsou přepočítané.');
  } catch (error) {
    setControlCenterResult('cc-backup-result', { error: error.message });
  }
}

async function restoreControlCenterBackup() {
  const backupId = (document.getElementById('cc-restore-backup-id')?.value || '').trim();
  const scope = (document.getElementById('cc-restore-scope')?.value || 'full').trim();
  const confirmText = (document.getElementById('cc-restore-confirm')?.value || '').trim();
  const userId = getNumberValue('cc-restore-user-id');
  const vehicleId = getNumberValue('cc-restore-vehicle-id');

  if (!backupId) {
    showGlobalError('Vyplňte backup ID.');
    return;
  }

  const reason = await promptAdminReason('Restore backupu může přepsat data.');
  if (!reason) return;
  if (!confirm(`Restore může přepsat data. Pokračovat?\n\nDůvod: ${reason}`)) return;
  setControlCenterLoading('cc-backup-result');

  try {
    const data = await apiRequest('POST', '/admin-api/control-center/backups/restore', {
      backup_id: backupId,
      scope,
      user_id: userId,
      vehicle_id: vehicleId,
      confirm_text: confirmText,
    });
    setControlCenterResult('cc-backup-result', data);
    showSuccess('Restore dokončen');
    await Promise.all([
      loadOverview(),
      loadUsers(),
      loadVehicles(),
      loadRecords(),
      loadControlCenterBackups(),
      loadControlCenterUsersSnapshot(),
      loadControlCenterPresence(),
    ]);
  } catch (error) {
    setControlCenterResult('cc-backup-result', { error: error.message });
  }
}

async function loadControlCenterApiMonitor() {
  setControlCenterLoading('cc-infra-result', ['cc-api-monitor-table']);
  try {
    const data = await apiRequest('GET', '/admin-api/control-center/api-monitor');
    setControlCenterState('apiMonitor', data);
    const rows = Array.isArray(data?.items) ? data.items : [];
    renderControlCenterTable(
      'cc-api-monitor-table',
      [
        { key: 'endpoint', label: 'Endpoint', render: (row) => escapeHtml(row.endpoint || '-') },
        { key: 'hits', label: 'Hits 24h', render: (row) => formatNumber(row.hits || 0) },
      ],
      rows.slice(0, 30),
    );
    setControlCenterResult('cc-infra-result', data);
  } catch (error) {
    clearControlCenterTable('cc-api-monitor-table');
    setControlCenterResult('cc-infra-result', { error: error.message });
  }
}

async function loadControlCenterWebhookMonitor() {
  setControlCenterLoading('cc-infra-result', ['cc-webhooks-table']);
  try {
    const data = await apiRequest('GET', '/admin-api/control-center/webhook-monitor');
    setControlCenterState('webhookMonitor', data);
    const rows = Array.isArray(data?.tail) ? data.tail : [];
    renderControlCenterTable(
      'cc-webhooks-table',
      [
        { key: 'idx', label: '#', render: (row) => String(row.idx) },
        { key: 'line', label: 'Webhook log řádek', render: (row) => escapeHtml(row.line || '-') },
      ],
      rows.slice(0, 20).map((line, index) => ({ idx: index + 1, line })),
    );
    setControlCenterResult('cc-infra-result', data);
  } catch (error) {
    clearControlCenterTable('cc-webhooks-table');
    setControlCenterResult('cc-infra-result', { error: error.message });
  }
}

async function loadControlCenterStorage() {
  setControlCenterLoading('cc-infra-result', ['cc-storage-summary-table']);
  try {
    const data = await apiRequest('GET', '/admin-api/control-center/storage');
    setControlCenterState('storage', data);
    const dbSize = data?.database?.size_human || '-';
    const dataDir = data?.directories?.data?.total_human || '-';
    const logsDir = data?.directories?.logs?.total_human || '-';
    const backupsDir = data?.directories?.backups?.total_human || '-';
    renderControlCenterTable(
      'cc-storage-summary-table',
      [
        { key: 'label', label: 'Storage položka', render: (row) => escapeHtml(row.label) },
        { key: 'value', label: 'Využití', render: (row) => escapeHtml(row.value) },
      ],
      [
        { label: 'Database', value: dbSize },
        { label: 'Data dir', value: dataDir },
        { label: 'Logs dir', value: logsDir },
        { label: 'Backups dir', value: backupsDir },
      ],
    );
    setControlCenterResult('cc-infra-result', data);
  } catch (error) {
    clearControlCenterTable('cc-storage-summary-table');
    setControlCenterResult('cc-infra-result', { error: error.message });
  }
}

async function loadControlCenterEmailMonitor() {
  setControlCenterLoading('cc-ops-result', ['cc-email-table']);
  try {
    const data = await apiRequest('GET', '/admin-api/control-center/email-monitor');
    setControlCenterState('email', data);
    const items = Array.isArray(data?.items) ? data.items : [];
    renderControlCenterTable(
      'cc-email-table',
      [
        { key: 'id', label: '#' },
        { key: 'email', label: 'Email', render: (row) => escapeHtml(row.email || '-') },
        { key: 'subject', label: 'Předmět', render: (row) => escapeHtml(row.subject || '-') },
        { key: 'status', label: 'Stav', render: (row) => escapeHtml(row.status || '-') },
        { key: 'sent_at', label: 'Čas', render: (row) => formatDateTime(row.sent_at) },
      ],
      items.slice(0, 20),
    );
    setControlCenterResult('cc-ops-result', data);
  } catch (error) {
    clearControlCenterTable('cc-email-table');
    setControlCenterResult('cc-ops-result', { error: error.message });
  }
}

async function loadControlCenterJobs() {
  setControlCenterLoading('cc-ops-result', ['cc-jobs-table']);
  try {
    const data = await apiRequest('GET', '/admin-api/control-center/jobs');
    setControlCenterState('jobs', data);
    const jobs = Array.isArray(data?.jobs) ? data.jobs : [];
    renderControlCenterTable(
      'cc-jobs-table',
      [
        { key: 'name', label: 'Job', render: (row) => escapeHtml(row.name || '-') },
        { key: 'state', label: 'Stav', render: (row) => escapeHtml(row.state || '-') },
        { key: 'interval_seconds', label: 'Interval (s)' },
        { key: 'paused_by', label: 'Paused by', render: (row) => escapeHtml(row.paused_by || '-') },
        { key: 'pause_reason', label: 'Důvod', render: (row) => escapeHtml(row.pause_reason || '-') },
      ],
      jobs,
    );
    setControlCenterResult('cc-ops-result', data);
  } catch (error) {
    clearControlCenterTable('cc-jobs-table');
    setControlCenterResult('cc-ops-result', { error: error.message });
  }
}

async function runControlCenterJobPrompt() {
  const jobName = prompt('Zadejte job_name (např. license.subscription.cycle, reminders.notification.check):', 'license.subscription.cycle');
  if (!jobName) return;
  try {
    setControlCenterLoading('cc-ops-result');
    const data = await apiRequest('POST', '/admin-api/control-center/jobs/run', { job_name: jobName.trim() });
    setControlCenterResult('cc-ops-result', data);
    showSuccess(`Job ${jobName.trim()} dokončen`);
    await loadControlCenterJobs();
  } catch (error) {
    setControlCenterResult('cc-ops-result', { error: error.message });
  }
}

async function pauseControlCenterJobPrompt() {
  const jobName = prompt('Zadejte job_name pro pozastavení:', 'license.subscription.cycle');
  if (!jobName) return;
  const reason = prompt('Důvod pozastavení (volitelné):', 'maintenance') || null;
  try {
    setControlCenterLoading('cc-ops-result');
    const data = await apiRequest('POST', '/admin-api/control-center/jobs/pause', {
      job_name: jobName.trim(),
      reason,
    });
    setControlCenterResult('cc-ops-result', data);
    showSuccess(`Job ${jobName.trim()} byl pozastaven`);
    await loadControlCenterJobs();
  } catch (error) {
    setControlCenterResult('cc-ops-result', { error: error.message });
  }
}

async function resumeControlCenterJobPrompt() {
  const jobName = prompt('Zadejte job_name pro obnovení:', 'license.subscription.cycle');
  if (!jobName) return;
  const reason = prompt('Důvod obnovení (volitelné):', '') || null;
  try {
    setControlCenterLoading('cc-ops-result');
    const data = await apiRequest('POST', '/admin-api/control-center/jobs/resume', {
      job_name: jobName.trim(),
      reason,
    });
    setControlCenterResult('cc-ops-result', data);
    showSuccess(`Job ${jobName.trim()} byl obnoven`);
    await loadControlCenterJobs();
  } catch (error) {
    setControlCenterResult('cc-ops-result', { error: error.message });
  }
}

async function loadControlCenterSystemLogs() {
  setControlCenterLoading('cc-logs-result', ['cc-system-logs-table']);
  try {
    const data = await apiRequest('GET', '/admin-api/control-center/system-logs');
    setControlCenterState('systemLogs', data);
    const logs = Array.isArray(data?.logs) ? data.logs : [];
    renderControlCenterTable(
      'cc-system-logs-table',
      [
        { key: 'file', label: 'Soubor', render: (row) => escapeHtml(row.file || '-') },
        { key: 'exists', label: 'Existuje', render: (row) => row.exists ? 'ANO' : 'NE' },
        { key: 'tail_count', label: 'Tail řádků', render: (row) => formatNumber(Array.isArray(row.tail) ? row.tail.length : 0) },
        {
          key: 'last_line',
          label: 'Poslední řádek',
          render: (row) => {
            const tail = Array.isArray(row.tail) ? row.tail : [];
            const lastLine = tail.length > 0 ? tail[tail.length - 1] : '-';
            return escapeHtml(lastLine || '-');
          },
        },
      ],
      logs.slice(0, 20),
    );
    setControlCenterResult('cc-logs-result', data);
  } catch (error) {
    clearControlCenterTable('cc-system-logs-table');
    setControlCenterResult('cc-logs-result', { error: error.message });
  }
}

async function loadControlCenterAuditActions() {
  setControlCenterLoading('cc-logs-result', ['cc-audit-actions-table']);
  try {
    const data = await apiRequest('GET', '/admin-api/control-center/audit-actions?limit=200');
    setControlCenterState('audit', data);
    const items = Array.isArray(data?.items) ? data.items : [];
    renderControlCenterTable(
      'cc-audit-actions-table',
      [
        { key: 'id', label: '#' },
        { key: 'developer_email', label: 'Developer', render: (row) => escapeHtml(row.developer_email || '-') },
        { key: 'action_type', label: 'Akce', render: (row) => escapeHtml(row.action_type || '-') },
        { key: 'target_resource', label: 'Target', render: (row) => escapeHtml(row.target_resource || '-') },
        { key: 'result', label: 'Výsledek', render: (row) => escapeHtml(row.result || '-') },
        { key: 'created_at', label: 'Čas', render: (row) => formatDateTime(row.created_at) },
      ],
      items.slice(0, 40),
    );
    setControlCenterResult('cc-logs-result', data);
  } catch (error) {
    clearControlCenterTable('cc-audit-actions-table');
    setControlCenterResult('cc-logs-result', { error: error.message });
  }
}

async function executeControlCenterCommand() {
  const command = (document.getElementById('cc-command')?.value || '').trim();
  if (!command) {
    showGlobalError('Vyplňte příkaz.');
    return;
  }
  setControlCenterLoading('cc-command-result');
  try {
    const data = await apiRequest('POST', '/admin-api/control-center/commands/execute', { command });
    setControlCenterState('command', data);
    setControlCenterResult('cc-command-result', data);
    setControlCenterText('cc-command-summary', data?.ok ? 'Příkaz byl úspěšně dokončen.' : 'Příkaz dokončen.');
    setControlCenterStatusChip('cc-module-command-status', data?.ok ? 'ok' : 'warn', data?.ok ? 'Done' : 'Review');
  } catch (error) {
    setControlCenterResult('cc-command-result', { error: error.message });
    setControlCenterText('cc-command-summary', `Chyba příkazu: ${error.message}`);
    setControlCenterStatusChip('cc-module-command-status', 'alert', 'Error');
  }
}

async function loadControlCenterUserInsight() {
  const userId = getNumberValue('cc-insight-user-id');
  if (!userId) {
    showGlobalError('Vyplňte validní User ID.');
    return;
  }
  setControlCenterLoading('cc-insight-result', ['cc-insight-summary', 'cc-insight-payments-table']);
  try {
    const data = await apiRequest('GET', `/admin-api/control-center/user-insight/${userId}`);
    controlCenterCurrentInsight = data;
    setControlCenterState('insight', data);
    const insightUser = data?.user || {};
    const license = data?.license || {};
    const presence = data?.presence || {};
    const paymentsSummary = data?.payments_summary || {};
    populateLicensePlanSelect(
      'cc-license-plan',
      insightUser.role || 'user',
      license.current_plan || insightUser.license_plan || '',
      { includeBlank: true, blankLabel: 'beze změny' }
    );
    const summaryRows = [
      { key: 'plan', label: 'Plan', value: escapeHtml(formatAdminLicensePlanLabel(license.current_plan || '-', data?.user?.role || 'user')) },
      { key: 'status', label: 'Status', value: escapeHtml(license.status || '-') },
      { key: 'source', label: 'Zdroj', value: escapeHtml(license.source_of_activation || '-') },
      { key: 'purchase', label: 'Purchase', value: formatDateTime(license.purchase_date) },
      { key: 'activation', label: 'Activation', value: formatDateTime(license.activation_date) },
      { key: 'expiration', label: 'Expiration', value: formatDateTime(license.expiration_date) },
      { key: 'next_renewal', label: 'Next renewal', value: formatDateTime(license.next_renewal_date) },
      { key: 'has_paid', label: 'LIVE paid', value: paymentsSummary.has_live_paid ? 'Ano' : 'Ne' },
      { key: 'paid_live_count', label: 'LIVE paid count', value: String(paymentsSummary.live_paid_count ?? 0) },
      { key: 'paid_test_count', label: 'TEST paid count', value: String(paymentsSummary.test_paid_count ?? 0) },
      { key: 'payments_live_count', label: 'LIVE tx', value: String(paymentsSummary.count_live ?? 0) },
      { key: 'payments_test_count', label: 'TEST tx', value: String(paymentsSummary.count_test ?? 0) },
      { key: 'last_paid', label: 'Last paid', value: formatDateTime(paymentsSummary.last_paid_at) },
      { key: 'online', label: 'Online', value: escapeHtml(presence.online_status || '-') },
      { key: 'last_seen', label: 'Last seen', value: formatDateTime(presence.last_seen_at) },
      { key: 'sessions', label: 'Aktivní relace', value: String(presence.active_session_count ?? 0) },
    ];
    renderControlCenterTable(
      'cc-insight-summary',
      [
        { key: 'label', label: 'Položka', render: (row) => escapeHtml(row.label) },
        { key: 'value', label: 'Hodnota', render: (row) => row.value },
      ],
      summaryRows,
    );
    const paymentItems = Array.isArray(data?.payments) ? data.payments : [];
    renderControlCenterTable(
      'cc-insight-payments-table',
      [
        { key: 'id', label: '#' },
        { key: 'payment_environment', label: 'Env', render: (row) => escapeHtml(normalizePaymentEnvironment(row)) },
        { key: 'trans_id', label: 'Trans ID', render: (row) => escapeHtml(row.trans_id || '-') },
        { key: 'provider', label: 'Provider', render: (row) => escapeHtml(row.provider || '-') },
        { key: 'amount_halers', label: 'Částka', render: (row) => Number(row.amount_halers || 0).toLocaleString('cs-CZ') + ' hal.' },
        { key: 'currency', label: 'Měna', render: (row) => escapeHtml(row.currency || '-') },
        { key: 'provider_status', label: 'Status', render: (row) => escapeHtml(row.provider_status || '-') },
        { key: 'refund_status', label: 'Refund', render: (row) => escapeHtml(row.refund_status || 'none') },
        { key: 'payment_timestamp', label: 'Čas', render: (row) => formatDateTime(row.payment_timestamp) },
      ],
      paymentItems
        .slice()
        .sort((a, b) => {
          const envA = normalizePaymentEnvironment(a);
          const envB = normalizePaymentEnvironment(b);
          if (envA !== envB) return envA === 'LIVE' ? -1 : 1;
          return new Date(b.payment_timestamp || 0).getTime() - new Date(a.payment_timestamp || 0).getTime();
        })
        .slice(0, 20),
    );
    setControlCenterResult('cc-insight-result', data);
    setControlCenterStatusChip('cc-module-users-status', data?.user?.is_disabled ? 'warn' : 'ok', data?.user?.is_disabled ? 'Disabled' : 'Ready');
  } catch (error) {
    controlCenterCurrentInsight = null;
    setControlCenterState('insight', null);
    populateLicensePlanSelect('cc-license-plan', 'user', '', { includeBlank: true, blankLabel: 'beze změny' });
    clearControlCenterTable('cc-insight-summary');
    clearControlCenterTable('cc-insight-payments-table');
    setControlCenterResult('cc-insight-result', { error: error.message });
  }
}

function getControlCenterSelectedUserId() {
  return getNumberValue('cc-insight-user-id');
}

async function disableUserFromControlCenter() {
  const userId = getControlCenterSelectedUserId();
  if (!userId) {
    showGlobalError('Nejprve vyberte user ID.');
    return;
  }
  const reason = await promptAdminReason(`Pozastavení účtu #${userId}.`);
  if (!reason) return;
  if (!confirm(`Pozastavit účet uživatele #${userId}?\n\nDůvod: ${reason}`)) return;
  setControlCenterLoading('cc-insight-result');
  try {
    const data = await apiRequest('POST', `/admin-api/control-center/users/${userId}/disable`, { reason });
    setControlCenterResult('cc-insight-result', data);
    showSuccess('Účet byl pozastaven');
    await Promise.all([loadUsers(), loadControlCenterUsersSnapshot(), loadControlCenterUserInsight()]);
  } catch (error) {
    setControlCenterResult('cc-insight-result', { error: error.message });
  }
}

async function enableUserFromControlCenter() {
  const userId = getControlCenterSelectedUserId();
  if (!userId) {
    showGlobalError('Nejprve vyberte user ID.');
    return;
  }
  const reason = await promptAdminReason(`Aktivace účtu #${userId}.`);
  if (!reason) return;
  if (!confirm(`Aktivovat účet uživatele #${userId}?\n\nDůvod: ${reason}`)) return;
  setControlCenterLoading('cc-insight-result');
  try {
    const data = await apiRequest('POST', `/admin-api/control-center/users/${userId}/enable`, { reason });
    setControlCenterResult('cc-insight-result', data);
    showSuccess('Účet byl aktivován');
    await Promise.all([loadUsers(), loadControlCenterUsersSnapshot(), loadControlCenterUserInsight()]);
  } catch (error) {
    setControlCenterResult('cc-insight-result', { error: error.message });
  }
}

async function forceLogoutFromControlCenter() {
  const userId = getControlCenterSelectedUserId();
  if (!userId) {
    showGlobalError('Nejprve vyberte user ID.');
    return;
  }
  const reason = await promptAdminReason(`Force logout účtu #${userId}.`);
  if (!reason) return;
  if (!confirm(`Ukončit všechny relace uživatele #${userId}?\n\nDůvod: ${reason}`)) return;
  setControlCenterLoading('cc-insight-result');
  try {
    const data = await apiRequest('POST', `/admin-api/control-center/users/${userId}/force-logout`, { reason });
    setControlCenterResult('cc-insight-result', data);
    showSuccess('Relace uživatele byly ukončeny');
    await loadControlCenterUserInsight();
  } catch (error) {
    setControlCenterResult('cc-insight-result', { error: error.message });
  }
}

async function resetUserPasswordFromControlCenter() {
  const userId = getControlCenterSelectedUserId();
  if (!userId) {
    showGlobalError('Nejprve vyberte user ID.');
    return;
  }
  const customPassword = prompt('Nové heslo (nechte prázdné pro náhodné dočasné heslo):', '');
  setControlCenterLoading('cc-insight-result');
  try {
    const data = await apiRequest('POST', `/admin-api/control-center/users/${userId}/reset-password`, {
      new_password: customPassword || null,
      generate_random: !customPassword,
      reason: 'admin_control_center',
    });
    setControlCenterResult('cc-insight-result', data);
    if (data?.temporary_password) {
      showSuccess(`Heslo resetováno. Dočasné heslo: ${data.temporary_password}`);
    } else {
      showSuccess('Heslo bylo resetováno');
    }
    await loadControlCenterUserInsight();
  } catch (error) {
    setControlCenterResult('cc-insight-result', { error: error.message });
  }
}

async function updateUserLicenseFromControlCenter() {
  const userId = getControlCenterSelectedUserId();
  if (!userId) {
    showGlobalError('Nejprve vyberte user ID.');
    return;
  }
  const plan = (document.getElementById('cc-license-plan')?.value || '').trim();
  const status = (document.getElementById('cc-license-status')?.value || '').trim();
  if (!plan && !status) {
    showGlobalError('Vyberte alespoň jednu změnu licence (plan/status).');
    return;
  }
  const reason = await promptAdminReason(`Změna licence účtu #${userId}.`);
  if (!reason) return;
  setControlCenterLoading('cc-insight-result');
  try {
    const data = await apiRequest('POST', `/admin-api/control-center/users/${userId}/license`, {
      plan: plan || null,
      status: status || null,
      source: 'developer_override',
      reason,
    });
    setControlCenterResult('cc-insight-result', data);
    showSuccess('Licence byla aktualizována');
    await Promise.all([loadUsers(), loadControlCenterUsersSnapshot(), loadControlCenterUserInsight()]);
  } catch (error) {
    setControlCenterResult('cc-insight-result', { error: error.message });
  }
}

const CC_NOTIFICATION_HTML_MARKER_JS = '__TOOZH_NOTIFY_HTML_v1\n';

function ccStripNotificationMarker(raw) {
  const s = String(raw ?? '');
  return s.startsWith(CC_NOTIFICATION_HTML_MARKER_JS) ? s.slice(CC_NOTIFICATION_HTML_MARKER_JS.length) : s;
}

/** Bezpečný textový výřez zprávy pro tabulku (bez HTML výstupu). */
function ccNotificationPlainPreviewForTable(row) {
  const raw = row?.message ?? '';
  const kind =
    row?.message_kind || (String(raw).startsWith(CC_NOTIFICATION_HTML_MARKER_JS) ? 'html' : 'plain');
  let t = '';
  if (kind !== 'html') {
    t = String(raw).replace(/\s+/g, ' ').trim();
  } else {
    const div = document.createElement('div');
    div.innerHTML = ccStripNotificationMarker(raw);
    t = String(div.textContent || '').replace(/\s+/g, ' ').trim();
  }
  if (t.length > 220) return `${t.slice(0, 217)}…`;
  return t || '—';
}

function syncCcBroadcastLivePreview() {
  const editor = document.getElementById('cc-broadcast-editor');
  const titleInput = document.getElementById('cc-broadcast-title');
  const previewTitle = document.getElementById('cc-broadcast-preview-title');
  const previewMsg = document.getElementById('cc-broadcast-preview-msg');
  const previewMeta = document.getElementById('cc-broadcast-preview-meta');
  if (!previewTitle || !previewMsg) return;

  const tit = String(titleInput?.value || '').trim() || 'Oznámení';
  previewTitle.textContent = tit;

  const rawHtml = String(editor?.innerHTML || '').trim().replace(/^<br\s*\/?>$/i, '');
  const plain = String(editor?.innerText || '')
    .replace(/\u200b/g, '')
    .replace(/\s+/g, ' ')
    .trim();
  editor?.classList.toggle('is-empty', plain.length === 0);

  if (!plain.length) {
    previewMsg.innerHTML =
      '<span class="cc-broadcast-preview-placeholder">Začněte psát výše…</span>';
  } else {
    previewMsg.innerHTML = rawHtml;
  }

  if (previewMeta) {
    const today = formatDate(new Date().toISOString(), '');
    previewMeta.textContent = today ? today : '';
  }
}

function initControlCenterBroadcastComposer() {
  const moduleRoot = document.getElementById('cc-module-notifications');
  const editor = document.getElementById('cc-broadcast-editor');
  const toolbar = moduleRoot?.querySelector('.cc-broadcast-toolbar');
  const titleEl = document.getElementById('cc-broadcast-title');
  if (!editor || !moduleRoot || editor.dataset.ccComposerBound === '1') return;
  editor.dataset.ccComposerBound = '1';

  syncCcBroadcastLivePreview();

  toolbar?.addEventListener('mousedown', (ev) => {
    const btn = ev.target.closest('[data-cc-cmd]');
    if (!btn || !toolbar.contains(btn)) return;
    ev.preventDefault();
    const cmd = btn.getAttribute('data-cc-cmd');
    editor.focus({ preventScroll: true });
    try {
      document.execCommand(cmd, false, null);
    } catch (_) {
      /* ignore */
    }
    syncCcBroadcastLivePreview();
  });

  editor.addEventListener('input', syncCcBroadcastLivePreview);
  titleEl?.addEventListener('input', syncCcBroadcastLivePreview);
}

async function broadcastControlCenterNotification() {
  const editor = document.getElementById('cc-broadcast-editor');
  const visible = String(editor?.innerText || '')
    .replace(/\u200b/g, '')
    .replace(/\s+/g, ' ')
    .trim();
  const messageHtml = String(editor?.innerHTML || '').trim();
  const title = (document.getElementById('cc-broadcast-title')?.value || '').trim();
  const targetType = (document.getElementById('cc-broadcast-target-type')?.value || 'all').trim();
  const targetValueRaw = (document.getElementById('cc-broadcast-target-value')?.value || '').trim();
  if (visible.length < 3) {
    showGlobalError('Zpráva musí mít alespoň 3 viditelné znaky.');
    return;
  }
  let targetValue = targetValueRaw || null;
  if (targetType === 'all') {
    targetValue = null;
  }
  setControlCenterLoading('cc-notifications-result');
  try {
    const data = await apiRequest('POST', '/admin-api/control-center/notifications/broadcast', {
      message: messageHtml,
      rich: true,
      title: title || null,
      target_type: targetType,
      target_value: targetValue,
      severity: 'info',
    });
    setControlCenterResult('cc-notifications-result', data);
    showSuccess('Broadcast byl odeslán');
    setControlCenterText('cc-notifications-target-preview', targetValue ? `${targetType}:${targetValue}` : targetType);
    if (editor) {
      editor.innerHTML = '';
      syncCcBroadcastLivePreview();
    }
    await loadControlCenterNotifications();
  } catch (error) {
    setControlCenterResult('cc-notifications-result', { error: error.message });
  }
}

async function loadControlCenterNotifications() {
  initControlCenterBroadcastComposer();
  setControlCenterLoading('cc-notifications-result', ['cc-notifications-table']);
  try {
    const data = await apiRequest('GET', '/admin-api/control-center/notifications?limit=50');
    setControlCenterState('notifications', data);
    const items = Array.isArray(data?.items) ? data.items : [];
    renderControlCenterTable(
      'cc-notifications-table',
      [
        { key: 'id', label: '#' },
        { key: 'target_type', label: 'Target', render: (row) => `${escapeHtml(row.target_type || '-')}${row.target_value ? `:${escapeHtml(row.target_value)}` : ''}` },
        { key: 'severity', label: 'Severity', render: (row) => escapeHtml(row.severity || 'info') },
        { key: 'message_kind', label: 'Obsah', render: (row) => escapeHtml(row.message_kind === 'html' ? 'html' : 'text') },
        { key: 'title', label: 'Titulek', render: (row) => escapeHtml(row.title || '-') },
        {
          key: 'message',
          label: 'Zpráva',
          render: (row) => escapeHtml(ccNotificationPlainPreviewForTable(row)),
        },
        { key: 'created_at', label: 'Vytvořeno', render: (row) => formatDateTime(row.created_at) },
      ],
      items,
    );
    setControlCenterResult('cc-notifications-result', data);
    const details = document.getElementById('cc-notifications-details');
    if (details && items.length > 0) {
      details.open = true;
    }
  } catch (error) {
    clearControlCenterTable('cc-notifications-table');
    setControlCenterResult('cc-notifications-result', { error: error.message });
  }
}

async function previewControlCenterStorageCleanup() {
  setControlCenterLoading('cc-infra-result', ['cc-storage-preview-table']);
  try {
    const data = await apiRequest('GET', '/admin-api/control-center/storage/cleanup-preview?logs_days=30&backups_days=30');
    setControlCenterState('storageCleanupPreview', data);
    renderControlCenterTable(
      'cc-storage-preview-table',
      [
        { key: 'label', label: 'Cleanup preview', render: (row) => escapeHtml(row.label) },
        { key: 'value', label: 'Hodnota', render: (row) => escapeHtml(row.value) },
      ],
      [
        { label: 'Confirm text', value: String(data.confirm_text_required || '-') },
        { label: 'Old logs', value: `${formatNumber(data.old_logs_count || 0)} (${data.old_logs_human || '-'})` },
        { label: 'Old backups', value: `${formatNumber(data.old_backups_count || 0)} (${data.old_backups_human || '-'})` },
      ],
    );
    setControlCenterResult('cc-infra-result', data);
  } catch (error) {
    clearControlCenterTable('cc-storage-preview-table');
    setControlCenterResult('cc-infra-result', { error: error.message });
  }
}

async function runControlCenterStorageCleanup() {
  const confirmText = (document.getElementById('cc-storage-cleanup-confirm')?.value || '').trim();
  if (!confirm('Storage cleanup smaže staré logy a backupy. Pokračovat?')) return;
  setControlCenterLoading('cc-infra-result');
  try {
    const data = await apiRequest('POST', '/admin-api/control-center/storage/cleanup', {
      confirm_text: confirmText,
      delete_old_logs_days: 30,
      delete_old_backups_days: 30,
    });
    setControlCenterResult('cc-infra-result', data);
    showSuccess('Storage cleanup dokončen');
    await Promise.all([loadControlCenterStorage(), previewControlCenterStorageCleanup()]);
  } catch (error) {
    setControlCenterResult('cc-infra-result', { error: error.message });
  }
}

async function openControlCenterProblemUsers() {
  let users = Array.isArray(controlCenterDataState.users) ? controlCenterDataState.users : [];
  if (users.length === 0) {
    try {
      users = await fetchAllList('/admin-api/users');
      setControlCenterState('users', users);
    } catch (error) {
      showGlobalError(`Nelze načíst problémové uživatele: ${error.message}`);
      return;
    }
  }

  const problemUsers = users.filter((user) => isUnpaidProblemUser(user));
  renderControlCenterTable(
    'cc-problem-users-table',
    [
      { key: 'id', label: 'User ID', render: (row) => formatNumber(row.id || 0) },
      { key: 'email', label: 'Email', render: (row) => escapeHtml(row.email || '-') },
      { key: 'license_plan', label: 'Plan', render: (row) => escapeHtml(formatAdminLicensePlanLabel(row.license_plan || 'free', row.role || 'user')) },
      { key: 'license_status', label: 'Licence status', render: (row) => escapeHtml(String(row.license_status || 'active')) },
      { key: 'has_paid', label: 'Has paid', render: (row) => row.has_paid ? 'ANO' : 'NE' },
      { key: 'last_paid_at', label: 'Poslední platba', render: (row) => formatDateTime(row.last_paid_at) },
    ],
    problemUsers.slice(0, 120),
  );
  openControlCenterModuleDetails('cc-payments-details');
  setControlCenterResult('cc-payments-result', {
    message: `Filtrovaní problémoví uživatelé: ${problemUsers.length}`,
    count: problemUsers.length,
  });
}

// ============================================
// LOGIN & AUTH
// ============================================

async function handleAdminLogin(event) {
  event.preventDefault();
  hideGlobalError();
  
  const email = document.getElementById('admin-email').value.trim();
  const password = document.getElementById('admin-password').value;
  const errorEl = document.getElementById('login-error');
  
  errorEl.style.display = 'none';
  
  if (!email || !password) {
    errorEl.textContent = 'Vyplňte prosím email a heslo';
    errorEl.classList.remove('hidden');
    return;
  }
  
  try {
    const data = await apiRequest('POST', '/user/login', { email, password });
    
    const role = data?.user?.role;
    if (!role || !['developer_admin', 'admin'].includes(role)) {
      throw new Error('Přístup odepřen. Vyžadována role developer_admin nebo admin.');
    }
    
    setAuthToken(data.access_token);
    setAdminRole(role);
    showDashboard();
    
  } catch (error) {
    errorEl.textContent = error.message || 'Chyba při přihlášení';
    errorEl.classList.remove('hidden');
  }
}

function handleAdminLogout() {
  clearAuthToken();
  showLoginScreen();
}

function showLoginScreen() {
  stopAdminNavbarClock();
  closeAllControlCenterDetails();
  closeAdminMobileNav();
  document.getElementById('login-screen').classList.remove('hidden');
  document.getElementById('dashboard-screen').classList.add('hidden');
  document.getElementById('admin-email').value = '';
  document.getElementById('admin-password').value = '';
  document.getElementById('login-error').classList.add('hidden');
}

function showDashboard() {
  closeAllControlCenterDetails();
  document.getElementById('login-screen').classList.add('hidden');
  document.getElementById('dashboard-screen').classList.remove('hidden');
  hideGlobalError();
  closeAdminMobileNav();

  startAdminNavbarClock();

  initSysNotificationDeactivateDelegation();

  initSectionViewModes();
  
  // Inicializovat navigaci
  initNavigation();

  updateControlCenterVisibility();
  resolveCurrentAdminRole();
  loadSystemCapabilitiesAdmin();
  
  // Načíst přehled jako výchozí
  switchSection('overview');
}

// ============================================
// ADMIN VEHICLE SUPPORT VIEW (read-only + corrections)
// ============================================

const VEHICLE_SUPPORT_VEHICLE_FIELDS = [
  'nickname',
  'brand',
  'model',
  'year',
  'plate',
  'vin',
  'engine',
  'fuel',
  'body_type',
  'notes',
  'stk_valid_until',
  'insurance_provider',
  'insurance_valid_until',
  'tyres_info',
  'current_mileage_km',
  'last_stk_mileage_km',
  'orv_number',
];
const VEHICLE_SUPPORT_SERVICE_FIELDS = ['description', 'mileage', 'note', 'performed_at'];
const VEHICLE_SUPPORT_REMINDER_FIELDS = ['text', 'due_date'];

/** Čitelné popisky pro snapshot (jen UI; backend zůstává beze změny). */
const VEHICLE_SUPPORT_FIELD_LABELS = {
  owner_user_id: 'ID uživatele (vlastník)',
  tenant_id: 'Tenant ID',
  account_email_masked: 'E-mail (maskovaný)',
  support_note: 'Poznámka',
  id: 'ID',
  nickname: 'Přezdívka',
  brand: 'Značka',
  model: 'Model',
  year: 'Rok',
  plate: 'SPZ',
  vin: 'VIN',
  engine: 'Motor',
  fuel: 'Palivo',
  body_type: 'Karoserie',
  notes: 'Poznámka',
  status: 'Stav',
  stk_valid_until: 'STK do',
  insurance_provider: 'Pojišťovna',
  insurance_valid_until: 'POV do',
  orv_number: 'Číslo ORV',
  data_trust_state: 'Důvěra dat',
  created_at: 'Vytvořeno',
  updated_at: 'Upraveno',
  tyres_info: 'Pneumatiky',
  current_mileage_km: 'Aktuální km',
  last_stk_mileage_km: 'Km při STK',
  mileage_checked_at: 'Km zkontrolováno',
  latest_stk_odometer_km: 'STK tachometr (km)',
  latest_stk_odometer_date: 'STK tachometr (datum)',
  latest_stk_sync_at: 'STK sync',
  latest_stk_source: 'STK zdroj',
  latest_stk_import_status: 'STK import',
};

let vehicleSupportContext = { vehicleId: null, snapshot: null };

function labelSupportField(key) {
  return VEHICLE_SUPPORT_FIELD_LABELS[key] || key;
}

(function initVehicleSupportTocNav() {
  const modal = document.getElementById('vehicle-support-modal');
  const toc = modal && modal.querySelector('.vehicle-support-toc');
  if (!toc) return;
  toc.addEventListener('click', (e) => {
    const a = e.target.closest('a.vehicle-support-toc-link');
    if (!a) return;
    e.preventDefault();
    const id = (a.getAttribute('href') || '').replace(/^#/, '');
    if (!id) return;
    const target = document.getElementById(id);
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
})();

function maybeOpenVehicleSupportView(event, vehicleId) {
  if (event.target.closest('.card-actions')) return;
  openVehicleSupportViewModal(vehicleId);
}

function formatSupportScalar(value) {
  if (value === null || value === undefined) return '';
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

function renderSupportKeyValueRows(data) {
  if (!data || typeof data !== 'object') return '<p class="muted vehicle-support-empty">—</p>';
  const parts = [];
  Object.keys(data).forEach((key) => {
    const label = escapeHtml(labelSupportField(key));
    const val = escapeHtml(formatSupportScalar(data[key]));
    parts.push(
      `<div class="vehicle-support-kv-row"><span class="vehicle-support-kv-key">${label}</span><span class="vehicle-support-kv-val">${val}</span></div>`,
    );
  });
  return `<div class="vehicle-support-kv-grid">${parts.join('')}</div>`;
}

function renderSupportTable(headers, rows) {
  if (!rows || rows.length === 0) return '<p class="muted vehicle-support-empty">Žádné záznamy</p>';
  const th = headers.map((h) => `<th>${escapeHtml(h.label)}</th>`).join('');
  const body = rows
    .map((row) => {
      const tds = headers.map((h) => `<td>${escapeHtml(formatSupportScalar(row[h.key]))}</td>`).join('');
      return `<tr>${tds}</tr>`;
    })
    .join('');
  return `<div class="vehicle-support-table-wrap"><table class="vehicle-support-table"><thead><tr>${th}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function openVehicleSupportPhotoLightbox(imageSrc, captionText) {
  const lb = document.getElementById('vehicle-support-photo-lightbox');
  const imgEl = document.getElementById('vehicle-support-photo-lightbox-img');
  const capEl = document.getElementById('vehicle-support-photo-lightbox-caption');
  if (!lb || !imgEl || !imageSrc) return;
  imgEl.src = imageSrc;
  const cap = (captionText || '').trim();
  imgEl.alt = cap || 'Fotografie vozidla';
  if (capEl) {
    if (cap) {
      capEl.textContent = cap;
      capEl.classList.remove('hidden');
    } else {
      capEl.textContent = '';
      capEl.classList.add('hidden');
    }
  }
  lb.classList.remove('hidden');
}

function closeVehicleSupportPhotoLightbox() {
  const lb = document.getElementById('vehicle-support-photo-lightbox');
  const imgEl = document.getElementById('vehicle-support-photo-lightbox-img');
  if (!lb) return;
  lb.classList.add('hidden');
  if (imgEl) {
    imgEl.removeAttribute('src');
    imgEl.alt = '';
  }
  const capEl = document.getElementById('vehicle-support-photo-lightbox-caption');
  if (capEl) {
    capEl.textContent = '';
    capEl.classList.add('hidden');
  }
}

document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  const lb = document.getElementById('vehicle-support-photo-lightbox');
  if (lb && !lb.classList.contains('hidden')) {
    closeVehicleSupportPhotoLightbox();
  }
});

function wireVehicleSupportPhotoClicks(root) {
  if (!root) return;
  root.querySelectorAll('.vehicle-support-photo-card img').forEach((img) => {
    if (!img.getAttribute('data-support-photo')) return;
    img.style.cursor = 'pointer';
    img.setAttribute('tabindex', '0');
    img.setAttribute('role', 'button');
    img.setAttribute('aria-label', 'Zvětšit náhled fotografie');
    const card = img.closest('.vehicle-support-photo-card');
    const meta = card && card.querySelector('.vehicle-support-photo-meta');
    const caption = meta ? meta.textContent.trim() : '';
    const open = () => {
      if (!img.src) return;
      openVehicleSupportPhotoLightbox(img.src, caption);
    };
    img.addEventListener('click', (ev) => {
      ev.preventDefault();
      open();
    });
    img.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter' || ev.key === ' ') {
        ev.preventDefault();
        open();
      }
    });
  });
}

async function hydrateVehicleSupportPhotos(root) {
  const token = getAuthToken();
  if (!root || !token) return;
  const imgs = root.querySelectorAll('img[data-support-photo]');
  const tasks = Array.from(imgs).map(async (img) => {
    const rel = img.getAttribute('data-support-photo');
    if (!rel) return;
    try {
      const res = await fetch(API_BASE + rel, {
        headers: { Authorization: `Bearer ${token}`, Accept: '*/*' },
        credentials: 'include',
      });
      if (!res.ok) {
        img.replaceWith(document.createTextNode('(náhled nedostupný)'));
        return;
      }
      const blob = await res.blob();
      img.src = URL.createObjectURL(blob);
    } catch {
      img.replaceWith(document.createTextNode('(náhled nedostupný)'));
    }
  });
  await Promise.all(tasks);
  wireVehicleSupportPhotoClicks(root);
}

function renderVehicleSupportSnapshot(data) {
  const ownerEl = document.getElementById('vehicle-support-owner');
  const basicEl = document.getElementById('vehicle-support-basic');
  const techEl = document.getElementById('vehicle-support-technical');
  const photosEl = document.getElementById('vehicle-support-photos');
  const docsEl = document.getElementById('vehicle-support-documents');
  const recEl = document.getElementById('vehicle-support-records');
  const remEl = document.getElementById('vehicle-support-reminders');
  const accEl = document.getElementById('vehicle-support-access');
  const tachoEl = document.getElementById('vehicle-support-tacho');
  const auditEl = document.getElementById('vehicle-support-audit');
  if (!ownerEl || !data) return;

  ownerEl.innerHTML = renderSupportKeyValueRows(data.owner_context || {});
  basicEl.innerHTML = renderSupportKeyValueRows(data.vehicle || {});

  const tech = data.technical_data || {};
  let techHtml = renderSupportKeyValueRows({
    tyres_info: tech.tyres_info,
    current_mileage_km: tech.current_mileage_km,
    last_stk_mileage_km: tech.last_stk_mileage_km,
    mileage_checked_at: tech.mileage_checked_at,
    latest_stk_odometer_km: tech.latest_stk_odometer_km,
    latest_stk_odometer_date: tech.latest_stk_odometer_date,
    latest_stk_sync_at: tech.latest_stk_sync_at,
    latest_stk_source: tech.latest_stk_source,
    latest_stk_import_status: tech.latest_stk_import_status,
  });
  if (tech.vehicle_technical_overview) {
    techHtml += `<h4 class="vehicle-support-subheading">Technický přehled (JSON)</h4><pre class="vehicle-support-json-block">${escapeHtml(
      JSON.stringify(tech.vehicle_technical_overview, null, 2),
    )}</pre>`;
  }
  techEl.innerHTML = techHtml;

  const photos = data.photos || [];
  if (photos.length === 0) {
    photosEl.innerHTML = '<p class="muted vehicle-support-empty">Žádné fotografie</p>';
  } else {
    photosEl.innerHTML = `<div class="vehicle-support-photos-grid">${photos
      .map((p) => {
        const src = p.preview_url_admin || '';
        return `<div class="vehicle-support-photo-card"><img data-support-photo="${escapeHtml(src)}" alt="" /><div class="vehicle-support-photo-meta">#${escapeHtml(
          String(p.id),
        )} · ${escapeHtml(p.role || '')} · ${escapeHtml(p.photo_kind || '')}</div></div>`;
      })
      .join('')}</div>`;
    hydrateVehicleSupportPhotos(photosEl);
  }

  docsEl.innerHTML = renderSupportTable(
    [
      { key: 'id', label: 'ID' },
      { key: 'document_type', label: 'Typ' },
      { key: 'document_id', label: 'Dokument' },
      { key: 'status', label: 'Stav' },
      { key: 'finalized_at', label: 'Finalizováno' },
    ],
    data.documents || [],
  );

  recEl.innerHTML = renderSupportTable(
    [
      { key: 'id', label: 'ID' },
      { key: 'performed_at', label: 'Provedeno' },
      { key: 'mileage', label: 'Km' },
      { key: 'description', label: 'Popis' },
      { key: 'record_status', label: 'Stav' },
    ],
    data.service_records || [],
  );

  remEl.innerHTML = renderSupportTable(
    [
      { key: 'id', label: 'ID' },
      { key: 'type', label: 'Typ' },
      { key: 'due_date', label: 'Termín' },
      { key: 'text', label: 'Text' },
      { key: 'is_completed', label: 'Hotovo' },
    ],
    data.reminders || [],
  );

  accEl.innerHTML = renderSupportTable(
    [
      { key: 'id', label: 'ID' },
      { key: 'service_customer_id', label: 'Servis (účet ID)' },
      { key: 'status', label: 'Stav' },
      { key: 'created_at', label: 'Vytvořeno' },
    ],
    data.service_access || [],
  );

  tachoEl.innerHTML = renderSupportTable(
    [
      { key: 'entry_kind', label: 'Druh' },
      { key: 'id', label: 'ID' },
      { key: 'check_date', label: 'Datum kontroly' },
      { key: 'inspection_date', label: 'Datum (STK)' },
      { key: 'mileage_km', label: 'Km' },
      { key: 'odometer_km', label: 'Km (STK řádek)' },
      { key: 'source', label: 'Zdroj' },
      { key: 'status', label: 'Stav' },
      { key: 'imported_at', label: 'Import' },
    ],
    data.tachometer_history || [],
  );

  auditEl.innerHTML = renderSupportTable(
    [
      { key: 'id', label: 'ID' },
      { key: 'action', label: 'Akce' },
      { key: 'entity_type', label: 'Entita' },
      { key: 'occurred_at', label: 'Čas' },
      { key: 'actor_user_id', label: 'Actor' },
    ],
    data.audit_log || [],
  );
}

async function openVehicleSupportViewModal(vehicleId) {
  const modal = document.getElementById('vehicle-support-modal');
  const loading = document.getElementById('vehicle-support-loading');
  const err = document.getElementById('vehicle-support-error');
  const body = document.getElementById('vehicle-support-body');
  if (!modal || !loading || !err || !body) return;
  vehicleSupportContext.vehicleId = Number(vehicleId);
  vehicleSupportContext.snapshot = null;
  modal.classList.remove('hidden');
  loading.classList.remove('hidden');
  err.classList.add('hidden');
  err.textContent = '';
  body.classList.add('hidden');
  try {
    const data = await apiRequest('GET', `/admin-api/vehicles/${vehicleId}/detail-snapshot`);
    vehicleSupportContext.snapshot = data;
    renderVehicleSupportSnapshot(data);
    loading.classList.add('hidden');
    body.classList.remove('hidden');
  } catch (e) {
    loading.classList.add('hidden');
    err.textContent = e.message || String(e);
    err.classList.remove('hidden');
  }
}

function closeVehicleSupportModal() {
  const modal = document.getElementById('vehicle-support-modal');
  if (modal) modal.classList.add('hidden');
}

async function refreshVehicleSupportSnapshot() {
  if (!vehicleSupportContext.vehicleId) return;
  await openVehicleSupportViewModal(vehicleSupportContext.vehicleId);
}

function syncVehicleSupportTargetIdUi() {
  const entEl = document.getElementById('vsc-target-entity');
  const wrap = document.getElementById('vsc-target-id-wrap');
  const inp = document.getElementById('vsc-target-id');
  if (!entEl || !wrap || !inp) return;
  const ent = entEl.value;
  if (ent === 'vehicle') {
    wrap.classList.add('hidden');
    inp.required = false;
    inp.value = '';
  } else {
    wrap.classList.remove('hidden');
    inp.required = true;
  }
}

function syncVehicleSupportCorrectionFields() {
  const ent = document.getElementById('vsc-target-entity')?.value || 'vehicle';
  const sel = document.getElementById('vsc-field');
  if (!sel) return;
  let fields = VEHICLE_SUPPORT_VEHICLE_FIELDS;
  if (ent === 'service_record') fields = VEHICLE_SUPPORT_SERVICE_FIELDS;
  if (ent === 'reminder') fields = VEHICLE_SUPPORT_REMINDER_FIELDS;
  sel.innerHTML = fields.map((f) => `<option value="${escapeHtml(f)}">${escapeHtml(f)}</option>`).join('');
}

function readVehicleSupportOldValueForForm() {
  const snap = vehicleSupportContext.snapshot;
  if (!snap) return '';
  const ent = document.getElementById('vsc-target-entity')?.value || 'vehicle';
  const field = document.getElementById('vsc-field')?.value;
  const targetId = document.getElementById('vsc-target-id')?.value;
  if (!field) return '';
  if (ent === 'vehicle') {
    const v = snap.vehicle ? snap.vehicle[field] : undefined;
    return formatSupportScalar(v);
  }
  if (ent === 'service_record') {
    const id = Number(targetId);
    const row = (snap.service_records || []).find((r) => Number(r.id) === id);
    return row ? formatSupportScalar(row[field]) : '';
  }
  if (ent === 'reminder') {
    const id = Number(targetId);
    const row = (snap.reminders || []).find((r) => Number(r.id) === id);
    return row ? formatSupportScalar(row[field]) : '';
  }
  return '';
}

function updateVehicleSupportOldValueField() {
  const el = document.getElementById('vsc-old-value');
  if (!el) return;
  el.value = readVehicleSupportOldValueForForm();
}

function openVehicleSupportCorrectionDialog() {
  if (!vehicleSupportContext.snapshot || !vehicleSupportContext.vehicleId) {
    showGlobalError('Nejdříve načtěte náhled vozidla.');
    return;
  }
  const modal = document.getElementById('vehicle-support-correction-modal');
  const form = document.getElementById('vehicle-support-correction-form');
  const err = document.getElementById('vsc-form-error');
  if (!modal || !form || !err) return;
  form.reset();
  err.classList.add('hidden');
  err.textContent = '';
  document.getElementById('vsc-target-entity').value = 'vehicle';
  document.getElementById('vsc-notify-user').checked = true;
  syncVehicleSupportTargetIdUi();
  syncVehicleSupportCorrectionFields();
  updateVehicleSupportOldValueField();
  modal.classList.remove('hidden');
}

function closeVehicleSupportCorrectionModal() {
  const modal = document.getElementById('vehicle-support-correction-modal');
  if (modal) modal.classList.add('hidden');
}

async function submitVehicleSupportCorrection(event) {
  event.preventDefault();
  const err = document.getElementById('vsc-form-error');
  const submit = document.getElementById('vsc-submit');
  if (!vehicleSupportContext.vehicleId) return;
  err.classList.add('hidden');
  err.textContent = '';
  const targetEntity = document.getElementById('vsc-target-entity').value;
  const targetIdRaw = document.getElementById('vsc-target-id').value;
  const field = document.getElementById('vsc-field').value;
  const oldValue = document.getElementById('vsc-old-value').value;
  const newValue = document.getElementById('vsc-new-value').value;
  const reason = document.getElementById('vsc-reason').value.trim();
  const notifyUser = document.getElementById('vsc-notify-user').checked;
  if (!reason) {
    err.textContent = 'Vyplňte důvod změny.';
    err.classList.remove('hidden');
    return;
  }
  if (targetEntity !== 'vehicle' && !targetIdRaw) {
    err.textContent = 'Vyplňte ID cílového záznamu.';
    err.classList.remove('hidden');
    return;
  }
  submit.disabled = true;
  try {
    const payload = {
      target_entity: targetEntity,
      target_id: targetEntity === 'vehicle' ? null : String(targetIdRaw),
      field,
      old_value: oldValue,
      new_value: newValue,
      reason,
      notify_user: notifyUser,
    };
    const res = await apiRequest(
      'POST',
      `/admin-api/vehicles/${vehicleSupportContext.vehicleId}/corrections`,
      payload,
    );
    closeVehicleSupportCorrectionModal();
    if (res.notification_status === 'sent') {
      showSuccess('Oprava byla provedena, zapsána do auditu a uživatel byl informován e-mailem.');
    } else if (res.notification_status === 'failed') {
      showSuccess(
        'Oprava byla provedena, ale e-mailové oznámení selhalo. Stav byl zapsán do auditu.',
      );
    } else {
      showSuccess('Oprava byla provedena a zapsána do auditu (oznámení uživateli vynecháno nebo nedostupné).');
    }
    await refreshVehicleSupportSnapshot();
  } catch (e) {
    err.textContent = e.message || String(e);
    err.classList.remove('hidden');
  } finally {
    submit.disabled = false;
  }
}

function initVehicleSupportCorrectionForm() {
  const ent = document.getElementById('vsc-target-entity');
  const field = document.getElementById('vsc-field');
  const tid = document.getElementById('vsc-target-id');
  if (!ent || !field || !tid) return;
  ent.addEventListener('change', () => {
    syncVehicleSupportTargetIdUi();
    syncVehicleSupportCorrectionFields();
    updateVehicleSupportOldValueField();
    document.getElementById('vsc-new-value').value = '';
  });
  field.addEventListener('change', () => {
    updateVehicleSupportOldValueField();
    document.getElementById('vsc-new-value').value = '';
  });
  tid.addEventListener('input', () => {
    updateVehicleSupportOldValueField();
  });
  syncVehicleSupportTargetIdUi();
  syncVehicleSupportCorrectionFields();
}

// ============================================
// INITIALIZATION
// ============================================

window.addEventListener('DOMContentLoaded', () => {
  const token = getAuthToken();
  initVehicleSupportCorrectionForm();

  window.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      closeVehicleSupportCorrectionModal();
      closeVehicleSupportModal();
      closeAdminMobileNav();
      closeAllControlCenterDetails();
    }
  });

  window.addEventListener('resize', () => {
    if (!isAdminMobileViewport()) {
      closeAdminMobileNav();
    }
    if (!window.matchMedia('(min-width: 1101px)').matches) {
      closeAllControlCenterDetails();
      return;
    }
    syncControlCenterDetailsOverlayState();
  });
  
  const userRoleSelect = document.getElementById('user-role');
  if (userRoleSelect && userRoleSelect.dataset.wsBound !== '1') {
    userRoleSelect.addEventListener('change', () => {
      applyDefaultUserWorkspaceCheckboxesFromRole();
    });
    userRoleSelect.dataset.wsBound = '1';
  }

  populateLicensePlanSelect('user-license-plan', userRoleSelect?.value || 'user', document.getElementById('user-license-plan')?.value || 'free', {
    includeBlank: false,
  });
  populateLicensePlanSelect('cc-license-plan', 'user', '', { includeBlank: true, blankLabel: 'beze změny' });

  if (token) {
    // Lehké ověření session; seznam uživatelů se načte až při otevření dané sekce.
    apiRequest('GET', '/user/me')
      .then(() => {
        showDashboard();
      })
      .catch(() => {
        clearAuthToken();
        showLoginScreen();
      });
  } else {
    showLoginScreen();
  }
});

// --- PODPORA (CHAT) ---
let supportWs = null;
let activeChatUserId = null;
let supportSessions = [];
let supportAdminTypingStopTimer = null;
let supportUserTypingByCustomer = {};
let supportAvailability = null;

function getSupportAdminToken() {
  return localStorage.getItem('adminAccessToken') || localStorage.getItem('adminToken') || (typeof getAuthToken === 'function' ? getAuthToken() : '');
}

function formatSupportChatTime(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString('cs-CZ', {
      day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
    });
  } catch (e) {
    return '';
  }
}

function truncateSupportText(text, maxLen) {
  const raw = String(text || '').trim();
  if (raw.length <= maxLen) return raw;
  return raw.slice(0, maxLen - 1) + '…';
}

function isSupportSystemMessage(text) {
  return String(text || '').trim().startsWith('[Offline formulář]');
}

function setSupportWsBadge(connected) {
  const statusBadge = document.getElementById('support-admin-status');
  if (!statusBadge) return;
  statusBadge.textContent = connected ? 'Live chat připojen' : 'Odpojeno';
  statusBadge.classList.toggle('is-connected', !!connected);
  statusBadge.classList.toggle('is-disconnected', !connected);
}

async function loadSupportAvailability() {
  const token = getSupportAdminToken();
  if (!token) return;
  try {
    const res = await fetch('/api/v1/support/status', {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      supportAvailability = await res.json();
      renderSupportAvailabilityBanner();
    }
  } catch (e) {
    console.error('Failed to load support availability', e);
  }
}

function renderSupportAvailabilityBanner() {
  const el = document.getElementById('support-admin-availability');
  if (!el) return;
  if (!supportAvailability) {
    el.innerHTML = '';
    el.className = 'support-admin-availability';
    return;
  }
  const a = supportAvailability;
  el.className = `support-admin-availability is-${a.mode || 'waiting'}`;
  el.innerHTML = `
    <div class="support-admin-avail-card">
      <span class="support-admin-avail-label">Režim podpory</span>
      <strong>${escapeHtml(a.status_label || '—')}</strong>
      <span>Dostupnost: ${escapeHtml(a.business_hours_label || 'Po–Pá 8:00–18:00')} · ${escapeHtml(a.timezone || 'Europe/Prague')}</span>
    </div>`;
}

function refreshSupportChatPanel() {
  loadSupportAvailability();
  loadSupportSessions();
  if (!supportWs || supportWs.readyState !== WebSocket.OPEN) {
    initSupportChat();
  }
}

function notifySupportAdminTyping(active) {
  if (!supportWs || supportWs.readyState !== WebSocket.OPEN || !activeChatUserId) return;
  if (supportAdminTypingStopTimer) clearTimeout(supportAdminTypingStopTimer);
  supportWs.send(JSON.stringify({
    type: 'typing',
    customer_id: activeChatUserId,
    active: !!active,
  }));
  if (active) {
    supportAdminTypingStopTimer = setTimeout(() => notifySupportAdminTyping(false), 2500);
  }
}

function updateSupportUserTypingIndicator(customerId, active) {
  supportUserTypingByCustomer[customerId] = !!active;
  const typingEl = document.getElementById('support-chat-user-typing');
  if (typingEl) {
    if (activeChatUserId === customerId && active) {
      typingEl.hidden = false;
      typingEl.textContent = 'Uživatel píše…';
    } else {
      typingEl.hidden = true;
      typingEl.textContent = '';
    }
  }
  const session = supportSessions.find((s) => s.customer_id === customerId);
  if (session) updateSupportSessionStatusLabel(session);
  renderSupportChatList();
}

function updateSupportSessionStatusLabel(session) {
  const statusEl = document.getElementById('support-chat-session-status');
  const headerDot = document.getElementById('support-chat-user-online-dot');
  if (!session || !statusEl) return;
  const cid = session.customer_id;
  if (supportUserTypingByCustomer[cid]) {
    statusEl.textContent = 'Uživatel píše…';
    statusEl.className = 'support-chat-session-status is-typing';
  } else if (session.is_online) {
    statusEl.textContent = 'Uživatel je online v chatu';
    statusEl.className = 'support-chat-session-status is-online';
  } else {
    statusEl.textContent = 'Uživatel offline';
    statusEl.className = 'support-chat-session-status is-offline';
  }
  if (headerDot) {
    headerDot.classList.toggle('is-online', !!session.is_online);
  }
}

function updateSupportChatHeader(session) {
  const header = document.getElementById('support-chat-header');
  const emailEl = document.getElementById('support-chat-user-email');
  const metaEl = document.getElementById('support-chat-header-meta');
  const inputArea = document.getElementById('support-chat-input-area');
  if (!session) {
    if (header) header.hidden = true;
    if (inputArea) inputArea.hidden = true;
    return;
  }
  if (header) header.hidden = false;
  if (inputArea) inputArea.hidden = false;
  if (emailEl) emailEl.textContent = session.customer_email || 'Neznámý';
  if (metaEl) {
    metaEl.textContent = session.customer_name
      ? `${session.customer_name} · ID ${session.customer_id}`
      : `ID ${session.customer_id}`;
  }
  updateSupportSessionStatusLabel(session);
}

function initSupportChat() {
  const token = getSupportAdminToken();
  if (!token) return;
  if (supportWs && (supportWs.readyState === WebSocket.OPEN || supportWs.readyState === WebSocket.CONNECTING)) {
    return;
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/api/v1/support/ws/admin?token=${token}`;
  supportWs = new WebSocket(wsUrl);

  supportWs.onopen = () => {
    console.log('Admin Support WS connected');
    setSupportWsBadge(true);
    loadSupportSessions();
    loadSupportAvailability();
  };

  supportWs.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'message') {
      handleIncomingSupportMessage(data);
    } else if (data.type === 'typing') {
      if (data.sender_type === 'user' && data.customer_id) {
        updateSupportUserTypingIndicator(data.customer_id, !!data.active);
      }
    }
  };

  supportWs.onclose = () => {
    console.log('Admin Support WS disconnected');
    setSupportWsBadge(false);
    supportWs = null;
    setTimeout(initSupportChat, 5000);
  };
}

async function loadSupportSessions() {
  const token = getSupportAdminToken();
  if (!token) return;

  try {
    const res = await fetch('/api/v1/support/admin/sessions', {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      const data = await res.json();
      const prevUnread = new Map(supportSessions.map((s) => [s.customer_id, s.unread]));
      const prevMessages = new Map(supportSessions.map((s) => [s.customer_id, s.messages]));
      supportSessions = data.map((s) => ({
        ...s,
        unread: prevUnread.get(s.customer_id) || false,
        messages: prevMessages.get(s.customer_id) || s.messages || null,
      }));
      renderSupportChatList();
      if (activeChatUserId) {
        const active = supportSessions.find((s) => s.customer_id === activeChatUserId);
        if (active) updateSupportChatHeader(active);
        renderSupportChatMessages(activeChatUserId);
      }
    }
  } catch (e) {
    console.error('Failed to load support sessions', e);
  }
}

function renderSupportChatList() {
  const listEl = document.getElementById('support-chat-list');
  const countEl = document.getElementById('support-chat-list-count');
  if (!listEl) return;
  if (countEl) countEl.textContent = String(supportSessions.length);

  if (supportSessions.length === 0) {
    listEl.innerHTML = '<div class="support-admin-empty">Žádné aktivní chaty</div>';
    return;
  }

  listEl.innerHTML = '';
  supportSessions.forEach((session) => {
    const item = document.createElement('button');
    item.type = 'button';
    item.className = 'support-admin-chat-item';
    if (activeChatUserId === session.customer_id) item.classList.add('is-active');
    if (session.unread) item.classList.add('is-unread');

    const isTyping = !!supportUserTypingByCustomer[session.customer_id];
    const preview = isTyping
      ? '<div class="support-admin-chat-item-typing">Uživatel píše…</div>'
      : `<div class="support-admin-chat-item-preview">${escapeHtml(truncateSupportText(session.last_message || 'Nový chat', 80))}</div>`;

    item.innerHTML = `
      <div class="support-admin-chat-item-row">
        <span class="support-admin-online-dot${session.is_online ? ' is-online' : ''}" aria-hidden="true"></span>
        <span class="support-admin-chat-item-email">${escapeHtml(session.customer_email || 'Neznámý')}</span>
      </div>
      ${preview}
      <div class="support-admin-chat-item-meta">
        <span>${escapeHtml(session.customer_name || `ID ${session.customer_id}`)}</span>
        <span>${escapeHtml(formatSupportChatTime(session.last_message_time))}</span>
      </div>`;

    item.addEventListener('click', () => { void openSupportAdminChat(session.customer_id); });
    listEl.appendChild(item);
  });
}

async function openSupportAdminChat(customerId) {
  const session = supportSessions.find((s) => s.customer_id === customerId);
  if (!session) return;

  session.unread = false;
  updateSupportBadge();
  activeChatUserId = customerId;
  updateSupportChatHeader(session);

  const token = getSupportAdminToken();
  try {
    const res = await fetch(`/api/v1/support/admin/sessions/${session.session_id}/messages`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      session.messages = await res.json();
    }
  } catch (e) {
    console.error('Failed to load session messages', e);
  }

  renderSupportChatList();
  renderSupportChatMessages(customerId);
}

function renderSupportChatMessages(userId) {
  const session = supportSessions.find((s) => s.customer_id === userId);
  const messagesEl = document.getElementById('support-chat-messages');
  if (!messagesEl) return;

  if (!session || !session.messages || session.messages.length === 0) {
    messagesEl.innerHTML = '<div class="support-admin-empty support-admin-empty-center">Zatím žádné zprávy — napište uživateli první odpověď.</div>';
    return;
  }

  messagesEl.innerHTML = '';
  session.messages.forEach((msg) => {
    appendMessageToUI(msg.text, msg.sender_type, msg.created_at, false);
  });
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function appendMessageToUI(text, senderType, createdAt, scroll) {
  const messagesEl = document.getElementById('support-chat-messages');
  if (!messagesEl) return;

  const empty = messagesEl.querySelector('.support-admin-empty-center');
  if (empty) empty.remove();

  const isSystem = isSupportSystemMessage(text);
  const isAdmin = senderType === 'admin';
  const msgDiv = document.createElement('div');
  msgDiv.className = 'support-admin-msg' + (isSystem ? ' is-system' : (isAdmin ? ' is-admin' : ' is-user'));

  const label = isSystem ? 'Systém' : (isAdmin ? 'Vy (operátor)' : 'Uživatel');
  const body = escapeHtml(text).replace(/\n/g, '<br>');
  const time = formatSupportChatTime(createdAt);
  msgDiv.innerHTML = `
    <span class="support-admin-msg-label">${label}</span>
    ${body}
    ${time ? `<span class="support-admin-msg-time">${escapeHtml(time)}</span>` : ''}`;

  messagesEl.appendChild(msgDiv);
  if (scroll !== false) messagesEl.scrollTop = messagesEl.scrollHeight;
}

function updateSupportBadge() {
  const unreadCount = supportSessions.filter((s) => s.unread).length;
  const navBtn = document.querySelector('.nav-item[data-section="support-chat"]');
  if (!navBtn) return;

  let badge = navBtn.querySelector('.chat-badge');
  if (unreadCount > 0) {
    if (!badge) {
      navBtn.style.position = 'relative';
      badge = document.createElement('span');
      badge.className = 'chat-badge';
      badge.style.position = 'absolute';
      badge.style.right = '12px';
      badge.style.top = '50%';
      badge.style.transform = 'translateY(-50%)';
      badge.style.background = '#ef4444';
      badge.style.color = '#fff';
      badge.style.fontSize = '11px';
      badge.style.fontWeight = 'bold';
      badge.style.minWidth = '18px';
      badge.style.height = '18px';
      badge.style.borderRadius = '50%';
      badge.style.display = 'flex';
      badge.style.alignItems = 'center';
      badge.style.justifyContent = 'center';
      badge.style.padding = '0 4px';
      navBtn.appendChild(badge);
    }
    badge.textContent = unreadCount;
  } else if (badge) {
    badge.remove();
  }
}

function handleIncomingSupportMessage(data) {
  if (data.customer_id) {
    updateSupportUserTypingIndicator(data.customer_id, false);
  }

  let session = supportSessions.find((s) => s.customer_id === data.customer_id);
  if (!session) {
    session = {
      session_id: data.session_id,
      customer_id: data.customer_id,
      customer_email: data.customer_email || 'Neznámý',
      customer_name: data.customer_name || '',
      messages: [],
      unread: false,
      is_online: true,
      last_message: data.text,
      last_message_time: data.created_at,
    };
    supportSessions.unshift(session);
  }

  if (!session.messages) session.messages = [];
  session.messages.push({
    sender_type: data.sender_type,
    text: data.text,
    created_at: data.created_at,
  });
  session.last_message = data.text;
  session.last_message_time = data.created_at;

  if (activeChatUserId === data.customer_id && currentSection === 'support-chat') {
    appendMessageToUI(data.text, data.sender_type, data.created_at);
    session.unread = false;
    updateSupportChatHeader(session);
  } else if (data.sender_type !== 'admin') {
    if (!session.unread) {
      showSuccess(`Nová zpráva na podpoře od: ${session.customer_email}`);
    }
    session.unread = true;
  }

  renderSupportChatList();
  updateSupportBadge();
}

document.addEventListener('DOMContentLoaded', () => {
  const sendBtn = document.getElementById('support-chat-send');
  const input = document.getElementById('support-chat-input');

  if (sendBtn && input) {
    const sendMsg = () => {
      const text = input.value.trim();
      if (!text || !activeChatUserId || !supportWs || supportWs.readyState !== WebSocket.OPEN) return;

      const session = supportSessions.find((s) => s.customer_id === activeChatUserId);
      if (!session) return;

      notifySupportAdminTyping(false);
      supportWs.send(JSON.stringify({
        type: 'message',
        customer_id: activeChatUserId,
        session_id: session.session_id,
        text,
      }));

      input.value = '';
    };

    sendBtn.addEventListener('click', sendMsg);
    input.addEventListener('input', () => notifySupportAdminTyping(true));
    input.addEventListener('blur', () => notifySupportAdminTyping(false));
    input.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') sendMsg();
    });
  }

  if (getSupportAdminToken()) {
    initSupportChat();
  }
});

window.refreshSupportChatPanel = refreshSupportChatPanel;

// Hook into login/logout
const originalHandleAdminLogin = window.handleAdminLogin;
window.handleAdminLogin = async function(e) {
    if (originalHandleAdminLogin) await originalHandleAdminLogin(e);
    if (localStorage.getItem('adminAccessToken') || localStorage.getItem('adminToken')) {
        initSupportChat();
    }
};

const originalHandleAdminLogout = window.handleAdminLogout;
window.handleAdminLogout = function() {
    if (supportWs) {
        supportWs.close();
        supportWs = null;
    }
    if (originalHandleAdminLogout) originalHandleAdminLogout();
};
