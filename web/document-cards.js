/**
 * Shared vehicle document cards (C1.0 platform).
 */
(function initToozDocumentCards(global) {
  'use strict';

  const STATUS_LABELS = {
    draft: 'Koncept',
    pending: 'Čeká',
    approved: 'Schváleno',
    completed: 'Dokončeno',
    cancelled: 'Zrušeno',
    archived: 'Archiv',
  };

  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function statusLabel(status) {
    return STATUS_LABELS[String(status || '').toLowerCase()] || String(status || '—');
  }

  function renderDocumentCard(doc, options) {
    const opts = options || {};
    const cardClass = opts.cardClass || 'vehicle-document-card';
    const id = Number(doc.id);
    const thumbUrl = doc.thumbnail_url || '';
    const actions = Array.isArray(doc.actions) ? doc.actions : ['open', 'download'];
    const actionButtons = [];

    if (actions.includes('open')) {
      actionButtons.push(`<button type="button" class="${opts.buttonClass || 'vehicle-document-action'}" data-testid="vehicle-document-open-button" data-doc-action="open" data-doc-id="${id}" data-doc-file-url="${escapeHtml(doc.file_url || '')}">Otevřít</button>`);
    }
    if (actions.includes('download')) {
      actionButtons.push(`<button type="button" class="${opts.buttonClass || 'vehicle-document-action'}" data-testid="vehicle-document-download-button" data-doc-action="download" data-doc-id="${id}" data-doc-file-url="${escapeHtml(doc.file_url || '')}">Stáhnout</button>`);
    }
    if (actions.includes('share') && doc.verify_url) {
      actionButtons.push(`<button type="button" class="${opts.buttonClass || 'vehicle-document-action'}" data-testid="vehicle-document-share-button" data-doc-action="share" data-doc-id="${id}" data-doc-verify-url="${escapeHtml(doc.verify_url || '')}">Sdílet</button>`);
    }
    if (actions.includes('verify') && doc.verify_url) {
      actionButtons.push(`<button type="button" class="${opts.buttonClass || 'vehicle-document-action'}" data-testid="vehicle-document-verify-button" data-doc-action="verify" data-doc-id="${id}" data-doc-verify-url="${escapeHtml(doc.verify_url || '')}">Ověřit</button>`);
    }

    return `
      <article class="${cardClass}" data-testid="vehicle-document-card" data-document-id="${id}" data-document-type="${escapeHtml(doc.document_type || '')}">
        <div class="vehicle-document-card__thumb-wrap">
          <img class="vehicle-document-card__thumb" data-testid="vehicle-document-thumbnail" src="${escapeHtml(thumbUrl)}" alt="Náhled dokumentu ${escapeHtml(doc.label || '')}" loading="lazy" />
        </div>
        <div class="vehicle-document-card__body">
          <div class="vehicle-document-card__type" data-testid="vehicle-document-type">${escapeHtml(doc.label || doc.document_type || 'Dokument')}</div>
          <div class="vehicle-document-card__status" data-testid="vehicle-document-status">${escapeHtml(statusLabel(doc.status))}</div>
          <div class="vehicle-document-card__title">${escapeHtml(doc.title || '')}</div>
          <div class="vehicle-document-card__meta">
            <span data-testid="vehicle-document-date">${escapeHtml((doc.created_at || '').slice(0, 10))}</span>
            <span>${escapeHtml(doc.service_display || 'Servis')}</span>
            <span>${escapeHtml(doc.vehicle_label || '')}</span>
          </div>
          <div class="vehicle-document-card__actions">${actionButtons.join('')}</div>
        </div>
      </article>`;
  }

  function renderDocumentCards(docs, options) {
    const list = Array.isArray(docs) ? docs : [];
    if (!list.length) {
      return `<div class="vehicle-document-cards-empty">${escapeHtml((options && options.emptyText) || 'Žádné dokumenty.')}</div>`;
    }
    const gridClass = (options && options.gridClass) || 'vehicle-document-cards-grid';
    return `<div class="${gridClass}" data-testid="vehicle-document-cards-grid">${list.map((doc) => renderDocumentCard(doc, options)).join('')}</div>`;
  }

  function bindDocumentCardActions(root, handlers) {
    const container = root || document;
    container.querySelectorAll('[data-doc-action]').forEach((button) => {
      button.addEventListener('click', () => {
        const action = button.getAttribute('data-doc-action');
        const fileUrl = button.getAttribute('data-doc-file-url') || '';
        const verifyUrl = button.getAttribute('data-doc-verify-url') || '';
        if (action === 'open' && fileUrl) {
          if (handlers && typeof handlers.onOpen === 'function') handlers.onOpen(fileUrl, button);
          else window.open(fileUrl, '_blank', 'noopener');
          return;
        }
        if (action === 'download' && fileUrl) {
          if (handlers && typeof handlers.onDownload === 'function') handlers.onDownload(fileUrl, button);
          else window.open(fileUrl, '_blank', 'noopener');
          return;
        }
        if ((action === 'verify' || action === 'share') && verifyUrl) {
          if (handlers && typeof handlers.onVerify === 'function') handlers.onVerify(verifyUrl, button);
          else window.open(verifyUrl, '_blank', 'noopener');
        }
      });
    });
  }

  global.ToozDocumentCards = {
    renderDocumentCard,
    renderDocumentCards,
    bindDocumentCardActions,
    statusLabel,
  };
})(typeof window !== 'undefined' ? window : globalThis);
