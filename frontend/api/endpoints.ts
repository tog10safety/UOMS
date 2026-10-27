import { apiClient } from './client';
import type {
  AircraftItem,
  AmmunitionIssuance,
  AmmunitionStock,
  AORBoundary,
  ArmoryInspection,
  ArmoryTransaction,
  Checkpoint,
  ConsolidatedAOR,
  DashboardSummary,
  Firearm,
  FirearmIssuance,
  FlightCrewAssignment,
  FlightDetail,
  FlightListItem,
  FlightWaypoint,
  GisRoute,
  HazardAssessment,
  InventoryItem,
  InventoryReport,
  InventoryTransaction,
  ItemCategory,
  LandingZone,
  LatLng,
  LoginResponse,
  MapHazard,
  MapLayerDef,
  MissionApprovalLogEntry,
  MissionDetail,
  MissionListItem,
  OperationalOverlay,
  PaginatedResponse,
  PersonnelDetail,
  PersonnelListItem,
  Position,
  Qualification,
  Rank,
  ReportData,
  ReportListItem,
  ReportType,
  Section,
  Trip,
  Unit,
  User,
  UserWritePayload,
  VehicleDetail,
  VehicleListItem,
  VehicleLocationUpdate,
  VehicleMaintenanceRecord,
} from '@/types';

type Params = Record<string, string | number | boolean>;

// multipart bodies (file uploads) need the JSON default header overridden.
const bodyConfig = (payload: unknown) =>
  typeof FormData !== 'undefined' && payload instanceof FormData
    ? { headers: { 'Content-Type': 'multipart/form-data' } }
    : undefined;

/** Standard list/get/create/update/delete wrapper around a DRF ModelViewSet route. */
function crud<T>(path: string) {
  return {
    list: (params?: Params) => apiClient.get<PaginatedResponse<T>>(`${path}/`, { params }).then((r) => r.data),
    get: (id: string) => apiClient.get<T>(`${path}/${id}/`).then((r) => r.data),
    create: (payload: unknown) => apiClient.post<T>(`${path}/`, payload, bodyConfig(payload)).then((r) => r.data),
    update: (id: string, payload: unknown) =>
      apiClient.patch<T>(`${path}/${id}/`, payload, bodyConfig(payload)).then((r) => r.data),
    remove: (id: string) => apiClient.delete(`${path}/${id}/`),
  };
}

export const authApi = {
  login: (username: string, password: string) =>
    apiClient.post<LoginResponse>('/auth/login/', { username, password }).then((r) => r.data),

  logout: (refresh: string) => apiClient.post('/auth/logout/', { refresh }),

  me: () => apiClient.get<User>('/auth/me/').then((r) => r.data),

  /** PATCH /auth/me/ — only ever send the self-service fields below. */
  updateProfile: (payload: Pick<User, 'first_name' | 'last_name' | 'email' | 'phone_number'>) =>
    apiClient.patch<User>('/auth/me/', payload).then((r) => r.data),

  changePassword: (current_password: string, new_password: string) =>
    apiClient.post('/auth/change-password/', { current_password, new_password }),
};

export const dashboardApi = {
  getSummary: () => apiClient.get<DashboardSummary>('/dashboard/summary/').then((r) => r.data),
};

const personnelCrud = crud<PersonnelDetail>('/personnel/records');

export const personnelApi = {
  list: (params?: Params) =>
    apiClient.get<PaginatedResponse<PersonnelListItem>>('/personnel/records/', { params }).then((r) => r.data),
  get: personnelCrud.get,
  create: personnelCrud.create,
  update: personnelCrud.update,
  archive: personnelCrud.remove,
};

export const ranksApi = crud<Rank>('/personnel/ranks');
export const sectionsApi = crud<Section>('/personnel/sections');
export const positionsApi = crud<Position>('/personnel/positions');
export const qualificationsApi = crud<Qualification>('/personnel/qualifications');

export const unitsApi = {
  list: () =>
    apiClient.get<PaginatedResponse<Unit>>('/personnel/units/', { params: { page_size: 200 } }).then((r) => r.data),

  get: (id: string) => apiClient.get<Unit>(`/personnel/units/${id}/`).then((r) => r.data),

  create: (payload: Partial<Unit>) => apiClient.post<Unit>('/personnel/units/', payload).then((r) => r.data),

  update: (id: string, payload: Partial<Unit>) =>
    apiClient.patch<Unit>(`/personnel/units/${id}/`, payload).then((r) => r.data),

  archive: (id: string) => apiClient.delete(`/personnel/units/${id}/`),

  restore: (id: string) => apiClient.patch<Unit>(`/personnel/units/${id}/`, { is_active: true }).then((r) => r.data),
};

