import type { MissionDetail } from './index';

export type MissionCategoryKey = 'AIR_OPERATIONS' | 'GROUND_OPERATIONS';
export type ApprovalStatus = 'DRAFT' | 'PENDING' | 'APPROVED' | 'REJECTED';
export type MrmPrepStatus = 'NOT_STARTED' | 'IN_PROGRESS' | 'REVISION_REQUIRED' | 'SUBMITTED' | 'APPROVED';

export interface CategoryInfo { key: MissionCategoryKey; label: string; enabled: boolean; description: string }
export interface RoleOption { value: string; label: string }
export interface AuthorityOption { id: string; name: string; designation: string; unit: string | null }

export interface PlaceOut { name: string; lat: number; lng: number; mgrs: string }
export interface PersonBrief {
  id: string; name: string; service_number: string; rank: string; unit: string | null; has_account: boolean; account_id?: string | null;
}
export interface PlanPersonnel { id: string; personnel: string; role: string; role_other: string; role_label: string; person: PersonBrief }
export interface PlanStop extends PlaceOut { sequence: number; notes: string }
export interface PlanLeg {
  id: string; sequence: number; origin: PlaceOut; destination: PlaceOut; stops: PlanStop[];
  planned_departure: string | null; planned_arrival: string | null; notes: string;
}
export interface PlanVehicle {
  id: string; is_pov: boolean; sequence: number; vehicle: string | null;
  fleet: { plate_number: string; vehicle_type: string; make: string; model: string } | null;
  pov: { plate_number: string; vehicle_type: string; make: string; model: string; color: string; owner_name: string; description: string } | null;
  driver: string | null; driver_name: string | null; notes: string; itinerary: PlanLeg[];
}

export interface MissionPlanning {
  category: MissionCategoryKey | '';
  category_label: string;
  unit_name: string | null;
  unit_code: string | null;
  responsible_section_name: string | null;
  created_by: string | null;
  created_by_name: string | null;
  personnel: PlanPersonnel[];
  vehicles: PlanVehicle[];
  approval: {
    status: ApprovalStatus; status_label: string;
    authority: { id: string; name: string; designation: string; unit: string | null } | null;
    submitted_at: string | null; decided_by_name: string | null; decided_at: string | null; comments: string;
  };
  mrm_assignee: (PersonBrief & { account_id: string | null }) | null;
  mrm_preparation: { status: MrmPrepStatus; label: string; form_id: string | null; mrm_number: string | null };
  can: { edit: boolean; submit: boolean; decide: boolean; prepare_mrm: boolean };
  responsible_section?: string | null;
  newly_submitted?: boolean;
}

export type MissionPlan = MissionDetail & MissionPlanning;

export interface ActivityEvent { when: string; kind: 'approval' | 'risk_review' | 'audit' | 'notification'; title: string; actor: string; detail: string }

export interface AppNotification {
  id: string; kind: string; title: string; message: string; link: string; is_read: boolean; created_at: string;
  metadata: Record<string, unknown>;
}
