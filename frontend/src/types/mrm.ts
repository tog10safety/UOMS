export type MrmAuthority = 'ADMINISTRATOR' | 'EVALUATOR' | 'CREATOR' | 'UNIT_SAFETY_OFFICER' | '';
export type MrmDesignation = 'OPERATOR' | 'SUPERVISOR' | 'SQUADRON_COMMANDER' | 'DIRECTOR_FOR_OPERATIONS' | 'COMMANDER' | '';
export type RiskTier = 'HIGH' | 'MEDIUM' | 'LOW';
export type MrmStage =
  | 'draft' | 'awaiting_review' | 'needs_revision' | 'rejected'
  | 'awaiting_authority' | 'needs_authority_assignment' | 'approved';

export interface MrmConfig {
  activity_codes: string[];
  environment_options: { weather: string[]; lighting: string[]; workspace: string[]; operational_tempo: string[] };
  imsafe_checklist: Record<string, string>;
  personnel_roles: string[];
  default_mission_statement: string;
  likelihoods: Record<string, string>;
  severities: Record<string, string>;
  matrix: { red: string[]; yellow: string[]; green: string[] };
  authority_tiers: { code: string; label: string; range: string; max_percent: number }[];
}

export interface MrmMe {
  authority: MrmAuthority;
  designation: MrmDesignation;
  has_signature: boolean;
  unit: string | null;
  can_author: boolean;
  can_manage_registry: boolean;
  is_admin: boolean;
  is_safety_officer: boolean;
  sees_all_units: boolean;
  scope_units: string[] | null;
}

export interface WorkQueue {
  my_drafts: number;
  needs_revision: number;
  awaiting_my_review: number;
  awaiting_my_approval: number;
  feedback_to_give: number;
  needs_authority_assignment?: number;
  missions_awaiting_my_approval?: number;
  mrm_to_prepare?: number;
  feedback_to_review: number;
  total_action_items: number;
}

export interface RiskBlock {
  likelihood: number;
  severity: string;
  rating: string;
  level: RiskTier;
}

export interface Hazard {
  id: string;
  unit: string;
  unit_name: string;
  unit_code: string;
  activity_code: string;
  hazard_description: string;
  before_likelihood: number;
  before_severity: string;
  before_risk_rating: string;
  before_level: RiskTier;
  mitigations: string;
  after_likelihood: number;
  after_severity: string;
  after_risk_rating: string;
  after_level: RiskTier;
  created_by_name: string | null;
  in_use: boolean;
  can_edit: boolean;
  updated_at: string;
}

export interface MrmListItem {
  id: string;
  mrm_number: string;
  activity_mission: string;
  mission: string | null;
  mission_name: string | null;
  unit: string | null;
  unit_name: string | null;
  unit_code: string | null;
  creator_name: string;
  reviewer_name: string;
  authority_name: string;
  status: 'draft' | 'submitted' | 'reviewed';
  review_status: 'pending' | 'approved' | 'rejected' | 'needs_revision';
  total_percent: number;
  risk_category: string;
  authority_level: string;
  authority_level_label: string;
  authority_approved: boolean;
  stage: MrmStage;
  has_pdf: boolean;
  my_roles: ('creator' | 'reviewer' | 'authority' | 'tagged')[];
  created_at: string;
  date_submitted: string | null;
  authority_approval_date: string | null;
}

export interface MrmHazardLine {
  id: number;
  hazard: string;
  activity_code: string;
  hazard_description: string;
  mitigations: string;
  before: RiskBlock;
  registry_after: RiskBlock;
  override: RiskBlock | null;
  additional_mitigations: string;
  residual: RiskBlock;
  registry_changed: boolean;
}

export interface MrmUserBrief {
  id: string;
  username: string;
  full_name: string;
  display_name: string;
  unit: string | null;
  mrm_authority: string;
  mrm_designation: string;
}

