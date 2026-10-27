export type UserRole = 'ADMIN' | 'COMMANDER' | 'STAFF' | 'OPERATOR' | 'VIEWER';

export type PermissionModule =
  | 'DASHBOARD' | 'PERSONNEL' | 'VEHICLES' | 'AIRCRAFT' | 'MISSIONS'
  | 'ARMORY' | 'INVENTORY' | 'GIS' | 'REPORTS' | 'ADMINISTRATION';

export type PermissionAction =
  | 'VIEW' | 'CREATE' | 'EDIT' | 'DELETE' | 'APPROVE'
  | 'DISPATCH' | 'ISSUE' | 'RETURN' | 'ASSIGN' | 'EXPORT' | 'REPORT';

export interface User {
  id: string;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  role: UserRole;
  unit: string | null;
  unit_name: string | null;
  section: string | null;
  section_name: string | null;
  permissions: Partial<Record<PermissionModule, PermissionAction[]>>;
  phone_number: string;
  is_active: boolean;
  must_change_password: boolean;
  mrm_authority: string;
  mrm_designation: string;
  effective_mrm_authority: string;
  has_signature: boolean;
  last_login: string | null;
  date_joined: string;
}

export interface MissionMrmSummary {
  id: string;
  mrm_number: string;
  stage: string;
  total_percent: number;
  risk_category: string;
  authority_level: string;
  authority_level_label: string;
  authority_name: string;
  authority_approved: boolean;
}

export interface LoginResponse {
  access: string;
  refresh: string;
  user: User;
}

export interface Rank {
  id: string;
  name: string;
  abbreviation: string;
  order: number;
  is_active: boolean;
}

export type UnitCategory = 'HPAF' | 'COMMAND' | 'WING' | 'GROUP' | 'SQUADRON';

export interface Unit {
  id: string;
  name: string;
  code: string;
  category: UnitCategory | '';
  category_display: string;
  parent_unit: string | null;
  parent_unit_name: string | null;
  subordinate_count: number;
  description: string;
  is_active: boolean;
}

export interface ConsolidatedAOR {
  unit: string;
  unit_category: UnitCategory | '';
  source_boundary_count: number;
  source_units: string[];
  consolidated_boundary: LatLng[][];
}

export interface Position {
  id: string;
  title: string;
  description: string;
  is_active: boolean;
}

export interface Qualification {
  id: string;
  name: string;
  description: string;
  validity_period_days: number | null;
  is_active: boolean;
}

export type PersonnelStatus = 'ACTIVE' | 'ON_LEAVE' | 'DEPLOYED' | 'TRAINING' | 'MEDICAL' | 'SEPARATED';

export interface PersonnelListItem {
  id: string;
  service_number: string;
  full_name: string;
  rank_abbreviation: string;
  unit_name: string;
  position_title: string | null;
  status: PersonnelStatus;
  is_active: boolean;
  /** has a login account */
  has_account?: boolean;
  /** that account may author MRM forms (eligible to be a mission's MRM preparer) */
  mrm_ready?: boolean;
}

