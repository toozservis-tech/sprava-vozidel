export type UiAuditActionType =
  | 'navigate'
  | 'open_modal'
  | 'close_modal'
  | 'open_dropdown'
  | 'filter'
  | 'detail'
  | 'download'
  | 'blocked_destructive'
  | 'unknown';

export type UiAuditVerdict = 'PASS' | 'FAIL' | 'WARN' | 'BLOCKED';

export type SafetyClassification = 'SAFE' | 'WARN' | 'BLOCKED';

export type GdprScope = 'account' | 'vehicle' | 'service_access' | 'public' | 'admin';

export type ExpectedTarget =
  | { type: 'route'; route: string }
  | { type: 'modal'; modal_testid: string }
  | { type: 'panel'; panel_testid: string }
  | { type: 'blocked'; reason: string };

export type ExpectedClickRule = {
  source_section: string;
  element_text: string;
  data_testid?: string;
  allowed_actions: string[];
  expected_target: ExpectedTarget;
  destructive: boolean;
  requires_confirmation: boolean;
  gdpr_scope: GdprScope;
};

export type UiAuditStep = {
  run_id: string;
  step_index: number;

  before_url: string;
  after_url: string;

  section_guess: string;
  element_text: string;
  element_role: string;
  selector: string | null;
  data_testid: string | null;

  discovery_phase: 'top-level' | 'dynamic-child';
  parent_element: string | null;
  parent_panel: string | null;
  isolated_child_run: boolean;
  parent_panel_reopened: boolean;

  action_type: UiAuditActionType;
  safety_class: SafetyClassification;

  expected_result: {
    expected_url?: string;
    expected_view?: string;
    expected_modal?: string;
    expected_api?: string[];
  };

  actual_result: {
    url_changed: boolean;
    modal_opened: boolean;
    view_changed: boolean;
    api_calls: string[];
    http_errors: Array<{ url: string; status: number }>;
    console_errors: string[];
    screenshot_before: string;
    screenshot_after: string;
    trace_path: string;
  };

  verdict: UiAuditVerdict;
  reason: string;
  recommended_fix: string | null;

  gdpr: {
    owner_data_visible: boolean;
    vehicle_data_visible: boolean;
    vin_visible: boolean;
    spz_visible: boolean;
    public_context: boolean;
    violation: boolean;
    note: string;
  };
};

export type ClickableElementDescriptor = {
  index: number;
  text: string;
  role: string;
  tagName: string;
  selector: string | null;
  dataTestId: string | null;
  dataUappAction: string | null;
  href: string | null;
  type: string | null;
  sectionGuess: string;
  discoveryPhase?: 'top-level' | 'dynamic-child';
  parentElement?: string | null;
  parentPanel?: string | null;
  onclickSnippet?: string | null;
  isDangerAction?: boolean;
};

export type PageObservation = {
  url: string;
  activeTab: string | null;
  activeView: string | null;
  openModals: string[];
  openPanels: string[];
  accountSettingsVisible: boolean;
  bodyTextSample: string;
};

export type UiAuditRunSummary = {
  run_id: string;
  started_at: string;
  finished_at: string;
  scope: string;
  base_url: string;
  overall_verdict: UiAuditVerdict;
  total_elements: number;
  safe_count: number;
  warn_count: number;
  blocked_count: number;
  pass_count: number;
  fail_count: number;
  warn_verdict_count: number;
  blocked_verdict_count: number;
  fail_redirect_count: number;
  dynamic_panels: Array<{
    panel_id: string;
    panel_label: string;
    parent_element: string;
    parent_panel: string | null;
    child_count: number;
    child_testids: string[];
  }>;
  profile_panel_child_count: number;
  steps: UiAuditStep[];
};

export type AiReviewInput = {
  step: UiAuditStep;
  screenshotBeforePath?: string;
  screenshotAfterPath?: string;
};

export type AiReviewResult = {
  enabled: boolean;
  summary: string | null;
  semantic_match: boolean | null;
  design_ok: boolean | null;
  gdpr_risk: string | null;
  suggested_target: string | null;
};