const usersCrud = crud<User>('/auth/users');

export const usersApi = {
  list: (params?: Params) => usersCrud.list(params),
  get: usersCrud.get,
  create: (payload: UserWritePayload) => usersCrud.create(payload),
  update: (id: string, payload: Partial<UserWritePayload>) => usersCrud.update(id, payload),
  /** Soft delete — the backend deactivates the account rather than removing it. */
  deactivate: usersCrud.remove,
  reactivate: (id: string) => usersCrud.update(id, { is_active: true }),
};

// ---------------------------------------------------------------------------
// Vehicle Tracking and Monitoring
// ---------------------------------------------------------------------------
export const vehiclesApi = {
  list: (params?: Record<string, string | number | boolean>) =>
    apiClient
      .get<PaginatedResponse<VehicleListItem>>('/vehicles/registry/', { params })
      .then((r) => r.data),

  get: (id: string) => apiClient.get<VehicleDetail>(`/vehicles/registry/${id}/`).then((r) => r.data),

  create: (payload: Partial<VehicleDetail>) =>
    apiClient.post<VehicleDetail>('/vehicles/registry/', payload).then((r) => r.data),

  update: (id: string, payload: Partial<VehicleDetail>) =>
    apiClient.patch<VehicleDetail>(`/vehicles/registry/${id}/`, payload).then((r) => r.data),

  archive: (id: string) => apiClient.delete(`/vehicles/registry/${id}/`),

  dispatch: (id: string, missionId?: string) =>
    apiClient.post<VehicleDetail>(`/vehicles/registry/${id}/dispatch/`, missionId ? { mission: missionId } : {}).then((r) => r.data),

  returnVehicle: (id: string) =>
    apiClient.post<VehicleDetail>(`/vehicles/registry/${id}/return/`).then((r) => r.data),

  reportLocation: (id: string, payload: { location: LatLng; speed_kph?: number; heading_degrees?: number }) =>
    apiClient.post(`/vehicles/registry/${id}/location/`, payload).then((r) => r.data),

  locationHistory: (id: string) =>
    apiClient.get<VehicleLocationUpdate[]>(`/vehicles/registry/${id}/location-history/`).then((r) => r.data),

  trips: (params?: Record<string, string | number | boolean>) =>
    apiClient.get<PaginatedResponse<Trip>>('/vehicles/trips/', { params }).then((r) => r.data),

  getTrip: (id: string) => apiClient.get<Trip>(`/vehicles/trips/${id}/`).then((r) => r.data),

  createTrip: (payload: Partial<Trip>) => apiClient.post<Trip>('/vehicles/trips/', payload).then((r) => r.data),

  updateTrip: (id: string, payload: Partial<Trip>) =>
    apiClient.patch<Trip>(`/vehicles/trips/${id}/`, payload).then((r) => r.data),

  /** Hard delete — the backend does not soft-delete trips. */
  deleteTrip: (id: string) => apiClient.delete(`/vehicles/trips/${id}/`),

  maintenanceRecords: (params?: Record<string, string | number | boolean>) =>
    apiClient
      .get<PaginatedResponse<VehicleMaintenanceRecord>>('/vehicles/maintenance/', { params })
      .then((r) => r.data),

  getMaintenanceRecord: (id: string) =>
    apiClient.get<VehicleMaintenanceRecord>(`/vehicles/maintenance/${id}/`).then((r) => r.data),

  createMaintenanceRecord: (payload: Partial<VehicleMaintenanceRecord>) =>
    apiClient.post<VehicleMaintenanceRecord>('/vehicles/maintenance/', payload).then((r) => r.data),

  updateMaintenanceRecord: (id: string, payload: Partial<VehicleMaintenanceRecord>) =>
    apiClient.patch<VehicleMaintenanceRecord>(`/vehicles/maintenance/${id}/`, payload).then((r) => r.data),

  /** Hard delete — the backend does not soft-delete maintenance records. */
  deleteMaintenanceRecord: (id: string) => apiClient.delete(`/vehicles/maintenance/${id}/`),
};

