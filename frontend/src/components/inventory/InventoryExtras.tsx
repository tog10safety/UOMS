import { useCallback, useState } from 'react';

import { inventoryApi } from '@/api/endpoints';
import { badgeClass } from '@/components/common/FormFields';
import ResourceManager, { ColumnDef, FieldDef } from '@/components/common/ResourceManager';
import { useAuth } from '@/contexts/AuthContext';
import type { InventoryTransaction, InventoryTransactionType, ItemCategory } from '@/types';
import { formatDateTime } from '@/utils/errors';

const TYPE_BADGE: Record<InventoryTransactionType, string> = {
  RECEIPT: 'bg-ops-success/10 text-ops-success',
  ISSUANCE: 'bg-ops-accent/10 text-ops-accent',
  RETURN: 'bg-ops-success/10 text-ops-success',
  ADJUSTMENT: 'bg-ops-warning/10 text-ops-warning',
  DISPOSAL: 'bg-ops-danger/10 text-ops-danger',
};

const categoryFields: FieldDef[] = [
  { name: 'name', label: 'Category Name', type: 'text', required: true, span: 2 },
  { name: 'description', label: 'Description', type: 'textarea' },
];

export default function InventoryExtras({ refreshKey, onCategoriesChanged }: { refreshKey: number; onCategoriesChanged: () => void }) {
  const { can } = useAuth();
  const [typeFilter, setTypeFilter] = useState('');

  const loadCategories = useCallback(() => inventoryApi.categories().then((d) => d.results), []);
  const loadTransactions = useCallback(
    (params: Record<string, string | number | boolean>) =>
      inventoryApi.transactions({ ordering: '-transaction_date', ...params }).then((d) => d.results),
    [],
  );

  const txnColumns: ColumnDef<InventoryTransaction>[] = [
    { header: 'Date', render: (t) => formatDateTime(t.transaction_date), className: 'text-xs text-ops-textDim' },
    { header: 'Type', render: (t) => <span className={`${badgeClass} ${TYPE_BADGE[t.transaction_type]}`}>{t.transaction_type}</span> },
    { header: 'Item', render: (t) => t.item_name },
    { header: 'Qty', render: (t) => t.quantity.toLocaleString(), className: 'font-mono text-xs' },
    { header: 'Issued To / Source', render: (t) => t.issued_to_name ?? (t.supplier_or_source || '—') },
    { header: 'Ref #', render: (t) => t.reference_number || '—', className: 'font-mono text-xs text-ops-textDim' },
    { header: 'By', render: (t) => t.performed_by_username ?? '—', className: 'text-xs' },
  ];

  const catColumns: ColumnDef<ItemCategory>[] = [
    { header: 'Category', render: (c) => c.name, className: 'font-medium text-ops-text' },
    { header: 'Description', render: (c) => c.description || '—', className: 'text-ops-textDim' },
  ];

  return (
    <div className="space-y-6">
      <ResourceManager<InventoryTransaction>
        title="Transaction History"
        noun="inventory transaction"
        columns={txnColumns}
        fields={[]}
        load={loadTransactions}
        supportsArchive={false}
        rowLabel={(t) => `${t.transaction_type} of ${t.item_name}`}
        refreshKey={refreshKey}
        extraParams={typeFilter ? { transaction_type: typeFilter } : undefined}
        toolbar={
          <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className="rounded-md border border-ops-border bg-ops-panelLight px-2 py-1.5 text-xs text-ops-text">
            <option value="">All types</option>
            {(['RECEIPT', 'ISSUANCE', 'RETURN', 'ADJUSTMENT', 'DISPOSAL'] as const).map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        }
      />

      <ResourceManager<ItemCategory>
        title="Item Categories"
        noun="category"
        columns={catColumns}
        fields={categoryFields}
        load={loadCategories}
        create={inventoryApi.createCategory}
        update={inventoryApi.updateCategory}
        remove={inventoryApi.deleteCategory}
        removeVerb="Delete"
        supportsArchive={false}
        canCreate={can('INVENTORY', 'CREATE')}
        canEdit={can('INVENTORY', 'EDIT')}
        canDelete={can('INVENTORY', 'DELETE')}
        rowLabel={(c) => `category "${c.name}"`}
        onChanged={onCategoriesChanged}
      />
    </div>
  );
}
