(function () {
  'use strict';

  const API_BASE = '/api/v1/user/settings';
  const SUPPORT_EMAIL = 'podpora@toozservis.cz';
  const SUPPORT_PHONE_DISPLAY = '+420 731 552 299';
  const SUPPORT_PHONE_TEL = '+420731552299';
  const SUPPORT_MAILTO = 'mailto:podpora@toozservis.cz?subject=Podpora%20Spr%C3%A1va%20vozidel';
  const PANELS = [
    { id: 'profile', label: 'Profil a účet', icon: 'user' },
    { id: 'security', label: 'Zabezpečení', icon: 'shield' },
    { id: 'license', label: 'Licence a tarif', icon: 'crown' },
    { id: 'notifications', label: 'Oznámení', icon: 'bell' },
    { id: 'garage', label: 'Vozidla a garáž', icon: 'garage' },
    { id: 'documents', label: 'Dokumenty', icon: 'folder' },
    { id: 'billing', label: 'Faktury a platby', icon: 'invoice' },
    { id: 'services-sharing', label: 'Servisy a sdílení', icon: 'building' },
    { id: 'privacy', label: 'Soukromí a data', icon: 'lock' },
    { id: 'support', label: 'Podpora', icon: 'globe' },
  ];

  const FAQ_ITEMS = [
    { label: 'Začínáme se správou vozidel', action: 'faq:getting-started', tutorialId: 'add-vehicle' },
    { label: 'Přidávání vozidel a dokumentů', action: 'faq:vehicles-documents', tutorialId: 'documents' },
    { label: 'Servisy, připomínky a historie', action: 'faq:services-reminders', tutorialId: 'service-partners' },
    { label: 'Fakturace a tarify', action: 'faq:billing', panel: 'license' },
    { label: 'Účet a zabezpečení', action: 'faq:account-security', panel: 'security' },
  ];

  const STATE = {
    panel: 'profile',
    search: '',
    loading: false,
    snapshot: null,
    security: null,
    license: null,
    billing: null,
    services: null,
    documents: null,
    modal: null,
    saveBusy: false,
    formDraft: {},
  };

  function esc(v) {
    if (typeof window.escapeHtml === 'function') return window.escapeHtml(v == null ? '' : String(v));
    return String(v == null ? '' : v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function hasFn(n) { return typeof window[n] === 'function'; }

  function showMsg(msg, type) {
    if (hasFn('showAlert')) window.showAlert(msg, type || 'info');
    else alert(msg);
  }

  async function api(url, method, body) {
    if (!hasFn('apiCall')) throw new Error('API není dostupné');
    return apiCall(url, method || 'GET', body == null ? null : body);
  }

  function fmtDate(iso) {
    if (!iso) return '—';
    try {
      const d = new Date(iso);
      return d.toLocaleDateString('cs-CZ', { day: 'numeric', month: 'numeric', year: 'numeric' });
    } catch (_) { return '—'; }
  }

  function fmtDateTime(iso) {
    if (!iso) return '—';
    try {
      const d = new Date(iso);
      return d.toLocaleString('cs-CZ', { day: 'numeric', month: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch (_) { return '—'; }
  }

  function trialBadge(snapshot) {
    const lic = snapshot && snapshot.license;
    if (!lic) return '';
    if (lic.trial_active && lic.trial_days_remaining != null) {
      return `<span class="uapp-settings-trial-badge">Trial ${esc(String(lic.trial_days_remaining))} dní</span>`;
    }
    return '';
  }

  function progressBar(current, limit) {
    const cur = Number(current) || 0;
    const lim = Number(limit);
    const pct = !lim || lim <= 0 ? Math.min(cur > 0 ? 100 : 8, 100) : Math.min(100, Math.round((cur / lim) * 100));
    return `<div class="uapp-settings-progress"><div class="uapp-settings-progress-bar" style="width:${pct}%"></div></div>`;
  }

  function toggleHtml(checked, disabled, toggleKey) {
    const keyAttr = toggleKey ? ` data-uapp-settings-toggle="${esc(toggleKey)}"` : '';
    return `<button type="button" class="uapp-settings-toggle${checked ? ' is-on' : ''}${disabled ? ' is-disabled' : ''}"${keyAttr} ${disabled ? 'disabled' : ''} role="switch" aria-checked="${checked ? 'true' : 'false'}"><span class="uapp-settings-toggle-knob"></span></button>`;
  }

  function badge(text, tone) {
    return `<span class="uapp-settings-badge is-${tone || 'neutral'}">${esc(text)}</span>`;
  }

  function quickAction(label, action, opts) {
    const o = opts || {};
    return `<button type="button" class="uapp-settings-quick-action${o.danger ? ' is-danger' : ''}" data-uapp-settings-action="${esc(action)}"><span>${esc(label)}</span><span aria-hidden="true">›</span></button>`;
  }

  function supportContactRow(icon, title, subtitle, actionHtml) {
    return `
      <div class="uapp-settings-contact-row">
        <span class="uapp-settings-contact-icon" aria-hidden="true">${icon}</span>
        <div class="uapp-settings-contact-text">
          <strong>${esc(title)}</strong>
          <span>${esc(subtitle)}</span>
        </div>
        <div class="uapp-settings-contact-action">${actionHtml}</div>
      </div>`;
  }

  function filteredCategories() {
    const q = String(STATE.search || '').trim().toLowerCase();
    if (!q) return PANELS;
    return PANELS.filter((p) => p.label.toLowerCase().includes(q));
  }

  function panelMeta(id) {
    return PANELS.find((p) => p.id === id) || PANELS[0];
  }

  async function loadSnapshot(force) {
    if (STATE.snapshot && !force) return STATE.snapshot;
    STATE.loading = true;
    try {
      STATE.snapshot = await api(API_BASE);
      return STATE.snapshot;
    } finally {
      STATE.loading = false;
    }
  }

  async function loadPanelData(panel) {
    if (panel === 'security') {
      STATE.security = await api(`${API_BASE}/security`);
    } else if (panel === 'license') {
      STATE.license = await api(`${API_BASE}/license`);
    } else if (panel === 'billing') {
      STATE.billing = await api(`${API_BASE}/billing`);
    } else if (panel === 'services-sharing') {
      STATE.services = await api(`${API_BASE}/services-sharing`);
    } else if (panel === 'documents') {
      STATE.documents = await api(`${API_BASE}/documents/summary`);
    }
  }

  function renderTopbar(snapshot) {
    const u = snapshot && snapshot.profile;
    const name = (u && u.name) ? u.name.split(' ').map((p) => p[0]).join('').slice(0, 2).toUpperCase() : 'U';
    const count = '3';
    return `
      <header class="uapp-settings-topbar">
        <div class="uapp-settings-topbar-left">
          <span class="uapp-settings-topbar-icon" aria-hidden="true">⚙</span>
          <div>
            <h1 class="uapp-settings-topbar-title">Nastavení</h1>
            <p class="uapp-settings-topbar-sub">Správa účtu, zabezpečení, oznámení a předvoleb aplikace</p>
          </div>
        </div>
        <label class="uapp-settings-search">
          <span aria-hidden="true">🔍</span>
          <input type="search" placeholder="Hledat v nastavení…" value="${esc(STATE.search)}" data-uapp-settings-field="search">
        </label>
        <div class="uapp-settings-topbar-actions">
          <button type="button" class="uapp-settings-notify-btn" data-uapp-action="notifications" aria-label="Oznámení"><span>${count}</span>🔔</button>
          <button type="button" class="uapp-settings-profile-btn" data-uapp-action="profile">
            <span class="uapp-settings-avatar">${esc(name)}</span>
            <span class="uapp-settings-profile-meta">
              <strong>${esc((u && u.name) || 'Uživatel')}</strong>
              ${trialBadge(snapshot)}
            </span>
            <span aria-hidden="true">▾</span>
          </button>
        </div>
      </header>`;
  }

  function renderCategoryNav() {
    const cats = filteredCategories();
    return `
      <nav class="uapp-settings-categories" aria-label="Kategorie nastavení">
        <h2 class="uapp-settings-categories-title">Kategorie nastavení</h2>
        <div class="uapp-settings-categories-list">
          ${cats.map((c) => `
            <button type="button" class="uapp-settings-category${STATE.panel === c.id ? ' is-active' : ''}" data-uapp-settings-action="panel:${c.id}">
              <span class="uapp-settings-category-ico" data-ico="${esc(c.icon)}" aria-hidden="true"></span>
              <span>${esc(c.label)}</span>
            </button>`).join('')}
        </div>
      </nav>`;
  }

  function renderAside(panel, snapshot) {
    const usage = (snapshot && snapshot.usage) || {};
    const lic = (snapshot && snapshot.license) || {};
    if (panel === 'profile') {
      return `
        <aside class="uapp-settings-aside">
          <div class="uapp-settings-aside-card">
            <h3>Stav účtu</h3>
            <div class="uapp-settings-status-ok">Aktivní účet — Vše funguje správně</div>
            <ul class="uapp-settings-aside-list">
              <li><span>Trial verze</span><strong>${lic.trial_active ? esc(String(lic.trial_days_remaining)) + ' dní zbývá' : '—'}</strong></li>
              <li><span>Využití garáže</span><strong>${esc(String(usage.vehicles_count || 0))} / ${lic.is_unlimited ? '∞' : esc(String(lic.vehicles_limit || '—'))}</strong></li>
              <li><span>Dokumenty</span><strong>${esc(String(usage.documents_count || 0))} položek</strong></li>
              <li><span>Připomínky</span><strong>${esc(String(usage.reminders_active || 0))} aktivní</strong></li>
              <li><span>Zabezpečení</span><strong class="is-green">V pořádku</strong></li>
            </ul>
          </div>
          <div class="uapp-settings-aside-card">
            <h3>Rychlé akce</h3>
            ${quickAction('Změnit heslo', 'modal:password')}
            ${quickAction('Nastavit dvoufázové ověření', 'modal:2fa')}
            ${quickAction('Exportovat moje data', 'export-data')}
            ${quickAction('Odhlásit všechna zařízení', 'modal:logout-all')}
            ${quickAction('Smazat účet', 'modal:delete-account', { danger: true })}
          </div>
        </aside>`;
    }
    if (panel === 'security') {
      return `
        <aside class="uapp-settings-aside">
          <div class="uapp-settings-aside-card uapp-settings-aside-card--center">
            <div class="uapp-settings-shield-ok" aria-hidden="true">✓</div>
            <h3>Stav zabezpečení</h3>
            <p>Váš účet je zabezpečený. Doporučené kroky jsou splněny.</p>
            <ul class="uapp-settings-checklist">
              <li>Silné heslo</li>
              <li>Dvoufázové ověření <small>(doporučeno)</small></li>
              <li>Ověřený e-mail</li>
              <li>Aktivní zařízení zkontrolována</li>
              <li>Bezpečnostní e-maily zapnuty</li>
            </ul>
          </div>
          <div class="uapp-settings-aside-card">
            <h3>Rychlé akce</h3>
            ${quickAction('Změnit heslo', 'modal:password')}
            ${quickAction('Nastavit dvoufázové ověření', 'modal:2fa')}
            ${quickAction('Odhlásit všechna zařízení', 'modal:logout-all')}
            ${quickAction('Zobrazit historii přihlášení', 'modal:login-history')}
            ${quickAction('Zrušit účet', 'modal:delete-account', { danger: true })}
          </div>
        </aside>`;
    }
    if (panel === 'license') {
      const days = lic.trial_days_remaining != null ? lic.trial_days_remaining : '—';
      return `
        <aside class="uapp-settings-aside">
          <div class="uapp-settings-aside-card uapp-settings-aside-card--center">
            <div class="uapp-settings-gauge">${esc(String(days))}</div>
            <p>Trial verze ${badge(String(days) + ' dní zbývá', 'warn')}</p>
            <p class="uapp-settings-muted">Po skončení zkušební doby si vyberte tarif a pokračujte bez omezení.</p>
            <button type="button" class="uapp-settings-btn uapp-settings-btn-primary" data-uapp-settings-action="open-license">Vybrat tarif</button>
          </div>
          <div class="uapp-settings-aside-card">
            <h3>Co získáte s placenými tarify</h3>
            <ul class="uapp-settings-checklist">
              <li>Více vozidel v garáži</li><li>Neomezené dokumenty</li><li>Pokročilé připomínky</li>
              <li>Export dat a reporty</li><li>Sdílení se servisy</li><li>Prioritní podpora</li>
            </ul>
          </div>
          <div class="uapp-settings-aside-card">
            <h3>Fakturace a platby</h3>
            <p class="uapp-settings-row"><span>Platební metoda</span><button type="button" class="uapp-settings-link" data-uapp-settings-action="panel:billing">Přidat</button></p>
            <p class="uapp-settings-row"><span>Fakturační údaje</span><button type="button" class="uapp-settings-link" data-uapp-settings-action="panel:billing">Upravit</button></p>
            <p class="uapp-settings-row"><span>Historie plateb</span><button type="button" class="uapp-settings-link" data-uapp-settings-action="panel:billing">Zobrazit</button></p>
          </div>
        </aside>`;
    }
    if (panel === 'notifications') {
      return `
        <aside class="uapp-settings-aside">
          <div class="uapp-settings-aside-card">
            <h3>Souhrn vašeho nastavení</h3>
            <ul class="uapp-settings-aside-list">
              <li><span>E-mail</span><strong class="is-green">Aktivní</strong></li>
              <li><span>SMS</span><strong class="is-orange">Neověřeno</strong></li>
              <li><span>Push oznámení</span><strong class="is-green">Aktivní</strong></li>
            </ul>
            <button type="button" class="uapp-settings-link" data-uapp-settings-action="scroll:channels">Upravit kanály oznámení</button>
          </div>
          <div class="uapp-settings-aside-card">
            <h3>Náhled oznámení</h3>
            <div class="uapp-settings-preview-item"><strong>Připomínka servisu</strong><span>Dnes 9:00</span></div>
            <div class="uapp-settings-preview-item"><strong>Nový dokument</strong><span>Včera</span></div>
            <div class="uapp-settings-preview-item"><strong>Bezpečnost</strong><span>Před 3 dny</span></div>
          </div>
          <div class="uapp-settings-aside-card uapp-settings-tip">
            <strong>💡 Doporučení</strong>
            <p>Doporučujeme mít aktivní e-mail a push oznámení.</p>
          </div>
        </aside>`;
    }
    if (panel === 'garage') {
      const lim = lic.is_unlimited ? null : Number(lic.vehicles_limit || 0);
      const rem = lim != null ? Math.max(0, lim - Number(usage.vehicles_count || 0)) : null;
      return `
        <aside class="uapp-settings-aside">
          <div class="uapp-settings-aside-card uapp-settings-aside-card--center">
            <div class="uapp-settings-gauge">${esc(String(usage.vehicles_count || 0))}/${lim == null ? '∞' : esc(String(lim))}</div>
            <p>${rem != null ? `Máte ještě ${rem} volných míst` : 'Neomezená garáž'}</p>
            <button type="button" class="uapp-settings-link" data-uapp-settings-action="open-license">Zvýšit limit garáže</button>
          </div>
          <div class="uapp-settings-aside-card">
            <h3>Rychlé akce</h3>
            ${quickAction('Přidat vozidlo', 'add-vehicle')}
            ${quickAction('Importovat vozidlo', 'nav:vehicles')}
            ${quickAction('Skrýt vozidlo', 'nav:vehicles')}
            ${quickAction('Změnit pořadí vozidel', 'nav:vehicles')}
            ${quickAction('Smazat vozidlo', 'nav:vehicles', { danger: true })}
          </div>
        </aside>`;
    }
    if (panel === 'documents') {
      return `
        <aside class="uapp-settings-aside">
          <div class="uapp-settings-aside-card uapp-settings-aside-card--center">
            <div class="uapp-settings-gauge">${esc(String(usage.documents_count || 0))}</div>
            <p>dokumentů celkem</p>
          </div>
          <div class="uapp-settings-aside-card">
            <h3>Rychlé akce</h3>
            ${quickAction('Nahrát dokument', 'upload-document')}
            ${quickAction('Vytvořit složku', 'nav:documents')}
            ${quickAction('Spravovat kategorie', 'nav:documents')}
            ${quickAction('Vyčistit nevyužité soubory', 'nav:documents')}
            ${quickAction('Zobrazit koš', 'nav:documents')}
          </div>
        </aside>`;
    }
    if (panel === 'billing') {
      return `
        <aside class="uapp-settings-aside">
          <div class="uapp-settings-aside-card">
            <h3>Přehled fakturace</h3>
            <ul class="uapp-settings-aside-list">
              <li><span>Aktuální tarif</span><strong>${esc(String(lic.plan_public_label || lic.effective_plan || '—'))}</strong></li>
              <li><span>Další platba</span><strong>${fmtDate(lic.trial_ends_at)}</strong></li>
            </ul>
          </div>
          <div class="uapp-settings-aside-card">
            <h3>Rychlé akce</h3>
            ${quickAction('Změnit tarif', 'open-license')}
            ${quickAction('Upravit fakturační údaje', 'edit-billing-profile')}
            ${quickAction('Změnit platební metodu', 'open-license')}
            ${quickAction('Stáhnout poslední fakturu', 'download-invoice')}
            ${quickAction('Zrušit předplatné', 'modal:cancel-subscription', { danger: true })}
          </div>
        </aside>`;
    }
    if (panel === 'services-sharing') {
      const sum = (STATE.services && STATE.services.summary) || {};
      return `
        <aside class="uapp-settings-aside">
          <div class="uapp-settings-aside-card uapp-settings-aside-card--center">
            <div class="uapp-settings-gauge">${esc(String(sum.favorites_count || 0))}</div>
            <p>oblíbené servisy</p>
            <ul class="uapp-settings-aside-list">
              <li><span>Sdílená vozidla</span><strong class="is-green">${esc(String(sum.active_shares || 0))} aktivní</strong></li>
              <li><span>Žádosti o přístup</span><strong class="is-orange">${esc(String(sum.pending_requests || 0))} čeká</strong></li>
            </ul>
          </div>
          <div class="uapp-settings-aside-card">
            <h3>Rychlé akce</h3>
            ${quickAction('Přidat servis', 'nav:servicesDirectory')}
            ${quickAction('Sdílet vozidlo se servisem', 'modal:share-service')}
            ${quickAction('Zobrazit pozvánky', 'nav:servicesDirectory')}
            ${quickAction('Odebrat všechny přístupy', 'modal:revoke-all-services', { danger: true })}
          </div>
          <div class="uapp-settings-aside-card uapp-settings-tip"><p>Sdílení vozidel se servisy umožňuje rychlejší servisní péči.</p></div>
        </aside>`;
    }
    if (panel === 'privacy') {
      return `
        <aside class="uapp-settings-aside">
          <div class="uapp-settings-aside-card uapp-settings-aside-card--center">
            <div class="uapp-settings-shield-ok">✓</div>
            <h3>Vaše data jsou v bezpečí.</h3>
            <ul class="uapp-settings-checklist"><li>Vaše data neprodáváme</li><li>Šifrované přenosy</li><li>Máte kontrolu nad údaji</li></ul>
          </div>
          <div class="uapp-settings-aside-card">
            <h3>Rychlé akce</h3>
            ${quickAction('Stáhnout moje data', 'export-data')}
            ${quickAction('Odstranit účet', 'modal:delete-account', { danger: true })}
          </div>
        </aside>`;
    }
    if (panel === 'support') {
      return `
        <aside class="uapp-settings-aside">
          <div class="uapp-settings-aside-card">
            <h3>Rychlý přehled</h3>
            <p>Jsme tu, abychom vám pomohli.</p>
            <ul class="uapp-settings-aside-list">
              <li><span>Průměrná doba odpovědi</span><strong>do 4 hodin</strong></li>
              <li><span>Dostupnost podpory</span><strong>Po–Pá 8:00–18:00</strong></li>
              <li><span>Jazyk podpory</span><strong>Čeština</strong></li>
            </ul>
          </div>
          <div class="uapp-settings-aside-card">
            <h3>Rychlé akce</h3>
            ${quickAction('Napsat e-mail', 'mailto:support')}
            ${quickAction('Spustit online chat', 'open-support-chat')}
            ${quickAction('Zobrazit nápovědu', 'open-help')}
            ${quickAction('Odeslat zpětnou vazbu', 'modal:feedback')}
          </div>
        </aside>`;
    }
    return '';
  }

  function renderPanelProfile(snapshot) {
    const p = (snapshot && snapshot.profile) || {};
    const prefs = (snapshot && snapshot.preferences) || {};
    return `
      <div class="uapp-settings-panel-head"><span class="uapp-settings-panel-ico">👤</span><div><h2>Profil a účet</h2><p>Spravujte své osobní údaje a nastavení účtu</p></div></div>
      <section class="uapp-settings-card">
        <h3>Osobní údaje</h3>
        <div class="uapp-settings-grid-2">
          <label>Jméno a příjmení<input data-uapp-settings-field="name" value="${esc(p.name || '')}"></label>
          <label>E-mail<input disabled value="${esc(p.email_masked || '')}"><small>E-mail nelze změnit bez ověření</small></label>
          <label>Telefon<input data-uapp-settings-field="phone" value="${esc(STATE.formDraft.phone || '')}" placeholder="+420 …"></label>
          <label>Preferovaný jazyk<select data-uapp-settings-field="preferred_language"><option value="cs"${prefs.preferred_language === 'cs' ? ' selected' : ''}>Čeština</option></select></label>
        </div>
        <label class="uapp-settings-full">Adresa<input data-uapp-settings-field="address_display" disabled value="${esc(p.address || '')}"></label>
        <div class="uapp-settings-card-actions"><button type="button" class="uapp-settings-btn uapp-settings-btn-primary" data-uapp-settings-action="save-profile">Uložit změny</button></div>
      </section>
      <section class="uapp-settings-card">
        <h3>Kontaktní údaje</h3>
        <div class="uapp-settings-row-line"><div><strong>Primární e-mail</strong><span>${esc(p.email_masked || '')}</span></div>${badge('Ověřeno', 'green')}</div>
        <div class="uapp-settings-row-line"><div><strong>Telefonní číslo</strong><span>${esc(p.phone_masked || '')}</span></div><button type="button" class="uapp-settings-link" data-uapp-settings-action="modal:verify-phone">Ověřit</button></div>
        <label>Preferovaný kontakt<select data-uapp-settings-field="preferred_contact"><option value="email">E-mail</option><option value="phone">Telefon</option><option value="sms">SMS</option></select></label>
      </section>
      <section class="uapp-settings-card">
        <h3>Účet</h3>
        <div class="uapp-settings-info-grid">
          <div><span>Typ účtu</span><strong>${esc(p.account_type || 'Osobní účet')}</strong></div>
          <div><span>Role</span><strong>${esc(p.role_label || 'Uživatel')}</strong></div>
          <div><span>Stav účtu</span>${badge('Aktivní', 'green')}</div>
          <div><span>Datum registrace</span><strong>${fmtDate(p.registered_at)}</strong></div>
          <div><span>Poslední přihlášení</span><strong>${fmtDateTime(p.last_login_at)}</strong></div>
        </div>
      </section>`;
  }

  function renderPanelSecurity() {
    const sec = STATE.security || {};
    const devices = sec.devices || [];
    return `
      <div class="uapp-settings-panel-head"><span class="uapp-settings-panel-ico">🛡</span><div><h2>Zabezpečení</h2><p>Spravujte zabezpečení účtu a chraňte svá data</p></div></div>
      <section class="uapp-settings-card"><h3>Heslo</h3><p>Stav hesla: <strong>${esc(sec.password_strength || 'Silné')}</strong></p><button type="button" class="uapp-settings-btn" data-uapp-settings-action="modal:password">Změnit heslo</button></section>
      <section class="uapp-settings-card"><h3>Dvoufázové ověření (2FA)</h3><p>Stav 2FA: <strong>${sec.two_factor_enabled ? 'Zapnuto' : 'Vypnuto'}</strong></p><button type="button" class="uapp-settings-btn" data-uapp-settings-action="modal:2fa">Nastavit 2FA</button></section>
      <section class="uapp-settings-card"><h3>Přihlášená zařízení</h3>
        ${devices.length ? devices.map((d) => `
          <div class="uapp-settings-device">
            <div><strong>${esc(d.os)} • ${esc(d.browser)}</strong><span>${esc(d.location)} • ${fmtDateTime(d.last_active_at)} ${d.is_current ? badge('Aktuální', 'green') : ''}</span></div>
            ${d.is_current ? '' : '<button type="button" class="uapp-settings-btn uapp-settings-btn-ghost" disabled title="Vyžaduje správu relací">Odhlásit</button>'}
          </div>`).join('') : '<p class="uapp-settings-muted">Žádná zařízení k zobrazení.</p>'}
        <button type="button" class="uapp-settings-link" data-uapp-settings-action="modal:login-history">Zobrazit všechna zařízení (${esc(String(sec.devices_total || devices.length))})</button>
      </section>
      <section class="uapp-settings-card"><h3>Bezpečnostní e-maily</h3><p>E-maily o přihlášení: <strong class="is-green">Zapnuto</strong></p><p>E-maily o změnách účtu: <strong class="is-green">Zapnuto</strong></p></section>`;
  }

  function renderPanelLicense() {
    const lic = (STATE.license && STATE.license.license) || (STATE.snapshot && STATE.snapshot.license) || {};
    const usage = (STATE.license && STATE.license.usage) || (STATE.snapshot && STATE.snapshot.usage) || {};
    const cg = (STATE.license && STATE.license.comgate) || {};
    const plans = cg.plans || {};
    const planKey = String(lic.effective_plan || lic.trial_plan || lic.plan || 'free').toLowerCase();
    const gatingPlan = planKey === 'premium_trial' ? 'premium' : planKey;
    return `
      <div class="uapp-settings-panel-head"><span class="uapp-settings-panel-ico">👑</span><div><h2>Licence a tarif</h2><p>Spravujte svou licenci, tarif a využití funkcí aplikace</p></div></div>
      <section class="uapp-settings-card">
        <h3>Váš aktuální tarif</h3>
        <p><strong>${esc(String(lic.plan_public_label || planKey))}</strong> ${lic.trial_active ? badge(String(lic.trial_days_remaining) + ' dní zbývá', 'warn') : ''}</p>
        <p class="uapp-settings-muted">Zkušební / tarifní období dle vašeho účtu.</p>
        <button type="button" class="uapp-settings-btn uapp-settings-btn-primary" data-uapp-settings-action="open-license">${planKey === 'free' || lic.trial_active ? 'Vybrat tarif' : 'Změnit tarif'}</button>
        <div class="uapp-settings-meta-row"><span>Aktivováno: ${fmtDate(lic.trial_started_at || lic.valid_to)}</span><span>Konec trial: ${fmtDate(lic.trial_ends_at)}</span></div>
      </section>
      <section class="uapp-settings-card"><h3>Využití vašeho účtu</h3>
        <p>Vozidla v garáži: ${esc(String(usage.vehicles_count || 0))} / ${lic.is_unlimited ? '∞' : esc(String(lic.vehicles_limit || '—'))}${progressBar(usage.vehicles_count, lic.vehicles_limit)}</p>
        <p>Dokumenty: ${esc(String(usage.documents_count || 0))} položek</p>
        <p>Připomínky: ${esc(String(usage.reminders_active || 0))} aktivních</p>
      </section>
      <section class="uapp-settings-card"><h3>Dostupné tarify</h3>
        <div class="uapp-settings-plans">
          ${['free', 'basic', 'premium'].map((pk) => {
            const price = plans[pk] && plans[pk].monthly ? Math.round(plans[pk].monthly / 100) : (pk === 'free' ? 0 : pk === 'basic' ? 99 : 299);
            const active = gatingPlan === pk || (pk === 'premium' && lic.trial_active);
            return `<div class="uapp-settings-plan${active ? ' is-active' : ''}"><h4>${pk === 'free' ? 'Free' : pk === 'basic' ? 'Basic' : 'Premium'}</h4><p>${price} Kč / měsíc</p><button type="button" class="uapp-settings-btn${active ? ' is-outline-green' : ''}" data-uapp-settings-action="open-license" ${!cg.enabled && pk !== 'free' ? 'disabled title="Platby nejsou aktivní"' : ''}>${active ? 'Aktivní tarif' : 'Zvolit ' + (pk === 'basic' ? 'Basic' : 'Premium')}</button></div>`;
          }).join('')}
        </div>
      </section>`;
  }

  function renderPanelNotifications(snapshot) {
    const prefs = (snapshot && snapshot.preferences && snapshot.preferences.notifications) || {};
    const channels = prefs.channels || {};
    const types = prefs.types || {};
    const quiet = String(prefs.quiet_mode || 'off');
    const typeRows = [
      ['service_reminders', 'Připomínky servisu a údržby'],
      ['documents', 'Dokumenty'],
      ['news', 'Novinky a aktuality'],
      ['security', 'Bezpečnost účtu'],
      ['marketing', 'Marketingové nabídky'],
    ];
    return `
      <div class="uapp-settings-panel-head"><span class="uapp-settings-panel-ico">🔔</span><div><h2>Oznámení</h2><p>Spravujte kanály a typy oznámení</p></div></div>
      <section class="uapp-settings-card"><h3>Obecná nastavení oznámení</h3>
        <div class="uapp-settings-row-line"><span>Hlavní přepínač</span>${toggleHtml(prefs.master !== false, false, 'notify.master')}</div>
        <label>Tichý režim<select data-uapp-settings-field="quiet_mode"><option value="off"${quiet === 'off' ? ' selected' : ''}>Vypnuto</option><option value="1h"${quiet === '1h' ? ' selected' : ''}>1 hodina</option><option value="today"${quiet === 'today' ? ' selected' : ''}>Dnes</option></select></label>
      </section>
      <section class="uapp-settings-card" id="uappSettingsChannels"><h3>Kanály oznámení</h3>
        <div class="uapp-settings-row-line"><div><strong>E-mail</strong><span>${esc((snapshot.profile && snapshot.profile.email_masked) || '')}</span></div>${toggleHtml(channels.email !== false, false, 'notify.email')}</div>
        <div class="uapp-settings-row-line"><div><strong>SMS</strong><span>${esc((snapshot.profile && snapshot.profile.phone_masked) || '')}</span></div>${badge('Neověřeno', 'orange')}</div>
        <div class="uapp-settings-row-line"><div><strong>Push oznámení</strong></div>${toggleHtml(channels.push !== false, false, 'notify.push')}</div>
      </section>
      <section class="uapp-settings-card"><h3>Typy oznámení</h3>
        <table class="uapp-settings-matrix"><thead><tr><th>Typ</th><th>E-mail</th><th>SMS</th><th>Push</th></tr></thead><tbody>
          ${typeRows.map(([key, label]) => {
            const row = types[key] || {};
            return `<tr><td>${esc(label)}</td><td><input type="checkbox" data-notify-type="${key}:email" ${row.email !== false ? 'checked' : ''}></td><td><input type="checkbox" data-notify-type="${key}:sms" ${row.sms ? 'checked' : ''}></td><td><input type="checkbox" data-notify-type="${key}:push" ${row.push !== false ? 'checked' : ''}></td></tr>`;
          }).join('')}
        </tbody></table>
        <button type="button" class="uapp-settings-btn uapp-settings-btn-primary" data-uapp-settings-action="save-notifications">Uložit nastavení</button>
      </section>`;
  }

  function renderPanelGarage(snapshot) {
    const lic = (snapshot && snapshot.license) || {};
    const usage = (snapshot && snapshot.usage) || {};
    const prefs = (snapshot && snapshot.preferences && snapshot.preferences.garage) || {};
    return `
      <div class="uapp-settings-panel-head"><span class="uapp-settings-panel-ico">🚗</span><div><h2>Vozidla a garáž</h2><p>Spravujte garáž, limity a výchozí nastavení</p></div></div>
      <div class="uapp-settings-mini-stats">
        <div><span>Vozidla</span><strong>${esc(String(usage.vehicles_count || 0))} / ${lic.is_unlimited ? '∞' : esc(String(lic.vehicles_limit || '—'))}</strong></div>
        <div><span>Dokumenty</span><strong>${esc(String(usage.documents_count || 0))}</strong></div>
        <div><span>Připomínky</span><strong>${esc(String(usage.reminders_active || 0))}</strong></div>
      </div>
      <section class="uapp-settings-card"><h3>Limity garáže</h3><p>Maximální počet vozidel dle tarifu.</p>${progressBar(usage.vehicles_count, lic.vehicles_limit)}<button type="button" class="uapp-settings-link" data-uapp-settings-action="open-license">Zvýšit limit</button></section>
      <section class="uapp-settings-card"><h3>Výchozí nastavení vozidel</h3>
        <label>Jednotky<select data-uapp-settings-field="default_units"><option value="metric">Metrické (km, °C, l)</option></select></label>
        <label>Měna<select data-uapp-settings-field="default_currency"><option value="CZK">CZK – Kč</option></select></label>
        <div class="uapp-settings-row-line"><span>Automatická aktualizace dat vozidel (MDČR)</span>${toggleHtml(prefs.mdcr_auto_update !== false, false, 'garage.mdcr_auto_update')}</div>
        <button type="button" class="uapp-settings-btn" data-uapp-settings-action="save-garage">Uložit</button>
      </section>
      <section class="uapp-settings-card"><h3>Sdílení vozidel</h3><button type="button" class="uapp-settings-btn" data-uapp-settings-action="panel:services-sharing">Spravovat sdílení</button></section>
      <section class="uapp-settings-card"><h3>Odstranění vozidla</h3><button type="button" class="uapp-settings-btn is-danger-outline" data-uapp-settings-action="nav:vehicles">Spravovat vozidla</button></section>`;
  }

  function renderPanelDocuments() {
    const doc = STATE.documents || {};
    const prefs = doc.preferences || {};
    return `
      <div class="uapp-settings-panel-head"><span class="uapp-settings-panel-ico">📁</span><div><h2>Dokumenty</h2><p>Nastavení úložiště a organizace dokumentů</p></div></div>
      <section class="uapp-settings-card"><h3>Nastavení úložiště</h3><p>Maximální velikost souboru: <strong>25 MB</strong></p><p>Celkem dokumentů: <strong>${esc(String(doc.total || 0))}</strong></p><button type="button" class="uapp-settings-link" data-uapp-settings-action="nav:documents">Spravovat úložiště</button></section>
      <section class="uapp-settings-card"><h3>Organizace dokumentů</h3>
        <div class="uapp-settings-row-line"><span>Automatické řazení</span>${toggleHtml(prefs.auto_sort !== false, false, 'documents.auto_sort')}</div>
        <div class="uapp-settings-row-line"><span>Pojmenování souborů</span>${toggleHtml(prefs.smart_naming !== false, false, 'documents.smart_naming')}</div>
        <button type="button" class="uapp-settings-btn" data-uapp-settings-action="save-documents">Uložit</button>
      </section>
      <section class="uapp-settings-card"><h3>Zálohování a bezpečnost</h3><p>Pravidelné zálohování: <strong class="is-green">Aktivní</strong></p><p>Skenování malware: <strong class="is-green">Aktivní</strong> <small>(status)</small></p></section>`;
  }

  function renderPanelBilling() {
    const bill = STATE.billing || {};
    const lic = bill.license || {};
    const inv = bill.invoices || [];
    const pm = bill.payment_method || {};
    return `
      <div class="uapp-settings-panel-head"><span class="uapp-settings-panel-ico">💳</span><div><h2>Faktury a platby</h2><p>Fakturace licence a platební metody</p></div></div>
      <section class="uapp-settings-card"><h3>Aktuální tarif</h3><p>${esc(String(lic.plan_public_label || lic.effective_plan || 'Trial'))} ${lic.trial_active ? badge(String(lic.trial_days_remaining) + ' dní', 'warn') : ''}</p><button type="button" class="uapp-settings-btn uapp-settings-btn-primary" data-uapp-settings-action="open-license">Změnit tarif</button></section>
      <section class="uapp-settings-card"><h3>Fakturační údaje</h3><p>${esc((bill.billing_profile && bill.billing_profile.name) || '—')}</p><p>${esc((bill.billing_profile && bill.billing_profile.email) || '')}</p><button type="button" class="uapp-settings-link" data-uapp-settings-action="edit-billing-profile">Upravit</button></section>
      <section class="uapp-settings-card"><h3>Historie faktur</h3>
        ${inv.length ? `<table class="uapp-settings-table"><thead><tr><th>Číslo</th><th>Datum</th><th>Částka</th><th>Stav</th></tr></thead><tbody>${inv.slice(0, 5).map((r) => `<tr><td>${esc(r.invoice_number)}</td><td>${fmtDate(r.issued_at)}</td><td>${esc(String(r.amount_czk))} Kč</td><td>${esc(r.status)}</td></tr>`).join('')}</tbody></table>` : '<p class="uapp-settings-muted">Žádné platby zatím nejsou k dispozici.</p>'}
      </section>
      <section class="uapp-settings-card"><h3>Platební metoda</h3><p>${pm.configured ? 'Karta ' + esc(pm.masked || '****') : 'Není nastavena'}</p><button type="button" class="uapp-settings-link" data-uapp-settings-action="open-license">${pm.configured ? 'Upravit' : 'Přidat platební metodu'}</button></section>`;
  }

  function renderPanelServices() {
    const data = STATE.services || {};
    const fav = data.favorites || [];
    const sharing = data.sharing || [];
    return `
      <div class="uapp-settings-panel-head"><span class="uapp-settings-panel-ico">🔧</span><div><h2>Servisy a sdílení</h2><p>Oblíbené servisy a sdílení vozidel</p></div></div>
      <section class="uapp-settings-card"><div class="uapp-settings-card-head-row"><h3>Oblíbené servisy</h3><button type="button" class="uapp-settings-btn" data-uapp-settings-action="nav:servicesDirectory">Přidat servis</button></div>
        ${fav.length ? fav.map((s) => `<div class="uapp-settings-service-row"><div><strong>${esc(s.name)}</strong><span>${esc(s.city || '')}, ${esc(s.country || '')}</span></div><button type="button" class="uapp-settings-link" data-uapp-settings-action="nav:servicesDirectory">Nastavení</button></div>`).join('') : '<p class="uapp-settings-muted">Zatím nemáte oblíbené servisy.</p>'}
      </section>
      <section class="uapp-settings-card"><div class="uapp-settings-card-head-row"><h3>Sdílení vozidel se servisy</h3><button type="button" class="uapp-settings-btn" data-uapp-settings-action="modal:share-service">Sdílet vozidlo</button></div>
        ${sharing.length ? `<table class="uapp-settings-table"><thead><tr><th>Servis</th><th>Vozidlo</th><th>Přístup</th><th>Stav</th></tr></thead><tbody>${sharing.map((r) => `<tr><td>${esc(r.service_name)}</td><td>${esc(r.vehicle_name)}</td><td>${esc(r.access_level)}</td><td>${esc(r.status)}</td></tr>`).join('')}</tbody></table>` : '<p class="uapp-settings-muted">Žádné sdílení.</p>'}
      </section>
      <section class="uapp-settings-card"><h3>Komunikace se servisy</h3>
        <div class="uapp-settings-row-line"><span>Povolit servisům přístup k vozidlům</span>${toggleHtml((data.communication && data.communication.allow_vehicle_access) !== false, false, 'services.allow_vehicle_access')}</div>
        <div class="uapp-settings-row-line"><span>Povolit komunikaci se servisy</span>${toggleHtml((data.communication && data.communication.allow_communication) !== false, false, 'services.allow_communication')}</div>
        <button type="button" class="uapp-settings-btn" data-uapp-settings-action="save-services">Uložit</button>
      </section>`;
  }

  function renderPanelPrivacy(snapshot) {
    const priv = (snapshot && snapshot.preferences && snapshot.preferences.privacy) || {};
    return `
      <div class="uapp-settings-panel-head"><span class="uapp-settings-panel-ico">🔒</span><div><h2>Soukromí a data</h2><p>Spravujte soukromí, data a oprávnění</p></div></div>
      <section class="uapp-settings-card"><h3>Oprávnění aplikace</h3>
        <div class="uapp-settings-row-line"><span>Přístup k poloze</span>${badge('Povoleno', 'green')}</div>
        <div class="uapp-settings-row-line"><span>Přístup k fotoaparátu</span>${badge('Povoleno', 'green')}</div>
        <div class="uapp-settings-row-line"><span>Oznámení</span>${badge('Povoleno', 'green')}</div>
      </section>
      <section class="uapp-settings-card"><h3>Ochrana osobních údajů</h3>
        <div class="uapp-settings-row-line"><span>Sdílení dat s třetími stranami</span>${toggleHtml(!!priv.third_party, false, 'privacy.third_party')}</div>
        <div class="uapp-settings-row-line"><span>Personalizace</span>${toggleHtml(priv.personalization !== false, false, 'privacy.personalization')}</div>
        <div class="uapp-settings-row-line"><span>Marketingová oznámení</span>${toggleHtml(!!priv.marketing, false, 'privacy.marketing')}</div>
        <button type="button" class="uapp-settings-btn" data-uapp-settings-action="save-privacy">Uložit</button>
      </section>
      <section class="uapp-settings-card"><h3>Správa a export dat</h3>
        <button type="button" class="uapp-settings-btn" data-uapp-settings-action="export-data">Exportovat data</button>
        <button type="button" class="uapp-settings-btn is-danger-outline" data-uapp-settings-action="modal:delete-account">Odstranit účet</button>
      </section>`;
  }

  function renderPanelSupport() {
    return `
      <div class="uapp-settings-panel-head"><span class="uapp-settings-panel-ico">🌐</span><div><h2>Podpora</h2><p>Získejte pomoc, nápovědu a kontaktujte tým podpory</p></div></div>
      <section class="uapp-settings-card" id="uappSettingsSupportFaq"><h3>Časté dotazy</h3>
        ${FAQ_ITEMS.map((item) => `<button type="button" class="uapp-settings-faq-row" data-uapp-settings-action="${esc(item.action)}">${esc(item.label)} <span>›</span></button>`).join('')}
      </section>
      <section class="uapp-settings-card"><h3>Kontaktujte podporu</h3>
        ${supportContactRow('✉️', 'Napsat e-mail', 'Odpovíme vám co nejdříve', `<a class="uapp-settings-link" href="${SUPPORT_MAILTO}">${esc(SUPPORT_EMAIL)}</a>`)}
        ${supportContactRow('💬', 'Online chat', 'Jsme online v pracovní době', '<button type="button" class="uapp-settings-btn" data-uapp-settings-action="open-support-chat">Spustit chat</button>')}
        ${supportContactRow('📞', 'Zavolat nám', 'Po–Pá 8:00–18:00', `<a class="uapp-settings-link" href="tel:${SUPPORT_PHONE_TEL}">${esc(SUPPORT_PHONE_DISPLAY)}</a>`)}
      </section>
      <section class="uapp-settings-card"><h3>Nápověda a návody</h3><p>Uživatelská nápověda — průvodce funkcemi aplikace.</p><button type="button" class="uapp-settings-btn" data-uapp-settings-action="open-help">Otevřít nápovědu</button></section>
      <footer class="uapp-settings-footer-meta">
        <span>Novinky v aplikaci</span>
        <button type="button" class="uapp-settings-link" data-uapp-settings-action="open-changelog">Zobrazit historii změn</button>
      </footer>`;
  }

  function renderMainPanel(snapshot) {
    switch (STATE.panel) {
      case 'security': return renderPanelSecurity();
      case 'license': return renderPanelLicense();
      case 'notifications': return renderPanelNotifications(snapshot);
      case 'garage': return renderPanelGarage(snapshot);
      case 'documents': return renderPanelDocuments();
      case 'billing': return renderPanelBilling();
      case 'services-sharing': return renderPanelServices();
      case 'privacy': return renderPanelPrivacy(snapshot);
      case 'support': return renderPanelSupport();
      default: return renderPanelProfile(snapshot);
    }
  }

  function renderModals() {
    const m = STATE.modal;
    if (!m) return '';
    if (m === 'password') {
      return `<div class="uapp-settings-modal-backdrop" data-uapp-settings-action="modal:close"><div class="uapp-settings-modal" role="dialog"><h3>Změna hesla</h3><label>Staré heslo<input type="password" data-uapp-settings-field="old_password"></label><label>Nové heslo<input type="password" data-uapp-settings-field="new_password"></label><label>Potvrzení<input type="password" data-uapp-settings-field="new_password2"></label><div class="uapp-settings-modal-actions"><button type="button" data-uapp-settings-action="modal:close">Zrušit</button><button type="button" class="uapp-settings-btn-primary" data-uapp-settings-action="submit-password">Změnit heslo</button></div></div></div>`;
    }
    if (m === 'logout-all') {
      return `<div class="uapp-settings-modal-backdrop" data-uapp-settings-action="modal:close"><div class="uapp-settings-modal"><h3>Odhlásit všechna zařízení?</h3><p>Ukončí všechny aktivní relace kromě této (může být nutné se znovu přihlásit).</p><div class="uapp-settings-modal-actions"><button type="button" data-uapp-settings-action="modal:close">Zrušit</button><button type="button" class="uapp-settings-btn-primary" data-uapp-settings-action="submit-logout-all">Potvrdit</button></div></div></div>`;
    }
    if (m === 'delete-account') {
      return `<div class="uapp-settings-modal-backdrop"><div class="uapp-settings-modal"><h3>Smazat účet</h3><p>Tato akce je nevratná. Použijte existující bezpečný postup v aplikaci.</p><div class="uapp-settings-modal-actions"><button type="button" data-uapp-settings-action="modal:close">Zrušit</button><button type="button" class="is-danger" data-uapp-settings-action="legacy-delete-account">Pokračovat</button></div></div></div>`;
    }
    if (m === '2fa') {
      return `<div class="uapp-settings-modal-backdrop" data-uapp-settings-action="modal:close"><div class="uapp-settings-modal"><h3>Dvoufázové ověření</h3><p>Nastavení 2FA probíhá v zabezpečeném průvodci aplikace.</p><button type="button" class="uapp-settings-btn-primary" data-uapp-settings-action="legacy-2fa">Spustit nastavení 2FA</button></div></div>`;
    }
    if (m === 'verify-phone') {
      return `<div class="uapp-settings-modal-backdrop" data-uapp-settings-action="modal:close"><div class="uapp-settings-modal"><h3>Ověření telefonu</h3><p>SMS ověření zatím není aktivní na backendu. Uložte telefon v profilu — ověření bude dostupné brzy.</p><button type="button" data-uapp-settings-action="modal:close">Rozumím</button></div></div>`;
    }
    if (m === 'login-history') {
      return `<div class="uapp-settings-modal-backdrop" data-uapp-settings-action="modal:close"><div class="uapp-settings-modal uapp-settings-modal-wide"><h3>Historie přihlášení</h3><div id="uappSettingsLoginHistory">Načítám…</div></div></div>`;
    }
    if (m === 'feedback') {
      return `<div class="uapp-settings-modal-backdrop" data-uapp-settings-action="modal:close"><div class="uapp-settings-modal"><h3>Zpětná vazba</h3><label>Typ<select data-uapp-settings-field="feedback_type"><option value="bug">Chyba</option><option value="idea">Nápad</option><option value="other">Jiné</option></select></label><label>Zpráva<textarea data-uapp-settings-field="feedback_message" rows="4"></textarea></label><button type="button" class="uapp-settings-btn-primary" data-uapp-settings-action="submit-feedback">Odeslat</button></div></div>`;
    }
    if (m === 'cancel-subscription') {
      return `<div class="uapp-settings-modal-backdrop" data-uapp-settings-action="modal:close"><div class="uapp-settings-modal"><h3>Zrušit předplatné?</h3><p>Předplatné bude ukončeno ke konci fakturačního období.</p><div class="uapp-settings-modal-actions"><button type="button" data-uapp-settings-action="modal:close">Zpět</button><button type="button" class="is-danger" data-uapp-settings-action="submit-cancel-subscription">Zrušit předplatné</button></div></div></div>`;
    }
    if (m === 'share-service') {
      return `<div class="uapp-settings-modal-backdrop" data-uapp-settings-action="modal:close"><div class="uapp-settings-modal"><h3>Sdílet vozidlo se servisem</h3><p>Vyberte servis v adresáři a povolte přístup k vybranému vozidlu. Sdílení je dostupné od tarifu Basic.</p><div class="uapp-settings-modal-actions"><button type="button" data-uapp-settings-action="modal:close">Zrušit</button><button type="button" class="uapp-settings-btn-primary" data-uapp-settings-action="nav:servicesDirectory">Otevřít servisy</button></div></div></div>`;
    }
    return '';
  }

  function renderPageHtml(snapshot) {
    return `
      <div class="uapp-settings-page" data-testid="user-app-next-settings">
        ${renderTopbar(snapshot)}
        <div class="uapp-settings-layout">
          ${renderCategoryNav()}
          <div class="uapp-settings-main">
            ${STATE.loading ? '<div class="uapp-settings-loading">Načítám nastavení…</div>' : renderMainPanel(snapshot)}
          </div>
          ${renderAside(STATE.panel, snapshot)}
        </div>
        ${renderModals()}
      </div>`;
  }

  function collectProfileDraft(root) {
    const draft = {};
    root.querySelectorAll('[data-uapp-settings-field]').forEach((el) => {
      const key = el.getAttribute('data-uapp-settings-field');
      if (!key || key === 'search') return;
      draft[key] = el.value;
    });
    return draft;
  }

  async function saveProfile(root) {
    const draft = collectProfileDraft(root);
    await api(`${API_BASE}/profile`, 'PATCH', {
      name: draft.name,
      phone: draft.phone,
      preferred_language: draft.preferred_language,
      preferred_contact: draft.preferred_contact,
    });
    showMsg('Profil byl uložen.', 'success');
    await loadSnapshot(true);
  }

  function collectToggleState(root, key) {
    const el = root && root.querySelector(`[data-uapp-settings-toggle="${key}"]`);
    if (!el) return null;
    return el.classList.contains('is-on');
  }

  function leaveSettingsToTab(tab, options) {
    if (hasFn('switchTab')) window.switchTab(tab, options || {});
  }

  function openFaqItem(item) {
    if (!item) return;
    if (item.panel) {
      navigatePanel(item.panel);
      return;
    }
    if (item.tutorialId && hasFn('openHowToHubModal')) {
      window.openHowToHubModal();
      window.setTimeout(() => {
        const btn = document.querySelector(`[data-tutorial-id="${item.tutorialId}"]`);
        if (btn) btn.click();
      }, 120);
      return;
    }
    if (hasFn('openHowToHubModal')) window.openHowToHubModal();
  }

  async function saveNotifications(root) {
    const types = {};
    root.querySelectorAll('[data-notify-type]').forEach((el) => {
      const spec = el.getAttribute('data-notify-type').split(':');
      if (spec.length !== 2) return;
      types[spec[0]] = types[spec[0]] || {};
      types[spec[0]][spec[1]] = el.checked;
    });
    const quietEl = root.querySelector('[data-uapp-settings-field="quiet_mode"]');
    await api(`${API_BASE}/notifications`, 'PATCH', {
      master: collectToggleState(root, 'notify.master') !== false,
      quiet_mode: quietEl ? quietEl.value : 'off',
      channels: {
        email: collectToggleState(root, 'notify.email') !== false,
        push: collectToggleState(root, 'notify.push') !== false,
        sms: false,
      },
      types,
    });
    showMsg('Nastavení oznámení uloženo.', 'success');
    await loadSnapshot(true);
  }

  async function saveGaragePrefs(root) {
    const draft = collectProfileDraft(root);
    await api(`${API_BASE}/garage`, 'PATCH', {
      default_units: draft.default_units || 'metric',
      default_currency: draft.default_currency || 'CZK',
      mdcr_auto_update: collectToggleState(root, 'garage.mdcr_auto_update') !== false,
    });
    showMsg('Nastavení garáže uloženo.', 'success');
    await loadSnapshot(true);
  }

  async function saveDocumentsPrefs(root) {
    await api(`${API_BASE}/documents`, 'PATCH', {
      auto_sort: collectToggleState(root, 'documents.auto_sort') !== false,
      smart_naming: collectToggleState(root, 'documents.smart_naming') !== false,
    });
    showMsg('Nastavení dokumentů uloženo.', 'success');
    if (STATE.panel === 'documents') await loadPanelData('documents');
  }

  async function saveServicesPrefs(root) {
    await api(`${API_BASE}/services`, 'PATCH', {
      allow_vehicle_access: collectToggleState(root, 'services.allow_vehicle_access') !== false,
      allow_communication: collectToggleState(root, 'services.allow_communication') !== false,
    });
    showMsg('Nastavení komunikace uloženo.', 'success');
    await loadPanelData('services-sharing');
    refresh();
  }

  async function savePrivacyPrefs(root) {
    await api(`${API_BASE}/privacy`, 'PATCH', {
      third_party: collectToggleState(root, 'privacy.third_party') === true,
      personalization: collectToggleState(root, 'privacy.personalization') !== false,
      marketing: collectToggleState(root, 'privacy.marketing') === true,
    });
    showMsg('Nastavení soukromí uloženo.', 'success');
    await loadSnapshot(true);
    refresh();
  }

  async function handleAction(action, event) {
    const root = document.querySelector('.uapp-settings-page');
    if (action === 'modal:close') { STATE.modal = null; return refresh(); }
    if (action.startsWith('panel:')) {
      const panel = action.split(':')[1];
      navigatePanel(panel);
      return;
    }
    if (action === 'save-profile' && root) { try { await saveProfile(root); refresh(); } catch (e) { showMsg(e.message || 'Uložení selhalo', 'error'); } return; }
    if (action === 'save-notifications' && root) { try { await saveNotifications(root); refresh(); } catch (e) { showMsg(e.message || 'Uložení selhalo', 'error'); } return; }
    if (action === 'save-garage' && root) { try { await saveGaragePrefs(root); refresh(); } catch (e) { showMsg(e.message, 'error'); } return; }
    if (action === 'save-privacy' && root) { try { await savePrivacyPrefs(root); } catch (e) { showMsg(e.message, 'error'); } return; }
    if (action === 'save-services' && root) { try { await saveServicesPrefs(root); } catch (e) { showMsg(e.message, 'error'); } return; }
    if (action === 'save-documents' && root) { try { await saveDocumentsPrefs(root); refresh(); } catch (e) { showMsg(e.message, 'error'); } return; }
    if (action.startsWith('faq:')) {
      const item = FAQ_ITEMS.find((f) => f.action === action);
      openFaqItem(item);
      return;
    }
    if (action === 'open-license') { if (hasFn('openLicenseModal')) window.openLicenseModal(); else showMsg('Modul licencí není dostupný.', 'warning'); return; }
    if (action === 'add-vehicle') { if (hasFn('openAddVehicleModal')) window.openAddVehicleModal(); else leaveSettingsToTab('vehicles', { expandVehiclesAdd: true }); return; }
    if (action === 'upload-document') { leaveSettingsToTab('documents'); return; }
    if (action.startsWith('nav:')) { const tab = action.split(':')[1]; leaveSettingsToTab(tab === 'servicesDirectory' ? 'servicesDirectory' : tab); return; }
    if (action === 'export-data') {
      try {
        if (!hasFn('apiCall')) throw new Error('API není dostupné');
        const blobResp = await fetch((typeof getApiBaseUrl === 'function' ? getApiBaseUrl() : '') + API_BASE + '/export-data', {
          method: 'POST',
          headers: {
            Authorization: typeof accessToken !== 'undefined' && accessToken ? `Bearer ${accessToken}` : '',
            Accept: 'application/zip',
          },
        });
        if (!blobResp.ok) throw new Error('Export selhal (' + blobResp.status + ')');
        const blob = await blobResp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'export-dat.zip';
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        showMsg('Export dat byl spuštěn.', 'success');
      } catch (e) { showMsg('Export selhal: ' + e.message, 'error'); }
      return;
    }
    if (action === 'legacy-delete-account') { STATE.modal = null; if (hasFn('handleDeleteAccount')) window.handleDeleteAccount(); else showMsg('Funkce smazání účtu není dostupná.', 'warning'); refresh(); return; }
    if (action === 'legacy-2fa') { STATE.modal = null; if (hasFn('setSettingsPanel')) { /* noop */ } showMsg('Použijte stávající 2FA průvodce v sekci zabezpečení.', 'info'); refresh(); return; }
    if (action === 'submit-password') {
      const oldP = root && root.querySelector('[data-uapp-settings-field="old_password"]');
      const newP = root && root.querySelector('[data-uapp-settings-field="new_password"]');
      const newP2 = root && root.querySelector('[data-uapp-settings-field="new_password2"]');
      if (!newP || newP.value !== newP2.value) { showMsg('Hesla se neshodují.', 'error'); return; }
      try {
        await api(`${API_BASE}/security/change-password`, 'POST', { current_password: oldP.value, new_password: newP.value });
        STATE.modal = null; showMsg('Heslo změněno.', 'success'); refresh();
      } catch (e) { showMsg(e.message || 'Změna hesla selhala', 'error'); }
      return;
    }
    if (action === 'submit-logout-all') {
      try {
        const res = await api(`${API_BASE}/security/logout-all`, 'POST', {});
        STATE.modal = null; showMsg(res.message || 'Odhlášeno.', 'success');
        if (res.requires_relogin && hasFn('logout')) window.logout();
      } catch (e) { showMsg(e.message, 'error'); }
      return;
    }
    if (action === 'submit-cancel-subscription') {
      try {
        await api('/api/v1/license/subscription/cancel', 'POST', {});
        STATE.modal = null; showMsg('Předplatné bude zrušeno ke konci období.', 'success');
      } catch (e) { showMsg(e.message || 'Zrušení selhalo', 'error'); }
      return;
    }
    if (action === 'submit-feedback') {
      const msgEl = root && root.querySelector('[data-uapp-settings-field="feedback_message"]');
      const typeEl = root && root.querySelector('[data-uapp-settings-field="feedback_type"]');
      try {
        await api(`${API_BASE}/support-feedback`, 'POST', { subject: 'Zpětná vazba z nastavení', message: msgEl.value, category: typeEl.value, feedback_type: typeEl.value });
        STATE.modal = null; showMsg('Děkujeme za zpětnou vazbu.', 'success'); refresh();
      } catch (e) { showMsg(e.message, 'error'); }
      return;
    }
    if (action === 'modal:password' || action === 'modal:2fa' || action === 'modal:logout-all' || action === 'modal:delete-account' || action === 'modal:verify-phone' || action === 'modal:login-history' || action === 'modal:feedback' || action === 'modal:cancel-subscription' || action === 'modal:share-service') {
      STATE.modal = action.replace('modal:', '');
      refresh();
      if (STATE.modal === 'login-history') {
        api(`${API_BASE}/security/login-history`).then((res) => {
          const box = document.getElementById('uappSettingsLoginHistory');
          if (!box) return;
          const items = (res.items || []).map((i) => `<div class="uapp-settings-history-row"><strong>${esc(i.event_type)}</strong> ${esc(i.os)} / ${esc(i.browser)} — ${fmtDateTime(i.created_at)}</div>`).join('');
          box.innerHTML = items || '<p>Žádná historie.</p>';
        }).catch(() => {});
      }
      return;
    }
    if (action === 'open-help') {
      if (hasFn('openHowToHubModal')) { window.openHowToHubModal(); return; }
      const faq = document.getElementById('uappSettingsSupportFaq');
      if (faq) faq.scrollIntoView({ behavior: 'smooth', block: 'start' });
      else showMsg('Nápověda — rozbalte sekci Časté dotazy níže.', 'info');
      return;
    }
    if (action === 'open-changelog') { if (hasFn('apiCall')) apiCall('/version', 'GET').then((v) => showMsg((v && v.version) ? 'Verze ' + v.version : 'Historie změn', 'info')).catch(() => showMsg('Historie změn', 'info')); return; }
    if (action === 'open-support-chat') { openSupportChat(); return; }
    if (action === 'mailto:support') { window.location.href = SUPPORT_MAILTO; return; }
    if (action === 'download-invoice') { showMsg('Stažení faktury bude dostupné po první platbě.', 'info'); return; }
    if (action === 'edit-billing-profile') { navigatePanel('profile'); return; }
  }

  function bindEvents(root) {
    if (!root) return;
    root.addEventListener('click', (ev) => {
      const toggle = ev.target.closest('[data-uapp-settings-toggle]');
      if (toggle && !toggle.disabled) {
        ev.preventDefault();
        toggle.classList.toggle('is-on');
        toggle.setAttribute('aria-checked', toggle.classList.contains('is-on') ? 'true' : 'false');
        return;
      }
      const btn = ev.target.closest('[data-uapp-settings-action]');
      if (!btn) return;
      ev.preventDefault();
      void handleAction(btn.getAttribute('data-uapp-settings-action'), ev);
    });
    root.addEventListener('input', (ev) => {
      const field = ev.target.closest('[data-uapp-settings-field="search"]');
      if (!field) return;
      STATE.search = field.value;
      const nav = root.querySelector('.uapp-settings-categories-list');
      if (nav) nav.innerHTML = filteredCategories().map((c) => `
        <button type="button" class="uapp-settings-category${STATE.panel === c.id ? ' is-active' : ''}" data-uapp-settings-action="panel:${c.id}"><span>${esc(c.label)}</span></button>`).join('');
    });
  }

  function getMountRoot() {
    return document.querySelector('#uappNextSettingsMount');
  }

  function getPageRoot() {
    return document.querySelector('.uapp-settings-page');
  }

  function updateCategoryNav(root) {
    const list = root.querySelector('.uapp-settings-categories-list');
    if (!list) return;
    list.innerHTML = filteredCategories().map((c) => `
      <button type="button" class="uapp-settings-category${STATE.panel === c.id ? ' is-active' : ''}" data-uapp-settings-action="panel:${c.id}">
        <span class="uapp-settings-category-ico" data-ico="${esc(c.icon)}" aria-hidden="true"></span>
        <span>${esc(c.label)}</span>
      </button>`).join('');
  }

  function updateMainAndAside(root, snapshot) {
    const main = root.querySelector('.uapp-settings-main');
    if (main) {
      main.innerHTML = STATE.loading
        ? '<div class="uapp-settings-loading">Načítám nastavení…</div>'
        : renderMainPanel(snapshot);
    }
    const layout = root.querySelector('.uapp-settings-layout');
    const oldAside = root.querySelector('.uapp-settings-aside');
    if (oldAside) oldAside.remove();
    const asideHtml = renderAside(STATE.panel, snapshot);
    if (layout && asideHtml) layout.insertAdjacentHTML('beforeend', asideHtml);
  }

  function updateModals(root) {
    root.querySelectorAll('.uapp-settings-modal-backdrop').forEach((el) => el.remove());
    const modalsHtml = renderModals();
    if (modalsHtml) root.insertAdjacentHTML('beforeend', modalsHtml);
  }

  function updateDom(snapshot) {
    const root = getPageRoot();
    if (!root) return false;
    const snap = snapshot || STATE.snapshot;
    if (!snap) return false;
    updateCategoryNav(root);
    updateMainAndAside(root, snap);
    updateModals(root);
    return true;
  }

  function refresh() {
    if (updateDom(STATE.snapshot)) return;
    if (hasFn('UserAppNext') && window.UserAppNext.render) window.UserAppNext.render();
  }

  async function switchPanel(panel) {
    const next = normalizePanel(
      panel || (hasFn('getSettingsPanelFromRoute') ? window.getSettingsPanelFromRoute() : STATE.panel)
    );
    STATE.panel = next;
    const pageRoot = getPageRoot();
    if (!pageRoot) {
      await mount(getMountRoot());
      return;
    }
    STATE.loading = true;
    updateDom(STATE.snapshot);
    try {
      await loadPanelData(next);
      if (!STATE.snapshot) await loadSnapshot();
    } finally {
      STATE.loading = false;
      updateDom(STATE.snapshot);
    }
  }

  async function navigatePanel(panel) {
    const next = normalizePanel(panel);
    if (hasFn('setSettingsPanelRoute')) window.setSettingsPanelRoute(next);
    await switchPanel(next);
  }

  async function onRoutePanel(panel) {
    const next = normalizePanel(
      panel || (hasFn('getSettingsPanelFromRoute') ? window.getSettingsPanelFromRoute() : STATE.panel)
    );
    if (!getPageRoot()) {
      await new Promise((resolve) => {
        let tries = 0;
        const waitForMount = () => {
          if (getPageRoot() || getMountRoot() || tries++ > 150) {
            resolve();
            return;
          }
          window.requestAnimationFrame(waitForMount);
        };
        waitForMount();
      });
    }
    await switchPanel(next);
  }

  function normalizePanel(p) {
    const id = String(p || 'profile').toLowerCase();
    return PANELS.some((x) => x.id === id) ? id : 'profile';
  }

  async function mount(container) {
    if (!container) return;
    STATE.panel = normalizePanel(hasFn('getSettingsPanelFromRoute') ? window.getSettingsPanelFromRoute() : STATE.panel);
    const snapshot = await loadSnapshot(true);
    STATE.formDraft.phone = '';
    await loadPanelData(STATE.panel);
    container.innerHTML = renderPageHtml(snapshot);
    bindEvents(container);
  }

  function renderInto(container) {
    void mount(container);
    return '<div class="uapp-settings-loading-wrap">Načítám nastavení…</div>';
  }

  const supportChatState = {
    open: false,
    ws: null,
    reconnectTimer: null,
    typingTimer: null,
    typingStopTimer: null,
    messages: [],
    adminOnline: false,
    mode: 'waiting',
    statusLabel: '',
    businessHours: true,
    welcome: '',
    adminTyping: false,
    userTyping: false,
    status: 'idle',
    error: '',
    offlineSubmitting: false,
    ownerKey: '',
    ownerCustomerId: null,
    sessionId: null,
    activeSessionId: null,
    viewingSessionId: null,
    viewingReadOnly: false,
    sessions: [],
    previousSessionsCount: 0,
    sessionsPanelOpen: false,
  };

  function getSupportChatOwnerKey() {
    const snap = STATE.snapshot && STATE.snapshot.profile;
    if (snap && snap.email) return String(snap.email).trim().toLowerCase();
    if (hasFn('getCurrentUserEmail')) {
      const email = window.getCurrentUserEmail();
      if (email) return String(email).trim().toLowerCase();
    }
    if (window.currentUser && window.currentUser.email) {
      return String(window.currentUser.email).trim().toLowerCase();
    }
    return '';
  }

  function assertSupportChatOwner(expectedCustomerId, expectedEmail) {
    const ownerKey = getSupportChatOwnerKey();
    if (expectedEmail && ownerKey && String(expectedEmail).trim().toLowerCase() !== ownerKey) {
      return false;
    }
    if (expectedCustomerId != null && supportChatState.ownerCustomerId != null
      && Number(expectedCustomerId) !== Number(supportChatState.ownerCustomerId)) {
      return false;
    }
    return true;
  }

  function bindSupportChatOwner(customerId, customerEmail) {
    const ownerKey = getSupportChatOwnerKey();
    supportChatState.ownerKey = ownerKey || String(customerEmail || '').trim().toLowerCase();
    supportChatState.ownerCustomerId = customerId == null ? null : Number(customerId);
  }

  function clearSupportChatDom() {
    const box = document.getElementById('uappSupportChatMessages');
    if (box) {
      box.innerHTML = '<p class="uapp-support-chat-welcome">Načítám váš chat podpory…</p>';
    }
    const offlineEmail = document.getElementById('uappSupportOfflineEmail');
    const offlineSubject = document.getElementById('uappSupportOfflineSubject');
    const offlineMessage = document.getElementById('uappSupportOfflineMessage');
    const offlinePhone = document.getElementById('uappSupportOfflinePhone');
    const offlineResult = document.getElementById('uappSupportOfflineResult');
    if (offlineEmail) offlineEmail.value = '';
    if (offlineSubject) offlineSubject.value = '';
    if (offlineMessage) offlineMessage.value = '';
    if (offlinePhone) offlinePhone.value = '';
    if (offlineResult) {
      offlineResult.hidden = true;
      offlineResult.textContent = '';
    }
    const input = document.getElementById('uappSupportChatInput');
    if (input) input.value = '';
  }

  function resetSupportChatForUserChange() {
    if (supportChatState.reconnectTimer) {
      clearTimeout(supportChatState.reconnectTimer);
      supportChatState.reconnectTimer = null;
    }
    if (supportChatState.typingStopTimer) {
      clearTimeout(supportChatState.typingStopTimer);
      supportChatState.typingStopTimer = null;
    }
    if (supportChatState.ws) {
      try { supportChatState.ws.close(); } catch (e) { /* ignore */ }
      supportChatState.ws = null;
    }
    supportChatState.open = false;
    supportChatState.messages = [];
    supportChatState.adminOnline = false;
    supportChatState.mode = 'waiting';
    supportChatState.statusLabel = '';
    supportChatState.businessHours = true;
    supportChatState.welcome = '';
    supportChatState.adminTyping = false;
    supportChatState.status = 'idle';
    supportChatState.error = '';
    supportChatState.offlineSubmitting = false;
    supportChatState.ownerKey = '';
    supportChatState.ownerCustomerId = null;
    supportChatState.sessionId = null;
    supportChatState.activeSessionId = null;
    supportChatState.viewingSessionId = null;
    supportChatState.viewingReadOnly = false;
    supportChatState.sessions = [];
    supportChatState.previousSessionsCount = 0;
    supportChatState.sessionsPanelOpen = false;
    clearSupportChatDom();
    updateSupportChatUi();
  }

  function getSupportAuthToken() {
    if (hasFn('getEffectiveAccessToken')) return window.getEffectiveAccessToken();
    return localStorage.getItem('accessToken') || localStorage.getItem('token') || null;
  }

  function getSupportUserEmail() {
    const snap = STATE.snapshot;
    const profile = snap && snap.profile;
    if (profile && profile.email && String(profile.email).includes('@')) return String(profile.email);
    if (profile && profile.email_masked && String(profile.email_masked).includes('@')) return String(profile.email_masked);
    if (hasFn('getCurrentUserEmail')) {
      const e = window.getCurrentUserEmail();
      if (e) return e;
    }
    return '';
  }

  function bindSupportChatDomEvents(root) {
    root.querySelector('#uappSupportChatClose').addEventListener('click', () => closeSupportChat());
    root.querySelector('#uappSupportChatForm').addEventListener('submit', (ev) => {
      ev.preventDefault();
      sendSupportChatMessage();
    });
    const chatInput = root.querySelector('#uappSupportChatInput');
    if (chatInput) {
      chatInput.addEventListener('input', () => notifySupportUserTyping(true));
      chatInput.addEventListener('blur', () => notifySupportUserTyping(false));
    }
    root.querySelector('#uappSupportOfflineSubmit').addEventListener('click', () => { void submitSupportOfflineForm(); });
    const sessionsToggle = root.querySelector('#uappSupportChatSessionsToggle');
    if (sessionsToggle) {
      sessionsToggle.addEventListener('click', () => toggleSupportChatSessionsPanel());
    }
    const newSessionBtn = root.querySelector('#uappSupportChatNewSession');
    if (newSessionBtn) {
      newSessionBtn.addEventListener('click', () => { void startNewSupportChatSession(); });
    }
    const backActiveBtn = root.querySelector('#uappSupportChatBackActive');
    if (backActiveBtn) {
      backActiveBtn.addEventListener('click', () => { void returnToActiveSupportChat(); });
    }
    const sessionsList = root.querySelector('#uappSupportChatSessionsList');
    if (sessionsList) {
      sessionsList.addEventListener('click', (ev) => {
        const btn = ev.target.closest('[data-support-session-id]');
        if (!btn) return;
        const sessionId = Number(btn.getAttribute('data-support-session-id'));
        const isActive = btn.getAttribute('data-support-session-active') === '1';
        void openSupportChatSession(sessionId, isActive);
      });
    }
  }

  function supportChatSessionsBarHtml() {
    return `
      <div id="uappSupportChatSessionsBar" class="uapp-support-chat-sessions-bar">
        <button type="button" id="uappSupportChatSessionsToggle" class="uapp-support-chat-sessions-toggle" aria-expanded="false" aria-controls="uappSupportChatSessionsList">
          <span>Předchozí požadavky</span>
          <span id="uappSupportChatSessionsCount" class="uapp-support-chat-sessions-count">0</span>
          <span class="uapp-support-chat-sessions-chevron" aria-hidden="true">›</span>
        </button>
        <button type="button" id="uappSupportChatNewSession" class="uapp-support-chat-new-session" title="Založit nový požadavek">+ Nový</button>
      </div>
      <div id="uappSupportChatSessionsList" class="uapp-support-chat-sessions-list" hidden></div>
      <div id="uappSupportChatViewBanner" class="uapp-support-chat-view-banner" hidden>
        <span>Prohlížíte uzavřený požadavek (pouze ke čtení)</span>
        <button type="button" id="uappSupportChatBackActive" class="uapp-settings-link">Zpět na aktuální</button>
      </div>`;
  }

  function patchSupportChatDom() {
    const panel = document.getElementById('uappSupportChatPanel');
    if (!panel || document.getElementById('uappSupportChatSessionsBar')) return;
    const messages = document.getElementById('uappSupportChatMessages');
    if (!messages) return;
    const wrap = document.createElement('div');
    wrap.innerHTML = supportChatSessionsBarHtml();
    while (wrap.firstChild) {
      panel.insertBefore(wrap.firstChild, messages);
    }
    const root = document.getElementById('uappSupportChatRoot');
    root.querySelector('#uappSupportChatSessionsToggle')?.addEventListener('click', () => toggleSupportChatSessionsPanel());
    root.querySelector('#uappSupportChatNewSession')?.addEventListener('click', () => { void startNewSupportChatSession(); });
    root.querySelector('#uappSupportChatBackActive')?.addEventListener('click', () => { void returnToActiveSupportChat(); });
    root.querySelector('#uappSupportChatSessionsList')?.addEventListener('click', (ev) => {
      const btn = ev.target.closest('[data-support-session-id]');
      if (!btn) return;
      const sessionId = Number(btn.getAttribute('data-support-session-id'));
      const isActive = btn.getAttribute('data-support-session-active') === '1';
      void openSupportChatSession(sessionId, isActive);
    });
  }

  function fmtSupportSessionDate(iso) {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleString('cs-CZ', {
        day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
      });
    } catch (e) {
      return '—';
    }
  }

  function toggleSupportChatSessionsPanel() {
    supportChatState.sessionsPanelOpen = !supportChatState.sessionsPanelOpen;
    updateSupportChatUi();
  }

  function renderSupportChatSessionsList() {
    const listEl = document.getElementById('uappSupportChatSessionsList');
    const countEl = document.getElementById('uappSupportChatSessionsCount');
    if (!listEl) return;

    const previous = (supportChatState.sessions || []).filter((s) => !s.is_active);
    if (countEl) countEl.textContent = String(previous.length);

    if (!previous.length) {
      listEl.innerHTML = '<p class="uapp-support-chat-sessions-empty">Zatím nemáte žádné starší požadavky.</p>';
      return;
    }

    listEl.innerHTML = previous.map((s) => {
      const active = supportChatState.viewingSessionId === s.session_id;
      return `
        <button type="button" class="uapp-support-chat-session-item${active ? ' is-active' : ''}"
          data-support-session-id="${esc(String(s.session_id))}" data-support-session-active="0">
          <span class="uapp-support-chat-session-item-title">${esc(fmtSupportSessionDate(s.last_message_time || s.updated_at))}</span>
          <span class="uapp-support-chat-session-item-preview">${esc(s.preview || 'Bez zpráv')}</span>
          <span class="uapp-support-chat-session-item-meta">${esc(String(s.message_count || 0))} zpráv · Uzavřeno</span>
        </button>`;
    }).join('');
  }

  async function loadSupportChatSessions() {
    try {
      const data = await api('/api/v1/support/sessions', 'GET');
      if (!assertSupportChatOwner(data.customer_id, data.customer_email)) {
        return;
      }
      supportChatState.sessions = Array.isArray(data.sessions) ? data.sessions : [];
      supportChatState.previousSessionsCount = Number(data.previous_count) || supportChatState.sessions.filter((s) => !s.is_active).length;
      supportChatState.activeSessionId = data.active_session_id || null;
      if (supportChatState.viewingSessionId == null) {
        supportChatState.sessionId = supportChatState.activeSessionId;
      }
      renderSupportChatSessionsList();
      updateSupportChatUi();
    } catch (e) {
      /* sidebar is optional — ignore */
    }
  }

  async function openSupportChatSession(sessionId, isActive) {
    if (!sessionId) return;
    try {
      const data = await api(`/api/v1/support/sessions/${sessionId}/messages`, 'GET');
      if (!assertSupportChatOwner(data.customer_id, data.customer_email)) {
        supportChatState.error = 'Tento požadavek nepatří k vašemu účtu.';
        updateSupportChatUi();
        return;
      }
      supportChatState.viewingSessionId = sessionId;
      supportChatState.viewingReadOnly = !!data.read_only && !isActive;
      supportChatState.sessionId = sessionId;
      supportChatState.messages = Array.isArray(data.messages) ? data.messages.map((m) => ({
        id: m.id,
        sender_type: m.sender_type,
        text: m.text,
        created_at: m.created_at,
      })) : [];
      supportChatState.sessionsPanelOpen = false;
      renderSupportChatMessages();
      updateSupportChatUi();
    } catch (e) {
      supportChatState.error = (e && e.message) ? e.message : 'Požadavek se nepodařilo načíst.';
      updateSupportChatUi();
    }
  }

  async function returnToActiveSupportChat() {
    supportChatState.viewingSessionId = null;
    supportChatState.viewingReadOnly = false;
    supportChatState.sessionId = supportChatState.activeSessionId;
    await loadSupportChatHistory();
    updateSupportChatUi();
  }

  async function startNewSupportChatSession() {
    if (supportChatState.viewingReadOnly) {
      await returnToActiveSupportChat();
    }
    try {
      const data = await api('/api/v1/support/sessions/new', 'POST', {});
      if (!assertSupportChatOwner(data.customer_id, data.customer_email)) return;
      supportChatState.activeSessionId = data.session_id || null;
      supportChatState.sessionId = supportChatState.activeSessionId;
      supportChatState.viewingSessionId = null;
      supportChatState.viewingReadOnly = false;
      supportChatState.messages = [];
      supportChatState.welcome = '';
      clearSupportChatDom();
      await loadSupportChatSessions();
      await loadSupportChatStatus();
      await loadSupportChatHistory();
      if (supportChatState.ws && supportChatState.ws.readyState === WebSocket.OPEN) {
        try { supportChatState.ws.close(); } catch (e) { /* ignore */ }
        supportChatState.ws = null;
      }
      connectSupportChatWs();
      appendSupportSystemMessage('Nový požadavek založen. Napište nám, s čím vám můžeme pomoci.');
      updateSupportChatUi();
    } catch (e) {
      supportChatState.error = (e && e.message) ? e.message : 'Nový požadavek se nepodařilo založit.';
      updateSupportChatUi();
    }
  }

  function ensureSupportChatDom() {
    let root = document.getElementById('uappSupportChatRoot');
    if (root) {
      patchSupportChatDom();
      return root;
    }
    root = document.createElement('div');
    root.id = 'uappSupportChatRoot';
    root.innerHTML = `
      <div id="uappSupportChatPanel" class="uapp-support-chat" hidden>
        <div class="uapp-support-chat-header">
          <div class="uapp-support-chat-header-main">
            <span class="uapp-support-chat-avatar" aria-hidden="true">🤖</span>
            <div>
              <strong>Asistent podpory</strong>
              <span id="uappSupportChatStatus" class="uapp-support-chat-status">Připojuji…</span>
            </div>
          </div>
          <button type="button" class="uapp-support-chat-close" id="uappSupportChatClose" aria-label="Zavřít chat">×</button>
        </div>
        ${supportChatSessionsBarHtml()}
        <div id="uappSupportChatMessages" class="uapp-support-chat-messages">
          <p class="uapp-support-chat-welcome">Načítám asistenta podpory…</p>
        </div>
        <div id="uappSupportChatTyping" class="uapp-support-chat-typing" hidden></div>
        <div id="uappSupportChatError" class="uapp-support-chat-error" hidden></div>
        <form id="uappSupportChatForm" class="uapp-support-chat-form">
          <input type="text" id="uappSupportChatInput" placeholder="Napište zprávu…" maxlength="2000" autocomplete="off">
          <button type="submit" id="uappSupportChatSend" class="uapp-settings-btn uapp-settings-btn-primary">Odeslat</button>
        </form>
        <div id="uappSupportChatOffline" class="uapp-support-chat-offline" hidden>
          <p class="uapp-support-chat-offline-lead">Mimo pracovní dobu (Po–Pá 8:00–18:00). Zanechte nám zprávu — odpovíme e-mailem.</p>
          <label>Kontaktní e-mail<input type="email" id="uappSupportOfflineEmail" autocomplete="email"></label>
          <label>Předmět<input type="text" id="uappSupportOfflineSubject" maxlength="180" placeholder="Krátce popište dotaz"></label>
          <label>Zpráva<textarea id="uappSupportOfflineMessage" rows="4" maxlength="4000" placeholder="Popište prosím váš požadavek…"></textarea></label>
          <label>Telefon (volitelně)<input type="text" id="uappSupportOfflinePhone" placeholder="+420 …"></label>
          <button type="button" id="uappSupportOfflineSubmit" class="uapp-settings-btn uapp-settings-btn-primary">Odeslat požadavek</button>
          <p id="uappSupportOfflineResult" class="uapp-support-chat-offline-result" hidden></p>
        </div>
      </div>`;
    document.body.appendChild(root);
    bindSupportChatDomEvents(root);
    return root;
  }

  function supportChatStatusText() {
    if (supportChatState.adminTyping) return 'Operátor píše…';
    if (supportChatState.status === 'connecting') return 'Připojuji k podpoře…';
    if (supportChatState.status === 'error') return supportChatState.statusLabel || 'Nepřipojeno';
    if (supportChatState.status !== 'connected') return 'Zavřeno';
    if (supportChatState.statusLabel) return supportChatState.statusLabel;
    if (supportChatState.mode === 'live') return 'Operátor je online';
    if (supportChatState.mode === 'waiting') return 'Čeká se na připojení operátora…';
    return 'Mimo pracovní dobu';
  }

  function updateSupportChatUi() {
    const panel = document.getElementById('uappSupportChatPanel');
    const statusEl = document.getElementById('uappSupportChatStatus');
    const errorEl = document.getElementById('uappSupportChatError');
    const sendBtn = document.getElementById('uappSupportChatSend');
    const input = document.getElementById('uappSupportChatInput');
    const form = document.getElementById('uappSupportChatForm');
    const offline = document.getElementById('uappSupportChatOffline');
    const typingEl = document.getElementById('uappSupportChatTyping');
    if (!panel) return;
    panel.hidden = !supportChatState.open;
    panel.classList.toggle('is-offline-mode', supportChatState.mode === 'offline');
    panel.classList.toggle('is-live-mode', supportChatState.mode === 'live');
    panel.classList.toggle('is-waiting-mode', supportChatState.mode === 'waiting');
    if (statusEl) statusEl.textContent = supportChatStatusText();
    if (typingEl) {
      if (supportChatState.adminTyping && !readOnlyView) {
        typingEl.hidden = false;
        typingEl.textContent = 'Operátor píše…';
      } else {
        typingEl.hidden = true;
        typingEl.textContent = '';
      }
    }
    if (errorEl) {
      if (supportChatState.error) {
        errorEl.hidden = false;
        errorEl.textContent = supportChatState.error;
      } else {
        errorEl.hidden = true;
        errorEl.textContent = '';
      }
    }
    const offlineMode = supportChatState.mode === 'offline';
    const readOnlyView = !!supportChatState.viewingReadOnly;
    const sessionsToggle = document.getElementById('uappSupportChatSessionsToggle');
    const sessionsList = document.getElementById('uappSupportChatSessionsList');
    const viewBanner = document.getElementById('uappSupportChatViewBanner');
    if (sessionsToggle) {
      sessionsToggle.setAttribute('aria-expanded', supportChatState.sessionsPanelOpen ? 'true' : 'false');
      sessionsToggle.classList.toggle('is-open', supportChatState.sessionsPanelOpen);
    }
    if (sessionsList) sessionsList.hidden = !supportChatState.sessionsPanelOpen;
    if (viewBanner) viewBanner.hidden = !readOnlyView;
    if (offline) offline.hidden = !offlineMode || readOnlyView;
    if (form) form.hidden = offlineMode || readOnlyView;
    const canSend = !offlineMode && !readOnlyView && supportChatState.status === 'connected' && !supportChatState.error;
    if (sendBtn) sendBtn.disabled = !canSend;
    if (input) input.disabled = !canSend;
    if (offlineMode) {
      const emailEl = document.getElementById('uappSupportOfflineEmail');
      if (emailEl && !emailEl.value) emailEl.value = getSupportUserEmail();
    }
  }

  function appendSupportSystemMessage(text) {
    if (!text) return;
    supportChatState.messages.push({ sender_type: 'system', text: String(text) });
    renderSupportChatMessages();
  }

  function renderSupportChatMessages() {
    const box = document.getElementById('uappSupportChatMessages');
    if (!box) return;
    const items = supportChatState.messages || [];
    if (!items.length) {
      const welcome = supportChatState.welcome || 'Napište zprávu — tým podpory vám odpoví.';
      box.innerHTML = `<p class="uapp-support-chat-welcome">${esc(welcome)}</p>`;
      return;
    }
    box.innerHTML = items.map((m) => {
      if (m.sender_type === 'system') {
        return `<div class="uapp-support-chat-msg is-system">${esc(m.text)}</div>`;
      }
      const mine = m.sender_type === 'user';
      const label = mine ? 'Vy' : 'Podpora';
      return `<div class="uapp-support-chat-msg${mine ? ' is-user' : ' is-admin'}"><span class="uapp-support-chat-msg-label">${label}</span>${esc(m.text)}</div>`;
    }).join('');
    box.scrollTop = box.scrollHeight;
  }

  function appendSupportChatMessage(msg) {
    if (!msg || !msg.text) return;
    if (msg.customer_id != null && supportChatState.ownerCustomerId != null
      && Number(msg.customer_id) !== Number(supportChatState.ownerCustomerId)) {
      return;
    }
    const existing = supportChatState.messages.find((m) => m.id && msg.id && m.id === msg.id);
    if (existing) return;
    if (supportChatState.viewingReadOnly) {
      void loadSupportChatSessions();
      return;
    }
    if (msg.session_id != null && supportChatState.activeSessionId != null
      && Number(msg.session_id) !== Number(supportChatState.activeSessionId)) {
      void loadSupportChatSessions();
      return;
    }
    supportChatState.messages.push(msg);
    if (msg.sender_type === 'admin') supportChatState.adminTyping = false;
    renderSupportChatMessages();
    updateSupportChatUi();
  }

  function applySupportSessionInfo(data) {
    if (!data) return;
    if (data.customer_id != null || data.customer_email) {
      if (!assertSupportChatOwner(data.customer_id, data.customer_email)) {
        resetSupportChatForUserChange();
        supportChatState.error = 'Chat byl resetován kvůli změně účtu. Otevřete podporu znovu.';
        updateSupportChatUi();
        return;
      }
      bindSupportChatOwner(data.customer_id, data.customer_email);
    }
    supportChatState.businessHours = data.business_hours !== false;
    supportChatState.adminOnline = !!data.admin_online;
    supportChatState.mode = data.mode || (data.business_hours === false ? 'offline' : (data.admin_online ? 'live' : 'waiting'));
    supportChatState.statusLabel = data.status_label || '';
    if (data.welcome) {
      supportChatState.welcome = data.welcome;
      if (!supportChatState.messages.length) appendSupportSystemMessage(data.welcome);
    }
    updateSupportChatUi();
  }

  function notifySupportUserTyping(active) {
    const ws = supportChatState.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN || supportChatState.mode === 'offline') return;
    if (supportChatState.typingStopTimer) clearTimeout(supportChatState.typingStopTimer);
    ws.send(JSON.stringify({ type: 'typing', active: !!active }));
    if (active) {
      supportChatState.typingStopTimer = setTimeout(() => {
        notifySupportUserTyping(false);
      }, 2500);
    }
  }

  function scheduleSupportChatReconnect() {
    if (supportChatState.reconnectTimer || !supportChatState.open) return;
    supportChatState.reconnectTimer = window.setTimeout(() => {
      supportChatState.reconnectTimer = null;
      if (supportChatState.open) connectSupportChatWs();
    }, 4000);
  }

  async function loadSupportChatStatus() {
    try {
      const data = await api('/api/v1/support/status', 'GET');
      applySupportSessionInfo(data);
      return data;
    } catch (e) {
      supportChatState.error = (e && e.message) ? e.message : 'Stav podpory se nepodařilo načíst.';
      updateSupportChatUi();
      return null;
    }
  }

  function connectSupportChatWs() {
    const token = getSupportAuthToken();
    if (!token) {
      supportChatState.status = 'error';
      supportChatState.error = 'Pro chat se nejprve přihlaste.';
      updateSupportChatUi();
      return;
    }
    if (supportChatState.mode === 'offline') {
      supportChatState.status = 'connected';
      updateSupportChatUi();
      return;
    }
    if (supportChatState.ws) {
      try { supportChatState.ws.close(); } catch (e) { /* ignore */ }
      supportChatState.ws = null;
    }
    supportChatState.status = 'connecting';
    supportChatState.error = '';
    updateSupportChatUi();
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/v1/support/ws/user?token=${encodeURIComponent(token)}`;
    let ws;
    try {
      ws = new WebSocket(wsUrl);
    } catch (e) {
      supportChatState.status = 'error';
      supportChatState.error = 'Chat se nepodařilo otevřít. Zkuste kontaktní formulář nebo e-mail.';
      updateSupportChatUi();
      return;
    }
    supportChatState.ws = ws;
    ws.onopen = () => {
      supportChatState.status = 'connected';
      supportChatState.error = '';
      updateSupportChatUi();
    };
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'session_owner') {
          if (!assertSupportChatOwner(data.customer_id, data.customer_email)) {
            resetSupportChatForUserChange();
            return;
          }
          bindSupportChatOwner(data.customer_id, data.customer_email);
          supportChatState.activeSessionId = data.session_id || null;
          if (supportChatState.viewingSessionId == null) {
            supportChatState.sessionId = supportChatState.activeSessionId;
          }
          return;
        }
        if (data.type === 'session_info') {
          applySupportSessionInfo(data);
        } else if (data.type === 'admin_status') {
          supportChatState.adminOnline = !!data.online;
          if (data.mode) supportChatState.mode = data.mode;
          if (data.status_label) supportChatState.statusLabel = data.status_label;
          updateSupportChatUi();
        } else if (data.type === 'typing') {
          if (data.sender_type === 'admin') {
            supportChatState.adminTyping = !!data.active;
            updateSupportChatUi();
          }
        } else if (data.type === 'system') {
          appendSupportSystemMessage(data.text);
        } else if (data.type === 'message') {
          if (data.customer_id != null && !assertSupportChatOwner(data.customer_id, data.customer_email)) {
            return;
          }
          appendSupportChatMessage({
            id: data.id,
            session_id: data.session_id,
            sender_type: data.sender_type,
            text: data.text,
            created_at: data.created_at,
          });
        }
      } catch (e) { /* ignore malformed payload */ }
    };
    ws.onerror = () => {
      supportChatState.status = 'error';
      supportChatState.error = 'Spojení s podporou selhalo. Zkuste to znovu nebo použijte formulář níže.';
      updateSupportChatUi();
    };
    ws.onclose = () => {
      if (supportChatState.ws === ws) supportChatState.ws = null;
      if (!supportChatState.open) {
        supportChatState.status = 'idle';
        updateSupportChatUi();
        return;
      }
      if (supportChatState.mode === 'offline') return;
      supportChatState.status = 'error';
      supportChatState.error = 'Chat byl odpojen. Obnovujeme spojení…';
      updateSupportChatUi();
      scheduleSupportChatReconnect();
    };
  }

  async function loadSupportChatHistory() {
    try {
      const data = await api('/api/v1/support/history', 'GET');
      const payload = Array.isArray(data)
        ? { messages: data, customer_id: null, customer_email: getSupportChatOwnerKey() }
        : (data || {});
      if (!assertSupportChatOwner(payload.customer_id, payload.customer_email)) {
        resetSupportChatForUserChange();
        supportChatState.error = 'Historie chatu nepatří k aktuálnímu účtu.';
        updateSupportChatUi();
        return;
      }
      bindSupportChatOwner(payload.customer_id, payload.customer_email);
      supportChatState.activeSessionId = payload.session_id || null;
      if (supportChatState.viewingSessionId == null) {
        supportChatState.sessionId = supportChatState.activeSessionId;
        supportChatState.viewingReadOnly = !!payload.read_only;
      }
      const history = Array.isArray(payload.messages) ? payload.messages.map((m) => ({
        id: m.id,
        sender_type: m.sender_type,
        text: m.text,
        created_at: m.created_at,
      })) : [];
      supportChatState.messages = history;
      renderSupportChatMessages();
      void loadSupportChatSessions();
    } catch (e) {
      supportChatState.error = (e && e.message) ? e.message : 'Historii chatu se nepodařilo načíst.';
      updateSupportChatUi();
    }
  }

  function sendSupportChatMessage() {
    if (supportChatState.viewingReadOnly) return;
    const input = document.getElementById('uappSupportChatInput');
    const text = (input && input.value || '').trim();
    if (!text) return;
    notifySupportUserTyping(false);
    const ws = supportChatState.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      supportChatState.error = 'Chat není připojen. Počkejte na připojení nebo použijte formulář.';
      updateSupportChatUi();
      return;
    }
    ws.send(JSON.stringify({ type: 'message', text }));
    if (input) input.value = '';
  }

  async function submitSupportOfflineForm() {
    if (supportChatState.offlineSubmitting) return;
    const emailEl = document.getElementById('uappSupportOfflineEmail');
    const subjectEl = document.getElementById('uappSupportOfflineSubject');
    const messageEl = document.getElementById('uappSupportOfflineMessage');
    const phoneEl = document.getElementById('uappSupportOfflinePhone');
    const resultEl = document.getElementById('uappSupportOfflineResult');
    const contactEmail = (emailEl && emailEl.value || '').trim();
    const subject = (subjectEl && subjectEl.value || '').trim();
    const message = (messageEl && messageEl.value || '').trim();
    const phone = (phoneEl && phoneEl.value || '').trim();
    if (!contactEmail || contactEmail.indexOf('@') < 1) {
      supportChatState.error = 'Zadejte platný kontaktní e-mail.';
      updateSupportChatUi();
      return;
    }
    if (subject.length < 3 || message.length < 10) {
      supportChatState.error = 'Předmět (min. 3 znaky) a zpráva (min. 10 znaků) jsou povinné.';
      updateSupportChatUi();
      return;
    }
    supportChatState.offlineSubmitting = true;
    supportChatState.error = '';
    updateSupportChatUi();
    try {
      const res = await api('/api/v1/support/offline-contact', 'POST', {
        contact_email: contactEmail,
        subject,
        message,
        phone: phone || null,
      });
      if (resultEl) {
        resultEl.hidden = false;
        resultEl.textContent = (res && res.message) || 'Požadavek odeslán. Kopii jsme poslali na váš e-mail.';
        resultEl.className = 'uapp-support-chat-offline-result is-ok';
      }
      appendSupportSystemMessage('Váš požadavek jsme přijali. Kopii jsme poslali na ' + contactEmail + '.');
      if (subjectEl) subjectEl.value = '';
      if (messageEl) messageEl.value = '';
    } catch (e) {
      supportChatState.error = (e && e.message) ? e.message : 'Odeslání se nezdařilo.';
      if (resultEl) {
        resultEl.hidden = false;
        resultEl.textContent = supportChatState.error;
        resultEl.className = 'uapp-support-chat-offline-result is-error';
      }
    } finally {
      supportChatState.offlineSubmitting = false;
      updateSupportChatUi();
    }
  }

  async function openSupportChat() {
    const ownerKey = getSupportChatOwnerKey();
    if (supportChatState.ownerKey && ownerKey && supportChatState.ownerKey !== ownerKey) {
      resetSupportChatForUserChange();
    }
    ensureSupportChatDom();
    bindSupportChatOwner(null, ownerKey);
    supportChatState.open = true;
    supportChatState.error = '';
    supportChatState.adminTyping = false;
    supportChatState.viewingSessionId = null;
    supportChatState.viewingReadOnly = false;
    supportChatState.sessionsPanelOpen = false;
    clearSupportChatDom();
    updateSupportChatUi();
    await loadSupportChatStatus();
    await loadSupportChatSessions();
    await loadSupportChatHistory();
    connectSupportChatWs();
  }

  function closeSupportChat() {
    if (supportChatState.reconnectTimer) {
      clearTimeout(supportChatState.reconnectTimer);
      supportChatState.reconnectTimer = null;
    }
    if (supportChatState.typingStopTimer) {
      clearTimeout(supportChatState.typingStopTimer);
      supportChatState.typingStopTimer = null;
    }
    if (supportChatState.ws) {
      try { supportChatState.ws.close(); } catch (e) { /* ignore */ }
      supportChatState.ws = null;
    }
    supportChatState.open = false;
    supportChatState.status = 'idle';
    updateSupportChatUi();
  }

  function toggleSupportChat() {
    if (supportChatState.open) closeSupportChat();
    else openSupportChat();
  }

  window.openSupportChat = openSupportChat;
  window.toggleSupportChat = toggleSupportChat;
  window.closeSupportChat = closeSupportChat;
  window.resetSupportChatForUserChange = resetSupportChatForUserChange;

  window.UserSettings = {
    renderInto,
    mount,
    refresh,
    onRoutePanel,
    navigatePanel,
    getPanel: () => STATE.panel,
  };
})();
