import type { Page, Route } from '@playwright/test';

import { loginServiceUser, waitForServiceShellReady } from './helpers';

export const serviceUser = {
  id: 9901,
  email: 'service.workspace@example.com',
  role: 'service',
  name: 'ToozServis',
  phone: '+420123456789',
};

const serviceWorkspaceMe = {
  authenticated: true,
  app_name: 'Správa vozidel',
  account_type: 'service',
  account_id: serviceUser.id,
  display_name: serviceUser.name,
  email: serviceUser.email,
  account_slug: 'toozservis',
  tenant_id: 9901,
  workspace_route_kind: 'service',
  default_app_path: '/app/s/toozservis/dashboard',
  role: 'service',
  license_plan: 'test',
  license_status: 'active',
  permissions: {},
};

function json(route: Route, status: number, body: unknown): Promise<void> {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

export async function installServiceShellMocks(
  page: Page,
  options: {
    seedCurrentUser?: boolean;
    forceServiceWorkspaceRole?: boolean;
    preserveAuth?: boolean;
  } = {},
): Promise<void> {
  const seedCurrentUser = options.seedCurrentUser !== false;
  const forceServiceWorkspaceRole = options.forceServiceWorkspaceRole !== false;
  const preserveAuth = options.preserveAuth === true;
  let linkedCustomer = false;
  let nextWorkOrderId = 777;
  let nextRecordId = 602;
  const workOrders = [
    {
      id: 501,
      title: 'Výchozí zakázka',
      customer_name: 'Linked Customer',
      owner_id: 101,
      vehicle_id: 301,
      vehicle_vin: 'VINLINKED123456789',
      vehicle_spz: '1AB2345',
      due_date: '2026-04-12',
      status: 'completed',
      source_type: 'manual',
      source_intake_id: 701,
      service_record_id: 601,
      technician_id: 9901,
      technician_name: 'ToozServis',
      description: 'Detail zakázky',
      audit_log: [
        { id: 1, action: 'create', created_at: '2026-04-12T10:00:00Z' },
        { id: 2, action: 'approve', created_at: '2026-04-12T11:00:00Z' },
      ],
    },
    {
      id: 502,
      title: 'Dokončená zakázka bez záznamu',
      customer_name: 'Linked Customer',
      owner_id: 101,
      vehicle_id: 301,
      vehicle_vin: 'VINLINKED123456789',
      vehicle_spz: '1AB2345',
      due_date: '2026-04-13',
      status: 'completed',
      source_type: 'manual',
      source_intake_id: null,
      service_record_id: null,
      technician_id: 9901,
      technician_name: 'ToozServis',
      description: 'Servis brzd',
      audit_log: [
        { id: 1, action: 'create', created_at: '2026-04-13T10:00:00Z' },
        { id: 2, action: 'completed', created_at: '2026-04-13T11:00:00Z' },
      ],
    },
  ];
  const serviceRecords = [
    {
      id: 601,
      vehicle_id: 301,
      performed_at: '2026-04-11T08:30:00Z',
      mileage: 145000,
      description: 'Výměna oleje a filtrů',
      price: 3490,
      total_price: 3490,
      note: 'Interní poznámka',
      notes_customer_visible: 'Další výměna za 12 měsíců.',
      category: 'OLEJ',
      record_status: 'submitted',
      attachments: '[]',
      created_by_service_customer_id: 9901,
    },
  ];
   let nextQuoteId = 805;
  type MockServiceQuote = {
    id: number;
    vehicle_id: number;
    customer_id: number;
    service_id: number;
    work_order_id: number | null;
    service_record_id: number | null;
    items: { name: string; quantity: number; unit_price: number; total_price: number }[];
    labor_hours: number | null;
    labor_rate: number | null;
    total_price: number;
    status: string;
    status_label: string;
    vehicle_label: string;
    service_name: string;
    service_ico: string;
    pdf_url: string;
    public_quote_url: string;
    customer_email: string;
    customer_phone: string;
    created_at: string;
    updated_at: string;
    approved_at?: string;
    rejected_at?: string;
  };
  const serviceQuotes: MockServiceQuote[] = [
    {
      id: 800,
      vehicle_id: 301,
      customer_id: 101,
      service_id: 9901,
      work_order_id: 501,
      service_record_id: 601,
      items: [
        { name: 'Výměna oleje a filtrů', quantity: 1, unit_price: 3490, total_price: 3490 },
      ],
      labor_hours: 1.5,
      labor_rate: 890,
      total_price: 3490,
      status: 'sent',
      status_label: 'Odesláno',
      vehicle_label: 'Skoda Octavia',
      service_name: 'ToozServis',
      service_ico: '12345678',
      pdf_url: '/api/service/quotes/800/pdf',
      public_quote_url: 'http://127.0.0.1:8000/web/public-quote.html?token=quote-public-token',
      customer_email: 'linked@example.com',
      customer_phone: '+420111222333',
      created_at: '2026-04-15T09:00:00Z',
      updated_at: '2026-04-15T09:00:00Z',
    },
    {
      id: 802,
      vehicle_id: 301,
      customer_id: 101,
      service_id: 9901,
      work_order_id: null,
      service_record_id: null,
      items: [],
      labor_hours: null,
      labor_rate: null,
      total_price: 1500,
      status: 'draft',
      status_label: 'Koncept',
      vehicle_label: 'Skoda Octavia',
      service_name: 'ToozServis',
      service_ico: '12345678',
      pdf_url: '/api/service/quotes/802/pdf',
      public_quote_url: 'http://127.0.0.1:8000/web/public-quote.html?token=tok-802',
      customer_email: 'linked@example.com',
      customer_phone: '+420111222333',
      created_at: '2026-04-10T10:00:00Z',
      updated_at: '2026-04-10T10:00:00Z',
    },
    {
      id: 803,
      vehicle_id: 301,
      customer_id: 101,
      service_id: 9901,
      work_order_id: null,
      service_record_id: null,
      items: [],
      labor_hours: null,
      labor_rate: null,
      total_price: 9000,
      status: 'approved',
      status_label: 'Schváleno',
      vehicle_label: 'Skoda Octavia',
      service_name: 'ToozServis',
      service_ico: '12345678',
      pdf_url: '/api/service/quotes/803/pdf',
      public_quote_url: 'http://127.0.0.1:8000/web/public-quote.html?token=tok-803',
      customer_email: 'linked@example.com',
      customer_phone: '+420111222333',
      created_at: '2026-04-14T11:00:00Z',
      updated_at: '2026-04-14T11:00:00Z',
      approved_at: '2026-04-14T15:00:00Z',
    },
    {
      id: 804,
      vehicle_id: 301,
      customer_id: 101,
      service_id: 9901,
      work_order_id: null,
      service_record_id: null,
      items: [],
      labor_hours: null,
      labor_rate: null,
      total_price: 1200,
      status: 'rejected',
      status_label: 'Zamítnuto',
      vehicle_label: 'Skoda Octavia',
      service_name: 'ToozServis',
      service_ico: '12345678',
      pdf_url: '/api/service/quotes/804/pdf',
      public_quote_url: 'http://127.0.0.1:8000/web/public-quote.html?token=tok-804',
      customer_email: 'linked@example.com',
      customer_phone: '+420111222333',
      created_at: '2026-04-13T12:00:00Z',
      updated_at: '2026-04-13T12:00:00Z',
      rejected_at: '2026-04-13T16:00:00Z',
    },
  ];
  let nextInvoiceId = 9002;
  const buildInvoiceVehicleDocument = (invoiceId: number, vehicleId = 301, status = 'draft') => {
    const docId = 5000 + invoiceId;
    const issued = status === 'issued';
    return {
      id: docId,
      document_type: 'invoice',
      label: 'Faktura',
      status: issued ? 'completed' : 'draft',
      title: issued ? `Faktura FV-2026-${String(invoiceId).padStart(4, '0')}` : `Faktura — koncept #${invoiceId}`,
      document_number: issued ? `FV-2026-${String(invoiceId).padStart(4, '0')}` : null,
      created_at: '2026-04-16T10:00:00Z',
      vehicle_id: vehicleId,
      vehicle_label: 'Octavia',
      service_display: 'ToozServis',
      thumbnail_url: `/api/v1/vehicles/${vehicleId}/documents/${docId}/thumbnail`,
      file_url: `/api/v1/vehicles/${vehicleId}/documents/${docId}/file`,
      verify_url: `http://127.0.0.1:8000/api/public/documents/verify/inv-token-${invoiceId}`,
      actions: ['open', 'download', 'verify'],
    };
  };
  const attachInvoicePlatformDoc = (invoice: Record<string, unknown>) => {
    const id = Number(invoice.id || 0);
    const vehicleId = Number(invoice.vehicle_id || 301);
    const status = String(invoice.status || 'draft');
    const card = buildInvoiceVehicleDocument(id, vehicleId, status);
    invoice.vehicle_document_id = card.id;
    invoice.vehicle_document = card;
    invoice.pdf_url = card.file_url;
    return invoice;
  };
  const buildQuoteVehicleDocument = (quoteId: number, vehicleId = 301, status = 'sent') => {
    const docId = 6000 + quoteId;
    return {
      id: docId,
      document_type: 'quote',
      label: 'Nabídka',
      status: status === 'approved' ? 'approved' : status === 'sent' ? 'pending' : 'draft',
      title: `Nabídka NAB-${String(quoteId).padStart(5, '0')}`,
      document_number: `NAB-${String(quoteId).padStart(5, '0')}`,
      created_at: '2026-04-15T09:00:00Z',
      vehicle_id: vehicleId,
      vehicle_label: 'Octavia',
      service_display: 'ToozServis',
      thumbnail_url: `/api/v1/vehicles/${vehicleId}/documents/${docId}/thumbnail`,
      file_url: `/api/v1/vehicles/${vehicleId}/documents/${docId}/file`,
      verify_url: `http://127.0.0.1:8000/api/public/documents/verify/quote-token-${quoteId}`,
      actions: ['open', 'download', 'verify'],
    };
  };
  const attachQuotePlatformDoc = (quote: Record<string, unknown>) => {
    const id = Number(quote.id || 0);
    const vehicleId = Number(quote.vehicle_id || 301);
    const status = String(quote.status || 'draft');
    const card = buildQuoteVehicleDocument(id, vehicleId, status);
    quote.vehicle_document_id = card.id;
    quote.vehicle_document = card;
    quote.pdf_url = card.file_url;
    quote.quote_number = `NAB-${String(id).padStart(5, '0')}`;
    return quote;
  };
  serviceQuotes.forEach((quote) => attachQuotePlatformDoc(quote as unknown as Record<string, unknown>));
  const buildWorkOrderSheetVehicleDocument = (workOrderId: number, vehicleId = 301, status = 'pending') => {
    const docId = 5000 + workOrderId;
    return {
      id: docId,
      document_type: 'work_order_sheet',
      label: 'Zakázkový list',
      status,
      title: `Zakázkový list ZL-${String(workOrderId).padStart(5, '0')}`,
      document_number: `ZL-${String(workOrderId).padStart(5, '0')}`,
      created_at: '2026-04-12T09:00:00Z',
      vehicle_id: vehicleId,
      vehicle_label: 'Octavia',
      service_display: 'ToozServis',
      thumbnail_url: `/api/v1/vehicles/${vehicleId}/documents/${docId}/thumbnail`,
      file_url: `/api/v1/vehicles/${vehicleId}/documents/${docId}/file`,
      verify_url: `http://127.0.0.1:8000/api/public/documents/verify/wo-sheet-token-${workOrderId}`,
      actions: ['open', 'download', 'verify'],
    };
  };
  const attachWorkOrderSheetPlatformDoc = (item: Record<string, unknown>) => {
    const id = Number(item.id || 0);
    const vehicleId = Number(item.vehicle_id || 301);
    const card = buildWorkOrderSheetVehicleDocument(id, vehicleId, String(item.status || '').toLowerCase() === 'completed' ? 'completed' : 'pending');
    item.work_order_sheet_document = card;
    item.work_order_sheet_pdf_url = `/api/service/work-orders/${id}/sheet.pdf`;
    return item;
  };
  const buildIntakeProtocolVehicleDocument = (intakeId: number, vehicleId = 301, status = 'pending') => {
    const docId = 7000 + intakeId;
    return {
      id: docId,
      document_type: 'intake_protocol',
      label: 'Příjmový protokol',
      status,
      title: `Příjmový protokol PP-${String(intakeId).padStart(5, '0')}`,
      document_number: `PP-${String(intakeId).padStart(5, '0')}`,
      created_at: '2026-04-12T09:00:00Z',
      vehicle_id: vehicleId,
      vehicle_label: 'Octavia',
      service_display: 'ToozServis',
      thumbnail_url: `/api/v1/vehicles/${vehicleId}/documents/${docId}/thumbnail`,
      file_url: `/api/v1/vehicles/${vehicleId}/documents/${docId}/file`,
      pdf_url: `/api/service/intakes/${intakeId}/protocol.pdf`,
      verify_url: `http://127.0.0.1:8000/api/public/documents/verify/intake-protocol-token-${intakeId}`,
      actions: ['open', 'download', 'verify'],
    };
  };
  const attachIntakeProtocolPlatformDoc = (item: Record<string, unknown>) => {
    const intakeId = Number(item.source_intake_id || 0);
    if (!intakeId) return item;
    const vehicleId = Number(item.vehicle_id || 301);
    const card = buildIntakeProtocolVehicleDocument(intakeId, vehicleId);
    item.intake_protocol_document = card;
    item.intake_protocol_pdf_url = `/api/service/intakes/${intakeId}/protocol.pdf`;
    return item;
  };
  const buildServiceReportVehicleDocument = (serviceRecordId: number, vehicleId = 301, status = 'completed', visibilityScope = 'owner_visible') => {
    const docId = 8000 + serviceRecordId;
    return {
      id: docId,
      document_type: 'service_report',
      label: 'Servisní zpráva',
      status,
      title: `Servisní zpráva SZ-${String(serviceRecordId).padStart(5, '0')}`,
      document_number: `SZ-${String(serviceRecordId).padStart(5, '0')}`,
      created_at: '2026-04-12T09:00:00Z',
      vehicle_id: vehicleId,
      vehicle_label: 'Octavia',
      service_display: 'ToozServis',
      visibility_scope: visibilityScope,
      thumbnail_url: `/api/v1/vehicles/${vehicleId}/documents/${docId}/thumbnail`,
      file_url: `/api/v1/vehicles/${vehicleId}/documents/${docId}/file`,
      pdf_url: `/api/service/service-records/${serviceRecordId}/report.pdf`,
      verify_url: `http://127.0.0.1:8000/api/public/documents/verify/service-report-token-${serviceRecordId}`,
      actions: ['open', 'download', 'verify'],
    };
  };
  const attachServiceReportPlatformDoc = (item: Record<string, unknown>) => {
    const recordId = Number(item.service_record_id || 0);
    if (!recordId) return item;
    const vehicleId = Number(item.vehicle_id || 301);
    const card = buildServiceReportVehicleDocument(recordId, vehicleId);
    item.service_report_document = card;
    item.service_report_pdf_url = `/api/service/service-records/${recordId}/report.pdf`;
    return item;
  };
  workOrders.forEach((item) => {
    attachWorkOrderSheetPlatformDoc(item as unknown as Record<string, unknown>);
    attachIntakeProtocolPlatformDoc(item as unknown as Record<string, unknown>);
    attachServiceReportPlatformDoc(item as unknown as Record<string, unknown>);
  });
  const serviceInvoices = [
    {
      id: 9001,
      tenant_id: 1,
      service_id: 9901,
      customer_id: 101,
      vehicle_id: 301,
      invoice_number: null as string | null,
      status: 'draft',
      status_label: 'Koncept',
      subtotal: 826.45,
      tax_total: 173.55,
      total: 1000,
      currency: 'CZK',
      issued_at: null as string | null,
      due_at: null as string | null,
      cancelled_at: null as string | null,
      notes: null as string | null,
      customer_label: 'Linked Customer',
      vehicle_label: 'Octavia',
      created_at: '2026-04-16T10:00:00Z',
      updated_at: '2026-04-16T10:00:00Z',
      lines: [
        {
          id: 1,
          description: 'Servisní úkon',
          quantity: 1,
          unit: 'ks',
          unit_price: 826.45,
          tax_rate: 21,
          line_total: 1000,
          sort_order: 0,
        },
      ],
    },
  ];
  attachInvoicePlatformDoc(serviceInvoices[0]);
  let qrToken: {
    id: number;
    vehicle_id: number;
    token: string;
    public_mode: string;
    explicit_full_consent: boolean;
    issued_at: string;
    revoked_at: string | null;
    last_access_at: string | null;
    signature_hash: string;
    active: boolean;
    public_history_url: string;
    qr_svg: string;
  } = {
    id: 91,
    vehicle_id: 301,
    token: 'secure-public-token',
    public_mode: 'verified',
    explicit_full_consent: false,
    issued_at: '2026-04-15T09:30:00Z',
    revoked_at: null,
    last_access_at: '2026-04-15T10:30:00Z',
    signature_hash: 'test-signature',
    active: true,
    public_history_url: 'http://127.0.0.1:8000/web/public-vehicle-history.html?token=secure-public-token',
    qr_svg: '<svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10" fill="white"/><rect x="1" y="1" width="3" height="3" fill="black"/><rect x="6" y="1" width="3" height="3" fill="black"/><rect x="3" y="6" width="4" height="3" fill="black"/></svg>',
  };

  const buildSummary = () => ({
    active_jobs: workOrders.filter((item) => ['in_progress', 'approved'].includes(String(item.status || '').toLowerCase())).length,
    awaiting_approval: workOrders.filter((item) => String(item.status || '').toLowerCase() === 'awaiting_client_approval').length,
    due_today: 1,
    overdue: 0,
  });

  const buildQueue = () => {
    const awaitingApproval = workOrders.filter((item) => String(item.status || '').toLowerCase() === 'awaiting_client_approval').length;
    return {
      new_jobs: workOrders.length,
      new_orders: workOrders.length,
      awaiting_approval: awaitingApproval,
      missing_documents: workOrders.length,
      conflicting_data: 0,
      missing_client_consent: awaitingApproval,
      suspicious_km: 0,
      unfinished_jobs: workOrders.filter((item) => String(item.status || '').toLowerCase() !== 'completed').length,
      internal_warnings: 0,
    };
  };

  const serializeWorkOrderDetail = (item: (typeof workOrders)[number]) => ({
    quote_summary: (() => {
      const quote = serviceQuotes.find((entry) => entry.work_order_id === item.id);
      return quote ? {
        quote_id: quote.id,
        status: quote.status,
        status_label: quote.status_label,
        total_price: quote.total_price,
        approved_at: (quote as { approved_at?: string }).approved_at || null,
        rejected_at: (quote as { rejected_at?: string }).rejected_at || null,
        public_quote_url: quote.public_quote_url,
        consistency_note: null,
      } : null;
    })(),
    work_order_sheet_document: (item as { work_order_sheet_document?: unknown }).work_order_sheet_document || null,
    work_order_sheet_pdf_url: `/api/service/work-orders/${item.id}/sheet.pdf`,
    intake_protocol_document: (item as { intake_protocol_document?: unknown }).intake_protocol_document || null,
    intake_protocol_pdf_url: (item as { intake_protocol_pdf_url?: string }).intake_protocol_pdf_url || null,
    source_intake_id: (item as { source_intake_id?: number }).source_intake_id || null,
    service_record_id: (item as { service_record_id?: number | null }).service_record_id ?? null,
    service_report_document: (item as { service_report_document?: unknown }).service_report_document || null,
    service_report_pdf_url: (item as { service_report_pdf_url?: string }).service_report_pdf_url || null,
    items: {
      labor: [{ id: 1, item_type: 'labor', name: 'Výměna oleje a filtrů', quantity: 1.5, unit: 'h', note: null }],
      parts: [{ id: 2, item_type: 'part', name: 'Filtr oleje', quantity: 1, unit: 'ks', note: null }],
      time: [],
    },
    photos: [{ id: 1, photo_type: 'intake', photo_type_label: 'Příjem', visibility_scope: 'service_private' }],
    capabilities: {
      labor: true,
      parts: true,
      time: true,
      photos: true,
      edit_items: true,
      quotes: true,
      invoices: true,
      complete: true,
      create_service_record: String(item.status || '').toLowerCase() === 'completed' && !(item as { service_record_id?: number | null }).service_record_id,
    },
    limited_notices: {},
    entity_type: 'work_order',
    id: item.id,
    title: item.title,
    customer_name: item.customer_name,
    owner_id: item.owner_id,
    vehicle_id: item.vehicle_id,
    vehicle_vin: item.vehicle_vin,
    vehicle_spz: item.vehicle_spz,
    vehicle_label: `${item.vehicle_vin} / ${item.vehicle_spz}`,
    source_label: 'Ruční zápis',
    status: item.status,
    technician_id: item.technician_id,
    description: item.description,
    disclosure: 'full',
    can_edit: true,
    can_create_work_order: false,
    audit_log: item.audit_log,
  });

  if (!preserveAuth) {
    await page.addInitScript(({ user, seedUser, forceRole }) => {
      localStorage.setItem('accessToken', 'test-token');
      localStorage.setItem('wasLoggedIn', 'true');
      localStorage.setItem('loginMode', 'service');
      if (seedUser) {
        localStorage.setItem('currentUser', JSON.stringify(user));
        (window as typeof window & { currentUser?: unknown }).currentUser = user;
      } else {
        localStorage.removeItem('currentUser');
        (window as typeof window & { currentUser?: unknown }).currentUser = undefined;
      }
      if (forceRole) {
        (window as typeof window & { isServiceWorkspaceRole?: () => boolean }).isServiceWorkspaceRole = () => true;
      }
    }, { user: serviceUser, seedUser: seedCurrentUser, forceRole: forceServiceWorkspaceRole });
  }

  await page.route('**/health', (route) => json(route, 200, { status: 'ok' }));
  await page.context().route('**/api/public/quote/quote-public-token', async (route) => {
    const quote = serviceQuotes.find((entry) => entry.public_quote_url?.includes('quote-public-token'));
    if (!quote) return json(route, 404, { detail: 'Not Found' });
    return json(route, 200, {
      quote_id: quote.id,
      vehicle_label: quote.vehicle_label,
      service_name: quote.service_name,
      service_ico: quote.service_ico,
      items: quote.items,
      labor_hours: quote.labor_hours,
      labor_rate: quote.labor_rate,
      total_price: quote.total_price,
      status: quote.status,
      status_label: quote.status_label,
      approved_at: (quote as { approved_at?: string }).approved_at || null,
      rejected_at: (quote as { rejected_at?: string }).rejected_at || null,
      decision_available: !['approved', 'rejected'].includes(String(quote.status || '').toLowerCase()),
      created_at: quote.created_at,
    });
  });
  await page.context().route('**/api/public/quote/quote-public-token/approve', async (route) => {
    const quote = serviceQuotes.find((entry) => entry.public_quote_url?.includes('quote-public-token'));
    if (!quote) return json(route, 404, { detail: 'Not Found' });
    quote.status = 'approved';
    quote.status_label = 'Schváleno';
    (quote as { approved_at?: string }).approved_at = '2026-04-15T14:00:00Z';
    const workOrder = workOrders.find((entry) => entry.id === quote.work_order_id);
    if (workOrder) workOrder.status = 'approved';
    return json(route, 200, { status: 'approved', message: 'Nabídka byla schválena.' });
  });
  await page.context().route('**/api/public/quote/quote-public-token-*/approve', async (route) => {
    const token = route.request().url().split('/').slice(-2, -1)[0] || '';
    const quote = serviceQuotes.find((entry) => entry.public_quote_url?.includes(token));
    if (!quote) return json(route, 404, { detail: 'Not Found' });
    quote.status = 'approved';
    quote.status_label = 'Schváleno';
    (quote as { approved_at?: string }).approved_at = '2026-04-15T14:00:00Z';
    const workOrder = workOrders.find((entry) => entry.id === quote.work_order_id);
    if (workOrder) workOrder.status = 'approved';
    return json(route, 200, { status: 'approved', message: 'Nabídka byla schválena.' });
  });
  await page.context().route('**/api/public/quote/quote-public-token-*', async (route) => {
    const token = route.request().url().split('/').pop() || '';
    const quote = serviceQuotes.find((entry) => entry.public_quote_url?.includes(token));
    if (!quote) return json(route, 404, { detail: 'Not Found' });
    return json(route, 200, {
      quote_id: quote.id,
      vehicle_label: quote.vehicle_label,
      service_name: quote.service_name,
      service_ico: quote.service_ico,
      items: quote.items,
      labor_hours: quote.labor_hours,
      labor_rate: quote.labor_rate,
      total_price: quote.total_price,
      status: quote.status,
      status_label: quote.status_label,
      approved_at: (quote as { approved_at?: string }).approved_at || null,
      rejected_at: (quote as { rejected_at?: string }).rejected_at || null,
      decision_available: !['approved', 'rejected'].includes(String(quote.status || '').toLowerCase()),
      created_at: quote.created_at,
    });
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    if (path === '/api/me') {
      if (preserveAuth) {
        return route.fallback();
      }
      const authorization = String(route.request().headers().authorization || '');
      if (!authorization.includes('test-token')) {
        return json(route, 200, { authenticated: false, app_name: 'Správa vozidel' });
      }
      return json(route, 200, serviceWorkspaceMe);
    }
    if (path === '/api/v1/system-notifications') return json(route, 200, { items: [] });
    if (path === '/api/v1/customers/me' || path === '/user/me') {
      if (preserveAuth) {
        return route.fallback();
      }
      return json(route, 200, serviceUser);
    }
    if (path.startsWith('/api/v1/license')) return json(route, 200, {});
    if (path === '/api/v1/services/my-contacts') return json(route, 200, { services: [] });
    if (path === '/api/v1/services/workspace/partner-public-profile') {
      return json(route, 200, {
        service_name: 'ToozServis',
        verified: true,
        public_profile_enabled: true,
      });
    }

    if (path === '/api/service/dashboard/summary') {
      return json(route, 200, buildSummary());
    }
    if (path === '/api/service/dashboard/overview') {
      return json(route, 200, {
        today_vehicles: 2,
        waiting_intake: 1,
        open_work_orders: workOrders.filter((item) => String(item.status || '').toLowerCase() !== 'completed').length,
        in_progress_work_orders: workOrders.filter((item) => ['approved', 'in_progress'].includes(String(item.status || '').toLowerCase())).length,
        waiting_approval: serviceQuotes.filter((item) => String(item.status || '').toLowerCase() === 'sent').length,
        monthly_invoice_total: 186400,
        monthly_invoice_count: 12,
        currency: 'CZK',
      });
    }
    if (path === '/api/service/dashboard/work-orders') {
      return json(route, 200, {
        items: workOrders.map((item) => ({
          id: item.id,
          vehicle_id: item.vehicle_id,
          vehicle_title: 'Škoda Octavia III',
          license_plate: item.vehicle_spz,
          vin_short: 'VIN...6789',
          customer_display: 'Linked C.',
          personal_data_hidden: false,
          status: item.status,
          status_label: item.status === 'approved' ? 'Práce probíhá' : item.status,
          technician_name: item.technician_name,
          work_time_minutes: 95,
          priority: 'normal',
          vin_record: true,
          owner_access_granted: true,
          audited: true,
          missing_photos: false,
          approval_required: false,
          detail_path: `/app/s/toozservis/work-orders/${item.id}`,
        })),
      });
    }
    if (path === '/api/service/dashboard/pending-authorizations') {
      return json(route, 200, { items: [] });
    }
    if (path === '/api/service/dashboard/today-reservations') {
      return json(route, 200, {
        items: [
          {
            id: 901,
            time: '09:00',
            title: 'Příjem vozidla',
            vehicle_title: 'Škoda Octavia',
            status: 'accepted',
            status_label: 'Přijato',
            detail_path: '/app/s/toozservis/reservations/901',
          },
        ],
      });
    }
    if (path === '/api/service/dashboard/risks') {
      return json(route, 200, {
        items: [
          {
            type: 'missing_photos',
            label: 'Chybí vstupní fotodokumentace u 1 vozidla',
            severity: 'warning',
            count: 1,
            target_path: '/app/s/toozservis/photos?filter=missing',
          },
        ],
      });
    }
    if (path === '/api/service/technicians/performance') {
      return json(route, 200, {
        items: [
          {
            technician_id: 9901,
            name: 'ToozServis',
            jobs_total: workOrders.filter((item) => String(item.status || '').toLowerCase() !== 'completed').length,
            awaiting_count: workOrders.filter((item) => String(item.status || '').toLowerCase() === 'awaiting_client_approval').length,
            overdue_count: 0,
          },
        ],
      });
    }
    if (path === '/api/service/dashboard/queue') {
      return json(route, 200, buildQueue());
    }
    if (path === '/api/service/quotes' && method === 'GET') {
      return json(route, 200, {
        items: serviceQuotes.map((entry) => ({
          quote_id: entry.id,
          status: entry.status,
          status_label: entry.status_label,
          total_price: entry.total_price,
          work_order_id: entry.work_order_id,
          vehicle_label: entry.vehicle_label,
          created_at: entry.created_at,
          pdf_url: (entry as { pdf_url?: string }).pdf_url,
          vehicle_document_id: (entry as { vehicle_document_id?: number }).vehicle_document_id,
          vehicle_document: (entry as { vehicle_document?: unknown }).vehicle_document,
        })),
      });
    }
    if (path === '/api/service/invoices' && method === 'GET') {
      return json(route, 200, {
        items: serviceInvoices.map(({ lines: _lines, ...invoice }) => invoice),
      });
    }
    if (path === '/api/service/invoices' && method === 'POST') {
      const body = route.request().postDataJSON() as {
        customer_id: number;
        vehicle_id?: number | null;
        currency?: string;
        due_at?: string | null;
        notes?: string | null;
        lines?: Array<{
          description?: string;
          quantity?: number;
          unit?: string;
          unit_price?: number;
          tax_rate?: number;
        }>;
      };
      const lines = (Array.isArray(body.lines) ? body.lines : []).map((line, index) => {
        const quantity = Number(line.quantity || 1);
        const unitPrice = Number(line.unit_price || 0);
        const taxRate = Number(line.tax_rate ?? 21);
        return {
          id: index + 1,
          description: String(line.description || 'Položka'),
          quantity,
          unit: String(line.unit || 'ks'),
          unit_price: unitPrice,
          tax_rate: taxRate,
          line_total: Math.round(quantity * unitPrice * (1 + taxRate / 100) * 100) / 100,
          sort_order: index,
        };
      });
      const total = Math.round(lines.reduce((sum, line) => sum + Number(line.line_total || 0), 0) * 100) / 100;
      const created = {
        id: nextInvoiceId++,
        tenant_id: 1,
        service_id: 9901,
        customer_id: Number(body.customer_id || 101),
        vehicle_id: Number(body.vehicle_id || 301),
        invoice_number: null as string | null,
        status: 'draft',
        status_label: 'Koncept',
        subtotal: total,
        tax_total: 0,
        total,
        currency: String(body.currency || 'CZK'),
        issued_at: null as string | null,
        due_at: body.due_at || null,
        cancelled_at: null as string | null,
        notes: body.notes || null,
        customer_label: 'Linked Customer',
        vehicle_label: 'Octavia',
        created_at: '2026-04-16T11:00:00Z',
        updated_at: '2026-04-16T11:00:00Z',
        lines,
      };
      serviceInvoices.unshift(created);
      attachInvoicePlatformDoc(created);
      return json(route, 201, created);
    }
    if (/^\/api\/service\/invoices\/\d+$/.test(path) && method === 'GET') {
      const id = Number(path.split('/').pop());
      const invoice = serviceInvoices.find((entry) => entry.id === id);
      return json(route, invoice ? 200 : 404, invoice || { detail: 'Not Found' });
    }
    if (/^\/api\/service\/invoices\/\d+$/.test(path) && method === 'PUT') {
      const id = Number(path.split('/').pop());
      const invoice = serviceInvoices.find((entry) => entry.id === id);
      if (!invoice) return json(route, 404, { detail: 'Not Found' });
      const body = route.request().postDataJSON() as {
        customer_id?: number;
        vehicle_id?: number | null;
        currency?: string;
        due_at?: string | null;
        notes?: string | null;
        lines?: Array<{
          description?: string;
          quantity?: number;
          unit?: string;
          unit_price?: number;
          tax_rate?: number;
        }>;
      };
      if (body.customer_id) invoice.customer_id = Number(body.customer_id);
      if (Object.prototype.hasOwnProperty.call(body, 'vehicle_id')) invoice.vehicle_id = Number(body.vehicle_id || 0);
      if (body.currency) invoice.currency = String(body.currency);
      if (Object.prototype.hasOwnProperty.call(body, 'due_at')) invoice.due_at = body.due_at || null;
      if (Object.prototype.hasOwnProperty.call(body, 'notes')) invoice.notes = body.notes || null;
      if (Array.isArray(body.lines)) {
        invoice.lines = body.lines.map((line, index) => {
          const quantity = Number(line.quantity || 1);
          const unitPrice = Number(line.unit_price || 0);
          const taxRate = Number(line.tax_rate ?? 21);
          return {
            id: index + 1,
            description: String(line.description || 'Položka'),
            quantity,
            unit: String(line.unit || 'ks'),
            unit_price: unitPrice,
            tax_rate: taxRate,
            line_total: Math.round(quantity * unitPrice * (1 + taxRate / 100) * 100) / 100,
            sort_order: index,
          };
        });
        invoice.total = Math.round(invoice.lines.reduce((sum, line) => sum + Number(line.line_total || 0), 0) * 100) / 100;
        invoice.subtotal = invoice.total;
      }
      invoice.updated_at = '2026-04-16T11:30:00Z';
      return json(route, 200, invoice);
    }
    if (/^\/api\/service\/invoices\/\d+\/issue$/.test(path) && method === 'POST') {
      const id = Number(path.split('/').slice(-2, -1)[0]);
      const invoice = serviceInvoices.find((entry) => entry.id === id);
      if (!invoice) return json(route, 404, { detail: 'Not Found' });
      invoice.status = 'issued';
      invoice.status_label = 'Vystaveno';
      invoice.invoice_number = `FV-2026-${String(id).padStart(4, '0')}`;
      invoice.issued_at = '2026-04-16T12:00:00Z';
      invoice.updated_at = '2026-04-16T12:00:00Z';
      attachInvoicePlatformDoc(invoice);
      return json(route, 200, invoice);
    }
    if (/^\/api\/service\/invoices\/\d+\/cancel$/.test(path) && method === 'POST') {
      const id = Number(path.split('/').slice(-2, -1)[0]);
      const invoice = serviceInvoices.find((entry) => entry.id === id);
      if (!invoice) return json(route, 404, { detail: 'Not Found' });
      invoice.status = 'cancelled';
      invoice.status_label = 'Zrušeno';
      invoice.cancelled_at = '2026-04-16T12:30:00Z';
      invoice.updated_at = '2026-04-16T12:30:00Z';
      return json(route, 200, invoice);
    }
    if (/^\/api\/service\/invoices\/\d+\/pdf$/.test(path) && method === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/pdf',
        body: Buffer.from('%PDF-1.4 mock platform invoice pdf Document Platform C1.1'),
      });
    }
    if (/^\/api\/v1\/vehicles\/\d+\/documents$/.test(path) && method === 'GET') {
      const vehicleId = Number(path.split('/')[4]);
      const invoiceDocs = serviceInvoices
        .filter((inv) => Number(inv.vehicle_id) === vehicleId && inv.vehicle_document)
        .map((inv) => inv.vehicle_document);
      const quoteDocs = serviceQuotes
        .filter((quote) => Number(quote.vehicle_id) === vehicleId && (quote as { vehicle_document?: unknown }).vehicle_document)
        .map((quote) => (quote as { vehicle_document: unknown }).vehicle_document);
      const sheetDocs = workOrders
        .filter((wo) => Number(wo.vehicle_id) === vehicleId && (wo as { work_order_sheet_document?: unknown }).work_order_sheet_document)
        .map((wo) => (wo as { work_order_sheet_document: unknown }).work_order_sheet_document);
      const intakeDocs = workOrders
        .filter((wo) => Number(wo.vehicle_id) === vehicleId && (wo as { intake_protocol_document?: unknown }).intake_protocol_document)
        .map((wo) => (wo as { intake_protocol_document: unknown }).intake_protocol_document);
      const reportDocs = workOrders
        .filter((wo) => Number(wo.vehicle_id) === vehicleId && (wo as { service_report_document?: unknown }).service_report_document)
        .map((wo) => (wo as { service_report_document: unknown }).service_report_document);
      const privateServiceReport = buildServiceReportVehicleDocument(599, vehicleId, 'completed', 'service_private');
      return json(route, 200, [...invoiceDocs, ...quoteDocs, ...sheetDocs, ...intakeDocs, ...reportDocs, privateServiceReport]);
    }
    if (/^\/api\/v1\/vehicles\/\d+\/documents\/\d+\/file$/.test(path) && method === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/pdf',
        body: Buffer.from('%PDF-1.4 mock platform invoice file'),
      });
    }
    if (/^\/api\/service\/work-orders\/?$/.test(path) && method === 'GET') {
      return json(route, 200, {
        items: workOrders.map((item) => ({
          id: item.id,
          title: item.title,
          customer_name: item.customer_name,
          owner_id: item.owner_id,
          vehicle_id: item.vehicle_id,
          vehicle_vin: item.vehicle_vin,
          vehicle_spz: item.vehicle_spz,
          due_date: item.due_date,
          status: item.status,
          source_type: item.source_type,
          technician_name: item.technician_name,
        })),
      });
    }
    if (/^\/api\/service\/work-orders\/?$/.test(path) && method === 'POST') {
      const body = route.request().postDataJSON() as {
        owner_id: number;
        vehicle_id: number;
        technician_id: number;
        title: string;
        description?: string;
        due_date?: string;
        status?: string;
        source_type?: string;
        source_intake_id?: number;
      };
      const shouldExerciseDuplicateGuard = /duplicit/i.test(String(body.title || ''));
      const duplicate = shouldExerciseDuplicateGuard
        ? workOrders.find((item) => (
            item.owner_id === body.owner_id
            && item.vehicle_id === body.vehicle_id
            && String(item.status || '').toLowerCase() !== 'completed'
          ))
        : null;
      if (duplicate) {
        return json(route, 409, {
          detail: {
            code: 'duplicate_work_order',
            message: 'Na stejné vozidlo už existuje rozpracovaná zakázka. Otevřete existující záznam místo vytváření duplicity.',
            existing_work_order_id: duplicate.id,
            existing_work_order_title: duplicate.title,
            existing_work_order_status: duplicate.status,
          },
        });
      }
      const created = {
        id: nextWorkOrderId++,
        title: body.title,
        customer_name: 'Linked Customer',
        owner_id: body.owner_id,
        vehicle_id: body.vehicle_id,
        vehicle_vin: 'VINLINKED123456789',
        vehicle_spz: '1AB2345',
        due_date: body.due_date || '2026-04-13',
        status: body.status || 'awaiting_client_approval',
        source_type: body.source_type || 'manual',
        source_intake_id: body.source_intake_id || null,
        technician_id: body.technician_id || 9901,
        technician_name: 'ToozServis',
        description: body.description || 'Zakázka vytvořená testem',
        audit_log: [{ id: 2, action: 'create', created_at: '2026-04-13T10:00:00Z' }],
      };
      workOrders.unshift(created);
      attachWorkOrderSheetPlatformDoc(created as unknown as Record<string, unknown>);
      attachIntakeProtocolPlatformDoc(created as unknown as Record<string, unknown>);
      attachServiceReportPlatformDoc(created as unknown as Record<string, unknown>);
      return json(route, 200, serializeWorkOrderDetail(created));
    }
    if (/^\/api\/service\/work-orders\/\d+$/.test(path) && method === 'GET') {
      const workOrderId = Number(path.split('/').pop());
      const item = workOrders.find((entry) => entry.id === workOrderId);
      return json(route, item ? 200 : 404, item ? serializeWorkOrderDetail(item) : { detail: 'Not Found' });
    }
    if (/^\/api\/service\/work-orders\/\d+\/sheet\.pdf$/.test(path) && method === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/pdf',
        body: Buffer.from('%PDF-1.4 mock platform work order sheet Document Platform C1.3 ZAKAZKOVY LIST'),
      });
    }
    if (/^\/api\/service\/work-orders\/\d+\/document-card$/.test(path) && method === 'GET') {
      const workOrderId = Number(path.split('/').slice(-2, -1)[0]);
      const item = workOrders.find((entry) => entry.id === workOrderId) as Record<string, unknown> | undefined;
      const card = item?.work_order_sheet_document;
      return json(route, card ? 200 : 404, card || { detail: 'Not Found' });
    }
    if (/^\/api\/service\/intakes\/\d+\/protocol\.pdf$/.test(path) && method === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/pdf',
        body: Buffer.from('%PDF-1.4 mock platform intake protocol Document Platform C1.4 PRIJMOVY PROTOKOL'),
      });
    }
    if (/^\/api\/service\/intakes\/\d+\/document-card$/.test(path) && method === 'GET') {
      const intakeId = Number(path.split('/').slice(-2, -1)[0]);
      const item = workOrders.find((entry) => Number((entry as { source_intake_id?: number }).source_intake_id) === intakeId) as Record<string, unknown> | undefined;
      const card = item?.intake_protocol_document || buildIntakeProtocolVehicleDocument(intakeId);
      return json(route, 200, card);
    }
    if (/^\/api\/service\/work-orders\/\d+\/service-record$/.test(path) && method === 'POST') {
      const workOrderId = Number(path.split('/').slice(-2, -1)[0]);
      const item = workOrders.find((entry) => entry.id === workOrderId);
      if (!item) return json(route, 404, { detail: 'Not Found' });
      const recordId = nextRecordId++;
      (item as { service_record_id?: number }).service_record_id = recordId;
      attachServiceReportPlatformDoc(item as unknown as Record<string, unknown>);
      return json(route, 200, {
        service_record_id: recordId,
        vehicle_id: item.vehicle_id,
        work_order_id: workOrderId,
        visibility_scope: 'owner_visible_no_prices',
        record_status: 'published',
        service_report_document: (item as { service_report_document?: unknown }).service_report_document,
        service_report_pdf_url: `/api/service/service-records/${recordId}/report.pdf`,
      });
    }
    if (/^\/api\/service\/service-records\/\d+\/report\.pdf$/.test(path) && method === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/pdf',
        body: Buffer.from('%PDF-1.4 mock platform service report Document Platform C1.5 SERVISNI ZPRAVA'),
      });
    }
    if (/^\/api\/service\/service-records\/\d+\/document-card$/.test(path) && method === 'GET') {
      const recordId = Number(path.split('/').slice(-2, -1)[0]);
      const item = workOrders.find((entry) => Number((entry as { service_record_id?: number | null }).service_record_id) === recordId) as Record<string, unknown> | undefined;
      const card = item?.service_report_document || buildServiceReportVehicleDocument(recordId);
      return json(route, 200, card);
    }
    if (/^\/api\/service\/work-orders\/\d+$/.test(path) && method === 'PUT') {
      const workOrderId = Number(path.split('/').pop());
      const body = route.request().postDataJSON() as {
        status?: string;
        due_date?: string;
        technician_id?: number;
        description?: string | null;
      };
      const item = workOrders.find((entry) => entry.id === workOrderId);
      if (!item) return json(route, 404, { detail: 'Not Found' });
      if (body.status) item.status = body.status;
      if (Object.prototype.hasOwnProperty.call(body, 'due_date')) item.due_date = body.due_date || item.due_date;
      if (Object.prototype.hasOwnProperty.call(body, 'description')) item.description = body.description || '';
      if (body.technician_id) item.technician_id = body.technician_id;
      item.audit_log = [
        ...(item.audit_log || []),
        { id: (item.audit_log || []).length + 1, action: 'update', created_at: '2026-04-13T11:00:00Z' },
      ];
      return json(route, 200, serializeWorkOrderDetail(item));
    }

    if (path === '/api/v1/services/workspace/customers' && method === 'GET') {
      const items = [
        {
          customer_id: 101,
          name: 'Linked Customer',
          email: 'linked@example.com',
          phone: '+420111222333',
          vehicles_count: 1,
          shared_vehicles_count: 1,
          last_service_date: '2026-04-12T09:00:00Z',
        },
      ];
      if (linkedCustomer) {
        items.push({
          customer_id: 201,
          name: 'Klient Vyhledany',
          email: 'vyhledany@example.com',
          phone: '+420999888777',
          vehicles_count: 1,
          shared_vehicles_count: 1,
          last_service_date: '2026-04-12T08:00:00Z',
        });
      }
      return json(route, 200, items);
    }
    if (path === '/api/v1/services/workspace/customers/search') {
      return json(route, 200, {
        query: 'Vyhledany',
        result_count: 1,
        has_multiple_matches: false,
        items: [{
          customer_id: 201,
          name: 'Klient Vyhledany',
          email_masked: 'vy***@example.com',
          phone_masked: '***777',
          role: 'user',
          already_linked: linkedCustomer,
          can_link: !linkedCustomer,
          can_open_detail: true,
          can_send_invite: !linkedCustomer,
          status: linkedCustomer ? 'linked' : 'not_linked',
          match_score: 0.88,
          match_type: 'fuzzy',
        }],
      });
    }
    if (path === '/api/v1/services/workspace/customers/101/detail') {
      return json(route, 200, {
        entity_type: 'customer',
        entity_id: 101,
        customer_id: 101,
        name: 'Linked Customer',
        email: 'linked@example.com',
        phone: '+420111222333',
        disclosure: 'full',
        status: 'linked',
        can_open_detail: true,
        can_edit: false,
        can_link: false,
        can_create_work_order: true,
        vehicles: [{
          vehicle_id: 301,
          label: 'Octavia',
          plate: '1AB2345',
          vin: 'VINLINKED123456789',
          can_open_detail: true,
          can_create_work_order: true,
        }],
      });
    }
    if (path === '/api/v1/services/workspace/customers/201/detail') {
      return json(route, 200, {
        entity_type: 'customer',
        entity_id: 201,
        customer_id: 201,
        name: 'Klient Vyhledany',
        email: 'vyhledany@example.com',
        phone: '+420999888777',
        disclosure: 'full',
        status: linkedCustomer ? 'linked' : 'not_linked',
        can_open_detail: true,
        can_edit: false,
        can_link: !linkedCustomer,
        can_create_work_order: linkedCustomer,
        vehicles: linkedCustomer ? [{
          vehicle_id: 302,
          label: 'Superb',
          plate: '2BC3456',
          vin: 'VINVYHLEDANY123456',
          can_open_detail: true,
          can_create_work_order: true,
        }] : [],
      });
    }
    if (path === '/api/v1/services/workspace/customers/201/link' && method === 'POST') {
      linkedCustomer = true;
      return json(route, 200, {
        linked: true,
        created: true,
        message: 'Klient byl úspěšně propojen.',
        customer_id: 201,
      });
    }
    if (path === '/api/v1/services/workspace/invitations/send' && method === 'POST') {
      return json(route, 200, { email_sent: true, message: 'Pozvánka byla odeslána.' });
    }
    if (path === '/api/v1/services/workspace/customers/101/vehicles') {
      return json(route, 200, [
        { id: 301, nickname: 'Octavia', plate: '1AB2345', vin: 'VINLINKED123456789', year: 2022, stk_valid_until: '2027-04-12', is_shared: true },
      ]);
    }
    if (path === '/api/v1/services/workspace/customers/201/vehicles') {
      return json(route, 200, [
        { id: 302, nickname: 'Superb', plate: '2BC3456', vin: 'VINVYHLEDANY123456', year: 2023, stk_valid_until: '2027-05-12', is_shared: true },
      ]);
    }
    if (/^\/api\/v1\/services\/workspace\/customers\/\d+\/vehicles$/.test(path) && method === 'POST') {
      return json(route, 200, { id: 450, message: 'Vozidlo bylo přidáno ke klientovi a zpřístupněno servisu.' });
    }
    if (path === '/api/v1/services/workspace/vehicle-lookup' && method === 'POST') {
      const request = route.request().postDataJSON() as { query?: string };
      if (String(request?.query || '').trim().toUpperCase() === 'NOTFOUND123') {
        return json(route, 200, { query: 'NOTFOUND123', result_count: 0, candidates: [] });
      }
      return json(route, 200, {
        query: String(request?.query || ''),
        result_count: 1,
        candidates: [{
          id: 'vehicle-301',
          vehicle_id: 301,
          owner_customer_id: 101,
          nickname: 'Octavia',
          brand: 'Skoda',
          model: 'Octavia',
          plate_masked: '1AB2345',
          vin_masked: 'VIN*****6789',
          city: 'Praha',
          owner_label: null,
          status: 'already_approved',
          can_request_access: false,
          can_open_detail: true,
          can_create_work_order: true,
          match_score: 1,
          match_type: 'spz',
        }],
      });
    }
    if (path === '/api/v1/services/workspace/access-requests' && method === 'POST') {
      return json(route, 200, { created: true, status: 'pending', message: 'Žádost o přístup byla uložena.' });
    }
    if (path === '/api/v1/services/workspace/approved-vehicles') {
      return json(route, 200, {
        items: [
          {
            id: 301,
            nickname: 'Octavia',
            plate: '1AB2345',
            vin: 'VINLINKED123456789',
            owner_id: 101,
            owner_name: 'Linked Customer',
            next_stk: '2027-04-12',
            is_shared: true,
          },
        ],
      });
    }
    if (path === '/api/v1/services/workspace/vehicles/301/detail') {
      return json(route, 200, {
        entity_type: 'vehicle',
        entity_id: 301,
        vehicle_id: 301,
        nickname: 'Octavia',
        plate: '1AB2345',
        vin: 'VINLINKED123456789',
        owner_customer_id: 101,
        owner_name: 'Linked Customer',
        disclosure: 'full',
        status: 'approved',
        can_open_detail: true,
        can_create_work_order: true,
        has_qr_token: true,
        qr_public_mode: qrToken.public_mode,
        qr_last_access_at: qrToken.last_access_at,
        records_count: serviceRecords.length,
      });
    }
    if (path === '/api/service/vehicles/301/quotes' && method === 'GET') {
      return json(route, 200, {
        items: serviceQuotes.filter((entry) => entry.vehicle_id === 301).map((entry) => ({
          quote_id: entry.id,
          status: entry.status,
          status_label: entry.status_label,
          total_price: entry.total_price,
          approved_at: (entry as { approved_at?: string }).approved_at || null,
          rejected_at: (entry as { rejected_at?: string }).rejected_at || null,
          created_at: entry.created_at,
          updated_at: entry.updated_at,
          service_record_id: entry.service_record_id,
          work_order_id: entry.work_order_id,
          pdf_url: entry.pdf_url,
          public_quote_url: entry.public_quote_url,
          consistency_note: null,
        })),
      });
    }
    if (path === '/api/v1/vehicles/301/records' && method === 'GET') {
      return json(route, 200, serviceRecords);
    }
    if (/^\/api\/v1\/vehicles\/301\/records\/\d+$/.test(path) && method === 'GET') {
      const recordId = Number(path.split('/').pop());
      const item = serviceRecords.find((entry) => entry.id === recordId);
      return json(route, item ? 200 : 404, item || { detail: 'Not Found' });
    }
    if (path === '/api/v1/vehicles/301/records/attachments/upload' && method === 'POST') {
      const body = route.request().postDataJSON() as { file_name?: string; file_mime_type?: string; file_content_base64?: string };
      return json(route, 200, {
        file_name: body.file_name || 'photo.jpg',
        mime_type: body.file_mime_type || 'image/jpeg',
        file_size: String(body.file_content_base64 || '').length,
        storage_key: `uploads/${body.file_name || 'photo.jpg'}`,
        download_url: `/files/${encodeURIComponent(body.file_name || 'photo.jpg')}`,
      });
    }
    if (path === '/api/v1/vehicles/301/records' && method === 'POST') {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      const created = {
        id: nextRecordId++,
        vehicle_id: 301,
        performed_at: String(body.performed_at || '2026-04-15T08:00:00Z'),
        mileage: Number(body.mileage || 0),
        description: String(body.description || ''),
        price: Number(body.price || 0),
        total_price: Number(body.total_price || body.price || 0),
        note: String(body.note || ''),
        notes_customer_visible: String(body.notes_customer_visible || ''),
        category: String(body.category || 'JINE'),
        record_status: String(body.record_status || 'draft'),
        attachments: String(body.attachments || '[]'),
        created_by_service_customer_id: 9901,
      };
      serviceRecords.unshift(created);
      return json(route, 200, created);
    }
    if (/^\/api\/v1\/vehicles\/301\/records\/\d+$/.test(path) && method === 'PUT') {
      const recordId = Number(path.split('/').pop());
      const body = route.request().postDataJSON() as Record<string, unknown>;
      const item = serviceRecords.find((entry) => entry.id === recordId);
      if (!item) return json(route, 404, { detail: 'Not Found' });
      Object.assign(item, {
        performed_at: body.performed_at ?? item.performed_at,
        mileage: body.mileage ?? item.mileage,
        description: body.description ?? item.description,
        price: body.price ?? item.price,
        total_price: body.total_price ?? item.total_price,
        note: body.note ?? item.note,
        notes_customer_visible: body.notes_customer_visible ?? item.notes_customer_visible,
        category: body.category ?? item.category,
        record_status: body.record_status ?? item.record_status,
        attachments: body.attachments ?? item.attachments,
      });
      return json(route, 200, item);
    }
    if (/^\/api\/service\/quotes\/from-record\/\d+$/.test(path) && method === 'POST') {
      const recordId = Number(path.split('/').pop());
      const existing = serviceQuotes.find((entry) => entry.service_record_id === recordId);
      if (existing) return json(route, 200, existing);
      const record = serviceRecords.find((entry) => entry.id === recordId);
      if (!record) return json(route, 404, { detail: 'Not Found' });
      const created = {
        id: nextQuoteId++,
        vehicle_id: 301,
        customer_id: 101,
        service_id: 9901,
        work_order_id: 501,
        service_record_id: recordId,
        items: [
          { name: String(record.description || 'Servisní práce'), quantity: 1, unit_price: Number(record.total_price || record.price || 0), total_price: Number(record.total_price || record.price || 0) },
        ],
        labor_hours: 1.0,
        labor_rate: 890,
        total_price: Number(record.total_price || record.price || 0),
        status: 'draft',
        status_label: 'Koncept',
        vehicle_label: 'Skoda Octavia',
        service_name: 'ToozServis',
        service_ico: '12345678',
        pdf_url: `/api/service/quotes/${nextQuoteId - 1}/pdf`,
        public_quote_url: `http://127.0.0.1:8000/web/public-quote.html?token=quote-public-token-${nextQuoteId - 1}`,
        customer_email: 'linked@example.com',
        customer_phone: '+420111222333',
        created_at: '2026-04-15T12:00:00Z',
        updated_at: '2026-04-15T12:00:00Z',
      };
      if (record) (record as typeof serviceRecords[number] & { quote_id?: number }).quote_id = created.id;
      serviceQuotes.unshift(created);
      attachQuotePlatformDoc(created as unknown as Record<string, unknown>);
      return json(route, 200, created);
    }
    if (/^\/api\/service\/quotes\/\d+$/.test(path) && method === 'GET') {
      const quoteId = Number(path.split('/').pop());
      const item = serviceQuotes.find((entry) => entry.id === quoteId);
      return json(route, item ? 200 : 404, item || { detail: 'Not Found' });
    }
    if (/^\/api\/service\/quotes\/\d+$/.test(path) && method === 'PUT') {
      const quoteId = Number(path.split('/').pop());
      const body = route.request().postDataJSON() as Record<string, unknown>;
      const item = serviceQuotes.find((entry) => entry.id === quoteId);
      if (!item) return json(route, 404, { detail: 'Not Found' });
      if (Array.isArray(body.items)) item.items = body.items as typeof item.items;
      if (Object.prototype.hasOwnProperty.call(body, 'labor_hours')) item.labor_hours = Number(body.labor_hours || 0);
      if (Object.prototype.hasOwnProperty.call(body, 'labor_rate')) item.labor_rate = Number(body.labor_rate || 0);
      if (Object.prototype.hasOwnProperty.call(body, 'total_price')) item.total_price = Number(body.total_price || 0);
      if (body.status) {
        item.status = String(body.status);
        item.status_label = item.status === 'sent' ? 'Odesláno' : item.status === 'approved' ? 'Schváleno' : item.status === 'rejected' ? 'Zamítnuto' : 'Koncept';
        if (item.status === 'approved') {
          (item as { approved_at?: string }).approved_at = '2026-04-15T13:00:00Z';
          const workOrder = workOrders.find((entry) => entry.id === item.work_order_id);
          if (workOrder) workOrder.status = 'approved';
        }
        if (item.status === 'rejected') {
          (item as { rejected_at?: string }).rejected_at = '2026-04-15T13:05:00Z';
        }
      }
      item.updated_at = '2026-04-15T12:30:00Z';
      attachQuotePlatformDoc(item as unknown as Record<string, unknown>);
      return json(route, 200, item);
    }
    if (/^\/api\/service\/quotes\/\d+\/pdf$/.test(path) && method === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/pdf',
        body: Buffer.from('%PDF-1.4 mock platform quote pdf Document Platform C1.2'),
      });
    }
    if (/^\/api\/service\/invoices\/from-quote\/\d+$/.test(path) && method === 'POST') {
      const quoteId = Number(path.split('/').slice(-1)[0]);
      const quote = serviceQuotes.find((entry) => entry.id === quoteId);
      if (!quote) return json(route, 404, { detail: 'Not Found' });
      const created = {
        id: nextInvoiceId++,
        tenant_id: 1,
        service_id: 9901,
        customer_id: quote.customer_id,
        vehicle_id: quote.vehicle_id,
        invoice_number: null as string | null,
        status: 'draft',
        status_label: 'Koncept',
        subtotal: quote.total_price,
        tax_total: 0,
        total: quote.total_price,
        currency: 'CZK',
        work_order_id: quote.work_order_id,
        customer_label: 'Linked Customer',
        vehicle_label: quote.vehicle_label,
        created_at: '2026-04-16T12:00:00Z',
        updated_at: '2026-04-16T12:00:00Z',
        lines: [],
      };
      serviceInvoices.unshift(created);
      attachInvoicePlatformDoc(created);
      return json(route, 201, created);
    }
    if (path === '/api/v1/services/workspace/vehicles/301/qr' && method === 'GET') {
      return json(route, 200, qrToken);
    }
    if (path === '/api/v1/services/workspace/vehicles/301/qr' && method === 'POST') {
      qrToken = {
        ...qrToken,
        issued_at: '2026-04-15T11:00:00Z',
        last_access_at: null,
      };
      return json(route, 200, qrToken);
    }
    if (path === '/api/v1/services/workspace/vehicles/301/qr/regenerate' && method === 'POST') {
      qrToken = {
        ...qrToken,
        token: 'regenerated-public-token',
        public_history_url: 'http://127.0.0.1:8000/web/public-vehicle-history.html?token=regenerated-public-token',
        issued_at: '2026-04-15T12:00:00Z',
        last_access_at: null,
      };
      return json(route, 200, qrToken);
    }
    if (path === '/api/v1/reservations/service') {
      return json(route, 200, [
        { id: 901, customer_name: 'Linked Customer', vehicle_name: 'Octavia', scheduled_for: '2026-04-12T09:00:00Z', status: 'pending', note: 'Příjem vozidla' },
      ]);
    }
    if (path === '/api/v1/services/workspace/reservations/901/detail') {
      return json(route, 200, {
        entity_type: 'reservation',
        entity_id: 901,
        id: 901,
        customer_id: 101,
        customer_name: 'Linked Customer',
        vehicle_id: 301,
        vehicle_name: 'Octavia',
        disclosure: 'full',
        status: 'approved',
        can_open_detail: true,
        can_edit: true,
        can_create_work_order: true,
        scheduled_for: '2026-04-12T09:00:00Z',
        note: 'Příjem vozidla',
      });
    }
    if (path === '/api/v1/services/workspace/reminders') {
      return json(route, 200, [
        { id: 801, customer_name: 'Linked Customer', customer_email: 'linked@example.com', vehicle_label: 'Octavia', text: 'Kontrola STK', due_date: '2026-04-20', is_completed: false },
      ]);
    }
    if (path === '/api/v1/services/workspace/reminders/801/detail') {
      return json(route, 200, {
        entity_type: 'reminder',
        entity_id: 801,
        id: 801,
        customer_id: 101,
        customer_name: 'Linked Customer',
        vehicle_id: 301,
        vehicle_label: 'Octavia',
        disclosure: 'full',
        status: 'scheduled',
        can_open_detail: true,
        can_edit: true,
        can_create_work_order: true,
        text: 'Kontrola STK',
        due_date: '2026-04-20',
        is_completed: false,
      });
    }
    if (path === '/api/v1/services/workspace/documents') {
      return json(route, 200, [
        {
          id: 701,
          document_number: 'FV-001',
          supplier_name: 'Dodavatel',
          customer_name: 'Linked Customer',
          processing_status: 'processed',
          created_at: '2026-04-12T08:00:00Z',
          auto_created_service_record_id: 601,
          vehicle_id: 301,
        },
      ]);
    }
    if (path === '/api/v1/services/workspace/documents/701/detail') {
      return json(route, 200, {
        entity_type: 'document',
        entity_id: 701,
        id: 701,
        customer_id: 101,
        customer_name: 'Linked Customer',
        vehicle_id: 301,
        document_number: 'FV-001',
        processing_status: 'processed',
        disclosure: 'full',
        status: 'processed',
        can_open_detail: true,
        can_edit: false,
        can_create_work_order: true,
        auto_created_service_record_id: 601,
      });
    }

    return route.fallback();
  });
}

