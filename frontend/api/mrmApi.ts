import type {
  Hazard, HazardImportResult, MrmAnalytics, MrmConfig, MrmDetail, MrmFeedbackItem, MrmFormInput, MrmListItem, MrmMe,
  RiskPreview, SafetyAssignment, SafetyUser, UnitLogoItem, WorkQueue,
} from '@/types/mrm';
import type { PaginatedResponse } from '@/types';

import { apiClient } from './client';

type Params = Record<string, string | number | boolean | undefined>;

const clean = (params?: Params) =>
  params ? Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== '')) : undefined;

/** Fetches a binary endpoint and either opens it in a tab or saves it. */
async function fetchFile(url: string, params?: Params, method: 'get' | 'post' = 'get', data?: unknown) {
  const response = await apiClient.request<Blob>({ url, method, params: clean(params), data, responseType: 'blob' });
  const disposition = String(response.headers['content-disposition'] ?? '');
  const match = /filename="?([^";]+)"?/i.exec(disposition);
  return { blob: response.data, filename: match?.[1] ?? 'download' };
}

export function saveBlob(blob: Blob, filename: string) {
  const objectUrl = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(objectUrl);
}

export function openBlob(blob: Blob) {
  const objectUrl = window.URL.createObjectURL(new Blob([blob], { type: 'application/pdf' }));
  window.open(objectUrl, '_blank', 'noopener');
  setTimeout(() => window.URL.revokeObjectURL(objectUrl), 60_000);
}

const BASE = '/mrm';