// ---------------------------------------------------------------------------
// Aircraft Flying Monitoring
// ---------------------------------------------------------------------------
export const aircraftApi = {
  list: (params?: Record<string, string | number | boolean>) =>
    apiClient.get<PaginatedResponse<AircraftItem>>('/aircraft/registry/', { params }).then((r) => r.data),

  createAircraft: (payload: Partial<AircraftItem>) =>
    apiClient.post<AircraftItem>('/aircraft/registry/', payload).then((r) => r.data),

  updateAircraft: (id: string, payload: Partial<AircraftItem>) =>
    apiClient.patch<AircraftItem>(`/aircraft/registry/${id}/`, payload).then((r) => r.data),

  archiveAircraft: (id: string) => apiClient.delete(`/aircraft/registry/${id}/`),

  flights: (params?: Record<string, string | number | boolean>) =>
    apiClient.get<PaginatedResponse<FlightListItem>>('/aircraft/flights/', { params }).then((r) => r.data),

  getFlight: (id: string) => apiClient.get<FlightDetail>(`/aircraft/flights/${id}/`).then((r) => r.data),

  createFlight: (payload: Partial<FlightDetail>) =>
    apiClient.post<FlightDetail>('/aircraft/flights/', payload).then((r) => r.data),

  updateFlight: (id: string, payload: Partial<FlightDetail>) =>
    apiClient.patch<FlightDetail>(`/aircraft/flights/${id}/`, payload).then((r) => r.data),

  cancelFlight: (id: string) => apiClient.delete(`/aircraft/flights/${id}/`),

  markDeparted: (id: string) => apiClient.post<FlightDetail>(`/aircraft/flights/${id}/depart/`).then((r) => r.data),

  markArrived: (id: string) => apiClient.post<FlightDetail>(`/aircraft/flights/${id}/arrive/`).then((r) => r.data),

  // Crew — nested action for list/add, plain viewset for edit/remove.
  flightCrew: (flightId: string) =>
    apiClient.get<FlightCrewAssignment[]>(`/aircraft/flights/${flightId}/crew/`).then((r) => r.data),

  addFlightCrew: (flightId: string, payload: { personnel: string; crew_role: FlightCrewAssignment['crew_role'] }) =>
    apiClient.post<FlightCrewAssignment>(`/aircraft/flights/${flightId}/crew/`, payload).then((r) => r.data),

  crewAssignments: (params?: Params) =>
    apiClient
      .get<PaginatedResponse<FlightCrewAssignment>>('/aircraft/crew-assignments/', { params })
      .then((r) => r.data),

  updateCrewAssignment: (id: string, payload: Partial<FlightCrewAssignment>) =>
    apiClient.patch<FlightCrewAssignment>(`/aircraft/crew-assignments/${id}/`, payload).then((r) => r.data),

  removeCrewAssignment: (id: string) => apiClient.delete(`/aircraft/crew-assignments/${id}/`),

  // Waypoints — the backend only exposes list + add.
  flightWaypoints: (flightId: string) =>
    apiClient.get<FlightWaypoint[]>(`/aircraft/flights/${flightId}/waypoints/`).then((r) => r.data),

  addFlightWaypoint: (
    flightId: string,
    payload: { sequence: number; name: string; location_input?: LatLng; eta?: string | null; notes?: string },
  ) => apiClient.post<FlightWaypoint>(`/aircraft/flights/${flightId}/waypoints/`, payload).then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Mission Risk Management
// ---------------------------------------------------------------------------
export const missionsApi = {
  list: (params?: Record<string, string | number | boolean>) =>
    apiClient.get<PaginatedResponse<MissionListItem>>('/missions/profiles/', { params }).then((r) => r.data),

  get: (id: string) => apiClient.get<MissionDetail>(`/missions/profiles/${id}/`).then((r) => r.data),

  create: (payload: Partial<MissionDetail>) =>
    apiClient.post<MissionDetail>('/missions/profiles/', payload).then((r) => r.data),

  update: (id: string, payload: Partial<MissionDetail>) =>
    apiClient.patch<MissionDetail>(`/missions/profiles/${id}/`, payload).then((r) => r.data),

  /** Soft delete — marks the mission inactive. */
  archive: (id: string) => apiClient.delete(`/missions/profiles/${id}/`),

  restore: (id: string) =>
    apiClient.patch<MissionDetail>(`/missions/profiles/${id}/`, { is_active: true }).then((r) => r.data),

  submitForApproval: (id: string) =>
    apiClient.post<MissionDetail>(`/missions/profiles/${id}/submit-for-approval/`).then((r) => r.data),

  approve: (id: string, comments?: string) =>
    apiClient.post<MissionDetail>(`/missions/profiles/${id}/approve/`, { comments: comments ?? '' }).then((r) => r.data),

  reject: (id: string, comments: string) =>
    apiClient.post<MissionDetail>(`/missions/profiles/${id}/reject/`, { comments }).then((r) => r.data),

  hazards: (missionId: string) =>
    apiClient.get<HazardAssessment[]>(`/missions/profiles/${missionId}/hazards/`).then((r) => r.data),

  approvalLogs: (params?: Params) =>
    apiClient
      .get<PaginatedResponse<MissionApprovalLogEntry>>('/missions/approval-logs/', { params })
      .then((r) => r.data),

  addHazard: (missionId: string, payload: Partial<HazardAssessment>) =>
    apiClient.post<HazardAssessment>(`/missions/profiles/${missionId}/hazards/`, payload).then((r) => r.data),

  updateHazard: (hazardId: string, payload: Partial<HazardAssessment>) =>
    apiClient.patch<HazardAssessment>(`/missions/hazards/${hazardId}/`, payload).then((r) => r.data),

  deleteHazard: (hazardId: string) => apiClient.delete(`/missions/hazards/${hazardId}/`),
};

// ---------------------------------------------------------------------------
// Armory Management
// ---------------------------------------------------------------------------
export const armoryApi = {
  firearms: (params?: Record<string, string | number | boolean>) =>
    apiClient.get<PaginatedResponse<Firearm>>('/armory/firearms/', { params }).then((r) => r.data),

  createFirearm: (payload: Partial<Firearm>) =>
    apiClient.post<Firearm>('/armory/firearms/', payload).then((r) => r.data),

  updateFirearm: (id: string, payload: Partial<Firearm>) =>
    apiClient.patch<Firearm>(`/armory/firearms/${id}/`, payload).then((r) => r.data),

  getFirearm: (id: string) => apiClient.get<Firearm>(`/armory/firearms/${id}/`).then((r) => r.data),

  archiveFirearm: (id: string) => apiClient.delete(`/armory/firearms/${id}/`),

  restoreFirearm: (id: string) =>
    apiClient.patch<Firearm>(`/armory/firearms/${id}/`, { is_active: true }).then((r) => r.data),

  ammunition: (params?: Record<string, string | number | boolean>) =>
    apiClient.get<PaginatedResponse<AmmunitionStock>>('/armory/ammunition/', { params }).then((r) => r.data),

  createAmmunition: (payload: Partial<AmmunitionStock>) =>
    apiClient.post<AmmunitionStock>('/armory/ammunition/', payload).then((r) => r.data),

  updateAmmunition: (id: string, payload: Partial<AmmunitionStock>) =>
    apiClient.patch<AmmunitionStock>(`/armory/ammunition/${id}/`, payload).then((r) => r.data),

  issuances: (params?: Record<string, string | number | boolean>) =>
    apiClient.get<PaginatedResponse<FirearmIssuance>>('/armory/issuances/', { params }).then((r) => r.data),

  issueFirearm: (payload: Partial<FirearmIssuance>) =>
    apiClient.post<FirearmIssuance>('/armory/issuances/', payload).then((r) => r.data),

  returnFirearm: (issuanceId: string, payload?: { condition_on_return?: string; remarks?: string }) =>
    apiClient.post<FirearmIssuance>(`/armory/issuances/${issuanceId}/return/`, payload ?? {}).then((r) => r.data),

  getIssuance: (id: string) => apiClient.get<FirearmIssuance>(`/armory/issuances/${id}/`).then((r) => r.data),

  updateIssuance: (id: string, payload: Partial<FirearmIssuance>) =>
    apiClient.patch<FirearmIssuance>(`/armory/issuances/${id}/`, payload).then((r) => r.data),

  ammunitionIssuances: (params?: Params) =>
    apiClient
      .get<PaginatedResponse<AmmunitionIssuance>>('/armory/ammunition-issuances/', { params })
      .then((r) => r.data),

  issueAmmunition: (payload: Partial<AmmunitionIssuance>) =>
    apiClient.post<AmmunitionIssuance>('/armory/ammunition-issuances/', payload).then((r) => r.data),

  updateAmmunitionIssuance: (id: string, payload: Partial<AmmunitionIssuance>) =>
    apiClient.patch<AmmunitionIssuance>(`/armory/ammunition-issuances/${id}/`, payload).then((r) => r.data),

  inspections: (params?: Params) =>
    apiClient.get<PaginatedResponse<ArmoryInspection>>('/armory/inspections/', { params }).then((r) => r.data),

  getInspection: (id: string) =>
    apiClient.get<ArmoryInspection>(`/armory/inspections/${id}/`).then((r) => r.data),

  createInspection: (payload: Partial<ArmoryInspection>) =>
    apiClient.post<ArmoryInspection>('/armory/inspections/', payload).then((r) => r.data),

  updateInspection: (id: string, payload: Partial<ArmoryInspection>) =>
    apiClient.patch<ArmoryInspection>(`/armory/inspections/${id}/`, payload).then((r) => r.data),

  /** Hard delete — the backend does not soft-delete inspections. */
  deleteInspection: (id: string) => apiClient.delete(`/armory/inspections/${id}/`),

  transactions: () => apiClient.get<ArmoryTransaction[]>('/armory/transactions/').then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Inventory Management
// ---------------------------------------------------------------------------
export const inventoryApi = {
  categories: () => apiClient.get<PaginatedResponse<ItemCategory>>('/inventory/categories/', { params: { page_size: 200 } }).then((r) => r.data),

  getCategory: (id: string) => apiClient.get<ItemCategory>(`/inventory/categories/${id}/`).then((r) => r.data),

  createCategory: (payload: Partial<ItemCategory>) =>
    apiClient.post<ItemCategory>('/inventory/categories/', payload).then((r) => r.data),

  updateCategory: (id: string, payload: Partial<ItemCategory>) =>
    apiClient.patch<ItemCategory>(`/inventory/categories/${id}/`, payload).then((r) => r.data),

  /** Hard delete — the backend does not soft-delete categories. */
  deleteCategory: (id: string) => apiClient.delete(`/inventory/categories/${id}/`),

  getItem: (id: string) => apiClient.get<InventoryItem>(`/inventory/items/${id}/`).then((r) => r.data),

  restoreItem: (id: string) =>
    apiClient.patch<InventoryItem>(`/inventory/items/${id}/`, { is_active: true }).then((r) => r.data),

  items: (params?: Record<string, string | number | boolean>) =>
    apiClient.get<PaginatedResponse<InventoryItem>>('/inventory/items/', { params }).then((r) => r.data),

  createItem: (payload: Partial<InventoryItem>) =>
    apiClient.post<InventoryItem>('/inventory/items/', payload).then((r) => r.data),

  updateItem: (id: string, payload: Partial<InventoryItem>) =>
    apiClient.patch<InventoryItem>(`/inventory/items/${id}/`, payload).then((r) => r.data),

  archiveItem: (id: string) => apiClient.delete(`/inventory/items/${id}/`),

  transactions: (params?: Record<string, string | number | boolean>) =>
    apiClient
      .get<PaginatedResponse<InventoryTransaction>>('/inventory/transactions/', { params })
      .then((r) => r.data),

  createTransaction: (payload: Partial<InventoryTransaction>) =>
    apiClient.post<InventoryTransaction>('/inventory/transactions/', payload).then((r) => r.data),

  report: () => apiClient.get<InventoryReport>('/inventory/report/').then((r) => r.data),
};

// ---------------------------------------------------------------------------
// GIS / Operational Mapping
// ---------------------------------------------------------------------------
export const gisApi = {
  overlay: () => apiClient.get<OperationalOverlay>('/gis/overlay/').then((r) => r.data),

  convertToMgrs: (lat: number, lng: number) =>
    apiClient.get<{ lat: number; lng: number; mgrs: string | null }>('/gis/mgrs-convert/', { params: { lat, lng } }).then((r) => r.data),

  consolidatedAor: (unitId: string) =>
    apiClient.get<ConsolidatedAOR>('/gis/aor-boundaries/consolidated/', { params: { unit: unitId } }).then((r) => r.data),
};

export const aorBoundariesApi = crud<AORBoundary>('/gis/aor-boundaries');
export const checkpointsApi = crud<Checkpoint>('/gis/checkpoints');
export const landingZonesApi = crud<LandingZone>('/gis/landing-zones');
export const mapHazardsApi = crud<MapHazard>('/gis/hazards');
export const gisRoutesApi = crud<GisRoute>('/gis/routes');
export const mapLayersApi = crud<MapLayerDef>('/gis/layers');

// ---------------------------------------------------------------------------
// Reports
// ---------------------------------------------------------------------------
export const reportsApi = {
  list: () => apiClient.get<ReportListItem[]>('/reports/').then((r) => r.data),

  get: (type: ReportType) => apiClient.get<ReportData>(`/reports/${type}/`).then((r) => r.data),

  download: async (type: ReportType, format: 'pdf' | 'xlsx') => {
    const response = await apiClient.get(`/reports/${type}/export/`, {
      params: { format },
      responseType: 'blob',
    });
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    link.download = `${type.toLowerCase()}_report.${format}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },
};
