const betaApplicationForm = document.getElementById('betaApplicationForm');
const betaFormStatus = document.getElementById('betaFormStatus');
const betaApplicantTypeInput = document.getElementById('betaApplicantType');
const betaAudienceCards = Array.from(document.querySelectorAll('[data-beta-audience]'));
const betaVehicleHint = document.getElementById('betaVehicleHint');

function setBetaFormStatus(message, tone = '') {
  if (!betaFormStatus) return;
  betaFormStatus.textContent = message || '';
  betaFormStatus.classList.remove('is-error', 'is-success');
  if (tone === 'error') betaFormStatus.classList.add('is-error');
  if (tone === 'success') betaFormStatus.classList.add('is-success');
}

function applyAudienceSelection(type) {
  if (!betaApplicantTypeInput) return;
  betaApplicantTypeInput.value = type;
  betaAudienceCards.forEach((card) => {
    card.classList.toggle('is-selected', card.dataset.betaAudience === type);
  });

  if (!betaVehicleHint) return;
  if (type === 'service') {
    betaVehicleHint.textContent = 'U servisu uveďte přibližný počet aktivně obsluhovaných vozidel nebo zákaznických aut měsíčně.';
  } else if (type === 'company') {
    betaVehicleHint.textContent = 'U firmy nebo malé flotily uveďte počet vozidel, která opravdu plánujete spravovat v beta provozu.';
  } else {
    betaVehicleHint.textContent = 'U běžného uživatele stačí počet aut, která chcete ve službě Správa vozidel aktivně spravovat.';
  }
}

betaAudienceCards.forEach((card) => {
  card.addEventListener('click', () => applyAudienceSelection(card.dataset.betaAudience || 'user'));
});

if (betaApplicantTypeInput) {
  betaApplicantTypeInput.addEventListener('change', (event) => {
    applyAudienceSelection(event.target.value || 'user');
  });
}

async function submitBetaApplication(event) {
  event.preventDefault();
  if (!betaApplicationForm) return;

  const submitButton = betaApplicationForm.querySelector('button[type="submit"]');
  const formData = new FormData(betaApplicationForm);
  const payload = {
    name: String(formData.get('name') || '').trim(),
    email: String(formData.get('email') || '').trim(),
    phone: String(formData.get('phone') || '').trim(),
    applicant_type: String(formData.get('applicant_type') || '').trim(),
    vehicle_count: Number(formData.get('vehicle_count') || 0),
    note: String(formData.get('note') || '').trim(),
    gdpr_consent: Boolean(formData.get('gdpr_consent')),
  };

  if (!payload.name || !payload.email || !payload.phone || !payload.applicant_type) {
    setBetaFormStatus('Vyplňte prosím jméno, e-mail, telefon a typ zájemce.', 'error');
    return;
  }
  if (!payload.gdpr_consent) {
    setBetaFormStatus('Bez GDPR souhlasu nemůžeme beta přihlášku přijmout.', 'error');
    return;
  }

  try {
    setBetaFormStatus('Odesílám beta přihlášku...');
    if (submitButton) submitButton.disabled = true;

    const response = await fetch('/beta/applications', {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || data.message || 'Nepodařilo se odeslat beta přihlášku.');
    }

    betaApplicationForm.reset();
    applyAudienceSelection('user');
    setBetaFormStatus(data.message || 'Beta přihláška byla přijata.', 'success');
  } catch (error) {
    setBetaFormStatus(error.message || 'Nepodařilo se odeslat beta přihlášku.', 'error');
  } finally {
    if (submitButton) submitButton.disabled = false;
  }
}

if (betaApplicationForm) {
  betaApplicationForm.addEventListener('submit', submitBetaApplication);
}

applyAudienceSelection(betaApplicantTypeInput?.value || 'user');
