import { ReactNode, useCallback, useEffect, useMemo, useState } from 'react';

import { useToast } from '@/contexts/ToastContext';
import { extractApiError } from '@/utils/errors';

import ConfirmDialog from './ConfirmDialog';
import { activeBadge } from './FormFields';
import RecordFormModal, { FieldDef } from './RecordForm';

export type { FieldDef, FieldType } from './RecordForm';

export interface ColumnDef<T> {
  header: string;
  render: (row: T) => ReactNode;
  className?: string;
}


interface ResourceManagerProps<T extends { id: string }> {
  title?: string;
  /** Singular noun used in dialogs and toasts, e.g. "rank". */
  noun: string;
  columns: ColumnDef<T>[];
  fields: FieldDef[];
  load: (params: Record<string, string | number | boolean>) => Promise<T[]>;
  create?: (payload: any) => Promise<unknown>;
  update?: (id: string, payload: any) => Promise<unknown>;
  remove?: (id: string) => Promise<unknown>;
  canCreate?: boolean;
  canEdit?: boolean;
  canDelete?: boolean;
  /** Word shown on the destructive button — "Archive" (soft delete) or "Delete" (permanent). */
  removeVerb?: 'Archive' | 'Delete' | 'Deactivate';
  rowLabel: (row: T) => string;
  /** Load the full record before editing (list serializers are often trimmed down). */
  fetchForEdit?: (row: T) => Promise<any>;
  extraRowActions?: (row: T, reload: () => void) => ReactNode;
  /** Per-row veto for the destructive action (e.g. an admin cannot deactivate themselves). */
  canDeleteRow?: (row: T) => boolean;
  /** Per-row veto for editing (e.g. records from another unit are read-only). */
  canEditRow?: (row: T) => boolean;
  toolbar?: ReactNode;
  /** Extra query params (filters) — a change triggers a reload. */
  extraParams?: Record<string, string | number | boolean>;
  searchPlaceholder?: string;
  /** Allows hiding/showing soft-deleted rows and restoring them. Default true. */
  supportsArchive?: boolean;
  /** Called after any successful create/update/remove/restore. */
  onChanged?: () => void;
  /** Bump to force a reload from the outside. */
  refreshKey?: number;
  emptyText?: string;
  /** Last chance to adjust the payload before it is sent. */
  transformPayload?: (payload: Record<string, any>, mode: 'create' | 'edit') => Record<string, any>;
  addLabel?: string;
  formWidth?: 'sm' | 'md' | 'lg';
}

