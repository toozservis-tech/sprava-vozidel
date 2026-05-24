import fs from 'node:fs';
import path from 'node:path';

import type { UiAuditRunSummary, UiAuditStep, UiAuditVerdict } from './schemas';

const VIN_RE = /\b([A-HJ-NPR-Z0-9]{3})[A-HJ-NPR-Z0-9]{11,14}\b/gi;
const SPZ_RE = /\b([0-9][A-Z0-9]{1,2})[A-Z0-9]{2,5}\b/gi;
const EMAIL_RE = /([A-Za-z0-9])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})/g;
const PHONE_RE = /(\+?\d{3})[\s\d]{3,}[\s]?(\d{3})\b/g;

export function maskPii(text: string): string {
  return text
    .replace(VIN_RE, (_m, prefix) => `${String(prefix).toUpperCase()}************`)
    .replace(SPZ_RE, (_m, prefix) => `${String(prefix).toUpperCase()}****`)
    .replace(EMAIL_RE, (_m, first, domain) => `${first}***@${domain}`)
    .replace(PHONE_RE, (_m, a, b) => `${a} *** ${b}`);
}

function maskStep(step: UiAuditStep): UiAuditStep {
  return {
    ...step,
    before_url: maskPii(step.before_url),
    after_url: maskPii(step.after_url),
    element_text: maskPii(step.element_text),
    parent_element: step.parent_element ? maskPii(step.parent_element) : null,
    reason: maskPii(step.reason),
    recommended_fix: step.recommended_fix ? maskPii(step.recommended_fix) : null,
    actual_result: {
      ...step.actual_result,
      api_calls: step.actual_result.api_calls.map(maskPii),
      http_errors: step.actual_result.http_errors.map((e) => ({ ...e, url: maskPii(e.url) })),
      console_errors: step.actual_result.console_errors.map(maskPii),
    },
    gdpr: { ...step.gdpr, note: maskPii(step.gdpr.note) },
  };
}

function overallVerdict(steps: UiAuditStep[]): UiAuditVerdict {
  if (steps.some((s) => s.verdict === 'FAIL')) return 'FAIL';
  if (steps.some((s) => s.verdict === 'WARN')) return 'WARN';
  if (steps.length > 0 && steps.every((s) => s.verdict === 'BLOCKED')) return 'BLOCKED';
  return 'PASS';
}

export function buildRunSummary(
  runId: string,
  scope: string,
  baseUrl: string,
  startedAt: string,
  steps: UiAuditStep[],
  dynamicPanels: UiAuditRunSummary['dynamic_panels'] = [],
  profilePanelChildCount = 0,
  totalElements?: number,
): UiAuditRunSummary {
  const maskedSteps = steps.map(maskStep);
  const safe_count = steps.filter((s) => s.safety_class === 'SAFE').length;
  const warn_count = steps.filter((s) => s.safety_class === 'WARN').length;
  const blocked_count = steps.filter((s) => s.safety_class === 'BLOCKED').length;

  return {
    run_id: runId,
    started_at: startedAt,
    finished_at: new Date().toISOString(),
    scope,
    base_url: maskPii(baseUrl),
    overall_verdict: overallVerdict(maskedSteps),
    total_elements: totalElements ?? steps.length,
    safe_count,
    warn_count,
    blocked_count,
    pass_count: maskedSteps.filter((s) => s.verdict === 'PASS').length,
    fail_count: maskedSteps.filter((s) => s.verdict === 'FAIL').length,
    warn_verdict_count: maskedSteps.filter((s) => s.verdict === 'WARN').length,
    blocked_verdict_count: maskedSteps.filter((s) => s.verdict === 'BLOCKED').length,
    fail_redirect_count: maskedSteps.filter((s) => s.verdict === 'FAIL' && s.action_type === 'navigate').length,
    dynamic_panels: dynamicPanels,
    profile_panel_child_count: profilePanelChildCount,
    steps: maskedSteps,
  };
}

function relScreenshot(runDir: string, screenshotPath: string): string {
  if (!screenshotPath) return '';
  const rel = path.relative(runDir, screenshotPath);
  return rel.startsWith('..') ? path.basename(screenshotPath) : rel;
}