export async function installQuotePlatformMocks(page: Page): Promise<void> {
  await installServiceShellMocks(page, { preserveAuth: true });
}

export async function bootstrapAuthenticatedQuotePlatformShell(page: Page): Promise<string> {
  await installQuotePlatformMocks(page);
  await loginServiceUser(page);
  const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
  const slug = slugMatch?.[1] || 'e2e-fixed-service';
  await page.goto(`/web/app/s/${slug}/billing`, { waitUntil: 'domcontentloaded' });
  await waitForServiceShellReady(page);
  return slug;
}

export async function bootstrapAuthenticatedWorkOrderShell(page: Page): Promise<string> {
  await installQuotePlatformMocks(page);
  await loginServiceUser(page);
  const slugMatch = page.url().match(/\/app\/s\/([^/]+)\//);
  const slug = slugMatch?.[1] || 'e2e-fixed-service';
  await page.goto(`/web/app/s/${slug}/work-orders`, { waitUntil: 'domcontentloaded' });
  await waitForServiceShellReady(page);
  return slug;
}

export async function bootstrapMockServiceShell(
  page: Page,
  options: { section?: string; requireShell?: boolean } = {},
): Promise<void> {
  await installServiceShellMocks(page);
  await page.goto('/web/index.html', { waitUntil: 'domcontentloaded' });
  if (options.requireShell !== false) {
    await page.waitForFunction(() => {
      const hasRoot = Boolean(
        document.querySelector('[data-service-shell="root"]')
        || document.querySelector('[data-testid="service-shell-root"]'),
      );
      const shell = (window as typeof window & {
        serviceShell?: { openBillingQuoteDetail?: (quoteId: number) => void };
      }).serviceShell;
      return hasRoot && typeof shell?.openBillingQuoteDetail === 'function';
    }, { timeout: 30000 });
  }
}