export default function ResourceManager<T extends { id: string }>(props: ResourceManagerProps<T>) {
  const {
    title, noun, columns, fields, load, create, update, remove, rowLabel, fetchForEdit, extraRowActions, canDeleteRow, canEditRow, toolbar,
    extraParams, searchPlaceholder, onChanged, refreshKey, transformPayload,
  } = props;
  const canCreate = !!(props.canCreate && create);
  const canEdit = !!(props.canEdit && update);
  const canDelete = !!(props.canDelete && remove);
  const supportsArchive = props.supportsArchive ?? true;
  const removeVerb = props.removeVerb ?? 'Archive';
  const { showSuccess, showError } = useToast();

  const [rows, setRows] = useState<T[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [showArchived, setShowArchived] = useState(false);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<T | null>(null);
  // Full record loaded for editing (list serializers are often trimmed down).
  const [editRecord, setEditRecord] = useState<any>(null);

  const [pendingRemove, setPendingRemove] = useState<T | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const paramsKey = JSON.stringify(extraParams ?? {});

  const reload = useCallback(async () => {
    try {
      const params: Record<string, string | number | boolean> = { page_size: 200, ...(extraParams ?? {}) };
      if (search.trim()) params.search = search.trim();
      setRows(await load(params));
      setError('');
    } catch (err) {
      setError(extractApiError(err, `Unable to load ${noun} data.`));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load, search, paramsKey, noun]);

  useEffect(() => {
    setIsLoading(true);
    const timer = setTimeout(() => reload().finally(() => setIsLoading(false)), search ? 300 : 0);
    return () => clearTimeout(timer);
  }, [reload, refreshKey]);

  const isActive = (row: T) => (row as any).is_active !== false;
  const visibleRows = useMemo(
    () => (supportsArchive && !showArchived ? rows.filter(isActive) : rows),
    [rows, showArchived, supportsArchive],
  );
  const hasArchived = rows.some((r) => !isActive(r));

  const afterChange = async () => {
    await reload();
    onChanged?.();
  };

  const openCreate = () => {
    setEditing(null);
    setEditRecord(null);
    setFormOpen(true);
  };

  const openEdit = async (row: T) => {
    try {
      const record = fetchForEdit ? await fetchForEdit(row) : row;
      setEditing(row);
      setEditRecord(record);
      setFormOpen(true);
    } catch (err) {
      showError(extractApiError(err, `Unable to load ${noun} details.`));
    }
  };

  const handleSubmit = async (body: unknown, mode: 'create' | 'edit') => {
    if (mode === 'edit' && editing) {
      await update!(editing.id, body);
      showSuccess(`${rowLabel(editing)} updated successfully.`);
    } else {
      await create!(body);
      showSuccess(`New ${noun} created successfully.`);
    }
    setFormOpen(false);
    await afterChange();
  };

  const confirmRemove = async () => {
    if (!pendingRemove) return;
    setIsBusy(true);
    try {
      await remove!(pendingRemove.id);
      showSuccess(`${rowLabel(pendingRemove)} ${removeVerb === 'Delete' ? 'deleted' : removeVerb === 'Deactivate' ? 'deactivated' : 'archived'}.`);
      setPendingRemove(null);
      await afterChange();
    } catch (err) {
      showError(extractApiError(err, 'You do not have permission to perform this action.'));
    } finally {
      setIsBusy(false);
    }
  };

  const restore = async (row: T) => {
    try {
      await update!(row.id, { is_active: true });
      showSuccess(`${rowLabel(row)} restored.`);
      await afterChange();
    } catch (err) {
      showError(extractApiError(err, 'Unable to restore this record.'));
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          {title && <p className="ops-label">{title}</p>}
          {searchPlaceholder && (
            <input
              type="text" placeholder={searchPlaceholder} value={search} onChange={(e) => setSearch(e.target.value)}
              className="w-64 rounded-md border border-ops-border bg-ops-panelLight px-3 py-1.5 text-xs text-ops-text outline-none focus:border-ops-accent"
            />
          )}
          {toolbar}
        </div>
        <div className="flex items-center gap-3">
          {supportsArchive && hasArchived && (
            <label className="flex cursor-pointer items-center gap-1.5 text-xs text-ops-textDim">
              <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} className="rounded border-ops-border" />
              Show archived
            </label>
          )}
          <span className="text-xs text-ops-textDim">{visibleRows.length} record(s)</span>
          {canCreate && (
            <button onClick={openCreate} className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg">
              {props.addLabel ?? `+ Add ${noun.charAt(0).toUpperCase()}${noun.slice(1)}`}
            </button>
          )}
        </div>
      </div>

      {error && <p className="text-sm text-ops-danger">{error}</p>}

      <div className="ops-card overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-ops-panelLight text-xs uppercase tracking-wider text-ops-textDim">
            <tr>
              {columns.map((c) => (
                <th key={c.header} className="whitespace-nowrap px-4 py-3">{c.header}</th>
              ))}
              {supportsArchive && <th className="px-4 py-3">State</th>}
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {!isLoading && visibleRows.length === 0 && (
              <tr>
                <td colSpan={columns.length + 2} className="px-4 py-6 text-center text-ops-textDim">
                  {props.emptyText ?? `No ${noun} records found.`}
                </td>
              </tr>
            )}
            {visibleRows.map((row) => {
              const active = isActive(row);
              return (
                <tr key={row.id} className={`border-t border-ops-border hover:bg-ops-panelLight/50 ${active ? '' : 'opacity-60'}`}>
                  {columns.map((c) => (
                    <td key={c.header} className={`px-4 py-3 ${c.className ?? ''}`}>{c.render(row)}</td>
                  ))}
                  {supportsArchive && (
                    <td className="px-4 py-3">
                      <span className={activeBadge(active)}>{active ? 'Active' : 'Archived'}</span>
                    </td>
                  )}
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-3 whitespace-nowrap">
                      {extraRowActions?.(row, () => void afterChange())}
                      {canEdit && active && (canEditRow ? canEditRow(row) : true) && (
                        <button onClick={() => openEdit(row)} className="text-xs font-medium text-ops-textDim hover:text-ops-text">Edit</button>
                      )}
                      {canEdit && supportsArchive && !active && (
                        <button onClick={() => restore(row)} className="text-xs font-medium text-ops-success hover:underline">Restore</button>
                      )}
                      {canDelete && active && (canDeleteRow ? canDeleteRow(row) : true) && (
                        <button onClick={() => setPendingRemove(row)} className="text-xs font-medium text-ops-danger hover:underline">{removeVerb}</button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {formOpen && (
        <RecordFormModal
          title={`${editing ? 'Edit' : 'Add'} ${noun}`}
          width={props.formWidth ?? 'md'}
          fields={fields}
          record={editing ? editRecord : null}
          transformPayload={transformPayload}
          onSubmit={handleSubmit}
          onClose={() => setFormOpen(false)}
        />
      )}

      {pendingRemove && (
        <ConfirmDialog
          title={`${removeVerb} ${noun}`}
          message={
            removeVerb === 'Delete'
              ? `Permanently delete ${rowLabel(pendingRemove)}? This cannot be undone.`
              : `${removeVerb} ${rowLabel(pendingRemove)}? It will be hidden from active lists and can be restored later.`
          }
          confirmLabel={removeVerb}
          danger
          isBusy={isBusy}
          onConfirm={confirmRemove}
          onCancel={() => setPendingRemove(null)}
        />
      )}
    </div>
  );
}