export function writeMarkdownReport(summary: UiAuditRunSummary, runDir: string): string {
  const lines: string[] = [];
  lines.push('# UI Audit Report — Správa vozidel');
  lines.push('');
  lines.push(`- **Run ID:** ${summary.run_id}`);
  lines.push(`- **Scope:** ${summary.scope}`);
  lines.push(`- **Overall verdict:** ${summary.overall_verdict}`);
  lines.push(`- **Started:** ${summary.started_at}`);
  lines.push(`- **Finished:** ${summary.finished_at}`);
  lines.push('');
  lines.push('## Actionable Solution');
  lines.push('');
  const fails = summary.steps.filter((s) => s.verdict === 'FAIL');
  const warns = summary.steps.filter((s) => s.verdict === 'WARN');
  if (!fails.length && !warns.length) {
    lines.push('Všechny bezpečně otestované prvky v rozsahu prošly. Rozšiřte scope na další sekce.');
  } else {
    fails.slice(0, 10).forEach((s) => {
      lines.push(`- **FAIL** \`${maskPii(s.element_text || s.data_testid || 'prvek')}\`: ${s.reason}${s.recommended_fix ? ` → ${s.recommended_fix}` : ''}`);
    });
    warns.slice(0, 5).forEach((s) => {
      lines.push(`- **WARN** \`${maskPii(s.element_text || s.data_testid || 'prvek')}\`: ${s.reason}`);
    });
  }
  lines.push('');
  lines.push('## Technical Architecture');
  lines.push('');
  lines.push('- Deterministic crawler (`audit-crawler.spec.ts`) + safety-policy + route-oracle');
  lines.push('- READ/SAFE CLICK režim — bez submitů, plateb, mazání');
  lines.push('- Volitelný AI reviewer přes `UI_AUDIT_AI=1`');
  lines.push('- Artefakty: JSON + Markdown + screenshots + trace');
  lines.push('');
  lines.push('## Business Impact');
  lines.push('');
  lines.push(`- Celkem prvků: **${summary.total_elements}** (SAFE ${summary.safe_count} / WARN ${summary.warn_count} / BLOCKED ${summary.blocked_count})`);
  lines.push(`- Profil panel child prvků: **${summary.profile_panel_child_count}**`);
  lines.push(`- FAIL redirectů: **${summary.fail_redirect_count}**`);
  lines.push(`- PASS: ${summary.pass_count}, FAIL: ${summary.fail_count}, WARN: ${summary.warn_verdict_count}, BLOCKED: ${summary.blocked_verdict_count}`);
  lines.push('');
  lines.push('## Discovered dynamic panels');
  lines.push('');
  if (!summary.dynamic_panels.length) {
    lines.push('Žádné dynamické panely nebyly otevřeny.');
  } else {
    summary.dynamic_panels.forEach((panel) => {
      lines.push(`- **${panel.panel_id}** (${panel.panel_label}): parent=\`${panel.parent_element}\`, children=${panel.child_count}${panel.child_testids.length ? ` [${panel.child_testids.join(', ')}]` : ''}`);
    });
  }
  lines.push('');
  lines.push('## Detailní tabulka kliků');
  lines.push('');
  lines.push('| Sekce | Text | testid | Parent | Panel | Isolated | Reopened | URL před | URL po | Verdict | Chyby | Screenshot |');
  lines.push('| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |');

  summary.steps.forEach((s) => {
    const errors = [
      ...s.actual_result.console_errors.slice(0, 1),
      ...s.actual_result.http_errors.map((e) => `${e.status}:${path.basename(e.url)}`).slice(0, 1),
    ].join('; ') || '—';
    const shot = relScreenshot(runDir, s.actual_result.screenshot_after) || relScreenshot(runDir, s.actual_result.screenshot_before);
    lines.push(
      `| ${s.section_guess} | ${s.element_text.slice(0, 36)} | ${s.data_testid || '—'} | ${s.parent_element || '—'} | ${s.parent_panel || '—'} | ${s.isolated_child_run ? 'yes' : 'no'} | ${s.parent_panel_reopened ? 'yes' : 'no'} | ${s.before_url.slice(0, 32)} | ${s.after_url.slice(0, 32)} | ${s.verdict} | ${errors} | ${shot || '—'} |`,
    );
  });

  lines.push('');
  return lines.join('\n');
}

export function publishAuditArtifacts(summary: UiAuditRunSummary, runDir: string, tracePath?: string): {
  reportJson: string;
  reportMd: string;
  latestDir: string;
} {
  const repoRoot = path.resolve(__dirname, '../../..');
  const latestDir = path.join(repoRoot, 'artifacts/ui-audit/latest');
  const screenshotsLatest = path.join(latestDir, 'screenshots');

  fs.mkdirSync(screenshotsLatest, { recursive: true });
  fs.mkdirSync(runDir, { recursive: true });

  const reportJsonRun = path.join(runDir, 'report.json');
  const reportMdRun = path.join(runDir, 'report.md');
  const markdown = writeMarkdownReport(summary, runDir);

  fs.writeFileSync(reportJsonRun, JSON.stringify(summary, null, 2), 'utf8');
  fs.writeFileSync(reportMdRun, markdown, 'utf8');

  fs.writeFileSync(path.join(latestDir, 'report.json'), JSON.stringify(summary, null, 2), 'utf8');
  fs.writeFileSync(path.join(latestDir, 'report.md'), markdown, 'utf8');

  const shotsSrc = path.join(runDir, 'screenshots');
  if (fs.existsSync(shotsSrc)) {
    for (const file of fs.readdirSync(shotsSrc)) {
      fs.copyFileSync(path.join(shotsSrc, file), path.join(screenshotsLatest, file));
    }
  }

  if (tracePath && fs.existsSync(tracePath)) {
    fs.copyFileSync(tracePath, path.join(latestDir, 'trace.zip'));
    fs.copyFileSync(tracePath, path.join(runDir, 'trace.zip'));
  }

  return {
    reportJson: path.join(latestDir, 'report.json'),
    reportMd: path.join(latestDir, 'report.md'),
    latestDir,
  };
}

export function writeScreenshotIndex(summary: UiAuditRunSummary, runDir: string): void {
  const index = summary.steps.map((s) => ({
    step: s.step_index,
    text: s.element_text,
    before: s.actual_result.screenshot_before,
    after: s.actual_result.screenshot_after,
    verdict: s.verdict,
  }));
  fs.writeFileSync(path.join(runDir, 'screenshot-index.json'), JSON.stringify(index, null, 2), 'utf8');
}
