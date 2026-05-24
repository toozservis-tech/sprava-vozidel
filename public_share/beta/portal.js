const portalState = {
  participant: null,
  application: null,
  reward: null,
};

function portalToken() {
  return (
    localStorage.getItem('accessToken')
    || sessionStorage.getItem('accessToken')
    || localStorage.getItem('token')
    || sessionStorage.getItem('token')
    || ''
  );
}

function portalSetText(id, value) {
  const element = document.getElementById(id);
  if (!element) return;
  element.textContent = value ?? '-';
}

function portalSetHtml(id, value) {
  const element = document.getElementById(id);
  if (!element) return;
  element.innerHTML = value || '';
}

function portalSetStatus(message, tone = '') {
  const element = document.getElementById('portalFeedbackStatus');
  if (!element) return;
  element.textContent = message || '';
  element.classList.remove('is-error', 'is-success');
  if (tone === 'error') element.classList.add('is-error');
  if (tone === 'success') element.classList.add('is-success');
}

function betaApiHeaders() {
  const token = portalToken();
  if (!token) return null;
  return {
    Accept: 'application/json',
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  };
}

function formatDateTime(value) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleString('cs-CZ');
}

function renderPortalBanner(payload) {
  const banner = document.getElementById('portalStatusBanner');
  if (!banner) return;

  if (payload.is_participant && payload.participant) {
    const reward = payload.reward;
    const recommendation = payload.participant.recommendation || {};
    const rewardLine = reward?.status === 'granted'
      ? 'Lifetime Premium už byl přidělen.'
      : (recommendation.recommended
        ? 'Developer admin už vidí doporučení na lifetime Premium.'
        : 'Lifetime Premium se posuzuje podle reálné aktivity, feedbacku a dopadu.');

    banner.className = 'status-banner is-success';
    banner.innerHTML = `
      <strong>Beta účet je aktivní</strong>
      <p>${rewardLine}</p>
    `;
    return;
  }

  if (payload.application) {
    const status = String(payload.application.status || '').toLowerCase();
    if (status === 'pending') {
      banner.className = 'status-banner is-warn';
      banner.innerHTML = `
        <strong>Beta přihláška čeká na posouzení</strong>
        <p>Developer admin ji může schválit až ve chvíli, kdy dává smysl navázání na reálný účet a testovací přínos.</p>
      `;
      return;
    }
    if (status === 'rejected') {
      banner.className = 'status-banner is-error';
      banner.innerHTML = `
        <strong>Beta přihláška zatím nebyla schválena</strong>
        <p>${payload.application.decision_reason || 'Pokud máte nový účet nebo silnější use-case, pošlete novou beta přihlášku.'}</p>
      `;
      return;
    }
  }

  banner.className = 'status-banner';
  banner.innerHTML = `
    <strong>Nejste ve schválené beta</strong>
    <p>Nejdřív pošlete beta přihlášku na landing page, nebo dokončete navázání účtu s developer adminem.</p>
  `;
}

function renderPortalMetrics(participant) {
  const metrics = participant?.metrics || {};
  portalSetText('metricActivityScore', String(Math.round(Number(metrics.activity_score || 0))));
  portalSetText('metricImpactScore', String(Math.round(Number(metrics.impact_score || 0))));
  portalSetText('metricFeedbackCount', String((metrics.feedback_count || 0) + (metrics.bug_reports_count || 0)));
  portalSetText('metricLastActive', participant?.last_active_at ? formatDateTime(participant.last_active_at) : 'bez aktivity');
  portalSetText('portalLinkedAccount', participant?.linked_user?.email || participant?.linked_service_account?.email || participant?.email || '-');
  portalSetText('portalLinkedTenant', participant?.linked_tenant?.name || 'Nepřiřazeno');
  portalSetText('portalParticipantType', participant?.applicant_type || '-');
  portalSetText('portalRewardStatus', participant?.reward?.status === 'granted' ? 'Lifetime Premium přidělen' : 'Zatím bez finální odměny');
}

function renderPortalApplication(application) {
  const container = document.getElementById('portalApplicationSummary');
  if (!container) return;
  if (!application) {
    container.innerHTML = '<div class="empty-copy">Zatím tu není žádná aktivní beta přihláška.</div>';
    return;
  }
  container.innerHTML = `
    <div class="helper-card">
      <strong>Beta přihláška #${application.id}</strong>
      <p class="helper-copy">Stav: <strong>${application.status}</strong><br>Typ: <strong>${application.applicant_type}</strong><br>Vazba: <strong>${application.link_method || 'čeká na link'}</strong></p>
      <p class="helper-copy">${application.link_note || application.review_note || application.decision_reason || 'Čeká na další krok developera.'}</p>
    </div>
  `;
}