export interface PersonnelDetail {
  id: string;
  service_number: string;
  first_name: string;
  last_name: string;
  middle_name: string;
  full_name: string;
  rank: string;
  unit: string;
  position: string | null;
  qualifications: string[];
  status: PersonnelStatus;
  date_of_birth: string | null;
  contact_number: string;
  email: string;
  date_enlisted: string | null;
  photo: string | null;
  linked_account: string | null;
  remarks: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface MapPoint {
  type: 'vehicle' | 'mission';
  label: string;
  lat: number;
  lng: number;
}

export interface RiskAlertSummary {
  id: string;
  title: string;
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  mission: string | null;
  created_at: string;
}

export interface RecentActivity {
  id: number;
  user: string;
  action: string;
  model_name: string;
  description: string;
  created_at: string;
}

export interface DashboardSummary {
  generated_at: string;
  operational_status: {
    total_personnel: number;
    total_vehicles: number;
    total_aircraft: number;
    active_missions: number;
    open_risk_alerts: number;
  };
  personnel_summary: { total: number; by_status: Record<string, number> };
  vehicle_status: { total: number; by_status: Record<string, number> };
  aircraft_flying_status: { total: number; by_status: Record<string, number> };
  mission_status: { total: number; by_status: Record<string, number> };
  risk_alerts: RiskAlertSummary[];
  recent_activities: RecentActivity[];
  map_overview: MapPoint[];
}

// ---------------------------------------------------------------------------
// Vehicle Tracking and Monitoring
// ---------------------------------------------------------------------------
export type VehicleStatus = 'AVAILABLE' | 'ON_MISSION' | 'MAINTENANCE' | 'OUT_OF_SERVICE';

export interface LatLng {
  lat: number;
  lng: number;
}

export interface VehicleListItem {
  id: string;
  plate_number: string;
  vehicle_type: string;
  make: string;
  model: string;
  status: VehicleStatus;
  driver_name: string | null;
  mission_name: string | null;
  odometer_km: number;
  last_known_location: LatLng | null;
  last_location_updated_at: string | null;
  is_active: boolean;
}

export interface VehicleDetail {
  id: string;
  plate_number: string;
  make: string;
  model: string;
  vehicle_type: string;
  year: number | null;
  capacity: number | null;
  fuel_type: string;
  odometer_km: number;
  status: VehicleStatus;
  assigned_driver: string | null;
  assigned_mission: string | null;
  last_known_location: LatLng | null;
  last_location_updated_at: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Trip {
  id: string;
  vehicle: string;
  vehicle_plate: string;
  driver: string;
  driver_name: string;
  mission: string | null;
  origin: string;
  destination: string;
  purpose: string;
  status: 'ONGOING' | 'COMPLETED' | 'CANCELLED';
  start_time: string;
  end_time: string | null;
  start_odometer_km: number;
  end_odometer_km: number | null;
  distance_km: number | null;
  remarks: string;
  is_active: boolean;
  created_at: string;
}

export interface VehicleMaintenanceRecord {
  id: string;
  vehicle: string;
  vehicle_plate: string;
  maintenance_type: 'PREVENTIVE' | 'REPAIR' | 'INSPECTION' | 'TIRE_CHANGE' | 'OIL_CHANGE' | 'OTHER';
  description: string;
  performed_by: string;
  cost: string | null;
  service_date: string;
  next_due_date: string | null;
  odometer_at_service_km: number | null;
  is_active: boolean;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Aircraft Flying Monitoring
// ---------------------------------------------------------------------------
export type AircraftFlyingStatus = 'GROUNDED' | 'SCHEDULED' | 'IN_FLIGHT' | 'MAINTENANCE';

export interface AircraftItem {
  id: string;
  tail_number: string;
  aircraft_type: string;
  manufacturer: string;
  model: string;
  capacity: number | null;
  flying_status: AircraftFlyingStatus;
  base_unit: string | null;
  base_unit_name: string | null;
  is_active: boolean;
  created_at: string;
}

export type FlightStatus = 'SCHEDULED' | 'DEPARTED' | 'EN_ROUTE' | 'ARRIVED' | 'DELAYED' | 'CANCELLED';

export interface FlightListItem {
  id: string;
  flight_number: string;
  aircraft: string;
  aircraft_tail_number: string;
  mission: string | null;
  mission_name: string | null;
  unit: string | null;
  unit_name: string | null;
  origin: string;
  destination: string;
  scheduled_departure: string;
  scheduled_arrival: string;
  actual_departure: string | null;
  actual_arrival: string | null;
  status: FlightStatus;
}

export interface FlightCrewAssignment {
  id: string;
  flight: string;
  personnel: string;
  personnel_name: string;
  crew_role: 'PIC' | 'CO_PILOT' | 'FLIGHT_ENGINEER' | 'LOADMASTER' | 'CREW_CHIEF' | 'OTHER';
}

export interface FlightWaypoint {
  id: string;
  flight: string;
  sequence: number;
  name: string;
  location: LatLng | null;
  eta: string | null;
  notes: string;
}

export interface FlightDetail {
  id: string;
  flight_number: string;
  aircraft: string;
  mission: string | null;
  unit: string | null;
  origin: string;
  origin_location: LatLng | null;
  destination: string;
  destination_location: LatLng | null;
  scheduled_departure: string;
  scheduled_arrival: string;
  actual_departure: string | null;
  actual_arrival: string | null;
  status: FlightStatus;
  caap_flight_plan_number: string;
  caap_aircraft_registration: string;
  caap_remarks: string;
  crew_assignments: FlightCrewAssignment[];
  waypoints: FlightWaypoint[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Mission Risk Management
// ---------------------------------------------------------------------------
export type MissionStatus = 'PLANNED' | 'APPROVED' | 'ONGOING' | 'COMPLETED' | 'CANCELLED';
export type RiskReviewStatus = 'DRAFT' | 'SUBMITTED' | 'APPROVED' | 'REJECTED';
export type HazardCategory =
  | 'WEATHER'
  | 'MECHANICAL'
  | 'HUMAN_ERROR'
  | 'ENEMY_ACTION'
  | 'TERRAIN'
  | 'MEDICAL'
  | 'OTHER';
export type RiskProbability = 'FREQUENT' | 'LIKELY' | 'OCCASIONAL' | 'SELDOM' | 'UNLIKELY';
export type RiskSeverity = 'CATASTROPHIC' | 'CRITICAL' | 'MODERATE' | 'NEGLIGIBLE';
export type RiskLevel = 'EXTREMELY_HIGH' | 'HIGH' | 'MEDIUM' | 'LOW';

export interface HazardAssessment {
  id: string;
  mission: string;
  hazard_description: string;
  category: HazardCategory;
  probability: RiskProbability;
  severity: RiskSeverity;
  initial_risk_level: RiskLevel;
  existing_controls: string;
  additional_controls: string;
  residual_probability: RiskProbability | '';
  residual_severity: RiskSeverity | '';
  residual_risk_level: RiskLevel | '';
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface MissionApprovalLogEntry {
  id: string;
  mission: string;
  action: 'SUBMITTED' | 'APPROVED' | 'REJECTED' | 'REOPENED';
  actor: string | null;
  actor_name: string | null;
  comments: string;
  created_at: string;
}

export interface MissionListItem {
  id: string;
  name: string;
  category: 'AIR_OPERATIONS' | 'GROUND_OPERATIONS' | '';
  category_label: string;
  approval_status: 'DRAFT' | 'PENDING' | 'APPROVED' | 'REJECTED';
  mrm_preparation: { status: string; label: string };
  status: MissionStatus;
  unit: string | null;
  unit_name: string | null;
  commander_name: string | null;
  risk_review_status: RiskReviewStatus;
  overall_risk_level: RiskLevel | null;
  mrm: MissionMrmSummary | null;
  start_date: string | null;
  end_date: string | null;
  is_active: boolean;
}

export interface MissionDetail {
  id: string;
  name: string;
  /** '' for missions created before categories existed */
  category: 'AIR_OPERATIONS' | 'GROUND_OPERATIONS' | '';
  mrm: MissionMrmSummary | null;
  description: string;
  unit: string | null;
  mission_commander: string | null;
  status: MissionStatus;
  location: LatLng | null;
  start_date: string | null;
  end_date: string | null;
  risk_review_status: RiskReviewStatus;
  submitted_by: string | null;
  submitted_by_name: string | null;
  submitted_at: string | null;
  reviewed_by: string | null;
  reviewed_by_name: string | null;
  reviewed_at: string | null;
  review_comments: string;
  overall_risk_level: RiskLevel | null;
  overall_residual_risk_level: RiskLevel | null;
  hazard_assessments: HazardAssessment[];
  approval_logs: MissionApprovalLogEntry[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Armory Management
// ---------------------------------------------------------------------------
export type FirearmStatus = 'SERVICEABLE' | 'ISSUED' | 'UNSERVICEABLE' | 'IN_REPAIR' | 'DECOMMISSIONED';

export interface Firearm {
  id: string;
  serial_number: string;
  firearm_type: string;
  make: string;
  model: string;
  caliber: string;
  status: FirearmStatus;
  unit: string | null;
  unit_name: string | null;
  accountable_personnel: string | null;
  accountable_personnel_name: string | null;
  acquisition_date: string | null;
  remarks: string;
  is_active: boolean;
  created_at: string;
}

export interface AmmunitionStock {
  id: string;
  ammunition_type: string;
  lot_number: string;
  unit: string | null;
  unit_name: string | null;
  quantity_on_hand: number;
  unit_of_measure: string;
  storage_location: string;
  expiration_date: string | null;
  is_low_stock: boolean;
  is_active: boolean;
  created_at: string;
}

export type FirearmIssuanceStatus = 'ISSUED' | 'RETURNED' | 'OVERDUE' | 'LOST';

export interface FirearmIssuance {
  id: string;
  firearm: string;
  firearm_serial: string;
  issued_to: string;
  issued_to_name: string;
  issued_by: string | null;
  issued_by_username: string | null;
  issue_date: string;
  expected_return_date: string | null;
  return_date: string | null;
  condition_on_issue: string;
  condition_on_return: string;
  status: FirearmIssuanceStatus;
  purpose: string;
  remarks: string;
  is_active: boolean;
  created_at: string;
}

export interface ArmoryTransaction {
  id: string;
  type: 'FIREARM_ISSUE' | 'FIREARM_RETURN' | 'AMMUNITION_ISSUE';
  description: string;
  quantity: number;
  date: string;
}

// ---------------------------------------------------------------------------
// Inventory Management
// ---------------------------------------------------------------------------
export type InventoryItemType = 'EQUIPMENT' | 'SUPPLY';
export type InventoryCondition = 'SERVICEABLE' | 'UNSERVICEABLE' | 'FOR_DISPOSAL';

export interface ItemCategory {
  id: string;
  name: string;
  description: string;
  is_active: boolean;
}

export interface InventoryItem {
  id: string;
  name: string;
  category: string | null;
  category_name: string | null;
  item_type: InventoryItemType;
  property_number: string;
  sku: string;
  unit_of_measure: string;
  quantity_on_hand: number;
  reorder_level: number;
  is_low_stock: boolean;
  condition: InventoryCondition;
  unit: string | null;
  unit_name: string | null;
  storage_location: string;
  accountable_personnel: string | null;
  accountable_personnel_name: string | null;
  description: string;
  remarks: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export type InventoryTransactionType = 'RECEIPT' | 'ISSUANCE' | 'RETURN' | 'ADJUSTMENT' | 'DISPOSAL';

export interface InventoryTransaction {
  id: string;
  item: string;
  item_name: string;
  transaction_type: InventoryTransactionType;
  quantity: number;
  issued_to: string | null;
  issued_to_name: string | null;
  supplier_or_source: string;
  performed_by: string | null;
  performed_by_username: string | null;
  transaction_date: string;
  reference_number: string;
  remarks: string;
  is_active: boolean;
  created_at: string;
}

export interface InventoryReportRow {
  category: string;
  item_count: number;
  total_quantity_on_hand: number;
  low_stock_count: number;
}

export interface InventoryReport {
  generated_at: string;
  total_items: number;
  total_low_stock: number;
  by_category: InventoryReportRow[];
}

// ---------------------------------------------------------------------------
// GIS / Operational Mapping
// ---------------------------------------------------------------------------
export interface MGRSPoint extends LatLng {
  mgrs: string | null;
}

export type CheckpointType = 'ENTRY' | 'EXIT' | 'INSPECTION' | 'TRAFFIC_CONTROL' | 'OTHER';
export type LZType = 'HELICOPTER' | 'FIXED_WING' | 'DROP_ZONE';
export type LZStatus = 'ACTIVE' | 'INACTIVE' | 'UNDER_SURVEY';
export type MapHazardType = 'MINEFIELD' | 'IED' | 'FLOODING' | 'LANDSLIDE' | 'CIVIL_UNREST' | 'OTHER';
export type MapHazardSeverity = 'LOW' | 'MEDIUM' | 'HIGH';
export type GisRouteType = 'SUPPLY' | 'PATROL' | 'EVACUATION' | 'OTHER';

export interface OverlayAORBoundary {
  id: string;
  name: string;
  unit: string | null;
  color: string;
  coordinates: LatLng[];
}

export interface OverlayCheckpoint extends MGRSPoint {
  id: string;
  name: string;
  checkpoint_type: CheckpointType;
  is_operational: boolean;
}

export interface OverlayLandingZone extends MGRSPoint {
  id: string;
  name: string;
  lz_type: LZType;
  status: LZStatus;
}

export interface OverlayHazard extends MGRSPoint {
  id: string;
  name: string;
  hazard_type: MapHazardType;
  severity: MapHazardSeverity;
  radius_meters: number | null;
}

export interface OverlayRoute {
  id: string;
  name: string;
  route_type: GisRouteType;
  coordinates: LatLng[];
}

export interface OverlayVehicle extends MGRSPoint {
  id: string;
  label: string;
}

export interface OverlayMission extends MGRSPoint {
  id: string;
  label: string;
  status: string;
}

export interface MapLayerDef {
  id: string;
  name: string;
  layer_type: string;
  is_visible_by_default: boolean;
  color: string;
  description: string;
  is_active: boolean;
}

export interface OperationalOverlay {
  generated_at: string;
  layers: MapLayerDef[];
  aor_boundaries: OverlayAORBoundary[];
  checkpoints: OverlayCheckpoint[];
  landing_zones: OverlayLandingZone[];
  hazards: OverlayHazard[];
  routes: OverlayRoute[];
  vehicles: OverlayVehicle[];
  missions: OverlayMission[];
}

// ---------------------------------------------------------------------------
// Reports
// ---------------------------------------------------------------------------
export type ReportType = 'PERSONNEL' | 'VEHICLE' | 'FLIGHT' | 'MISSION' | 'RISK' | 'INVENTORY';

export interface ReportListItem {
  type: ReportType;
  label: string;
}

export interface ReportData {
  title: string;
  headers: string[];
  rows: (string | number)[][];
  row_count: number;
}

// ---------------------------------------------------------------------------
// Additions: reference data, accounts, and the remaining module records
// ---------------------------------------------------------------------------
export interface Section {
  id: string;
  name: string;
  code: string;
  unit: string;
  unit_name: string;
  description: string;
  is_active: boolean;
}

export interface VehicleLocationUpdate {
  id: string;
  vehicle: string;
  location_display: LatLng | null;
  speed_kph: string | null;
  heading_degrees: string | null;
  recorded_at: string;
}

export interface AmmunitionIssuance {
  id: string;
  ammunition_stock: string;
  ammunition_type: string;
  issued_to: string;
  issued_to_name: string;
  issued_by: string | null;
  quantity: number;
  issue_date: string;
  purpose: string;
  remarks: string;
  is_active: boolean;
  created_at: string;
}

export type InspectionResult = 'PASSED' | 'FAILED' | 'NEEDS_MAINTENANCE';

export interface ArmoryInspection {
  id: string;
  firearm: string | null;
  firearm_serial: string | null;
  inspection_date: string;
  inspected_by: string;
  inspected_by_name: string;
  result: InspectionResult;
  findings: string;
  is_active: boolean;
  created_at: string;
}

export interface AORBoundary {
  id: string;
  name: string;
  unit: string | null;
  unit_name: string | null;
  boundary: LatLng[] | null;
  color: string;
  description: string;
  is_active: boolean;
  created_at: string;
}

export interface Checkpoint {
  id: string;
  name: string;
  checkpoint_type: CheckpointType;
  location: MGRSPoint | null;
  unit: string | null;
  unit_name: string | null;
  is_operational: boolean;
  remarks: string;
  is_active: boolean;
  created_at: string;
}

export interface LandingZone {
  id: string;
  name: string;
  lz_type: LZType;
  location: MGRSPoint | null;
  status: LZStatus;
  unit: string | null;
  unit_name: string | null;
  capacity: string;
  surface_type: string;
  remarks: string;
  is_active: boolean;
  created_at: string;
}

export interface MapHazard {
  id: string;
  name: string;
  hazard_type: MapHazardType;
  location: MGRSPoint | null;
  radius_meters: number | null;
  severity: MapHazardSeverity;
  reported_by: string | null;
  reported_by_name: string | null;
  reported_at: string | null;
  is_resolved: boolean;
  description: string;
  is_active: boolean;
  created_at: string;
}

export interface GisRoute {
  id: string;
  name: string;
  route_type: GisRouteType;
  path: LatLng[] | null;
  unit: string | null;
  unit_name: string | null;
  description: string;
  is_active: boolean;
  created_at: string;
}

export interface UserWritePayload {
  mrm_authority?: string;
  mrm_designation?: string;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  role: UserRole;
  unit: string | null;
  section: string | null;
  phone_number: string;
  is_active: boolean;
  password?: string;
}