export interface MrmCapabilities {
  edit: string | null;
  edit_message: string;
  delete: boolean;
  submit: boolean;
  review: boolean;
  authority_approve: boolean;
  reassign_authority: boolean;
  reassign_reviewer: boolean;
  manage_personnel: boolean;
  sign: 'creator' | 'evaluator' | null;
  give_feedback: boolean;
  regenerate_pdf: boolean;
  is_resubmission: boolean;
}

export interface MrmEvent {
  id: number;
  kind: string;
  label: string;
  actor: string;
  comments: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface MrmDetail extends MrmListItem {
  safety_objectives: string;
  imsafe: Record<string, boolean>;
  aircraft_vehicle: string;
  mission_statement: string;
  environment: string;
  environment_data: Record<string, string>;
  hazards: MrmHazardLine[];
  risk: {
    max_risk: number; residual_risk: number; total_percent: number; risk_category: string;
    authority_level: string; authority_level_label: string; authority_range: string;
  };
  creator: MrmUserBrief | null;
  reviewer: MrmUserBrief | null;
  authority: MrmUserBrief | null;
  review_notes: string;
  date_reviewed: string | null;
  creator_signed: boolean;
  creator_signature_date: string | null;
  evaluator_signed: boolean;
  evaluator_signature_date: string | null;
  completion_time_seconds: number | null;
  feedback_collection_closed: boolean;
  tagged_personnel: { id: string; user: string; name: string; role: string; feedback_submitted: boolean }[];
  feedback_counts: { submitted: number; pending_review: number; awaiting: number };
  events: MrmEvent[];
  can: MrmCapabilities;
  warnings?: string[];
}

export interface MrmFormInput {
  mission?: string | null;
  unit?: string | null;
  activity_mission: string;
  safety_objectives: string;
  reviewer: string | null;
  aircraft_vehicle: string;
  mission_statement: string;
  imsafe: Record<string, boolean>;
  environment: Record<string, string>;
  hazards: { hazard: string; override_likelihood?: number | null; override_severity?: string; additional_mitigations?: string }[];
  tagged_personnel: { user: string; role: string }[];
}

export interface RiskPreview {
  max_risk: number; residual_risk: number; total_percent: number;
  authority_level: string; authority_label: string; risk_category: string;
}

export interface MrmFeedbackItem {
  id: string;
  mrm: string;
  mrm_number: string;
  activity_mission: string;
  unit_name: string | null;
  submitted_by: string | null;
  is_anonymous: boolean;
  risk_assessment_accuracy: number;
  hazard_identification_rating: number;
  mitigation_effectiveness: number;
  what_went_well: string;
  what_could_be_improved: string;
  new_hazards_identified: string;
  lessons_learned: string;
  additional_comments: string;
  recommend_add_to_hazard_registry: boolean;
  recommended_hazard_description: string;
  recommended_mitigations: string;
  status: 'pending' | 'reviewed' | 'action_taken';
  submitted_at: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_notes: string;
  action_taken: string;
  action_taken_at: string | null;
  can_review: boolean;
  created_hazard?: string | null;
}

export interface SafetyUser {
  id: string; username: string; full_name: string; email: string; unit: string | null;
  mrm_authority: string; mrm_designation: string; is_active: boolean; has_signature: boolean; last_login: string | null;
}

export interface SafetyAssignment {
  id: string; user: string; username: string; user_name: string; unit: string; unit_name: string; unit_code: string; is_primary: boolean;
}

export interface UnitLogoItem { id: string; unit: string; unit_name: string; unit_code: string }

export interface MrmAnalytics {
  totals: { forms: number; approved: number; stages: Record<string, number> };
  risk_category: Record<string, number>;
  authority_level: Record<string, number>;
  by_month: Record<string, number>;
  by_unit: { unit__code: string; unit__name: string; count: number }[];
  avg_completion_hours: number;
  top_hazards: { activity_code: string; hazard_description: string; after_risk_rating: string; uses: number }[];
  feedback: {
    total: number; pending: number; reviewed: number; action_taken: number;
    avg_ratings: { accuracy: number | null; identification: number | null; mitigation: number | null };
  };
}

export interface HazardImportResult {
  created: number; updated: number; skipped: number; skip_reasons: string[]; errors: string[];
}
