import type { AiReviewInput, AiReviewResult, UiAuditStep } from './schemas';

export interface AiReviewer {
  reviewStep(input: AiReviewInput): Promise<AiReviewResult>;
}

export class NoOpAiReviewer implements AiReviewer {
  async reviewStep(_input: AiReviewInput): Promise<AiReviewResult> {
    return {
      enabled: false,
      summary: null,
      semantic_match: null,
      design_ok: null,
      gdpr_risk: null,
      suggested_target: null,
    };
  }
}

export class PlaceholderAiReviewer implements AiReviewer {
  async reviewStep(input: AiReviewInput): Promise<AiReviewResult> {
    const step = input.step;
    const semanticMatch = step.verdict === 'PASS';
    return {
      enabled: true,
      summary: `AI placeholder: prvek "${step.element_text}" → ${step.verdict}`,
      semantic_match: semanticMatch,
      design_ok: step.actual_result.console_errors.length === 0,
      gdpr_risk: step.gdpr.violation ? 'Možné míchání PII v UI' : null,
      suggested_target: step.recommended_fix,
    };
  }
}

export function createAiReviewer(): AiReviewer {
  const enabled = process.env.UI_AUDIT_AI === '1' || process.env.UI_AUDIT_AI === 'true';
  if (!enabled) return new NoOpAiReviewer();
  return new PlaceholderAiReviewer();
}

export async function maybeEnhanceStepWithAi(
  step: UiAuditStep,
  reviewer: AiReviewer,
  screenshotBeforePath?: string,
  screenshotAfterPath?: string,
): Promise<UiAuditStep> {
  const ai = await reviewer.reviewStep({ step, screenshotBeforePath, screenshotAfterPath });
  if (!ai.enabled) return step;

  let reason = step.reason;
  if (ai.summary) reason = `${reason} | AI: ${ai.summary}`;
  if (ai.semantic_match === false && step.verdict === 'PASS') {
    return { ...step, verdict: 'WARN', reason, recommended_fix: ai.suggested_target || step.recommended_fix };
  }
  return { ...step, reason };
}
