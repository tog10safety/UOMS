import { FormEvent, useEffect, useState } from 'react';

import { inventoryApi, personnelApi, unitsApi } from '@/api/endpoints';
import InventoryExtras from '@/components/inventory/InventoryExtras';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import SearchableSelect from '@/components/common/SearchableSelect';
import { useAuth } from '@/contexts/AuthContext';
import { useToast } from '@/contexts/ToastContext';
import type {
  InventoryCondition,
  InventoryItem,
  InventoryItemType,
  InventoryReport,
  InventoryTransactionType,
  ItemCategory,
  PersonnelListItem,
  Unit,
} from '@/types';

const CONDITION_BADGE: Record<InventoryCondition, string> = {
  SERVICEABLE: 'bg-ops-success/10 text-ops-success',
  UNSERVICEABLE: 'bg-ops-danger/10 text-ops-danger',
  FOR_DISPOSAL: 'bg-ops-textDim/10 text-ops-textDim',
};

const TRANSACTION_TYPES: InventoryTransactionType[] = ['RECEIPT', 'ISSUANCE', 'RETURN', 'ADJUSTMENT', 'DISPOSAL'];

const emptyItemForm = {
  name: '', category: null as string | null, item_type: 'SUPPLY' as InventoryItemType, property_number: '',
  sku: '', unit_of_measure: 'pcs', reorder_level: '0', condition: 'SERVICEABLE' as InventoryCondition,
  unit: null as string | null, storage_location: '', description: '',
};

const emptyTxnForm = {
  item: '', transaction_type: 'RECEIPT' as InventoryTransactionType, quantity: '1',
  issued_to: null as string | null, supplier_or_source: '', reference_number: '', remarks: '',
};

