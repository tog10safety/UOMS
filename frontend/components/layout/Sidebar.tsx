import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';

import { mrmApi } from '@/api/mrmApi';
import { useMrmMe } from '@/components/mrm/useMrm';
import type { WorkQueue } from '@/types/mrm';

interface NavItem {
  label: string;
  path: string;
  icon: string;
  enabled: boolean;
  /** Which work-queue counter to show as a badge. */
  badge?: 'forms' | 'feedback';
  /** Only for administrators / unit safety officers. */
  safetyOnly?: boolean;
  /** Indented sub-item of the Missions group. */
  sub?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { label: 'Dashboard', path: '/', icon: '◆', enabled: true },
  { label: 'Personnel', path: '/personnel', icon: '◈', enabled: true },
  { label: 'Vehicles', path: '/vehicles', icon: '▲', enabled: true },
  { label: 'Aircraft', path: '/aircraft', icon: '✈', enabled: true },
  { label: 'Missions', path: '/missions', icon: '⚑', enabled: true },
  { label: 'MRM Forms', path: '/mrm', icon: '▧', enabled: true, badge: 'forms', sub: true },
  { label: 'Hazard Registry', path: '/mrm/hazards', icon: '⚠', enabled: true, sub: true },
  { label: 'MRM Feedback', path: '/mrm/feedback', icon: '✎', enabled: true, badge: 'feedback', sub: true },
  { label: 'Safety Office', path: '/mrm/safety', icon: '⛨', enabled: true, safetyOnly: true, sub: true },
  { label: 'Armory', path: '/armory', icon: '⛊', enabled: true },
  { label: 'Inventory', path: '/inventory', icon: '▣', enabled: true },
  { label: 'GIS / Mapping', path: '/gis', icon: '⊕', enabled: true },
  { label: 'Reports', path: '/reports', icon: '▤', enabled: true },
  { label: 'User Management', path: '/admin/users', icon: '⚙', enabled: true },
  { label: 'Units', path: '/admin/units', icon: '⌂', enabled: true },
];

export default function Sidebar() {
  const me = useMrmMe();
  const [queue, setQueue] = useState<WorkQueue | null>(null);

  useEffect(() => {
    const load = () => mrmApi.workQueue().then(setQueue).catch(() => {});
    load();
    const timer = setInterval(load, 60_000);
    return () => clearInterval(timer);
  }, []);

  const badgeFor = (item: NavItem) => {
    if (!queue) return 0;
    if (item.badge === 'forms') return queue.needs_revision + queue.awaiting_my_review + queue.awaiting_my_approval + (queue.needs_authority_assignment ?? 0);
    if (item.badge === 'feedback') return queue.feedback_to_give + (queue.feedback_to_review ?? 0);
    return 0;
  };

  return (
    <aside className="flex h-screen w-60 flex-shrink-0 flex-col border-r border-ops-border bg-ops-panel">
      <div className="flex items-center gap-2 border-b border-ops-border px-5 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-md bg-ops-accent/10 font-mono text-lg font-bold text-ops-accent">
          U
        </div>
        <div>
          <p className="text-sm font-bold leading-tight text-ops-text">UOMS</p>
          <p className="text-[10px] leading-tight text-ops-textDim">Unit Operations</p>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4">
        {NAV_ITEMS.filter((item) => !item.safetyOnly || me?.is_admin || me?.is_safety_officer).map((item) =>
          item.enabled ? (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === '/' || item.path === '/mrm'}
              className={({ isActive }) =>
                `mb-1 flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors ${item.sub ? 'ml-4 py-1.5 text-[13px]' : ''} ${
                  isActive
                    ? 'bg-ops-accent/10 text-ops-accent'
                    : 'text-ops-textDim hover:bg-ops-panelLight hover:text-ops-text'
                }`
              }
            >
              <span className="w-4 text-center">{item.icon}</span>
              <span className="flex-1">{item.label}</span>
              {badgeFor(item) > 0 && (
                <span className="rounded-full bg-ops-warning px-1.5 py-0.5 font-mono text-[10px] font-bold leading-none text-ops-bg">{badgeFor(item)}</span>
              )}
            </NavLink>
          ) : (
            <div
              key={item.path}
              title="Coming in a later phase"
              className="mb-1 flex cursor-not-allowed items-center gap-3 rounded-md px-3 py-2 text-sm text-ops-textDim/40"
            >
              <span className="w-4 text-center">{item.icon}</span>
              {item.label}
            </div>
          ),
        )}
      </nav>

      <div className="border-t border-ops-border px-4 py-3 text-[10px] text-ops-textDim">
        UOMS v1.0.0 — Phase 1
      </div>
    </aside>
  );
}
