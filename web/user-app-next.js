(function () {
  'use strict';

  const STATE = {
    installed: false,
    renderToken: 0,
    lastVehicles: [],
    latestData: null,
    vehiclesFilter: 'all',
    vehiclesSort: 'activity',
    vehiclesSearchQuery: '',
    vehiclesReorderMode: false,
    vehiclesManageHint: null,
    reorderDraftOrder: null,
    garageVehicleOrder: null,
    detailModal: { open: false, vehicleId: null, activeTab: 'tech', vehicle: null, records: [], optionsOpen: false },
    attentionModalOpen: false,
    attentionItems: [],
    legacyDetailReadyFor: null,
    legacyMount: { tabId: null },
    settingsPanel: 'profile',
    originalShowVehicleDetail: null,
    modalEscBound: false,
    viewOverride: null,
    remindersTipHidden: false,
    serviceHistoryLimit: 8,
    serviceHistoryFilters: { vehicle: 'all', period: '2y', type: 'all', service: 'all', docStatus: 'all' },
    documentsTipHidden: false,
    documentsFiltersOpen: false,
    documentsFilters: { search: '', category: 'all', type: 'all', vehicle: 'all' },
    documentsPage: 1,
    documentsPerPage: 10,
    documentsSort: { key: 'uploadedAt', dir: 'desc' },
    documentsMenuOpenId: null,
    documentsUploadPickerOpen: false,
    servicesDirectoryView: 'map',
    servicesDirectoryRadius: 50,
    servicesDirectoryUseLocation: true,
    servicesDirectorySort: 'distance',
    servicesDirectoryLimit: 30,
    servicesDirectoryTipHidden: false,
    servicesDirectoryFilters: { type: 'all', service: 'all', rating: '0', inAppOnly: false, authorizedOnly: false },
    servicesMapRows: [],
    servicesMapCategory: 'all',
    servicesMapSearchQ: '',
    servicesMapVerifiedOnly: false,
    servicesMapBounds: null,
    servicesMapHint: '',
    servicesMapTotal: 0,
    servicesMapBoundsDebounce: null,
    servicesMapControlsOpen: false,
    servicesOsmRows: [],
    servicesOsmLoading: false,
    servicesOsmError: null,
    servicesOsmLoadToken: 0,
    lastRenderedView: null,
    mapsConfig: undefined,
    leafletLoadPromise: null,
    leafletClusterLoadPromise: null,
    googleMapsLoadPromise: null,
    servicesMapRuntime: null,
    servicesLocationLabel: '',
    servicesLocationSuggestDebounce: null,
    servicesSearchDebounce: null,
    serviceAddressCache: {},
    serviceAddressResolveToken: 0,
  };

  const DETAIL_MODAL_ID = 'uappNextVehicleDetail';
  const ATTENTION_MODAL_ID = 'uappNextAttentionModal';

  const LOGO_SRC = '/web/assets/landing/sprava-vozidel-logo.jpeg';
  const USER_APP_SCREEN_ID = 'userAppNextScreen';
  const USER_INVOICES_ENABLED = window.FEATURE_USER_INVOICES_STAGING_ONLY === true;

  const ICO = {
    home: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/></svg>',
    car: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M18.92 6.01C18.72 5.42 18.16 5 17.5 5h-11c-.66 0-1.21.42-1.42 1.01L3 12v8c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1h12v1c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-8l-2.08-5.99zM6.5 16c-.83 0-1.5-.67-1.5-1.5S5.67 13 6.5 13s1.5.67 1.5 1.5S7.33 16 6.5 16zm11 0c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zM5 11l1.5-4.5h11L19 11H5z"/></svg>',
    wrench: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M22.7 19l-9.1-9.1c.9-2.3.4-5-1.5-6.9-2-2-5-2.4-7.4-1.3L9 6 6 9 1.6 4.7C.4 7.1.9 10.1 2.9 12.1c1.9 1.9 4.6 2.4 6.9 1.5l9.1 9.1c.4.4 1 .4 1.4 0l2.3-2.3c.5-.4.5-1.1.1-1.4z"/></svg>',
    bell: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z"/></svg>',
    doc: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>',
    building: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 7V3H2v18h20V7H12zM6 19H4v-2h2v2zm0-4H4v-2h2v2zm0-4H4V9h2v2zm0-4H4V5h2v2zm4 12H8v-2h2v2zm0-4H8v-2h2v2zm0-4H8V9h2v2zm0-4H8V5h2v2zm10 12h-8v-2h2v-2h-2v-2h2v-2h-2V9h8v10zm-2-8h-2v2h2v-2zm0 4h-2v2h2v-2z"/></svg>',
    invoice: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>',
    gear: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M19.14 12.94c.04-.31.06-.63.06-.94 0-.31-.02-.63-.06-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.04.31-.06.63-.06.94s.02.63.06.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/></svg>',
    calendar: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M19 4h-1V2h-2v2H8V2H6v2H5c-1.11 0-1.99.9-1.99 2L3 20c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V10h14v10zM7 12h5v5H7z"/></svg>',
    support: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 1c-4.97 0-9 4.03-9 9v7c0 1.66 1.34 3 3 3h1v-8H5c-.55 0-1-.45-1-1 0-4.42 3.58-8 8-8s8 3.58 8 8c0 .55-.45 1-1 1h-2v8h1c1.66 0 3-1.34 3-3v-7c0-4.97-4.03-9-9-9z"/></svg>',
    search: '<svg class="uapp-next-search-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0016 9.5 6.5 6.5 0 109.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>',
    quickStk: '<svg class="uapp-next-quick-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z"/></svg>',
    quickShield: '<svg class="uapp-next-quick-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z"/></svg>',
    share: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M18 16.08c-.76 0-1.44.3-1.96.77L8.91 12.7c.05-.23.09-.46.09-.7s-.04-.47-.09-.7l7.05-4.11c.54.5 1.25.81 2.04.81 1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3c0 .24.04.47.09.7L8.04 9.81C7.5 9.31 6.79 9 6 9c-1.66 0-3 1.34-3 3s1.34 3 3 3c.79 0 1.5-.31 2.04-.81l7.12 4.16c-.05.21-.08.43-.08.65 0 1.61 1.31 2.92 2.92 2.92s2.92-1.31 2.92-2.92-1.31-2.92-2.92-2.92z"/></svg>',
    detail: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>',
    edit: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>',
    upload: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M9 16h6v-6h4l-7-7-7 7h4v6zm-4 2h14v2H5v-2z"/></svg>',
    folder: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/></svg>',
    filter: '<svg class="uapp-doc-filter-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M10 18h4v-2h-4v2zM3 6v2h18V6H3zm3 7h12v-2H6v2z"/></svg>',
    download: '<svg class="uapp-doc-action-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>',
    more: '<svg class="uapp-doc-action-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"/></svg>',
    odometer: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67V7z"/></svg>',
    pdf: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>',
    qr: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M3 3h8v8H3V3zm2 2v4h4V5H5zm8-2h8v8h-8V3zm2 2v4h4V5h-4zM3 13h8v8H3v-8zm2 2v4h4v-4H5zm13-2h3v2h-3v-2zM14 13h2v3h-2v-3zm3 3h2v2h-2v-2zm-3 0h2v2h-2v-2zm3 3h2v3h-2v-3zm-3 0h2v2h-2v-2z"/></svg>',
    checkOk: '<svg class="uapp-next-overall-ico uapp-next-overall-ico--ok" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>',
    checkWarn: '<svg class="uapp-next-overall-ico uapp-next-overall-ico--warn" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg>',
  };

  const PLATE_EU_STARS_SVG = (function buildPlateEuStarsSvg() {
    const cx = 9;
    const cy = 9;
    const r = 5.15;
    const star = 'M0,-0.95 L0.22,-0.3 L0.95,-0.3 L0.36,0.12 L0.58,0.82 L0,0.38 L-0.58,0.82 L-0.36,0.12 L-0.95,-0.3 L-0.22,-0.3 Z';
    let paths = '';
    for (let i = 0; i < 12; i += 1) {
      const rad = ((i * 30) - 90) * (Math.PI / 180);
      const x = cx + r * Math.cos(rad);
      const y = cy + r * Math.sin(rad);
      paths += `<path d="${star}" transform="translate(${x.toFixed(2)} ${y.toFixed(2)}) scale(0.36)"/>`;
    }
    return `<svg class="uapp-plate__eu-stars" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><g fill="#FFCC00">${paths}</g></svg>`;
  })();

  function hasFn(name) {
    return typeof window[name] === 'function';
  }

  function esc(value) {
    if (typeof window.escapeHtml === 'function') {
      return window.escapeHtml(value == null ? '' : String(value));
    }
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function user() {
    try {
      return typeof currentUser !== 'undefined' ? currentUser : null;
    } catch (_) {
      return null;
    }
  }

  function apiReady() {
    return typeof apiCall === 'function';
  }

  function isAuthed() {
    try {
      return typeof isAuthenticated === 'function' && isAuthenticated();
    } catch (_) {
      return false;
    }
  }

  function isServiceMode() {
    try {
      return typeof isServiceWorkspaceRole === 'function' && isServiceWorkspaceRole();
    } catch (_) {
      return false;
    }
  }

  const LEGACY_SECTION_META = {
    support: { tabId: 'supportTab', testId: 'user-app-next-support' },
    reservations: { tabId: 'reservationsTab', testId: 'user-app-next-reservations' },
  };

  const FEATURE_TO_LICENSE_TAB = {
    documents: 'documents',
    reservations: 'reservations',
    service_discovery: 'servicesDirectory',
    service_partners: 'servicesDirectory',
    servicesDirectory: 'servicesDirectory',
    vin_mdcr_decode: 'vin',
    vin: 'vin',
    vehicleHistory: 'vehicleHistory',
    costs: 'costs',
  };

  function canAccessFeature(featureKey) {
    if (isServiceMode()) return true;
    const tabKey = FEATURE_TO_LICENSE_TAB[featureKey] || featureKey;
    if (tabKey === 'invoices') return USER_INVOICES_ENABLED === true;
    if (tabKey === 'ai_features' || tabKey === 'ai') {
      return window.FEATURE_ENABLE_AI_FEATURES === true || window.ENABLE_AI_FEATURES === true;
    }
    if (typeof window.getDashboardTabLicenseLock === 'function') {
      const lock = window.getDashboardTabLicenseLock(tabKey, null);
      return !(lock && lock.allowed === false);
    }
    const flags = window.__licenseFlags;
    if (flags && typeof flags === 'object') {
      if (tabKey === 'documents') return !!flags.documentsEnabled;
      if (tabKey === 'reservations') return !!flags.reservationsEnabled;
      if (tabKey === 'servicesDirectory') return !!flags.sharingWithServiceEnabled;
      if (tabKey === 'vin') return !!flags.vinEnabled;
      if (tabKey === 'vehicleHistory') return !!flags.vehicleHistoryEnabled;
    }
    return true;
  }

  function showFeatureLock(featureKey) {
    const message = getUserAppLockedMessage(featureKey);
    if (typeof window.showDashboardUpgradePrompt === 'function') {
      window.showDashboardUpgradePrompt(featureKey);
      return;
    }
    alert(message);
  }

  window.canAccessFeature = canAccessFeature;

  function getUserAppLockedMessage(featureKey) {
    if (typeof window.getLicenseLockedMessage === 'function') {
      try { return window.getLicenseLockedMessage(featureKey); } catch (_) {}
    }
    const key = String(featureKey || '').trim();
    if (key === 'vin' || key === 'vin_mdcr_decode') {
      return 'Tato funkce je dostupná v licenci Premium. Pro automatické načtení údajů z VIN si aktivujte Premium licenci.';
    }
    if (key === 'documents') return 'Dokumenty a PDF exporty jsou dostupné od licence Basic.';
    if (key === 'reservations') return 'Objednání servisu je dostupné od licence Basic.';
    if (key === 'servicesDirectory' || key === 'service_discovery' || key === 'service_partners') {
      return 'Servisní partneři a mapa servisů jsou dostupní v licenci Premium.';
    }
    return 'Tato funkce je dostupná po zakoupení odpovídající licence.';
  }

  function getSidebarLockFlags() {
    return {
      documents: !canAccessFeature('documents'),
      reservations: !canAccessFeature('reservations'),
      servicesDirectory: !canAccessFeature('servicesDirectory'),
    };
  }

  function navigateLicensedTab(tabName, featureKey) {
    const key = featureKey || tabName;
    if (!canAccessFeature(key)) {
      showFeatureLock(key);
      return;
    }
    closeMobileNav();
    if (LEGACY_SECTION_META[tabName] || tabName === 'reservations' || tabName === 'support') {
      STATE.viewOverride = tabName;
    } else {
      STATE.viewOverride = tabName;
    }
    if (hasFn('switchTab')) return window.switchTab(tabName);
    return render();
  }

  function getActiveView() {
    if (STATE.viewOverride) return STATE.viewOverride;
    if (!document.body.classList.contains('route-app-view') || !isAuthed() || isServiceMode()) {
      return null;
    }
    const pathname = String(window.location.pathname || '');
    if (/\/settings(?:\/|$)/i.test(pathname)) {
      return 'settings';
    }
    if (/\/service-history(?:\/|$)/i.test(pathname)) {
      return 'serviceHistory';
    }
    const appShell = document.getElementById('app-shell');
    if (!appShell || appShell.hidden) return null;
    const viewByTabId = {
      homeTab: 'home',
      vehiclesTab: 'vehicles',
      remindersTab: 'reminders',
      documentsTab: 'documents',
      servicesDirectoryTab: 'servicesDirectory',
      accountTab: 'settings',
      supportTab: 'settings',
      reservationsTab: 'reservations',
    };
    if (USER_INVOICES_ENABLED) viewByTabId.invoicesTab = 'invoices';
    for (const [tabId, view] of Object.entries(viewByTabId)) {
      const tab = document.getElementById(tabId);
      if (tab && tab.classList.contains('active')) return view;
    }
    return null;
  }

  function shouldActivate() {
    return getActiveView() !== null;
  }

  function getStoredViewMode() {
    if (hasFn('getVehicleViewMode')) {
      try {
        const mode = window.getVehicleViewMode();
        if (mode === 'grid' || mode === 'list' || mode === 'compact') return mode;
      } catch (_) {}
    }
    return 'grid';
  }

  function stkCatalogLabel(vehicle) {
    const meta = stkFieldMeta(vehicle);
    const raw = getStkValue(vehicle);
    const diff = daysUntil(raw);
    if (diff != null && diff >= 0) {
      if (diff === 0) return { label: 'dnes', tone: meta.tone };
      if (diff === 1) return { label: 'do 1 dne', tone: meta.tone };
      return { label: `do ${diff} dnů`, tone: meta.tone };
    }
    return { label: meta.label, tone: meta.tone };
  }

  function lastServiceLabel(records) {
    const list = Array.isArray(records) ? records.slice() : [];
    if (!list.length) return { label: 'Bez záznamu', tone: 'muted' };
    list.sort((a, b) => (Date.parse(b?.performed_at || b?.created_at) || 0) - (Date.parse(a?.performed_at || a?.created_at) || 0));
    const latest = list[0];
    const status = String(latest?.record_status || '').toLowerCase();
    if (status === 'in_progress' || status === 'draft') {
      return { label: 'právě probíhá', tone: 'bad' };
    }
    const months = monthsSince(latest?.performed_at || latest?.created_at);
    if (months == null) return { label: 'Záznam k dispozici', tone: 'ok' };
    if (months <= 0) return { label: 'tento měsíc', tone: 'ok' };
    if (months === 1) return { label: 'před 1 měsícem', tone: 'ok' };
    return { label: `před ${months} měsíci`, tone: 'ok' };
  }

  function getCatalogVehicleStatus(vehicle, records) {
    if (String(vehicle?.status || '').toLowerCase() === 'archived') {
      return { key: 'archived', label: 'V archivu', tone: 'archived' };
    }
    const openService = (records || []).some((record) => {
      const st = String(record?.record_status || '').toLowerCase();
      return st === 'in_progress' || st === 'draft';
    });
    if (openService) {
      return { key: 'service', label: 'V servisu', tone: 'service' };
    }
    const stk = stkFieldMeta(vehicle);
    const ins = insuranceFieldMeta(vehicle);
    if (stk.tone === 'bad' || ins.tone === 'bad' || stk.tone === 'warn' || ins.tone === 'warn') {
      return { key: 'attention', label: 'Vyžaduje pozornost', tone: 'warn' };
    }
    return { key: 'ok', label: 'V pořádku', tone: 'ok' };
  }

  function catalogBadgeClass(tone) {
    if (tone === 'warn') return 'uapp-next-badge uapp-next-badge--warn';
    if (tone === 'service' || tone === 'bad') return 'uapp-next-badge uapp-next-badge--danger';
    if (tone === 'archived') return 'uapp-next-badge uapp-next-badge--muted';
    return 'uapp-next-badge uapp-next-badge--ok';
  }

  function getFilterCounts(data) {
    const counts = { all: 0, ok: 0, attention: 0, service: 0, archived: 0 };
    (data.vehicles || []).forEach((vehicle) => {
      counts.all += 1;
      const status = getCatalogVehicleStatus(vehicle, recordsFor(data, vehicle.id));
      if (status.key === 'ok') counts.ok += 1;
      else if (status.key === 'attention') counts.attention += 1;
      else if (status.key === 'service') counts.service += 1;
      else if (status.key === 'archived') counts.archived += 1;
    });
    return counts;
  }

  function filterCatalogVehicles(data, filter, query) {
    const q = String(query || '').trim().toLowerCase();
    let list = (data.vehicles || []).slice();
    if (q) {
      list = list.filter((vehicle) => {
        const hay = [getVehicleName(vehicle), vehicle.plate, vehicle.vin, vehicle.brand, vehicle.model].filter(Boolean).join(' ').toLowerCase();
        return hay.includes(q);
      });
    }
    if (filter === 'all') return list;
    return list.filter((vehicle) => getCatalogVehicleStatus(vehicle, recordsFor(data, vehicle.id)).key === filter);
  }

  function getGarageVehicleOrder() {
    const raw = STATE.garageVehicleOrder != null ? STATE.garageVehicleOrder : window.__garageVehicleOrder;
    if (!Array.isArray(raw)) return [];
    return raw.map((id) => Number(id)).filter((id) => Number.isFinite(id) && id > 0);
  }

  function applyCustomVehicleOrder(list, order) {
    if (!order || !order.length) return list;
    const index = new Map(order.map((id, idx) => [Number(id), idx]));
    return list.slice().sort((a, b) => {
      const ia = index.has(Number(a.id)) ? index.get(Number(a.id)) : 9999;
      const ib = index.has(Number(b.id)) ? index.get(Number(b.id)) : 9999;
      if (ia !== ib) return ia - ib;
      return getVehicleName(a).localeCompare(getVehicleName(b), 'cs');
    });
  }

  function sortCatalogVehicles(list, data, sortKey) {
    const copy = list.slice();
    if (sortKey === 'custom') {
      return applyCustomVehicleOrder(copy, getGarageVehicleOrder());
    }
    if (sortKey === 'name') {
      copy.sort((a, b) => getVehicleName(a).localeCompare(getVehicleName(b), 'cs'));
      return copy;
    }
    const rank = { service: 0, attention: 1, ok: 2, archived: 3 };
    copy.sort((a, b) => {
      const sa = getCatalogVehicleStatus(a, recordsFor(data, a.id)).key;
      const sb = getCatalogVehicleStatus(b, recordsFor(data, b.id)).key;
      const da = rank[sa] != null ? rank[sa] : 9;
      const db = rank[sb] != null ? rank[sb] : 9;
      if (da !== db) return da - db;
      const ra = (recordsFor(data, a.id)[0]?.performed_at || recordsFor(data, a.id)[0]?.created_at || '');
      const rb = (recordsFor(data, b.id)[0]?.performed_at || recordsFor(data, b.id)[0]?.created_at || '');
      return (Date.parse(rb) || 0) - (Date.parse(ra) || 0);
    });
    return copy;
  }

  function fullName() {
    const u = user() || {};
    const raw = String(u.name || u.email || '').trim();
    if (!raw) return 'uživateli';
    const visible = raw.includes('@') ? raw.split('@')[0].replace(/[._-]+/g, ' ') : raw;
    return visible.split(/\s+/).filter(Boolean)[0] || 'uživateli';
  }

  function profileName() {
    const u = user() || {};
    return String(u.name || fullName()).trim() || 'Profil';
  }

  function initials() {
    const u = user() || {};
    const source = String(u.name || u.email || 'SV').trim();
    return source
      .split(/[\s@._-]+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part.charAt(0).toUpperCase())
      .join('') || 'SV';
  }

  function profileTopbarTrialBadgeHtml() {
    const lic = window.__profileTopbarLicenseUi;
    if (lic && lic.trial_active) {
      const raw = lic.trial_days_remaining;
      if (raw != null && raw !== '' && Number.isFinite(Number(raw))) {
        const days = Math.max(0, Math.floor(Number(raw)));
        return `<span class="uapp-settings-trial-badge">Trial ${esc(String(days))} dní</span>`;
      }
      return '<span class="uapp-settings-trial-badge">Trial</span>';
    }

    const label = document.getElementById('licenseQuickLabel')?.textContent?.trim() || '';
    const current = document.getElementById('licenseQuickCurrent')?.textContent?.trim() || '';
    const isTrial = /trial|zkušeb/i.test(label) || /trial/i.test(current);
    if (!isTrial) return '';

    const daysMatch = current.match(/(\d+)\s*d(en|ny|ní)/i) || label.match(/(\d+)\s*d(níň)/i);
    if (daysMatch) {
      return `<span class="uapp-settings-trial-badge">Trial ${esc(daysMatch[1])} dní</span>`;
    }
    return '<span class="uapp-settings-trial-badge">Trial</span>';
  }

  function renderTopbarProfileButton() {
    return `
      <button type="button" class="uapp-settings-profile-btn" data-uapp-action="profile" aria-label="Profil uživatele" data-testid="dashboard-profile">
        <span class="uapp-settings-avatar" aria-hidden="true">${esc(initials())}</span>
        <span class="uapp-settings-profile-meta">
          <strong>${esc(profileName())}</strong>
          ${profileTopbarTrialBadgeHtml()}
        </span>
        <span aria-hidden="true">▾</span>
      </button>`;
  }

  function renderTopbarNotificationsButton() {
    const badge = document.getElementById('desktopNotificationsBadge') || document.getElementById('mobileNotificationsBadge');
    const count = badge ? String(badge.getAttribute('data-count') || badge.textContent || '0').trim() : '0';
    return `
      <button type="button" class="uapp-next-btn uapp-next-icon-btn" data-uapp-action="notifications" aria-label="Oznámení" data-count="${esc(count || '0')}" data-testid="dashboard-notifications">${ICO.bell}</button>`;
  }

  function formatDate(value) {
    if (!value) return '—';
    try {
      if (typeof formatDateCZ === 'function') return formatDateCZ(value);
    } catch (_) {}
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('cs-CZ');
  }

  function formatDateTime(value) {
    if (!value) return '—';
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return '—';
    try {
      return d.toLocaleString('cs-CZ', { day: 'numeric', month: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch (_) {
      return formatDate(value);
    }
  }

  function formatTodayTimeHm() {
    try {
      return new Date().toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit' });
    } catch (_) {
      return '';
    }
  }

  function parseDate(value) {
    if (!value) return null;
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  function daysUntil(value) {
    const d = parseDate(value);
    if (!d) return null;
    const today = new Date();
    const start = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
    const target = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
    return Math.round((target - start) / 86400000);
  }

  function monthsSince(value) {
    const d = parseDate(value);
    if (!d) return null;
    const now = new Date();
    return (now.getFullYear() - d.getFullYear()) * 12 + (now.getMonth() - d.getMonth());
  }

  function getVehicleName(vehicle) {
    return String(vehicle?.nickname || vehicle?.name || [vehicle?.brand, vehicle?.model].filter(Boolean).join(' ') || vehicle?.plate || `Vozidlo #${vehicle?.id || ''}`).trim();
  }

  function shortVin(vehicle) {
    const s = String(vehicle?.vin || '').trim();
    if (!s) return '—';
    return s.length <= 14 ? s : `${s.slice(0, 12)}…`;
  }

  function normalizePlateSize(size) {
    const raw = String(size || '').toLowerCase();
    if (raw.includes('lg')) return 'lg';
    if (raw.includes('sm')) return 'sm';
    if (raw === 'lg' || raw === 'sm') return raw;
    return 'sm';
  }

  function renderPlateBadge(plate, size) {
    const raw = String(plate || '').trim();
    const isEmpty = !raw || raw === '—';
    const text = isEmpty ? 'Nezadáno' : raw;
    const sizeKey = normalizePlateSize(size);
    const titleAttr = isEmpty ? '' : ` title="${esc(text)}"`;
    return (
      `<span class="uapp-plate uapp-plate--${sizeKey}${isEmpty ? ' uapp-plate--empty' : ''}"${titleAttr}>` +
      `<span class="uapp-plate__country" aria-hidden="true">` +
      `<span class="uapp-plate__eu">${PLATE_EU_STARS_SVG}</span>` +
      `<span class="uapp-plate__cz">CZ</span>` +
      `</span>` +
      `<span class="uapp-plate__number">${esc(text)}</span>` +
      `</span>`
    );
  }

  function renderCardActionBar(vehicleId, withArrow) {
    const id = Number(vehicleId);
    const addRecordBlocked = !hasFn('openAddServiceRecordModal');
    return `
      <div class="uapp-next-card-actions">
        <button type="button" class="uapp-next-card-action" data-uapp-action="detail:${id}">
          <span class="uapp-next-card-action-ico" aria-hidden="true">${ICO.detail}</span>
          <span class="uapp-next-card-action-label">Detail</span>
        </button>
        <button type="button" class="uapp-next-card-action${addRecordBlocked ? ' is-blocked' : ''}" data-uapp-action="addRecord:${id}"${addRecordBlocked ? ' disabled title="Funkce není dostupná"' : ''}>
          <span class="uapp-next-card-action-ico" aria-hidden="true">${ICO.wrench}</span>
          <span class="uapp-next-card-action-label">Přidat záznam</span>
        </button>
        <button type="button" class="uapp-next-card-action" data-uapp-action="documentsVehicle:${id}">
          <span class="uapp-next-card-action-ico" aria-hidden="true">${ICO.doc}</span>
          <span class="uapp-next-card-action-label">Dokumenty</span>
        </button>
        <button type="button" class="uapp-next-card-action" data-uapp-action="shareVehicle:${id}">
          <span class="uapp-next-card-action-ico" aria-hidden="true">${ICO.share}</span>
          <span class="uapp-next-card-action-label">Sdílet</span>
        </button>
        ${withArrow ? `<button type="button" class="uapp-next-card-action uapp-next-card-action--arrow" data-uapp-action="detail:${id}" aria-label="Otevřít detail">›</button>` : ''}
      </div>`;
  }

  function vehicleFuelLabel(vehicle) {
    const raw = vehicle?.fuel_type;
    if (!raw) return '—';
    if (hasFn('normalizeFuelType')) {
      try { return window.normalizeFuelType(raw); } catch (_) {}
    }
    return String(raw);
  }

  function vehiclePowerLabel(vehicle) {
    if (vehicle?.engine_power_kw != null && vehicle.engine_power_kw !== '') {
      return `${vehicle.engine_power_kw} kW`;
    }
    return '—';
  }

  function vehicleVolumeLabel(vehicle) {
    if (vehicle?.engine_displacement_cc != null && vehicle.engine_displacement_cc !== '') {
      return `${Number(vehicle.engine_displacement_cc).toLocaleString('cs-CZ')} ccm`;
    }
    return '—';
  }

  function getStkValue(vehicle) {
    if (vehicle?.stk_valid_until) return vehicle.stk_valid_until;
    if (hasFn('getVehicleStkDateValueSimple')) {
      try {
        const d = window.getVehicleStkDateValueSimple(vehicle);
        return d || null;
      } catch (_) {}
    }
    return null;
  }

  function stkFieldMeta(vehicle) {
    const raw = getStkValue(vehicle);
    const dateObj = raw instanceof Date ? raw : parseDate(raw);
    if (hasFn('getVehicleStkStatusMeta') && dateObj) {
      try {
        const meta = window.getVehicleStkStatusMeta(dateObj);
        const diff = daysUntil(dateObj);
        let tone = 'ok';
        if (meta.className === 'stk-expired') tone = 'bad';
        else if (meta.className === 'stk-soon') tone = 'warn';
        else if (meta.className === 'stk-unknown') tone = 'muted';
        let label = meta.label || 'STK';
        if (diff != null && diff >= 0 && diff <= 120) {
          label = diff === 0 ? 'dnes' : (diff === 1 ? 'za 1 den' : `za ${diff} dní`);
        } else if (diff != null && diff < 0) {
          label = 'po termínu';
        }
        return { label, tone, hint: formatDate(raw), className: meta.className || 'stk-unknown' };
      } catch (_) {}
    }
    const diff = daysUntil(raw);
    if (diff == null) return { label: 'Nezadáno', tone: 'muted', hint: 'Bez data', className: 'stk-unknown' };
    if (diff < 0) return { label: 'po termínu', tone: 'bad', hint: formatDate(raw), className: 'stk-expired' };
    if (diff <= 60) return { label: `za ${diff} dní`, tone: 'warn', hint: formatDate(raw), className: 'stk-soon' };
    return { label: 'v pořádku', tone: 'ok', hint: formatDate(raw), className: 'stk-ok' };
  }

  function insuranceFieldMeta(vehicle) {
    const raw = vehicle?.insurance_valid_until;
    const diff = daysUntil(raw);
    if (diff == null) return { label: 'Nezadáno', tone: 'muted' };
    if (diff < 0) return { label: 'po termínu', tone: 'bad' };
    if (diff <= 45) return { label: formatDate(raw), tone: 'warn' };
    return { label: 'v pořádku', tone: 'ok' };
  }

  function serviceFieldMeta(records) {
    const list = Array.isArray(records) ? records.slice() : [];
    if (!list.length) return { label: 'Bez záznamu', tone: 'warn' };
    list.sort((a, b) => (Date.parse(b?.performed_at || b?.created_at) || 0) - (Date.parse(a?.performed_at || a?.created_at) || 0));
    const latest = list[0];
    const months = monthsSince(latest?.performed_at || latest?.created_at);
    if (months == null) return { label: 'Záznam k dispozici', tone: 'ok' };
    if (months <= 0) return { label: 'tento měsíc', tone: 'ok' };
    if (months === 1) return { label: 'před 1 měsícem', tone: 'ok' };
    if (months < 6) return { label: `před ${months} měsíci`, tone: 'ok' };
    if (months < 12) return { label: 'naplánovat servis', tone: 'warn' };
    return { label: 'dlouho bez servisu', tone: 'warn' };
  }

  function vehicleStatusMeta(vehicle, records) {
    const stk = stkFieldMeta(vehicle);
    const ins = insuranceFieldMeta(vehicle);
    if (stk.className === 'stk-expired' || stk.tone === 'bad' || ins.tone === 'bad') {
      return { label: 'Vyžaduje pozornost', tone: 'warn' };
    }
    if (stk.tone === 'warn' || ins.tone === 'warn') {
      return { label: 'Vyžaduje pozornost', tone: 'warn' };
    }
    const svc = serviceFieldMeta(records);
    if (svc.tone === 'warn') return { label: 'Vyžaduje pozornost', tone: 'warn' };
    return { label: 'V pořádku', tone: 'ok' };
  }

  function toneClass(tone) {
    if (tone === 'bad') return 'is-bad';
    if (tone === 'warn') return 'is-warn';
    if (tone === 'muted') return 'is-muted';
    return 'is-ok';
  }

  function badgeClass(tone) {
    if (tone === 'warn') return 'uapp-next-badge uapp-next-badge--warn';
    if (tone === 'bad') return 'uapp-next-badge uapp-next-badge--danger';
    if (tone === 'service') return 'uapp-next-badge uapp-next-badge--service';
    return 'uapp-next-badge uapp-next-badge--ok';
  }

  function quickToneClass(tone) {
    if (tone === 'warning') return 'uapp-next-quick-card--warn';
    if (tone === 'danger') return 'uapp-next-quick-card--danger';
    if (tone === 'info') return 'uapp-next-quick-card--info';
    return 'uapp-next-quick-card--ok';
  }

  function heroCarSvg() {
    return (
      '<svg class="uapp-next-hero-car-svg" viewBox="0 0 400 175" aria-hidden="true" focusable="false">' +
      '<defs><linearGradient id="uappH1" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#1e3a8a"/><stop offset="100%" stop-color="#2563eb"/></linearGradient>' +
      '<linearGradient id="uappH2" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" stop-color="#93c5fd"/><stop offset="100%" stop-color="#1d4ed8"/></linearGradient>' +
      '<filter id="uappHs" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur in="SourceAlpha" stdDeviation="4"/><feOffset dy="8" result="o"/><feFlood flood-color="rgba(11,31,122,0.25)"/><feComposite in2="o" operator="in"/><feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>' +
      '<ellipse cx="200" cy="138" rx="175" ry="14" fill="rgba(11,31,122,0.07)"/>' +
      '<g filter="url(#uappHs)"><path d="M48 102 L118 78 L268 74 L338 86 L368 104 L368 122 L38 122 Z" fill="url(#uappH1)"/>' +
      '<path d="M125 80 L248 78 L318 88 L328 108 L98 110 Z" fill="url(#uappH2)" opacity="0.88"/>' +
      '<rect x="142" y="86" width="52" height="24" rx="4" fill="rgba(255,255,255,0.28)"/>' +
      '<rect x="258" y="88" width="44" height="20" rx="3" fill="rgba(255,255,255,0.22)"/>' +
      '<circle cx="108" cy="122" r="16" fill="#0f172a"/><circle cx="108" cy="122" r="7" fill="#475569"/>' +
      '<circle cx="278" cy="122" r="16" fill="#0f172a"/><circle cx="278" cy="122" r="7" fill="#475569"/></g></svg>'
    );
  }

  async function safeApi(url, fallback, timeoutMs) {
    if (!apiReady()) return fallback;
    try {
      const result = typeof timeoutMs === 'number'
        ? await apiCall(url, 'GET', null, timeoutMs)
        : await apiCall(url, 'GET');
      return result == null ? fallback : result;
    } catch (error) {
      console.warn('[USER_APP_NEXT] API skipped:', url, error?.message || error);
      return fallback;
    }
  }

  async function loadRecordsForVehicles(vehicles) {
    const targets = vehicles.filter((vehicle) => Number(vehicle?.id) > 0);
    const entries = await Promise.all(targets.map(async (vehicle) => {
      const records = await safeApi(`/api/v1/vehicles/${Number(vehicle.id)}/records`, []);
      return { vehicle, records: Array.isArray(records) ? records : [] };
    }));
    return entries;
  }

  async function loadData() {
    const [summary, vehicles, reminders, accessPayload, contactsPayload] = await Promise.all([
      safeApi('/api/v1/analytics/dashboard', {}),
      safeApi('/api/v1/vehicles', []),
      safeApi('/api/v1/reminders', []),
      safeApi('/api/v1/services/vehicle-access', { grants: [] }),
      safeApi('/api/v1/services/my-contacts', { services: [] }),
    ]);
    const vehicleList = Array.isArray(vehicles) ? vehicles : [];
    window._lastVehiclesById = vehicleList.reduce((acc, vehicle) => {
      if (vehicle && Number(vehicle.id) > 0) acc[Number(vehicle.id)] = vehicle;
      return acc;
    }, {});
    STATE.lastVehicles = vehicleList;
    const activeView = getActiveView();
    const needsVehicleRecords = activeView !== 'servicesDirectory' && activeView !== 'documents';
    let recordEntries = [];
    let recordMap = {};
    if (needsVehicleRecords) {
      recordEntries = await loadRecordsForVehicles(vehicleList);
      recordMap = recordEntries.reduce((acc, entry) => {
        acc[Number(entry.vehicle.id)] = entry.records;
        return acc;
      }, {});
    }
    let documentsHub = null;
    if (activeView === 'documents' && apiReady()) {
      documentsHub = await safeApi('/api/v1/vehicles/documents/hub?attachments_limit=100&reports_limit=100&tachometer_limit=100', null);
    }
    let servicesDiscovery = null;
    if (activeView === 'servicesDirectory' && apiReady()) {
      let clientRef = null;
      const cachedRef = STATE.servicesRefCoords;
      if (cachedRef && Number.isFinite(Number(cachedRef.lat)) && Number.isFinite(Number(cachedRef.lon))) {
        clientRef = { lat: Number(cachedRef.lat), lon: Number(cachedRef.lon) };
      } else if (STATE.servicesDirectoryUseLocation !== false) {
        if (hasFn('waitForClientGeolocation')) {
          try {
            const geo = await window.waitForClientGeolocation(8000);
            if (geo && Number.isFinite(Number(geo.lat)) && Number.isFinite(Number(geo.lon))) {
              clientRef = { lat: Number(geo.lat), lon: Number(geo.lon) };
              STATE.servicesRefCoords = clientRef;
              STATE.servicesLocationLabel = '';
            }
          } catch (_) {}
        } else if (hasFn('captureClientGeolocation')) {
          try { window.captureClientGeolocation(true); } catch (_) {}
          await new Promise((resolve) => { window.setTimeout(resolve, 1500); });
          if (hasFn('getClientGeoTelemetryForHeaders')) {
            try {
              const geo = window.getClientGeoTelemetryForHeaders();
              if (geo && Number.isFinite(Number(geo.lat)) && Number.isFinite(Number(geo.lon))) {
                clientRef = { lat: Number(geo.lat), lon: Number(geo.lon) };
                STATE.servicesRefCoords = clientRef;
                STATE.servicesLocationLabel = '';
              }
            } catch (_) {}
          }
        }
      }
      const ref = clientRef || STATE.servicesRefCoords || null;
      let discoveryUrl = '/api/v1/services/discovery?radius_km=0';
      if (ref && Number.isFinite(Number(ref.lat)) && Number.isFinite(Number(ref.lon))) {
        discoveryUrl += `&ref_lat=${encodeURIComponent(String(ref.lat))}&ref_lon=${encodeURIComponent(String(ref.lon))}`;
      }
      servicesDiscovery = await safeApi(discoveryUrl, null);
      const discoveryMeta = servicesDiscovery?.meta || {};
      const discoverySource = String(discoveryMeta.reference_source || 'none');
      if (clientRef) {
        STATE.servicesRefCoords = clientRef;
      } else if (discoveryMeta.reference_coordinates && discoverySource !== 'profile_address') {
        STATE.servicesRefCoords = discoveryMeta.reference_coordinates;
      } else if (discoveryMeta.reference_coordinates && STATE.servicesDirectoryUseLocation === false) {
        STATE.servicesRefCoords = discoveryMeta.reference_coordinates;
      }
      if (discoveryMeta.reference_label) {
        STATE.servicesLocationLabel = String(discoveryMeta.reference_label);
      }
      void refreshServicesLocationLabel({ servicesDiscovery });
    }
    const data = {
      summary: summary && typeof summary === 'object' ? summary : {},
      vehicles: vehicleList,
      reminders: Array.isArray(reminders) ? reminders : [],
      accessGrants: Array.isArray(accessPayload?.grants) ? accessPayload.grants : [],
      services: Array.isArray(contactsPayload?.services) ? contactsPayload.services : [],
      recordEntries,
      recordMap,
      documentsHub,
      servicesDiscovery,
    };
    STATE.latestData = data;
    return data;
  }

  async function fetchServicesGeocodeSuggestions(query) {
    const q = String(query || '').trim();
    if (q.length < 2) return { items: [] };
    return safeApi(
      `/api/v1/services/geocode-suggest?q=${encodeURIComponent(q)}&limit=8`,
      { items: [] },
      20000,
    );
  }

  function closeServicesLocationModal() {
    const modal = document.getElementById('uappSvcLocationModal');
    if (modal) modal.remove();
    if (STATE.servicesLocationSuggestDebounce) {
      clearTimeout(STATE.servicesLocationSuggestDebounce);
      STATE.servicesLocationSuggestDebounce = null;
    }
  }

  async function applyServicesLocationFromItem(item) {
    if (!item || !Number.isFinite(Number(item.lat)) || !Number.isFinite(Number(item.lon))) return;
    closeServicesLocationModal();
    STATE.servicesRefCoords = { lat: Number(item.lat), lon: Number(item.lon) };
    STATE.servicesLocationLabel = String(item.label || item.subtitle || 'Vybraná adresa');
    STATE.servicesDirectoryUseLocation = false;
    STATE.servicesMapBounds = null;
    STATE.servicesOsmRows = [];
    STATE.servicesMapRows = [];
    STATE.servicesDirectoryLimit = 30;
    await render();
  }

  async function applyServicesLocationFromGps() {
    const modal = document.getElementById('uappSvcLocationModal');
    const gpsBtn = modal?.querySelector('[data-uapp-action="servicesLocationUseGps"]');
    const status = modal?.querySelector('#uappSvcLocationStatus');
    if (gpsBtn) {
      gpsBtn.disabled = true;
      gpsBtn.textContent = 'Načítám GPS…';
    }
    if (status) status.textContent = 'Čekám na polohu z prohlížeče…';

    if (hasFn('clearClientGeoTelemetry')) {
      try { window.clearClientGeoTelemetry(); } catch (_) {}
    }

    let geoError = null;
    try {
      if (hasFn('waitForClientGeolocation')) {
        const geo = await window.waitForClientGeolocation(12000, { force: true });
        if (geo && Number.isFinite(Number(geo.lat)) && Number.isFinite(Number(geo.lon))) {
          STATE.servicesRefCoords = { lat: Number(geo.lat), lon: Number(geo.lon) };
          STATE.servicesDirectoryUseLocation = true;
          STATE.servicesLocationLabel = 'Načítám adresu…';
        }
      } else if (hasFn('captureClientGeolocation')) {
        window.captureClientGeolocation(true);
        await new Promise((resolve) => { window.setTimeout(resolve, 3000); });
        if (hasFn('getClientGeoTelemetryForHeaders')) {
          const geo = window.getClientGeoTelemetryForHeaders();
          if (geo && Number.isFinite(Number(geo.lat)) && Number.isFinite(Number(geo.lon))) {
            STATE.servicesRefCoords = { lat: Number(geo.lat), lon: Number(geo.lon) };
            STATE.servicesDirectoryUseLocation = true;
            STATE.servicesLocationLabel = 'Načítám adresu…';
          }
        }
      }
    } catch (err) {
      geoError = String(err?.message || err || 'Polohu se nepodařilo načíst.');
    }

    if (!STATE.servicesRefCoords) {
      if (status) status.textContent = geoError || 'Polohu se nepodařilo načíst. Povolte GPS v prohlížeči.';
      if (gpsBtn) {
        gpsBtn.disabled = false;
        gpsBtn.textContent = 'Použít GPS z prohlížeče';
      }
      return;
    }

    closeServicesLocationModal();
    STATE.servicesMapBounds = null;
    STATE.servicesOsmRows = [];
    STATE.servicesMapRows = [];
    STATE.servicesDirectoryLimit = 30;
    await render();
  }

  function openServicesLocationModal() {
    closeServicesLocationModal();
    const currentLabel = STATE.servicesLocationLabel || resolveServicesLocationLabel(STATE.latestData || {}) || '';
    const skipPrefill = !currentLabel
      || currentLabel === 'Podle adresy v profilu'
      || currentLabel.startsWith('Načítám');
    const overlay = document.createElement('div');
    overlay.id = 'uappSvcLocationModal';
    overlay.className = 'uapp-svc-modal-overlay';
    overlay.innerHTML = `
      <div class="uapp-svc-modal uapp-svc-location-modal" role="dialog" aria-modal="true" aria-labelledby="uappSvcLocationTitle">
        <div class="uapp-svc-modal-head">
          <div>
            <p class="uapp-svc-modal-kicker">Servisy v okolí</p>
            <h2 id="uappSvcLocationTitle">Nastavit polohu</h2>
          </div>
          <button type="button" class="uapp-svc-modal-close" data-uapp-action="servicesLocationClose" aria-label="Zavřít">×</button>
        </div>
        <p class="uapp-svc-location-modal-lead">Zadejte město, ulici a číslo popisné. Vyberte přesnou adresu z našeptávače.</p>
        <label class="uapp-svc-location-field">
          <span>Adresa nebo místo</span>
          <input type="search" id="uappSvcLocationInput" autocomplete="off" placeholder="např. Olomoucká 45, Svitavy" value="${esc(skipPrefill ? '' : currentLabel)}">
        </label>
        <p class="uapp-svc-location-status" id="uappSvcLocationStatus">Pište alespoň 2 znaky pro našeptávání.</p>
        <div class="uapp-svc-location-suggest" id="uappSvcLocationSuggest" role="listbox" aria-label="Nalezené adresy" hidden></div>
        <div class="uapp-svc-location-modal-actions">
          <button type="button" class="uapp-next-btn uapp-next-btn-secondary" data-uapp-action="servicesLocationUseGps">Použít GPS z prohlížeče</button>
          <button type="button" class="uapp-next-btn uapp-next-btn-secondary" data-uapp-action="servicesLocationClose">Zrušit</button>
        </div>
      </div>`;

    overlay.addEventListener('click', (event) => {
      if (event.target === overlay) closeServicesLocationModal();
    });

    document.body.appendChild(overlay);

    const input = overlay.querySelector('#uappSvcLocationInput');
    const list = overlay.querySelector('#uappSvcLocationSuggest');
    const status = overlay.querySelector('#uappSvcLocationStatus');
    let suggestions = [];
    let suggestToken = 0;

    const renderList = () => {
      if (!list) return;
      if (!suggestions.length) {
        list.innerHTML = '';
        list.hidden = true;
        return;
      }
      list.hidden = false;
      list.innerHTML = suggestions.map((item, idx) => `
        <button type="button" class="uapp-svc-location-suggest-item" role="option" data-uapp-action="servicesLocationPick:${idx}">
          <strong>${esc(item.label || 'Adresa')}</strong>
          ${item.subtitle ? `<span>${esc(item.subtitle)}</span>` : ''}
        </button>
      `).join('');
      overlay._suggestions = suggestions;
    };

    const loadSuggestions = async (q) => {
      const query = String(q || '').trim();
      if (query.length < 2) {
        suggestions = [];
        renderList();
        if (status) {
          status.textContent = query.length
            ? 'Pište alespoň 2 znaky pro našeptávání.'
            : 'Zadejte město, ulici nebo číslo popisné.';
        }
        return;
      }
      const token = ++suggestToken;
      if (status) status.textContent = 'Hledám adresy…';
      const payload = await fetchServicesGeocodeSuggestions(query);
      if (token !== suggestToken) return;
      suggestions = Array.isArray(payload?.items) ? payload.items : [];
      if (status) {
        status.textContent = suggestions.length
          ? 'Vyberte přesnou adresu ze seznamu.'
          : 'Nic nenalezeno – zkuste upřesnit zadání (město, ulice, číslo).';
      }
      renderList();
    };

    if (input) {
      input.addEventListener('input', () => {
        if (STATE.servicesLocationSuggestDebounce) clearTimeout(STATE.servicesLocationSuggestDebounce);
        STATE.servicesLocationSuggestDebounce = setTimeout(() => {
          void loadSuggestions(input.value);
        }, 320);
      });
      input.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          if (suggestions[0]) void applyServicesLocationFromItem(suggestions[0]);
        }
        if (event.key === 'Escape') closeServicesLocationModal();
      });
      window.setTimeout(() => {
        input.focus();
        if (input.value.trim().length >= 2) void loadSuggestions(input.value);
      }, 0);
    }
  }

  async function loadServicesOsmData(options) {
    const silent = Boolean(options && options.silent);
    const skipRender = Boolean(options && options.skipRender);
    if (!apiReady() || getActiveView() !== 'servicesDirectory') return;
    const osmToken = ++STATE.servicesOsmLoadToken;
    const ref = STATE.servicesRefCoords
      || STATE.latestData?.servicesDiscovery?.meta?.reference_coordinates
      || {};
    const lat = Number(ref.lat) || 49.7559;
    const lon = Number(ref.lon) || 16.4683;
    const radius = Number(STATE.servicesDirectoryRadius) || 50;
    const category = STATE.servicesMapCategory && STATE.servicesMapCategory !== 'all' && STATE.servicesMapCategory !== 'verified'
      ? STATE.servicesMapCategory
      : '';
    const q = String(STATE.servicesMapSearchQ || '').trim();
    const bounds = silent ? STATE.servicesMapBounds : null;

    if (!silent) {
      STATE.servicesOsmLoading = true;
      STATE.servicesOsmError = null;
      if (STATE.latestData && getActiveView() === 'servicesDirectory') {
        renderShell(STATE.latestData);
      }
    }

    try {
      let url;
      if (bounds && Number.isFinite(bounds.north) && Number.isFinite(bounds.south) && Number.isFinite(bounds.east) && Number.isFinite(bounds.west)) {
        url = `/api/v1/service-map/search?north=${encodeURIComponent(String(bounds.north))}&south=${encodeURIComponent(String(bounds.south))}&east=${encodeURIComponent(String(bounds.east))}&west=${encodeURIComponent(String(bounds.west))}&limit=100`;
        url += `&lat=${encodeURIComponent(String(lat))}&lng=${encodeURIComponent(String(lon))}`;
      } else {
        url = `/api/v1/service-map/search?lat=${encodeURIComponent(String(lat))}&lng=${encodeURIComponent(String(lon))}&radius_km=${encodeURIComponent(String(radius))}&limit=500`;
      }
      if (category) url += `&category=${encodeURIComponent(category)}`;
      if (q) url += `&q=${encodeURIComponent(q)}`;
      if (STATE.servicesMapVerifiedOnly || STATE.servicesMapCategory === 'verified') {
        url += '&verified_only=true';
      }
      const payload = await safeApi(url, { items: [], total: 0, radius_km: radius }, 90000);
      if (osmToken !== STATE.servicesOsmLoadToken || getActiveView() !== 'servicesDirectory') return;
      STATE.servicesMapRows = Array.isArray(payload?.items) ? payload.items : [];
      STATE.servicesMapTotal = Number(payload?.total) || STATE.servicesMapRows.length;
      STATE.servicesMapHint = String(payload?.hint || '');
      STATE.servicesOsmRows = STATE.servicesMapRows.map(mapApiItemToCatalogRow);
      if (silent && STATE.servicesMapRuntime?.map) {
        updateServicesMapMarkers(STATE.latestData || {});
        return;
      }
    } catch (err) {
      if (osmToken !== STATE.servicesOsmLoadToken) return;
      STATE.servicesMapRows = [];
      STATE.servicesOsmRows = [];
      STATE.servicesMapHint = '';
      STATE.servicesOsmError = String(err?.message || err || 'Nepodařilo se načíst servisy z katalogu.');
      console.warn('[USER_APP_NEXT] service-map load failed', err);
    } finally {
      if (osmToken !== STATE.servicesOsmLoadToken) return;
      STATE.servicesOsmLoading = false;
      if (!silent && !skipRender && STATE.latestData && getActiveView() === 'servicesDirectory') {
        renderShell(STATE.latestData);
      }
    }
  }

  async function refreshServicesLocationLabel(data) {
    const ref = getServicesRefCoords(data || STATE.latestData || {}) || STATE.servicesRefCoords;
    if (!ref || !Number.isFinite(Number(ref.lat)) || !Number.isFinite(Number(ref.lon))) return;
    if (!apiReady()) return;
    const payload = await safeApi(
      `/api/v1/system/reverse-geocode?lat=${encodeURIComponent(String(ref.lat))}&lon=${encodeURIComponent(String(ref.lon))}`,
      null,
    );
    const label = payload?.location_label || payload?.city || null;
    if (!label) return;
    STATE.servicesLocationLabel = String(label);
    const locEl = document.querySelector('.uapp-svc-widget .uapp-svc-location');
    if (locEl) locEl.textContent = STATE.servicesLocationLabel;
    const coordsEl = document.querySelector('.uapp-svc-widget .uapp-svc-location-coords');
    if (coordsEl && ref) {
      coordsEl.textContent = `${Number(ref.lat).toFixed(5)}, ${Number(ref.lon).toFixed(5)}`;
    }
  }

  function patchServicesDirectoryList(data) {
    if (getActiveView() !== 'servicesDirectory') return;
    const allRows = buildMergedServiceCatalog(data);
    const filtered = filterServicesRows(allRows);
    const radius = Number(STATE.servicesDirectoryRadius) || 50;
    const nearbyCount = filtered.filter((row) => {
      const dist = Number(row.distance_km);
      return Number.isFinite(dist) && dist <= radius;
    }).length;
    const limit = Number(STATE.servicesDirectoryLimit) || 10;
    const visible = filtered.slice(0, limit);
    const head = document.querySelector('.uapp-svc-list-head h2');
    if (head) head.textContent = `Nalezeno ${nearbyCount || filtered.length} servisů do ${radius} km`;
    const list = document.querySelector('.uapp-svc-list');
    if (list) {
      list.innerHTML = visible.length
        ? visible.map((service) => renderServicesCard(service)).join('')
        : '<div class="uapp-svc-empty">V okolí nejsou servisy odpovídající filtrům.</div>';
    }
    const loading = document.querySelector('.uapp-svc-loading');
    if (loading) loading.remove();
    const errEl = document.querySelector('.uapp-svc-osm-error');
    if (errEl && !STATE.servicesOsmError) errEl.remove();
    if (STATE.servicesMapRuntime?.map) updateServicesMapMarkers(data);
    void hydrateServiceAddresses(visible);
  }

  function getOsmRowCoords(row) {
    if (!row || typeof row !== 'object') return { lat: NaN, lon: NaN };
    const lat = Number(row.lat ?? row.coordinates?.lat);
    const lon = Number(row.lon ?? row.lng ?? row.coordinates?.lon);
    return { lat, lon };
  }

  function mapApiCategoryToShopType(category) {
    const map = {
      autoservis: 'auto',
      pneuservis: 'pneu',
      stk: 'stk',
      sme: 'emis',
      truck_service: 'truck',
      karosarna: 'auto',
      autoskla: 'auto',
      odtah: 'truck',
      diagnostika: 'auto',
      other: 'auto',
    };
    return map[String(category || '').toLowerCase()] || 'auto';
  }

  function mapApiItemToCatalogRow(item) {
    const lat = Number(item?.lat);
    const lng = Number(item?.lng);
    const category = String(item?.category || 'other');
    const services = Array.isArray(item?.services) ? item.services : [];
    const locationId = Number(item?.id) || null;
    return {
      id: null,
      location_id: locationId,
      osm_id: locationId,
      lat,
      lng,
      lon: lng,
      shop_type: mapApiCategoryToShopType(category),
      category,
      name: item?.name || 'Servis',
      street: '',
      city: item?.city || '',
      zip: '',
      phone: item?.phone || '',
      email: '',
      website: item?.website || '',
      address: item?.address_text || item?.city || '',
      coordinates: Number.isFinite(lat) && Number.isFinite(lng) ? { lat, lon: lng } : null,
      distance_km: item?.distance_km,
      in_app: false,
      is_linked: false,
      source: item?.source_type || 'catalog',
      source_type: item?.source_type || 'catalog',
      verification_status: item?.verification_status || 'imported',
      is_verified: Boolean(item?.is_verified),
      opening_hours: item?.opening_hours || '',
      vehicle_scope: Array.isArray(item?.vehicle_scope) ? item.vehicle_scope : [],
      partner_public_profile: { services_offered: services.length ? services : [category] },
      row_key: `map-${item?.id}`,
    };
  }

  function recordsFor(data, vehicleId) {
    if (data.recordMap && data.recordMap[vehicleId]) return data.recordMap[vehicleId];
    const hit = (data.recordEntries || []).find((entry) => Number(entry.vehicle?.id) === Number(vehicleId));
    return hit ? hit.records : [];
  }

  function activeRemindersCount(data) {
    const fromSummary = Number(data.summary?.active_reminders);
    if (Number.isFinite(fromSummary)) return fromSummary;
    return data.reminders.filter((item) => !item?.is_completed).length;
  }

  function stkSoonCount(data) {
    const fromSummary = Number(data.summary?.stk_soon);
    if (Number.isFinite(fromSummary) && fromSummary >= 0) return fromSummary;
    return data.vehicles.filter((vehicle) => {
      const meta = stkFieldMeta(vehicle);
      return meta.tone === 'warn' || meta.tone === 'bad';
    }).length;
  }

  function serviceNotificationsCount(data) {
    const pending = data.accessGrants.filter((grant) => {
      const status = String(grant?.status || '').toLowerCase();
      return status.includes('pending') || status.includes('ček') || status.includes('wait');
    }).length;
    if (pending > 0) return pending;
    const notes = window.__systemNotificationsLastItems || [];
    return notes.filter((item) => {
      const hay = `${item?.title || ''} ${item?.body || ''} ${item?.kind || ''}`.toLowerCase();
      return hay.includes('servis') || hay.includes('service') || hay.includes('přístup');
    }).length;
  }

  function fleetNeedsAttention(data) {
    if (Array.isArray(data.summary?.attention) && data.summary.attention.length) return true;
    return data.vehicles.some((vehicle) => {
      const meta = vehicleStatusMeta(vehicle, recordsFor(data, vehicle.id));
      return meta.tone !== 'ok';
    });
  }

  function attentionPriorityRank(priority) {
    if (priority === 'high') return 3;
    if (priority === 'warning') return 2;
    return 1;
  }

  function attentionItemIcon(type) {
    const map = {
      stk: ICO.quickStk,
      insurance: ICO.quickShield,
      service: ICO.wrench,
      documents: ICO.doc,
      access: ICO.share,
      reminder: ICO.bell,
    };
    return map[type] || ICO.bell;
  }

  function reminderLooksLikeStk(text) {
    const hay = String(text || '').toLowerCase();
    return hay.includes('stk') || hay.includes('sme') || hay.includes('technick');
  }

  function reminderLooksLikeInsurance(text) {
    const hay = String(text || '').toLowerCase();
    return hay.includes('pojišt') || hay.includes('pojist');
  }

  function getVehicleAttentionItems(vehicle, data) {
    const items = [];
    const id = Number(vehicle?.id);
    if (!Number.isFinite(id) || id <= 0) return items;
    const records = recordsFor(data, id);
    const vehicleName = getVehicleName(vehicle);
    const plate = vehicle.plate || '';
    const push = (item) => items.push({ vehicleId: id, vehicleName, plate, vehicle, ...item });

    const stk = stkFieldMeta(vehicle);
    if (stk.tone === 'bad') {
      push({
        type: 'stk',
        problemText: 'STK po termínu',
        priority: 'high',
        priorityLabel: 'Po termínu',
        actionText: 'Otevřít STK',
        action: `detailTab:ops:${id}`,
      });
    } else if (stk.tone === 'warn') {
      push({
        type: 'stk',
        problemText: stk.label === 'po termínu' ? 'STK po termínu' : `STK ${stk.label}`,
        priority: 'warning',
        priorityLabel: 'Blíží se',
        actionText: 'Otevřít STK',
        action: `detailTab:ops:${id}`,
      });
    } else if (stk.tone === 'muted' && stk.label === 'Nezadáno') {
      push({
        type: 'stk',
        problemText: 'STK nezadána',
        priority: 'warning',
        priorityLabel: 'Vyžaduje doplnění',
        actionText: 'Otevřít detail',
        action: `detail:${id}`,
      });
    }

    const ins = insuranceFieldMeta(vehicle);
    if (ins.tone === 'bad') {
      push({
        type: 'insurance',
        problemText: 'Pojištění po termínu',
        priority: 'high',
        priorityLabel: 'Po termínu',
        actionText: 'Otevřít detail',
        action: `detail:${id}`,
      });
    } else if (ins.tone === 'warn') {
      push({
        type: 'insurance',
        problemText: 'Pojištění brzy končí',
        priority: 'warning',
        priorityLabel: 'Blíží se',
        actionText: 'Otevřít detail',
        action: `detail:${id}`,
      });
    } else if (ins.tone === 'muted') {
      push({
        type: 'insurance',
        problemText: 'Pojištění nezadáno',
        priority: 'warning',
        priorityLabel: 'Vyžaduje doplnění',
        actionText: 'Otevřít detail',
        action: `detail:${id}`,
      });
    }

    const openService = (records || []).filter((record) => {
      const st = String(record?.record_status || '').toLowerCase();
      return st === 'in_progress' || st === 'draft';
    });
    if (openService.length) {
      const draft = openService.some((record) => String(record?.record_status || '').toLowerCase() === 'draft');
      push({
        type: 'service',
        problemText: draft ? 'Rozepsaný servisní záznam' : 'Servis právě probíhá',
        priority: 'warning',
        priorityLabel: 'V servisu',
        actionText: 'Otevřít servis',
        action: `detailTab:service:${id}`,
      });
    }

    const hasStkItem = items.some((item) => item.type === 'stk');
    const hasInsuranceItem = items.some((item) => item.type === 'insurance');
    (data?.reminders || []).forEach((reminder) => {
      if (reminder?.is_completed || Number(reminder?.vehicle_id) !== id) return;
      const title = String(reminder.text || reminder.title || reminder.type || 'Připomínka').trim();
      if (hasStkItem && reminderLooksLikeStk(title)) return;
      if (hasInsuranceItem && reminderLooksLikeInsurance(title)) return;
      const diff = daysUntil(reminder.due_date || reminder.notify_at);
      if (diff == null || diff > 60) return;
      push({
        type: 'reminder',
        problemText: title,
        priority: diff < 0 ? 'high' : 'warning',
        priorityLabel: diff < 0 ? 'Po termínu' : 'Blíží se',
        actionText: 'Otevřít připomínky',
        action: `detailTab:ops:${id}`,
      });
    });

    (data?.accessGrants || []).forEach((grant) => {
      if (Number(grant?.vehicle_id) !== id) return;
      const badge = grantBadge(grant.status);
      if (badge.tone !== 'warn') return;
      const serviceLabel = grant.service_name || grant.service_email || 'servis';
      push({
        type: 'access',
        problemText: `Přístup servisu — ${serviceLabel}`,
        priority: 'warning',
        priorityLabel: 'Čeká na schválení',
        actionText: 'Otevřít přístupy',
        action: `detailTab:access:${id}`,
      });
    });

    return items;
  }

  function collectAllAttentionItems(data) {
    const all = [];
    (data?.vehicles || []).forEach((vehicle) => {
      getVehicleAttentionItems(vehicle, data).forEach((item) => all.push(item));
    });
    all.sort((a, b) => {
      const rankDiff = attentionPriorityRank(b.priority) - attentionPriorityRank(a.priority);
      if (rankDiff !== 0) return rankDiff;
      return String(a.vehicleName || '').localeCompare(String(b.vehicleName || ''), 'cs');
    });
    return all;
  }

  function attentionCountLabel(count) {
    if (count === 1) return '1 položka k řešení';
    if (count >= 2 && count <= 4) return `${count} položky k řešení`;
    return `${count} položek k řešení`;
  }

  function renderAttentionModalContent(data) {
    const items = collectAllAttentionItems(data);
    STATE.attentionItems = items;
    const count = items.length;
    const listHtml = count
      ? items.map((item, index) => `
        <article class="uapp-next-attention-item">
          <div class="uapp-next-attention-item-main">
            <span class="uapp-next-attention-item-ico" aria-hidden="true">${attentionItemIcon(item.type)}</span>
            <div class="uapp-next-attention-item-body">
              <div class="uapp-next-attention-item-head">
                <strong class="uapp-next-attention-vehicle">${esc(item.vehicleName)}</strong>
                ${renderPlateBadge(item.plate)}
                <span class="uapp-next-attention-badge is-${esc(item.priority)}">${esc(item.priorityLabel)}</span>
              </div>
              <p class="uapp-next-attention-problem">${esc(item.problemText)}</p>
            </div>
          </div>
          <button type="button" class="uapp-next-attention-resolve" data-uapp-action="attentionResolve:${index}">${esc(item.actionText)}</button>
        </article>`).join('')
      : `
        <div class="uapp-next-attention-empty">
          <div class="uapp-next-attention-empty-ico" aria-hidden="true">${ICO.checkOk}</div>
          <p>Všechna vozidla jsou aktuálně v pořádku.</p>
          <button type="button" class="uapp-next-btn uapp-next-btn-primary" data-uapp-action="attentionAllVehicles">Zobrazit přehled vozidel</button>
        </div>`;

    return `
      <div class="uapp-next-attention-modal" role="dialog" aria-modal="true" aria-labelledby="uappNextAttentionTitle">
        <button type="button" class="uapp-next-attention-close" data-uapp-action="attentionClose" aria-label="Zavřít">×</button>
        <header class="uapp-next-attention-head">
          <h2 id="uappNextAttentionTitle">Co je potřeba řešit</h2>
          <p class="uapp-next-attention-sub">Přehled vozidel a úkolů, které vyžadují vaši pozornost.</p>
          ${count ? `<p class="uapp-next-attention-count">${esc(attentionCountLabel(count))}</p>` : ''}
        </header>
        <div class="uapp-next-attention-list">${listHtml}</div>
        <footer class="uapp-next-attention-foot">
          <button type="button" class="uapp-next-btn uapp-next-btn-secondary" data-uapp-action="attentionAllVehicles">Zobrazit všechna vozidla</button>
          <button type="button" class="uapp-next-btn uapp-next-btn-ghost" data-uapp-action="attentionClose">Zavřít</button>
        </footer>
      </div>`;
  }

  function mountAttentionModalShell(html) {
    let backdrop = document.getElementById(ATTENTION_MODAL_ID);
    if (!backdrop) {
      backdrop = document.createElement('div');
      backdrop.id = ATTENTION_MODAL_ID;
      backdrop.className = 'uapp-next-attention-backdrop';
      backdrop.setAttribute('data-testid', 'user-app-next-attention-modal');
      document.body.appendChild(backdrop);
    }
    backdrop.innerHTML = `<div class="uapp-next-attention-backdrop-inner">${html}</div>`;
    backdrop.onclick = (event) => {
      if (event.target === backdrop || event.target.classList.contains('uapp-next-attention-backdrop-inner')) {
        closeAttentionModal();
      }
    };
  }

  function openAttentionModal() {
    bindModalEsc();
    const data = STATE.latestData;
    if (!data) return;
    STATE.attentionModalOpen = true;
    document.body.classList.add('uapp-next-attention-open');
    mountAttentionModalShell(renderAttentionModalContent(data));
  }

  function closeAttentionModal() {
    STATE.attentionModalOpen = false;
    STATE.attentionItems = [];
    document.body.classList.remove('uapp-next-attention-open');
    const root = document.getElementById(ATTENTION_MODAL_ID);
    if (root) root.remove();
  }

  function computeQuickCards(data) {
    const vehicles = data.vehicles || [];
    let stkN = 0;
    let stkSample = '';
    let insWarn = 0;
    let insBad = 0;
    vehicles.forEach((vehicle) => {
      const stk = stkFieldMeta(vehicle);
      const ins = insuranceFieldMeta(vehicle);
      if (stk.tone === 'warn' || stk.tone === 'bad') {
        stkN += 1;
        if (!stkSample) stkSample = stk.label;
      }
      if (ins.tone === 'warn') insWarn += 1;
      if (ins.tone === 'bad') insBad += 1;
    });

    let svcBlock = { tone: 'success', title: 'Bez servisního záznamu', desc: 'Doplňte první servisní záznam' };
    let latestMonths = null;
    data.recordEntries.forEach(({ records }) => {
      const meta = serviceFieldMeta(records);
      if (meta.tone === 'ok' && meta.label.includes('měs')) {
        const m = monthsSince(records[0]?.performed_at || records[0]?.created_at);
        if (m != null && (latestMonths == null || m < latestMonths)) latestMonths = m;
      }
    });
    if (latestMonths != null) {
      svcBlock = {
        tone: 'info',
        title: latestMonths <= 1 ? 'Poslední servis tento měsíc' : `Poslední servis před ${latestMonths} měsíci`,
        desc: 'Váš vůz je v pořádku',
      };
    } else if (data.recordEntries.some((entry) => entry.records.length)) {
      svcBlock = { tone: 'info', title: 'Servisní záznamy k dispozici', desc: 'Zkontrolujte historii servisu' };
    }

    const docsMissing = Number(data.summary?.missing_main_photo || 0) + Number(data.summary?.records_missing_history || 0);
    const docPending = docsMissing > 0 ? docsMissing : Number(data.summary?.documents_pending || 0);

    return {
      stk: {
        tone: stkN > 0 ? 'warning' : 'success',
        title: stkN === 0 ? 'STK / SME v pořádku' : (stkN === 1 ? `1 vozidlo — ${stkSample}` : `${stkN} vozidla — zkontrolujte STK`),
        desc: stkN > 0 ? 'Zkontrolujte včas' : 'Žádná blížící se lhůta',
        action: 'reminders',
      },
      ins: {
        tone: insWarn + insBad > 0 ? 'warning' : 'success',
        title: insWarn + insBad > 0 ? 'Zkontrolujte pojistné smlouvy' : 'Všechna vozidla v pořádku',
        desc: insWarn + insBad > 0 ? 'Zkontrolujte pojištění' : 'Platné smlouvy',
        action: 'reminders',
      },
      svc: { ...svcBlock, action: 'serviceHistory' },
      docs: {
        tone: docPending > 0 ? 'warning' : 'success',
        title: docPending > 0 ? `${docPending} dokumenty čekají na doplnění` : 'Dokumenty v pořádku',
        desc: docPending > 0 ? 'Doplňte chybějící' : 'Žádné chybějící podklady',
        action: 'documents',
      },
    };
  }

  function preserveLegacyOverlays() {
    preserveLegacyVehicleModal();
    detachedPanels();
  }

  function detachedPanels() {
    ['appNotificationsPanel', 'mobileProfileMenu'].forEach((id) => {
      const el = document.getElementById(id);
      if (el && el.parentElement !== document.body) {
        document.body.appendChild(el);
      }
    });
  }

  function preserveLegacyVehicleModal() {
    const modal = document.getElementById('addVehicleModal');
    if (modal && modal.parentElement !== document.body) {
      document.body.appendChild(modal);
    }
  }

  function ensureUserAppScreenRoot() {
    const dashboard = document.getElementById('dashboard');
    if (!dashboard) return null;
    let root = document.getElementById(USER_APP_SCREEN_ID);
    if (!root) {
      root = document.createElement('div');
      root.id = USER_APP_SCREEN_ID;
      root.className = 'user-app-next-screen';
      root.setAttribute('data-testid', 'user-app-next-screen');
      dashboard.appendChild(root);
    }
    return root;
  }

  function clearUserAppScreen() {
    restoreLegacyTabMount();
    const root = document.getElementById(USER_APP_SCREEN_ID);
    if (root) root.replaceChildren();
  }

  function restoreLegacyTabMount() {
    if (!STATE.legacyMount.tabId) return;
    const tab = document.getElementById(STATE.legacyMount.tabId);
    const mount = document.getElementById('uappNextLegacyMount');
    if (tab && mount) {
      while (mount.firstChild) {
        tab.appendChild(mount.firstChild);
      }
    }
    STATE.legacyMount = { tabId: null };
  }

  function mountLegacyTabContent(view) {
    const meta = LEGACY_SECTION_META[view];
    if (!meta) return;
    const tab = document.getElementById(meta.tabId);
    const mount = document.getElementById('uappNextLegacyMount');
    if (!tab || !mount) return;
    while (tab.firstChild) {
      mount.appendChild(tab.firstChild);
    }
    STATE.legacyMount = { tabId: meta.tabId };
  }

  function renderLegacySectionCanvas(view) {
    const meta = LEGACY_SECTION_META[view] || { testId: `user-app-next-${view}` };
    return `
      ${renderTopbar()}
      <div class="uapp-next-legacy-page" data-testid="${esc(meta.testId)}">
        <div class="uapp-next-legacy-mount" id="uappNextLegacyMount"></div>
      </div>`;
  }

  function setActiveClass(active) {
    document.body.classList.toggle('user-app-next-active', Boolean(active));
    if (!active) {
      document.body.classList.remove(
        'user-app-next-sidebar-collapsed',
        'user-app-next-view-vehicles',
        'user-app-next-view-legacy',
        'user-app-next-view-reservations',
        'user-app-next-view-support',
        'user-app-next-mobile-nav-open'
      );
      clearUserAppScreen();
    }
  }

  function navButton(label, iconSvg, action, active, badge, locked) {
    const badgeHtml = badge > 0 ? `<span class="uapp-next-nav-badge">${esc(String(badge))}</span>` : '';
    const lockHtml = locked ? '<span class="uapp-next-nav-lock" aria-hidden="true" title="Vyžaduje vyšší licenci">🔒</span>' : '';
    const lockClass = locked ? ' is-locked' : '';
    const testId = `dashboard-nav-${String(action || 'unknown').replace(/[^a-z0-9]+/gi, '-')}`;
    return `<button type="button" class="${active ? 'is-active' : ''}${lockClass}" data-uapp-action="${esc(action)}" data-testid="${esc(testId)}"${locked ? ' data-uapp-locked="1"' : ''}><span class="uapp-next-nav-ico" aria-hidden="true">${iconSvg}</span><span class="uapp-next-nav-label">${esc(label)}</span>${lockHtml}${badgeHtml}</button>`;
  }

  function reminderReferenceDate(reminder) {
    const notify = parseDate(reminder?.notify_at);
    if (notify) return notify;
    return parseDate(reminder?.due_date);
  }

  function reminderColumnKey(reminder) {
    if (reminder?.is_completed === true) return 'completed';
    const ref = reminderReferenceDate(reminder);
    if (!ref) return 'planned';
    const diff = daysUntil(ref);
    if (diff == null) return 'planned';
    if (diff < 0) return 'overdue';
    if (diff <= 60) return 'upcoming';
    return 'planned';
  }

  function reminderPriorityLabel(reminder) {
    const key = String(reminder?.type || '').toUpperCase();
    if (key === 'STK') return 'STK';
    if (key === 'OLEJ') return 'Olej';
    if (key === 'GENERAL') return 'Servis';
    if (key === 'VLASTNI') return 'Vlastní';
    return key || 'Připomínka';
  }

  function reminderSummaryStats(data) {
    const buckets = bucketReminders(data);
    const now = new Date();
    const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);
    let today = 0;
    let thisWeek = 0;
    (data?.reminders || []).forEach((item) => {
      if (item?.is_completed) return;
      const ref = reminderReferenceDate(item);
      const diff = ref ? daysUntil(ref) : null;
      if (diff === 0) today += 1;
      if (diff != null && diff >= 0 && diff <= 7) thisWeek += 1;
    });
    const completedMonth = (data?.reminders || []).filter((item) => {
      if (!item?.is_completed) return false;
      const ref = parseDate(item?.completed_at || item?.due_date || item?.updated_at);
      return ref && ref >= monthStart;
    }).length;
    return {
      today,
      thisWeek,
      overdue: buckets.overdue.length,
      completedMonth,
      planned: buckets.planned.length,
      upcoming: buckets.upcoming.length,
      completed: buckets.completed.length,
    };
  }

  function bucketReminders(data) {
    const buckets = { overdue: [], upcoming: [], planned: [], completed: [] };
    (data?.reminders || []).forEach((item) => {
      const col = reminderColumnKey(item);
      if (buckets[col]) buckets[col].push(item);
    });
    const sortByDate = (a, b) => {
      const da = reminderReferenceDate(a);
      const db = reminderReferenceDate(b);
      if (!da && !db) return 0;
      if (!da) return 1;
      if (!db) return -1;
      return da.getTime() - db.getTime();
    };
    buckets.overdue.sort(sortByDate);
    buckets.upcoming.sort(sortByDate);
    buckets.planned.sort(sortByDate);
    buckets.completed.sort((a, b) => {
      const da = parseDate(a?.completed_at || a?.due_date);
      const db = parseDate(b?.completed_at || b?.due_date);
      return (db?.getTime() || 0) - (da?.getTime() || 0);
    });
    return buckets;
  }

  function vehicleLabelById(data, vehicleId) {
    const id = Number(vehicleId);
    if (!id) return 'Bez vozidla';
    const vehicle = (data?.vehicles || []).find((v) => Number(v.id) === id);
    return vehicle ? getVehicleName(vehicle) : `Vozidlo #${id}`;
  }

  function reminderDueLabel(reminder) {
    const ref = reminderReferenceDate(reminder);
    if (!ref) return 'Bez termínu';
    const diff = daysUntil(ref);
    if (diff == null) return formatDate(ref);
    if (diff < 0) return `${Math.abs(diff) === 1 ? '1 den' : `${Math.abs(diff)} dní`} po termínu`;
    if (diff === 0) return 'Dnes';
    if (diff === 1) return 'Zítra';
    if (diff <= 14) return `Za ${diff} dní`;
    return formatDate(ref);
  }

  function renderReminderKanbanCard(item, data) {
    const id = Number(item.id);
    const col = reminderColumnKey(item);
    const vehicleId = Number(item?.vehicle_id) || 0;
    const vehicle = (data?.vehicles || []).find((v) => Number(v.id) === vehicleId);
    const plate = vehicle?.plate ? renderPlateBadge(vehicle.plate, 'sm') : '';
    return `
      <article class="uapp-rem-kanban-card is-${esc(col)}" data-testid="uapp-reminder-card-${id}">
        <div class="uapp-rem-kanban-card-top">
          <span class="uapp-rem-kanban-priority">${esc(reminderPriorityLabel(item))}</span>
          ${item?.is_manual === false ? '<span class="uapp-rem-kanban-auto">Auto</span>' : ''}
        </div>
        <h4 class="uapp-rem-kanban-title">${esc(String(item.text || item.title || item.type || 'Připomínka').trim())}</h4>
        <p class="uapp-rem-kanban-vehicle">${plate}<span>${esc(vehicleLabelById(data, vehicleId))}</span></p>
        <p class="uapp-rem-kanban-due ${col === 'overdue' ? 'is-overdue' : ''}">${esc(reminderDueLabel(item))}</p>
        <div class="uapp-rem-kanban-actions">
          ${col !== 'completed' ? `<button type="button" class="uapp-rem-kanban-btn" data-uapp-action="reminderComplete:${id}">✓ Splnit</button>` : ''}
          ${col !== 'completed' ? `<button type="button" class="uapp-rem-kanban-btn" data-uapp-action="reminderSnooze:${id}">◷ Odložit</button>` : ''}
          <button type="button" class="uapp-rem-kanban-btn" data-uapp-action="reminderDetail:${id}">▣ Detail</button>
        </div>
      </article>`;
  }

  function renderRemindersCalendar(data) {
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth();
    const first = new Date(year, month, 1);
    const startPad = (first.getDay() + 6) % 7;
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const monthLabel = first.toLocaleDateString('cs-CZ', { month: 'long', year: 'numeric' });
    const dueDays = new Set();
    (data?.reminders || []).forEach((item) => {
      if (item?.is_completed) return;
      const ref = reminderReferenceDate(item);
      if (!ref || ref.getFullYear() !== year || ref.getMonth() !== month) return;
      dueDays.add(ref.getDate());
    });
    let cells = '';
    for (let i = 0; i < startPad; i += 1) {
      cells += '<span class="uapp-rem-cal-day is-empty" aria-hidden="true"></span>';
    }
    for (let day = 1; day <= daysInMonth; day += 1) {
      const isToday = day === now.getDate();
      const hasDue = dueDays.has(day);
      cells += `<span class="uapp-rem-cal-day${isToday ? ' is-today' : ''}${hasDue ? ' has-due' : ''}">${day}</span>`;
    }
    return `
      <section class="uapp-rem-aside-card">
        <h3>Kalendář termínů</h3>
        <p class="uapp-rem-cal-month">${esc(monthLabel)}</p>
        <div class="uapp-rem-cal-weekdays" aria-hidden="true">
          <span>Po</span><span>Út</span><span>St</span><span>Čt</span><span>Pá</span><span>So</span><span>Ne</span>
        </div>
        <div class="uapp-rem-cal-grid" role="grid" aria-label="Kalendář připomínek">${cells}</div>
      </section>`;
  }

  function renderRemindersPage(data) {
    const stats = reminderSummaryStats(data);
    const buckets = bucketReminders(data);
    const columns = [
      { key: 'overdue', title: 'Po termínu', tone: 'danger' },
      { key: 'upcoming', title: 'Blíží se', tone: 'warn' },
      { key: 'planned', title: 'Naplánováno', tone: 'info' },
      { key: 'completed', title: 'Dokončeno', tone: 'ok' },
    ];
    const kanban = columns.map((col) => {
      const items = buckets[col.key] || [];
      return `
        <section class="uapp-rem-kanban-col is-${col.tone}" aria-label="${esc(col.title)}">
          <header class="uapp-rem-kanban-col-head">
            <h3>${esc(col.title)}</h3>
            <span class="uapp-rem-kanban-count">${items.length}</span>
          </header>
          <div class="uapp-rem-kanban-col-body">
            ${items.length
              ? items.map((item) => renderReminderKanbanCard(item, data)).join('')
              : '<p class="uapp-rem-kanban-empty">Žádné položky</p>'}
          </div>
        </section>`;
    }).join('');

    const tipBanner = STATE.remindersTipHidden ? '' : `
      <div class="uapp-rem-tip" role="note">
        <div>
          <strong>Tip</strong>
          <p>Tip: Připomínky se automaticky synchronizují s vozidly a jejich servisní historií.</p>
        </div>
        <button type="button" class="uapp-rem-tip-close" data-uapp-action="remindersTipClose" aria-label="Zavřít tip">×</button>
      </div>`;

    return `
      <div class="uapp-rem-page" data-testid="user-app-next-reminders">
        <header class="uapp-rem-page-head">
          <div>
            <h1 class="uapp-rem-page-title">Připomínky</h1>
            <p class="uapp-rem-page-sub">Hlídejte STK, pojištění, servis i vlastní úkoly</p>
          </div>
          <button type="button" class="uapp-next-btn uapp-next-btn-primary" data-uapp-action="newReminder">+ Nová připomínka</button>
        </header>
        <div class="uapp-rem-stats">
          <article class="uapp-rem-stat is-danger"><span class="uapp-rem-stat-ico" aria-hidden="true">📅</span><div><strong>${esc(String(stats.today))}</strong><span>Dnes</span><small>${esc(String(stats.today))} ${stats.today === 1 ? 'úkol' : 'úkoly'}</small></div></article>
          <article class="uapp-rem-stat is-warn"><span class="uapp-rem-stat-ico" aria-hidden="true">📅</span><div><strong>${esc(String(stats.thisWeek))}</strong><span>Tento týden</span><small>${esc(String(stats.thisWeek))} ${stats.thisWeek === 1 ? 'úkol' : 'úkolů'}</small></div></article>
          <article class="uapp-rem-stat is-danger-soft"><span class="uapp-rem-stat-ico" aria-hidden="true">!</span><div><strong>${esc(String(stats.overdue))}</strong><span>Po termínu</span><small>${esc(String(stats.overdue))} ${stats.overdue === 1 ? 'úkol' : 'úkoly'}</small></div></article>
          <article class="uapp-rem-stat is-ok"><span class="uapp-rem-stat-ico" aria-hidden="true">✓</span><div><strong>${esc(String(stats.completedMonth))}</strong><span>Dokončeno</span><small>tento měsíc</small></div></article>
        </div>
        <div class="uapp-rem-layout">
          <div class="uapp-rem-main">
            <div class="uapp-rem-kanban-board" role="region" aria-label="Kanban připomínek">${kanban}</div>
            ${tipBanner}
          </div>
          <aside class="uapp-rem-aside" aria-label="Nastavení připomínek">
            ${renderRemindersCalendar(data)}
            <section class="uapp-rem-aside-card">
              <h3>Automatické připomínky</h3>
              <label class="uapp-rem-toggle"><input type="checkbox" checked disabled><span>STK / SME před termínem</span></label>
              <label class="uapp-rem-toggle"><input type="checkbox" checked disabled><span>Pojištění před vypršením</span></label>
              <label class="uapp-rem-toggle"><input type="checkbox" checked disabled><span>Servisní intervaly</span></label>
              <p class="uapp-rem-aside-hint">Nastavení upravíte v sekci Nastavení účtu.</p>
            </section>
            <section class="uapp-rem-aside-card">
              <h3>Doporučení pro vozidla</h3>
              <ul class="uapp-rem-rec-list">
                ${(data?.vehicles || []).slice(0, 3).map((vehicle) => {
                  const stk = stkFieldMeta(vehicle);
                  const hint = stk.tone === 'bad' || stk.tone === 'warn'
                    ? `STK ${stk.label}`
                    : (serviceFieldMeta(recordsFor(data, vehicle.id)).tone === 'warn' ? 'Zkontrolujte servis' : 'V pořádku');
                  return `<li><button type="button" data-uapp-action="detail:${Number(vehicle.id)}"><strong>${esc(getVehicleName(vehicle))}</strong><span>${esc(hint)}</span></button></li>`;
                }).join('') || '<li class="uapp-rem-rec-empty">Zatím bez vozidel.</li>'}
              </ul>
            </section>
          </aside>
        </div>
      </div>`;
  }

  function flattenAllRecords(data) {
    const rows = [];
    (data?.recordEntries || []).forEach((entry) => {
      const vehicle = entry?.vehicle;
      const vehicleId = Number(vehicle?.id) || 0;
      (entry?.records || []).forEach((record) => {
        rows.push({ vehicle, vehicleId, record });
      });
    });
    rows.sort((a, b) => (Date.parse(b.record?.performed_at || b.record?.created_at) || 0) - (Date.parse(a.record?.performed_at || a.record?.created_at) || 0));
    return rows;
  }

  function formatMoneyCzk(value) {
    const num = Number(value);
    if (!Number.isFinite(num) || num <= 0) return '—';
    try {
      return `${num.toLocaleString('cs-CZ', { maximumFractionDigits: 0 })} Kč`;
    } catch (_) {
      return `${Math.round(num)} Kč`;
    }
  }

  function serviceRecordIconClass(record) {
    const type = String(record?.service_type || record?.category || '').toLowerCase();
    if (type.includes('stk') || type.includes('technick')) return 'stk';
    if (type.includes('olej') || type.includes('oil')) return 'oil';
    if (type.includes('brzd') || type.includes('brake')) return 'brakes';
    if (type.includes('pneu') || type.includes('tire')) return 'tires';
    return 'service';
  }

  function serviceRecordStatusMeta(record) {
    const status = String(record?.record_status || '').toLowerCase();
    if (status === 'in_progress' || status === 'draft' || status === 'pending') {
      return { label: 'Čeká na ověření', tone: 'warn' };
    }
    if (status === 'cancelled' || status === 'canceled') {
      return { label: 'Zrušeno', tone: 'muted' };
    }
    return { label: 'Ověřeno', tone: 'ok' };
  }

  function serviceRecordIconGlyph(record) {
    const cls = serviceRecordIconClass(record);
    const map = { stk: '✓', oil: '🛢', brakes: '◉', tires: '◎', service: '⚙' };
    return map[cls] || map.service;
  }

  function filterServiceHistoryRows(data) {
    const filters = STATE.serviceHistoryFilters || {};
    let rows = flattenAllRecords(data);
    if (filters.vehicle && filters.vehicle !== 'all') {
      const vid = Number(filters.vehicle);
      rows = rows.filter((entry) => Number(entry.vehicleId) === vid);
    }
    if (filters.period === '1y') {
      const cutoff = Date.now() - (365 * 86400000);
      rows = rows.filter((entry) => (Date.parse(entry.record?.performed_at || entry.record?.created_at) || 0) >= cutoff);
    } else if (filters.period === '2y') {
      const cutoff = Date.now() - (730 * 86400000);
      rows = rows.filter((entry) => (Date.parse(entry.record?.performed_at || entry.record?.created_at) || 0) >= cutoff);
    }
    if (filters.docStatus === 'with_doc') {
      rows = rows.filter((entry) => Array.isArray(entry.record?.attachments) && entry.record.attachments.length > 0);
    }
    return rows;
  }

  function serviceHistoryTopActions(data) {
    const counts = {};
    flattenAllRecords(data).forEach((entry) => {
      const title = String(entry.record?.description || entry.record?.service_type || 'Servis').trim();
      const key = title.length > 28 ? `${title.slice(0, 28)}…` : title;
      counts[key] = (counts[key] || 0) + 1;
    });
    return Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 5);
  }

  function serviceHistoryWorkshops(data) {
    const map = new Map();
    flattenAllRecords(data).forEach((entry) => {
      const name = String(entry.record?.service_name || entry.record?.workshop_name || 'TooZServis').trim() || 'TooZServis';
      const price = Number(entry.record?.total_price ?? entry.record?.price);
      const hit = map.get(name) || { name, count: 0, total: 0 };
      hit.count += 1;
      if (Number.isFinite(price) && price > 0) hit.total += price;
      map.set(name, hit);
    });
    return Array.from(map.values()).sort((a, b) => b.count - a.count).slice(0, 4);
  }

  function serviceHistoryStats(data) {
    const rows = filterServiceHistoryRows(data);
    const limit = STATE.serviceHistoryLimit || 8;
    const visible = rows.slice(0, limit);
    let totalCost = 0;
    let costCount = 0;
    rows.forEach((entry) => {
      const price = Number(entry.record?.total_price ?? entry.record?.price);
      if (Number.isFinite(price) && price > 0) {
        totalCost += price;
        costCount += 1;
      }
    });
    const mid = Math.floor(visible.length / 2);
    let firstHalf = 0;
    let secondHalf = 0;
    visible.forEach((entry, idx) => {
      const price = Number(entry.record?.total_price ?? entry.record?.price);
      if (!Number.isFinite(price) || price <= 0) return;
      if (idx < mid) firstHalf += price;
      else secondHalf += price;
    });
    let trendPct = null;
    if (firstHalf > 0 && secondHalf >= 0) {
      trendPct = Math.round(((secondHalf - firstHalf) / firstHalf) * 100);
    }
    return {
      totalRecords: rows.length,
      visibleCount: visible.length,
      totalCost,
      averageCost: costCount ? totalCost / costCount : 0,
      trendPct,
      workshops: serviceHistoryWorkshops(data),
      topActions: serviceHistoryTopActions(data),
    };
  }

  function renderServiceHistoryRecordRow(entry) {
    const { vehicle, vehicleId, record } = entry;
    const meta = serviceRecordStatusMeta(record);
    const iconClass = serviceRecordIconClass(record);
    const title = String(record?.description || record?.service_type || 'Servisní záznam').trim();
    const dateLabel = formatDate(record?.performed_at || record?.created_at);
    const cost = formatMoneyCzk(record?.total_price ?? record?.price);
    const km = record?.mileage_km != null && record.mileage_km !== ''
      ? `${Number(record.mileage_km).toLocaleString('cs-CZ')} km`
      : (vehicle?.current_mileage_km != null ? `${Number(vehicle.current_mileage_km).toLocaleString('cs-CZ')} km` : '');
    const workshop = String(record?.service_name || record?.workshop_name || 'TooZServis').trim() || 'TooZServis';
    const recordId = Number(record?.id) || 0;
    const attCount = Array.isArray(record?.attachments) ? record.attachments.length : 0;
    return `
      <article class="uapp-sh-record">
        <div class="uapp-sh-record-date">
          <strong>${esc(dateLabel)}</strong>
          ${km ? `<span>${esc(km)}</span>` : ''}
        </div>
        <div class="uapp-sh-record-icon is-${esc(iconClass)}" aria-hidden="true">${serviceRecordIconGlyph(record)}</div>
        <div class="uapp-sh-record-main">
          <h4>${esc(title)}</h4>
          <p class="uapp-sh-record-vehicle">
            <span>${esc(getVehicleName(vehicle || {}))}</span>
            ${vehicle?.plate ? renderPlateBadge(vehicle.plate, 'sm') : ''}
          </p>
          <p class="uapp-sh-record-workshop">${esc(workshop)}</p>
          <div class="uapp-sh-record-meta">
            <span class="uapp-sh-cost">${esc(cost)}</span>
            <span class="uapp-sh-status is-${meta.tone}">${esc(meta.label)}</span>
            ${attCount ? `<span class="uapp-sh-att">📎 ${attCount}</span>` : ''}
          </div>
        </div>
        <div class="uapp-sh-record-actions">
          <button type="button" data-uapp-action="serviceRecordDetail:${vehicleId}">Detail</button>
          <button type="button" data-uapp-action="detailTab:documents:${vehicleId}">Dokumenty</button>
          ${recordId && hasFn('openEditServiceRecordModal') ? `<button type="button" data-uapp-action="serviceRecordEdit:${vehicleId}:${recordId}">Upravit</button>` : ''}
        </div>
      </article>`;
  }

  function renderServiceHistoryTimeline(data) {
    const rows = filterServiceHistoryRows(data);
    const limit = STATE.serviceHistoryLimit || 8;
    const visible = rows.slice(0, limit);
    if (!visible.length) {
      return '<p class="uapp-sh-empty">Zatím nemáte žádné servisní záznamy. Přidejte první záznam tlačítkem výše nebo z detailu vozidla.</p>';
    }
    let html = '';
    let lastYear = null;
    visible.forEach((entry) => {
      const d = parseDate(entry.record?.performed_at || entry.record?.created_at);
      const year = d ? d.getFullYear() : null;
      if (year && year !== lastYear) {
        html += `<div class="uapp-sh-year" aria-hidden="true">${year}</div>`;
        lastYear = year;
      }
      html += renderServiceHistoryRecordRow(entry);
    });
    return html;
  }

  function renderServiceHistoryFilters(data) {
    const f = STATE.serviceHistoryFilters || {};
    const vehicleOptions = (data?.vehicles || []).map((v) => {
      const id = Number(v.id);
      const selected = String(f.vehicle) === String(id) ? ' selected' : '';
      return `<option value="${id}"${selected}>${esc(getVehicleName(v))}</option>`;
    }).join('');
    return `
      <div class="uapp-sh-filters" role="region" aria-label="Filtry historie">
        <label class="uapp-sh-filter-field"><span>Vozidlo</span>
          <select data-uapp-sh-filter="vehicle">
            <option value="all"${f.vehicle === 'all' ? ' selected' : ''}>Všechna vozidla</option>
            ${vehicleOptions}
          </select>
        </label>
        <label class="uapp-sh-filter-field"><span>Období</span>
          <select data-uapp-sh-filter="period">
            <option value="2y"${f.period === '2y' ? ' selected' : ''}>Poslední 2 roky</option>
            <option value="1y"${f.period === '1y' ? ' selected' : ''}>Poslední rok</option>
            <option value="all"${f.period === 'all' ? ' selected' : ''}>Celá historie</option>
          </select>
        </label>
        <label class="uapp-sh-filter-field"><span>Typ úkonu</span>
          <select data-uapp-sh-filter="type">
            <option value="all"${f.type === 'all' ? ' selected' : ''}>Všechny typy</option>
          </select>
        </label>
        <label class="uapp-sh-filter-field"><span>Servis</span>
          <select data-uapp-sh-filter="service">
            <option value="all"${f.service === 'all' ? ' selected' : ''}>Všechny servisy</option>
          </select>
        </label>
        <label class="uapp-sh-filter-field"><span>Stav dokladu</span>
          <select data-uapp-sh-filter="docStatus">
            <option value="all"${f.docStatus === 'all' ? ' selected' : ''}>Všechny stavy</option>
            <option value="with_doc"${f.docStatus === 'with_doc' ? ' selected' : ''}>S dokladem</option>
          </select>
        </label>
        <button type="button" class="uapp-sh-filter-reset" data-uapp-action="serviceHistoryResetFilters">↺ Vymazat filtry</button>
      </div>`;
  }

  function renderServiceHistoryPage(data) {
    const rows = filterServiceHistoryRows(data);
    const limit = STATE.serviceHistoryLimit || 8;
    const stats = serviceHistoryStats(data);
    const hasMore = rows.length > limit;
    const trendHtml = stats.trendPct == null
      ? ''
      : `<p class="uapp-sh-trend${stats.trendPct <= 0 ? ' is-down' : ' is-up'}">${stats.trendPct <= 0 ? '↓' : '↑'} ${esc(String(Math.abs(stats.trendPct)))} % ${stats.trendPct <= 0 ? 'méně' : 'více'} než předchozí období</p>`;

    const workshopList = stats.workshops.length
      ? stats.workshops.map((ws) => `<li><strong>${esc(ws.name)}</strong><span>${esc(String(ws.count))} zásahů · ${esc(formatMoneyCzk(ws.total))}</span></li>`).join('')
      : '<li class="uapp-sh-widget-empty">Zatím bez evidovaných servisů.</li>';

    const topActions = stats.topActions.length
      ? stats.topActions.map(([label, count]) => `<li><span>${esc(label)}</span><strong>${esc(String(count))}×</strong></li>`).join('')
      : '<li class="uapp-sh-widget-empty">Zatím bez opakovaných úkonů.</li>';

    return `
      <div class="uapp-sh-page" data-testid="user-app-next-service-history">
        <header class="uapp-sh-page-head">
          <div>
            <h1 class="uapp-sh-page-title">Servisní historie</h1>
            <p class="uapp-sh-page-sub">Kompletní přehled servisních zásahů napříč vašimi vozidly</p>
          </div>
          ${hasFn('openAddServiceRecordModal') ? '<button type="button" class="uapp-next-btn uapp-next-btn-primary" data-uapp-action="serviceHistoryAdd">+ Přidat servisní záznam</button>' : ''}
        </header>
        ${renderServiceHistoryFilters(data)}
        <div class="uapp-sh-layout">
          <div class="uapp-sh-main">
            <div class="uapp-sh-list-head">
              <h2>Servisní záznamy</h2>
              <span class="uapp-sh-list-count">${esc(String(stats.totalRecords))} záznamů</span>
            </div>
            <section class="uapp-sh-timeline" aria-label="Servisní záznamy">
              ${renderServiceHistoryTimeline(data)}
            </section>
            ${hasMore ? `<button type="button" class="uapp-sh-load-more" data-uapp-action="loadMoreServiceHistory">Načíst další záznamy ▾</button>` : ''}
          </div>
          <aside class="uapp-sh-aside" aria-label="Souhrn servisní historie">
            <section class="uapp-sh-widget">
              <div class="uapp-sh-widget-head">
                <h3>Souhrn nákladů</h3>
                <span class="uapp-sh-widget-period">Poslední 2 roky</span>
              </div>
              <p class="uapp-sh-widget-kpi">${esc(formatMoneyCzk(stats.totalCost))}</p>
              ${trendHtml}
              <div class="uapp-sh-chart-placeholder" aria-hidden="true"><svg viewBox="0 0 200 48" preserveAspectRatio="none"><polyline fill="none" stroke="currentColor" stroke-width="2.5" points="0,40 30,34 60,28 90,32 120,18 150,22 180,12 200,16"/></svg></div>
            </section>
            <section class="uapp-sh-widget">
              <h3>Nejčastější úkony</h3>
              <ul class="uapp-sh-top-actions">${topActions}</ul>
            </section>
            <section class="uapp-sh-widget">
              <h3>Servisy, které vozidla obsluhovaly</h3>
              <ul class="uapp-sh-workshops">${workshopList}</ul>
              <button type="button" class="uapp-sh-widget-link" data-uapp-action="servicesDirectory">Zobrazit všechny servisy ›</button>
            </section>
            <section class="uapp-sh-widget">
              <h3>Doporučené další kroky</h3>
              <ul class="uapp-sh-rec">
                ${(data?.vehicles || []).slice(0, 2).map((vehicle) => {
                  const svc = serviceFieldMeta(recordsFor(data, vehicle.id));
                  if (svc.tone !== 'warn') return '';
                  return `<li class="uapp-sh-rec-card is-warn"><button type="button" data-uapp-action="detail:${Number(vehicle.id)}"><strong>Vyměnit brzdovou kapalinu</strong><span>${esc(getVehicleName(vehicle))} · ${esc(svc.label)}</span></button></li>`;
                }).filter(Boolean).join('') || '<li class="uapp-sh-widget-empty">Všechna vozidla mají aktuální servis.</li>'}
              </ul>
              <button type="button" class="uapp-sh-widget-link" data-uapp-action="reminders">Zobrazit všechny doporučené kroky ›</button>
            </section>
          </aside>
        </div>
      </div>`;
  }

  function bindServiceHistoryFilters() {
    document.querySelectorAll('[data-uapp-sh-filter]').forEach((select) => {
      if (select.dataset.uappShBound === '1') return;
      select.dataset.uappShBound = '1';
      select.addEventListener('change', () => {
        const key = select.getAttribute('data-uapp-sh-filter');
        if (!key) return;
        STATE.serviceHistoryFilters = STATE.serviceHistoryFilters || {};
        STATE.serviceHistoryFilters[key] = select.value;
        STATE.serviceHistoryLimit = 8;
        render();
      });
    });
  }

  function formatDocumentSize(bytes) {
    const value = Number(bytes);
    if (!Number.isFinite(value) || value <= 0) return '';
    if (typeof formatAttachmentSize === 'function') return formatAttachmentSize(value);
    if (value < 1024) return `${value} B`;
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
    return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  }

  function resolveAttachmentFileSize(data, recordId, fileName) {
    const id = Number(recordId);
    if (!Number.isFinite(id) || id <= 0) return null;
    const records = (data?.recordEntries || []).flatMap((entry) => entry.records || []);
    const record = records.find((item) => Number(item?.id) === id);
    if (!record?.attachments) return null;
    let attachments = record.attachments;
    if (typeof attachments === 'string') {
      try { attachments = JSON.parse(attachments); } catch (_) { return null; }
    }
    if (!Array.isArray(attachments)) return null;
    const hit = attachments.find((item) => String(item?.file_name || '').trim() === String(fileName || '').trim());
    const size = Number(hit?.file_size);
    return Number.isFinite(size) && size > 0 ? size : null;
  }

  function estimateDocumentSizeBytes(row) {
    if (row.fileSizeBytes) return row.fileSizeBytes;
    if (row.fileType === 'PDF') return 850000;
    if (row.fileType === 'XLSX') return 420000;
    if (row.fileType === 'DOCX') return 310000;
    if (row.fileType === 'JPG' || row.fileType === 'PNG') return 1800000;
    return 240000;
  }

  function computeDocumentsStorage(data, rows) {
    const usedBytes = rows.reduce((sum, row) => sum + estimateDocumentSizeBytes(row), 0);
    const quotaBytes = 10 * 1024 * 1024 * 1024;
    const pct = quotaBytes > 0 ? Math.min(100, Math.round((usedBytes / quotaBytes) * 100)) : 0;
    const usedGb = usedBytes / (1024 * 1024 * 1024);
    const usedLabel = usedGb >= 0.1 ? `${usedGb.toFixed(1)} GB` : `${(usedBytes / (1024 * 1024)).toFixed(1)} MB`;
    return { usedBytes, quotaBytes, pct, usedLabel };
  }

  const DOC_CATEGORY_META = {
    pojisteni: { label: 'Pojištění', tone: 'insurance' },
    technicke: { label: 'Technické kontroly', tone: 'technical' },
    servis: { label: 'Servis', tone: 'service' },
    faktury: { label: 'Faktury', tone: 'invoice' },
    ostatni: { label: 'Ostatní', tone: 'other' },
  };

  function fileTypeFromDocument(name, mimeType) {
    const mime = String(mimeType || '').toLowerCase();
    const ext = String(name || '').split('.').pop().toLowerCase();
    if (mime.includes('pdf') || ext === 'pdf') return 'PDF';
    if (['xlsx', 'xls'].includes(ext) || mime.includes('spreadsheet') || mime.includes('excel')) return 'XLSX';
    if (['docx', 'doc'].includes(ext) || mime.includes('word')) return 'DOCX';
    if (['jpg', 'jpeg'].includes(ext) || mime.includes('jpeg')) return 'JPG';
    if (ext === 'png' || mime.includes('png')) return 'PNG';
    return ext ? ext.toUpperCase() : 'SOUBOR';
  }

  function resolveDocumentCategoryKey(rawCategory, kind, fileName) {
    const hay = `${rawCategory || ''} ${fileName || ''} ${kind || ''}`.toLowerCase();
    if (hay.includes('poji') || hay.includes('insur')) return 'pojisteni';
    if (hay.includes('fakt') || hay.includes('invoice')) return 'faktury';
    if (kind === 'technical_cert' || kind === 'tachometer' || hay.includes('stk') || hay.includes('sme') || hay.includes('technick') || hay.includes('tachomet')) {
      return 'technicke';
    }
    if (kind === 'report' || kind === 'attachment' || hay.includes('servis')) return 'servis';
    return 'ostatni';
  }

  function vehicleById(data, vehicleId) {
    const id = Number(vehicleId);
    if (window._lastVehiclesById && window._lastVehiclesById[id]) return window._lastVehiclesById[id];
    return (data?.vehicles || []).find((item) => Number(item?.id) === id) || null;
  }

  function vehicleSubtitle(vehicle) {
    if (!vehicle) return '';
    const parts = [vehicle.brand, vehicle.model].filter(Boolean);
    if (parts.length) return parts.join(' ');
    return getVehicleName(vehicle);
  }

  function resolveDocumentExpiry(vehicle, categoryKey, item, kind) {
    if (categoryKey === 'pojisteni' && vehicle?.insurance_valid_until) return vehicle.insurance_valid_until;
    if (categoryKey === 'technicke') {
      if (kind === 'tachometer' && item?.check_date) return item.check_date;
      if (vehicle?.stk_valid_until) return vehicle.stk_valid_until;
    }
    return null;
  }

  function renderExpiryCell(expiryAt) {
    if (!expiryAt) return '<span class="uapp-doc-expiry is-muted">—</span>';
    const diff = daysUntil(expiryAt);
    const dateLabel = formatDate(expiryAt);
    if (diff == null) return `<span class="uapp-doc-expiry">${esc(dateLabel)}</span>`;
    let tone = 'ok';
    if (diff < 0) tone = 'danger';
    else if (diff <= 60) tone = 'warn';
    const countdown = diff === 0
      ? 'dnes'
      : (diff > 0 ? `za ${diff} ${diff === 1 ? 'den' : (diff < 5 ? 'dny' : 'dní')}` : `po ${Math.abs(diff)} ${Math.abs(diff) === 1 ? 'dni' : 'dnech'}`);
    return `<span class="uapp-doc-expiry is-${tone}">${esc(dateLabel)} <small>(${esc(countdown)})</small></span>`;
  }

  function buildDocumentsRows(data) {
    const hub = data?.documentsHub;
    if (!hub || typeof hub !== 'object') return [];
    const uploader = profileName();
    const rows = [];

    (hub.attachments || []).forEach((item, index) => {
      const vehicle = vehicleById(data, item.vehicle_id);
      const categoryKey = resolveDocumentCategoryKey(item.category, 'attachment', item.file_name);
      const category = DOC_CATEGORY_META[categoryKey] || DOC_CATEGORY_META.ostatni;
      const fileType = fileTypeFromDocument(item.file_name, item.mime_type);
      const uploadedAt = item.performed_at || null;
      rows.push({
        id: `att-${item.vehicle_id}-${item.record_id}-${index}`,
        kind: 'attachment',
        name: item.file_name || 'Doklad',
        fileType,
        fileSizeBytes: resolveAttachmentFileSize(data, item.record_id, item.file_name),
        vehicleId: Number(item.vehicle_id),
        vehiclePlate: vehicle?.plate || item.vehicle_name || '—',
        vehicleModel: vehicleSubtitle(vehicle),
        categoryKey,
        category,
        uploadedAt,
        uploadedBy: uploader,
        expiryAt: resolveDocumentExpiry(vehicle, categoryKey, item, 'attachment'),
        downloadUrl: item.download_url || '',
        recordId: item.record_id,
      });
    });

    (hub.reports || []).forEach((item) => {
      const vehicle = vehicleById(data, item.vehicle_id);
      const category = DOC_CATEGORY_META.servis;
      const uploadedAt = item.finalized_at || null;
      rows.push({
        id: `rep-${item.vehicle_id}`,
        kind: 'report',
        name: `Servisní historie — ${item.vehicle_name || getVehicleName(vehicle)}`,
        fileType: 'PDF',
        vehicleId: Number(item.vehicle_id),
        vehiclePlate: vehicle?.plate || item.vehicle_name || '—',
        vehicleModel: vehicleSubtitle(vehicle),
        categoryKey: 'servis',
        category,
        uploadedAt,
        uploadedBy: uploader,
        expiryAt: null,
        hasVerified: Boolean(item.has_verified_report),
        verifyUrl: item.verify_url || '',
      });
      if (item.has_verified_report) {
        rows.push({
          id: `repv-${item.vehicle_id}`,
          kind: 'verified_report',
          name: `Digitální výpis — ${item.vehicle_name || getVehicleName(vehicle)}`,
          fileType: 'PDF',
          vehicleId: Number(item.vehicle_id),
          vehiclePlate: vehicle?.plate || item.vehicle_name || '—',
          vehicleModel: vehicleSubtitle(vehicle),
          categoryKey: 'servis',
          category,
          uploadedAt,
          uploadedBy: uploader,
          expiryAt: null,
          verifyUrl: item.verify_url || '',
        });
      }
    });

    (hub.technical_certificates || []).forEach((item) => {
      const vehicle = vehicleById(data, item.vehicle_id);
      const category = DOC_CATEGORY_META.technicke;
      rows.push({
        id: `vtp-${item.vehicle_id}`,
        kind: 'technical_cert',
        name: item.document_title || 'Velký technický průkaz',
        fileType: 'PDF',
        vehicleId: Number(item.vehicle_id),
        vehiclePlate: vehicle?.plate || item.vehicle_name || '—',
        vehicleModel: vehicleSubtitle(vehicle),
        categoryKey: 'technicke',
        category,
        uploadedAt: item.generated_at || null,
        uploadedBy: uploader,
        expiryAt: resolveDocumentExpiry(vehicle, 'technicke', item, 'technical_cert'),
        downloadUrl: item.download_url || '',
      });
    });

    (hub.tachometer_documents || []).forEach((item) => {
      const vehicle = vehicleById(data, item.vehicle_id);
      const category = DOC_CATEGORY_META.technicke;
      const label = item.protocol_number
        ? `Protokol tachometru ${item.protocol_number}`
        : 'Protokol tachometru';
      rows.push({
        id: `tach-${item.vehicle_id}-${item.history_entry_id}`,
        kind: 'tachometer',
        name: label,
        fileType: 'PDF',
        vehicleId: Number(item.vehicle_id),
        vehiclePlate: vehicle?.plate || item.vehicle_name || '—',
        vehicleModel: vehicleSubtitle(vehicle),
        categoryKey: 'technicke',
        category,
        uploadedAt: item.check_date || null,
        uploadedBy: uploader,
        expiryAt: resolveDocumentExpiry(vehicle, 'technicke', item, 'tachometer'),
        detailUrl: item.detail_url || '',
      });
    });

    return rows;
  }

  function filterDocumentsRows(rows, data) {
    const filters = STATE.documentsFilters || {};
    const search = String(filters.search || '').trim().toLowerCase();
    return rows.filter((row) => {
      if (filters.category && filters.category !== 'all' && row.categoryKey !== filters.category) return false;
      if (filters.type && filters.type !== 'all' && row.fileType !== filters.type) return false;
      if (filters.vehicle && filters.vehicle !== 'all' && Number(filters.vehicle) !== Number(row.vehicleId)) return false;
      if (!search) return true;
      const hay = `${row.name} ${row.vehiclePlate} ${row.vehicleModel} ${row.category.label} ${row.fileType}`.toLowerCase();
      return hay.includes(search);
    });
  }

  function sortDocumentsRows(rows) {
    const sort = STATE.documentsSort || { key: 'uploadedAt', dir: 'desc' };
    const dir = sort.dir === 'asc' ? 1 : -1;
    return rows.slice().sort((a, b) => {
      if (sort.key === 'name') {
        return dir * String(a.name).localeCompare(String(b.name), 'cs');
      }
      const av = Date.parse(a.uploadedAt || 0) || 0;
      const bv = Date.parse(b.uploadedAt || 0) || 0;
      if (av === bv) return dir * String(a.name).localeCompare(String(b.name), 'cs');
      return dir * (av - bv);
    });
  }

  function documentsCategoryStats(rows) {
    const stats = Object.keys(DOC_CATEGORY_META).reduce((acc, key) => {
      acc[key] = 0;
      return acc;
    }, {});
    rows.forEach((row) => {
      if (stats[row.categoryKey] != null) stats[row.categoryKey] += 1;
    });
    return stats;
  }

  function renderDocumentsFileIcon(fileType) {
    const type = String(fileType || '').toUpperCase();
    const cls = type === 'PDF' ? 'is-pdf' : (type === 'XLSX' ? 'is-xlsx' : (type === 'DOCX' ? 'is-docx' : 'is-other'));
    const label = type === 'PDF' ? 'PDF' : (type === 'XLSX' ? 'XLS' : (type === 'DOCX' ? 'DOC' : type.slice(0, 3)));
    return `<span class="uapp-doc-file-ico ${cls}" aria-hidden="true">${esc(label)}</span>`;
  }

  function openDocumentPreviewFromParts(action) {
    const parts = String(action || '').split(':');
    const kind = parts[0];
    if (kind === 'report' && hasFn('previewVehicleReportFromHub')) {
      return window.previewVehicleReportFromHub(Number(parts[1] || 0));
    }
    if (kind === 'verified_report' && hasFn('previewVehicleVerifiedReportFromHub')) {
      return window.previewVehicleVerifiedReportFromHub(Number(parts[1] || 0));
    }
    if (kind === 'technical_cert' && hasFn('openVehicleLargeTechnicalCertificatePreview')) {
      return void window.openVehicleLargeTechnicalCertificatePreview(Number(parts[1] || 0));
    }
    let url = '';
    let fileName = 'doklad';
    if (kind === 'attachment') {
      url = decodeURIComponent(parts[2] || '');
      fileName = decodeURIComponent(parts.slice(3).join(':') || 'doklad');
    } else if (String(parts[0] || '').includes('%2F') || String(parts[0] || '').startsWith('/')) {
      url = decodeURIComponent(parts[0] || '');
      fileName = decodeURIComponent(parts.slice(1).join(':') || 'doklad');
    } else {
      url = decodeURIComponent(parts[1] || '');
      fileName = decodeURIComponent(parts.slice(2).join(':') || 'doklad');
    }
    if (url && hasFn('openServiceRecordAttachmentPreview')) {
      return window.openServiceRecordAttachmentPreview(encodeURIComponent(url), encodeURIComponent(fileName));
    }
    return undefined;
  }

  function renderDocumentsDownloadBtn(row) {
    return `<button type="button" class="uapp-doc-icon-btn" data-uapp-action="docPreview:${row.kind}:${row.vehicleId}:${encodeURIComponent(row.downloadUrl || '')}:${encodeURIComponent(row.name)}" aria-label="Náhled">${ICO.detail}</button>`;
  }

  function renderDocumentsRowMenu(row) {
    const open = STATE.documentsMenuOpenId === row.id;
    const items = [];
    if (row.kind === 'attachment' && row.downloadUrl) {
      items.push(`<button type="button" data-uapp-action="docPreview:${encodeURIComponent(row.downloadUrl)}:${encodeURIComponent(row.name)}">Náhled</button>`);
    } else if (['report', 'verified_report', 'technical_cert'].includes(row.kind)) {
      items.push(`<button type="button" data-uapp-action="docPreview:${row.kind}:${row.vehicleId}:${encodeURIComponent(row.downloadUrl || '')}:${encodeURIComponent(row.name)}">Náhled</button>`);
    }
    items.push(`<button type="button" data-uapp-action="docDownload:${row.kind}:${row.vehicleId}:${encodeURIComponent(row.downloadUrl || '')}">Stáhnout</button>`);
    items.push(`<button type="button" data-uapp-action="documentsVehicle:${row.vehicleId}">Otevřít vozidlo</button>`);
    if (row.verifyUrl) {
      items.push(`<button type="button" data-uapp-action="docVerify:${encodeURIComponent(row.verifyUrl)}">Veřejné ověření</button>`);
    }
    if (row.kind === 'tachometer' && row.detailUrl) {
      items.push(`<button type="button" data-uapp-action="docTachometerDetail:${encodeURIComponent(row.detailUrl)}:${row.vehicleId}">Detail protokolu</button>`);
    }
    return `
      <div class="uapp-doc-row-menu${open ? ' is-open' : ''}">
        <button type="button" class="uapp-doc-icon-btn" data-uapp-action="docMenuToggle:${encodeURIComponent(row.id)}" aria-label="Další akce">${ICO.more}</button>
        ${open ? `<div class="uapp-doc-row-menu-pop">${items.join('')}</div>` : ''}
      </div>`;
  }

  function renderDocumentsTableRow(row) {
    const sizeLabel = formatDocumentSize(row.fileSizeBytes) || formatDocumentSize(estimateDocumentSizeBytes(row));
    return `
      <tr data-doc-row-id="${esc(row.id)}">
        <td class="uapp-doc-col-name">
          <div class="uapp-doc-name-cell">
            ${renderDocumentsFileIcon(row.fileType)}
            <div>
              <strong>${esc(row.name)}</strong>
              <span class="uapp-doc-file-meta">${esc(sizeLabel)}</span>
            </div>
          </div>
        </td>
        <td class="uapp-doc-col-vehicle">
          <strong>${esc(row.vehiclePlate)}</strong>
          <span>${esc(row.vehicleModel)}</span>
        </td>
        <td><span class="uapp-doc-cat is-${row.category.tone}">${esc(row.category.label)}</span></td>
        <td class="uapp-doc-col-type">${esc(row.fileType)}</td>
        <td class="uapp-doc-col-uploaded">
          <strong>${esc(formatDate(row.uploadedAt))}</strong>
          <span>${esc(row.uploadedBy)}</span>
        </td>
        <td>${renderExpiryCell(row.expiryAt)}</td>
        <td class="uapp-doc-col-actions">
          ${renderDocumentsDownloadBtn(row)}
          ${renderDocumentsRowMenu(row)}
        </td>
      </tr>`;
  }

  function renderDocumentsPagination(total, page, perPage) {
    const totalPages = Math.max(1, Math.ceil(total / perPage));
    const safePage = Math.min(Math.max(1, page), totalPages);
    const start = total === 0 ? 0 : ((safePage - 1) * perPage) + 1;
    const end = Math.min(total, safePage * perPage);
    const pages = [];
    for (let i = 1; i <= totalPages; i += 1) {
      if (totalPages > 7 && i > 2 && i < totalPages - 1 && Math.abs(i - safePage) > 1) {
        if (pages[pages.length - 1] !== '…') pages.push('…');
        continue;
      }
      pages.push(i);
    }
    const pageButtons = pages.map((item) => {
      if (item === '…') return '<span class="uapp-doc-page-ellipsis">…</span>';
      return `<button type="button" class="uapp-doc-page-btn${item === safePage ? ' is-active' : ''}" data-uapp-action="documentsPage:${item}">${item}</button>`;
    }).join('');
    return `
      <div class="uapp-doc-pagination">
        <span class="uapp-doc-pagination-info">Zobrazeno ${esc(String(start))}-${esc(String(end))} z ${esc(String(total))}</span>
        <div class="uapp-doc-pagination-pages">
          <button type="button" class="uapp-doc-page-nav" data-uapp-action="documentsPagePrev" aria-label="Předchozí stránka"${safePage <= 1 ? ' disabled' : ''}>&lt;</button>
          ${pageButtons}
          <button type="button" class="uapp-doc-page-nav" data-uapp-action="documentsPageNext" aria-label="Další stránka"${safePage >= totalPages ? ' disabled' : ''}>&gt;</button>
        </div>
        <label class="uapp-doc-per-page">
          <select data-uapp-doc-filter="perPage">
            ${[10, 20, 50].map((n) => `<option value="${n}"${Number(perPage) === n ? ' selected' : ''}>${n} na stránku</option>`).join('')}
          </select>
        </label>
      </div>`;
  }

  function renderDocumentsUploadPicker(data) {
    if (!STATE.documentsUploadPickerOpen) return '';
    const vehicles = data?.vehicles || [];
    return `
      <div class="uapp-doc-picker-backdrop">
        <button type="button" class="uapp-doc-picker-scrim" data-uapp-action="documentsUploadPickerClose" aria-label="Zavřít"></button>
        <div class="uapp-doc-picker" role="dialog" aria-modal="true" aria-label="Vyberte vozidlo">
          <header>
            <h3>Nahrát dokument</h3>
            <button type="button" class="uapp-doc-picker-close" data-uapp-action="documentsUploadPickerClose" aria-label="Zavřít">×</button>
          </header>
          <p>Vyberte vozidlo, ke kterému chcete nahrát dokument.</p>
          <ul class="uapp-doc-picker-list">
            ${vehicles.map((vehicle) => `
              <li>
                <button type="button" data-uapp-action="documentsUploadTo:${Number(vehicle.id)}">
                  <strong>${esc(vehicle.plate || getVehicleName(vehicle))}</strong>
                  <span>${esc(vehicleSubtitle(vehicle))}</span>
                </button>
              </li>`).join('') || '<li class="uapp-doc-picker-empty">Nejdříve přidejte vozidlo.</li>'}
          </ul>
        </div>
      </div>`;
  }

  function renderDocumentsPage(data) {
    const hub = data?.documentsHub;
    const allRows = sortDocumentsRows(buildDocumentsRows(data));
    const filtered = filterDocumentsRows(allRows, data);
    const perPage = Number(STATE.documentsPerPage) || 10;
    const totalPages = Math.max(1, Math.ceil(filtered.length / perPage));
    if ((STATE.documentsPage || 1) > totalPages) STATE.documentsPage = totalPages;
    const page = Number(STATE.documentsPage) || 1;
    const pageRows = filtered.slice((page - 1) * perPage, page * perPage);
    const stats = documentsCategoryStats(allRows);
    const filters = STATE.documentsFilters || {};
    const sort = STATE.documentsSort || { key: 'uploadedAt', dir: 'desc' };
    const hubMissing = hub == null;
    const vehicleOptions = (data?.vehicles || []).map((vehicle) =>
      `<option value="${Number(vehicle.id)}"${String(filters.vehicle) === String(vehicle.id) ? ' selected' : ''}>${esc(vehicle.plate || getVehicleName(vehicle))}</option>`,
    ).join('');
    const typeOptions = [...new Set(allRows.map((row) => row.fileType))].sort();
    const activeFilterCount = ['category', 'type', 'vehicle'].filter((key) => filters[key] && filters[key] !== 'all').length;

    const categoryWidget = Object.entries(DOC_CATEGORY_META).map(([key, meta]) => `
      <li>
        <span class="uapp-doc-cat-ico is-${meta.tone}" aria-hidden="true">${ICO.folder.replace('class="uapp-next-svg"', 'class="uapp-doc-cat-folder"')}</span>
        <span>${esc(meta.label)}</span>
        <strong>${esc(String(stats[key] || 0))}</strong>
      </li>`).join('');

    const storage = computeDocumentsStorage(data, allRows);

    const tipBanner = STATE.documentsTipHidden ? '' : `
      <div class="uapp-doc-tip" role="note">
        <span class="uapp-doc-tip-ico" aria-hidden="true">💡</span>
        <p>Nahrajte dokumenty jako PDF, JPG, PNG nebo DOCX. Maximální velikost souboru je 20 MB.</p>
        <button type="button" class="uapp-doc-tip-close" data-uapp-action="documentsTipClose" aria-label="Zavřít tip">×</button>
      </div>`;

    return `
      <div class="uapp-doc-page" data-testid="user-app-next-documents">
        <nav class="uapp-doc-breadcrumbs" aria-label="Drobečková navigace">
          <button type="button" data-uapp-action="home">Přehled</button>
          <span aria-hidden="true">/</span>
          <span aria-current="page">Dokumenty</span>
        </nav>
        <header class="uapp-doc-page-head">
          <div>
            <div class="uapp-doc-title-row">
              <h1 class="uapp-doc-page-title">Dokumenty</h1>
              <span class="uapp-doc-count-badge">${esc(String(allRows.length))}</span>
            </div>
            <p class="uapp-doc-page-sub">Spravujte všechny dokumenty související s vašimi vozidly na jednom místě.</p>
          </div>
          <button type="button" class="uapp-next-btn uapp-next-btn-primary uapp-doc-upload-btn" data-uapp-action="documentsUpload">↑ Nahrát dokument</button>
        </header>
        <div class="uapp-doc-toolbar">
          <label class="uapp-doc-search">
            <span class="uapp-next-search-icon" aria-hidden="true">${ICO.search}</span>
            <input type="search" data-uapp-doc-filter="search" placeholder="Hledat dokument" value="${esc(filters.search || '')}" autocomplete="off">
          </label>
          <label class="uapp-doc-filter-field">
            <select data-uapp-doc-filter="category">
              <option value="all"${filters.category === 'all' ? ' selected' : ''}>Všechny kategorie</option>
              ${Object.entries(DOC_CATEGORY_META).map(([key, meta]) => `<option value="${key}"${filters.category === key ? ' selected' : ''}>${esc(meta.label)}</option>`).join('')}
            </select>
          </label>
          <label class="uapp-doc-filter-field">
            <select data-uapp-doc-filter="type">
              <option value="all"${filters.type === 'all' ? ' selected' : ''}>Všechny typy</option>
              ${typeOptions.map((type) => `<option value="${esc(type)}"${filters.type === type ? ' selected' : ''}>${esc(type)}</option>`).join('')}
            </select>
          </label>
          <label class="uapp-doc-filter-field">
            <select data-uapp-doc-filter="vehicle">
              <option value="all"${filters.vehicle === 'all' ? ' selected' : ''}>Všechna vozidla</option>
              ${vehicleOptions}
            </select>
          </label>
          <button type="button" class="uapp-doc-filters-btn${activeFilterCount ? ' is-active' : ''}" data-uapp-action="documentsFiltersToggle">
            ${ICO.filter}
            Filtry
          </button>
        </div>
        <div class="uapp-doc-layout">
          <div class="uapp-doc-main">
            ${hubMissing ? '<div class="uapp-doc-empty-state">Nepodařilo se načíst dokumenty. Zkuste stránku obnovit.</div>' : ''}
            ${!hubMissing && filtered.length === 0 ? '<div class="uapp-doc-empty-state">Žádné dokumenty neodpovídají zvoleným filtrům.</div>' : ''}
            ${filtered.length ? `
              <div class="uapp-doc-table-wrap">
                <table class="uapp-doc-table">
                  <thead>
                    <tr>
                      <th>Název dokumentu</th>
                      <th>Vozidlo</th>
                      <th>Kategorie</th>
                      <th>Typ</th>
                      <th>
                        <button type="button" class="uapp-doc-sort-btn${sort.key === 'uploadedAt' ? ' is-active' : ''}" data-uapp-action="documentsSortToggle">
                          Nahráno dne ${sort.key === 'uploadedAt' ? (sort.dir === 'desc' ? '↓' : '↑') : ''}
                        </button>
                      </th>
                      <th>Platnost do</th>
                      <th>Akce</th>
                    </tr>
                  </thead>
                  <tbody>${pageRows.map((row) => renderDocumentsTableRow(row)).join('')}</tbody>
                </table>
              </div>
              ${renderDocumentsPagination(filtered.length, page, perPage)}` : ''}
          </div>
          <aside class="uapp-doc-aside" aria-label="Postranní panel dokumentů">
            <section class="uapp-doc-widget">
              <h3>Kategorie dokumentů</h3>
              <ul class="uapp-doc-cat-list">${categoryWidget}</ul>
            </section>
            <section class="uapp-doc-widget">
              <h3>Rychlé akce</h3>
              <div class="uapp-doc-quick-actions">
                <button type="button" class="uapp-doc-quick-btn" data-uapp-action="documentsUpload">↑ Nahrát dokument</button>
                <button type="button" class="uapp-doc-quick-btn" data-uapp-action="documentsOrganize">📁 Vytvořit složku</button>
                <button type="button" class="uapp-doc-quick-btn" data-uapp-action="documentsExport">📄 Exportovat seznam</button>
              </div>
            </section>
            <section class="uapp-doc-widget">
              <div class="uapp-doc-storage-head">
                <h3>Úložiště</h3>
                <span class="uapp-doc-storage-pct">${esc(String(storage.pct))} %</span>
              </div>
              <p class="uapp-doc-storage-label">Využito ${esc(storage.usedLabel)} z 10 GB</p>
              <div class="uapp-doc-storage-bar" aria-hidden="true"><span style="width:${storage.pct}%"></span></div>
              <button type="button" class="uapp-doc-storage-link" data-uapp-action="documentsManageStorage">Spravovat úložiště</button>
            </section>
            ${tipBanner}
          </aside>
        </div>
        ${renderDocumentsUploadPicker(data)}
      </div>`;
  }

  function bindDocumentsFilters() {
    document.querySelectorAll('[data-uapp-doc-filter]').forEach((el) => {
      if (el.dataset.uappDocBound === '1') return;
      el.dataset.uappDocBound = '1';
      const key = el.getAttribute('data-uapp-doc-filter');
      const handler = () => {
        STATE.documentsFilters = STATE.documentsFilters || {};
        if (key === 'search') {
          STATE.documentsFilters.search = el.value;
        } else if (key === 'perPage') {
          STATE.documentsPerPage = Number(el.value) || 10;
          STATE.documentsPage = 1;
        } else {
          STATE.documentsFilters[key] = el.value;
          STATE.documentsPage = 1;
        }
        render();
      };
      if (el.tagName === 'INPUT') {
        el.addEventListener('input', handler);
      } else {
        el.addEventListener('change', handler);
      }
    });
  }

  function exportDocumentsCsv(rows) {
    const header = ['Název', 'Vozidlo SPZ', 'Vozidlo', 'Kategorie', 'Typ', 'Nahráno dne', 'Nahrál', 'Platnost do'];
    const lines = [header.join(';')];
    rows.forEach((row) => {
      lines.push([
        row.name,
        row.vehiclePlate,
        row.vehicleModel,
        row.category.label,
        row.fileType,
        formatDate(row.uploadedAt),
        row.uploadedBy,
        row.expiryAt ? formatDate(row.expiryAt) : '',
      ].map((cell) => `"${String(cell || '').replace(/"/g, '""')}"`).join(';'));
    });
    const blob = new Blob([`\uFEFF${lines.join('\n')}`], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `dokumenty-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function openDocumentsUploadFlow(data) {
    const vehicles = data?.vehicles || [];
    if (!vehicles.length) {
      if (hasFn('openAddVehicleModal')) return window.openAddVehicleModal();
      return;
    }
    if (vehicles.length === 1) return openVehicleDocuments(Number(vehicles[0].id));
    STATE.documentsUploadPickerOpen = true;
    render();
  }

  function looksLikeCoordinates(text) {
    return /^\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*$/.test(String(text || ''));
  }

  function serviceAddressCacheKey(service) {
    const coords = service?.coordinates;
    if (coords && Number.isFinite(Number(coords.lat)) && Number.isFinite(Number(coords.lon))) {
      return `${Number(coords.lat).toFixed(5)},${Number(coords.lon).toFixed(5)}`;
    }
    return String(service?.row_key || service?.osm_id || service?.location_id || '');
  }

  function hasUsableServiceAddress(service) {
    const directAddress = String(service?.address || '').trim();
    if (directAddress && !looksLikeCoordinates(directAddress)) return true;
    const street = [service?.street, service?.street_number].filter(Boolean).join(' ').trim();
    const cityZip = [service?.zip, service?.city].filter(Boolean).join(' ').trim();
    return Boolean(street || cityZip);
  }

  function buildServiceAddressLine(service) {
    if (hasFn('buildServiceAddressLine')) {
      try {
        const legacy = window.buildServiceAddressLine(service);
        if (legacy && legacy !== 'Adresa není uvedena' && !looksLikeCoordinates(legacy)) return legacy;
      } catch (_) {}
    }
    const directAddress = String(service?.address || '').trim();
    if (directAddress && !looksLikeCoordinates(directAddress)) return directAddress;
    const street = [service?.street, service?.street_number].filter(Boolean).join(' ').trim();
    const cityZip = [service?.zip, service?.city].filter(Boolean).join(' ').trim();
    const line = [street, cityZip].filter(Boolean).join(', ');
    if (line) return line;
    const cacheKey = serviceAddressCacheKey(service);
    if (cacheKey && STATE.serviceAddressCache[cacheKey]) return STATE.serviceAddressCache[cacheKey];
    return 'Adresa není uvedena';
  }

  function formatServiceAddressDisplay(service) {
    const line = buildServiceAddressLine(service);
    if (line && line !== 'Adresa není uvedena') return line;
    const cacheKey = serviceAddressCacheKey(service);
    if (cacheKey && STATE.serviceAddressCache[cacheKey]) return STATE.serviceAddressCache[cacheKey];
    if (String(service?.city || '').trim()) return String(service.city).trim();
    return 'Načítám adresu…';
  }

  async function ensureServiceAddressResolved(service) {
    if (hasUsableServiceAddress(service)) return buildServiceAddressLine(service);
    const cacheKey = serviceAddressCacheKey(service);
    if (cacheKey && STATE.serviceAddressCache[cacheKey]) return STATE.serviceAddressCache[cacheKey];
    const coords = service?.coordinates;
    if (!coords || !Number.isFinite(Number(coords.lat)) || !Number.isFinite(Number(coords.lon)) || !apiReady()) {
      return 'Adresa neuvedena';
    }
    const payload = await safeApi(
      `/api/v1/system/reverse-geocode?lat=${encodeURIComponent(String(coords.lat))}&lon=${encodeURIComponent(String(coords.lon))}`,
      null,
    );
    const label = payload?.location_label || payload?.city || null;
    if (!label) return 'Adresa neuvedena';
    const text = String(label);
    if (cacheKey) STATE.serviceAddressCache[cacheKey] = text;
    return text;
  }

  function applyResolvedServiceAddress(service, label) {
    const rowKey = esc(service?.row_key || '');
    if (rowKey) {
      document.querySelectorAll(`[data-service-row="${rowKey}"] .uapp-svc-address`).forEach((el) => {
        el.textContent = label;
      });
    }
    const modal = document.getElementById('uappSvcExternalModal');
    if (modal && modal.dataset.serviceRowKey === String(service?.row_key || '')) {
      const addrEl = modal.querySelector('[data-uapp-svc-address]');
      if (addrEl) addrEl.textContent = label;
    }
  }

  async function hydrateServiceAddresses(services) {
    if (!apiReady() || getActiveView() !== 'servicesDirectory') return;
    const token = ++STATE.serviceAddressResolveToken;
    const targets = (Array.isArray(services) ? services : [])
      .filter((service) => !hasUsableServiceAddress(service))
      .slice(0, 24);
    let index = 0;
    const worker = async () => {
      while (index < targets.length) {
        if (token !== STATE.serviceAddressResolveToken || getActiveView() !== 'servicesDirectory') return;
        const service = targets[index++];
        const label = await ensureServiceAddressResolved(service);
        if (token !== STATE.serviceAddressResolveToken) return;
        applyResolvedServiceAddress(service, label);
      }
    };
    await Promise.all([worker(), worker(), worker(), worker()]);
  }

  function formatServiceOfferedLine(service) {
    const profile = service?.partner_public_profile || {};
    const items = (Array.isArray(profile.services_offered) ? profile.services_offered : [])
      .map((item) => String(item || '').trim())
      .filter(Boolean)
      .slice(0, 6);
    return items.join(' • ');
  }

  function formatServiceContactRows(service) {
    const rows = [];
    const phone = String(service?.phone || '').trim();
    const email = String(service?.email || '').trim();
    const website = String(service?.website || '').trim();
    const ico = String(service?.ico || '').trim();
    if (phone) rows.push({ label: 'Telefon', value: phone, href: `tel:${phone.replace(/[^\d+]/g, '')}` });
    if (email) rows.push({ label: 'E-mail', value: email, href: `mailto:${email}` });
    if (website) {
      const href = /^https?:\/\//i.test(website) ? website : `https://${website}`;
      rows.push({ label: 'Web', value: website.replace(/^https?:\/\//i, ''), href });
    }
    if (ico) rows.push({ label: 'IČO', value: ico, href: null });
    return rows;
  }

  function servicesMapZoomForRadius(radiusKm) {
    const radius = Number(radiusKm) || 50;
    if (radius <= 10) return 12;
    if (radius <= 25) return 11;
    if (radius <= 50) return 10;
    if (radius <= 75) return 9;
    return 8;
  }

  function servicesMapProject(lon, lat, zoom) {
    const scale = 256 * (2 ** zoom);
    const x = ((lon + 180) / 360) * scale;
    const sinLat = Math.sin((lat * Math.PI) / 180);
    const y = ((0.5 - Math.log((1 + sinLat) / (1 - sinLat)) / (4 * Math.PI)) * scale);
    return { x, y };
  }

  function servicesMapTileXY(lon, lat, zoom) {
    const n = 2 ** zoom;
    const x = Math.floor(((lon + 180) / 360) * n);
    const latRad = (lat * Math.PI) / 180;
    const y = Math.floor((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2 * n);
    return { x, y };
  }

  function servicesMapBBoxDelta(radiusKm) {
    const radius = Number(radiusKm) || 50;
    return Math.min(0.42, Math.max(0.08, (radius / 50) * 0.12));
  }

  function servicePinPosition(serviceLat, serviceLon, centerLat, centerLon, delta) {
    const x = ((serviceLon - (centerLon - delta)) / (2 * delta)) * 100;
    const y = (1 - ((serviceLat - (centerLat - delta * 0.7)) / (2 * delta * 0.7))) * 100;
    return {
      x: Math.min(96, Math.max(4, x)),
      y: Math.min(92, Math.max(8, y)),
    };
  }

  function serviceMapPinColor(typeMeta, inApp) {
    if (inApp) return '#1a73e8';
    const key = typeMeta?.key || typeMeta?.tone || 'auto';
    const colors = {
      auto: '#4285F4',
      indep: '#4285F4',
      auth: '#1967D2',
      pneu: '#FBBC04',
      tire: '#FBBC04',
      stk: '#34A853',
      emis: '#0F9D58',
      moto: '#9334E6',
      truck: '#EA4335',
    };
    return colors[key] || '#4285F4';
  }

  function serviceMapLegendItems() {
    return [
      { key: 'auto', label: 'Autoservis', tone: 'auto' },
      { key: 'pneu', label: 'Pneuservis', tone: 'tire' },
      { key: 'stk', label: 'STK / emise', tone: 'stk' },
      { key: 'moto', label: 'Motocykly', tone: 'moto' },
      { key: 'truck', label: 'Nákladní vozidla', tone: 'truck' },
      { key: 'inapp', label: 'V aplikaci', tone: 'inapp' },
    ];
  }

  const OSM_MAPS_FALLBACK = {
    provider: 'osm_tiles',
    configured: true,
    tile_url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '© OpenStreetMap contributors',
    fallback_allowed: true,
  };

  function resolveMapsConfigForLeaflet(config) {
    if (config?.configured && config?.tile_url) return config;
    if (config?.provider === 'mapy_com' && config?.configured === false) {
      console.warn('Mapy.com provider selected but API key missing, using OSM fallback.');
    }
    if (config?.fallback_allowed !== false) return { ...OSM_MAPS_FALLBACK };
    return config || OSM_MAPS_FALLBACK;
  }

  async function ensureMapsConfig() {
    if (STATE.mapsConfig !== undefined) {
      return resolveMapsConfigForLeaflet(STATE.mapsConfig);
    }
    const result = await safeApi('/api/v1/system/maps-config', OSM_MAPS_FALLBACK);
    STATE.mapsConfig = result || OSM_MAPS_FALLBACK;
    return resolveMapsConfigForLeaflet(STATE.mapsConfig);
  }

  function loadLeafletAssets() {
    if (window.L) return Promise.resolve();
    if (STATE.leafletLoadPromise) return STATE.leafletLoadPromise;
    STATE.leafletLoadPromise = new Promise((resolve, reject) => {
      if (!document.getElementById('uappLeafletCss')) {
        const link = document.createElement('link');
        link.id = 'uappLeafletCss';
        link.rel = 'stylesheet';
        link.href = '/web/vendor/leaflet/leaflet.css';
        document.head.appendChild(link);
      }
      const script = document.createElement('script');
      script.src = '/web/vendor/leaflet/leaflet.js';
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error('Leaflet se nepodařilo načíst'));
      document.head.appendChild(script);
    });
    return STATE.leafletLoadPromise;
  }

  function loadLeafletClusterAssets() {
    return loadLeafletAssets().then(() => {
      if (window.L && window.L.markerClusterGroup) return;
      if (STATE.leafletClusterLoadPromise) return STATE.leafletClusterLoadPromise;
      STATE.leafletClusterLoadPromise = new Promise((resolve, reject) => {
        if (!document.getElementById('uappLeafletClusterCss')) {
          const link = document.createElement('link');
          link.id = 'uappLeafletClusterCss';
          link.rel = 'stylesheet';
          link.href = '/web/vendor/leaflet.markercluster/MarkerCluster.css';
          document.head.appendChild(link);
          const link2 = document.createElement('link');
          link2.rel = 'stylesheet';
          link2.href = '/web/vendor/leaflet.markercluster/MarkerCluster.Default.css';
          document.head.appendChild(link2);
        }
        const script = document.createElement('script');
        script.src = '/web/vendor/leaflet.markercluster/leaflet.markercluster.js';
        script.async = true;
        script.onload = () => resolve();
        script.onerror = () => reject(new Error('Leaflet cluster se nepodařilo načíst'));
        document.head.appendChild(script);
      });
      return STATE.leafletClusterLoadPromise;
    });
  }

  function scheduleServicesMapBoundsLoad() {
    if (STATE.servicesMapBoundsDebounce) clearTimeout(STATE.servicesMapBoundsDebounce);
    STATE.servicesMapBoundsDebounce = setTimeout(() => {
      const runtime = STATE.servicesMapRuntime;
      if (!runtime?.map || getActiveView() !== 'servicesDirectory') return;
      const b = runtime.map.getBounds();
      STATE.servicesMapBounds = {
        north: b.getNorth(),
        south: b.getSouth(),
        east: b.getEast(),
        west: b.getWest(),
      };
      void loadServicesOsmData({ silent: true });
    }, 400);
  }

  function updateServicesMapMarkers(data) {
    const runtime = STATE.servicesMapRuntime;
    if (!runtime?.map || !window.L) return;
    const L = window.L;
    const rows = servicesMapRowsForDisplay(data);
    if (runtime.cluster && runtime.cluster.clearLayers) {
      runtime.cluster.clearLayers();
    } else {
      runtime.cluster = L.markerClusterGroup({ maxClusterRadius: 50, showCoverageOnHover: false });
      runtime.map.addLayer(runtime.cluster);
    }
    rows.forEach((service) => {
      const plat = Number(service?.coordinates?.lat);
      const plon = Number(service?.coordinates?.lon);
      if (!Number.isFinite(plat) || !Number.isFinite(plon)) return;
      const type = resolveServiceTypeMeta(service);
      const marker = L.circleMarker([plat, plon], {
        radius: service.in_app ? 10 : 8,
        color: '#ffffff',
        weight: 2,
        fillColor: serviceMapPinColor(type, service.in_app),
        fillOpacity: 1,
      });
      marker.on('click', () => openServiceLocationSheet(service));
      runtime.cluster.addLayer(marker);
    });
    runtime.markers = rows;
  }

  function destroyServicesMap() {
    const runtime = STATE.servicesMapRuntime;
    if (!runtime) return;
    if (runtime.provider === 'leaflet' && runtime.map && runtime.map.remove) {
      runtime.map.remove();
    }
    STATE.servicesMapRuntime = null;
  }

  function servicesMapRowsForDisplay(data) {
    const source = data || STATE.latestData || {};
    return filterServicesRows(buildMergedServiceCatalog(source))
      .filter((row) => row?.coordinates?.lat != null && row?.coordinates?.lon != null);
  }

  function bindLeafletServicesMap(host, ref, radius, rows, mapsConfig) {
    const L = window.L;
    if (!L) throw new Error('Leaflet není k dispozici');
    const layerConfig = resolveMapsConfigForLeaflet(mapsConfig);
    if (!layerConfig?.tile_url) {
      host.innerHTML = `<div class="uapp-svc-map-fallback" role="alert">${esc(mapsConfig?.fallback_message || 'Mapa není nakonfigurovaná. Servisy lze zobrazit v seznamu.')}</div>`;
      STATE.servicesMapRuntime = { provider: 'fallback' };
      return;
    }
    const map = L.map(host, { zoomControl: true, attributionControl: true }).setView([ref.lat, ref.lon], servicesMapZoomForRadius(radius));
    L.tileLayer(layerConfig.tile_url, {
      attribution: layerConfig.attribution || '',
      maxZoom: 19,
    }).addTo(map);
    L.circleMarker([ref.lat, ref.lon], {
      radius: 7,
      color: '#111827',
      fillColor: '#111827',
      fillOpacity: 1,
      weight: 2,
    }).addTo(map).bindTooltip('Vaše poloha', { permanent: false });

    const cluster = L.markerClusterGroup ? L.markerClusterGroup({ maxClusterRadius: 50, showCoverageOnHover: false }) : null;
    const targetLayer = cluster || map;
    rows.slice(0, 500).forEach((service) => {
      const plat = Number(service?.coordinates?.lat);
      const plon = Number(service?.coordinates?.lon);
      if (!Number.isFinite(plat) || !Number.isFinite(plon)) return;
      const type = resolveServiceTypeMeta(service);
      const marker = L.circleMarker([plat, plon], {
        radius: service.in_app ? 10 : 8,
        color: '#ffffff',
        weight: 2,
        fillColor: serviceMapPinColor(type, service.in_app),
        fillOpacity: 1,
      });
      marker.on('click', () => openServiceLocationSheet(service));
      targetLayer.addLayer(marker);
    });
    if (cluster) map.addLayer(cluster);

    const b = map.getBounds();
    STATE.servicesMapBounds = {
      north: b.getNorth(),
      south: b.getSouth(),
      east: b.getEast(),
      west: b.getWest(),
    };
    map.on('moveend', () => {
      const rt = STATE.servicesMapRuntime;
      if (!rt?.map) return;
      const bounds = rt.map.getBounds();
      STATE.servicesMapBounds = {
        north: bounds.getNorth(),
        south: bounds.getSouth(),
        east: bounds.getEast(),
        west: bounds.getWest(),
      };
    });

    STATE.servicesMapRuntime = { provider: 'leaflet', map, cluster, markers: rows };
  }

  async function bindServicesMap(data) {
    const host = document.getElementById('uappSvcMapCanvas');
    if (!host || (STATE.servicesDirectoryView || 'map') === 'list') return;
    destroyServicesMap();
    host.replaceChildren();

    const ref = getServicesRefCoords(data || STATE.latestData || {}) || { lat: 49.7559, lon: 16.4683 };
    const radius = Number(STATE.servicesDirectoryRadius) || 50;
    const rows = servicesMapRowsForDisplay(data);
    const loading = document.createElement('div');
    loading.className = 'uapp-svc-map-loading';
    loading.textContent = 'Načítám mapu servisů…';
    host.appendChild(loading);

    try {
      const mapsConfig = await ensureMapsConfig();
      await loadLeafletClusterAssets();
      host.replaceChildren();
      bindLeafletServicesMap(host, ref, radius, rows, mapsConfig);
    } catch (err) {
      console.warn('[USER_APP_NEXT] map init failed', err);
      host.replaceChildren();
      host.innerHTML = '<div class="uapp-svc-map-fallback" role="alert">Mapa není nakonfigurovaná. Servisy lze zobrazit v seznamu.</div>';
      STATE.servicesMapRuntime = { provider: 'fallback' };
    }
  }

  function formatServicesDistanceKm(value) {
    if (hasFn('formatServicesDistance')) {
      try {
        const label = window.formatServicesDistance(value);
        if (label) return label;
      } catch (_) {}
    }
    const km = Number(value);
    if (!Number.isFinite(km) || km < 0) return null;
    const decimals = km < 10 ? 1 : 0;
    return `${km.toLocaleString('cs-CZ', { minimumFractionDigits: 0, maximumFractionDigits: decimals })} km`;
  }

  function haversineKm(lat1, lon1, lat2, lon2) {
    const r = 6371;
    const toRad = (deg) => deg * (Math.PI / 180);
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a = Math.sin(dLat / 2) ** 2
      + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
    return r * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(Math.max(1 - a, 0)));
  }

  function getServicesRefCoords(data) {
    const stateRef = STATE.servicesRefCoords || {};
    const stateLat = Number(stateRef.lat);
    const stateLon = Number(stateRef.lon);
    if (Number.isFinite(stateLat) && Number.isFinite(stateLon)) {
      return { lat: stateLat, lon: stateLon };
    }
    const meta = data?.servicesDiscovery?.meta || {};
    const ref = meta.reference_coordinates || {};
    const lat = Number(ref.lat);
    const lon = Number(ref.lon);
    if (Number.isFinite(lat) && Number.isFinite(lon)) return { lat, lon };
    return null;
  }

  function normalizeServicesFromData(data) {
    const base = Array.isArray(data?.servicesDiscovery?.services) ? data.servicesDiscovery.services : [];
    const contacts = Array.isArray(data?.services) ? data.services : [];
    const map = new Map();
    base.forEach((item) => {
      const id = Number(item?.id);
      if (!id) return;
      map.set(id, { ...item, is_linked: Boolean(item?.is_linked) });
    });
    contacts.forEach((contact) => {
      const id = Number(contact?.id);
      if (!id) return;
      const existing = map.get(id);
      if (existing) {
        map.set(id, {
          ...existing,
          is_linked: true,
          name: existing?.name || contact?.name || contact?.email || existing?.email || 'Servis',
          phone: existing?.phone || contact?.phone || '',
          email: existing?.email || contact?.email || '',
          ico: existing?.ico || contact?.ico || '',
          city: existing?.city || contact?.city || '',
          street: existing?.street || contact?.street || '',
          street_number: existing?.street_number || contact?.street_number || '',
          zip: existing?.zip || contact?.zip || '',
          address: existing?.address || contact?.address || '',
        });
        return;
      }
      map.set(id, {
        id,
        name: contact?.name || contact?.email || `Servis #${id}`,
        email: contact?.email || '',
        phone: contact?.phone || '',
        ico: contact?.ico || '',
        city: contact?.city || '',
        street: contact?.street || '',
        street_number: contact?.street_number || '',
        zip: contact?.zip || '',
        address: contact?.address || '',
        is_linked: true,
        distance_km: null,
        coordinates: null,
        partner_public_profile: {},
      });
    });
    let list = Array.from(map.values());
    if (hasFn('dedupePartnerDirectoryRows')) {
      try { list = window.dedupePartnerDirectoryRows(list); } catch (_) {}
    }
    return list.sort((a, b) => {
      const da = Number.isFinite(Number(a?.distance_km)) ? Number(a.distance_km) : Infinity;
      const db = Number.isFinite(Number(b?.distance_km)) ? Number(b.distance_km) : Infinity;
      if (da !== db) return da - db;
      return String(a?.name || '').localeCompare(String(b?.name || ''), 'cs');
    });
  }

  function buildMergedServiceCatalog(data) {
    const ref = getServicesRefCoords(data);
    const radius = Number(STATE.servicesDirectoryRadius) || 50;
    const osmRows = Array.isArray(STATE.servicesOsmRows) ? STATE.servicesOsmRows : [];

    const appRows = normalizeServicesFromData(data).map((row) => {
      const coords = row?.coordinates
        && Number.isFinite(Number(row.coordinates.lat))
        && Number.isFinite(Number(row.coordinates.lon))
        ? { lat: Number(row.coordinates.lat), lon: Number(row.coordinates.lon) }
        : null;
      let distanceKm = row.distance_km;
      if (ref && coords) {
        distanceKm = Math.round(haversineKm(ref.lat, ref.lon, coords.lat, coords.lon) * 10) / 10;
      }
      return {
        ...row,
        in_app: true,
        source: 'app',
        row_key: `app-${row.id}`,
        coordinates: coords || row.coordinates,
        distance_km: distanceKm,
      };
    });

    const matchedOsmIds = new Set();
    const merged = [];

    appRows.forEach((appRow) => {
      let matchedOsmId = null;
      let matchedOsmRow = null;
      const appCoords = appRow.coordinates;
      if (appCoords && Number.isFinite(Number(appCoords.lat)) && Number.isFinite(Number(appCoords.lon))) {
        osmRows.forEach((osmRow) => {
          if (matchedOsmIds.has(osmRow.osm_id)) return;
          const { lat: olat, lon: olon } = getOsmRowCoords(osmRow);
          if (!Number.isFinite(olat) || !Number.isFinite(olon)) return;
          const dist = haversineKm(Number(appCoords.lat), Number(appCoords.lon), olat, olon);
          if (dist <= 0.25) {
            matchedOsmId = osmRow.osm_id;
            matchedOsmRow = osmRow;
            matchedOsmIds.add(osmRow.osm_id);
          }
        });
      }
      const enriched = { ...appRow, matched_osm_id: matchedOsmId };
      if (matchedOsmRow) {
        if (!enriched.street && matchedOsmRow.street) enriched.street = matchedOsmRow.street;
        if (!enriched.city && matchedOsmRow.city) enriched.city = matchedOsmRow.city;
        if (!enriched.zip && matchedOsmRow.postcode) enriched.zip = matchedOsmRow.postcode;
        if (!enriched.address && matchedOsmRow.address) enriched.address = matchedOsmRow.address;
        if (!enriched.phone && matchedOsmRow.phone) enriched.phone = matchedOsmRow.phone;
        if (!enriched.email && matchedOsmRow.email) enriched.email = matchedOsmRow.email;
        if (!enriched.website && matchedOsmRow.website) enriched.website = matchedOsmRow.website;
      }
      merged.push(enriched);
    });

    osmRows.forEach((osmRow) => {
      if (matchedOsmIds.has(osmRow.osm_id)) return;
      const { lat: olat, lon: olon } = getOsmRowCoords(osmRow);
      if (!Number.isFinite(olat) || !Number.isFinite(olon)) return;
      const dist = ref
        ? Math.round(haversineKm(ref.lat, ref.lon, olat, olon) * 10) / 10
        : Number(osmRow.distance_km);
      const street = String(osmRow.street || osmRow.address || '').trim();
      const city = String(osmRow.city || '').trim();
      const zip = String(osmRow.postcode || '').trim();
      const shopType = String(osmRow.shop_type || 'auto');
      const servicesOffered = shopType === 'pneu'
        ? ['Pneuservis']
        : shopType === 'stk' || shopType === 'emis'
          ? ['STK / emise']
          : shopType === 'moto'
            ? ['Servis motocyklů']
            : shopType === 'truck'
              ? ['Servis nákladních vozidel']
              : ['Autoservis'];
      merged.push({
        id: null,
        osm_id: osmRow.osm_id,
        shop_type: shopType,
        name: osmRow.name || 'Servis',
        street,
        city,
        zip,
        phone: osmRow.phone || '',
        email: osmRow.email || '',
        website: osmRow.website || '',
        address: String(osmRow.address || [street, [zip, city].filter(Boolean).join(' ')].filter(Boolean).join(', ')),
        coordinates: { lat: olat, lon: olon },
        distance_km: dist,
        in_app: false,
        is_linked: false,
        source: 'osm',
        osm_tags: osmRow.tags || {},
        partner_public_profile: { services_offered: servicesOffered },
        row_key: `osm-${osmRow.osm_id}`,
      });
    });

    return merged
      .filter((row) => {
        if (row.is_linked) return true;
        const dist = Number(row.distance_km);
        if (!Number.isFinite(dist)) return Boolean(row.in_app);
        return dist <= radius;
      })
      .sort((a, b) => {
        const da = Number.isFinite(Number(a.distance_km)) ? Number(a.distance_km) : 9999;
        const db = Number.isFinite(Number(b.distance_km)) ? Number(b.distance_km) : 9999;
        if (da !== db) return da - db;
        if (Boolean(a.in_app) !== Boolean(b.in_app)) return a.in_app ? -1 : 1;
        return String(a.name || '').localeCompare(String(b.name || ''), 'cs');
      });
  }

  function resolveServicesLocationLabel(data) {
    if (STATE.servicesLocationLabel) return STATE.servicesLocationLabel;
    const meta = data?.servicesDiscovery?.meta || {};
    const refSource = String(meta.reference_source || 'none');
    if (meta.reference_label) return String(meta.reference_label);
    const ref = getServicesRefCoords(data);
    if (refSource === 'browser' || refSource === 'explore_place') {
      if (ref) return 'Načítám adresu polohy…';
      return 'Vaše aktuální poloha (GPS)';
    }
    if (refSource === 'profile_address') {
      const profile = window.currentUser || {};
      const parts = [
        [profile.street, profile.street_number].filter(Boolean).join(' ').trim(),
        [profile.zip, profile.city].filter(Boolean).join(' ').trim(),
      ].filter(Boolean);
      if (parts.length) return parts.join(', ');
      return 'Podle adresy v profilu';
    }
    if (ref) return 'Načítám adresu polohy…';
    return 'Poloha není určena';
  }

  function resolveServiceTypeMeta(service) {
    const apiCategory = String(service?.category || '').toLowerCase();
    if (apiCategory === 'pneuservis') return { key: 'pneu', label: 'Pneuservis', tone: 'tire' };
    if (apiCategory === 'stk') return { key: 'stk', label: 'STK', tone: 'stk' };
    if (apiCategory === 'sme') return { key: 'stk', label: 'Emise (SME)', tone: 'stk' };
    if (apiCategory === 'truck_service') return { key: 'truck', label: 'Nákladní vozidla', tone: 'truck' };
    if (apiCategory === 'autoservis') return { key: 'indep', label: 'Autoservis', tone: 'indep' };
    const directType = String(service?.shop_type || '').toLowerCase();
    if (directType === 'pneu') return { key: 'pneu', label: 'Pneuservis', tone: 'tire' };
    if (directType === 'stk') return { key: 'stk', label: 'STK', tone: 'stk' };
    if (directType === 'emis') return { key: 'stk', label: 'Emise', tone: 'stk' };
    if (directType === 'moto') return { key: 'moto', label: 'Motocykly', tone: 'moto' };
    if (directType === 'truck') return { key: 'truck', label: 'Nákladní vozidla', tone: 'truck' };
    if (directType === 'auto') return { key: 'indep', label: 'Autoservis', tone: 'indep' };
    const osmTags = service?.osm_tags && typeof service.osm_tags === 'object' ? service.osm_tags : null;
    if (osmTags) {
      const shop = String(osmTags.shop || '').toLowerCase();
      const amenity = String(osmTags.amenity || '').toLowerCase();
      const name = String(osmTags.name || service?.name || '').toLowerCase();
      if (amenity === 'vehicle_inspection' || name.includes('stk') || name.includes('technick')) return { key: 'stk', label: 'STK', tone: 'stk' };
      if (name.includes('emis')) return { key: 'stk', label: 'Emise', tone: 'stk' };
      if (shop === 'tyres' || name.includes('pneu')) return { key: 'pneu', label: 'Pneuservis', tone: 'tire' };
      if (shop === 'motorcycle_repair' || shop === 'motorcycle' || name.includes('moto')) return { key: 'moto', label: 'Motocykly', tone: 'moto' };
      if (name.includes('kamion') || name.includes('náklad') || name.includes('tir')) return { key: 'truck', label: 'Nákladní vozidla', tone: 'truck' };
      return { key: 'indep', label: 'Autoservis', tone: 'indep' };
    }
    const profile = service?.partner_public_profile && typeof service.partner_public_profile === 'object'
      ? service.partner_public_profile
      : {};
    const offered = (profile.services_offered || []).join(' ').toLowerCase();
    const brands = (profile.brands || []).join(' ').toLowerCase();
    const name = String(service?.name || '').toLowerCase();
    const hay = `${offered} ${brands} ${name}`;
    if (hay.includes('stk') || hay.includes('emis')) return { key: 'stk', label: 'STK', tone: 'stk' };
    if (hay.includes('pneu')) return { key: 'pneu', label: 'Pneuservis', tone: 'tire' };
    if (hay.includes('moto')) return { key: 'moto', label: 'Motocykly', tone: 'moto' };
    if (hay.includes('kamion') || hay.includes('náklad')) return { key: 'truck', label: 'Nákladní vozidla', tone: 'truck' };
    if ((profile.brands || []).length > 0 || hay.includes('autoriz')) return { key: 'auth', label: 'Autorizovaný servis', tone: 'auth' };
    return { key: 'indep', label: 'Nezávislý servis', tone: 'indep' };
  }

  function serviceLogoLabel(service) {
    const profile = service?.partner_public_profile || {};
    const brand = Array.isArray(profile.brands) && profile.brands[0] ? String(profile.brands[0]) : '';
    const source = brand || service?.name || service?.email || 'S';
    return source.trim().slice(0, 3).toUpperCase();
  }

  function filterServicesRows(rows) {
    const filters = STATE.servicesDirectoryFilters || {};
    return rows.filter((service) => {
      if (filters.inAppOnly && !service.in_app) return false;
      if (STATE.servicesMapVerifiedOnly && !service.is_verified) return false;
      const type = resolveServiceTypeMeta(service);
      const mapCat = STATE.servicesMapCategory || 'all';
      if (mapCat === 'verified' && !service.is_verified) return false;
      if (mapCat === 'autoservis' && type.key !== 'indep' && service.category !== 'autoservis') return false;
      if (mapCat === 'pneuservis' && type.key !== 'pneu') return false;
      if (mapCat === 'stk' && service.category !== 'stk' && type.key !== 'stk') return false;
      if (mapCat === 'sme' && service.category !== 'sme') return false;
      if (mapCat === 'truck_service' && type.key !== 'truck') return false;
      if (filters.type && filters.type !== 'all' && type.key !== filters.type) return false;
      if (filters.authorizedOnly && type.key !== 'auth') return false;
      if (filters.service && filters.service !== 'all') {
        const profile = service?.partner_public_profile || {};
        const offered = Array.isArray(profile.services_offered) ? profile.services_offered : [];
        if (!offered.some((item) => String(item).toLowerCase().includes(String(filters.service).toLowerCase()))) return false;
      }
      const minRating = Number(filters.rating || 0);
      if (minRating > 0) {
        const profile = service?.partner_public_profile || {};
        const rating = Number(profile.average_rating || profile.rating);
        if (!Number.isFinite(rating) || rating < minRating) return false;
      }
      return true;
    });
  }

  function servicesOfferedOptions(rows) {
    const set = new Set();
    rows.forEach((service) => {
      const profile = service?.partner_public_profile || {};
      (profile.services_offered || []).forEach((item) => {
        const label = String(item || '').trim();
        if (label) set.add(label);
      });
    });
    return [...set].sort((a, b) => a.localeCompare(b, 'cs')).slice(0, 20);
  }

  function serviceSourceLabel(service) {
    const map = {
      osm: 'OpenStreetMap',
      mdcr: 'MDČR',
      manual: 'Ručně doplněno',
      staging_seed: 'Staging seed',
      verified_service: 'Ověřený servis',
      catalog: 'Katalog',
    };
    return map[String(service?.source_type || service?.source || '').toLowerCase()] || String(service?.source_type || service?.source || 'Katalog');
  }

  function serviceNavigateUrl(service) {
    const coords = service?.coordinates;
    if (coords && Number.isFinite(Number(coords.lat)) && Number.isFinite(Number(coords.lon))) {
      const lat = Number(coords.lat);
      const lon = Number(coords.lon);
      return `https://mapy.cz/zakladni?planovani-trasy&x=${encodeURIComponent(String(lon))}&y=${encodeURIComponent(String(lat))}&z=16`;
    }
    const query = encodeURIComponent(buildServiceAddressLine(service));
    return `https://mapy.cz/hledani?q=${query}`;
  }

  function serviceNavigateFallbackUrl(service) {
    const coords = service?.coordinates;
    if (coords && Number.isFinite(Number(coords.lat)) && Number.isFinite(Number(coords.lon))) {
      return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(String(coords.lat))},${encodeURIComponent(String(coords.lon))}`;
    }
    return serviceNavigateUrl(service);
  }

  function serviceMapsUrl(service) {
    return serviceNavigateUrl(service);
  }

  function openServiceLocationSheet(service) {
    if (!service) return;
    if (service.in_app && service.id) {
      return runAction(`serviceDetail:${service.id}`);
    }
    return openExternalServiceDetailModal(service);
  }

  function renderServiceMapQuickFilters() {
    const active = STATE.servicesMapCategory || 'all';
    const chips = [
      ['all', 'Vše'],
      ['autoservis', 'Autoservis'],
      ['pneuservis', 'Pneuservis'],
      ['stk', 'STK'],
      ['sme', 'Emise'],
      ['truck_service', 'Nákladní'],
      ['verified', 'Ověřené'],
    ];
    return `<div class="uapp-svc-quick-filters" role="group" aria-label="Rychlé filtry">${chips.map(([key, label]) => `<button type="button" class="uapp-svc-chip${active === key ? ' is-active' : ''}" data-uapp-action="servicesMapCategory:${key}">${esc(label)}</button>`).join('')}</div>`;
  }

  function renderServicesMapEmbed(data, rows) {
    const ref = getServicesRefCoords(data) || {};
    const lat = Number(ref.lat) || 50.0755;
    const lon = Number(ref.lon) || 14.4378;
    const radius = Number(STATE.servicesDirectoryRadius) || 50;
    const legend = serviceMapLegendItems().map((item) => {
      const color = item.key === 'inapp' ? '#1a73e8' : serviceMapPinColor({ key: item.key, tone: item.tone }, item.key === 'inapp');
      return `<span class="uapp-svc-map-legend-item"><i style="background:${color}"></i>${esc(item.label)}</span>`;
    }).join('');
    return `
      <div class="uapp-svc-map-wrap" id="uappSvcMapHost" data-map-lat="${esc(String(lat))}" data-map-lon="${esc(String(lon))}" data-map-radius="${esc(String(radius))}">
        <div class="uapp-svc-map-canvas" id="uappSvcMapCanvas" role="region" aria-label="Mapa servisů"></div>
        <div class="uapp-svc-map-legend" aria-label="Legenda mapy">${legend}</div>
        <div class="uapp-svc-map-controls-wrap${STATE.servicesMapControlsOpen ? ' is-open' : ''}">
          <button type="button" class="uapp-svc-map-controls-toggle" data-uapp-action="servicesMapControlsToggle" aria-expanded="${STATE.servicesMapControlsOpen ? 'true' : 'false'}" aria-controls="uappSvcMapControlsPanel" title="Nastavení vzdálenosti">
            <span aria-hidden="true">◎</span>
            <span>${esc(String(radius))} km</span>
          </button>
          <div class="uapp-svc-map-controls" id="uappSvcMapControlsPanel">
            <h3>Vzdálenost od polohy</h3>
            <label class="uapp-svc-map-slider">
              <input type="range" min="5" max="100" step="5" value="${esc(String(radius))}" data-uapp-svc-filter="radius">
              <span>${esc(String(radius))} km</span>
            </label>
            <label class="uapp-svc-map-toggle">
              <input type="checkbox"${STATE.servicesDirectoryUseLocation !== false ? ' checked' : ''} data-uapp-svc-filter="useLocation">
              <span>Použít aktuální polohu</span>
            </label>
            <button type="button" class="uapp-svc-map-refresh" data-uapp-action="servicesRefreshLocation">⟳ Aktualizovat polohu</button>
          </div>
        </div>
      </div>`;
  }

  function renderServicesCard(service) {
    const id = Number(service?.id);
    const rowKey = esc(service.row_key || (id ? `app-${id}` : `osm-${service.osm_id || 'unknown'}`));
    const type = resolveServiceTypeMeta(service);
    const offeredLine = formatServiceOfferedLine(service);
    const distance = formatServicesDistanceKm(service?.distance_km);
    const address = formatServiceAddressDisplay(service);
    const detailAction = service.in_app && id
      ? `serviceDetail:${id}`
      : `serviceOsmDetail:${encodeURIComponent(String(service.row_key || service.osm_id || ''))}`;
    const statusBits = [
      service?.is_linked ? '<span class="uapp-svc-linked">Propojeno</span>' : '',
      service.in_app
        ? '<span class="uapp-svc-inapp is-yes">V aplikaci</span>'
        : '<span class="uapp-svc-inapp is-no">Mimo aplikaci</span>',
    ].filter(Boolean).join('');
    return `
      <article class="uapp-svc-card" data-service-row="${rowKey}"${id ? ` data-service-id="${id}"` : ''}>
        <div class="uapp-svc-card-logo is-${type.tone}" aria-hidden="true">${esc(serviceLogoLabel(service))}</div>
        <div class="uapp-svc-card-info">
          <div class="uapp-svc-card-title-row">
            <h3>${esc(service?.name || service?.email || 'Servis')}</h3>
            <span class="uapp-svc-badge is-${type.tone}">${esc(type.label)}</span>
          </div>
          ${statusBits ? `<div class="uapp-svc-card-status">${statusBits}</div>` : ''}
          ${offeredLine ? `<p class="uapp-svc-offered">${esc(offeredLine)}</p>` : ''}
        </div>
        <div class="uapp-svc-card-address-col">
          <p class="uapp-svc-address">${esc(address)}</p>
        </div>
        <div class="uapp-svc-distance-col">
          ${distance ? `<span class="uapp-svc-distance"><svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2a7 7 0 0 0-7 7c0 5.25 7 13 7 13s7-7.75 7-13a7 7 0 0 0-7-7zm0 9.5a2.5 2.5 0 1 1 0-5 2.5 2.5 0 0 1 0 5z"/></svg>${esc(distance)}</span>` : ''}
        </div>
        <div class="uapp-svc-card-actions">
          <button type="button" class="uapp-svc-outline-btn" data-uapp-action="${detailAction}">Zobrazit detail</button>
          <a class="uapp-next-btn uapp-next-btn-primary uapp-svc-nav-btn" href="${esc(serviceMapsUrl(service))}" target="_blank" rel="noopener noreferrer">Navigovat</a>
        </div>
      </article>`;
  }

  function openExternalServiceDetailModal(service) {
    if (!service) return;
    const existing = document.getElementById('uappSvcExternalModal');
    if (existing) existing.remove();
    const type = resolveServiceTypeMeta(service);
    const overlay = document.createElement('div');
    overlay.id = 'uappSvcExternalModal';
    overlay.className = 'uapp-svc-modal-overlay uapp-svc-bottom-sheet-host';
    overlay.innerHTML = `
      <div class="uapp-svc-modal uapp-svc-bottom-sheet" role="dialog" aria-modal="true" aria-labelledby="uappSvcExternalTitle">
        <div class="uapp-svc-sheet-handle" aria-hidden="true"></div>
        <div class="uapp-svc-modal-head">
          <div>
            <p class="uapp-svc-modal-kicker">${esc(type.label)} · ${esc(serviceSourceLabel(service))}</p>
            <h2 id="uappSvcExternalTitle">${esc(service.name || 'Servis')}</h2>
          </div>
          <button type="button" class="uapp-svc-modal-close" data-uapp-action="serviceOsmClose" aria-label="Zavřít">×</button>
        </div>
        <p class="uapp-svc-modal-note">${service.is_verified ? 'Ověřený servis v katalogu ToozHub.' : 'Neověřený záznam – údaje se mohou lišit.'}</p>
        <dl class="uapp-svc-modal-meta">
          <div><dt>Stav</dt><dd>${service.is_verified ? 'Ověřený' : 'Neověřený'}</dd></div>
          <div><dt>Zdroj</dt><dd>${esc(serviceSourceLabel(service))}</dd></div>
          <div><dt>Adresa</dt><dd data-uapp-svc-address>${esc(formatServiceAddressDisplay(service))}</dd></div>
          ${service.opening_hours ? `<div><dt>Otevírací doba</dt><dd>${esc(service.opening_hours)}</dd></div>` : ''}
          ${formatServiceContactRows(service).map((row) => `<div><dt>${esc(row.label)}</dt><dd>${row.href ? `<a href="${esc(row.href)}">${esc(row.value)}</a>` : esc(row.value)}</dd></div>`).join('')}
          ${service.distance_km != null ? `<div><dt>Vzdálenost</dt><dd>${esc(formatServicesDistanceKm(service.distance_km) || '')}</dd></div>` : ''}
        </dl>
        <div class="uapp-svc-modal-actions">
          ${service.phone ? `<a class="uapp-next-btn uapp-next-btn-secondary" href="tel:${esc(String(service.phone).replace(/[^\d+]/g, ''))}">Zavolat</a>` : ''}
          <a class="uapp-next-btn uapp-next-btn-primary" href="${esc(serviceNavigateUrl(service))}" target="_blank" rel="noopener noreferrer">Navigovat</a>
          <a class="uapp-next-btn uapp-next-btn-secondary" href="${esc(serviceNavigateFallbackUrl(service))}" target="_blank" rel="noopener noreferrer">Google Maps</a>
          ${service.location_id ? `<button type="button" class="uapp-next-btn uapp-next-btn-secondary" data-uapp-action="serviceMapReport:${service.location_id}">Nahlásit chybu</button>` : ''}
          <button type="button" class="uapp-next-btn uapp-next-btn-secondary" data-uapp-action="servicesConnect">Pozvat servis</button>
          <button type="button" class="uapp-next-btn uapp-next-btn-secondary" data-uapp-action="serviceOsmClose">Zavřít</button>
        </div>
      </div>`;
    overlay.dataset.serviceRowKey = String(service?.row_key || '');
    overlay.addEventListener('click', (event) => {
      if (event.target === overlay) overlay.remove();
    });
    document.body.appendChild(overlay);
    if (!hasUsableServiceAddress(service)) {
      void ensureServiceAddressResolved(service).then((label) => {
        if (!overlay.isConnected) return;
        applyResolvedServiceAddress(service, label);
      });
    }
  }

  function renderServicesDirectoryPage(data) {
    const allRows = buildMergedServiceCatalog(data);
    let filtered = filterServicesRows(allRows);
    if (STATE.servicesDirectorySort === 'name') {
      filtered = filtered.slice().sort((a, b) => String(a?.name || '').localeCompare(String(b?.name || ''), 'cs'));
    }
    const limit = Number(STATE.servicesDirectoryLimit) || 10;
    const visible = filtered.slice(0, limit);
    const hasMore = filtered.length > limit;
    const filters = STATE.servicesDirectoryFilters || {};
    const radius = Number(STATE.servicesDirectoryRadius) || 50;
    const ref = getServicesRefCoords(data) || {};
    const locationLabel = resolveServicesLocationLabel(data);
    const nearbyCount = filtered.filter((row) => {
      const dist = Number(row.distance_km);
      return Number.isFinite(dist) && dist <= radius;
    }).length;
    const serviceOptions = servicesOfferedOptions(allRows);
    const view = STATE.servicesDirectoryView || 'map';
    const loadingBanner = STATE.servicesOsmLoading
      ? '<div class="uapp-svc-loading">Načítám servisy z mapy (autoservisy, pneuservisy, STK, motocykly, kamiony)…</div>'
      : '';
    const errorBanner = STATE.servicesOsmError
      ? `<div class="uapp-svc-osm-error" role="alert">${esc(STATE.servicesOsmError)}</div>`
      : '';
    const mapHintBanner = STATE.servicesMapHint
      ? `<div class="uapp-svc-map-hint" role="status">${esc(STATE.servicesMapHint)}</div>`
      : '';
    const tipBanner = STATE.servicesDirectoryTipHidden ? '' : `
      <div class="uapp-svc-tip" role="note">
        <span aria-hidden="true">💡</span>
        <p>Tip: Zobrazujeme servisy do ${esc(String(radius))} km od vaší polohy. Poloměr hledání můžete kdykoliv upravit posuvníkem na mapě.</p>
        <button type="button" class="uapp-svc-tip-close" data-uapp-action="servicesTipClose" aria-label="Zavřít tip">×</button>
      </div>`;

    return `
      <div class="uapp-svc-page" data-testid="user-app-next-services">
        <nav class="uapp-doc-breadcrumbs" aria-label="Drobečková navigace">
          <button type="button" data-uapp-action="home">Přehled</button>
          <span aria-hidden="true">/</span>
          <span aria-current="page">Servisy</span>
        </nav>
        <header class="uapp-svc-page-head">
          <div>
            <h1 class="uapp-svc-page-title">Mapa servisů</h1>
            <p class="uapp-svc-page-sub">Autoservisy, pneuservisy, STK a emise ve vašem okolí – data z vlastního katalogu.</p>
          </div>
          <div class="uapp-svc-view-toggle" role="group" aria-label="Zobrazení servisů">
            <button type="button" class="${view === 'list' ? 'is-active' : ''}" data-uapp-action="servicesView:list">Seznam</button>
            <button type="button" class="${view === 'map' ? 'is-active' : ''}" data-uapp-action="servicesView:map">Mapa</button>
          </div>
        </header>
        <div class="uapp-svc-search-bar">
          <input type="search" class="uapp-svc-search-input" placeholder="Město, adresa nebo servis" value="${esc(STATE.servicesMapSearchQ || '')}" data-uapp-svc-filter="searchQ">
          <button type="button" class="uapp-next-btn uapp-next-btn-secondary" data-uapp-action="servicesRefreshLocation">Použít moji polohu</button>
        </div>
        ${renderServiceMapQuickFilters()}
        <div class="uapp-svc-layout">
          <div class="uapp-svc-main">
            ${loadingBanner}
            ${errorBanner}
            ${mapHintBanner}
            ${view !== 'list' ? renderServicesMapEmbed(data, filtered) : ''}
            <section class="uapp-svc-list-section">
              <div class="uapp-svc-list-head">
                <h2>Nalezeno ${esc(String(nearbyCount || filtered.length))} servisů do ${esc(String(radius))} km</h2>
                <label class="uapp-svc-sort">
                  <span>Seřadit podle:</span>
                  <select data-uapp-svc-filter="sort">
                    <option value="distance"${STATE.servicesDirectorySort === 'distance' ? ' selected' : ''}>Vzdálenosti</option>
                    <option value="name"${STATE.servicesDirectorySort === 'name' ? ' selected' : ''}>Názvu</option>
                  </select>
                </label>
              </div>
              <div class="uapp-svc-list">
                ${visible.length
                  ? visible.map((service) => renderServicesCard(service)).join('')
                  : '<div class="uapp-svc-empty">V okolí nejsou servisy odpovídající filtrům.</div>'}
              </div>
              ${hasMore ? '<button type="button" class="uapp-svc-load-more" data-uapp-action="servicesLoadMore">Zobrazit další servisy ▾</button>' : ''}
            </section>
          </div>
          <aside class="uapp-svc-aside" aria-label="Filtry servisů">
            <section class="uapp-svc-widget">
              <h3>Filtry</h3>
              <label class="uapp-svc-filter-field">
                <span>Typ servisu</span>
                <select data-uapp-svc-filter="type">
                  <option value="all"${filters.type === 'all' ? ' selected' : ''}>Všechny typy</option>
                  <option value="auth"${filters.type === 'auth' ? ' selected' : ''}>Autorizovaný servis</option>
                  <option value="indep"${filters.type === 'indep' ? ' selected' : ''}>Nezávislý servis</option>
                  <option value="pneu"${filters.type === 'pneu' ? ' selected' : ''}>Pneuservis</option>
                  <option value="stk"${filters.type === 'stk' ? ' selected' : ''}>STK / emise</option>
                  <option value="moto"${filters.type === 'moto' ? ' selected' : ''}>Motocykly</option>
                  <option value="truck"${filters.type === 'truck' ? ' selected' : ''}>Nákladní vozidla</option>
                </select>
              </label>
              <label class="uapp-svc-filter-field">
                <span>Služby</span>
                <select data-uapp-svc-filter="service">
                  <option value="all"${filters.service === 'all' ? ' selected' : ''}>Vyberte službu</option>
                  ${serviceOptions.map((opt) => `<option value="${esc(opt)}"${filters.service === opt ? ' selected' : ''}>${esc(opt)}</option>`).join('')}
                </select>
              </label>
              <div class="uapp-svc-rating-filter">
                <span>Hodnocení</span>
                <div class="uapp-svc-rating-btns">
                  ${[1, 2, 3, 4].map((n) => `<button type="button" class="${Number(filters.rating) === n ? 'is-active' : ''}" data-uapp-action="servicesRating:${n}">${n}+</button>`).join('')}
                </div>
              </div>
              <label class="uapp-svc-check">
                <input type="checkbox" data-uapp-svc-filter="authorizedOnly"${filters.authorizedOnly ? ' checked' : ''}>
                <span>Pouze autorizované servisy</span>
              </label>
            </section>
            <section class="uapp-svc-widget">
              <h3>Moje poloha</h3>
              <p class="uapp-svc-location">${esc(locationLabel)}</p>
              ${ref.lat != null && ref.lon != null
                ? `<p class="uapp-svc-location-coords">${esc(ref.lat.toFixed(5))}, ${esc(ref.lon.toFixed(5))}</p>
                   <p class="uapp-svc-location-meta">${STATE.servicesDirectoryUseLocation === false ? 'Podle zadané adresy' : 'Přesnost: ± 20 m'}</p>`
                : '<p class="uapp-svc-location-meta">Poloha se načte z prohlížeče nebo profilu.</p>'}
              <button type="button" class="uapp-svc-location-btn" data-uapp-action="servicesRefreshLocation">Změnit polohu</button>
            </section>
            ${tipBanner}
            <section class="uapp-svc-widget">
              <h3>Rychlé akce</h3>
              <div class="uapp-svc-quick">
                <button type="button" data-uapp-action="servicesConnect">+ Přidat nový servis</button>
                <button type="button" data-uapp-action="servicesView:map">🗺 Zobrazit mapu všech servisů</button>
                <button type="button" data-uapp-action="serviceHistory">🔧 Servisní historie</button>
              </div>
            </section>
          </aside>
        </div>
      </div>`;
  }

  function bindServicesFilters() {
    document.querySelectorAll('[data-uapp-svc-filter]').forEach((el) => {
      if (el.dataset.uappSvcBound === '1') return;
      el.dataset.uappSvcBound = '1';
      const key = el.getAttribute('data-uapp-svc-filter');
      const apply = () => {
        if (key === 'radius') {
          const nextRadius = Number(el.value) || 50;
          STATE.servicesDirectoryRadius = nextRadius;
          STATE.servicesDirectoryLimit = 30;
          STATE.servicesMapBounds = null;
          STATE.servicesOsmRows = [];
          STATE.servicesMapRows = [];
          const sliderLabel = el.closest('.uapp-svc-map-slider')?.querySelector('span:last-child');
          if (sliderLabel) sliderLabel.textContent = `${nextRadius} km`;
          const toggleLabel = document.querySelector('.uapp-svc-map-controls-toggle span:last-child');
          if (toggleLabel) toggleLabel.textContent = `${nextRadius} km`;
          void loadServicesOsmData({ skipRender: true }).then(() => {
            if (STATE.latestData) patchServicesDirectoryList(STATE.latestData);
          });
          return;
        }
        if (key === 'useLocation') {
          STATE.servicesDirectoryUseLocation = Boolean(el.checked);
          STATE.servicesRefCoords = null;
          STATE.servicesLocationLabel = '';
          STATE.servicesOsmRows = [];
          STATE.servicesMapRows = [];
          if (STATE.servicesDirectoryUseLocation && hasFn('clearClientGeoTelemetry')) {
            try { window.clearClientGeoTelemetry(); } catch (_) {}
          }
          return render();
        }
        if (key === 'searchQ') {
          STATE.servicesMapSearchQ = String(el.value || '');
          STATE.servicesMapBounds = null;
          STATE.servicesOsmRows = [];
          STATE.servicesMapRows = [];
          if (STATE.servicesSearchDebounce) clearTimeout(STATE.servicesSearchDebounce);
          STATE.servicesSearchDebounce = setTimeout(() => {
            void loadServicesOsmData({ skipRender: true }).then(() => {
              if (STATE.latestData) patchServicesDirectoryList(STATE.latestData);
            });
          }, 450);
          return;
        }
        if (key === 'sort') {
          STATE.servicesDirectorySort = el.value;
          return render();
        }
        if (key === 'inAppOnly' || key === 'authorizedOnly') {
          STATE.servicesDirectoryFilters = STATE.servicesDirectoryFilters || {};
          STATE.servicesDirectoryFilters[key] = Boolean(el.checked);
          STATE.servicesDirectoryLimit = 30;
          return render();
        }
        STATE.servicesDirectoryFilters = STATE.servicesDirectoryFilters || {};
        STATE.servicesDirectoryFilters[key] = el.value;
        STATE.servicesDirectoryLimit = 30;
        render();
      };
      if (el.type === 'range' || el.type === 'checkbox') {
        el.addEventListener('change', apply);
        if (el.type === 'range') el.addEventListener('input', apply);
      } else {
        el.addEventListener('change', apply);
      }
    });
  }

  function renderMobileChrome() {
    const badge = document.getElementById('desktopNotificationsBadge') || document.getElementById('mobileNotificationsBadge');
    const count = badge ? String(badge.getAttribute('data-count') || badge.textContent || '0').trim() : '0';
    const showBadge = count && count !== '0';
    return `
      <div class="uapp-next-mobile-bar" aria-label="Mobilní navigace">
        <button type="button" class="uapp-next-mobile-menu" data-uapp-action="mobileNav" aria-label="Otevřít menu" aria-expanded="false">☰</button>
        <div class="uapp-next-mobile-brand">
          <img src="${LOGO_SRC}" alt="" width="32" height="32">
          <span>Správa vozidel</span>
        </div>
        <div class="uapp-next-mobile-actions">
          <button type="button" class="uapp-next-mobile-icon-btn" data-uapp-action="notifications" aria-label="Oznámení"${showBadge ? ` data-count="${esc(count)}"` : ''}>${ICO.bell}</button>
          <button type="button" class="uapp-next-mobile-profile" data-uapp-action="profile" aria-label="Profil">
            <span class="uapp-next-avatar" aria-hidden="true">${esc(initials())}</span>
          </button>
        </div>
      </div>
      <button type="button" class="uapp-next-mobile-overlay" data-uapp-action="mobileNavClose" aria-label="Zavřít menu" tabindex="-1"></button>`;
  }

  function closeMobileNav() {
    document.body.classList.remove('user-app-next-mobile-nav-open');
    const btn = document.querySelector('.uapp-next-mobile-menu');
    if (btn) btn.setAttribute('aria-expanded', 'false');
  }

  function toggleMobileNav() {
    const open = document.body.classList.toggle('user-app-next-mobile-nav-open');
    const btn = document.querySelector('.uapp-next-mobile-menu');
    if (btn) btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  function renderSidebar(data, activeNav) {
    const reminderBadge = activeRemindersCount(data);
    const nav = activeNav || 'home';
    const locks = getSidebarLockFlags();
    return `
      <aside class="uapp-next-sidebar" aria-label="Navigace uživatelského rozhraní">
        <div class="uapp-next-brand">
          <img src="${LOGO_SRC}" alt="" width="40" height="40">
          <span>Správa vozidel</span>
        </div>
        <nav class="uapp-next-nav" aria-label="Sekce aplikace">
          ${navButton('Přehled', ICO.home, 'home', nav === 'home', 0, false)}
          ${navButton('Moje vozidla', ICO.car, 'vehicles', nav === 'vehicles', 0, false)}
          ${navButton('Servisní historie', ICO.wrench, 'serviceHistory', nav === 'serviceHistory', 0, false)}
          ${navButton('Připomínky', ICO.bell, 'reminders', nav === 'reminders', reminderBadge, false)}
          ${navButton('Objednat servis', ICO.calendar, 'reservations', nav === 'reservations', 0, locks.reservations)}
          ${navButton('Dokumenty', ICO.folder, 'documents', nav === 'documents', 0, locks.documents)}
          ${navButton('Servisy', ICO.building, 'servicesDirectory', nav === 'servicesDirectory', 0, locks.servicesDirectory)}
          ${USER_INVOICES_ENABLED ? navButton('Faktury', ICO.invoice, 'invoices', nav === 'invoices', 0, false) : ''}
          ${navButton('Nastavení', ICO.gear, 'settings', nav === 'settings', 0, false)}
        </nav>
        <div class="uapp-next-sidebar-bottom">
          <button type="button" class="uapp-next-help-card" data-uapp-action="help" data-testid="dashboard-help">
            <span class="uapp-next-help-card-ico" aria-hidden="true">?</span>
            <span class="uapp-next-help-card-text">Nápověda</span>
            <span class="uapp-next-help-card-chevron" aria-hidden="true">›</span>
          </button>
          <button type="button" class="uapp-next-side-action" data-uapp-action="collapse" data-testid="dashboard-collapse-sidebar"><span aria-hidden="true">⇤</span><span>Sbalit menu</span></button>
        </div>
      </aside>
    `;
  }

  function searchShortcutKbdLabel() {
    try {
      const platform = String(navigator.platform || '');
      const ua = String(navigator.userAgent || '');
      if (/Mac|iPhone|iPad|iPod/i.test(platform) || /Mac OS X/i.test(ua)) return '⌘ K';
    } catch (_) {}
    return 'Ctrl K';
  }

  function renderTopbar() {
    return `
      <header class="uapp-next-topbar" aria-label="Horní lišta" data-testid="dashboard-topbar">
        <label class="uapp-next-search">
          <span class="uapp-next-search-icon" aria-hidden="true">${ICO.search}</span>
          <input id="uappNextSearch" type="search" autocomplete="off" placeholder="Hledejte podle SPZ, VIN, názvu vozidla…" data-testid="dashboard-search-input">
          <kbd class="uapp-next-search-kbd" aria-hidden="true">${esc(searchShortcutKbdLabel())}</kbd>
        </label>
        <button type="button" class="uapp-next-btn uapp-next-btn-primary" data-uapp-action="addVehicle" data-testid="dashboard-add-vehicle">+ Přidat vozidlo</button>
        <div class="uapp-next-top-actions">
          ${renderTopbarNotificationsButton()}
          ${renderTopbarProfileButton()}
        </div>
      </header>
    `;
  }

  function heroSummaryHtml(data) {
    const total = Number(data.summary?.vehicles_total ?? data.vehicles.length) || 0;
    const stkSoon = stkSoonCount(data);
    const reminders = activeRemindersCount(data);
    const serviceNotes = serviceNotificationsCount(data);
    const vehicleWord = total === 1 ? 'vozidlo' : (total > 1 && total < 5 ? 'vozidla' : 'vozidel');
    const stkWord = stkSoon === 1 ? 'blížící se STK' : 'blížící se STK';
    const reminderWord = reminders === 1 ? 'aktivní připomínku' : (reminders > 1 && reminders < 5 ? 'aktivní připomínky' : 'aktivních připomínek');
    const serviceWord = serviceNotes === 1 ? 'nové upozornění od servisu' : 'nových upozornění od servisu';
    return (
      `Máte <span class="uapp-next-stat-pill uapp-next-stat-pill--navy">${esc(String(total))}</span> ${vehicleWord}, ` +
      `<span class="uapp-next-stat-pill uapp-next-stat-pill--amber">${esc(String(stkSoon))}</span> ${stkWord}, ` +
      `<span class="uapp-next-stat-pill uapp-next-stat-pill--rose">${esc(String(reminders))}</span> ${reminderWord} a ` +
      `<span class="uapp-next-stat-pill uapp-next-stat-pill--blue">${esc(String(serviceNotes))}</span> ${serviceWord}.`
    );
  }

  function renderHero(data) {
    const heroVehicle = data.vehicles[0] || null;
    const needsAttention = fleetNeedsAttention(data);
    return `
      <div class="uapp-next-overview-top" data-testid="dashboard-hero-row">
        <section class="uapp-next-hero" data-testid="dashboard-hero">
          <div class="uapp-next-hero-copy">
            <h1 data-testid="dashboard-hero-greeting">Dobrý den, ${esc(fullName())} 👋</h1>
            <p class="uapp-next-hero-summary">${heroSummaryHtml(data)}</p>
          </div>
          <div class="uapp-next-hero-visual" aria-hidden="true">
            <div class="uapp-next-hero-landscape"></div>
            <div class="uapp-next-hero-car-wrap" data-next-photo-wrap="${heroVehicle ? Number(heroVehicle.id) : ''}">
              ${heroVehicle
                ? '<img id="uappNextHeroPhoto" class="uapp-next-hero-photo-img" alt="" loading="eager">'
                : `<div class="uapp-next-hero-car-fallback">${heroCarSvg()}</div>`}
            </div>
          </div>
        </section>
        <button type="button" class="uapp-next-overall-status" data-uapp-action="attentionOpen" aria-label="Zobrazit, co je potřeba řešit" data-testid="dashboard-overall-status">
          <div class="uapp-next-overall-inner">
            <div class="uapp-next-overall-text">
              <h2>Celkový stav</h2>
              <p class="uapp-next-overall-main ${needsAttention ? 'is-warn' : 'is-ok'}">${needsAttention ? 'Vyžaduje pozornost' : 'Vozidla pod kontrolou'}</p>
              <p class="uapp-next-overall-meta">Poslední aktualizace: dnes v ${esc(formatTodayTimeHm())}</p>
              <span class="uapp-next-overall-link">Zobrazit detaily <span aria-hidden="true">›</span></span>
            </div>
            <div class="uapp-next-overall-ico-wrap" aria-hidden="true">${needsAttention ? ICO.checkWarn : ICO.checkOk}</div>
          </div>
        </button>
      </div>
    `;
  }

  function quickCards(data) {
    const cards = computeQuickCards(data);
    const icoMap = { stk: ICO.quickStk, ins: ICO.quickShield, svc: ICO.wrench, docs: ICO.doc };
    const labels = { stk: 'STK / SME', ins: 'Pojištění', svc: 'Servis', docs: 'Dokumenty' };
    const accentClass = { stk: 'uapp-next-quick-card--warn', ins: 'uapp-next-quick-card--ok', svc: 'uapp-next-quick-card--info', docs: 'uapp-next-quick-card--warn' };
    const quickTestIds = { stk: 'dashboard-quick-stk', ins: 'dashboard-quick-insurance', svc: 'dashboard-quick-service', docs: 'dashboard-quick-documents' };
    return `<div class="uapp-next-quick-grid" data-testid="dashboard-quick-grid">${Object.keys(cards).map((key) => {
      const card = cards[key];
      return `
        <button type="button" class="uapp-next-quick-card ${accentClass[key] || quickToneClass(card.tone)}" data-uapp-action="${esc(card.action)}" data-testid="${esc(quickTestIds[key] || 'dashboard-quick-card')}">
          <span class="uapp-next-quick-card-ico">${icoMap[key] || ICO.quickStk}</span>
          <span class="uapp-next-quick-card-body">
            <span class="uapp-next-quick-card-cat">${labels[key]}</span>
            <strong class="uapp-next-quick-card-title">${esc(card.title)}</strong>
            <span class="uapp-next-quick-card-desc">${esc(card.desc)}</span>
          </span>
          <span class="uapp-next-quick-card-arrow" aria-hidden="true">›</span>
        </button>`;
    }).join('')}</div>`;
  }

  function renderVehicleCard(vehicle, data) {
    const id = Number(vehicle.id);
    const records = recordsFor(data, id);
    const status = vehicleStatusMeta(vehicle, records);
    const stk = stkFieldMeta(vehicle);
    const ins = insuranceFieldMeta(vehicle);
    const svc = serviceFieldMeta(records);
    const km = vehicle.current_mileage_km != null && vehicle.current_mileage_km !== ''
      ? `${Number(vehicle.current_mileage_km).toLocaleString('cs-CZ')} km`
      : '—';
    return `
      <article class="uapp-next-vehicle-card" data-uapp-vehicle-card data-search-text="${esc([getVehicleName(vehicle), vehicle.plate, vehicle.vin, vehicle.brand, vehicle.model].filter(Boolean).join(' ').toLowerCase())}" data-vehicle-id="${id}" data-testid="dashboard-vehicle-card-${id}">
        <button type="button" class="uapp-next-vehicle-open" data-uapp-action="detail:${id}" aria-label="Otevřít detail vozidla ${esc(getVehicleName(vehicle))}">
          <div class="uapp-next-vehicle-visual">
            <div class="uapp-next-photo" data-next-photo-wrap="${id}">
              <img id="uappNextVehiclePhoto-${id}" alt="Fotka vozidla ${esc(getVehicleName(vehicle))}" loading="lazy">
              <div class="uapp-next-photo-fallback">Bez fotky</div>
            </div>
            <span class="${badgeClass(status.tone === 'warn' ? 'warn' : 'ok')}">${esc(status.label)}</span>
          </div>
          <div class="uapp-next-vehicle-body uapp-next-vehicle-body--open">
            <h3 class="uapp-next-vehicle-title">${esc(getVehicleName(vehicle))}</h3>
          <div class="uapp-next-vehicle-subrow">
            ${renderPlateBadge(vehicle.plate)}
          </div>
          <div class="uapp-next-vehicle-meta">
            <div class="uapp-next-meta-row"><span class="uapp-next-meta-k">VIN</span><span class="uapp-next-meta-v">${esc(shortVin(vehicle))}</span></div>
            <div class="uapp-next-meta-row"><span class="uapp-next-meta-k">Nájezd</span><span class="uapp-next-meta-v"><strong>${esc(km)}</strong></span></div>
          </div>
          <div class="uapp-next-status-lines">
            <div class="uapp-next-status-line"><span>STK</span><strong class="uapp-next-status-val ${toneClass(stk.tone)}">${esc(stk.label)}</strong></div>
            <div class="uapp-next-status-line"><span>Pojištění</span><strong class="uapp-next-status-val ${toneClass(ins.tone)}">${esc(ins.label)}</strong></div>
            <div class="uapp-next-status-line"><span>Servis</span><strong class="uapp-next-status-val ${toneClass(svc.tone)}">${esc(svc.label)}</strong></div>
          </div>
          </div>
        </button>
        ${renderCardActionBar(id, false)}
      </article>
    `;
  }

  function renderVehicles(data) {
    const vehicles = data.vehicles.slice(0, 3);
    const cards = vehicles.length
      ? vehicles.map((vehicle) => renderVehicleCard(vehicle, data)).join('')
      : '';
    return `
      <section class="uapp-next-vehicles-section" data-testid="dashboard-vehicles-section">
        <div class="uapp-next-section-head">
          <h2 class="uapp-next-section-title">Moje vozidla</h2>
          <button type="button" class="uapp-next-section-link" data-uapp-action="vehicles" data-testid="dashboard-view-all-vehicles">Zobrazit všechna vozidla →</button>
        </div>
        <div class="uapp-next-vehicle-grid" data-testid="dashboard-vehicle-grid">
          ${cards || '<div class="uapp-next-empty uapp-next-empty--inline">Zatím nemáte žádné vozidlo. Přidejte první vozidlo a přehled se naplní reálnými daty.</div>'}
        </div>
        <button type="button" class="uapp-next-add-card" data-uapp-action="addVehicle" data-testid="dashboard-add-vehicle-card">
          <span class="uapp-next-add-plus">+</span>
          <strong>Přidat další vozidlo</strong>
          <span>Rychle přidejte nové vozidlo do své správy</span>
        </button>
      </section>
    `;
  }

  function asideHead(title, actionLabel, action) {
    return `
      <div class="uapp-next-aside-head">
        <h3>${esc(title)}</h3>
        <button type="button" class="uapp-next-aside-link" data-uapp-action="${esc(action)}">${esc(actionLabel)}</button>
      </div>`;
  }

  function reminderAsideRows(data) {
    const rows = data.reminders
      .filter((item) => !item?.is_completed)
      .slice(0, 4)
      .map((item) => {
        const title = item.text || item.title || item.type || 'Připomínka';
        const vehicle = item.vehicle_name || item.vehicle_plate || '';
        const diff = daysUntil(item.due_date || item.notify_at);
        let value = formatDate(item.due_date || item.notify_at);
        let tone = 'neutral';
        if (diff != null && diff >= 0 && diff <= 60) {
          value = diff === 1 ? 'za 1 den' : `do ${diff} dnů`;
          tone = 'warn';
        } else if (diff != null && diff < 0) {
          value = 'po termínu';
          tone = 'bad';
        }
        return {
          icon: '□',
          title,
          detail: vehicle,
          value,
          tone,
          action: Number(item?.vehicle_id) > 0 ? `detailTab:ops:${Number(item.vehicle_id)}` : 'reminders',
        };
      });
    if (rows.length) return rows;
    return [];
  }

  function activityAsideRows(data) {
    const recent = Array.isArray(data.summary?.recent_activity) ? data.summary.recent_activity : [];
    const fromSummary = recent.slice(0, 4).map((item) => ({
      title: item.description || item.title || 'Aktivita',
      when: formatDateTime(item.performed_at || item.created_at),
      detail: item.vehicle_name || '',
      action: Number(item?.vehicle_id) > 0 ? `detail:${Number(item.vehicle_id)}` : 'serviceHistory',
    }));
    if (fromSummary.length) return fromSummary;
    const fromRecords = [];
    data.recordEntries.forEach(({ vehicle, records }) => {
      records.slice(0, 1).forEach((record) => {
        fromRecords.push({
          title: record.description || 'Servisní záznam',
          when: formatDateTime(record.performed_at || record.created_at),
          detail: getVehicleName(vehicle),
          action: `detailTab:service:${Number(vehicle.id)}`,
        });
      });
    });
    fromRecords.sort((a, b) => String(b.when).localeCompare(String(a.when), 'cs'));
    return fromRecords.slice(0, 4);
  }

  function grantBadge(statusRaw) {
    const status = String(statusRaw || '').toLowerCase();
    if (status.includes('approve') || status.includes('schv') || status.includes('active') || status.includes('granted')) {
      return { label: 'Schváleno', tone: 'ok' };
    }
    if (status.includes('pending') || status.includes('ček') || status.includes('wait')) {
      return { label: 'Čeká na schválení', tone: 'warn' };
    }
    if (status.includes('reject') || status.includes('odm')) {
      return { label: 'Odmítnuto', tone: 'bad' };
    }
    return { label: statusRaw || 'Stav přístupu', tone: 'neutral' };
  }

  function serviceAsideRows(data) {
    const grants = data.accessGrants.slice(0, 4).map((grant) => {
      const badge = grantBadge(grant.status);
      return {
        name: grant.service_name || grant.service_email || 'Servis',
        meta: [grant.vehicle_name || grant.vehicle_plate, grant.access_level || grant.role].filter(Boolean).join(' · ') || 'Servisní přístup',
        badge: badge.label,
        tone: badge.tone,
        action: Number(grant?.vehicle_id) > 0 ? `detailTab:access:${Number(grant.vehicle_id)}` : 'servicesDirectory',
      };
    });
    if (grants.length) return grants;
    return data.services.slice(0, 3).map((service) => ({
      name: service.name || service.email || 'Servis',
      meta: [service.city, service.email].filter(Boolean).join(' · ') || 'Uložený kontakt',
      badge: 'Bez přístupu',
      tone: 'neutral',
    }));
  }

  function renderSide(data) {
    const reminders = reminderAsideRows(data);
    const activity = activityAsideRows(data);
    const services = serviceAsideRows(data);

    const reminderList = reminders.length
      ? reminders.map((row) => `
          <li>
            <button type="button" class="uapp-next-aside-row" data-uapp-action="${esc(row.action || 'reminders')}">
              <span class="uapp-next-aside-row-icon" aria-hidden="true">${row.icon}</span>
              <div class="uapp-next-aside-row-main">
                <strong>${esc(row.title)}</strong>
                <span>${esc(row.detail || '')}</span>
              </div>
              <span class="uapp-next-aside-pill ${toneClass(row.tone)}">${esc(row.value)}</span>
              <span class="uapp-next-aside-row-arrow" aria-hidden="true">›</span>
            </button>
          </li>`).join('')
      : '<li class="uapp-next-aside-empty">Bez blížících se termínů.</li>';

    const activityList = activity.length
      ? activity.map((row) => `
          <li>
            <button type="button" class="uapp-next-aside-activity-item" data-uapp-action="${esc(row.action || 'serviceHistory')}">
              <span class="uapp-next-act-dot" aria-hidden="true"></span>
              <div>
                <strong>${esc(row.title)}</strong>
                <span>${esc(row.when)}${row.detail ? ` · ${esc(row.detail)}` : ''}</span>
              </div>
            </button>
          </li>`).join('')
      : '<li class="uapp-next-aside-empty">Zatím bez poslední aktivity.</li>';

    const serviceList = services.length
      ? services.map((row) => `
          <li>
            <button type="button" class="uapp-next-aside-access-item" data-uapp-action="${esc(row.action || 'servicesDirectory')}">
              <div class="uapp-next-aside-access-top">
                <strong>${esc(row.name)}</strong>
                <span class="uapp-next-aside-pill ${toneClass(row.tone)}">${esc(row.badge)}</span>
              </div>
              <span class="uapp-next-aside-access-meta">${esc(row.meta)}</span>
            </button>
          </li>`).join('')
      : '<li class="uapp-next-aside-empty">Zatím nejsou aktivní sdílené přístupy ani servisní kontakty.</li>';

    return `
      <aside class="uapp-next-overview-aside" data-testid="dashboard-overview-aside">
        <section class="uapp-next-aside-card" data-testid="dashboard-aside-deadlines">
          ${asideHead('Blížící se termíny', 'Zobrazit všechny →', 'reminders')}
          <ul class="uapp-next-aside-list">${reminderList}</ul>
          <button type="button" class="uapp-next-aside-foot-link" data-uapp-action="reminders" data-testid="dashboard-aside-all-reminders">Zobrazit všechny připomínky →</button>
        </section>
        <section class="uapp-next-aside-card" data-testid="dashboard-aside-activity">
          ${asideHead('Poslední aktivita', 'Zobrazit vše →', 'serviceHistory')}
          <ul class="uapp-next-aside-activity">${activityList}</ul>
        </section>
        <section class="uapp-next-aside-card" data-testid="dashboard-aside-access">
          ${asideHead('Servisy a přístupy', 'Spravovat přístupy →', 'servicesDirectory')}
          <ul class="uapp-next-aside-access">${serviceList}</ul>
        </section>
      </aside>
    `;
  }

  function renderGarageVehicleCard(vehicle, data, viewMode) {
    const id = Number(vehicle.id);
    const records = recordsFor(data, id);
    const status = getCatalogVehicleStatus(vehicle, records);
    const stk = stkCatalogLabel(vehicle);
    const ins = insuranceFieldMeta(vehicle);
    const svc = lastServiceLabel(records);
    const km = vehicle.current_mileage_km != null && vehicle.current_mileage_km !== ''
      ? `${Number(vehicle.current_mileage_km).toLocaleString('cs-CZ')} km`
      : '—';
    const searchText = [getVehicleName(vehicle), vehicle.plate, vehicle.vin, vehicle.brand, vehicle.model].filter(Boolean).join(' ').toLowerCase();

    if (viewMode === 'list') {
      return `
        <article class="uapp-next-garage-card uapp-next-garage-card--list" data-uapp-vehicle-card data-search-text="${esc(searchText)}" data-vehicle-id="${id}">
          <button type="button" class="uapp-next-garage-list-main" data-uapp-action="detail:${id}">
            <span class="${catalogBadgeClass(status.tone)}">${esc(status.label)}</span>
            <strong>${esc(getVehicleName(vehicle))}</strong>
            ${renderPlateBadge(vehicle.plate, 'sm')}
            <span class="uapp-next-garage-list-meta">${esc(stk.label)} · ${esc(svc.label)}</span>
          </button>
          <div class="uapp-next-garage-list-actions">
            <button type="button" data-uapp-action="detail:${id}">Detail</button>
            <button type="button" data-uapp-action="addRecord:${id}">Přidat záznam</button>
            <button type="button" data-uapp-action="documentsVehicle:${id}">Dokumenty</button>
            <button type="button" data-uapp-action="shareVehicle:${id}">Sdílet</button>
          </div>
        </article>`;
    }

    return `
      <article class="uapp-next-garage-card" data-uapp-vehicle-card data-search-text="${esc(searchText)}" data-vehicle-id="${id}">
        <div class="uapp-next-garage-photo">
          <div class="uapp-next-photo" data-next-photo-wrap="${id}">
            <img id="uappNextGaragePhoto-${id}" alt="Fotka vozidla ${esc(getVehicleName(vehicle))}" loading="lazy">
            <div class="uapp-next-photo-fallback">Bez fotky</div>
          </div>
          <span class="${catalogBadgeClass(status.tone)}">${esc(status.label)}</span>
        </div>
        <div class="uapp-next-garage-body">
          <h3 class="uapp-next-garage-title">${esc(getVehicleName(vehicle))}</h3>
          <div class="uapp-next-garage-sub">
            ${renderPlateBadge(vehicle.plate)}
            <span class="uapp-next-garage-vin">VIN ${esc(vehicle.vin || '—')}</span>
          </div>
          <div class="uapp-next-garage-km-row">
            <span class="uapp-next-garage-km-ico" aria-hidden="true">◔</span>
            <span>Nájezd</span>
            <strong>${esc(km)}</strong>
          </div>
          <div class="uapp-next-garage-lines">
            <div class="uapp-next-garage-line">
              <span class="uapp-next-garage-line-ico" aria-hidden="true">${ICO.quickStk}</span>
              <span>STK</span>
              <strong class="uapp-next-status-val ${toneClass(stk.tone)}">${esc(stk.label)}</strong>
            </div>
            <div class="uapp-next-garage-line">
              <span class="uapp-next-garage-line-ico" aria-hidden="true">${ICO.quickShield}</span>
              <span>Pojištění</span>
              <strong class="uapp-next-status-val ${toneClass(ins.tone)}">${esc(ins.label)}</strong>
            </div>
            <div class="uapp-next-garage-line">
              <span class="uapp-next-garage-line-ico" aria-hidden="true">${ICO.wrench}</span>
              <span>Poslední servis</span>
              <strong class="uapp-next-status-val ${toneClass(svc.tone)}">${esc(svc.label)}</strong>
            </div>
          </div>
          ${renderCardActionBar(id, true)}
        </div>
      </article>`;
  }

  function renderAddGarageCard() {
    return `
      <article class="uapp-next-garage-card uapp-next-garage-card--add">
        <div class="uapp-next-garage-add-inner">
          <div class="uapp-next-garage-add-ico" aria-hidden="true">${ICO.car}<span>+</span></div>
          <h3 class="uapp-next-garage-add-title">Přidat nové vozidlo</h3>
          <p class="uapp-next-garage-add-text">Přidejte vozidlo podle SPZ nebo VIN a mějte vše pohromadě.</p>
          <button type="button" class="uapp-next-btn uapp-next-btn-primary" data-uapp-action="addVehicle">+ Přidat vozidlo</button>
        </div>
      </article>`;
  }

  function renderVehiclesManageHint() {
    if (!STATE.vehiclesManageHint) return '';
    const text = STATE.vehiclesManageHint === 'hide'
      ? 'Skrytí vozidla: otevřete detail vozidla a použijte tlačítko „Odebrat“ — vozidlo se archivuje a zmizí z běžného přehledu.'
      : 'Odebrání vozidla: otevřete detail vozidla a použijte tlačítko „Odebrat vozidlo“ — historie zůstane v digitálním výpisu.';
    return `
      <div class="uapp-next-manage-hint" data-testid="vehicles-manage-hint">
        <p>${esc(text)}</p>
        <button type="button" class="uapp-next-manage-hint-close" data-uapp-action="vehiclesManageHintClose" aria-label="Zavřít">×</button>
      </div>`;
  }

  function renderVehiclesReorderPanel(vehicles) {
    const order = (STATE.reorderDraftOrder && STATE.reorderDraftOrder.length)
      ? STATE.reorderDraftOrder.slice()
      : vehicles.map((v) => Number(v.id));
    return `
      <section class="uapp-next-reorder-panel" data-testid="vehicles-reorder-panel">
        <div class="uapp-next-reorder-head">
          <h2>Změnit pořadí vozidel</h2>
          <p>Přesuňte vozidla šipkami nahoru nebo dolů. Po dokončení uložte pořadí.</p>
        </div>
        <ol class="uapp-next-reorder-list">
          ${order.map((id, idx) => {
            const vehicle = vehicles.find((v) => Number(v.id) === Number(id));
            if (!vehicle) return '';
            return `
              <li class="uapp-next-reorder-item">
                <span class="uapp-next-reorder-index">${idx + 1}.</span>
                <span class="uapp-next-reorder-name">${esc(getVehicleName(vehicle))}</span>
                <span class="uapp-next-reorder-actions">
                  <button type="button" data-uapp-action="vehicleReorderUp:${id}" ${idx === 0 ? 'disabled' : ''} aria-label="Posunout nahoru">↑</button>
                  <button type="button" data-uapp-action="vehicleReorderDown:${id}" ${idx === order.length - 1 ? 'disabled' : ''} aria-label="Posunout dolů">↓</button>
                </span>
              </li>`;
          }).join('')}
        </ol>
        <div class="uapp-next-reorder-actions-bar">
          <button type="button" class="uapp-next-btn uapp-next-btn-primary" data-uapp-action="vehicleReorderSave">Uložit pořadí</button>
          <button type="button" class="uapp-next-btn uapp-next-btn-secondary" data-uapp-action="vehicleReorderCancel">Zrušit</button>
        </div>
      </section>`;
  }

  function renderFilterPill(id, label, count, dotClass) {
    const active = STATE.vehiclesFilter === id ? ' is-active' : '';
    const dot = dotClass ? `<span class="uapp-next-filter-dot ${dotClass}" aria-hidden="true"></span>` : '';
    return `<button type="button" class="uapp-next-filter-pill${active}" data-uapp-action="filter:${id}">${dot}${esc(label)} <span class="uapp-next-filter-count">${esc(String(count))}</span></button>`;
  }

  function renderVehiclesCatalog(data) {
    const counts = getFilterCounts(data);
    const total = counts.all;
    const viewMode = getStoredViewMode();
    const baseList = filterCatalogVehicles(data, STATE.vehiclesFilter, STATE.vehiclesSearchQuery);
    const reorderVehicles = filterCatalogVehicles(data, 'all', '');
    const filtered = sortCatalogVehicles(baseList, data, STATE.vehiclesSort);
    const vehicleWord = total === 1 ? 'vozidlo' : (total > 1 && total < 5 ? 'vozidla' : 'vozidel');
    const gridClass = viewMode === 'list' ? 'uapp-next-garage-grid uapp-next-garage-grid--list' : 'uapp-next-garage-grid';
    const customOrder = getGarageVehicleOrder();

    const cards = filtered.length
      ? filtered.map((vehicle) => renderGarageVehicleCard(vehicle, data, viewMode)).join('')
      : `<div class="uapp-next-empty uapp-next-garage-empty">${STATE.vehiclesFilter === 'archived' ? 'Archivovaná vozidla nejsou v aktuálním seznamu API. Po archivaci vozidlo zmizí z běžného přehledu.' : 'Žádné vozidlo neodpovídá filtru nebo vyhledávání.'}</div>`;

    return `
      <section class="uapp-next-catalog" data-testid="user-app-next-vehicles">
        ${STATE.vehiclesReorderMode ? renderVehiclesReorderPanel(reorderVehicles) : ''}
        ${!STATE.vehiclesReorderMode ? renderVehiclesManageHint() : ''}
        <header class="uapp-next-catalog-head">
          <div>
            <h1 class="uapp-next-catalog-title">Moje vozidla</h1>
            <p class="uapp-next-catalog-sub">Máte <strong>${esc(String(total))}</strong> ${vehicleWord} · <button type="button" class="uapp-next-link-btn" data-uapp-action="filter:archived">Zobrazit archivovaná</button></p>
          </div>
        </header>
        <div class="uapp-next-catalog-toolbar">
          <div class="uapp-next-filter-pills">
            ${renderFilterPill('all', 'Všechna', counts.all, '')}
            ${renderFilterPill('ok', 'V pořádku', counts.ok, 'is-green')}
            ${renderFilterPill('attention', 'Vyžaduje pozornost', counts.attention, 'is-orange')}
            ${renderFilterPill('service', 'V servisu', counts.service, 'is-red')}
            ${renderFilterPill('archived', 'V archivu', counts.archived, 'is-gray')}
          </div>
          <div class="uapp-next-catalog-controls">
            <label class="uapp-next-sort-label">
              <span>Řadit podle:</span>
              <select id="uappNextSortSelect" data-uapp-sort-select>
                <option value="activity"${STATE.vehiclesSort === 'activity' ? ' selected' : ''}>Poslední aktivity</option>
                <option value="name"${STATE.vehiclesSort === 'name' ? ' selected' : ''}>Název A–Z</option>
                ${customOrder.length ? `<option value="custom"${STATE.vehiclesSort === 'custom' ? ' selected' : ''}>Vlastní pořadí</option>` : ''}
              </select>
            </label>
            <div class="uapp-next-view-toggle" role="group" aria-label="Zobrazení vozidel">
              <button type="button" class="${viewMode === 'grid' || viewMode === 'compact' ? 'is-active' : ''}" data-uapp-action="viewMode:grid" aria-label="Mřížka">▦</button>
              <button type="button" class="${viewMode === 'list' ? 'is-active' : ''}" data-uapp-action="viewMode:list" aria-label="Seznam">☰</button>
            </div>
            ${!STATE.vehiclesReorderMode && total > 1 ? '<button type="button" class="uapp-next-link-btn" data-uapp-action="vehiclesReorderStart">Změnit pořadí</button>' : ''}
          </div>
        </div>
        ${STATE.vehiclesReorderMode ? '' : `<div class="${gridClass}">
          ${cards}
          ${viewMode !== 'list' ? renderAddGarageCard() : ''}
        </div>`}
        <div class="uapp-next-catalog-summary">
          <div class="uapp-next-summary-stats">
            <div class="uapp-next-summary-stat is-blue"><span aria-hidden="true">▣</span><div><strong>${esc(String(counts.all))}</strong><span>Celkem vozidel</span></div></div>
            <div class="uapp-next-summary-stat is-orange"><span aria-hidden="true">◷</span><div><strong>${esc(String(counts.attention))}</strong><span>Vyžaduje pozornost</span></div></div>
            <div class="uapp-next-summary-stat is-red"><span aria-hidden="true">${ICO.wrench.replace('class="uapp-next-svg"', 'class="uapp-next-svg uapp-next-summary-ico"')}</span><div><strong>${esc(String(counts.service))}</strong><span>V servisu</span></div></div>
            <div class="uapp-next-summary-stat is-green"><span aria-hidden="true">✓</span><div><strong>${esc(String(counts.ok))}</strong><span>V pořádku</span></div></div>
          </div>
          <button type="button" class="uapp-next-summary-link-card" data-uapp-action="home">
            <span>Zobrazit všechna vozidla v přehledu</span>
            <span aria-hidden="true">›</span>
          </button>
        </div>
      </section>`;
  }

  function renderMainCanvas(view, data) {
    if (view === 'invoices' && !USER_INVOICES_ENABLED) {
      view = 'home';
    }
    if (view === 'vehicles') {
      return `
        ${renderTopbar()}
        ${renderVehiclesCatalog(data)}
      `;
    }
    if (view === 'reminders') {
      return `
        ${renderTopbar()}
        ${renderRemindersPage(data)}
      `;
    }
    if (view === 'serviceHistory') {
      return `
        ${renderTopbar()}
        ${renderServiceHistoryPage(data)}
      `;
    }
    if (view === 'documents') {
      return `
        ${renderTopbar()}
        ${renderDocumentsPage(data)}
      `;
    }
    if (view === 'invoices') {
      return `
        ${renderTopbar()}
        <div class="uapp-next-invoices-page" data-testid="user-app-next-invoices">
          <div id="uappNextInvoicesMount" class="uapp-next-invoices-mount"></div>
        </div>
      `;
    }
    if (view === 'servicesDirectory') {
      return `
        ${renderTopbar()}
        ${renderServicesDirectoryPage(data)}
      `;
    }
    if (view === 'settings') {
      return `
        <div class="uapp-next-settings-mount" id="uappNextSettingsMount" data-testid="user-app-next-settings-root"></div>
      `;
    }
    if (view === 'home') {
      return `
        ${renderTopbar()}
        <div class="uapp-next-overview-shell" data-testid="dashboard-overview-shell">
          ${renderHero(data)}
          ${quickCards(data)}
          <div class="uapp-next-overview-body" data-testid="dashboard-overview-body">
            <div class="uapp-next-overview-main">
              ${renderVehicles(data)}
            </div>
            ${renderSide(data)}
          </div>
        </div>
      `;
    }
    return renderLegacySectionCanvas(view);
  }

  function renderUserAppScreen(view, data) {
    preserveLegacyOverlays();
    restoreLegacyTabMount();
    const root = ensureUserAppScreenRoot();
    if (!root) return;

    const activeView = view || 'home';
    const isLegacySection = Boolean(LEGACY_SECTION_META[activeView]);
    let testId = 'user-app-next-dashboard';
    if (isLegacySection) testId = LEGACY_SECTION_META[activeView].testId;
    else if (activeView === 'vehicles') testId = 'user-app-next-vehicles';
    else if (activeView === 'reminders') testId = 'user-app-next-reminders';
    else if (activeView === 'serviceHistory') testId = 'user-app-next-service-history';
    else if (activeView === 'documents') testId = 'user-app-next-documents';
    else if (activeView === 'invoices') testId = 'user-app-next-invoices';
    else if (activeView === 'servicesDirectory') testId = 'user-app-next-services';
    else if (activeView === 'settings') testId = 'user-app-next-settings';
    else if (activeView === 'reservations') testId = 'user-app-next-reservations';
    else if (activeView === 'support') testId = 'user-app-next-support';

    root.replaceChildren();
    root.innerHTML = `
      <div class="uapp-next-shell" data-testid="${testId}">
        ${renderMobileChrome()}
        ${renderSidebar(data, activeView)}
        <main class="uapp-next-main">
          <div class="uapp-next-canvas">
            ${renderMainCanvas(activeView, data)}
          </div>
        </main>
      </div>
    `;

    document.body.classList.toggle('user-app-next-view-vehicles', activeView === 'vehicles');
    document.body.classList.toggle('user-app-next-view-legacy', isLegacySection);
    document.body.classList.toggle('user-app-next-view-reminders', activeView === 'reminders');
    document.body.classList.toggle('user-app-next-view-service-history', activeView === 'serviceHistory');
    document.body.classList.toggle('user-app-next-view-documents', activeView === 'documents');
    document.body.classList.toggle('user-app-next-view-invoices', activeView === 'invoices');
    document.body.classList.toggle('user-app-next-view-services', activeView === 'servicesDirectory');
    document.body.classList.toggle('user-app-next-view-settings', activeView === 'settings');
    document.body.classList.toggle('user-app-next-view-reservations', activeView === 'reservations');
    document.body.classList.toggle('user-app-next-view-support', activeView === 'support');
    if (isLegacySection) {
      mountLegacyTabContent(activeView);
    }
    bindSearch();
    bindSearchShortcut();
    if (activeView === 'vehicles') {
      hydrateGarageImages(data);
      bindSortSelect();
    } else if (activeView === 'home') {
      hydrateImages(data);
    } else if (activeView === 'serviceHistory') {
      bindServiceHistoryFilters();
    } else if (activeView === 'documents') {
      bindDocumentsFilters();
    } else if (activeView === 'invoices') {
      mountInvoicesModule(root);
    } else if (activeView === 'servicesDirectory') {
      bindServicesFilters();
      void bindServicesMap(data);
      const visibleServices = filterServicesRows(buildMergedServiceCatalog(data)).slice(0, Number(STATE.servicesDirectoryLimit) || 30);
      void hydrateServiceAddresses(visibleServices);
    } else if (activeView === 'settings') {
      const settingsMount = root.querySelector('#uappNextSettingsMount');
      if (settingsMount && typeof window.UserSettings !== 'undefined') {
        const panel = hasFn('getSettingsPanelFromRoute') ? window.getSettingsPanelFromRoute() : 'profile';
        if (settingsMount.querySelector('.uapp-settings-page') && typeof window.UserSettings.onRoutePanel === 'function') {
          void window.UserSettings.onRoutePanel(panel);
        } else if (typeof window.UserSettings.mount === 'function') {
          void window.UserSettings.mount(settingsMount);
        }
      }
    }
  }

  function mountInvoicesModule(root) {
    if (!USER_INVOICES_ENABLED) return;
    const mount = root && root.querySelector('#uappNextInvoicesMount');
    if (!mount) return;
    if (typeof window.UserInvoicesDashboard !== 'undefined' && typeof window.UserInvoicesDashboard.mountInto === 'function') {
      window.UserInvoicesDashboard.mountInto(mount);
      return;
    }
    if (typeof window.loadUserInvoices === 'function') {
      window.loadUserInvoices(true);
      return;
    }
    mount.innerHTML = '<div class="uapp-doc-empty-state">Modul faktur se nepodařilo načíst. Obnovte stránku.</div>';
  }

  function renderShell(data) {
    setActiveClass(true);
    const view = getActiveView() || 'home';
    renderUserAppScreen(view, data);
  }

  async function hydrateImageForVehicle(vehicle, img, scope) {
    if (!vehicle || !img) return;
    const wrap = img.closest('[data-next-photo-wrap]');
    const fallback = wrap?.querySelector('.uapp-next-photo-fallback');
    const heroFallback = wrap?.querySelector('.uapp-next-hero-car-fallback');
    if (fallback) fallback.style.display = 'grid';
    try {
      if (typeof vehiclePrimaryPhotoAvailable === 'function' && vehiclePrimaryPhotoAvailable(vehicle) && typeof hydrateVehiclePhotoPreview === 'function') {
        await hydrateVehiclePhotoPreview(Number(vehicle.id), img, scope);
      } else if (typeof fetchVehicleStockImageUrl === 'function') {
        const url = await fetchVehicleStockImageUrl(vehicle);
        if (!url) throw new Error('Bez katalogové fotky');
        if (typeof isProtectedCatalogImageUrl === 'function' && isProtectedCatalogImageUrl(url) && typeof hydrateAuthorizedImageUrl === 'function') {
          await hydrateAuthorizedImageUrl(url, img, scope);
        } else {
          img.src = url;
        }
      } else {
        throw new Error('Bez fotky');
      }
      img.style.display = 'block';
      if (fallback) fallback.style.display = 'none';
      if (heroFallback) heroFallback.style.display = 'none';
    } catch (_) {
      img.removeAttribute('src');
      img.style.display = 'none';
      if (fallback) fallback.style.display = 'grid';
    }
  }

  function hydrateImages(data) {
    const heroVehicle = data.vehicles[0];
    if (heroVehicle) {
      hydrateImageForVehicle(heroVehicle, document.getElementById('uappNextHeroPhoto'), `uapp-next-hero:${heroVehicle.id}`);
    }
    data.vehicles.slice(0, 3).forEach((vehicle) => {
      hydrateImageForVehicle(vehicle, document.getElementById(`uappNextVehiclePhoto-${Number(vehicle.id)}`), `uapp-next-card:${vehicle.id}`);
    });
  }

  function hydrateGarageImages(data) {
    (data.vehicles || []).forEach((vehicle) => {
      const img = document.getElementById(`uappNextGaragePhoto-${Number(vehicle.id)}`);
      if (img) {
        hydrateImageForVehicle(vehicle, img, `uapp-next-garage:${vehicle.id}`);
      }
    });
  }

  function setStoredViewMode(mode) {
    const next = mode === 'list' ? 'list' : 'grid';
    if (typeof SpravaVozidelStorage !== 'undefined') {
      SpravaVozidelStorage.setLocal('vehicleViewMode', next);
    } else {
      localStorage.setItem('sprava_vozidel_vehicle_view_mode', next);
      localStorage.removeItem('toozhub_vehicle_view_mode');
    }
  }

  function reRenderCatalog() {
    if (STATE.latestData && getActiveView() === 'vehicles') {
      renderUserAppScreen('vehicles', STATE.latestData);
    }
  }

  function bindSortSelect() {
    const select = document.getElementById('uappNextSortSelect');
    if (!select || select.dataset.uappBound === '1') return;
    select.dataset.uappBound = '1';
    select.addEventListener('change', () => {
      const val = select.value;
      STATE.vehiclesSort = val === 'name' ? 'name' : (val === 'custom' ? 'custom' : 'activity');
      reRenderCatalog();
    });
  }

  function initReorderDraftFromData(data) {
    const vehicles = filterCatalogVehicles(data || STATE.latestData || {}, 'all', '');
    const saved = getGarageVehicleOrder();
    const ids = vehicles.map((v) => Number(v.id)).filter((id) => Number.isFinite(id));
    if (saved.length) {
      const known = new Set(ids);
      const ordered = saved.filter((id) => known.has(id));
      ids.forEach((id) => { if (!ordered.includes(id)) ordered.push(id); });
      STATE.reorderDraftOrder = ordered;
      return;
    }
    STATE.reorderDraftOrder = ids;
  }

  function moveReorderDraftItem(vehicleId, direction) {
    const order = (STATE.reorderDraftOrder || []).slice();
    const idx = order.findIndex((id) => Number(id) === Number(vehicleId));
    if (idx < 0) return;
    const next = idx + direction;
    if (next < 0 || next >= order.length) return;
    const tmp = order[idx];
    order[idx] = order[next];
    order[next] = tmp;
    STATE.reorderDraftOrder = order;
    reRenderCatalog();
  }

  async function saveVehicleOrderDraft() {
    const order = (STATE.reorderDraftOrder || []).slice();
    if (!order.length) return;
    if (!apiReady()) throw new Error('Nejste přihlášeni.');
    await apiCall('/api/v1/user/settings/garage', 'PATCH', { vehicle_order: order });
    STATE.garageVehicleOrder = order.slice();
    window.__garageVehicleOrder = order.slice();
    STATE.vehiclesSort = 'custom';
    STATE.vehiclesReorderMode = false;
    STATE.reorderDraftOrder = null;
    if (hasFn('showToast')) window.showToast('Pořadí vozidel bylo uloženo.', 'success');
    else if (hasFn('showAlert')) window.showAlert('Pořadí vozidel bylo uloženo.', 'success');
    reRenderCatalog();
  }

  function runIntent(intent, payload) {
    const data = payload || {};
    if (intent === 'vehicles:reorder') {
      STATE.viewOverride = 'vehicles';
      STATE.vehiclesManageHint = null;
      STATE.vehiclesReorderMode = true;
      initReorderDraftFromData(STATE.latestData || {});
      if (hasFn('switchTab')) return window.switchTab('vehicles');
      return render();
    }
    if (intent === 'vehicles:manage') {
      STATE.viewOverride = 'vehicles';
      STATE.vehiclesReorderMode = false;
      STATE.reorderDraftOrder = null;
      STATE.vehiclesManageHint = data.action === 'hide' ? 'hide' : 'delete';
      if (hasFn('switchTab')) return window.switchTab('vehicles');
      return render();
    }
    if (intent === 'vehicles:import') {
      STATE.viewOverride = 'vehicles';
      if (hasFn('switchTab')) return window.switchTab('vehicles', { expandVehiclesAdd: true });
      return render();
    }
    if (intent === 'documents:upload') {
      STATE.viewOverride = 'documents';
      if (hasFn('switchTab')) window.switchTab('documents');
      return runAction('documentsUpload', null, STATE.latestData || {});
    }
    if (intent === 'documents:folder' || intent === 'documents:organize') {
      STATE.viewOverride = 'documents';
      if (hasFn('switchTab')) window.switchTab('documents');
      return runAction('documentsOrganize', null, STATE.latestData || {});
    }
    if (intent === 'documents:categories') {
      STATE.viewOverride = 'documents';
      STATE.documentsFiltersOpen = true;
      if (hasFn('switchTab')) window.switchTab('documents');
      return render();
    }
    if (intent === 'documents:cleanup') {
      STATE.viewOverride = 'documents';
      if (hasFn('switchTab')) window.switchTab('documents');
      if (hasFn('showAlert')) window.showAlert('Projděte seznam dokumentů a odstraňte nepotřebné položky u jednotlivých vozidel.', 'info');
      return render();
    }
    if (intent === 'documents:trash') {
      STATE.viewOverride = 'documents';
      if (hasFn('switchTab')) window.switchTab('documents');
      if (hasFn('showAlert')) window.showAlert('Koš dokumentů není samostatná sekce — smazané položky spravujte v detailu vozidla / dokumentech.', 'info');
      return render();
    }
    if (intent === 'services:invites') {
      STATE.viewOverride = 'servicesDirectory';
      if (hasFn('switchTab')) return window.switchTab('servicesDirectory');
      return render();
    }
    return false;
  }

  function focusDashboardSearch() {
    const input = document.getElementById('uappNextSearch');
    if (!input) return;
    input.focus();
    if (typeof input.select === 'function') input.select();
  }

  function bindSearchShortcut() {
    if (document.documentElement.dataset.uappSearchShortcutBound === '1') return;
    document.documentElement.dataset.uappSearchShortcutBound = '1';
    document.addEventListener('keydown', (event) => {
      if (!(event.metaKey || event.ctrlKey) || String(event.key || '').toLowerCase() !== 'k') return;
      if (!shouldActivate() || getActiveView() === 'settings') return;
      const tag = String(event.target && event.target.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select' || (event.target && event.target.isContentEditable)) return;
      event.preventDefault();
      focusDashboardSearch();
    });
  }

  function bindSearch() {
    const input = document.getElementById('uappNextSearch');
    if (!input || input.dataset.uappBound === '1') return;
    input.dataset.uappBound = '1';
    if (STATE.vehiclesSearchQuery) input.value = STATE.vehiclesSearchQuery;
    input.addEventListener('input', () => {
      const q = input.value.trim().toLowerCase();
      STATE.vehiclesSearchQuery = q;
      if (getActiveView() === 'vehicles') {
        reRenderCatalog();
        return;
      }
      document.querySelectorAll('[data-uapp-vehicle-card]').forEach((card) => {
        const haystack = String(card.getAttribute('data-search-text') || '');
        card.style.display = !q || haystack.includes(q) ? '' : 'none';
      });
    });
  }

  function clickOriginal(selector) {
    const target = document.querySelector(selector);
    if (target && typeof target.click === 'function') {
      target.click();
      return true;
    }
    return false;
  }

  function legacyPanelAnchor(event) {
    return (event && event.currentTarget) || document.querySelector('.uapp-next-icon-btn[data-uapp-action="notifications"]') || document.querySelector('[data-testid="dashboard-profile"], .uapp-settings-profile-btn[data-uapp-action="profile"]');
  }

  function openNotificationsPanel(event) {
    preserveLegacyOverlays();
    if (hasFn('toggleAppNotificationsPanel')) {
      return window.toggleAppNotificationsPanel({
        currentTarget: legacyPanelAnchor(event),
        stopPropagation() {},
      });
    }
    return clickOriginal('#desktopNotificationsButton') || clickOriginal('#mobileNotificationsButton');
  }

  function openProfileMenu(event) {
    preserveLegacyOverlays();
    if (hasFn('toggleMobileProfileMenu')) return window.toggleMobileProfileMenu(event);
    return clickOriginal('#desktopProfileButton') || clickOriginal('#mobileProfileButton');
  }

  async function openVehicleDocuments(vehicleId) {
    const id = Number(vehicleId);
    if (!Number.isFinite(id) || id <= 0) return;
    await openUserVehicleDetailModal(id);
    return openDetailLegacyTab('documents', id);
  }

  async function openVehicleAccess(vehicleId) {
    const id = Number(vehicleId);
    if (!Number.isFinite(id) || id <= 0) return;
    await openUserVehicleDetailModal(id);
    return openDetailLegacyTab('access', id);
  }

  function openVehicleSection(vehicleId, section) {
    const id = Number(vehicleId);
    if (!Number.isFinite(id) || id <= 0) return;
    preserveLegacyOverlays();
    ensureLegacyDetailDom(id).then(() => {
      if (hasFn('openVehicleDetailFloatingSection')) {
        window.openVehicleDetailFloatingSection(section, id);
      }
    });
  }

  function suppressLegacyDetailModal() {
    const modal = document.getElementById('vehicleDetailModal');
    if (!modal) return;
    modal.classList.add('uapp-next-legacy-detail-suppressed');
    modal.style.display = 'none';
    modal.setAttribute('aria-hidden', 'true');
    if (typeof clearBodyScrollLocks === 'function') {
      try { clearBodyScrollLocks(); } catch (_) {}
    }
  }

  async function ensureLegacyDetailDom(vehicleId) {
    const id = Number(vehicleId);
    if (!Number.isFinite(id) || id <= 0) return;
    if (STATE.legacyDetailReadyFor === id) return;
    const loader = STATE.originalShowVehicleDetail;
    if (typeof loader !== 'function') return;
    await loader(id);
    suppressLegacyDetailModal();
    STATE.legacyDetailReadyFor = id;
  }

  function bindModalEsc() {
    if (STATE.modalEscBound) return;
    STATE.modalEscBound = true;
    document.addEventListener('keydown', (event) => {
      if (event.key !== 'Escape') return;
      const floatingRoot = document.getElementById('appFloatingModalRoot');
      if (floatingRoot && floatingRoot.innerHTML.trim()) {
        if (hasFn('closeVehicleDetailFloatingSection') && window.vehicleDetailFloatingSectionState?.sectionId) {
          event.preventDefault();
          event.stopPropagation();
          window.closeVehicleDetailFloatingSection();
          return;
        }
        if (hasFn('unmountFloatingModal')) {
          event.preventDefault();
          event.stopPropagation();
          window.unmountFloatingModal();
          return;
        }
      }
      if (STATE.detailModal.open) {
        if (STATE.detailModal.optionsOpen) {
          STATE.detailModal.optionsOpen = false;
          refreshDetailModalShell();
          return;
        }
        event.preventDefault();
        event.stopPropagation();
        closeUserVehicleDetailModal();
        return;
      }
      if (STATE.attentionModalOpen) {
        event.preventDefault();
        event.stopPropagation();
        closeAttentionModal();
      }
    }, true);
  }

  function closeUserVehicleDetailModal() {
    STATE.detailModal = { open: false, vehicleId: null, activeTab: 'tech', vehicle: null, records: [], optionsOpen: false };
    STATE.legacyDetailReadyFor = null;
    document.body.classList.remove('uapp-next-detail-open');
    const root = document.getElementById(DETAIL_MODAL_ID);
    if (root) root.remove();
    if (hasFn('closeVehicleModal')) {
      try { window.closeVehicleModal(); } catch (_) {}
    }
  }

  function detailSummaryCards(vehicle, records, data) {
    const id = Number(vehicle.id);
    const stk = stkFieldMeta(vehicle);
    const ins = insuranceFieldMeta(vehicle);
    const svc = lastServiceLabel(records);
    const km = vehicle.current_mileage_km != null && vehicle.current_mileage_km !== ''
      ? `${Number(vehicle.current_mileage_km).toLocaleString('cs-CZ')} km`
      : '—';
    const grants = (data?.accessGrants || []).filter((g) => Number(g.vehicle_id) === id);
    const pendingAccess = grants.filter((g) => {
      const st = String(g?.status || '').toLowerCase();
      return st.includes('pending') || st.includes('ček') || st.includes('wait');
    }).length;
    const stkDate = getStkValue(vehicle) ? formatDate(getStkValue(vehicle)) : 'Nezadáno';
    const insDate = vehicle.insurance_valid_until ? formatDate(vehicle.insurance_valid_until) : 'Nezadáno';
    const latestRecord = (records || []).slice().sort((a, b) => (Date.parse(b?.performed_at || b?.created_at) || 0) - (Date.parse(a?.performed_at || a?.created_at) || 0))[0];
    const svcDate = latestRecord ? formatDate(latestRecord.performed_at || latestRecord.created_at) : 'Bez záznamu';
    return [
      { key: 'stk', tone: stk.tone, icon: '◷', title: 'STK / SME', value: stk.label, sub: stkDate, action: `detailTab:ops:${id}` },
      { key: 'ins', tone: ins.tone, icon: '⛨', title: 'Pojištění', value: ins.label, sub: insDate, action: `detailTab:ops:${id}` },
      { key: 'km', tone: 'ok', icon: '◔', title: 'Nájezd', value: km, sub: 'Aktuální stav tachometru', action: `detailTab:ops:${id}` },
      { key: 'svc', tone: svc.tone, icon: '⚙', title: 'Poslední servis', value: svc.label, sub: svcDate, action: `detailTab:service:${id}` },
      { key: 'docs', tone: records.length ? 'ok' : 'warn', icon: '▣', title: 'Dokumenty', value: String(records.length || '0'), sub: records.length ? 'Servisní záznamy a přílohy' : 'Bez příloh', action: `detailTab:documents:${id}` },
      { key: 'access', tone: pendingAccess ? 'warn' : 'ok', icon: '👥', title: 'Přístupy servisů', value: String(grants.length), sub: pendingAccess ? `${pendingAccess} čeká na schválení` : 'Aktivní servisní přístupy', action: `detailTab:access:${id}` },
    ];
  }

  function detailTimelineRows(records) {
    const sorted = (records || []).slice().sort((a, b) => (Date.parse(b?.performed_at || b?.created_at) || 0) - (Date.parse(a?.performed_at || a?.created_at) || 0));
    return sorted.slice(0, 6).map((record) => {
      const meta = serviceRecordStatusMeta(record);
      const iconClass = serviceRecordIconClass(record);
      return {
        title: record.description || record.service_type || 'Servisní záznam',
        when: formatDateTime(record.performed_at || record.created_at),
        detail: formatMoneyCzk(record?.total_price ?? record?.price),
        tone: meta.tone,
        iconClass,
        statusLabel: meta.label,
      };
    });
  }

  function vehicleIdentificationVerified(vehicle) {
    return Boolean(String(vehicle?.vin || '').trim() && String(vehicle?.plate || '').trim());
  }

  function detailReminderRows(data, vehicleId) {
    return (data?.reminders || [])
      .filter((item) => !item?.is_completed && Number(item?.vehicle_id) === Number(vehicleId))
      .slice(0, 4)
      .map((item) => {
        const diff = daysUntil(item.due_date || item.notify_at);
        let value = formatDate(item.due_date || item.notify_at);
        if (diff != null && diff >= 0 && diff <= 120) {
          value = diff === 0 ? 'dnes' : (diff === 1 ? 'zítra' : `za ${diff} dnů`);
        }
        return { title: item.text || item.title || item.type || 'Připomínka', value };
      });
  }

  function renderDetailTechTab(vehicle) {
    const rows = [
      ['Značka', vehicle.brand || '—'],
      ['Typ / model', [vehicle.brand, vehicle.model].filter(Boolean).join(' ') || '—'],
      ['VIN', vehicle.vin || '—'],
      ['SPZ', vehicle.plate || '—'],
      ['Barva', vehicle.color || '—'],
      ['Emisní norma', vehicle.emission_norm || vehicle.emission_class || '—'],
      ['Palivo', vehicleFuelLabel(vehicle)],
      ['Objem', vehicleVolumeLabel(vehicle)],
      ['Výkon', vehiclePowerLabel(vehicle)],
      ['Převodovka', vehicle.transmission || '—'],
      ['Rok výroby', vehicle.year || '—'],
      ['Motor', vehicle.engine || '—'],
    ];
    const notes = String(vehicle.notes || '').trim();
    return `
      <div class="uapp-next-detail-tab-grid">
        <section class="uapp-next-detail-panel">
          <h3 class="uapp-next-detail-panel-title">Základní informace</h3>
          <dl class="uapp-next-detail-spec">
            ${rows.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(String(v))}</dd></div>`).join('')}
          </dl>
        </section>
        <section class="uapp-next-detail-panel">
          <h3 class="uapp-next-detail-panel-title">Identifikace vozidla</h3>
          <div class="uapp-next-detail-id-box">
            <ul class="uapp-next-detail-id-list">
              <li class="${vehicle.vin ? 'is-ok' : 'is-muted'}">${vehicle.vin ? '✓' : '○'} VIN ${vehicle.vin ? 'evidován' : 'neuveden'}</li>
              <li class="${vehicle.plate ? 'is-ok' : 'is-muted'}">${vehicle.plate ? '✓' : '○'} SPZ ${vehicle.plate ? 'evidována' : 'neuvedena'}</li>
              <li class="${vehicle.stk_valid_until ? 'is-ok' : 'is-muted'}">${vehicle.stk_valid_until ? '✓' : '○'} STK ${vehicle.stk_valid_until ? 'evidována' : 'neuvedena'}</li>
            </ul>
            ${hasFn('previewVehicleVerifiedReportFromHub') ? `<button type="button" class="uapp-next-btn uapp-next-btn-secondary uapp-next-detail-id-btn" data-uapp-action="detailVerifiedPdf:${Number(vehicle.id)}">Digitální výpis</button>` : ''}
          </div>
        </section>
      </div>
      <section class="uapp-next-detail-note">
        <div class="uapp-next-detail-note-head">
          <h3 class="uapp-next-detail-panel-title">Poznámka k vozidlu</h3>
        </div>
        <p>${esc(notes || '—')}</p>
      </section>`;
  }

  function renderDetailOptionsMenu(vehicleId) {
    const id = Number(vehicleId);
    const items = [];
    if (hasFn('openAddServiceRecordModal')) items.push([`addRecord:${id}`, 'Přidat servisní záznam']);
    items.push([`detailTab:documents:${id}`, 'Nahrát dokument']);
    items.push([`detailTab:access:${id}`, 'Sdílet se servisem']);
    items.push([`detailTab:ops:${id}`, 'Připomínky a STK']);
    items.push([`detailTab:gallery:${id}`, 'Fotogalerie a QR']);
    if (hasFn('previewVehicleReportFromHub')) items.push([`detailPdf:${id}`, 'Náhled PDF report']);
    if (hasFn('refreshExistingVehicleFromVin')) items.push([`detailVinRefresh:${id}`, 'Obnovit údaje z VIN']);
    return items.map(([action, label]) => (
      `<button type="button" class="uapp-next-detail-options-item" data-uapp-action="${esc(action)}">${esc(label)}</button>`
    )).join('');
  }

  function refreshDetailModalShell() {
    if (!STATE.detailModal.open || !STATE.detailModal.vehicle) return;
    mountDetailModalShell(renderDetailModalContent(
      STATE.detailModal.vehicle,
      STATE.detailModal.records,
      STATE.latestData || {},
    ));
    const img = document.getElementById(`uappNextDetailPhoto-${Number(STATE.detailModal.vehicleId)}`);
    if (img) hydrateImageForVehicle(STATE.detailModal.vehicle, img, `uapp-next-detail:${STATE.detailModal.vehicleId}`);
  }

  function closeDetailOptionsMenu() {
    if (!STATE.detailModal.optionsOpen) return;
    STATE.detailModal.optionsOpen = false;
    refreshDetailModalShell();
  }

  function renderDetailModalContent(vehicle, records, data) {
    const id = Number(vehicle.id);
    const status = getCatalogVehicleStatus(vehicle, records);
    const tabs = [
      ['tech', 'Technické údaje'],
      ['service', 'Servisní historie'],
      ['documents', 'Dokumenty'],
      ['gallery', 'Fotogalerie'],
      ['reminders', 'Připomínky'],
      ['access', 'Přístupy a sdílení'],
    ];
    const summary = detailSummaryCards(vehicle, records, data);
    const timeline = detailTimelineRows(records);
    const upcoming = detailReminderRows(data, id);
    const activeTab = STATE.detailModal.activeTab || 'tech';
    const optionsOpen = Boolean(STATE.detailModal.optionsOpen);

    return `
      <div class="uapp-next-detail-modal" role="dialog" aria-modal="true" aria-labelledby="uappNextDetailTitle">
        <button type="button" class="uapp-next-detail-close" data-uapp-action="detailClose" aria-label="Zavřít detail">×</button>
        <div class="uapp-next-detail-scroll">
          <nav class="uapp-next-detail-crumb" aria-label="Drobečková navigace">
            <button type="button" class="uapp-next-link-btn" data-uapp-action="vehicles">Moje vozidla</button>
            <span aria-hidden="true">/</span>
            <span>Detail vozidla</span>
          </nav>
          <section class="uapp-next-detail-hero">
            <div class="uapp-next-detail-photo">
              <div class="uapp-next-photo" data-next-photo-wrap="detail-${id}">
                <img id="uappNextDetailPhoto-${id}" alt="Fotka vozidla ${esc(getVehicleName(vehicle))}" loading="lazy">
                <div class="uapp-next-photo-fallback">Bez fotky</div>
              </div>
            </div>
            <div class="uapp-next-detail-hero-body">
              <div class="uapp-next-detail-hero-top">
                <h2 id="uappNextDetailTitle" class="uapp-next-detail-title">${esc(getVehicleName(vehicle))}</h2>
                <div class="uapp-next-detail-menu-wrap">
                  <button type="button" class="uapp-next-detail-menu${optionsOpen ? ' is-open' : ''}" data-uapp-action="detailOptionsToggle:${id}" aria-label="Možnosti vozidla" aria-expanded="${optionsOpen}" aria-haspopup="menu">⋯</button>
                  ${optionsOpen ? `<div class="uapp-next-detail-options" role="menu">${renderDetailOptionsMenu(id)}</div>` : ''}
                </div>
              </div>
              <div class="uapp-next-detail-hero-meta">
                ${renderPlateBadge(vehicle.plate, 'lg')}
                <span class="${catalogBadgeClass(status.tone)}">${esc(status.label)}</span>
              </div>
              <dl class="uapp-next-detail-metrics-inline">
                <div><dt>VIN</dt><dd>${esc(vehicle.vin || '—')}</dd></div>
                <div><dt>Rok výroby</dt><dd>${esc(vehicle.year || '—')}</dd></div>
                <div><dt>Palivo</dt><dd>${esc(vehicleFuelLabel(vehicle))}</dd></div>
                <div><dt>Výkon</dt><dd>${esc(vehiclePowerLabel(vehicle))}</dd></div>
                <div><dt>Objem</dt><dd>${esc(vehicleVolumeLabel(vehicle))}</dd></div>
              </dl>
              <div class="uapp-next-detail-hero-actions">
                ${hasFn('openAddServiceRecordModal') ? `<button type="button" class="uapp-next-btn uapp-next-btn-primary" data-uapp-action="addRecord:${id}">+ <span>Přidat záznam</span></button>` : ''}
                <button type="button" class="uapp-next-btn uapp-next-btn-secondary" data-uapp-action="detailTab:documents:${id}">${ICO.upload}<span>Nahrát dokument</span></button>
                <button type="button" class="uapp-next-btn uapp-next-btn-secondary" data-uapp-action="detailTab:access:${id}">${ICO.share}<span>Sdílet se servisem</span></button>
              </div>
            </div>
          </section>
          <div class="uapp-next-detail-summary-grid">
            ${summary.map((card) => `
              <article class="uapp-next-detail-summary-card is-${esc(card.tone)}">
                <div class="uapp-next-detail-summary-ico" aria-hidden="true">${card.icon}</div>
                <div>
                  <span class="uapp-next-detail-summary-k">${esc(card.title)}</span>
                  <strong>${esc(card.value)}</strong>
                  <span class="uapp-next-detail-summary-sub">${esc(card.sub)}</span>
                  ${card.action ? `<button type="button" class="uapp-next-detail-summary-link" data-uapp-action="${esc(card.action)}">Zobrazit ›</button>` : ''}
                </div>
              </article>`).join('')}
          </div>
          <div class="uapp-next-detail-body">
            <div class="uapp-next-detail-main">
              <div class="uapp-next-detail-tabs" role="tablist" aria-label="Sekce detailu vozidla">
                ${tabs.map(([key, label]) => `<button type="button" role="tab" class="uapp-next-detail-tab${activeTab === key ? ' is-active' : ''}" data-uapp-action="detailTab:${key}:${id}" aria-selected="${activeTab === key}">${esc(label)}</button>`).join('')}
              </div>
              <div class="uapp-next-detail-tab-content">
                ${activeTab === 'tech' ? renderDetailTechTab(vehicle) : `<div class="uapp-next-detail-tab-placeholder"><p>Obsah sekce se otevře v plné verzi detailu.</p><button type="button" class="uapp-next-btn uapp-next-btn-primary" data-uapp-action="detailTab:${activeTab}:${id}">Otevřít ${esc(tabs.find((t) => t[0] === activeTab)?.[1] || 'sekci')}</button></div>`}
              </div>
            </div>
            <aside class="uapp-next-detail-aside">
              <section class="uapp-next-detail-aside-card">
                <h3>Časová osa vozidla</h3>
                ${timeline.length ? timeline.map((row) => `
                  <div class="uapp-next-detail-timeline-item is-${row.tone}">
                    <strong>${esc(row.title)}</strong>
                    <span>${esc(row.when)}</span>
                  </div>`).join('') : '<p class="uapp-next-detail-empty">Zatím bez záznamů.</p>'}
              </section>
              <section class="uapp-next-detail-aside-card">
                <h3>Nejbližší termíny</h3>
                ${upcoming.length ? upcoming.map((row) => `
                  <div class="uapp-next-detail-upcoming-item">
                    <strong>${esc(row.title)}</strong>
                    <span>${esc(row.value)}</span>
                  </div>`).join('') : '<p class="uapp-next-detail-empty">Žádné blížící se termíny.</p>'}
              </section>
              <section class="uapp-next-detail-aside-card">
                <h3>Rychlé akce</h3>
                <div class="uapp-next-detail-quick">
                  ${hasFn('openAddServiceRecordModal') ? `<button type="button" data-uapp-action="addRecord:${id}">+ Přidat servisní úkon</button>` : ''}
                  <button type="button" data-uapp-action="detailTab:ops:${id}">+ Přidat záznam tachometru</button>
                  <button type="button" data-uapp-action="detailTab:documents:${id}">Nahrát dokument</button>
                  ${hasFn('previewVehicleReportFromHub') ? `<button type="button" data-uapp-action="detailPdf:${id}">Náhled PDF report</button>` : ''}
                  ${hasFn('openVehicleDetailFloatingSection') ? `<button type="button" data-uapp-action="detailTab:gallery:${id}">Generovat QR historii</button>` : ''}
                </div>
              </section>
            </aside>
          </div>
        </div>
      </div>`;
  }

  function mountDetailModalShell(html) {
    let backdrop = document.getElementById(DETAIL_MODAL_ID);
    if (!backdrop) {
      backdrop = document.createElement('div');
      backdrop.id = DETAIL_MODAL_ID;
      backdrop.className = 'uapp-next-detail-backdrop';
      backdrop.setAttribute('data-testid', 'user-app-next-vehicle-detail');
      document.body.appendChild(backdrop);
    }
    backdrop.innerHTML = `<div class="uapp-next-detail-backdrop-inner">${html}</div>`;
    backdrop.onclick = (event) => {
      if (event.target === backdrop || event.target.classList.contains('uapp-next-detail-backdrop-inner')) {
        closeUserVehicleDetailModal();
      }
    };
  }

  async function openUserVehicleDetailModal(vehicleId) {
    const id = Number(vehicleId);
    if (!Number.isFinite(id) || id <= 0) return;
    bindModalEsc();
    STATE.detailModal = { open: true, vehicleId: id, activeTab: 'tech', vehicle: null, records: [], optionsOpen: false };
    document.body.classList.add('uapp-next-detail-open');
    mountDetailModalShell('<div class="uapp-next-loading">Načítám detail vozidla…</div>');

    let vehicle = (STATE.latestData?.vehicles || []).find((v) => Number(v.id) === id) || null;
    let records = recordsFor(STATE.latestData || {}, id);
    if (apiReady()) {
      vehicle = await safeApi(`/api/v1/vehicles/${id}`, vehicle);
      records = await safeApi(`/api/v1/vehicles/${id}/records`, records);
    }

    if (!vehicle) {
      mountDetailModalShell('<div class="uapp-next-empty">Vozidlo se nepodařilo načíst.</div>');
      return;
    }

    STATE.detailModal.vehicle = vehicle;
    STATE.detailModal.records = Array.isArray(records) ? records : [];
    const data = STATE.latestData || { vehicles: [vehicle], reminders: [], accessGrants: [], recordEntries: [{ vehicle, records: STATE.detailModal.records }] };
    mountDetailModalShell(renderDetailModalContent(vehicle, STATE.detailModal.records, data));
    void ensureLegacyDetailDom(id);
    const img = document.getElementById(`uappNextDetailPhoto-${id}`);
    if (img) hydrateImageForVehicle(vehicle, img, `uapp-next-detail:${id}`);
  }

  function openDetailLegacyTab(tabKey, vehicleId) {
    const id = Number(vehicleId);
    const map = { tech: 'basic', service: 'service', documents: 'documents', gallery: 'gallery', reminders: 'ops', access: 'access', ops: 'ops' };
    const section = map[String(tabKey || '').toLowerCase()] || 'basic';
    if (section === 'basic') {
      STATE.detailModal.activeTab = 'tech';
      if (STATE.detailModal.vehicle) {
        mountDetailModalShell(renderDetailModalContent(STATE.detailModal.vehicle, STATE.detailModal.records, STATE.latestData || {}));
        const img = document.getElementById(`uappNextDetailPhoto-${id}`);
        if (img) hydrateImageForVehicle(STATE.detailModal.vehicle, img, `uapp-next-detail:${id}`);
      }
      return;
    }
    ensureLegacyDetailDom(id).then(() => {
      if (hasFn('openVehicleDetailFloatingSection')) {
        window.openVehicleDetailFloatingSection(section, id);
      }
    });
  }

  function runAction(action, event) {
    const [name, rawId] = String(action || '').split(':');
    const id = Number(rawId || 0);
    if (name === 'detailOptionsToggle' && id) {
      STATE.detailModal.optionsOpen = !STATE.detailModal.optionsOpen;
      refreshDetailModalShell();
      return;
    }
    if (STATE.detailModal.open && STATE.detailModal.optionsOpen) {
      STATE.detailModal.optionsOpen = false;
      refreshDetailModalShell();
    }
    if (name === 'mobileNav') return toggleMobileNav();
    if (name === 'mobileNavClose') return closeMobileNav();
    if (name === 'home' && hasFn('switchTab')) { closeMobileNav(); STATE.viewOverride = null; return window.switchTab('home'); }
    if (name === 'vehicles' && hasFn('switchTab')) { closeMobileNav(); STATE.viewOverride = null; return window.switchTab('vehicles'); }
    if (name === 'reminders' && hasFn('switchTab')) { closeMobileNav(); STATE.viewOverride = null; return window.switchTab('reminders'); }
    if (name === 'reservations') return navigateLicensedTab('reservations', 'reservations');
    if (name === 'documents') return navigateLicensedTab('documents', 'documents');
    if (name === 'servicesDirectory') return navigateLicensedTab('servicesDirectory', 'servicesDirectory');
    if (name === 'support') {
      closeMobileNav();
      STATE.viewOverride = 'settings';
      if (hasFn('setSettingsPanelRoute')) window.setSettingsPanelRoute('support');
      if (hasFn('switchTab')) return window.switchTab('account');
      return render();
    }
    if (name === 'settings' || name === 'account') {
      closeMobileNav();
      STATE.viewOverride = 'settings';
      if (hasFn('setSettingsPanelRoute')) window.setSettingsPanelRoute('profile', { replace: name === 'settings' });
      if (hasFn('switchTab')) return window.switchTab('account');
      return render();
    }
    if (name === 'invoices') {
      if (!USER_INVOICES_ENABLED) return null;
      closeMobileNav();
      STATE.viewOverride = 'invoices';
      if (hasFn('switchTab')) return window.switchTab('invoices');
      return render();
    }
    if (name === 'serviceHistory') {
      closeMobileNav();
      STATE.viewOverride = 'serviceHistory';
      if (hasFn('switchTab')) {
        try { window.switchTab('serviceHistory', { skipUnsavedGuard: true }); } catch (_) {}
      }
      if (hasFn('syncUserTabUrlHistory')) {
        try { window.syncUserTabUrlHistory('serviceHistory'); } catch (_) {}
      }
      return render();
    }
    if (name === 'documentsUpload') return openDocumentsUploadFlow(STATE.latestData || {});
    if (name === 'documentsUploadPickerClose') { STATE.documentsUploadPickerOpen = false; return render(); }
    if (name === 'documentsUploadTo' && id) {
      STATE.documentsUploadPickerOpen = false;
      return openVehicleDocuments(id);
    }
    if (name === 'documentsTipClose') { STATE.documentsTipHidden = true; return render(); }
    if (name === 'documentsFiltersToggle') {
      const input = document.querySelector('[data-uapp-doc-filter="search"]');
      if (input) input.focus();
      return;
    }
    if (name === 'documentsResetFilters') {
      STATE.documentsFilters = { search: '', category: 'all', type: 'all', vehicle: 'all' };
      STATE.documentsPage = 1;
      return render();
    }
    if (name === 'documentsSortToggle') {
      const sort = STATE.documentsSort || { key: 'uploadedAt', dir: 'desc' };
      STATE.documentsSort = { key: 'uploadedAt', dir: sort.dir === 'desc' ? 'asc' : 'desc' };
      return render();
    }
    if (name === 'documentsPage' && rawId) {
      STATE.documentsPage = Number(rawId) || 1;
      STATE.documentsMenuOpenId = null;
      return render();
    }
    if (name === 'documentsPagePrev') {
      STATE.documentsPage = Math.max(1, (Number(STATE.documentsPage) || 1) - 1);
      STATE.documentsMenuOpenId = null;
      return render();
    }
    if (name === 'documentsPageNext') {
      STATE.documentsPage = (Number(STATE.documentsPage) || 1) + 1;
      STATE.documentsMenuOpenId = null;
      return render();
    }
    if (name === 'docMenuToggle') {
      const rowId = decodeURIComponent(String(rawId || ''));
      STATE.documentsMenuOpenId = STATE.documentsMenuOpenId === rowId ? null : rowId;
      return render();
    }
    if (name === 'docPreview') {
      const payload = String(action || '').includes(':')
        ? String(action).slice(String(action).indexOf(':') + 1)
        : '';
      return openDocumentPreviewFromParts(payload);
    }
    if (name === 'docDownload') {
      const parts = String(action || '').split(':');
      const kind = parts[1];
      const vehicleId = Number(parts[2] || 0);
      const downloadUrl = decodeURIComponent(parts.slice(3).join(':') || '');
      if (kind === 'attachment' && downloadUrl) {
        return openDocumentPreviewFromParts(`attachment:${vehicleId}:${encodeURIComponent(downloadUrl)}:doklad`);
      }
      if (kind === 'report' && vehicleId) {
        return openDocumentPreviewFromParts(`report:${vehicleId}`);
      }
      if (kind === 'verified_report' && vehicleId) {
        return openDocumentPreviewFromParts(`verified_report:${vehicleId}`);
      }
      if (kind === 'technical_cert' && vehicleId) {
        return openDocumentPreviewFromParts(`technical_cert:${vehicleId}`);
      }
      if (kind === 'tachometer' && vehicleId) return openVehicleDocuments(vehicleId);
      return;
    }
    if (name === 'docVerify') {
      const verifyUrl = decodeURIComponent(String(action || '').split(':').slice(1).join(':') || '');
      if (verifyUrl && hasFn('openDocumentsVerifyPage')) return window.openDocumentsVerifyPage(verifyUrl);
      return;
    }
    if (name === 'docTachometerDetail') {
      const parts = String(action || '').split(':');
      const detailUrl = decodeURIComponent(parts[1] || '');
      const vehicleId = Number(parts[2] || 0);
      if (detailUrl && detailUrl.startsWith('/')) {
        window.location.href = detailUrl;
        return;
      }
      if (vehicleId) return openVehicleDocuments(vehicleId);
      return;
    }
    if (name === 'documentsExport') {
      const rows = sortDocumentsRows(filterDocumentsRows(buildDocumentsRows(STATE.latestData || {}), STATE.latestData || {}));
      return exportDocumentsCsv(rows);
    }
    if (name === 'documentsOrganize') {
      const vehicles = STATE.latestData?.vehicles || [];
      if (vehicles.length === 1) return openVehicleDocuments(Number(vehicles[0].id));
      if (vehicles.length > 1) {
        STATE.documentsUploadPickerOpen = true;
        return render();
      }
      if (hasFn('openAddVehicleModal')) return window.openAddVehicleModal();
      return;
    }
    if (name === 'documentsManageStorage') {
      if (hasFn('switchTab')) {
        STATE.viewOverride = null;
        window.switchTab('account');
        window.setTimeout(() => {
          if (hasFn('setSettingsPanel')) window.setSettingsPanel('data');
        }, 120);
      }
      return;
    }
    if (name === 'servicesView') {
      STATE.servicesDirectoryView = rawId === 'list' ? 'list' : 'map';
      return render();
    }
    if (name === 'servicesLoadMore') {
      STATE.servicesDirectoryLimit = (Number(STATE.servicesDirectoryLimit) || 10) + 10;
      return render();
    }
    if (name === 'servicesTipClose') {
      STATE.servicesDirectoryTipHidden = true;
      return render();
    }
    if (name === 'servicesMapControlsToggle') {
      STATE.servicesMapControlsOpen = !STATE.servicesMapControlsOpen;
      const wrap = document.querySelector('.uapp-svc-map-controls-wrap');
      const btn = document.querySelector('.uapp-svc-map-controls-toggle');
      if (wrap) wrap.classList.toggle('is-open', STATE.servicesMapControlsOpen);
      if (btn) btn.setAttribute('aria-expanded', STATE.servicesMapControlsOpen ? 'true' : 'false');
      return;
    }
    if (name === 'servicesRefreshLocation') {
      openServicesLocationModal();
      return;
    }
    if (name === 'servicesLocationClose') {
      closeServicesLocationModal();
      return;
    }
    if (name === 'servicesLocationUseGps') {
      void applyServicesLocationFromGps();
      return;
    }
    if (name === 'servicesLocationPick' && rawId !== undefined && rawId !== '') {
      const modal = document.getElementById('uappSvcLocationModal');
      const items = modal?._suggestions || [];
      const idx = Number(rawId);
      const item = items[idx];
      if (item) void applyServicesLocationFromItem(item);
      return;
    }
    if (name === 'servicesMapCategory') {
      const nextCategory = rawId || 'all';
      STATE.servicesMapCategory = nextCategory;
      STATE.servicesMapVerifiedOnly = nextCategory === 'verified';
      STATE.servicesMapBounds = null;
      STATE.servicesOsmRows = [];
      STATE.servicesMapRows = [];
      document.querySelectorAll('.uapp-svc-chip[data-uapp-action^="servicesMapCategory:"]').forEach((btn) => {
        const chipKey = (btn.getAttribute('data-uapp-action') || '').split(':')[1] || 'all';
        btn.classList.toggle('is-active', chipKey === nextCategory);
      });
      void loadServicesOsmData({ skipRender: true }).then(() => {
        if (STATE.latestData) patchServicesDirectoryList(STATE.latestData);
      });
      return;
    }
    if (name === 'serviceMapReport' && id) {
      const reportType = window.prompt('Typ hlášení: wrong_phone, closed, duplicate, fake, wrong_category, wrong_location', 'wrong_category');
      if (!reportType) return;
      const reportText = window.prompt('Popis problému (volitelné):', '') || '';
      if (!apiReady()) return window.alert('Nejste přihlášeni.');
      void apiCall(`/api/v1/service-map/locations/${encodeURIComponent(String(id))}/report`, 'POST', {
        report_type: reportType,
        report_text: reportText,
      }).then(() => {
        if (hasFn('showToast')) window.showToast('Hlášení odesláno. Děkujeme.', 'success');
        else window.alert('Hlášení odesláno. Děkujeme.');
      }).catch((err) => {
        window.alert(String(err?.message || err || 'Hlášení se nepodařilo odeslat.'));
      });
      return;
    }
    if (name === 'servicesRating' && rawId) {
      STATE.servicesDirectoryFilters = STATE.servicesDirectoryFilters || {};
      const current = Number(STATE.servicesDirectoryFilters.rating || 0);
      const next = Number(rawId);
      STATE.servicesDirectoryFilters.rating = current === next ? '0' : String(next);
      STATE.servicesDirectoryLimit = 30;
      return render();
    }
    if (name === 'serviceOsmClose') {
      const modal = document.getElementById('uappSvcExternalModal');
      if (modal) modal.remove();
      return;
    }
    if (name === 'serviceOsmDetail' && rawId) {
      const latest = STATE.latestData || {};
      const key = decodeURIComponent(String(rawId));
      const service = buildMergedServiceCatalog(latest).find((row) => row.row_key === key || String(row.osm_id) === key || String(row.location_id) === key.replace(/^map-/, ''));
      if (service) return openExternalServiceDetailModal(service);
      return;
    }
    if (name === 'serviceDetail' && id) {
      if (hasFn('openServicePartnerDetailModal')) {
        const latest = STATE.latestData || {};
        if (window.servicesDirectoryState && latest.servicesDiscovery) {
          window.servicesDirectoryState.payload = {
            services: buildMergedServiceCatalog(latest).filter((row) => row.in_app),
            meta: latest.servicesDiscovery.meta || {},
            userVehicles: latest.vehicles || [],
            vehicleAccessGrants: latest.accessGrants || [],
            vehicleAccessApiAvailable: true,
          };
        }
        return window.openServicePartnerDetailModal(id);
      }
      return;
    }
    if (name === 'servicesConnect') {
      const email = window.prompt('Zadejte e-mail servisu pro propojení účtů:');
      if (!email) return;
      if (!apiReady()) return;
      return apiCall('/api/v1/services/connect-by-email', 'POST', { service_email: String(email).trim() })
        .then(() => render())
        .catch((err) => console.warn('[USER_APP_NEXT] connect service failed', err));
    }
    if (name === 'serviceHistoryAdd') {
      if (hasFn('openAddServiceRecordModal')) return window.openAddServiceRecordModal();
      return;
    }
    if (name === 'loadMoreServiceHistory') {
      STATE.serviceHistoryLimit = (STATE.serviceHistoryLimit || 8) + 8;
      return render();
    }
    if (name === 'serviceHistoryResetFilters') {
      STATE.serviceHistoryFilters = { vehicle: 'all', period: '2y', type: 'all', service: 'all', docStatus: 'all' };
      STATE.serviceHistoryLimit = 8;
      return render();
    }
    if (name === 'serviceRecordDetail' && id) return openUserVehicleDetailModal(id);
    if (name === 'serviceRecordEdit') {
      const parts = String(action || '').split(':');
      const vehicleId = Number(parts[1] || 0);
      const recordId = Number(parts[2] || 0);
      if (vehicleId && recordId && hasFn('openEditServiceRecordModal')) {
        return window.openEditServiceRecordModal(recordId, vehicleId);
      }
      return;
    }
    if (name === 'newReminder') {
      if (hasFn('showCreateReminderForm')) return window.showCreateReminderForm();
      return;
    }
    if (name === 'reminderComplete' && id && apiReady()) {
      return apiCall(`/api/v1/reminders/${id}`, 'PUT', { is_completed: true })
        .then(() => render())
        .catch((err) => console.warn('[USER_APP_NEXT] reminder complete failed', err));
    }
    if (name === 'reminderDetail' && id && hasFn('editReminder')) return window.editReminder(id);
    if (name === 'reminderSnooze' && id && hasFn('editReminder')) return window.editReminder(id);
    if (name === 'remindersTipClose') { STATE.remindersTipHidden = true; return render(); }
    if (name === 'help') {
      if (hasFn('openHowToHubModal')) return window.openHowToHubModal();
      closeMobileNav();
      STATE.viewOverride = 'settings';
      if (hasFn('setSettingsPanelRoute')) window.setSettingsPanelRoute('support');
      if (hasFn('switchTab')) return window.switchTab('account');
      return render();
    }
    if (name === 'collapse') return document.body.classList.toggle('user-app-next-sidebar-collapsed');
    if (name === 'addVehicle') {
      if (hasFn('openAddVehicleModal')) return window.openAddVehicleModal();
      return clickOriginal('#btnOpenAddVehicleModal');
    }
    if (name === 'notifications') return openNotificationsPanel(event);
    if (name === 'profile') return openProfileMenu(event);
    if (name === 'detail' && id) return openUserVehicleDetailModal(id);
    if (name === 'addRecord' && id) {
      if (hasFn('openAddServiceRecordModal')) return window.openAddServiceRecordModal(id);
      console.warn('[USER_APP_NEXT] BLOCKER: openAddServiceRecordModal missing');
      return;
    }
    if (name === 'documentsVehicle' && id) return openVehicleDocuments(id);
    if (name === 'shareVehicle' && id) return openVehicleAccess(id);
    if (name === 'attentionOpen') return openAttentionModal();
    if (name === 'attentionClose') return closeAttentionModal();
    if (name === 'attentionAllVehicles') {
      closeAttentionModal();
      if (hasFn('switchTab')) return window.switchTab('vehicles');
    }
    if (name === 'attentionResolve') {
      const idx = Number(rawId);
      const item = STATE.attentionItems[idx];
      if (!item?.action) return;
      closeAttentionModal();
      return runAction(item.action, event);
    }
    if (name === 'detailClose') return closeUserVehicleDetailModal();
    if (name === 'detailEdit' && id) {
      if (STATE.detailModal.open) {
        STATE.detailModal.activeTab = 'tech';
        refreshDetailModalShell();
        return;
      }
      return ensureLegacyDetailDom(id).then(() => {
        if (hasFn('openVehicleDetailFloatingSection')) window.openVehicleDetailFloatingSection('basic', id);
        else if (hasFn('startEditModal')) window.startEditModal('nickname', id);
      });
    }
    if (name === 'detailVinRefresh' && id && hasFn('refreshExistingVehicleFromVin')) {
      return window.refreshExistingVehicleFromVin(id);
    }
    if (name === 'detailTab') {
      const parts = String(action || '').split(':');
      const tabKey = parts[1];
      const vid = Number(parts[2] || 0);
      if (tabKey && vid) {
        if (tabKey === 'tech') {
          STATE.detailModal.activeTab = 'tech';
          if (STATE.detailModal.vehicle) {
            mountDetailModalShell(renderDetailModalContent(STATE.detailModal.vehicle, STATE.detailModal.records, STATE.latestData || {}));
          }
          return;
        }
        STATE.detailModal.activeTab = tabKey;
        return openDetailLegacyTab(tabKey, vid);
      }
    }
    if (name === 'detailPdf' && id && hasFn('previewVehicleReportFromHub')) return window.previewVehicleReportFromHub(id);
    if (name === 'detailVerifiedPdf' && id && hasFn('previewVehicleVerifiedReportFromHub')) return window.previewVehicleVerifiedReportFromHub(id);
    if (name === 'detailQrOpen' && id) return openDetailLegacyTab('gallery', id);
    if (name === 'vehiclesReorderStart') {
      STATE.vehiclesReorderMode = true;
      STATE.vehiclesManageHint = null;
      initReorderDraftFromData(STATE.latestData || {});
      return reRenderCatalog();
    }
    if (name === 'vehiclesManageHintClose') {
      STATE.vehiclesManageHint = null;
      return reRenderCatalog();
    }
    if (name === 'vehicleReorderCancel') {
      STATE.vehiclesReorderMode = false;
      STATE.reorderDraftOrder = null;
      return reRenderCatalog();
    }
    if (name === 'vehicleReorderSave') {
      void saveVehicleOrderDraft().catch((err) => {
        window.alert(String(err?.message || err || 'Uložení pořadí selhalo.'));
      });
      return;
    }
    if (name === 'vehicleReorderUp' && id) return moveReorderDraftItem(id, -1);
    if (name === 'vehicleReorderDown' && id) return moveReorderDraftItem(id, 1);
    if (name === 'filter') {
      const key = String(rawId || 'all');
      if (['all', 'ok', 'attention', 'service', 'archived'].includes(key)) {
        STATE.vehiclesFilter = key;
        reRenderCatalog();
      }
      return;
    }
    if (name === 'viewMode') {
      setStoredViewMode(rawId === 'list' ? 'list' : 'grid');
      reRenderCatalog();
      return;
    }
    console.warn('[USER_APP_NEXT] BLOCKER: handler not found for action', action);
  }

  async function render() {
    if (!shouldActivate()) {
      setActiveClass(false);
      return;
    }
    const token = ++STATE.renderToken;
    setActiveClass(true);
    preserveLegacyOverlays();
    const view = getActiveView() || 'home';
    const root = ensureUserAppScreenRoot();
    const needsLoadingShell = root && (!root.querySelector('.uapp-next-shell') || STATE.lastRenderedView !== view);
    if (needsLoadingShell) {
      root.replaceChildren();
      const loading = document.createElement('div');
      loading.className = 'uapp-next-loading';
      loading.textContent = view === 'servicesDirectory' ? 'Načítám servisy…' : 'Načítám…';
      root.appendChild(loading);
    }
    STATE.lastRenderedView = view;
    try {
      const data = await loadData();
      if (token !== STATE.renderToken || !shouldActivate()) return;
      if (view === 'servicesDirectory') {
        await loadServicesOsmData({ skipRender: true });
        if (token !== STATE.renderToken || !shouldActivate()) return;
        await refreshServicesLocationLabel(data);
      }
      renderShell(data);
    } catch (err) {
      console.error('[USER_APP_NEXT] render failed', err);
      if (token !== STATE.renderToken || !shouldActivate()) return;
      if (root) {
        root.replaceChildren();
        const errWrap = document.createElement('div');
        errWrap.className = 'uapp-next-error-state';
        errWrap.setAttribute('data-testid', 'dashboard-load-error');
        const errEl = document.createElement('p');
        errEl.className = 'uapp-next-loading';
        errEl.textContent = 'Nepodařilo se načíst sekci. Zkuste to znovu nebo obnovte stránku.';
        const retryBtn = document.createElement('button');
        retryBtn.type = 'button';
        retryBtn.className = 'uapp-next-btn uapp-next-btn-primary';
        retryBtn.textContent = 'Zkusit znovu';
        retryBtn.setAttribute('data-testid', 'dashboard-retry-load');
        retryBtn.addEventListener('click', () => { void render(); });
        errWrap.appendChild(errEl);
        errWrap.appendChild(retryBtn);
        root.appendChild(errWrap);
      }
    }
  }

  function installHooks() {
    if (STATE.installed) return;
    STATE.installed = true;

    const originalLoadHomeDashboard = window.loadHomeDashboard;
    if (typeof originalLoadHomeDashboard === 'function') {
      window.loadHomeDashboard = async function () {
        const result = await originalLoadHomeDashboard.apply(this, arguments);
        if (shouldActivate()) {
          await render();
        } else {
          setActiveClass(false);
        }
        return result;
      };
    }

    const originalLoadVehicles = window.loadVehicles;
    if (typeof originalLoadVehicles === 'function') {
      window.loadVehicles = async function () {
        if (shouldActivate()) {
          if (getActiveView() === 'vehicles') {
            await render();
          }
          return;
        }
        return originalLoadVehicles.apply(this, arguments);
      };
    }

    const CANVAS_TAB_TO_VIEW = {
      home: 'home',
      vehicles: 'vehicles',
      reminders: 'reminders',
      reservations: 'reservations',
      account: 'settings',
      support: 'settings',
      documents: 'documents',
      servicesDirectory: 'servicesDirectory',
      serviceHistory: 'serviceHistory',
    };
    if (USER_INVOICES_ENABLED) CANVAS_TAB_TO_VIEW.invoices = 'invoices';

    const originalSwitchTab = window.switchTab;
    if (typeof originalSwitchTab === 'function') {
      window.switchTab = function () {
        const tabName = String(arguments[0] || '');
        if (CANVAS_TAB_TO_VIEW[tabName]) {
          STATE.viewOverride = CANVAS_TAB_TO_VIEW[tabName];
        } else if (tabName === 'serviceHistory') {
          STATE.viewOverride = 'serviceHistory';
        } else {
          STATE.viewOverride = null;
        }
        const result = originalSwitchTab.apply(this, arguments);
        if (shouldActivate()) {
          setActiveClass(true);
          if (CANVAS_TAB_TO_VIEW[tabName]) {
            document.querySelectorAll('#dashboard > .tab-content').forEach((el) => el.classList.remove('active'));
          }
          void render();
        } else {
          setActiveClass(false);
        }
        return result;
      };
    }

    if (typeof window.showVehicleDetail === 'function') {
      STATE.originalShowVehicleDetail = window.showVehicleDetail;
      window.showVehicleDetail = async function (vehicleId) {
        if (shouldActivate()) {
          return openUserVehicleDetailModal(vehicleId);
        }
        return STATE.originalShowVehicleDetail.apply(this, arguments);
      };
    }

    document.addEventListener('click', (event) => {
      const trigger = event.target && event.target.closest && event.target.closest('[data-uapp-action]');
      if (!trigger || trigger.disabled || trigger.getAttribute('aria-disabled') === 'true') return;
      const action = trigger.getAttribute('data-uapp-action');
      if (action === 'profile' || action === 'notifications') {
        event.preventDefault();
        event.stopPropagation();
        if (typeof event.stopImmediatePropagation === 'function') {
          event.stopImmediatePropagation();
        }
        if (action === 'profile') openProfileMenu(event);
        else openNotificationsPanel(event);
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      if (typeof event.stopImmediatePropagation === 'function') {
        event.stopImmediatePropagation();
      }
      runAction(action, event);
    }, true);

    window.UserAppNext = {
      render,
      runAction,
      runIntent,
      openVehicleSection,
      openUserVehicleDetailModal,
      closeUserVehicleDetailModal,
      get audit() {
        return {
          loadHomeDashboard: hasFn('loadHomeDashboard'),
          loadVehicles: hasFn('loadVehicles'),
          showVehicleDetail: hasFn('showVehicleDetail'),
          openAddVehicleModal: hasFn('openAddVehicleModal'),
          openAddServiceRecordModal: hasFn('openAddServiceRecordModal'),
          notifications: hasFn('toggleAppNotificationsPanel'),
          profileMenu: hasFn('toggleMobileProfileMenu'),
        };
      },
    };
  }

  function boot() {
    preserveLegacyOverlays();
    installHooks();
    window.setTimeout(() => {
      if (!shouldActivate() && document.body.classList.contains('route-app-view') && isAuthed() && !isServiceMode()) {
        const pathname = String(window.location.pathname || '');
        if (/\/service-history(?:\/|$)/i.test(pathname)) {
          STATE.viewOverride = 'serviceHistory';
        } else {
          const homeTab = document.getElementById('homeTab');
          if (homeTab && homeTab.classList.contains('active')) {
            STATE.viewOverride = 'home';
          }
        }
      }
      if (shouldActivate()) render();
    }, 0);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
