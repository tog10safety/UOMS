import type { ComponentType } from 'react';

import type { MissionCategoryKey, MissionPlan } from '@/types/missionOps';
import type { FieldErrors } from '@/utils/formErrors';
import {
  buildGroundPayload, emptyGroundForm, hydrateGroundForm, validateGroundForm, type GroundForm,
} from '@/utils/missionForm';

import AirOperationsForm from './AirOperationsForm';
import GroundOperationsForm, { type CategoryFormProps } from './GroundOperationsForm';

/**
 * Registry of mission categories. A category supplies its own form component, empty state, validator, payload builder
 * and a way to rebuild state from a saved mission — the editor and detail page know nothing category-specific.
 */
export interface CategoryModule<S> {
  key: MissionCategoryKey;
  Form: ComponentType<CategoryFormProps<S>>;
  empty: () => S;
  hydrate: (plan: MissionPlan, mrmReadyIds: Set<string>) => S;
  validate: (state: S, opts: { forSubmit: boolean }) => FieldErrors;
  payload: (state: S, clientRequestId?: string) => unknown;
  /** false while the category's form is pending requirements */
  ready: boolean;
}

const ground: CategoryModule<GroundForm> = {
  key: 'GROUND_OPERATIONS',
  Form: GroundOperationsForm,
  empty: emptyGroundForm,
  hydrate: (plan, ready) => hydrateGroundForm(plan, ready),
  validate: (state, opts) => validateGroundForm(state, opts),
  payload: buildGroundPayload,
  ready: true,
};

const air: CategoryModule<Record<string, never>> = {
  key: 'AIR_OPERATIONS',
  Form: AirOperationsForm,
  empty: () => ({}),
  hydrate: () => ({}),
  validate: () => ({ _general: 'Air Operations missions cannot be created yet.' }),
  payload: () => ({ category: 'AIR_OPERATIONS' }),
  ready: false,
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const CATEGORY_MODULES: Record<MissionCategoryKey, CategoryModule<any>> = {
  GROUND_OPERATIONS: ground,
  AIR_OPERATIONS: air,
};