export const mrmApi = {
  config: () => apiClient.get<MrmConfig>(`${BASE}/config/`).then((r) => r.data),
  me: () => apiClient.get<MrmMe>(`${BASE}/me/`).then((r) => r.data),
  workQueue: () => apiClient.get<WorkQueue>(`${BASE}/work-queue/`).then((r) => r.data),

  uploadSignature: (file: File) => {
    const body = new FormData();
    body.append('signature', file);
    return apiClient.post(`${BASE}/signature/`, body, { headers: { 'Content-Type': 'multipart/form-data' } }).then((r) => r.data);
  },
  deleteSignature: () => apiClient.delete(`${BASE}/signature/`),
  signatureImage: () => fetchFile(`${BASE}/signature/`),

  // ---- hazard registry ------------------------------------------------------
  hazards: {
    list: (params?: Params) => apiClient.get<PaginatedResponse<Hazard>>(`${BASE}/hazards/`, { params: clean(params) }).then((r) => r.data),
    pickable: (params?: Params) =>
      apiClient.get<PaginatedResponse<Hazard>>(`${BASE}/hazards/pickable/`, { params: clean(params) }).then((r) => r.data),
    create: (payload: unknown) => apiClient.post<Hazard>(`${BASE}/hazards/`, payload).then((r) => r.data),
    update: (id: string, payload: unknown) => apiClient.patch<Hazard>(`${BASE}/hazards/${id}/`, payload).then((r) => r.data),
    remove: (id: string) => apiClient.delete(`${BASE}/hazards/${id}/`),
    bulkDelete: (ids: string[]) =>
      apiClient.post<{ deleted: number; skipped: { id: string; reason: string }[] }>(`${BASE}/hazards/bulk-delete/`, { ids }).then((r) => r.data),
    activityCodes: () => apiClient.get<string[]>(`${BASE}/hazards/activity-codes/`).then((r) => r.data),
    export: (params?: Params) => fetchFile(`${BASE}/hazards/export/`, params),
    template: () => fetchFile(`${BASE}/hazards/import-template/`),
    import: (file: File, opts: { overwrite: boolean; unit?: string }) => {
      const body = new FormData();
      body.append('file', file);
      body.append('overwrite', String(opts.overwrite));
      if (opts.unit) body.append('unit', opts.unit);
      return apiClient
        .post<HazardImportResult>(`${BASE}/hazards/import/`, body, { headers: { 'Content-Type': 'multipart/form-data' } })
        .then((r) => r.data);
    },
  },

  // ---- MRM forms --------------------------------------------------------------
  forms: {
    list: (params?: Params) => apiClient.get<PaginatedResponse<MrmListItem>>(`${BASE}/forms/`, { params: clean(params) }).then((r) => r.data),
    get: (id: string) => apiClient.get<MrmDetail>(`${BASE}/forms/${id}/`).then((r) => r.data),
    create: (payload: MrmFormInput) => apiClient.post<MrmDetail>(`${BASE}/forms/`, payload).then((r) => r.data),
    update: (id: string, payload: Partial<MrmFormInput>) => apiClient.patch<MrmDetail>(`${BASE}/forms/${id}/`, payload).then((r) => r.data),
    archive: (id: string) => apiClient.delete(`${BASE}/forms/${id}/`),

    calculateRisk: (hazards: MrmFormInput['hazards'], unit?: string | null) =>
      apiClient.post<RiskPreview>(`${BASE}/forms/calculate-risk/`, { hazards, unit }).then((r) => r.data),
    evaluators: (unit?: string | null) =>
      apiClient.get<{ id: string; name: string; unit: string | null }[]>(`${BASE}/forms/evaluators/`, { params: clean({ unit: unit ?? undefined }) }).then((r) => r.data),
    people: (q: string, unit?: string | null) =>
      apiClient
        .get<{ id: string; name: string; username: string; service_number: string }[]>(`${BASE}/forms/people/`, { params: clean({ q, unit: unit ?? undefined }) })
        .then((r) => r.data),

    submit: (id: string) => apiClient.post<MrmDetail>(`${BASE}/forms/${id}/submit/`).then((r) => r.data),
    review: (id: string, payload: { review_status: string; review_notes?: string; auto_sign?: boolean }) =>
      apiClient.post<MrmDetail>(`${BASE}/forms/${id}/review/`, payload).then((r) => r.data),
    approve: (id: string, comments?: string) => apiClient.post<MrmDetail>(`${BASE}/forms/${id}/approve/`, { comments }).then((r) => r.data),
    sign: (id: string) => apiClient.post<MrmDetail>(`${BASE}/forms/${id}/sign/`).then((r) => r.data),
    reassignReviewer: (id: string, reviewer: string) =>
      apiClient.post<MrmDetail>(`${BASE}/forms/${id}/reassign-reviewer/`, { reviewer }).then((r) => r.data),
    authorityCandidates: (id: string) =>
      apiClient
        .get<{ required: string; candidates: { id: string; name: string; unit: string | null }[] }>(`${BASE}/forms/${id}/authority-candidates/`)
        .then((r) => r.data),
    reassignAuthority: (id: string, authority?: string | null) =>
      apiClient.post<MrmDetail>(`${BASE}/forms/${id}/reassign-authority/`, { authority }).then((r) => r.data),

    pdf: (id: string) => fetchFile(`${BASE}/forms/${id}/pdf/`, { inline: 1 }),
    regeneratePdf: (id: string) => apiClient.post<MrmDetail>(`${BASE}/forms/${id}/regenerate-pdf/`).then((r) => r.data),

    tag: (id: string, user: string, role: string) => apiClient.post(`${BASE}/forms/${id}/personnel/`, { user, role }).then((r) => r.data),
    untag: (id: string, tagId: string) => apiClient.delete(`${BASE}/forms/${id}/personnel/${tagId}/`),
    closeFeedback: (id: string) => apiClient.post<MrmDetail>(`${BASE}/forms/${id}/close-feedback/`).then((r) => r.data),
    remind: (id: string) =>
      apiClient.get<{ pending: { user: string; name: string; role: string }[] }>(`${BASE}/forms/${id}/remind/`).then((r) => r.data),
    feedback: (id: string) => apiClient.get<MrmFeedbackItem[]>(`${BASE}/forms/${id}/feedback/`).then((r) => r.data),
    giveFeedback: (id: string, payload: Record<string, unknown>) =>
      apiClient.post<MrmFeedbackItem>(`${BASE}/forms/${id}/feedback/`, payload).then((r) => r.data),
  },

  // ---- feedback inbox ---------------------------------------------------------
  feedback: {
    list: (params?: Params) =>
      apiClient.get<PaginatedResponse<MrmFeedbackItem>>(`${BASE}/feedback/`, { params: clean(params) }).then((r) => r.data),
    mine: () =>
      apiClient
        .get<{ stats: { total_tagged: number; pending_feedback: number; completed_feedback: number }; pending: MrmListItem[]; completed: MrmFeedbackItem[] }>(
          `${BASE}/feedback/mine/`,
        )
        .then((r) => r.data),
    review: (id: string, payload: Record<string, unknown>) =>
      apiClient.post<MrmFeedbackItem>(`${BASE}/feedback/${id}/review/`, payload).then((r) => r.data),
    pendingCount: () => apiClient.get<{ count: number }>(`${BASE}/feedback/pending-count/`).then((r) => r.data.count),
  },

  // ---- safety office --------------------------------------------------------
  safety: {
    users: (params?: Params) =>
      apiClient.get<PaginatedResponse<SafetyUser>>(`${BASE}/safety/users/`, { params: clean(params) }).then((r) => r.data),
    toggleActive: (id: string) => apiClient.post<SafetyUser>(`${BASE}/safety/users/${id}/toggle-active/`).then((r) => r.data),
    resetPassword: (id: string, new_password: string, confirm_password: string) =>
      apiClient.post<{ detail: string }>(`${BASE}/safety/users/${id}/reset-password/`, { new_password, confirm_password }).then((r) => r.data),
    assignments: () =>
      apiClient.get<PaginatedResponse<SafetyAssignment>>(`${BASE}/safety/assignments/`, { params: { page_size: 200 } }).then((r) => r.data),
    createAssignment: (payload: { user: string; unit: string; is_primary?: boolean }) =>
      apiClient.post<SafetyAssignment>(`${BASE}/safety/assignments/`, payload).then((r) => r.data),
    removeAssignment: (id: string) => apiClient.delete(`${BASE}/safety/assignments/${id}/`),
    analytics: (params?: Params) => apiClient.get<MrmAnalytics>(`${BASE}/analytics/`, { params: clean(params) }).then((r) => r.data),
  },

  logos: {
    list: () => apiClient.get<UnitLogoItem[]>(`${BASE}/unit-logos/`).then((r) => r.data),
    upload: (unit: string, file: File) => {
      const body = new FormData();
      body.append('unit', unit);
      body.append('image', file);
      return apiClient.post(`${BASE}/unit-logos/`, body, { headers: { 'Content-Type': 'multipart/form-data' } }).then((r) => r.data);
    },
    remove: (id: string) => apiClient.delete(`${BASE}/unit-logos/${id}/`),
  },
};
