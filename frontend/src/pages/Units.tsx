import { FormEvent, useEffect, useMemo, useState } from 'react';

import { gisApi, unitsApi } from '@/api/endpoints';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import { useAuth } from '@/contexts/AuthContext';
import type { ConsolidatedAOR, Unit, UnitCategory } from '@/types';

const CATEGORY_ORDER: UnitCategory[] = ['HPAF', 'COMMAND', 'WING', 'GROUP', 'SQUADRON'];

const CATEGORY_BADGE: Record<UnitCategory, string> = {
  HPAF: 'bg-ops-danger/10 text-ops-danger',
  COMMAND: 'bg-ops-accent/10 text-ops-accent',
  WING: 'bg-ops-warning/10 text-ops-warning',
  GROUP: 'bg-ops-success/10 text-ops-success',
  SQUADRON: 'bg-ops-textDim/10 text-ops-textDim',
};

interface TreeNode extends Unit {
  children: TreeNode[];
}

function buildTree(units: Unit[]): TreeNode[] {
  const nodes = new Map<string, TreeNode>(units.map((u) => [u.id, { ...u, children: [] }]));
  const roots: TreeNode[] = [];

  nodes.forEach((node) => {
    if (node.parent_unit && nodes.has(node.parent_unit)) {
      nodes.get(node.parent_unit)!.children.push(node);
    } else {
      roots.push(node);
    }
  });

  return roots;
}

const emptyForm = { name: '', code: '', category: '' as UnitCategory | '', parent_unit: '', description: '' };

