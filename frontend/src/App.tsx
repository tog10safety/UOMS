import { Navigate, Route, Routes } from 'react-router-dom';

import ProtectedRoute from '@/components/common/ProtectedRoute';
import DashboardLayout from '@/components/layout/DashboardLayout';
import Aircraft from '@/pages/Aircraft';
import Armory from '@/pages/Armory';
import Dashboard from '@/pages/Dashboard';
import Gis from '@/pages/Gis';
import Inventory from '@/pages/Inventory';
import Login from '@/pages/Login';
import MissionDetail from '@/pages/MissionDetail';
import Missions from '@/pages/Missions';
import MissionEditor from '@/pages/missions/MissionEditor';
import HazardRegistry from '@/pages/mrm/HazardRegistry';
import MrmFeedback from '@/pages/mrm/MrmFeedback';
import MrmFormDetail from '@/pages/mrm/MrmFormDetail';
import MrmFormEditor from '@/pages/mrm/MrmFormEditor';
import MrmForms from '@/pages/mrm/MrmForms';
import MrmSafety from '@/pages/mrm/MrmSafety';
import Personnel from '@/pages/Personnel';
import Reports from '@/pages/Reports';
import UserManagement from '@/pages/UserManagement';
import Units from '@/pages/Units';
import Vehicles from '@/pages/Vehicles';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<DashboardLayout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/personnel" element={<Personnel />} />
          <Route path="/vehicles" element={<Vehicles />} />
          <Route path="/aircraft" element={<Aircraft />} />
          <Route path="/missions" element={<Missions />} />
          <Route path="/missions/new" element={<MissionEditor />} />
          <Route path="/missions/:id/edit" element={<MissionEditor />} />
          <Route path="/missions/:id" element={<MissionDetail />} />
          <Route path="/mrm" element={<MrmForms />} />
          <Route path="/mrm/new" element={<MrmFormEditor />} />
          <Route path="/mrm/hazards" element={<HazardRegistry />} />
          <Route path="/mrm/feedback" element={<MrmFeedback />} />
          <Route path="/mrm/safety" element={<MrmSafety />} />
          <Route path="/mrm/:id" element={<MrmFormDetail />} />
          <Route path="/mrm/:id/edit" element={<MrmFormEditor />} />
          <Route path="/armory" element={<Armory />} />
          <Route path="/inventory" element={<Inventory />} />
          <Route path="/gis" element={<Gis />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/admin/users" element={<UserManagement />} />
          <Route path="/admin/units" element={<Units />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