function renderPortalFeedbackHistory(items = []) {
  const container = document.getElementById('portalFeedbackHistory');
  if (!container) return;
  if (!Array.isArray(items) || items.length === 0) {
    container.innerHTML = '<div class="empty-copy">Zatím tu není žádný feedback ani bug report.</div>';
    return;
  }

  container.innerHTML = items.map((item) => {
    const categoryClass = item.category === 'bug_report' ? 'pill is-bug' : 'pill is-feedback';
    return `
      <article class="history-item">
        <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;">
          <div>
            <strong>${item.title}</strong>
            <div class="history-meta">
              <span class="${categoryClass}">${item.category === 'bug_report' ? 'Bug report' : 'Feedback'}</span>
              <span class="pill">${item.status}</span>
              <span class="pill">${item.severity}</span>
              <span>${formatDateTime(item.created_at)}</span>
            </div>
          </div>
        </div>
        <p>${item.message}</p>
        ${item.admin_note ? `<p><strong>Poznámka developera:</strong> ${item.admin_note}</p>` : ''}
      </article>
    `;
  }).join('');
}

function togglePortalExperience(payload) {
  const gate = document.getElementById('portalAuthGate');
  const app = document.getElementById('portalApp');
  const feedbackPanel = document.getElementById('portalFeedbackPanel');
  const participantActive = Boolean(payload?.is_participant && payload?.participant);

  if (app) app.classList.remove('hidden');
  if (gate) gate.classList.add('hidden');
  if (feedbackPanel) feedbackPanel.classList.toggle('hidden', !participantActive);
}

async function loadPortalState() {
  const headers = betaApiHeaders();
  const gate = document.getElementById('portalAuthGate');
  const app = document.getElementById('portalApp');

  if (!headers) {
    if (gate) gate.classList.remove('hidden');
    if (app) app.classList.add('hidden');
    return;
  }

  try {
    const response = await fetch('/beta/me', {
      method: 'GET',
      headers,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || 'Nepodařilo se načíst beta portál.');
    }

    portalState.participant = payload.participant || null;
    portalState.application = payload.application || null;
    portalState.reward = payload.reward || null;

    renderPortalBanner(payload);
    renderPortalMetrics(payload.participant || {});
    renderPortalApplication(payload.application);
    renderPortalFeedbackHistory(payload.feedback || []);
    togglePortalExperience(payload);
  } catch (error) {
    if (gate) gate.classList.remove('hidden');
    if (app) app.classList.add('hidden');
    const helper = document.getElementById('portalAuthStatus');
    if (helper) helper.textContent = error.message || 'Beta portál se nepodařilo načíst.';
  }
}

async function submitPortalFeedback(event) {
  event.preventDefault();
  if (!portalState.participant) {
    portalSetStatus('Feedback mohou posílat jen schválení beta testeři.', 'error');
    return;
  }

  const headers = betaApiHeaders();
  if (!headers) {
    portalSetStatus('Chybí přihlášení. Přihlaste se z hlavní aplikace.', 'error');
    return;
  }

  const form = event.currentTarget;
  const submitButton = form.querySelector('button[type="submit"]');
  const formData = new FormData(form);
  const payload = {
    category: String(formData.get('category') || '').trim(),
    title: String(formData.get('title') || '').trim(),
    message: String(formData.get('message') || '').trim(),
    severity: String(formData.get('severity') || '').trim(),
    context_area: String(formData.get('context_area') || '').trim(),
    route_path: String(formData.get('route_path') || '').trim(),
  };

  try {
    portalSetStatus('Odesílám feedback...');
    if (submitButton) submitButton.disabled = true;
    const response = await fetch('/beta/feedback', {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || 'Nepodařilo se uložit feedback.');
    }
    form.reset();
    portalSetStatus(data.message || 'Feedback byl uložen.', 'success');
    await loadPortalState();
  } catch (error) {
    portalSetStatus(error.message || 'Nepodařilo se uložit feedback.', 'error');
  } finally {
    if (submitButton) submitButton.disabled = false;
  }
}

const portalFeedbackForm = document.getElementById('portalFeedbackForm');
if (portalFeedbackForm) {
  portalFeedbackForm.addEventListener('submit', submitPortalFeedback);
}

loadPortalState();
