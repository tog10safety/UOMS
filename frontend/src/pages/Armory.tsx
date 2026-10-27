import { FormEvent, useEffect, useState } from 'react';

import { armoryApi, personnelApi, unitsApi } from '@/api/endpoints';
import { AmmoAction, AmmoActionModals, AmmoIssuancesPanel, InspectionsPanel } from '@/components/armory/ArmoryExtras';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import SearchableSelect from '@/components/common/SearchableSelect';
import { useAuth } from '@/contexts/AuthContext';
import { useToast } from '@/contexts/ToastContext';
import type { AmmunitionStock, ArmoryTransaction, Firearm, FirearmIssuance, FirearmStatus, PersonnelListItem, Unit } from '@/types';

const FIREARM_STATUS_BADGE: Record<FirearmStatus, string> = {
  SERVICEABLE: 'bg-ops-success/10 text-ops-success',
  ISSUED: 'bg-ops-accent/10 text-ops-accent',
  UNSERVICEABLE: 'bg-ops-danger/10 text-ops-danger',
  IN_REPAIR: 'bg-ops-warning/10 text-ops-warning',
  DECOMMISSIONED: 'bg-ops-textDim/10 text-ops-textDim',
};

const emptyFirearmForm = { serial_number: '', firearm_type: '', make: '', model: '', caliber: '', unit: null as string | null, remarks: '' };
const emptyAmmoForm = { ammunition_type: '', lot_number: '', unit: null as string | null, quantity_on_hand: '', unit_of_measure: 'rounds', storage_location: '' };
const emptyIssueForm = { firearm: '', issued_to: null as string | null, expected_return_date: '', condition_on_issue: 'Good', purpose: '' };

