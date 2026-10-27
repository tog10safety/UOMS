import { Outlet, useLocation } from 'react-router-dom';

import AccountModal from '@/components/common/AccountModal';
import { useAuth } from '@/contexts/AuthContext';

import Header from './Header';
import Sidebar from './Sidebar';

const TITLES: Record<string, string> = {
  '/': 'Operations Dashboard',
  '/personnel': 'Personnel Management',
  '/vehicles': 'Vehicle Tracking and Monitoring',
  '/aircraft': 'Aircraft Flying Monitoring',
  '/missions': 'Mission Risk Management',
  '/armory': 'Armory Management',
  '/inventory': 'Inventory Management',
  '/gis': 'GIS / Operational Mapping',
  '/reports': 'Reports',
  '/admin/users': 'User & Role Management',
  '/admin/units': 'Unit Management',
};

export default function DashboardLayout() {
  const location = useLocation();
  const { user } = useAuth();
  const title = location.pathname.startsWith('/missions/') ? 'Mission Detail' : TITLES[location.pathname] ?? 'UOMS';

  return (
    <div className="flex h-screen overflow-hidden bg-ops-bg">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header title={title} />
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
      {/* Accounts created by an administrator must set their own password before doing anything else. */}
      {user?.must_change_password && <AccountModal forcePasswordChange onClose={() => undefined} />}
    </div>
  );
}