export default function Inventory() {
  const { can } = useAuth();
  const { showSuccess, showError } = useToast();

  const [items, setItems] = useState<InventoryItem[]>([]);
  const [report, setReport] = useState<InventoryReport | null>(null);
  const [categories, setCategories] = useState<ItemCategory[]>([]);
  const [extrasVersion, setExtrasVersion] = useState(0);
  const [units, setUnits] = useState<Unit[]>([]);
  const [personnel, setPersonnel] = useState<PersonnelListItem[]>([]);
  const [typeFilter, setTypeFilter] = useState<'ALL' | 'EQUIPMENT' | 'SUPPLY'>('ALL');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  const [showItemForm, setShowItemForm] = useState(false);
  const [editingItemId, setEditingItemId] = useState<string | null>(null);
  const [itemForm, setItemForm] = useState(emptyItemForm);
  const [itemFormError, setItemFormError] = useState('');
  const [isSavingItem, setIsSavingItem] = useState(false);

  const [showTxnForm, setShowTxnForm] = useState(false);
  const [txnForm, setTxnForm] = useState(emptyTxnForm);
  const [txnFormError, setTxnFormError] = useState('');
  const [isSavingTxn, setIsSavingTxn] = useState(false);

  const [pendingArchive, setPendingArchive] = useState<InventoryItem | null>(null);
  const [isActionBusy, setIsActionBusy] = useState(false);

  const canCreate = can('INVENTORY', 'CREATE');
  const canEdit = can('INVENTORY', 'EDIT');
  const canDelete = can('INVENTORY', 'DELETE');
  const canTransact = can('INVENTORY', 'ISSUE') || can('INVENTORY', 'ASSIGN') || canCreate;

  const loadItems = () =>
    Promise.all([
      inventoryApi.items(typeFilter === 'ALL' ? undefined : { item_type: typeFilter }),
      inventoryApi.report(),
    ]).then(([itemsData, reportData]) => {
      setItems(itemsData.results);
      setReport(reportData);
    });

  useEffect(() => {
    setIsLoading(true);
    loadItems()
      .catch(() => setError('Unable to load inventory data.'))
      .finally(() => setIsLoading(false));
  }, [typeFilter]);

  useEffect(() => {
    inventoryApi.categories().then((d) => setCategories(d.results)).catch(() => {});
    unitsApi.list().then((d) => setUnits(d.results)).catch(() => {});
    personnelApi.list({ page_size: 200 }).then((d) => setPersonnel(d.results)).catch(() => {});
  }, []);

  // ---- Item form ----
  const openCreateItem = () => {
    setEditingItemId(null);
    setItemForm(emptyItemForm);
    setItemFormError('');
    setShowItemForm(true);
  };

  const openEditItem = (item: InventoryItem) => {
    setEditingItemId(item.id);
    setItemForm({
      name: item.name, category: item.category, item_type: item.item_type, property_number: item.property_number,
      sku: item.sku, unit_of_measure: item.unit_of_measure, reorder_level: item.reorder_level.toString(),
      condition: item.condition, unit: item.unit, storage_location: item.storage_location, description: item.description,
    });
    setItemFormError('');
    setShowItemForm(true);
  };

  const handleItemSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setIsSavingItem(true);
    setItemFormError('');
    const payload = { ...itemForm, reorder_level: Number(itemForm.reorder_level) as any };
    try {
      if (editingItemId) {
        await inventoryApi.updateItem(editingItemId, payload);
        showSuccess(`Item "${itemForm.name}" updated successfully.`);
      } else {
        await inventoryApi.createItem(payload);
        showSuccess(`Item "${itemForm.name}" added successfully.`);
      }
      setShowItemForm(false);
      await loadItems();
    } catch (err: any) {
      const data = err?.response?.data;
      setItemFormError(data ? Object.values(data).flat().join(' ') : 'Unable to save record. Please check the required fields.');
    } finally {
      setIsSavingItem(false);
    }
  };

  // ---- Transaction form ----
  const openTxnForm = (item?: InventoryItem) => {
    setTxnForm({ ...emptyTxnForm, item: item?.id ?? '' });
    setTxnFormError('');
    setShowTxnForm(true);
  };

  const handleTxnSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setIsSavingTxn(true);
    setTxnFormError('');
    try {
      await inventoryApi.createTransaction({
        ...txnForm,
        quantity: Number(txnForm.quantity) as any,
        transaction_date: new Date().toISOString(),
      });
      showSuccess(`${txnForm.transaction_type} transaction recorded successfully.`);
      setShowTxnForm(false);
      await loadItems();
      setExtrasVersion((v) => v + 1);
    } catch (err: any) {
      const data = err?.response?.data;
      setTxnFormError(data ? Object.values(data).flat().join(' ') : 'Unable to record transaction — check the quantity against stock on hand.');
    } finally {
      setIsSavingTxn(false);
    }
  };

  const runArchive = async () => {
    if (!pendingArchive) return;
    setIsActionBusy(true);
    try {
      await inventoryApi.archiveItem(pendingArchive.id);
      showSuccess(`Item "${pendingArchive.name}" archived.`);
      setPendingArchive(null);
      await loadItems();
    } catch (err: any) {
      showError(err?.response?.data?.detail ?? 'You do not have permission to perform this action.');
    } finally {
      setIsActionBusy(false);
    }
  };

  const categoryOptions = categories.map((c) => ({ value: c.id, label: c.name }));
  const unitOptions = units.map((u) => ({ value: u.id, label: `${u.code} — ${u.name}` }));
  const personnelOptions = personnel.map((p) => ({ value: p.id, label: p.full_name, sublabel: p.service_number }));
  const itemOptions = items.map((i) => ({ value: i.id, label: i.name, sublabel: `${i.quantity_on_hand} ${i.unit_of_measure} on hand` }));

  return (
    <div className="space-y-6">
      {error && <p className="text-sm text-ops-danger">{error}</p>}

      {report && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <div className="ops-card p-4">
            <p className="ops-label">Total Items</p>
            <p className="mt-1 font-mono text-2xl font-bold text-ops-accent">{report.total_items}</p>
          </div>
          <div className="ops-card p-4">
            <p className="ops-label">Low Stock Items</p>
            <p className={`mt-1 font-mono text-2xl font-bold ${report.total_low_stock > 0 ? 'text-ops-warning' : 'text-ops-success'}`}>
              {report.total_low_stock}
            </p>
          </div>
          <div className="ops-card col-span-2 p-4">
            <p className="ops-label mb-2">By Category</p>
            <div className="space-y-1">
              {report.by_category.map((row) => (
                <div key={row.category} className="flex justify-between text-xs">
                  <span className="text-ops-text">{row.category}</span>
                  <span className="text-ops-textDim">
                    {row.item_count} items · {row.total_quantity_on_hand} on hand
                    {row.low_stock_count > 0 && <span className="text-ops-warning"> · {row.low_stock_count} low</span>}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          {(['ALL', 'EQUIPMENT', 'SUPPLY'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTypeFilter(t)}
              className={`rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
                typeFilter === t
                  ? 'border-ops-accent bg-ops-accent/10 text-ops-accent'
                  : 'border-ops-border text-ops-textDim hover:text-ops-text'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-ops-textDim">{items.length} item(s)</span>
          {canTransact && (
            <button onClick={() => openTxnForm()} className="rounded-md border border-ops-accent/40 px-3 py-1.5 text-xs font-medium text-ops-accent hover:bg-ops-accent/10">
              Log Transaction
            </button>
          )}
          {canCreate && (
            <button onClick={openCreateItem} className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg">
              + Add Item
            </button>
          )}
        </div>
      </div>

      <div className="ops-card overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-ops-panelLight text-xs uppercase tracking-wider text-ops-textDim">
            <tr>
              <th className="px-4 py-3">Item</th>
              <th className="px-4 py-3">Category</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">On Hand</th>
              <th className="px-4 py-3">Custodian</th>
              <th className="px-4 py-3">Condition</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {!isLoading && items.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-6 text-center text-ops-textDim">No inventory items found.</td></tr>
            )}
            {items.map((item) => (
              <tr key={item.id} className="border-t border-ops-border hover:bg-ops-panelLight/50">
                <td className="px-4 py-3">
                  <p className="text-ops-text">{item.name}</p>
                  {item.property_number && <p className="font-mono text-xs text-ops-textDim">{item.property_number}</p>}
                </td>
                <td className="px-4 py-3">{item.category_name ?? '—'}</td>
                <td className="px-4 py-3 text-xs text-ops-textDim">{item.item_type}</td>
                <td className="px-4 py-3">
                  <span className="font-mono text-xs">{item.quantity_on_hand} {item.unit_of_measure}</span>
                  {item.is_low_stock && (
                    <span className="ml-2 rounded-full bg-ops-warning/10 px-2 py-0.5 text-xs font-medium text-ops-warning">Low</span>
                  )}
                </td>
                <td className="px-4 py-3">{item.accountable_personnel_name ?? '—'}</td>
                <td className="px-4 py-3">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${CONDITION_BADGE[item.condition]}`}>
                    {item.condition.replace('_', ' ')}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-2 whitespace-nowrap">
                    {canTransact && (
                      <button onClick={() => openTxnForm(item)} className="text-xs font-medium text-ops-accent hover:underline">
                        Transact
                      </button>
                    )}
                    {canEdit && (
                      <button onClick={() => openEditItem(item)} className="text-xs font-medium text-ops-textDim hover:text-ops-text">
                        Edit
                      </button>
                    )}
                    {canDelete && (
                      <button onClick={() => setPendingArchive(item)} className="text-xs font-medium text-ops-danger hover:underline">
                        Archive
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <InventoryExtras
        refreshKey={extrasVersion}
        onCategoriesChanged={() => inventoryApi.categories().then((d) => setCategories(d.results)).catch(() => {})}
      />

      {showItemForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <form onSubmit={handleItemSubmit} className="ops-card w-full max-w-lg space-y-3 p-6 max-h-[90vh] overflow-y-auto">
            <p className="ops-label">{editingItemId ? 'Edit Item' : 'Add Item'}</p>

            <div>
              <label className="mb-1 block text-xs text-ops-textDim">Name *</label>
              <input required value={itemForm.name} onChange={(e) => setItemForm({ ...itemForm, name: e.target.value })}
                className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent" />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Item Type *</label>
                <select value={itemForm.item_type} onChange={(e) => setItemForm({ ...itemForm, item_type: e.target.value as InventoryItemType })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text">
                  <option value="SUPPLY">Supply (Consumable)</option>
                  <option value="EQUIPMENT">Equipment (Accountable)</option>
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Category</label>
                <SearchableSelect options={categoryOptions} value={itemForm.category} onChange={(v) => setItemForm({ ...itemForm, category: v })} placeholder="Search categories…" />
              </div>
            </div>

            {itemForm.item_type === 'EQUIPMENT' && (
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Property Number * (required for Equipment)</label>
                <input required value={itemForm.property_number} onChange={(e) => setItemForm({ ...itemForm, property_number: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent" />
              </div>
            )}

            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">SKU</label>
                <input value={itemForm.sku} onChange={(e) => setItemForm({ ...itemForm, sku: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent" />
              </div>
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Unit of Measure</label>
                <input value={itemForm.unit_of_measure} onChange={(e) => setItemForm({ ...itemForm, unit_of_measure: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent" />
              </div>
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Reorder Level</label>
                <input type="number" value={itemForm.reorder_level} onChange={(e) => setItemForm({ ...itemForm, reorder_level: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent" />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Condition</label>
                <select value={itemForm.condition} onChange={(e) => setItemForm({ ...itemForm, condition: e.target.value as InventoryCondition })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text">
                  <option value="SERVICEABLE">Serviceable</option>
                  <option value="UNSERVICEABLE">Unserviceable</option>
                  <option value="FOR_DISPOSAL">For Disposal</option>
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Unit</label>
                <SearchableSelect options={unitOptions} value={itemForm.unit} onChange={(v) => setItemForm({ ...itemForm, unit: v })} placeholder="Search units…" />
              </div>
            </div>

            <div>
              <label className="mb-1 block text-xs text-ops-textDim">Storage Location</label>
              <input value={itemForm.storage_location} onChange={(e) => setItemForm({ ...itemForm, storage_location: e.target.value })}
                className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent" />
            </div>

            <div>
              <label className="mb-1 block text-xs text-ops-textDim">Description</label>
              <textarea value={itemForm.description} onChange={(e) => setItemForm({ ...itemForm, description: e.target.value })} rows={2}
                className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent" />
            </div>

            {itemFormError && <p className="text-xs text-ops-danger">{itemFormError}</p>}

            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={() => setShowItemForm(false)} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-textDim">Cancel</button>
              <button type="submit" disabled={isSavingItem} className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg disabled:opacity-50">
                {isSavingItem ? 'Saving…' : 'Save'}
              </button>
            </div>
          </form>
        </div>
      )}

      {showTxnForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <form onSubmit={handleTxnSubmit} className="ops-card w-full max-w-md space-y-3 p-6">
            <p className="ops-label">Log Inventory Transaction</p>

            <div>
              <label className="mb-1 block text-xs text-ops-textDim">Item *</label>
              <SearchableSelect options={itemOptions} value={txnForm.item || null} onChange={(v) => setTxnForm({ ...txnForm, item: v ?? '' })} placeholder="Search items…" />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Transaction Type *</label>
                <select value={txnForm.transaction_type} onChange={(e) => setTxnForm({ ...txnForm, transaction_type: e.target.value as InventoryTransactionType })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text">
                  {TRANSACTION_TYPES.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Quantity *</label>
                <input required type="number" min={1} value={txnForm.quantity} onChange={(e) => setTxnForm({ ...txnForm, quantity: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent" />
              </div>
            </div>

            {txnForm.transaction_type === 'ISSUANCE' && (
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Issue To *</label>
                <SearchableSelect options={personnelOptions} value={txnForm.issued_to} onChange={(v) => setTxnForm({ ...txnForm, issued_to: v })} placeholder="Search personnel…" />
              </div>
            )}

            {txnForm.transaction_type === 'RECEIPT' && (
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Supplier / Source</label>
                <input value={txnForm.supplier_or_source} onChange={(e) => setTxnForm({ ...txnForm, supplier_or_source: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent" />
              </div>
            )}

            <div>
              <label className="mb-1 block text-xs text-ops-textDim">Reference Number</label>
              <input value={txnForm.reference_number} onChange={(e) => setTxnForm({ ...txnForm, reference_number: e.target.value })}
                placeholder="PO#, DR#, etc." className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent" />
            </div>

            <div>
              <label className="mb-1 block text-xs text-ops-textDim">Remarks</label>
              <textarea value={txnForm.remarks} onChange={(e) => setTxnForm({ ...txnForm, remarks: e.target.value })} rows={2}
                className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent" />
            </div>

            {txnFormError && <p className="text-xs text-ops-danger">{txnFormError}</p>}

            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={() => setShowTxnForm(false)} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-textDim">Cancel</button>
              <button type="submit" disabled={isSavingTxn} className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg disabled:opacity-50">
                {isSavingTxn ? 'Recording…' : 'Record'}
              </button>
            </div>
          </form>
        </div>
      )}

      {pendingArchive && (
        <ConfirmDialog
          title="Archive Item"
          message={`Archive "${pendingArchive.name}"? It will be hidden from the active catalog.`}
          danger
          isBusy={isActionBusy}
          onConfirm={runArchive}
          onCancel={() => setPendingArchive(null)}
        />
      )}
    </div>
  );
}
