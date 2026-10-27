import type { PaginatedResponse } from '@/types';
import type { ActivityEvent, AppNotification, AuthorityOption, CategoryInfo, MissionPlan, PersonBrief, RoleOption } from '@/types/missionOps';

import { apiClient } from './client';

type Params = Record<string, string | number | boolean | undefined>;
const clean = (p?: Params) => (p ? Object.fromEntries(Object.entries(p).filter(([, v]) => v !== undefined && v !== '')) : undefined);
const BASE = '/missions/profiles';

export const missionOpsApi = {
  categories: () => apiClient.get<{ categories: CategoryInfo[]; roles: RoleOption[] }>(`${BASE}/categories/`).then((r) => r.data),
  authorities: (unit: string) => apiClient.get<AuthorityOption[]>(`${BASE}/authorities/`, { params: { unit } }).then((r) => r.data),
  get: (id: string) => apiClient.get<MissionPlan>(`${BASE}/${id}/`).then((r) => r.data),
  create: (payload: unknown) => apiClient.post<MissionPlan>(`${BASE}/`, payload).then((r) => r.data),
  update: (id: string, payload: unknown) => apiClient.patch<MissionPlan>(`${BASE}/${id}/`, payload).then((r) => r.data),
  submit: (id: string) => apiClient.post<MissionPlan>(`${BASE}/${id}/submit-mission/`).then((r) => r.data),
  approve: (id: string, comments?: string) => apiClient.post<MissionPlan>(`${BASE}/${id}/approve-mission/`, { comments }).then((r) => r.data),
  reject: (id: string, comments: string) => apiClient.post<MissionPlan>(`${BASE}/${id}/reject-mission/`, { comments }).then((r) => r.data),
  mrmCandidates: (id: string) => apiClient.get<PersonBrief[]>(`${BASE}/${id}/mrm-candidates/`).then((r) => r.data),
  activity: (id: string) => apiClient.get<ActivityEvent[]>(`${BASE}/${id}/activity/`).then((r) => r.data),
  list: (params?: Params) => apiClient.get<PaginatedResponse<unknown>>(`${BASE}/`, { params: clean(params) }).then((r) => r.data),
};

export const notificationsApi = {
  list: (params?: Params) => apiClient.get<PaginatedResponse<AppNotification>>('/notifications/', { params: clean(params) }).then((r) => r.data),
  unreadCount: () => apiClient.get<{ count: number }>('/notifications/unread-count/').then((r) => r.data.count),
  read: (id: string) => apiClient.post<AppNotification>(`/notifications/${id}/read/`).then((r) => r.data),
  readAll: () => apiClient.post<{ updated: number }>('/notifications/read-all/').then((r) => r.data),
};

/** MGRS <-> coordinates. The server is authoritative; invalid input resolves to a readable message. */
export const coordsApi = {
  parseMgrs: (mgrs: string) =>
    apiClient
      .get<{ lat: number; lng: number; mgrs: string }>('/gis/mgrs-parse/', { params: { mgrs } })
      .then((r) => ({ ok: true as const, ...r.data }))
      .catch((e) => ({ ok: false as const, message: String(e?.response?.data?.mgrs?.[0] ?? 'That MGRS reference could not be read.') })),
  toMgrs: (lat: number, lng: number) =>
    apiClient.get<{ mgrs: string | null }>('/gis/mgrs-convert/', { params: { lat, lng } }).then((r) => r.data.mgrs ?? '').catch(() => ''),
};
