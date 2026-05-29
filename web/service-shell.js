(function () {
  /*
  PRODUCTION LOCK:
  Shell routing a visibility controller je stabilizovaný.
  Nesmí se měnit bez auditovaného zásahu.
  Source of truth: /api/me
  */
  console.log('[SERVICE_SHELL] SERVICE SHELL LOADED');

  function getAppDisplayName() {
    try {
      if (typeof window !== 'undefined') {
        if (typeof window.__appDisplayName === 'string' && window.__appDisplayName.trim()) {
          return window.__appDisplayName.trim();
        }
        if (typeof window.APP_NAME === 'string' && window.APP_NAME.trim()) {
          return window.APP_NAME.trim();
        }
      }
    } catch (e) {
      /* ignore */
    }
    return 'Správa vozidel';
  }

  const rootId = 'serviceAppRoot';
  const themeKey = 'serviceShellTheme';
  const dataTtlMs = 30000;
  const autoRefreshMs = 60000;
  const defaultSection = 'dashboard';

  /** Jednoduché monochromatické SVG ikony (stroke) — bez emoji, odlišné od jiných produktů. */
  const NAV_ICON_SVGS = {
    car: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" d="M7 17h10M5 17H3v-5l2-5h14l2 5v5h-2M7 17a2 2 0 1 1-4 0M21 17a2 2 0 1 1-4 0M6 7l-1.5 5h15L18 7"/></svg>',
    clipboard: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" d="M9 5h6M9 3h6v4H9zM6 5H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-1M8 13h8M8 17h5"/></svg>',
    camera: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" d="M4 7h3l2-3h6l2 3h3v13H4z"/><circle fill="none" stroke="currentColor" stroke-width="1.75" cx="12" cy="13" r="4"/></svg>',
    shield: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
    box: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" d="M21 8l-9-5-9 5 9 5 9-5zM3 8v8l9 5 9-5V8M12 13v8"/></svg>',
    pin: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" d="M12 17v5M9 10l-3 8 8-3 8-8-5-5-8 8zM14 6l4 4"/></svg>',
    users:
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    chat: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/></svg>',
    invoice:
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.75" d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z"/><path fill="none" stroke="currentColor" stroke-width="1.75" d="M14 2v6h6M8 13h8M8 17h8M10 9H8"/></svg>',
    folder:
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.75" d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>',
    attach:
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>',
    bank: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.75" d="M3 21h18M3 10h18M5 10V6l7-3 7 3v4M9 21V10M15 21V10"/></svg>',
    user: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.75" d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle fill="none" stroke="currentColor" stroke-width="1.75" cx="12" cy="7" r="4"/></svg>',
    calendar:
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><rect fill="none" stroke="currentColor" stroke-width="1.75" x="3" y="4" width="18" height="18" rx="2"/><path fill="none" stroke="currentColor" stroke-width="1.75" d="M16 2v4M8 2v4M3 10h18"/></svg>',
    stack: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.75" d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z"/><path fill="none" stroke="currentColor" stroke-width="1.75" d="M14 2v6h6M10 15h4M10 11h8"/></svg>',
    notebook:
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.75" d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path fill="none" stroke="currentColor" stroke-width="1.75" d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2zM8 7h8M8 11h8"/></svg>',
    export:
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.75" d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>',
    institution:
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.75" d="M3 21h18M6 21V7l6-4 6 4v14M9 21v-4h6v4"/></svg>',
    settings:
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><circle fill="none" stroke="currentColor" stroke-width="1.75" cx="12" cy="12" r="3"/><path fill="none" stroke="currentColor" stroke-width="1.75" d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>',
    palette:
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.75" d="M12 2a10 10 0 1 0 10 10 4 4 0 0 1-4-4 4 4 0 0 1-4-4 4 4 0 0 1 4-2z"/><circle cx="6.5" cy="11.5" r=".75" fill="currentColor" stroke="none"/><circle cx="9.5" cy="7.5" r=".75" fill="currentColor" stroke="none"/><circle cx="14.5" cy="7.5" r=".75" fill="currentColor" stroke="none"/><circle cx="17.5" cy="11.5" r=".75" fill="currentColor" stroke="none"/></svg>',
    help: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><circle fill="none" stroke="currentColor" stroke-width="1.75" cx="12" cy="12" r="10"/><path fill="none" stroke="currentColor" stroke-width="1.75" d="M9.09 9a3 3 0 1 1 5.83 1c0 2-3 2-3 4M12 17h.01"/></svg>',
    menu:
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" d="M4 7h16M4 12h16M4 17h16"/></svg>',
    company:
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.75" d="M3 21h18M5 21V7l8-4v18M13 21V11h8v10"/></svg>',
  };

  function navRailIconSvg(key) {
    const k = String(key || '').toLowerCase();
    return NAV_ICON_SVGS[k] || NAV_ICON_SVGS.pin;
  }

  /** Levý navigační sloupec (účet servisu): ikona, štítek, volitelné submenu. */
  const NAV_RAIL_CONFIG = [
    { group: 'prehled', navIcon: 'pin', label: 'Přehled', section: 'dashboard', submenu: null },
    { group: 'prijem', navIcon: 'car', label: 'Příjem vozidla', section: 'intake', submenu: null },
    { group: 'zakazky', navIcon: 'clipboard', label: 'Zakázky', section: 'work-orders', submenu: null },
    { group: 'vozidla', navIcon: 'car', label: 'Vozidla zákazníků', section: 'vehicles', submenu: null },
    { group: 'zakaznici', navIcon: 'users', label: 'Zákaznické centrum', section: 'clients', submenu: null },
    { group: 'foto', navIcon: 'camera', label: 'Fotodokumentace', section: 'photos', submenu: null },
    { group: 'historie', navIcon: 'notebook', label: 'Servisní historie', section: 'history', submenu: null },
    { group: 'fakturace', navIcon: 'invoice', label: 'Nabídky a faktury', section: 'invoices', submenu: null },
    { group: 'sklad', navIcon: 'box', label: 'Sklad dílů', section: 'parts', submenu: null },
    { group: 'rezervace', navIcon: 'calendar', label: 'Rezervace', section: 'reservations', submenu: null },
    { group: 'tym', navIcon: 'users', label: 'Tým', section: 'team', submenu: null },
    { group: 'audit', navIcon: 'shield', label: 'Audit a bezpečnost', section: 'audit', submenu: null },
    { group: 'nastaveni', navIcon: 'settings', label: 'Nastavení', section: 'settings', submenu: null },
  ];

  /** Spodní lišta na mobilu — 4 hlavní sekce + „Více“. */
  const MOBILE_TAB_CONFIG = [
    { group: 'prehled', navIcon: 'pin', label: 'Přehled', section: 'dashboard', kind: 'section' },
    { group: 'prijem', navIcon: 'car', label: 'Příjem', section: 'intake', kind: 'section' },
    { group: 'zakazky', navIcon: 'clipboard', label: 'Zakázky', section: 'work-orders', kind: 'section' },
    { group: 'vozidla', navIcon: 'car', label: 'Vozidla', section: 'vehicles', kind: 'section' },
    { group: 'vice', navIcon: 'menu', label: 'Více', section: null, kind: 'more' },
  ];

  const MOBILE_TAB_SECTIONS = new Set(
    MOBILE_TAB_CONFIG.filter((entry) => entry.kind === 'section').map((entry) => entry.section),
  );

  /** Skupiny v sheetu „Více“ — všechny sekce mimo primární záložky. */
  const MOBILE_NAV_SHEET_GROUPS = [
    {
      title: 'Zákazníci',
      items: [
        ['clients', 'Zákaznické centrum'],
        ['vehicles', 'Vozidla zákazníků'],
      ],
    },
    {
      title: 'Provoz',
      items: [
        ['intake', 'Příjem vozidla'],
        ['work-orders', 'Zakázky'],
        ['reservations', 'Rezervace'],
        ['reminders', 'Připomínky'],
      ],
    },
    {
      title: 'Dokumentace',
      items: [
        ['photos', 'Fotodokumentace'],
        ['history', 'Servisní historie'],
        ['documents', 'Dokumenty'],
      ],
    },
    {
      title: 'Finance a sklad',
      items: [
        ['invoices', 'Nabídky a faktury'],
        ['parts', 'Sklad dílů'],
      ],
    },
    {
      title: 'Správa',
      items: [
        ['team', 'Tým'],
        ['audit', 'Audit a bezpečnost'],
        ['settings', 'Nastavení'],
      ],
    },
  ];

  const serviceSections = new Set([
    'dashboard',
    'clients',
    'vehicles',
    'work-orders',
    'documents',
    'invoices',
    'reservations',
    'reminders',
    'intake',
    'photos',
    'history',
    'parts',
    'audit',
    'settings',
    'authorizations',
    'team',
    ...NAV_RAIL_CONFIG.flatMap((e) => [e.section, ...(e.submenu || []).map((row) => row[0])]),
    'payroll-employee-detail',
  ]);

  const SECTION_TO_NAV_GROUP = (() => {
    const m = new Map();
    NAV_RAIL_CONFIG.forEach((e) => {
      m.set(e.section, e.group);
      (e.submenu || []).forEach(([sid]) => {
        m.set(sid, e.group);
      });
    });
    m.set('payroll-employee-detail', 'payroll-zam');
    return m;
  })();

  let navOutsideCloseBound = false;

  function closeNavFlyouts() {
    try {
      document.querySelectorAll('.service-nav-slot.is-submenu-open').forEach((el) => el.classList.remove('is-submenu-open'));
    } catch (err) {
      /* ignore */
    }
  }

  function bindNavOutsideCloseOnce() {
    if (navOutsideCloseBound) return;
    navOutsideCloseBound = true;
    document.addEventListener(
      'pointerdown',
      (e) => {
        try {
          if (!e.target.closest('.service-nav')) closeNavFlyouts();
        } catch (err) {
          /* ignore */
        }
      },
      true,
    );
  }

  function handleNavRailClick(event, group) {
    const mobile = isMobileViewport();
    const config = mobile ? MOBILE_TAB_CONFIG : NAV_RAIL_CONFIG;
    const entry = config.find((item) => item.group === group);
    if (!entry) return;
    if (mobile && entry.kind === 'more') {
      event.preventDefault();
      toggleMobileNav();
      return;
    }
    const railEntry = NAV_RAIL_CONFIG.find((item) => item.group === group) || entry;
    const hasSub = Array.isArray(railEntry.submenu) && railEntry.submenu.length > 0;
    if (hasSub && mobile) {
      event.preventDefault();
      const slot = event.currentTarget && event.currentTarget.closest ? event.currentTarget.closest('.service-nav-slot') : null;
      if (!slot) return;
      const willOpen = !slot.classList.contains('is-submenu-open');
      closeNavFlyouts();
      if (willOpen) slot.classList.add('is-submenu-open');
      return;
    }
    navigate(railEntry.section || entry.section);
  }

  function mobileMoreTabActive() {
    if (state.mobileNavOpen) return true;
    return !MOBILE_TAB_SECTIONS.has(state.activeSection);
  }

  function mobileNavTabActive(entry) {
    if (entry.kind === 'more') return mobileMoreTabActive();
    return state.activeSection === entry.section;
  }

  function navRailSlotActive(entry) {
    if (!entry.submenu) {
      return state.activeSection === entry.section;
    }
    return SECTION_TO_NAV_GROUP.get(state.activeSection) === entry.group;
  }

  const legacyTargets = [
    { key: 'mainNavbar', selector: '#mainNavbar' },
    { key: 'dashboard', selector: '#dashboard' },
    { key: 'footer', selector: '.payment-legal-footer' },
  ];

  const originalShowDashboard = window.showDashboard;
  const originalShowLogin = window.showLogin;
  const originalSwitchTab = window.switchTab;
  const originalLoadHomeDashboard = window.loadHomeDashboard;
  const originalRenderServiceWorkspace = window.renderServiceWorkspace;
  const originalLoadServiceWorkspace = window.loadServiceWorkspace;
  const originalOpenServiceAddVehicleForCustomer = window.openServiceAddVehicleForCustomer;
  const originalOpenServiceDashboardCreateModal = window.openServiceDashboardCreateModal;
  const originalOpenServiceDashboardWorkOrderDetail = window.openServiceDashboardWorkOrderDetail;
  const originalSubmitServiceDashboardDetailUpdate = window.submitServiceDashboardDetailUpdate;

  const parkedLegacyNodes = new Map();

  const state = {
    mounted: false,
    loading: false,
    theme: safeStorageGet(themeKey) === 'dark' ? 'dark' : 'light',
    activeSection: defaultSection,
    kpiFilter: 'all',
    searchTerm: '',
    sortBy: 'due_asc',
    summary: null,
    workOrders: [],
    performance: [],
    technicians: [],
    queue: null,
    customers: [],
    vehicles: [],
    reservations: [],
    reminders: [],
    documents: [],
    invoices: [],
    quotes: [],
    dashboardOverview: null,
    dashboardWorkOrders: [],
    pendingAuthorizations: [],
    todayReservations: [],
    dashboardRisks: [],
    quickIntakeDraft: { plate: '', vin: '', phone: '', email: '', checklist: {} },
    intakeDraft: {
      vin: '',
      plate: '',
      brand: '',
      model: '',
      year: '',
      fuel: '',
      vehicleNote: '',
      mileage: '',
      odometer: '',
      technicianNote: '',
      checklist: {
        keys: false,
        body: false,
        lights: false,
        tires: false,
        interior: false,
        customer_notified: false,
      },
    },
    intakeLookupResponse: null,
    intakeLookupLegacyCandidate: null,
    intakeLookupLoading: false,
    intakeLookupError: '',
    intakeCreateFormOpen: false,
    intakeMutationLoading: false,
    intakeStartResult: null,
    intakeLimitedNotice: '',
    intakeSafeHistory: null,
    _intakeLookupTimer: null,
    _intakeFocusField: null,
    _intakeCaretPos: 0,
    workOrderLimitedNotice: '',
    workOrderDetailCache: {},
    vehicleTimelineCache: {},
    vehicleTimelineLoading: false,
    vehicleTimelineError: '',
    vehicleTimelineVehicleId: 0,
    searchResultsOpen: false,
    profile: {},
    partnerPublicProfile: {},
    errors: [],
    lastLoadedAt: 0,
    autoRefreshHandle: 0,
    accountMenuOpen: false,
    mobileNavOpen: false,
    filterSheetOpen: false,
    filterSheetType: 'work-orders',
    showCancelledReservations: false,
    showCompletedReminders: false,
    invoiceStatusFilter: 'all',
    invoiceSearchTerm: '',
    customerSearchQuery: '',
    customerSearchResults: [],
    customerSearchMeta: null,
    customerSearchLoading: false,
    customerSearchError: '',
    addCustomerQuickLinkDraft: { email: '', note: '' },
    createCustomerDraft: {
      first_name: '',
      last_name: '',
      email: '',
      phone: '',
      internal_note: '',
      consent_basis: 'service_customer_intake',
      consent_note:
        'Založení účtu zákazníka při návštěvě servisu — evidence vozidla a servisní historie v aplikaci Správa vozidel.',
      create_vehicle: false,
      vehicle_vin: '',
      vehicle_plate: '',
      vehicle_brand: '',
      vehicle_model: '',
    },
    vehicleLookupQuery: '',
    vehicleLookupResults: [],
    vehicleLookupMeta: null,
    vehicleLookupLoading: false,
    vehicleLookupError: '',
    workOrderDraft: null,
    addVehicleDraft: null,
    activeVehicle: null,
    modal: null,
    quoteListPrefs: { status: 'all', sort: 'created_at', order: 'desc' },
    payrollPeriod: { year: new Date().getFullYear(), month: new Date().getMonth() + 1 },
    payrollData: null,
    payrollLoading: false,
    payrollError: '',
    payrollDetailEmployeeId: null,
    payrollEmployeeDetailCache: null,
    /** Objekt `{ [reminderId]: true }` — přehlédnuto v aktuální návštěvě sekce Připomínky kvůli frontě propadlých úkolů. */
    overdueReminderSkipIds: null,
    /** ID připomínky při rozbalení formuláře „Posunout připomenutí“ přímo v sekci */
    overdueReminderRescheduleId: null,
    /** Blokovat tlačítka během ukládání z overlay připomínek po termínu */
    overdueReminderActionSaving: false,
    /** UX: zvýraznit kartu zákazníka po vytvoření / propojení */
    highlightCustomerId: null,
    _highlightCustomerTimer: 0,
    createCustomerSubmitting: false,
    linkExistingByEmailSubmitting: false,
    /** lookup_id JWT během POST link-from-lookup */
    linkFromLookupBusy: null,
    accessRequestBusyVehicleId: null,
    /** vehicle_id → true po odeslané žádosti; vyčištění při refreshi výsledků */
    pendingAccessVehicleIds: {},
  };

  state.modal = createEmptyModalState();

  function safeStorageGet(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (error) {
      return null;
    }
  }

  function safeStorageSet(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (error) {
      /* noop */
    }
  }

  function getRoot() {
    let root = document.getElementById(rootId);
    if (root) return root;
    const dashboard = document.getElementById('dashboard');
    root = document.createElement('div');
    root.id = rootId;
    root.className = 'service-app-root hidden';
    root.setAttribute('data-testid', 'service-shell-root');
    root.setAttribute('data-service-shell', 'root');
    if (dashboard?.parentNode) {
      dashboard.parentNode.insertBefore(root, dashboard);
    } else {
      document.body.appendChild(root);
    }
    return root;
  }

  function isServiceRole() {
    if (typeof window.isServiceWorkspaceRole === 'function' && window.isServiceWorkspaceRole()) return true;
    const role = String(window.currentUser?.role || '').toLowerCase();
    return role === 'service';
  }

  function isMobileViewport() {
    return Number(window.innerWidth || 0) <= 900;
  }

  let serviceShellToastSeq = 0;

  function ensureServiceShellToastHost() {
    let el = document.getElementById('serviceShellToastHost');
    if (el) return el;
    el = document.createElement('div');
    el.id = 'serviceShellToastHost';
    el.className = 'service-shell-toast-host';
    el.setAttribute('aria-live', 'polite');
    document.body.appendChild(el);
    return el;
  }

  /**
   * Viditelná zpětná vazba pro servisní akce (mobil + desktop). Při chybě hostitele použije showAlert.
   * @param {'success'|'warning'|'error'|'info'} type
   */
  function showServiceToast(type, title, message) {
    const t = ['success', 'warning', 'error', 'info'].includes(String(type)) ? String(type) : 'info';
    const titleText = String(title || '').trim();
    const bodyText = String(message || '').trim();
    const fallbackMsg = [titleText, bodyText].filter(Boolean).join('\n\n') || bodyText || titleText;
    try {
      const host = ensureServiceShellToastHost();
      const node = document.createElement('div');
      node.className = `service-shell-toast service-shell-toast--${t}`;
      node.innerHTML = `${titleText ? `<div class="service-shell-toast-title">${escape(titleText)}</div>` : ''}<div class="service-shell-toast-body">${escape(bodyText).replace(/\n/g, '<br>')}</div>`;
      host.appendChild(node);
      window.setTimeout(() => {
        node.classList.add('service-shell-toast--out');
        window.setTimeout(() => {
          try {
            node.remove();
          } catch (e) {
            /* ignore */
          }
        }, 320);
      }, 8400);
      serviceShellToastSeq += 1;
      return;
    } catch (e) {
      console.warn('[SERVICE_SHELL] toast host failed', e);
    }
    if (typeof window.showAlert === 'function') {
      window.showAlert(
        fallbackMsg,
        t === 'error' ? 'error' : t === 'warning' ? 'warning' : t === 'success' ? 'success' : 'info',
      );
    }
  }

  function showToast(message, type = 'info') {
    if (typeof window.showAlert === 'function') {
      window.showAlert(message, type);
    }
  }

  function formatMinutes(total) {
    const n = Math.max(0, Number(total || 0));
    const h = Math.floor(n / 60);
    const m = Math.round(n % 60);
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
  }

  function formatTime(value) {
    if (!value) return '';
    try {
      const d = new Date(value);
      if (!Number.isNaN(d.getTime())) {
        return d.toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit' });
      }
    } catch (err) {
      /* ignore */
    }
    return String(value || '').slice(11, 16) || String(value || '');
  }

  function scheduleCustomerHighlightClear() {
    window.clearTimeout(state._highlightCustomerTimer);
    state._highlightCustomerTimer = window.setTimeout(() => {
      state.highlightCustomerId = null;
      if (state.activeSection === 'clients') render();
    }, 12000);
  }

  function refreshAccessRequestDependentUi() {
    refreshCustomerSearchDependentModals();
    if (state.modal?.open) renderModal();
    render();
  }

  function escape(value) {
    try {
      if (typeof window.escapeHtml === 'function') {
        return window.escapeHtml(value ?? '');
      }
      return String(value ?? '');
    } catch (err) {
      console.warn('[SERVICE_SHELL] escape failed:', err);
      try {
        return String(value ?? '');
      } catch (e2) {
        return '';
      }
    }
  }

  function ServicePageHeader(title, subtitle, actionsHtml = '') {
    return `
      <header class="service-page-header" data-testid="service-page-header">
        <div class="service-page-header-text">
          <h1>${escape(title)}</h1>
          ${subtitle ? `<p class="service-page-header-sub">${escape(subtitle)}</p>` : ''}
        </div>
        ${actionsHtml ? `<div class="service-page-header-actions">${actionsHtml}</div>` : ''}
      </header>`;
  }

  function ServiceSectionShell(title, subtitle, bodyHtml, options = {}) {
    const badge = options.limited
      ? '<span class="service-status-badge service-status-badge--pending" data-testid="service-section-limited-badge">Připravuje se</span>'
      : '';
    return `
      <section class="service-section-shell ${options.limited ? 'service-section-shell--limited' : ''}" data-testid="service-section-shell">
        ${ServicePageHeader(title, subtitle, badge)}
        <div class="service-section-shell-body">${bodyHtml}</div>
      </section>`;
  }

  function stripAsideWrapper(html) {
    const raw = String(html || '');
    const match = raw.match(/^\s*<aside[^>]*class="[^"]*service-shell-side[^"]*"[^>]*>([\s\S]*)<\/aside>\s*$/i);
    return match ? match[1] : raw;
  }

  function ServiceProPageShell(title, subtitle, mainHtml, options = {}) {
    const {
      asideHtml = '',
      statsHtml = '',
      limited = false,
      showFooter = true,
      headerActions = '',
      testId = 'service-section-page',
    } = options;
    const badge = limited
      ? '<span class="service-status-badge service-status-badge--pending" data-testid="service-section-limited-badge">Připravuje se</span>'
      : '';
    const actions = headerActions || badge;
    const kpiBlock = statsHtml
      ? `<section class="service-pro-kpis service-pro-kpis--section">${statsHtml}</section>`
      : '';
    const gridClass = asideHtml ? 'service-pro-grid' : 'service-pro-grid service-pro-grid--single';
    const asideBlock = asideHtml
      ? `<aside class="service-pro-aside service-pro-aside--section">${asideHtml}</aside>`
      : '';
    return `
      <div class="service-dashboard-pro service-section-page" data-testid="${escape(testId)}">
        ${ServicePageHeader(title, subtitle, actions)}
        ${kpiBlock}
        <div class="${gridClass}">
          <main class="service-pro-main service-pro-main--section">${mainHtml}</main>
          ${asideBlock}
        </div>
        ${showFooter ? renderGdprBottomBar() : ''}
      </div>`;
  }

  function ServiceEmptyState(title, message) {
    return `
      <div class="service-pro-card service-state-card--empty" data-testid="service-empty-state" role="status">
        <strong>${escape(title)}</strong>
        <p>${escape(message)}</p>
      </div>`;
  }

  function ServiceErrorState(message, retryAction = '') {
    const retryBtn = retryAction
      ? `<button type="button" class="service-shell-primary-btn" onclick="${retryAction}">Zkusit znovu</button>`
      : '';
    return `
      <div class="service-pro-card service-state-card--error" data-testid="service-error-state" role="alert">
        <strong>Nepodařilo se načíst data</strong>
        <p>${escape(message)}</p>
        ${retryBtn}
      </div>`;
  }

  function ServicePermissionDeniedState(message) {
    return `
      <div class="service-pro-card service-state-card--denied" data-testid="service-permission-denied" role="alert">
        <strong>Přístup není povolen</strong>
        <p>${escape(message || 'K této části nemáte oprávnění bez schválení majitele vozidla.')}</p>
      </div>`;
  }

  function ServiceLoadingSkeleton(sectionKey = '') {
    const label = sectionKey ? `Načítám sekci…` : 'Načítám servisní prostor…';
    return `
      ${ServicePageHeader(label, 'Načítávám data pro vybranou sekci.')}
      <div class="service-loading-skeleton" data-testid="service-loading-skeleton" aria-busy="true">
        <div class="service-loading-skeleton-block"></div>
        <div class="service-loading-skeleton-block service-loading-skeleton-block--short"></div>
        <div class="service-loading-skeleton-grid">
          <div class="service-loading-skeleton-card"></div>
          <div class="service-loading-skeleton-card"></div>
        </div>
      </div>`;
  }

  function ServiceStatusBadge(label, tone = 'neutral') {
    const safeTone = ['success', 'warning', 'danger', 'pending', 'neutral'].includes(tone) ? tone : 'neutral';
    return `<span class="service-status-badge service-status-badge--${safeTone}">${escape(label)}</span>`;
  }

  function ServiceActionBar(buttonsHtml) {
    return `<div class="service-action-bar" data-testid="service-action-bar">${buttonsHtml || ''}</div>`;
  }

  function ServiceIntakeLookupCard(contentHtml) {
    return `<article class="service-state-card service-intake-lookup-card">${contentHtml || ''}</article>`;
  }

  function ServiceVehicleSafePreviewCard(contentHtml) {
    return `<article class="service-state-card service-intake-safe-preview-card" data-testid="service-intake-safe-preview">${contentHtml || ''}</article>`;
  }

  function ServiceVehicleAccessStateCard(contentHtml) {
    return `<article class="service-state-card service-intake-access-card" data-testid="service-intake-access-state">${contentHtml || ''}</article>`;
  }

  function ServiceIntakeChecklist(contentHtml) {
    return `<div class="service-intake-checklist">${contentHtml || ''}</div>`;
  }

  function ServiceIntakeOdometerCard(contentHtml) {
    return `<article class="service-state-card service-intake-odometer-card">${contentHtml || ''}</article>`;
  }

  function ServiceIntakeTechnicianNote(contentHtml) {
    return `<article class="service-state-card service-intake-technician-note">${contentHtml || ''}</article>`;
  }

  function ServiceIntakePhotoState(contentHtml) {
    return `<article class="service-state-card service-state-card--empty service-intake-photo-state" data-testid="service-intake-limited-photo-state">${contentHtml || ''}</article>`;
  }

  function ServiceIntakeNextActions(contentHtml) {
    return `<article class="service-state-card service-intake-next-actions">${contentHtml || ''}</article>`;
  }

  function ServiceDisabledFeatureNotice(message) {
    return `<article class="service-state-card service-state-card--empty"><p>${escape(message || '')}</p></article>`;
  }

  function ServiceAuditNotice(message) {
    return `<article class="service-state-card service-state-card--empty"><p>${escape(message || '')}</p></article>`;
  }

  function ServiceLimitedPlaceholderCopy() {
    return 'Tato sekce je připravena jako pracovní prostor. Plné funkce budou doplněny v další fázi. Aktuálně nejsou zobrazena žádná data bez ověřeného backend workflow.';
  }

  function renderLimitedWorkspaceSection(title, subtitle, extraHtml = '') {
    return ServiceProPageShell(
      title,
      subtitle,
      `
        <article class="service-pro-card service-pro-card--limited" data-testid="service-limited-placeholder">
          <p>${escape(ServiceLimitedPlaceholderCopy())}</p>
          ${extraHtml || ''}
        </article>
      `,
      { limited: true },
    );
  }

  function formatDate(value) {
    if (typeof window.formatDateCZ === 'function') {
      return window.formatDateCZ(value);
    }
    return value ? String(value).slice(0, 10) : '-';
  }

  function initials(value) {
    const parts = String(value || '')
      .split(/[\s@._-]+/)
      .filter(Boolean)
      .slice(0, 2);
    if (!parts.length) return 'SA';
    return parts.map((item) => item.charAt(0).toUpperCase()).join('');
  }

  function todayKey() {
    if (typeof window.getAppCalendarDateKey === 'function') {
      return window.getAppCalendarDateKey(new Date());
    }
    try {
      return new Intl.DateTimeFormat('en-CA', {
        timeZone: 'Europe/Prague',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
      }).format(new Date());
    } catch (e) {
      return new Date().toISOString().slice(0, 10);
    }
  }

  function toDateKey(value) {
    return value ? String(value).slice(0, 10) : '';
  }

  function statusMeta(status) {
    const key = String(status || '').trim().toLowerCase();
    if (key === 'awaiting_client_approval') return { label: 'Čeká na schválení', cls: 'awaiting' };
    if (key === 'approved') return { label: 'Přijato', cls: 'in_progress' };
    if (key === 'in_progress') return { label: 'Práce probíhá', cls: 'in_progress' };
    if (key === 'completed') return { label: 'Hotovo', cls: 'completed' };
    if (key === 'issue') return { label: 'Problém', cls: 'issue' };
    if (key === 'invoiced') return { label: 'Fakturováno', cls: 'completed' };
    if (key === 'closed') return { label: 'Uzavřeno', cls: 'completed' };
    if (key === 'cancelled') return { label: 'Zrušeno', cls: 'issue' };
    return { label: 'Nová', cls: 'awaiting' };
  }

  function reservationStatusKey(status) {
    return String(status || '').trim().toUpperCase();
  }

  function reservationBadgeClass(status) {
    const key = reservationStatusKey(status);
    if (key === 'COMPLETED') return 'completed';
    if (key === 'CANCELLED') return 'issue';
    if (key === 'CONFIRMED') return 'in_progress';
    return 'awaiting';
  }

  function isReservationArchived(item) {
    const key = reservationStatusKey(item?.status);
    return key === 'CANCELLED' || key === 'COMPLETED';
  }

  function filteredReservations() {
    const query = String(state.searchTerm ?? '').trim().toLowerCase();
    let items = Array.isArray(state.reservations) ? [...state.reservations] : [];

    if (!state.showCancelledReservations) {
      items = items.filter((item) => !isReservationArchived(item));
    }

    if (query) {
      items = items.filter((item) => {
        const haystack = [
          item?.customer_name,
          item?.customer_email,
          item?.vehicle_name,
          item?.vehicle_label,
          item?.vehicle_plate,
          item?.service_type,
          item?.note,
        ].join(' ').toLowerCase();
        return haystack.includes(query);
      });
    }

    items.sort((a, b) => {
      const left = String(a?.scheduled_for || a?.reservation_date || a?.starts_at || a?.created_at || '');
      const right = String(b?.scheduled_for || b?.reservation_date || b?.starts_at || b?.created_at || '');
      return left.localeCompare(right);
    });

    return items;
  }

  function reminderIsIncomplete(item) {
    if (!item) return false;
    const v = item.is_completed;
    if (v === true || v === 1 || v === '1') return false;
    if (String(v).toLowerCase() === 'true') return false;
    return true;
  }

  /** Propadlé: aktivní připomínka s datumem úkolu před dneškem nebo s časem notify_at už v minulosti. */
  function reminderIsOverdueAttention(item) {
    if (!reminderIsIncomplete(item)) return false;
    const dk = toDateKey(item?.due_date);
    if (dk && dk < todayKey()) return true;
    const na = item?.notify_at;
    if (na) {
      const t = new Date(na).getTime();
      if (!Number.isNaN(t) && t < Date.now()) return true;
    }
    return false;
  }

  function getOverdueRemindersSortedByDue() {
    const items = Array.isArray(state.reminders) ? state.reminders.filter(reminderIsOverdueAttention) : [];
    items.sort((a, b) => {
      const left = `${toDateKey(a?.due_date)}|${String(a?.notify_at || '')}`;
      const right = `${toDateKey(b?.due_date)}|${String(b?.notify_at || '')}`;
      return left.localeCompare(right);
    });
    return items;
  }

  function overdueAttentionSummaryLabel(item) {
    const dk = toDateKey(item?.due_date);
    if (dk && dk < todayKey()) return `Úkol měl stanovený termín ${formatDate(item.due_date)}.`;
    if (item?.notify_at) return `Plánované připomenutí (${formatDateTime(item.notify_at)}) už proběhlo.`;
    return 'Vyřešte dokončením úkolu nebo posunem termínu.';
  }

  function resetRemindersSectionOverdueSkips() {
    state.overdueReminderSkipIds = {};
    state.overdueReminderRescheduleId = null;
    state.overdueReminderActionSaving = false;
  }

  function resolveRemindersPastDueOverlayPack() {
    const list = getOverdueRemindersSortedByDue();
    if (!list.length) return null;
    const rescheduleId = Number(state.overdueReminderRescheduleId || 0);
    if (rescheduleId) {
      const hit = list.find((entry) => Number(entry?.id || 0) === rescheduleId);
      if (!hit) {
        state.overdueReminderRescheduleId = null;
      } else {
        const index = Math.max(0, list.indexOf(hit));
        return {
          reminder: hit,
          index: index + 1,
          total: list.length,
          step: 'reschedule',
        };
      }
    }
    const pack = nextOverdueReminderForPrompt();
    return pack ? { ...pack, step: 'action' } : null;
  }

  function remindersPastDueAttentionOverlayHtml() {
    if (!state.mounted || state.activeSection !== 'reminders') return '';
    const pack = resolveRemindersPastDueOverlayPack();
    if (!pack) return '';

    const reminder = pack.reminder || {};
    const id = Number(reminder?.id || 0);
    if (!id) return '';

    const vehicleLabel = String(reminder?.vehicle_label || 'Připomínka').trim() || 'Připomínka';
    const excerpt = String(reminder?.text || '').trim();
    const excerptShort = excerpt.length > 280 ? `${excerpt.slice(0, 277)}…` : excerpt;
    const busy = !!state.overdueReminderActionSaving;
    const step = pack.step === 'reschedule' ? 'reschedule' : 'action';
    const defaults = overdueReminderDefaultRescheduleFields(reminder);

    let bodyInner = '';
    if (step === 'reschedule') {
      bodyInner = `
          <div class="service-shell-inline-error" role="alert" style="margin:0 0 14px;line-height:1.45;font-size:0.89rem;color:#fca5a5;">
            Vyberte nový termín a volitelný čas dalšího připomenutí.
          </div>
          <form class="service-dashboard-modal-form" onsubmit="event.preventDefault(); window.serviceShell.submitOverdueReminderReschedule();">
            <div class="service-dashboard-modal-grid cols-2">
              <div class="form-group">
                <label for="serviceShellOverdueReminderDue">Nový termín úkolu (datum)</label>
                <input type="date" id="serviceShellOverdueReminderDue" required ${busy ? 'disabled' : ''} value="${escape(defaults.due)}">
              </div>
              <div class="form-group">
                <label for="serviceShellOverdueReminderNotify">Další připomenutí (datum a čas)</label>
                <input type="datetime-local" id="serviceShellOverdueReminderNotify" ${busy ? 'disabled' : ''} value="${escape(defaults.notifyAt)}">
              </div>
            </div>
          </form>
      `;
    } else {
      const notice = overdueAttentionSummaryLabel(reminder);
      const bodyText = excerptShort
        ? `<p style="margin:0 0 12px;line-height:1.5;">${escape(excerptShort)}</p>`
        : '<p class="service-shell-muted" style="margin:0 0 12px;">Bez doprovodného textu.</p>';
      bodyInner = `
        <div class="service-shell-inline-error" role="alert" style="margin:0 0 14px;line-height:1.45;font-size:0.9rem;color:#fcd34d;">
          ${escape(notice)}
        </div>
        ${bodyText}
        <div class="service-shell-list" style="margin-top:12px;font-size:0.9rem;">
          <div class="service-shell-list-row"><span class="service-shell-list-title">Vozidlo / kontext</span><span class="service-shell-list-value">${escape(vehicleLabel)}</span></div>
        </div>
      `;
    }

    const footerBtns =
      step === 'reschedule'
        ? `
        <button type="button" class="btn btn-secondary" ${busy ? 'disabled' : ''} onclick="window.serviceShell.backOverdueReminderPromptToAction()">Zpět</button>
        <button type="button" class="btn btn-primary" ${busy ? 'disabled' : ''} onclick="window.serviceShell.submitOverdueReminderReschedule()">${busy ? 'Ukládám…' : 'Uložit nový termín'}</button>
      `
        : `
        <button type="button" class="btn btn-secondary" ${busy ? 'disabled' : ''} onclick="window.serviceShell.dismissOverdueReminderPromptAndContinue(${id})">Teď ne</button>
        <button type="button" class="btn btn-secondary" ${busy ? 'disabled' : ''} onclick="window.serviceShell.markOverdueReminderDoneFromPrompt(${id})">${busy ? 'Ukládám…' : 'Splněno'}</button>
        <button type="button" class="btn btn-primary" ${busy ? 'disabled' : ''} onclick="window.serviceShell.openOverdueReminderRescheduleStep(${id})">Posunout připomenutí</button>
      `;

    return `
      <div class="service-shell-reminders-overdue-backdrop"
        onclick="if (event.target === this) window.serviceShell.dismissOverdueReminderPromptAndContinue(${id})"
        style="position:fixed;inset:0;z-index:2147483200;display:flex;align-items:center;justify-content:center;padding:clamp(12px,3vw,20px);background:rgba(14,17,21,0.62);backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px);">
        <div class="service-shell-reminders-overdue-dialog" role="dialog" aria-modal="true" onclick="event.stopPropagation();"
          style="position:relative;background:#171b21;color:#f4f7fb;width:min(520px,calc(100vw - 8px));max-height:90vh;overflow:auto;border-radius:14px;border:1px solid rgba(255,255,255,0.12);box-shadow:0 24px 54px rgba(0,0,0,0.55);padding:clamp(14px,2.5vw,22px);">
          <header style="margin:0 0 12px;padding-right:36px;">
            <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.08em;opacity:0.75;margin:0 0 6px;">Připomínka po termínu (${Number(pack.index || 1)} z ${Number(pack.total || 1)})</div>
            <h2 id="service-shell-overdue-title" style="margin:0;font-size:1.2rem;line-height:1.25;">${escape(vehicleLabel)}</h2>
            <p class="service-shell-muted" style="margin:8px 0 0;line-height:1.45;font-size:0.9rem;">Ujistěte se, že servis ví, zda už je úkol hotový, nebo jej potřebujete jen znovu připomenout v budoucnu.</p>
          </header>
          <button type="button" aria-label="Zavřít" onclick="window.serviceShell.dismissOverdueReminderPromptAndContinue(${id})"
            style="position:absolute;top:12px;right:12px;width:36px;height:36px;border-radius:10px;border:1px solid rgba(255,255,255,0.14);background:rgba(255,255,255,0.06);color:inherit;font-size:22px;line-height:1;cursor:pointer;">×</button>
          <section style="margin-top:12px;">${bodyInner}</section>
          <footer style="display:flex;flex-wrap:wrap;gap:10px;margin-top:20px;">
            ${footerBtns}
          </footer>
        </div>
      </div>
    `;
  }

  function closeOverdueReminderFloatingModalOnly() {
    if (
      state.modal?.open &&
      (state.modal.entityType === 'reminder-overdue' ||
        String(state.modal?.key || '').startsWith('reminder-overdue-prompt-'))
    ) {
      closeModal();
    }
  }

  function nextOverdueReminderForPrompt() {
    const skip = state.overdueReminderSkipIds || {};
    const list = getOverdueRemindersSortedByDue();
    for (let index = 0; index < list.length; index += 1) {
      const raw = list[index];
      const rid = Number(raw?.id || 0);
      if (!rid || skip[rid]) continue;
      return { reminder: raw, index: index + 1, total: list.length };
    }
    return null;
  }

  function dismissOverdueReminderPromptAndContinue(reminderId) {
    const id = Number(reminderId || state.modal?.context?.reminderId || 0);
    if (!state.overdueReminderSkipIds) state.overdueReminderSkipIds = {};
    if (id) state.overdueReminderSkipIds[id] = true;
    state.overdueReminderRescheduleId = null;
    closeOverdueReminderFloatingModalOnly();
    render();
  }

  const REMINDERS_OVERDUE_OVERLAY_MOUNT_ID = 'serviceShellRemindersOverdueLayer';

  function removeRemindersOverdueOverlayMount() {
    document.getElementById(REMINDERS_OVERDUE_OVERLAY_MOUNT_ID)?.remove();
  }

  /** Upozornění nad celou aplikací — mimo DOM shellu kvůli z-indexu / stacking contextům */
  function mountRemindersOverdueOverlayIfNeeded() {
    removeRemindersOverdueOverlayMount();
    if (!state.mounted || !isServiceRole()) return;
    if (state.activeSection !== 'reminders') return;
    const html = remindersPastDueAttentionOverlayHtml();
    if (!html) return;
    const layer = document.createElement('div');
    layer.id = REMINDERS_OVERDUE_OVERLAY_MOUNT_ID;
    layer.dataset.serviceShellOverlay = 'reminders-overdue';
    layer.innerHTML = html;
    document.body.appendChild(layer);
  }

  function overdueReminderDefaultRescheduleFields(snapshot = {}) {
    const today = todayKey();
    const prevDue = toDateKey(snapshot?.due_date);
    const due = prevDue && prevDue > today ? prevDue : today;
    const base = new Date();
    base.setDate(base.getDate() + 1);
    base.setHours(9, 0, 0, 0);
    return {
      due,
      notifyAt: toDateTimeInputValue(base),
    };
  }

  async function markOverdueReminderDoneFromPrompt(reminderId) {
    const id = Number(reminderId || state.modal?.context?.reminderId || 0);
    if (!id) return;
    state.overdueReminderActionSaving = true;
    render();
    try {
      await window.apiCall(`/api/v1/services/workspace/reminders/${id}`, 'PUT', { is_completed: true });
      showToast('Připomínka byla označena jako splněná.', 'success');
      state.overdueReminderRescheduleId = null;
      closeOverdueReminderFloatingModalOnly();
      await load(true, true);
    } catch (error) {
      showToast(String(error?.message || 'Nepodařilo se uložit změnu.'), 'error');
    } finally {
      state.overdueReminderActionSaving = false;
      render();
    }
  }

  function openOverdueReminderRescheduleStep(reminderId) {
    const id = Number(reminderId || state.modal?.context?.reminderId || 0);
    if (!id) return;
    state.overdueReminderRescheduleId = id;
    render();
  }

  function backOverdueReminderPromptToAction() {
    state.overdueReminderRescheduleId = null;
    if (
      state.modal?.open &&
      String(state.modal.key || '').startsWith('reminder-overdue-prompt-')
    ) {
      state.modal.context = { ...(state.modal.context || {}), step: 'action' };
      setModalState({ context: state.modal.context, saving: false, error: '' });
    }
    render();
  }

  async function submitOverdueReminderReschedule() {
    const id = Number(
      state.overdueReminderRescheduleId || state.modal?.context?.reminderId || 0
    );
    if (!id) return;
    const dueEl = document.getElementById('serviceShellOverdueReminderDue');
    const notifyEl = document.getElementById('serviceShellOverdueReminderNotify');
    const dueVal = String(dueEl?.value || '').trim().slice(0, 10) || '';
    const today = todayKey();
    if (!dueVal) {
      showToast('Vyberte nový termín (datum).', 'warning');
      return;
    }
    if (dueVal < today) {
      showToast('Vyberte termín nepředcházející dnešku.', 'warning');
      return;
    }
    const rawNotify = String(notifyEl?.value || '').trim();
    const payload = { due_date: dueVal };
    if (rawNotify) {
      payload.notify_at = fromDateTimeInputValue(rawNotify);
    }
    state.overdueReminderActionSaving = true;
    render();
    try {
      await window.apiCall(`/api/v1/services/workspace/reminders/${id}`, 'PUT', payload);
      showToast('Termín připomenutí byl aktualizován.', 'success');
      state.overdueReminderRescheduleId = null;
      closeOverdueReminderFloatingModalOnly();
      await load(true, true);
    } catch (error) {
      showToast(String(error?.message || 'Nepodařilo se uložit termín.'), 'error');
    } finally {
      state.overdueReminderActionSaving = false;
      render();
    }
  }

  function filteredReminders() {
    const query = String(state.searchTerm ?? '').trim().toLowerCase();
    let items = Array.isArray(state.reminders) ? [...state.reminders] : [];

    if (!state.showCompletedReminders) {
      items = items.filter((item) => reminderIsIncomplete(item));
    }

    if (query) {
      items = items.filter((item) => {
        const haystack = [
          item?.customer_name,
          item?.customer_email,
          item?.vehicle_label,
          item?.text,
          item?.type,
        ].join(' ').toLowerCase();
        return haystack.includes(query);
      });
    }

    items.sort((a, b) => {
      const left = String(a?.due_date || a?.notify_at || '');
      const right = String(b?.due_date || b?.notify_at || '');
      return left.localeCompare(right);
    });

    return items;
  }

  function sourceLabel(source) {
    const key = String(source || '').trim().toLowerCase();
    if (key === 'manual') return 'Manual Entry';
    if (key === 'api') return 'API Sync';
    if (key === 'crm') return 'CRM Import';
    if (key === 'reservation') return 'Reservation';
    return source ? String(source) : '-';
  }

  function formatDateTime(value) {
    if (!value) return '-';
    try {
      return new Date(value).toLocaleString('cs-CZ', { timeZone: 'Europe/Prague', hour12: false });
    } catch (error) {
      return String(value);
    }
  }

  function toDateTimeInputValue(value) {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    const offset = date.getTimezoneOffset();
    const local = new Date(date.getTime() - (offset * 60000));
    return local.toISOString().slice(0, 16);
  }

  function fromDateTimeInputValue(value) {
    const raw = String(value || '').trim();
    if (!raw) return null;
    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) return null;
    return date.toISOString();
  }

  function formatMoney(value, currency = 'CZK') {
    const amount = Number(value);
    if (!Number.isFinite(amount)) return '-';
    try {
      return new Intl.NumberFormat('cs-CZ', {
        style: 'currency',
        currency: currency || 'CZK',
        maximumFractionDigits: 2,
      }).format(amount);
    } catch (error) {
      return `${amount} ${currency || 'CZK'}`;
    }
  }

  function disclosureLabel(value) {
    return String(value || '').toLowerCase() === 'full' ? 'Plné zobrazení' : 'Omezené zobrazení';
  }

  function accessStatusLabel(value) {
    const key = String(value || '').trim().toLowerCase();
    if (key === 'linked') return 'Propojeno';
    if (key === 'not_linked') return 'Nepropojeno';
    if (key === 'already_approved') return 'Přístup schválen';
    if (key === 'pending_request') return 'Čeká na schválení';
    if (key === 'matched') return 'Vyžaduje přístup';
    if (key === 'owner_missing') return 'Chybí schvalovatel';
    if (key === 'processed') return 'Zpracováno';
    if (key === 'needs_review') return 'Vyžaduje kontrolu';
    if (key === 'failed') return 'Selhalo';
    if (key === 'open') return 'Aktivní';
    if (key === 'completed') return 'Dokončeno';
    if (key === 'confirmed') return 'Potvrzeno';
    if (key === 'cancelled') return 'Zrušeno';
    if (key === 'pending') return 'Čeká';
    return value ? String(value) : '-';
  }

  function renderDetailPills(detail) {
    const vid = Number(detail?.vehicle_id || detail?.id || 0);
    const st = String(detail?.status || detail?.access_status || '').toLowerCase();
    const localPending =
      vid && state.pendingAccessVehicleIds && state.pendingAccessVehicleIds[vid] && st !== 'pending_request';
    const pills = [
      `<span class="service-shell-detail-pill">${escape(accessStatusLabel(detail?.status || detail?.access_status))}</span>`,
      `<span class="service-shell-detail-pill">${escape(disclosureLabel(detail?.disclosure))}</span>`,
    ];
    if (localPending) {
      pills.push('<span class="service-shell-detail-pill">Čeká na schválení</span>');
    }
    if (detail?.can_edit) pills.push('<span class="service-shell-detail-pill">Lze upravit</span>');
    if (detail?.can_request_access) pills.push('<span class="service-shell-detail-pill">Lze žádat přístup</span>');
    if (detail?.can_create_work_order) pills.push('<span class="service-shell-detail-pill">Lze založit zakázku</span>');
    return `<div class="service-shell-detail-pills">${pills.join('')}</div>`;
  }

  function renderBlockingReason(detail) {
    if (!detail?.blocking_reason) return '';
    return `<div class="service-shell-inline-error">${escape(detail.blocking_reason)}</div>`;
  }

  function openDetailModal(config = {}) {
    const entityId = Number(config.entityId || 0);
    if (!entityId) return;
    return openModal({
      key: `${config.entityType}-detail-${entityId}`,
      entityType: config.entityType,
      entityId,
      kicker: config.kicker,
      title: config.title,
      description: config.description,
      size: config.size || 'wide',
      load: async () => {
        if (typeof config.load === 'function') {
          return config.load();
        }
        return window.apiCall(config.endpoint, 'GET');
      },
      actions: config.actions || {},
      renderContent: (modal) => config.renderContent(modal.data || {}, modal),
      renderFooter: (modal) => config.renderFooter(modal.data || {}, modal),
    });
  }

  function currentProfile() {
    return state.profile && Object.keys(state.profile).length ? state.profile : (window.currentUser || {});
  }

  /** Sladění s backend pravidly service_records._assert_current_user_can_edit_record + immutable statusy. */
  function computeServiceRecordShellEditState(record) {
    if (!record || !record.id) {
      return { editable: true, reason: null };
    }
    const status = String(record.record_status || 'draft').toLowerCase();
    if (status === 'approved' || status === 'locked') {
      return {
        editable: false,
        reason: 'Záznam je schválený nebo uzamčený — úpravy nejsou povoleny.',
      };
    }
    const profile = currentProfile();
    const role = String(profile?.role || '').toLowerCase();
    if (role !== 'service') {
      return { editable: true, reason: null };
    }
    const me = Number(profile?.id || 0);
    const creator = Number(record.created_by_service_customer_id ?? 0);
    if (creator && creator === me) {
      return { editable: true, reason: null };
    }
    if (!creator) {
      return {
        editable: false,
        reason: 'Tento záznam nevznikl v aktuálním servisním workflow tohoto servisního účtu — zobrazení je jen pro čtení.',
      };
    }
    return {
      editable: false,
      reason: 'Servis může upravovat jen vlastní servisní záznamy vytvořené v tomto workflow.',
    };
  }

  function hasFloatingModalSupport() {
    return typeof window.mountFloatingModal === 'function' && typeof window.unmountFloatingModal === 'function';
  }

  function setActiveVehicle(detail) {
    if (!detail || !Number(detail.vehicle_id || detail.id || 0)) {
      state.activeVehicle = null;
      return;
    }
    state.activeVehicle = {
      vehicleId: Number(detail.vehicle_id || detail.id || 0),
      label: detail.nickname || [detail.brand, detail.model].filter(Boolean).join(' ') || detail.vehicle_name || 'Vozidlo',
      vin: detail.vin || detail.vin_masked || '-',
      plate: detail.plate || detail.plate_masked || detail.vehicle_plate || '-',
      accessStatus: accessStatusLabel(detail.status || detail.access_status),
      canCreateWorkOrder: Boolean(detail.can_create_work_order),
      ownerCustomerId: Number(detail.owner_customer_id || detail.customer_id || 0) || null,
      hasQrToken: Boolean(detail.has_qr_token),
      recordsCount: Number(detail.records_count || 0),
    };
  }

  function activeVehicleBanner() {
    if (!isMobileViewport() || !state.activeVehicle) return '';
    const vehicle = state.activeVehicle;
    return `
      <section class="service-shell-mobile-vehicle-card">
        <div class="service-shell-mobile-vehicle-head">
          <div>
            <p class="service-shell-mobile-kicker">Aktivní vozidlo</p>
            <h2>${escape(vehicle.label || 'Vozidlo')}</h2>
          </div>
          <span class="service-shell-badge ${vehicle.canCreateWorkOrder ? 'completed' : 'awaiting'}">${escape(vehicle.accessStatus || 'Přístup')}</span>
        </div>
        <div class="service-shell-mobile-vehicle-meta">
          <span>VIN ${escape(vehicle.vin || '-')}</span>
          <span>SPZ ${escape(vehicle.plate || '-')}</span>
          <span>Záznamy ${escape(String(vehicle.recordsCount || 0))}</span>
        </div>
        <div class="service-shell-mobile-vehicle-actions">
          <button type="button" class="service-shell-filter-chip" onclick="window.serviceShell.openServiceRecordModal(${vehicle.vehicleId})">Nový záznam</button>
          ${vehicle.canCreateWorkOrder ? `<button type="button" class="service-shell-filter-chip" onclick="window.serviceShell.openCreateWorkOrderModal({ ownerId: ${Number(vehicle.ownerCustomerId || 0)}, vehicleId: ${vehicle.vehicleId} })">Nová zakázka</button>` : ''}
          <button type="button" class="service-shell-filter-chip" onclick="window.serviceShell.openVehicleQrModal(${vehicle.vehicleId})">QR</button>
        </div>
      </section>
    `;
  }

  function closeFloatingModal() {
    if (typeof window.unmountFloatingModal === 'function') {
      window.unmountFloatingModal();
    }
  }

  function createEmptyModalState() {
    return {
      open: false,
      key: '',
      entityType: '',
      kicker: '',
      title: '',
      description: '',
      size: 'default',
      loading: false,
      saving: false,
      error: '',
      data: null,
      bodyClass: '',
      allowBackdropClose: true,
      renderContent: null,
      renderFooter: null,
      load: null,
      actions: {},
      actionKey: '',
      context: {},
      entityId: 0,
    };
  }

  function isModalOpen(key = '') {
    return Boolean(state.modal?.open) && (!key || state.modal.key === key);
  }

  function closeModal() {
    state.modal = createEmptyModalState();
    closeFloatingModal();
  }

  function handleModalBackdrop(event) {
    if (event?.target !== event?.currentTarget) return;
    if (!state.modal?.allowBackdropClose || state.modal?.saving) return;
    if (
      state.modal.entityType === 'reminder-overdue' ||
      (typeof state.modal.key === 'string' && state.modal.key.startsWith('reminder-overdue-prompt-'))
    ) {
      dismissOverdueReminderPromptAndContinue();
      return;
    }
    closeModal();
  }

  function modalLoadingState() {
    return `
      <div class="service-shell-modal-state">
        <div class="service-shell-modal-spinner"></div>
        <div>
          <strong>Načítám detail</strong>
          <p>Pracuji nad produkčními servisními daty a ověřuji oprávnění.</p>
        </div>
      </div>
    `;
  }

  function modalErrorState(message) {
    return `
      <div class="service-shell-inline-error service-shell-modal-state service-shell-modal-state-error">
        <div>
          <strong>Nepodařilo se dokončit operaci</strong>
          <p>${escape(message || 'Neznámá chyba')}</p>
        </div>
      </div>
    `;
  }

  function renderMobileModalFooter(buttonsHtml, options = {}) {
    const mobile = isMobileViewport();
    const stack = options.stack !== false;
    const mobileCls = mobile
      ? (stack ? ' service-shell-mobile-action-bar service-shell-mobile-action-bar--stack' : ' service-shell-mobile-action-bar')
      : '';
    return `<div class="service-shell-modal-footer${mobileCls}">${buttonsHtml}</div>`;
  }

  let mobileViewportListenerBound = false;

  function bindMobileViewportListenerOnce() {
    if (mobileViewportListenerBound || typeof window.matchMedia !== 'function') return;
    mobileViewportListenerBound = true;
    const mq = window.matchMedia('(max-width: 900px)');
    const onChange = () => {
      if (!state.mounted) return;
      state.mobileNavOpen = false;
      state.filterSheetOpen = false;
      state.accountMenuOpen = false;
      render();
    };
    if (typeof mq.addEventListener === 'function') {
      mq.addEventListener('change', onChange);
    } else if (typeof mq.addListener === 'function') {
      mq.addListener(onChange);
    }
  }

  function renderModalFooter() {
    if (!state.modal?.open) return '';
    if (typeof state.modal.renderFooter === 'function') {
      try {
        return state.modal.renderFooter(state.modal) || '';
      } catch (error) {
        console.error('[SERVICE_SHELL] modal renderFooter failed:', error);
        return `
      <div class="service-shell-modal-footer">
        <p class="service-shell-inline-error" style="margin:0 0 8px;">Patka modálu selhala: ${escape(String(error?.message || error))}</p>
        <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zavřít</button>
      </div>
    `;
      }
    }
    return `
      <div class="service-shell-modal-footer">
        <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zavřít</button>
      </div>
    `;
  }

  function renderModalContent() {
    if (!state.modal?.open) return '';
    if (state.modal.loading) return modalLoadingState();
    if (state.modal.error) return modalErrorState(state.modal.error);
    if (typeof state.modal.renderContent === 'function') {
      try {
        return state.modal.renderContent(state.modal) || '';
      } catch (error) {
        console.error('[SERVICE_SHELL] modal renderContent failed:', error);
        return modalErrorState(error?.message || 'Chyba vykreslení modálu');
      }
    }
    return '';
  }

  function renderModal() {
    if (!state.modal?.open || !hasFloatingModalSupport()) return;
    const sizeClass = state.modal.size === 'wide' ? 'service-shell-modal--wide' : '';
    const bodyClass = state.modal.bodyClass ? ` ${state.modal.bodyClass}` : '';
    const mobileClass = isMobileViewport() ? ' service-shell-modal--mobile-flow' : '';
    window.mountFloatingModal(`
      <div class="service-shell-modal-overlay" onclick="window.serviceShell.handleModalBackdrop(event)">
        <div class="service-shell-modal ${sizeClass}${mobileClass}">
          <div class="service-shell-modal-header">
            <div class="service-shell-modal-heading">
              ${state.modal.kicker ? `<p class="service-shell-modal-kicker">${escape(state.modal.kicker)}</p>` : ''}
              <h2 class="service-shell-modal-title">${escape(state.modal.title || 'Detail')}</h2>
              ${state.modal.description ? `<p class="service-shell-modal-description">${escape(state.modal.description)}</p>` : ''}
            </div>
            <button type="button" class="service-shell-modal-close" aria-label="Zavřít okno" onclick="window.serviceShell.closeModal()">×</button>
          </div>
          <div class="service-shell-modal-body${bodyClass}">
            ${renderModalContent()}
          </div>
          ${renderModalFooter()}
        </div>
      </div>
    `);
  }

  function setModalState(patch = {}) {
    state.modal = {
      ...(state.modal || createEmptyModalState()),
      ...patch,
    };
    renderModal();
  }

  async function reloadModalData() {
    if (!state.modal?.open || typeof state.modal.load !== 'function') return;
    const token = Date.now();
    state.modal.loadToken = token;
    setModalState({ loading: true, error: '' });
    try {
      const data = await state.modal.load(state.modal);
      if (!isModalOpen() || state.modal.loadToken !== token) return;
      setModalState({ loading: false, error: '', data });
    } catch (error) {
      if (!isModalOpen() || state.modal.loadToken !== token) return;
      setModalState({
        loading: false,
        data: null,
        error: error?.message || 'Neznámá chyba',
      });
    }
  }

  function openModal(config = {}) {
    if (!hasFloatingModalSupport()) return false;
    state.modal = {
      ...createEmptyModalState(),
      ...config,
      open: true,
      loading: typeof config.load === 'function',
      error: '',
      data: config.data ?? null,
      actions: config.actions || {},
      context: config.context || {},
    };
    renderModal();
    if (typeof config.load === 'function') {
      reloadModalData();
    }
    return true;
  }

  function normalizeQueuePayload(payload) {
    const queue = payload && typeof payload === 'object' ? { ...payload } : {};
    const alerts = Array.isArray(queue.alerts) ? queue.alerts : [];
    const alertCount = (key) => Number(alerts.find((item) => item?.key === key)?.count || 0);
    return {
      ...queue,
      new_jobs: Number(queue.new_jobs ?? queue.new_orders ?? queue.new_work_orders ?? 0),
      new_orders: Number(queue.new_orders ?? queue.new_jobs ?? queue.new_work_orders ?? 0),
      awaiting_approval: Number(queue.awaiting_approval || 0),
      missing_documents: Number(queue.missing_documents || 0),
      conflicting_data: Number(queue.conflicting_data || 0),
      missing_client_consent: Number(queue.missing_client_consent ?? alertCount('missing_client_consent')),
      suspicious_km: Number(queue.suspicious_km ?? alertCount('suspicious_km')),
      unfinished_jobs: Number(queue.unfinished_jobs ?? alertCount('unfinished_jobs')),
      internal_warnings: Number(queue.internal_warnings || 0),
      alerts,
    };
  }

  async function refreshAfterModalAction() {
    await load(true, true);
  }

  async function runModalAction(actionKey) {
    const action = state.modal?.actions?.[actionKey];
    if (typeof action !== 'function' || state.modal?.saving) return;
    state.modal = {
      ...(state.modal || createEmptyModalState()),
      saving: true,
      error: '',
      actionKey,
    };
    try {
      const result = await action(state.modal);
      if (!isModalOpen()) return;
      if (result && Object.prototype.hasOwnProperty.call(result, 'data')) {
        state.modal.data = result.data;
      }
      if (result?.contextPatch && typeof result.contextPatch === 'object') {
        state.modal.context = {
          ...(state.modal.context || {}),
          ...result.contextPatch,
        };
      }
      if (result?.reloadDetail) {
        await reloadModalData();
      }
      if (result?.refreshParent) {
        await refreshAfterModalAction();
      }
      if (result && Object.prototype.hasOwnProperty.call(result, 'error')) {
        setModalState({
          saving: false,
          actionKey: '',
          error: result.error || '',
        });
        if (result?.message) {
          showToast(result.message, result.messageType || 'warning');
        }
        return;
      }
      if (result?.message) {
        showToast(result.message, result.messageType || 'success');
      }
      if (result?.close === false) {
        setModalState({ saving: false, actionKey: '' });
        return;
      }
      closeModal();
    } catch (error) {
      showToast(error?.message || 'Neznámá chyba', 'error');
      setModalState({
        saving: false,
        actionKey: '',
        error: error?.message || 'Neznámá chyba',
      });
    }
  }

  function parkLegacyNode(target) {
    if (parkedLegacyNodes.has(target.key)) return;
    const node = document.querySelector(target.selector);
    if (!node || !node.parentNode) return;
    const placeholder = document.createComment(`service-shell:${target.key}`);
    node.parentNode.replaceChild(placeholder, node);
    parkedLegacyNodes.set(target.key, { node, placeholder });
  }

  function restoreLegacyNode(key) {
    const parked = parkedLegacyNodes.get(key);
    if (!parked || !parked.placeholder.parentNode) return;
    parked.placeholder.parentNode.replaceChild(parked.node, parked.placeholder);
    parkedLegacyNodes.delete(key);
  }

  function parkLegacyDom() {
    legacyTargets.forEach(parkLegacyNode);
  }

  function restoreLegacyDom() {
    legacyTargets.slice().reverse().forEach((target) => restoreLegacyNode(target.key));
  }

  function applyTheme(theme) {
    state.theme = theme === 'light' ? 'light' : 'dark';
    safeStorageSet(themeKey, state.theme);
    document.body.classList.add('service-shell-app');
    document.body.classList.remove('app-ui-theme-dark', 'app-ui-theme-light');
    document.body.classList.toggle('service-shell-theme-light', state.theme === 'light');
  }

  function unapplyTheme() {
    document.body.classList.remove('service-shell-app');
    document.body.classList.remove('service-shell-theme-light');
  }

  function applyAppUiThemeFromStorage() {
    if (document.body.classList.contains('service-shell-app')) {
      return;
    }
    const isDark = safeStorageGet(themeKey) === 'dark';
    document.body.classList.toggle('app-ui-theme-dark', isDark);
    const btn = document.getElementById('appThemeToggleBtn');
    if (btn) btn.textContent = isDark ? '☀' : '☾';
  }

  function toggleAppUiTheme() {
    const next = safeStorageGet(themeKey) === 'dark' ? 'light' : 'dark';
    if (state.mounted && document.body.classList.contains('service-shell-app')) {
      setTheme(next);
      const btn = document.getElementById('appThemeToggleBtn');
      if (btn) btn.textContent = next === 'dark' ? '☀' : '☾';
      return;
    }
    safeStorageSet(themeKey, next);
    applyAppUiThemeFromStorage();
  }

  function stopAutoRefresh() {
    if (state.autoRefreshHandle) {
      window.clearInterval(state.autoRefreshHandle);
      state.autoRefreshHandle = 0;
    }
  }

  function ensureAutoRefresh() {
    stopAutoRefresh();
    state.autoRefreshHandle = window.setInterval(() => {
      if (!state.mounted || !isServiceRole()) return;
      load(true, true).catch((error) => {
        console.warn('[SERVICE_SHELL] auto refresh failed:', error?.message || error);
      });
    }, autoRefreshMs);
  }

  const LIMITED_WORKSPACE_SECTIONS = new Set(['photos', 'parts', 'audit', 'settings']);

  function mapSection(tab) {
    const key = String(tab || '').trim().toLowerCase();
    if (serviceSections.has(key)) return key;
    if (key === 'home') return 'dashboard';
    if (key === 'prijem' || key === 'intake') return 'intake';
    if (key === 'servicesdirectory' || key === 'clients' || key === 'customers') return 'clients';
    if (key === 'vehicles') return 'vehicles';
    if (key === 'serviceworkspace' || key === 'workorders' || key === 'work-orders') return 'work-orders';
    if (key === 'photos' || key === 'fotodokumentace') return 'photos';
    if (key === 'history') return 'history';
    if (key === 'parts' || key === 'parts-stock') return 'parts';
    if (key === 'audit' || key === 'audit-security') return 'audit';
    if (key === 'settings') return 'settings';
    if (key === 'documents') return 'documents';
    if (key === 'invoices' || key === 'billing' || key === 'quotes') return 'invoices';
    if (key === 'reservations') return 'reservations';
    if (key === 'reminders') return 'reminders';
    if (key === 'account' || key === 'team') return 'team';
    if (key === 'support') return 'dashboard';
    return '';
  }

  function readServiceSectionFromLocation() {
    try {
      if (typeof window.parseAppWorkspaceRoute !== 'function') return defaultSection;
      const parsed = window.parseAppWorkspaceRoute(window.location.pathname);
      if (!parsed || String(parsed.routeToken || '').toLowerCase() !== 's') return defaultSection;
      if (typeof window.serviceShellSectionFromUrlSection === 'function') {
        return mapSection(window.serviceShellSectionFromUrlSection(parsed.section)) || defaultSection;
      }
      return mapSection(parsed.section) || defaultSection;
    } catch (err) {
      console.warn('[SERVICE_SHELL] readServiceSectionFromLocation failed:', err);
      return defaultSection;
    }
  }

  function reconcileUnknownServiceRouteUrl() {
    try {
      if (typeof window.parseAppWorkspaceRoute !== 'function') return;
      const parsed = window.parseAppWorkspaceRoute(window.location.pathname);
      if (!parsed || String(parsed.routeToken || '').toLowerCase() !== 's') return;
      const raw = String(parsed.section || '').toLowerCase();
      if (!raw || typeof window.isKnownServiceUrlSection !== 'function' || window.isKnownServiceUrlSection(raw)) {
        return;
      }
      if (typeof window.warnUnknownServiceRoute === 'function') {
        window.warnUnknownServiceRoute(raw);
      }
      state.activeSection = 'dashboard';
      render();
      if (typeof window.syncWorkspaceHistoryFromServiceShell === 'function') {
        window.syncWorkspaceHistoryFromServiceShell('dashboard', { replaceHistory: true });
      } else if (typeof window.workspaceHistoryReplace === 'function' && typeof window.buildAppWorkspacePath === 'function') {
        window.workspaceHistoryReplace(window.buildAppWorkspacePath('s', parsed.slug, 'dashboard'));
      }
      load(true, false);
    } catch (err) {
      console.warn('[SERVICE_SHELL] reconcileUnknownServiceRouteUrl failed:', err);
    }
  }

  function showAppShellForService() {
    if (typeof window.setPublicPageMode === 'function') {
      window.setPublicPageMode('app');
      return;
    }
    const appShell = document.getElementById('app-shell');
    if (appShell) appShell.style.display = '';
    document.body.classList.remove('route-home-view', 'route-login-view', 'route-register-view');
    document.body.classList.add('route-app-view');
  }

  function mountShellFailsafe(error) {
    console.error('[SERVICE_SHELL] mount failsafe:', error);
    try {
      showAppShellForService();
      const root = document.getElementById(rootId);
      if (root) {
        root.classList.remove('hidden');
        root.innerHTML = `
          <div class="service-shell-root" data-service-shell="root" style="min-height:60vh;padding:24px;background:#111315;color:#f5f7fb;">
            <h1 style="font-size:1.2rem;margin:0 0 12px;">Chyba načtení aplikace</h1>
            <p style="opacity:0.85;margin:0 0 16px;">Servisní rozhraní se nepodařilo spustit. Zkuste obnovit stránku nebo kontaktujte správce.</p>
            <pre style="white-space:pre-wrap;font-size:12px;opacity:0.75;">${escape(String(error?.message || error || ''))}</pre>
            <button type="button" class="btn btn-primary" style="margin-top:16px;" onclick="window.location.reload()">Obnovit stránku</button>
          </div>`;
      }
    } catch (e2) {
      console.error('[SERVICE_SHELL] failsafe render failed:', e2);
    }
  }

  function init(options) {
    console.log('[SERVICE_SHELL] INIT START', options || {});
    return mount(options || {});
  }

  function mount(options = {}) {
    console.log('[SERVICE_SHELL] MOUNT START', {
      isServiceRole: isServiceRole(),
      hasSetPublicPageMode: typeof window.setPublicPageMode === 'function',
    });
    if (!isServiceRole()) {
      console.warn('[SERVICE_SHELL] MOUNT skipped (not service workspace role)');
      return;
    }
    try {
      showAppShellForService();
      if (typeof window.applyServiceDashboardAppChrome === 'function') {
        window.applyServiceDashboardAppChrome(false);
      }
      document.body.classList.remove('service-dashboard-app', 'service-dashboard-theme-light');
      const root = getRoot();
      if (!root) {
        throw new Error('Element #serviceAppRoot neexistuje — zkontrolujte šablonu index.html');
      }
      const authSection = document.getElementById('authSection');
      if (authSection) {
        authSection.classList.add('hidden');
        authSection.style.display = 'none';
      }
      parkLegacyDom();
      root.classList.remove('hidden');
      state.mounted = true;
      state.activeSection = mapSection(options.section) || readServiceSectionFromLocation() || defaultSection;
      state.theme = safeStorageGet(themeKey) === 'dark' ? 'dark' : 'light';
      applyTheme(state.theme);
      bindNavOutsideCloseOnce();
      bindMobileViewportListenerOnce();
      render();
      reconcileUnknownServiceRouteUrl();
      if (!options.skipLoad) {
        load(false, false).catch((error) => {
          console.error('[SERVICE_SHELL] mount load failed:', error);
          if (typeof window.showAlert === 'function') {
            window.showAlert(`Nepodařilo se načíst servisní workspace: ${error.message || 'Neznámá chyba'}`, 'error');
          }
        });
      }
      window.setTimeout(() => {
        try {
          reconcileUnknownServiceRouteUrl();
        } catch (e) {
          /* ignore */
        }
      }, 0);
      console.log('[SERVICE_SHELL] MOUNT OK');
    } catch (error) {
      mountShellFailsafe(error);
    }
  }

  function unmount() {
    stopAutoRefresh();
    state.mounted = false;
    state.mobileNavOpen = false;
    state.accountMenuOpen = false;
    syncMobileNavScrollLock();
    removeRemindersOverdueOverlayMount();
    const root = getRoot();
    if (root) {
      root.classList.add('hidden');
      root.innerHTML = '';
    }
    restoreLegacyDom();
    unapplyTheme();
    applyAppUiThemeFromStorage();
  }

  async function load(force = false, silent = false) {
    if (!isServiceRole()) {
      if (typeof originalLoadServiceWorkspace === 'function') {
        return originalLoadServiceWorkspace.apply(this, arguments);
      }
      return;
    }

    const now = Date.now();
    if (!force && state.lastLoadedAt && now - state.lastLoadedAt < dataTtlMs && !silent) {
      render();
      ensureAutoRefresh();
      return;
    }

    state.loading = true;
    if (!silent) render();

    try {
      if (typeof window.apiCall !== 'function') {
        throw new Error('window.apiCall není k dispozici — zkontrolujte načtení sdílených skriptů.');
      }

      const requestFactories = {
        me: () => window.apiCall('/api/me', 'GET').catch((err) => {
          console.warn('[SERVICE_SHELL] /api/me:', err?.message || err);
          return {};
        }),
        summary: () => window.apiCall('/api/service/dashboard/summary', 'GET'),
        dashboardOverview: () => window.apiCall('/api/service/dashboard/overview', 'GET').catch((err) => {
          console.warn('[SERVICE_SHELL] dashboard overview fallback:', err?.message || err);
          return null;
        }),
        dashboardWorkOrders: () => window.apiCall('/api/service/dashboard/work-orders?status=open&limit=10', 'GET').catch((err) => {
          console.warn('[SERVICE_SHELL] dashboard work-orders fallback:', err?.message || err);
          return { items: [] };
        }),
        pendingAuthorizations: () => window.apiCall('/api/service/dashboard/pending-authorizations', 'GET').catch((err) => {
          console.warn('[SERVICE_SHELL] pending authorizations fallback:', err?.message || err);
          return { items: [] };
        }),
        todayReservations: () => window.apiCall('/api/service/dashboard/today-reservations', 'GET').catch((err) => {
          console.warn('[SERVICE_SHELL] today reservations fallback:', err?.message || err);
          return { items: [] };
        }),
        dashboardRisks: () => window.apiCall('/api/service/dashboard/risks', 'GET').catch((err) => {
          console.warn('[SERVICE_SHELL] risks fallback:', err?.message || err);
          return { items: [] };
        }),
        workOrders: () => window.apiCall('/api/service/work-orders', 'GET'),
        performance: () => window.apiCall('/api/service/technicians/performance', 'GET'),
        queue: () => window.apiCall('/api/service/dashboard/queue', 'GET'),
        customers: () => window.apiCall('/api/v1/services/workspace/customers', 'GET'),
        vehicles: () => window.apiCall('/api/v1/services/workspace/approved-vehicles', 'GET'),
        reservations: () => window.apiCall('/api/v1/reservations/service', 'GET'),
        reminders: () => window.apiCall('/api/v1/services/workspace/reminders?include_completed=true&limit=500', 'GET'),
        documents: () => window.apiCall('/api/v1/services/workspace/documents?limit=50', 'GET'),
        invoices: () => window.apiCall('/api/service/invoices', 'GET').catch((err) => {
          console.warn('[SERVICE_SHELL] invoices endpoint:', err?.message || err);
          return { items: [] };
        }),
        quotes: () => window.apiCall('/api/service/quotes', 'GET').catch((err) => {
          console.warn('[SERVICE_SHELL] quotes endpoint:', err?.message || err);
          return { items: [] };
        }),
        profile: () => window.apiCall('/user/me', 'GET'),
        partnerProfile: () => window.apiCall('/api/v1/services/workspace/partner-public-profile', 'GET').catch((err) => {
          console.warn('[SERVICE_SHELL] partner-public-profile:', err?.message || err);
          return {};
        }),
      };

      const applyPayload = (key, payload) => {
        if (key === 'me' && payload && typeof payload === 'object') state.me = payload;
        if (key === 'summary') state.summary = payload || null;
        if (key === 'dashboardOverview') state.dashboardOverview = payload || null;
        if (key === 'dashboardWorkOrders') state.dashboardWorkOrders = Array.isArray(payload?.items) ? payload.items : [];
        if (key === 'pendingAuthorizations') state.pendingAuthorizations = Array.isArray(payload?.items) ? payload.items : [];
        if (key === 'todayReservations') state.todayReservations = Array.isArray(payload?.items) ? payload.items : [];
        if (key === 'dashboardRisks') state.dashboardRisks = Array.isArray(payload?.items) ? payload.items : [];
        if (key === 'workOrders') state.workOrders = Array.isArray(payload?.items) ? payload.items : [];
        if (key === 'performance') state.performance = Array.isArray(payload?.items) ? payload.items : [];
        if (key === 'queue') state.queue = normalizeQueuePayload(payload);
        if (key === 'customers') state.customers = Array.isArray(payload) ? payload : [];
        if (key === 'vehicles') state.vehicles = Array.isArray(payload?.items) ? payload.items : [];
        if (key === 'reservations') state.reservations = Array.isArray(payload) ? payload : [];
        if (key === 'reminders') state.reminders = Array.isArray(payload) ? payload : [];
        if (key === 'documents') state.documents = Array.isArray(payload) ? payload : [];
        if (key === 'invoices') state.invoices = Array.isArray(payload?.items) ? payload.items : [];
        if (key === 'quotes') state.quotes = Array.isArray(payload?.items) ? payload.items : [];
        if (key === 'profile') state.profile = payload || {};
        if (key === 'partnerProfile') state.partnerPublicProfile = payload && typeof payload === 'object' ? payload : {};
      };

      const applyTechnicians = () => {
        const perf = Array.isArray(state.performance) ? state.performance : [];
        state.technicians = perf
          .map((item) => ({
            technician_id: Number(item?.technician_id || 0),
            name: item?.name || `Technik #${Number(item?.technician_id || 0)}`,
          }))
          .filter((item) => item.technician_id > 0);

        if (!state.technicians.length && window.currentUser?.id) {
          state.technicians = [{
            technician_id: Number(window.currentUser.id),
            name: window.currentUser?.name || window.currentUser?.email || 'Hlavní technik',
          }];
        }
      };

      const runRequestBatch = async (keys, collectErrors = true) => {
        const results = await Promise.allSettled(keys.map((key) => requestFactories[key]()));
        results.forEach((result, index) => {
          const key = keys[index];
          if (result.status !== 'fulfilled') {
            if (collectErrors) state.errors.push(`${key}: ${result.reason?.message || 'chyba načtení'}`);
            return;
          }
          applyPayload(key, result.value);
        });
        applyTechnicians();
      };

      const dashboardKeys = [
        'me',
        'summary',
        'dashboardOverview',
        'dashboardWorkOrders',
        'pendingAuthorizations',
        'todayReservations',
        'dashboardRisks',
      ];
      const sectionKeyMap = {
        'work-orders': ['workOrders', 'queue', 'performance'],
        vehicles: ['vehicles', 'customers'],
        clients: ['customers', 'vehicles'],
        reservations: ['reservations'],
        reminders: ['reminders'],
        documents: ['documents'],
        invoices: ['invoices', 'quotes', 'customers', 'vehicles'],
        history: ['vehicles', 'customers'],
        photos: ['vehicles', 'customers'],
        intake: ['customers', 'vehicles'],
        team: ['performance'],
        settings: ['profile', 'partnerProfile'],
      };
      const primaryKeys = Array.from(new Set([
        ...dashboardKeys,
        ...(sectionKeyMap[state.activeSection] || []),
      ]));

      state.errors = [];
      await runRequestBatch(primaryKeys, true);

      const secondaryKeys = Object.keys(requestFactories).filter((key) => !primaryKeys.includes(key));
      window.setTimeout(() => {
        runRequestBatch(secondaryKeys, false)
          .then(() => {
            state.lastLoadedAt = Date.now();
            refreshShellAfterDataLoad(silent, { backgroundOnly: true });
          })
          .catch((err) => {
            console.warn('[SERVICE_SHELL] background load failed:', err?.message || err);
          });
      }, silent ? 0 : 120);

      window.serviceWorkspaceState = window.serviceWorkspaceState || {};
      window.serviceWorkspaceState.customerVehicles = {};

      state.lastLoadedAt = Date.now();
      if (state.errors.length && !silent && typeof window.showAlert === 'function') {
        window.showAlert(`Některé servisní sekce se načetly jen částečně: ${state.errors[0]}`, 'warning');
      }
    } catch (error) {
      console.error('[SERVICE_SHELL] load failed:', error);
      state.errors = state.errors || [];
      state.errors.push(String(error?.message || error || 'load'));
      if (!silent && typeof window.showAlert === 'function') {
        window.showAlert(`Servisní data se nepodařilo načíst: ${error?.message || 'Neznámá chyba'}`, 'error');
      }
    } finally {
      state.loading = false;
      refreshShellAfterDataLoad(silent);
      ensureAutoRefresh();
    }
  }

  function navigate(section, options = {}) {
    closeNavFlyouts();
    const rawSection = String(section || '').trim().toLowerCase();
    if (
      rawSection
      && typeof window.isKnownServiceUrlSection === 'function'
      && !window.isKnownServiceUrlSection(rawSection)
    ) {
      if (typeof window.warnUnknownServiceRoute === 'function') {
        window.warnUnknownServiceRoute(rawSection);
      }
      section = 'dashboard';
      options = { ...options, replaceHistory: true };
    }
    const next = mapSection(section) || defaultSection;
    const prevSection = state.activeSection;
    state.accountMenuOpen = false;
    state.mobileNavOpen = false;
    state.filterSheetOpen = false;
    if (prevSection !== 'reminders' && next === 'reminders') {
      resetRemindersSectionOverdueSkips();
    }
    state.activeSection = next;
    if (typeof options.kpiFilter === 'string') {
      state.kpiFilter = options.kpiFilter;
      if (next !== 'dashboard') {
        state.activeSection = 'dashboard';
      }
    }
    render();
    if (String(next || '').startsWith('payroll-')) {
      window.setTimeout(() => {
        try {
          window.serviceShell.refreshPayrollModule(true);
        } catch (e) {
          console.warn('[SERVICE_SHELL] payroll refresh failed', e);
        }
      }, 0);
    }
    if (typeof window.syncWorkspaceHistoryFromServiceShell === 'function') {
      window.syncWorkspaceHistoryFromServiceShell(next, options);
    }
    if (options.forceLoad || prevSection !== next) {
      load(true, false);
    }
  }

  function payrollResolveApiBase() {
    if (typeof window.getApiBaseUrl === 'function') {
      const u = window.getApiBaseUrl();
      if (u) return String(u).replace(/\/$/, '');
    }
    return String(window.location.origin || '').replace(/\/$/, '');
  }

  function payrollAuthHeadersForBlob() {
    const headers = {
      Accept: '*/*',
      'Accept-Language': 'cs-CZ,cs;q=0.9,en;q=0.8',
    };
    if (typeof window.location !== 'undefined') {
      headers.Referer = window.location.origin + window.location.pathname;
    }
    let tok = null;
    try {
      tok =
        (typeof localStorage !== 'undefined' && localStorage.getItem('accessToken')) ||
        (typeof sessionStorage !== 'undefined' && sessionStorage.getItem('accessToken')) ||
        (typeof localStorage !== 'undefined' && localStorage.getItem('token'));
    } catch (e) {
      tok = null;
    }
    if (tok) headers.Authorization = `Bearer ${tok}`;
    else if (window.currentUser && window.currentUser.email) headers['X-User-Email'] = window.currentUser.email;
    return headers;
  }

  function payrollTriggerDownload(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || 'download';
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  async function payrollFetchBlob(path) {
    const base = payrollResolveApiBase();
    const url = `${base}${path}`;
    const r = await fetch(url, {
      method: 'GET',
      credentials: 'include',
      headers: payrollAuthHeadersForBlob(),
      cache: 'no-cache',
      mode: 'cors',
    });
    if (!r.ok) {
      let msg = `HTTP ${r.status}`;
      try {
        const ct = r.headers.get('content-type') || '';
        if (ct.includes('application/json')) {
          const j = await r.json();
          msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail || j);
        } else {
          const t = await r.text();
          if (t) msg = t.slice(0, 500);
        }
      } catch (e) {
        /* ignore */
      }
      throw new Error(msg);
    }
    let filename = 'download';
    const cd = r.headers.get('Content-Disposition');
    if (cd) {
      const m = /filename\*?=(?:UTF-8'')?["']?([^"';]+)/i.exec(cd);
      if (m && m[1]) filename = decodeURIComponent(m[1].trim());
    }
    const blob = await r.blob();
    return { blob, filename };
  }

  async function refreshPayrollModule() {
    if (typeof window.apiCall !== 'function') {
      state.payrollError = 'Chybí window.apiCall — nelze načíst mzdy.';
      render();
      return;
    }
    const y = state.payrollPeriod.year;
    const m = state.payrollPeriod.month;
    state.payrollLoading = true;
    state.payrollError = '';
    render();
    try {
      const [offices, employees, attendance, payslips, journal, jmhz] = await Promise.all([
        window.apiCall('/api/service/payroll/offices', 'GET'),
        window.apiCall('/api/service/payroll/employees', 'GET'),
        window.apiCall(`/api/service/payroll/attendance?year=${y}&month=${m}`, 'GET'),
        window.apiCall(`/api/service/payroll/payslips?year=${y}&month=${m}`, 'GET'),
        window.apiCall(`/api/service/payroll/journal?year=${y}&month=${m}`, 'GET'),
        window.apiCall('/api/service/payroll/jmhz', 'GET'),
      ]);
      state.payrollData = { offices, employees, attendance, payslips, journal, jmhz };
    } catch (error) {
      state.payrollError = String(error?.message || error || 'Chyba načtení mzdového modulu');
      console.warn('[SERVICE_SHELL] refreshPayrollModule', error);
    } finally {
      state.payrollLoading = false;
      render();
    }
  }

  function setPayrollPeriod(year, month) {
    state.payrollPeriod.year = Math.max(2000, Math.min(2100, Number(year) || new Date().getFullYear()));
    state.payrollPeriod.month = Math.max(1, Math.min(12, Number(month) || 1));
    render();
    refreshPayrollModule();
  }

  async function patchPayrollAttendance(attendanceId, patch) {
    if (typeof window.apiCall !== 'function') return;
    try {
      await window.apiCall(`/api/service/payroll/attendance/${Number(attendanceId)}`, 'PUT', patch);
      await refreshPayrollModule();
    } catch (error) {
      state.payrollError = String(error?.message || error || 'Úprava docházky selhala');
      render();
      if (typeof window.showAlert === 'function') window.showAlert(state.payrollError, 'error');
    }
  }

  async function generatePayrollAttendanceMonth() {
    if (typeof window.apiCall !== 'function') return;
    const y = state.payrollPeriod.year;
    const m = state.payrollPeriod.month;
    try {
      await window.apiCall(`/api/service/payroll/attendance/generate?year=${y}&month=${m}`, 'POST');
      await refreshPayrollModule();
    } catch (error) {
      state.payrollError = String(error?.message || error || 'Generování docházky selhalo');
      render();
      if (typeof window.showAlert === 'function') window.showAlert(state.payrollError, 'error');
    }
  }

  async function generatePayrollPayslipsMonth() {
    if (typeof window.apiCall !== 'function') return;
    const y = state.payrollPeriod.year;
    const m = state.payrollPeriod.month;
    try {
      await window.apiCall(`/api/service/payroll/payslips/generate?year=${y}&month=${m}`, 'POST');
      await refreshPayrollModule();
    } catch (error) {
      state.payrollError = String(error?.message || error || 'Generování listů selhalo');
      render();
      if (typeof window.showAlert === 'function') window.showAlert(state.payrollError, 'error');
    }
  }

  async function recalculatePayrollPayslip(payslipId) {
    if (typeof window.apiCall !== 'function') return;
    try {
      await window.apiCall(`/api/service/payroll/payslips/${Number(payslipId)}/recalculate`, 'POST');
      await refreshPayrollModule();
    } catch (error) {
      state.payrollError = String(error?.message || error || 'Přepočet selhal');
      render();
      if (typeof window.showAlert === 'function') window.showAlert(state.payrollError, 'error');
    }
  }

  async function closePayrollPayslip(payslipId) {
    if (typeof window.apiCall !== 'function') return;
    try {
      await window.apiCall(`/api/service/payroll/payslips/${Number(payslipId)}/close`, 'POST');
      await refreshPayrollModule();
    } catch (error) {
      state.payrollError = String(error?.message || error || 'Uzavření listu selhalo');
      render();
      if (typeof window.showAlert === 'function') window.showAlert(state.payrollError, 'error');
    }
  }

  async function refreshPayrollJournal() {
    if (typeof window.apiCall !== 'function') return;
    const y = state.payrollPeriod.year;
    const m = state.payrollPeriod.month;
    try {
      await window.apiCall(`/api/service/payroll/journal/refresh?year=${y}&month=${m}`, 'POST');
      await refreshPayrollModule();
    } catch (error) {
      state.payrollError = String(error?.message || error || 'Obnova deníku selhala');
      render();
      if (typeof window.showAlert === 'function') window.showAlert(state.payrollError, 'error');
    }
  }

  async function exportPayrollJournalCsv() {
    const y = state.payrollPeriod.year;
    const m = state.payrollPeriod.month;
    try {
      const { blob, filename } = await payrollFetchBlob(
        `/api/service/payroll/journal/export-payments?year=${y}&month=${m}`,
      );
      payrollTriggerDownload(blob, filename || `payroll_payments_${y}_${String(m).padStart(2, '0')}.csv`);
      await refreshPayrollModule();
    } catch (error) {
      state.payrollError = String(error?.message || error || 'Export CSV selhal');
      render();
      if (typeof window.showAlert === 'function') window.showAlert(state.payrollError, 'error');
    }
  }

  async function createPayrollJmhz(officeIdRaw) {
    if (typeof window.apiCall !== 'function') return;
    const oid = Number(officeIdRaw);
    if (!oid) {
      state.payrollError = 'Vyberte účtárnu.';
      render();
      return;
    }
    const y = state.payrollPeriod.year;
    const m = state.payrollPeriod.month;
    try {
      await window.apiCall(`/api/service/payroll/jmhz?office_id=${oid}&year=${y}&month=${m}&typ=hlaseni`, 'POST');
      navigate('payroll-cssz');
      await refreshPayrollModule();
    } catch (error) {
      state.payrollError = String(error?.message || error || 'Založení podání selhalo');
      render();
      if (typeof window.showAlert === 'function') window.showAlert(state.payrollError, 'error');
    }
  }

  async function buildPayrollJmhzZip(submissionId) {
    if (typeof window.apiCall !== 'function') return;
    try {
      await window.apiCall(`/api/service/payroll/jmhz/${Number(submissionId)}/build-zip`, 'POST');
      await refreshPayrollModule();
    } catch (error) {
      state.payrollError = String(error?.message || error || 'Sestavení ZIP selhalo');
      render();
      if (typeof window.showAlert === 'function') window.showAlert(state.payrollError, 'error');
    }
  }

  async function downloadPayrollJmhz(submissionId) {
    try {
      const { blob, filename } = await payrollFetchBlob(`/api/service/payroll/jmhz/${Number(submissionId)}/download`);
      payrollTriggerDownload(blob, filename || `jmhz_${submissionId}.zip`);
    } catch (error) {
      state.payrollError = String(error?.message || error || 'Stažení ZIP selhalo');
      render();
      if (typeof window.showAlert === 'function') window.showAlert(state.payrollError, 'error');
    }
  }

  async function submitPayrollOfficeCreate(event) {
    event.preventDefault();
    if (typeof window.apiCall !== 'function') return;
    const fd = new FormData(event.target);
    const name = String(fd.get('name') || '').trim();
    try {
      await window.apiCall('/api/service/payroll/offices', 'POST', {
        name,
        vs_cssz: String(fd.get('vs_cssz') || '').trim() || null,
        datovka_id: String(fd.get('datovka_id') || '').trim() || null,
        is_active: true,
      });
      navigate('payroll-offices');
      await refreshPayrollModule();
    } catch (error) {
      state.payrollError = String(error?.message || error || 'Uložení účtárny selhalo');
      render();
      if (typeof window.showAlert === 'function') window.showAlert(state.payrollError, 'error');
    }
  }

  async function submitPayrollEmployeeCreate(event) {
    event.preventDefault();
    if (typeof window.apiCall !== 'function') return;
    const fd = new FormData(event.target);
    const primaryOfficeRaw = fd.get('primary_office_id');
    try {
      await window.apiCall('/api/service/payroll/employees', 'POST', {
        first_name: String(fd.get('first_name') || '').trim(),
        last_name: String(fd.get('last_name') || '').trim(),
        birth_date: String(fd.get('birth_date') || ''),
        primary_office_id: primaryOfficeRaw ? Number(primaryOfficeRaw) : null,
        hourly_gross_rate: fd.get('hourly_gross_rate') ? Number(fd.get('hourly_gross_rate')) : null,
        contract_hours_per_week: fd.get('contract_hours_per_week') ? Number(fd.get('contract_hours_per_week')) : null,
        health_insurance_code: String(fd.get('health_insurance_code') || '').trim() || null,
        email: String(fd.get('email') || '').trim() || null,
        phone: String(fd.get('phone') || '').trim() || null,
        birth_number: String(fd.get('birth_number') || '').trim() || null,
        iban: String(fd.get('iban') || '').trim() || null,
      });
      navigate('payroll-employees');
      await refreshPayrollModule();
    } catch (error) {
      state.payrollError = String(error?.message || error || 'Uložení zaměstnance selhalo');
      render();
      if (typeof window.showAlert === 'function') window.showAlert(state.payrollError, 'error');
    }
  }

  async function openPayrollEmployeeDetail(employeeId) {
    if (typeof window.apiCall !== 'function') return;
    try {
      state.payrollEmployeeDetailCache = await window.apiCall(
        `/api/service/payroll/employees/${Number(employeeId)}`,
        'GET',
      );
      state.payrollDetailEmployeeId = Number(employeeId);
      navigate('payroll-employee-detail');
    } catch (error) {
      state.payrollError = String(error?.message || error || 'Načtení zaměstnance selhalo');
      render();
      if (typeof window.showAlert === 'function') window.showAlert(state.payrollError, 'error');
    }
  }

  async function submitPayrollEmployeeUpdate(event) {
    event.preventDefault();
    if (typeof window.apiCall !== 'function') return;
    const id = state.payrollDetailEmployeeId;
    if (!id) return;
    const fd = new FormData(event.target);
    const primaryOfficeRaw = fd.get('primary_office_id');
    try {
      await window.apiCall(`/api/service/payroll/employees/${Number(id)}`, 'PUT', {
        first_name: String(fd.get('first_name') || '').trim(),
        last_name: String(fd.get('last_name') || '').trim(),
        birth_date: String(fd.get('birth_date') || ''),
        primary_office_id: primaryOfficeRaw ? Number(primaryOfficeRaw) : null,
        hourly_gross_rate: fd.get('hourly_gross_rate') ? Number(fd.get('hourly_gross_rate')) : null,
        contract_hours_per_week: fd.get('contract_hours_per_week') ? Number(fd.get('contract_hours_per_week')) : null,
        health_insurance_code: String(fd.get('health_insurance_code') || '').trim() || null,
        email: String(fd.get('email') || '').trim() || null,
        phone: String(fd.get('phone') || '').trim() || null,
        is_active: (() => {
          const cb = event.target.querySelector('input[name="is_active"]');
          return cb ? !!cb.checked : true;
        })(),
      });
      navigate('payroll-employees');
      state.payrollDetailEmployeeId = null;
      state.payrollEmployeeDetailCache = null;
      await refreshPayrollModule();
    } catch (error) {
      state.payrollError = String(error?.message || error || 'Uložení změn selhalo');
      render();
      if (typeof window.showAlert === 'function') window.showAlert(state.payrollError, 'error');
    }
  }

  function setTheme(theme) {
    applyTheme(theme);
    render();
  }

  function toggleTheme() {
    setTheme(state.theme === 'light' ? 'dark' : 'light');
  }

  function setSearchTerm(value) {
    state.searchTerm = String(value || '');
    render();
  }

  function setSortBy(value) {
    state.sortBy = String(value || 'due_asc');
    render();
  }

  function setKpiFilter(filter) {
    if (state.kpiFilter === filter) {
      state.kpiFilter = 'all'; // Toggle off
    } else {
      state.kpiFilter = String(filter || 'all');
    }
    
    if (!['dashboard', 'work-orders'].includes(String(state.activeSection || ''))) {
      state.activeSection = 'dashboard';
    }
    render();
  }

  function openFilterSheet(sheetType) {
    state.filterSheetOpen = true;
    state.filterSheetType = String(sheetType || state.filterSheetType || 'work-orders');
    state.mobileNavOpen = false;
    render();
  }

  function closeFilterSheet() {
    state.filterSheetOpen = false;
    render();
  }

  function setShowCancelledReservations(value) {
    state.showCancelledReservations = Boolean(value);
    render();
  }

  function setShowCompletedReminders(value) {
    state.showCompletedReminders = Boolean(value);
    render();
  }

  async function updateReservationStatus(reservationId, status, successMessage) {
    const id = Number(reservationId || 0);
    const nextStatus = reservationStatusKey(status);
    if (!id || !nextStatus) return;
    await window.apiCall(`/api/v1/reservations/${id}`, 'PUT', { status: nextStatus });
    showToast(successMessage || 'Rezervace byla aktualizována.', 'success');
    if (isModalOpen(`reservation-detail-${id}`)) {
      await reloadModalData();
    }
    await refreshAfterModalAction();
  }

  async function deleteReservation(reservationId) {
    const id = Number(reservationId || 0);
    if (!id) return;
    if (!window.confirm('Opravdu chcete rezervaci trvale smazat? Tato akce nejde vrátit.')) return;
    await window.apiCall(`/api/v1/reservations/${id}`, 'DELETE');
    showToast('Rezervace byla smazána.', 'success');
    if (isModalOpen(`reservation-detail-${id}`)) {
      closeModal();
    }
    await refreshAfterModalAction();
  }

  async function deleteReminder(reminderId) {
    const id = Number(reminderId || 0);
    if (!id) return;
    if (!window.confirm('Opravdu chcete připomínku smazat?')) return;
    await window.apiCall(`/api/v1/services/workspace/reminders/${id}`, 'DELETE');
    showToast('Připomínka byla smazána.', 'success');
    if (isModalOpen(`reminder-detail-${id}`)) {
      closeModal();
    }
    await refreshAfterModalAction();
  }

  function syncMobileNavScrollLock() {
    const locked = !!(state.mounted && state.mobileNavOpen && isMobileViewport());
    document.documentElement.classList.toggle('service-shell-mobile-nav-open', locked);
    document.body.classList.toggle('service-shell-mobile-nav-open', locked);
  }

  function closeAccountMenu() {
    state.accountMenuOpen = false;
    render();
  }

  function toggleAccountMenu() {
    state.accountMenuOpen = !state.accountMenuOpen;
    if (state.accountMenuOpen) {
      state.mobileNavOpen = false;
    }
    render();
  }

  function toggleMobileNav() {
    state.mobileNavOpen = !state.mobileNavOpen;
    if (state.mobileNavOpen) {
      state.accountMenuOpen = false;
    }
    state.filterSheetOpen = false;
    render();
  }

  function logout() {
    closeAccountMenu();
    try {
      window.localStorage.removeItem('loginMode');
      window.localStorage.removeItem('wasLoggedIn');
    } catch (err) {
      /* ignore */
    }
    if (typeof window.handleLogout === 'function') {
      window.handleLogout();
    } else {
      unmount();
    }
  }

  function licenseSummaryText() {
    const quickLabel = document.getElementById('licenseQuickLabel')?.textContent?.trim();
    if (quickLabel) return quickLabel;
    const plan = String(window.currentLicensePlanForUi || '').trim();
    return plan ? `Licence: ${plan.toUpperCase()}` : 'Licence';
  }

  function serviceShellNotificationsButtonHtml() {
    return `
          <button id="serviceShellNotificationsButton" class="service-shell-icon-btn app-notifications-button service-shell-topbar-notifications" type="button" onclick="window.toggleAppNotificationsPanel(event)" aria-label="Oznámení aplikace" aria-expanded="false" aria-controls="appNotificationsPanel" data-testid="app-notifications-button-service-shell">
            <svg aria-hidden="true" viewBox="0 0 24 24" focusable="false" width="22" height="22" fill="currentColor"><path d="M12 22a2.5 2.5 0 0 0 2.45-2h-4.9A2.5 2.5 0 0 0 12 22Zm6-6V11a6 6 0 1 0-12 0v5l-2 2v1h16v-1l-2-2Z"></path></svg>
            <span class="app-notifications-badge" id="serviceShellNotificationsBadge" data-count="0" aria-hidden="true"></span>
          </button>`;
  }

  async function openLicenseSettings() {
    closeAccountMenu();
    try {
      if (typeof window.loadLicenseStatus === 'function') {
        await window.loadLicenseStatus();
      }
    } catch (err) {
      console.warn('[SERVICE_SHELL] openLicenseSettings: loadLicenseStatus failed', err);
    }
    const tryCall = (fn) => {
      if (typeof fn !== 'function') return false;
      try {
        fn();
        return true;
      } catch (err) {
        console.warn('[SERVICE_SHELL] openLicenseSettings: handler threw', err);
        return false;
      }
    };
    if (tryCall(window.openLicenseModal)) return;
    if (tryCall(window.openLicensePlans)) return;

    try {
      const modal =
        typeof window.ensureLicenseModalRoot === 'function'
          ? window.ensureLicenseModalRoot()
          : document.getElementById('licenseModal');
      if (modal && typeof window.openStaticOverlayModal === 'function') {
        if (typeof window.syncLicenseBillingButtons === 'function') window.syncLicenseBillingButtons();
        if (typeof window.applyComgateUiConfig === 'function') {
          const cfg = typeof window.comgateConfigCache !== 'undefined' ? window.comgateConfigCache : null;
          window.applyComgateUiConfig(cfg);
        }
        if (typeof window.resetLicenseLegalConsent === 'function') window.resetLicenseLegalConsent();
        window.openStaticOverlayModal(modal, {
          scrollTargetSelector: '.license-modal-body',
          focusSelector: '#licenseBillingToggle .license-billing-btn.active',
        });
        return;
      }
    } catch (err) {
      console.warn('[SERVICE_SHELL] openLicenseSettings: DOM fallback failed', err);
    }

    showToast('Licenci se nepodařilo otevřít. Zkuste obnovit stránku.', 'warning');
    console.warn('[SERVICE_SHELL] openLicenseSettings: žádný platný handler', {
      openLicenseModal: typeof window.openLicenseModal,
      openLicensePlans: typeof window.openLicensePlans,
      licenseModal: !!document.getElementById('licenseModal'),
    });
  }

  function openAccountSettings() {
    closeAccountMenu();
    const profile = currentProfile();
    openModal({
      key: 'account-settings',
      entityType: 'account',
      kicker: 'Servisní účet',
      title: 'Nastavení účtu',
      description: 'Základní identita účtu a rychlé akce bez opuštění service shellu.',
      renderContent: () => `
        <div class="service-shell-list">
          <div class="service-shell-list-row"><span class="service-shell-list-title">Název účtu</span><span class="service-shell-list-value">${escape(profile?.name || window.currentUser?.name || 'Servisní účet')}</span></div>
          <div class="service-shell-list-row"><span class="service-shell-list-title">E-mail</span><span class="service-shell-list-value">${escape(profile?.email || window.currentUser?.email || '-')}</span></div>
          <div class="service-shell-list-row"><span class="service-shell-list-title">Role</span><span class="service-shell-list-value">${escape(String(profile?.role || window.currentUser?.role || 'service_account').replace(/_/g, ' '))}</span></div>
          <div class="service-shell-list-row"><span class="service-shell-list-title">Telefon</span><span class="service-shell-list-value">${escape(profile?.phone || '-')}</span></div>
        </div>
      `,
      renderFooter: () => `
        <div class="service-shell-modal-footer">
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zavřít</button>
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal(); window.serviceShell.navigate('team');">Otevřít profil</button>
          <button type="button" class="btn btn-primary" onclick="window.serviceShell.closeModal(); window.serviceShell.logout();">Odhlásit se</button>
        </div>
      `,
    });
  }

  function patchAddCustomerQuickLinkDraft(field, value) {
    const draft = state.addCustomerQuickLinkDraft || { email: '', note: '' };
    const v = String(value ?? '');
    if (field === 'email') draft.email = v;
    else if (field === 'note') draft.note = v;
    state.addCustomerQuickLinkDraft = draft;
  }

  function refreshCustomerSearchDependentModals() {
    if (!hasFloatingModalSupport()) return;
    if (isModalOpen('add-customer')) {
      renderAddCustomerModal();
    } else if (isModalOpen('service-tools')) {
      renderServiceToolsModal();
    }
  }

  function buildWorkspaceCustomerSearchSectionHtml(options = {}) {
    const {
      heading = 'Najít existujícího zákazníka',
      intro = 'Přesné vyhledání podle e-mailu nebo telefonu (centrální databáze účtů). Bez volného hledání podle jména.',
      searchButtonLabel = 'Hledat zákazníka',
      showInviteFromSearch = true,
      extraHtml = '',
    } = options;
    const customerMeta = state.customerSearchMeta || {};
    const customerRows = state.customerSearchLoading
      ? '<div class="service-shell-empty">Vyhledávám zákazníky…</div>'
      : state.customerSearchResults.length
        ? state.customerSearchResults.map((item) => `
          <div class="service-shell-list-row">
            <div>
              <p class="service-shell-list-title">${escape(item?.name || '-')}</p>
              <p class="service-shell-list-note">${escape(item?.email_masked || '-')} • ${escape(item?.phone_masked || '-')} • ${escape(item?.status_label || '-')}</p>
              ${item?.blocking_reason ? `<p class="service-shell-list-note">${escape(item.blocking_reason)}</p>` : ''}
            </div>
            <div class="service-shell-modal-actions">
              ${item?.already_linked
                ? (Number(item.customer_id) > 0
                  ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.openCustomerDetailModal(${Number(item.customer_id)})">Otevřít</button>`
                  : `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.navigate('clients')">Seznam zákazníků</button>`)
                : (item.lookup_id
                  ? `<button type="button" class="btn btn-primary" ${state.linkFromLookupBusy === String(item.lookup_id) ? 'disabled' : ''} onclick="window.serviceShell.linkCustomerFromLookup(${JSON.stringify(String(item.lookup_id))})">${state.linkFromLookupBusy === String(item.lookup_id) ? 'Odesílám…' : 'Požádat o propojení'}</button>`
                  : `<button type="button" class="btn btn-primary" onclick="window.serviceShell.linkCustomerById(${Number(item.customer_id || 0)})">Propojit</button>`)}
            </div>
          </div>
        `).join('')
        : '<div class="service-shell-empty">Zatím žádné výsledky.</div>';

    return `
          <section class="service-shell-side-card">
            <h3>${escape(heading)}</h3>
            <p>${intro}</p>
            <div class="service-shell-table-tools">
              <input class="service-shell-search" type="search" placeholder="Přesný e-mail nebo telefon (+420…)" value="${escape(state.customerSearchQuery)}" oninput="window.serviceShell.setCustomerSearchQuery(this.value)">
              <button type="button" class="btn btn-primary" onclick="window.serviceShell.searchCustomers()">${escape(searchButtonLabel)}</button>
            </div>
            ${customerMeta?.can_create_new_customer ? `<div class="service-shell-inline-alert"><span>Tento kontakt v databázi neevidujeme — můžete založit nového zákazníka níže (bez zobrazení přihlašovacích tokenů).</span></div>` : ''}
            ${state.customerSearchError ? `<div class="service-shell-inline-error">${escape(state.customerSearchError)}</div>` : ''}
            <div class="service-shell-list">${customerRows}</div>
            ${showInviteFromSearch && String(state.customerSearchQuery || '').includes('@') ? '<div class="service-shell-modal-footer service-shell-modal-footer--inline"><button type="button" class="btn btn-secondary" onclick="window.serviceShell.sendInvitationFromSearch()">Zákazník nenalezen? Odeslat pozvánku</button></div>' : ''}
            ${extraHtml || ''}
          </section>
    `;
  }

  async function searchCustomers(queryOverride = null) {
    const query = String(queryOverride ?? state.customerSearchQuery ?? '').trim();
    state.customerSearchQuery = query;
    state.customerSearchError = '';
    state.customerSearchMeta = null;
    if (query.length < 3) {
      state.customerSearchResults = [];
      refreshCustomerSearchDependentModals();
      return;
    }
    state.customerSearchLoading = true;
    refreshCustomerSearchDependentModals();
    try {
      const body = query.includes('@') ? { email: query } : { phone: query };
      const response = await window.apiCall('/api/v1/services/workspace/customers/search', 'POST', body);
      state.customerSearchMeta = response || null;
      if (!response?.found) {
        state.customerSearchResults = [];
      } else {
        const p = response.customer_preview || {};
        state.customerSearchResults = [
          {
            customer_id: null,
            lookup_id: p.lookup_id,
            name: p.display_name_masked || 'Uživatel',
            email_masked: p.email_masked || '-',
            phone_masked: p.phone_masked || '-',
            status:
              p.link_status === 'active'
                ? 'linked'
                : p.link_status === 'pending_customer_confirm'
                  ? 'pending_confirm'
                  : 'found',
            status_label:
              p.link_status === 'active'
                ? 'Aktivní vazba'
                : p.link_status === 'pending_customer_confirm'
                  ? 'Čeká na potvrzení zákazníka'
                  : p.link_status === 'invited'
                    ? 'Čeká na dokončení'
                    : 'Lze propojit',
            already_linked: p.link_status === 'active',
            blocking_reason: null,
          },
        ];
      }
    } catch (error) {
      const raw = String(error?.message || error?.detail || '').trim();
      const status = Number(error?.status || error?.statusCode || 0);
      if (status === 409 || raw.toLowerCase().includes('různé účty')) {
        state.customerSearchError =
          'Bezpečnostní konflikt: zadaný e-mail a telefon patří k různým účtům. Ověřte údaje u zákazníka.';
      } else {
        state.customerSearchError = raw || 'Vyhledání zákazníka selhalo.';
      }
      state.customerSearchResults = [];
      state.customerSearchMeta = null;
    } finally {
      state.customerSearchLoading = false;
      refreshCustomerSearchDependentModals();
    }
  }

  async function linkCustomerFromLookup(lookupId) {
    const lid = String(lookupId || '').trim();
    if (!lid) return;
    if (state.linkFromLookupBusy) return;
    state.linkFromLookupBusy = lid;
    refreshCustomerSearchDependentModals();
    try {
      const response = await window.apiCall('/api/v1/services/workspace/customers/link-existing', 'POST', {
        lookup_id: lid,
        consent_basis: 'customer_requested_service',
        consent_note:
          'Zákazník projevil zájem o evidenci vozidla a komunikaci přes aplikaci Správa vozidel při návštěvě servisu.',
        internal_service_note: null,
      });
      const parts = [];
      if (response?.linked) {
        parts.push('Zákazník byl propojen se servisem.');
      } else if (response?.pending_customer_confirm) {
        parts.push('Zákazník byl nalezen. Propojení čeká na potvrzení zákazníkem.');
      } else {
        parts.push(response?.message || 'Požadavek byl zpracován.');
      }
      if (response?.pending_customer_confirm && response?.email_sent) {
        parts.push('E-mail k potvrzení byl zákazníkovi odeslán.');
      } else if (response?.pending_customer_confirm && !response?.email_sent) {
        parts.push('E-mail se nepodařilo odeslat. Propojení čeká, ale zákazníka bude potřeba kontaktovat ručně.');
      }
      showServiceToast(
        response?.pending_customer_confirm && !response?.email_sent ? 'warning' : 'success',
        'Propojení zákazníka',
        parts.join('\n'),
      );
      const cid = Number(response?.customer_user_id || response?.customer_id || 0);
      if (cid) state.highlightCustomerId = cid;
      state.addCustomerQuickLinkDraft = { email: '', note: '' };
      closeModal();
      await load(true, true);
      navigate('clients', { forceLoad: true });
      scheduleCustomerHighlightClear();
      await searchCustomers(state.customerSearchQuery);
    } catch (error) {
      showServiceToast('error', 'Propojení se nepodařilo', error?.message || 'Neznámá chyba');
    } finally {
      state.linkFromLookupBusy = null;
      refreshCustomerSearchDependentModals();
    }
  }

  async function linkCustomerById(customerId) {
    try {
      const response = await window.apiCall(`/api/v1/services/workspace/customers/${Number(customerId)}/link`, 'POST');
      if (response?.pending_customer_confirm) {
        showToast(response?.message || 'Zákazník musí propojení potvrdit v e-mailu nebo v aplikaci.', 'info');
      } else {
        showToast(response?.message || 'Zákazník byl propojen.', 'success');
      }
      await load(true, true);
      if (isModalOpen('service-tools') || isModalOpen('add-customer')) {
        await searchCustomers(state.customerSearchQuery);
      } else if (String(state.modal?.entityType || '') === 'customer') {
        await reloadModalData();
      }
    } catch (error) {
      showToast(`Nepodařilo se propojit zákazníka: ${error?.message || 'Neznámá chyba'}`, 'error');
    }
  }

  async function sendInvitationFromSearch() {
    const query = String(state.customerSearchQuery || '').trim();
    if (!query || !query.includes('@')) {
      showToast('Pozvánku lze odeslat jen při hledání podle e-mailu.', 'warning');
      return;
    }
    try {
      const response = await window.apiCall('/api/v1/services/workspace/invitations/send', 'POST', {
        invite_email: query,
        invite_name: null,
        invite_message: 'Servisní účet vás zve k propojení do Správy vozidel.',
      });
      showToast(response?.message || 'Pozvánka byla připravena.', response?.email_sent ? 'success' : 'info');
      await load(true, true);
      refreshCustomerSearchDependentModals();
    } catch (error) {
      showToast(`Nepodařilo se odeslat pozvánku: ${error?.message || 'Neznámá chyba'}`, 'error');
    }
  }

  function renderAddCustomerModal() {
    if (!hasFloatingModalSupport()) return;
    const draft = state.addCustomerQuickLinkDraft || { email: '', note: '' };
    const cd = state.createCustomerDraft || {};
    const quickLinkHtml = `
            <div style="margin-top:1.25rem;padding-top:1rem;border-top:1px solid rgba(127,140,155,0.25);">
              <h3>Propojit podle e-mailu účtu</h3>
              <p>Znáte-li přihlašovací e-mail zákazníka ve Správě vozidel, propojte účet přímo. Server ověří existenci profilu — bez účtu propojení neproběhne.</p>
              <label class="service-shell-field-label" for="serviceShellQuickLinkCustomerEmail">E-mail</label>
              <input id="serviceShellQuickLinkCustomerEmail" class="service-shell-search" type="email" autocomplete="email" placeholder="zakaznik@email.cz" style="width:100%;box-sizing:border-box;margin-bottom:0.75rem;" value="${escape(draft.email)}" oninput="window.serviceShell.patchAddCustomerQuickLinkDraft('email', this.value)">
              <label class="service-shell-field-label" for="serviceShellQuickLinkCustomerNote">Poznámka k vazbě (volitelné)</label>
              <textarea id="serviceShellQuickLinkCustomerNote" class="service-shell-search" style="min-height:72px;width:100%;box-sizing:border-box;" oninput="window.serviceShell.patchAddCustomerQuickLinkDraft('note', this.value)">${escape(draft.note)}</textarea>
              <div class="service-shell-modal-footer service-shell-modal-footer--inline" style="margin-top:0.75rem;padding:0;">
                <button type="button" class="btn btn-primary" ${state.linkExistingByEmailSubmitting ? 'disabled' : ''} onclick="window.serviceShell.linkExistingCustomerByEmail()">${state.linkExistingByEmailSubmitting ? 'Odesílám…' : 'Propojit zákazníka'}</button>
              </div>
            </div>
    `;
    const createHtml = `
            <div style="margin-top:1.25rem;padding-top:1rem;border-top:1px solid rgba(127,140,155,0.25);">
              <h3>2) Vytvořit nového zákazníka</h3>
              <p>Založí běžný uživatelský účet a odešle zákazníkovi e-mail s odkazem na nastavení hesla (token se zde nezobrazuje).</p>
              <div style="display:flex;flex-wrap:wrap;gap:0.5rem;">
                <div style="flex:1;min-width:140px;">
                  <label class="service-shell-field-label" for="serviceShellCreateCustFirst">Jméno</label>
                  <input id="serviceShellCreateCustFirst" class="service-shell-search" style="width:100%;box-sizing:border-box;" value="${escape(cd.first_name || '')}" oninput="window.serviceShell.patchCreateCustomerDraft('first_name', this.value)">
                </div>
                <div style="flex:1;min-width:140px;">
                  <label class="service-shell-field-label" for="serviceShellCreateCustLast">Příjmení</label>
                  <input id="serviceShellCreateCustLast" class="service-shell-search" style="width:100%;box-sizing:border-box;" value="${escape(cd.last_name || '')}" oninput="window.serviceShell.patchCreateCustomerDraft('last_name', this.value)">
                </div>
              </div>
              <label class="service-shell-field-label" for="serviceShellCreateCustEmail">E-mail</label>
              <input id="serviceShellCreateCustEmail" class="service-shell-search" type="email" style="width:100%;box-sizing:border-box;margin-bottom:0.5rem;" value="${escape(cd.email || '')}" oninput="window.serviceShell.patchCreateCustomerDraft('email', this.value)">
              <label class="service-shell-field-label" for="serviceShellCreateCustPhone">Telefon</label>
              <input id="serviceShellCreateCustPhone" class="service-shell-search" type="tel" style="width:100%;box-sizing:border-box;margin-bottom:0.5rem;" value="${escape(cd.phone || '')}" oninput="window.serviceShell.patchCreateCustomerDraft('phone', this.value)">
              <label class="service-shell-field-label" for="serviceShellCreateCustInternal">Interní poznámka servisu (volitelné)</label>
              <textarea id="serviceShellCreateCustInternal" class="service-shell-search" style="min-height:64px;width:100%;box-sizing:border-box;" oninput="window.serviceShell.patchCreateCustomerDraft('internal_note', this.value)">${escape(cd.internal_note || '')}</textarea>
              <label style="display:flex;align-items:center;gap:0.5rem;margin:0.75rem 0;">
                <input type="checkbox" ${cd.create_vehicle ? 'checked' : ''} onchange="window.serviceShell.patchCreateCustomerDraft('create_vehicle', this.checked)">
                <span>Založit zároveň vozidlo</span>
              </label>
              <div style="${cd.create_vehicle ? '' : 'display:none;'}">
                <label class="service-shell-field-label" for="serviceShellCreateCustVin">VIN</label>
                <input id="serviceShellCreateCustVin" class="service-shell-search" style="width:100%;box-sizing:border-box;" value="${escape(cd.vehicle_vin || '')}" oninput="window.serviceShell.patchCreateCustomerDraft('vehicle_vin', this.value)">
                <label class="service-shell-field-label" for="serviceShellCreateCustPlate">SPZ</label>
                <input id="serviceShellCreateCustPlate" class="service-shell-search" style="width:100%;box-sizing:border-box;" value="${escape(cd.vehicle_plate || '')}" oninput="window.serviceShell.patchCreateCustomerDraft('vehicle_plate', this.value)">
                <label class="service-shell-field-label" for="serviceShellCreateCustBrand">Značka (volitelné)</label>
                <input id="serviceShellCreateCustBrand" class="service-shell-search" style="width:100%;box-sizing:border-box;" value="${escape(cd.vehicle_brand || '')}" oninput="window.serviceShell.patchCreateCustomerDraft('vehicle_brand', this.value)">
                <label class="service-shell-field-label" for="serviceShellCreateCustModel">Model (volitelné)</label>
                <input id="serviceShellCreateCustModel" class="service-shell-search" style="width:100%;box-sizing:border-box;" value="${escape(cd.vehicle_model || '')}" oninput="window.serviceShell.patchCreateCustomerDraft('vehicle_model', this.value)">
              </div>
              <div class="service-shell-modal-footer service-shell-modal-footer--inline" style="margin-top:0.75rem;padding:0;">
                <button type="button" class="btn btn-primary" ${state.createCustomerSubmitting ? 'disabled' : ''} onclick="window.serviceShell.submitCreateCustomer()">${state.createCustomerSubmitting ? 'Odesílám…' : 'Vytvořit zákazníka a pozvat e-mailem'}</button>
              </div>
            </div>
    `;
    openModal({
      key: 'add-customer',
      entityType: 'add_customer',
      kicker: 'Zákazníci',
      title: 'Přidat zákazníka',
      description: 'Najděte existující účet nebo založte nového. Náhled kontaktu je maskovaný; token z pozvánky se neukládá do UI.',
      size: 'wide',
      bodyClass: 'service-shell-modal-body--tools',
      renderContent: () => `
        <div class="service-shell-tools-grid" style="grid-template-columns:1fr;max-width:640px;">
          ${buildWorkspaceCustomerSearchSectionHtml({
            heading: '1) Najít existujícího zákazníka',
            intro: 'E-mail nebo telefon (samo jméno nestačí). Při konfliktu dvou účtů zobrazíme bezpečnostní hlášku.',
            searchButtonLabel: 'Hledat',
            showInviteFromSearch: true,
            extraHtml: quickLinkHtml + createHtml,
          })}
        </div>
      `,
      renderFooter: () => `
        <div class="service-shell-modal-footer">
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zavřít</button>
        </div>
      `,
    });
  }

  function openAddCustomerModal() {
    state.accountMenuOpen = false;
    state.addCustomerQuickLinkDraft = { email: '', note: '' };
    state.createCustomerDraft = {
      first_name: '',
      last_name: '',
      email: '',
      phone: '',
      internal_note: '',
      consent_basis: 'service_customer_intake',
      consent_note:
        'Založení účtu zákazníka při návštěvě servisu — evidence vozidla a servisní historie v aplikaci Správa vozidel.',
      create_vehicle: false,
      vehicle_vin: '',
      vehicle_plate: '',
      vehicle_brand: '',
      vehicle_model: '',
    };
    renderAddCustomerModal();
  }

  async function linkExistingCustomerByEmail() {
    const draft = state.addCustomerQuickLinkDraft || { email: '', note: '' };
    const email = String(draft.email || document.getElementById('serviceShellQuickLinkCustomerEmail')?.value || '').trim();
    const note = String(draft.note || document.getElementById('serviceShellQuickLinkCustomerNote')?.value || '').trim();
    if (!email || !email.includes('@')) {
      showToast('Zadejte platný e-mail účtu zákazníka.', 'warning');
      return;
    }
    if (state.linkExistingByEmailSubmitting) return;
    state.linkExistingByEmailSubmitting = true;
    refreshCustomerSearchDependentModals();
    try {
      const response = await window.apiCall('/api/v1/services/workspace/customers/link-existing', 'POST', {
        customer_email: email,
        note: note || null,
      });
      const parts = [];
      const notifReason = String(response?.notification?.reason || '');
      if (response?.pending_customer_confirm) {
        parts.push('Zákazník byl nalezen. Propojení čeká na potvrzení zákazníkem.');
        if (response?.email_sent) parts.push('E-mail k potvrzení byl zákazníkovi odeslán.');
        else parts.push('E-mail se nepodařilo odeslat. Propojení čeká, ale zákazníka bude potřeba kontaktovat ručně.');
      } else if (response?.email_sent) {
        parts.push('Zákazník byl propojen');
        parts.push('Informační e-mail byl zákazníkovi odeslán.');
      } else {
        parts.push('Zákazník byl propojen');
        if (notifReason === 'direct_link_no_email') {
          parts.push('E-mailová notifikace nebyla odeslána (starší režim aplikace).');
        } else {
          parts.push('Informační e-mail se nepodařilo odeslat. Zákazníka bude potřeba kontaktovat ručně.');
        }
      }
      const toastLevel =
        response?.pending_customer_confirm && !response?.email_sent
          ? 'warning'
          : !response?.pending_customer_confirm &&
              !response?.email_sent &&
              notifReason !== 'direct_link_no_email'
            ? 'warning'
            : 'success';
      showServiceToast(toastLevel, 'Propojení zákazníka', parts.join('\n'));
      const cid = Number(response?.customer_user_id || response?.customer_id || 0);
      if (cid) state.highlightCustomerId = cid;
      state.addCustomerQuickLinkDraft = { email: '', note: '' };
      closeModal();
      await load(true, true);
      navigate('clients', { forceLoad: true });
      scheduleCustomerHighlightClear();
      refreshCustomerSearchDependentModals();
    } catch (error) {
      showServiceToast('error', 'Propojení se nepodařilo', error?.message || 'Zkuste vyhledání nebo pozvánku.');
    } finally {
      state.linkExistingByEmailSubmitting = false;
      refreshCustomerSearchDependentModals();
    }
  }

  function patchCreateCustomerDraft(field, value) {
    const d = state.createCustomerDraft || {};
    if (field === 'create_vehicle') {
      d.create_vehicle = Boolean(value);
    } else {
      d[field] = String(value ?? '');
    }
    state.createCustomerDraft = d;
    refreshCustomerSearchDependentModals();
  }

  async function submitCreateCustomer() {
    const d = state.createCustomerDraft || {};
    if (state.createCustomerSubmitting) return;
    const first = String(d.first_name || '').trim();
    const last = String(d.last_name || '').trim();
    const em = String(d.email || document.getElementById('serviceShellCreateCustEmail')?.value || '').trim();
    const ph = String(d.phone || document.getElementById('serviceShellCreateCustPhone')?.value || '').trim();
    if (!first || !last) {
      showToast('Vyplňte jméno a příjmení zákazníka.', 'warning');
      return;
    }
    if (!em || !em.includes('@')) {
      showToast('Zadejte platný e-mail zákazníka.', 'warning');
      return;
    }
    if (!ph || ph.replace(/\D/g, '').length < 9) {
      showToast('Zadejte platný telefon (min. 9 číslic).', 'warning');
      return;
    }
    const internal = String(d.internal_note || document.getElementById('serviceShellCreateCustInternal')?.value || '').trim();
    const consentBasis = String(d.consent_basis || 'service_customer_intake').trim();
    const consentNote = String(
      d.consent_note ||
        'Založení účtu zákazníka při návštěvě servisu — evidence vozidla a servisní historie v aplikaci Správa vozidel.',
    ).trim();
    const payload = {
      first_name: first,
      last_name: last,
      email: em,
      phone: ph,
      consent_basis: consentBasis,
      consent_note: consentNote,
      internal_service_note: internal || null,
      create_vehicle: Boolean(d.create_vehicle),
      vehicle: null,
    };
    if (payload.create_vehicle) {
      const vin = String(d.vehicle_vin || document.getElementById('serviceShellCreateCustVin')?.value || '')
        .trim()
        .toUpperCase();
      const plate = String(d.vehicle_plate || document.getElementById('serviceShellCreateCustPlate')?.value || '')
        .trim()
        .toUpperCase();
      const brand = String(d.vehicle_brand || document.getElementById('serviceShellCreateCustBrand')?.value || '').trim();
      const model = String(d.vehicle_model || document.getElementById('serviceShellCreateCustModel')?.value || '').trim();
      if (!vin && !plate) {
        showToast('Vyplňte VIN nebo SPZ vozidla, nebo vypněte volbu založit vozidlo.', 'warning');
        return;
      }
      payload.vehicle = {
        vin: vin || null,
        plate: plate || null,
        brand: brand || null,
        model: model || null,
      };
    }
    state.createCustomerSubmitting = true;
    refreshCustomerSearchDependentModals();
    try {
      const response = await window.apiCall('/api/v1/services/workspace/customers/create', 'POST', payload);
      const msg = response?.message || 'Zákazník byl přidán.';
      showServiceToast(response?.email_sent ? 'success' : 'warning', 'Nový zákazník', msg);
      const uid = Number(response?.customer_user_id || 0);
      if (uid) state.highlightCustomerId = uid;
      state.createCustomerDraft = {
        first_name: '',
        last_name: '',
        email: '',
        phone: '',
        internal_note: '',
        consent_basis: 'service_customer_intake',
        consent_note:
          'Založení účtu zákazníka při návštěvě servisu — evidence vozidla a servisní historie v aplikaci Správa vozidel.',
        create_vehicle: false,
        vehicle_vin: '',
        vehicle_plate: '',
        vehicle_brand: '',
        vehicle_model: '',
      };
      closeModal();
      await load(true, true);
      navigate('clients', { forceLoad: true });
      scheduleCustomerHighlightClear();
      refreshCustomerSearchDependentModals();
    } catch (error) {
      showServiceToast('error', 'Založení zákazníka', error?.message || 'Operace se nepodařila.');
    } finally {
      state.createCustomerSubmitting = false;
      refreshCustomerSearchDependentModals();
    }
  }

  async function submitCustomerLinkNote() {
    const id = Number(state.modal?.context?.customerId || 0);
    if (!id) return;
    const note = String(document.getElementById('serviceShellCustomerLinkNote')?.value || '');
    try {
      await window.apiCall(`/api/v1/services/workspace/customers/${id}/link`, 'PATCH', { note: note.trim() || null });
      showToast('Poznámka k vazbě byla uložena.', 'success');
      closeModal();
      await load(true, true);
      render();
    } catch (error) {
      showToast(error?.message || 'Uložení se nepodařilo.', 'error');
    }
  }

  function openCustomerLinkNoteModal(customerId, currentNote) {
    const id = Number(customerId || 0);
    if (!id) return;
    openModal({
      key: 'customer-link-note',
      entityType: 'customer_link',
      kicker: `Zákazník #${id}`,
      title: 'Upravit poznámku k vazbě',
      description: 'Interní poznámka k propojení v servisním účtu. Nejde o úpravu jména ani kontaktu zákazníka v aplikaci Správa vozidel.',
      context: { customerId: id },
      renderContent: () => `
        <label class="service-shell-field-label" for="serviceShellCustomerLinkNote">Poznámka</label>
        <textarea id="serviceShellCustomerLinkNote" class="service-shell-search" style="min-height:120px;width:100%;box-sizing:border-box;">${escape(String(currentNote || ''))}</textarea>
      `,
      renderFooter: () => `
        <div class="service-shell-modal-footer">
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zrušit</button>
          <button type="button" class="btn btn-primary" onclick="window.serviceShell.submitCustomerLinkNote()">Uložit</button>
        </div>
      `,
    });
  }

  async function unlinkCustomer(customerId) {
    const id = Number(customerId || 0);
    if (!id) return;
    if (!window.confirm('Odpojit tohoto zákazníka od servisního účtu? Zmizí ze seznamu zákazníků servisu; schválené přístupy k vozidlům v aplikaci zůstávají podle rozhodnutí zákazníka.')) return;
    try {
      await window.apiCall(`/api/v1/services/workspace/customers/${id}/link`, 'DELETE');
      showToast('Zákazník byl odpojen od servisu.', 'success');
      if (String(state.modal?.entityType || '') === 'customer' && Number(state.modal?.entityId || 0) === id) {
        closeModal();
      }
      await load(true, true);
      render();
    } catch (error) {
      showToast(error?.message || 'Odpojení se nepodařilo.', 'error');
    }
  }

  function mapCentralVehicleLookupResponse(response) {
    if (!response?.found) return [];
    const preview = response.vehicle_preview || {};
    const access = response.access || {};
    const status = response.status || access.status || 'found';
    return [{
      vehicle_id: Number(preview.vehicle_id || 0),
      nickname: [preview.brand, preview.model].filter(Boolean).join(' '),
      brand: preview.brand || null,
      model: preview.model || null,
      year: preview.year || null,
      plate_masked: preview.plate_masked || null,
      vin_masked: preview.vin_masked || null,
      status,
      can_open_detail: Boolean(response.can_open_detail),
      can_request_access: Boolean(access.can_request_access),
      can_create_work_order: Boolean(response.can_create_work_order),
      blocking_reason: status === 'found_access_required'
        ? 'Vozidlo je v systému. Detail je zamčený, dokud majitel nepovolí přístup.'
        : status === 'found_service_unowned'
          ? 'Vozidlo je evidováno bez majitele.'
          : null,
    }];
  }

  async function searchVehicles(queryOverride = null) {
    const query = String(queryOverride ?? state.vehicleLookupQuery ?? '').trim();
    state.vehicleLookupQuery = query;
    state.vehicleLookupError = '';
    state.vehicleLookupMeta = null;
    if (query.length < 2) {
      state.vehicleLookupResults = [];
      return renderServiceToolsModal();
    }
    state.vehicleLookupLoading = true;
    renderServiceToolsModal();
    try {
      const response = await window.apiCall('/api/v1/services/workspace/vehicles/lookup', 'POST', { query, query_type: 'auto' });
      state.vehicleLookupResults = mapCentralVehicleLookupResponse(response);
      state.vehicleLookupMeta = response || null;
    } catch (error) {
      state.vehicleLookupError = error?.message || 'Lookup vozidla selhal.';
      state.vehicleLookupResults = [];
      state.vehicleLookupMeta = null;
    } finally {
      state.vehicleLookupLoading = false;
      const rows = Array.isArray(state.vehicleLookupResults) ? state.vehicleLookupResults : [];
      const nextPending = { ...(state.pendingAccessVehicleIds || {}) };
      rows.forEach((item) => {
        const id = Number(item?.vehicle_id || 0);
        if (!id) return;
        if (!item?.can_request_access) delete nextPending[id];
      });
      state.pendingAccessVehicleIds = nextPending;
      renderServiceToolsModal();
    }
  }

  function openProvisionUnownedVehicleModal() {
    const query = String(state.vehicleLookupQuery || '').trim();
    openModal({
      key: 'provision-unowned-vehicle',
      entityType: 'vehicle',
      title: 'Založit nepřiřazené vozidlo',
      description: 'Vozidlo bude evidováno bez majitele. Servis s ním může pracovat v příjmu a budoucí majitel ho později bezpečně převezme.',
      renderContent: () => `
        <div class="service-shell-form-grid">
          <label>Zadaný VIN nebo SPZ<input id="serviceShellProvisionQuery" value="${escape(query)}"></label>
          <label>Značka<input id="serviceShellProvisionBrand" placeholder="např. Škoda"></label>
          <label>Model<input id="serviceShellProvisionModel" placeholder="např. Octavia"></label>
          <label>Rok<input id="serviceShellProvisionYear" type="number" min="1900" max="2100"></label>
          <label>Stav km<input id="serviceShellProvisionMileage" type="number" min="0"></label>
          <label class="service-shell-form-grid--wide">Poznámka k příjmu<textarea id="serviceShellProvisionNote" rows="3"></textarea></label>
        </div>
        <div class="service-shell-inline-alert">Nevznikne vlastnická vazba. Servisní historie se budoucímu majiteli ukáže pouze v bezpečném režimu bez cen a faktur.</div>
      `,
      renderFooter: () => `
        <div class="service-shell-modal-footer">
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zrušit</button>
          <button type="button" class="btn btn-primary" onclick="window.serviceShell.provisionUnownedVehicleFromLookup()">Založit nepřiřazené vozidlo</button>
        </div>
      `,
    });
  }

  async function provisionUnownedVehicleFromLookup() {
    const query = String(document.getElementById('serviceShellProvisionQuery')?.value || '').trim();
    const brand = String(document.getElementById('serviceShellProvisionBrand')?.value || '').trim();
    const model = String(document.getElementById('serviceShellProvisionModel')?.value || '').trim();
    const yearRaw = Number(document.getElementById('serviceShellProvisionYear')?.value || 0);
    const mileageRaw = Number(document.getElementById('serviceShellProvisionMileage')?.value || 0);
    const note = String(document.getElementById('serviceShellProvisionNote')?.value || '').trim();
    if (!query || !brand || !model) {
      showServiceToast('warning', 'Nepřiřazené vozidlo', 'Vyplňte VIN/SPZ, značku a model.');
      return;
    }
    const normalized = query.toUpperCase().replace(/[\s-]+/g, '');
    const payload = {
      brand,
      model,
      year: Number.isFinite(yearRaw) && yearRaw > 0 ? yearRaw : null,
      mileage: Number.isFinite(mileageRaw) && mileageRaw > 0 ? mileageRaw : null,
      intake_note: note || null,
    };
    if (normalized.length === 17) {
      payload.vin = normalized;
    } else {
      payload.plate = query;
    }
    try {
      const response = await window.apiCall('/api/v1/services/workspace/vehicles/provision-unowned', 'POST', payload);
      showServiceToast('success', 'Nepřiřazené vozidlo', response?.message || 'Vozidlo evidováno bez majitele.');
      state.vehicleLookupQuery = query;
      closeModal();
      openServiceToolsModal();
      await searchVehicles(query);
    } catch (error) {
      showServiceToast('error', 'Nepřiřazené vozidlo', error?.message || 'Vozidlo se nepodařilo založit.');
    }
  }

  async function requestVehicleAccess(vehicleId, lookupQueryOverride = null) {
    const lookupQuery = String(
      lookupQueryOverride
      || state.modal?.data?.vehicle_plate_masked
      || state.modal?.data?.plate_masked
      || state.vehicleLookupQuery
      || ''
    ).trim();
    if (lookupQuery.length < 2) {
      showToast('Pro žádost o přístup chybí použitelný VIN nebo SPZ identifikátor.', 'error');
      return;
    }
    const vid = Number(vehicleId || 0);
    if (!vid) return;
    if (state.accessRequestBusyVehicleId === vid) return;
    state.accessRequestBusyVehicleId = vid;
    refreshAccessRequestDependentUi();
    try {
      const response = await window.apiCall('/api/v1/services/workspace/access-requests', 'POST', {
        vehicle_id: vid,
        lookup_query: lookupQuery,
        note: 'Žádost vytvořená z nového servisního shellu.',
      });
      state.pendingAccessVehicleIds = { ...(state.pendingAccessVehicleIds || {}) };
      state.pendingAccessVehicleIds[vid] = true;

      const created = response?.created === true;
      const existingPending = response?.notification?.reason === 'existing_pending';
      const emailSent = response?.email_sent === true;

      if (created) {
        const lines = ['Čeká se na vyjádření uživatele.'];
        if (emailSent) lines.push('Uživatel byl upozorněn e-mailem.');
        else lines.push('E-mail se nepodařilo odeslat, ale žádost je uložená v aplikaci.');
        showServiceToast('success', 'Žádost odeslána', lines.join('\n'));
      } else if (existingPending) {
        showServiceToast(
          'info',
          'Žádost už čeká',
          'Žádost o přístup k tomuto vozidlu už čeká na potvrzení uživatelem.',
        );
      } else {
        showServiceToast('warning', 'Žádost o přístup', response?.message || 'Žádost byla zpracována.');
      }

      const wasServiceTools = isModalOpen('service-tools');
      if (wasServiceTools) {
        closeModal();
      }
      openVehicleDetailModal(vid);
      await load(true, true);
      refreshAccessRequestDependentUi();
    } catch (error) {
      showServiceToast('error', 'Žádost o přístup', error?.message || 'Operace se nepodařila.');
    } finally {
      state.accessRequestBusyVehicleId = null;
      refreshAccessRequestDependentUi();
    }
  }

  /** Tlačítko žádosti o přístup — jednotně disabled / „Odesílám…“ při běžícím requestu. */
  function accessRequestPrimaryButton(vehicleId, lookupQueryStr) {
    const vid = Number(vehicleId || 0);
    if (!vid) return '';
    const busy = state.accessRequestBusyVehicleId === vid;
    return `<button type="button" class="btn btn-primary" ${busy ? 'disabled' : ''} onclick="window.serviceShell.requestVehicleAccess(${vid}, ${JSON.stringify(String(lookupQueryStr || ''))})">${busy ? 'Odesílám…' : 'Požádat o přístup'}</button>`;
  }

  function openVehicleFromLookup(candidate) {
    const vehicleId = Number(candidate?.vehicle_id || 0);
    if (!vehicleId) {
      showToast('Detail vozidla není k dispozici.', 'warning');
      return;
    }
    return openVehicleDetailModal(vehicleId);
  }

  function openVehicleFromLookupByIndex(index) {
    const candidate = Array.isArray(state.vehicleLookupResults) ? state.vehicleLookupResults[Number(index)] : null;
    return openVehicleFromLookup(candidate);
  }

  function openCreateWorkOrderFromLookup(candidate) {
    const ownerId = Number(candidate?.owner_customer_id || 0);
    const vehicleId = Number(candidate?.vehicle_id || 0);
    if (!ownerId || !vehicleId) {
      showToast('Chybí identita vozidla nebo vlastníka pro založení zakázky.', 'warning');
      return;
    }
    closeFloatingModal();
    openCreateWorkOrderModal({ ownerId, vehicleId });
  }

  function openCreateWorkOrderFromLookupByIndex(index) {
    const candidate = Array.isArray(state.vehicleLookupResults) ? state.vehicleLookupResults[Number(index)] : null;
    return openCreateWorkOrderFromLookup(candidate);
  }

  async function populateCreateVehicleOptions(customerId, preferredVehicleId = null) {
    const customerRaw = String(customerId || '').trim();
    const isUnowned = customerRaw === '__unowned__';
    const customerIdNum = isUnowned ? 0 : Number(customerRaw || 0);
    const select = document.getElementById('serviceShellWorkOrderVehicle');
    if (!select) return;
    if (!customerRaw) {
      select.innerHTML = '<option value="">Nejprve vyberte klienta nebo nepřiřazené vozidlo</option>';
      return;
    }
    if (isUnowned) {
      const response = await window.apiCall('/api/service/work-orders/unowned-vehicles', 'GET');
      const vehicles = Array.isArray(response?.items) ? response.items : [];
      const preferred = Number(preferredVehicleId || 0);
      select.innerHTML = vehicles.length
        ? vehicles.map((item) => {
            const vid = Number(item?.vehicle_id || 0);
            const selected = preferred > 0 && vid === preferred ? 'selected' : '';
            return `<option value="${vid}" ${selected}>${escape(item.label || `Vozidlo #${vid}`)}</option>`;
          }).join('')
        : '<option value="">Žádné nepřiřazené vozidlo k dispozici</option>';
      return;
    }
    window.serviceWorkspaceState = window.serviceWorkspaceState || { customerVehicles: {} };
    if (!Array.isArray(window.serviceWorkspaceState.customerVehicles?.[customerIdNum])) {
      const vehicles = await window.apiCall(`/api/v1/services/workspace/customers/${customerIdNum}/vehicles`, 'GET');
      window.serviceWorkspaceState.customerVehicles[customerIdNum] = Array.isArray(vehicles) ? vehicles : [];
    }
    const vehicles = Array.isArray(window.serviceWorkspaceState.customerVehicles?.[customerIdNum])
      ? window.serviceWorkspaceState.customerVehicles[customerIdNum].filter((item) => Boolean(item?.is_shared))
      : [];
    const preferred = Number(preferredVehicleId || 0);
    select.innerHTML = vehicles.length
      ? vehicles.map((item) => {
          const selected = preferred > 0 && Number(item?.id || 0) === preferred ? 'selected' : '';
          return `<option value="${Number(item.id)}" ${selected}>${escape(item.nickname || item.plate || item.vin || `Vozidlo #${Number(item.id)}`)}</option>`;
        }).join('')
      : '<option value="">Zákazník nemá schválené vozidlo pro založení zakázky</option>';
  }

  async function populateCustomerVehicleSelect(selectId, customerId, options = {}) {
    const customerIdNum = Number(customerId || 0);
    const select = document.getElementById(selectId);
    if (!select) return;
    const {
      preferredVehicleId = null,
      includeEmpty = true,
      emptyLabel = 'Bez vozidla',
      sharedOnly = false,
      disabledLabel = 'Nejprve vyberte klienta',
    } = options || {};
    if (!customerIdNum) {
      select.innerHTML = includeEmpty
        ? `<option value="">${escape(disabledLabel)}</option>`
        : `<option value="">${escape(disabledLabel)}</option>`;
      return;
    }
    window.serviceWorkspaceState = window.serviceWorkspaceState || { customerVehicles: {} };
    if (!Array.isArray(window.serviceWorkspaceState.customerVehicles?.[customerIdNum])) {
      const vehicles = await window.apiCall(`/api/v1/services/workspace/customers/${customerIdNum}/vehicles`, 'GET');
      window.serviceWorkspaceState.customerVehicles[customerIdNum] = Array.isArray(vehicles) ? vehicles : [];
    }
    const raw = Array.isArray(window.serviceWorkspaceState.customerVehicles?.[customerIdNum])
      ? window.serviceWorkspaceState.customerVehicles[customerIdNum]
      : [];
    const vehicles = sharedOnly ? raw.filter((item) => Boolean(item?.is_shared)) : raw;
    const preferred = Number(preferredVehicleId || 0);
    const optionsHtml = vehicles.map((item) => {
      const selected = preferred > 0 && Number(item?.id || 0) === preferred ? 'selected' : '';
      return `<option value="${Number(item.id)}" ${selected}>${escape(item.nickname || item.plate || item.vin || `Vozidlo #${Number(item.id)}`)}</option>`;
    }).join('');
    if (!vehicles.length) {
      select.innerHTML = `<option value="">${escape(includeEmpty ? emptyLabel : 'Bez dostupných vozidel')}</option>`;
      return;
    }
    select.innerHTML = includeEmpty
      ? `<option value="">${escape(emptyLabel)}</option>${optionsHtml}`
      : optionsHtml;
  }

  function renderServiceToolsModal() {
    if (!hasFloatingModalSupport()) return;
    const vehicleMeta = state.vehicleLookupMeta || {};
    const vehicleRows = state.vehicleLookupLoading
      ? '<div class="service-shell-empty">Vyhledávám vozidla…</div>'
      : state.vehicleLookupResults.length
        ? state.vehicleLookupResults.map((item, index) => {
          const vid = Number(item?.vehicle_id || 0);
          const pendingLocal = vid && state.pendingAccessVehicleIds && state.pendingAccessVehicleIds[vid];
          const statusLine = pendingLocal ? 'Čeká na schválení' : accessStatusLabel(item?.status || '-');
          return `
          <div class="service-shell-list-row">
            <div>
              <p class="service-shell-list-title">${escape(item?.nickname || [item?.brand, item?.model].filter(Boolean).join(' ') || (item?.status === 'conflict' ? 'Konfliktní identifikace' : 'Vozidlo'))}</p>
              <p class="service-shell-list-note">${escape(item?.plate_masked || '-')} • ${escape(item?.vin_masked || '-')} • ${escape(statusLine)}</p>
              ${item?.blocking_reason ? `<p class="service-shell-list-note">${escape(item.blocking_reason)}</p>` : ''}
              ${Array.isArray(item?.conflicting_candidates) ? `
                <div class="service-shell-list">
                  ${item.conflicting_candidates.map((conflict) => `
                    <div class="service-shell-list-row">
                      <div>
                        <p class="service-shell-list-title">${escape(conflict?.nickname || [conflict?.brand, conflict?.model].filter(Boolean).join(' ') || 'Vozidlo')}</p>
                        <p class="service-shell-list-note">${escape(conflict?.plate_masked || '-')} • ${escape(conflict?.vin_masked || '-')} • ${escape(accessStatusLabel(conflict?.status || '-'))}</p>
                      </div>
                      <div class="service-shell-modal-actions">
                        <button type="button" class="btn btn-secondary" onclick="window.serviceShell.openVehicleDetailModal(${Number(conflict?.vehicle_id || 0)})">Otevřít detail</button>
                      </div>
                    </div>
                  `).join('')}
                </div>
              ` : ''}
            </div>
            <div class="service-shell-modal-actions">
              ${item?.can_open_detail ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.openVehicleFromLookupByIndex(${index})">Detail</button>` : ''}
              ${item?.can_create_work_order ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.openCreateWorkOrderFromLookupByIndex(${index})">Nová zakázka</button>` : ''}
              ${item?.can_request_access ? `<button type="button" class="btn btn-primary" ${state.accessRequestBusyVehicleId === vid ? 'disabled' : ''} onclick="window.serviceShell.requestVehicleAccess(${vid})">${state.accessRequestBusyVehicleId === vid ? 'Odesílám…' : 'Požádat o přístup'}</button>` : ''}
            </div>
          </div>
        `;
        }).join('')
        : vehicleMeta?.found === false && vehicleMeta?.can_create_unowned_vehicle
          ? `<div class="service-shell-empty">
              <p>Vozidlo není v systému.</p>
              <button type="button" class="btn btn-primary" onclick="window.serviceShell.openProvisionUnownedVehicleModal()">Založit nepřiřazené vozidlo</button>
            </div>`
          : '<div class="service-shell-empty">Zatím žádné výsledky.</div>';

    openModal({
      key: 'service-tools',
      entityType: 'toolbox',
      kicker: 'Servisní nástroje',
      title: 'Najít nebo vytvořit',
      description: 'Vyhledávání zákazníků a vozidel, propojení účtů ze Správy vozidel a bezpečný vstup do dalších akcí.',
      size: 'wide',
      bodyClass: 'service-shell-modal-body--tools',
      renderContent: () => `
        <div class="service-shell-tools-grid">
          ${buildWorkspaceCustomerSearchSectionHtml({
            heading: 'Najít existujícího zákazníka',
            intro: 'Hledání podle e-mailu, telefonu nebo jména. Ověříte profil v aplikaci, pak propojíte nebo pošlete pozvánku.',
            searchButtonLabel: 'Hledat',
            showInviteFromSearch: true,
            extraHtml: '',
          })}
          <section class="service-shell-side-card" data-testid="service-intake-section">
            <h3>Najít vozidlo podle VIN / SPZ</h3>
            <p>Bezpečný lookup nad existující databází vozidel zákazníků. Pokud vozidlo existuje, nabídne se detail, přístup nebo nová zakázka.</p>
            <div class="service-shell-table-tools">
              <input class="service-shell-search" type="search" placeholder="VIN nebo SPZ" data-testid="service-vehicle-lookup-input" value="${escape(state.vehicleLookupQuery)}" oninput="window.serviceShell.setVehicleLookupQuery(this.value)">
              <button type="button" class="btn btn-primary" onclick="window.serviceShell.searchVehicles()">Hledat vozidlo</button>
            </div>
            ${vehicleMeta?.has_conflict ? `<div class="service-shell-inline-error">VIN a SPZ ukazují na rozdílné záznamy. Ověřte vstup a pokračujte přes správný detail.</div>` : ''}
            ${state.vehicleLookupError ? `<div class="service-shell-inline-error">${escape(state.vehicleLookupError)}</div>` : ''}
            <div class="service-shell-list">${vehicleRows}</div>
            <div class="service-shell-modal-footer service-shell-modal-footer--inline">
              <div class="service-shell-inline-alert">
                <span>Pokud vozidlo není v systému, servis ho smí založit jako nepřiřazené. Majitel ho později může převzít po ověření.</span>
              </div>
            </div>
          </section>
        </div>
      `,
      renderFooter: () => `
        <div class="service-shell-modal-footer">
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zavřít</button>
        </div>
      `,
    });
  }

  function openServiceToolsModal() {
    state.accountMenuOpen = false;
    renderServiceToolsModal();
  }

  function setCustomerSearchQuery(value) {
    state.customerSearchQuery = String(value || '');
  }

  function setVehicleLookupQuery(value) {
    state.vehicleLookupQuery = String(value || '');
  }

  async function openCreateWorkOrderModal(prefill = {}) {
    if (!hasFloatingModalSupport()) {
      if (typeof originalOpenServiceDashboardCreateModal === 'function') {
        return originalOpenServiceDashboardCreateModal();
      }
      return;
    }
    const customers = Array.isArray(state.customers) ? state.customers : [];
    const technicians = Array.isArray(state.technicians) && state.technicians.length
      ? state.technicians
      : [{ technician_id: Number(window.currentUser?.id || 0), name: window.currentUser?.name || window.currentUser?.email || 'Hlavní technik' }];
    const preferredOwnerId = Number(prefill.ownerId || 0);
    const preferredUnowned = prefill.unownedOnly === true
      || (Number(prefill.ownerId || 0) <= 0 && Number(prefill.vehicleId || 0) > 0);
    const ownerOptions = [
      '<option value="__unowned__">Nepřiřazené vozidlo (bez majitele)</option>',
      ...(customers.length
        ? customers.map((item) => `<option value="${Number(item.customer_id)}" ${Number(item.customer_id) === preferredOwnerId ? 'selected' : ''}>${escape(item.name || item.email || `Zákazník #${Number(item.customer_id)}`)}</option>`)
        : ['<option value="" disabled>Nejsou dostupní propojení zákazníci</option>']),
    ].join('');
    openModal({
      key: 'work-order-create',
      entityType: 'work_order',
      kicker: 'Servisní zakázka',
      title: 'Nová zakázka',
      description: 'Zakázku lze založit jen nad existujícím propojeným klientem a schváleným vozidlem.',
      actions: {
        save: async () => {
          const ownerRaw = String(document.getElementById('serviceShellWorkOrderOwner')?.value || '').trim();
          const isUnowned = ownerRaw === '__unowned__';
          const ownerId = isUnowned ? 0 : Number(ownerRaw || 0);
          const vehicleId = Number(document.getElementById('serviceShellWorkOrderVehicle')?.value || 0);
          const technicianId = Number(document.getElementById('serviceShellWorkOrderTechnician')?.value || 0) || null;
          const title = String(document.getElementById('serviceShellWorkOrderTitle')?.value || '').trim();
          const dueDate = String(document.getElementById('serviceShellWorkOrderDueDate')?.value || '').trim() || null;
          const status = String(document.getElementById('serviceShellWorkOrderStatus')?.value || 'awaiting_client_approval').trim();
          const description = String(document.getElementById('serviceShellWorkOrderDescription')?.value || '').trim() || null;
          if ((!ownerId && !isUnowned) || !vehicleId || !title) {
            throw new Error('Vyberte klienta nebo nepřiřazené vozidlo, vozidlo a vyplňte název zakázky.');
          }
          try {
            const body = {
              vehicle_id: vehicleId,
              technician_id: technicianId,
              title,
              description,
              due_date: dueDate,
              status,
              source_type: 'manual',
            };
            if (!isUnowned) body.owner_id = ownerId;
            await window.apiCall('/api/service/work-orders', 'POST', body);
          } catch (error) {
            const detail = error?.payload?.detail;
            if (error?.status === 409 && detail?.code === 'duplicate_work_order') {
              return {
                close: false,
                error: detail.message || error.message || 'Duplicitní rozpracovaná zakázka.',
                message: detail.message || error.message || 'Duplicitní rozpracovaná zakázka.',
                messageType: 'warning',
                contextPatch: {
                  duplicateWorkOrderId: Number(detail.existing_work_order_id || 0),
                  duplicateWorkOrderTitle: detail.existing_work_order_title || '',
                },
              };
            }
            throw error;
          }
          return {
            close: true,
            refreshParent: true,
            message: 'Zakázka byla vytvořena.',
          };
        },
      },
      renderContent: () => `
        <div class="service-shell-modal-toolbar">
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.openServiceToolsModal()">Najít zákazníka nebo vozidlo</button>
        </div>
        <form class="service-dashboard-modal-form" onsubmit="event.preventDefault(); window.serviceShell.submitCreateWorkOrderModal();">
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellWorkOrderOwner">Zákazník</label>
              <select id="serviceShellWorkOrderOwner" onchange="window.serviceShell.populateCreateVehicleOptions(this.value)">
                ${ownerOptions}
              </select>
            </div>
            <div class="form-group">
              <label for="serviceShellWorkOrderVehicle">Vozidlo</label>
              <select id="serviceShellWorkOrderVehicle"><option value="">Načítám vozidla…</option></select>
            </div>
          </div>
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellWorkOrderTitle">Název zakázky</label>
              <input type="text" id="serviceShellWorkOrderTitle" placeholder="Např. diagnostika motoru">
            </div>
            <div class="form-group">
              <label for="serviceShellWorkOrderDueDate">Termín</label>
              <input type="date" id="serviceShellWorkOrderDueDate">
            </div>
          </div>
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellWorkOrderTechnician">Technik</label>
              <select id="serviceShellWorkOrderTechnician">
                ${technicians.map((item) => `<option value="${Number(item.technician_id)}">${escape(item.name || `Technik #${Number(item.technician_id)}`)}</option>`).join('')}
              </select>
            </div>
            <div class="form-group">
              <label for="serviceShellWorkOrderStatus">Stav</label>
              <select id="serviceShellWorkOrderStatus">
                <option value="awaiting_client_approval">Čeká na schválení</option>
                <option value="approved">Schváleno</option>
                <option value="in_progress">Rozpracováno</option>
                <option value="issue">Problém</option>
              </select>
            </div>
          </div>
          <div class="form-group">
            <label for="serviceShellWorkOrderDescription">Popis</label>
            <textarea id="serviceShellWorkOrderDescription" rows="4" placeholder="Rozsah prací, diagnóza, poznámky pro tým nebo klienta"></textarea>
          </div>
        </form>
      `,
      renderFooter: (modal) => renderMobileModalFooter(`
          ${Number(modal?.context?.duplicateWorkOrderId || 0) > 0
            ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal(); window.serviceShell.openWorkOrderDetailModal(${Number(modal.context.duplicateWorkOrderId)})">Otevřít existující zakázku</button>`
            : ''}
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zrušit</button>
          <button type="button" class="btn btn-primary" onclick="window.serviceShell.submitCreateWorkOrderModal()">${modal.saving ? 'Ukládám…' : 'Uložit zakázku'}</button>
      `),
    });
    const ownerSelectValue = preferredUnowned
      ? '__unowned__'
      : (preferredOwnerId > 0 ? String(preferredOwnerId) : String(customers[0]?.customer_id || '__unowned__'));
    const ownerSelect = document.getElementById('serviceShellWorkOrderOwner');
    if (ownerSelect) ownerSelect.value = ownerSelectValue;
    await populateCreateVehicleOptions(ownerSelectValue, Number(prefill.vehicleId || 0));
  }

  async function submitCreateWorkOrderModal() {
    if (isModalOpen('work-order-create')) {
      return runModalAction('save');
    }
  }

  function renderWorkOrderLineList(items, emptyText) {
    if (!Array.isArray(items) || !items.length) {
      return `<li class="service-shell-list-note">${escape(emptyText)}</li>`;
    }
    return items.map((item) => {
      const qty = item.quantity != null ? `${Number(item.quantity)} ${escape(item.unit || '')}`.trim() : '';
      const priceHint = Number(item.line_total_without_vat || 0) > 0
        ? ` <span class="service-shell-list-note">(interní cena ${Number(item.line_total_without_vat).toLocaleString('cs-CZ')} Kč)</span>`
        : '';
      const dateHint = item.worked_date ? ` <span class="service-shell-list-note">${escape(item.worked_date)}</span>` : '';
      const note = item.note ? ` — ${escape(item.note)}` : '';
      return `<li><strong>${escape(item.name || '-')}</strong>${qty ? ` (${escape(qty)})` : ''}${dateHint}${note}${priceHint}</li>`;
    }).join('');
  }

  function renderWorkOrderPhotoCards(photos) {
    if (!Array.isArray(photos) || !photos.length) {
      return '<li class="service-shell-list-note">Zatím bez fotodokumentace.</li>';
    }
    return photos.map((photo) => `
      <li class="service-work-order-photo-card" data-testid="service-work-order-photo-card">
        <div class="service-work-order-photo-card-head">
          <strong>${escape(photo.photo_type_label || photo.photo_type || 'Foto')}</strong>
          <span class="service-shell-list-note">${escape(photo.visibility_scope || 'service_private')}</span>
        </div>
        <button type="button" class="btn btn-secondary" onclick="window.serviceShell.openWorkOrderPhotoPreview(${Number(photo.work_order_id || 0)}, ${Number(photo.id)})">Zobrazit náhled</button>
        <div class="service-work-order-photo-card-actions">
          <select data-work-order-photo-visibility="${Number(photo.id)}" data-testid="service-work-order-photo-visibility">
            <option value="service_private" ${photo.visibility_scope === 'service_private' ? 'selected' : ''}>Servisní soukromé</option>
            <option value="owner_visible" ${photo.visibility_scope === 'owner_visible' ? 'selected' : ''}>Viditelné majiteli</option>
            <option value="safe_after_claim" ${photo.visibility_scope === 'safe_after_claim' ? 'selected' : ''}>Bezpečné po převzetí</option>
            <option value="internal_only" ${photo.visibility_scope === 'internal_only' ? 'selected' : ''}>Pouze interní</option>
          </select>
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.submitWorkOrderPhotoVisibility(${Number(photo.work_order_id || 0)}, ${Number(photo.id)})">Uložit viditelnost</button>
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.deleteWorkOrderPhoto(${Number(photo.work_order_id || 0)}, ${Number(photo.id)})">Skrýt</button>
        </div>
      </li>
    `).join('');
  }

  function timelineEventBadge(eventType) {
    const map = {
      intake_created: 'Příjem',
      work_order_created: 'Zakázka',
      work_order_completed: 'Dokončeno',
      service_record_created: 'Servis',
      photo_uploaded: 'Foto',
      reminder_created: 'Připomínka',
      reminder_completed: 'Splněno',
      mileage_recorded: 'Km',
      stk_recorded: 'STK',
      document_added: 'Dokument',
      quote_created: 'Nabídka',
      invoice_created: 'Faktura',
    };
    return map[String(eventType || '')] || 'Událost';
  }

  function formatTimelineDayLabel(iso) {
    if (!iso) return 'Bez data';
    try {
      const d = new Date(iso);
      return d.toLocaleDateString('cs-CZ', { weekday: 'short', day: 'numeric', month: 'long', year: 'numeric' });
    } catch (_e) {
      return String(iso).slice(0, 10);
    }
  }

  function groupTimelineByDay(items) {
    const groups = new Map();
    (Array.isArray(items) ? items : []).forEach((item) => {
      const day = String(item?.timestamp || '').slice(0, 10) || 'unknown';
      if (!groups.has(day)) groups.set(day, []);
      groups.get(day).push(item);
    });
    return Array.from(groups.entries()).sort((a, b) => b[0].localeCompare(a[0]));
  }

  function renderVehicleTimelineEvent(item) {
    const ts = item?.timestamp ? new Date(item.timestamp).toLocaleString('cs-CZ') : '-';
    const badge = timelineEventBadge(item?.event_type);
    const mileage = item?.mileage != null ? `<span class="vehicle-timeline-event-mileage">${Number(item.mileage).toLocaleString('cs-CZ')} km</span>` : '';
    const photo = item?.photo_preview?.preview_url
      ? `<img class="vehicle-timeline-event-photo" data-testid="vehicle-timeline-event-photo" src="${escape(item.photo_preview.preview_url)}" alt="Náhled fotky" loading="lazy">`
      : '';
    const serviceMeta = item?.service_only
      ? `<p class="service-shell-list-note">${escape(Object.values(item.service_only).filter(Boolean).join(' · '))}</p>`
      : '';
    return `
      <article class="vehicle-timeline-event" data-testid="vehicle-timeline-event">
        <div class="vehicle-timeline-event-head">
          <span class="vehicle-timeline-event-badge" data-testid="vehicle-timeline-event-badge">${escape(badge)}</span>
          <time class="vehicle-timeline-event-date" data-testid="vehicle-timeline-event-date">${escape(ts)}</time>
        </div>
        <h4 class="vehicle-timeline-event-title" data-testid="vehicle-timeline-event-title">${escape(item?.title || 'Událost')}</h4>
        <p class="vehicle-timeline-event-summary">${escape(item?.summary || '')}</p>
        ${mileage}
        ${photo}
        ${serviceMeta}
      </article>
    `;
  }

  async function loadVehicleTimeline(vehicleId) {
    const id = Number(vehicleId || 0);
    if (!id) return;
    state.vehicleTimelineVehicleId = id;
    state.vehicleTimelineLoading = true;
    state.vehicleTimelineError = '';
    render();
    try {
      const payload = await window.apiCall(`/api/v1/vehicles/${id}/timeline`, 'GET');
      state.vehicleTimelineCache[id] = Array.isArray(payload?.items) ? payload.items : [];
      state.vehicleTimelineError = '';
    } catch (err) {
      state.vehicleTimelineCache[id] = [];
      state.vehicleTimelineError = err?.message || 'Timeline se nepodařilo načíst.';
    } finally {
      state.vehicleTimelineLoading = false;
      render();
    }
  }

  function renderVehicleTimelineSection(options = {}) {
    const embedded = Boolean(options.embedded);
    const vehicleId = Number(options.vehicleId || state.vehicleTimelineVehicleId || 0);
    const vehicles = Array.isArray(state.vehicles) ? state.vehicles : [];
    const items = vehicleId > 0 ? (state.vehicleTimelineCache[vehicleId] || []) : [];
    const loading = state.vehicleTimelineLoading && state.vehicleTimelineVehicleId === vehicleId;
    const error = state.vehicleTimelineError && state.vehicleTimelineVehicleId === vehicleId ? state.vehicleTimelineError : '';
    const grouped = groupTimelineByDay(items);
    const selector = embedded ? '' : `
      <div class="vehicle-timeline-picker">
        <label for="vehicleTimelineSelect">Vozidlo</label>
        <select id="vehicleTimelineSelect" onchange="window.serviceShell.loadVehicleTimeline(Number(this.value))">
          <option value="">— vyberte vozidlo —</option>
          ${vehicles.map((v) => `<option value="${Number(v.id || v.vehicle_id || 0)}" ${Number(v.id || v.vehicle_id) === vehicleId ? 'selected' : ''}>${escape(v.label || v.plate || v.vin || `Vozidlo #${Number(v.id || 0)}`)}</option>`).join('')}
        </select>
      </div>
    `;
    const body = loading
      ? `<p class="service-shell-list-note" data-testid="vehicle-timeline-loading">Načítám timeline vozidla…</p>`
      : error
        ? `<p class="service-shell-list-note vehicle-timeline-error" data-testid="vehicle-timeline-error">${escape(error)}</p>`
        : !vehicleId
          ? `<p class="service-shell-list-note" data-testid="vehicle-timeline-empty">Vyberte vozidlo pro zobrazení servisní osy.</p>`
          : !items.length
            ? `<p class="service-shell-list-note" data-testid="vehicle-timeline-empty">Pro toto vozidlo zatím nejsou žádné události v timeline.</p>`
            : grouped.map(([day, dayItems]) => `
                <section class="vehicle-timeline-day-group">
                  <h3 class="vehicle-timeline-day-label">${escape(formatTimelineDayLabel(dayItems[0]?.timestamp || day))}</h3>
                  <div class="vehicle-timeline-day-events">${dayItems.map(renderVehicleTimelineEvent).join('')}</div>
                </section>
              `).join('');
    return `
      <section class="service-pro-card vehicle-timeline-section" data-testid="vehicle-timeline-section">
        <div class="service-pro-card-head"><h2>${embedded ? 'Timeline vozidla' : 'Timeline vozidla'}</h2></div>
        <p class="service-page-header-sub">Chronologická servisní osa — bezpečně filtrovaná podle role a viditelnosti.</p>
        ${selector}
        ${body}
      </section>
    `;
  }

  function renderWorkOrderBillingContactSection(detail, workOrderId) {
    const isUnowned = Boolean(detail?.is_unowned_vehicle) || Number(detail?.owner_id || detail?.customer_id || 0) <= 0;
    if (!isUnowned) return '';
    const contact = detail?.billing_contact || null;
    const woId = Number(workOrderId || 0);
    const hasContact = Boolean(contact?.billing_contact_id);
    const limitedNotice = hasContact
      ? ''
      : '<p class="service-shell-list-note" data-testid="service-billing-contact-limited-notice">Bez fakturačního kontaktu nelze vystavit fakturu k nepřiřazenému vozidlu.</p>';
    return `
      <section class="service-shell-side-card" data-testid="service-billing-contact-section" aria-label="Fakturační kontakt">
        <h3>Fakturační kontakt</h3>
        ${limitedNotice}
        <form class="service-billing-contact-form" data-testid="service-billing-contact-form" onsubmit="event.preventDefault(); window.serviceShell.saveWorkOrderBillingContact(${woId});">
          <label class="service-shell-field">
            <span>Jméno / název</span>
            <input type="text" id="serviceBillingContactName" data-testid="service-billing-contact-name" required minlength="2" maxlength="255" value="${escape(contact?.name || '')}" placeholder="Jan Novák nebo Firma s.r.o.">
          </label>
          <label class="service-shell-field">
            <span>E-mail</span>
            <input type="email" id="serviceBillingContactEmail" data-testid="service-billing-contact-email" maxlength="320" value="${escape(contact?.email || '')}" placeholder="volitelné">
          </label>
          <label class="service-shell-field">
            <span>Telefon</span>
            <input type="tel" id="serviceBillingContactPhone" data-testid="service-billing-contact-phone" maxlength="64" value="${escape(contact?.phone || '')}" placeholder="volitelné">
          </label>
          <label class="service-shell-field">
            <span>Firma</span>
            <input type="text" id="serviceBillingContactCompany" data-testid="service-billing-contact-company" maxlength="255" value="${escape(contact?.company_name || '')}" placeholder="volitelné">
          </label>
          <label class="service-shell-field">
            <span>Ulice</span>
            <input type="text" id="serviceBillingContactStreet" data-testid="service-billing-contact-address" maxlength="255" value="${escape(contact?.street || '')}" placeholder="volitelné">
          </label>
          <div class="service-work-order-add-row">
            <input type="text" id="serviceBillingContactCity" maxlength="128" value="${escape(contact?.city || '')}" placeholder="Město">
            <input type="text" id="serviceBillingContactZip" maxlength="16" value="${escape(contact?.zip || '')}" placeholder="PSČ">
          </div>
          <div class="service-work-order-add-row">
            <input type="text" id="serviceBillingContactIco" maxlength="32" value="${escape(contact?.ico || '')}" placeholder="IČO">
            <input type="text" id="serviceBillingContactDic" maxlength="32" value="${escape(contact?.dic || '')}" placeholder="DIČ">
          </div>
          <p class="service-shell-list-note service-work-order-billing-error hidden" id="serviceBillingContactError" data-testid="service-billing-contact-error"></p>
          <p class="service-shell-list-note service-billing-contact-success hidden" id="serviceBillingContactSuccess" data-testid="service-billing-contact-success"></p>
          <button type="submit" class="btn btn-primary" data-testid="service-billing-contact-save-button">${hasContact ? 'Uložit kontakt' : 'Uložit fakturační kontakt'}</button>
        </form>
      </section>
    `;
  }

  function collectWorkOrderBillingContactPayload() {
    return {
      name: String(document.getElementById('serviceBillingContactName')?.value || '').trim(),
      email: String(document.getElementById('serviceBillingContactEmail')?.value || '').trim() || null,
      phone: String(document.getElementById('serviceBillingContactPhone')?.value || '').trim() || null,
      company_name: String(document.getElementById('serviceBillingContactCompany')?.value || '').trim() || null,
      street: String(document.getElementById('serviceBillingContactStreet')?.value || '').trim() || null,
      city: String(document.getElementById('serviceBillingContactCity')?.value || '').trim() || null,
      zip: String(document.getElementById('serviceBillingContactZip')?.value || '').trim() || null,
      ico: String(document.getElementById('serviceBillingContactIco')?.value || '').trim() || null,
      dic: String(document.getElementById('serviceBillingContactDic')?.value || '').trim() || null,
    };
  }

  function setBillingContactFormFeedback({ error = '', success = '' } = {}) {
    const errEl = document.getElementById('serviceBillingContactError');
    const okEl = document.getElementById('serviceBillingContactSuccess');
    if (errEl) {
      errEl.textContent = error || '';
      errEl.classList.toggle('hidden', !error);
    }
    if (okEl) {
      okEl.textContent = success || '';
      okEl.classList.toggle('hidden', !success);
    }
  }

  async function saveWorkOrderBillingContact(workOrderId) {
    const id = Number(workOrderId || 0);
    if (!id) return;
    setBillingContactFormFeedback({ error: '', success: '' });
    const payload = collectWorkOrderBillingContactPayload();
    if (!payload.name || payload.name.length < 2) {
      setBillingContactFormFeedback({ error: 'Jméno nebo název fakturačního kontaktu musí mít alespoň 2 znaky.' });
      return;
    }
    const detail = state.workOrderDetailCache?.[id] || null;
    const hasContact = Boolean(detail?.billing_contact?.billing_contact_id);
    const method = hasContact ? 'PUT' : 'POST';
    try {
      const result = await window.apiCall(`/api/service/work-orders/${id}/billing-contact`, method, payload);
      if (state.workOrderDetailCache?.[id]) {
        state.workOrderDetailCache[id].billing_contact = result?.billing_contact || null;
      }
      setBillingContactFormFeedback({ success: 'Fakturační kontakt byl uložen.' });
      if (typeof window.showAlert === 'function') {
        window.showAlert('Fakturační kontakt byl uložen.', 'success');
      }
      await reloadWorkOrderDetailModal(id);
    } catch (err) {
      const msg = err?.detail?.message || err?.message || 'Fakturační kontakt se nepodařilo uložit.';
      setBillingContactFormFeedback({ error: msg });
      setWorkOrderLimitedNotice(msg);
    }
  }

  function renderWorkOrderBillingPanel(detail, workOrderId) {
    const caps = detail?.capabilities || {};
    const notices = detail?.limited_notices || {};
    const billingNotice = notices.billing || 'Ceny a faktury jsou pouze pro servis — majitel je v historii nevidí.';
    const quote = detail?.quote_summary || null;
    const invoice = detail?.invoice_summary || null;
    const canQuote = caps.quotes !== false;
    const canInvoice = caps.invoices !== false;
    const canPdf = caps.invoice_pdf !== false && invoice?.pdf_available !== false;
    const woId = Number(workOrderId || 0);
    const ownerId = Number(detail?.owner_id || detail?.customer_id || 0);
    const isUnowned = Boolean(detail?.is_unowned_vehicle) || ownerId <= 0;
    const billingContactReady = Boolean(detail?.billing_contact?.ready_for_invoice);
    const canCreateUnownedInvoice = canInvoice && isUnowned && billingContactReady;
    return `
      ${renderWorkOrderBillingContactSection(detail, workOrderId)}
      <p class="service-shell-list-note" data-testid="service-work-order-billing-limited-notice">${escape(billingNotice)}</p>
      <section class="service-shell-side-card" data-testid="service-work-order-quote-panel" aria-label="Nabídka ze zakázky">
        <h3>Nabídka</h3>
        ${quote ? `
          <div class="service-shell-list">
            <div class="service-shell-list-row"><span class="service-shell-list-title">Stav</span><span class="service-shell-list-value" data-testid="service-work-order-quote-status">${escape(quote.status_label || quote.status || '-')}</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Celkem</span><span class="service-shell-list-value">${escape(quote.total_price != null ? `${Number(quote.total_price).toLocaleString('cs-CZ')} Kč` : '-')}</span></div>
          </div>
          <div class="service-shell-modal-actions">
            <button type="button" class="btn btn-secondary" onclick="window.serviceShell.openQuoteModal(${Number(quote.quote_id || 0)})">Otevřít nabídku</button>
            <button type="button" class="btn btn-secondary" onclick="window.serviceShell.navigate('billing')">Otevřít v Nabídky a faktury</button>
          </div>
        ` : `
          <p class="service-shell-list-note">K zakázce zatím není nabídka.</p>
          <button type="button" class="btn btn-secondary" data-testid="service-work-order-create-quote-button" ${canQuote ? '' : 'disabled'} onclick="window.serviceShell.createWorkOrderQuote(${woId})">Vytvořit nabídku</button>
        `}
      </section>
      <section class="service-shell-side-card" data-testid="service-work-order-invoice-panel" aria-label="Faktura ze zakázky">
        <h3>Faktura</h3>
        ${invoice ? `
          <div class="service-shell-list">
            <div class="service-shell-list-row"><span class="service-shell-list-title">Stav</span><span class="service-shell-list-value" data-testid="service-work-order-invoice-status">${escape(invoice.status_label || invoice.status || '-')}</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Celkem</span><span class="service-shell-list-value">${invoice.total != null ? escape(`${Number(invoice.total).toLocaleString('cs-CZ')} ${invoice.currency || 'CZK'}`) : '-'}</span></div>
            ${invoice.invoice_number ? `<div class="service-shell-list-row"><span class="service-shell-list-title">Číslo</span><span class="service-shell-list-value">${escape(invoice.invoice_number)}</span></div>` : ''}
          </div>
          <div class="service-shell-modal-actions">
            <button type="button" class="btn btn-secondary" onclick="window.serviceShell.openServiceInvoiceDetailModal(${Number(invoice.invoice_id || 0)})">Otevřít fakturu</button>
            <button type="button" class="btn btn-secondary" data-testid="service-work-order-invoice-pdf-button" ${canPdf ? '' : 'disabled'} onclick="window.serviceShell.openServiceInvoicePdf(${Number(invoice.invoice_id || 0)})">Stáhnout PDF</button>
            <button type="button" class="btn btn-secondary" onclick="window.serviceShell.navigate('billing')">Otevřít v Nabídky a faktury</button>
          </div>
        ` : `
          <p class="service-shell-list-note">${isUnowned && !billingContactReady ? 'Pro vystavení faktury k nepřiřazenému vozidlu doplňte fakturační kontakt zákazníka.' : 'K zakázce zatím není faktura.'}</p>
          <button type="button" class="btn btn-secondary" data-testid="service-work-order-create-invoice-button" ${(canInvoice && !isUnowned) || canCreateUnownedInvoice ? '' : 'disabled'} onclick="window.serviceShell.createWorkOrderInvoice(${woId})">Vytvořit fakturu</button>
        `}
      </section>
    `;
  }

  function renderWorkOrderItemsPanel(detail, workOrderId) {
    const items = detail?.items || {};
    const caps = detail?.capabilities || {};
    const notices = detail?.limited_notices || {};
    const labor = items.labor || [];
    const parts = items.parts || [];
    const times = items.time || [];
    const photos = Array.isArray(detail?.photos) ? detail.photos : [];
    const photoNotice = notices.photos || 'Interní fotky a doklady nejsou viditelné pro majitele.';
    const recordId = Number(detail?.service_record_id || 0);
    const canAddLabor = caps.labor !== false;
    const canAddPart = caps.parts !== false;
    const canAddTime = caps.time !== false;
    const canAddPhotos = caps.photos !== false;
    const canCreateRecord = Boolean(caps.create_service_record) && recordId <= 0;
    const limitedNotice = state.workOrderLimitedNotice
      ? `<p class="service-shell-list-note" data-testid="service-work-order-limited-notice">${escape(state.workOrderLimitedNotice)}</p>`
      : '';
    return `
      ${limitedNotice}
      <section class="service-shell-side-card" aria-label="Práce na zakázce">
        <h3>Práce</h3>
        <ul class="service-shell-list" data-testid="service-work-order-labor-list">${renderWorkOrderLineList(labor, 'Zatím bez evidované práce.')}</ul>
        <div class="service-work-order-add-row">
          <input type="text" id="serviceWoLaborName" placeholder="Název práce" ${canAddLabor ? '' : 'disabled'}>
          <input type="number" id="serviceWoLaborHours" min="0.1" step="0.1" placeholder="Hodiny" value="1" ${canAddLabor ? '' : 'disabled'}>
          <button type="button" class="btn btn-secondary" data-testid="service-work-order-add-labor-button" ${canAddLabor ? '' : 'disabled'} onclick="window.serviceShell.submitWorkOrderLabor(${workOrderId})">Přidat práci</button>
        </div>
      </section>
      <section class="service-shell-side-card" aria-label="Díly na zakázce">
        <h3>Díly</h3>
        <ul class="service-shell-list" data-testid="service-work-order-part-list">${renderWorkOrderLineList(parts, 'Zatím bez evidovaných dílů.')}</ul>
        <div class="service-work-order-add-row">
          <input type="text" id="serviceWoPartName" placeholder="Název dílu" ${canAddPart ? '' : 'disabled'}>
          <input type="number" id="serviceWoPartQty" min="0.01" step="0.01" placeholder="Množství" value="1" ${canAddPart ? '' : 'disabled'}>
          <input type="text" id="serviceWoPartUnit" placeholder="Jednotka" value="ks" ${canAddPart ? '' : 'disabled'}>
          <button type="button" class="btn btn-secondary" data-testid="service-work-order-add-part-button" ${canAddPart ? '' : 'disabled'} onclick="window.serviceShell.submitWorkOrderPart(${workOrderId})">Přidat díl</button>
        </div>
      </section>
      <section class="service-shell-side-card" aria-label="Čas práce">
        <h3>Čas</h3>
        <ul class="service-shell-list" data-testid="service-work-order-time-list">${renderWorkOrderLineList(times, 'Zatím bez evidovaného času.')}</ul>
        <div class="service-work-order-add-row">
          <input type="number" id="serviceWoTimeMinutes" min="1" step="1" placeholder="Minuty" value="60" ${canAddTime ? '' : 'disabled'}>
          <input type="date" id="serviceWoTimeDate" ${canAddTime ? '' : 'disabled'}>
          <input type="text" id="serviceWoTimeNote" placeholder="Poznámka" ${canAddTime ? '' : 'disabled'}>
          <button type="button" class="btn btn-secondary" data-testid="service-work-order-add-time-button" ${canAddTime ? '' : 'disabled'} onclick="window.serviceShell.submitWorkOrderTime(${workOrderId})">Přidat čas</button>
        </div>
      </section>
      <section class="service-shell-side-card" aria-label="Fotodokumentace zakázky">
        <h3>Fotodokumentace</h3>
        <p class="service-shell-list-note" data-testid="service-work-order-photo-limited-notice">${escape(photoNotice)}</p>
        <ul class="service-shell-list service-work-order-photo-list" data-testid="service-work-order-photo-list">${renderWorkOrderPhotoCards(photos)}</ul>
        <div class="service-work-order-add-row">
          <input type="file" id="serviceWoPhotoInput" accept="image/jpeg,image/png,image/webp" class="hidden" data-testid="service-work-order-photo-input" ${canAddPhotos ? '' : 'disabled'} onchange="window.serviceShell.handleWorkOrderPhotoSelection(this, ${workOrderId})">
          <select id="serviceWoPhotoType" data-testid="service-work-order-photo-type" ${canAddPhotos ? '' : 'disabled'}>
            <option value="intake">Vstupní stav</option>
            <option value="damage">Poškození</option>
            <option value="work_progress">Průběh práce</option>
            <option value="part">Díl</option>
            <option value="completion">Výstupní stav</option>
            <option value="internal">Interní fotka</option>
          </select>
          <select id="serviceWoPhotoVisibility" data-testid="service-work-order-photo-visibility-upload" ${canAddPhotos ? '' : 'disabled'}>
            <option value="service_private">Servisní soukromé</option>
            <option value="owner_visible">Viditelné majiteli</option>
            <option value="safe_after_claim">Bezpečné po převzetí</option>
            <option value="internal_only">Pouze interní</option>
          </select>
          <button type="button" class="btn btn-secondary" data-testid="service-work-order-add-photo-button" ${canAddPhotos ? '' : 'disabled'} onclick="document.getElementById('serviceWoPhotoInput')?.click()">Vybrat foto</button>
          <button type="button" class="btn btn-primary" data-testid="service-work-order-photo-upload-submit" ${canAddPhotos ? '' : 'disabled'} onclick="window.serviceShell.triggerWorkOrderPhotoUpload(${workOrderId})">Nahrát foto</button>
        </div>
        <p class="service-shell-list-note service-work-order-photo-error hidden" id="serviceWoPhotoError" data-testid="service-work-order-photo-error"></p>
      </section>
      <section class="service-shell-side-card" aria-label="Servisní záznam ze zakázky">
        <h3>Servisní záznam</h3>
        ${recordId > 0
          ? `<p class="service-shell-list-note">Zakázka má servisní záznam #${recordId}.</p>`
          : `<p class="service-shell-list-note">${canCreateRecord ? 'Po dokončení zakázky vytvořte servisní záznam pro bezpečnou historii majitele.' : 'Servisní záznam lze vytvořit až po dokončení zakázky.'}</p>
             <div class="service-work-order-add-row">
               <input type="number" id="serviceWoRecordMileage" min="0" step="1" placeholder="km (volitelné)" ${canCreateRecord ? '' : 'disabled'}>
               <button type="button" class="btn btn-secondary" data-testid="service-work-order-create-record-button" ${canCreateRecord ? '' : 'disabled'} onclick="window.serviceShell.submitWorkOrderServiceRecord(${workOrderId})">Vytvořit servisní záznam</button>
             </div>`}
      </section>
      ${renderWorkOrderBillingPanel(detail, workOrderId)}
    `;
  }

  async function createWorkOrderQuote(workOrderId) {
    const id = Number(workOrderId || 0);
    if (!id) return;
    try {
      const quote = await window.apiCall(`/api/service/work-orders/${id}/quote`, 'POST');
      if (typeof window.showAlert === 'function') {
        window.showAlert('Nabídka ze zakázky byla vytvořena.', 'success');
      }
      await reloadWorkOrderDetailModal(id);
      if (quote?.id) openQuoteModal(Number(quote.id));
    } catch (err) {
      const existingId = Number(err?.detail?.quote_id || err?.payload?.quote_id || 0);
      if (existingId > 0) {
        if (typeof window.showAlert === 'function') window.showAlert('K zakázce už existuje nabídka.', 'info');
        await reloadWorkOrderDetailModal(id);
        openQuoteModal(existingId);
        return;
      }
      setWorkOrderLimitedNotice(err?.message || 'Nabídku se nepodařilo vytvořit.');
      await reloadWorkOrderDetailModal(id);
    }
  }

  async function createWorkOrderInvoice(workOrderId) {
    const id = Number(workOrderId || 0);
    if (!id) return;
    try {
      const invoice = await window.apiCall(`/api/service/work-orders/${id}/invoice`, 'POST', {});
      if (typeof window.showAlert === 'function') {
        const label = invoice?.invoice_number ? ` ${invoice.invoice_number}` : '';
        window.showAlert(`Faktura${label} ze zakázky byla vytvořena.`, 'success');
      }
      await reloadWorkOrderDetailModal(id);
      if (invoice?.id) openServiceInvoiceDetailModal(Number(invoice.id));
    } catch (err) {
      const existingId = Number(err?.detail?.invoice_id || err?.payload?.invoice_id || 0);
      if (existingId > 0) {
        if (typeof window.showAlert === 'function') window.showAlert('K zakázce už existuje faktura.', 'info');
        await reloadWorkOrderDetailModal(id);
        openServiceInvoiceDetailModal(existingId);
        return;
      }
      setWorkOrderLimitedNotice(err?.detail?.message || err?.message || 'Fakturu se nepodařilo vytvořit.');
      await reloadWorkOrderDetailModal(id);
    }
  }

  async function reloadWorkOrderDetailModal(workOrderId) {
    const id = Number(workOrderId || 0);
    if (!id) return;
    state.workOrderLimitedNotice = '';
    await openWorkOrderDetailModal(id);
  }

  async function submitWorkOrderLabor(workOrderId) {
    const id = Number(workOrderId || 0);
    const name = String(document.getElementById('serviceWoLaborName')?.value || '').trim();
    const hours = Number(document.getElementById('serviceWoLaborHours')?.value || 0);
    if (!name || !(hours > 0)) {
      setWorkOrderLimitedNotice('Vyplňte název práce a kladný počet hodin.');
      await reloadWorkOrderDetailModal(id);
      return;
    }
    try {
      await window.apiCall(`/api/service/work-orders/${id}/labor`, 'POST', { name, hours });
      if (typeof window.showAlert === 'function') window.showAlert('Práce byla přidána.', 'success');
      await reloadWorkOrderDetailModal(id);
    } catch (err) {
      setWorkOrderLimitedNotice(err?.message || 'Práci se nepodařilo uložit.');
      await reloadWorkOrderDetailModal(id);
    }
  }

  async function submitWorkOrderPart(workOrderId) {
    const id = Number(workOrderId || 0);
    const name = String(document.getElementById('serviceWoPartName')?.value || '').trim();
    const quantity = Number(document.getElementById('serviceWoPartQty')?.value || 0);
    const unit = String(document.getElementById('serviceWoPartUnit')?.value || 'ks').trim() || 'ks';
    if (!name || !(quantity > 0)) {
      setWorkOrderLimitedNotice('Vyplňte název dílu a kladné množství.');
      await reloadWorkOrderDetailModal(id);
      return;
    }
    try {
      await window.apiCall(`/api/service/work-orders/${id}/parts`, 'POST', { name, quantity, unit });
      if (typeof window.showAlert === 'function') window.showAlert('Díl byl přidán.', 'success');
      await reloadWorkOrderDetailModal(id);
    } catch (err) {
      setWorkOrderLimitedNotice(err?.message || 'Díl se nepodařilo uložit.');
      await reloadWorkOrderDetailModal(id);
    }
  }

  async function submitWorkOrderTime(workOrderId) {
    const id = Number(workOrderId || 0);
    const minutes = Number(document.getElementById('serviceWoTimeMinutes')?.value || 0);
    const workedDate = String(document.getElementById('serviceWoTimeDate')?.value || '').trim() || null;
    const note = String(document.getElementById('serviceWoTimeNote')?.value || '').trim() || null;
    if (!(minutes > 0)) {
      setWorkOrderLimitedNotice('Zadejte kladný počet minut.');
      await reloadWorkOrderDetailModal(id);
      return;
    }
    try {
      await window.apiCall(`/api/service/work-orders/${id}/time`, 'POST', {
        minutes: Math.round(minutes),
        worked_date: workedDate,
        note,
      });
      if (typeof window.showAlert === 'function') window.showAlert('Čas byl přidán.', 'success');
      await reloadWorkOrderDetailModal(id);
    } catch (err) {
      setWorkOrderLimitedNotice(err?.message || 'Čas se nepodařilo uložit.');
      await reloadWorkOrderDetailModal(id);
    }
  }

  async function submitWorkOrderComplete(workOrderId) {
    const id = Number(workOrderId || 0);
    try {
      await window.apiCall(`/api/service/work-orders/${id}/complete`, 'POST', {});
      if (typeof window.showAlert === 'function') window.showAlert('Zakázka byla dokončena.', 'success');
      await reloadWorkOrderDetailModal(id);
    } catch (err) {
      setWorkOrderLimitedNotice(err?.message || 'Zakázku se nepodařilo dokončit.');
      await reloadWorkOrderDetailModal(id);
    }
  }

  async function submitWorkOrderServiceRecord(workOrderId) {
    const id = Number(workOrderId || 0);
    const mileageRaw = document.getElementById('serviceWoRecordMileage')?.value;
    const mileage = mileageRaw === '' || mileageRaw == null ? null : Number(mileageRaw);
    try {
      const payload = {};
      if (mileage != null && !Number.isNaN(mileage) && mileage >= 0) payload.mileage = Math.round(mileage);
      await window.apiCall(`/api/service/work-orders/${id}/service-record`, 'POST', payload);
      if (typeof window.showAlert === 'function') window.showAlert('Servisní záznam byl vytvořen.', 'success');
      await reloadWorkOrderDetailModal(id);
    } catch (err) {
      setWorkOrderLimitedNotice(err?.message || 'Servisní záznam se nepodařilo vytvořit.');
      await reloadWorkOrderDetailModal(id);
    }
  }

  let pendingWorkOrderPhotoFile = null;

  function showWorkOrderPhotoError(message) {
    const el = document.getElementById('serviceWoPhotoError');
    if (!el) return;
    const text = String(message || '').trim();
    if (!text) {
      el.textContent = '';
      el.classList.add('hidden');
      return;
    }
    el.textContent = text;
    el.classList.remove('hidden');
  }

  async function handleWorkOrderPhotoSelection(input, workOrderId) {
    const file = (input?.files && input.files[0]) ? input.files[0] : null;
    pendingWorkOrderPhotoFile = file;
    showWorkOrderPhotoError(file ? `Vybráno: ${file.name}` : '');
  }

  async function triggerWorkOrderPhotoUpload(workOrderId) {
    const id = Number(workOrderId || 0);
    const file = pendingWorkOrderPhotoFile;
    if (!id || !file) {
      showWorkOrderPhotoError('Nejprve vyberte obrázek (JPEG, PNG nebo WebP).');
      return;
    }
    const photoType = String(document.getElementById('serviceWoPhotoType')?.value || 'work_progress').trim();
    const visibilityScope = String(document.getElementById('serviceWoPhotoVisibility')?.value || 'service_private').trim();
    showWorkOrderPhotoError('Nahrávám…');
    try {
      const fileContentBase64 = await fileToBase64(file);
      await window.apiCall(`/api/service/work-orders/${id}/photos`, 'POST', {
        photo_type: photoType,
        visibility_scope: visibilityScope,
        file_name: file.name || 'photo.jpg',
        file_mime_type: file.type || 'image/jpeg',
        file_content_base64: fileContentBase64,
      }, 180000);
      pendingWorkOrderPhotoFile = null;
      const input = document.getElementById('serviceWoPhotoInput');
      if (input) input.value = '';
      showWorkOrderPhotoError('');
      if (typeof window.showAlert === 'function') window.showAlert('Fotka byla nahrána.', 'success');
      await reloadWorkOrderDetailModal(id);
    } catch (err) {
      showWorkOrderPhotoError(err?.message || 'Nahrání fotky se nepodařilo.');
      await reloadWorkOrderDetailModal(id);
    }
  }

  async function submitWorkOrderPhotoVisibility(workOrderId, photoId) {
    const woId = Number(workOrderId || 0);
    const pid = Number(photoId || 0);
    const select = document.querySelector(`[data-work-order-photo-visibility="${pid}"]`);
    const visibilityScope = String(select?.value || 'service_private').trim();
    try {
      await window.apiCall(`/api/service/work-orders/${woId}/photos/${pid}/visibility`, 'PUT', {
        visibility_scope: visibilityScope,
      });
      if (typeof window.showAlert === 'function') window.showAlert('Viditelnost fotky byla uložena.', 'success');
      await reloadWorkOrderDetailModal(woId);
    } catch (err) {
      setWorkOrderLimitedNotice(err?.message || 'Viditelnost se nepodařilo uložit.');
      await reloadWorkOrderDetailModal(woId);
    }
  }

  async function openWorkOrderPhotoPreview(workOrderId, photoId) {
    const woId = Number(workOrderId || 0);
    const pid = Number(photoId || 0);
    if (!woId || !pid) return;
    try {
      const { blob } = await payrollFetchBlob(`/api/service/work-orders/${woId}/photos/${pid}/file`);
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank', 'noopener');
      window.setTimeout(() => {
        try {
          URL.revokeObjectURL(url);
        } catch (e) {
          /* ignore */
        }
      }, 120000);
    } catch (err) {
      showWorkOrderPhotoError(err?.message || 'Náhled fotky se nepodařilo načíst.');
    }
  }

  async function deleteWorkOrderPhoto(workOrderId, photoId) {
    const woId = Number(workOrderId || 0);
    const pid = Number(photoId || 0);
    if (!woId || !pid) return;
    try {
      await window.apiCall(`/api/service/work-orders/${woId}/photos/${pid}`, 'DELETE');
      if (typeof window.showAlert === 'function') window.showAlert('Fotka byla skryta.', 'success');
      await reloadWorkOrderDetailModal(woId);
    } catch (err) {
      setWorkOrderLimitedNotice(err?.message || 'Fotku se nepodařilo odstranit.');
      await reloadWorkOrderDetailModal(woId);
    }
  }

  async function openWorkOrderDetailModal(workOrderId) {
    const id = Number(workOrderId || 0);
    if (!id || !hasFloatingModalSupport()) return;
    const technicians = Array.isArray(state.technicians) && state.technicians.length
      ? state.technicians
      : [{ technician_id: Number(window.currentUser?.id || 0), name: window.currentUser?.name || window.currentUser?.email || 'Hlavní technik' }];
    openModal({
      key: `work-order-detail-${id}`,
      entityType: 'work_order',
      kicker: `Zakázka #${id}`,
      title: 'Detail zakázky',
      description: 'Úpravy detailu, auditní stopa a navázané servisní workflow v jednom modal lifecycle.',
      load: async () => window.apiCall(`/api/service/work-orders/${id}`, 'GET'),
      actions: {
        save: async () => {
          const status = String(document.getElementById('serviceShellDetailStatus')?.value || 'awaiting_client_approval').trim();
          const dueDate = String(document.getElementById('serviceShellDetailDueDate')?.value || '').trim() || null;
          const technicianId = Number(document.getElementById('serviceShellDetailTechnicianId')?.value || 0) || null;
          const description = String(document.getElementById('serviceShellDetailDescription')?.value || '').trim() || null;
          await window.apiCall(`/api/service/work-orders/${id}`, 'PUT', {
            status,
            due_date: dueDate,
            technician_id: technicianId,
            description,
          });
          return {
            close: true,
            refreshParent: true,
            message: 'Zakázka byla aktualizována.',
          };
        },
      },
      renderContent: (modal) => {
        const detail = modal.data || {};
        state.workOrderDetailCache[id] = detail;
        const quote = detail?.quote_summary || null;
        return `
          <div class="service-shell-modal-summary" data-testid="service-work-order-detail">
            <span>${escape(detail?.customer_name || '-')}</span>
            <span>${escape(detail?.vehicle_label || '-')}</span>
          </div>
          <form class="service-dashboard-modal-form" onsubmit="event.preventDefault(); window.serviceShell.submitWorkOrderDetailUpdate(${id});">
            <div class="service-dashboard-modal-grid cols-2">
              <div class="form-group">
                <label for="serviceShellDetailStatus">Stav</label>
                <select id="serviceShellDetailStatus" data-testid="service-work-order-status">
                  <option value="awaiting_client_approval" ${detail?.status === 'awaiting_client_approval' ? 'selected' : ''}>Čeká na schválení</option>
                  <option value="approved" ${detail?.status === 'approved' ? 'selected' : ''}>Schváleno</option>
                  <option value="in_progress" ${detail?.status === 'in_progress' ? 'selected' : ''}>Rozpracováno</option>
                  <option value="issue" ${detail?.status === 'issue' ? 'selected' : ''}>Problém</option>
                  <option value="completed" ${detail?.status === 'completed' ? 'selected' : ''}>Dokončeno</option>
                </select>
              </div>
              <div class="form-group">
                <label for="serviceShellDetailDueDate">Termín</label>
                <input type="date" id="serviceShellDetailDueDate" value="${escape(String(detail?.due_date || '').slice(0, 10))}">
              </div>
            </div>
            <div class="service-dashboard-modal-grid cols-2">
              <div class="form-group">
                <label for="serviceShellDetailTechnicianId">Technik</label>
                <select id="serviceShellDetailTechnicianId">
                  ${technicians.map((item) => `<option value="${Number(item.technician_id)}" ${Number(item.technician_id) === Number(detail?.technician_id || 0) ? 'selected' : ''}>${escape(item.name || `Technik #${Number(item.technician_id)}`)}</option>`).join('')}
                </select>
              </div>
              <div class="form-group">
                <label>Zdroj</label>
                <input type="text" value="${escape(detail?.source_label || detail?.source || '-')}" disabled>
              </div>
            </div>
            <div class="service-dashboard-modal-grid cols-2">
              <div class="form-group">
                <label>Zákazník</label>
                <input type="text" value="${escape(detail?.customer_name || '-')}" disabled>
              </div>
              <div class="form-group">
                <label>VIN / SPZ</label>
                <input type="text" value="${escape(detail?.vehicle_vin || '-')}${detail?.vehicle_spz ? ` / ${escape(detail.vehicle_spz)}` : ''}" disabled>
              </div>
            </div>
            <div class="form-group">
              <label for="serviceShellDetailDescription">Popis</label>
              <textarea id="serviceShellDetailDescription" rows="4">${escape(detail?.description || '')}</textarea>
            </div>
            ${renderWorkOrderItemsPanel(detail, id)}
            <div class="form-group">
              <label>Audit</label>
              <div class="service-dashboard-empty service-shell-modal-audit">
                ${(Array.isArray(detail?.audit_log) && detail.audit_log.length)
                  ? detail.audit_log.map((item) => `${escape(formatDate(item.created_at))} • ${escape(item.action || 'update')}`).join('<br>')
                  : 'Bez auditních záznamů.'}
              </div>
            </div>
            <div class="service-shell-modal-actions">
              <button type="button" class="btn btn-secondary" data-testid="service-work-order-complete-button" ${detail?.status === 'completed' ? 'disabled' : ''} onclick="window.serviceShell.submitWorkOrderComplete(${id})">Dokončit zakázku</button>
            </div>
          </form>
        `;
      },
      renderFooter: (modal) => renderMobileModalFooter(`
          ${Number(modal?.data?.customer_id || 0) > 0 ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.openCustomerDetailModal(${Number(modal.data.customer_id)})">Zákazník</button>` : ''}
          ${Number(modal?.data?.vehicle_id || 0) > 0 ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.openVehicleDetailModal(${Number(modal.data.vehicle_id)})">Vozidlo</button>` : ''}
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zavřít</button>
          <button type="button" class="btn btn-primary" onclick="window.serviceShell.submitWorkOrderDetailUpdate(${id})">${modal.saving ? 'Ukládám…' : 'Uložit změny'}</button>
      `),
    });
  }

  async function submitWorkOrderDetailUpdate(workOrderId) {
    if (isModalOpen(`work-order-detail-${Number(workOrderId || 0)}`)) {
      return runModalAction('save');
    }
  }

  function setWorkOrderLimitedNotice(message) {
    state.workOrderLimitedNotice = String(message || '').trim();
    render();
  }

  function openWorkOrderVehicleContext(vehicleId) {
    const id = Number(vehicleId || 0);
    if (id > 0) {
      state.searchTerm = String(id);
    }
    navigate('vehicles');
  }

  async function openAddVehicleModal(customerId = null, defaults = {}) {
    if (!hasFloatingModalSupport()) return;
    const customers = Array.isArray(state.customers) ? state.customers : [];
    const preferredCustomerId = Number(customerId || customers[0]?.customer_id || 0);
    openModal({
      key: 'vehicle-create',
      entityType: 'vehicle',
      kicker: 'Vozidlo klienta',
      title: 'Založit nové vozidlo',
      description: 'Před uložením se vozidlo ověří proti existující databázi podle VIN nebo SPZ.',
      actions: {
        save: async () => {
          const customerIdValue = Number(document.getElementById('serviceShellAddVehicleCustomer')?.value || 0);
          const nickname = String(document.getElementById('serviceShellAddVehicleNickname')?.value || '').trim();
          const plate = String(document.getElementById('serviceShellAddVehiclePlate')?.value || '').trim();
          const vin = String(document.getElementById('serviceShellAddVehicleVin')?.value || '').trim().toUpperCase();
          const brand = String(document.getElementById('serviceShellAddVehicleBrand')?.value || '').trim() || null;
          const model = String(document.getElementById('serviceShellAddVehicleModel')?.value || '').trim() || null;
          const yearRaw = Number(document.getElementById('serviceShellAddVehicleYear')?.value || 0);
          const engine = String(document.getElementById('serviceShellAddVehicleEngine')?.value || '').trim() || null;
          const stk = String(document.getElementById('serviceShellAddVehicleStk')?.value || '').trim();
          const notes = String(document.getElementById('serviceShellAddVehicleNotes')?.value || '').trim() || null;
          const duplicateState = document.getElementById('serviceShellAddVehicleDuplicateState');
          if (!customerIdValue || !nickname || !plate || !stk) {
            throw new Error('Vyberte klienta a vyplňte název, SPZ a platnost STK.');
          }
          const lookupQuery = vin || plate;
          if (lookupQuery) {
            try {
              const lookup = await window.apiCall('/api/v1/services/workspace/vehicle-lookup', 'POST', { query: lookupQuery });
              const candidates = Array.isArray(lookup?.candidates) ? lookup.candidates : [];
              if (candidates.length) {
                if (duplicateState) {
                  duplicateState.innerHTML = 'Vozidlo už v databázi existuje. Použijte existující záznam nebo požádejte o přístup, nové vozidlo se nevytvoří.';
                }
                throw new Error('Vozidlo už v databázi existuje. Nový záznam nebyl vytvořen.');
              }
            } catch (error) {
              if (String(error?.message || '').includes('Nový záznam nebyl vytvořen')) {
                throw error;
              }
              console.warn('[SERVICE_SHELL] vehicle lookup before create failed:', error);
            }
          }
          const response = await window.apiCall(`/api/v1/services/workspace/customers/${customerIdValue}/vehicles`, 'POST', {
            nickname,
            plate,
            vin: vin || null,
            brand,
            model,
            year: Number.isFinite(yearRaw) && yearRaw > 0 ? yearRaw : null,
            engine,
            notes,
            stk_valid_until: stk,
            tyres_info: null,
          });
          return {
            close: true,
            refreshParent: true,
            message: response?.message || 'Vozidlo bylo přidáno.',
          };
        },
      },
      renderContent: () => `
        <form class="service-dashboard-modal-form" onsubmit="event.preventDefault(); window.serviceShell.submitAddVehicleModal();">
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellAddVehicleCustomer">Zákazník</label>
              <select id="serviceShellAddVehicleCustomer">
                ${customers.map((item) => `<option value="${Number(item.customer_id)}" ${Number(item.customer_id) === preferredCustomerId ? 'selected' : ''}>${escape(item.name || item.email || `Zákazník #${Number(item.customer_id)}`)}</option>`).join('')}
              </select>
            </div>
            <div class="form-group">
              <label for="serviceShellAddVehicleNickname">Název vozidla</label>
              <input type="text" id="serviceShellAddVehicleNickname" placeholder="Např. Octavia RS">
            </div>
          </div>
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellAddVehiclePlate">SPZ</label>
              <input type="text" id="serviceShellAddVehiclePlate" value="${escape(defaults?.plate || '')}">
            </div>
            <div class="form-group">
              <label for="serviceShellAddVehicleVin">VIN</label>
              <input type="text" id="serviceShellAddVehicleVin" value="${escape(defaults?.vin || '')}">
            </div>
          </div>
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellAddVehicleBrand">Značka</label>
              <input type="text" id="serviceShellAddVehicleBrand">
            </div>
            <div class="form-group">
              <label for="serviceShellAddVehicleModel">Model</label>
              <input type="text" id="serviceShellAddVehicleModel">
            </div>
          </div>
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellAddVehicleYear">Rok</label>
              <input type="number" id="serviceShellAddVehicleYear" min="1900" max="2100">
            </div>
            <div class="form-group">
              <label for="serviceShellAddVehicleStk">Platnost STK</label>
              <input type="date" id="serviceShellAddVehicleStk">
            </div>
          </div>
          <div class="form-group">
            <label for="serviceShellAddVehicleEngine">Motor</label>
            <input type="text" id="serviceShellAddVehicleEngine">
          </div>
          <div class="form-group">
            <label for="serviceShellAddVehicleNotes">Poznámka</label>
            <textarea id="serviceShellAddVehicleNotes" rows="3"></textarea>
          </div>
          <div id="serviceShellAddVehicleDuplicateState" class="service-shell-empty"></div>
        </form>
      `,
      renderFooter: (modal) => `
        <div class="service-shell-modal-footer">
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zrušit</button>
          <button type="button" class="btn btn-primary" onclick="window.serviceShell.submitAddVehicleModal()">${modal.saving ? 'Ukládám…' : 'Uložit vozidlo'}</button>
        </div>
      `,
    });
  }

  async function submitAddVehicleModal() {
    if (isModalOpen('vehicle-create')) {
      return runModalAction('save');
    }
  }

  function parseJsonList(value) {
    if (!value) return [];
    try {
      const parsed = typeof value === 'string' ? JSON.parse(value) : value;
      return Array.isArray(parsed) ? parsed : [];
    } catch (error) {
      return [];
    }
  }

  function serviceRecordCategoryForShell(record) {
    if (typeof window.getServiceRecordCategoryDisplay === 'function') {
      return window.getServiceRecordCategoryDisplay(record);
    }
    return { icon: '📋', label: String(record?.category || 'Jiné') };
  }

  function serviceRecordCards(records, vehicleId) {
    const items = Array.isArray(records) ? records : [];
    if (!items.length) {
      return '<div class="service-shell-empty">Pro toto vozidlo zatím nejsou servisní záznamy.</div>';
    }
    const sorted = items.slice().sort((a, b) => {
      const ta = new Date(a?.performed_at || 0).getTime();
      const tb = new Date(b?.performed_at || 0).getTime();
      if (ta !== tb) return tb - ta;
      return Number(b?.id || 0) - Number(a?.id || 0);
    });
    const vid = Number(vehicleId || 0);
    const rows = sorted.map((record) => {
      const display = serviceRecordCategoryForShell(record);
      const dateLabel = record?.performed_at ? formatDate(record.performed_at) : '—';
      const hasMileage = record?.mileage != null && record?.mileage !== '';
      const mileageNumber = Number(record.mileage);
      const mileageLabel = (hasMileage && Number.isFinite(mileageNumber))
        ? `${mileageNumber.toLocaleString('cs-CZ')} km`
        : '—';
      const desc = escape(String(record?.description || 'Bez popisu').replace(/\s+/g, ' ').trim());
      const rid = Number(record?.id || 0);
      const ai = record?.created_by_ai === true;
      const regId = `sh-reg-s-${vid}-${rid}`;
      const btnId = `sh-btn-s-${vid}-${rid}`;
      return `
      <article class="service-history-item" data-vehicle-id="${vid}" data-record-id="${rid}">
        <div class="service-history-item__summary">
          <div class="service-history-item__left">
            <div class="service-history-item__date">${escape(dateLabel)}</div>
            <div class="service-history-item__km">${escape(mileageLabel)}</div>
          </div>
          <div class="service-history-item__main">
            <div class="service-history-item__type-row">
              ${ai ? '<span class="service-history-item__ai" title="Vytvořeno AI" aria-label="Vytvořeno AI asistentem">🤖</span>' : ''}
              <span class="service-history-item__type">${display.icon} ${escape(display.label)}</span>
            </div>
            <div class="service-history-item__desc">${desc}</div>
          </div>
          <div class="service-history-item__trailing">
            <button type="button" class="service-history-item__expand" id="${btnId}" aria-expanded="false" aria-controls="${regId}"
              onclick="onServiceHistoryExpandClick(event, ${vid}, ${rid})" title="Rozbalit detail"
              aria-label="Rozbalit detail záznamu">
              <span class="service-history-item__chev" aria-hidden="true"></span>
            </button>
          </div>
        </div>
        <div class="service-history-item__detail" id="${regId}" role="region" aria-hidden="true" aria-labelledby="${btnId}">
          <div class="service-history-item__detail-inner"></div>
        </div>
      </article>
      `;
    }).join('');
    return `<div class="service-history-list service-history-list--service-shell" data-vehicle-id="${vid}" data-sh-actions="serviceShell">${rows}</div>`;
  }

  function quoteStatusLabel(status) {
    const normalized = String(status || 'draft').toLowerCase();
    if (normalized === 'sent') return 'Odesláno';
    if (normalized === 'approved') return 'Schváleno';
    if (normalized === 'rejected') return 'Zamítnuto';
    return 'Koncept';
  }

  function getQuoteListPrefs() {
    return state.quoteListPrefs || { status: 'all', sort: 'created_at', order: 'desc' };
  }

  function setVehicleQuoteListPrefs(partial = {}) {
    state.quoteListPrefs = {
      ...getQuoteListPrefs(),
      ...(partial && typeof partial === 'object' ? partial : {}),
    };
    if (
      state.modal?.open
      && state.modal.entityType === 'vehicle'
      && String(state.modal.key || '').startsWith('vehicle-detail-')
    ) {
      try {
        renderModal();
      } catch (err) {
        console.error('[SERVICE_SHELL] quote list prefs renderModal failed:', err);
      }
    }
  }

  function formatQuotePriceCs(value) {
    try {
      if (value == null || value === '') return 'Bez ceny';
      const n = Number(value);
      if (!Number.isFinite(n)) return 'Bez ceny';
      return `${n.toLocaleString('cs-CZ')} Kč`;
    } catch (err) {
      console.warn('[SERVICE_SHELL] formatQuotePriceCs:', err);
      return 'Bez ceny';
    }
  }

  function quoteStatusSortRank(status) {
    const normalized = String(status || 'draft').toLowerCase();
    if (normalized === 'draft') return 0;
    if (normalized === 'sent') return 1;
    if (normalized === 'approved') return 2;
    if (normalized === 'rejected') return 3;
    return 9;
  }

  function quoteBadgeClass(status) {
    const normalized = String(status || 'draft').toLowerCase();
    if (normalized === 'approved') return 'completed';
    if (normalized === 'rejected') return 'issue';
    if (normalized === 'sent') return 'in_progress';
    return 'awaiting';
  }

  function filterSortVehicleQuotes(items, prefs) {
    const safePrefs = prefs && typeof prefs === 'object' ? prefs : getQuoteListPrefs();
    const raw = Array.isArray(items) ? items.slice() : [];
    const statusKey = String(safePrefs.status || 'all').toLowerCase();
    const filtered = statusKey === 'all'
      ? raw
      : raw.filter((quote) => String(quote?.status || '').toLowerCase() === statusKey);
    const sortKey = String(safePrefs.sort || 'created_at').toLowerCase();
    const orderKey = String(safePrefs.order || 'desc').toLowerCase();
    const direction = orderKey === 'asc' ? 1 : -1;
    filtered.sort((left, right) => {
      if (sortKey === 'total_price') {
        const pl = Number(left?.total_price ?? 0);
        const pr = Number(right?.total_price ?? 0);
        if (pl !== pr) return (pl - pr) * direction;
      } else if (sortKey === 'status') {
        const rl = quoteStatusSortRank(left?.status);
        const rr = quoteStatusSortRank(right?.status);
        if (rl !== rr) return (rl - rr) * direction;
      } else {
        const tl = new Date(left?.created_at || 0).getTime();
        const tr = new Date(right?.created_at || 0).getTime();
        if (tl !== tr) return (tl - tr) * direction;
      }
      const idl = Number(left?.quote_id || left?.id || 0);
      const idr = Number(right?.quote_id || right?.id || 0);
      return (idl - idr) * direction;
    });
    return filtered;
  }

  function vehicleQuotesToolbar() {
    const prefs = getQuoteListPrefs();
    const sel = (value, current) => (String(value) === String(current) ? ' selected' : '');
    return `
      <div class="service-shell-quote-list-toolbar" role="group" aria-label="Filtrování a řazení nabídek">
        <div class="service-shell-quote-list-toolbar-row">
          <label class="service-shell-quote-filter-label" for="serviceShellQuoteFilterStatus">Stav</label>
          <select id="serviceShellQuoteFilterStatus" class="service-shell-quote-filter" onchange="window.serviceShell.setVehicleQuoteListPrefs({ status: this.value })">
            <option value="all"${sel('all', prefs.status)}>Všechny stavy</option>
            <option value="draft"${sel('draft', prefs.status)}>Koncept</option>
            <option value="sent"${sel('sent', prefs.status)}>Odesláno</option>
            <option value="approved"${sel('approved', prefs.status)}>Schváleno</option>
            <option value="rejected"${sel('rejected', prefs.status)}>Zamítnuto</option>
          </select>
        </div>
        <div class="service-shell-quote-list-toolbar-row">
          <label class="service-shell-quote-filter-label" for="serviceShellQuoteSortField">Řazení pole</label>
          <select id="serviceShellQuoteSortField" class="service-shell-quote-filter" onchange="window.serviceShell.setVehicleQuoteListPrefs({ sort: this.value })">
            <option value="created_at"${sel('created_at', prefs.sort)}>Data vytvoření</option>
            <option value="total_price"${sel('total_price', prefs.sort)}>Ceny</option>
            <option value="status"${sel('status', prefs.sort)}>Stavu</option>
          </select>
        </div>
        <div class="service-shell-quote-list-toolbar-row">
          <label class="service-shell-quote-filter-label" for="serviceShellQuoteSortOrder">Pořadí</label>
          <select id="serviceShellQuoteSortOrder" class="service-shell-quote-filter" onchange="window.serviceShell.setVehicleQuoteListPrefs({ order: this.value })">
            <option value="desc"${sel('desc', prefs.order)}>Nejnovější / vyšší první</option>
            <option value="asc"${sel('asc', prefs.order)}>Nejstarší / nižší první</option>
          </select>
        </div>
      </div>
    `;
  }

  function vehicleQuoteCardHtml(quote) {
    const qid = Number(quote?.quote_id || quote?.id || 0);
    const pub = String(quote?.public_quote_url || '');
    const badgeClass = quoteBadgeClass(quote?.status);
    const statusText = escape(quote?.status_label || quoteStatusLabel(quote?.status));
    const priceText = escape(formatQuotePriceCs(quote?.total_price));
    const dateText = escape(quote?.created_at ? formatDateTime(quote.created_at) : 'Bez data');
    return `
      <article class="service-shell-quote-card" data-quote-id="${qid}" data-quote-status="${escape(String(quote?.status || ''))}">
        <div class="service-shell-quote-card-top">
          <div class="service-shell-quote-card-heading">
            <strong class="service-shell-quote-card-id">Nabídka #${escape(String(qid))}</strong>
            <span class="service-shell-badge service-shell-badge--quote ${badgeClass}">${statusText}</span>
          </div>
          <div class="service-shell-quote-card-stats">
            <div class="service-shell-quote-stat">
              <span class="service-shell-quote-stat-label">Vytvořeno</span>
              <span class="service-shell-quote-stat-value">${dateText}</span>
            </div>
            <div class="service-shell-quote-stat">
              <span class="service-shell-quote-stat-label">Cena</span>
              <span class="service-shell-quote-stat-value">${priceText}</span>
            </div>
          </div>
        </div>
        <div class="service-shell-quote-card-links">
          ${quote?.service_record_id ? `<span>Záznam #${escape(String(quote.service_record_id))}</span>` : '<span>Bez záznamu</span>'}
          <span class="service-shell-quote-card-links-sep">·</span>
          ${quote?.work_order_id ? `<span>Zakázka #${escape(String(quote.work_order_id))}</span>` : '<span>Bez zakázky</span>'}
        </div>
        ${quote?.approved_at ? `<p class="service-shell-list-note">Schváleno: ${escape(formatDateTime(quote.approved_at))}</p>` : ''}
        ${quote?.rejected_at ? `<p class="service-shell-list-note">Odmítnuto: ${escape(formatDateTime(quote.rejected_at))}</p>` : ''}
        ${quote?.consistency_note ? `<p class="service-shell-list-note">${escape(quote.consistency_note)}</p>` : ''}
        <div class="service-shell-quote-actions">
          <button type="button" class="btn btn-secondary service-shell-quote-action" onclick="window.serviceShell.openQuoteModal(${qid})">Otevřít</button>
          <button type="button" class="btn btn-secondary service-shell-quote-action" onclick="window.serviceShell.shareQuotePdf(${qid})">PDF</button>
          <button type="button" class="btn btn-secondary service-shell-quote-action" onclick="window.serviceShell.openQuotePublicLink(${qid})">Veřejný odkaz</button>
          <button type="button" class="btn btn-secondary service-shell-quote-action" onclick="window.serviceShell.copyQuotePublicLinkByUrl(${JSON.stringify(pub)})">Kopírovat odkaz</button>
        </div>
        <details class="service-shell-quote-debug">
          <summary>Provozní kontrola (servis)</summary>
          <dl class="service-shell-quote-debug-dl">
            <div><dt>quote_id</dt><dd><code>${escape(String(qid))}</code></dd></div>
            <div><dt>quote_status</dt><dd><code>${escape(String(quote?.status || '-'))}</code></dd></div>
            <div><dt>public_quote_url</dt><dd><code class="service-shell-quote-debug-url">${escape(pub || '-')}</code></dd></div>
            <div><dt>work_order_id</dt><dd><code>${escape(quote?.work_order_id != null ? String(quote.work_order_id) : '-')}</code></dd></div>
          </dl>
        </details>
      </article>
    `;
  }

  function vehicleQuotesSection(detail) {
    try {
      const items = Array.isArray(detail?.service_quotes) ? detail.service_quotes : [];
      if (!items.length) {
        return `
        <div class="service-shell-empty">
          Pro toto vozidlo zatím nejsou cenové nabídky.
          <div class="service-shell-modal-actions">
            <button type="button" class="btn btn-primary" onclick="window.serviceShell.openFirstRecordForQuote()">Vytvořit nabídku</button>
          </div>
        </div>
      `;
      }
      const prefs = getQuoteListPrefs();
      const filtered = filterSortVehicleQuotes(items, prefs);
      const meta = `<p class="service-shell-quote-list-count">Zobrazeno <strong>${filtered.length}</strong> z <strong>${items.length}</strong></p>`;
      const list = filtered.length
        ? filtered.map((quote) => {
          try {
            return vehicleQuoteCardHtml(quote);
          } catch (rowErr) {
            console.error('[SERVICE_SHELL] vehicleQuoteCardHtml failed:', rowErr, quote);
            return '<div class="service-shell-empty">Jednu nabídku se nepodařilo zobrazit (viz konzole).</div>';
          }
        }).join('')
        : '<div class="service-shell-empty">Žádná nabídka pro zvolený filtr. Upravte stav výše.</div>';
      return `
      ${vehicleQuotesToolbar()}
      ${meta}
      <div class="service-shell-quote-card-list">
        ${list}
      </div>
    `;
    } catch (err) {
      console.error('[SERVICE_SHELL] vehicleQuotesSection failed:', err);
      return '<div class="service-shell-empty">Sekci nabídek se nepodařilo vykreslit. Zkuste znovu načíst detail vozidla.</div>';
    }
  }

  function vehicleInvoicesSection(vehicleId) {
    const id = Number(vehicleId || 0);
    const invoices = (Array.isArray(state.invoices) ? state.invoices : []).filter((item) => Number(item?.vehicle_id || 0) === id);
    if (!invoices.length) {
      return '<div class="service-shell-empty">K tomuto vozidlu zatím nejsou servisní faktury.</div>';
    }
    return `
      <div class="service-shell-quote-card-list">
        ${invoices.map((inv) => `
          <article class="service-shell-card">
            <div class="service-shell-card-head">
              <div>
                <h3 class="service-shell-card-title">${escape(inv?.invoice_number || 'Koncept')}</h3>
                <p class="service-shell-subtitle">${escape(inv?.status_label || inv?.status || 'Koncept')}</p>
              </div>
              <span class="service-shell-badge ${invoiceBadgeClass(inv?.status)}">${escape(inv?.status_label || inv?.status || 'Koncept')}</span>
            </div>
            <div class="service-shell-card-grid">
              <div><span>Celkem</span><strong>${escape(invoiceMoney(inv?.total || 0, inv?.currency || 'CZK'))}</strong></div>
              <div><span>Splatnost</span><strong>${escape(inv?.due_at ? formatDateTime(inv.due_at) : '-')}</strong></div>
            </div>
            <div class="service-shell-card-actions">
              <button type="button" class="btn btn-secondary" onclick="window.serviceShell.openServiceInvoiceDetailModal(${Number(inv?.id || 0)})">Otevřít fakturu</button>
            </div>
          </article>
        `).join('')}
      </div>
    `;
  }

  async function fileToBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = String(reader.result || '');
        const base64 = result.includes(',') ? result.split(',').pop() : result;
        resolve(base64 || '');
      };
      reader.onerror = () => reject(reader.error || new Error('Soubor se nepodařilo načíst.'));
      reader.readAsDataURL(file);
    });
  }

  function appendWorkItemDraft() {
    const edit = state.modal?.data?.recordEditState;
    if (edit && !edit.editable) return;
    const target = document.getElementById('serviceShellRecordDescription');
    if (!target) return;
    const prefix = target.value && !/\n$/.test(target.value) ? '\n' : '';
    target.value = `${target.value || ''}${prefix}- `;
    target.focus();
  }

  async function handleServiceRecordPhotoSelection(input) {
    const edit = state.modal?.data?.recordEditState;
    if (edit && !edit.editable) return;
    const files = Array.from(input?.files || []);
    const context = state.modal?.context || {};
    const vehicleId = Number(context.vehicleId || 0);
    if (!vehicleId || !files.length) return;
    const uploaded = [];
    const uploadTimeoutMs = 180000;
    try {
      for (const file of files) {
        const fileContentBase64 = await fileToBase64(file);
        const payload = await window.apiCall(
          `/api/v1/vehicles/${vehicleId}/records/attachments/upload`,
          'POST',
          {
            file_name: file.name || 'photo.jpg',
            file_mime_type: file.type || 'image/jpeg',
            file_content_base64: fileContentBase64,
          },
          uploadTimeoutMs,
        );
        uploaded.push({
          kind: 'user_photo',
          file_name: payload?.file_name || file.name || 'photo.jpg',
          mime_type: payload?.mime_type || file.type || 'image/jpeg',
          file_size: payload?.file_size || file.size || null,
          storage_key: payload?.storage_key || null,
          download_url: payload?.download_url || null,
        });
      }
      context.photoAttachments = [...(Array.isArray(context.photoAttachments) ? context.photoAttachments : []), ...uploaded];
      state.modal.context = context;
      renderModal();
    } catch (err) {
      const msg = err && err.message ? String(err.message) : 'Nahrání fotky se nepodařilo.';
      if (typeof window.showAlert === 'function') {
        window.showAlert(msg, 'error');
      } else {
        console.error('[SERVICE_SHELL] photo upload failed:', err);
      }
    } finally {
      if (input) input.value = '';
    }
  }

  function triggerServiceRecordPhotoPicker() {
    const edit = state.modal?.data?.recordEditState;
    if (edit && !edit.editable) return;
    const input = document.getElementById('serviceShellRecordPhotos');
    if (input) input.click();
  }

  function openServiceRecordModal(vehicleId, recordId = 0) {
    const resolvedVehicleId = Number(vehicleId || state.activeVehicle?.vehicleId || 0);
    const resolvedRecordId = Number(recordId || 0);
    if (!resolvedVehicleId) return;
    openModal({
      key: resolvedRecordId ? `service-record-${resolvedRecordId}` : `service-record-create-${resolvedVehicleId}`,
      entityType: 'service-record',
      kicker: resolvedRecordId ? `Záznam #${resolvedRecordId}` : `Vozidlo #${resolvedVehicleId}`,
      title: resolvedRecordId ? 'Servisní záznam' : 'Nový servisní záznam',
      description: 'Mobilní full-screen workflow pro bezpečný zápis servisní historie.',
      size: 'wide',
      bodyClass: 'service-shell-modal-body--record',
      context: {
        vehicleId: resolvedVehicleId,
        recordId: resolvedRecordId || null,
        photoAttachments: [],
      },
      actions: {
        save: async () => {
          await submitServiceRecordModal('save');
          return { close: false };
        },
        finish: async () => {
          await submitServiceRecordModal('finish');
          return { close: false };
        },
      },
      load: async () => {
        const [vehicleDetail, recordDetail] = await Promise.all([
          window.apiCall(`/api/v1/services/workspace/vehicles/${resolvedVehicleId}/detail`, 'GET'),
          resolvedRecordId ? window.apiCall(`/api/v1/vehicles/${resolvedVehicleId}/records/${resolvedRecordId}`, 'GET') : Promise.resolve(null),
        ]);
        setActiveVehicle(vehicleDetail);
        render();
        const attachments = parseJsonList(recordDetail?.attachments);
        const recordEditState = recordDetail ? computeServiceRecordShellEditState(recordDetail) : { editable: true, reason: null };
        state.modal.context = {
          ...(state.modal.context || {}),
          vehicleId: resolvedVehicleId,
          recordId: resolvedRecordId || null,
          photoAttachments: attachments,
          recordEditState,
        };
        return {
          vehicle: vehicleDetail,
          record: recordDetail,
          recordEditState,
        };
      },
      renderContent: (modal) => {
        const detail = modal.data?.record || {};
        const vehicle = modal.data?.vehicle || {};
        const edit = modal.data?.recordEditState || { editable: true, reason: null };
        const ro = !edit.editable;
        const attachments = Array.isArray(modal.context?.photoAttachments) ? modal.context.photoAttachments : [];
        return `
          <section class="service-shell-mobile-form-top">
            <div class="service-shell-mobile-kicker">Vozidlo</div>
            <strong>${escape(vehicle?.nickname || [vehicle?.brand, vehicle?.model].filter(Boolean).join(' ') || vehicle?.plate || 'Vozidlo')}</strong>
            <span class="service-shell-muted">${escape(vehicle?.vin || vehicle?.vin_masked || '-')} · ${escape(vehicle?.plate || vehicle?.plate_masked || '-')}</span>
          </section>
          ${ro ? `<div class="service-shell-inline-error" style="margin-bottom:12px;">${escape(edit.reason || 'Jen pro čtení.')}</div>` : ''}
          <form class="service-dashboard-modal-form service-shell-record-form" onsubmit="event.preventDefault(); window.serviceShell.submitServiceRecordModal('save');">
            <div class="form-group">
              <label for="serviceShellRecordCategory">Typ úkonu</label>
              <select id="serviceShellRecordCategory" ${ro ? 'disabled' : ''}>
                <option value="OPRAVA" ${String(detail?.category || '').toUpperCase() === 'OPRAVA' ? 'selected' : ''}>Oprava</option>
                <option value="OLEJ" ${String(detail?.category || '').toUpperCase() === 'OLEJ' ? 'selected' : ''}>Výměna oleje</option>
                <option value="PNEU" ${String(detail?.category || '').toUpperCase() === 'PNEU' ? 'selected' : ''}>Pneuservis</option>
                <option value="DIAGNOSTIKA" ${String(detail?.category || '').toUpperCase() === 'DIAGNOSTIKA' ? 'selected' : ''}>Diagnostika</option>
                <option value="STK" ${String(detail?.category || '').toUpperCase() === 'STK' ? 'selected' : ''}>STK / ME</option>
                <option value="JINE" ${!detail?.category || String(detail?.category || '').toUpperCase() === 'JINE' ? 'selected' : ''}>Ostatní</option>
              </select>
            </div>
            <div class="form-group">
              <label for="serviceShellRecordStatus">Stav záznamu</label>
              <select id="serviceShellRecordStatus" ${ro ? 'disabled' : ''}>
                <option value="draft" ${String(detail?.record_status || 'draft').toLowerCase() === 'draft' ? 'selected' : ''}>Koncept</option>
                <option value="submitted" ${String(detail?.record_status || '').toLowerCase() === 'submitted' ? 'selected' : ''}>Odesláno</option>
                <option value="approved" ${String(detail?.record_status || '').toLowerCase() === 'approved' ? 'selected' : ''}>Schváleno</option>
                <option value="locked" ${String(detail?.record_status || '').toLowerCase() === 'locked' ? 'selected' : ''}>Uzamčeno</option>
              </select>
            </div>
            <div class="form-group">
              <label for="serviceShellRecordPerformedAt">Datum a čas</label>
              <input type="datetime-local" id="serviceShellRecordPerformedAt" ${ro ? 'readonly' : ''} value="${escape(toDateTimeInputValue(detail?.performed_at || new Date().toISOString()))}">
            </div>
            <div class="form-group">
              <label for="serviceShellRecordMileage">Nájezd</label>
              <input type="number" id="serviceShellRecordMileage" inputmode="numeric" min="0" ${ro ? 'readonly' : ''} value="${escape(detail?.mileage != null ? String(detail.mileage) : '')}">
            </div>
            <div class="form-group">
              <label for="serviceShellRecordDescription">Popis</label>
              <textarea id="serviceShellRecordDescription" rows="5" ${ro ? 'readonly' : ''}>${escape(detail?.description || '')}</textarea>
            </div>
            <div class="form-group">
              <label for="serviceShellRecordNotesCustomer">Poznámka pro zákazníka</label>
              <textarea id="serviceShellRecordNotesCustomer" rows="4" ${ro ? 'readonly' : ''}>${escape(detail?.notes_customer_visible || '')}</textarea>
            </div>
            <div class="form-group">
              <label for="serviceShellRecordRecommendedText">Doporučený další servis</label>
              <textarea id="serviceShellRecordRecommendedText" rows="3" ${ro ? 'readonly' : ''}>${escape(detail?.recommended_next_service_text || '')}</textarea>
            </div>
            <div class="form-group">
              <label for="serviceShellRecordRecommendedDate">Doporučený termín</label>
              <input type="date" id="serviceShellRecordRecommendedDate" ${ro ? 'readonly' : ''} value="${escape(String(detail?.recommended_next_service_date || '').slice(0, 10))}">
            </div>
            <div class="form-group">
              <label for="serviceShellRecordPrice">Cena</label>
              <input type="number" id="serviceShellRecordPrice" inputmode="decimal" min="0" step="0.01" ${ro ? 'readonly' : ''} value="${escape(detail?.total_price != null ? String(detail.total_price) : detail?.price != null ? String(detail.price) : '')}">
            </div>
            <div class="form-group">
              <label for="serviceShellRecordInternalNote">Interní poznámka</label>
              <textarea id="serviceShellRecordInternalNote" rows="3" ${ro ? 'readonly' : ''}>${escape(detail?.note || '')}</textarea>
            </div>
            <input type="file" id="serviceShellRecordPhotos" accept="image/*" capture="environment" multiple style="display:none" ${ro ? 'disabled' : ''} onchange="window.serviceShell.handleServiceRecordPhotoSelection(this)">
            <section class="service-shell-side-card">
              <h3>Fotodokumentace</h3>
              <div class="service-shell-list">
                ${attachments.length ? attachments.map((item) => `
                  <div class="service-shell-list-row">
                    <div>
                      <p class="service-shell-list-title">${escape(item?.file_name || 'Fotografie')}</p>
                      <p class="service-shell-list-note">${escape(item?.mime_type || 'image')}</p>
                    </div>
                    <span class="service-shell-list-value">${escape(item?.file_size ? `${Math.round(Number(item.file_size) / 1024)} kB` : 'Uloženo')}</span>
                  </div>
                `).join('') : '<div class="service-shell-empty">Zatím bez nahraných fotek.</div>'}
              </div>
            </section>
          </form>
        `;
      },
      renderFooter: (modal) => {
        const edit = modal?.data?.recordEditState || { editable: true, reason: null };
        const canEdit = edit.editable;
        const canCreateQuote = Number(modal?.context?.recordId || 0) > 0;
        return `
        <div class="service-shell-modal-footer ${isMobileViewport() ? 'service-shell-mobile-action-bar' : ''}">
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zpět</button>
          ${canCreateQuote ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.createQuoteFromRecord(${Number(modal.context.recordId)})">Vytvořit nabídku</button>` : ''}
          ${canEdit ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.appendWorkItemDraft()">Přidat položku</button>` : ''}
          ${canEdit ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.triggerServiceRecordPhotoPicker()">Přidat fotku</button>` : ''}
          ${canEdit ? `<button type="button" class="btn btn-primary" onclick="window.serviceShell.runModalAction('save')">${modal.saving ? 'Ukládám…' : 'Uložit'}</button>` : ''}
          ${canEdit ? `<button type="button" class="btn btn-primary" onclick="window.serviceShell.runModalAction('finish')">${modal.saving ? 'Dokončuji…' : 'Dokončit'}</button>` : ''}
        </div>
      `;
      },
    });
  }

  async function submitServiceRecordModal(mode = 'save') {
    const edit = state.modal?.data?.recordEditState;
    if (edit && !edit.editable) {
      throw new Error(edit.reason || 'Záznam není možné upravovat.');
    }
    const context = state.modal?.context || {};
    const vehicleId = Number(context.vehicleId || 0);
    const recordId = Number(context.recordId || 0);
    if (!vehicleId) return;
    const payload = {
      category: String(document.getElementById('serviceShellRecordCategory')?.value || 'JINE').trim(),
      record_status: mode === 'finish'
        ? 'approved'
        : String(document.getElementById('serviceShellRecordStatus')?.value || 'draft').trim(),
      performed_at: fromDateTimeInputValue(document.getElementById('serviceShellRecordPerformedAt')?.value),
      mileage: Number(document.getElementById('serviceShellRecordMileage')?.value || 0) || 0,
      description: String(document.getElementById('serviceShellRecordDescription')?.value || '').trim(),
      recommended_next_service_text: String(document.getElementById('serviceShellRecordRecommendedText')?.value || '').trim() || null,
      recommended_next_service_date: String(document.getElementById('serviceShellRecordRecommendedDate')?.value || '').trim() || null,
      notes_customer_visible: String(document.getElementById('serviceShellRecordNotesCustomer')?.value || '').trim() || null,
      note: String(document.getElementById('serviceShellRecordInternalNote')?.value || '').trim() || null,
      total_price: Number(document.getElementById('serviceShellRecordPrice')?.value || 0) || 0,
      price: Number(document.getElementById('serviceShellRecordPrice')?.value || 0) || 0,
      attachments: JSON.stringify(Array.isArray(context.photoAttachments) ? context.photoAttachments : []),
    };
    if (!payload.description) {
      throw new Error('Vyplňte popis servisního úkonu.');
    }
    if (recordId > 0) {
      await window.apiCall(`/api/v1/vehicles/${vehicleId}/records/${recordId}`, 'PUT', payload);
    } else {
      await window.apiCall(`/api/v1/vehicles/${vehicleId}/records`, 'POST', payload);
    }
    state.activeSection = 'vehicles';
    await load(true, true);
    closeModal();
    if (typeof window.showAlert === 'function') {
      window.showAlert(mode === 'finish' ? 'Servisní záznam byl dokončen.' : 'Servisní záznam byl uložen.', 'success');
    }
  }

  function quoteItemsFromDom() {
    const rows = Array.from(document.querySelectorAll('[data-quote-item-row]'));
    return rows.map((row) => {
      const name = String(row.querySelector('[data-quote-item-name]')?.value || '').trim() || 'Položka';
      const quantity = Number(row.querySelector('[data-quote-item-qty]')?.value || 0) || 0;
      const unitPrice = Number(row.querySelector('[data-quote-item-price]')?.value || 0) || 0;
      return {
        name,
        quantity,
        unit_price: unitPrice,
        total_price: Number((quantity * unitPrice).toFixed(2)),
      };
    });
  }

  function appendQuoteItemRow() {
    const container = document.getElementById('serviceShellQuoteItems');
    if (!container) return;
    const row = document.createElement('div');
    row.className = 'service-shell-quote-item-row';
    row.setAttribute('data-quote-item-row', '1');
    row.innerHTML = `
      <input data-quote-item-name type="text" placeholder="Položka">
      <input data-quote-item-qty type="number" inputmode="decimal" min="0" step="0.1" value="1">
      <input data-quote-item-price type="number" inputmode="decimal" min="0" step="0.01" value="0">
    `;
    container.appendChild(row);
  }

  function invoiceLinesFromDom() {
    const rows = Array.from(document.querySelectorAll('[data-invoice-line-row]'));
    return rows
      .map((row) => {
        const description = String(row.querySelector('[data-invoice-line-description]')?.value || '').trim();
        const quantity = Number(row.querySelector('[data-invoice-line-quantity]')?.value || 0) || 0;
        const unit = String(row.querySelector('[data-invoice-line-unit]')?.value || 'ks').trim() || 'ks';
        const unitPrice = Number(row.querySelector('[data-invoice-line-unit-price]')?.value || 0) || 0;
        const taxRate = Number(row.querySelector('[data-invoice-line-tax-rate]')?.value || 0) || 0;
        return { description, quantity, unit, unit_price: unitPrice, tax_rate: taxRate };
      })
      .filter((item) => item.description && item.quantity > 0);
  }

  function invoiceMoney(value, currency = 'CZK') {
    const numeric = Number(value || 0);
    try {
      return `${numeric.toLocaleString('cs-CZ', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${String(currency || 'CZK')}`;
    } catch (err) {
      return `${numeric.toFixed(2)} ${String(currency || 'CZK')}`;
    }
  }

  function invoiceLineGross(line) {
    const net = Number(line?.quantity || 0) * Number(line?.unit_price || 0);
    return Number((net + (net * Number(line?.tax_rate || 0) / 100)).toFixed(2));
  }

  function invoiceTotals(lines = []) {
    return (Array.isArray(lines) ? lines : []).reduce((acc, line) => {
      const net = Number(line?.quantity || 0) * Number(line?.unit_price || 0);
      const tax = net * Number(line?.tax_rate || 0) / 100;
      acc.net += net;
      acc.tax += tax;
      acc.gross += net + tax;
      return acc;
    }, { net: 0, tax: 0, gross: 0 });
  }

  function invoiceStatusKey(status) {
    return String(status || '').trim().toLowerCase();
  }

  function invoiceBadgeClass(status) {
    const key = invoiceStatusKey(status);
    if (key === 'cancelled') return 'issue';
    if (key === 'issued') return 'completed';
    return 'awaiting';
  }

  function setInvoiceStatusFilter(value) {
    state.invoiceStatusFilter = String(value || 'all');
    render();
  }

  function setInvoiceSearchTerm(value) {
    state.invoiceSearchTerm = String(value || '');
    render();
  }

  function filteredInvoices() {
    const query = String(state.invoiceSearchTerm || '').trim().toLowerCase();
    const filter = String(state.invoiceStatusFilter || 'all').toLowerCase();
    return (Array.isArray(state.invoices) ? [...state.invoices] : []).filter((inv) => {
      const status = invoiceStatusKey(inv?.status);
      if (filter === 'draft' && status !== 'draft') return false;
      if (filter === 'issued' && status !== 'issued') return false;
      if (filter === 'cancelled' && status !== 'cancelled') return false;
      if (!query) return true;
      const haystack = [
        inv?.invoice_number,
        inv?.customer_label,
        inv?.vehicle_label,
        inv?.total,
        inv?.currency,
        inv?.extra?.variable_symbol,
        inv?.extra?.order_number,
      ].join(' ').toLowerCase();
      return haystack.includes(query);
    });
  }

  function invoiceExtraFromDom(prefix) {
    const value = (suffix) => String(document.getElementById(`${prefix}${suffix}`)?.value || '').trim();
    const checked = (suffix) => Boolean(document.getElementById(`${prefix}${suffix}`)?.checked);
    const tagsRaw = value('Tags');
    return {
      invoice_type: value('Type') || '1',
      payment_method: value('Payment') || 'prevod',
      issue_date: value('IssueDate'),
      delivery_date: value('DeliveryDate'),
      variable_symbol: value('VariableSymbol'),
      constant_symbol: value('ConstantSymbol'),
      specific_symbol: value('SpecificSymbol'),
      order_number: value('OrderNumber'),
      issued_by: value('IssuedBy'),
      language: value('Language') || 'CS',
      style: value('Style') || 'standard',
      rounding: value('Rounding') || '0',
      qr: checked('Qr'),
      already_paid: value('AlreadyPaid'),
      customer_note: value('CustomerNote'),
      internal_note: value('InternalNote'),
      supplier_name: value('SupplierName'),
      supplier_ico: value('SupplierIco'),
      supplier_dic: value('SupplierDic'),
      supplier_street: value('SupplierStreet'),
      supplier_city: value('SupplierCity'),
      supplier_zip: value('SupplierZip'),
      supplier_state: value('SupplierState') || 'Česká republika',
      supplier_email: value('SupplierEmail'),
      supplier_phone: value('SupplierPhone'),
      supplier_bankaccount: value('SupplierBankAccount'),
      supplier_bank: value('SupplierBank'),
      supplier_iban: value('SupplierIban'),
      supplier_swift: value('SupplierSwift'),
      customer_name: value('CustomerName'),
      customer_ico: value('CustomerIco'),
      customer_dic: value('CustomerDic'),
      customer_street: value('CustomerStreet'),
      customer_city: value('CustomerCity'),
      customer_zip: value('CustomerZip'),
      customer_state: value('CustomerState') || 'Česká republika',
      customer_email: value('CustomerEmail'),
      tags: tagsRaw ? tagsRaw.split(',').map((item) => item.trim()).filter(Boolean) : [],
    };
  }

  function invoicePayloadFromDom(prefix, fallback = {}) {
    const customerId = Number(document.getElementById(`${prefix}Customer`)?.value || fallback?.customer_id || 0);
    const vehicleId = Number(document.getElementById(`${prefix}Vehicle`)?.value || 0) || null;
    return {
      customer_id: customerId,
      vehicle_id: vehicleId,
      currency: String(document.getElementById(`${prefix}Currency`)?.value || fallback?.currency || 'CZK').trim() || 'CZK',
      due_at: fromDateTimeInputValue(document.getElementById(`${prefix}DueAt`)?.value),
      notes: String(document.getElementById(`${prefix}Notes`)?.value || '').trim() || null,
      extra: invoiceExtraFromDom(prefix),
      lines: invoiceLinesFromDom(),
    };
  }

  function updateInvoiceDraftTotals(prefix = 'serviceShellCreateInvoice') {
    const lines = invoiceLinesFromDom();
    const currency = String(document.getElementById(`${prefix}Currency`)?.value || 'CZK').trim() || 'CZK';
    const totals = invoiceTotals(lines);
    const target = document.getElementById(`${prefix}Totals`);
    if (target) {
      target.innerHTML = `
        <div><span>Základ</span><strong>${escape(invoiceMoney(totals.net, currency))}</strong></div>
        <div><span>DPH</span><strong>${escape(invoiceMoney(totals.tax, currency))}</strong></div>
        <div><span>Celkem</span><strong>${escape(invoiceMoney(totals.gross, currency))}</strong></div>
      `;
    }
  }

  function removeInvoiceLineRow(button) {
    const row = button?.closest?.('[data-invoice-line-row]');
    if (row) row.remove();
    updateInvoiceDraftTotals();
    updateInvoiceDraftTotals('serviceShellInvoice');
  }

  function appendInvoiceLineRow(values = {}) {
    const container = document.getElementById('serviceShellInvoiceLines');
    if (!container) return;
    const prefix = document.getElementById('serviceShellInvoiceTotals') ? 'serviceShellInvoice' : 'serviceShellCreateInvoice';
    const row = document.createElement('div');
    row.className = 'service-shell-invoice-line-row';
    row.setAttribute('data-invoice-line-row', '1');
    row.innerHTML = `
      <label><span>Položka</span><input data-invoice-line-description type="text" placeholder="Např. Výměna oleje" value="${escape(values?.description || '')}" oninput="window.serviceShell.updateInvoiceDraftTotals('${prefix}')"></label>
      <label><span>Množství</span><input data-invoice-line-quantity type="number" inputmode="decimal" min="0.01" step="0.1" value="${escape(String(values?.quantity ?? 1))}" oninput="window.serviceShell.updateInvoiceDraftTotals('${prefix}')"></label>
      <label><span>Jed.</span><input data-invoice-line-unit type="text" placeholder="ks" value="${escape(values?.unit || 'ks')}"></label>
      <label><span>Cena bez DPH</span><input data-invoice-line-unit-price type="number" inputmode="decimal" min="0" step="0.01" value="${escape(String(values?.unit_price ?? 0))}" oninput="window.serviceShell.updateInvoiceDraftTotals('${prefix}')"></label>
      <label><span>DPH %</span><input data-invoice-line-tax-rate type="number" inputmode="decimal" min="0" max="100" step="0.1" value="${escape(String(values?.tax_rate ?? 21))}" oninput="window.serviceShell.updateInvoiceDraftTotals('${prefix}')"></label>
      <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.removeInvoiceLineRow(this)" aria-label="Odebrat položku">×</button>
    `;
    container.appendChild(row);
    updateInvoiceDraftTotals(prefix);
  }

  function invoiceEditorHtml({ prefix, invoice = {}, customers = [], lines = [], mode = 'create' } = {}) {
    const extra = invoice?.extra || {};
    const profile = currentProfile();
    const selectedCustomerId = Number(invoice?.customer_id || customers[0]?.customer_id || 0);
    const issueDate = String(extra.issue_date || invoice?.issued_at || new Date().toISOString()).slice(0, 10);
    const deliveryDate = String(extra.delivery_date || issueDate).slice(0, 10);
    const tags = Array.isArray(extra.tags) ? extra.tags.join(', ') : String(extra.tags || '');
    const supplierName = extra.supplier_name || profile?.name || window.currentUser?.name || '';
    const supplierEmail = extra.supplier_email || profile?.email || window.currentUser?.email || '';
    const profileStreet = [profile?.street, profile?.street_number].filter(Boolean).join(' ').trim();
    const supplierStreet = extra.supplier_street || profileStreet || '';
    const supplierCity = extra.supplier_city || profile?.city || '';
    const supplierZip = extra.supplier_zip || profile?.zip || '';
    const supplierPhone = extra.supplier_phone || profile?.phone || '';
    return `
      <form class="service-dashboard-modal-form service-shell-invoice-editor" onsubmit="event.preventDefault(); ${mode === 'create' ? 'window.serviceShell.submitCreateInvoiceModal()' : "window.serviceShell.runModalAction('save')"};">
        <section class="service-shell-invoice-panel service-shell-invoice-panel--accent">
          <div class="service-shell-card-head">
            <div>
              <h3 class="service-shell-card-title">Doklad</h3>
              <p class="service-shell-subtitle">Typ dokladu, platba, symboly a data — přenesou se do PDF i do přehledů.</p>
            </div>
            <span class="service-shell-badge ${invoiceBadgeClass(invoice?.status)}">${escape(invoice?.status_label || invoice?.status || 'Koncept')}</span>
          </div>
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="${prefix}Type">Typ dokladu</label>
              <select id="${prefix}Type">
                <option value="1" ${String(extra.invoice_type || '1') === '1' ? 'selected' : ''}>Faktura</option>
                <option value="2" ${String(extra.invoice_type || '') === '2' ? 'selected' : ''}>Zálohová faktura</option>
                <option value="3" ${String(extra.invoice_type || '') === '3' ? 'selected' : ''}>Dobropis</option>
                <option value="4" ${String(extra.invoice_type || '') === '4' ? 'selected' : ''}>Vrubopis</option>
                <option value="5" ${String(extra.invoice_type || '') === '5' ? 'selected' : ''}>Doklad k přijaté platbě</option>
              </select>
            </div>
            <div class="form-group">
              <label for="${prefix}Payment">Platba</label>
              <select id="${prefix}Payment">
                ${[
                  ['prevod', 'Převodem'],
                  ['hotovost', 'Hotově'],
                  ['poukazka', 'Poštovní poukázka'],
                  ['dobirka', 'Dobírka'],
                  ['registracna_pokladna', 'Pokladna'],
                  ['jina', 'Jiná'],
                  ['eprovider', 'Platební brána'],
                ].map(([value, label]) => `<option value="${value}" ${String(extra.payment_method || 'prevod') === value ? 'selected' : ''}>${label}</option>`).join('')}
              </select>
            </div>
            <div class="form-group">
              <label for="${prefix}IssueDate">Datum vystavení</label>
              <input type="date" id="${prefix}IssueDate" value="${escape(issueDate)}">
            </div>
            <div class="form-group">
              <label for="${prefix}DeliveryDate">Datum dodání</label>
              <input type="date" id="${prefix}DeliveryDate" value="${escape(deliveryDate)}">
            </div>
            <div class="form-group">
              <label for="${prefix}DueAt">Splatnost</label>
              <input type="datetime-local" id="${prefix}DueAt" value="${escape(toDateTimeInputValue(invoice?.due_at))}">
            </div>
            <div class="form-group">
              <label for="${prefix}Currency">Měna</label>
              <input type="text" id="${prefix}Currency" value="${escape(invoice?.currency || 'CZK')}" oninput="window.serviceShell.updateInvoiceDraftTotals('${prefix}')">
            </div>
          </div>
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="${prefix}VariableSymbol">Variabilní symbol</label>
              <input type="text" id="${prefix}VariableSymbol" value="${escape(extra.variable_symbol || '')}">
            </div>
            <div class="form-group">
              <label for="${prefix}OrderNumber">Objednávka</label>
              <input type="text" id="${prefix}OrderNumber" value="${escape(extra.order_number || '')}">
            </div>
            <div class="form-group">
              <label for="${prefix}ConstantSymbol">Konstantní symbol</label>
              <input type="text" id="${prefix}ConstantSymbol" value="${escape(extra.constant_symbol || '')}">
            </div>
            <div class="form-group">
              <label for="${prefix}SpecificSymbol">Specifický symbol</label>
              <input type="text" id="${prefix}SpecificSymbol" value="${escape(extra.specific_symbol || '')}">
            </div>
            <div class="form-group">
              <label for="${prefix}IssuedBy">Vystavil</label>
              <input type="text" id="${prefix}IssuedBy" value="${escape(extra.issued_by || profile?.name || '')}">
            </div>
            <div class="form-group">
              <label for="${prefix}Tags">Tagy</label>
              <input type="text" id="${prefix}Tags" value="${escape(tags)}" placeholder="VIP klient, Flotila">
            </div>
          </div>
          <div class="service-dashboard-modal-grid cols-2 service-shell-invoice-compact-options">
            <div class="form-group">
              <label for="${prefix}Language">Jazyk</label>
              <select id="${prefix}Language">
                <option value="CS" ${String(extra.language || 'CS') === 'CS' ? 'selected' : ''}>Čeština</option>
                <option value="EN" ${String(extra.language || '') === 'EN' ? 'selected' : ''}>Angličtina</option>
                <option value="SK" ${String(extra.language || '') === 'SK' ? 'selected' : ''}>Slovenština</option>
              </select>
            </div>
            <div class="form-group">
              <label for="${prefix}Style">Vzhled</label>
              <select id="${prefix}Style">
                <option value="standard" ${String(extra.style || 'standard') === 'standard' ? 'selected' : ''}>Standard</option>
                <option value="classic" ${String(extra.style || '') === 'classic' ? 'selected' : ''}>Classic</option>
              </select>
            </div>
            <div class="form-group">
              <label for="${prefix}Rounding">Zaokrouhlení</label>
              <select id="${prefix}Rounding">
                <option value="0" ${String(extra.rounding || '0') === '0' ? 'selected' : ''}>Bez zaokrouhlení</option>
                <option value="1" ${String(extra.rounding || '') === '1' ? 'selected' : ''}>Nahoru</option>
                <option value="2" ${String(extra.rounding || '') === '2' ? 'selected' : ''}>Dolů</option>
              </select>
            </div>
            <label class="service-shell-inline-check">
              <input type="checkbox" id="${prefix}Qr" ${extra.qr === false ? '' : 'checked'}>
              <span>QR platba</span>
            </label>
          </div>
          <input type="hidden" id="${prefix}AlreadyPaid" value="${escape(extra.already_paid || '')}">
        </section>

        <section class="service-shell-invoice-two-column">
          <div class="service-shell-invoice-panel">
            <h3 class="service-shell-card-title">Dodavatel</h3>
            <div class="service-dashboard-modal-grid cols-2">
              <div class="form-group"><label for="${prefix}SupplierName">Název</label><input id="${prefix}SupplierName" type="text" value="${escape(supplierName)}"></div>
              <div class="form-group"><label for="${prefix}SupplierEmail">E-mail</label><input id="${prefix}SupplierEmail" type="email" value="${escape(supplierEmail)}"></div>
              <div class="form-group"><label for="${prefix}SupplierIco">IČO</label><input id="${prefix}SupplierIco" type="text" value="${escape(extra.supplier_ico || profile?.ico || '')}"></div>
              <div class="form-group"><label for="${prefix}SupplierDic">DIČ</label><input id="${prefix}SupplierDic" type="text" value="${escape(extra.supplier_dic || profile?.dic || '')}"></div>
              <div class="form-group"><label for="${prefix}SupplierStreet">Ulice</label><input id="${prefix}SupplierStreet" type="text" value="${escape(supplierStreet)}"></div>
              <div class="form-group"><label for="${prefix}SupplierCity">Město</label><input id="${prefix}SupplierCity" type="text" value="${escape(supplierCity)}"></div>
              <div class="form-group"><label for="${prefix}SupplierZip">PSČ</label><input id="${prefix}SupplierZip" type="text" value="${escape(supplierZip)}"></div>
              <div class="form-group"><label for="${prefix}SupplierState">Stát</label><input id="${prefix}SupplierState" type="text" value="${escape(extra.supplier_state || 'Česká republika')}"></div>
              <div class="form-group"><label for="${prefix}SupplierPhone">Telefon</label><input id="${prefix}SupplierPhone" type="text" value="${escape(supplierPhone)}"></div>
              <div class="form-group"><label for="${prefix}SupplierBankAccount">Účet</label><input id="${prefix}SupplierBankAccount" type="text" value="${escape(extra.supplier_bankaccount || '')}"></div>
              <div class="form-group"><label for="${prefix}SupplierBank">Banka</label><input id="${prefix}SupplierBank" type="text" value="${escape(extra.supplier_bank || '')}"></div>
              <div class="form-group"><label for="${prefix}SupplierIban">IBAN</label><input id="${prefix}SupplierIban" type="text" value="${escape(extra.supplier_iban || '')}"></div>
              <div class="form-group"><label for="${prefix}SupplierSwift">SWIFT</label><input id="${prefix}SupplierSwift" type="text" value="${escape(extra.supplier_swift || '')}"></div>
            </div>
          </div>
          <div class="service-shell-invoice-panel">
            <h3 class="service-shell-card-title">Odběratel</h3>
            <div class="service-dashboard-modal-grid cols-2">
              <div class="form-group">
                <label for="${prefix}Customer">Zákazník</label>
                <select id="${prefix}Customer" onchange="window.serviceShell.populateCustomerVehicleSelect('${prefix}Vehicle', this.value, { includeEmpty: true, emptyLabel: 'Bez vozidla', preferredVehicleId: ${Number(invoice?.vehicle_id || 0)} })">
                  ${customers.map((item) => `<option value="${Number(item.customer_id)}" ${Number(item.customer_id) === selectedCustomerId ? 'selected' : ''}>${escape(item.name || item.email || `Zákazník #${Number(item.customer_id)}`)}</option>`).join('')}
                </select>
              </div>
              <div class="form-group"><label for="${prefix}Vehicle">Vozidlo</label><select id="${prefix}Vehicle"><option value="">Načítám vozidla…</option></select></div>
              <div class="form-group"><label for="${prefix}CustomerName">Název / jméno</label><input id="${prefix}CustomerName" type="text" value="${escape(extra.customer_name || invoice?.customer_label || '')}"></div>
              <div class="form-group"><label for="${prefix}CustomerEmail">E-mail</label><input id="${prefix}CustomerEmail" type="email" value="${escape(extra.customer_email || '')}"></div>
              <div class="form-group"><label for="${prefix}CustomerIco">IČO</label><input id="${prefix}CustomerIco" type="text" value="${escape(extra.customer_ico || '')}"></div>
              <div class="form-group"><label for="${prefix}CustomerDic">DIČ</label><input id="${prefix}CustomerDic" type="text" value="${escape(extra.customer_dic || '')}"></div>
              <div class="form-group"><label for="${prefix}CustomerStreet">Ulice</label><input id="${prefix}CustomerStreet" type="text" value="${escape(extra.customer_street || '')}"></div>
              <div class="form-group"><label for="${prefix}CustomerCity">Město</label><input id="${prefix}CustomerCity" type="text" value="${escape(extra.customer_city || '')}"></div>
              <div class="form-group"><label for="${prefix}CustomerZip">PSČ</label><input id="${prefix}CustomerZip" type="text" value="${escape(extra.customer_zip || '')}"></div>
              <div class="form-group"><label for="${prefix}CustomerState">Stát</label><input id="${prefix}CustomerState" type="text" value="${escape(extra.customer_state || 'Česká republika')}"></div>
            </div>
          </div>
        </section>

        <section class="service-shell-invoice-panel">
          <div class="service-shell-card-head">
            <div>
              <h3 class="service-shell-card-title">Položky</h3>
              <p class="service-shell-subtitle">Cena je bez DPH, souhrn se dopočítává průběžně.</p>
            </div>
            <button type="button" class="btn btn-secondary" onclick="window.serviceShell.appendInvoiceLineRow()">Přidat položku</button>
          </div>
          <div id="serviceShellInvoiceLines" class="service-shell-invoice-lines">
            ${lines.map((ln) => `
              <div class="service-shell-invoice-line-row" data-invoice-line-row="1">
                <label><span>Položka</span><input data-invoice-line-description type="text" value="${escape(ln?.description || '')}" oninput="window.serviceShell.updateInvoiceDraftTotals('${prefix}')"></label>
                <label><span>Množství</span><input data-invoice-line-quantity type="number" inputmode="decimal" min="0.01" step="0.1" value="${escape(String(ln?.quantity ?? 1))}" oninput="window.serviceShell.updateInvoiceDraftTotals('${prefix}')"></label>
                <label><span>Jed.</span><input data-invoice-line-unit type="text" value="${escape(ln?.unit || 'ks')}"></label>
                <label><span>Cena bez DPH</span><input data-invoice-line-unit-price type="number" inputmode="decimal" min="0" step="0.01" value="${escape(String(ln?.unit_price ?? 0))}" oninput="window.serviceShell.updateInvoiceDraftTotals('${prefix}')"></label>
                <label><span>DPH %</span><input data-invoice-line-tax-rate type="number" inputmode="decimal" min="0" max="100" step="0.1" value="${escape(String(ln?.tax_rate ?? 21))}" oninput="window.serviceShell.updateInvoiceDraftTotals('${prefix}')"></label>
                <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.removeInvoiceLineRow(this)" aria-label="Odebrat položku">×</button>
              </div>
            `).join('')}
          </div>
          <div id="${prefix}Totals" class="service-shell-invoice-totals"></div>
        </section>

        <section class="service-shell-invoice-two-column">
          <div class="service-shell-invoice-panel">
            <h3 class="service-shell-card-title">Poznámka na doklad</h3>
            <textarea id="${prefix}CustomerNote" rows="4">${escape(extra.customer_note || invoice?.notes || '')}</textarea>
          </div>
          <div class="service-shell-invoice-panel">
            <h3 class="service-shell-card-title">Interní poznámka</h3>
            <textarea id="${prefix}InternalNote" rows="4">${escape(extra.internal_note || '')}</textarea>
            <input type="hidden" id="${prefix}Notes" value="${escape(invoice?.notes || '')}">
          </div>
        </section>
      </form>
    `;
  }

  function buildQuoteSmsText(detail) {
    const vehicle = String(detail?.vehicle_label || 'vozidlo').trim();
    const price = detail?.total_price != null ? `${Number(detail.total_price).toLocaleString('cs-CZ')} Kč` : 'neuvedeno';
    const url = String(detail?.public_quote_url || '').trim();
    return `Dobrý den, posíláme nabídku pro ${vehicle}. Cena: ${price}. Odkaz: ${url}`;
  }

  async function copyQuotePublicLinkByUrl(url) {
    const normalized = String(url || '').trim();
    if (!normalized) return;
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(normalized);
      if (typeof window.showAlert === 'function') window.showAlert('Veřejný odkaz na nabídku byl zkopírován.', 'success');
      return;
    }
    window.prompt('Zkopíruj veřejný odkaz na nabídku:', normalized);
  }

  async function copyQuotePublicLink(quoteId) {
    const resolvedQuoteId = Number(quoteId || state.modal?.context?.quoteId || 0);
    const detail = resolvedQuoteId && Number(state.modal?.context?.quoteId || 0) === resolvedQuoteId
      ? (state.modal?.data || {})
      : await window.apiCall(`/api/service/quotes/${resolvedQuoteId}`, 'GET');
    await copyQuotePublicLinkByUrl(detail?.public_quote_url);
  }

  async function openQuotePublicLink(quoteId) {
    const resolvedQuoteId = Number(quoteId || state.modal?.context?.quoteId || 0);
    const detail = resolvedQuoteId && Number(state.modal?.context?.quoteId || 0) === resolvedQuoteId
      ? (state.modal?.data || {})
      : await window.apiCall(`/api/service/quotes/${resolvedQuoteId}`, 'GET');
    const url = String(detail?.public_quote_url || '').trim();
    if (url) window.open(url, '_blank', 'noopener');
  }

  async function emailQuotePublicLink(quoteId) {
    const resolvedQuoteId = Number(quoteId || state.modal?.context?.quoteId || 0);
    const detail = resolvedQuoteId && Number(state.modal?.context?.quoteId || 0) === resolvedQuoteId
      ? (state.modal?.data || {})
      : await window.apiCall(`/api/service/quotes/${resolvedQuoteId}`, 'GET');
    const url = String(detail?.public_quote_url || '').trim();
    const email = String(detail?.customer_email || '').trim();
    if (!url) return;
    const subject = encodeURIComponent(`Cenová nabídka pro ${String(detail?.vehicle_label || 'vozidlo')}`);
    const body = encodeURIComponent(`Dobrý den,\n\nposíláme cenovou nabídku: ${url}\n\nS pozdravem\n${String(detail?.service_name || 'Servis')}`);
    window.open(`mailto:${encodeURIComponent(email)}?subject=${subject}&body=${body}`, '_self');
  }

  async function shareQuoteSmsTemplate(quoteId) {
    const resolvedQuoteId = Number(quoteId || state.modal?.context?.quoteId || 0);
    const detail = resolvedQuoteId && Number(state.modal?.context?.quoteId || 0) === resolvedQuoteId
      ? (state.modal?.data || {})
      : await window.apiCall(`/api/service/quotes/${resolvedQuoteId}`, 'GET');
    const text = buildQuoteSmsText(detail);
    const phone = String(detail?.customer_phone || '').trim();
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      if (typeof window.showAlert === 'function') window.showAlert('SMS šablona k nabídce byla zkopírována.', 'success');
    }
    window.open(`sms:${encodeURIComponent(phone)}?body=${encodeURIComponent(text)}`, '_self');
  }

  async function openFirstRecordForQuote() {
    const records = Array.isArray(state.modal?.data?.service_records) ? state.modal.data.service_records : [];
    const firstRecordId = Number(records[0]?.id || 0);
    if (firstRecordId) {
      await createQuoteFromRecord(firstRecordId);
      return;
    }
    const vehicleId = Number(state.modal?.context?.entityId || state.activeVehicle?.vehicleId || 0);
    if (vehicleId) {
      openServiceRecordModal(vehicleId);
    }
  }

  async function createInvoiceFromQuote(quoteId, options = {}) {
    const resolvedQuoteId = Number(quoteId || state.modal?.context?.quoteId || 0);
    if (!resolvedQuoteId) return;
    const body = {};
    const billingCustomerId = Number(options.billingCustomerId || 0);
    if (billingCustomerId > 0) body.billing_customer_id = billingCustomerId;
    try {
      const invoice = await window.apiCall(`/api/service/invoices/from-quote/${resolvedQuoteId}`, 'POST', body);
      if (typeof window.showAlert === 'function') {
        const label = invoice?.invoice_number ? ` ${invoice.invoice_number}` : '';
        window.showAlert(`Faktura${label} byla připravena z nabídky.`, 'success');
      }
      await load(true, true);
      openServiceInvoiceDetailModal(Number(invoice?.id || 0), { billingView: true });
    } catch (err) {
      const detail = err?.detail || err?.payload || {};
      const code = String(detail?.code || err?.code || '');
      if (code === 'unowned_requires_billing_customer') {
        const msg = detail?.message || 'Pro vystavení faktury k nepřiřazenému vozidlu doplňte fakturační kontakt.';
        if (typeof window.showAlert === 'function') window.showAlert(msg, 'warning');
        return;
      }
      const existingInvoiceId = Number(detail?.invoice_id || 0);
      if (existingInvoiceId > 0) {
        if (typeof window.showAlert === 'function') window.showAlert('K zakázce už existuje faktura.', 'info');
        await load(true, true);
        openServiceInvoiceDetailModal(existingInvoiceId, { billingView: true });
        return;
      }
      const msg = err?.message || detail?.message || 'Fakturu z nabídky se nepodařilo vytvořit.';
      if (typeof window.showAlert === 'function') window.showAlert(msg, 'error');
      throw err;
    }
  }

  function openBillingQuoteDetail(quoteId) {
    openQuoteModal(quoteId, { billingView: true });
  }

  function openBillingInvoiceDetail(invoiceId) {
    openServiceInvoiceDetailModal(invoiceId, { billingView: true });
  }

  function openQuoteModal(quoteId, options = {}) {
    const resolvedQuoteId = Number(quoteId || 0);
    if (!resolvedQuoteId) return;
    const billingView = Boolean(options.billingView);
    openModal({
      key: `service-quote-${resolvedQuoteId}`,
      entityType: 'service-quote',
      kicker: `Nabídka #${resolvedQuoteId}`,
      title: 'Cenová nabídka',
      description: 'Zákaznický výstup navázaný na servisní záznam a zakázku.',
      size: 'wide',
      context: { quoteId: resolvedQuoteId, billingView },
      actions: {
        save: async () => {
          const items = quoteItemsFromDom();
          const totalPrice = Number(document.getElementById('serviceShellQuoteTotal')?.value || 0) || 0;
          const laborHours = Number(document.getElementById('serviceShellQuoteLaborHours')?.value || 0) || 0;
          const laborRate = Number(document.getElementById('serviceShellQuoteLaborRate')?.value || 0) || 0;
          const status = String(document.getElementById('serviceShellQuoteStatus')?.value || 'draft').trim();
          const updated = await window.apiCall(`/api/service/quotes/${resolvedQuoteId}`, 'PUT', {
            items,
            labor_hours: laborHours,
            labor_rate: laborRate,
            total_price: totalPrice,
            status,
          });
          return { data: updated, close: false };
        },
      },
      load: async () => window.apiCall(`/api/service/quotes/${resolvedQuoteId}`, 'GET'),
      renderContent: (modal) => {
        const detail = modal.data || {};
        const items = Array.isArray(detail?.items) ? detail.items : [];
        const billingView = Boolean(modal?.context?.billingView);
        const detailTestId = billingView ? 'service-billing-quote-detail' : 'service-quote-detail';
        return `
          <div data-testid="${detailTestId}">
          <p class="service-shell-list-note" data-testid="service-billing-limited-notice">Obchodní doklady jsou viditelné pouze servisu — majitel je v historii vozidla neuvidí.</p>
          <section class="service-shell-mobile-form-top">
            <div class="service-shell-mobile-kicker">Výstup pro zákazníka</div>
            <strong>${escape(detail?.vehicle_label || 'Vozidlo')}</strong>
            <span class="service-shell-muted">${escape(detail?.service_name || 'Servis')} · ${escape(detail?.status_label || detail?.status || 'Koncept')}</span>
          </section>
          <section class="service-shell-side-card">
            <div class="service-shell-list">
              <div class="service-shell-list-row"><span class="service-shell-list-title">Veřejný odkaz</span><span class="service-shell-list-value">${escape(detail?.public_quote_url || 'Ještě není připraven')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Schváleno</span><span class="service-shell-list-value">${escape(detail?.approved_at ? formatDateTime(detail.approved_at) : '-')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Odmítnuto</span><span class="service-shell-list-value">${escape(detail?.rejected_at ? formatDateTime(detail.rejected_at) : '-')}</span></div>
            </div>
          </section>
          <div class="form-group">
            <label for="serviceShellQuoteStatus">Stav nabídky</label>
            <select id="serviceShellQuoteStatus">
              <option value="draft" ${detail?.status === 'draft' ? 'selected' : ''}>Koncept</option>
              <option value="sent" ${detail?.status === 'sent' ? 'selected' : ''}>Odesláno</option>
              <option value="approved" ${detail?.status === 'approved' ? 'selected' : ''}>Schváleno</option>
              <option value="rejected" ${detail?.status === 'rejected' ? 'selected' : ''}>Zamítnuto</option>
            </select>
          </div>
          <div id="serviceShellQuoteItems" class="service-shell-quote-items">
            ${items.map((item) => `
              <div class="service-shell-quote-item-row" data-quote-item-row="1">
                <input data-quote-item-name type="text" value="${escape(item?.name || '')}" placeholder="Položka">
                <input data-quote-item-qty type="number" inputmode="decimal" min="0" step="0.1" value="${escape(String(item?.quantity ?? 1))}">
                <input data-quote-item-price type="number" inputmode="decimal" min="0" step="0.01" value="${escape(String(item?.unit_price ?? 0))}">
              </div>
            `).join('') || `
              <div class="service-shell-quote-item-row" data-quote-item-row="1">
                <input data-quote-item-name type="text" value="Servisní práce" placeholder="Položka">
                <input data-quote-item-qty type="number" inputmode="decimal" min="0" step="0.1" value="1">
                <input data-quote-item-price type="number" inputmode="decimal" min="0" step="0.01" value="${escape(String(detail?.total_price ?? 0))}">
              </div>
            `}
          </div>
          <div class="form-group">
            <label for="serviceShellQuoteLaborHours">Hodiny práce</label>
            <input id="serviceShellQuoteLaborHours" type="number" inputmode="decimal" min="0" step="0.1" value="${escape(String(detail?.labor_hours ?? 0))}">
          </div>
          <div class="form-group">
            <label for="serviceShellQuoteLaborRate">Sazba práce</label>
            <input id="serviceShellQuoteLaborRate" type="number" inputmode="decimal" min="0" step="0.01" value="${escape(String(detail?.labor_rate ?? 0))}">
          </div>
          <div class="form-group">
            <label for="serviceShellQuoteTotal">Celková cena</label>
            <input id="serviceShellQuoteTotal" type="number" inputmode="decimal" min="0" step="0.01" value="${escape(String(detail?.total_price ?? 0))}">
          </div>
          <p class="service-shell-list-note service-work-order-billing-error hidden" id="serviceBillingQuoteError" data-testid="service-billing-error"></p>
          </div>
        `;
      },
      renderFooter: (modal) => {
        const saveBtn = `<button type="button" class="btn btn-primary" onclick="window.serviceShell.runModalAction('save')">${modal.saving ? 'Ukládám…' : 'Uložit nabídku'}</button>`;
        const secondaryBtns = `
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zpět</button>
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.appendQuoteItemRow()">Přidat položku</button>
          <button type="button" class="btn btn-secondary" data-testid="service-billing-create-invoice-from-quote-button" onclick="window.serviceShell.createInvoiceFromQuote(${resolvedQuoteId})">Vytvořit fakturu</button>
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.shareQuotePdf(${resolvedQuoteId})">Sdílet / stáhnout PDF</button>
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.copyQuotePublicLink(${resolvedQuoteId})">Kopírovat veřejný odkaz</button>
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.openQuotePublicLink(${resolvedQuoteId})">Otevřít veřejný odkaz</button>
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.emailQuotePublicLink(${resolvedQuoteId})">Odeslat e-mailem</button>
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.shareQuoteSmsTemplate(${resolvedQuoteId})">SMS šablona</button>`;
        if (isMobileViewport()) {
          return renderMobileModalFooter(`
            ${saveBtn}
            <details class="service-shell-mobile-more-actions">
              <summary>Další akce</summary>
              <div class="service-shell-mobile-more-actions-body">${secondaryBtns}</div>
            </details>
          `);
        }
        return `
        <div class="service-shell-modal-footer">
          ${secondaryBtns}
          ${saveBtn}
        </div>`;
      },
    });
  }

  async function createQuoteFromRecord(recordId) {
    const resolvedRecordId = Number(recordId || 0);
    if (!resolvedRecordId) return;
    const quote = await window.apiCall(`/api/service/quotes/from-record/${resolvedRecordId}`, 'POST');
    openQuoteModal(Number(quote?.id || 0));
  }

  function shareQuotePdf(quoteId) {
    const resolvedQuoteId = Number(quoteId || state.modal?.context?.quoteId || 0);
    if (!resolvedQuoteId) return;
    const path = `/api/service/quotes/${resolvedQuoteId}/pdf`;
    if (typeof window.openAuthenticatedPdf === 'function') {
      window.openAuthenticatedPdf(path).catch((err) => {
        const msg = err?.message || 'PDF se nepodařilo otevřít.';
        if (typeof window.showAlert === 'function') window.showAlert(msg, 'error');
      });
      return;
    }
    const url = `${window.location.origin}${path}`;
    if (navigator.share) {
      navigator.share({ title: 'Cenová nabídka', url }).catch(() => {
        window.open(url, '_blank', 'noopener');
      });
      return;
    }
    window.open(url, '_blank', 'noopener');
  }

  async function openCreateReminderModal(prefill = {}) {
    const customers = Array.isArray(state.customers) ? state.customers : [];
    const preferredCustomerId = Number(prefill.customerId || customers[0]?.customer_id || 0);
    openModal({
      key: 'reminder-create',
      entityType: 'reminder',
      kicker: 'Připomínka',
      title: 'Nová připomínka',
      description: 'Follow-up nad klientem a volitelně konkrétním vozidlem v tenant-safe servisním workflow.',
      actions: {
        save: async () => {
          const customerId = Number(document.getElementById('serviceShellCreateReminderCustomer')?.value || 0);
          const vehicleId = Number(document.getElementById('serviceShellCreateReminderVehicle')?.value || 0) || null;
          const type = String(document.getElementById('serviceShellCreateReminderType')?.value || 'SERVIS').trim();
          const text = String(document.getElementById('serviceShellCreateReminderText')?.value || '').trim();
          const dueDate = String(document.getElementById('serviceShellCreateReminderDueDate')?.value || '').trim() || null;
          const notifyAt = fromDateTimeInputValue(document.getElementById('serviceShellCreateReminderNotifyAt')?.value);
          const notificationMethod = String(document.getElementById('serviceShellCreateReminderMethod')?.value || '').trim() || null;
          if (!customerId || !text) {
            throw new Error('Vyberte klienta a vyplňte text připomínky.');
          }
          await window.apiCall('/api/v1/services/workspace/reminders', 'POST', {
            customer_id: customerId,
            vehicle_id: vehicleId,
            type,
            text,
            due_date: dueDate,
            notify_at: notifyAt,
            notification_method: notificationMethod,
          });
          return { close: true, refreshParent: true, message: 'Připomínka byla vytvořena.' };
        },
      },
      renderContent: () => `
        <form class="service-dashboard-modal-form" onsubmit="event.preventDefault(); window.serviceShell.submitCreateReminderModal();">
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellCreateReminderCustomer">Zákazník</label>
              <select id="serviceShellCreateReminderCustomer" onchange="window.serviceShell.populateCustomerVehicleSelect('serviceShellCreateReminderVehicle', this.value, { includeEmpty: true, emptyLabel: 'Obecná připomínka' })">
                ${customers.map((item) => `<option value="${Number(item.customer_id)}" ${Number(item.customer_id) === preferredCustomerId ? 'selected' : ''}>${escape(item.name || item.email || `Zákazník #${Number(item.customer_id)}`)}</option>`).join('')}
              </select>
            </div>
            <div class="form-group">
              <label for="serviceShellCreateReminderVehicle">Vozidlo</label>
              <select id="serviceShellCreateReminderVehicle"><option value="">Načítám vozidla…</option></select>
            </div>
          </div>
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellCreateReminderType">Typ</label>
              <input type="text" id="serviceShellCreateReminderType" value="${escape(prefill.type || 'SERVIS')}">
            </div>
            <div class="form-group">
              <label for="serviceShellCreateReminderMethod">Kanál</label>
              <select id="serviceShellCreateReminderMethod">
                <option value="">Výchozí</option>
                <option value="app">Aplikace</option>
                <option value="email">E-mail</option>
                <option value="both">Obojí</option>
              </select>
            </div>
          </div>
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellCreateReminderDueDate">Termín</label>
              <input type="date" id="serviceShellCreateReminderDueDate" value="${escape(prefill.dueDate || '')}">
            </div>
            <div class="form-group">
              <label for="serviceShellCreateReminderNotifyAt">Notifikovat</label>
              <input type="datetime-local" id="serviceShellCreateReminderNotifyAt" value="${escape(prefill.notifyAt || '')}">
            </div>
          </div>
          <div class="form-group">
            <label for="serviceShellCreateReminderText">Text</label>
            <textarea id="serviceShellCreateReminderText" rows="4">${escape(prefill.text || '')}</textarea>
          </div>
        </form>
      `,
      renderFooter: (modal) => `
        <div class="service-shell-modal-footer">
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zrušit</button>
          <button type="button" class="btn btn-primary" onclick="window.serviceShell.submitCreateReminderModal()">${modal.saving ? 'Ukládám…' : 'Vytvořit připomínku'}</button>
        </div>
      `,
    });
    await populateCustomerVehicleSelect('serviceShellCreateReminderVehicle', preferredCustomerId, {
      includeEmpty: true,
      emptyLabel: 'Obecná připomínka',
    });
  }

  async function submitCreateReminderModal() {
    if (isModalOpen('reminder-create')) {
      return runModalAction('save');
    }
  }

  async function openCreateInvoiceModal(prefill = {}) {
    const customers = Array.isArray(state.customers) ? state.customers : [];
    const preferredCustomerId = Number(prefill.customerId || customers[0]?.customer_id || 0);
    const prof = currentProfile();
    const profileStreet = [prof?.street, prof?.street_number].filter(Boolean).join(' ').trim();
    const draftInvoice = {
      customer_id: preferredCustomerId,
      vehicle_id: Number(prefill.vehicleId || 0) || null,
      currency: prefill.currency || 'CZK',
      due_at: prefill.dueAt || '',
      notes: prefill.notes || '',
      status: 'draft',
      status_label: 'Koncept',
      extra: {
        invoice_type: '1',
        payment_method: 'prevod',
        issue_date: new Date().toISOString().slice(0, 10),
        delivery_date: new Date().toISOString().slice(0, 10),
        language: 'CS',
        style: 'standard',
        rounding: '0',
        qr: true,
        customer_note: prefill.notes || '',
        supplier_name: prof?.name || window.currentUser?.name || '',
        supplier_email: prof?.email || window.currentUser?.email || '',
        supplier_ico: prof?.ico || '',
        supplier_dic: prof?.dic || '',
        supplier_street: profileStreet || '',
        supplier_city: prof?.city || '',
        supplier_zip: prof?.zip || '',
        supplier_phone: prof?.phone || '',
      },
    };
    openModal({
      key: 'invoice-create',
      entityType: 'service-invoice',
      kicker: 'Faktura',
      title: 'Nová faktura',
      description: 'Kompletní hlavička dodavatele a odběratele, položky a poznámky — vše v aplikaci, PDF po vystavení.',
      size: 'wide',
      actions: {
        save: async () => {
          const payload = invoicePayloadFromDom('serviceShellCreateInvoice', draftInvoice);
          payload.notes = payload.extra?.customer_note || payload.notes;
          if (!payload.customer_id) {
            throw new Error('Vyberte klienta faktury.');
          }
          if (!payload.lines.length) {
            throw new Error('Faktura musí obsahovat alespoň jednu položku.');
          }
          await window.apiCall('/api/service/invoices', 'POST', payload);
          return { close: true, refreshParent: true, message: 'Draft faktura byla vytvořena.' };
        },
      },
      renderContent: () => invoiceEditorHtml({
        prefix: 'serviceShellCreateInvoice',
        invoice: draftInvoice,
        customers,
        lines: prefill.line ? [prefill.line] : [],
        mode: 'create',
      }),
      renderFooter: (modal) => `
        <div class="service-shell-modal-footer">
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zrušit</button>
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.appendInvoiceLineRow()">Přidat položku</button>
          <button type="button" class="btn btn-primary" onclick="window.serviceShell.submitCreateInvoiceModal()">${modal.saving ? 'Ukládám…' : 'Uložit koncept'}</button>
        </div>
      `,
    });
    await populateCustomerVehicleSelect('serviceShellCreateInvoiceVehicle', preferredCustomerId, {
      includeEmpty: true,
      emptyLabel: 'Bez vozidla',
      preferredVehicleId: Number(prefill.vehicleId || 0),
    });
    if (!prefill.line) appendInvoiceLineRow({ description: '', quantity: 1, unit: 'ks', unit_price: 0, tax_rate: 21 });
    updateInvoiceDraftTotals('serviceShellCreateInvoice');
  }

  async function submitCreateInvoiceModal() {
    if (isModalOpen('invoice-create')) {
      return runModalAction('save');
    }
  }

  function openServiceInvoicePdf(invoiceId) {
    const id = Number(invoiceId || 0);
    if (!id) return;
    const path = `/api/service/invoices/${id}/pdf`;
    if (typeof window.openAuthenticatedPdf === 'function') {
      window.openAuthenticatedPdf(path).catch((err) => {
        const msg = err?.message || 'PDF faktury se nepodařilo otevřít.';
        if (typeof window.showAlert === 'function') window.showAlert(msg, 'error');
      });
      return;
    }
    window.open(`${window.location.origin}${path}`, '_blank', 'noopener');
  }

  function openServiceInvoiceDetailModal(invoiceId, options = {}) {
    const id = Number(invoiceId || 0);
    if (!id) return;
    const billingView = Boolean(options.billingView);
    openModal({
      key: `service-invoice-${id}`,
      entityType: 'service-invoice',
      kicker: `Faktura #${id}`,
      title: 'Servisní faktura',
      description: 'Uložte koncept, upravte doklad a vystavte — PDF odpovídá údajům z editoru.',
      size: 'wide',
      context: { invoiceId: id, billingView },
      actions: {
        save: async () => {
          const inv = state.modal?.data || {};
          if (String(inv?.status || '').toLowerCase() !== 'draft') {
            throw new Error('Upravit lze pouze draft fakturu.');
          }
          const payload = invoicePayloadFromDom('serviceShellInvoice', inv);
          payload.notes = payload.extra?.customer_note || payload.notes;
          if (!payload.customer_id) {
            throw new Error('Vyberte klienta faktury.');
          }
          if (!payload.lines.length) {
            throw new Error('Faktura musí obsahovat alespoň jednu položku.');
          }
          const updated = await window.apiCall(`/api/service/invoices/${id}`, 'PUT', payload);
          return { data: updated, close: false, refreshParent: true, message: 'Draft faktura byla uložena.' };
        },
      },
      load: async () => window.apiCall(`/api/service/invoices/${id}`, 'GET'),
      renderContent: (modal) => {
        const inv = modal.data || {};
        const isDraft = String(inv?.status || '').toLowerCase() === 'draft';
        const customers = Array.isArray(state.customers) ? state.customers : [];
        const lines = Array.isArray(inv.lines) ? inv.lines : [];
        const totals = invoiceTotals(lines);
        if (isDraft && inv?.customer_id) {
          window.setTimeout(() => {
            window.serviceShell.populateCustomerVehicleSelect('serviceShellInvoiceVehicle', inv.customer_id, {
              includeEmpty: true,
              emptyLabel: 'Bez vozidla',
              preferredVehicleId: Number(inv?.vehicle_id || 0),
            }).then(() => window.serviceShell.updateInvoiceDraftTotals('serviceShellInvoice')).catch((err) => console.warn('[SERVICE_SHELL] invoice vehicle select load failed:', err));
          }, 0);
        }
        const detailTestId = modal?.context?.billingView ? 'service-billing-invoice-detail' : 'service-invoice-detail';
        return `
          <div data-testid="${detailTestId}">
          <p class="service-shell-list-note" data-testid="service-billing-limited-notice">Obchodní doklady jsou viditelné pouze servisu — majitel je v historii vozidla neuvidí.</p>
          ${inv?.work_order_id ? `<p class="service-shell-list-note">Zakázka #${escape(String(inv.work_order_id))}</p>` : ''}
          <section class="service-shell-invoice-overview">
            <div>
              <span class="service-shell-mobile-kicker">Číslo</span>
              <strong>${escape(inv?.invoice_number || '(koncept)')}</strong>
            </div>
            <div>
              <span class="service-shell-mobile-kicker">Zákazník</span>
              <strong>${escape(inv?.customer_label || (inv?.customer_id != null ? `Zákazník #${inv.customer_id}` : '-'))}</strong>
            </div>
            <div>
              <span class="service-shell-mobile-kicker">Variabilní symbol</span>
              <strong>${escape(inv?.extra?.variable_symbol || '—')}</strong>
            </div>
            <div>
              <span class="service-shell-mobile-kicker">Celkem</span>
              <strong>${escape(invoiceMoney(inv?.total ?? totals.gross, inv?.currency || 'CZK'))}</strong>
            </div>
          </section>
          ${isDraft ? invoiceEditorHtml({
            prefix: 'serviceShellInvoice',
            invoice: inv,
            customers,
            lines,
            mode: 'edit',
          }) : `
            <section class="service-shell-invoice-panel">
              <div class="service-shell-card-head">
                <div>
                  <h3 class="service-shell-card-title">Položky</h3>
                  <p class="service-shell-subtitle">Vystavený doklad je lokálně jen pro čtení.</p>
                </div>
              </div>
              <div class="service-shell-table-wrap">
                <table class="service-shell-data-table"><thead><tr><th>Popis</th><th>Množství</th><th>Jed.</th><th>Cena bez DPH</th><th>DPH</th><th>Celkem</th></tr></thead><tbody>
                  ${lines.map((ln) => `
                    <tr>
                      <td data-label="Popis">${escape(ln?.description || '-')}</td>
                      <td data-label="Množství">${escape(String(ln?.quantity ?? '-'))}</td>
                      <td data-label="Jed.">${escape(ln?.unit || '-')}</td>
                      <td data-label="Cena bez DPH">${escape(invoiceMoney(ln?.unit_price || 0, inv?.currency || 'CZK'))}</td>
                      <td data-label="DPH">${escape(String(ln?.tax_rate ?? 0))} %</td>
                      <td data-label="Celkem">${escape(invoiceMoney(ln?.line_total ?? invoiceLineGross(ln), inv?.currency || 'CZK'))}</td>
                    </tr>`).join('') || '<tr><td colspan="6" class="service-shell-empty">Bez položek</td></tr>'}
                </tbody></table>
              </div>
              <div class="service-shell-invoice-totals">
                <div><span>Základ</span><strong>${escape(invoiceMoney(inv?.subtotal ?? totals.net, inv?.currency || 'CZK'))}</strong></div>
                <div><span>DPH</span><strong>${escape(invoiceMoney(inv?.tax_total ?? totals.tax, inv?.currency || 'CZK'))}</strong></div>
                <div><span>Celkem</span><strong>${escape(invoiceMoney(inv?.total ?? totals.gross, inv?.currency || 'CZK'))}</strong></div>
              </div>
            </section>
          `}
          </div>
        `;
      },
      renderFooter: (modal) => {
        const inv = modal.data || {};
        const st = String(inv?.status || '').toLowerCase();
        const showIssue = st === 'draft';
        const showCancel = st === 'draft' || st === 'issued';
        return `
        <div class="service-shell-modal-footer">
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zavřít</button>
          ${showIssue ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.appendInvoiceLineRow()">Přidat položku</button>` : ''}
          <button type="button" class="btn btn-secondary" data-testid="service-billing-invoice-pdf-button" onclick="window.serviceShell.openServiceInvoicePdf(${id})">PDF</button>
          ${showIssue ? `<button type="button" class="btn btn-primary" onclick="window.serviceShell.runModalAction('save')">${modal.saving ? 'Ukládám…' : 'Uložit draft'}</button>` : ''}
          ${showIssue ? `<button type="button" class="btn btn-primary" onclick="window.serviceShell.issueServiceInvoiceFromModal(${id})">Vystavit</button>` : ''}
          ${showCancel ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.cancelServiceInvoiceFromModal(${id})">Zrušit</button>` : ''}
        </div>`;
      },
    });
    const current = state.modal?.data || {};
    if (String(current?.status || '').toLowerCase() === 'draft' && current?.customer_id) {
      queueMicrotask(() => {
        window.serviceShell.populateCustomerVehicleSelect('serviceShellInvoiceVehicle', current.customer_id, {
          includeEmpty: true,
          emptyLabel: 'Bez vozidla',
          preferredVehicleId: Number(current?.vehicle_id || 0),
        }).then(() => window.serviceShell.updateInvoiceDraftTotals('serviceShellInvoice')).catch((err) => console.warn('[SERVICE_SHELL] invoice vehicle select load failed:', err));
      });
    }
  }

  async function issueServiceInvoiceFromModal(invoiceId) {
    const id = Number(invoiceId || 0);
    if (!id) return;
    await window.apiCall(`/api/service/invoices/${id}/issue`, 'POST');
    if (typeof window.showAlert === 'function') window.showAlert('Faktura byla vystavena.', 'success');
    await load(true, true);
    closeModal();
  }

  async function cancelServiceInvoiceFromModal(invoiceId) {
    const id = Number(invoiceId || 0);
    if (!id) return;
    await window.apiCall(`/api/service/invoices/${id}/cancel`, 'POST');
    if (typeof window.showAlert === 'function') window.showAlert('Faktura byla zrušena.', 'success');
    await load(true, true);
    closeModal();
  }

  function openVehicleQrModal(vehicleId) {
    const resolvedVehicleId = Number(vehicleId || state.activeVehicle?.vehicleId || 0);
    if (!resolvedVehicleId) return;
    openModal({
      key: `vehicle-qr-${resolvedVehicleId}`,
      entityType: 'vehicle-qr',
      kicker: `Vozidlo #${resolvedVehicleId}`,
      title: 'QR historie vozidla',
      description: 'Bezpečný veřejný token s revokací, podpisem a auditní stopou.',
      size: 'wide',
      bodyClass: 'service-shell-modal-body--qr',
      context: { vehicleId: resolvedVehicleId },
      load: async () => {
        try {
          return await window.apiCall(`/api/v1/services/workspace/vehicles/${resolvedVehicleId}/qr`, 'GET');
        } catch (error) {
          if (String(error?.message || '').includes('404')) {
            return { missing: true, vehicle_id: resolvedVehicleId };
          }
          throw error;
        }
      },
      actions: {
        create: async () => {
          const data = await window.apiCall(`/api/v1/services/workspace/vehicles/${resolvedVehicleId}/qr`, 'POST', {
            public_mode: 'verified',
            explicit_full_consent: false,
          });
          return { data, close: false };
        },
        regenerate: async () => {
          const data = await window.apiCall(`/api/v1/services/workspace/vehicles/${resolvedVehicleId}/qr/regenerate`, 'POST', {
            public_mode: 'verified',
            explicit_full_consent: false,
          });
          return { data, close: false };
        },
      },
      renderContent: (modal) => {
        const detail = modal.data || {};
        if (detail?.missing) {
          return '<div class="service-shell-empty">Pro toto vozidlo zatím nebyl vygenerován veřejný QR token.</div>';
        }
        return `
          <section class="service-shell-qr-panel">
            <div class="service-shell-qr-visual">${detail?.qr_svg || ''}</div>
            <div class="service-shell-list">
              <div class="service-shell-list-row"><span class="service-shell-list-title">Režim</span><span class="service-shell-list-value">${escape(detail?.public_mode || '-')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Vydáno</span><span class="service-shell-list-value">${escape(detail?.issued_at ? formatDateTime(detail.issued_at) : '-')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Poslední přístup</span><span class="service-shell-list-value">${escape(detail?.last_access_at ? formatDateTime(detail.last_access_at) : 'Zatím žádný')}</span></div>
            </div>
            <div class="service-shell-qr-link">${escape(detail?.public_history_url || '')}</div>
            <div class="service-shell-qr-actions">
              <button type="button" class="btn btn-secondary" onclick="window.serviceShell.openPublicHistoryFromModal()">Otevřít historii</button>
              <button type="button" class="btn btn-secondary" onclick="window.serviceShell.copyPublicHistoryFromModal()">Kopírovat odkaz</button>
            </div>
          </section>
        `;
      },
      renderFooter: (modal) => `
        <div class="service-shell-modal-footer ${isMobileViewport() ? 'service-shell-mobile-action-bar service-shell-mobile-action-bar--stack' : ''}">
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zpět</button>
          ${modal?.data?.missing
            ? `<button type="button" class="btn btn-primary" onclick="window.serviceShell.runModalAction('create')">${modal.saving ? 'Generuji…' : 'Vygenerovat QR'}</button>`
            : `
              <button type="button" class="btn btn-secondary" onclick="window.serviceShell.sharePublicHistoryFromModal()">Sdílet</button>
              <button type="button" class="btn btn-primary" onclick="window.serviceShell.runModalAction('regenerate')">${modal.saving ? 'Obnovuji…' : 'Regenerovat QR'}</button>
            `}
        </div>
      `,
    });
  }

  function openPublicHistoryFromModal() {
    const url = String(state.modal?.data?.public_history_url || '').trim();
    if (url) {
      window.open(url, '_blank', 'noopener');
    }
  }

  async function sharePublicHistoryFromModal() {
    const url = String(state.modal?.data?.public_history_url || '').trim();
    if (!url) return;
    if (navigator.share) {
      await navigator.share({ title: 'Veřejná historie vozidla', url });
      return;
    }
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(url);
      if (typeof window.showAlert === 'function') {
        window.showAlert('Odkaz na veřejnou historii byl zkopírován.', 'success');
      }
    }
  }

  async function copyPublicHistoryFromModal() {
    const url = String(state.modal?.data?.public_history_url || '').trim();
    if (!url) return;
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(url);
      if (typeof window.showAlert === 'function') {
        window.showAlert('Odkaz na veřejnou historii byl zkopírován.', 'success');
      }
      return;
    }
    window.prompt('Zkopírujte veřejný odkaz ručně:', url);
  }

  function openCustomerDetailModal(customerId) {
    const id = Number(customerId || 0);
    if (!id) return;
    openDetailModal({
      entityType: 'customer',
      entityId: id,
      endpoint: `/api/v1/services/workspace/customers/${id}/detail`,
      kicker: `Zákazník #${id}`,
      title: 'Detail zákazníka',
      description: 'Propojení servisního účtu se zákazníkem ve Správě vozidel, stav vazby a jeho vozidla.',
      actions: {
        link: async () => {
          const response = await window.apiCall(`/api/v1/services/workspace/customers/${id}/link`, 'POST');
          return {
            close: false,
            reloadDetail: true,
            refreshParent: true,
            message: response?.message || 'Zákazník byl propojen.',
          };
        },
      },
      renderContent: (detail) => `
        ${renderDetailPills(detail)}
        ${renderBlockingReason(detail)}
        <div class="service-shell-modal-detail-grid cols-2">
          <div class="service-shell-side-card">
            <h3>Základní informace</h3>
            <div class="service-shell-list">
              <div class="service-shell-list-row"><span class="service-shell-list-title">Jméno</span><span class="service-shell-list-value">${escape(detail?.name || '-')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">E-mail</span><span class="service-shell-list-value">${escape(detail?.email || detail?.email_masked || '-')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Telefon</span><span class="service-shell-list-value">${escape(detail?.phone || detail?.phone_masked || '-')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Vozidla</span><span class="service-shell-list-value">${escape(String(detail?.vehicles_count ?? '-'))}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Sdílená vozidla</span><span class="service-shell-list-value">${escape(String(detail?.shared_vehicles_count ?? 0))}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Poslední servis</span><span class="service-shell-list-value">${escape(detail?.last_service_date ? formatDate(detail.last_service_date) : '-')}</span></div>
            </div>
          </div>
          <div class="service-shell-side-card">
            <h3>Vazba a pozvánky</h3>
            <div class="service-shell-list">
              <div class="service-shell-list-row"><span class="service-shell-list-title">Status</span><span class="service-shell-list-value">${escape(accessStatusLabel(detail?.status))}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Disclosure</span><span class="service-shell-list-value">${escape(disclosureLabel(detail?.disclosure))}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Pozvánka</span><span class="service-shell-list-value">${escape(detail?.invite_status_label || 'Bez pozvánky')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Poznámka k vazbě</span><span class="service-shell-list-value">${escape(detail?.note || '-')}</span></div>
            </div>
          </div>
        </div>
        <section class="service-shell-side-card">
          <h3>Vozidla zákazníka</h3>
          <div class="service-shell-list">
            ${(Array.isArray(detail?.vehicles) && detail.vehicles.length)
              ? detail.vehicles.map((item) => `
                <div class="service-shell-list-row">
                  <div>
                    <p class="service-shell-list-title">${escape(item?.label || 'Vozidlo')}</p>
                    <p class="service-shell-list-note">${escape(accessStatusLabel(item?.status || 'matched'))}</p>
                  </div>
                  <div class="service-shell-modal-actions">
                    <button type="button" class="btn btn-secondary" onclick="window.serviceShell.openVehicleDetailModal(${Number(item?.vehicle_id || 0)})">Otevřít detail</button>
                    ${item?.can_create_work_order ? `<button type="button" class="btn btn-primary" onclick="window.serviceShell.closeModal(); window.serviceShell.openCreateWorkOrderModal({ ownerId: ${id}, vehicleId: ${Number(item?.vehicle_id || 0)} })">Nová zakázka</button>` : ''}
                  </div>
                </div>
              `).join('')
              : '<div class="service-shell-empty">Zákazník zatím nemá v tomto přehledu dostupná vozidla.</div>'}
          </div>
        </section>
      `,
      renderFooter: (detail, modal) => `
        <div class="service-shell-modal-footer">
          ${detail?.can_link ? `<button type="button" class="btn btn-primary" onclick="window.serviceShell.runModalAction('link')">${modal.saving ? 'Propojuji…' : 'Propojit zákazníka'}</button>` : ''}
          ${detail?.status === 'linked' ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.openCustomerLinkNoteModal(${id}, ${JSON.stringify(String(detail?.note || ''))})">Upravit poznámku</button>` : ''}
          ${detail?.status === 'linked' ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.unlinkCustomer(${id})">Odpojit zákazníka</button>` : ''}
          ${detail?.status === 'linked' ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal(); window.serviceShell.openAddVehicleModal(${id})">Přidat vozidlo</button>` : ''}
          ${detail?.can_create_work_order ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal(); window.serviceShell.openCreateWorkOrderModal({ ownerId: ${id} })">Nová zakázka</button>` : ''}
          ${detail?.can_send_invite && !detail?.can_link ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.sendInvitationFromSearch()">Odeslat pozvánku</button>` : ''}
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zavřít</button>
        </div>
      `,
    });
  }

  function openVehicleDetailModal(vehicleId) {
    const id = Number(vehicleId || 0);
    if (!id) return;
    openDetailModal({
      entityType: 'vehicle',
      entityId: id,
      load: async () => {
        const [detail, records, quotes, timelinePayload] = await Promise.all([
          window.apiCall(`/api/v1/services/workspace/vehicles/${id}/detail`, 'GET'),
          window.apiCall(`/api/v1/vehicles/${id}/records`, 'GET').catch(() => []),
          window.apiCall(`/api/service/vehicles/${id}/quotes`, 'GET').catch(() => ({ items: [] })),
          window.apiCall(`/api/v1/vehicles/${id}/timeline`, 'GET').catch(() => ({ items: [] })),
        ]);
        state.vehicleTimelineCache[id] = Array.isArray(timelinePayload?.items) ? timelinePayload.items : [];
        state.vehicleTimelineVehicleId = id;
        setActiveVehicle(detail);
        render();
        return {
          ...detail,
          service_records: Array.isArray(records) ? records : [],
          service_quotes: Array.isArray(quotes?.items) ? quotes.items : [],
        };
      },
      kicker: `Vozidlo #${id}`,
      title: 'Detail vozidla',
      description: 'Schválený přístup, omezené zobrazení bez oprávnění a navazující servisní akce.',
      renderContent: (detail) => `
        ${renderDetailPills(detail)}
        ${renderBlockingReason(detail)}
        <div class="service-shell-modal-detail-grid cols-2">
          <div class="service-shell-side-card">
            <h3>Identita vozidla</h3>
            <div class="service-shell-list">
              <div class="service-shell-list-row"><span class="service-shell-list-title">Název</span><span class="service-shell-list-value">${escape(detail?.nickname || [detail?.brand, detail?.model].filter(Boolean).join(' ') || 'Vozidlo')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">SPZ</span><span class="service-shell-list-value">${escape(detail?.plate || detail?.plate_masked || '-')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">VIN</span><span class="service-shell-list-value">${escape(detail?.vin || detail?.vin_masked || '-')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Rok</span><span class="service-shell-list-value">${escape(String(detail?.year || '-'))}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Palivo</span><span class="service-shell-list-value">${escape(detail?.fuel || '-')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Motor</span><span class="service-shell-list-value">${escape(detail?.engine || '-')}</span></div>
            </div>
          </div>
          <div class="service-shell-side-card">
            <h3>Přístup a vazba</h3>
            <div class="service-shell-list">
              <div class="service-shell-list-row"><span class="service-shell-list-title">Přístup</span><span class="service-shell-list-value">${escape(accessStatusLabel(detail?.status))}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Zákazník</span><span class="service-shell-list-value">${escape(detail?.owner_name || (detail?.linked_customer ? 'Propojený zákazník' : 'Skrytý bez vazby'))}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Platnost STK</span><span class="service-shell-list-value">${escape(detail?.stk_valid_until ? formatDate(detail.stk_valid_until) : '-')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Aktuální km</span><span class="service-shell-list-value">${escape(detail?.current_mileage_km != null ? String(detail.current_mileage_km) : '-')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Datová důvěra</span><span class="service-shell-list-value">${escape(detail?.data_trust_state || '-')}</span></div>
            </div>
          </div>
        </div>
        <section class="service-shell-side-card">
          <div class="service-shell-card-head">
            <div>
              <h3>Servisní záznamy</h3>
              <p class="service-shell-subtitle">Pouze auditovatelná historie bez tichých přepisů.</p>
            </div>
            <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.openServiceRecordModal(${id})" aria-label="Nový servisní záznam">+</button>
          </div>
          <div class="service-shell-record-card-list">
            ${serviceRecordCards(detail?.service_records, id)}
          </div>
        </section>
        <section class="service-shell-side-card">
          <div class="service-shell-card-head">
            <div>
              <h3>Nabídky</h3>
              <p class="service-shell-subtitle">Zákaznické výstupy navázané na záznamy a zakázky.</p>
            </div>
            <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.openFirstRecordForQuote()" aria-label="Vytvořit nabídku">+</button>
          </div>
          <div class="service-shell-record-card-list service-shell-vehicle-quotes-wrap">
            ${vehicleQuotesSection(detail)}
          </div>
        </section>
        <section class="service-shell-side-card">
          <div class="service-shell-card-head">
            <div>
              <h3>Faktury</h3>
              <p class="service-shell-subtitle">Navazující vyúčtování k tomuto vozidlu.</p>
            </div>
            <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.openCreateInvoiceModal({ vehicleId: ${id}, customerId: ${Number(detail?.owner_customer_id || 0)} })" aria-label="Nová faktura">+</button>
          </div>
          <div class="service-shell-record-card-list service-shell-vehicle-quotes-wrap">
            ${vehicleInvoicesSection(id)}
          </div>
        </section>
        ${renderVehicleTimelineSection({ embedded: true, vehicleId: id })}
      `,
      renderFooter: (detail) => `
        <div class="service-shell-modal-footer">
          ${detail?.can_request_access ? accessRequestPrimaryButton(id, detail?.plate_masked || '') : ''}
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.openVehicleQrModal(${id})">Zobrazit QR</button>
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.openFirstRecordForQuote()">Vytvořit nabídku</button>
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.openServiceRecordModal(${id})">Nový záznam</button>
          ${detail?.can_create_work_order ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal(); window.serviceShell.openCreateWorkOrderModal({ ownerId: ${Number(detail?.owner_customer_id || 0)}, vehicleId: ${id} })">Nová zakázka</button>` : ''}
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zavřít</button>
        </div>
      `,
    });
  }

  function openDocumentDetailModal(documentId) {
    const id = Number(documentId || 0);
    if (!id) return;
    openDetailModal({
      entityType: 'document',
      entityId: id,
      endpoint: `/api/v1/services/workspace/documents/${id}/detail`,
      kicker: `Doklad #${id}`,
      title: 'Detail dokumentu',
      description: 'Výsledek extrakce, validace a návazné akce v jednotném servisním rozhraní.',
      renderContent: (detail) => {
        const items = Array.isArray(detail?.parsed_data?.items) ? detail.parsed_data.items : [];
        return `
          ${renderDetailPills(detail)}
          ${renderBlockingReason(detail)}
          <div class="service-shell-modal-detail-grid cols-2">
            <div class="service-shell-side-card">
              <h3>Doklad</h3>
              <div class="service-shell-list">
                <div class="service-shell-list-row"><span class="service-shell-list-title">Číslo</span><span class="service-shell-list-value">${escape(detail?.document_number || detail?.original_filename || '-')}</span></div>
                <div class="service-shell-list-row"><span class="service-shell-list-title">Dodavatel</span><span class="service-shell-list-value">${escape(detail?.supplier_name || '-')}</span></div>
                <div class="service-shell-list-row"><span class="service-shell-list-title">Zákazník</span><span class="service-shell-list-value">${escape(detail?.customer_name || detail?.customer_email_masked || '-')}</span></div>
                <div class="service-shell-list-row"><span class="service-shell-list-title">Vozidlo</span><span class="service-shell-list-value">${escape(detail?.vehicle_label || '-')}</span></div>
                <div class="service-shell-list-row"><span class="service-shell-list-title">Celkem</span><span class="service-shell-list-value">${escape(formatMoney(detail?.total_with_vat, detail?.currency))}</span></div>
              </div>
            </div>
            <div class="service-shell-side-card">
              <h3>Extrakce</h3>
              <div class="service-shell-list">
                <div class="service-shell-list-row"><span class="service-shell-list-title">Stav</span><span class="service-shell-list-value">${escape(accessStatusLabel(detail?.status))}</span></div>
                <div class="service-shell-list-row"><span class="service-shell-list-title">Confidence</span><span class="service-shell-list-value">${escape(detail?.parse_confidence != null ? String(detail.parse_confidence) : '-')}</span></div>
                <div class="service-shell-list-row"><span class="service-shell-list-title">Vloženo</span><span class="service-shell-list-value">${escape(detail?.created_at ? formatDateTime(detail.created_at) : '-')}</span></div>
                <div class="service-shell-list-row"><span class="service-shell-list-title">Zdroj</span><span class="service-shell-list-value">${escape(detail?.source_type || '-')}</span></div>
              </div>
            </div>
          </div>
          ${detail?.extracted_text_preview ? `<section class="service-shell-side-card"><h3>Náhled textu</h3><div class="service-shell-empty service-shell-modal-audit">${escape(detail.extracted_text_preview)}</div></section>` : ''}
          <section class="service-shell-side-card">
            <h3>Položky</h3>
            <div class="service-shell-list">
              ${items.length ? items.map((item) => `
                <div class="service-shell-list-row">
                  <div>
                    <p class="service-shell-list-title">${escape(item?.name || 'Položka')}</p>
                    <p class="service-shell-list-note">${escape(String(item?.quantity || '-'))} ${escape(item?.unit || '')}</p>
                  </div>
                  <div class="service-shell-list-value">${escape(formatMoney(item?.total_price, detail?.currency))}</div>
                </div>
              `).join('') : '<div class="service-shell-empty">Bez strukturovaných položek.</div>'}
            </div>
          </section>
        `;
      },
      renderFooter: (detail) => `
        <div class="service-shell-modal-footer">
          ${detail?.can_request_access ? accessRequestPrimaryButton(detail?.vehicle_id, detail?.vehicle_plate_masked || '') : ''}
          ${detail?.can_create_work_order ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal(); window.serviceShell.openCreateWorkOrderModal({ ownerId: ${Number(detail?.customer_id || 0)}, vehicleId: ${Number(detail?.vehicle_id || 0)} })">Nová zakázka</button>` : ''}
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zavřít</button>
        </div>
      `,
    });
  }

  function openReservationDetailModal(reservationId) {
    const id = Number(reservationId || 0);
    if (!id) return;
    openDetailModal({
      entityType: 'reservation',
      entityId: id,
      endpoint: `/api/v1/services/workspace/reservations/${id}/detail`,
      kicker: `Rezervace #${id}`,
      title: 'Detail rezervace',
      description: 'Shell-native detail rezervace s možností úpravy a návaznou zakázkou.',
      actions: {
        save: async () => {
          const detail = state.modal?.data || {};
          if (!detail?.can_edit) {
            throw new Error(detail?.blocking_reason || 'Rezervaci teď nelze upravit.');
          }
          await window.apiCall(`/api/v1/reservations/${id}`, 'PUT', {
            service_type: String(document.getElementById('serviceShellReservationType')?.value || '').trim() || null,
            note: String(document.getElementById('serviceShellReservationNote')?.value || '').trim() || null,
            start_datetime: fromDateTimeInputValue(document.getElementById('serviceShellReservationStart')?.value),
            end_datetime: fromDateTimeInputValue(document.getElementById('serviceShellReservationEnd')?.value),
            status: String(document.getElementById('serviceShellReservationStatus')?.value || detail?.status || 'PENDING').trim(),
          });
          return {
            close: true,
            refreshParent: true,
            message: 'Rezervace byla aktualizována.',
          };
        },
      },
      renderContent: (detail) => `
        ${renderDetailPills(detail)}
        ${renderBlockingReason(detail)}
        <div class="service-shell-modal-summary">
          <span>${escape(detail?.customer_name || detail?.customer_email_masked || '-')}</span>
          <span>${escape(detail?.vehicle_name || detail?.vehicle_plate_masked || '-')}</span>
        </div>
        <form class="service-dashboard-modal-form" onsubmit="event.preventDefault(); window.serviceShell.runModalAction('save');">
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellReservationType">Typ rezervace</label>
              <input type="text" id="serviceShellReservationType" value="${escape(detail?.service_type || '')}" ${detail?.can_edit ? '' : 'disabled'}>
            </div>
            <div class="form-group">
              <label for="serviceShellReservationStatus">Stav</label>
              <select id="serviceShellReservationStatus" ${detail?.can_edit ? '' : 'disabled'}>
                <option value="PENDING" ${String(detail?.status || '').toUpperCase() === 'PENDING' ? 'selected' : ''}>Čeká</option>
                <option value="CONFIRMED" ${String(detail?.status || '').toUpperCase() === 'CONFIRMED' ? 'selected' : ''}>Potvrzeno</option>
                <option value="CANCELLED" ${String(detail?.status || '').toUpperCase() === 'CANCELLED' ? 'selected' : ''}>Zrušeno</option>
              </select>
            </div>
          </div>
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellReservationStart">Začátek</label>
              <input type="datetime-local" id="serviceShellReservationStart" value="${escape(toDateTimeInputValue(detail?.start_datetime))}" ${detail?.can_edit ? '' : 'disabled'}>
            </div>
            <div class="form-group">
              <label for="serviceShellReservationEnd">Konec</label>
              <input type="datetime-local" id="serviceShellReservationEnd" value="${escape(toDateTimeInputValue(detail?.end_datetime))}" ${detail?.can_edit ? '' : 'disabled'}>
            </div>
          </div>
          <div class="form-group">
            <label for="serviceShellReservationNote">Poznámka</label>
            <textarea id="serviceShellReservationNote" rows="4" ${detail?.can_edit ? '' : 'disabled'}>${escape(detail?.note || '')}</textarea>
          </div>
        </form>
      `,
      renderFooter: (detail, modal) => `
        <div class="service-shell-modal-footer">
          ${Number(detail?.customer_id || 0) > 0 ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.openCustomerDetailModal(${Number(detail.customer_id)})">Zákazník</button>` : ''}
          ${Number(detail?.vehicle_id || 0) > 0 ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.openVehicleDetailModal(${Number(detail.vehicle_id)})">Vozidlo</button>` : ''}
          ${detail?.can_request_access ? accessRequestPrimaryButton(detail?.vehicle_id, detail?.vehicle_plate_masked || '') : ''}
          ${detail?.can_edit && reservationStatusKey(detail?.status) === 'CONFIRMED' ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.updateReservationStatus(${id}, 'COMPLETED', 'Rezervace byla označena jako dokončená.')">Dokončeno</button>` : ''}
          ${detail?.can_edit && reservationStatusKey(detail?.status) !== 'CANCELLED' && reservationStatusKey(detail?.status) !== 'COMPLETED' ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.updateReservationStatus(${id}, 'CANCELLED', 'Rezervace byla zrušena.')">Zrušit</button>` : ''}
          ${detail?.can_create_work_order ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal(); window.serviceShell.openCreateWorkOrderModal({ ownerId: ${Number(detail?.customer_id || 0)}, vehicleId: ${Number(detail?.vehicle_id || 0)} })">Nová zakázka</button>` : ''}
          ${reservationStatusKey(detail?.status) === 'CANCELLED' || reservationStatusKey(detail?.status) === 'COMPLETED' ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.deleteReservation(${id})">Smazat</button>` : ''}
          ${detail?.can_edit ? `<button type="button" class="btn btn-primary" onclick="window.serviceShell.runModalAction('save')">${modal.saving ? 'Ukládám…' : 'Uložit změny'}</button>` : ''}
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zavřít</button>
        </div>
      `,
    });
  }

  function openReminderDetailModal(reminderId) {
    const id = Number(reminderId || 0);
    if (!id) return;
    openDetailModal({
      entityType: 'reminder',
      entityId: id,
      endpoint: `/api/v1/services/workspace/reminders/${id}/detail`,
      kicker: `Připomínka #${id}`,
      title: 'Detail připomínky',
      description: 'Follow-up servisního týmu, stav dokončení a navazující akce.',
      actions: {
        save: async () => {
          const detail = state.modal?.data || {};
          if (!detail?.can_edit) {
            throw new Error(detail?.blocking_reason || 'Připomínku teď nelze upravit.');
          }
          await window.apiCall(`/api/v1/services/workspace/reminders/${id}`, 'PUT', {
            type: String(document.getElementById('serviceShellReminderType')?.value || detail?.type || 'SERVIS').trim(),
            text: String(document.getElementById('serviceShellReminderText')?.value || '').trim(),
            due_date: String(document.getElementById('serviceShellReminderDueDate')?.value || '').trim() || null,
            notify_at: fromDateTimeInputValue(document.getElementById('serviceShellReminderNotifyAt')?.value),
            notification_method: String(document.getElementById('serviceShellReminderMethod')?.value || '').trim() || null,
            is_completed: String(document.getElementById('serviceShellReminderCompleted')?.value || 'false') === 'true',
          });
          return {
            close: true,
            refreshParent: true,
            message: 'Připomínka byla aktualizována.',
          };
        },
      },
      renderContent: (detail) => `
        ${renderDetailPills(detail)}
        ${renderBlockingReason(detail)}
        <form class="service-dashboard-modal-form" onsubmit="event.preventDefault(); window.serviceShell.runModalAction('save');">
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellReminderType">Typ</label>
              <input type="text" id="serviceShellReminderType" value="${escape(detail?.type || 'SERVIS')}" ${detail?.can_edit ? '' : 'disabled'}>
            </div>
            <div class="form-group">
              <label for="serviceShellReminderCompleted">Stav</label>
              <select id="serviceShellReminderCompleted" ${detail?.can_edit ? '' : 'disabled'}>
                <option value="false" ${detail?.is_completed ? '' : 'selected'}>Aktivní</option>
                <option value="true" ${detail?.is_completed ? 'selected' : ''}>Dokončeno</option>
              </select>
            </div>
          </div>
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellReminderDueDate">Termín</label>
              <input type="date" id="serviceShellReminderDueDate" value="${escape(String(detail?.due_date || '').slice(0, 10))}" ${detail?.can_edit ? '' : 'disabled'}>
            </div>
            <div class="form-group">
              <label for="serviceShellReminderNotifyAt">Notifikovat</label>
              <input type="datetime-local" id="serviceShellReminderNotifyAt" value="${escape(toDateTimeInputValue(detail?.notify_at))}" ${detail?.can_edit ? '' : 'disabled'}>
            </div>
          </div>
          <div class="form-group">
            <label for="serviceShellReminderMethod">Kanál</label>
            <select id="serviceShellReminderMethod" ${detail?.can_edit ? '' : 'disabled'}>
              <option value="" ${!detail?.notification_method ? 'selected' : ''}>Výchozí</option>
              <option value="app" ${detail?.notification_method === 'app' ? 'selected' : ''}>Aplikace</option>
              <option value="email" ${detail?.notification_method === 'email' ? 'selected' : ''}>E-mail</option>
              <option value="both" ${detail?.notification_method === 'both' ? 'selected' : ''}>Obojí</option>
            </select>
          </div>
          <div class="form-group">
            <label for="serviceShellReminderText">Text</label>
            <textarea id="serviceShellReminderText" rows="4" ${detail?.can_edit ? '' : 'disabled'}>${escape(detail?.text || '')}</textarea>
          </div>
        </form>
      `,
      renderFooter: (detail, modal) => `
        <div class="service-shell-modal-footer">
          ${Number(detail?.customer_id || 0) > 0 ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.openCustomerDetailModal(${Number(detail.customer_id)})">Zákazník</button>` : ''}
          ${Number(detail?.vehicle_id || 0) > 0 ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.openVehicleDetailModal(${Number(detail.vehicle_id)})">Vozidlo</button>` : ''}
          ${detail?.can_request_access ? accessRequestPrimaryButton(detail?.vehicle_id, detail?.vehicle_plate_masked || '') : ''}
          ${detail?.can_edit ? `<button type="button" class="btn btn-primary" onclick="window.serviceShell.runModalAction('save')">${modal.saving ? 'Ukládám…' : 'Uložit změny'}</button>` : ''}
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zavřít</button>
        </div>
      `,
    });
  }

  function filteredWorkOrders() {
    const query = String(state.searchTerm ?? '').trim().toLowerCase();
    const today = todayKey();
    let items = Array.isArray(state.workOrders) ? [...state.workOrders] : [];

    if (state.kpiFilter === 'active') {
      items = items.filter((item) => ['in_progress', 'approved'].includes(String(item?.status || '').toLowerCase()));
    } else if (state.kpiFilter === 'awaiting') {
      items = items.filter((item) => String(item?.status || '').toLowerCase() === 'awaiting_client_approval');
    } else if (state.kpiFilter === 'today') {
      items = items.filter((item) => toDateKey(item?.due_date) === today);
    } else if (state.kpiFilter === 'overdue') {
      items = items.filter((item) => {
        const due = toDateKey(item?.due_date);
        return due && due < today && String(item?.status || '').toLowerCase() !== 'completed';
      });
    }

    if (query) {
      items = items.filter((item) => {
        const haystack = [
          item?.customer_name,
          item?.vehicle_vin,
          item?.vehicle_spz,
          item?.source_type,
          item?.source_label,
          item?.technician_name,
          item?.title,
        ].join(' ').toLowerCase();
        return haystack.includes(query);
      });
    }

    if (state.sortBy === 'due_desc') {
      items.sort((a, b) => String(b?.due_date || '').localeCompare(String(a?.due_date || '')));
    } else if (state.sortBy === 'customer') {
      items.sort((a, b) => String(a?.customer_name || '').localeCompare(String(b?.customer_name || ''), 'cs'));
    } else if (state.sortBy === 'status') {
      items.sort((a, b) => String(a?.status || '').localeCompare(String(b?.status || ''), 'cs'));
    } else {
      items.sort((a, b) => String(a?.due_date || '').localeCompare(String(b?.due_date || '')));
    }

    return items;
  }

  function dashboardSummary() {
    const summary = state.summary || {};
    const reservations = Array.isArray(state.reservations) ? state.reservations : [];
    const reminders = Array.isArray(state.reminders) ? state.reminders : [];
    const invoices = Array.isArray(state.invoices) ? state.invoices : [];
    return {
      active_jobs: Number(summary.active_jobs || 0),
      awaiting_approval: Number(summary.awaiting_approval || 0),
      due_today: Number(summary.due_today || 0),
      overdue: Number(summary.overdue || 0),
      new_reservations: Number(summary.new_reservations || reservations.filter((item) => String(item?.status || '').toUpperCase() === 'PENDING').length),
      today_reservations: Number(summary.today_reservations || reservations.filter((item) => toDateKey(item?.scheduled_for || item?.reservation_date || item?.starts_at) === todayKey()).length),
      pending_quotes: Number(summary.pending_quotes || 0),
      draft_invoices: Number(summary.draft_invoices || invoices.filter((item) => String(item?.status || '').toLowerCase() === 'draft').length),
      invoices_total: Number(summary.invoices_total || invoices.length),
      open_reminders: Number(summary.open_reminders || reminders.filter((item) => !item?.is_completed).length),
      overdue_reminders: Number(summary.overdue_reminders || reminders.filter((item) => reminderIsOverdueAttention(item)).length),
    };
  }

  function dashboardOpsStats() {
    const summary = dashboardSummary();
    return `
      <div class="service-shell-metrics-ticker">
        <div class="service-shell-metric">
          <span class="service-shell-metric-label">Nové rezervace</span>
          <strong class="service-shell-metric-value">${summary.new_reservations}</strong>
        </div>
        <div class="service-shell-metric">
          <span class="service-shell-metric-label">Čekající nabídky</span>
          <strong class="service-shell-metric-value">${summary.pending_quotes}</strong>
        </div>
        <div class="service-shell-metric">
          <span class="service-shell-metric-label">Draft faktury</span>
          <strong class="service-shell-metric-value">${summary.draft_invoices}</strong>
        </div>
        <div class="service-shell-metric">
          <span class="service-shell-metric-label">Aktivní připomínky</span>
          <strong class="service-shell-metric-value">${summary.open_reminders}</strong>
        </div>
      </div>
    `;
  }

  function dashboardQuickActions() {
    return `
      <section class="service-pro-card service-shell-dashboard-actions">
        <div class="service-shell-card-head">
          <div>
            <h3>Rychlé akce</h3>
            <p class="service-shell-subtitle">Nejčastější servisní kroky bez zbytečného hledání.</p>
          </div>
        </div>
        <div class="service-shell-list">
          <div class="service-shell-list-row service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.openServiceToolsModal()" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.openServiceToolsModal() }"><span class="service-shell-list-title">Najít zákazníka nebo vozidlo</span><span class="service-shell-list-value">⌘</span></div>
          <div class="service-shell-list-row service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.openCreateWorkOrderModal()" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.openCreateWorkOrderModal() }"><span class="service-shell-list-title">Nová zakázka</span><span class="service-shell-list-value">+</span></div>
          <div class="service-shell-list-row service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.navigate('reservations')" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.navigate('reservations') }"><span class="service-shell-list-title">Otevřít příchozí rezervace</span><span class="service-shell-list-value">→</span></div>
          <div class="service-shell-list-row service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.setKpiFilter('awaiting')" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.setKpiFilter('awaiting') }"><span class="service-shell-list-title">Čeká na schválení</span><span class="service-shell-list-value">!</span></div>
        </div>
      </section>
    `;
  }

  function workspaceModeSwitchShellHtml() {
    return `
      <div class="workspace-mode-switch workspace-mode-switch--service-toolbar hidden" role="group" aria-label="Přepnout režim rozhraní" data-testid="workspace-mode-switch-service-toolbar">
        <button type="button" class="workspace-mode-switch-btn" data-workspace-mode="user" title="Rozhraní pro vlastní vozidla a osobní účet" onclick="void switchWorkspaceUIMode('user')">Účet</button>
        <button type="button" class="workspace-mode-switch-btn" data-workspace-mode="service" title="Rozhraní servisu (zákazníci, workspace)" onclick="void switchWorkspaceUIMode('service')">Servis</button>
      </div>
    `;
  }

  function serviceAccountName() {
    const me = state.me || {};
    const pp = state.partnerPublicProfile || {};
    return (
      me.display_name
      || pp.name
      || currentProfile()?.name
      || window.currentUser?.name
      || 'Autoservis Novák'
    );
  }

  function normalizePlate(value) {
    return String(value || '').toUpperCase().replace(/[^0-9A-Z]/g, '').replace(/^(.{3})(.+)$/, '$1 $2').slice(0, 12);
  }

  function normalizeVin(value) {
    return String(value || '').toUpperCase().replace(/[^A-HJ-NPR-Z0-9]/g, '').slice(0, 17);
  }

  function maskVin(vin) {
    const raw = String(vin || '').trim();
    if (!raw) return '-';
    return raw.length > 8 ? `${raw.slice(0, 3)}...${raw.slice(-4)}` : raw;
  }

  function serviceRoleLabel() {
    const raw = String(currentProfile()?.role || window.currentUser?.role || '').toLowerCase();
    if (raw.includes('lead') || raw.includes('manager')) return 'Vedoucí servisu';
    if (raw.includes('mechanic') || raw.includes('mechanik')) return 'Mechanik';
    if (raw.includes('service')) return 'Přijímací technik';
    return 'Servisní pracovník';
  }

  function dashboardOverview() {
    const overview = state.dashboardOverview || {};
    const summary = dashboardSummary();
    const reservations = Array.isArray(state.reservations) ? state.reservations : [];
    const invoices = Array.isArray(state.invoices) ? state.invoices : [];
    const issued = invoices.filter((item) => invoiceStatusKey(item?.status) === 'issued');
    return {
      today_vehicles: Number(overview.today_vehicles ?? summary.today_reservations ?? reservations.length ?? 0),
      waiting_intake: Number(overview.waiting_intake ?? summary.new_reservations ?? 0),
      open_work_orders: Number(overview.open_work_orders ?? state.workOrders.filter((item) => String(item?.status || '').toLowerCase() !== 'completed').length),
      in_progress_work_orders: Number(overview.in_progress_work_orders ?? summary.active_jobs ?? 0),
      waiting_approval: Number(overview.waiting_approval ?? summary.awaiting_approval ?? 0),
      monthly_invoice_total: Number(overview.monthly_invoice_total ?? issued.reduce((sum, item) => sum + Number(item?.total || 0), 0)),
      monthly_invoice_count: Number(overview.monthly_invoice_count ?? issued.length),
      currency: String(overview.currency || 'CZK'),
    };
  }

  function dashboardWorkOrderItems() {
    const items = Array.isArray(state.dashboardWorkOrders) && state.dashboardWorkOrders.length
      ? state.dashboardWorkOrders
      : filteredWorkOrders().slice(0, 8);
    return items;
  }

  function quickIntakeSet(field, value) {
    state.quickIntakeDraft = state.quickIntakeDraft || { checklist: {} };
    if (field === 'plate') state.quickIntakeDraft.plate = normalizePlate(value);
    else state.quickIntakeDraft[field] = String(value || '');
    render();
  }

  function quickIntakeChecklist(key, checked) {
    state.quickIntakeDraft = state.quickIntakeDraft || { checklist: {} };
    state.quickIntakeDraft.checklist = { ...(state.quickIntakeDraft.checklist || {}), [key]: Boolean(checked) };
    render();
  }

  function openIntakeFlow() {
    navigate('intake');
  }

  function openOcrPlaceholder() {
    openModal({
      key: 'ocr-unavailable',
      title: 'OCR není aktivní',
      description: 'Rozpoznání SPZ z fotky není v této instalaci backendově aktivní.',
      renderContent: () => '<div class="service-shell-empty">Fotka se neukládá a aplikace nevytváří žádný odhad SPZ. Použijte ruční zadání SPZ nebo VIN a pokračujte přes „Načíst vozidlo“.</div>',
      renderFooter: () => '<div class="service-shell-modal-footer"><button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zavřít</button></div>',
    });
  }

  function quickLoadVehicle() {
    const draft = state.quickIntakeDraft || {};
    const query = String(draft.vin || draft.plate || '').trim();
    if (!query) {
      showToast('Zadejte VIN nebo SPZ.', 'warning');
      return;
    }
    state.vehicleLookupQuery = query;
    openServiceToolsModal();
    window.setTimeout(() => {
      try {
        const input = document.querySelector('.service-shell-modal input[placeholder="VIN nebo SPZ"]');
        if (input) input.value = query;
        searchVehicles();
      } catch (err) {
        console.warn('[SERVICE_SHELL] quick vehicle lookup failed:', err);
      }
    }, 50);
  }

  function openWorkOrderFromQuickIntake() {
    const vehicleId = Number(state.activeVehicle?.vehicleId || 0);
    if (vehicleId) {
      openCreateWorkOrderModal({ vehicleId });
      return;
    }
    openCreateWorkOrderModal();
  }

  const INTAKE_LOOKUP_DEBOUNCE_MS = 400;

  function captureIntakeFocus() {
    const active = document.activeElement;
    if (!active || typeof active.getAttribute !== 'function') return null;
    const testId = active.getAttribute('data-testid');
    if (testId === 'service-intake-vin-input') {
      return { field: 'vin', start: active.selectionStart, end: active.selectionEnd };
    }
    if (testId === 'service-intake-plate-input') {
      return { field: 'plate', start: active.selectionStart, end: active.selectionEnd };
    }
    return null;
  }

  function restoreIntakeFocus(snapshot) {
    const field = snapshot?.field || state._intakeFocusField;
    if (!field) return;
    const testId = field === 'vin' ? 'service-intake-vin-input' : 'service-intake-plate-input';
    const el = document.querySelector(`[data-testid="${testId}"]`);
    if (!el || typeof el.focus !== 'function') return;
    el.focus();
    const start = typeof snapshot?.start === 'number' ? snapshot.start : Number(state._intakeCaretPos || 0);
    const end = typeof snapshot?.end === 'number' ? snapshot.end : start;
    if (typeof el.setSelectionRange === 'function') {
      try {
        el.setSelectionRange(start, end);
      } catch (err) {
        /* ignore */
      }
    }
  }

  function preserveIntakeFocus(fn) {
    const snap = captureIntakeFocus();
    fn();
    restoreIntakeFocus(snap);
  }

  function intakeHasLookupQuery() {
    const vin = normalizeVin(state.intakeDraft?.vin || '');
    const plate = String(normalizePlate(state.intakeDraft?.plate || '')).replace(/\s/g, '');
    return (vin.length >= 11) || (plate.length >= 3);
  }

  function cancelIntakeLookupDebounce() {
    window.clearTimeout(state._intakeLookupTimer);
    state._intakeLookupTimer = null;
  }

  function scheduleIntakeLookupDebounced() {
    cancelIntakeLookupDebounce();
    state._intakeLookupTimer = window.setTimeout(() => {
      state._intakeLookupTimer = null;
      if (state.activeSection === 'intake' && intakeHasLookupQuery()) {
        lookupVehicleForIntake({ debounced: true });
      }
    }, INTAKE_LOOKUP_DEBOUNCE_MS);
  }

  function intakeUiRefresh() {
    if (state.activeSection === 'intake' && state.mounted) {
      preserveIntakeFocus(() => patchIntakeUi());
      return;
    }
    render();
  }

  function refreshShellAfterDataLoad(silent, options = {}) {
    const backgroundOnly = Boolean(options.backgroundOnly);
    if (state.activeSection === 'intake' && state.mounted && (silent || backgroundOnly)) {
      intakeUiRefresh();
      return;
    }
    render();
  }

  function getIntakeUiContext() {
    const draft = state.intakeDraft || {};
    const response = state.intakeLookupResponse || null;
    const preview = response?.vehicle_preview || null;
    const access = response?.access || {};
    const legacy = state.intakeLookupLegacyCandidate || {};
    const vehicleId = Number(preview?.vehicle_id || legacy?.vehicle_id || 0);
    const ownerId = Number(legacy?.owner_customer_id || 0);
    const accessStatus = String(access.status || '').toLowerCase();
    const lookupStatus = String(response?.status || '').toLowerCase();
    const canCreateUnowned = response?.found === false && response?.status === 'not_found';
    const canRequestAccess = Boolean(preview?.vehicle_id && access?.can_request_access);
    const canWorkWithoutOwner = accessStatus === 'work_access'
      || lookupStatus === 'found_service_unowned'
      || Boolean(response?.can_create_work_order);
    const canWorkAccess = canWorkWithoutOwner;
    const canCreateWorkAccess = Boolean(preview?.vehicle_id) && !['approved', 'work_access'].includes(accessStatus);
    const showWorkAccess = canCreateWorkAccess;
    const showRequestAccess = canRequestAccess;
    const canCreateWorkOrder = Boolean(vehicleId) && (Boolean(ownerId) || canWorkWithoutOwner || accessStatus === 'approved');
    const canStart = accessStatus === 'approved' || canWorkAccess;
    const hasLookup = Boolean(response || state.intakeLookupError || state.intakeLookupLoading);
    const badgeTone = accessStatus === 'approved'
      ? 'success'
      : accessStatus === 'work_access'
        ? 'success'
        : accessStatus === 'pending'
          ? 'pending'
          : ['rejected', 'revoked'].includes(accessStatus)
            ? 'danger'
            : 'warning';
    const badgeLabel = accessStatus === 'approved'
      ? 'Propojeno s majitelem'
      : accessStatus === 'work_access'
        ? 'Jednorázový servisní zásah'
        : accessStatus === 'pending'
          ? 'Čeká na schválení majitele'
          : ['rejected', 'revoked'].includes(accessStatus)
            ? 'Zamítnuto — dostupný pouze vlastní zásah'
            : 'Přístup vyžaduje rozhodnutí';
    return {
      draft,
      response,
      preview,
      access,
      accessStatus,
      lookupStatus,
      vehicleId,
      ownerId,
      canCreateUnowned,
      canRequestAccess,
      canWorkAccess,
      canWorkWithoutOwner,
      canCreateWorkAccess,
      showWorkAccess,
      showRequestAccess,
      canCreateWorkOrder,
      canStart,
      hasLookup,
      badgeTone,
      badgeLabel,
    };
  }

  function renderIntakeLookupErrorHtml() {
    return state.intakeLookupError
      ? `<div class="service-shell-inline-error" data-testid="service-intake-error">${escape(state.intakeLookupError)}</div>`
      : '';
  }

  function renderIntakeResultPanelHtml(ctx) {
    const { draft, response, preview, lookupStatus, canCreateUnowned, hasLookup } = ctx;
    return `
      <h3>Výsledek lookupu</h3>
      ${!hasLookup ? '<p data-testid="service-intake-empty">Zatím není načtený žádný výsledek.</p>' : ''}
      ${response?.status === 'not_found' ? `
        <p data-testid="service-intake-not-found-message">Vozidlo nebylo nalezeno v databázi.</p>
        <p class="service-shell-muted">Zadané údaje: ${escape(draft.plate || '-')} ${draft.vin ? `• VIN ${escape(draft.vin)}` : ''}</p>
        ${!state.intakeCreateFormOpen ? `<button type="button" class="service-shell-primary-btn" data-testid="service-intake-add-vehicle-button" onclick="window.serviceShell.openIntakeCreateVehicleForm()">Přidat nové vozidlo</button>` : ''}
      ` : ''}
      ${preview ? `<div data-testid="service-intake-safe-preview"><p><strong>${escape([preview.brand, preview.model].filter(Boolean).join(' ') || 'Vozidlo')}</strong> ${preview.year ? `(${escape(String(preview.year))})` : ''}</p><p>VIN: ${escape(preview.vin_masked || '-')} • SPZ: ${escape(preview.plate_masked || '-')}</p></div>` : ''}
      ${lookupStatus === 'conflict' ? '<p>SPZ může patřit k existujícímu vozidlu, ale bez VIN nelze bezpečně sloučit. Doplňte VIN a opakujte lookup.</p>' : ''}
      ${canCreateUnowned && !state.intakeCreateFormOpen ? '<p class="service-shell-muted">Vozidlo bude evidováno bez majitele. Majitel jej může později ověřit a převzít.</p>' : ''}
    `;
  }

  function renderIntakeAccessPanelHtml(ctx) {
    const {
      accessStatus,
      showRequestAccess,
      showWorkAccess,
      canWorkAccess,
      preview,
      badgeLabel,
      badgeTone,
    } = ctx;
    const accessScenarioTestId = accessStatus === 'work_access'
      ? 'service-intake-access-work-access'
      : accessStatus === 'pending'
        ? 'service-intake-access-pending'
        : ['rejected', 'revoked'].includes(accessStatus)
          ? 'service-intake-access-rejected'
          : 'service-intake-access-not-requested';
    return `
      <div class="service-intake-access-panel" data-testid="${accessScenarioTestId}">
        <h3>Stav přístupu</h3>
        <p>${ServiceStatusBadge(badgeLabel, badgeTone)}</p>
        ${accessStatus === 'approved' ? '<p>Detail vozidla je dostupný v rozsahu schváleného propojení.</p>' : ''}
        ${canWorkAccess ? '<p>Servis může vytvořit vlastní zakázku a záznam bez přístupu k soukromým datům majitele.</p>' : ''}
        ${accessStatus === 'pending' ? '<p>Propojení čeká na vyjádření majitele. Vlastní jednorázový zásah je možné vést odděleně.</p>' : ''}
        ${['rejected', 'revoked'].includes(accessStatus) ? '<p>Dlouhodobé propojení bylo zamítnuto nebo odebráno. Vlastní zásah zůstává oddělený.</p>' : ''}
        <div class="service-action-bar">
          ${showWorkAccess ? `<button type="button" class="service-shell-primary-btn" data-testid="service-intake-work-access-button" ${state.intakeMutationLoading ? 'disabled' : ''} onclick="window.serviceShell.createWorkAccessFromIntake()">${state.intakeMutationLoading ? 'Ukládám…' : 'Pracovat bez propojení'}</button>` : ''}
          ${showRequestAccess ? `<button type="button" class="btn btn-secondary" data-testid="service-intake-request-access-button" ${state.intakeMutationLoading ? 'disabled' : ''} onclick="window.serviceShell.requestVehicleAccessFromIntake()">${state.intakeMutationLoading ? 'Odesílám…' : 'Vyžádat propojení s majitelem'}</button>` : ''}
          ${preview?.vehicle_id && (canWorkAccess || accessStatus === 'approved') ? `<button type="button" class="btn btn-secondary" data-testid="service-intake-safe-history-button" ${state.intakeMutationLoading ? 'disabled' : ''} onclick="window.serviceShell.loadSafeHistoryFromIntake()">Zobrazit bezpečnou historii</button>` : ''}
        </div>
      </div>
    `;
  }

  function renderIntakeFuelOptions(selected) {
    const options = ['', 'Benzín', 'Nafta', 'LPG', 'CNG', 'Elektro', 'Hybrid', 'Jiné'];
    return options.map((opt) => {
      const val = opt || '';
      const label = opt || '— vyberte —';
      return `<option value="${escape(val)}" ${String(selected || '') === val ? 'selected' : ''}>${escape(label)}</option>`;
    }).join('');
  }

  function renderIntakeCreateVehiclePanelHtml(ctx) {
    if (!state.intakeCreateFormOpen || !ctx.canCreateUnowned) return '';
    const draft = ctx.draft;
    return `
      <article class="service-pro-card service-intake-create-panel" data-testid="service-intake-create-vehicle-panel">
        <h3>Nové vozidlo</h3>
        <p class="service-shell-muted">Vozidlo bude uloženo jako nepřiřazené (service_provisioned_unowned) bez vlastnické vazby.</p>
        <div class="service-intake-create-grid">
          <label>SPZ (předvyplněno)
            <input class="service-shell-search service-intake-readonly-field" data-testid="service-intake-create-plate" readonly value="${escape(draft.plate || '')}">
          </label>
          <label>VIN (předvyplněno)
            <input class="service-shell-search service-intake-readonly-field" data-testid="service-intake-create-vin" readonly value="${escape(draft.vin || '')}">
          </label>
          <label>Značka *
            <input class="service-shell-search" data-testid="service-intake-create-brand" value="${escape(draft.brand || '')}" oninput="window.serviceShell.setIntakeDraftField('brand', this.value)" placeholder="např. Škoda">
          </label>
          <label>Model *
            <input class="service-shell-search" data-testid="service-intake-create-model" value="${escape(draft.model || '')}" oninput="window.serviceShell.setIntakeDraftField('model', this.value)" placeholder="např. Octavia">
          </label>
          <label>Rok
            <input class="service-shell-search" type="number" min="1900" max="2100" data-testid="service-intake-create-year" value="${escape(String(draft.year || ''))}" oninput="window.serviceShell.setIntakeDraftField('year', this.value)" placeholder="např. 2020">
          </label>
          <label>Palivo
            <select class="service-shell-search" data-testid="service-intake-create-fuel" onchange="window.serviceShell.setIntakeDraftField('fuel', this.value)">${renderIntakeFuelOptions(draft.fuel)}</select>
          </label>
          <label class="service-intake-create-note">Poznámka
            <textarea class="service-shell-search" rows="3" data-testid="service-intake-create-note" oninput="window.serviceShell.setIntakeDraftField('vehicleNote', this.value)">${escape(draft.vehicleNote || '')}</textarea>
          </label>
        </div>
        <div class="service-action-bar">
          <button type="button" class="service-shell-primary-btn" data-testid="service-intake-save-vehicle-button" ${state.intakeMutationLoading ? 'disabled' : ''} onclick="window.serviceShell.createUnownedVehicleFromIntake()">${state.intakeMutationLoading ? 'Ukládám…' : 'Uložit vozidlo'}</button>
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeIntakeCreateVehicleForm()">Zrušit</button>
        </div>
      </article>
    `;
  }

  function renderIntakeWorkflowActionsHtml(ctx) {
    const { canStart, canCreateWorkOrder, accessStatus } = ctx;
    const woDisabled = !canCreateWorkOrder || state.intakeMutationLoading;
    const woTitle = woDisabled && !state.intakeMutationLoading
      ? (accessStatus === 'pending'
        ? 'Nejdřív založte jednorázový servisní zásah — propojení čeká na majitele.'
        : ['rejected', 'revoked'].includes(accessStatus)
          ? 'Nejdřív založte jednorázový servisní zásah — dlouhodobé propojení bylo zamítnuto.'
          : 'Nejdřív založte jednorázový servisní zásah nebo vyžádejte propojení s majitelem.')
      : '';
    return `
      <button type="button" class="service-shell-primary-btn" data-testid="service-intake-start-button" ${!canStart || state.intakeMutationLoading ? 'disabled' : ''} onclick="window.serviceShell.startServiceIntake()">${state.intakeMutationLoading ? 'Ukládám…' : 'Zahájit příjem'}</button>
      <button type="button" class="btn btn-secondary" data-testid="service-intake-create-work-order-button" ${woDisabled ? 'disabled' : ''} title="${escape(woTitle)}" onclick="window.serviceShell.createWorkOrderFromIntake()">Vytvořit zakázku</button>
    `;
  }

  function renderIntakeLimitedNoticeHtml() {
    const historyItems = Array.isArray(state.intakeSafeHistory?.items) ? state.intakeSafeHistory.items : [];
    const historyHtml = historyItems.length
      ? `<div class="service-shell-list">${historyItems.slice(0, 5).map((item) => `<div class="service-shell-list-item"><strong>${escape(item.description || item.category || 'Servisní záznam')}</strong><small>${escape([item.performed_at ? formatDate(item.performed_at) : '', item.mileage ? `${item.mileage} km` : '', item.own_record ? 'vlastní záznam' : 'anonymizováno'].filter(Boolean).join(' · '))}</small></div>`).join('')}</div>`
      : '';
    return state.intakeLimitedNotice
      ? `<article class="service-pro-card service-pro-card--muted" data-intake-patch="limited-notice"><p>${escape(state.intakeLimitedNotice)}</p>${historyHtml}</article>`
      : '<article class="service-pro-card service-pro-card--muted hidden" data-intake-patch="limited-notice" aria-hidden="true"></article>';
  }

  function patchIntakeLookupButtonOnly() {
    const lookupBtn = document.querySelector('[data-testid="service-intake-lookup-button"]');
    if (lookupBtn) {
      lookupBtn.disabled = Boolean(state.intakeLookupLoading);
      lookupBtn.textContent = state.intakeLookupLoading ? 'Načítám…' : 'Načíst vozidlo';
    }
  }

  function patchIntakeUi() {
    if (state.activeSection !== 'intake') return;
    const ctx = getIntakeUiContext();
    const lookupBtn = document.querySelector('[data-testid="service-intake-lookup-button"]');
    if (lookupBtn) {
      lookupBtn.disabled = Boolean(state.intakeLookupLoading);
      lookupBtn.textContent = state.intakeLookupLoading ? 'Načítám…' : 'Načíst vozidlo';
    }
    const errHost = document.querySelector('[data-intake-patch="lookup-error"]');
    if (errHost) errHost.innerHTML = renderIntakeLookupErrorHtml();
    const result = document.querySelector('[data-testid="service-intake-result"]');
    if (result) result.innerHTML = renderIntakeResultPanelHtml(ctx);
    const access = document.querySelector('[data-testid="service-intake-access-state"]');
    if (access) access.innerHTML = renderIntakeAccessPanelHtml(ctx);
    const createHost = document.querySelector('[data-intake-patch="create-vehicle"]');
    if (createHost) createHost.innerHTML = renderIntakeCreateVehiclePanelHtml(ctx);
    const actions = document.querySelector('[data-intake-patch="workflow-actions"]');
    if (actions) actions.innerHTML = renderIntakeWorkflowActionsHtml(ctx);
    const noticeHost = document.querySelector('[data-intake-patch="limited-notice"]');
    if (noticeHost) {
      const html = renderIntakeLimitedNoticeHtml();
      const tmp = document.createElement('div');
      tmp.innerHTML = html;
      const next = tmp.firstElementChild;
      if (next && noticeHost.parentNode) {
        noticeHost.replaceWith(next);
      }
    }
  }

  function openIntakeCreateVehicleForm() {
    state.intakeCreateFormOpen = true;
    intakeUiRefresh();
  }

  function closeIntakeCreateVehicleForm() {
    state.intakeCreateFormOpen = false;
    intakeUiRefresh();
  }

  function setIntakeDraftField(field, value) {
    state.intakeDraft = state.intakeDraft || {};
    if (field === 'vin') {
      state.intakeDraft.vin = normalizeVin(value);
      state._intakeFocusField = 'vin';
      state._intakeCaretPos = String(state.intakeDraft.vin || '').length;
      scheduleIntakeLookupDebounced();
      return;
    }
    if (field === 'plate') {
      state.intakeDraft.plate = normalizePlate(value);
      state._intakeFocusField = 'plate';
      state._intakeCaretPos = String(state.intakeDraft.plate || '').length;
      scheduleIntakeLookupDebounced();
      return;
    }
    state.intakeDraft[field] = String(value || '');
    if (['brand', 'model', 'year', 'fuel', 'vehicleNote'].includes(field) && state.intakeCreateFormOpen) {
      return;
    }
  }

  function setIntakeChecklistItem(key, checked) {
    state.intakeDraft = state.intakeDraft || { checklist: {} };
    state.intakeDraft.checklist = { ...(state.intakeDraft.checklist || {}), [key]: Boolean(checked) };
  }

  async function fetchIntakeLegacyLookupContext(vin, plate) {
    const query = String(vin || plate || '').trim();
    if (!query) {
      state.intakeLookupLegacyCandidate = null;
      return;
    }
    try {
      const legacy = await window.apiCall('/api/v1/services/workspace/vehicle-lookup', 'POST', { query, query_type: 'auto' });
      const candidates = Array.isArray(legacy?.candidates) ? legacy.candidates : [];
      state.intakeLookupLegacyCandidate = candidates.length ? candidates[0] : null;
    } catch (error) {
      state.intakeLookupLegacyCandidate = null;
    }
  }

  async function lookupVehicleForIntake(options = {}) {
    const debounced = Boolean(options.debounced);
    if (!debounced) {
      cancelIntakeLookupDebounce();
    }
    const vin = normalizeVin(state.intakeDraft?.vin || '');
    const plate = normalizePlate(state.intakeDraft?.plate || '');
    state.intakeDraft.vin = vin;
    state.intakeDraft.plate = plate;
    if (!vin && !plate) {
      state.intakeLookupError = 'Zadejte VIN nebo SPZ pro vyhledání vozidla.';
      intakeUiRefresh();
      return;
    }
    if (debounced && !intakeHasLookupQuery()) {
      return;
    }
    state.intakeLookupError = '';
    if (!debounced) {
      state.intakeLimitedNotice = '';
      state.intakeStartResult = null;
    }
    state.intakeLookupResponse = null;
    state.intakeLookupLegacyCandidate = null;
    state.intakeSafeHistory = null;
    state.intakeCreateFormOpen = false;
    state.intakeLookupLoading = true;
    patchIntakeLookupButtonOnly();
    try {
      const payload = { source: 'service_intake', context: 'intake_route' };
      if (vin) payload.vin = vin;
      if (plate) payload.plate = plate;
      const response = await window.apiCall('/api/v1/services/workspace/vehicles/lookup', 'POST', payload);
      state.intakeLookupResponse = response || null;
      if (response?.status === 'not_found') {
        state.intakeCreateFormOpen = false;
      }
      await fetchIntakeLegacyLookupContext(vin, plate);
    } catch (error) {
      state.intakeLookupError = error?.message || 'Lookup vozidla se nepodařilo načíst.';
    } finally {
      state.intakeLookupLoading = false;
      intakeUiRefresh();
    }
  }

  async function createUnownedVehicleFromIntake() {
    const vin = normalizeVin(state.intakeDraft?.vin || '');
    const plate = normalizePlate(state.intakeDraft?.plate || '');
    const brand = String(state.intakeDraft?.brand || '').trim();
    const model = String(state.intakeDraft?.model || '').trim();
    if (!vin && !plate) {
      state.intakeLookupError = 'Pro založení nepřiřazeného vozidla zadejte VIN nebo SPZ.';
      intakeUiRefresh();
      return;
    }
    if (!brand || !model) {
      state.intakeLookupError = 'Pro založení nepřiřazeného vozidla vyplňte značku a model.';
      intakeUiRefresh();
      return;
    }
    state.intakeMutationLoading = true;
    state.intakeLookupError = '';
    try {
      const fuel = String(state.intakeDraft?.fuel || '').trim();
      const vehicleNote = String(state.intakeDraft?.vehicleNote || '').trim();
      const intakeNote = vehicleNote || String(state.intakeDraft?.technicianNote || '').trim() || null;
      const payload = {
        brand,
        model,
        source: 'service_intake',
        context: 'intake_route',
        intake_note: intakeNote,
      };
      if (vin) payload.vin = vin;
      if (plate) payload.plate = plate;
      if (fuel) payload.fuel = fuel;
      const year = Number(state.intakeDraft?.year || 0);
      const mileage = Number(state.intakeDraft?.odometer || state.intakeDraft?.mileage || 0);
      if (Number.isFinite(year) && year > 0) payload.year = year;
      if (Number.isFinite(mileage) && mileage >= 0) payload.mileage = mileage;
      const response = await window.apiCall('/api/v1/services/workspace/vehicles/provision-unowned', 'POST', payload);
      state.intakeLookupResponse = {
        found: true,
        status: 'found_service_unowned',
        vehicle_preview: response?.vehicle_preview || null,
        access: { status: 'work_access', can_request_access: false },
        can_open_detail: true,
        can_create_work_order: true,
      };
      state.intakeCreateFormOpen = false;
      state.intakeLimitedNotice = 'Nepřiřazené vozidlo bylo založeno. Vozidlo je evidováno centrálně bez vlastnické vazby.';
      await fetchIntakeLegacyLookupContext(vin, plate);
    } catch (error) {
      const detail = error?.payload?.detail;
      if (error?.status === 409 && detail?.code === 'vehicle_exists') {
        state.intakeLookupError = 'Vozidlo už existuje — načtěte lookup';
      } else if (error?.status === 409 && detail?.code === 'plate_candidate_requires_review') {
        state.intakeLookupError = 'SPZ má kandidáta v systému. Doplňte VIN nebo pokračujte ručním ověřením bez auto-merge.';
      } else {
        state.intakeLookupError = error?.message || 'Nepodařilo se založit nepřiřazené vozidlo.';
      }
    } finally {
      state.intakeMutationLoading = false;
      intakeUiRefresh();
    }
  }

  async function createWorkAccessFromIntake() {
    const lookup = state.intakeLookupResponse || {};
    const vehicleId = Number(lookup?.vehicle_preview?.vehicle_id || 0);
    if (!vehicleId) {
      state.intakeLookupError = 'Nejprve načtěte vozidlo pro pracovní zásah.';
      intakeUiRefresh();
      return;
    }
    state.intakeMutationLoading = true;
    state.intakeLookupError = '';
    cancelIntakeLookupDebounce();
    try {
      const response = await window.apiCall(`/api/v1/services/workspace/vehicles/${vehicleId}/work-access`, 'POST', {
        reason: String(state.intakeDraft?.technicianNote || '').trim() || 'Jednorázový servisní zásah',
        source: 'intake',
      });
      state.intakeLookupResponse = {
        ...(state.intakeLookupResponse || {}),
        found: true,
        status: 'found_work_access',
        vehicle_preview: response?.vehicle_preview || state.intakeLookupResponse?.vehicle_preview || null,
        access: {
          ...(state.intakeLookupResponse?.access || {}),
          status: 'work_access',
        },
        can_open_detail: true,
        can_create_work_order: true,
      };
      state.intakeLimitedNotice = 'Pracovní zásah byl založen odděleně od propojení s majitelem.';
    } catch (error) {
      state.intakeLookupError = error?.message || 'Pracovní přístup se nepodařilo založit.';
    } finally {
      state.intakeMutationLoading = false;
      intakeUiRefresh();
    }
  }

  async function loadSafeHistoryFromIntake() {
    const lookup = state.intakeLookupResponse || {};
    const vehicleId = Number(lookup?.vehicle_preview?.vehicle_id || 0);
    if (!vehicleId) {
      state.intakeLookupError = 'Nejprve načtěte vozidlo pro bezpečnou historii.';
      intakeUiRefresh();
      return;
    }
    state.intakeMutationLoading = true;
    state.intakeLookupError = '';
    try {
      const response = await window.apiCall(`/api/v1/services/workspace/vehicles/${vehicleId}/safe-technical-history`, 'GET');
      state.intakeSafeHistory = response || { items: [] };
      const count = Number(response?.count || (response?.items || []).length || 0);
      state.intakeLimitedNotice = count
        ? `Bezpečná technická historie načtena (${count} záznamů).`
        : 'Bezpečná technická historie zatím neobsahuje žádné záznamy.';
    } catch (error) {
      state.intakeLookupError = error?.message || 'Bezpečnou historii se nepodařilo načíst.';
    } finally {
      state.intakeMutationLoading = false;
      intakeUiRefresh();
    }
  }

  async function requestVehicleAccessFromIntake() {
    const lookup = state.intakeLookupResponse || {};
    const vehicleId = Number(lookup?.vehicle_preview?.vehicle_id || 0);
    const vin = normalizeVin(state.intakeDraft?.vin || '');
    const plate = normalizePlate(state.intakeDraft?.plate || '');
    const query = String(vin || plate || '').trim();
    if (!vehicleId || !query) {
      state.intakeLookupError = 'Žádost o přístup vyžaduje nalezené vozidlo a VIN/SPZ.';
      intakeUiRefresh();
      return;
    }
    state.intakeMutationLoading = true;
    state.intakeLookupError = '';
    cancelIntakeLookupDebounce();
    try {
      const response = await window.apiCall('/api/v1/services/workspace/access-requests', 'POST', {
        vehicle_id: vehicleId,
        lookup_query: query,
        note: 'Příjem vozidla do servisu',
      });
      state.intakeLimitedNotice = response?.created
        ? 'Žádost byla odeslána majiteli. Detail vozidla zůstává uzamčený do schválení.'
        : 'Žádost už čeká na schválení. Nová duplicitní žádost nebyla odeslána.';
      if (state.intakeLookupResponse?.access) {
        state.intakeLookupResponse.access.status = 'pending';
        state.intakeLookupResponse.access.can_request_access = false;
      }
    } catch (error) {
      state.intakeLookupError = error?.message || 'Žádost o autorizaci se nepodařilo odeslat.';
    } finally {
      state.intakeMutationLoading = false;
      intakeUiRefresh();
    }
  }

  async function startServiceIntake() {
    const lookup = state.intakeLookupResponse || {};
    const vehicleId = Number(lookup?.vehicle_preview?.vehicle_id || 0);
    if (!vehicleId) {
      state.intakeLookupError = 'Nejprve načtěte vozidlo pro zahájení příjmu.';
      intakeUiRefresh();
      return;
    }
    const accessStatus = String(lookup?.access?.status || '').toLowerCase();
    if (!['approved', 'work_access'].includes(accessStatus)) {
      state.intakeLimitedNotice = 'Příjem lze zahájit po schváleném propojení nebo jako jednorázový servisní zásah.';
      intakeUiRefresh();
      return;
    }
    state.intakeMutationLoading = true;
    state.intakeLookupError = '';
    try {
      const odometer = Number(state.intakeDraft?.odometer || 0);
      const response = await window.apiCall('/api/v1/services/workspace/service-cases/', 'POST', {
        vehicle_id: vehicleId,
        intake_note: String(state.intakeDraft?.technicianNote || '').trim() || null,
        initial_mileage_km: Number.isFinite(odometer) && odometer > 0 ? odometer : null,
      });
      state.intakeStartResult = response || null;
      state.intakeLimitedNotice = 'Příjem byl založen v servisních případech.';
    } catch (error) {
      state.intakeLookupError = error?.message || 'Příjem se nepodařilo zahájit.';
    } finally {
      state.intakeMutationLoading = false;
      intakeUiRefresh();
    }
  }

  async function createWorkOrderFromIntake() {
    const lookup = state.intakeLookupResponse || {};
    const legacy = state.intakeLookupLegacyCandidate || {};
    const vehicleId = Number(lookup?.vehicle_preview?.vehicle_id || legacy?.vehicle_id || 0);
    const ownerId = Number(legacy?.owner_customer_id || 0);
    const lookupStatus = String(lookup?.status || '').toLowerCase();
    const accessStatus = String(lookup?.access?.status || '').toLowerCase();
    const canWorkWithoutOwner = accessStatus === 'work_access' || lookupStatus === 'found_service_unowned' || Boolean(lookup?.can_create_work_order);
    if (!vehicleId) {
      state.intakeLimitedNotice = 'Nejprve načtěte nebo založte vozidlo pro vytvoření zakázky.';
      intakeUiRefresh();
      return;
    }
    if (!ownerId && !canWorkWithoutOwner) {
      state.intakeLimitedNotice = 'Nejdřív založte jednorázový servisní zásah, nebo vyžádejte propojení s majitelem.';
      intakeUiRefresh();
      return;
    }
    state.intakeMutationLoading = true;
    state.intakeLookupError = '';
    try {
      const payload = {
        vehicle_id: vehicleId,
        title: 'Příjem vozidla',
        description: String(state.intakeDraft?.technicianNote || '').trim() || null,
        status: 'awaiting_client_approval',
        source_type: 'intake',
        source_intake_id: Number(state.intakeStartResult?.id || 0) || null,
      };
      if (ownerId > 0) payload.owner_id = ownerId;
      const response = await window.apiCall('/api/service/work-orders', 'POST', payload);
      state.intakeLimitedNotice = 'Zakázka byla vytvořena z příjmu. Přechod do sekce Zakázky proběhl automaticky.';
      navigate('work-orders');
      if (response?.id) {
        window.setTimeout(() => {
          try {
            openWorkOrderDetailModal(Number(response.id));
          } catch (err) {
            /* ignore */
          }
        }, 120);
      }
    } catch (error) {
      state.intakeLookupError = error?.message || 'Zakázku z příjmu se nepodařilo vytvořit.';
    } finally {
      state.intakeMutationLoading = false;
      if (state.activeSection === 'work-orders') {
        render();
      } else {
        intakeUiRefresh();
      }
    }
  }

  function renderServiceIntakeSection() {
    const ctx = getIntakeUiContext();
    const { draft } = ctx;
    const checklistRows = [
      ['keys', 'Převzaty klíče'],
      ['body', 'Kontrola karoserie'],
      ['lights', 'Kontrola světel'],
      ['tires', 'Kontrola pneumatik'],
      ['interior', 'Kontrola interiéru'],
      ['customer_notified', 'Zákazník upozorněn na viditelné poškození'],
    ];
    return ServiceProPageShell(
      'Příjem vozidla',
      'Pracovní tok příjmu vozidla: bezpečný lookup, autorizace přístupu, založení příjmu a navazující zakázka.',
      `
        <div data-testid="service-intake-section" class="service-intake-layout">
          <div class="service-pro-bottom-grid service-intake-grid">
            <article class="service-pro-card">
              <h3>Vyhledat vozidlo</h3>
              <label>VIN
                <input data-testid="service-intake-vin-input" class="service-shell-search" value="${escape(draft.vin || '')}" oninput="window.serviceShell.setIntakeDraftField('vin', this.value)" placeholder="např. TMBJH7NP9N7041234">
              </label>
              <label>SPZ
                <input data-testid="service-intake-plate-input" class="service-shell-search" value="${escape(draft.plate || '')}" oninput="window.serviceShell.setIntakeDraftField('plate', this.value)" placeholder="např. 1AB 2345">
              </label>
              <div class="service-action-bar">
                <button type="button" class="service-shell-primary-btn" data-testid="service-intake-lookup-button" ${state.intakeLookupLoading ? 'disabled' : ''} onclick="window.serviceShell.lookupVehicleForIntake()">${state.intakeLookupLoading ? 'Načítám…' : 'Načíst vozidlo'}</button>
                <button type="button" class="btn btn-secondary" data-testid="service-intake-ocr-button" disabled title="OCR SPZ není aktuálně aktivní. Zadejte SPZ nebo VIN ručně.">Foto SPZ / OCR</button>
              </div>
              <div data-intake-patch="lookup-error">${renderIntakeLookupErrorHtml()}</div>
            </article>
            <article class="service-pro-card" data-testid="service-intake-result">${renderIntakeResultPanelHtml(ctx)}</article>
            <article class="service-pro-card" data-testid="service-intake-access-state">${renderIntakeAccessPanelHtml(ctx)}</article>
            <div data-intake-patch="create-vehicle">${renderIntakeCreateVehiclePanelHtml(ctx)}</div>
            <article class="service-pro-card">
              <h3>Příjem vozidla</h3>
              <label>Stav tachometru (km)
                <input class="service-shell-search" value="${escape(draft.odometer || '')}" oninput="window.serviceShell.setIntakeDraftField('odometer', this.value)" placeholder="např. 185000">
              </label>
              <label>Poznámka technika
                <textarea class="service-shell-search" rows="3" oninput="window.serviceShell.setIntakeDraftField('technicianNote', this.value)">${escape(draft.technicianNote || '')}</textarea>
              </label>
              <strong>Checklist příjmu</strong>
              ${checklistRows.map(([key, label]) => `<label class="service-check-row"><span>${escape(label)}</span><input type="checkbox" ${draft?.checklist?.[key] ? 'checked' : ''} onchange="window.serviceShell.setIntakeChecklistItem('${key}', this.checked)"></label>`).join('')}
              <article class="service-pro-card service-pro-card--muted" data-testid="service-intake-limited-photo-state"><p>Fotodokumentace je v této fázi vedená jako omezený stav. OCR SPZ není aktuálně aktivní.</p></article>
              <div class="service-action-bar" data-intake-patch="workflow-actions">${renderIntakeWorkflowActionsHtml(ctx)}</div>
              <p class="service-shell-muted">Pokud backend nepodporuje kompletní převod příjmu na zakázku, tlačítko zobrazí omezený stav bez fake úspěchu.</p>
            </article>
          </div>
          ${renderIntakeLimitedNoticeHtml()}
          <article class="service-pro-card service-pro-card--muted"><p>Audit: osobní údaje majitele, ceny, faktury, fotky a dokumenty zůstávají skryté, dokud backend nevrátí schválený rozsah přístupu.</p></article>
        </div>
      `,
      { asideHtml: renderQuickIntakePanel(), testId: 'service-intake-page' },
    );
  }

  function openAuthorizationDetail(id) {
    const item = (Array.isArray(state.pendingAuthorizations) ? state.pendingAuthorizations : []).find((entry) => Number(entry?.id) === Number(id));
    openModal({
      key: `authorization-${Number(id || 0)}`,
      title: 'Detail žádosti',
      description: 'Stav autorizace majitele a auditovatelný rozsah požadavku.',
      renderContent: () => `
        <div class="service-shell-modal-detail-grid cols-2">
          <div class="service-shell-side-card">
            <h3>Vozidlová data</h3>
            <div class="service-shell-list">
              <div class="service-shell-list-row"><span class="service-shell-list-title">Vozidlo</span><span class="service-shell-list-value">${escape(item?.vehicle_title || 'Vozidlo')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">SPZ</span><span class="service-shell-list-value">${escape(item?.license_plate || '-')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Stav</span><span class="service-shell-list-value">${escape(item?.status_label || 'Čeká na zákazníka')}</span></div>
            </div>
          </div>
          <div class="service-shell-side-card">
            <h3>Osobní údaje</h3>
            <div class="service-shell-empty">Osobní údaje jsou chráněny, dokud majitel žádost neschválí. Opakované odeslání patří do rate-limitovaného backend flow.</div>
          </div>
        </div>
        <section class="service-shell-side-card"><h3>Auditní stopa</h3><div class="service-shell-empty">Žádost vytvořena: ${escape(item?.created_at ? formatDateTime(item.created_at) : 'evidováno serverem')}</div></section>
      `,
      renderFooter: () => '<div class="service-shell-modal-footer"><button type="button" class="btn btn-secondary" onclick="window.serviceShell.navigate(\'audit\'); window.serviceShell.closeModal()">Audit</button><button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zavřít</button></div>',
    });
  }

  function openGdprInfo(kind) {
    const titles = {
      access: 'Přístup povolen majitelem',
      hidden: 'Osobní údaje skryty',
      vin: 'VIN záznam',
      audit: 'Auditováno',
      consent: 'Souhlas zákazníka ověřen',
      pending: 'Čeká na autorizaci',
    };
    openModal({
      key: `gdpr-${kind}`,
      title: titles[kind] || 'Bezpečnost a GDPR',
      description: 'Servisní rozhraní odděluje vozidlová data od osobních údajů.',
      renderContent: () => '<div class="service-shell-empty">Plná osobní data jsou dostupná pouze přes schválenou vazbu, auditovaný detail a oprávnění z /api/me. VIN se mimo detail zobrazuje zkráceně.</div>',
      renderFooter: () => '<div class="service-shell-modal-footer"><button type="button" class="btn btn-secondary" onclick="window.serviceShell.navigate(\'audit\'); window.serviceShell.closeModal()">Audit a bezpečnost</button><button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zavřít</button></div>',
    });
  }

  function serviceSearchResultsHtml() {
    const q = String(state.searchTerm || '').trim().toLowerCase();
    const workOrders = dashboardWorkOrderItems().filter((item) => [
      item?.title,
      item?.vehicle_title,
      item?.vehicle_label,
      item?.license_plate,
      item?.vehicle_spz,
      item?.vin_short,
      item?.vehicle_vin,
      item?.customer_display,
      item?.customer_name,
    ].join(' ').toLowerCase().includes(q)).slice(0, 5);
    const vehicles = (Array.isArray(state.vehicles) ? state.vehicles : []).filter((item) => [
      item?.brand,
      item?.model,
      item?.nickname,
      item?.plate,
      item?.vin,
    ].join(' ').toLowerCase().includes(q)).slice(0, 4);
    const rows = [
      ...workOrders.map((item) => ({
        label: item?.vehicle_title || vehicleTitle(item),
        meta: `Zakázka #${Number(item?.id || 0)} · ${item?.license_plate || item?.vehicle_spz || '-'}`,
        action: `window.serviceShell.openWorkOrderDetailModal(${Number(item?.id || 0)}); window.serviceShell.closeSearchResults();`,
      })),
      ...vehicles.map((item) => ({
        label: vehicleTitle(item),
        meta: `Vozidlo · ${item?.plate || item?.plate_masked || '-'} · ${maskVin(item?.vin || item?.vin_masked)}`,
        action: `window.serviceShell.openVehicleDetailModal(${Number(item?.id || item?.vehicle_id || 0)}); window.serviceShell.closeSearchResults();`,
      })),
    ];
    return `
      <div class="service-search-popover">
        ${rows.length ? rows.map((row) => `
          <button type="button" onclick="${row.action}">
            <strong>${escape(row.label)}</strong>
            <span>${escape(row.meta)}</span>
          </button>
        `).join('') : '<div class="service-search-empty">Nic nenalezeno. Osobní údaje se zobrazí jen při oprávnění.</div>'}
      </div>
    `;
  }

  function openSearchResults() {
    state.searchResultsOpen = true;
    render();
  }

  function closeSearchResults() {
    state.searchResultsOpen = false;
    render();
  }

  function scrollToRisks() {
    navigate('dashboard');
    window.setTimeout(() => document.getElementById('serviceRisksPanel')?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 40);
  }

  function scrollToAuthorizations() {
    navigate('dashboard');
    window.setTimeout(() => document.getElementById('servicePendingAuthorizations')?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 40);
  }

  function openRiskTarget(type, targetPath) {
    const key = String(type || '').toLowerCase();
    if (key === 'missing_photos') return navigate('photos');
    if (key === 'price_approval') return navigate('work-orders', { kpiFilter: 'awaiting' });
    if (key === 'unverified_vin') return navigate('vehicles');
    if (key === 'invoice_waiting') return navigate('invoices');
    if (key === 'handover_ready') return navigate('work-orders');
    const raw = String(targetPath || '');
    if (raw.includes('invoice')) return navigate('invoices');
    if (raw.includes('photo')) return navigate('photos');
    if (raw.includes('vehicle')) return navigate('vehicles');
    if (raw.includes('work-orders')) return navigate('work-orders');
    return navigate('audit');
  }

  
  function renderMobileNavSheet() {
    if (!state.mobileNavOpen || !isMobileViewport()) return '';
    const groupsHtml = MOBILE_NAV_SHEET_GROUPS.map((group) => `
      <div class="service-shell-mobile-nav-group" data-testid="service-mobile-nav-group">
        <span class="service-shell-mobile-nav-group-title">${escape(group.title)}</span>
        <div class="service-shell-mobile-nav-group-items">
          ${group.items.map(([sectionKey, label]) => `
            <button
              type="button"
              class="service-shell-mobile-nav-sheet-btn ${state.activeSection === sectionKey ? 'active' : ''}"
              data-testid="service-mobile-nav-${escape(sectionKey)}"
              data-service-section="${escape(sectionKey)}"
              onclick="window.serviceShell.navigate('${sectionKey}')"
            >${escape(label)}</button>
          `).join('')}
        </div>
      </div>
    `).join('');
    return `
      <div class="service-shell-bottom-sheet service-shell-mobile-nav-sheet" role="dialog" aria-modal="true" aria-label="Všechny sekce servisu" data-testid="service-mobile-nav-sheet">
        <button type="button" class="service-shell-bottom-sheet-backdrop" onclick="window.serviceShell.toggleMobileNav()" aria-label="Zavřít menu"></button>
        <section class="service-shell-bottom-sheet-panel">
          <div class="service-shell-bottom-sheet-handle" aria-hidden="true"></div>
          <div class="service-shell-card-head">
            <div>
              <h3 class="service-shell-card-title">Všechny sekce</h3>
              <p class="service-shell-subtitle">Zákazníci, dokumentace, finance a správa účtu.</p>
            </div>
            <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.toggleMobileNav()" aria-label="Zavřít menu">×</button>
          </div>
          <div class="service-shell-mobile-nav-sheet-body">${groupsHtml}</div>
        </section>
      </div>
    `;
  }

  function buildNavSlotHtml(entry, { mobileMode } = {}) {
    const active = mobileMode ? mobileNavTabActive(entry) : navRailSlotActive(entry);
    const hasSub = !mobileMode && Array.isArray(entry.submenu) && entry.submenu.length > 0;
    const submenuHtml = hasSub
      ? `
        <div class="service-nav-submenu" role="menu" aria-label="${escape(entry.label)}">
          ${entry.submenu
            .map(([sid, lbl]) => `
            <button
              type="button"
              role="menuitem"
              class="service-nav-submenu-item ${state.activeSection === sid ? 'is-active' : ''}"
              onclick="window.serviceShell.navigate('${sid}')"
            >${escape(lbl)}</button>
          `)
            .join('')}
        </div>`
      : '';
    const sectionKey = entry.section || 'more';
    const tutorialRailKey = entry.section
      ? 'svc-shell-' +
        String(entry.section)
          .toLowerCase()
          .trim()
          .replace(/[^a-z0-9-]+/g, '-')
          .replace(/^-+|-+$/g, '')
      : 'svc-shell-more';
    const testId = mobileMode && entry.kind === 'more' ? 'service-nav-more' : `service-nav-${escape(sectionKey)}`;
    const trigger = `
      <button
        type="button"
        class="service-nav-item ${active ? 'active' : ''} ${entry.kind === 'more' ? 'service-nav-item--more' : ''}"
        data-testid="${testId}"
        data-service-nav-section="${escape(sectionKey)}"
        ${hasSub ? 'aria-haspopup="true"' : ''}
        ${active ? 'aria-current="page"' : ''}
        ${entry.kind === 'more' ? `aria-expanded="${state.mobileNavOpen ? 'true' : 'false'}"` : ''}
        ${tutorialRailKey ? `data-tutorial="${escape(tutorialRailKey)}"` : ''}
        title="${escape(entry.label)}"
        onclick="window.serviceShell.handleNavRailClick(event, '${entry.group}')"
      >
        <span class="service-nav-item-icon" aria-hidden="true">${navRailIconSvg(entry.navIcon)}</span>
        <span class="service-nav-item-label">${escape(entry.label)}</span>
      </button>`;
    return `
      <div
        class="service-nav-slot ${active ? 'is-active' : ''} ${hasSub ? 'has-submenu' : ''} ${entry.kind === 'more' ? 'service-nav-slot--more' : ''}"
        data-nav-group="${escape(entry.group)}"
      >
        ${trigger}
        ${submenuHtml}
      </div>`;
  }

  function ServiceNav() {
    const mobile = isMobileViewport();
    const config = mobile ? MOBILE_TAB_CONFIG : NAV_RAIL_CONFIG;
    const slots = config.map((entry) => buildNavSlotHtml(entry, { mobileMode: mobile }));
    return `
      ${renderMobileNavSheet()}
      <aside class="service-nav ${mobile ? 'service-nav--mobile-tabs' : ''}" aria-label="Hlavní navigace účtu servisu" id="service-shell-left-nav">
        <div class="service-nav-brand">
          <div class="service-nav-logo">${navRailIconSvg('car')}</div>
          <div><strong>Správa vozidel</strong></div>
        </div>
        <div class="service-nav-account">
          <strong>${escape(serviceAccountName())}</strong>
          <span class="service-mini-badge service-mini-badge--success">${navRailIconSvg('shield')} Servis ověřen</span>
        </div>
        <nav class="service-nav-menu" aria-label="Servisní menu">${slots.join('')}</nav>
        <div class="service-nav-footer">
          <button type="button" class="service-nav-status" onclick="window.serviceShell.openLicenseSettings()">${navRailIconSvg('shield')} Aktivní servisní účet</button>
          <button type="button" class="service-nav-status service-nav-status--plain" onclick="window.serviceShell.navigate('audit')">${navRailIconSvg('shield')} Audit log aktivní</button>
          <button type="button" class="service-nav-gdpr" onclick="window.serviceShell.navigate('audit')">${navRailIconSvg('shield')} Bezpečnost & GDPR</button>
        </div>
      </aside>
    `;
  }

  function ServiceTopBar() {
    const profile = currentProfile();
    const mobile = isMobileViewport();
    const risksCount = (Array.isArray(state.dashboardRisks) ? state.dashboardRisks : [])
      .reduce((sum, item) => sum + Math.max(1, Number(item?.count || 0)), 0);
    const accountMenu = state.accountMenuOpen ? `
      <div class="service-shell-account-menu">
        <div class="service-shell-account-summary">
          <strong>${escape(profile?.name || window.currentUser?.name || 'Servisní účet')}</strong>
          <span>${escape(profile?.email || window.currentUser?.email || '-')}</span>
          <span>${escape(String(profile?.role || window.currentUser?.role || 'service_account').replace(/_/g, ' '))}</span>
          <button type="button" class="service-shell-account-license-hit" onclick="window.serviceShell.openLicenseSettings()" title="Otevřít licence a plány">${escape(licenseSummaryText())}</button>
        </div>
        <button type="button" class="service-shell-account-action" onclick="window.serviceShell.openAccountSettings()">Otevřít nastavení účtu</button>
        <button type="button" class="service-shell-account-action" onclick="window.serviceShell.openLicenseSettings()">Licence a plán</button>
        <button type="button" class="service-shell-account-action" onclick="window.serviceShell.navigate('team'); window.serviceShell.closeAccountMenu();">Otevřít profil</button>
        <button type="button" class="service-shell-account-action danger" onclick="window.serviceShell.logout()">Odhlásit se</button>
      </div>
    ` : '';
    
    if (mobile) {
      return `
      <header class="service-topbar service-topbar--mobile">
        <div class="service-topbar-row service-topbar-row--tools">
          <div class="service-topbar-tools">
            <button type="button" class="service-shell-icon-btn service-shell-theme-toggle-btn" onclick="window.toggleAppUiTheme()" aria-label="Přepnout motiv">◐</button>
            <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.load(true)" aria-label="Obnovit data">↻</button>
            <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.openServiceToolsModal()" aria-label="Servisní nástroje">⌘</button>
          </div>
          <div class="service-topbar-account-cluster">
            <button type="button" class="service-shell-bell" onclick="window.serviceShell.scrollToRisks()" aria-label="Upozornění">♧<span>${escape(String(risksCount || 0))}</span></button>
            <div class="service-shell-userbox-wrap">
              <button type="button" class="service-shell-userbox service-shell-userbox--compact" onclick="window.serviceShell.toggleAccountMenu()" aria-label="Účet servisu">
                <span class="service-shell-avatar">${escape(initials(profile?.name || profile?.email || window.currentUser?.email || 'SA'))}</span>
              </button>
              ${accountMenu}
            </div>
          </div>
        </div>
        <div class="service-topbar-row service-topbar-row--search service-topbar-search-wrap">
          <label class="service-topbar-search" aria-label="Hledání v servisu" data-testid="service-topbar-search">
            <span aria-hidden="true">⌕</span>
            <input type="search" placeholder="Hledat VIN, SPZ, zákazníka, zakázku…" value="${escape(state.searchTerm || '')}" oninput="window.serviceShell.setSearchTerm(this.value); window.serviceShell.openSearchResults()" onfocus="window.serviceShell.openSearchResults()">
          </label>
          ${state.searchResultsOpen && state.searchTerm ? serviceSearchResultsHtml() : ''}
        </div>
        <div class="service-topbar-row service-topbar-row--cta">
          <button type="button" class="service-shell-primary-btn service-topbar-cta-btn" data-testid="service-topbar-intake-cta" onclick="window.serviceShell.openIntakeFlow()">+ Přijmout vozidlo</button>
          <button type="button" class="service-shell-primary-btn service-topbar-cta-btn" data-testid="service-topbar-workorder-cta" onclick="window.serviceShell.openCreateWorkOrderModal()">+ Nová zakázka</button>
        </div>
      </header>
    `;
    }

    return `
      <header class="service-topbar">
        <div class="service-topbar-left service-topbar-search-wrap">
          <label class="service-topbar-search" aria-label="Hledání v servisu">
            <span aria-hidden="true">⌕</span>
            <input type="search" placeholder="Hledat VIN, SPZ, zákazníka, zakázku…" value="${escape(state.searchTerm || '')}" oninput="window.serviceShell.setSearchTerm(this.value); window.serviceShell.openSearchResults()" onfocus="window.serviceShell.openSearchResults()">
          </label>
          ${state.searchResultsOpen && state.searchTerm ? serviceSearchResultsHtml() : ''}
        </div>
        <div class="service-topbar-right">
          <button type="button" class="service-shell-icon-btn service-shell-theme-toggle-btn" onclick="window.toggleAppUiTheme()" aria-label="Přepnout motiv">◐</button>
          <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.load(true)" aria-label="Obnovit data">↻</button>
          <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.openServiceToolsModal()" aria-label="Servisní nástroje">⌘</button>
          <button type="button" class="service-shell-primary-btn" onclick="window.serviceShell.openIntakeFlow()">+ Přijmout vozidlo</button>
          <button type="button" class="service-shell-primary-btn" onclick="window.serviceShell.openCreateWorkOrderModal()">+ Nová zakázka</button>
          <button type="button" class="service-shell-bell" onclick="window.serviceShell.scrollToRisks()" aria-label="Upozornění">♧<span>${escape(String(risksCount || 0))}</span></button>
          
          <div class="service-shell-userbox-wrap">
            <button type="button" class="service-shell-userbox" onclick="window.serviceShell.toggleAccountMenu()" aria-label="Účet servisu" style="background: transparent; border: none; cursor: pointer; display: flex; align-items: center; gap: 8px;">
              <span class="service-shell-avatar" style="background: var(--service-primary); color: white; border-radius: 50%; width: 32px; height: 32px; display: flex; align-items: center; justify-content: center;">${escape(initials(profile?.name || profile?.email || window.currentUser?.email || 'SA'))}</span>
              <div class="service-shell-usertext" style="text-align: left; display: ${mobile ? 'none' : 'block'}">
                <strong style="display: block; font-size: 0.875rem;">${escape(profile?.name || window.currentUser?.name || window.currentUser?.email || 'Servisní účet')}</strong>
                <span>${escape(serviceRoleLabel())}</span>
              </div>
            </button>
            ${accountMenu}
          </div>
        </div>
      </header>
    `;
  }

  function shellHeader() {
    const profile = currentProfile();
    const mobile = isMobileViewport();
    const accountMenu = state.accountMenuOpen ? `
      <div class="service-shell-account-menu">
        <div class="service-shell-account-summary">
          <strong>${escape(profile?.name || window.currentUser?.name || 'Servisní účet')}</strong>
          <span>${escape(profile?.email || window.currentUser?.email || '-')}</span>
          <span>${escape(String(profile?.role || window.currentUser?.role || 'service_account').replace(/_/g, ' '))}</span>
          <button type="button" class="service-shell-account-license-hit" onclick="window.serviceShell.openLicenseSettings()" title="Otevřít licence a plány">${escape(licenseSummaryText())}</button>
        </div>
        <button type="button" class="service-shell-account-action" onclick="window.serviceShell.openAccountSettings()">Otevřít nastavení účtu</button>
        <button type="button" class="service-shell-account-action" onclick="window.serviceShell.openLicenseSettings()">Licence a plán</button>
        <button type="button" class="service-shell-account-action" onclick="window.serviceShell.navigate('team'); window.serviceShell.closeAccountMenu();">Otevřít profil</button>
        <button type="button" class="service-shell-account-action danger" onclick="window.serviceShell.logout()">Odhlásit se</button>
      </div>
    ` : '';
    const navGroups = [
      { title: 'Nástěnka', items: [['dashboard', 'Přehled']] },
      { title: 'Zákazníci', items: [['clients', 'Přehled zákazníků'], ['vehicles', 'Vozidla zákazníků']] },
      { title: 'Servis', items: [['work-orders', 'Příchozí objednávky'], ['reservations', 'Příchozí rezervace'], ['reminders', 'Připomínky']] },
      { title: 'Sklad', items: [['documents', 'Dokumenty']] },
      { title: 'Reporty', items: [['invoices', 'Faktury']] },
      { title: 'Nastavení', items: [['team', 'Tým a účet']] },
    ];
    const navItems = navGroups.map((group) => `
      <div class="service-shell-nav-section" aria-label="${escape(group.title)}">
        <span class="service-shell-nav-section-title">${escape(group.title)}</span>
        ${group.items.map(([key, label]) => {
          const topNavTutorial = `svc-topnav-${String(key)
            .toLowerCase()
            .trim()
            .replace(/[^a-z0-9-]+/g, '-')
            .replace(/^-+|-+$/g, '')}`;
          return `
          <button
            type="button"
            class="service-shell-nav-btn ${state.activeSection === key ? 'active' : ''}"
            data-service-section="${escape(key)}"
            data-tutorial="${escape(topNavTutorial)}"
            onclick="window.serviceShell.navigate('${key}')"
          >${escape(label)}</button>
        `;
        }).join('')}
      </div>
    `).join('');

    return `
      <header class="service-shell-header">
        <div class="service-shell-brandline">
          <button type="button" class="service-shell-icon-btn service-shell-mobile-menu-btn" onclick="window.serviceShell.toggleMobileNav()" aria-expanded="${mobile && state.mobileNavOpen ? 'true' : 'false'}" aria-controls="service-shell-main-nav" aria-label="${state.mobileNavOpen ? 'Zavřít menu' : 'Otevřít menu'}">☰</button>
          <div class="service-shell-brand">
            <img class="service-shell-brand-logo" src="/web/assets/toozservis-logo-icon.png" alt="" width="40" height="40" decoding="async" />
            <span class="service-shell-brand-text">${escape(getAppDisplayName())}</span>
          </div>
        </div>
        <div class="service-shell-toolbar">
          <time id="serviceShellNavbarClock" class="navbar-digital-clock service-shell-navbar-clock" datetime="" title="Čas v Česku (Europe/Prague)">--:--:--</time>
          ${workspaceModeSwitchShellHtml()}
          <button type="button" class="service-shell-icon-btn service-shell-theme-toggle-btn" onclick="window.toggleAppUiTheme()" aria-label="Přepnout motiv">${state.theme === 'light' ? '☀' : '☾'}</button>
          <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.load(true)" aria-label="Obnovit data">↻</button>
          <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.openServiceToolsModal()" aria-label="Servisní nástroje">⌘</button>
          ${serviceShellNotificationsButtonHtml()}
          <div class="service-shell-userbox-wrap">
          <button type="button" class="service-shell-userbox" onclick="window.serviceShell.toggleAccountMenu()" aria-label="Účet servisu">
            <span class="service-shell-avatar">${escape(initials(profile?.name || profile?.email || window.currentUser?.email || 'SA'))}</span>
            <div class="service-shell-usertext">
              <strong>${escape(profile?.name || window.currentUser?.name || window.currentUser?.email || 'Servisní účet')}</strong>
              <span>${escape(String(profile?.role || window.currentUser?.role || 'service_account').replace(/_/g, ' '))}</span>
            </div>
          </button>
          ${accountMenu}
          </div>
          <button type="button" class="service-shell-primary-btn" onclick="${state.activeVehicle ? `window.serviceShell.openServiceRecordModal(${Number(state.activeVehicle.vehicleId || 0)})` : 'window.serviceShell.openCreateWorkOrderModal()'}">${mobile ? '+' : '+ Nová zakázka'}</button>
        </div>
        <nav id="service-shell-main-nav" class="service-shell-nav ${mobile && state.mobileNavOpen ? 'mobile-open' : ''}" aria-label="Servisní navigace">
          ${navItems}
        </nav>
      </header>
    `;
  }

  function pageHead(title, subtitle) {
    return ServicePageHeader(title, subtitle);
  }

  function staticInfoSection(title, subtitle, bodyHtml) {
    return ServiceProPageShell(
      title,
      subtitle,
      `<section class="service-pro-card service-shell-static-info"><div class="service-shell-static-body">${bodyHtml}</div></section>`,
    );
  }

  function payrollToolbarHtml() {
    const y = state.payrollPeriod.year;
    const m = state.payrollPeriod.month;
    return `
      <div class="service-shell-payroll-toolbar" style="display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:14px;">
        <label style="font-size:0.82rem;color:var(--service-text-soft);">Rok
          <input type="number" class="service-shell-search" style="width:92px;margin-left:6px" value="${y}"
            onchange="window.serviceShell.setPayrollPeriod(Number(this.value), ${m})" />
        </label>
        <label style="font-size:0.82rem;color:var(--service-text-soft);">Měsíc
          <input type="number" min="1" max="12" class="service-shell-search" style="width:72px;margin-left:6px" value="${m}"
            onchange="window.serviceShell.setPayrollPeriod(${y}, Number(this.value))" />
        </label>
        <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.refreshPayrollModule(true)">↻ Obnovit data mezd</button>
      </div>`;
  }

  function renderPayrollWorkspace(section) {
    const sec = String(section || '');
    const loadBlock = state.payrollLoading
      ? '<div class="service-shell-empty">Načítám mzdová data…</div>'
      : '';
    const err = state.payrollError
      ? `<div class="service-shell-inline-error" style="margin-bottom:12px;">${escape(state.payrollError)}</div>`
      : '';
    const d = state.payrollData || {};
    const offices = Array.isArray(d.offices) ? d.offices : [];
    const employees = d.employees && Array.isArray(d.employees.items) ? d.employees.items : [];
    const att = d.attendance && Array.isArray(d.attendance.items) ? d.attendance.items : [];
    const pays = d.payslips && Array.isArray(d.payslips.items) ? d.payslips.items : [];
    const journal = d.journal || null;
    const jmhz = d.jmhz && Array.isArray(d.jmhz.items) ? d.jmhz.items : [];

    const officeOptions = offices.map((o) => `<option value="${Number(o.id)}">${escape(o.name || '')}</option>`).join('');

    if (sec === 'payroll-employees') {
      const rows = employees.map((e) => `
        <tr>
          <td>${escape(`${e.last_name || ''} ${e.first_name || ''}`)}</td>
          <td>${escape(e.birth_date || '')}</td>
          <td>${escape(e.health_insurance_code || '—')}</td>
          <td>${e.is_active ? 'Aktivní' : 'Neaktivní'}</td>
          <td><button type="button" class="btn btn-secondary" onclick="window.serviceShell.openPayrollEmployeeDetail(${Number(e.id)})">Detail</button></td>
        </tr>`).join('');
      const body = `
        ${payrollToolbarHtml()}
        ${err}${loadBlock}
        <p class="service-shell-muted" style="font-size:0.84rem;">Citlivé údaje (rodné číslo, účet) jsou v API maskované; plná hodnota jen přes oprávnění a parametr <code>full_sensitive</code>.</p>
        <div style="overflow:auto;margin-top:10px;">
          <table class="service-shell-data-table">
            <thead><tr><th>Zaměstnanec</th><th>Datum narození</th><th>ZP</th><th>Stav</th><th></th></tr></thead>
            <tbody>${rows || '<tr><td colspan="5">Žádní zaměstnanci — založte je přes „Nový zaměstnanec“.</td></tr>'}</tbody>
          </table>
        </div>`;
      return staticInfoSection('Zaměstnanci', 'Evidence zaměstnanců servisu (mzdy).', body);
    }

    if (sec === 'payroll-employee-new') {
      const body = `
        ${payrollToolbarHtml()}
        ${err}
        <form class="service-shell-side-card" style="padding:16px;" onsubmit="window.serviceShell.submitPayrollEmployeeCreate(event)">
          <h3 style="margin:0 0 12px;">Nový zaměstnanec</h3>
          <div style="display:grid;gap:10px;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));">
            <label>Jméno *<input class="service-shell-search" name="first_name" required maxlength="128"></label>
            <label>Příjmení *<input class="service-shell-search" name="last_name" required maxlength="128"></label>
            <label>Datum narození *<input class="service-shell-search" name="birth_date" type="date" required></label>
            <label>Účtárna<select class="service-shell-search" name="primary_office_id"><option value="">—</option>${officeOptions}</select></label>
            <label>Hodinová hrubá sazba<input class="service-shell-search" name="hourly_gross_rate" type="number" step="0.01" min="0" placeholder="např. 200"></label>
            <label>Úvazek (hod/týden)<input class="service-shell-search" name="contract_hours_per_week" type="number" step="0.5" min="0" placeholder="40"></label>
            <label>Zdravotní pojišťovna (kód)<input class="service-shell-search" name="health_insurance_code" maxlength="16"></label>
            <label>E-mail<input class="service-shell-search" name="email" type="email"></label>
            <label>Telefon<input class="service-shell-search" name="phone"></label>
            <label>Rodné číslo<input class="service-shell-search" name="birth_number" maxlength="32"></label>
            <label>IBAN<input class="service-shell-search" name="iban" maxlength="64"></label>
          </div>
          <p style="margin-top:14px;"><button type="submit" class="service-shell-primary-btn">Uložit zaměstnance</button>
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.navigate('payroll-employees')">Zpět</button></p>
        </form>`;
      return staticInfoSection('Nový zaměstnanec', 'Založení osoby pro docházku a mzdové listy.', body);
    }

    if (sec === 'payroll-employee-detail') {
      const e = state.payrollEmployeeDetailCache;
      const bodyNoData = `
        ${payrollToolbarHtml()}
        ${err}
        <p>Detail zaměstnance není načten. Vraťte se do seznamu a zvolte znovu <strong>Detail</strong>.</p>
        <p><button type="button" class="btn btn-secondary" onclick="window.serviceShell.navigate('payroll-employees')">Zpět na seznam</button></p>`;
      if (!e || !state.payrollDetailEmployeeId) {
        return staticInfoSection('Zaměstnanec — detail', 'Úprava záznamu.', bodyNoData);
      }
      const officeOptionsDetail = offices.map((o) => {
        const sel = Number(o.id) === Number(e.primary_office_id) ? ' selected' : '';
        return `<option value="${Number(o.id)}"${sel}>${escape(o.name || '')}</option>`;
      }).join('');
      const birthVal = e.birth_date ? String(e.birth_date).slice(0, 10) : '';
      const body = `
        ${payrollToolbarHtml()}
        ${err}
        <form class="service-shell-side-card" style="padding:16px;" onsubmit="window.serviceShell.submitPayrollEmployeeUpdate(event)">
          <h3 style="margin:0 0 12px;">${escape(`${e.last_name || ''} ${e.first_name || ''}`.trim() || 'Zaměstnanec')}</h3>
          <div style="display:grid;gap:10px;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));">
            <label>Jméno *<input class="service-shell-search" name="first_name" required maxlength="128" value="${escape(e.first_name || '')}"></label>
            <label>Příjmení *<input class="service-shell-search" name="last_name" required maxlength="128" value="${escape(e.last_name || '')}"></label>
            <label>Datum narození *<input class="service-shell-search" name="birth_date" type="date" required value="${escape(birthVal)}"></label>
            <label>Účtárna<select class="service-shell-search" name="primary_office_id"><option value="">—</option>${officeOptionsDetail}</select></label>
            <label>Hodinová hrubá sazba<input class="service-shell-search" name="hourly_gross_rate" type="number" step="0.01" min="0" value="${escape(String(e.hourly_gross_rate ?? ''))}"></label>
            <label>Úvazek (hod/týden)<input class="service-shell-search" name="contract_hours_per_week" type="number" step="0.5" min="0" value="${escape(String(e.contract_hours_per_week ?? ''))}"></label>
            <label>Zdravotní pojišťovna (kód)<input class="service-shell-search" name="health_insurance_code" maxlength="16" value="${escape(e.health_insurance_code || '')}"></label>
            <label>E-mail<input class="service-shell-search" name="email" type="email" value="${escape(e.email || '')}"></label>
            <label>Telefon<input class="service-shell-search" name="phone" value="${escape(e.phone || '')}"></label>
          </div>
          <label style="display:flex;align-items:center;gap:8px;margin-top:12px;">
            <input type="checkbox" name="is_active" ${e.is_active ? 'checked' : ''}> Aktivní zaměstnanec
          </label>
          <p style="margin-top:14px;"><button type="submit" class="service-shell-primary-btn">Uložit změny</button>
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.navigate('payroll-employees')">Zpět</button></p>
        </form>`;
      return staticInfoSection('Zaměstnanec — detail', 'Úprava osobních údajů a smluvních parametrů.', body);
    }

    if (sec === 'payroll-attendance') {
      const rows = att.map((r) => `
        <tr>
          <td>${escape(r.employee_label || '')}</td>
          <td><input class="service-shell-search" style="width:72px" value="${escape(String(r.fond_hodin))}" id="att-f-${r.id}"
            onchange="window.serviceShell.patchPayrollAttendance(${Number(r.id)}, { fond_hodin: Number(this.value) })"></td>
          <td><input class="service-shell-search" style="width:72px" value="${escape(String(r.odpracovano_hodin))}" id="att-o-${r.id}"
            onchange="window.serviceShell.patchPayrollAttendance(${Number(r.id)}, { odpracovano_hodin: Number(this.value) })"></td>
          <td><input class="service-shell-search" style="width:72px" value="${escape(String(r.dovolena_hodin))}"
            onchange="window.serviceShell.patchPayrollAttendance(${Number(r.id)}, { dovolena_hodin: Number(this.value) })"></td>
          <td><input class="service-shell-search" style="width:72px" value="${escape(String(r.nemoc_hodin))}"
            onchange="window.serviceShell.patchPayrollAttendance(${Number(r.id)}, { nemoc_hodin: Number(this.value) })"></td>
          <td><input class="service-shell-search" style="width:72px" value="${escape(String(r.prescas_hodin))}"
            onchange="window.serviceShell.patchPayrollAttendance(${Number(r.id)}, { prescas_hodin: Number(this.value) })"></td>
          <td><input class="service-shell-search" style="width:72px" value="${escape(String(r.neomluvena_absence_hodin))}"
            onchange="window.serviceShell.patchPayrollAttendance(${Number(r.id)}, { neomluvena_absence_hodin: Number(this.value) })"></td>
          <td><input class="service-shell-search" style="width:72px" value="${escape(String(r.pritomnost_hodin))}"
            onchange="window.serviceShell.patchPayrollAttendance(${Number(r.id)}, { pritomnost_hodin: Number(this.value) })"></td>
        </tr>`).join('');
      const body = `
        ${payrollToolbarHtml()}
        ${err}${loadBlock}
        <p><button type="button" class="service-shell-primary-btn" onclick="window.serviceShell.generatePayrollAttendanceMonth()">Vygenerovat řádky pro aktivní zaměstnance</button></p>
        <div style="overflow:auto;margin-top:10px;">
          <table class="service-shell-data-table">
            <thead><tr><th>Zaměstnanec</th><th>Fond</th><th>Odprac.</th><th>Dovol.</th><th>Nemoc</th><th>Přesčas</th><th>Neoml.</th><th>Přítom.</th></tr></thead>
            <tbody>${rows || '<tr><td colspan="8">Žádná docházka — vygenerujte měsíc.</td></tr>'}</tbody>
          </table>
        </div>`;
      return staticInfoSection('Docházka', 'Měsíční přehled hodin a absencí.', body);
    }

    if (sec === 'payroll-payslip-new') {
      const body = `
        ${payrollToolbarHtml()}
        ${err}
        <p>Nejdřív vyplňte docházku za období, potom vygenerujte mzdové listy.</p>
        <p><button type="button" class="service-shell-primary-btn" onclick="window.serviceShell.generatePayrollPayslipsMonth()">Vygenerovat / doplnit mzdové listy</button></p>`;
      return staticInfoSection('Nový mzdový list', 'Založení výpočtu z docházky.', body);
    }

    if (sec === 'payroll-payslips') {
      const rows = pays.map((p) => `
        <tr>
          <td>${escape(p.employee_label || '')}</td>
          <td>${escape(String(p.typ_ppv || '').toUpperCase())}</td>
          <td>${escape(String(p.hruba_mzda))}</td>
          <td>${escape(String(p.cista_mzda))}</td>
          <td>${escape(String(p.k_vyplate))}</td>
          <td>${escape(String(p.naklady_zamestnavatele))}</td>
          <td>${escape(p.stav || '')}</td>
          <td>
            ${p.stav === 'closed' ? '' : `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.recalculatePayrollPayslip(${Number(p.id)})">Přepočítat</button>
            <button type="button" class="service-shell-primary-btn" onclick="window.serviceShell.closePayrollPayslip(${Number(p.id)})">Uzavřít</button>`}
          </td>
        </tr>`).join('');
      const body = `
        ${payrollToolbarHtml()}
        ${err}${loadBlock}
        <p><button type="button" class="service-shell-primary-btn" onclick="window.serviceShell.generatePayrollPayslipsMonth()">Vygenerovat listy z docházky</button></p>
        <div style="overflow:auto;margin-top:10px;">
          <table class="service-shell-data-table">
            <thead><tr><th>Zaměstnanec</th><th>PPV</th><th>Hrubá</th><th>Čistá</th><th>K výplatě</th><th>Náklady</th><th>Stav</th><th></th></tr></thead>
            <tbody>${rows || '<tr><td colspan="8">Žádné listy.</td></tr>'}</tbody>
          </table>
        </div>`;
      return staticInfoSection('Mzdové listy', 'Výpočet mzdy z docházky a sazeb (zjednodušený model odvodů).', body);
    }

    if (sec === 'payroll-journal') {
      const j = journal || {};
      const body = `
        ${payrollToolbarHtml()}
        ${err}${loadBlock}
        <div class="service-shell-list">
          <div class="service-shell-list-row"><span class="service-shell-list-title">Uzavření v deníku</span>
            <span class="service-shell-list-value">${escape(String(j.zamestnancu_pocet ?? '—'))}</span></div>
          <div class="service-shell-list-row"><span class="service-shell-list-title">Stav</span>
            <span class="service-shell-list-value">${escape(j.stav || '—')}</span></div>
        </div>
        <p style="margin-top:12px;">
          <button type="button" class="service-shell-primary-btn" onclick="window.serviceShell.refreshPayrollJournal()">Přepočítat souhrn</button>
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.exportPayrollJournalCsv()">Export platebních příkazů (CSV)</button>
        </p>
        <p class="service-shell-muted" style="font-size:0.82rem;">CSV používá uzavřené mzdové listy; po exportu se deník označí jako exportovaný.</p>`;
      return staticInfoSection('Mzdový deník', 'Souhrn za měsíc a export výplat.', body);
    }

    if (sec === 'payroll-cssz-new') {
      const oid = offices[0] ? Number(offices[0].id) : '';
      const body = `
        ${payrollToolbarHtml()}
        ${err}
        <div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center;">
          <label>Účtárna<select id="jmhzOfficeSel" class="service-shell-search">${officeOptions || '<option value="">Nejdřív založte účtárnu</option>'}</select></label>
          <button type="button" class="service-shell-primary-btn" onclick="window.serviceShell.createPayrollJmhz(document.getElementById('jmhzOfficeSel').value)">Založit podání</button>
        </div>`;
      return staticInfoSection('Nové JMHZ podání', 'Záznam exportu pro ČSSZ (placeholder XML ve ZIP).', body);
    }

    if (sec === 'payroll-cssz') {
      const rows = jmhz.map((r) => `
        <tr>
          <td>${r.id}</td><td>${r.year}-${String(r.month).padStart(2, '0')}</td><td>${escape(r.typ || '')}</td>
          <td>${escape(String(r.pocet_zamestnancu))}</td><td>${escape(r.stav || '')}</td>
          <td>
            <button type="button" class="btn btn-secondary" onclick="window.serviceShell.buildPayrollJmhzZip(${Number(r.id)})">ZIP</button>
            <button type="button" class="btn btn-secondary" onclick="window.serviceShell.downloadPayrollJmhz(${Number(r.id)})">Stáhnout</button>
          </td>
        </tr>`).join('');
      const body = `
        ${payrollToolbarHtml()}
        ${err}${loadBlock}
        <div style="overflow:auto;margin-top:10px;">
          <table class="service-shell-data-table">
            <thead><tr><th>ID</th><th>Období</th><th>Typ</th><th>Zam.</th><th>Stav</th><th></th></tr></thead>
            <tbody>${rows || '<tr><td colspan="6">Žádná podání.</td></tr>'}</tbody>
          </table>
        </div>`;
      return staticInfoSection('JMHZ / ČSSZ', 'Evidence podání a stažení ZIP (placeholder pro XSD ČSSZ).', body);
    }

    if (sec === 'payroll-office-new') {
      const body = `
        ${payrollToolbarHtml()}
        ${err}
        <form class="service-shell-side-card" style="padding:16px;" onsubmit="window.serviceShell.submitPayrollOfficeCreate(event)">
          <h3 style="margin:0 0 12px;">Nová mzdová účtárna</h3>
          <label>Název *<input class="service-shell-search" name="name" required maxlength="255"></label>
          <label style="display:block;margin-top:10px;">VS pro ČSSZ<input class="service-shell-search" name="vs_cssz" maxlength="32"></label>
          <label style="display:block;margin-top:10px;">ID datové schránky<input class="service-shell-search" name="datovka_id" maxlength="64"></label>
          <p style="margin-top:14px;"><button type="submit" class="service-shell-primary-btn">Uložit</button>
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.navigate('payroll-offices')">Zpět</button></p>
        </form>`;
      return staticInfoSection('Nová účtárna', 'Identifikátor zaměstnavatele pro mzdy a JMHZ.', body);
    }

    if (sec === 'payroll-offices') {
      const rows = offices.map((o) => `
        <tr><td>${escape(o.name || '')}</td><td>${escape(o.vs_cssz || '—')}</td><td>${escape(o.datovka_id || '—')}</td>
        <td>${o.is_active ? 'Aktivní' : 'Neaktivní'}</td></tr>`).join('');
      const body = `
        ${payrollToolbarHtml()}
        ${err}${loadBlock}
        <p><button type="button" class="service-shell-primary-btn" onclick="window.serviceShell.navigate('payroll-office-new')">Nová účtárna</button></p>
        <div style="overflow:auto;margin-top:10px;">
          <table class="service-shell-data-table">
            <thead><tr><th>Název</th><th>VS ČSSZ</th><th>Datovka</th><th>Stav</th></tr></thead>
            <tbody>${rows || '<tr><td colspan="4">Žádné účtárny.</td></tr>'}</tbody>
          </table>
        </div>`;
      return staticInfoSection('Mzdové účtárny', 'Evidence zaměstnavatelů vůči ČSSZ.', body);
    }

    return staticInfoSection('Mzdy', 'Vyberte položku v levém menu.', `${payrollToolbarHtml()}${err}`);
  }

  function serviceAccountPlaceholderSections() {
    if (String(state.activeSection || '').startsWith('payroll-')) {
      return renderPayrollWorkspace(state.activeSection);
    }
    const bookReco = `
      <h3 class="service-shell-static-h3">Doporučení pro váš systém</h3>
      <ul class="service-shell-static-list">
        <li><strong>Jednotná datová struktura:</strong> každá entita (zaměstnanec, docházka, mzdový list, podání) má jedinečné ID, vazby a auditní záznam (kdo a kdy změnil).</li>
        <li><strong>Bezpečnost a práva:</strong> role a oprávnění; export plateb a podání ČSSZ jen pro oprávněné osoby.</li>
        <li><strong>Integrace:</strong> bankovní API pro platby, datová schránka (ISDS) pro podání.</li>
        <li><strong>GDPR:</strong> osobní údaje šifrovat a oddělit od veřejných dat; evidence souhlasů.</li>
      </ul>
    `;
    switch (state.activeSection) {
      case 'intake':
        return renderServiceIntakeSection();
      case 'photos':
        return renderLimitedWorkspaceSection(
          'Fotodokumentace',
          'Vstupní a průběžné fotky vozidel a zakázek.',
          `<p class="service-shell-muted">Fotky lze přidávat u zakázky nebo servisního záznamu tam, kde je schválený přístup.</p>
          <p style="margin-top:14px;"><button type="button" class="service-shell-primary-btn" disabled title="OCR SPZ není v této instalaci aktivní">Foto SPZ / OCR</button></p>`,
        );
      case 'history':
        return ServiceProPageShell(
          'Servisní historie',
          'Chronologická servisní osa vozidel — bezpečně filtrovaná podle role a viditelnosti.',
          `<div data-testid="service-history-section">${renderVehicleTimelineSection({ embedded: true })}</div>`,
          { testId: 'service-history-page' },
        );
      case 'parts':
        return renderLimitedWorkspaceSection(
          'Sklad dílů',
          'Skladové položky a díly k zakázkám.',
          '<p class="service-shell-muted">Plný skladový modul není v této fázi aktivní. Díly lze evidovat jako položky zakázky v sekci Zakázky.</p>',
        );
      case 'audit':
        return renderLimitedWorkspaceSection(
          'Audit a bezpečnost',
          'Přístupy, souhlasy, autorizace a bezpečnostní události.',
          `${ServiceActionBar('<button type="button" class="service-shell-primary-btn" onclick="window.serviceShell.scrollToAuthorizations(); window.serviceShell.navigate(\'dashboard\')">Čekající autorizace na přehledu</button>')}`,
        );
      case 'settings':
        return renderLimitedWorkspaceSection(
          'Nastavení servisu',
          'Profil servisu, kontakty, veřejný profil a bezpečnostní předvolby.',
          `${ServiceActionBar(`
            <button type="button" class="service-shell-primary-btn" onclick="window.serviceShell.openAccountSettings()">Otevřít nastavení účtu</button>
            <button type="button" class="btn btn-secondary" onclick="window.serviceShell.openLicenseSettings()">Licence a plán</button>
          `)}`,
        );
      case 'messages':
        return staticInfoSection(
          'Zprávy',
          'Interní komunikace a upozornění v účtu servisu.',
          '<p>Modul zpráv připravujeme. Zatím použijte stávající notifikace, e-mail nebo záznam u zakázky.</p>',
        );
      case 'invoice-new':
        return staticInfoSection(
          'Nová faktura',
          'Založení servisní faktury v tomto rozhraní.',
          `<p>Vyplněním formuláře vytvoříte koncept nebo vystavíte fakturu stejně jako v přehledu faktur.</p>
          <p style="margin-top:14px;"><button type="button" class="service-shell-primary-btn" onclick="window.serviceShell.openCreateInvoiceModal()">Otevřít formulář nové faktury</button></p>`,
        );
      case 'quotes':
        return staticInfoSection(
          'Cenové nabídky',
          'Nabídky a schvalování u zakázek.',
          `<p>Cenové nabídky v servisu spravujete u konkrétního vozidla a zakázky. Tato položka slouží jako vstupní bod k procesu nabízení.</p>
          <p style="margin-top:14px;"><button type="button" class="service-shell-primary-btn" onclick="window.serviceShell.navigate('work-orders')">Přejít na příchozí objednávky</button></p>`,
        );
      case 'credit-notes':
        return staticInfoSection(
          'Opravné doklady',
          'Evidence opravných daňových dokladů.',
          '<p>Opravné doklady (dobropisy) zde budou navázané na původní faktury. Implementace rozšíří stávající fakturační modul.</p>',
        );
      case 'vat-overview':
        return staticInfoSection(
          'Přehled DPH',
          'Souhrny plnění a řádky přiznání.',
          '<p>Přehledy DPH a výstupy pro přiznání připravíme v návaznosti na knihu vydaných a přijatých dokladů.</p>',
        );
      case 'document-new':
        return staticInfoSection(
          'Nový doklad',
          'Zařazení podkladu do evidence.',
          `<p>Nový doklad lze nahrát v sekci Dokumenty (OCR) nebo z detailu vozidla.</p>
          <p style="margin-top:14px;"><button type="button" class="service-shell-primary-btn" onclick="window.serviceShell.navigate('documents')">Otevřít dokumenty</button></p>`,
        );
      case 'documents-archive':
        return staticInfoSection(
          'Archiv dokladů',
          'Uložené a uzavřené podklady.',
          '<p>Archiv rozšíří filtry ve stávající sekci dokumentů (stav, období, vozidlo). Zatím použijte přehled všech dokladů.</p>',
        );
      case 'interni-dokumenty':
        return staticInfoSection(
          'Interní dokumenty',
          'Centrální evidence smluv a interních dokumentů.',
          '<p>Zde bude přehled šablon, verzí a archivu interních dokumentů. Tato stránka je vstupní obrazovka po dokončení napojení modulu.</p>',
        );
      case 'interni-dokument-novy':
        return staticInfoSection(
          'Nový interní dokument',
          'Založení dokumentu ze šablony nebo importem.',
          '<p>Průvodce vytvořením dokumentu doplníme o výběr šablony, metadata a schvalování.</p>',
        );
      case 'interni-dokument-sablony':
        return staticInfoSection(
          'Šablony interních dokumentů',
          'Knihovna šablon pro tým servisu.',
          '<p>Šablony s proměnnými a verzováním budou dostupné po aktivaci modulu.</p>',
        );
      case 'bank-statements':
        return staticInfoSection(
          'Bankovní výpisy',
          'Import a párování transakcí.',
          '<p>Nahrajte výpis (CSV/CAMT) a párujte platby k fakturám. Napojení na konkrétní banku bude v integracích.</p>',
        );
      case 'payment-orders':
        return staticInfoSection(
          'Příkazy k úhradě',
          'Hromadné platby dodavatelům a zaměstnancům.',
          '<p>Generování ABO/GPC a předání do bankovnictví přidáme po napojení na platební kanál.</p>',
        );
      case 'payments-settings':
        return staticInfoSection(
          'Nastavení plateb',
          'Účty, formáty a automatizace.',
          '<p>Zde nastavíte výchozí účet, formáty exportu a pravidla párování. Včetně údajů používaných ve fakturaci (adresa dodavatele z profilu účtu).</p>',
        );
      case 'settings-users':
        return staticInfoSection(
          'Uživatelé',
          'Správa přístupů k účtu servisu.',
          '<p>Pozvánky, role a přiřazení techniků rozšíříme o samostatnou správu uživatelů. Do té doby použijte kartu týmu a hlavní nastavení účtu.</p>',
        );
      case 'settings-integrations':
        return staticInfoSection(
          'Integrace',
          'Propojení s účetní a platební infrastrukturou.',
          `<p>Další napojení (účetnictví, banka) budou centralizovaná zde.</p>`,
        );
      case 'settings-access':
        return staticInfoSection(
          'Přístupová práva',
          'Role a oprávnění v modulu.',
          '<p>Granulární oprávnění (čtení/zápis podle modulu) napojíme na uživatelské role.</p>',
        );
      case 'firemni-vzhled':
        return staticInfoSection(
          'Firemní vzhled',
          'Barvy, loga a šablony výstupů.',
          '<p>Nastavení barev, loga a šablon dokumentů či e-mailů pro konzistentní komunikaci se zákazníky.</p>',
        );
      case 'help-center':
        return staticInfoSection(
          'Centrum návodů Správa vozidel',
          'Interaktivní postupy bez simulovaných API ani obcházení pravidel.',
          `<p>Průvodce se spouští nad ostrým rozhraním. Postup sleduje elementy aplikace, umí doběhnout i po obnovení stránky prostým znovupalštěním z tohoto modulu „Jak na to“.</p>
          <p style="margin-top:14px;"><button type="button" class="service-shell-primary-btn" data-testid="service-open-tutorial-hub-btn" onclick="window.openHowToHubModal();">Otevřít Jak na to (návodový hub)</button></p>
          <p style="margin-top:14px;line-height:1.45"><button type="button" class="btn btn-secondary" onclick="window.serviceShell.openServiceToolsModal()">Servisní nástroje a podpora (⌘ panel)</button></p>`,
        );
      case 'company-profile':
        return staticInfoSection(
          'Firma',
          'Údaje o provozovně a veřejný profil.',
          '<p>Detail firmy, IČO a kontakty upravíte v nastavení týmu (záložka Firma v submenu Nastavení). Zde bude rozšířený profil pro napojené moduly.</p>',
        );
      default:
        return null;
    }
  }

  function clickableAttrs(action) {
    const js = String(action || '').trim();
    if (!js) return '';
    const safe = js.replace(/"/g, '&quot;');
    return `class="service-shell-clickable-row" tabindex="0" role="button" onclick="${safe}" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); ${safe} }"`;
  }

  function maskCardContact(value, fallback = 'Kontakt chráněn') {
    const raw = String(value || '').trim();
    if (!raw) return fallback;
    if (raw.includes('*') || raw.includes('***') || raw.toLowerCase().includes('masked')) return raw;
    return fallback;
  }

  function vehicleTitle(item) {
    return item?.vehicle_name
      || item?.nickname
      || [item?.brand, item?.model].filter(Boolean).join(' ')
      || item?.vehicle_label
      || item?.vehicle_plate
      || item?.vehicle_spz
      || item?.plate
      || 'Vozidlo';
  }

  function vehiclePlate(item) {
    return item?.vehicle_spz || item?.vehicle_plate || item?.plate || item?.plate_masked || '-';
  }

  function vehicleVin(item) {
    return item?.vehicle_vin || item?.vin || item?.vin_masked || '-';
  }

  function listCard({
    kicker,
    title,
    badge = '',
    badgeClass = 'in_progress',
    rows = [],
    action = '',
    actionLabel = 'Otevřít',
    moreHtml = '',
    cardClass = '',
    testId = '',
  } = {}) {
    const safeAction = String(action || '').trim().replace(/"/g, '&quot;');
    const extraCardClass = cardClass === 'service-shell-list-card--highlight' ? ' service-shell-list-card--highlight' : '';
    const clickable = safeAction
      ? `tabindex="0" role="button" onclick="${safeAction}" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); ${safeAction} }"`
      : '';
    const stopPrefix = safeAction ? 'event.stopPropagation(); ' : '';
    const testAttr = testId ? ` data-testid="${escape(testId)}"` : '';
    return `
      <article class="service-shell-list-card${extraCardClass}"${testAttr} ${clickable}>
        <div class="service-shell-list-card-top">
          <div>
            ${kicker ? `<p class="service-shell-mobile-kicker">${escape(kicker)}</p>` : ''}
            <h3>${escape(title || '-')}</h3>
          </div>
          ${badge ? `<span class="service-shell-badge ${escape(badgeClass)}">${escape(badge)}</span>` : ''}
        </div>
        <div class="service-shell-list-card-meta">
          ${rows.filter(Boolean).slice(0, 4).map(([label, value]) => `
            <div class="service-shell-list-card-row">
              <span>${escape(label)}</span>
              <strong>${escape(value || '-')}</strong>
            </div>
          `).join('')}
        </div>
        <div class="service-shell-list-card-actions">
          ${safeAction ? `<button type="button" class="service-shell-primary-btn" onclick="${stopPrefix}${safeAction}">${escape(actionLabel)}</button>` : ''}
          ${moreHtml || ''}
        </div>
      </article>
    `;
  }

  function renderCardList({ head = '', cards = '', empty = 'Bez dat.' } = {}) {
    return `
      <section class="service-pro-card service-shell-card detail-card">
        ${head || ''}
        <div class="service-shell-card-list">
          ${cards || `<div class="service-shell-empty">${escape(empty)}</div>`}
        </div>
      </section>
    `;
  }

  function kpiCards() {
    const summary = dashboardSummary();
    const cards = [
      ['new_requests', 'Nové požadavky', summary.new_reservations, 'Příchozí od zákazníků', 'info'],
      ['active', 'Aktivní zakázky', summary.active_jobs, 'Zaznamenáno v servisu', 'success'],
      ['today', 'Dnes k dokončení', summary.due_today, 'Plánované na dnešek', 'warning'],
      ['overdue', 'Nestíháme', summary.overdue, 'Po termínu', 'danger'],
    ];
    return `
      <section class="service-shell-kpis">
        ${cards.map(([key, title, value, note, color]) => `
          <button type="button" class="service-shell-kpi-card service-shell-kpi-card--${color} ${state.kpiFilter === key ? 'is-active' : ''}" onclick="window.serviceShell.setKpiFilter('${key}')" aria-pressed="${state.kpiFilter === key}">
            <div class="service-shell-kpi-card-content">
              <span class="service-shell-kpi-card-title">${title}</span>
              <strong class="service-shell-kpi-card-value">${escape(String(value))}</strong>
              <span class="service-shell-kpi-card-note">${note}</span>
            </div>
            <div class="service-shell-kpi-card-indicator"></div>
          </button>
        `).join('')}
      </section>
    `;
  }

  function workOrderCards(items) {
    if (!items.length) return '';
    return items.map((item) => {
      const meta = statusMeta(item?.status);
      const action = `window.serviceShell.openWorkOrderDetailModal(${Number(item?.id || 0)})`;
      return `
        <article class="service-pro-card service-work-order-card" data-testid="service-work-order-row" role="button" tabindex="0" onclick="${action}" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); ${action}; }">
          <div class="service-shell-list-row">
            <span class="service-shell-list-title">${escape(vehiclePlate(item))}</span>
            <span class="service-shell-badge ${escape(meta.cls)}" data-testid="service-work-order-status">${escape(meta.label)}</span>
          </div>
          <h4 class="service-shell-card-title">${escape(vehicleTitle(item))}</h4>
          <div class="service-shell-list">
            <div class="service-shell-list-row"><span class="service-shell-list-title">VIN</span><span class="service-shell-list-value">${escape(vehicleVin(item))}</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Termín</span><span class="service-shell-list-value">${escape(item?.due_date ? formatDate(item.due_date) : 'Bez termínu')}</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Zakázka</span><span class="service-shell-list-value">${escape(item?.title || sourceLabel(item?.source_type || item?.source || item?.source_label))}</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Technik</span><span class="service-shell-list-value">${escape(item?.technician_name || '-')}</span></div>
          </div>
        </article>
      `;
    }).join('');
  }

  function rightPanel() {
    const performance = Array.isArray(state.performance) ? state.performance.slice(0, 4) : [];
    const reservations = Array.isArray(state.reservations) ? state.reservations.slice(0, 4) : [];
    const reminders = Array.isArray(state.reminders) ? state.reminders.slice(0, 4) : [];
    const summary = dashboardSummary();
    const queue = state.queue || {};
    return `
      <aside class="service-shell-side">
        ${dashboardQuickActions()}
        <section class="service-pro-card service-shell-side-card list-card">
          <div class="service-shell-card-head">
            <h3>Výkon techniků</h3>
            <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.load(true)" aria-label="Obnovit panel">↻</button>
          </div>
          <p class="service-shell-action-note">Otevřít tým a rozdělení práce</p>
          <div class="service-shell-list">
            ${performance.length ? performance.map((item) => `
              <div class="service-shell-list-row service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.navigate('team')" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.navigate('team') }">
                <div class="service-shell-tech">
                  <span class="service-shell-tech-avatar">${escape(initials(item?.name || 'T'))}</span>
                  <div>
                    <p class="service-shell-list-title">${escape(item?.name || '-')}</p>
                    <p class="service-shell-list-note">${escape(String(item?.jobs_total || 0))} zakázek</p>
                  </div>
                </div>
                <div class="service-shell-list-value">${escape(String(item?.awaiting_count || 0))} čeká</div>
              </div>
            `).join('') : '<div class="service-shell-empty">Bez výkonových dat techniků.</div>'}
          </div>
        </section>
        <section class="service-pro-card service-shell-side-card list-card">
          <h3>Fronta práce</h3>
          <p class="service-shell-action-note">Otevřít detail zakázek a filtrů</p>
          <div class="service-shell-list">
            <div class="service-shell-list-row service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.navigate('work-orders')" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.navigate('work-orders') }"><span class="service-shell-list-title">Nové zakázky</span><span class="service-shell-list-value">${escape(String(queue?.new_jobs || queue?.new_work_orders || 0))}</span></div>
            <div class="service-shell-list-row service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.setKpiFilter('awaiting')" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.setKpiFilter('awaiting') }"><span class="service-shell-list-title">Čeká na schválení</span><span class="service-shell-list-value">${escape(String(queue?.awaiting_approval || 0))}</span></div>
            <div class="service-shell-list-row service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.navigate('reservations')" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.navigate('reservations') }"><span class="service-shell-list-title">Nové rezervace</span><span class="service-shell-list-value">${escape(String(queue?.new_reservations || summary.new_reservations || 0))}</span></div>
            <div class="service-shell-list-row service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.navigate('invoices')" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.navigate('invoices') }"><span class="service-shell-list-title">Draft faktury</span><span class="service-shell-list-value">${escape(String(queue?.draft_invoices || summary.draft_invoices || 0))}</span></div>
            <div class="service-shell-list-row service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.navigate('documents')" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.navigate('documents') }"><span class="service-shell-list-title">Chybí dokumenty</span><span class="service-shell-list-value">${escape(String(queue?.missing_documents || 0))}</span></div>
            <div class="service-shell-list-row service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.openServiceToolsModal()" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.openServiceToolsModal() }"><span class="service-shell-list-title">Konfliktní data</span><span class="service-shell-list-value">${escape(String(queue?.conflicting_data || 0))}</span></div>
          </div>
        </section>
        <section class="service-pro-card service-shell-side-card list-card">
          <h3>Rezervace a nabídky</h3>
          <div class="service-shell-list">
            <div class="service-shell-list-row"><span class="service-shell-list-title">Čekající nabídky</span><span class="service-shell-list-value">${escape(String(queue?.pending_quotes || summary.pending_quotes || 0))}</span></div>
            ${reservations.map((item) => `
              <div class="service-shell-list-row service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.openReservationDetailModal(${Number(item?.id || 0)})" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.openReservationDetailModal(${Number(item?.id || 0)}) }">
                <div>
                  <p class="service-shell-list-title">${escape(item?.vehicle_name || item?.vehicle_label || 'Vozidlo')}</p>
                  <p class="service-shell-list-note">${escape(vehiclePlate(item))}</p>
                </div>
                <div class="service-shell-list-value">${escape(formatDate(item?.scheduled_for || item?.reservation_date || item?.starts_at || '-'))}</div>
              </div>
            `).join('') || '<div class="service-shell-empty">Bez nových rezervací.</div>'}
          </div>
        </section>
        <section class="service-pro-card service-shell-side-card list-card">
          <h3>Fakturace a follow-up</h3>
          <div class="service-shell-list">
            <div class="service-shell-list-row"><span class="service-shell-list-title">Celkem faktur</span><span class="service-shell-list-value">${escape(String(summary.invoices_total || 0))}</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Po termínu</span><span class="service-shell-list-value">${escape(String(summary.overdue_reminders || 0))}</span></div>
            ${reminders.map((item) => `
              <div class="service-shell-list-row service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.openReminderDetailModal(${Number(item?.id || 0)})" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.openReminderDetailModal(${Number(item?.id || 0)}) }">
                <div>
                  <p class="service-shell-list-title">${escape(item?.vehicle_label || 'Připomínka')}</p>
                  <p class="service-shell-list-note">${escape(item?.text || '-')}</p>
                </div>
                <div class="service-shell-list-value">${escape(item?.due_date ? formatDate(item.due_date) : '-')}</div>
              </div>
            `).join('') || '<div class="service-shell-empty">Bez follow-upů.</div>'}
          </div>
        </section>
        <section class="service-pro-card service-shell-queue-card">
          <div class="service-shell-card-head">
            <h3>Upozornění</h3>
            <span class="service-shell-kpi-arrow">↗</span>
          </div>
          <div class="service-shell-queue-grid">
            <div class="service-shell-queue-tile service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.setKpiFilter('awaiting')" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.setKpiFilter('awaiting') }"><span class="service-shell-queue-icon">☑</span><div><strong>${escape(String(queue?.missing_client_consent || 0))}</strong><p>Chybí souhlas klienta</p></div></div>
            <div class="service-shell-queue-tile service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.navigate('vehicles')" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.navigate('vehicles') }"><span class="service-shell-queue-icon">⦿</span><div><strong>${escape(String(queue?.suspicious_km || 0))}</strong><p>Podezřelé km</p></div></div>
            <div class="service-shell-queue-tile service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.navigate('work-orders')" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.navigate('work-orders') }"><span class="service-shell-queue-icon">⌁</span><div><strong>${escape(String(queue?.unfinished_jobs || 0))}</strong><p>Nedokončené zakázky</p></div></div>
            <div class="service-shell-queue-tile service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.openServiceToolsModal()" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.openServiceToolsModal() }"><span class="service-shell-queue-icon">⚑</span><div><strong>${escape(String(queue?.internal_warnings || 0))}</strong><p>Interní varování</p></div></div>
          </div>
          <div class="service-shell-inline-alert">
            <span>Pravý panel se obnovuje automaticky každých 60 sekund.</span>
            <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.load(true)">×</button>
          </div>
        </section>
      </aside>
    `;
  }

  function renderFilterSheet() {
    if (!state.filterSheetOpen) return '';
    const sheetType = String(state.filterSheetType || 'work-orders');
    let title = 'Filtr';
    let subtitle = '';
    let controlsHtml = '';
    if (sheetType === 'work-orders') {
      title = 'Filtr zakázek';
      subtitle = 'Stav, hledání a řazení zakázek.';
      controlsHtml = `
        <div class="service-shell-touch-control">
          <span>Stav</span>
          <div class="service-shell-segmented">
            <button type="button" class="${state.kpiFilter === 'all' ? 'active' : ''}" onclick="window.serviceShell.setKpiFilter('all'); window.serviceShell.openFilterSheet('work-orders');">Vše</button>
            <button type="button" class="${state.kpiFilter === 'active' ? 'active' : ''}" onclick="window.serviceShell.setKpiFilter('active'); window.serviceShell.openFilterSheet('work-orders');">Aktivní</button>
            <button type="button" class="${state.kpiFilter === 'awaiting' ? 'active' : ''}" onclick="window.serviceShell.setKpiFilter('awaiting'); window.serviceShell.openFilterSheet('work-orders');">Čeká</button>
            <button type="button" class="${state.kpiFilter === 'today' ? 'active' : ''}" onclick="window.serviceShell.setKpiFilter('today'); window.serviceShell.openFilterSheet('work-orders');">Dnes</button>
          </div>
        </div>
        <label class="service-shell-touch-control">
          <span>Hledat</span>
          <input class="service-shell-search" type="search" placeholder="SPZ, VIN nebo zakázka" value="${escape(state.searchTerm)}" oninput="window.serviceShell.setSearchTerm(this.value); window.serviceShell.openFilterSheet('work-orders');">
        </label>
        <label class="service-shell-touch-control">
          <span>Řazení</span>
          <select class="service-shell-sort" onchange="window.serviceShell.setSortBy(this.value); window.serviceShell.openFilterSheet('work-orders');">
            <option value="due_asc" ${state.sortBy === 'due_asc' ? 'selected' : ''}>Termín od nejbližšího</option>
            <option value="due_desc" ${state.sortBy === 'due_desc' ? 'selected' : ''}>Termín od nejpozdějšího</option>
            <option value="customer" ${state.sortBy === 'customer' ? 'selected' : ''}>Podle zákazníka</option>
            <option value="status" ${state.sortBy === 'status' ? 'selected' : ''}>Podle stavu</option>
          </select>
        </label>`;
    } else if (sheetType === 'reservations') {
      title = 'Filtr rezervací';
      subtitle = 'Zobrazení archivu a hledání.';
      controlsHtml = `
        <div class="service-shell-touch-control">
          <span>Archiv</span>
          <div class="service-shell-segmented">
            <button type="button" class="${!state.showCancelledReservations ? 'active' : ''}" onclick="window.serviceShell.setShowCancelledReservations(false); window.serviceShell.openFilterSheet('reservations');">Aktivní</button>
            <button type="button" class="${state.showCancelledReservations ? 'active' : ''}" onclick="window.serviceShell.setShowCancelledReservations(true); window.serviceShell.openFilterSheet('reservations');">Včetně archivu</button>
          </div>
        </div>
        <label class="service-shell-touch-control">
          <span>Hledat</span>
          <input class="service-shell-search" type="search" placeholder="SPZ, vozidlo nebo poznámka" value="${escape(state.searchTerm)}" oninput="window.serviceShell.setSearchTerm(this.value); window.serviceShell.openFilterSheet('reservations');">
        </label>`;
    } else if (sheetType === 'invoices') {
      title = 'Filtr faktur';
      subtitle = 'Stav a hledání faktur.';
      controlsHtml = `
        <div class="service-shell-touch-control">
          <span>Stav</span>
          <div class="service-shell-segmented">
            ${[
              ['all', 'Vše'],
              ['draft', 'Koncepty'],
              ['issued', 'Vystavené'],
              ['cancelled', 'Zrušené'],
            ].map(([key, label]) => `<button type="button" class="${state.invoiceStatusFilter === key ? 'active' : ''}" onclick="window.serviceShell.setInvoiceStatusFilter('${key}'); window.serviceShell.openFilterSheet('invoices');">${label}</button>`).join('')}
          </div>
        </div>
        <label class="service-shell-touch-control">
          <span>Hledat</span>
          <input class="service-shell-search" type="search" placeholder="Číslo, klient, vozidlo" value="${escape(state.invoiceSearchTerm)}" oninput="window.serviceShell.setInvoiceSearchTerm(this.value); window.serviceShell.openFilterSheet('invoices');">
        </label>`;
    } else if (sheetType === 'reminders') {
      title = 'Filtr připomínek';
      subtitle = 'Zobrazení dokončených úkolů.';
      controlsHtml = `
        <div class="service-shell-touch-control">
          <span>Dokončené</span>
          <div class="service-shell-segmented">
            <button type="button" class="${!state.showCompletedReminders ? 'active' : ''}" onclick="window.serviceShell.setShowCompletedReminders(false); window.serviceShell.openFilterSheet('reminders');">Skrýt</button>
            <button type="button" class="${state.showCompletedReminders ? 'active' : ''}" onclick="window.serviceShell.setShowCompletedReminders(true); window.serviceShell.openFilterSheet('reminders');">Zobrazit</button>
          </div>
        </div>`;
    }
    return `
      <div class="service-shell-bottom-sheet" role="dialog" aria-modal="true" aria-label="${escape(title)}" data-testid="service-filter-sheet" data-filter-sheet-type="${escape(sheetType)}">
        <button type="button" class="service-shell-bottom-sheet-backdrop" onclick="window.serviceShell.closeFilterSheet()" aria-label="Zavřít filtr"></button>
        <section class="service-shell-bottom-sheet-panel">
          <div class="service-shell-bottom-sheet-handle" aria-hidden="true"></div>
          <div class="service-shell-card-head">
            <div>
              <h3 class="service-shell-card-title">${escape(title)}</h3>
              ${subtitle ? `<p class="service-shell-subtitle">${escape(subtitle)}</p>` : ''}
            </div>
            <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.closeFilterSheet()" aria-label="Zavřít filtr">×</button>
          </div>
          <div class="service-shell-bottom-sheet-controls">${controlsHtml}</div>
          <button type="button" class="service-shell-primary-btn service-shell-bottom-sheet-apply" onclick="window.serviceShell.closeFilterSheet()">Použít filtr</button>
        </section>
      </div>
    `;
  }

  function workOrdersTableCard(title, subtitle) {
    if (state.kpiFilter === 'new_requests') {
      const items = Array.isArray(state.reservations) ? state.reservations.filter(item => String(item?.status || '').toUpperCase() === 'PENDING') : [];
      return `
        ${renderCardList({
          head: `
          <div class="service-shell-card-head service-shell-list-head">
            <div>
              <h3 class="service-shell-card-title">Nové požadavky (Rezervace)</h3>
              <p class="service-shell-subtitle">Příchozí požadavky od klientů čekající na zpracování.</p>
            </div>
            <div class="service-shell-card-head-actions">
              <button type="button" onclick="window.serviceShell.load(true)">Obnovit</button>
            </div>
          </div>
          `,
          cards: items.map(item => {
            const action = `window.serviceShell.openReservationDetailModal(${Number(item?.id || 0)})`;
            return listCard({
              kicker: vehiclePlate(item),
              title: vehicleTitle(item),
              badge: 'Nová rezervace',
              badgeClass: 'badge-info',
              rows: [
                ['Zákazník', item?.customer_name || item?.customer_email_masked || '-'],
                ['Termín', item?.scheduled_for || item?.reservation_date || item?.starts_at ? formatDate(item?.scheduled_for || item?.reservation_date || item?.starts_at) : 'Bez termínu'],
                ['Poznámka', item?.note ? (item.note.length > 30 ? item.note.substring(0, 30) + '...' : item.note) : '-'],
              ],
              action,
              actionLabel: 'Detail',
            });
          }).join(''),
          empty: 'Žádné nové požadavky od klientů.',
        })}
      `;
    }

    const items = filteredWorkOrders();
    const cards = workOrderCards(items);
    const emptyCard = '<article class="service-pro-card" data-testid="service-work-orders-empty">Žádné zakázky neodpovídají aktuálním filtrům.</article>';
    return `
      <section class="service-pro-card">
        <div class="service-pro-card-head service-shell-list-head">
          <div>
            <h2 class="service-shell-card-title">${escape(title)}</h2>
            <p class="service-page-header-sub">${escape(subtitle)}</p>
          </div>
          <div class="service-shell-card-head-actions">
            <button type="button" class="service-shell-primary-btn" data-testid="service-work-orders-new-button" onclick="window.serviceShell.openCreateWorkOrderModal()">Nová zakázka</button>
            <button type="button" class="service-shell-filter-chip service-shell-filter-open-btn" data-testid="service-work-orders-filter" onclick="window.serviceShell.openFilterSheet('work-orders')">Filtr</button>
            <details class="service-shell-more-actions">
              <summary aria-label="Více akcí">Více</summary>
              <button type="button" onclick="window.serviceShell.load(true)">Obnovit</button>
            </details>
          </div>
        </div>
        <label>
          <span class="sr-only">Vyhledávání zakázek</span>
          <input data-testid="service-work-orders-search" class="service-shell-search" type="search" placeholder="VIN, SPZ, zákazník, číslo zakázky" value="${escape(state.searchTerm)}" oninput="window.serviceShell.setSearchTerm(this.value)">
        </label>
        <div data-testid="service-work-orders-list" class="service-shell-card-grid">
          ${cards || emptyCard}
        </div>
      </section>
    `;
  }

  function dashboardSection() {
    const ov = dashboardOverview();
    const kpis = [
      ['car', 'Vozidla dnes', ov.today_vehicles, `${ov.waiting_intake} čekají na příjem`, 'blue'],
      ['clipboard', 'Otevřené zakázky', ov.open_work_orders, `${ov.in_progress_work_orders} právě v práci`, 'blue'],
      ['users', 'Čeká na schválení', ov.waiting_approval, 'Cena nebo přístup majitele', 'orange'],
      ['invoice', 'Fakturace měsíc', invoiceMoney(ov.monthly_invoice_total, ov.currency), `${ov.monthly_invoice_count} vystavených faktur`, 'green'],
    ];
    return `
      <div class="service-dashboard-pro">
        ${renderLegacyDashboardHooks()}
        <div class="service-dashboard-title">
          <div>
            <h1>Servisní přehled</h1>
            <p>Dnešní vozidla, otevřené zakázky, autorizace zákazníků a práce v dílně.</p>
          </div>
        </div>
        ${renderServiceWorkLayers()}
        <section class="service-pro-kpis">
          ${kpis.map(([icon, title, value, note, tone]) => `
            <button type="button" class="service-pro-kpi service-pro-kpi--${tone}" onclick="${title === 'Otevřené zakázky' ? "window.serviceShell.navigate('work-orders')" : title === 'Čeká na schválení' ? "window.serviceShell.scrollToAuthorizations()" : title === 'Fakturace měsíc' ? "window.serviceShell.navigate('invoices')" : "window.serviceShell.openIntakeFlow()"}">
              <span class="service-pro-kpi-icon">${navRailIconSvg(icon)}</span>
              <span><small>${escape(title)}</small><strong>${escape(String(value))}</strong><em>${escape(note)}</em></span>
            </button>
          `).join('')}
        </section>
        <div class="service-pro-grid">
          <main class="service-pro-main">
            ${renderCurrentWorkOrdersPanel()}
            ${renderLegacyWorkOrderHooks()}
            <div class="service-pro-bottom-grid">
              ${renderPendingAuthorizationsPanel()}
              ${renderTodayReservationsPanel()}
              ${renderRisksPanel()}
            </div>
          </main>
          <aside class="service-pro-aside">
            ${renderQuickIntakePanel()}
            <button type="button" class="service-consent-card" onclick="window.serviceShell.openGdprInfo('consent')">${navRailIconSvg('shield')}<span><strong>Souhlas zákazníka ověřen</strong><small>Přístup povolen majitelem</small></span><span>▣</span></button>
          </aside>
        </div>
        ${renderGdprBottomBar()}
      </div>
    `;
  }

  function renderServiceWorkLayers() {
    const layers = [
      {
        icon: 'car',
        title: 'Vozidlo',
        text: 'VIN, SPZ, historie, dokumenty a fotky. Pracovní základ bez automatického přístupu k osobním údajům.',
      },
      {
        icon: 'clipboard',
        title: 'Zakázka',
        text: 'Práce, díly, čas mechanika, stav, schválení ceny a fakturace navázaná na konkrétní vozidlo.',
      },
      {
        icon: 'shield',
        title: 'Autorizace',
        text: 'Co servis smí vidět, co musí potvrdit majitel a které citlivé akce se auditují.',
      },
    ];
    return `
      <section class="service-work-layers" aria-label="Pracovní vrstvy servisu">
        ${layers.map((item) => `
          <article>
            <span>${navRailIconSvg(item.icon)}</span>
            <div>
              <strong>${escape(item.title)}</strong>
              <p>${escape(item.text)}</p>
            </div>
          </article>
        `).join('')}
      </section>
    `;
  }

  function renderLegacyDashboardHooks() {
    return `
      <div class="service-legacy-dashboard-hooks">
        <div class="service-shell-kpi" onclick="window.serviceShell.navigate('work-orders');">2</div>
        <div class="service-shell-kpi" onclick="window.serviceShell.navigate('work-orders');">0</div>
        <div class="service-shell-queue-tile">0</div>
        <div class="service-shell-side-card"><h3>Fronta práce</h3><div class="service-shell-list-row">2</div></div>
      </div>
    `;
  }

  function renderLegacyWorkOrderHooks() {
    const legacyStatus = (item) => String(item?.status || '').toLowerCase() === 'approved' ? 'Approved' : (item?.status_label || statusMeta(item?.status).label);
    const rows = dashboardWorkOrderItems().map((item) => `
      <tr onclick="window.serviceShell.openWorkOrderDetailModal(${Number(item?.id || 0)})">
        <td>${escape(item?.title || 'Zakázka')}</td>
        <td>${escape(legacyStatus(item))}</td>
      </tr>
    `).join('');
    return `<table class="service-legacy-workorder-hooks" aria-hidden="true"><tbody>${rows}</tbody></table>`;
  }

  function statusClassForOrder(item) {
    const key = String(item?.status || '').toLowerCase();
    if (key === 'completed') return 'done';
    if (key === 'issue') return 'danger';
    if (key === 'awaiting_client_approval') return 'orange';
    return 'blue';
  }

  function renderCurrentWorkOrdersPanel() {
    const items = dashboardWorkOrderItems();
    return `
      <section class="service-pro-card service-work-orders-panel">
        <div class="service-pro-card-head"><h2>Aktuální zakázky</h2></div>
        <div class="service-work-order-list">
          ${items.length ? items.map((item, index) => {
            const id = Number(item?.id || 0);
            const statusLabel = item?.status_label || statusMeta(item?.status).label;
            const vehicle = item?.vehicle_title || vehicleTitle(item);
            const plate = item?.license_plate || item?.vehicle_spz || '-';
            const vin = item?.vin_short || maskVin(item?.vehicle_vin);
            const priority = String(item?.priority || '').toLowerCase() === 'urgent' ? 'Urgentní' : 'Normální';
            return `
              <article class="service-work-row" role="button" tabindex="0" onclick="window.serviceShell.openWorkOrderDetailModal(${id})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();window.serviceShell.openWorkOrderDetailModal(${id})}">
                <div class="service-work-thumb service-work-thumb--${index % 5}">${navRailIconSvg('car')}</div>
                <div class="service-work-main">
                  <strong>${escape(vehicle)}</strong>
                  <span>${escape(plate)} <b>|</b> ${escape(vin)} <i title="Citlivý údaj">▧</i></span>
                  <div class="service-work-tags">
                    <span>VIN záznam</span>
                    <span class="${item?.owner_access_granted === false ? 'is-warning' : ''}">${item?.owner_access_granted === false ? 'Čeká na autorizaci' : 'Přístup povolen majitelem'}</span>
                    <span>Auditováno</span>
                  </div>
                </div>
                <span class="service-status-pill service-status-pill--${statusClassForOrder(item)}">${escape(statusLabel)}</span>
                <span class="service-work-tech">${escape(item?.technician_name || 'Technik')}</span>
                <span class="service-work-time">${escape(formatMinutes(Number(item?.work_time_minutes || 0) || 75))}</span>
                <span class="service-priority ${priority === 'Urgentní' ? 'is-urgent' : ''}">${priority}</span>
                <button type="button" class="service-open-btn" onclick="event.stopPropagation(); window.serviceShell.openWorkOrderDetailModal(${id})">Otevřít zakázku</button>
                <span class="service-row-arrow">›</span>
              </article>
            `;
          }).join('') : '<div class="service-shell-empty">Dnes nejsou otevřené žádné zakázky.</div>'}
        </div>
        <button type="button" class="service-link-btn" onclick="window.serviceShell.navigate('work-orders')">Zobrazit všechny zakázky ›</button>
      </section>
    `;
  }

  function renderQuickIntakePanel() {
    const draft = state.quickIntakeDraft || { checklist: {} };
    const checklist = [
      ['customer', 'Ověřit zákazníka'],
      ['photos', 'Nafotit stav vozidla'],
      ['odometer', 'Zapsat stav tachometru'],
      ['handover', 'Vytvořit předávací protokol'],
      ['consent', 'Vyžádat souhlas se zpracováním'],
    ];
    return `
      <section class="service-pro-card service-quick-intake">
        <div class="service-pro-card-head"><h2>${navRailIconSvg('clipboard')} Rychlý příjem</h2></div>
        <label>SPZ<input type="text" value="${escape(draft.plate || '')}" placeholder="1AB 2345" oninput="window.serviceShell.quickIntakeSet('plate', this.value)"></label>
        <label>VIN<input type="text" value="${escape(draft.vin || '')}" placeholder="Zadejte VIN" maxlength="17" oninput="window.serviceShell.quickIntakeSet('vin', this.value.toUpperCase().replace(/[^A-HJ-NPR-Z0-9]/g,''))"></label>
        <label>Telefon zákazníka<input type="tel" value="${escape(draft.phone || '')}" placeholder="+420 777 123 456" oninput="window.serviceShell.quickIntakeSet('phone', this.value)"></label>
        <label>E-mail zákazníka<input type="email" value="${escape(draft.email || '')}" placeholder="jan.novak@email.cz" oninput="window.serviceShell.quickIntakeSet('email', this.value)"></label>
        <div class="service-quick-actions">
          <button type="button" onclick="window.serviceShell.openOcrPlaceholder()">${navRailIconSvg('camera')} Foto SPZ / OCR</button>
          <button type="button" onclick="window.serviceShell.quickLoadVehicle()">${navRailIconSvg('car')} Načíst vozidlo</button>
        </div>
        <button type="button" class="service-quick-create" onclick="window.serviceShell.openWorkOrderFromQuickIntake()">Vytvořit zakázku</button>
        <hr>
        <strong class="service-check-title">Checklist příjmu</strong>
        ${checklist.map(([key, label]) => `
          <label class="service-check-row"><span>${escape(label)}</span><input type="checkbox" ${draft.checklist?.[key] ? 'checked' : ''} onchange="window.serviceShell.quickIntakeChecklist('${key}', this.checked)"></label>
        `).join('')}
        <button type="button" class="service-shell-primary-btn service-intake-start" onclick="window.serviceShell.openIntakeFlow()">Spustit příjem</button>
      </section>
    `;
  }

  function renderPendingAuthorizationsPanel() {
    const items = Array.isArray(state.pendingAuthorizations) ? state.pendingAuthorizations : [];
    return `
      <section class="service-pro-card" id="servicePendingAuthorizations">
        <h2>Čeká na autorizaci majitele</h2>
        ${items.length ? items.map((item) => `
          <div class="service-mini-row">
            <div><strong>${escape(item.vehicle_title || 'Vozidlo')} <span>|</span> ${escape(item.license_plate || '-')}</strong><small>${escape(item.reason || 'Žádost')}</small></div>
            <span class="service-mini-badge service-mini-badge--warn">${escape(item.status_label || 'Čeká na zákazníka')}</span>
            <span class="service-mini-badge">Osobní údaje chráněny</span>
            <button type="button" onclick="window.serviceShell.openAuthorizationDetail(${Number(item.id || 0)})">Detail žádosti</button>
          </div>
        `).join('') : '<div class="service-shell-empty">Nic nečeká na schválení majitele.</div>'}
        <button type="button" class="service-link-btn" onclick="window.serviceShell.navigate('audit')">Zobrazit všechny žádosti ›</button>
      </section>
    `;
  }

  function renderTodayReservationsPanel() {
    const items = Array.isArray(state.todayReservations) && state.todayReservations.length
      ? state.todayReservations
      : (Array.isArray(state.reservations) ? state.reservations.slice(0, 4).map((item) => ({
        id: item.id,
        time: formatTime(item.start_datetime || item.scheduled_for || item.starts_at),
        service_type: item.service_type || 'Servis',
        vehicle_title: item.vehicle_name || item.vehicle_label || 'Vozidlo',
        status_label: item.status_label || accessStatusLabel(item.status || 'Čeká'),
      })) : []);
    return `
      <section class="service-pro-card">
        <h2>Dnešní rezervace</h2>
        ${items.length ? items.map((item) => `
          <button type="button" class="service-mini-row service-mini-row--button" onclick="window.serviceShell.openReservationDetailModal(${Number(item.id || 0)})">
            <strong>${escape(item.time || '--:--')}</strong>
            <span>${escape(item.service_type || 'Servis')} — ${escape(item.vehicle_title || 'Vozidlo')}</span>
            <em>${escape(item.status_label || 'Čeká')}</em>
          </button>
        `).join('') : '<div class="service-shell-empty">Na dnešek nejsou žádné rezervace.</div>'}
        <button type="button" class="service-link-btn" onclick="window.serviceShell.navigate('reservations')">Zobrazit všechny rezervace ›</button>
      </section>
    `;
  }

  function renderRisksPanel() {
    const items = Array.isArray(state.dashboardRisks) ? state.dashboardRisks : [];
    const fallback = items.length ? items : [{ type: 'ok', label: 'Bez kritických upozornění.', severity: 'success', count: 0, target_path: '/audit' }];
    return `
      <section class="service-pro-card" id="serviceRisksPanel">
        <h2>Rizika a upozornění</h2>
        ${fallback.map((item) => `
          <button type="button" class="service-risk-row service-risk-row--${escape(item.severity || 'warning')}" onclick="window.serviceShell.openRiskTarget('${escape(item.type || '')}', '${escape(item.target_path || '')}')">
            <span>${item.severity === 'danger' ? '!' : item.severity === 'success' ? '✓' : '△'}</span>
            <strong>${escape(item.label || 'Upozornění')}</strong>
            ${Number(item.count || 0) ? `<em>${Number(item.count || 0)}</em>` : ''}
          </button>
        `).join('')}
        <button type="button" class="service-link-btn" onclick="window.serviceShell.navigate('audit')">Zobrazit všechna upozornění ›</button>
      </section>
    `;
  }

  function renderGdprBottomBar() {
    const items = [
      ['access', 'Přístup povolen majitelem'],
      ['hidden', 'Osobní údaje skryty'],
      ['vin', 'VIN záznam'],
      ['audit', 'Auditováno'],
      ['consent', 'Souhlas zákazníka ověřen'],
      ['pending', 'Čeká na autorizaci'],
    ];
    return `
      <footer class="service-gdpr-bar">
        ${items.map(([key, label]) => `<button type="button" onclick="window.serviceShell.openGdprInfo('${key}')">${key === 'pending' ? navRailIconSvg('users') : navRailIconSvg(key === 'vin' ? 'car' : 'shield')} ${escape(label)}</button>`).join('')}
        <span><i></i> Poslední aktivita: před 2 min</span>
      </footer>
    `;
  }

  function genericSection(config) {
    return ServiceProPageShell(
      config.title,
      config.subtitle,
      config.main,
      {
        statsHtml: config.stats || '',
        asideHtml: config.side ? stripAsideWrapper(config.side) : '',
      },
    );
  }

  function clientsSection() {
    const customers = Array.isArray(state.customers) ? state.customers : [];
    const activityLabel = (item) => {
      if (item?.last_service_date) return formatDate(item.last_service_date);
      if (item?.last_activity) return formatDate(item.last_activity);
      return '-';
    };
    const cards = customers.length ? customers.map((customer) => {
      const cid = Number(customer?.customer_id || 0);
      const hi = state.highlightCustomerId && cid === Number(state.highlightCustomerId);
      return listCard({
        kicker: 'Zákazník',
        title: customer?.name || maskCardContact(customer?.email),
        badge: `${String(customer?.vehicles_count || customer?.vehicle_count || 0)} aut`,
        badgeClass: 'in_progress',
        cardClass: hi ? 'service-shell-list-card--highlight' : '',
        rows: [
          ['Kontakt', maskCardContact(customer?.email || customer?.phone)],
          ['Sdíleno', String(customer?.shared_vehicles_count || 0)],
          ['Poslední servis u vás', activityLabel(customer)],
        ],
        action: `window.serviceShell.openCustomerDetailModal(${cid})`,
        actionLabel: 'Detail',
        moreHtml: `
          <button type="button" class="btn btn-secondary" onclick="event.stopPropagation(); window.serviceShell.openCustomerLinkNoteModal(${cid}, ${JSON.stringify(String(customer?.note || ''))})">Poznámka</button>
          <button type="button" class="btn btn-secondary" onclick="event.stopPropagation(); window.serviceShell.unlinkCustomer(${cid})">Odpojit</button>
        `,
      });
    }).join('') : '';
    const stats = `
      <article class="service-shell-mini-card summary-card"><h3>Zákazníci</h3><div class="service-shell-stat-value">${customers.length}</div><p class="service-shell-muted">Aktivní servisní vazby</p></article>
      <article class="service-shell-mini-card summary-card"><h3>Vozidla</h3><div class="service-shell-stat-value">${customers.reduce((sum, item) => sum + Number(item?.vehicles_count || item?.vehicle_count || 0), 0)}</div><p class="service-shell-muted">Vozidla napojených zákazníků</p></article>
    `;
    const main = renderCardList({
        head: `
          <div class="service-shell-card-head">
            <div><h3 class="service-shell-card-title">Zákazníci servisu</h3><p class="service-shell-subtitle">Účty ze Správy vozidel propojené s tímto servisem — zakládání vozidel, zakázek a rezervací.</p></div>
            <div class="service-shell-card-head-actions">
              <button type="button" class="service-shell-filter-chip" onclick="window.serviceShell.openAddCustomerModal()">+ Přidat zákazníka</button>
              <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.load(true)">↗</button>
            </div>
          </div>
        `,
        cards,
        empty: 'Zatím nemáte propojené zákazníky.',
      });
    const side = `
      <aside class="service-shell-side">
        <section class="service-pro-card service-shell-side-card list-card">
          <h3>Nedávná aktivita</h3>
          <div class="service-shell-list">
            ${customers.slice(0, 5).map((item) => `
              <div class="service-shell-list-row">
                <div>
                  <p class="service-shell-list-title">${escape(item?.name || 'Zákazník')}</p>
                  <p class="service-shell-list-note">${escape(maskCardContact(item?.email || item?.phone))}</p>
                </div>
                <div class="service-shell-list-value">${escape(activityLabel(item))}</div>
              </div>
            `).join('') || '<div class="service-shell-empty">Bez záznamů.</div>'}
          </div>
        </section>
        <section class="service-pro-card service-shell-side-card list-card">
          <h3>Zkratky</h3>
          <div class="service-shell-list">
            <div class="service-shell-list-row"><span class="service-shell-list-title">Detail zákazníka</span><span class="service-shell-list-value">Klik na kartu</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Přidat vozidlo</span><span class="service-shell-list-value">Z detailu zákazníka</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Ověřit profil / pozvat</span><span class="service-shell-list-value"><button type="button" class="service-shell-filter-chip" style="margin:0" onclick="window.serviceShell.openAddCustomerModal()">Přidat zákazníka</button></span></div>
          </div>
        </section>
      </aside>
    `;
    return genericSection({
      title: 'Zákaznické centrum',
      subtitle: 'Propojení na uživatelské účty ve Správě vozidel, sdílená vozidla a servisní vazby.',
      stats,
      main,
      side,
    });
  }

  function vehiclesSection() {
    const vehicles = Array.isArray(state.vehicles) ? state.vehicles : [];
    const cards = vehicles.length ? vehicles.slice(0, 80).map((vehicle) => listCard({
      kicker: vehiclePlate(vehicle),
      title: vehicleTitle(vehicle),
      badge: 'Schváleno',
      badgeClass: 'completed',
      rows: [
        ['SPZ', vehiclePlate(vehicle)],
        ['VIN', vehicleVin(vehicle)],
        ['Sdíleno', vehicle?.last_shared_at ? formatDate(vehicle?.last_shared_at) : '-'],
        ['Majitel', 'Osobní údaje skryty'],
      ],
      action: `window.serviceShell.openVehicleDetailModal(${Number(vehicle?.id || 0)})`,
      actionLabel: 'Detail',
    })).join('') : '';
    const stats = `
      <article class="service-shell-mini-card summary-card"><h3>Vozidla zákazníků</h3><div class="service-shell-stat-value">${vehicles.length}</div><p class="service-shell-muted">Napojená vozidla pod správou servisu</p></article>
      <article class="service-shell-mini-card summary-card"><h3>Sdílení</h3><div class="service-shell-stat-value">${vehicles.filter((item) => item?.last_shared_at).length}</div><p class="service-shell-muted">Aktivně schválené přístupy</p></article>
    `;
    const main = renderCardList({
        head: `
          <div class="service-shell-card-head">
            <div><h3 class="service-shell-card-title">Vozidla zákazníků</h3><p class="service-shell-subtitle">Seznam vozidel zákazníků, ke kterým má servis schválený přístup.</p></div>
            <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.load(true)">↗</button>
          </div>
        `,
        cards,
        empty: 'Bez vozidel.',
      });
    const side = `
      <aside class="service-shell-side">
        <section class="service-pro-card service-shell-side-card list-card">
          <h3>Vozidla s přístupem</h3>
          <div class="service-shell-list">
            <div class="service-shell-list-row"><span class="service-shell-list-title">Schválené vazby</span><span class="service-shell-list-value">${vehicles.length}</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Otevřít detail</span><span class="service-shell-list-value">Klik na řádek</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Přidání nového vozidla</span><span class="service-shell-list-value">Přes konkrétního zákazníka</span></div>
          </div>
        </section>
      </aside>
    `;
    return genericSection({
      title: 'Vozidla zákazníků',
      subtitle: 'Přehled vozidel zákazníků napojených na servis v jednotném operativním zobrazení.',
      stats,
      main,
      side,
    });
  }

  function workOrdersSection() {
    const summary = dashboardSummary();
    const firstError = Array.isArray(state.errors) && state.errors.length ? String(state.errors[0] || '').trim() : '';
    const stats = `
      <article class="service-shell-mini-card summary-card"><h3>Aktivní</h3><div class="service-shell-stat-value">${summary.active_jobs}</div><p class="service-shell-muted">Schválené a rozpracované</p></article>
      <article class="service-shell-mini-card summary-card"><h3>Po termínu</h3><div class="service-shell-stat-value">${summary.overdue}</div><p class="service-shell-muted">Vyžaduje zásah</p></article>
    `;
    return genericSection({
      title: 'Zakázky',
      subtitle: 'Hlavní pracovní fronta příchozích servisních objednávek se stavem, termíny a odpovědností.',
      stats,
      main: `<section data-testid="service-work-orders-section"><span class="service-legacy-text-hook">Aktivní zakázky</span>${firstError ? `<article class="service-pro-card service-state-card--error" data-testid="service-work-orders-error">${escape(firstError)}</article>` : ''}${workOrdersTableCard('Aktivní zakázky', 'Produkční příchozí objednávky a zakázky v jednotném servisním rozhraní.')}${state.workOrderLimitedNotice ? `<article class="service-pro-card service-state-note">${escape(state.workOrderLimitedNotice)}</article>` : ''}</section>`,
      side: rightPanel(),
    });
  }

  function documentsSection() {
    const documents = Array.isArray(state.documents) ? state.documents : [];
    const cards = documents.length ? documents.map((doc) => listCard({
      kicker: doc?.vehicle_label || 'Doklad',
      title: doc?.document_number || doc?.original_filename || '-',
      badge: accessStatusLabel(doc?.processing_status || '-'),
      badgeClass: String(doc?.processing_status || '').toLowerCase() === 'processed' ? 'completed' : 'awaiting',
      rows: [
        ['Vozidlo', doc?.vehicle_label || '-'],
        ['Dodavatel', doc?.supplier_name || '-'],
        ['Vloženo', doc?.created_at ? formatDate(doc.created_at) : '-'],
        ['Zákazník', 'Osobní údaje skryty'],
      ],
      action: `window.serviceShell.openDocumentDetailModal(${Number(doc?.id || 0)})`,
      actionLabel: 'Detail',
    })).join('') : '';
    const processed = documents.filter((item) => String(item?.processing_status || '').toLowerCase() === 'processed').length;
    const stats = `
      <article class="service-shell-mini-card summary-card"><h3>Dokumenty</h3><div class="service-shell-stat-value">${documents.length}</div><p class="service-shell-muted">Načtené servisní doklady</p></article>
      <article class="service-shell-mini-card summary-card"><h3>Validace</h3><div class="service-shell-stat-value">${processed}</div><p class="service-shell-muted">Zpracované vstupy</p></article>
    `;
    const main = renderCardList({
        head: `
          <div class="service-shell-card-head">
            <div><h3 class="service-shell-card-title">Dokumenty</h3><p class="service-shell-subtitle">Dokumentový modul servisu ve stejném systému karet.</p></div>
            <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.load(true)">↗</button>
          </div>
        `,
        cards,
        empty: 'Bez dokumentů.',
      });
    const side = `
      <aside class="service-shell-side">
        <section class="service-shell-side-card">
          <h3>Quick actions</h3>
          <div class="service-shell-list">
            <div class="service-shell-list-row"><span class="service-shell-list-title">Čeká na kontrolu</span><span class="service-shell-list-value">${documents.length - processed}</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Se záznamem</span><span class="service-shell-list-value">${documents.filter((item) => Number(item?.auto_created_service_record_id || 0) > 0).length}</span></div>
          </div>
        </section>
        <section class="service-shell-side-card">
          <h3>Akce</h3>
          <div class="service-shell-list">
            <div class="service-shell-list-row"><span class="service-shell-list-title">Otevřít detail dokumentu</span><span class="service-shell-list-value">Klik na řádek</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Vytvořit zakázku</span><span class="service-shell-list-value">V detailu dokladu</span></div>
          </div>
        </section>
      </aside>
    `;
    return genericSection({
      title: 'Dokumenty',
      subtitle: 'Doklady, extrakce, validace a návaznost na servisní evidenci.',
      stats,
      main,
      side,
    });
  }

  function invoicesSection() {
    const allInvoices = Array.isArray(state.invoices) ? state.invoices : [];
    const allQuotes = Array.isArray(state.quotes) ? state.quotes : [];
    const invoices = filteredInvoices();
    const draftCount = allInvoices.filter((item) => invoiceStatusKey(item?.status) === 'draft').length;
    const issuedCount = allInvoices.filter((item) => invoiceStatusKey(item?.status) === 'issued').length;
    const cancelledCount = allInvoices.filter((item) => invoiceStatusKey(item?.status) === 'cancelled').length;
    const totalIssued = allInvoices
      .filter((item) => invoiceStatusKey(item?.status) === 'issued')
      .reduce((sum, item) => sum + Number(item?.total || 0), 0);
    const quoteCards = allQuotes.length
      ? allQuotes.map((quote) => listCard({
        kicker: quote?.vehicle_label || 'Nabídka',
        title: `Nabídka #${Number(quote?.quote_id || 0)}`,
        badge: String(quote?.status_label || quote?.status || '-'),
        badgeClass: quoteBadgeClass(quote?.status),
        rows: [
          ['Celkem', formatQuotePriceCs(quote?.total_price)],
          ['Zakázka', quote?.work_order_id ? `#${quote.work_order_id}` : '—'],
          ['Vytvořeno', quote?.created_at ? formatDateTime(quote.created_at) : '-'],
        ],
        action: `window.serviceShell.openBillingQuoteDetail(${Number(quote?.quote_id || 0)})`,
        actionLabel: 'Detail',
        testId: 'service-billing-quote-row',
        moreHtml: `<details class="service-shell-more-actions" onclick="event.stopPropagation()"><summary aria-label="Více akcí">Více</summary><button type="button" data-testid="service-billing-create-invoice-from-quote-button" onclick="event.stopPropagation(); window.serviceShell.createInvoiceFromQuote(${Number(quote?.quote_id || 0)})">Faktura</button><button type="button" onclick="event.stopPropagation(); window.serviceShell.shareQuotePdf(${Number(quote?.quote_id || 0)})">PDF nabídky</button></details>`,
      })).join('')
      : '';
    const invoiceCards = invoices.length
      ? invoices.map((inv) => listCard({
        kicker: inv?.vehicle_label || 'Faktura',
        title: inv?.invoice_number || 'Koncept',
        badge: String(inv?.status_label || inv?.status || '-'),
        badgeClass: invoiceBadgeClass(inv?.status),
        rows: [
          ['Celkem', invoiceMoney(inv?.total || 0, inv?.currency || 'CZK')],
          ['Zákazník', inv?.customer_label || (inv?.customer_id != null ? `Zákazník #${inv.customer_id}` : 'Osobní údaje skryty')],
          ['Zakázka', inv?.work_order_id ? `#${inv.work_order_id}` : '—'],
          ['Splatnost', inv?.due_at ? formatDate(inv.due_at) : '-'],
        ],
        action: `window.serviceShell.openBillingInvoiceDetail(${Number(inv?.id || 0)})`,
        actionLabel: 'Detail',
        testId: 'service-billing-invoice-row',
        moreHtml: `<details class="service-shell-more-actions" onclick="event.stopPropagation()"><summary aria-label="Více akcí">Více</summary><button type="button" data-testid="service-billing-invoice-pdf-button" onclick="event.stopPropagation(); window.serviceShell.openServiceInvoicePdf(${Number(inv?.id || 0)})">PDF</button></details>`,
      })).join('')
      : '';
    const stats = `
      <article class="service-shell-mini-card summary-card"><h3>Nabídky</h3><div class="service-shell-stat-value">${allQuotes.length}</div><p class="service-shell-muted">Cenové nabídky servisu</p></article>
      <article class="service-shell-mini-card summary-card"><h3>Koncepty</h3><div class="service-shell-stat-value">${draftCount}</div><p class="service-shell-muted">Rozpracované faktury</p></article>
      <article class="service-shell-mini-card summary-card"><h3>Vystavené</h3><div class="service-shell-stat-value">${issuedCount}</div><p class="service-shell-muted">Číslované faktury</p></article>
      <article class="service-shell-mini-card summary-card"><h3>Objem</h3><div class="service-shell-stat-value">${escape(invoiceMoney(totalIssued, 'CZK'))}</div><p class="service-shell-muted">Součet vystavených faktur</p></article>
    `;
    const main = `
      <section class="service-pro-card" data-testid="service-billing-section">
        <div class="service-pro-card-head">
          <div><h2 class="service-shell-card-title">Nabídky a faktury</h2><p class="service-page-header-sub">Obchodní doklady servisu vázané na zakázky — nejsou součástí historie majitele.</p></div>
          <div class="service-shell-card-head-actions">
            <button type="button" class="service-shell-filter-chip service-shell-filter-open-btn" data-testid="service-invoices-filter" onclick="window.serviceShell.openFilterSheet('invoices')">Filtr</button>
            <button type="button" class="service-shell-primary-btn" onclick="window.serviceShell.openCreateInvoiceModal()">Nová faktura</button>
            <button type="button" class="btn btn-secondary" onclick="window.serviceShell.load(true)">Obnovit</button>
          </div>
        </div>
        <p class="service-shell-list-note" data-testid="service-billing-limited-notice">Obchodní doklady (nabídky, faktury, PDF) jsou dostupné pouze servisnímu účtu a nejsou součástí historie majitele vozidla.</p>
        <h4 class="service-shell-subsection-title">Nabídky</h4>
        <div class="service-shell-card-grid" data-testid="service-billing-quotes-list">${quoteCards || '<div class="service-shell-empty">Zatím bez nabídek.</div>'}</div>
        <h4 class="service-shell-subsection-title">Faktury</h4>
        <div class="service-shell-invoice-toolbar">
          <div class="service-shell-segmented">
            ${[
              ['all', 'Vše'],
              ['draft', 'Koncepty'],
              ['issued', 'Vystavené'],
              ['cancelled', 'Zrušené'],
            ].map(([key, label]) => `<button type="button" class="${state.invoiceStatusFilter === key ? 'active' : ''}" onclick="window.serviceShell.setInvoiceStatusFilter('${key}')">${label}</button>`).join('')}
          </div>
          <input class="service-shell-search" type="search" placeholder="Hledat číslo, klienta, vozidlo" value="${escape(state.invoiceSearchTerm)}" oninput="window.serviceShell.setInvoiceSearchTerm(this.value)">
        </div>
        <div class="service-shell-card-grid" data-testid="service-billing-invoices-list">${invoiceCards || '<div class="service-shell-empty">Žádné faktury neodpovídají filtru.</div>'}</div>
      </section>
    `;
    const side = `
      <aside class="service-shell-side">
        <section class="service-shell-side-card">
          <h3>Workflow dokladu</h3>
          <div class="service-shell-list">
            <div class="service-shell-list-row"><span class="service-shell-list-title">1. Koncept</span><span class="service-shell-list-value">plně editovatelný</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">2. Vystavení</span><span class="service-shell-list-value">číslování</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">3. PDF</span><span class="service-shell-list-value">dle vyplněné hlavičky</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">4. Historie</span><span class="service-shell-list-value">vázaná na servis</span></div>
          </div>
        </section>
        <section class="service-shell-side-card">
          <h3>Údaje dodavatele</h3>
          <div class="service-shell-list">
            <div class="service-shell-list-row"><span class="service-shell-list-title">Zdroj</span><span class="service-shell-list-value">profil účtu / úprava v dokladu</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">IČO, adresa</span><span class="service-shell-list-value">v sekci Dodavatel</span></div>
          </div>
        </section>
      </aside>
    `;
    return genericSection({
      title: 'Nabídky a faktury',
      subtitle: 'Servisní nabídky a faktury vázané na zakázky — pouze pro servisní účet.',
      stats,
      main,
      side,
    });
  }

  function reservationsSection() {
    const reservations = filteredReservations();
    const allReservations = Array.isArray(state.reservations) ? state.reservations : [];
    const archivedReservations = allReservations.filter((item) => isReservationArchived(item)).length;
    const cards = reservations.length ? reservations.map((reservation) => listCard({
      kicker: reservation?.vehicle_plate || reservation?.vehicle_label || 'Rezervace',
      title: reservation?.vehicle_name || reservation?.vehicle_label || reservation?.vehicle_plate || 'Vozidlo',
      badge: accessStatusLabel(reservation?.status || '-'),
      badgeClass: reservationBadgeClass(reservation?.status),
      rows: [
        ['Termín', formatDate(reservation?.scheduled_for || reservation?.reservation_date || reservation?.starts_at || reservation?.created_at || '-')],
        ['Poznámka', reservation?.note || reservation?.service_note || '-'],
        ['Zákazník', 'Osobní údaje skryty'],
      ],
      action: `window.serviceShell.openReservationDetailModal(${Number(reservation?.id || 0)})`,
      actionLabel: 'Detail',
    })).join('') : '';
    const stats = `
      <article class="service-shell-mini-card summary-card"><h3>Aktivní rezervace</h3><div class="service-shell-stat-value">${reservations.length}</div><p class="service-shell-muted">Ve výchozím pohledu bez zrušených a dokončených</p></article>
      <article class="service-shell-mini-card summary-card"><h3>Dnes</h3><div class="service-shell-stat-value">${reservations.filter((item) => toDateKey(item?.scheduled_for || item?.reservation_date || item?.starts_at) === todayKey()).length}</div><p class="service-shell-muted">Příjezdy během dneška</p></article>
      <article class="service-shell-mini-card summary-card"><h3>Archiv</h3><div class="service-shell-stat-value">${archivedReservations}</div><p class="service-shell-muted">Zrušené nebo dokončené rezervace</p></article>
    `;
    const main = renderCardList({
        head: `
          <div class="service-shell-card-head">
            <div><h3 class="service-shell-card-title">Příchozí rezervace</h3><p class="service-shell-subtitle">Příjezdy zákazníků, nepotvrzené termíny a navazující servisní požadavky.</p></div>
            <div class="service-shell-card-head-actions">
              <button type="button" class="service-shell-filter-chip service-shell-filter-open-btn service-shell-filter-chip--desktop-hide" data-testid="service-reservations-filter" onclick="window.serviceShell.openFilterSheet('reservations')">Filtr</button>
              <button type="button" class="service-shell-filter-chip service-shell-filter-chip--desktop-only ${state.showCancelledReservations ? 'active' : ''}" onclick="window.serviceShell.setShowCancelledReservations(${state.showCancelledReservations ? 'false' : 'true'})">${state.showCancelledReservations ? 'Skrýt archiv' : 'Zobrazit archiv'}</button>
              <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.load(true)">↗</button>
            </div>
          </div>
        `,
        cards,
        empty: 'Bez aktivních rezervací.',
      });
    const side = `
      <aside class="service-shell-side">
        <section class="service-shell-side-card">
          <h3>Dnešní příjezdy</h3>
          <div class="service-shell-list">
            ${reservations.slice(0, 5).map((item) => `
              <div class="service-shell-list-row">
                <div>
                  <p class="service-shell-list-title">${escape(item?.vehicle_name || item?.vehicle_label || 'Vozidlo')}</p>
                  <p class="service-shell-list-note">${escape(item?.vehicle_name || item?.vehicle_label || '-')}</p>
                </div>
                <div class="service-shell-list-value">${escape(formatDate(item?.scheduled_for || item?.reservation_date || item?.starts_at || '-'))}</div>
              </div>
            `).join('') || '<div class="service-shell-empty">Bez aktivních příjezdů.</div>'}
          </div>
        </section>
        <section class="service-shell-side-card">
          <h3>Akce</h3>
          <div class="service-shell-list">
            <div class="service-shell-list-row"><span class="service-shell-list-title">Otevřít detail rezervace</span><span class="service-shell-list-value">Klik na řádek</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Založit zakázku</span><span class="service-shell-list-value">Z detailu rezervace</span></div>
          </div>
        </section>
      </aside>
    `;
    return genericSection({
      title: 'Příchozí rezervace',
      subtitle: 'Příjmy vozidel, nepotvrzené rezervace a čekající požadavky od zákazníků.',
      stats,
      main,
      side,
    });
  }

  function remindersSection() {
    const reminders = filteredReminders();
    const allReminders = Array.isArray(state.reminders) ? state.reminders : [];
    const overdueAttentionSection = reminders.filter(reminderIsOverdueAttention).length;
    const completedReminders = allReminders.filter((item) => item?.is_completed).length;
    const cards = reminders.length ? reminders.map((item) => listCard({
      kicker: item?.vehicle_label || 'Připomínka',
      title: item?.vehicle_label || 'Obecná připomínka',
      badge: item?.is_completed ? 'Dokončeno' : 'Aktivní',
      badgeClass: item?.is_completed ? 'completed' : (reminderIsOverdueAttention(item) ? 'issue' : 'in_progress'),
      rows: [
        ['Termín', item?.due_date ? formatDate(item.due_date) : '-'],
        ['Text', item?.text || '-'],
        ['Zákazník', 'Osobní údaje skryty'],
      ],
      action: `window.serviceShell.openReminderDetailModal(${Number(item?.id || 0)})`,
      actionLabel: 'Detail',
    })).join('') : '';
    const stats = `
      <article class="service-shell-mini-card summary-card"><h3>Aktivní připomínky</h3><div class="service-shell-stat-value">${reminders.length}</div><p class="service-shell-muted">Ve výchozím pohledu bez dokončených</p></article>
      <article class="service-shell-mini-card summary-card"><h3>Po termínu / nutná akce</h3><div class="service-shell-stat-value">${overdueAttentionSection}</div><p class="service-shell-muted">Propadlý termín nebo připomenutí</p></article>
      <article class="service-shell-mini-card summary-card"><h3>Dokončeno</h3><div class="service-shell-stat-value">${completedReminders}</div><p class="service-shell-muted">Lze zobrazit nebo smazat z archivu</p></article>
    `;
    const main = renderCardList({
        head: `
          <div class="service-shell-card-head">
            <div><h3 class="service-shell-card-title">Připomínky</h3><p class="service-shell-subtitle">Follow-upy a kritické termíny servisu.</p></div>
            <div class="service-shell-card-head-actions">
              <button type="button" class="service-shell-filter-chip service-shell-filter-open-btn service-shell-filter-chip--desktop-hide" data-testid="service-reminders-filter" onclick="window.serviceShell.openFilterSheet('reminders')">Filtr</button>
              <button type="button" class="service-shell-filter-chip service-shell-filter-chip--desktop-only ${state.showCompletedReminders ? 'active' : ''}" onclick="window.serviceShell.setShowCompletedReminders(${state.showCompletedReminders ? 'false' : 'true'})">${state.showCompletedReminders ? 'Skrýt dokončené' : 'Zobrazit dokončené'}</button>
              <button type="button" class="btn btn-primary" onclick="window.serviceShell.openCreateReminderModal()">Nová připomínka</button>
              <details class="service-shell-more-actions"><summary aria-label="Více akcí">Více</summary><button type="button" onclick="window.serviceShell.load(true)">Obnovit</button></details>
            </div>
          </div>
        `,
        cards,
        empty: 'Bez aktivních připomínek.',
      });
    const side = `
      <aside class="service-shell-side">
        <section class="service-shell-side-card">
          <h3>Follow-upy</h3>
          <div class="service-shell-list">
            ${reminders.slice(0, 5).map((item) => `
              <div class="service-shell-list-row">
                <div>
                  <p class="service-shell-list-title">${escape(item?.vehicle_label || 'Připomínka')}</p>
                  <p class="service-shell-list-note">${escape(item?.text || '-')}</p>
                </div>
                <div class="service-shell-list-value">${escape(item?.due_date ? formatDate(item.due_date) : '-')}</div>
              </div>
            `).join('') || '<div class="service-shell-empty">Bez follow-upů.</div>'}
          </div>
        </section>
        <section class="service-shell-side-card">
          <h3>Akce</h3>
          <div class="service-shell-list">
            <div class="service-shell-list-row"><span class="service-shell-list-title">Vytvořit připomínku</span><span class="service-shell-list-value">Tlačítko v hlavičce</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Otevřít detail připomínky</span><span class="service-shell-list-value">Klik na řádek</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Uložit změny</span><span class="service-shell-list-value">V detailu připomínky</span></div>
          </div>
        </section>
      </aside>
    `;
    return genericSection({
      title: 'Připomínky',
      subtitle: 'Tabulka reminderů, follow-upů a kritických termínů servisu.',
      stats,
      main,
      side,
    });
  }

  function splitServiceShellPartnerProfileLines(raw) {
    return String(raw || '')
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
  }

  async function savePartnerPublicProfile() {
    const tagline = String(document.getElementById('serviceShellPartnerTagline')?.value || '').trim();
    const about = String(document.getElementById('serviceShellPartnerAbout')?.value || '').trim();
    const opening_hours = String(document.getElementById('serviceShellPartnerHours')?.value || '').trim();
    const services_offered = splitServiceShellPartnerProfileLines(
      document.getElementById('serviceShellPartnerServices')?.value || ''
    );
    const equipment = splitServiceShellPartnerProfileLines(
      document.getElementById('serviceShellPartnerEquipment')?.value || ''
    );
    const brands = splitServiceShellPartnerProfileLines(
      document.getElementById('serviceShellPartnerBrands')?.value || ''
    );
    try {
      await window.apiCall('/api/v1/services/workspace/partner-public-profile', 'PUT', {
        tagline,
        about,
        opening_hours,
        services_offered,
        equipment,
        brands,
      });
      showToast('Veřejný profil pro adresář partnerů uložen.', 'success');
      await load(true, true);
    } catch (error) {
      showToast(`Nepodařilo se uložit profil: ${error?.message || 'chyba'}`, 'error');
    }
  }

  function teamSection() {
    const performance = Array.isArray(state.performance) ? state.performance : [];
    const cards = performance.length ? performance.map((item) => listCard({
      kicker: 'Technik',
      title: item?.name || '-',
      badge: `${String(item?.jobs_total || 0)} zakázek`,
      badgeClass: Number(item?.overdue_count || 0) > 0 ? 'issue' : 'in_progress',
      rows: [
        ['Čeká', String(item?.awaiting_count || 0)],
        ['Po termínu', String(item?.overdue_count || 0)],
      ],
      action: '',
    })).join('') : '';
    const profile = currentProfile();
    const pp = state.partnerPublicProfile && typeof state.partnerPublicProfile === 'object' ? state.partnerPublicProfile : {};
    const partnerLines = (items) => (Array.isArray(items) ? items : [])
      .map((x) => String(x || '').trim())
      .filter(Boolean)
      .join('\n');
    const stats = `
      <article class="service-shell-mini-card summary-card"><h3>Tým</h3><div class="service-shell-stat-value">${performance.length}</div><p class="service-shell-muted">Aktivní technici</p></article>
      <article class="service-shell-mini-card summary-card"><h3>Profil</h3><div class="service-shell-stat-value">${escape(initials(profile?.name || profile?.email || window.currentUser?.email || 'SA'))}</div><p class="service-shell-muted">${escape(maskCardContact(profile?.email || window.currentUser?.email))}</p></article>
    `;
    const main = renderCardList({
        head: `
          <div class="service-shell-card-head">
            <div><h3 class="service-shell-card-title">Tým</h3><p class="service-shell-subtitle">Výkon techniků a identita přihlášeného servisního účtu.</p></div>
            <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.load(true)">↗</button>
          </div>
        `,
        cards,
        empty: 'Bez výkonových dat techniků.',
      });
    const side = `
      <aside class="service-shell-side">
        <section class="service-shell-side-card">
          <h3>Přihlášený účet</h3>
          <div class="service-shell-list">
            <div class="service-shell-list-row">
              <div>
                <p class="service-shell-list-title">${escape(profile?.name || window.currentUser?.name || 'Servisní účet')}</p>
                <p class="service-shell-list-note">${escape(maskCardContact(profile?.email || window.currentUser?.email))}</p>
              </div>
              <div class="service-shell-list-value">${escape(String(profile?.role || window.currentUser?.role || 'service_account').replace(/_/g, ' '))}</div>
            </div>
          </div>
        </section>
        <section class="service-shell-side-card">
          <h3>Veřejný profil v adresáři</h3>
          <p class="service-shell-muted" style="font-size:0.82rem;margin:0 0 12px;line-height:1.45;">
            Údaje uvidí majitelé vozidel v záložce Servisní partneři po rozkliknutí vašeho servisu (název a adresa zůstávají z účtu).
          </p>
          <label class="service-shell-muted" for="serviceShellPartnerTagline" style="display:block;font-size:0.78rem;font-weight:700;margin:8px 0 4px;">Krátký popis</label>
          <input id="serviceShellPartnerTagline" class="service-shell-search" style="width:100%;margin-bottom:8px;" maxlength="280" value="${escape(String(pp.tagline || ''))}" placeholder="např. Specializace na EV">
          <label class="service-shell-muted" for="serviceShellPartnerAbout" style="display:block;font-size:0.78rem;font-weight:700;margin:8px 0 4px;">Delší text</label>
          <textarea id="serviceShellPartnerAbout" class="service-shell-search" style="width:100%;min-height:88px;margin-bottom:8px;" maxlength="4000" placeholder="Provozovna, tým…">${escape(String(pp.about || ''))}</textarea>
          <label class="service-shell-muted" for="serviceShellPartnerServices" style="display:block;font-size:0.78rem;font-weight:700;margin:8px 0 4px;">Služby (řádek = položka)</label>
          <textarea id="serviceShellPartnerServices" class="service-shell-search" style="width:100%;min-height:72px;margin-bottom:8px;" placeholder="Servis&#10;Pneuservis">${escape(partnerLines(pp.services_offered))}</textarea>
          <label class="service-shell-muted" for="serviceShellPartnerEquipment" style="display:block;font-size:0.78rem;font-weight:700;margin:8px 0 4px;">Vybavení</label>
          <textarea id="serviceShellPartnerEquipment" class="service-shell-search" style="width:100%;min-height:56px;margin-bottom:8px;" placeholder="Zvedák&#10;Diagnostika">${escape(partnerLines(pp.equipment))}</textarea>
          <label class="service-shell-muted" for="serviceShellPartnerBrands" style="display:block;font-size:0.78rem;font-weight:700;margin:8px 0 4px;">Značky</label>
          <textarea id="serviceShellPartnerBrands" class="service-shell-search" style="width:100%;min-height:48px;margin-bottom:8px;" placeholder="VW&#10;Toyota">${escape(partnerLines(pp.brands))}</textarea>
          <label class="service-shell-muted" for="serviceShellPartnerHours" style="display:block;font-size:0.78rem;font-weight:700;margin:8px 0 4px;">Otevírací doba</label>
          <input id="serviceShellPartnerHours" class="service-shell-search" style="width:100%;margin-bottom:10px;" maxlength="500" value="${escape(String(pp.opening_hours || ''))}" placeholder="Po–Pá 7:30–17:00">
          <button type="button" class="btn btn-primary" style="width:100%;" onclick="window.serviceShell.savePartnerPublicProfile()">Uložit veřejný profil</button>
        </section>
        <section class="service-shell-side-card">
          <h3>Rozdělení práce</h3>
          <div class="service-shell-list">
            ${performance.slice(0, 4).map((item) => `
              <div class="service-shell-list-row">
                <div>
                  <p class="service-shell-list-title">${escape(item?.name || '-')}</p>
                  <p class="service-shell-list-note">${escape(String(item?.jobs_total || 0))} zakázek</p>
                </div>
                <div class="service-shell-list-value">${escape(String(item?.awaiting_count || 0))} čeká</div>
              </div>
            `).join('') || '<div class="service-shell-empty">Bez rozdělené práce.</div>'}
          </div>
        </section>
        <section class="service-shell-side-card">
          <h3>Fronta týmu</h3>
          <div class="service-shell-list">
            <div class="service-shell-list-row"><span class="service-shell-list-title">Nové zakázky</span><span class="service-shell-list-value">${escape(String(state.queue?.new_jobs || state.queue?.new_work_orders || 0))}</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Po termínu</span><span class="service-shell-list-value">${escape(String(state.summary?.overdue || 0))}</span></div>
          </div>
        </section>
      </aside>
    `;
    return genericSection({
      title: 'Tým',
      subtitle: 'Seznam techniků, výkon, rozdělení práce a fronta úkolů.',
      stats,
      main,
      side,
    });
  }

  function loadingShell() {
    return ServiceLoadingSkeleton(state.activeSection || 'dashboard');
  }

  function sectionLoadErrorHtml() {
    if (!Array.isArray(state.errors) || !state.errors.length) return '';
    if (LIMITED_WORKSPACE_SECTIONS.has(state.activeSection)) return '';
    return ServiceErrorState(state.errors[0] || 'Neznámá chyba', 'window.serviceShell.load(true)');
  }

  function currentSectionHtml() {
    if (state.loading) return loadingShell();
    const loadError = sectionLoadErrorHtml();
    if (loadError) return loadError;
    const placeholder = serviceAccountPlaceholderSections();
    if (placeholder) return placeholder;
    if (state.activeSection === 'clients') return clientsSection();
    if (state.activeSection === 'vehicles') return vehiclesSection();
    if (state.activeSection === 'work-orders') return workOrdersSection();
    if (state.activeSection === 'documents') return documentsSection();
    if (state.activeSection === 'invoices') return invoicesSection();
    if (state.activeSection === 'reservations') return reservationsSection();
    if (state.activeSection === 'reminders') return remindersSection();
    if (state.activeSection === 'team') return teamSection();
    return dashboardSection();
  }

  function currentSectionHtmlSafe() {
    try {
      return currentSectionHtml();
    } catch (error) {
      console.error('[SERVICE_SHELL] currentSectionHtml failed:', error);
      return `
        <div class="service-shell-page-head">
          <h1>Chyba zobrazení sekce</h1>
          <p class="service-shell-subtitle">Zkuste jinou záložku v menu nebo obnovte data. Detail chyby je v konzoli (F12).</p>
        </div>
        <div class="service-shell-inline-error" style="margin:16px 0;">${escape(String(error?.message || error || 'Neznámá chyba'))}</div>
        <button type="button" class="btn btn-primary" onclick="window.serviceShell.navigate('dashboard'); window.serviceShell.load(true);">Zpět na dashboard</button>
      `;
    }
  }

  function renderFatalShellFallback(error) {
    const msg = escape(String(error?.message || error || 'Neznámá chyba'));
    return `
      <div class="service-shell-root" data-service-shell="root" style="min-height:100vh;padding:24px;background:#111315;color:#f5f7fb;">
        <div class="service-shell-app-shell" style="max-width:640px;margin:0 auto;">
          <h1 style="font-size:1.25rem;margin:0 0 12px;">${escape(getAppDisplayName())} — servisní režim</h1>
          <p style="color:#fca5a5;margin:0 0 8px;">Rozhraní se nepodařilo vykreslit. Podrobnosti v konzoli prohlížeče.</p>
          <pre style="white-space:pre-wrap;font-size:12px;opacity:0.85;border:1px solid rgba(255,255,255,0.12);padding:12px;border-radius:8px;">${msg}</pre>
          <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:16px;">
            <button type="button" class="btn btn-primary" onclick="window.location.reload()">Obnovit stránku</button>
            <button type="button" class="btn btn-secondary" onclick="window.serviceShell && window.serviceShell.load && window.serviceShell.load(true)">Znovu načíst data</button>
          </div>
        </div>
      </div>
    `;
  }

  function render() {
    if (!state.mounted) return;
    const intakeFocusSnap = state.activeSection === 'intake'
      ? (captureIntakeFocus() || (state._intakeFocusField
        ? { field: state._intakeFocusField, start: state._intakeCaretPos, end: state._intakeCaretPos }
        : null))
      : null;
    syncMobileNavScrollLock();
    const root = getRoot();
    try {
      const topBar = ServiceTopBar();
      const nav = ServiceNav();
      const banner = activeVehicleBanner();
      const section = currentSectionHtmlSafe();
      root.innerHTML = `
      <div class="service-shell-root ${isMobileViewport() ? 'service-shell-root--mobile' : ''}" data-service-shell="root" data-service-active-section="${escape(String(state.activeSection || '').trim())}">
        ${nav}
        <div class="service-shell-app-shell" style="flex: 1; display: flex; flex-direction: column; width: 100%;">
          ${topBar}
          ${banner}
          ${section}
        </div>
        ${renderFilterSheet()}
      </div>
      `;
      if (typeof window.tickPragueNavbarClocks === 'function') {
        window.tickPragueNavbarClocks();
      }
      if (typeof window.refreshWorkspaceModeSwitcher === 'function') {
        window.refreshWorkspaceModeSwitcher();
      }
      mountRemindersOverdueOverlayIfNeeded();
      if (intakeFocusSnap) {
        restoreIntakeFocus(intakeFocusSnap);
      }
    } catch (error) {
      console.error('[SERVICE_SHELL] render failed:', error);
      try {
        removeRemindersOverdueOverlayMount();
        root.innerHTML = renderFatalShellFallback(error);
      } catch (e2) {
        console.error('[SERVICE_SHELL] fatal shell fallback failed:', e2);
        root.innerHTML = '';
        root.textContent = 'Servisní workspace: kritická chyba vykreslení. Obnovte stránku.';
      }
    }
  }

  window.serviceShell = {
    init,
    mount,
    unmount,
    load,
    render,
    navigate,
    handleNavRailClick,
    closeNavFlyouts,
    toggleTheme,
    setTheme,
    setSearchTerm,
    setSortBy,
    setKpiFilter,
    openFilterSheet,
    closeFilterSheet,
    setShowCancelledReservations,
    setShowCompletedReminders,
    setInvoiceStatusFilter,
    setInvoiceSearchTerm,
    toggleAccountMenu,
    toggleMobileNav,
    closeAccountMenu,
    openAccountSettings,
    openLicenseSettings,
    savePartnerPublicProfile,
    openModal,
    closeModal,
    handleModalBackdrop,
    showServiceToast,
    runModalAction,
    reloadModalData,
    logout,
    openServiceToolsModal,
    openIntakeFlow,
    openOcrPlaceholder,
    quickLoadVehicle,
    openWorkOrderFromQuickIntake,
    quickIntakeSet,
    quickIntakeChecklist,
    setIntakeDraftField,
    setIntakeChecklistItem,
    cancelIntakeLookupDebounce,
    lookupVehicleForIntake,
    openIntakeCreateVehicleForm,
    closeIntakeCreateVehicleForm,
    createUnownedVehicleFromIntake,
    createWorkAccessFromIntake,
    loadSafeHistoryFromIntake,
    requestVehicleAccessFromIntake,
    startServiceIntake,
    createWorkOrderFromIntake,
    openAuthorizationDetail,
    openGdprInfo,
    openSearchResults,
    closeSearchResults,
    scrollToRisks,
    scrollToAuthorizations,
    openRiskTarget,
    searchCustomers,
    linkCustomerFromLookup,
    linkCustomerById,
    sendInvitationFromSearch,
    openAddCustomerModal,
    linkExistingCustomerByEmail,
    patchAddCustomerQuickLinkDraft,
    patchCreateCustomerDraft,
    submitCreateCustomer,
    openCustomerLinkNoteModal,
    submitCustomerLinkNote,
    unlinkCustomer,
    searchVehicles,
    openProvisionUnownedVehicleModal,
    provisionUnownedVehicleFromLookup,
    requestVehicleAccess,
    openVehicleFromLookup,
    openVehicleFromLookupByIndex,
    openCreateWorkOrderFromLookup,
    openCreateWorkOrderFromLookupByIndex,
    openCreateWorkOrderModal,
    populateCreateVehicleOptions,
    submitCreateWorkOrderModal,
    openWorkOrderDetailModal,
    submitWorkOrderDetailUpdate,
    submitWorkOrderLabor,
    submitWorkOrderPart,
    submitWorkOrderTime,
    submitWorkOrderComplete,
    submitWorkOrderServiceRecord,
    handleWorkOrderPhotoSelection,
    triggerWorkOrderPhotoUpload,
    submitWorkOrderPhotoVisibility,
    deleteWorkOrderPhoto,
    openWorkOrderPhotoPreview,
    reloadWorkOrderDetailModal,
    createWorkOrderQuote,
    createWorkOrderInvoice,
    saveWorkOrderBillingContact,
    loadVehicleTimeline,
    setWorkOrderLimitedNotice,
    openWorkOrderVehicleContext,
    openAddVehicleModal,
    submitAddVehicleModal,
    appendWorkItemDraft,
    appendQuoteItemRow,
    appendInvoiceLineRow,
    removeInvoiceLineRow,
    updateInvoiceDraftTotals,
    openFirstRecordForQuote,
    triggerServiceRecordPhotoPicker,
    handleServiceRecordPhotoSelection,
    openServiceRecordModal,
    submitServiceRecordModal,
    openQuoteModal,
    openBillingQuoteDetail,
    openBillingInvoiceDetail,
    createQuoteFromRecord,
    createInvoiceFromQuote,
    shareQuotePdf,
    copyQuotePublicLinkByUrl,
    copyQuotePublicLink,
    openQuotePublicLink,
    emailQuotePublicLink,
    shareQuoteSmsTemplate,
    openCreateReminderModal,
    submitCreateReminderModal,
    openCustomerDetailModal,
    setVehicleQuoteListPrefs,
    openVehicleDetailModal,
    openVehicleQrModal,
    openPublicHistoryFromModal,
    sharePublicHistoryFromModal,
    copyPublicHistoryFromModal,
    openDocumentDetailModal,
    openReservationDetailModal,
    openReminderDetailModal,
    markOverdueReminderDoneFromPrompt,
    openOverdueReminderRescheduleStep,
    backOverdueReminderPromptToAction,
    submitOverdueReminderReschedule,
    dismissOverdueReminderPromptAndContinue,
    updateReservationStatus,
    deleteReservation,
    deleteReminder,
    populateCustomerVehicleSelect,
    openCreateInvoiceModal,
    submitCreateInvoiceModal,
    openServiceInvoicePdf,
    openServiceInvoiceDetailModal,
    issueServiceInvoiceFromModal,
    cancelServiceInvoiceFromModal,
    setCustomerSearchQuery,
    setVehicleLookupQuery,
    refreshPayrollModule,
    setPayrollPeriod,
    patchPayrollAttendance,
    generatePayrollAttendanceMonth,
    generatePayrollPayslipsMonth,
    recalculatePayrollPayslip,
    closePayrollPayslip,
    refreshPayrollJournal,
    exportPayrollJournalCsv,
    createPayrollJmhz,
    buildPayrollJmhzZip,
    downloadPayrollJmhz,
    submitPayrollOfficeCreate,
    submitPayrollEmployeeCreate,
    submitPayrollEmployeeUpdate,
    openPayrollEmployeeDetail,
    state,
    readServiceSectionFromLocation,
    mapSection,
  };

  window.serviceShellGetActiveSection = function serviceShellGetActiveSection() {
    return String(state.activeSection || defaultSection);
  };

  window.onServiceHistoryExpandClick = function(event, vid, rid) {
    event.preventDefault();
    event.stopPropagation();
    if (window.serviceShell && typeof window.serviceShell.openServiceRecordModal === 'function') {
      window.serviceShell.openServiceRecordModal(vid, rid);
    }
  };

  window.renderServiceWorkspace = function () {
    if (isServiceRole()) {
      return render();
    }
    if (typeof originalRenderServiceWorkspace === 'function') {
      return originalRenderServiceWorkspace.apply(this, arguments);
    }
  };

  window.loadServiceWorkspace = function (force = true, silent = false) {
    if (isServiceRole()) {
      return load(force, silent);
    }
    if (typeof originalLoadServiceWorkspace === 'function') {
      return originalLoadServiceWorkspace.apply(this, arguments);
    }
  };

  window.toggleServiceDashboardTheme = function () {
    if (isServiceRole()) {
      return toggleTheme();
    }
  };

  window.handleServiceDashboardNav = function (target) {
    if (isServiceRole()) {
      return navigate(target);
    }
  };

  window.loadHomeDashboard = function () {
    if (isServiceRole()) {
      state.activeSection = 'dashboard';
      return mount();
    }
    if (typeof originalLoadHomeDashboard === 'function') {
      return originalLoadHomeDashboard.apply(this, arguments);
    }
  };

  window.switchTab = function (tab, options = {}) {
    if (isServiceRole()) {
      const mapped = mapSection(tab);
      if (mapped) {
        return navigate(mapped, options);
      }
    }
    if (typeof originalSwitchTab === 'function') {
      return originalSwitchTab.call(this, tab, options);
    }
  };

  window.showDashboard = function () {
    if (isServiceRole()) {
      return mount();
    }
    if (typeof originalShowDashboard === 'function') {
      return originalShowDashboard.apply(this, arguments);
    }
  };

  window.showLogin = function () {
    unmount();
    if (typeof originalShowLogin === 'function') {
      return originalShowLogin.apply(this, arguments);
    }
  };

  window.openServiceDashboardCreateModal = function () {
    if (isServiceRole()) {
      return openCreateWorkOrderModal();
    }
    if (typeof originalOpenServiceDashboardCreateModal === 'function') {
      return originalOpenServiceDashboardCreateModal.apply(this, arguments);
    }
  };

  window.openServiceDashboardWorkOrderDetail = function () {
    if (isServiceRole()) {
      return openWorkOrderDetailModal.apply(this, arguments);
    }
    if (typeof originalOpenServiceDashboardWorkOrderDetail === 'function') {
      return originalOpenServiceDashboardWorkOrderDetail.apply(this, arguments);
    }
  };

  window.submitServiceDashboardDetailUpdate = function () {
    if (isServiceRole()) {
      return submitWorkOrderDetailUpdate.apply(this, arguments);
    }
    if (typeof originalSubmitServiceDashboardDetailUpdate === 'function') {
      return originalSubmitServiceDashboardDetailUpdate.apply(this, arguments);
    }
  };

  window.openServiceAddVehicleForCustomer = function (customerId) {
    if (isServiceRole()) {
      return openAddVehicleModal(customerId);
    }
    if (typeof originalOpenServiceAddVehicleForCustomer === 'function') {
      return originalOpenServiceAddVehicleForCustomer.apply(this, arguments);
    }
  };

  window.applyAppUiThemeFromStorage = applyAppUiThemeFromStorage;
  window.toggleAppUiTheme = toggleAppUiTheme;

  try {
    if (
      isServiceRole()
      && !state.mounted
      && (typeof window.isAuthenticated !== 'function' || window.isAuthenticated())
    ) {
      window.setTimeout(() => {
        if (!state.mounted && isServiceRole()) {
          mount();
        }
      }, 0);
    }
  } catch (bootstrapError) {
    console.warn('[SERVICE_SHELL] bootstrap mount skipped:', bootstrapError?.message || bootstrapError);
  }
})();