export default function Units() {
  const { hasRole, can } = useAuth();
  const [units, setUnits] = useState<Unit[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [isSaving, setIsSaving] = useState(false);
  const [consolidated, setConsolidated] = useState<ConsolidatedAOR | null>(null);
  const [consolidatedFor, setConsolidatedFor] = useState<string | null>(null);

  const canManage = hasRole('ADMIN', 'COMMANDER');
  const canArchive = can('PERSONNEL', 'DELETE');
  const [pendingArchive, setPendingArchive] = useState<Unit | null>(null);
  const [isArchiving, setIsArchiving] = useState(false);

  const load = () =>
    unitsApi
      .list()
      .then((data) => setUnits(data.results))
      .catch(() => setError('Unable to load units.'));

  useEffect(() => {
    setIsLoading(true);
    load().finally(() => setIsLoading(false));
  }, []);

  const tree = useMemo(() => buildTree(units), [units]);

  const openCreateForm = () => {
    setEditingId(null);
    setForm(emptyForm);
    setShowForm(true);
  };

  const openEditForm = (unit: Unit) => {
    setEditingId(unit.id);
    setForm({
      name: unit.name, code: unit.code, category: unit.category,
      parent_unit: unit.parent_unit ?? '', description: unit.description,
    });
    setShowForm(true);
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setError('');
    const payload = { ...form, parent_unit: form.parent_unit || null, category: form.category || undefined };
    try {
      if (editingId) await unitsApi.update(editingId, payload);
      else await unitsApi.create(payload);
      setShowForm(false);
      await load();
    } catch (err: any) {
      setError(err?.response?.data?.non_field_errors?.[0] ?? err?.response?.data?.detail ?? 'Unable to save unit — check for hierarchy conflicts.');
    } finally {
      setIsSaving(false);
    }
  };

  const runArchive = async () => {
    if (!pendingArchive) return;
    setIsArchiving(true);
    try {
      await unitsApi.archive(pendingArchive.id);
      setPendingArchive(null);
      await load();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Unable to archive unit.');
      setPendingArchive(null);
    } finally {
      setIsArchiving(false);
    }
  };

  const handleRestore = async (unit: Unit) => {
    try {
      await unitsApi.restore(unit.id);
      await load();
    } catch {
      setError('Unable to restore unit.');
    }
  };

  const handleViewConsolidated = async (unit: Unit) => {
    setConsolidatedFor(unit.id);
    setConsolidated(null);
    try {
      const data = await gisApi.consolidatedAor(unit.id);
      setConsolidated(data);
    } catch {
      setError('Unable to load consolidated AOR for this unit.');
    }
  };

  const renderNode = (node: TreeNode, depth: number) => (
    <div key={node.id}>
      <div
        className="flex items-center justify-between border-t border-ops-border py-2 hover:bg-ops-panelLight/50"
        style={{ paddingLeft: `${depth * 20 + 16}px` }}
      >
        <div className="flex items-center gap-3">
          <span className="font-mono text-xs text-ops-textDim">{node.code}</span>
          <span className={`text-sm ${node.is_active ? 'text-ops-text' : 'text-ops-textDim line-through'}`}>{node.name}</span>
          {!node.is_active && <span className="text-[10px] uppercase text-ops-textDim">archived</span>}
          {node.category && (
            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${CATEGORY_BADGE[node.category]}`}>
              {node.category_display}
            </span>
          )}
          {node.subordinate_count > 0 && (
            <span className="text-xs text-ops-textDim">({node.subordinate_count} subordinate{node.subordinate_count === 1 ? '' : 's'})</span>
          )}
        </div>
        <div className="flex items-center gap-3 pr-4">
          <button
            onClick={() => handleViewConsolidated(node)}
            className="text-xs font-medium text-ops-accent hover:underline"
          >
            View Consolidated AOR
          </button>
          {canManage && (
            <button onClick={() => openEditForm(node)} className="text-xs font-medium text-ops-textDim hover:text-ops-text">
              Edit
            </button>
          )}
          {canManage && !node.is_active && (
            <button onClick={() => handleRestore(node)} className="text-xs font-medium text-ops-success hover:underline">
              Restore
            </button>
          )}
          {canArchive && node.is_active && (
            <button onClick={() => setPendingArchive(node)} className="text-xs font-medium text-ops-danger hover:underline">
              Archive
            </button>
          )}
        </div>
      </div>
      {node.children.map((child) => renderNode(child, depth + 1))}
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-ops-textDim">
          Echelon hierarchy: HPAF → Command → Wing → Group → Squadron. A mother unit has visibility over every
          unit beneath it, and its AOR can be viewed as the consolidated union of its subordinates' AORs.
        </p>
        {canManage && (
          <button
            onClick={openCreateForm}
            className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg"
          >
            + Add Unit
          </button>
        )}
      </div>

      {error && <p className="text-sm text-ops-danger">{error}</p>}

      <div className="ops-card overflow-hidden">
        {isLoading && <p className="p-4 text-sm text-ops-textDim">Loading units…</p>}
        {!isLoading && tree.length === 0 && <p className="p-4 text-sm text-ops-textDim">No units found.</p>}
        {tree.map((root) => renderNode(root, 0))}
      </div>

      {consolidatedFor && (
        <div className="ops-card p-4">
          <div className="mb-2 flex items-center justify-between">
            <p className="ops-label">Consolidated AOR</p>
            <button onClick={() => setConsolidatedFor(null)} className="text-xs text-ops-textDim hover:text-ops-text">
              Close
            </button>
          </div>
          {!consolidated && <p className="text-sm text-ops-textDim">Computing union of subordinate AOR boundaries…</p>}
          {consolidated && (
            <div className="space-y-1 text-sm">
              <p className="text-ops-text">
                <span className="font-semibold">{consolidated.unit}</span>
                {consolidated.unit_category && <span className="text-ops-textDim"> ({consolidated.unit_category})</span>}
              </p>
              <p className="text-xs text-ops-textDim">
                Consolidated from {consolidated.source_boundary_count} AOR boundary(ies) across:{' '}
                {consolidated.source_units.join(', ') || '—'}
              </p>
              <p className="text-xs text-ops-textDim">
                Result: {consolidated.consolidated_boundary.length} polygon(s),{' '}
                {consolidated.consolidated_boundary.reduce((sum, ring) => sum + ring.length, 0)} total vertices.
              </p>
              {consolidated.consolidated_boundary.length === 0 && (
                <p className="text-xs text-ops-warning">No AOR boundaries defined for this unit or its subordinates yet.</p>
              )}
            </div>
          )}
        </div>
      )}

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <form onSubmit={handleSubmit} className="ops-card w-full max-w-md space-y-3 p-6">
            <p className="ops-label">{editingId ? 'Edit Unit' : 'Add Unit'}</p>

            <div>
              <label className="mb-1 block text-xs text-ops-textDim">Name *</label>
              <input
                required
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs text-ops-textDim">Code *</label>
              <input
                required
                value={form.code}
                onChange={(e) => setForm({ ...form, code: e.target.value })}
                className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs text-ops-textDim">Category (Echelon)</label>
              <select
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value as UnitCategory })}
                className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text"
              >
                <option value="">— Select —</option>
                {CATEGORY_ORDER.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="mb-1 block text-xs text-ops-textDim">Mother Unit (Parent)</label>
              <select
                value={form.parent_unit}
                onChange={(e) => setForm({ ...form, parent_unit: e.target.value })}
                className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text"
              >
                <option value="">— None (top level) —</option>
                {units.filter((u) => u.id !== editingId).map((u) => (
                  <option key={u.id} value={u.id}>{u.code} — {u.name}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="mb-1 block text-xs text-ops-textDim">Description</label>
              <textarea
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                rows={2}
                className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
              />
            </div>

            {error && <p className="text-xs text-ops-danger">{error}</p>}

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-textDim"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSaving}
                className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg disabled:opacity-50"
              >
                {isSaving ? 'Saving…' : 'Save'}
              </button>
            </div>
          </form>
        </div>
      )}
      {pendingArchive && (
        <ConfirmDialog
          title="Archive Unit"
          message={`Archive ${pendingArchive.name}? It can be restored later.`}
          confirmLabel="Archive"
          danger
          isBusy={isArchiving}
          onConfirm={runArchive}
          onCancel={() => setPendingArchive(null)}
        />
      )}
    </div>
  );
}
