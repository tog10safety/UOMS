import { useEffect, useState } from 'react';

import { personnelApi } from '@/api/endpoints';
import { inputClass } from '@/components/common/FormFields';
import type { PersonnelListItem } from '@/types';
import type { RoleOption } from '@/types/missionOps';
import type { FieldErrors } from '@/utils/formErrors';
import { newKey, removeAt, replaceAt, ROLE_OTHER, ROLE_TEAM_LEADER, type PersonInput } from '@/utils/missionForm';

interface Props {
  value: PersonInput[];
  onChange: (next: PersonInput[]) => void;
  roles: RoleOption[];
  errors: FieldErrors;
}

/** Searchable picker over the Personnel Inventory + a role for each person. Stored as structured rows, never free text. */
export default function PersonnelAssignments({ value, onChange, roles, errors }: Props) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<PersonnelListItem[]>([]);
  const [searching, setSearching] = useState(false);
  const [newRole, setNewRole] = useState('TEAM_MEMBER');

  useEffect(() => {
    if (query.trim().length < 2) { setResults([]); return; }
    setSearching(true);
    const timer = setTimeout(() => {
      personnelApi.list({ search: query.trim(), is_active: true, page_size: 15 })
        .then((d) => setResults(d.results))
        .catch(() => setResults([]))
        .finally(() => setSearching(false));
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  const taken = new Set(value.map((p) => p.personnel));
  const hasLeader = value.some((p) => p.role === ROLE_TEAM_LEADER);

  const add = (p: PersonnelListItem) => {
    const role = newRole === ROLE_TEAM_LEADER && hasLeader ? 'TEAM_MEMBER' : newRole;
    onChange([...value, {
      key: newKey(), personnel: p.id, label: `${p.rank_abbreviation} ${p.full_name}`.trim(),
      sublabel: `${p.service_number} · ${p.unit_name}`, role, role_other: '', mrmReady: !!p.mrm_ready,
    }]);
    setQuery('');
    setResults([]);
  };

  return (
    <div className="space-y-3">
      <div className="space-y-2 rounded-md border border-ops-border p-3">
        <div className="flex flex-wrap gap-2">
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search personnel by name or service number…" className={`${inputClass} max-w-md`} />
          <select value={newRole} onChange={(e) => setNewRole(e.target.value)} className={`${inputClass} max-w-[14rem]`} aria-label="Role for the next person added">
            {roles.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
        </div>
        {searching && <p className="text-xs text-ops-textDim">Searching…</p>}
        {query.trim().length >= 2 && !searching && results.length === 0 && <p className="text-xs text-ops-textDim">No matching personnel.</p>}
        {results.map((p) => {
          const already = taken.has(p.id);
          return (
            <div key={p.id} className="flex items-center justify-between gap-3 rounded-md border border-ops-border px-3 py-2 text-sm">
              <div className="min-w-0">
                <p className="text-ops-text">{p.rank_abbreviation} {p.full_name}</p>
                <p className="text-[11px] text-ops-textDim">{p.service_number} · {p.unit_name}{p.position_title ? ` · ${p.position_title}` : ''}{p.mrm_ready ? ' · can prepare MRM' : ''}</p>
              </div>
              <button type="button" disabled={already} onClick={() => add(p)}
                      className="rounded-md bg-ops-accent px-2 py-1 text-xs font-semibold text-ops-bg disabled:opacity-40">{already ? 'Added' : 'Add'}</button>
            </div>
          );
        })}
      </div>

      {errors.personnel && <p role="alert" className="text-xs text-ops-danger">{errors.personnel}</p>}

      {value.length === 0 ? (
        <p className="rounded-md border border-dashed border-ops-border p-4 text-center text-sm text-ops-textDim">No personnel assigned yet. Search above and add at least one — including a Team Leader.</p>
      ) : (
        <div className="overflow-hidden rounded-md border border-ops-border">
          <table className="w-full text-left text-sm">
            <thead className="bg-ops-panelLight text-xs uppercase tracking-wider text-ops-textDim">
              <tr><th className="px-3 py-2">Person</th><th className="px-3 py-2">Role</th><th className="px-3 py-2" /></tr>
            </thead>
            <tbody>
              {value.map((p, i) => (
                <tr key={p.key} className="border-t border-ops-border align-top">
                  <td className="px-3 py-2">
                    <p className="text-ops-text">{p.label}</p>
                    <p className="text-[11px] text-ops-textDim">{p.sublabel}</p>
                    {errors[`personnel[${i}].personnel`] && <p role="alert" className="text-xs text-ops-danger">{errors[`personnel[${i}].personnel`]}</p>}
                  </td>
                  <td className="px-3 py-2">
                    <select value={p.role} onChange={(e) => onChange(replaceAt(value, i, { ...p, role: e.target.value }))}
                            className={`${inputClass} ${errors[`personnel[${i}].role`] ? '!border-ops-danger' : ''}`}>
                      {roles.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                    </select>
                    {p.role === ROLE_OTHER && (
                      <input value={p.role_other} onChange={(e) => onChange(replaceAt(value, i, { ...p, role_other: e.target.value }))} maxLength={100}
                             placeholder="Describe the role" className={`${inputClass} mt-1 ${errors[`personnel[${i}].role_other`] ? '!border-ops-danger' : ''}`} />
                    )}
                    {(errors[`personnel[${i}].role`] || errors[`personnel[${i}].role_other`]) && (
                      <p role="alert" className="text-xs text-ops-danger">{errors[`personnel[${i}].role`] ?? errors[`personnel[${i}].role_other`]}</p>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button type="button" onClick={() => onChange(removeAt(value, i))} className="text-xs text-ops-danger hover:underline">Remove</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
