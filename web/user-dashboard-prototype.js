/* Správa vozidel — vizuální prototyp; volitelně READ-ONLY napojení (?real=1). */
(function () {
  'use strict';

  var API_PATHS = { ME: '/api/me', VEHICLES: '/api/v1/vehicles' };

  var DEMO_USER = { firstName: 'Tomáš', lastName: 'Novák' };
  var DEMO_SUMMARY = {
    vehicles: 3,
    stkSoon: 1,
    reminders: 2,
  };

  var DEMO_VEHICLES = [
    {
      id: 'demo-vw',
      kind: 'van',
      name: 'Volkswagen Transporter T5.1',
      plate: '5M2 1234',
      vin: 'WV2ZZZ7HZ9H123456',
      km: 245680,
      status: 'ok',
      statusLabel: 'V pořádku',
      stk: 'za 42 dní',
      insurance: 'v pořádku',
      service: 'v pořádku',
      toneStk: 'warn',
      toneIns: 'ok',
      toneSvc: 'ok',
      lastService: 'Výměna brzdových destiček — před 3 měsíci',
    },
    {
      id: 'demo-sk',
      kind: 'suv',
      name: 'Škoda Kodiaq 2.0 TDI 4x4',
      plate: '9A2 5518',
      vin: 'TMBLE9NSXKH789012',
      km: 128400,
      status: 'attention',
      statusLabel: 'Vyžaduje pozornost',
      stk: 'za 98 dní',
      insurance: 'kontrola smlouvy',
      service: 'naplánovat rozvody',
      toneStk: 'warn',
      toneIns: 'warn',
      toneSvc: 'warn',
      lastService: 'Brzdy — před 5 měsíci',
    },
    {
      id: 'demo-bmw',
      kind: 'sedan',
      name: 'BMW 320d xDrive',
      plate: '2P4 3391',
      vin: 'WBA3B5C50EK345678',
      km: 198200,
      status: 'service',
      statusLabel: 'V servisu',
      stk: 'po servisu',
      insurance: 'v pořádku',
      service: 'rozpracováno',
      toneStk: 'bad',
      toneIns: 'ok',
      toneSvc: 'bad',
      lastService: 'Diagnostika — probíhá',
    },
  ];

  var DEMO_TIMELINE = [
    { title: 'Výměna brzd', when: '2026 · plán', kind: 'planned' },
    { title: 'STK / měření emisí', when: '2025 · za 42 dní', kind: 'upcoming' },
    { title: 'Olejový servis', when: '2025 · proběhlo', kind: 'done' },
  ];

  var DEMO_UPCOMING = [
    { label: 'STK', value: 'za 42 dní', tone: 'warn' },
    { label: 'Pojištění', value: 'za 320 dní', tone: 'ok' },
    { label: 'Olejový servis', value: 'za 5 600 km / 4 měs.', tone: 'neutral' },
  ];

  var DEMO_DOCS = [
    { name: 'Velký technický průkaz', state: 'Platný' },
    { name: 'Malý technický průkaz', state: 'Platný' },
    { name: 'Prot. STK a emisí', state: 'Platný' },
    { name: 'Pojistka / ORV', state: 'Platný' },
  ];

  var DEMO_ACCESS = [
    {
      name: 'TooZServis',
      accessType: 'Plný přístup k vozidlu',
      badge: 'Schváleno',
      badgeKind: 'ok',
    },
    {
      name: 'AutoPoint Praha',
      accessType: 'Základní přístup',
      badge: 'Čeká na schválení',
      badgeKind: 'warn',
    },
    {
      name: 'Pneu Expert',
      accessType: 'Bez přístupu',
      badge: 'Odmítnuto',
      badgeKind: 'danger',
    },
  ];

  var DEMO_ACTIVE_SERVICES = [
    { name: 'TooZServis', detail: 'Plný přístup · schváleno' },
    { name: 'AutoPoint Praha', detail: 'Žádost o rozšíření' },
  ];

  /** Počet karet vozidel na Přehledu (zbytek přes „Moje vozidla“). */
  var OVERVIEW_VEHICLE_PREVIEW_COUNT = 3;

  var NAV_ITEMS = [
    { key: 'overview', label: 'Přehled', ico: 'home' },
    { key: 'vehicles', label: 'Moje vozidla', ico: 'car' },
    { key: 'history', label: 'Servisní historie', ico: 'wrench' },
    { key: 'reminders', label: 'Připomínky', ico: 'bell' },
    { key: 'documents', label: 'Dokumenty', ico: 'doc' },
    { key: 'services', label: 'Servisy', ico: 'building' },
    { key: 'invoices', label: 'Faktury', ico: 'invoice' },
    { key: 'settings', label: 'Nastavení', ico: 'gear' },
  ];

  var TAB_LABELS =
    'Přehled | Servisní historie | STK / tachometr | Dokumenty | Připomínky | Sdílení se servisy | Faktury'.split(
      ' | ',
    );

  var ICO = {
    home: '<svg class="sv-prototype-svg-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/></svg>',
    car: '<svg class="sv-prototype-svg-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M18.92 6.01C18.72 5.42 18.16 5 17.5 5h-11c-.66 0-1.21.42-1.42 1.01L3 12v8c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1h12v1c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-8l-2.08-5.99zM6.5 16c-.83 0-1.5-.67-1.5-1.5S5.67 13 6.5 13s1.5.67 1.5 1.5S7.33 16 6.5 16zm11 0c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zM5 11l1.5-4.5h11L19 11H5z"/></svg>',
    wrench:
      '<svg class="sv-prototype-svg-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M22.7 19l-9.1-9.1c.9-2.3.4-5-1.5-6.9-2-2-5-2.4-7.4-1.3L9 6 6 9 1.6 4.7C.4 7.1.9 10.1 2.9 12.1c1.9 1.9 4.6 2.4 6.9 1.5l9.1 9.1c.4.4 1 .4 1.4 0l2.3-2.3c.5-.4.5-1.1.1-1.4z"/></svg>',
    bell: '<svg class="sv-prototype-svg-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z"/></svg>',
    doc: '<svg class="sv-prototype-svg-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>',
    building:
      '<svg class="sv-prototype-svg-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 7V3H2v18h20V7H12zM6 19H4v-2h2v2zm0-4H4v-2h2v2zm0-4H4V9h2v2zm0-4H4V5h2v2zm4 12H8v-2h2v2zm0-4H8v-2h2v2zm0-4H8V9h2v2zm0-4H8V5h2v2zm10 12h-8v-2h2v-2h-2v-2h2v-2h-2V9h8v10zm-2-8h-2v2h2v-2zm0 4h-2v2h2v-2z"/></svg>',
    invoice:
      '<svg class="sv-prototype-svg-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>',
    gear: '<svg class="sv-prototype-svg-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M19.14 12.94c.04-.31.06-.63.06-.94 0-.31-.02-.63-.06-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.04.31-.06.63-.06.94s.02.63.06.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/></svg>',
    search:
      '<svg class="sv-prototype-search-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0016 9.5 6.5 6.5 0 109.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>',
    quickStk:
      '<svg class="sv-prototype-quick-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z"/></svg>',
    quickShield:
      '<svg class="sv-prototype-quick-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z"/></svg>',
    quickSvc:
      '<svg class="sv-prototype-quick-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M22.7 19l-9.1-9.1c.9-2.3.4-5-1.5-6.9-2-2-5-2.4-7.4-1.3L9 6 6 9 1.6 4.7C.4 7.1.9 10.1 2.9 12.1c1.9 1.9 4.6 2.4 6.9 1.5l9.1 9.1c.4.4 1 .4 1.4 0l2.3-2.3c.5-.4.5-1.1.1-1.4z"/></svg>',
    bellRing:
      '<svg class="sv-prototype-svg-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z"/></svg>',
    menu: '<svg class="sv-prototype-svg-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z"/></svg>',
    key: '<svg class="sv-prototype-access-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12.65 10A5.99 5.99 0 007 6a6 6 0 106.65 4H17l4 4v2h-2v3h-3v-3h-3.35zM7.5 9a1.5 1.5 0 100 3 1.5 1.5 0 000-3z"/></svg>',
  };

  function heroCarSvg() {
    return (
      '<svg class="sv-prototype-hero-car-svg" viewBox="0 0 400 175" aria-hidden="true" focusable="false">' +
      '<defs><linearGradient id="svH1" x1="0%" y1="0%" x2="100%" y2="100%">' +
      '<stop offset="0%" stop-color="#1e3a8a"/><stop offset="100%" stop-color="#2563eb"/></linearGradient>' +
      '<linearGradient id="svH2" x1="0%" y1="0%" x2="0%" y2="100%">' +
      '<stop offset="0%" stop-color="#93c5fd"/><stop offset="100%" stop-color="#1d4ed8"/></linearGradient>' +
      '<filter id="svHs" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur in="SourceAlpha" stdDeviation="4"/><feOffset dy="8" result="o"/><feFlood flood-color="rgba(11,31,122,0.25)"/><feComposite in2="o" operator="in"/><feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>' +
      '<path d="M280 118 L340 88 L380 90 L395 108 L395 128 L275 128 Z" fill="rgba(30,41,59,0.12)"/>' +
      '<ellipse cx="200" cy="138" rx="175" ry="14" fill="rgba(11,31,122,0.07)"/>' +
      '<g filter="url(#svHs)">' +
      '<path d="M48 102 L118 78 L268 74 L338 86 L368 104 L368 122 L38 122 Z" fill="url(#svH1)"/>' +
      '<path d="M125 80 L248 78 L318 88 L328 108 L98 110 Z" fill="url(#svH2)" opacity="0.88"/>' +
      '<rect x="142" y="86" width="52" height="24" rx="4" fill="rgba(255,255,255,0.28)"/>' +
      '<rect x="258" y="88" width="44" height="20" rx="3" fill="rgba(255,255,255,0.22)"/>' +
      '<circle cx="108" cy="122" r="16" fill="#0f172a"/><circle cx="108" cy="122" r="7" fill="#475569"/>' +
      '<circle cx="278" cy="122" r="16" fill="#0f172a"/><circle cx="278" cy="122" r="7" fill="#475569"/>' +
      '<circle cx="348" cy="116" r="12" fill="#0f172a"/><circle cx="348" cy="116" r="5" fill="#64748b"/>' +
      '</g></svg>'
    );
  }

  function vehicleSilhouette(kind, uid) {
    var u = (uid || 'x').replace(/[^a-z0-9]/gi, '');
    var gVan = 'svGv' + u;
    var gSuv = 'svGs' + u;
    var gSed = 'svGd' + u;
    if (kind === 'van') {
      return (
        '<svg class="sv-prototype-card-car" viewBox="0 0 280 108" aria-hidden="true">' +
        '<defs><linearGradient id="' +
        gVan +
        '" x1="0" y1="0" x2="1" y2="1">' +
        '<stop offset="0%" stop-color="#1d4ed8"/><stop offset="55%" stop-color="#3b82f6"/><stop offset="100%" stop-color="#64748b"/></linearGradient></defs>' +
        '<ellipse cx="68" cy="100" rx="15" ry="4.5" fill="rgba(15,23,42,0.22)"/>' +
        '<ellipse cx="212" cy="100" rx="15" ry="4.5" fill="rgba(15,23,42,0.22)"/>' +
        '<path fill="url(#' +
        gVan +
        ')" d="M18 56 L68 38 L212 36 L252 46 L266 60 L266 70 L14 70 Z"/>' +
        '<rect x="92" y="42" width="40" height="19" rx="2" fill="rgba(255,255,255,0.32)"/>' +
        '<circle cx="62" cy="70" r="12" fill="#0f172a"/><circle cx="62" cy="70" r="5" fill="#64748b"/>' +
        '<circle cx="208" cy="70" r="12" fill="#0f172a"/><circle cx="208" cy="70" r="5" fill="#64748b"/></svg>'
      );
    }
    if (kind === 'suv') {
      return (
        '<svg class="sv-prototype-card-car" viewBox="0 0 280 108" aria-hidden="true">' +
        '<defs><linearGradient id="' +
        gSuv +
        '" x1="0" y1="0" x2="1" y2="1">' +
        '<stop offset="0%" stop-color="#020617"/><stop offset="45%" stop-color="#1e293b"/><stop offset="100%" stop-color="#475569"/></linearGradient></defs>' +
        '<ellipse cx="84" cy="100" rx="13" ry="4" fill="rgba(0,0,0,0.35)"/>' +
        '<ellipse cx="218" cy="100" rx="13" ry="4" fill="rgba(0,0,0,0.35)"/>' +
        '<path fill="url(#' +
        gSuv +
        ')" d="M24 60 L98 42 L192 40 L248 50 L262 62 L262 72 L18 72 Z"/>' +
        '<path fill="rgba(255,255,255,0.16)" d="M108 46 L182 44 L228 52 L232 64 L102 66 Z"/>' +
        '<circle cx="82" cy="72" r="11" fill="#020617"/><circle cx="82" cy="72" r="4.5" fill="#64748b"/>' +
        '<circle cx="218" cy="72" r="11" fill="#020617"/><circle cx="218" cy="72" r="4.5" fill="#64748b"/></svg>'
      );
    }
    return (
      '<svg class="sv-prototype-card-car" viewBox="0 0 280 108" aria-hidden="true">' +
      '<defs><linearGradient id="' +
      gSed +
      '" x1="0" y1="0" x2="1" y2="1">' +
      '<stop offset="0%" stop-color="#e5e7eb"/><stop offset="45%" stop-color="#cbd5e1"/><stop offset="100%" stop-color="#94a3b8"/></linearGradient></defs>' +
      '<ellipse cx="72" cy="102" rx="12" ry="3.8" fill="rgba(15,23,42,0.14)"/>' +
      '<ellipse cx="214" cy="102" rx="12" ry="3.8" fill="rgba(15,23,42,0.14)"/>' +
      '<path fill="url(#' +
      gSed +
      ')" d="M20 58 L90 46 L202 44 L254 54 L264 66 L264 74 L16 74 Z"/>' +
      '<path fill="rgba(255,255,255,0.55)" d="M112 50 L198 48 L238 58 L240 68 L110 70 Z"/>' +
      '<circle cx="72" cy="74" r="10" fill="#374151"/><circle cx="72" cy="74" r="4" fill="#d1d5db"/>' +
      '<circle cx="210" cy="74" r="10" fill="#374151"/><circle cx="210" cy="74" r="4" fill="#d1d5db"/></svg>'
    );
  }

  function detailVehicleSvg(kind, uid) {
    return vehicleSilhouette(kind || 'sedan', uid);
  }

  var state = {
    activeNav: 'overview',
    view: 'overview',
    activeVehicleId: null,
    activeTabIdx: 0,
    toastTimer: null,
    cardFlashTimer: null,
    searchQuery: '',
    vehicleFilter: 'all',
    vehicleListMode: 'grid',
    vehicleSort: 'activity',
    dataSource: 'demo',
    runtimeVehicles: null,
    currentMe: null,
    detailTimelineIsSample: true,
    loginHref: 'index.html',
    protoDiag: {
      meStatus: null,
      authenticated: false,
      vehiclesStatus: null,
      vehiclesCount: null,
    },
  };

  function getQueryFlag(name) {
    try {
      var q = new URLSearchParams(window.location.search || '');
      var v = (q.get(name) || '').trim().toLowerCase();
      if (v === '1' || v === 'true' || v === 'yes') return true;
      return false;
    } catch (e) {
      return false;
    }
  }

  /** Stejný zdroj tokenu jako service-shell.js (Bearer pro /api/*). */
  function getStoredAccessToken() {
    try {
      if (typeof localStorage !== 'undefined') {
        var a = localStorage.getItem('accessToken');
        if (a && String(a).trim()) return String(a).trim();
        var t = localStorage.getItem('token');
        if (t && String(t).trim()) return String(t).trim();
      }
      if (typeof sessionStorage !== 'undefined') {
        var s = sessionStorage.getItem('accessToken');
        if (s && String(s).trim()) return String(s).trim();
      }
    } catch (e) {}
    return null;
  }

  function authHeadersJson() {
    var h = { Accept: 'application/json' };
    var tok = getStoredAccessToken();
    if (tok) h['Authorization'] = 'Bearer ' + tok;
    return h;
  }

  function isSessionAuthenticated(me) {
    if (!me || typeof me !== 'object') return false;
    if (me.authenticated === true) return true;
    if (me.is_authenticated === true) return true;
    if (me.user != null && typeof me.user === 'object') return true;
    var em = me.email != null ? me.email : me.user_email;
    if (em != null && String(em).trim() !== '') return true;
    if (me.tenant_id != null && me.tenant_id !== '') return true;
    if (me.account_id != null && me.account_id !== '') return true;
    if (me.authenticated === false) return false;
    return false;
  }

  function extractVehicles(payload) {
    if (payload == null) return [];
    if (Array.isArray(payload)) return payload;
    if (typeof payload !== 'object') return null;
    if (Array.isArray(payload.vehicles)) return payload.vehicles;
    if (Array.isArray(payload.items)) return payload.items;
    if (Array.isArray(payload.data)) return payload.data;
    return null;
  }

  function fetchAllowedApi(path) {
    var p = String(path || '');
    if (p !== API_PATHS.ME && p !== API_PATHS.VEHICLES) {
      return Promise.reject(new Error('api path not allowed'));
    }
    return fetch(p, {
      method: 'GET',
      credentials: 'include',
      headers: authHeadersJson(),
    }).then(function (res) {
      var status = res.status;
      if (p === API_PATHS.ME && (status === 401 || status === 403)) {
        return res
          .json()
          .catch(function () {
            return { authenticated: false };
          })
          .then(function (j) {
            var me = j && typeof j === 'object' ? j : { authenticated: false };
            return { status: status, data: me };
          });
      }
      if (status === 401 || status === 403) {
        var err = new Error('HTTP ' + status);
        err.status = status;
        throw err;
      }
      if (!res.ok) {
        var e2 = new Error('HTTP ' + status);
        e2.status = status;
        throw e2;
      }
      return res.json().catch(function () {
        return null;
      }).then(function (json) {
        return { status: status, data: json };
      });
    });
  }

  function loadSession() {
    return fetchAllowedApi(API_PATHS.ME).then(function (r) {
      var me = r.data || {};
      var ok = isSessionAuthenticated(me);
      return { ok: ok, me: me, status: r.status };
    });
  }

  function loadVehicles() {
    return fetchAllowedApi(API_PATHS.VEHICLES);
  }

  function parseIsoDate(s) {
    if (s == null || s === '') return null;
    var str = String(s);
    var d = new Date(str.length === 10 ? str + 'T12:00:00' : str);
    return isNaN(d.getTime()) ? null : d;
  }

  function daysUntil(target) {
    if (!target) return null;
    var now = new Date();
    var a = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    var b = new Date(target.getFullYear(), target.getMonth(), target.getDate());
    return Math.round((b - a) / 86400000);
  }

  function detectVehicleKind(title, bodyType) {
    var t = ((title || '') + ' ' + (bodyType || '')).toLowerCase();
    if (/\b(transporter|van|t5|t6|caddy|multivan)\b/.test(t)) return 'van';
    if (/\b(kodiaq|suv|q3|q5|q7|xdrive|country|scout)\b/.test(t)) return 'suv';
    return 'sedan';
  }

  /**
   * Detect MDČR / VIN decoder / technical specification blobs that must never
   * be shown as “servisní” stav (quick card, Poslední servis, apod.).
   */
  function isTechnicalDecodeText(value) {
    if (value == null) return false;
    var t = String(value).toLowerCase();
    var p = [
      'dekódováno z',
      'decodováno z',
      'mdcr',
      'local_vin',
      'pneumatik',
      'kola a ',
      'emisní norma',
      'emisni norma',
      'euro ',
      'euro5',
      'euro6',
      'typ motoru',
      'objem motoru',
      'zdvihový objem',
      'zdvihovy objem',
      'výkon',
      'vykon',
      'karoserie',
      'karosérie',
      'druh vozidla',
      'hmotnosti vozidla',
      'technický průkaz',
      'technicky prukaz',
      'mdv/',
      'vin dekod',
    ];
    for (var i = 0; i < p.length; i++) {
      if (t.indexOf(p[i]) >= 0) return true;
    }
    return false;
  }

  /** Vrací bezpečný servisní text nebo null (max ~70 znaků). */
  function normalizeServiceText(value) {
    if (value == null || typeof value !== 'string') return null;
    var s = value.replace(/\s+/g, ' ').trim();
    if (!s) return null;
    if (isTechnicalDecodeText(s)) return null;
    var maxLen = 70;
    if (s.length > maxLen) return s.slice(0, maxLen - 1) + '…';
    return s;
  }

  function tryPushServiceCandidate(buf, val) {
    var n = normalizeServiceText(val);
    if (n) buf.push(n);
  }

  /** Servisní pole z API — výhradně povolené zdroje; nikdy technical_* / mdcr / vin summary. */
  function mapServiceFieldsFromApi(v, statusLower) {
    var st = String(statusLower || '').toLowerCase();
    if (st === 'service' || st === 'in_service') {
      return {
        service: 'v servisu',
        lastService: 'V servisu',
        serviceLabel: 'Probíhá servisní zakázka',
        toneSvc: 'bad',
      };
    }

    var cand = [];

    var rec = v.latest_service_record;
    if (rec && typeof rec === 'object' && !Array.isArray(rec)) {
      tryPushServiceCandidate(cand, rec.title);
      tryPushServiceCandidate(cand, rec.summary);
      tryPushServiceCandidate(cand, rec.description);
      tryPushServiceCandidate(cand, rec.label);
    }
    var wo = v.open_work_order || v.active_service_order;
    if (wo && typeof wo === 'object' && !Array.isArray(wo)) {
      tryPushServiceCandidate(cand, wo.title || wo.name);
      tryPushServiceCandidate(cand, wo.status_label);
      tryPushServiceCandidate(cand, wo.summary);
    }

    var strKeys = ['last_service', 'last_service_label', 'service_summary', 'service_records_summary'];
    for (var i = 0; i < strKeys.length; i++) {
      tryPushServiceCandidate(cand, v[strKeys[i]]);
    }

    tryPushServiceCandidate(cand, v.service_status);

    tryPushServiceCandidate(cand, v.notes);
    tryPushServiceCandidate(cand, v.description);

    var picked = cand.length ? cand[0] : null;

    if (!picked) {
      var rawDt = v.last_service_at != null ? v.last_service_at : v.last_service_date;
      if (rawDt != null && String(rawDt).trim()) {
        var d = parseIsoDate(rawDt);
        if (d) {
          try {
            var line = 'Poslední servis — ' + d.toLocaleDateString('cs-CZ');
            return {
              service: 'evidováno',
              lastService: line,
              serviceLabel: 'Datum posledního servisu',
              toneSvc: 'ok',
            };
          } catch (e2) {}
        }
      }
    }

    if (picked) {
      var short = picked.length > 35 ? picked.slice(0, 32) + '…' : picked;
      return {
        service: short,
        lastService: picked,
        serviceLabel: 'Poslední servis',
        toneSvc: 'ok',
      };
    }

    return {
      service: 'bez záznamu',
      lastService: 'Bez servisního záznamu',
      serviceLabel: 'Doplňte servisní historii',
      toneSvc: 'warn',
    };
  }

  function mapVehicleFromApi(vehicle) {
    var v = vehicle || {};
    var brand = String(v.brand != null ? v.brand : '').trim();
    var model = String(v.model != null ? v.model : '').trim();
    var nick = String(v.nickname != null ? v.nickname : '').trim();
    var disp = v.display_name != null ? String(v.display_name).trim() : '';
    var legacyName = v.name != null ? String(v.name).trim() : '';
    var title =
      disp ||
      nick ||
      [brand, model].filter(Boolean).join(' ').trim() ||
      legacyName ||
      'Vozidlo bez názvu';
    var plate =
      (v.license_plate != null && String(v.license_plate).trim()) ||
      (v.plate != null && String(v.plate).trim()) ||
      (v.registration_number != null && String(v.registration_number).trim()) ||
      '—';
    var vinStr = v.vin != null && String(v.vin).trim() ? String(v.vin).trim() : '—';
    var kmRaw = v.current_mileage_km != null ? v.current_mileage_km : v.mileage_km;
    var km = kmRaw != null && kmRaw !== '' && !isNaN(Number(kmRaw)) ? Number(kmRaw) : null;

    var stkDate = parseIsoDate(v.stk_valid_until);
    var stkDays = stkDate ? daysUntil(stkDate) : null;
    var stk;
    var toneStk;
    if (stkDays == null) {
      stk = 'STK neznámá';
      toneStk = 'ok';
    } else if (stkDays < 0) {
      stk = 'po termínu';
      toneStk = 'bad';
    } else if (stkDays === 0) {
      stk = 'dnes';
      toneStk = 'warn';
    } else if (stkDays <= 45) {
      stk = 'za ' + stkDays + ' ' + (stkDays === 1 ? 'den' : stkDays < 5 ? 'dny' : 'dní');
      toneStk = 'warn';
    } else {
      stk = 'platná';
      toneStk = 'ok';
    }

    var insDate = parseIsoDate(v.insurance_valid_until);
    var insDays = insDate ? daysUntil(insDate) : null;
    var insurance;
    var toneIns;
    if (insDays == null) {
      insurance = 'nezadáno';
      toneIns = 'ok';
    } else if (insDays < 0) {
      insurance = 'po platnosti';
      toneIns = 'bad';
    } else if (insDays <= 30) {
      insurance = 'vyprší brzy';
      toneIns = 'warn';
    } else {
      insurance = 'v pořádku';
      toneIns = 'ok';
    }

    var rawStEarly = String(v.status || '').toLowerCase();
    var svcMap = mapServiceFieldsFromApi(v, rawStEarly);
    var service = svcMap.service;
    var lastService = svcMap.lastService;
    var serviceLabel = svcMap.serviceLabel;
    var toneSvc = svcMap.toneSvc;

    var rawArchived =
      v.archived === true ||
      v.is_archived === true ||
      String(v.lifecycle_state || v.vehicle_state || '').toLowerCase() === 'archived';
    var status = 'ok';
    var statusLabel = 'V pořádku';
    if (rawArchived) {
      status = 'archived';
      statusLabel = 'V archivu';
    } else if (toneStk === 'bad' || toneIns === 'bad') {
      status = 'attention';
      statusLabel = 'Vyžaduje pozornost';
    } else if (String(v.data_trust_state || '').toLowerCase() === 'pending') {
      status = 'pending';
      statusLabel = 'Čeká na schválení';
    }

    var rawSt = rawStEarly;
    if (!rawArchived && (rawSt === 'service' || rawSt === 'in_service')) {
      status = 'service';
      statusLabel = 'V servisu';
    } else if (!rawArchived && rawSt === 'pending') {
      status = 'pending';
      statusLabel = 'Čeká na schválení';
    } else if (!rawArchived && rawSt === 'archived') {
      status = 'archived';
      statusLabel = 'V archivu';
    }

    return {
      id: v.id != null ? String(v.id) : 'vehicle-unknown',
      kind: detectVehicleKind(title, v.body_type),
      name: title,
      plate: plate,
      vin: vinStr,
      km: km,
      status: status,
      statusLabel: statusLabel,
      stk: stk,
      insurance: insurance,
      service: service,
      toneStk: toneStk,
      toneIns: toneIns,
      toneSvc: toneSvc,
      lastService: lastService,
      serviceLabel: serviceLabel,
      _fromApi: true,
      _archived: !!rawArchived,
    };
  }

  function greetingFirstName(me) {
    if (!isSessionAuthenticated(me)) return DEMO_USER.firstName;
    if (me.display_name != null && String(me.display_name).trim()) {
      var p = String(me.display_name).trim().split(/\s+/);
      if (p[0]) return p[0];
    }
    if (me.email) return String(me.email).split('@')[0];
    return DEMO_USER.firstName;
  }

  function profileDisplayName(me) {
    if (!isSessionAuthenticated(me)) return DEMO_USER.firstName + ' ' + DEMO_USER.lastName;
    if (me.display_name != null && String(me.display_name).trim()) return String(me.display_name).trim();
    return me.email ? String(me.email) : DEMO_USER.firstName + ' ' + DEMO_USER.lastName;
  }

  function profileInitials(me) {
    var n = profileDisplayName(me);
    var parts = n.split(/\s+/).filter(Boolean);
    if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    if (n.length >= 2) return n.slice(0, 2).toUpperCase();
    return 'U';
  }

  function getVehicleList() {
    return state.runtimeVehicles || DEMO_VEHICLES;
  }

  function getVehicleStatus(vehicle) {
    var v = vehicle || {};
    var s = String(v.status || 'ok').toLowerCase();
    if (s === 'attention' || s === 'warning') return 'attention';
    if (s === 'service' || s === 'in_service') return 'service';
    if (s === 'pending') return 'pending';
    if (s === 'archived') return 'archived';
    if (v._archived === true) return 'archived';
    return 'ok';
  }

  function getVehicleStatusLabel(vehicle) {
    try {
      if (vehicle && vehicle.statusLabel) return String(vehicle.statusLabel);
    } catch (e) {}
    var st = getVehicleStatus(vehicle);
    if (st === 'ok') return 'V pořádku';
    if (st === 'attention') return 'Vyžaduje pozornost';
    if (st === 'service') return 'V servisu';
    if (st === 'pending') return 'Čeká na schválení';
    if (st === 'archived') return 'V archivu';
    return 'V pořádku';
  }

  function getVehicleStatusTone(vehicle) {
    var st = getVehicleStatus(vehicle);
    if (st === 'ok') return 'success';
    if (st === 'attention' || st === 'pending') return 'warning';
    if (st === 'service') return 'danger';
    if (st === 'archived') return 'neutral';
    return 'success';
  }

  function matchesSearch(v, q) {
    if (!q) return true;
    var hay = ((v.name || '') + ' ' + (v.plate || '') + ' ' + (v.vin || '')).toLowerCase();
    return hay.indexOf(q) >= 0;
  }

  function filterVehicles(vehicles, filter, searchQuery) {
    var q = (searchQuery || '').trim().toLowerCase();
    var f = filter || 'all';
    var list = Array.isArray(vehicles) ? vehicles.slice() : [];
    list = list.filter(function (v) {
      return matchesSearch(v, q);
    });
    if (f === 'all') return list;
    if (f === 'ok') return list.filter(function (v) {
      return getVehicleStatus(v) === 'ok';
    });
    if (f === 'attention') return list.filter(function (v) {
      var st = getVehicleStatus(v);
      return st === 'attention' || st === 'pending';
    });
    if (f === 'service') return list.filter(function (v) {
      return getVehicleStatus(v) === 'service';
    });
    if (f === 'archived') return list.filter(function (v) {
      return getVehicleStatus(v) === 'archived';
    });
    return list;
  }

  function getVehicleFilterCounts(vehicles) {
    var list = Array.isArray(vehicles) ? vehicles : [];
    var c = { all: list.length, ok: 0, attention: 0, service: 0, archived: 0 };
    for (var i = 0; i < list.length; i++) {
      var st = getVehicleStatus(list[i]);
      if (st === 'ok') c.ok++;
      else if (st === 'attention' || st === 'pending') c.attention++;
      else if (st === 'service') c.service++;
      else if (st === 'archived') c.archived++;
    }
    return c;
  }

  function getOverviewTopVehicles(vehicles, searchQuery) {
    var filtered = filterVehicles(vehicles, 'all', searchQuery);
    return filtered.slice(0, OVERVIEW_VEHICLE_PREVIEW_COUNT);
  }

  function getOverviewSummary(vehicles) {
    var list = vehicles || [];
    var base = computeSummaryFromVehicles(list);
    var svcAttention = 0;
    for (var i = 0; i < list.length; i++) {
      var st = getVehicleStatus(list[i]);
      if (st === 'attention' || st === 'service' || st === 'pending') svcAttention++;
    }
    var serviceNotifications = state.dataSource === 'demo' && !state.runtimeVehicles ? 1 : Math.min(svcAttention, 9);
    return {
      vehicles: base.vehicles,
      stkSoon: base.stkSoon,
      reminders: base.reminders,
      serviceTabloid: serviceNotifications,
    };
  }

  function computeSummaryFromVehicles(list) {
    list = list || [];
    var n = list.length;
    if (state.dataSource === 'real' && n === 0) {
      return { vehicles: 0, stkSoon: 0, reminders: 0 };
    }
    var stkSoon = 0;
    var insSoon = 0;
    for (var i = 0; i < list.length; i++) {
      if (list[i].toneStk === 'warn' || list[i].toneStk === 'bad') stkSoon++;
      if (list[i].toneIns === 'warn' || list[i].toneIns === 'bad') insSoon++;
    }
    var reminders = insSoon + stkSoon > 0 ? Math.min(insSoon + stkSoon, 9) : n > 0 ? 0 : 2;
    if (state.dataSource === 'demo' && !state.runtimeVehicles) reminders = DEMO_SUMMARY.reminders;
    if (state.dataSource === 'demo' && !state.runtimeVehicles) stkSoon = DEMO_SUMMARY.stkSoon;
    return { vehicles: n, stkSoon: stkSoon, reminders: reminders };
  }

  function renderHeroSummaryHtml(sum) {
    return (
      'Máte <span class="sv-prototype-stat-pill sv-prototype-stat-pill--navy">' +
      sum.vehicles +
      '</span> vozidel, ' +
      '<span class="sv-prototype-stat-pill sv-prototype-stat-pill--amber">' +
      sum.stkSoon +
      '</span> blížící se STK, ' +
      '<span class="sv-prototype-stat-pill sv-prototype-stat-pill--blue">' +
      sum.reminders +
      '</span> aktivní připomínky a ' +
      '<span class="sv-prototype-stat-pill sv-prototype-stat-pill--navy">' +
      sum.serviceTabloid +
      '</span> nové upozornění od servisu.'
    );
  }

  function formatTodayTimeHm() {
    try {
      return new Date().toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit' });
    } catch (e) {
      return '';
    }
  }

  function shortVin(v) {
    var s = v && v.vin != null ? String(v.vin) : '';
    if (!s || s === '—') return s || '—';
    if (s.length <= 11) return s;
    return s.slice(0, 10) + '…';
  }

  function fleetRequiresAttention(list) {
    list = list || [];
    for (var i = 0; i < list.length; i++) {
      var st = getVehicleStatus(list[i]);
      if (st !== 'ok' && st !== 'archived') return true;
    }
    return false;
  }

  function sortVehiclesCatalog(list) {
    var copy = (list || []).slice();
    if (state.vehicleSort === 'name') {
      copy.sort(function (a, b) {
        return String(a.name || '').localeCompare(String(b.name || ''), 'cs');
      });
      return copy;
    }
    var order = { service: 0, attention: 1, pending: 2, ok: 3, archived: 4 };
    copy.sort(function (a, b) {
      var da = order[getVehicleStatus(a)] != null ? order[getVehicleStatus(a)] : 9;
      var db = order[getVehicleStatus(b)] != null ? order[getVehicleStatus(b)] : 9;
      if (da !== db) return da - db;
      return String(a.name || '').localeCompare(String(b.name || ''), 'cs');
    });
    return copy;
  }

  function legacyIndexHref() {
    try {
      var p = window.location.pathname || '';
      var i = p.lastIndexOf('/');
      var base = i >= 0 ? p.slice(0, i + 1) : '/web/';
      return base + 'index.html';
    } catch (e) {
      return 'index.html';
    }
  }

  function navigateToLegacy(screen) {
    var msg =
      screen === 'service-history'
        ? 'Otevíráme hlavní aplikaci — servisní historie.'
        : screen === 'documents'
          ? 'Otevíráme hlavní aplikaci — dokumenty.'
          : screen === 'services'
            ? 'Otevíráme hlavní aplikaci — servisy a sdílení.'
            : screen === 'add-vehicle'
              ? 'Přejdete do aplikace, kde můžete vozidlo přidat.'
              : 'Otevíráme hlavní aplikaci.';
    showToast(msg);
    window.setTimeout(function () {
      try {
        window.location.href = legacyIndexHref();
      } catch (e2) {}
    }, 380);
  }

  function computeQuickCardsData(list) {
    list = list || [];
    var stkN = 0;
    var stkSample = '';
    var insWarn = 0;
    var insBad = 0;
    var svcWarn = 0;
    var docPending = 0;
    for (var i = 0; i < list.length; i++) {
      var v = list[i];
      if (v.toneStk === 'warn' || v.toneStk === 'bad') {
        stkN++;
        if (!stkSample) stkSample = String(v.stk || '');
      }
      if (v.toneIns === 'warn') insWarn++;
      if (v.toneIns === 'bad') insBad++;
      if (v.toneSvc === 'warn' || v.toneSvc === 'bad') svcWarn++;
    }
    if (state.dataSource === 'demo' && !state.runtimeVehicles) docPending = 2;
    var firstVan = null;
    for (var j = 0; j < list.length; j++) {
      if (list[j].kind === 'van' || j === 0) {
        firstVan = list[j];
        break;
      }
    }
    var svcBlock;
    if (state.dataSource === 'demo' && !state.runtimeVehicles) {
      var lastSvcLine = 'Poslední servis — zkontrolujte v aplikaci';
      if (firstVan && firstVan.lastService) {
        var nd = normalizeServiceText(String(firstVan.lastService));
        lastSvcLine = nd || lastSvcLine;
      } else if (list[0] && list[0].lastService) {
        var nd0 = normalizeServiceText(String(list[0].lastService));
        lastSvcLine = nd0 || lastSvcLine;
      }
      svcBlock = {
        tone: svcWarn > 0 ? 'warning' : 'info',
        title: list.length ? lastSvcLine : 'Servis',
        desc: svcWarn > 0 ? 'Doporučujeme naplánovat servis' : 'Váš vůz je podle údajů v pořádku',
      };
    } else {
      var inSvcFleet = false;
      for (var k = 0; k < list.length; k++) {
        if (getVehicleStatus(list[k]) === 'service') {
          inSvcFleet = true;
          break;
        }
      }
      if (inSvcFleet) {
        svcBlock = {
          tone: 'warning',
          title: 'Vozidlo v servisu',
          desc: 'Zkontrolujte stav servisní zakázky',
        };
      } else {
        var hasRealSvc = false;
        var sampleSvc = '';
        for (var m = 0; m < list.length; m++) {
          var nt = normalizeServiceText(list[m].lastService);
          if (nt && nt !== 'Bez servisního záznamu' && nt !== 'V servisu') {
            hasRealSvc = true;
            sampleSvc = nt;
            break;
          }
        }
        if (!list.length) {
          svcBlock = { tone: 'info', title: 'Servis', desc: 'Žádné vozidlo' };
        } else if (hasRealSvc && sampleSvc) {
          var lim = 52;
          var tail = sampleSvc.length > lim ? sampleSvc.slice(0, lim - 1) + '…' : sampleSvc;
          svcBlock = {
            tone: 'info',
            title: 'Poslední servis — ' + tail,
            desc: 'Zkontrolujte servisní historii v aplikaci',
          };
        } else {
          svcBlock = {
            tone: 'warning',
            title: 'Bez servisního záznamu',
            desc: 'Doplňte první servisní záznam',
          };
        }
      }
    }
    return {
      stk: {
        tone: stkN > 0 ? 'warning' : 'success',
        title: stkN === 0 ? 'STK / SME v pořádku' : stkN === 1 ? '1 vozidlo — ' + stkSample : stkN + ' vozidla — zkontrolujte STK',
        desc: stkN > 0 ? 'Zkontrolujte včas' : 'Žádná blížící se lhůta',
      },
      ins: {
        tone: insWarn + insBad > 0 ? 'warning' : 'success',
        title: insWarn + insBad > 0 ? 'Zkontrolujte pojistné smlouvy' : 'Všechna vozidla v pořádku',
        desc: insWarn + insBad > 0 ? 'Zkontrolujte pojištění' : 'Platné smlouvy',
      },
      svc: svcBlock,
      docs: {
        tone: docPending > 0 ? 'warning' : 'success',
        title: docPending > 0 ? docPending + ' dokumenty čekají na doplnění' : 'Dokumenty v pořádku',
        desc: docPending > 0 ? 'Doplňte chybějící' : 'Žádné chybějící podklady',
      },
    };
  }

  function quickToneClass(tone) {
    if (tone === 'warning') return 'sv-prototype-quick-card--warn';
    if (tone === 'danger') return 'sv-prototype-quick-card--danger';
    if (tone === 'info') return 'sv-prototype-quick-card--info';
    return 'sv-prototype-quick-card--ok';
  }

  function renderQuickCards(root) {
    var host = root.querySelector('[data-sv-quick-grid]');
    if (!host) return;
    var dash = root.querySelector('[data-sv-dashboard-root]');
    if (dash && dash.classList.contains('is-sv-dashboard-loading')) {
      host.innerHTML =
        '<div class="sv-prototype-quick-grid sv-prototype-quick-grid--loading" aria-hidden="true">' +
        '<div class="sv-prototype-skeleton-card sv-prototype-skeleton-quick"></div>' +
        '<div class="sv-prototype-skeleton-card sv-prototype-skeleton-quick"></div>' +
        '<div class="sv-prototype-skeleton-card sv-prototype-skeleton-quick"></div>' +
        '<div class="sv-prototype-skeleton-card sv-prototype-skeleton-quick"></div>' +
        '</div>';
      return;
    }
    var list = getVehicleList();
    var q = computeQuickCardsData(list);
    var rows = [
      { key: 'stk', data: q.stk, ico: 'stk' },
      { key: 'ins', data: q.ins, ico: 'shield' },
      { key: 'svc', data: q.svc, ico: 'svc' },
      { key: 'docs', data: q.docs, ico: 'doc' },
    ];
    var icoMap = { stk: ICO.quickStk, shield: ICO.quickShield, svc: ICO.quickSvc, doc: ICO.doc };
    host.innerHTML = rows
      .map(function (r) {
        var d = r.data;
        return (
          '<button type="button" class="sv-prototype-quick-card ' +
          quickToneClass(d.tone) +
          '" data-sv-quick-action="' +
          r.key +
          '">' +
          '<span class="sv-prototype-quick-card-ico">' +
          (icoMap[r.ico] || ICO.quickStk) +
          '</span>' +
          '<span class="sv-prototype-quick-card-body">' +
          '<span class="sv-prototype-quick-card-cat">' +
          (r.key === 'stk' ? 'STK / SME' : r.key === 'ins' ? 'Pojištění' : r.key === 'svc' ? 'Servis' : 'Dokumenty') +
          '</span>' +
          '<strong class="sv-prototype-quick-card-title">' +
          escapeHtml(d.title) +
          '</strong>' +
          '<span class="sv-prototype-quick-card-desc">' +
          escapeHtml(d.desc) +
          '</span></span>' +
          '<span class="sv-prototype-quick-card-arrow" aria-hidden="true">›</span></button>'
        );
      })
      .join('');
  }

  function renderOverallStatus(root) {
    var host = root.querySelector('[data-sv-overall-status]');
    if (!host) return;
    var dash = root.querySelector('[data-sv-dashboard-root]');
    if (dash && dash.classList.contains('is-sv-dashboard-loading')) {
      host.innerHTML = '<p class="sv-prototype-overall-loading">Načítám…</p>';
      return;
    }
    var list = getVehicleList();
    var bad = fleetRequiresAttention(list);
    var ok = !bad;
    var icon = ok
      ? '<svg class="sv-prototype-overall-ico sv-prototype-overall-ico--ok" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>'
      : '<svg class="sv-prototype-overall-ico sv-prototype-overall-ico--warn" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg>';
    host.innerHTML =
      '<div class="sv-prototype-overall-inner">' +
      '<div class="sv-prototype-overall-text">' +
      '<h3 class="sv-prototype-overall-heading">Celkový stav</h3>' +
      '<p class="sv-prototype-overall-main' +
      (ok ? ' sv-prototype-overall-main--ok' : ' sv-prototype-overall-main--warn') +
      '">' +
      (ok ? 'Vozidla pod kontrolou' : 'Vyžaduje pozornost') +
      '</p>' +
      '<p class="sv-prototype-overall-meta">Poslední aktualizace: dnes v ' +
      escapeHtml(formatTodayTimeHm()) +
      '</p></div>' +
      '<div class="sv-prototype-overall-ico-wrap" aria-hidden="true">' +
      icon +
      '</div></div>';
  }

  function pickVehicleForUpcoming(list, pred) {
    for (var i = 0; i < list.length; i++) {
      if (pred(list[i])) return list[i];
    }
    return null;
  }

  function renderOverviewAside(root) {
    var host = root.querySelector('[data-sv-overview-aside]');
    if (!host) return;
    var list = getVehicleList();
    var demo = state.dataSource === 'demo' && !state.runtimeVehicles;

    var upRows = [];
    if (demo) {
      upRows = DEMO_UPCOMING.map(function (u) {
        return { label: u.label, value: u.value, tone: u.tone, sample: true };
      });
    } else {
      var vStk = pickVehicleForUpcoming(list, function (v) {
        return v.toneStk === 'warn' || v.toneStk === 'bad';
      });
      if (vStk)
        upRows.push({
          label: 'STK',
          value: vStk.name ? vStk.stk + ' · ' + vStk.name : vStk.stk,
          tone: vStk.toneStk === 'bad' ? 'bad' : 'warn',
          sample: false,
        });
      var vOil = list[0];
      if (vOil && vOil.service)
        upRows.push({
          label: 'Servis',
          value: String(vOil.service) + ' · ' + String(vOil.name || ''),
          tone: vOil.toneSvc === 'bad' ? 'bad' : vOil.toneSvc === 'warn' ? 'warn' : 'neutral',
          sample: false,
        });
      var vIns = pickVehicleForUpcoming(list, function (v) {
        return v.toneIns === 'warn' || v.toneIns === 'bad';
      });
      if (!vIns) vIns = list[0];
      if (vIns && vIns.insurance)
        upRows.push({
          label: 'Pojištění',
          value: String(vIns.insurance) + (vIns.name ? ' · ' + vIns.name : ''),
          tone: vIns.toneIns === 'bad' ? 'bad' : vIns.toneIns === 'warn' ? 'warn' : 'ok',
          sample: false,
        });
      if (!upRows.length && list.length)
        upRows.push({
          label: 'Termíny',
          value: 'Žádný blížící se termín podle dostupných údajů.',
          tone: 'neutral',
          sample: false,
        });
    }

    var actRows = [];
    if (demo) {
      actRows = [
        { title: 'Servisní záznam přidán', when: '15. 5. 2026', kind: 'svc' },
        { title: 'Nahrán dokument', when: '12. 5. 2026', kind: 'doc' },
        { title: 'Žádost o přístup od servisu', when: '8. 5. 2026', kind: 'req' },
      ];
    } else {
      actRows = [];
    }

    var accessBody = '';
    if (demo) {
      accessBody =
        '<ul class="sv-prototype-aside-access-list">' +
        DEMO_ACCESS.map(function (a) {
          return (
            '<li><span class="sv-prototype-aside-access-name">' +
            escapeHtml(a.name) +
            '</span><span class="' +
            accessBadgeClass(a.badgeKind) +
            '">' +
            escapeHtml(a.badge) +
            '</span><span class="sv-prototype-aside-access-meta">' +
            escapeHtml(a.accessType) +
            '</span></li>'
          );
        }).join('') +
        '</ul><p class="sv-prototype-sample-tag">Ukázka</p>';
    } else {
      accessBody =
        '<p class="sv-prototype-aside-placeholder">Přístupy servisů budou dostupné po napojení detailních dat.</p>';
    }

    function rowCls(tone) {
      if (tone === 'bad') return 'sv-prototype-aside-upcoming-val--bad';
      if (tone === 'warn') return 'sv-prototype-aside-upcoming-val--warn';
      if (tone === 'ok') return 'sv-prototype-aside-upcoming-val--ok';
      return '';
    }

    host.innerHTML =
      '<div class="sv-prototype-aside-card">' +
      '<h3 class="sv-prototype-aside-title">Blížící se termíny</h3>' +
      '<ul class="sv-prototype-aside-list">' +
      upRows
        .map(function (r) {
          return (
            '<li><span>' +
            escapeHtml(r.label) +
            (r.sample ? ' <span class="sv-prototype-sample-tag sv-prototype-sample-tag--inline">ukázka</span>' : '') +
            '</span><strong class="' +
            rowCls(r.tone) +
            '">' +
            escapeHtml(r.value) +
            '</strong></li>'
          );
        })
        .join('') +
      '</ul></div>' +
      '<div class="sv-prototype-aside-card">' +
      '<h3 class="sv-prototype-aside-title">Poslední aktivita</h3>' +
      (actRows.length
        ? '<ul class="sv-prototype-aside-activity">' +
          actRows
            .map(function (a) {
              return (
                '<li><span class="sv-prototype-act-dot" aria-hidden="true"></span><div><strong>' +
                escapeHtml(a.title) +
                '</strong><span>' +
                escapeHtml(a.when) +
                '</span></div></li>'
              );
            })
            .join('') +
          '</ul>'
        : '<p class="sv-prototype-aside-placeholder">Zatím žádná nedávná aktivita v dostupných datech.</p>') +
      '</div>' +
      '<div class="sv-prototype-aside-card">' +
      '<h3 class="sv-prototype-aside-title">Servisy a přístupy</h3>' +
      accessBody +
      '</div>';
  }

  function renderFilterPills(root) {
    var host = root.querySelector('[data-sv-filter-pills]');
    if (!host) return;
    var list = getVehicleList();
    var c = getVehicleFilterCounts(list);
    var cur = state.vehicleFilter || 'all';
    var defs = [
      { id: 'all', label: 'Všechna' },
      { id: 'ok', label: 'V pořádku' },
      { id: 'attention', label: 'Vyžaduje pozornost' },
      { id: 'service', label: 'V servisu' },
      { id: 'archived', label: 'V archivu' },
    ];
    host.innerHTML = defs
      .map(function (d) {
        var cnt = c[d.id] != null ? c[d.id] : 0;
        var active = cur === d.id ? ' is-active' : '';
        return (
          '<button type="button" class="sv-prototype-filter-pill' +
          active +
          '" data-sv-filter-pick="' +
          d.id +
          '">' +
          escapeHtml(d.label) +
          ' <span class="sv-prototype-filter-count">' +
          cnt +
          '</span></button>'
        );
      })
      .join('');
  }

  function renderCatalogToolbar(root) {
    var sortEl = root.querySelector('[data-sv-sort-select]');
    if (sortEl && sortEl.value !== state.vehicleSort) sortEl.value = state.vehicleSort;
    var gridBtn = root.querySelector('[data-sv-grid-mode="grid"]');
    var listBtn = root.querySelector('[data-sv-grid-mode="list"]');
    if (gridBtn) gridBtn.classList.toggle('is-active', state.vehicleListMode === 'grid');
    if (listBtn) listBtn.classList.toggle('is-active', state.vehicleListMode === 'list');
  }

  function renderCatalogSummary(root) {
    var host = root.querySelector('[data-sv-catalog-summary]');
    if (!host) return;
    var list = getVehicleList();
    var c = getVehicleFilterCounts(list);
    host.innerHTML =
      '<div class="sv-prototype-catalog-summary-grid">' +
      '<div><span class="sv-prototype-cs-label">Celkem</span><strong>' +
      c.all +
      '</strong></div>' +
      '<div><span class="sv-prototype-cs-label">V pořádku</span><strong class="sv-prototype-cs-ok">' +
      c.ok +
      '</strong></div>' +
      '<div><span class="sv-prototype-cs-label">Vyžaduje pozornost</span><strong class="sv-prototype-cs-warn">' +
      c.attention +
      '</strong></div>' +
      '<div><span class="sv-prototype-cs-label">V servisu</span><strong class="sv-prototype-cs-danger">' +
      c.service +
      '</strong></div></div>' +
      '<button type="button" class="sv-prototype-btn-section sv-prototype-catalog-back" data-sv-goto-overview>Přehled — zobrazit dashboard</button>';
  }

  function renderHero(root) {
    var h1 = root.querySelector('[data-sv-hero-greeting]');
    var sumEl = root.querySelector('[data-sv-hero-summary]');
    var dash = root.querySelector('[data-sv-dashboard-root]');
    var loading = dash && dash.classList.contains('is-sv-dashboard-loading');
    var first = greetingFirstName(state.currentMe);
    if (h1) h1.textContent = 'Dobrý den, ' + first + ' 👋';
    if (sumEl) {
      if (loading) {
        sumEl.textContent = 'Načítám vaše vozidla…';
      } else {
        var list = getVehicleList();
        var sum = getOverviewSummary(list);
        sumEl.innerHTML = renderHeroSummaryHtml(sum);
      }
    }
  }

  function updateProfileUi(root) {
    var nameEl = root.querySelector('.sv-prototype-profile-name');
    var av = root.querySelector('.sv-prototype-avatar');
    if (nameEl) nameEl.textContent = profileDisplayName(state.currentMe);
    if (av) av.textContent = profileInitials(state.currentMe);
  }

  function setDashboardLoading(root, on) {
    var el = root.querySelector('[data-sv-dashboard-root]');
    if (!el) return;
    el.classList.toggle('is-sv-dashboard-loading', !!on);
  }

  function setDataSourceBadge(root, opts) {
    opts = opts || {};
    var banner = root.querySelector('[data-sv-data-banner]');
    var textEl = root.querySelector('[data-sv-data-banner-text]');
    var loginL = root.querySelector('[data-sv-login-link]');
    if (!banner || !textEl) return;
    var source = opts.source || state.dataSource;
    var reason = opts.reason;
    var msg;
    var kindClass = 'sv-prototype-data-banner--demo';
    var showLogin = false;
    var realEmpty = !!opts.realEmpty;
    if (source === 'real') {
      if (realEmpty) {
        msg = 'Reálná data — zatím žádné vozidlo';
        kindClass = 'sv-prototype-data-banner--real';
      } else {
        msg = 'Reálná data';
        kindClass = 'sv-prototype-data-banner--real';
      }
    } else if (reason === 'unauthenticated' && getQueryFlag('real')) {
      msg = 'Zobrazujete ukázková data. Pro reálná data se přihlaste.';
      kindClass = 'sv-prototype-data-banner--login';
      showLogin = true;
    } else if (source === 'fallback') {
      msg = 'Reálná data se nepodařilo načíst. Zobrazuji ukázku.';
      kindClass = 'sv-prototype-data-banner--warn';
    } else {
      msg = 'Ukázková data';
      kindClass = 'sv-prototype-data-banner--demo';
    }
    banner.hidden = false;
    banner.className = 'sv-prototype-data-banner ' + kindClass;
    textEl.textContent = msg;
    if (loginL) {
      loginL.hidden = !showLogin;
      if (state.loginHref) loginL.setAttribute('href', state.loginHref);
      loginL.setAttribute('rel', 'nofollow');
    }
  }

  function applyEmptyStateVisibility(root) {
    var empty = root.querySelector('[data-sv-empty-vehicles]');
    var grid = root.querySelector('[data-sv-vehicle-grid]');
    var ogrid = root.querySelector('[data-sv-overview-vehicle-grid]');
    if (!empty) return;
    var isEmptyReal =
      state.dataSource === 'real' &&
      Array.isArray(state.runtimeVehicles) &&
      state.runtimeVehicles.length === 0;
    empty.hidden = !isEmptyReal;
    if (grid) grid.hidden = isEmptyReal && state.view === 'vehicles';
    if (ogrid) ogrid.hidden = isEmptyReal && state.view === 'overview';
  }

  function applyDashboardData(root, opts) {
    opts = opts || {};
    setDashboardLoading(root, false);
    state.dataSource = opts.source || 'demo';
    state.runtimeVehicles = opts.vehicles != null ? opts.vehicles : null;
    if (opts.me !== undefined) state.currentMe = opts.me;
    state.detailTimelineIsSample = true;
    updateProfileUi(root);
    updateMainChrome(root);
    refreshDashboardBody(root);
    setDataSourceBadge(root, opts);
    renderProtoDebug(root);
    applyEmptyStateVisibility(root);
  }

  function refreshDashboardBody(root) {
    renderHero(root);
    renderOverallStatus(root);
    renderQuickCards(root);
    renderOverviewAside(root);
    renderFilterPills(root);
    renderCatalogToolbar(root);
    renderVehicleCards(root);
    renderCatalogSummary(root);
  }

  function logProtoRealDebug() {
    if (!getQueryFlag('real')) return;
    console.info('[SV PROTOTYPE] real mode', {
      realMode: true,
      meStatus: state.protoDiag.meStatus,
      authenticated: !!state.protoDiag.authenticated,
      vehiclesStatus: state.protoDiag.vehiclesStatus,
      vehiclesCount: state.protoDiag.vehiclesCount,
      source: state.dataSource,
    });
  }

  function renderProtoDebug(root) {
    var wrap = root.querySelector('[data-sv-proto-debug]');
    if (!wrap) return;
    if (!getQueryFlag('debug') || !getQueryFlag('real')) {
      wrap.hidden = true;
      return;
    }
    wrap.hidden = false;
    wrap.textContent =
      'realMode: true\n' +
      'debug: true\n' +
      'meStatus: ' +
      (state.protoDiag.meStatus != null ? String(state.protoDiag.meStatus) : '—') +
      '\n' +
      'authenticated: ' +
      !!state.protoDiag.authenticated +
      '\n' +
      'vehiclesStatus: ' +
      (state.protoDiag.vehiclesStatus != null ? String(state.protoDiag.vehiclesStatus) : '—') +
      '\n' +
      'vehiclesCount: ' +
      (state.protoDiag.vehiclesCount != null ? String(state.protoDiag.vehiclesCount) : '—') +
      '\n' +
      'source: ' +
      String(state.dataSource || '—');
  }

  function bootstrapDashboard(root) {
    if (!getQueryFlag('real')) {
      state.currentMe = null;
      applyDashboardData(root, { source: 'demo', vehicles: null, me: null, reason: null });
      return;
    }
    setDashboardLoading(root, true);
    refreshDashboardBody(root);
    var banner = root.querySelector('[data-sv-data-banner]');
    if (banner) {
      banner.hidden = false;
      banner.className = 'sv-prototype-data-banner sv-prototype-data-banner--loading';
      var te = root.querySelector('[data-sv-data-banner-text]');
      if (te) te.textContent = 'Načítám vaše vozidla…';
      var ll = root.querySelector('[data-sv-login-link]');
      if (ll) ll.hidden = true;
    }
    loadSession()
      .then(function (session) {
        state.protoDiag.meStatus = session.status;
        state.protoDiag.authenticated = !!session.ok;
        if (!session.ok) {
          state.currentMe = session.me || null;
          state.protoDiag.vehiclesStatus = null;
          state.protoDiag.vehiclesCount = null;
          applyDashboardData(root, {
            source: 'demo',
            vehicles: null,
            me: null,
            reason: 'unauthenticated',
            realEmpty: false,
          });
          logProtoRealDebug();
          return Promise.reject(new Error('sv-skip-chain'));
        }
        state.currentMe = session.me;
        return loadVehicles();
      })
      .then(function (vr) {
        if (vr === undefined) return;
        state.protoDiag.vehiclesStatus = vr.status;
        var arr = extractVehicles(vr.data);
        if (arr === null) {
          throw new Error('sv-invalid-vehicles');
        }
        state.protoDiag.vehiclesCount = arr.length;
        var mapped = arr.map(mapVehicleFromApi);
        applyDashboardData(root, {
          source: 'real',
          vehicles: mapped,
          me: state.currentMe,
          reason: null,
          realEmpty: mapped.length === 0,
        });
        logProtoRealDebug();
      })
      .catch(function (err) {
        if (err && err.message === 'sv-skip-chain') return;
        state.runtimeVehicles = null;
        state.currentMe = null;
        state.protoDiag.vehiclesStatus =
          err && err.status != null ? err.status : state.protoDiag.vehiclesStatus;
        state.protoDiag.vehiclesCount = null;
        state.protoDiag.authenticated = false;
        applyDashboardData(root, { source: 'fallback', vehicles: null, me: null, reason: 'error', realEmpty: false });
        showToast('Reálná data se nepodařilo načíst. Zobrazuji ukázku.');
        logProtoRealDebug();
      });
  }

  function formatKmDisplay(v) {
    if (v.km == null || v.km === '') return 'Nezadáno';
    return Number(v.km).toLocaleString('cs-CZ') + ' km';
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function showToast(message) {
    var host = document.querySelector('.sv-prototype-toast-host');
    if (!host) return;
    host.textContent = message;
    host.classList.add('is-visible');
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(function () {
      host.classList.remove('is-visible');
    }, 3200);
  }

  function badgeClass(status) {
    if (status === 'ok') return 'sv-prototype-badge sv-prototype-badge--ok';
    if (status === 'attention' || status === 'pending') return 'sv-prototype-badge sv-prototype-badge--warn';
    if (status === 'archived') return 'sv-prototype-badge sv-prototype-badge--archived';
    return 'sv-prototype-badge sv-prototype-badge--danger';
  }

  function accessBadgeClass(kind) {
    if (kind === 'ok') return 'sv-prototype-badge sv-prototype-badge--ok';
    if (kind === 'warn') return 'sv-prototype-badge sv-prototype-badge--warn';
    return 'sv-prototype-badge sv-prototype-badge--danger';
  }

  function vehicleVisualClass(kind) {
    var k = kind === 'van' || kind === 'suv' || kind === 'sedan' ? kind : 'sedan';
    return 'sv-prototype-vehicle-visual sv-vehicle-visual sv-vehicle-' + k;
  }

  function statusValClass(tone) {
    if (tone === 'ok') return 'sv-prototype-val--ok';
    if (tone === 'warn') return 'sv-prototype-val--warn';
    return 'sv-prototype-val--bad';
  }

  function onProtoAction(ev) {
    if (ev) ev.preventDefault();
    showToast('Tato akce je v prototypu pouze vizuální.');
  }

  function getVehicle(id) {
    var list = getVehicleList();
    var sid = String(id == null ? '' : id);
    for (var i = 0; i < list.length; i++) {
      if (String(list[i].id) === sid) return list[i];
    }
    return null;
  }

  function sidebarNavItemActive(key) {
    if (state.view === 'overview') return key === 'overview';
    if (state.view === 'vehicles' || state.view === 'detail') return key === 'vehicles';
    return state.activeNav === key;
  }

  function bottomNavItemActive(key) {
    if (key === 'overview') return state.view === 'overview';
    if (key === 'vehicles') return state.view === 'vehicles' || state.view === 'detail';
    return state.view !== 'detail' && state.activeNav === key;
  }

  function updateMainChrome(root) {
    var overviewPage = root.querySelector('[data-sv-overview-page]');
    var vehiclesPage = root.querySelector('[data-sv-vehicles-page]');
    if (overviewPage) overviewPage.hidden = state.view !== 'overview';
    if (vehiclesPage) vehiclesPage.hidden = state.view !== 'vehicles';

    var dash = root.querySelector('[data-sv-dashboard-root]');
    if (dash) {
      dash.classList.toggle('is-sv-view-vehicles', state.view === 'vehicles');
      dash.classList.toggle('is-sv-view-overview', state.view === 'overview');
    }

    var catSub = root.querySelector('[data-sv-catalog-sub]');
    if (catSub) {
      var n = getVehicleList().length;
      catSub.textContent =
        'Máte ' + n + ' ' + (n === 1 ? 'vozidlo' : n > 1 && n < 5 ? 'vozidla' : 'vozidel');
    }

    var inp = root.querySelector('[data-sv-search-filter]');
    if (inp) {
      inp.placeholder = 'Hledejte podle SPZ, VIN, názvu vozidla…';
    }
  }

  function scrollDashboardTop(root) {
    var sc = root.querySelector('.sv-prototype-scroll');
    if (sc) sc.scrollTop = 0;
  }

  function goToOverview(root) {
    state.view = 'overview';
    state.activeVehicleId = null;
    state.activeNav = 'overview';
    state.activeTabIdx = 0;
    renderNav(root);
    renderBottomNav(root);
    syncViews(root);
    updateMainChrome(root);
    refreshDashboardBody(root);
    applyEmptyStateVisibility(root);
    renderProtoDebug(root);
    scrollDashboardTop(root);
  }

  function goToVehicles(root) {
    state.view = 'vehicles';
    state.activeVehicleId = null;
    state.activeNav = 'vehicles';
    state.activeTabIdx = 0;
    renderNav(root);
    renderBottomNav(root);
    syncViews(root);
    updateMainChrome(root);
    refreshDashboardBody(root);
    applyEmptyStateVisibility(root);
    renderProtoDebug(root);
    scrollDashboardTop(root);
  }

  function openVehicleDetail(root, vid) {
    state.activeVehicleId = vid;
    state.view = 'detail';
    state.activeNav = 'vehicles';
    state.activeTabIdx = 0;
    renderNav(root);
    renderBottomNav(root);
    syncViews(root);
    flashCard(root, vid);
    renderDetail(root);
    scrollDashboardTop(root);
  }

  function renderNav(root) {
    var nav = root.querySelector('[data-sv-nav]');
    if (!nav) return;
    nav.innerHTML = NAV_ITEMS.map(function (item) {
      var active = sidebarNavItemActive(item.key) ? ' is-active' : '';
      var svg = ICO[item.ico] || ICO.home;
      return (
        '<button type="button" class="sv-prototype-nav-item' +
        active +
        '" data-sv-nav-key="' +
        escapeHtml(item.key) +
        '">' +
        '<span class="sv-prototype-nav-ico-wrap" aria-hidden="true">' +
        svg +
        '</span>' +
        '<span class="sv-prototype-nav-label">' +
        escapeHtml(item.label) +
        '</span></button>'
      );
    }).join('');
  }

  function renderBottomNav(root) {
    var bot = root.querySelector('[data-sv-bottom-nav]');
    if (!bot) return;
    var keys = ['overview', 'vehicles', 'reminders', 'documents', 'settings'];
    var mapIco = { overview: 'home', vehicles: 'car', reminders: 'bell', documents: 'doc', settings: 'menu' };
    var labels = ['Přehled', 'Vozidla', 'Připomínky', 'Dokumenty', 'Menu'];
    bot.innerHTML = keys
      .map(function (key, idx) {
        var active = bottomNavItemActive(key) ? ' is-active' : '';
        var svg = ICO[mapIco[key]] || ICO.home;
        return (
          '<button type="button" class="sv-prototype-bottom-item' +
          active +
          '" data-sv-bottom-key="' +
          key +
          '">' +
          '<span class="sv-prototype-bottom-ico-wrap" aria-hidden="true">' +
          svg +
          '</span>' +
          escapeHtml(labels[idx]) +
          '</button>'
        );
      })
      .join('');
  }

  function buildOverviewVehicleCardHtml(v) {
    var st = v.status;
    return (
      '<article class="sv-prototype-vehicle-card sv-prototype-vehicle-card--preview" data-sv-mode="preview" data-sv-open-vehicle="' +
      escapeHtml(v.id) +
      '" tabindex="0" role="button">' +
      '<div class="' +
      vehicleVisualClass(v.kind) +
      '" aria-hidden="true">' +
      '<div class="sv-prototype-vehicle-visual-sky"></div>' +
      '<div class="sv-prototype-vehicle-visual-ground"></div>' +
      '<div class="sv-prototype-vehicle-visual-car">' +
      vehicleSilhouette(v.kind, v.id) +
      '</div></div>' +
      '<div class="sv-prototype-vehicle-body">' +
      '<div class="sv-prototype-vehicle-head">' +
      '<h3 class="sv-prototype-vehicle-title">' +
      escapeHtml(v.name) +
      '</h3>' +
      '<span class="' +
      badgeClass(st) +
      '">' +
      escapeHtml(getVehicleStatusLabel(v)) +
      '</span></div>' +
      '<div class="sv-prototype-vehicle-subrow">' +
      '<span class="sv-prototype-plate-badge">' +
      escapeHtml(v.plate) +
      '</span></div>' +
      '<div class="sv-prototype-vehicle-meta">' +
      '<div class="sv-prototype-meta-row"><span class="sv-prototype-meta-k">VIN</span><span class="sv-prototype-meta-v">' +
      escapeHtml(shortVin(v)) +
      '</span></div>' +
      '<div class="sv-prototype-meta-row"><span class="sv-prototype-meta-k">Nájezd</span><span class="sv-prototype-meta-v"><strong>' +
      escapeHtml(formatKmDisplay(v)) +
      '</strong></span></div></div>' +
      '<div class="sv-prototype-status-lines">' +
      '<div class="sv-prototype-status-line"><span class="sv-prototype-status-label">STK</span><strong class="sv-prototype-status-val ' +
      statusValClass(v.toneStk || 'ok') +
      '">' +
      escapeHtml(v.stk) +
      '</strong></div>' +
      '<div class="sv-prototype-status-line"><span class="sv-prototype-status-label">Pojištění</span><strong class="sv-prototype-status-val ' +
      statusValClass(v.toneIns || 'ok') +
      '">' +
      escapeHtml(v.insurance) +
      '</strong></div>' +
      '<div class="sv-prototype-status-line"><span class="sv-prototype-status-label">Servis</span><strong class="sv-prototype-status-val ' +
      statusValClass(v.toneSvc || 'ok') +
      '">' +
      escapeHtml(v.service) +
      '</strong></div></div>' +
      '<div class="sv-prototype-vehicle-actions">' +
      '<button type="button" class="sv-prototype-veh-ico" title="Detail" data-sv-stop="1" data-sv-open-vehicle="' +
      escapeHtml(v.id) +
      '">' +
      ICO.doc +
      '<span class="sv-prototype-veh-ico-label">Detail</span></button>' +
      '<button type="button" class="sv-prototype-veh-ico" title="Přidat záznam" data-sv-stop="1" data-sv-legacy-nav="service-history">' +
      ICO.quickSvc +
      '<span class="sv-prototype-veh-ico-label">Přidat záznam</span></button>' +
      '<button type="button" class="sv-prototype-veh-ico" title="Dokumenty" data-sv-stop="1" data-sv-legacy-nav="documents">' +
      ICO.doc +
      '<span class="sv-prototype-veh-ico-label">Dokumenty</span></button>' +
      '<button type="button" class="sv-prototype-veh-ico" title="Sdílet" data-sv-stop="1" data-sv-legacy-nav="services">' +
      '<svg class="sv-prototype-svg-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M18 16.08c-.76 0-1.44.3-1.96.77L8.91 12.7c.05-.23.09-.46.09-.7s-.04-.47-.09-.7l7.05-4.11c.54.5 1.25.81 2.04.81 1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3c0 .24.04.47.09.7L8.04 9.81C7.5 9.31 6.79 9 6 9c-1.66 0-3 1.34-3 3s1.34 3 3 3c.79 0 1.5-.31 2.04-.81l7.12 4.16c-.05.21-.08.43-.08.65 0 1.61 1.31 2.92 2.92 2.92s2.92-1.31 2.92-2.92-1.31-2.92-2.92-2.92z"/></svg>' +
      '<span class="sv-prototype-veh-ico-label">Sdílet</span></button>' +
      '</div></div></article>'
    );
  }

  function buildGarageVehicleCardHtml(v) {
    var st = v.status;
    return (
      '<article class="sv-prototype-garage-card" data-sv-open-vehicle="' +
      escapeHtml(v.id) +
      '" tabindex="0" role="button">' +
      '<div class="sv-prototype-garage-photo ' +
      vehicleVisualClass(v.kind) +
      '">' +
      '<div class="sv-prototype-vehicle-visual-sky"></div>' +
      '<div class="sv-prototype-vehicle-visual-ground"></div>' +
      '<div class="sv-prototype-garage-car">' +
      vehicleSilhouette(v.kind, v.id) +
      '</div>' +
      '<span class="sv-prototype-garage-badge ' +
      badgeClass(st) +
      '">' +
      escapeHtml(getVehicleStatusLabel(v)) +
      '</span></div>' +
      '<div class="sv-prototype-garage-body">' +
      '<h3 class="sv-prototype-garage-title">' +
      escapeHtml(v.name) +
      '</h3>' +
      '<div class="sv-prototype-garage-sub">' +
      '<span class="sv-prototype-plate-badge">' +
      escapeHtml(v.plate) +
      '</span>' +
      '<span class="sv-prototype-garage-vin">VIN ' +
      escapeHtml(shortVin(v)) +
      '</span>' +
      '<span class="sv-prototype-garage-km"><strong>' +
      escapeHtml(formatKmDisplay(v)) +
      '</strong></span></div>' +
      '<div class="sv-prototype-garage-lines">' +
      '<div class="sv-prototype-status-line"><span class="sv-prototype-status-ico" aria-hidden="true">' +
      ICO.quickStk +
      '</span><span class="sv-prototype-status-label">STK</span><strong class="sv-prototype-status-val ' +
      statusValClass(v.toneStk || 'ok') +
      '">' +
      escapeHtml(v.stk) +
      '</strong></div>' +
      '<div class="sv-prototype-status-line"><span class="sv-prototype-status-ico" aria-hidden="true">' +
      ICO.quickShield +
      '</span><span class="sv-prototype-status-label">Pojištění</span><strong class="sv-prototype-status-val ' +
      statusValClass(v.toneIns || 'ok') +
      '">' +
      escapeHtml(v.insurance) +
      '</strong></div>' +
      '<div class="sv-prototype-status-line"><span class="sv-prototype-status-ico" aria-hidden="true">' +
      ICO.quickSvc +
      '</span><span class="sv-prototype-status-label">Poslední servis</span><strong class="sv-prototype-status-val ' +
      statusValClass(v.toneSvc || 'ok') +
      '">' +
      escapeHtml(v.lastService || v.service || '—') +
      '</strong></div></div>' +
      '<div class="sv-prototype-garage-actions">' +
      '<button type="button" class="sv-prototype-garage-btn" data-sv-stop="1" data-sv-open-vehicle="' +
      escapeHtml(v.id) +
      '">Detail</button>' +
      '<button type="button" class="sv-prototype-garage-btn" data-sv-stop="1" data-sv-legacy-nav="service-history">Přidat záznam</button>' +
      '<button type="button" class="sv-prototype-garage-btn" data-sv-stop="1" data-sv-legacy-nav="documents">Dokumenty</button>' +
      '<button type="button" class="sv-prototype-garage-btn" data-sv-stop="1" data-sv-legacy-nav="services">Sdílet servisem</button>' +
      '</div></div></article>'
    );
  }

  function buildAddVehicleCardHtml() {
    return (
      '<article class="sv-prototype-garage-card sv-prototype-garage-card--add">' +
      '<div class="sv-prototype-garage-add-inner">' +
      '<div class="sv-prototype-garage-add-ico" aria-hidden="true">' +
      ICO.car +
      '</div>' +
      '<h3 class="sv-prototype-garage-add-title">Přidat nové vozidlo</h3>' +
      '<p class="sv-prototype-garage-add-text">Přidejte vozidlo podle SPZ nebo VIN a mějte vše pohromadě.</p>' +
      '<button type="button" class="sv-prototype-btn-primary sv-prototype-garage-add-btn" data-sv-legacy-nav="add-vehicle">+ Přidat vozidlo</button>' +
      '</div></article>'
    );
  }

  function renderVehicleCards(root) {
    var ogrid = root.querySelector('[data-sv-overview-vehicle-grid]');
    var grid = root.querySelector('[data-sv-vehicle-grid]');
    var dash = root.querySelector('[data-sv-dashboard-root]');
    var loading = dash && dash.classList.contains('is-sv-dashboard-loading');
    if (loading) {
      var sk =
        '<div class="sv-prototype-skeleton-grid" aria-hidden="true">' +
        '<div class="sv-prototype-skeleton-card"></div>' +
        '<div class="sv-prototype-skeleton-card"></div>' +
        '<div class="sv-prototype-skeleton-card"></div>' +
        '</div>';
      if (ogrid) ogrid.innerHTML = sk;
      if (grid) grid.innerHTML = sk;
      return;
    }
    var fullList = getVehicleList();
    var q = state.searchQuery || '';
    if (ogrid) {
      var prevList = getOverviewTopVehicles(fullList, q);
      ogrid.innerHTML = prevList.map(buildOverviewVehicleCardHtml).join('');
    }
    if (grid) {
      var filtered = filterVehicles(fullList, state.vehicleFilter, q);
      filtered = sortVehiclesCatalog(filtered);
      if (!filtered.length) {
        grid.innerHTML =
          '<div class="sv-prototype-catalog-empty"><p>Žádné vozidlo neodpovídá filtru nebo vyhledávání.</p></div>';
      } else {
        grid.innerHTML = filtered.map(buildGarageVehicleCardHtml).join('') + buildAddVehicleCardHtml();
      }
    }
  }

  function renderDetail(root) {
    var v = getVehicle(state.activeVehicleId);
    if (!v) return;
    var imgEl = root.querySelector('[data-sv-detail-photo]');
    var titleEl = root.querySelector('[data-sv-detail-title]');
    var metaEl = root.querySelector('[data-sv-detail-meta]');
    var badgeEl = root.querySelector('[data-sv-detail-badge]');
    if (imgEl) {
      imgEl.className = 'sv-prototype-detail-photo ' + vehicleVisualClass(v.kind);
      imgEl.innerHTML =
        '<div class="sv-prototype-vehicle-visual-sky"></div>' +
        '<div class="sv-prototype-vehicle-visual-ground"></div>' +
        '<div class="sv-prototype-detail-car-wrap">' +
        detailVehicleSvg(v.kind, v.id) +
        '</div>';
    }
    if (titleEl) titleEl.textContent = v.name;
    if (metaEl) {
      metaEl.innerHTML =
        '<span class="sv-prototype-detail-plate">' +
        escapeHtml(v.plate) +
        '</span>' +
        '<span class="sv-prototype-detail-vin">VIN ' +
        escapeHtml(v.vin) +
        '</span>' +
        '<span class="sv-prototype-detail-km"><strong>' +
        escapeHtml(formatKmDisplay(v)) +
        '</strong></span>';
    }
    if (badgeEl) {
      badgeEl.className = badgeClass(v.status);
      badgeEl.textContent = v.statusLabel;
    }

    var tabs = root.querySelector('[data-sv-detail-tabs]');
    if (tabs) {
      tabs.innerHTML = TAB_LABELS.map(function (label, idx) {
        var ac = idx === state.activeTabIdx ? ' is-active' : '';
        return (
          '<button type="button" class="sv-prototype-tab' +
          ac +
          '" data-sv-tab="' +
          idx +
          '">' +
          escapeHtml(label) +
          '</button>'
        );
      }).join('');
    }

    var overview = root.querySelector('[data-sv-detail-overview]');
    if (overview) {
      overview.innerHTML =
        '<div class="sv-prototype-panel sv-prototype-panel--elevated sv-prototype-panel--timeline">' +
        '<h3>Časová osa vozidla' +
        (state.detailTimelineIsSample
          ? ' <span class="sv-prototype-sample-hint" title="Ukázková časová osa">(ukázka)</span>'
          : '') +
        '</h3>' +
        '<div class="sv-prototype-timeline">' +
        DEMO_TIMELINE.map(function (t) {
          var dot =
            t.kind === 'done'
              ? ' sv-prototype-timeline-dot--done'
              : t.kind === 'upcoming'
                ? ' sv-prototype-timeline-dot--soon'
                : ' sv-prototype-timeline-dot--planned';
          return (
            '<div class="sv-prototype-timeline-item">' +
            '<span class="sv-prototype-timeline-dot' +
            dot +
            '" aria-hidden="true"></span>' +
            '<div class="sv-prototype-timeline-body">' +
            '<strong>' +
            escapeHtml(t.title) +
            '</strong>' +
            '<span>' +
            escapeHtml(t.when) +
            '</span></div></div>'
          );
        }).join('') +
        '</div></div>';
    }

    var col2 = root.querySelector('[data-sv-detail-col2]');
    if (col2) {
      col2.innerHTML =
        '<div class="sv-prototype-panel sv-prototype-panel--elevated">' +
        '<h3>Poslední servisní úkon</h3>' +
        '<div class="sv-prototype-last-svc">' +
        '<div class="sv-prototype-last-svc-thumb" aria-hidden="true">' +
        '<svg class="sv-prototype-thumb-ico" viewBox="0 0 24 24"><path fill="currentColor" d="M22.7 19l-9.1-9.1c.9-2.3.4-5-1.5-6.9-2-2-5-2.4-7.4-1.3L9 6 6 9 1.6 4.7C.4 7.1.9 10.1 2.9 12.1c1.9 1.9 4.6 2.4 6.9 1.5l9.1 9.1c.4.4 1 .4 1.4 0l2.3-2.3c.5-.4.5-1.1.1-1.4z"/></svg></div>' +
        '<div class="sv-prototype-last-svc-body">' +
        '<p class="sv-prototype-last-svc-text">' +
        escapeHtml(v.lastService) +
        (v.serviceLabel && v.lastService === 'Bez servisního záznamu'
          ? '<br><span class="sv-prototype-last-svc-hint">' + escapeHtml(v.serviceLabel) + '</span>'
          : '') +
        '</p>' +
        '<button type="button" class="sv-prototype-btn-primary sv-prototype-btn-compact" data-sv-mock-action="1">Zobrazit detail</button>' +
        '</div></div></div>' +
        '<div class="sv-prototype-panel sv-prototype-panel--elevated">' +
        '<h3>Blížící se termíny</h3>' +
        '<ul class="sv-prototype-list-compact">' +
        DEMO_UPCOMING.map(function (u) {
          var cls =
            u.tone === 'warn'
              ? ' class="sv-prototype-upcoming-val--warn"'
              : u.tone === 'ok'
                ? ' class="sv-prototype-upcoming-val--ok"'
                : '';
          return (
            '<li><span>' +
            escapeHtml(u.label) +
            '</span><strong' +
            cls +
            '>' +
            escapeHtml(u.value) +
            '</strong></li>'
          );
        }).join('') +
        '</ul></div>' +
        '<div class="sv-prototype-panel sv-prototype-panel--elevated">' +
        '<h3>Stav dokumentů</h3>' +
        DEMO_DOCS.map(function (d) {
          return (
            '<div class="sv-prototype-doc-row">' +
            '<span>' +
            escapeHtml(d.name) +
            '</span>' +
            '<span class="sv-prototype-badge sv-prototype-badge--ok">' +
            escapeHtml(d.state) +
            '</span></div>'
          );
        }).join('') +
        '</div>' +
        '<div class="sv-prototype-panel sv-prototype-panel--elevated">' +
        '<h3>Aktivní servisy s přístupem</h3>' +
        '<ul class="sv-prototype-active-svc-list">' +
        DEMO_ACTIVE_SERVICES.map(function (s) {
          return (
            '<li><strong>' +
            escapeHtml(s.name) +
            '</strong><span>' +
            escapeHtml(s.detail) +
            '</span></li>'
          );
        }).join('') +
        '</ul></div>';
    }

    var col3 = root.querySelector('[data-sv-detail-col3]');
    if (col3) {
      col3.innerHTML =
        '<div class="sv-prototype-access-panel sv-prototype-panel--elevated">' +
        '<h3>Kdo má přístup k tomuto vozidlu' +
        (v._fromApi ? ' <span class="sv-prototype-sample-hint">(ukázka)</span>' : '') +
        '</h3>' +
        DEMO_ACCESS.map(function (a) {
          return (
            '<div class="sv-prototype-access-service">' +
            '<div class="sv-prototype-access-service-top">' +
            '<h4>' +
            escapeHtml(a.name) +
            '</h4>' +
            '<button type="button" class="sv-prototype-access-menu" aria-label="Menu" data-sv-mock-action="1">' +
            '<span></span><span></span><span></span></button></div>' +
            '<div class="sv-prototype-access-icons" aria-hidden="true">' +
            ICO.key +
            ICO.doc +
            ICO.wrench +
            '</div>' +
            '<span class="sv-prototype-access-type">' +
            escapeHtml(a.accessType) +
            '</span>' +
            '<span class="' +
            accessBadgeClass(a.badgeKind) +
            '">' +
            escapeHtml(a.badge) +
            '</span></div>'
          );
        }).join('') +
        '<button type="button" class="sv-prototype-btn-primary sv-prototype-btn-compact sv-prototype-btn-add-svc" data-sv-mock-action="1">+ Přidat servis</button>' +
        '</div>' +
        '<div class="sv-prototype-panel sv-prototype-panel--elevated sv-prototype-detail-privacy-card">' +
        '<div class="sv-prototype-toggle-row">' +
        '<div class="sv-prototype-toggle-copy"><strong>Povolit detailní historii</strong>' +
        '<span class="sv-prototype-toggle-hint">Servisy uvidí plnou historii vč. faktur</span></div>' +
        '<button type="button" class="sv-prototype-switch is-on" aria-pressed="true" data-sv-toggle-demo="1"></button>' +
        '</div></div>';
    }
  }

  function syncViews(root) {
    root.classList.toggle('is-detail', state.view === 'detail');
    var dash = root.querySelector('[data-sv-view-dashboard]');
    var det = root.querySelector('[data-sv-view-detail]');
    if (dash) {
      dash.hidden = state.view === 'detail';
      dash.classList.toggle('sv-prototype-view--entering', state.view !== 'detail');
    }
    if (det) {
      det.hidden = state.view !== 'detail';
      det.classList.toggle('sv-prototype-view--entering', state.view === 'detail');
    }
    window.requestAnimationFrame(function () {
      if (dash) dash.classList.remove('sv-prototype-view--entering');
      if (det) det.classList.remove('sv-prototype-view--entering');
    });
  }

  function flashCard(root, id) {
    var cards = root.querySelectorAll('.sv-prototype-vehicle-card, .sv-prototype-garage-card');
    for (var i = 0; i < cards.length; i++) {
      cards[i].classList.remove('is-focused');
    }
    var el = root.querySelector('[data-sv-open-vehicle="' + id + '"]');
    if (!el) return;
    el.classList.add('is-focused');
    clearTimeout(state.cardFlashTimer);
    state.cardFlashTimer = setTimeout(function () {
      el.classList.remove('is-focused');
    }, 420);
  }

  function bind(root) {
    root.addEventListener('click', function (ev) {
      var t = ev.target;
      if (!t || !t.closest) return;
      var stopBtn = t.closest('[data-sv-stop]');
      var navItem = t.closest('[data-sv-nav-key]');
      var bottom = t.closest('[data-sv-bottom-key]');
      var openV = t.closest('[data-sv-open-vehicle]');
      var back = t.closest('[data-sv-back]');
      var mock = t.closest('[data-sv-mock-action]');
      var tab = t.closest('[data-sv-tab]');
      var toggle = t.closest('[data-sv-toggle-demo]');
      var fab = t.closest('[data-sv-fab]');
      var leg = t.closest('[data-sv-legacy-nav]');
      var quick = t.closest('[data-sv-quick-action]');
      var filt = t.closest('[data-sv-filter-pick]');
      var vmode = t.closest('[data-sv-grid-mode]');
      var goOv = t.closest('[data-sv-goto-overview]');

      if (t.closest('[data-sv-show-all-vehicles]')) {
        ev.preventDefault();
        goToVehicles(root);
        return;
      }

      if (goOv) {
        ev.preventDefault();
        goToOverview(root);
        return;
      }

      if (t.closest('[data-sv-show-archived]')) {
        ev.preventDefault();
        state.vehicleFilter = 'archived';
        renderFilterPills(root);
        renderVehicleCards(root);
        renderCatalogSummary(root);
        showToast('Zobrazujete archivovaná vozidla (filtr).');
        return;
      }

      if (leg) {
        ev.preventDefault();
        navigateToLegacy(leg.getAttribute('data-sv-legacy-nav') || 'service-history');
        return;
      }

      if (quick) {
        ev.preventDefault();
        var qk = quick.getAttribute('data-sv-quick-action') || '';
        if (qk === 'stk') {
          goToVehicles(root);
          showToast('Projděte STK u jednotlivých vozidel ve filtrech.');
          return;
        }
        if (qk === 'ins') {
          navigateToLegacy('documents');
          return;
        }
        if (qk === 'svc') {
          navigateToLegacy('service-history');
          return;
        }
        if (qk === 'docs') {
          navigateToLegacy('documents');
          return;
        }
        return;
      }

      if (filt) {
        ev.preventDefault();
        state.vehicleFilter = filt.getAttribute('data-sv-filter-pick') || 'all';
        renderFilterPills(root);
        renderVehicleCards(root);
        renderCatalogSummary(root);
        return;
      }

      if (vmode) {
        ev.preventDefault();
        var mode = vmode.getAttribute('data-sv-grid-mode') || 'grid';
        if (mode === 'list') {
          showToast('Seznamové zobrazení připravujeme.');
          state.vehicleListMode = 'list';
        } else {
          state.vehicleListMode = 'grid';
        }
        renderCatalogToolbar(root);
        return;
      }

      if (navItem) {
        var nkey = navItem.getAttribute('data-sv-nav-key') || 'overview';
        if (nkey === 'overview') {
          goToOverview(root);
          return;
        }
        if (nkey === 'vehicles') {
          goToVehicles(root);
          return;
        }
        state.activeNav = nkey;
        renderNav(root);
        renderBottomNav(root);
        onProtoAction();
        return;
      }
      if (bottom) {
        var bkey = bottom.getAttribute('data-sv-bottom-key') || 'overview';
        if (bkey === 'overview') {
          goToOverview(root);
          return;
        }
        if (bkey === 'vehicles') {
          goToVehicles(root);
          return;
        }
        state.activeNav = bkey;
        renderNav(root);
        renderBottomNav(root);
        syncViews(root);
        onProtoAction();
        return;
      }
      if (openV) {
        if (stopBtn) ev.stopPropagation();
        var vid = openV.getAttribute('data-sv-open-vehicle');
        openVehicleDetail(root, vid);
        return;
      }
      if (back) {
        goToOverview(root);
        return;
      }
      if (tab) {
        state.activeTabIdx = parseInt(tab.getAttribute('data-sv-tab'), 10) || 0;
        renderDetail(root);
        if (state.activeTabIdx > 0) showToast('Záložka „' + TAB_LABELS[state.activeTabIdx] + '“ — pouze vizuální prototyp.');
        return;
      }
      if (t.closest('[data-sv-quick-mock]')) {
        onProtoAction(ev);
        return;
      }
      if (mock) {
        onProtoAction(ev);
        return;
      }
      if (toggle) {
        toggle.classList.toggle('is-on');
        toggle.setAttribute('aria-pressed', toggle.classList.contains('is-on') ? 'true' : 'false');
        showToast('Přepínač je v prototypu pouze vizuální.');
        return;
      }
      if (fab) {
        ev.preventDefault();
        navigateToLegacy('add-vehicle');
        return;
      }
    });

    root.addEventListener(
      'keydown',
      function (ev) {
        if (ev.key !== 'Enter' && ev.key !== ' ') return;
        var card = ev.target && ev.target.closest ? ev.target.closest('[data-sv-open-vehicle]') : null;
        if (!card || ev.target.closest('.sv-prototype-vehicle-actions')) return;
        if (ev.target.closest('.sv-prototype-garage-actions')) return;
        ev.preventDefault();
        var vid = card.getAttribute('data-sv-open-vehicle');
        openVehicleDetail(root, vid);
      },
      true,
    );

    var searchInp = root.querySelector('[data-sv-search-filter]');
    if (searchInp && !searchInp._svProtoSearchBound) {
      searchInp._svProtoSearchBound = true;
      searchInp.addEventListener('input', function () {
        state.searchQuery = searchInp.value || '';
        renderVehicleCards(root);
      });
    }

    var sortEl = root.querySelector('[data-sv-sort-select]');
    if (sortEl && !sortEl._svProtoSortBound) {
      sortEl._svProtoSortBound = true;
      sortEl.addEventListener('change', function () {
        state.vehicleSort = sortEl.value || 'activity';
        renderVehicleCards(root);
      });
    }
  }

  function mount(container) {
    container.className = 'sv-prototype';
    container.innerHTML =
      '<div class="sv-prototype-inner">' +
      '<div class="sv-prototype-shell">' +
      '<aside class="sv-prototype-sidebar" aria-label="Hlavní navigace">' +
      '<div class="sv-prototype-brand">' +
      '<span class="sv-prototype-brand-mark" aria-hidden="true">' +
      ICO.car +
      '</span>' +
      '<span class="sv-prototype-brand-text"><span class="sv-prototype-brand-line1">Správa</span> <span class="sv-prototype-brand-line2">vozidel</span></span></div>' +
      '<nav class="sv-prototype-nav" data-sv-nav></nav>' +
      '<div class="sv-prototype-sidebar-foot">' +
      '<button type="button" class="sv-prototype-btn-ghost" data-sv-mock-action="1">Sbalit</button>' +
      '</div></aside>' +
      '<div class="sv-prototype-main">' +
      '<div class="sv-prototype-main-frame">' +
      '<header class="sv-prototype-topbar">' +
      '<div class="sv-prototype-search">' +
      '<span class="sv-prototype-search-icon" aria-hidden="true">' +
      ICO.search +
      '</span>' +
      '<label class="sr-only" for="sv-proto-search">Hledat vozidlo</label>' +
      '<input id="sv-proto-search" type="search" autocomplete="off" placeholder="Hledejte podle SPZ, VIN, názvu vozidla…" data-sv-search-filter="1" />' +
      '</div>' +
      '<button type="button" class="sv-prototype-btn-primary sv-prototype-btn-add-vehicle" data-sv-legacy-nav="add-vehicle">' +
      '<span class="sv-prototype-btn-label-full">+ Přidat vozidlo</span>' +
      '<span class="sv-prototype-btn-label-short">+ Přidat</span></button>' +
      '<div class="sv-prototype-top-actions">' +
      '<button type="button" class="sv-prototype-icon-btn" aria-label="Oznámení" data-sv-mock-action="1">' +
      ICO.bellRing +
      '<span class="sv-prototype-badge-count">3</span></button>' +
      '<button type="button" class="sv-prototype-profile" data-sv-mock-action="1">' +
      '<span class="sv-prototype-avatar">TN</span>' +
      '<span class="sv-prototype-profile-name">' +
      escapeHtml(DEMO_USER.firstName + ' ' + DEMO_USER.lastName) +
      '</span><span class="sv-prototype-profile-caret" aria-hidden="true">▾</span></button></div></header>' +
      '<div class="sv-prototype-scroll">' +
      '<div class="sv-prototype-data-banner" data-sv-data-banner hidden>' +
      '<span class="sv-prototype-data-banner-inner">' +
      '<span data-sv-data-banner-text></span>' +
      '<a data-sv-login-link hidden class="sv-prototype-data-banner-link" href="/">Přihlásit se</a>' +
      '</span></div>' +
      '<pre class="sv-prototype-debug-panel" data-sv-proto-debug hidden></pre>' +
      '<div class="sv-prototype-view" data-sv-view-dashboard data-sv-dashboard-root>' +
      '<div class="sv-prototype-overview-page" data-sv-overview-page>' +
      '<div class="sv-prototype-overview-shell">' +
      '<div class="sv-prototype-overview-top">' +
      '<div class="sv-prototype-hero">' +
      '<div class="sv-prototype-hero-copy">' +
      '<h1 data-sv-hero-greeting>Dobrý den</h1>' +
      '<p class="sv-prototype-hero-summary" data-sv-hero-summary></p>' +
      '</div>' +
      '<div class="sv-prototype-hero-visual" aria-hidden="true">' +
      '<div class="sv-prototype-hero-landscape"></div>' +
      '<div class="sv-prototype-hero-car-wrap">' +
      heroCarSvg() +
      '</div></div></div>' +
      '<div class="sv-prototype-overall-status-card sv-prototype-overall-status" data-sv-overall-status></div>' +
      '</div>' +
      '<div class="sv-prototype-quick-grid" data-sv-quick-grid></div>' +
      '<div class="sv-prototype-overview-body">' +
      '<div class="sv-prototype-overview-main">' +
      '<div class="sv-prototype-preview-head">' +
      '<div class="sv-prototype-preview-head-text">' +
      '<h2 class="sv-prototype-preview-title">Moje vozidla</h2>' +
      '<p class="sv-prototype-preview-sub">Stručný náhled — klikněte na vozidlo nebo přejděte do garáže.</p></div>' +
      '<button type="button" class="sv-prototype-btn-section" data-sv-show-all-vehicles>Zobrazit všechna vozidla →</button>' +
      '</div>' +
      '<div class="sv-prototype-vehicle-grid sv-prototype-vehicle-grid--preview" data-sv-overview-vehicle-grid></div>' +
      '</div>' +
      '<aside class="sv-prototype-overview-aside" data-sv-overview-aside aria-label="Souhrn a termíny"></aside>' +
      '</div></div></div>' +
      '<div class="sv-prototype-vehicles-page" data-sv-vehicles-page hidden>' +
      '<div class="sv-prototype-catalog-head">' +
      '<div>' +
      '<h2 class="sv-prototype-catalog-title">Moje vozidla</h2>' +
      '<p class="sv-prototype-catalog-sub" data-sv-catalog-sub>Máte 0 vozidel</p>' +
      '<button type="button" class="sv-prototype-link-like" data-sv-show-archived>Zobrazit archivovaná</button></div></div>' +
      '<div class="sv-prototype-filter-pills-wrap">' +
      '<div class="sv-prototype-filter-pills" data-sv-filter-pills></div></div>' +
      '<div class="sv-prototype-catalog-toolbar">' +
      '<label class="sv-prototype-sort-label"><span>Řadit podle:</span> ' +
      '<select class="sv-prototype-sort-select" data-sv-sort-select>' +
      '<option value="activity">Poslední aktivity</option>' +
      '<option value="name">Název A–Z</option></select></label>' +
      '<div class="sv-prototype-view-toggle">' +
      '<button type="button" class="sv-prototype-view-toggle-btn is-active" data-sv-grid-mode="grid" aria-label="Mřížka">' +
      '<span class="sv-prototype-grid-ico" aria-hidden="true">▦</span></button>' +
      '<button type="button" class="sv-prototype-view-toggle-btn" data-sv-grid-mode="list" aria-label="Seznam">' +
      '<span class="sv-prototype-grid-ico" aria-hidden="true">☰</span></button></div></div>' +
      '<div class="sv-prototype-vehicle-grid sv-prototype-vehicle-grid--catalog" data-sv-vehicle-grid></div>' +
      '<div class="sv-prototype-empty-vehicles" data-sv-empty-vehicles hidden>' +
      '<p class="sv-prototype-empty-vehicles-text">Zatím nemáte přidané žádné vozidlo.</p>' +
      '<button type="button" class="sv-prototype-btn-primary" data-sv-legacy-nav="add-vehicle">+ Přidat vozidlo</button>' +
      '</div>' +
      '<div class="sv-prototype-catalog-summary" data-sv-catalog-summary></div></div></div>' +
      '<div class="sv-prototype-view" data-sv-view-detail hidden>' +
      '<button type="button" class="sv-prototype-back" data-sv-back>← Zpět na přehled</button>' +
      '<div class="sv-prototype-detail-header-card">' +
      '<div class="sv-prototype-detail-photo" data-sv-detail-photo></div>' +
      '<div class="sv-prototype-detail-head-main">' +
      '<h2 data-sv-detail-title></h2>' +
      '<div class="sv-prototype-detail-meta" data-sv-detail-meta></div></div>' +
      '<div class="sv-prototype-detail-head-aside">' +
      '<span data-sv-detail-badge class="sv-prototype-badge"></span></div></div>' +
      '<div class="sv-prototype-tabs-shell">' +
      '<div class="sv-prototype-tabs" data-sv-detail-tabs></div></div>' +
      '<div class="sv-prototype-detail-grid">' +
      '<div class="sv-prototype-detail-col sv-prototype-detail-col--timeline" data-sv-detail-overview></div>' +
      '<div class="sv-prototype-detail-col sv-prototype-detail-col--main" data-sv-detail-col2></div>' +
      '<div class="sv-prototype-detail-col sv-prototype-detail-col--aside" data-sv-detail-col3></div></div></div></div></div></div>' +
      '<nav class="sv-prototype-bottom-nav" data-sv-bottom-nav aria-label="Mobilní navigace"></nav>' +
      '<button type="button" class="sv-prototype-fab" data-sv-fab aria-label="Přidat">+</button>' +
      '<div class="sv-prototype-toast-host" role="status" aria-live="polite"></div></div>';

    state.activeNav = 'overview';
    state.view = 'overview';
    renderNav(container);
    renderBottomNav(container);
    syncViews(container);
    updateMainChrome(container);
    bind(container);
    bootstrapDashboard(container);
  }

  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn);
    else fn();
  }

  ready(function () {
    var el = document.getElementById('sv-prototype-root');
    if (el) mount(el);
  });

  /*
   * Servis vs MDČR: interní kontrola mapování (v konzoli, bez spamu v produkci):
   *   normalizeServiceText('Dekódováno z: mdcr … pneumatiky …') === null
   *   normalizeServiceText('Výměna oleje před 3 měsíci') !== null
   */
})();
