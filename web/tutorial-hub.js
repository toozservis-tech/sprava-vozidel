/**
 * Minimální production-safe hub „Jak na to“ — bez závislosti na chybějícím tutorial-engine.js.
 * Nepoužívá fake kroky; u nedostupných návodů zobrazí „Připravujeme“.
 */
(function () {
  'use strict';

  var TUTORIAL_CATALOG = [
    {
      id: 'add-vehicle',
      title: 'Přidání vozidla',
      description: 'Jak zadat vozidlo, SPZ, VIN a dokončit registraci v garáži.',
      ready: true,
      action: function () {
        if (typeof window.openAddVehicleModal === 'function') {
          window.closeHowToHubModal();
          window.openAddVehicleModal();
          return;
        }
        if (typeof window.switchTab === 'function') {
          window.closeHowToHubModal();
          window.switchTab('vehicles', { expandVehiclesAdd: true });
        }
      },
    },
    {
      id: 'reservations',
      title: 'Objednání servisu',
      description: 'Rezervace termínu u servisního partnera.',
      ready: true,
      action: function () {
        window.closeHowToHubModal();
        if (typeof window.switchTab === 'function') {
          window.switchTab('reservations');
        }
      },
    },
    {
      id: 'documents',
      title: 'Dokumenty a doklady',
      description: 'Nahrání a správa dokumentů k vozidlům.',
      ready: true,
      action: function () {
        window.closeHowToHubModal();
        if (typeof window.switchTab === 'function') {
          window.switchTab('documents');
        }
      },
    },
    {
      id: 'service-partners',
      title: 'Servisní partneři',
      description: 'Vyhledání servisu a propojení vozidla.',
      ready: true,
      action: function () {
        window.closeHowToHubModal();
        if (typeof window.switchTab === 'function') {
          window.switchTab('servicesDirectory');
        }
      },
    },
    {
      id: 'reminders',
      title: 'Připomínky STK a servisu',
      description: 'Nastavení termínů a upozornění.',
      ready: true,
      action: function () {
        window.closeHowToHubModal();
        if (typeof window.switchTab === 'function') {
          window.switchTab('reminders');
        }
      },
    },
    {
      id: 'vin-decode',
      title: 'Automatické načtení z VIN',
      description: 'Průvodce dekódováním VIN (Premium).',
      ready: false,
    },
    {
      id: 'ai-assistant',
      title: 'AI asistent',
      description: 'Nápověda k servisním záznamům.',
      ready: false,
    },
  ];

  function esc(text) {
    return String(text || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function renderCategories(container) {
    if (!container) return;
    container.innerHTML = TUTORIAL_CATALOG.map(function (item) {
      var status = item.ready
        ? '<button type="button" class="btn btn-primary how-to-hub-card__btn" data-tutorial-id="' + esc(item.id) + '">Zobrazit</button>'
        : '<span class="how-to-hub-card__pending">Připravujeme</span>';
      return (
        '<article class="how-to-hub-card" data-testid="how-to-hub-card-' + esc(item.id) + '">' +
          '<h3 class="how-to-hub-card__title">' + esc(item.title) + '</h3>' +
          '<p class="how-to-hub-card__desc">' + esc(item.description) + '</p>' +
          status +
        '</article>'
      );
    }).join('');

    container.querySelectorAll('[data-tutorial-id]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var id = btn.getAttribute('data-tutorial-id');
        var entry = TUTORIAL_CATALOG.find(function (x) { return x.id === id; });
        if (entry && typeof entry.action === 'function') {
          entry.action();
        }
      });
    });
  }

  function getModal() {
    return document.getElementById('howToHubModal');
  }

  window.openHowToHubModal = function openHowToHubModal() {
    var modal = getModal();
    if (!modal) {
      if (typeof window.switchTab === 'function') {
        window.switchTab('support');
      }
      return;
    }
    var container = document.getElementById('howToHubCategories');
    renderCategories(container);
    modal.style.display = 'flex';
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('modal-open');
  };

  window.closeHowToHubModal = function closeHowToHubModal() {
    var modal = getModal();
    if (!modal) return;
    modal.style.display = 'none';
    modal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('modal-open');
  };

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') {
      var modal = getModal();
      if (modal && modal.style.display !== 'none' && modal.getAttribute('aria-hidden') === 'false') {
        window.closeHowToHubModal();
      }
    }
  });
})();