export default function Armory() {
  const { can } = useAuth();
  const { showSuccess, showError } = useToast();

  const [firearms, setFirearms] = useState<Firearm[]>([]);
  const [ammunition, setAmmunition] = useState<AmmunitionStock[]>([]);
  const [issuances, setIssuances] = useState<FirearmIssuance[]>([]);
  const [transactions, setTransactions] = useState<ArmoryTransaction[]>([]);
  const [personnel, setPersonnel] = useState<PersonnelListItem[]>([]);
  const [units, setUnits] = useState<Unit[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  const [showFirearmForm, setShowFirearmForm] = useState(false);
  const [editingFirearmId, setEditingFirearmId] = useState<string | null>(null);
  const [firearmForm, setFirearmForm] = useState(emptyFirearmForm);
  const [firearmFormError, setFirearmFormError] = useState('');
  const [isSavingFirearm, setIsSavingFirearm] = useState(false);

  const [showAmmoForm, setShowAmmoForm] = useState(false);
  const [ammoForm, setAmmoForm] = useState(emptyAmmoForm);
  const [ammoFormError, setAmmoFormError] = useState('');
  const [isSavingAmmo, setIsSavingAmmo] = useState(false);

  const [showIssueForm, setShowIssueForm] = useState(false);
  const [issueForm, setIssueForm] = useState(emptyIssueForm);
  const [issueFormError, setIssueFormError] = useState('');
  const [isSavingIssue, setIsSavingIssue] = useState(false);

  const [pendingReturn, setPendingReturn] = useState<FirearmIssuance | null>(null);
  const [pendingArchive, setPendingArchive] = useState<Firearm | null>(null);
  const [isActionBusy, setIsActionBusy] = useState(false);
  const [ammoAction, setAmmoAction] = useState<AmmoAction | null>(null);
  const [extrasVersion, setExtrasVersion] = useState(0);

  const canCreateFirearm = can('ARMORY', 'CREATE');
  const canEditFirearm = can('ARMORY', 'EDIT');
  const canDeleteFirearm = can('ARMORY', 'DELETE');
  const canIssue = can('ARMORY', 'ISSUE');
  const canReturn = can('ARMORY', 'RETURN');

  const loadAll = () =>
    Promise.all([
      armoryApi.firearms(),
      armoryApi.ammunition(),
      armoryApi.issuances({ status: 'ISSUED' }),
      armoryApi.transactions(),
    ]).then(([f, a, i, t]) => {
      setFirearms(f.results);
      setAmmunition(a.results);
      setIssuances(i.results);
      setTransactions(t);
    });

  useEffect(() => {
    let isMounted = true;
    loadAll()
      .catch(() => {
        if (isMounted) setError('Unable to load armory data.');
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    personnelApi.list({ page_size: 200 }).then((d) => setPersonnel(d.results)).catch(() => {});
    unitsApi.list().then((d) => setUnits(d.results)).catch(() => {});
  }, []);

  // ---- Firearm form ----
  const openCreateFirearm = () => {
    setEditingFirearmId(null);
    setFirearmForm(emptyFirearmForm);
    setFirearmFormError('');
    setShowFirearmForm(true);
  };

  const openEditFirearm = (f: Firearm) => {
    setEditingFirearmId(f.id);
    setFirearmForm({
      serial_number: f.serial_number, firearm_type: f.firearm_type, make: f.make,
      model: f.model, caliber: f.caliber, unit: f.unit, remarks: f.remarks,
    });
    setFirearmFormError('');
    setShowFirearmForm(true);
  };

  const handleFirearmSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setIsSavingFirearm(true);
    setFirearmFormError('');
    try {
      if (editingFirearmId) {
        await armoryApi.updateFirearm(editingFirearmId, firearmForm);
        showSuccess(`Firearm ${firearmForm.serial_number} updated successfully.`);
      } else {
        await armoryApi.createFirearm(firearmForm);
        showSuccess(`Firearm ${firearmForm.serial_number} registered successfully.`);
      }
      setShowFirearmForm(false);
      await loadAll();
    } catch (err: any) {
      const data = err?.response?.data;
      setFirearmFormError(data ? Object.values(data).flat().join(' ') : 'Unable to save record. Please check the required fields.');
    } finally {
      setIsSavingFirearm(false);
    }
  };

  // ---- Ammunition form ----
  const openCreateAmmo = () => {
    setAmmoForm(emptyAmmoForm);
    setAmmoFormError('');
    setShowAmmoForm(true);
  };

  const handleAmmoSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setIsSavingAmmo(true);
    setAmmoFormError('');
    try {
      await armoryApi.createAmmunition({ ...ammoForm, quantity_on_hand: Number(ammoForm.quantity_on_hand) as any });
      showSuccess(`Ammunition stock "${ammoForm.ammunition_type}" added successfully.`);
      setShowAmmoForm(false);
      await loadAll();
    } catch (err: any) {
      const data = err?.response?.data;
      setAmmoFormError(data ? Object.values(data).flat().join(' ') : 'Unable to save record. Please check the required fields.');
    } finally {
      setIsSavingAmmo(false);
    }
  };

  // ---- Issue firearm ----
  const openIssueForm = () => {
    setIssueForm(emptyIssueForm);
    setIssueFormError('');
    setShowIssueForm(true);
  };

  const handleIssueSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setIsSavingIssue(true);
    setIssueFormError('');
    try {
      await armoryApi.issueFirearm({
        ...issueForm,
        expected_return_date: issueForm.expected_return_date || undefined,
      } as any);
      showSuccess('Firearm issued successfully.');
      setShowIssueForm(false);
      await loadAll();
    } catch (err: any) {
      const data = err?.response?.data;
      setIssueFormError(data ? Object.values(data).flat().join(' ') : 'Unable to issue firearm — it may not be serviceable.');
    } finally {
      setIsSavingIssue(false);
    }
  };

  // ---- Return / Archive ----
  const runReturn = async () => {
    if (!pendingReturn) return;
    setIsActionBusy(true);
    try {
      await armoryApi.returnFirearm(pendingReturn.id);
      showSuccess(`Firearm ${pendingReturn.firearm_serial} returned successfully.`);
      setPendingReturn(null);
      await loadAll();
    } catch (err: any) {
      showError(err?.response?.data?.detail ?? 'Unable to process return.');
    } finally {
      setIsActionBusy(false);
    }
  };

  const runArchive = async () => {
    if (!pendingArchive) return;
    setIsActionBusy(true);
    try {
      await armoryApi.archiveFirearm(pendingArchive.id);
      showSuccess(`Firearm ${pendingArchive.serial_number} archived.`);
      setPendingArchive(null);
      await loadAll();
    } catch (err: any) {
      showError(err?.response?.data?.detail ?? 'You do not have permission to perform this action.');
    } finally {
      setIsActionBusy(false);
    }
  };

  const unitOptions = units.map((u) => ({ value: u.id, label: `${u.code} — ${u.name}` }));
  const personnelOptions = personnel.map((p) => ({ value: p.id, label: p.full_name, sublabel: p.service_number }));
  const serviceableFirearmOptions = firearms
    .filter((f) => f.status === 'SERVICEABLE')
    .map((f) => ({ value: f.id, label: f.serial_number, sublabel: f.firearm_type }));

  return (
    <div className="space-y-6">
      {error && <p className="text-sm text-ops-danger">{error}</p>}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div>
          <div className="mb-2 flex items-center justify-between">
            <p className="ops-label">Firearms Registry</p>
            {canCreateFirearm && (
              <button onClick={openCreateFirearm} className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg">
                + Add Firearm
              </button>
            )}
          </div>
          <div className="ops-card overflow-hidden">
            <table className="w-full text-left text-sm">
              <thead className="bg-ops-panelLight text-xs uppercase tracking-wider text-ops-textDim">
                <tr>
                  <th className="px-4 py-2">Serial #</th>
                  <th className="px-4 py-2">Type</th>
                  <th className="px-4 py-2">Custodian</th>
                  <th className="px-4 py-2">Status</th>
                  <th className="px-4 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {!isLoading && firearms.length === 0 && (
                  <tr><td colSpan={5} className="px-4 py-6 text-center text-ops-textDim">No firearms registered.</td></tr>
                )}
                {firearms.map((f) => (
                  <tr key={f.id} className="border-t border-ops-border hover:bg-ops-panelLight/50">
                    <td className="px-4 py-3 font-mono text-xs">{f.serial_number}</td>
                    <td className="px-4 py-3">{f.firearm_type}</td>
                    <td className="px-4 py-3">{f.accountable_personnel_name ?? '—'}</td>
                    <td className="px-4 py-3">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${FIREARM_STATUS_BADGE[f.status]}`}>
                        {f.status.replace('_', ' ')}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-2">
                        {canEditFirearm && (
                          <button onClick={() => openEditFirearm(f)} className="text-xs font-medium text-ops-textDim hover:text-ops-text">
                            Edit
                          </button>
                        )}
                        {canDeleteFirearm && f.status === 'SERVICEABLE' && (
                          <button onClick={() => setPendingArchive(f)} className="text-xs font-medium text-ops-danger hover:underline">
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
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between">
            <p className="ops-label">Ammunition Stock</p>
            {canCreateFirearm && (
              <button onClick={openCreateAmmo} className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg">
                + Add Stock
              </button>
            )}
          </div>
          <div className="ops-card overflow-hidden">
            <table className="w-full text-left text-sm">
              <thead className="bg-ops-panelLight text-xs uppercase tracking-wider text-ops-textDim">
                <tr>
                  <th className="px-4 py-2">Type</th>
                  <th className="px-4 py-2">Lot #</th>
                  <th className="px-4 py-2">On Hand</th>
                  <th className="px-4 py-2"></th>
                  <th className="px-4 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {!isLoading && ammunition.length === 0 && (
                  <tr><td colSpan={5} className="px-4 py-6 text-center text-ops-textDim">No ammunition stock recorded.</td></tr>
                )}
                {ammunition.map((a) => (
                  <tr key={a.id} className="border-t border-ops-border hover:bg-ops-panelLight/50">
                    <td className="px-4 py-3">{a.ammunition_type}</td>
                    <td className="px-4 py-3 font-mono text-xs text-ops-textDim">{a.lot_number || '—'}</td>
                    <td className="px-4 py-3 font-mono text-xs">{a.quantity_on_hand.toLocaleString()} {a.unit_of_measure}</td>
                    <td className="px-4 py-3">
                      {a.is_low_stock && (
                        <span className="rounded-full bg-ops-warning/10 px-2 py-0.5 text-xs font-medium text-ops-warning">Low Stock</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-2 whitespace-nowrap">
                        {canIssue && a.quantity_on_hand > 0 && (
                          <button onClick={() => setAmmoAction({ type: 'issue', stock: a })} className="text-xs font-medium text-ops-accent hover:underline">Issue</button>
                        )}
                        {canEditFirearm && (
                          <button onClick={() => setAmmoAction({ type: 'edit', stock: a })} className="text-xs font-medium text-ops-textDim hover:text-ops-text">Edit</button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <p className="ops-label">Active Issuances</p>
          {canIssue && (
            <button onClick={openIssueForm} className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg">
              + Issue Firearm
            </button>
          )}
        </div>
        <div className="ops-card overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead className="bg-ops-panelLight text-xs uppercase tracking-wider text-ops-textDim">
              <tr>
                <th className="px-4 py-2">Firearm</th>
                <th className="px-4 py-2">Issued To</th>
                <th className="px-4 py-2">Issue Date</th>
                <th className="px-4 py-2">Purpose</th>
                {canReturn && <th className="px-4 py-2">Action</th>}
              </tr>
            </thead>
            <tbody>
              {!isLoading && issuances.length === 0 && (
                <tr><td colSpan={canReturn ? 5 : 4} className="px-4 py-6 text-center text-ops-textDim">No active issuances.</td></tr>
              )}
              {issuances.map((i) => (
                <tr key={i.id} className="border-t border-ops-border hover:bg-ops-panelLight/50">
                  <td className="px-4 py-3 font-mono text-xs">{i.firearm_serial}</td>
                  <td className="px-4 py-3">{i.issued_to_name}</td>
                  <td className="px-4 py-3 text-xs text-ops-textDim">{new Date(i.issue_date).toLocaleString()}</td>
                  <td className="px-4 py-3 text-xs text-ops-textDim">{i.purpose || '—'}</td>
                  {canReturn && (
                    <td className="px-4 py-3">
                      <button
                        onClick={() => setPendingReturn(i)}
                        className="rounded-md border border-ops-accent/40 px-2 py-1 text-xs text-ops-accent hover:bg-ops-accent/10"
                      >
                        Mark Returned
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div>
        <p className="ops-label mb-2">Transaction History</p>
        <div className="ops-card overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead className="bg-ops-panelLight text-xs uppercase tracking-wider text-ops-textDim">
              <tr>
                <th className="px-4 py-2">Type</th>
                <th className="px-4 py-2">Description</th>
                <th className="px-4 py-2">Qty</th>
                <th className="px-4 py-2">Date</th>
              </tr>
            </thead>
            <tbody>
              {!isLoading && transactions.length === 0 && (
                <tr><td colSpan={4} className="px-4 py-6 text-center text-ops-textDim">No transactions recorded.</td></tr>
              )}
              {transactions.map((t) => (
                <tr key={t.id} className="border-t border-ops-border hover:bg-ops-panelLight/50">
                  <td className="px-4 py-3 text-xs text-ops-textDim">{t.type.replace('_', ' ')}</td>
                  <td className="px-4 py-3">{t.description}</td>
                  <td className="px-4 py-3 font-mono text-xs">{t.quantity}</td>
                  <td className="px-4 py-3 text-xs text-ops-textDim">{new Date(t.date).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <AmmoIssuancesPanel refreshKey={extrasVersion} />
      <InspectionsPanel firearms={firearms} personnel={personnel} refreshKey={extrasVersion} onChanged={() => void loadAll()} />
      <AmmoActionModals
        action={ammoAction}
        units={units}
        personnel={personnel}
        onClose={() => setAmmoAction(null)}
        onDone={() => {
          setAmmoAction(null);
          setExtrasVersion((v) => v + 1);
          void loadAll();
        }}
      />

      {showFirearmForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <form onSubmit={handleFirearmSubmit} className="ops-card w-full max-w-lg space-y-3 p-6">
            <p className="ops-label">{editingFirearmId ? 'Edit Firearm' : 'Add Firearm'}</p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Serial Number *</label>
                <input required value={firearmForm.serial_number} onChange={(e) => setFirearmForm({ ...firearmForm, serial_number: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent" />
              </div>
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Firearm Type *</label>
                <input required value={firearmForm.firearm_type} onChange={(e) => setFirearmForm({ ...firearmForm, firearm_type: e.target.value })}
                  placeholder="e.g. Rifle, Pistol" className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent" />
              </div>
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Make</label>
                <input value={firearmForm.make} onChange={(e) => setFirearmForm({ ...firearmForm, make: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent" />
              </div>
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Model</label>
                <input value={firearmForm.model} onChange={(e) => setFirearmForm({ ...firearmForm, model: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent" />
              </div>
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Caliber</label>
                <input value={firearmForm.caliber} onChange={(e) => setFirearmForm({ ...firearmForm, caliber: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent" />
              </div>
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Unit</label>
                <SearchableSelect options={unitOptions} value={firearmForm.unit} onChange={(v) => setFirearmForm({ ...firearmForm, unit: v })} placeholder="Search units…" />
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs text-ops-textDim">Remarks</label>
              <textarea value={firearmForm.remarks} onChange={(e) => setFirearmForm({ ...firearmForm, remarks: e.target.value })} rows={2}
                className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent" />
            </div>
            {firearmFormError && <p className="text-xs text-ops-danger">{firearmFormError}</p>}
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={() => setShowFirearmForm(false)} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-textDim">Cancel</button>
              <button type="submit" disabled={isSavingFirearm} className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg disabled:opacity-50">
                {isSavingFirearm ? 'Saving…' : 'Save'}
              </button>
            </div>
          </form>
        </div>
      )}

      {showAmmoForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <form onSubmit={handleAmmoSubmit} className="ops-card w-full max-w-md space-y-3 p-6">
            <p className="ops-label">Add Ammunition Stock</p>
            <div>
              <label className="mb-1 block text-xs text-ops-textDim">Ammunition Type *</label>
              <input required value={ammoForm.ammunition_type} onChange={(e) => setAmmoForm({ ...ammoForm, ammunition_type: e.target.value })}
                placeholder="e.g. 5.56mm Ball" className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Lot Number</label>
                <input value={ammoForm.lot_number} onChange={(e) => setAmmoForm({ ...ammoForm, lot_number: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent" />
              </div>
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Quantity on Hand *</label>
                <input required type="number" value={ammoForm.quantity_on_hand} onChange={(e) => setAmmoForm({ ...ammoForm, quantity_on_hand: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent" />
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs text-ops-textDim">Unit</label>
              <SearchableSelect options={unitOptions} value={ammoForm.unit} onChange={(v) => setAmmoForm({ ...ammoForm, unit: v })} placeholder="Search units…" />
            </div>
            <div>
              <label className="mb-1 block text-xs text-ops-textDim">Storage Location</label>
              <input value={ammoForm.storage_location} onChange={(e) => setAmmoForm({ ...ammoForm, storage_location: e.target.value })}
                className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent" />
            </div>
            {ammoFormError && <p className="text-xs text-ops-danger">{ammoFormError}</p>}
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={() => setShowAmmoForm(false)} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-textDim">Cancel</button>
              <button type="submit" disabled={isSavingAmmo} className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg disabled:opacity-50">
                {isSavingAmmo ? 'Saving…' : 'Save'}
              </button>
            </div>
          </form>
        </div>
      )}

      {showIssueForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <form onSubmit={handleIssueSubmit} className="ops-card w-full max-w-md space-y-3 p-6">
            <p className="ops-label">Issue Firearm</p>
            <div>
              <label className="mb-1 block text-xs text-ops-textDim">Firearm (serviceable only) *</label>
              <SearchableSelect options={serviceableFirearmOptions} value={issueForm.firearm || null} onChange={(v) => setIssueForm({ ...issueForm, firearm: v ?? '' })} placeholder="Search firearms…" />
            </div>
            <div>
              <label className="mb-1 block text-xs text-ops-textDim">Issue To *</label>
              <SearchableSelect options={personnelOptions} value={issueForm.issued_to} onChange={(v) => setIssueForm({ ...issueForm, issued_to: v })} placeholder="Search personnel…" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Expected Return Date</label>
                <input type="date" value={issueForm.expected_return_date} onChange={(e) => setIssueForm({ ...issueForm, expected_return_date: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent" />
              </div>
              <div>
                <label className="mb-1 block text-xs text-ops-textDim">Condition on Issue</label>
                <input value={issueForm.condition_on_issue} onChange={(e) => setIssueForm({ ...issueForm, condition_on_issue: e.target.value })}
                  className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent" />
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs text-ops-textDim">Purpose</label>
              <input value={issueForm.purpose} onChange={(e) => setIssueForm({ ...issueForm, purpose: e.target.value })}
                className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent" />
            </div>
            {issueFormError && <p className="text-xs text-ops-danger">{issueFormError}</p>}
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={() => setShowIssueForm(false)} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-textDim">Cancel</button>
              <button type="submit" disabled={isSavingIssue} className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg disabled:opacity-50">
                {isSavingIssue ? 'Issuing…' : 'Issue'}
              </button>
            </div>
          </form>
        </div>
      )}

      {pendingReturn && (
        <ConfirmDialog
          title="Return Firearm"
          message={`Mark ${pendingReturn.firearm_serial} as returned from ${pendingReturn.issued_to_name}?`}
          isBusy={isActionBusy}
          onConfirm={runReturn}
          onCancel={() => setPendingReturn(null)}
        />
      )}

      {pendingArchive && (
        <ConfirmDialog
          title="Archive Firearm"
          message={`Archive ${pendingArchive.serial_number}? It will be hidden from the active registry.`}
          danger
          isBusy={isActionBusy}
          onConfirm={runArchive}
          onCancel={() => setPendingArchive(null)}
        />
      )}
    </div>
  );
}
