import type { FieldErrors } from './formErrors';

export const ENV_KEYS = ['weather', 'lighting', 'workspace', 'operational_tempo'] as const;
export const IMSAFE_KEYS = ['I', 'M', 'S', 'A', 'F', 'E'] as const;

export interface MrmDraftState {
  activity: string;
  objectives: string;
  /** selected evaluator id, or null/'' while nothing is chosen */
  reviewer: string | null;
  /** ids currently offered in the evaluator dropdown */
  evaluatorIds: string[];
  /** true when the reviewer cannot be edited (already submitted) so it is not required from the user */
  reviewerLocked: boolean;
  imsafe: Record<string, boolean>;
  env: Record<string, string>;
  hazardCount: number;
  needsUnit: boolean;
  unit: string | null;
}

/** Mirrors the server rules so problems are caught — and shown beside the field — before the request is sent. */
export function validateMrmDraft(s: MrmDraftState): FieldErrors {
  const e: FieldErrors = {};
  if (s.needsUnit && !s.unit) e.unit = 'Choose the unit this MRM is for.';
  if (!s.activity.trim()) e.activity_mission = 'Activity / Mission is required.';
  if (!s.objectives.trim()) e.safety_objectives = 'Safety objectives are required.';
  if (!s.reviewerLocked) {
    if (!s.reviewer) e.reviewer = s.evaluatorIds.length ? 'Select an evaluator to review this MRM.' : 'No evaluator is available in your unit or its mother units — ask an administrator to assign one.';
    else if (!s.evaluatorIds.includes(s.reviewer)) e.reviewer = 'The selected evaluator is no longer available — choose another.';
  }
  if (!IMSAFE_KEYS.every((k) => s.imsafe[k])) e.imsafe = "Confirm every I'M SAFE item.";
  const missingEnv = ENV_KEYS.filter((k) => !s.env[k]);
  if (missingEnv.length) e.environment = 'Select weather, lighting, workspace and operational tempo.';
  if (s.hazardCount < 1) e.hazards = 'Select at least one hazard from the registry.';
  return e;
}

export const MRM_FIELD_ORDER = ['unit', 'activity_mission', 'safety_objectives', 'reviewer', 'imsafe', 'environment', 'hazards'];
